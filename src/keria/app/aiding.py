# -*- encoding: utf-8 -*-
"""
KERIA
keria.app.ending module

"""
import json
from urllib.parse import urlparse

import falcon
from keri import kering
from keri.app import habbing
from keri.app.keeping import Algos
from keri.core import coring
from keri.core.coring import Ilks
from keri.db import dbing
from keri.help import ogler

from ..core import longrunning, httping
from ..core.eventing import cloneAid

logger = ogler.getLogger()


def loadEnds(app, agency):
    agentEnd = AgentResourceEnd(agency=agency)
    app.add_route("/agent/{caid}", agentEnd)

    aidsEnd = IdentifierCollectionEnd()
    app.add_route("/identifiers", aidsEnd)
    aidEnd = IdentifierResourceEnd()
    app.add_route("/identifiers/{name}", aidEnd)

    aidOOBIsEnd = IdentifierOOBICollectionEnd()
    app.add_route("/identifiers/{name}/oobis", aidOOBIsEnd)

    endRolesEnd = EndRoleCollectionEnd()
    app.add_route("/identifiers/{name}/endroles", endRolesEnd)

    endRoleEnd = EndRoleResourceEnd()
    app.add_route("/identifiers/{name}/endroles/{cid}/{role}/{eid}", endRoleEnd)


class AgentResourceEnd:
    """ Resource class for getting agent specific launch information """

    def __init__(self, agency):
        self.agency = agency

    def on_get(self, _, rep, caid):
        """ GET endpoint for Keystores

        Get keystore status

        Args:
            _: falcon.Request HTTP request
            rep: falcon.Response HTTP response
            caid(str): qb64 identifier prefix of Controller

        """
        agent = self.agency.get(caid)
        if agent is None:
            raise falcon.HTTPNotFound(description=f"not agent found for controller {caid}")

        kel = cloneAid(db=agent.hby.db, pre=agent.pre)
        pidx = agent.hby.db.habs.cntAll()
        body = dict(kel=kel, pidx=pidx)

        if (ctrlHab := agent.hby.habByName(agent.caid, ns="agent")) is not None:
            body["ridx"] = ctrlHab.kever.sn

        rep.content_type = "application/json"
        rep.data = json.dumps(body).encode("utf-8")
        rep.status = falcon.HTTP_200


