"""
requests.cookies
~~~~~~~~~~~~~~~~

This module provides cookie handling for Requests.

Extends Python's standard http.cookiejar with Requests-specific functionality.
"""

try:
    from collections.abc import MutableMapping
except ImportError:
    from collections import MutableMapping

from urllib.parse import urlparse
from http.cookiejar import Cookie, CookieJar as HTTPCookieJar


# Re-export Cookie for convenience
__all__ = ('Cookie', 'CookieJar', 'create_cookie', 'merge_cookies')


class CookieJar(HTTPCookieJar, MutableMapping):
    """Requests-specific cookie jar.

    Extends http.cookiejar.CookieJar with:
    - MutableMapping interface for dict-like access
    - get_cookies_for_url() convenience method
    - extract_cookies_from_response() convenience method

    This provides backward compatibility with existing Requests code
    while maintaining compatibility with the standard library.
    """

    def get_cookies_for_url(self, url):
        """Get all cookies that should be sent to the given URL.

        This is a Requests-specific convenience method that returns
        a simple dict of cookie names to values.

        Args:
            url: URL string

        Returns:
            dict: Cookie names mapped to values

        Example:
            cookies = jar.get_cookies_for_url('http://example.com/api')
            # Returns: {'session': 'abc123', 'user': 'john'}
        """
        parsed = urlparse(url)
        domain = parsed.hostname
        path = parsed.path or '/'
        scheme = parsed.scheme

        cookies = {}

        # Remove expired cookies
        expired_keys = []
        for key, cookie in self._cookies.items():
            if cookie.is_expired():
                expired_keys.append(key)

        for key in expired_keys:
            del self._cookies[key]

        # Find matching cookies
        for cookie in self._cookies.values():
            # Check secure flag
            if cookie.secure and scheme != 'https':
                continue

            # Check if cookie matches URL
            if self._cookie_matches_url(cookie, domain, path):
                cookies[cookie.name] = cookie.value

        return cookies

    def extract_cookies_from_response(self, response):
        """Extract cookies from a response object.

        This is a Requests-specific convenience method that wraps
        the stdlib extract_cookies() method.

        Args:
            response: A response object with 'headers' and 'url' attributes

        Example:
            jar = CookieJar()
            jar.extract_cookies_from_response(response)
        """
        # Create a minimal request object for stdlib interface
        class DummyRequest:
            pass

        request = DummyRequest()
        # The stdlib extract_cookies doesn't actually use the request parameter
        # in our implementation, but we provide it for API compatibility
        self.extract_cookies(response, request)

    # MutableMapping interface for dict-like access
    # This is Requests-specific and not part of stdlib http.cookiejar

    def __getitem__(self, name):
        """Get cookie value by name (from any domain/path).

        Args:
            name: Cookie name

        Returns:
            str: Cookie value

        Raises:
            KeyError: If no cookie with that name exists

        Example:
            value = jar['session']
        """
        for cookie in self._cookies.values():
            if cookie.name == name:
                return cookie.value
        raise KeyError(name)

    def __setitem__(self, name, value):
        """Set a cookie with default domain/path.

        Args:
            name: Cookie name
            value: Cookie value

        Creates a cookie with default domain and path.

        Example:
            jar['session'] = 'abc123'
        """
        cookie = Cookie(name, value)
        self.set_cookie(cookie)

    def __delitem__(self, name):
        """Delete all cookies with the given name.

        Args:
            name: Cookie name to delete

        Raises:
            KeyError: If no cookie with that name exists

        Example:
            del jar['session']
        """
        keys_to_delete = []
        for key, cookie in self._cookies.items():
            if cookie.name == name:
                keys_to_delete.append(key)

        if not keys_to_delete:
            raise KeyError(name)

        for key in keys_to_delete:
            del self._cookies[key]

    def __iter__(self):
        """Iterate over cookie names.

        Yields:
            str: Unique cookie names

        Example:
            for name in jar:
                print(name)
        """
        seen = set()
        for cookie in self._cookies.values():
            if cookie.name not in seen:
                seen.add(cookie.name)
                yield cookie.name

    def __len__(self):
        """Return number of unique cookie names.

        Returns:
            int: Number of unique cookie names

        Note: This returns unique names, not total cookies.
        Multiple cookies can have the same name but different domains/paths.
        """
        return len(set(cookie.name for cookie in self._cookies.values()))


def create_cookie(name, value, **kwargs):
    """Create a Cookie object.

    Convenience function for creating cookies.

    Args:
        name: Cookie name
        value: Cookie value
        **kwargs: Additional cookie attributes (domain, path, expires, etc.)

    Returns:
        Cookie: A new Cookie object

    Example:
        cookie = create_cookie('session', 'abc123', domain='example.com', path='/api')
    """
    return Cookie(name, value, **kwargs)


def merge_cookies(cookiejar, cookies):
    """Merge cookies into a cookie jar.

    Args:
        cookiejar: CookieJar to merge into
        cookies: Can be:
            - dict: Keys are cookie names, values are cookie values
            - CookieJar: Cookies will be copied from this jar
            - Iterable of Cookie objects

    Returns:
        CookieJar: The updated cookiejar (for chaining)

    Examples:
        # Merge dict
        merge_cookies(jar, {'session': 'abc123', 'user': 'john'})

        # Merge another jar
        merge_cookies(jar1, jar2)

        # Merge list of Cookie objects
        merge_cookies(jar, [cookie1, cookie2, cookie3])
    """
    if cookies is None:
        return cookiejar

    if isinstance(cookies, dict):
        for name, value in cookies.items():
            cookiejar[name] = value
    elif isinstance(cookies, CookieJar):
        cookiejar._cookies.update(cookies._cookies)
    else:
        # Assume iterable of Cookie objects
        for cookie in cookies:
            cookiejar.set_cookie(cookie)

    return cookiejar
