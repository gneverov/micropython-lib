"""
requests.sessions
~~~~~~~~~~~~~~~~~

This module provides a Session object to manage and persist settings across
requests (cookies, auth, proxies).
"""

from .adapters import HTTPAdapter
from .auth import AuthBase
from .cookies import CookieJar, merge_cookies
from .exceptions import TooManyRedirects, InvalidSchema, ChunkedEncodingError
from .models import Request, PreparedRequest, Response, DEFAULT_REDIRECT_LIMIT
from .structures import CaseInsensitiveDict
from .utils import (
    default_headers, get_encoding_from_headers, to_key_val_list,
)
from urllib.parse import urlparse, urlunparse

# Redirect status codes
REDIRECT_STATI = (301, 302, 303, 307, 308)


def merge_setting(request_setting, session_setting, dict_class=None):
    """Determine appropriate setting value from request and session."""
    if session_setting is None:
        return request_setting
    if request_setting is None:
        return session_setting

    # Attempt to reuse session setting if request setting is falsy
    if not request_setting:
        return session_setting

    # For dicts, merge them
    if dict_class is not None and (
        isinstance(session_setting, dict_class) or
        isinstance(request_setting, dict_class)
    ):
        merged = dict_class()
        if isinstance(session_setting, dict):
            merged.update(session_setting)
        if isinstance(request_setting, dict):
            merged.update(request_setting)
        return merged

    return request_setting


def merge_hooks(request_hooks, session_hooks):
    """Merge hooks from request and session."""
    if session_hooks is None or session_hooks == {}:
        return request_hooks
    if request_hooks is None or request_hooks == {}:
        return session_hooks

    merged = {}
    for event in set(list(session_hooks.keys()) + list(request_hooks.keys())):
        merged[event] = []
        if event in session_hooks:
            merged[event].extend(session_hooks[event])
        if event in request_hooks:
            merged[event].extend(request_hooks[event])

    return merged


class SessionRedirectMixin:
    """Mixin for handling redirects in a Session."""

    def resolve_redirects(self, resp, req, stream=False, timeout=None,
                          verify=True, cert=None, proxies=None, yield_requests=False, **adapter_kwargs):
        """Receive a Response. Yield redirect responses."""
        hist = []  # Keep track of redirect chain
        url = resp.url
        previous_fragment = urlparse(req.url).fragment

        i = 0
        while resp.is_redirect:
            prepared_request = req.copy()

            if i >= self.max_redirects:
                raise TooManyRedirects('Exceeded {} redirects.'.format(self.max_redirects), response=resp)

            # Release the connection back to the pool
            resp.close()

            # Add response to history
            hist.append(resp)

            # Get redirect location
            url = resp.headers['location']

            # Handle relative URLs
            if not url.startswith(('http://', 'https://')):
                # Relative URL
                parsed_original = urlparse(resp.url)

                if url.startswith('/'):
                    # Absolute path
                    url = '{}://{}{}'.format(
                        parsed_original.scheme,
                        parsed_original.netloc,
                        url
                    )
                else:
                    # Relative path
                    base_path = parsed_original.path
                    if '/' in base_path:
                        base_path = base_path.rsplit('/', 1)[0]
                    else:
                        base_path = ''

                    url = '{}://{}{}/{}'.format(
                        parsed_original.scheme,
                        parsed_original.netloc,
                        base_path,
                        url
                    )

            # Prepare next request
            prepared_request.url = url

            # Handle fragment
            scheme, netloc, path, params, query, fragment = urlparse(url)
            if not fragment:
                if previous_fragment:
                    url = urlunparse((scheme, netloc, path, params, query, previous_fragment))
                    prepared_request.url = url
            else:
                previous_fragment = fragment

            # http://tools.ietf.org/html/rfc7231#section-6.4.4
            if resp.status_code == 303 or \
               (resp.status_code == 302 and prepared_request.method != 'HEAD'):
                # Change method to GET for 303 and 302 (for non-HEAD)
                prepared_request.method = 'GET'
                prepared_request.body = None

                # Remove content-related headers
                for header in ('Content-Length', 'Content-Type'):
                    prepared_request.headers.pop(header, None)

            # Remove Authorization header on redirect to different host
            parsed_original = urlparse(resp.url)
            parsed_redirect = urlparse(url)

            if (parsed_original.hostname != parsed_redirect.hostname):
                prepared_request.headers.pop('Authorization', None)

            # Prepare cookies for redirected request
            merge_cookies(prepared_request._cookies, resp.cookies)

            # Send redirected request
            resp = self.send(
                prepared_request,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
                allow_redirects=False,
                **adapter_kwargs
            )

            i += 1
            yield resp

        # Set history on final response
        resp.history = hist

    def rebuild_auth(self, prepared_request, response):
        """When being redirected we may want to strip authentication from the request."""
        # Not implemented in this simplified version
        pass

    def rebuild_proxies(self, prepared_request, proxies):
        """Rebuild proxies dict for redirected request."""
        # Not implemented in this simplified version
        return proxies


