"""
requests.auth
~~~~~~~~~~~~~

This module contains authentication handlers.
"""

import hashlib
import re
import time

try:
    from binascii import a2b_base64, b2a_base64
except ImportError:
    import binascii
    a2b_base64 = binascii.a2b_base64
    b2a_base64 = binascii.b2a_base64


class AuthBase:
    """Base class for all auth handlers."""

    def __call__(self, r):
        raise NotImplementedError('Auth hooks must be callable.')


class HTTPBasicAuth(AuthBase):
    """Attaches HTTP Basic Authentication to the given Request object."""

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def __call__(self, r):
        # Encode credentials
        credentials = '{}:{}'.format(self.username, self.password)
        if isinstance(credentials, str):
            credentials = credentials.encode('latin1')

        # Base64 encode
        encoded = b2a_base64(credentials).strip()
        if isinstance(encoded, bytes):
            encoded = encoded.decode('ascii')

        # Set Authorization header
        r.headers['Authorization'] = 'Basic {}'.format(encoded)
        return r


class HTTPProxyAuth(HTTPBasicAuth):
    """Attaches HTTP Proxy Authentication to the given Request object."""

    def __call__(self, r):
        # Encode credentials
        credentials = '{}:{}'.format(self.username, self.password)
        if isinstance(credentials, str):
            credentials = credentials.encode('latin1')

        # Base64 encode
        encoded = b2a_base64(credentials).strip()
        if isinstance(encoded, bytes):
            encoded = encoded.decode('ascii')

        # Set Proxy-Authorization header
        r.headers['Proxy-Authorization'] = 'Basic {}'.format(encoded)
        return r


class HTTPDigestAuth(AuthBase):
    """Attaches HTTP Digest Authentication to the given Request object.

    This is a simplified implementation for microcontrollers.
    """

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.last_nonce = None
        self.nonce_count = 0
        self.chal = {}

    def _parse_challenge(self, challenge):
        """Parse WWW-Authenticate digest challenge."""
        if not challenge.startswith('Digest '):
            return {}

        challenge = challenge[7:]  # Remove 'Digest '

        # Parse key=value pairs
        chal = {}
        for match in re.finditer(r'(\w+)=("[^"]*"|[^,]*)', challenge):
            key = match.group(1)
            value = match.group(2).strip('"')
            chal[key] = value

        return chal

    def _build_digest_header(self, method, url):
        """Build digest authorization header."""
        realm = self.chal.get('realm', '')
        nonce = self.chal.get('nonce', '')
        qop = self.chal.get('qop', '')
        algorithm = self.chal.get('algorithm', 'MD5').upper()
        opaque = self.chal.get('opaque', '')

        if algorithm != 'MD5':
            # Only MD5 is supported in this simplified implementation
            return None

        # Parse URL to get path
        if '://' in url:
            url = url.split('://', 1)[1]
            if '/' in url:
                url = '/' + url.split('/', 1)[1]
            else:
                url = '/'
        elif not url.startswith('/'):
            url = '/' + url

        # Calculate HA1
        a1 = '{}:{}:{}'.format(self.username, realm, self.password)
        ha1 = hashlib.md5(a1.encode('utf-8')).hexdigest()

        # Calculate HA2
        a2 = '{}:{}'.format(method, url)
        ha2 = hashlib.md5(a2.encode('utf-8')).hexdigest()

        # Calculate response
        if qop in ('auth', 'auth-int'):
            self.nonce_count += 1
            nc = '{:08x}'.format(self.nonce_count)
            cnonce = hashlib.md5(str(time.time()).encode('utf-8')).hexdigest()[:16]

            s = '{}:{}:{}:{}:{}:{}'.format(ha1, nonce, nc, cnonce, qop, ha2)
            response_hash = hashlib.md5(s.encode('utf-8')).hexdigest()

            auth_header = 'Digest username="{}", realm="{}", nonce="{}", uri="{}", response="{}", qop={}, nc={}, cnonce="{}"'.format(
                self.username, realm, nonce, url, response_hash, qop, nc, cnonce
            )
        else:
            s = '{}:{}:{}'.format(ha1, nonce, ha2)
            response_hash = hashlib.md5(s.encode('utf-8')).hexdigest()

            auth_header = 'Digest username="{}", realm="{}", nonce="{}", uri="{}", response="{}"'.format(
                self.username, realm, nonce, url, response_hash
            )

        if opaque:
            auth_header += ', opaque="{}"'.format(opaque)

        if algorithm:
            auth_header += ', algorithm={}'.format(algorithm)

        return auth_header

    def handle_401(self, r, **kwargs):
        """Handle 401 Unauthorized response by adding digest auth."""
        if 'www-authenticate' not in r.headers:
            return r

        # Parse challenge
        self.chal = self._parse_challenge(r.headers['www-authenticate'])

        if not self.chal:
            return r

        # Retry request with digest auth
        request = r.request.copy()

        # Build digest header
        auth_header = self._build_digest_header(request.method, request.url)
        if auth_header:
            request.headers['Authorization'] = auth_header

            # Re-send request
            response = r.connection.send(request, **kwargs)
            response.history.append(r)
            return response

        return r

    def __call__(self, r):
        # If we have a previous challenge, use it
        if self.chal:
            auth_header = self._build_digest_header(r.method, r.url)
            if auth_header:
                r.headers['Authorization'] = auth_header

        # Register hook to handle 401 responses
        r.register_hook('response', self.handle_401)
        return r
