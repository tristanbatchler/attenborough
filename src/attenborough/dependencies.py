from ipaddress import AddressValueError, IPv4Address, IPv6Address

from fastapi import HTTPException
from fastapi.requests import Request
from pydantic.networks import IPvAnyAddress
from starlette.status import HTTP_400_BAD_REQUEST

from attenborough import settings


def str2ip(ip_str: str) -> IPvAnyAddress:
    try:
        return IPv4Address(ip_str)
    except AddressValueError:
        try:
            return IPv6Address(ip_str)
        except AddressValueError:
            raise AddressValueError(f"{ip_str} is not a value IP address")

async def get_request_origin(request: Request) -> IPvAnyAddress:
    if (real_ip := request.headers.get(settings.REAL_IP_HEADER)):
        return str2ip(real_ip)
    
    if not request.client:
        raise HTTPException(HTTP_400_BAD_REQUEST, "IP address undetectable")
    
    return str2ip(request.client.host)
    

