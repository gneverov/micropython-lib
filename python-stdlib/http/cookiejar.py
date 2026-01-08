# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
http.cookiejar - HTTP cookie handling for Python

This module provides cookie handling compatible with Python's standard library
http.cookiejar module, simplified for embedded systems.

Classes:
    Cookie - Represents a single HTTP cookie
    CookieJar - Storage and management of HTTP cookies
"""

import time
from urllib.parse import urlparse


class Cookie:
    """Represents a single HTTP cookie.

    Compatible with Python's http.cookiejar.Cookie class.
    Supports both RFC 2965 and Netscape cookie attributes.

    Attributes:
        Standard cookie attributes:
            version (int): Cookie version (0 for Netscape, 1 for RFC 2965)
            name (str): Cookie name
            value (str): Cookie value
            port (str): Port restriction
            domain (str): Domain the cookie applies to
            path (str): Path the cookie applies to
            secure (bool): Whether cookie requires secure connection
            expires (float): Expiration time (Unix timestamp)
            discard (bool): Whether cookie should be discarded at end of session
            comment (str): Cookie comment (RFC 2965)
            comment_url (str): URL for cookie policy
            httponly (bool): Whether cookie is HTTP-only (not accessible to JavaScript)
            rfc2109 (bool): Whether cookie follows RFC 2109

        Meta attributes (whether attribute was explicitly specified):
            port_specified (bool): Whether port was in Set-Cookie header
            domain_specified (bool): Whether domain was in Set-Cookie header
            domain_initial_dot (bool): Whether domain started with '.'
            path_specified (bool): Whether path was in Set-Cookie header
    """

    def __init__(self, name, value, domain='', path='/', expires=None,
                 secure=False, httponly=False, version=0, port=None,
                 discard=True, comment=None, comment_url=None, rfc2109=False,
                 port_specified=False, domain_specified=False,
                 domain_initial_dot=False, path_specified=False):
        """Initialize a Cookie object.

        Args:
            name: Cookie name
            value: Cookie value
            domain: Domain the cookie applies to
            path: Path the cookie applies to
            expires: Expiration time (Unix timestamp)
            secure: Whether cookie requires secure connection
            httponly: Whether cookie is HTTP-only
            version: Cookie version (0 for Netscape, 1 for RFC 2965)
            port: Port restriction
            discard: Whether cookie should be discarded at end of session
            comment: Cookie comment
            comment_url: URL for cookie policy
            rfc2109: Whether cookie follows RFC 2109
            port_specified: Whether port was explicitly specified
            domain_specified: Whether domain was explicitly specified
            domain_initial_dot: Whether domain started with '.'
            path_specified: Whether path was explicitly specified
        """
        # Standard cookie attributes
        self.version = version
        self.name = name
        self.value = value
        self.port = port
        self.domain = domain
        self.path = path
        self.secure = secure
        self.expires = expires
        self.discard = discard
        self.comment = comment
        self.comment_url = comment_url
        self.httponly = httponly
        self.rfc2109 = rfc2109

        # Meta attributes (whether attribute was explicitly specified)
        self.port_specified = port_specified if port_specified else bool(port)
        self.domain_specified = domain_specified if domain_specified else bool(domain)
        self.domain_initial_dot = domain_initial_dot if domain_initial_dot else (domain.startswith('.') if domain else False)
        self.path_specified = path_specified if path_specified else bool(path)

    def is_expired(self, now=None):
        """Check if cookie is expired.

        Args:
            now: Current time in seconds since epoch. If None, uses time.time()

        Returns:
            bool: True if cookie is expired, False otherwise
        """
        if self.expires is None:
            return False
        if now is None:
            now = time.time()
        return now > self.expires

    def __repr__(self):
        return '<Cookie {}={} for {}{}>'.format(
            self.name, self.value, self.domain, self.path
        )


class CookieJar:
    """Cookie storage and management.

    Compatible with Python's http.cookiejar.CookieJar class.
    Stores cookies and provides methods for cookie management and
    HTTP request/response integration.

    This is a simplified implementation suitable for embedded systems,
    without full CookiePolicy support.
    """

    def __init__(self):
        """Initialize an empty cookie jar."""
        self._cookies = {}

    def set_cookie(self, cookie):
        """Add a cookie to the jar.

        Args:
            cookie: A Cookie object to add

        If a cookie with the same domain, path, and name already exists,
        it will be replaced.
        """
        key = (cookie.domain, cookie.path, cookie.name)
        self._cookies[key] = cookie

    def clear(self, domain=None, path=None, name=None):
        """Clear cookies, optionally filtered by domain, path, and/or name.

        Args:
            domain: If specified, only clear cookies for this domain
            path: If specified, only clear cookies for this path
            name: If specified, only clear cookies with this name

        If all arguments are None, clears all cookies.

        Examples:
            jar.clear()  # Clear all cookies
            jar.clear(domain='example.com')  # Clear only example.com cookies
            jar.clear(path='/api')  # Clear only /api cookies
            jar.clear(name='session')  # Clear all cookies named 'session'
        """
        if domain is None and path is None and name is None:
            # Clear all cookies
            self._cookies.clear()
        else:
            # Selective clear
            keys_to_delete = []
            for key, cookie in self._cookies.items():
                if domain is not None and cookie.domain != domain:
                    continue
                if path is not None and cookie.path != path:
                    continue
                if name is not None and cookie.name != name:
                    continue
                keys_to_delete.append(key)

            for key in keys_to_delete:
                del self._cookies[key]

    def clear_session_cookies(self):
        """Discard all session cookies.

        Session cookies are cookies with discard=True or no expires attribute.
        Persistent cookies (those with an expiration time) are kept.
        """
        keys_to_delete = []
        for key, cookie in self._cookies.items():
            if cookie.discard or cookie.expires is None:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._cookies[key]

    def add_cookie_header(self, request):
        """Add Cookie header to request object.

        Args:
            request: A request object with 'url' and 'headers' attributes

        Adds a Cookie header with all appropriate cookies for the request URL.
        This is the standard http.cookiejar.CookieJar interface.

        Example:
            jar = CookieJar()
            jar.set_cookie(Cookie('session', 'abc123', domain='example.com'))

            request.url = 'http://example.com/api'
            request.headers = {}
            jar.add_cookie_header(request)
            # request.headers now contains: {'Cookie': 'session=abc123'}
        """
        if not hasattr(request, 'url'):
            return

        # Parse URL to get domain, path, scheme
        parsed = urlparse(request.url)
        domain = parsed.hostname
        path = parsed.path or '/'
        scheme = parsed.scheme

        # Remove expired cookies
        expired_keys = []
        for key, cookie in self._cookies.items():
            if cookie.is_expired():
                expired_keys.append(key)

        for key in expired_keys:
            del self._cookies[key]

        # Collect matching cookies
        cookies_to_send = []
        for cookie in self._cookies.values():
            # Check secure flag
            if cookie.secure and scheme != 'https':
                continue

            # Check if cookie matches URL
            if self._cookie_matches_url(cookie, domain, path):
                cookies_to_send.append((cookie.name, cookie.value))

        # Add Cookie header if we have cookies
        if cookies_to_send and hasattr(request, 'headers'):
            cookie_header = '; '.join('{}={}'.format(name, value)
                                     for name, value in cookies_to_send)
            request.headers['Cookie'] = cookie_header

    def extract_cookies(self, response, request):
        """Extract cookies from response object.

        Args:
            response: A response object with 'headers' and 'url' attributes
            request: A request object (not currently used but part of stdlib API)

        Parses Set-Cookie headers from the response and adds cookies to the jar.
        This is the standard http.cookiejar.CookieJar interface.

        Example:
            jar = CookieJar()
            jar.extract_cookies(response, request)
        """
        if not hasattr(response, 'headers'):
            return

        # Get all Set-Cookie headers
        set_cookie_headers = []

        # Handle both dict-like and list of tuples
        if hasattr(response.headers, 'items'):
            for key, value in response.headers.items():
                if key.lower() == 'set-cookie':
                    set_cookie_headers.append(value)
        else:
            for key, value in response.headers:
                if key.lower() == 'set-cookie':
                    set_cookie_headers.append(value)

        # Parse each Set-Cookie header
        parsed = urlparse(response.url)
        default_domain = parsed.hostname
        default_path = parsed.path or '/'

        # Extract path directory
        if '/' in default_path:
            default_path = default_path.rsplit('/', 1)[0] + '/'
        else:
            default_path = '/'

        for header in set_cookie_headers:
            cookie = self._parse_set_cookie(header, default_domain, default_path)
            if cookie:
                self.set_cookie(cookie)

    def _cookie_matches_url(self, cookie, domain, path):
        """Check if a cookie should be sent to the given URL.

        Args:
            cookie: Cookie object to check
            domain: Domain from URL
            path: Path from URL

        Returns:
            bool: True if cookie matches, False otherwise
        """
        # Check if expired
        if cookie.is_expired():
            return False

        # Check domain
        if cookie.domain:
            if not domain.endswith(cookie.domain):
                if not ('.' + domain).endswith(cookie.domain):
                    return False

        # Check path
        if cookie.path and not path.startswith(cookie.path):
            return False

        return True

    def _parse_set_cookie(self, header, default_domain, default_path):
        """Parse a Set-Cookie header.

        Args:
            header: Set-Cookie header value
            default_domain: Default domain from response URL
            default_path: Default path from response URL

        Returns:
            Cookie object or None if parsing failed
        """
        # Split into cookie and attributes
        parts = [p.strip() for p in header.split(';')]

        if not parts:
            return None

        # First part is name=value
        name_value = parts[0]
        if '=' not in name_value:
            return None

        name, value = name_value.split('=', 1)
        name = name.strip()
        value = value.strip()

        # Parse attributes
        domain = default_domain
        path = default_path
        expires = None
        secure = False
        httponly = False
        version = 0
        port = None
        comment = None
        comment_url = None
        discard = False  # Will be set to True if no expires/max-age

        # Track which attributes were explicitly specified
        domain_specified = False
        path_specified = False
        port_specified = False

        for part in parts[1:]:
            part_lower = part.lower()

            if part_lower == 'secure':
                secure = True
            elif part_lower == 'httponly':
                httponly = True
            elif '=' in part:
                attr_name, attr_value = part.split('=', 1)
                attr_name = attr_name.strip().lower()
                attr_value = attr_value.strip()

                if attr_name == 'domain':
                    domain = attr_value.lstrip('.')
                    domain_specified = True
                elif attr_name == 'path':
                    path = attr_value
                    path_specified = True
                elif attr_name == 'expires':
                    # Parse expires date (simplified)
                    expires = self._parse_expires(attr_value)
                elif attr_name == 'max-age':
                    # Convert max-age to expires timestamp
                    try:
                        max_age = int(attr_value)
                        expires = time.time() + max_age
                    except ValueError:
                        pass
                elif attr_name == 'version':
                    try:
                        version = int(attr_value)
                    except ValueError:
                        pass
                elif attr_name == 'port':
                    port = attr_value
                    port_specified = True
                elif attr_name == 'comment':
                    comment = attr_value
                elif attr_name == 'commenturl':
                    comment_url = attr_value

        # If no expires or max-age, this is a session cookie
        if expires is None:
            discard = True

        # Calculate domain_initial_dot
        domain_initial_dot = domain.startswith('.') if domain else False

        return Cookie(
            name=name,
            value=value,
            domain=domain,
            path=path,
            expires=expires,
            secure=secure,
            httponly=httponly,
            version=version,
            port=port,
            discard=discard,
            comment=comment,
            comment_url=comment_url,
            port_specified=port_specified,
            domain_specified=domain_specified,
            domain_initial_dot=domain_initial_dot,
            path_specified=path_specified
        )

    def _parse_expires(self, expires_str):
        """Parse cookie expires date.

        Args:
            expires_str: Expires date string from Set-Cookie header

        Returns:
            Unix timestamp or None if parsing failed

        Supports common date formats used in Set-Cookie headers.
        """
        # Common format: "Wed, 09 Jun 2021 10:18:14 GMT"
        import datetime

        # Try parsing common formats
        for fmt in [
            '%a, %d %b %Y %H:%M:%S GMT',
            '%A, %d-%b-%y %H:%M:%S GMT',
            '%a, %d-%b-%Y %H:%M:%S GMT',
        ]:
            try:
                dt = datetime.datetime.strptime(expires_str, fmt)
                return dt.timestamp()
            except (ValueError, AttributeError):
                continue

        return None

    def __iter__(self):
        """Iterate over all cookies in the jar.

        Yields:
            Cookie objects
        """
        return iter(self._cookies.values())

    def __len__(self):
        """Return number of cookies in the jar.

        Returns:
            int: Number of cookies
        """
        return len(self._cookies)

    def __repr__(self):
        return '<CookieJar with {} cookies>'.format(len(self._cookies))


__all__ = ('Cookie', 'CookieJar')
