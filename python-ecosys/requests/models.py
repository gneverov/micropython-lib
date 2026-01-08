"""
requests.models
~~~~~~~~~~~~~~~

This module contains the primary objects that power Requests.
"""

import io
import json as json_module

from .auth import AuthBase
from .cookies import CookieJar, merge_cookies
from .exceptions import (
    HTTPError, ConnectionError, InvalidURL, InvalidHeader,
    JSONDecodeError, StreamConsumedError, ContentDecodingError
)
from .structures import CaseInsensitiveDict
from .utils import (
    default_headers, to_key_val_list,
    encode_multipart_formdata, get_encoding_from_headers,
    stream_decode_response_unicode, iter_chunks, iter_slices, check_header_validity
)
from .status_codes import _codes
from urllib.parse import urlencode

# Default redirect limit
DEFAULT_REDIRECT_LIMIT = 30

# HTTP methods that allow body
CONTENT_METHODS = ('POST', 'PUT', 'PATCH')


class Request:
    """A user-created Request object.

    Used to prepare a :class:`PreparedRequest <PreparedRequest>`, which is sent to the server.
    """

    def __init__(self, method=None, url=None, headers=None, files=None,
                 data=None, json=None, params=None, auth=None, cookies=None,
                 hooks=None):
        # Default empty dicts for dict params.
        if data is None:
            data = {}
        if files is None:
            files = {}
        if headers is None:
            headers = {}
        if params is None:
            params = {}
        if hooks is None:
            hooks = {}

        self.method = method
        self.url = url
        self.headers = headers
        self.files = files
        self.data = data
        self.json = json
        self.params = params
        self.auth = auth
        self.cookies = cookies
        self.hooks = hooks

    def prepare(self):
        """Construct a :class:`PreparedRequest <PreparedRequest>` for transmission."""
        p = PreparedRequest()
        p.prepare(
            method=self.method,
            url=self.url,
            headers=self.headers,
            files=self.files,
            data=self.data,
            json=self.json,
            params=self.params,
            auth=self.auth,
            cookies=self.cookies,
            hooks=self.hooks,
        )
        return p

    def __repr__(self):
        return '<Request [{}]>'.format(self.method)