class IdentifierCollectionEnd:
    """ Resource class for creating and managing identifiers """

    @staticmethod
    def on_get(req, rep):
        """ Identifier List GET endpoint

        Parameters:
            req: falcon.Request HTTP request
            rep: falcon.Response HTTP response

        """
        agent = req.context.agent
        res = []

        for pre, hab in agent.hby.habs.items():
            data = info(hab, agent.remoteMgr)
            res.append(data)

        rep.status = falcon.HTTP_200
        rep.content_type = "application/json"
        rep.data = json.dumps(res).encode("utf-8")

    @staticmethod
    def on_post(req, rep):
        """ Inception event POST endpoint

        Parameters:
            req (Request): falcon.Request HTTP request object
            rep (Response): falcon.Response HTTP response object

        """
        agent = req.context.agent
        try:
            body = req.get_media()
            icp = httping.getRequiredParam(body, "icp")
            name = httping.getRequiredParam(body, "name")
            sigs = httping.getRequiredParam(body, "sigs")

            serder = coring.Serder(ked=icp)

            sigers = [coring.Siger(qb64=sig) for sig in sigs]

            # client is requesting agent to join multisig group
            if "group" in body:
                group = body["group"]

                if "mhab" not in group:
                    raise falcon.HTTPBadRequest(description=f'required field "mhab" missing from body.group')
                mpre = group["mhab"]["prefix"]

                if mpre not in agent.hby.habs:
                    raise falcon.HTTPBadRequest(description=f'signing member {mpre} not a local AID')
                mhab = agent.hby.habs[mpre]

                if "keys" not in group:
                    raise falcon.HTTPBadRequest(description=f'required field "keys" missing from body.group')
                keys = group["keys"]
                verfers = [coring.Verfer(qb64=key) for key in keys]

                if mhab.kever.fetchLatestContribTo(verfers=verfers) is None:
                    raise falcon.HTTPBadRequest(description=f"Member hab={mhab.pre} not a participant in "
                                                            f"event for this group hab.")

                if "ndigs" not in group:
                    raise falcon.HTTPBadRequest(description=f'required field "ndigs" missing from body.group')
                ndigs = group["ndigs"]
                digers = [coring.Diger(qb64=ndig) for ndig in ndigs]

                smids = httping.getRequiredParam(body, "smids")
                rmids = httping.getRequiredParam(body, "rmids")

                hab = agent.hby.makeSignifyGroupHab(name, mhab=mhab, serder=serder, sigers=sigers)
                try:
                    agent.inceptGroup(pre=serder.pre, mpre=mhab.pre, verfers=verfers, digers=digers)
                except ValueError as e:
                    agent.hby.deleteHab(name=name)
                    raise falcon.HTTPInternalServerError(description=f"{e.args[0]}")

                # Generate response, a long running operaton indicator for the type
                agent.groups.append(dict(pre=hab.pre, serder=serder, sigers=sigers, smids=smids, rmids=rmids))
                op = agent.monitor.submit(serder.pre, longrunning.OpTypes.group, metadata=dict(sn=0))

                rep.content_type = "application/json"
                rep.status = falcon.HTTP_202
                rep.data = op.to_json().encode("utf-8")

            else:
                # client is requesting that the Agent track the Salty parameters
                if Algos.salty in body:
                    salt = body[Algos.salty]
                    hab = agent.hby.makeSignifyHab(name, serder=serder, sigers=sigers)
                    try:
                        agent.inceptSalty(pre=serder.pre, **salt)
                    except ValueError as e:
                        agent.hby.deleteHab(name=name)
                        raise falcon.HTTPInternalServerError(description=f"{e.args[0]}")

                # client is storing encrypted randomly generated key material on agent
                elif Algos.randy in body:
                    rand = body[Algos.randy]
                    hab = agent.hby.makeSignifyHab(name, serder=serder, sigers=sigers)
                    try:
                        agent.inceptRandy(pre=serder.pre, verfers=serder.verfers, digers=serder.digers, **rand)
                    except ValueError as e:
                        agent.hby.deleteHab(name=name)
                        raise falcon.HTTPInternalServerError(description=f"{e.args[0]}")

                else:
                    raise falcon.HTTPBadRequest(
                        description="invalid request: one of group, rand or salt field required")

                # create Hab and incept the key store (if any)
                # Generate response, either the serder or a long running operaton indicator for the type
                rep.content_type = "application/json"
                if hab.kever.delegator:
                    agent.anchors.append(dict(pre=hab.pre, sn=0))
                    op = agent.monitor.submit(hab.kever.prefixer.qb64, longrunning.OpTypes.delegation,
                                              metadata=dict(sn=0))
                    rep.status = falcon.HTTP_202
                    rep.data = op.to_json().encode("utf-8")

                elif hab.kever.wits:
                    agent.witners.append(dict(serder=serder))
                    op = agent.monitor.submit(hab.kever.prefixer.qb64, longrunning.OpTypes.witness,
                                              metadata=dict(sn=0))
                    rep.status = falcon.HTTP_202
                    rep.data = op.to_json().encode("utf-8")

                else:
                    rep.status = falcon.HTTP_200
                    rep.data = serder.raw

        except (kering.AuthError, ValueError) as e:
            rep.status = falcon.HTTP_400
            rep.text = e.args[0]


