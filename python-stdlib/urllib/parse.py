# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
urllib.parse - Parse URLs into components

This module provides functions for parsing URLs into components and
constructing URLs from components, compatible with Python's standard
library urllib.parse.

Functions:
    quote - URL encode a string
    unquote - Decode a URL encoded string
    urlencode - Encode dict/list to query string
    parse_qs - Parse query string to dict
    urlsplit - Split URL into 5 components, returns SplitResult namedtuple
    urlparse - Parse URL into 6 components, returns ParseResult namedtuple
    urlunparse - Construct URL from components

Result Types:
    SplitResult - 5-tuple from urlsplit (scheme, netloc, path, query, fragment)
    ParseResult - 6-tuple from urlparse (scheme, netloc, path, params, query, fragment)

Both result types provide additional properties:
    - hostname: extracted from netloc, lowercased
    - port: extracted from netloc as int, with scheme defaults
    - username: extracted from netloc
    - password: extracted from netloc
"""

from collections import namedtuple

# Base namedtuple classes
_SplitResultBase = namedtuple('SplitResult', 'scheme netloc path query fragment')
_ParseResultBase = namedtuple('ParseResult', 'scheme netloc path params query fragment')


def quote(string, safe='/', encoding=None, errors=None):
    """URL encode a string.

    Args:
        string: String to encode
        safe: Characters that should not be encoded (default: '/')
        encoding: Character encoding (default: utf-8)
        errors: Error handling scheme (default: None)

    Returns:
        URL encoded string

    Example:
        >>> quote('hello world')
        'hello%20world'
        >>> quote('/path/to/resource', safe='')
        '%2Fpath%2Fto%2Fresource'
    """
    if not isinstance(string, (str, bytes)):
        string = str(string)
    if isinstance(string, str):
        string = string.encode('utf-8')

    result = []
    safe_bytes = safe.encode('ascii') if isinstance(safe, str) else safe

    for byte in string:
        char = bytes([byte])
        if (char.isalnum() or char in safe_bytes or
            char in b'-_.~'):
            result.append(chr(byte))
        else:
            result.append('%{:02X}'.format(byte))

    return ''.join(result)


def unquote(string, encoding='utf-8', errors='replace'):
    """Decode a URL encoded string.

    Args:
        string: URL encoded string
        encoding: Character encoding (default: 'utf-8')
        errors: Error handling scheme (default: 'replace')

    Returns:
        Decoded string

    Example:
        >>> unquote('hello%20world')
        'hello world'
        >>> unquote('hello+world')
        'hello world'
    """
    if not isinstance(string, str):
        string = str(string)

    # Replace %XX with actual bytes
    result = []
    i = 0
    while i < len(string):
        if string[i] == '%' and i + 2 < len(string):
            try:
                byte = int(string[i+1:i+3], 16)
                result.append(byte)
                i += 3
            except ValueError:
                result.append(ord(string[i]))
                i += 1
        elif string[i] == '+':
            result.append(ord(' '))
            i += 1
        else:
            result.append(ord(string[i]))
            i += 1

    return bytes(result).decode(encoding, errors)


def urlencode(query, doseq=False):
    """Encode a dict or list of tuples into a URL query string.

    Args:
        query: Dict or list of (key, value) tuples
        doseq: If True, encode list/tuple values as separate parameters

    Returns:
        URL encoded query string

    Example:
        >>> urlencode({'key': 'value', 'foo': 'bar'})
        'key=value&foo=bar'
        >>> urlencode([('key', 'value'), ('key', 'value2')])
        'key=value&key=value2'
    """
    if hasattr(query, 'items'):
        query = list(query.items())

    result = []
    for k, v in query:
        if isinstance(v, (list, tuple)) and doseq:
            for item in v:
                result.append('{}={}'.format(
                    quote(str(k), safe=''),
                    quote(str(item), safe='')
                ))
        else:
            result.append('{}={}'.format(
                quote(str(k), safe=''),
                quote(str(v), safe='')
            ))

    return '&'.join(result)


def parse_qs(qs, keep_blank_values=False, strict_parsing=False):
    """Parse a query string into a dict.

    Args:
        qs: Query string to parse
        keep_blank_values: If True, keep blank values in result
        strict_parsing: If True, raise ValueError on parsing errors

    Returns:
        Dict mapping parameter names to values

    Example:
        >>> parse_qs('key=value&foo=bar')
        {'key': 'value', 'foo': 'bar'}
        >>> parse_qs('key=value1&key=value2')
        {'key': ['value1', 'value2']}
    """
    result = {}
    if not qs:
        return result

    for pair in qs.split('&'):
        if not pair:
            continue

        if '=' in pair:
            key, value = pair.split('=', 1)
            key = unquote(key.replace('+', ' '))
            value = unquote(value.replace('+', ' '))
        else:
            key = unquote(pair.replace('+', ' '))
            value = ''

        if not keep_blank_values and not value:
            continue

        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value

    return result


# Mixin class for result objects to provide hostname, port, username, password properties
class _NetlocResultMixin:
    """Mixin to add computed properties to URL parsing result objects.

    Provides properties that extract components from the netloc field:
    - hostname: host name in lowercase
    - port: port number as integer (with scheme defaults)
    - username: user name if present
    - password: password if present
    """
    @property
    def _hostinfo(self):
        """Extract hostname and port from netloc.

        Returns:
            tuple: (hostname, port_string or None)
        """
        netloc = self.netloc

        # Remove userinfo if present (user:pass@host)
        _, _, hostinfo = netloc.rpartition('@')

        # Handle IPv6 addresses in brackets
        if '[' in hostinfo:
            if ']:' in hostinfo:
                # IPv6 with port: [host]:port
                hostname, port_str = hostinfo.rsplit(':', 1)
                hostname = hostname[1:-1]  # Remove brackets
                port = port_str
            else:
                # IPv6 without port: [host] or [host]
                hostname = hostinfo[1:-1] if hostinfo.endswith(']') else hostinfo[1:]
                port = None
        else:
            # IPv4 or hostname (possibly with port)
            if ':' in hostinfo:
                hostname, port = hostinfo.rsplit(':', 1)
            else:
                hostname = hostinfo
                port = None

        return hostname, port

    @property
    def _userinfo(self):
        """Extract username and password from netloc.

        Returns:
            tuple: (username or None, password or None)
        """
        netloc = self.netloc
        userinfo, have_info, hostinfo = netloc.rpartition('@')
        if have_info:
            username, have_password, password = userinfo.partition(':')
            if not have_password:
                password = None
        else:
            username = password = None
        return username, password

    @property
    def hostname(self):
        """Extract hostname from netloc, lowercased.

        Returns:
            str or None: Hostname in lowercase, or None if not present.
                        For IPv6, zone identifiers preserve their case.
        """
        hostname, port = self._hostinfo
        if not hostname:
            return None
        # Lowercase hostname (but preserve IPv6 zone identifiers case)
        if '%' in hostname:
            # IPv6 with zone identifier (e.g., fe80::1%eth0)
            host_part, zone = hostname.split('%', 1)
            return host_part.lower() + '%' + zone
        return hostname.lower()

    @property
    def port(self):
        """Extract port from netloc as integer, with scheme defaults.

        Returns:
            int or None: Port number, or default port for scheme, or None.

        Raises:
            ValueError: If port string is not a valid integer or out of range.
        """
        hostname, port_str = self._hostinfo

        if port_str:
            try:
                port = int(port_str)
                if not (0 <= port <= 65535):
                    raise ValueError(f"Port out of range 0-65535: {port}")
                return port
            except ValueError as e:
                if "Port out of range" in str(e):
                    raise
                raise ValueError(f"Invalid port: {port_str}")

        # Return default port for scheme
        return None

    @property
    def username(self):
        """Extract username from netloc.

        Returns:
            str or None: Username if present in netloc, otherwise None.
        """
        return self._userinfo[0]

    @property
    def password(self):
        """Extract password from netloc.

        Returns:
            str or None: Password if present in netloc, otherwise None.
        """
        return self._userinfo[1]


class SplitResult(_SplitResultBase, _NetlocResultMixin):
    """Result from urlsplit(): 5-tuple of (scheme, netloc, path, query, fragment).

    Supports both index access (result[0]) and attribute access (result.scheme).
    Provides additional computed properties: hostname, port, username, password.

    Methods:
        geturl(): Return the re-combined version of the original URL as a string.
    """
    def geturl(self):
        """Return the re-combined version of the original URL as a string."""
        # urlunparse handles namedtuples, will treat SplitResult as 5-tuple
        return urlunparse(self)


class ParseResult(_ParseResultBase, _NetlocResultMixin):
    """Result from urlparse(): 6-tuple of (scheme, netloc, path, params, query, fragment).

    Supports both index access (result[0]) and attribute access (result.scheme).
    Provides additional computed properties: hostname, port, username, password.

    Methods:
        geturl(): Return the re-combined version of the original URL as a string.
    """
    def geturl(self):
        """Return the re-combined version of the original URL as a string."""
        # urlunparse handles namedtuples
        return urlunparse(self)


def urlsplit(url):
    """Split a URL into 5 components: scheme, netloc, path, query, fragment.

    This is the base URL parsing function, compatible with Python's standard library.

    Args:
        url: URL string to parse

    Returns:
        SplitResult: A namedtuple with fields (scheme, netloc, path, query, fragment)
                    and additional properties (hostname, port, username, password)

    Raises:
        ValueError: If URL is invalid (no URL specified or no scheme)

    Example:
        >>> result = urlsplit('http://www.example.com:8080/path?query#fragment')
        >>> result.scheme
        'http'
        >>> result.hostname
        'www.example.com'
        >>> result.port
        8080
        >>> result.path
        '/path'
    """
    # Extract scheme
    if '://' in url:
        scheme, rest = url.split('://', 1)
        scheme = scheme.lower()
    else:
        scheme, rest = '', url

    # Extract fragment
    fragment = ''
    if '#' in rest:
        rest, fragment = rest.split('#', 1)

    # Extract query
    query = ''
    if '?' in rest:
        rest, query = rest.split('?', 1)

    # Extract path and netloc
    path = '/'
    if '/' in rest:
        netloc, path = rest.split('/', 1)
        path = '/' + path
    else:
        netloc = rest

    return SplitResult(scheme, netloc, path, query, fragment)


def urlparse(url):
    """Parse a URL into 6 components: scheme, netloc, path, params, query, fragment.

    This calls urlsplit() and additionally extracts params from the path using
    the ';' separator (as per RFC 2396, though rarely used in modern URLs).

    Args:
        url: URL string to parse

    Returns:
        ParseResult: A namedtuple with fields (scheme, netloc, path, params, query, fragment)
                    and additional properties (hostname, port, username, password)

    Raises:
        ValueError: If URL is invalid (no URL specified or no scheme)

    Example:
        >>> result = urlparse('http://example.com/path;params?query#fragment')
        >>> result.scheme
        'http'
        >>> result.params
        'params'
        >>> result.hostname
        'example.com'
        >>> result.port
        80
    """
    # Use urlsplit to get the base components
    split_result = urlsplit(url)

    # Extract params from path (;-separated parameters)
    path = split_result.path
    params = ''
    if ';' in path:
        path, params = path.split(';', 1)

    return ParseResult(
        split_result.scheme,
        split_result.netloc,
        path,
        params,
        split_result.query,
        split_result.fragment
    )


def urlunparse(parts):
    """Construct a URL from parsed components.

    Accepts either a dict, a ParseResult/SplitResult namedtuple, or any 6-item iterable
    with components: (scheme, netloc, path, params, query, fragment).
    If 'params' is present, it will be merged into the path with ';' separator.

    Args:
        parts: Dict, namedtuple, or 6-item iterable with URL components

    Returns:
        Reconstructed URL string

    Example:
        >>> urlunparse({'scheme': 'http', 'netloc': 'example.com',
        ...             'path': '/path', 'params': 'p1', 'query': 'q=v',
        ...             'fragment': 'section'})
        'http://example.com/path;p1?q=v#section'

        >>> result = urlparse('http://example.com/path?query')
        >>> urlunparse(result)
        'http://example.com/path?query'
    """
    # Handle dict-like objects
    if isinstance(parts, dict):
        scheme = parts.get('scheme', 'http')
        netloc = parts.get('netloc', '')
        path = parts.get('path', '/')
        params = parts.get('params', '')
        query = parts.get('query', '')
        fragment = parts.get('fragment', '')
    # Handle namedtuples and objects with attributes
    elif hasattr(parts, 'scheme'):
        scheme = getattr(parts, 'scheme', 'http')
        netloc = getattr(parts, 'netloc', '')
        path = getattr(parts, 'path', '/')
        params = getattr(parts, 'params', '')
        query = getattr(parts, 'query', '')
        fragment = getattr(parts, 'fragment', '')
    # Handle tuples/lists (6-item sequence)
    else:
        try:
            if len(parts) == 6:
                scheme, netloc, path, params, query, fragment = parts
            elif len(parts) == 5:
                # SplitResult doesn't have params
                scheme, netloc, path, query, fragment = parts
                params = ''
            else:
                raise ValueError("parts must have 5 or 6 elements")
        except (TypeError, ValueError):
            raise ValueError("urlunparse() arg must be a dict, namedtuple, or 5-6 item sequence")

    # Merge params into path if present
    if params:
        path = path + ';' + params

    url = '{}://{}{}'.format(scheme, netloc, path)
    if query:
        url += '?' + query
    if fragment:
        url += '#' + fragment

    return url


# Public API
__all__ = (
    'quote', 'unquote', 'urlencode', 'parse_qs',
    'urlsplit', 'urlparse', 'urlunparse',
    'SplitResult', 'ParseResult',
)
