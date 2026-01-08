"""
requests.utils
~~~~~~~~~~~~~~

This module provides utility functions that are used within Requests
that are also useful for external consumption.
"""

from freeze import frozendict
import io
import json
import re
import time

from .exceptions import InvalidURL, InvalidHeader
from .structures import CaseInsensitiveDict

# Import URL parsing functions from urllib.parse
from urllib.parse import (
    quote, unquote, urlencode, parse_qs,
)

DEFAULT_PORTS = frozendict({
    'http': 80,
    'https': 443,
})

# Default User-Agent string
DEFAULT_USER_AGENT = 'python-requests/2.31.0'


def prepend_scheme_if_needed(url, scheme):
    """Add scheme to URL if it doesn't have one."""
    if not url:
        return url

    if '://' not in url:
        return '{}://{}'.format(scheme, url)

    return url


def get_encoding_from_headers(headers):
    """Returns encodings from given HTTP Header Dict."""
    content_type = headers.get('content-type', '')

    if not content_type:
        return None

    # Look for charset parameter
    match = re.search(r'charset=([^;]+)', content_type, 0)  # re.IGNORECASE
    if match:
        encoding = match.group(1).strip().strip('"\'')
        return encoding

    return None


def get_encodings_from_content(content):
    """Returns encodings from given content bytes.

    For microcontrollers, we simplify and just check for common patterns.
    """
    # Check for XML encoding declaration
    if content[:5] == b'<?xml':
        match = re.search(rb'encoding=["\']?([^"\'\s>]+)', content[:1000])
        if match:
            try:
                return [match.group(1).decode('ascii')]
            except:
                pass

    # Check for HTML meta charset
    if content[:15].lower().startswith(b'<!doctype html') or content[:6].lower() == b'<html':
        match = re.search(rb'<meta[^>]+charset=["\']?([^"\'\s>]+)', content[:5000], re.IGNORECASE)
        if match:
            try:
                return [match.group(1).decode('ascii')]
            except:
                pass

    return []


def stream_decode_response_unicode(iterator, encoding=None):
    """Stream decode a response iterator."""
    if encoding is None:
        encoding = 'utf-8'

    for chunk in iterator:
        if isinstance(chunk, bytes):
            yield chunk.decode(encoding, errors='replace')
        else:
            yield chunk


def iter_chunks(file, chunk_size):
    """Iterate over chunks from a file."""
    chunk = file.read(chunk_size)
    while chunk:
        yield chunk
        chunk = file.read(chunk_size)


def iter_slices(string, slice_length):
    """Iterate over slices of a string."""
    pos = 0
    if slice_length is None or slice_length <= 0:
        slice_length = len(string)
    while pos < len(string):
        yield string[pos:pos + slice_length]
        pos += slice_length


def guess_filename(obj):
    """Try to guess the filename of an object."""
    name = getattr(obj, 'name', None)
    if name and isinstance(name, str) and name[0] != '<' and name[-1] != '>':
        return name
    return None


def to_key_val_list(value):
    """Take an object and return a list of tuples."""
    if value is None:
        return None

    if isinstance(value, (str, bytes, bool, int)):
        raise ValueError('cannot encode objects that are not 2-tuples')

    if hasattr(value, 'items'):
        return list(value.items())

    return list(value)


def encode_multipart_formdata(fields, boundary=None):
    """Encode fields for multipart/form-data.

    fields: list of (name, value) tuples or (name, (filename, fileobj, content_type)) tuples

    Returns: (body, content_type)
    """
    if boundary is None:
        boundary = '----WebKitFormBoundary{}'.format(
            ''.join(['{:02x}'.format(b) for b in bytes(range(16))])
        )

    body = io.BytesIO()

    for name, value in fields:
        body.write('--{}\r\n'.format(boundary).encode('utf-8'))

        # Check if this is a file upload
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            filename = value[0]
            fileobj = value[1]
            content_type = value[2] if len(value) > 2 else 'application/octet-stream'

            body.write('Content-Disposition: form-data; name="{}"; filename="{}"\r\n'.format(
                name, filename
            ).encode('utf-8'))
            body.write('Content-Type: {}\r\n\r\n'.format(content_type).encode('utf-8'))

            # Read file content
            if hasattr(fileobj, 'read'):
                content = fileobj.read()
            else:
                content = fileobj

            if isinstance(content, str):
                content = content.encode('utf-8')

            body.write(content)
            body.write(b'\r\n')
        else:
            # Regular field
            body.write('Content-Disposition: form-data; name="{}"\r\n\r\n'.format(
                name
            ).encode('utf-8'))

            if isinstance(value, str):
                value = value.encode('utf-8')
            elif not isinstance(value, bytes):
                value = str(value).encode('utf-8')

            body.write(value)
            body.write(b'\r\n')

    body.write('--{}--\r\n'.format(boundary).encode('utf-8'))

    content_type = 'multipart/form-data; boundary={}'.format(boundary)

    return body.getvalue(), content_type


def default_headers():
    """Return default headers."""
    return CaseInsensitiveDict({
        'User-Agent': DEFAULT_USER_AGENT,
        'Accept-Encoding': 'identity',
        'Accept': '*/*',
        'Connection': 'keep-alive',
    })


def default_user_agent(name='python-requests'):
    """Return a default user-agent string."""
    return '{}/2.31.0'.format(name)


def parse_header_links(value):
    """Parse Link header into a list of dicts."""
    links = []

    if not value:
        return links

    for val in re.split(', *<', value):
        try:
            url, params = val.split(';', 1)
        except ValueError:
            url, params = val, ''

        url = url.strip('<> \'"')

        link = {'url': url}

        for param in params.split(';'):
            param = param.strip()
            if '=' in param:
                key, value = param.split('=', 1)
                link[key.strip()] = value.strip(' \'"')

        links.append(link)

    return links


def requote_uri(uri):
    """Re-quote the given URI."""
    safe_with_percent = "!#$&'()*+,/:;=?@[]~%"
    return quote(unquote(uri), safe=safe_with_percent)


def check_header_validity(header):
    """Verify that header name and value are valid."""
    name, value = header

    # Header names must be strings
    if not isinstance(name, str):
        raise InvalidHeader("Header name must be a string, got {!r}".format(type(name)))

    # Header values must be strings or bytes
    if not isinstance(value, (str, bytes)):
        raise InvalidHeader("Header value must be a string or bytes, got {!r}".format(type(value)))

    # Check for invalid characters in name
    if not re.match(r'^[^:\s]+$', name):
        raise InvalidHeader("Invalid header name {!r}".format(name))

    # Check for newlines in value (potential header injection)
    if isinstance(value, str) and ('\n' in value or '\r' in value):
        raise InvalidHeader("Invalid header value {!r}".format(value))


def select_proxy(url, proxies):
    """Select a proxy for the given URL from a proxy dict."""
    if proxies is None:
        return None

    parsed = urlparse(url)
    scheme = parsed['scheme']

    # Check scheme-specific proxy
    proxy = proxies.get(scheme)
    if proxy:
        return proxy

    # Check for all:// proxy
    proxy = proxies.get('all')
    if proxy:
        return proxy

    return None


def should_bypass_proxies(url, no_proxy=None):
    """Returns whether we should bypass proxies or not."""
    # For microcontrollers, we typically don't use proxies
    return True
