"""Optional SNMP client for HP/Aruba ProCurve switches."""
from __future__ import annotations

import asyncio
import logging
from functools import partial

_LOGGER = logging.getLogger(__name__)

# HP hpicfCpuStat MIB — CPU utilisation (integer percent, 0-100)
_OID_CPU = "1.3.6.1.4.1.11.2.14.11.5.1.9.6.1.0"
# HP hpicfMemory MIB — free and used bytes in the first memory pool
_OID_MEM_FREE = "1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.6.1"
_OID_MEM_USED = "1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.7.1"


def _snmp_get_sync(host: str, port: int, community: str, oid: str) -> int | None:
    from pysnmp.hlapi import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        getCmd,
    )

    for errorIndication, errorStatus, errorIndex, varBinds in getCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((host, port), timeout=5, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
    ):
        if errorIndication:
            _LOGGER.debug("SNMP error (%s): %s", oid, errorIndication)
            return None
        if errorStatus:
            _LOGGER.debug("SNMP errorStatus (%s): %s", oid, errorStatus.prettyPrint())
            return None
        for varBind in varBinds:
            try:
                return int(varBind[1])
            except (TypeError, ValueError):
                return None
    return None


class SnmpClient:
    """Reads CPU and memory stats from an HP/Aruba switch via SNMPv2c."""

    def __init__(self, host: str, community: str, port: int = 161) -> None:
        self._host = host
        self._community = community
        self._port = port

    async def _get(self, oid: str) -> int | None:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, partial(_snmp_get_sync, self._host, self._port, self._community, oid)
            )
        except Exception:
            _LOGGER.debug("SNMP exception for OID %s", oid, exc_info=True)
            return None

    async def get_cpu_percent(self) -> int | None:
        return await self._get(_OID_CPU)

    async def get_memory_percent(self) -> int | None:
        free = await self._get(_OID_MEM_FREE)
        used = await self._get(_OID_MEM_USED)
        if free is None or used is None or (free + used) == 0:
            return None
        return int(used * 100 / (free + used))
