# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

import http.client
from urllib.parse import urlparse

def urlopen(url, data=None, timeout=None, *, cafile=None, capath=None, cadefault=False, context=None):
    """Open a URL and return a response object.

    This is a simplified implementation that forwards to http.client.
    """
    # Parse the URL
    parsed = urlparse(url)

    # Determine the connection class based on scheme
    if parsed.scheme == 'https':
        conn_class = http.client.HTTPSConnection
    elif parsed.scheme == 'http':
        conn_class = http.client.HTTPConnection
    else:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    # Extract host and port
    host = parsed.hostname
    port = parsed.port

    # Create connection (pass context for HTTPS if provided)
    if parsed.scheme == 'https' and context is not None:
        conn = conn_class(host, port, timeout=timeout, context=context)
    else:
        conn = conn_class(host, port, timeout=timeout)

    # Build the path (including query string if present)
    path = parsed.path or '/'
    if parsed.query:
        path = f"{path}?{parsed.query}"

    # Make the request
    method = 'POST' if data is not None else 'GET'
    headers = {}

    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if isinstance(data, str):
            data = data.encode('utf-8')

    conn.request(method, path, body=data, headers=headers)

    # Get and return the response
    return conn.getresponse()
