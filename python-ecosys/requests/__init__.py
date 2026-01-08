"""
Requests HTTP Library
~~~~~~~~~~~~~~~~~~~~~

Requests is an elegant and simple HTTP library for Python, built for human beings.

Basic GET usage:

   >>> import requests
   >>> r = requests.get('https://www.python.org')
   >>> r.status_code
   200
   >>> 'Python is a programming language' in r.content
   True

... or POST:

   >>> payload = dict(key1='value1', key2='value2')
   >>> r = requests.post('https://httpbin.org/post', data=payload)
   >>> print(r.text)
   {
     ...
     "form": {
       "key1": "value1",
       "key2": "value2"
     },
     ...
   }

The other HTTP methods are supported - see `requests.api`. Full documentation
is at <https://requests.readthedocs.io>.

:copyright: (c) 2012 by Kenneth Reitz.
:license: Apache2, see LICENSE for more details.
"""

__title__ = 'requests'
__version__ = '2.31.0'
__build__ = 0x023100
__author__ = 'Kenneth Reitz'
__license__ = 'Apache 2.0'
__copyright__ = 'Copyright 2012 Kenneth Reitz'

# Set default logging handler to avoid "No handler found" warnings.
import logging
try:  # Python 2.7+
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logging.getLogger(__name__).addHandler(NullHandler())

# Import API functions
from .api import (
    request, get, head, post, put, patch, delete, options
)

# Import session
from .sessions import Session, session

# Import models
from .models import Request, Response, PreparedRequest

# Import exceptions
from .exceptions import (
    RequestException, Timeout, URLRequired,
    TooManyRedirects, HTTPError, ConnectionError,
    FileModeWarning, ConnectTimeout, ReadTimeout,
    JSONDecodeError, InvalidJSONError,
    InvalidURL, InvalidHeader, InvalidSchema, MissingSchema,
    ChunkedEncodingError, ContentDecodingError,
    StreamConsumedError, RetryError, UnrewindableBodyError,
    RequestsWarning, RequestsDependencyWarning,
    SSLError, ProxyError
)

# Import auth
from .auth import AuthBase, HTTPBasicAuth, HTTPProxyAuth, HTTPDigestAuth

# Import cookies
from .cookies import CookieJar

# Import structures
from .structures import CaseInsensitiveDict

# Import adapters
from .adapters import HTTPAdapter

# Import utils
from .utils import (
    default_user_agent, default_headers,
)

# Warnings
import warnings

# FileModeWarnings go off per the default.
warnings.simplefilter('ignore', FileModeWarning, append=True)

# All public API
__all__ = (
    # API functions
    'request', 'get', 'head', 'post', 'put', 'patch', 'delete', 'options',

    # Session
    'Session', 'session',

    # Models
    'Request', 'Response', 'PreparedRequest',

    # Exceptions
    'RequestException', 'Timeout', 'URLRequired',
    'TooManyRedirects', 'HTTPError', 'ConnectionError',
    'ConnectTimeout', 'ReadTimeout',
    'JSONDecodeError', 'InvalidJSONError',
    'InvalidURL', 'InvalidHeader', 'InvalidSchema', 'MissingSchema',
    'ChunkedEncodingError', 'ContentDecodingError',
    'StreamConsumedError', 'RetryError', 'UnrewindableBodyError',
    'RequestsWarning', 'RequestsDependencyWarning',
    'SSLError', 'ProxyError',

    # Auth
    'AuthBase', 'HTTPBasicAuth', 'HTTPProxyAuth', 'HTTPDigestAuth',

    # Cookies
    'CookieJar',

    # Structures
    'CaseInsensitiveDict',

    # Adapters
    'HTTPAdapter',

    # Utils
    'default_user_agent', 'default_headers',
)
