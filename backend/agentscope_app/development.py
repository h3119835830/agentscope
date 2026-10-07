"""Explicit loopback-only, passwordless control access for local development."""
from ipaddress import ip_address
from urllib.parse import urlsplit
from .config import DEV_NO_AUTH


def passwordless(request):
    if not DEV_NO_AUTH or not request.client:
        return False
    try:
        local_peer = ip_address(request.client.host).is_loopback
    except ValueError:
        return False
    local_hosts = {'localhost', '127.0.0.1', '::1'}
    if not local_peer or request.url.hostname not in local_hosts:
        return False
    origin = request.headers.get('origin')
    if not origin: return True
    try:
        parsed = urlsplit(origin)
        return (parsed.scheme, parsed.netloc) == (request.url.scheme, request.url.netloc)
    except ValueError:
        return False