class IdentifierResourceEnd:
    """ Resource class for updating and deleting identifiers """

    @staticmethod
    def on_get(req, rep, name):
        """ Identifier GET endpoint

        Parameters:
            req: falcon.Request HTTP request
            rep: falcon.Response HTTP response
            name (str): human readable name for Hab to GET

        """
        agent = req.context.agent
        hab = agent.hby.habByName(name)
        if hab is None:
            rep.status = falcon.HTTP_400
            return

        data = info(hab, agent.remoteMgr, full=True)
        rep.status = falcon.HTTP_200
        rep.content_type = "application/json"
        rep.data = json.dumps(data).encode("utf-8")

    def on_put(self, req, rep, name):
        """ Identifier UPDATE endpoint

        Parameters:
            req (Request): falcon.Request HTTP request object
            rep (Response): falcon.Response HTTP response object
            name (str): human readable name for Hab to rotate or interact

        """
        agent = req.context.agent
        try:
            body = req.get_media()
            typ = Ilks.ixn if req.params.get("type") == "ixn" else Ilks.rot

            if typ in (Ilks.rot,):
                data = self.rotate(agent, name, body)
            else:
                data = self.interact(agent, name, body)

            rep.status = falcon.HTTP_200
            rep.content_type = "application/json"
            rep.data = data

        except (kering.AuthError, ValueError) as e:
            raise falcon.HTTPBadRequest(description=e.args[0])

    @staticmethod
    def rotate(agent, name, body):
        hab = agent.hby.habByName(name)
        if hab is None:
            raise falcon.HTTPNotFound(title=f"No AID with name {name} found")

        rot = body.get("rot")
        if rot is None:
            raise falcon.HTTPBadRequest(title="invalid rotation",
                                        description=f"required field 'rot' missing from request")

        sigs = body.get("sigs")
        if sigs is None or len(sigs) == 0:
            raise falcon.HTTPBadRequest(title="invalid rotation",
                                        description=f"required field 'sigs' missing from request")

        serder = coring.Serder(ked=rot)
        sigers = [coring.Siger(qb64=sig) for sig in sigs]

        hab.rotate(serder=serder, sigers=sigers)

        if Algos.salty in body:
            salt = body[Algos.salty]
            keeper = agent.remoteMgr.get(Algos.salty)

            try:
                keeper.rotate(pre=serder.pre, **salt)
            except ValueError as e:
                agent.hby.deleteHab(name=name)
                raise falcon.HTTPInternalServerError(description=f"{e.args[0]}")

        elif Algos.randy in body:
            rand = body[Algos.randy]
            keeper = agent.remoteMgr.get(Algos.randy)

            keeper.rotate(pre=serder.pre, verfers=serder.verfers, digers=serder.digers, **rand)

        elif Algos.group in body:
            keeper = agent.remoteMgr.get(Algos.group)

            keeper.rotate(pre=serder.pre, verfers=serder.verfers, digers=serder.digers)

            smids = httping.getRequiredParam(body, "smids")
            rmids = httping.getRequiredParam(body, "rmids")

            agent.groups.append(dict(pre=hab.pre, serder=serder, sigers=sigers, smids=smids, rmids=rmids))
            op = agent.monitor.submit(serder.pre, longrunning.OpTypes.group, metadata=dict(sn=serder.sn))

            return op.to_json().encode("utf-8")

        if hab.kever.delegator:
            agent.anchors.append(dict(alias=name, pre=hab.pre, sn=0))
            op = agent.monitor.submit(hab.kever.prefixer.qb64, longrunning.OpTypes.delegation,
                                      metadata=dict(sn=hab.kever.sn))
            return op.to_json().encode("utf-8")

        if hab.kever.wits:
            agent.witners.append(dict(serder=serder))
            op = agent.monitor.submit(hab.kever.prefixer.qb64, longrunning.OpTypes.witness,
                                      metadata=dict(sn=hab.kever.sn))
            return op.to_json().encode("utf-8")

        return serder.raw

    @staticmethod
    def interact(agent, name, body):
        hab = agent.hby.habByName(name)
        if hab is None:
            raise falcon.HTTPNotFound(title=f"No AID {name} found")

        ixn = body.get("ixn")
        if ixn is None:
            raise falcon.HTTPBadRequest(title="invalid interaction",
                                        description=f"required field 'ixn' missing from request")

        sigs = body.get("sigs")
        if sigs is None or len(sigs) == 0:
            raise falcon.HTTPBadRequest(title="invalid interaction",
                                        description=f"required field 'sigs' missing from request")

        serder = coring.Serder(ked=ixn)
        sigers = [coring.Siger(qb64=sig) for sig in sigs]

        hab.interact(serder=serder, sigers=sigers)

        if "group" in body:
            agent.groups.append(dict(pre=hab.pre, serder=serder, sigers=sigers))
            op = agent.monitor.submit(serder.pre, longrunning.OpTypes.group, metadata=dict(sn=serder.sn))

            return op.to_json().encode("utf-8")

        if hab.kever.wits:
            agent.witners.append(dict(serder=serder))
            op = agent.monitor.submit(hab.kever.prefixer.qb64, longrunning.OpTypes.delegation,
                                      metadata=dict(sn=hab.kever.sn))
            return op.to_json().encode("utf-8")

        return serder.raw


def info(hab, rm, full=False):
    data = dict(
        name=hab.name,
        prefix=hab.pre,
    )

    if not isinstance(hab, habbing.SignifyHab):
        raise kering.ConfigurationError("agent only allows SignifyHab instances")

    keeper = rm.get(pre=hab.pre)
    data.update(keeper.params(pre=hab.pre))
    if isinstance(hab, habbing.SignifyGroupHab):
        data["group"]["mhab"] = info(hab.mhab, rm, full)

    if hab.accepted and full:
        kever = hab.kevers[hab.pre]
        data["transferable"] = kever.transferable
        data["state"] = kever.state().ked
        dgkey = dbing.dgKey(kever.prefixer.qb64b, kever.serder.saidb)
        wigs = hab.db.getWigs(dgkey)
        data["windexes"] = [coring.Siger(qb64b=bytes(wig)).index for wig in wigs]

    return data


