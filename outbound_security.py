"""HTTPS-only public destinations, with DNS pinning and no redirects."""
import ipaddress
import socket
import time
from urllib.parse import urlsplit
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool
from requests.adapters import HTTPAdapter


def validate_public_url(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
        if parsed.port not in (None, 443):
            raise ValueError()
        host = parsed.hostname.rstrip('.').lower()
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            raise ValueError()
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addresses = {answer[4][0] for answer in answers}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise ValueError()
        return host, sorted(addresses)[0]
    except (ValueError, OSError) as error:
        raise ValueError('Use an HTTPS provider URL on a public internet address (port 443).') from error


class PinnedAdapter(HTTPAdapter):
    def __init__(self, host, address):
        self.host, self.address = host, address
        super().__init__(max_retries=0)

    def _pool(self):
        host, address = self.host, self.address
        class PinnedConnection(HTTPSConnection):
            def _new_conn(self):
                # Keep the original hostname for certificate checks and SNI.
                return socket.create_connection((address, 443), self.timeout)
        class PinnedPool(HTTPSConnectionPool):
            ConnectionCls = PinnedConnection
        return PinnedPool(host, port=443, maxsize=1, block=True)

    def get_connection(self, url, proxies=None):
        return self._pool()

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        return self._pool()


def public_request(method, url, **kwargs):
    import requests
    host, address = validate_public_url(url)
    with requests.Session() as client:
        client.trust_env = False
        client.mount('https://', PinnedAdapter(host, address))
        kwargs['allow_redirects'] = False
        kwargs['verify'] = True
        kwargs['stream'] = True
        kwargs.setdefault('timeout', (4, 15))
        response = client.request(method, url, **kwargs)
        if 300 <= response.status_code < 400:
            response.close()
            raise ValueError('Provider redirects are not allowed. Configure its final HTTPS URL.')
        chunks, size, started = [], 0, time.monotonic()
        try:
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 1024*1024 or time.monotonic() - started > 20:
                    raise ValueError('The provider response exceeded processing limits.')
                chunks.append(chunk)
            response._content = b''.join(chunks)
            response._content_consumed = True
        finally:
            response.close()
        return response