class PreparedRequest:
    """The fully prepared request, ready to be sent.

    This object is generated from a :class:`Request <Request>` object, and
    should not be instantiated manually.
    """

    def __init__(self):
        self.method = None
        self.url = None
        self.headers = None
        self._body = None
        self.hooks = {}
        self._cookies = None

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, value):
        self._body = value

    def prepare(self, method=None, url=None, headers=None, files=None,
                data=None, json=None, params=None, auth=None, cookies=None,
                hooks=None):
        """Prepare the request."""
        self.prepare_method(method)
        self.prepare_url(url, params)
        self.prepare_headers(headers)
        self.prepare_cookies(cookies)
        self.prepare_body(data, files, json)
        self.prepare_auth(auth, url)
        self.prepare_hooks(hooks)

    def prepare_method(self, method):
        """Prepare the request method."""
        self.method = method
        if self.method is not None:
            self.method = self.method.upper()

    def prepare_url(self, url, params):
        """Prepare the request URL."""
        if url is None:
            raise InvalidURL("Invalid URL {!r}: No URL specified".format(url))

        # Encode params
        if params:
            if isinstance(params, (str, bytes)):
                # Already encoded
                encoded_params = params
            else:
                # Dict or list of tuples
                params = to_key_val_list(params)
                encoded_params = urlencode(params, doseq=True)

            # Add to URL
            if '?' in url:
                url = url + '&' + encoded_params
            else:
                url = url + '?' + encoded_params

        self.url = url

    def prepare_headers(self, headers):
        """Prepare headers."""
        self.headers = CaseInsensitiveDict()

        if headers:
            for key, value in headers.items():
                check_header_validity((key, value))
                self.headers[key] = value

    def prepare_body(self, data, files, json=None):
        """Prepare the request body."""
        body = None
        content_type = None
        content_length = None
        transfer_encoding = None

        if json is not None:
            # JSON body takes precedence
            content_type = 'application/json'
            try:
                body = json_module.dumps(json)
                if not isinstance(body, bytes):
                    body = body.encode('utf-8')
                content_length = len(body)
            except (ValueError, TypeError) as e:
                raise JSONDecodeError('Unable to encode JSON: {}'.format(e))

        elif files:
            # Multipart form data
            fields = []
            # Add file fields
            for key, file_info in files.items():
                if isinstance(file_info, (tuple, list)):
                    # (filename, fileobj) or (filename, fileobj, content_type)
                    fields.append((key, file_info))
                elif hasattr(file_info, 'read'):
                    # File object
                    filename = getattr(file_info, 'name', 'file')
                    fields.append((key, (filename, file_info)))
                else:
                    # String or bytes
                    fields.append((key, ('file', file_info)))

            body, content_type = encode_multipart_formdata(fields)
            content_length = len(body)

        elif data:
            # Form data or raw body
            if isinstance(data, str):
                body = data.encode('utf-8')
                content_length = len(body)
            elif isinstance(data, (dict, list)):
                # Dict or list - form encode
                body = urlencode(data, doseq=True)
                if isinstance(body, str):
                    body = body.encode('utf-8')
                content_type = 'application/x-www-form-urlencoded'
                content_length = len(body)
            else:
                body = data
                transfer_encoding = "chunked"
                if hasattr(data, 'read'):
                    try:
                        cur = data.tell()
                        end = data.seek(0, 2)
                        data.seek(cur)
                    except (AttributeError, OSError):
                        pass
                    else:
                        content_length = end - cur
                        transfer_encoding = None

        self.body = body

        # Set Content-Type header if not already set
        if content_type and 'content-type' not in self.headers:
            self.headers['Content-Type'] = content_type

        # Set Content-Length
        if content_length is not None:
            self.headers['Content-Length'] = str(content_length)

        if transfer_encoding is not None:
            self.headers['Transfer-Encoding'] = transfer_encoding
    
    def prepare_auth(self, auth, url=''):
        """Prepare authentication."""
        if auth is None:
            return

        if isinstance(auth, tuple) and len(auth) == 2:
            # Basic auth tuple
            from .auth import HTTPBasicAuth
            auth = HTTPBasicAuth(*auth)

        if isinstance(auth, AuthBase):
            auth(self)
        else:
            raise TypeError('Auth must be a tuple or AuthBase instance')

    def prepare_cookies(self, cookies):
        """Prepare cookies."""
        if isinstance(cookies, CookieJar):
            self._cookies = cookies
        else:
            self._cookies = CookieJar()
            if cookies:
                merge_cookies(self._cookies, cookies)

    def prepare_hooks(self, hooks):
        """Prepare hooks."""
        hooks = hooks or {}
        for event in hooks:
            self.register_hook(event, hooks[event])

    def register_hook(self, event, hook):
        """Register a hook."""
        if event not in self.hooks:
            self.hooks[event] = []

        if callable(hook):
            self.hooks[event].append(hook)
        elif hasattr(hook, '__iter__'):
            self.hooks[event].extend(h for h in hook if callable(h))

    def deregister_hook(self, event, hook):
        """Deregister a hook."""
        if event in self.hooks:
            try:
                self.hooks[event].remove(hook)
            except ValueError:
                pass

    def copy(self):
        """Copy this PreparedRequest."""
        p = PreparedRequest()
        p.method = self.method
        p.url = self.url
        p.headers = CaseInsensitiveDict(self.headers)
        p._body = self._body
        p.hooks = self.hooks.copy()
        p._cookies = self._cookies
        return p

    def __repr__(self):
        return '<PreparedRequest [{}]>'.format(self.method)