class IdentifierOOBICollectionEnd:
    """
      This class represents the OOBI subresource collection endpoint for Identfiiers

    """

    @staticmethod
    def on_get(req, rep, name):
        """ Identifier GET endpoint

        Parameters:
            req: falcon.Request HTTP request
            rep: falcon.Response HTTP response
            name (str): human readable name for Hab to GET

        """
        agent = req.context.agent
        hab = agent.hby.habByName(name)
        if not hab:
            raise falcon.HTTPNotFound(f"invalid alias {name}")

        if "role" not in req.params:
            raise falcon.HTTPBadRequest("role parameter required")

        role = req.params["role"]

        res = dict(role=role)
        if role in (kering.Roles.witness,):  # Fetch URL OOBIs for all witnesses
            oobis = []
            for wit in hab.kever.wits:
                urls = hab.fetchUrls(eid=wit, scheme=kering.Schemes.http)
                if not urls:
                    raise falcon.HTTPNotFound(f"unable to query witness {wit}, no http endpoint")

                up = urlparse(urls[kering.Schemes.http])
                oobis.append(f"{kering.Schemes.http}://{up.hostname}:{up.port}/oobi/{hab.pre}/witness/{wit}")
            res["oobis"] = oobis
        elif role in (kering.Roles.controller,):  # Fetch any controller URL OOBIs
            oobis = []
            urls = hab.fetchUrls(eid=hab.pre, scheme=kering.Schemes.http)
            if not urls:
                raise falcon.HTTPNotFound(f"unable to query controller {hab.pre}, no http endpoint")

            up = urlparse(urls[kering.Schemes.http])
            oobis.append(f"{kering.Schemes.http}://{up.hostname}:{up.port}/oobi/{hab.pre}/controller")
            res["oobis"] = oobis
        elif role in (kering.Roles.agent,):  # Fetch URL OOBIs for all witnesses
            roleUrls = hab.fetchRoleUrls(cid=hab.pre, role=kering.Roles.agent, scheme=kering.Schemes.http)
            aoobis = roleUrls[kering.Roles.agent]

            oobis = list()
            for agent in set(aoobis.keys()):
                murls = aoobis.naball(agent)
                for murl in murls:
                    for url in murl.naball(kering.Schemes.http):
                        up = urlparse(url)
                        oobis.append(f"{kering.Schemes.http}://{up.hostname}:{up.port}/oobi/{hab.pre}/agent/{agent}")

            res["oobis"] = oobis
        else:
            raise falcon.HTTPBadRequest(description=f"unsupport role type {role} for oobi request")

        rep.status = falcon.HTTP_200
        rep.content_type = "application/json"
        rep.data = json.dumps(res).encode("utf-8")


class EndRoleCollectionEnd:

    @staticmethod
    def on_post(req, rep, name):
        """

        Args:
            req (Request): Falcon HTTP request object
            rep (Response): Falcon HTTP response object
            name (str): human readable alias for AID

        """
        agent = req.context.agent
        body = req.get_media()

        rpy = httping.getRequiredParam(body, "rpy")
        rsigs = httping.getRequiredParam(body, "sigs")

        rserder = coring.Serder(ked=rpy)
        data = rserder.ked['a']
        pre = data['cid']
        role = data['role']
        eid = data['eid']

        hab = agent.hby.habByName(name)
        if hab is None:
            raise falcon.errors.HTTPNotFound(f"invalid alias {name}")

        if pre != hab.pre:
            raise falcon.errors.HTTPBadRequest(f"error trying to create end role for unknown local AID {pre}")

        rsigers = [coring.Siger(qb64=rsig) for rsig in rsigs]
        tsg = (hab.kever.prefixer, coring.Seqner(sn=hab.kever.sn), hab.kever.serder.saider, rsigers)
        agent.hby.rvy.processReply(rserder, tsgs=[tsg])

        msg = hab.loadEndRole(cid=pre, role=role, eid=eid)
        if msg is None:
            raise falcon.errors.HTTPBadRequest(f"invalid end role rpy={rserder.ked}")

        rep.status = falcon.HTTP_200
        rep.content_type = "application/json"
        rep.data = rserder.raw


class EndRoleResourceEnd:

    def on_delete(self, req, rep):
        pass