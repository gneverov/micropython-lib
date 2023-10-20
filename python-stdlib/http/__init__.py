# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

class HTTPStatus:
    """HTTP status codes and reason phrases

    Status codes from the following RFCs are all observed:

        * RFC 7231: Hypertext Transfer Protocol (HTTP/1.1), obsoletes 2616
        * RFC 6585: Additional HTTP Status Codes
        * RFC 3229: Delta encoding in HTTP
        * RFC 4918: HTTP Extensions for WebDAV, obsoletes 2518
        * RFC 5842: Binding Extensions to WebDAV
        * RFC 7238: Permanent Redirect
        * RFC 2295: Transparent Content Negotiation in HTTP
        * RFC 2774: An HTTP Extension Framework
        * RFC 7725: An HTTP Status Code to Report Legal Obstacles
        * RFC 7540: Hypertext Transfer Protocol Version 2 (HTTP/2)
        * RFC 2324: Hyper Text Coffee Pot Control Protocol (HTCPCP/1.0)
        * RFC 8297: An HTTP Status Code for Indicating Hints
        * RFC 8470: Using Early Data in HTTP
    """
    def make_enum(value, phrase):
        return value

    # informational
    CONTINUE = make_enum(100, 'Continue')
    SWITCHING_PROTOCOLS = make_enum(101, 'Switching Protocols')
    PROCESSING = make_enum(102, 'Processing')
    EARLY_HINTS = make_enum(103, 'Early Hints')

    # success
    OK = make_enum(200, 'OK')
    CREATED = make_enum(201, 'Created')
    ACCEPTED = make_enum(202, 'Accepted')
    NON_AUTHORITATIVE_INFORMATION = make_enum(203, 'Non-Authoritative Information')
    NO_CONTENT = make_enum(204, 'No Content')
    RESET_CONTENT = make_enum(205, 'Reset Content')
    PARTIAL_CONTENT = make_enum(206, 'Partial Content')
    MULTI_STATUS = make_enum(207, 'Multi-Status')
    ALREADY_REPORTED = make_enum(208, 'Already Reported')
    IM_USED = make_enum(226, 'IM Used')

    # redirection
    MULTIPLE_CHOICES = make_enum(300, 'Multiple Choices')
    MOVED_PERMANENTLY = make_enum(301, 'Moved Permanently')
    FOUND = make_enum(302, 'Found')
    SEE_OTHER = make_enum(303, 'See Other')
    NOT_MODIFIED = make_enum(304, 'Not Modified')
    USE_PROXY = make_enum(305, 'Use Proxy')
    TEMPORARY_REDIRECT = make_enum(307, 'Temporary Redirect')
    PERMANENT_REDIRECT = make_enum(308, 'Permanent Redirect')

    # client error
    BAD_REQUEST = make_enum(400, 'Bad Request')
    UNAUTHORIZED = make_enum(401, 'Unauthorized')
    PAYMENT_REQUIRED = make_enum(402, 'Payment Required')
    FORBIDDEN = make_enum(403, 'Forbidden')
    NOT_FOUND = make_enum(404, 'Not Found')
    METHOD_NOT_ALLOWED = make_enum(405, 'Method Not Allowed')
    NOT_ACCEPTABLE = make_enum(406, 'Not Acceptable')
    PROXY_AUTHENTICATION_REQUIRED = make_enum(407, 'Proxy Authentication Required')
    REQUEST_TIMEOUT = make_enum(408, 'Request Timeout')
    CONFLICT = make_enum(409, 'Conflict')
    GONE = make_enum(410, 'Gone')
    LENGTH_REQUIRED = make_enum(411, 'Length Required')
    PRECONDITION_FAILED = make_enum(412, 'Precondition Failed')
    REQUEST_ENTITY_TOO_LARGE = make_enum(413, 'Request Entity Too Large')
    REQUEST_URI_TOO_LONG = make_enum(414, 'Request-URI Too Long')
    UNSUPPORTED_MEDIA_TYPE = make_enum(415, 'Unsupported Media Type')
    REQUESTED_RANGE_NOT_SATISFIABLE = make_enum(416, 'Requested Range Not Satisfiable')
    EXPECTATION_FAILED = make_enum(417, 'Expectation Failed')
    IM_A_TEAPOT = make_enum(418, 'I\'m a Teapot')
    MISDIRECTED_REQUEST = make_enum(421, 'Misdirected Request')
    UNPROCESSABLE_ENTITY = make_enum(422, 'Unprocessable Entity')
    LOCKED = make_enum(423, 'Locked')
    FAILED_DEPENDENCY = make_enum(424, 'Failed Dependency')
    TOO_EARLY = make_enum(425, 'Too Early')
    UPGRADE_REQUIRED = make_enum(426, 'Upgrade Required')
    PRECONDITION_REQUIRED = make_enum(428, 'Precondition Required')
    TOO_MANY_REQUESTS = make_enum(429, 'Too Many Requests')
    REQUEST_HEADER_FIELDS_TOO_LARGE = make_enum(431, 'Request Header Fields Too Large')
    UNAVAILABLE_FOR_LEGAL_REASONS = make_enum(451, 'Unavailable For Legal Reasons')

    # server errors
    INTERNAL_SERVER_ERROR = make_enum(500, 'Internal Server Error')
    NOT_IMPLEMENTED = make_enum(501, 'Not Implemented')
    BAD_GATEWAY = make_enum(502, 'Bad Gateway')
    SERVICE_UNAVAILABLE = make_enum(503, 'Service Unavailable')
    GATEWAY_TIMEOUT = make_enum(504, 'Gateway Timeout')
    HTTP_VERSION_NOT_SUPPORTED = make_enum(505, 'HTTP Version Not Supported')
    VARIANT_ALSO_NEGOTIATES = make_enum(506, 'Variant Also Negotiates')
    INSUFFICIENT_STORAGE = make_enum(507, 'Insufficient Storage')
    LOOP_DETECTED = make_enum(508, 'Loop Detected')
    NOT_EXTENDED = make_enum(510, 'Not Extended')
    NETWORK_AUTHENTICATION_REQUIRED = make_enum(511, 'Network Authentication Required')


class HTTPMethod:
    """HTTP methods and descriptions

    Methods from the following RFCs are all observed:

        * RFC 7231: Hypertext Transfer Protocol (HTTP/1.1), obsoletes 2616
        * RFC 5789: PATCH Method for HTTP
    """
    CONNECT = 'CONNECT'
    DELETE = 'DELETE'
    GET = 'GET'
    HEAD = 'HEAD'
    OPTIONS = 'OPTIONS'
    PATCH = 'PATCH'
    POST = 'POST'
    PUT = 'PUT'
    TRACE = 'TRACE'