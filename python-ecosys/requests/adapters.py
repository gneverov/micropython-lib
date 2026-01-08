"""
requests.adapters
~~~~~~~~~~~~~~~~~

This module contains the transport adapters that Requests uses to define
and maintain connections.
"""

import socket
import time

try:
    from http.client import HTTPConnection, HTTPSConnection, HTTPException
except ImportError:
    from http import client as http_client
    HTTPConnection = http_client.HTTPConnection
    HTTPSConnection = http_client.HTTPSConnection
    HTTPException = http_client.HTTPException

try:
    import ssl
except ImportError:
    ssl = None

from .cookies import CookieJar
from .exceptions import (
    ConnectionError, ConnectTimeout, ReadTimeout, SSLError,
    ProxyError, RetryError, InvalidURL, TooManyRedirects,
    InvalidProxyURL
)
from .models import Response
from .structures import CaseInsensitiveDict
from .utils import default_headers
from urllib.parse import urlparse

try:
    from binascii import b2a_base64
except ImportError:
    import binascii
    b2a_base64 = binascii.b2a_base64

DEFAULT_POOLSIZE = 10
DEFAULT_RETRIES = 0
DEFAULT_TIMEOUT = None


class HTTPAdapter:
    """The built-in HTTP Adapter for http.client.

    Provides a general-case interface for Requests sessions to contact HTTP
    servers using http.client instead of urllib3.
    """

    def __init__(self, pool_connections=DEFAULT_POOLSIZE,
                 pool_maxsize=DEFAULT_POOLSIZE, max_retries=DEFAULT_RETRIES):
        self.max_retries = max_retries
        self.pool_connections = pool_connections
        self.pool_maxsize = pool_maxsize

        # Connection pool (simple dict-based implementation)
        self._pool = {}

    def _parse_proxy(self, proxy_url):
        """Parse a proxy URL and return connection details.

        Returns: (scheme, hostname, port, username, password)
        """
        if not proxy_url:
            return None

        try:
            parsed = urlparse(proxy_url)
            scheme = parsed.scheme
            hostname = parsed.hostname
            port = parsed.port

            # Extract username and password from netloc if present
            username = None
            password = None
            netloc = parsed.netloc

            if '@' in netloc:
                userinfo, _ = netloc.split('@', 1)
                if ':' in userinfo:
                    username, password = userinfo.split(':', 1)
                else:
                    username = userinfo

            # Default ports
            if not port:
                port = 8080 if scheme == 'http' else 1080

            return (scheme, hostname, port, username, password)
        except Exception as e:
            raise InvalidProxyURL('Invalid proxy URL {!r}: {}'.format(proxy_url, e))

    def _get_proxy_headers(self, username, password):
        """Generate proxy authentication headers."""
        if not username:
            return {}

        credentials = '{}:{}'.format(username, password or '')
        if isinstance(credentials, str):
            credentials = credentials.encode('latin1')

        # Base64 encode
        encoded = b2a_base64(credentials).strip()
        if isinstance(encoded, bytes):
            encoded = encoded.decode('ascii')

        return {'Proxy-Authorization': 'Basic {}'.format(encoded)}

    def _get_connection(self, url, verify=True, cert=None, timeout=None, proxy=None):
        """Get a connection from the pool or create a new one.

        Args:
            url: Target URL
            verify: SSL verification (True/False or path to CA bundle)
            cert: Client certificate (path or (cert, key) tuple)
            timeout: Connection timeout
            proxy: Proxy URL (e.g., 'http://proxy.example.com:8080')

        Returns:
            HTTPConnection or HTTPSConnection object
        """
        parsed = urlparse(url)
        scheme = parsed.scheme
        hostname = parsed.hostname
        port = parsed.port

        # Parse proxy if provided
        proxy_info = self._parse_proxy(proxy) if proxy else None

        # Create connection key (include proxy in key for pooling)
        if proxy_info:
            key = (scheme, hostname, port, proxy)
        else:
            key = (scheme, hostname, port)

        # Check if we have a cached connection
        if key in self._pool:
            conn = self._pool[key]
            # Check if connection is still alive
            try:
                # Test connection by checking socket
                if hasattr(conn, 'sock') and conn.sock:
                    return conn, proxy_info
            except:
                pass

        # Create new connection
        if proxy_info:
            # Using proxy
            proxy_scheme, proxy_host, proxy_port, proxy_user, proxy_pass = proxy_info

            if scheme == 'https':
                # HTTPS through HTTP proxy requires CONNECT tunnel
                conn = self._create_https_proxy_connection(
                    hostname, port, proxy_host, proxy_port,
                    proxy_user, proxy_pass, verify, cert, timeout
                )
            else:
                # HTTP through proxy - connect to proxy directly
                conn = HTTPConnection(proxy_host, proxy_port, timeout=timeout)
        else:
            # Direct connection (no proxy)
            if scheme == 'https':
                if ssl is None:
                    raise SSLError('SSL/TLS support is not available')

                # Create SSL context
                if verify:
                    if isinstance(verify, str):
                        # Path to CA bundle
                        context = ssl.create_default_context(cafile=verify)
                    else:
                        # Use default verification
                        context = ssl.create_default_context()
                        context.check_hostname = True
                        context.verify_mode = ssl.CERT_REQUIRED
                else:
                    # Disable verification
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE

                # Load client certificate if provided
                if cert:
                    if isinstance(cert, tuple):
                        context.load_cert_chain(cert[0], cert[1])
                    else:
                        context.load_cert_chain(cert)

                try:
                    conn = HTTPSConnection(hostname, port, timeout=timeout,
                                           context=context)
                except TypeError:
                    # Fallback for older Python versions
                    conn = HTTPSConnection(hostname, port, timeout=timeout)
            else:
                conn = HTTPConnection(hostname, port, timeout=timeout)

        # Cache connection
        self._pool[key] = conn

        return conn, proxy_info

    def _create_https_proxy_connection(self, hostname, port, proxy_host, proxy_port,
                                       proxy_user, proxy_pass, verify, cert, timeout):
        """Create HTTPS connection through HTTP proxy using CONNECT tunnel."""
        if ssl is None:
            raise SSLError('SSL/TLS support is not available')

        # First, connect to the proxy
        conn = HTTPConnection(proxy_host, proxy_port, timeout=timeout)

        try:
            # Send CONNECT request to establish tunnel
            connect_headers = {}

            # Add proxy authentication if needed
            if proxy_user:
                proxy_auth_headers = self._get_proxy_headers(proxy_user, proxy_pass)
                connect_headers.update(proxy_auth_headers)

            # Send CONNECT
            conn.set_tunnel(hostname, port, connect_headers)

            # Create SSL context
            if verify:
                if isinstance(verify, str):
                    context = ssl.create_default_context(cafile=verify)
                else:
                    context = ssl.create_default_context()
                    context.check_hostname = True
                    context.verify_mode = ssl.CERT_REQUIRED
            else:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            # Load client certificate if provided
            if cert:
                if isinstance(cert, tuple):
                    context.load_cert_chain(cert[0], cert[1])
                else:
                    context.load_cert_chain(cert)

            # Wrap connection with SSL
            # For HTTPSConnection with set_tunnel, the SSL wrapping happens on connect()
            try:
                https_conn = HTTPSConnection(proxy_host, proxy_port, timeout=timeout,
                                             context=context)
                https_conn.set_tunnel(hostname, port, connect_headers)
                return https_conn
            except TypeError:
                # Fallback for older Python versions
                https_conn = HTTPSConnection(proxy_host, proxy_port, timeout=timeout)
                https_conn.set_tunnel(hostname, port, connect_headers)
                return https_conn

        except Exception as e:
            try:
                conn.close()
            except:
                pass
            raise ProxyError('Failed to establish CONNECT tunnel through proxy: {}'.format(e))

    def _send_request(self, conn, request, timeout=None, proxy_info=None):
        """Send a request using the connection.

        Args:
            conn: HTTPConnection or HTTPSConnection
            request: PreparedRequest object
            timeout: Read timeout
            proxy_info: Tuple of (scheme, host, port, user, pass) if using proxy

        Returns:
            HTTPResponse object
        """
        parsed = urlparse(request.url)

        # For HTTP requests through a proxy, use absolute URL
        # For HTTPS through proxy or direct connections, use relative path
        if proxy_info and parsed.scheme == 'http':
            # HTTP through proxy: send full URL
            path = request.url
        else:
            # Direct connection or HTTPS through proxy: send path only
            path = parsed.path
            if parsed.query:
                path += '?' + parsed.query

        # Add proxy authentication header for HTTP through proxy
        headers = dict(request.headers)
        if proxy_info and parsed.scheme == 'http':
            proxy_scheme, proxy_host, proxy_port, proxy_user, proxy_pass = proxy_info
            if proxy_user:
                proxy_auth_headers = self._get_proxy_headers(proxy_user, proxy_pass)
                headers.update(proxy_auth_headers)

        # Set timeout on socket if connection is established
        if timeout and hasattr(conn, 'sock') and conn.sock:
            conn.sock.settimeout(timeout)

        try:
            # Send request
            conn.request(
                request.method,
                path,
                body=request.body,
                headers=headers,
                encode_chunked=True,
            )

            # Get response
            http_response = conn.getresponse()

            return http_response

        except socket.timeout as e:
            raise ReadTimeout('Read timeout: {}'.format(e))
        except socket.error as e:
            raise ConnectionError('Connection error: {}'.format(e))
        except HTTPException as e:
            raise ConnectionError('HTTP error: {}'.format(e))

    def send(self, request, stream=False, timeout=None, verify=True, cert=None,
             proxies=None):
        """Send a PreparedRequest and return a Response.

        Args:
            request: PreparedRequest object
            stream: Whether to stream the response
            timeout: Timeout in seconds or (connect, read) tuple
            verify: SSL verification (True/False or path to CA bundle)
            cert: Client certificate (path or (cert, key) tuple)
            proxies: Dict mapping protocol to proxy URL
                     e.g., {'http': 'http://proxy:8080', 'https': 'http://proxy:8080'}

        Returns:
            Response object
        """
        # Parse timeout
        connect_timeout = None
        read_timeout = None

        if isinstance(timeout, tuple):
            connect_timeout, read_timeout = timeout
        else:
            connect_timeout = timeout
            read_timeout = timeout

        # Select proxy for this URL
        proxy = None
        if proxies:
            parsed = urlparse(request.url)
            scheme = parsed.scheme

            # Check for scheme-specific proxy
            if scheme in proxies:
                proxy = proxies[scheme]
            # Check for 'all' proxy
            elif 'all' in proxies:
                proxy = proxies['all']

        # Get connection (with proxy support)
        try:
            conn, proxy_info = self._get_connection(
                request.url,
                verify=verify,
                cert=cert,
                timeout=connect_timeout,
                proxy=proxy
            )
        except SSLError:
            raise
        except ProxyError:
            raise
        except Exception as e:
            raise ConnectionError(('Failed to get connection: {}'.format(e)))

        # Add cookies to request
        if request._cookies:
            cookie_header = '; '.join([
                '{}={}'.format(k, v)
                for k, v in request._cookies.get_cookies_for_url(request.url).items()
            ])
            if cookie_header:
                request.headers['Cookie'] = cookie_header

        # Send request
        start_time = time.time()

        try:
            http_response = self._send_request(
                conn,
                request,
                timeout=read_timeout,
                proxy_info=proxy_info
            )
        except ReadTimeout:
            raise
        except ConnectTimeout:
            raise
        except ConnectionError:
            raise
        # except Exception as e:
        #     raise ConnectionError('Failed to send request: {}'.format(e))

        elapsed = time.time() - start_time

        # Build Response object
        response = self.build_response(request, http_response, stream=stream)
        response.elapsed = elapsed

        # Extract cookies from response
        response.cookies.extract_cookies_from_response(response)

        return response

    def build_response(self, request, http_response, stream=False):
        """Build a Response object from an http.client response."""
        response = Response()

        # Store request
        response.request = request

        # Status
        response.status_code = http_response.status
        response.reason = http_response.reason

        # Headers
        response.headers = CaseInsensitiveDict()
        for key, value in http_response.getheaders():
            # Handle multiple headers with same name
            if key in response.headers:
                # Combine with comma
                response.headers[key] = response.headers[key] + ', ' + value
            else:
                response.headers[key] = value

        # URL
        response.url = request.url

        # Encoding
        from .utils import get_encoding_from_headers
        response.encoding = get_encoding_from_headers(response.headers)

        # Read response content immediately unless streaming
        if stream:
            # For streaming, store the raw response
            response.raw = http_response
        else:
            # Read all content immediately
            # try:
                response._content = http_response.read()
                response._content_consumed = True
                # Close the response to release the connection
                http_response.close()
            # except Exception as e:
            #     raise ConnectionError('Failed to read response: {}'.format(e))

        # Cookie jar
        response.cookies = CookieJar()

        return response

    def close(self):
        """Close all pooled connections."""
        for conn in self._pool.values():
            try:
                if hasattr(conn, 'close'):
                    conn.close()
            except:
                pass
        self._pool.clear()

    def __del__(self):
        """Cleanup when adapter is destroyed."""
        try:
            self.close()
        except:
            pass


class ConnectionPool:
    """Simple connection pool for reusing connections.

    This is a simplified version compared to urllib3's connection pool.
    """

    def __init__(self, scheme, host, port, maxsize=10):
        self.scheme = scheme
        self.host = host
        self.port = port
        self.maxsize = maxsize
        self.connections = []

    def get_connection(self):
        """Get a connection from the pool."""
        # Try to get an existing connection
        while self.connections:
            conn = self.connections.pop()
            # Check if still alive
            if hasattr(conn, 'sock') and conn.sock:
                return conn

        # Create new connection
        if self.scheme == 'https':
            return HTTPSConnection(self.host, self.port)
        else:
            return HTTPConnection(self.host, self.port)

    def return_connection(self, conn):
        """Return a connection to the pool."""
        if len(self.connections) < self.maxsize:
            self.connections.append(conn)
        else:
            # Pool is full, close connection
            try:
                conn.close()
            except:
                pass

    def close(self):
        """Close all connections in the pool."""
        for conn in self.connections:
            try:
                conn.close()
            except:
                pass
        self.connections.clear()
