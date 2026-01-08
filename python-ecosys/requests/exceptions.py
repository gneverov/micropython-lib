"""
requests.exceptions
~~~~~~~~~~~~~~~~~~~

This module contains the set of Requests' exceptions.
"""
from warnings import Warning

class RequestException(OSError):
    """Base exception for all requests exceptions."""

    def __init__(self, *args, **kwargs):
        response = kwargs.pop('response', None)
        self.response = response
        self.request = kwargs.pop('request', None)
        if response is not None and not self.request and hasattr(response, 'request'):
            self.request = response.request
        super(RequestException, self).__init__(*args, **kwargs)


class InvalidJSONError(RequestException):
    """A JSON error occurred."""
    pass


class JSONDecodeError(InvalidJSONError):
    """Couldn't decode the text into json."""
    pass


class HTTPError(RequestException):
    """An HTTP error occurred."""
    pass


class ConnectionError(RequestException):
    """A Connection error occurred."""
    pass


class ProxyError(ConnectionError):
    """A proxy error occurred."""
    pass


class SSLError(ConnectionError):
    """An SSL error occurred."""
    pass


class Timeout(RequestException):
    """The request timed out."""
    pass


class ConnectTimeout(ConnectionError):  # Timeout
    """The request timed out while trying to connect to the remote server."""
    pass


class ReadTimeout(Timeout):
    """The server did not send any data in the allotted amount of time."""
    pass


class URLRequired(RequestException):
    """A valid URL is required to make a request."""
    pass


class TooManyRedirects(RequestException):
    """Too many redirects."""
    pass


class MissingSchema(RequestException):  # ValueError
    """The URL scheme (e.g. http or https) is missing."""
    pass


class InvalidSchema(RequestException):  # ValueError
    """The URL scheme provided is not valid."""
    pass


class InvalidURL(RequestException):  # ValueError
    """The URL provided was somehow invalid."""
    pass


class InvalidHeader(RequestException):  # ValueError
    """The header value provided was somehow invalid."""
    pass


class InvalidProxyURL(InvalidURL):
    """The proxy URL provided is invalid."""
    pass


class ChunkedEncodingError(RequestException):
    """The server declared chunked encoding but sent an invalid chunk."""
    pass


class ContentDecodingError(RequestException):
    """Failed to decode response content."""
    pass


class StreamConsumedError(RequestException):  # TypeError
    """The content for this response was already consumed."""
    pass


class RetryError(RequestException):
    """Custom retries logic failed."""
    pass


class UnrewindableBodyError(RequestException):
    """Requests encountered an error when trying to rewind a body."""
    pass


# Warnings
class RequestsWarning(Warning):
    """Base warning for Requests."""
    pass


class FileModeWarning(RequestsWarning):
    """A file was opened in text mode, but Requests determined its binary length."""
    pass


class RequestsDependencyWarning(RequestsWarning):
    """An imported dependency doesn't match the expected version range."""
    pass