class Session(SessionRedirectMixin):
    """A Requests session.

    Provides cookie persistence, connection-pooling, and configuration.

    Basic Usage::

      >>> import requests
      >>> s = requests.Session()
      >>> s.get('https://httpbin.org/get')
      <Response [200]>
    """

    def __init__(self):
        #: Default headers for all requests
        self.headers = default_headers()

        #: Authentication tuple or callable to enable Basic/Custom HTTP Auth
        self.auth = None

        #: Dictionary mapping protocol or protocol and host to proxy URL
        self.proxies = {}

        #: Event-handling hooks
        self.hooks = {
            'response': []
        }

        #: Request parameters (e.g., query string)
        self.params = {}

        #: SSL Verification (True/False or path to CA bundle)
        self.verify = True

        #: SSL client side certificate (cert, key) pair or single file
        self.cert = None

        #: Maximum number of redirects allowed
        self.max_redirects = DEFAULT_REDIRECT_LIMIT

        #: Cookies persisted across requests
        self.cookies = CookieJar()

        #: Transport adapter
        self.adapters = {}
        self.mount('http://', HTTPAdapter())
        self.mount('https://', HTTPAdapter())

        #: Stream response content default
        self.stream = False

        #: Should we trust the environment (env vars)?
        self.trust_env = False

    def prepare_request(self, request):
        """Construct a :class:`PreparedRequest <PreparedRequest>` for transmission."""
        cookies = request.cookies or {}

        # Merge cookies
        merged_cookies = merge_cookies(
            merge_cookies(CookieJar(), self.cookies), cookies
        )

        # Merge headers
        headers = merge_setting(
            request.headers, self.headers, dict_class=CaseInsensitiveDict
        )

        # Merge params
        params = merge_setting(request.params, self.params)

        # Merge auth
        auth = merge_setting(request.auth, self.auth)

        # Merge hooks
        hooks = merge_hooks(request.hooks, self.hooks)

        # Create prepared request
        p = PreparedRequest()
        p.prepare(
            method=request.method,
            url=request.url,
            files=request.files,
            data=request.data,
            json=request.json,
            headers=headers,
            params=params,
            auth=auth,
            cookies=merged_cookies,
            hooks=hooks,
        )

        return p

    def request(self, method, url, params=None, data=None, headers=None,
                cookies=None, files=None, auth=None, timeout=None,
                allow_redirects=True, proxies=None, hooks=None, stream=None,
                verify=None, cert=None, json=None):
        """Construct a Request, prepare it, and send it."""
        # Create Request object
        req = Request(
            method=method.upper(),
            url=url,
            headers=headers,
            files=files,
            data=data,
            json=json,
            params=params,
            auth=auth,
            cookies=cookies,
            hooks=hooks,
        )

        prep = self.prepare_request(req)

        # Merge environment settings
        proxies = proxies or {}
        stream = stream if stream is not None else self.stream
        verify = verify if verify is not None else self.verify
        cert = cert or self.cert

        # Send request
        send_kwargs = {
            'timeout': timeout,
            'allow_redirects': allow_redirects,
            'stream': stream,
            'verify': verify,
            'cert': cert,
            'proxies': proxies,
        }

        resp = self.send(prep, **send_kwargs)

        return resp

    def get(self, url, **kwargs):
        """Send a GET request."""
        kwargs.setdefault('allow_redirects', True)
        return self.request('GET', url, **kwargs)

    def options(self, url, **kwargs):
        """Send an OPTIONS request."""
        kwargs.setdefault('allow_redirects', True)
        return self.request('OPTIONS', url, **kwargs)

    def head(self, url, **kwargs):
        """Send a HEAD request."""
        kwargs.setdefault('allow_redirects', False)
        return self.request('HEAD', url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        """Send a POST request."""
        return self.request('POST', url, data=data, json=json, **kwargs)

    def put(self, url, data=None, **kwargs):
        """Send a PUT request."""
        return self.request('PUT', url, data=data, **kwargs)

    def patch(self, url, data=None, **kwargs):
        """Send a PATCH request."""
        return self.request('PATCH', url, data=data, **kwargs)

    def delete(self, url, **kwargs):
        """Send a DELETE request."""
        return self.request('DELETE', url, **kwargs)

    def send(self, request, **kwargs):
        """Send a given PreparedRequest."""
        kwargs.setdefault('stream', self.stream)
        kwargs.setdefault('verify', self.verify)
        kwargs.setdefault('cert', self.cert)
        kwargs.setdefault('proxies', self.proxies)

        # Allow early exit if allow_redirects is False
        allow_redirects = kwargs.pop('allow_redirects', True)

        # Get adapter for URL
        adapter = self.get_adapter(url=request.url)

        # Send request
        resp = adapter.send(request, **kwargs)

        # Extract cookies from response
        merge_cookies(self.cookies, resp.cookies)

        # Handle redirects
        if allow_redirects:
            # Resolve redirects
            gen = self.resolve_redirects(resp, request, **kwargs)
            history = [r for r in gen]
            if history:
                # Get final response
                resp = history[-1]

        return resp

    def mount(self, prefix, adapter):
        """Register a connection adapter to a prefix."""
        self.adapters[prefix] = adapter

    def get_adapter(self, url):
        """Get the appropriate adapter for the given URL."""
        for prefix, adapter in self.adapters.items():
            if url.lower().startswith(prefix.lower()):
                return adapter

        raise InvalidSchema("No connection adapters found for {}".format(url))

    def close(self):
        """Close all adapters and clear the session."""
        for adapter in self.adapters.values():
            adapter.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Destructor."""
        try:
            self.close()
        except:
            pass


def session():
    """Create a new :class:`Session`."""
    return Session()