class Response:
    """The :class:`Response <Response>` object, which contains a
    server's response to an HTTP request.
    """

    def __init__(self):
        self._content = None
        self._content_consumed = False
        self._next = None

        #: Integer status code
        self.status_code = None

        #: Response headers (CaseInsensitiveDict)
        self.headers = CaseInsensitiveDict()

        #: Raw response from http.client
        self.raw = None

        #: Final URL location of Response
        self.url = None

        #: Encoding to decode with
        self.encoding = None

        #: A list of :class:`Response <Response>` objects from
        #: the history of the Request. Any redirect responses will end up here.
        self.history = []

        #: The :class:`PreparedRequest <PreparedRequest>` object that generated this response
        self.request = None

        #: The :class:`CookieJar <CookieJar>` of cookies the server sent back
        self.cookies = CookieJar()

        #: The amount of time elapsed between sending the request
        #: and the arrival of the response (as a timedelta)
        self.elapsed = None

        #: Reason phrase returned by server
        self.reason = None

    def __repr__(self):
        return '<Response [{}]>'.format(self.status_code)

    def __bool__(self):
        """Returns True if :attr:`status_code` is less than 400."""
        return self.ok

    def __nonzero__(self):
        """Returns True if :attr:`status_code` is less than 400."""
        return self.ok

    @property
    def ok(self):
        """Returns True if :attr:`status_code` is less than 400, False otherwise."""
        try:
            self.raise_for_status()
        except HTTPError:
            return False
        return True

    @property
    def is_redirect(self):
        """True if this Response is a well-formed HTTP redirect."""
        return 'location' in self.headers and self.status_code in (
            301, 302, 303, 307, 308
        )

    @property
    def is_permanent_redirect(self):
        """True if this Response one of the permanent versions of redirect."""
        return 'location' in self.headers and self.status_code in (301, 308)

    @property
    def apparent_encoding(self):
        """The apparent encoding, determined from content analysis."""
        # For microcontrollers, we'll just return utf-8
        return 'utf-8'

    def iter_content(self, chunk_size=1, decode_unicode=False):
        """Iterate over the response data."""
        if self._content_consumed and self._content is None:
            raise StreamConsumedError('The content for this response was already consumed')

        if self._content is not None:
            # Content already loaded
            content = self._content
            if decode_unicode:
                encoding = self.encoding or 'utf-8'
                if isinstance(content, bytes):
                    content = content.decode(encoding, errors='replace')

            yield from iter_slices(content, chunk_size)
        else:
            # Stream from raw response
            if not self.raw:
                return

            try:
                it = iter_chunks(self.raw, chunk_size)
                if decode_unicode:
                    it = stream_decode_response_unicode(it, self.encoding)
                yield from it
                        
            finally:
                self._content_consumed = True

    def iter_lines(self, chunk_size=512, decode_unicode=False, delimiter=None):
        """Iterate over the response data, one line at a time."""
        pending = None

        for chunk in self.iter_content(chunk_size=chunk_size, decode_unicode=decode_unicode):
            if pending is not None:
                chunk = pending + chunk

            if delimiter:
                lines = chunk.split(delimiter)
            else:
                lines = chunk.splitlines()

            # Keep last partial line
            if lines and lines[-1] and chunk and not chunk.endswith(
                delimiter or ('\r\n' if isinstance(chunk, str) else b'\r\n')
            ):
                pending = lines[-1]
                lines = lines[:-1]
            else:
                pending = None

            for line in lines:
                yield line

        if pending is not None:
            yield pending

    @property
    def content(self):
        """Content of the response, in bytes."""
        if self._content is None:
            # Read content if not already read
            if self._content_consumed:
                raise RuntimeError('The content for this response was already consumed')

            if self.raw:
                try:
                    self._content = self.raw.read()
                except Exception as e:
                    raise ConnectionError('Failed to read response: {}'.format(e))
            else:
                self._content = b''

            self._content_consumed = True

        return self._content

    @property
    def text(self):
        """Content of the response, in unicode."""
        content = self.content
        if content is None:
            return None

        # Determine encoding
        encoding = self.encoding

        if not encoding:
            # Try to get from headers
            encoding = get_encoding_from_headers(self.headers)

        if not encoding:
            # Default to utf-8
            encoding = 'utf-8'

        try:
            return content.decode(encoding, errors='replace')
        except (LookupError, TypeError):
            return content.decode('utf-8', errors='replace')

    def json(self, **kwargs):
        """Returns the json-encoded content of a response."""
        if not self.content:
            return None

        try:
            return json_module.loads(self.text, **kwargs)
        # except json_module.JSONDecodeError as e:
        #     raise JSONDecodeError('Failed to decode JSON: {}'.format(e))
        except ValueError as e:
            raise JSONDecodeError('Failed to decode JSON: {}'.format(e))

    @property
    def links(self):
        """Returns the parsed header links of the response, if any."""
        from .utils import parse_header_links

        header = self.headers.get('link')
        if header:
            return parse_header_links(header)
        return []

    def raise_for_status(self):
        """Raises :class:`HTTPError`, if one occurred."""
        if 400 <= self.status_code < 500:
            reason = _codes.get(self.status_code, 'Client Error')
            raise HTTPError('{} Client Error: {} for url: {}'.format(
                self.status_code, reason, self.url
            ), response=self)

        elif 500 <= self.status_code < 600:
            reason = _codes.get(self.status_code, 'Server Error')
            raise HTTPError('{} Server Error: {} for url: {}'.format(
                self.status_code, reason, self.url
            ), response=self)

    def close(self):
        """Release the connection back to the pool."""
        if self.raw:
            if hasattr(self.raw, 'close'):
                self.raw.close()
