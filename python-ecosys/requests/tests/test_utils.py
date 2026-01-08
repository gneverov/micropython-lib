import copy
import filecmp
import os
import tarfile
import tempfile
import unittest
import warnings
import zipfile
from collections import deque
from io import BytesIO
from unittest.mock import patch, MagicMock

from requests import compat
from requests._internal_utils import unicode_is_ascii
from requests.cookies import RequestsCookieJar
from requests.structures import CaseInsensitiveDict
from requests.utils import (
    _parse_content_type_header,
    add_dict_to_cookiejar,
    address_in_network,
    dotted_netmask,
    extract_zipped_paths,
    get_auth_from_url,
    get_encoding_from_headers,
    get_encodings_from_content,
    get_environ_proxies,
    guess_filename,
    guess_json_utf,
    is_ipv4_address,
    is_valid_cidr,
    iter_slices,
    parse_dict_header,
    parse_header_links,
    prepend_scheme_if_needed,
    requote_uri,
    select_proxy,
    set_environ,
    should_bypass_proxies,
    super_len,
    to_key_val_list,
    to_native_string,
    unquote_header_value,
    unquote_unreserved,
    urldefragauth,
)

from .compat import StringIO, cStringIO


class TestSuperLen(unittest.TestCase):
    def test_io_streams(self):
        """Ensures that we properly deal with different kinds of IO streams."""
        test_cases = [
            (StringIO.StringIO, "Test"),
            (BytesIO, b"Test"),
        ]
        if cStringIO is not None:
            test_cases.append((cStringIO, "Test"))

        for stream, value in test_cases:
            with self.subTest(stream=stream, value=value):
                self.assertEqual(super_len(stream()), 0)
                self.assertEqual(super_len(stream(value)), 4)

    def test_super_len_correctly_calculates_len_of_partially_read_file(self):
        """Ensure that we handle partially consumed file like objects."""
        s = StringIO.StringIO()
        s.write("foobarbogus")
        self.assertEqual(super_len(s), 0)

    def test_super_len_handles_files_raising_weird_errors_in_tell(self):
        """If tell() raises errors, assume the cursor is at position zero."""
        for error in [IOError, OSError]:
            with self.subTest(error=error):
                class BoomFile:
                    def __len__(self):
                        return 5

                    def tell(self):
                        raise error()

                self.assertEqual(super_len(BoomFile()), 0)

    def test_super_len_tell_ioerror(self):
        """Ensure that if tell gives an IOError super_len doesn't fail"""
        for error in [IOError, OSError]:
            with self.subTest(error=error):
                class NoLenBoomFile:
                    def tell(self):
                        raise error()

                    def seek(self, offset, whence):
                        pass

                self.assertEqual(super_len(NoLenBoomFile()), 0)

    def test_string(self):
        self.assertEqual(super_len("Test"), 4)

    def test_file(self):
        test_cases = [
            ("r", 1),
            ("rb", 0),
        ]
        for mode, warnings_num in test_cases:
            with self.subTest(mode=mode, warnings_num=warnings_num):
                with tempfile.TemporaryDirectory() as tmpdir:
                    file_path = os.path.join(tmpdir, "test.txt")
                    with open(file_path, "w") as f:
                        f.write("Test")

                    with warnings.catch_warnings(record=True) as w:
                        warnings.simplefilter("always")
                        with open(file_path, mode) as fd:
                            self.assertEqual(super_len(fd), 4)
                        self.assertEqual(len(w), warnings_num)

    def test_tarfile_member(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")
            with open(file_path, "w") as f:
                f.write("Test")

            tar_path = os.path.join(tmpdir, "test.tar")
            with tarfile.open(tar_path, "w") as tar:
                tar.add(file_path, arcname="test.txt")

            with tarfile.open(tar_path) as tar:
                member = tar.extractfile("test.txt")
                self.assertEqual(super_len(member), 4)

    def test_super_len_with__len__(self):
        foo = [1, 2, 3, 4]
        len_foo = super_len(foo)
        self.assertEqual(len_foo, 4)

    def test_super_len_with_no__len__(self):
        class LenFile:
            def __init__(self):
                self.len = 5

        self.assertEqual(super_len(LenFile()), 5)

    def test_super_len_with_tell(self):
        foo = StringIO.StringIO("12345")
        self.assertEqual(super_len(foo), 5)
        foo.read(2)
        self.assertEqual(super_len(foo), 3)

    def test_super_len_with_fileno(self):
        with open(__file__, "rb") as f:
            length = super_len(f)
            file_data = f.read()
        self.assertEqual(length, len(file_data))

    def test_super_len_with_no_matches(self):
        """Ensure that objects without any length methods default to 0"""
        self.assertEqual(super_len(object()), 0)


class TestToKeyValList(unittest.TestCase):
    def test_valid(self):
        test_cases = [
            ([("key", "val")], [("key", "val")]),
            ((("key", "val"),), [("key", "val")]),
            ({"key": "val"}, [("key", "val")]),
            (None, None),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertEqual(to_key_val_list(value), expected)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            to_key_val_list("string")


class TestUnquoteHeaderValue(unittest.TestCase):
    def test_valid(self):
        test_cases = [
            (None, None),
            ("Test", "Test"),
            ('"Test"', "Test"),
            ('"Test\\\\"', "Test\\"),
            ('"\\\\Comp\\Res"', "\\Comp\\Res"),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertEqual(unquote_header_value(value), expected)

    def test_is_filename(self):
        self.assertEqual(unquote_header_value('"\\\\Comp\\Res"', True), "\\\\Comp\\Res")


class TestGetEnvironProxies(unittest.TestCase):
    """Ensures that IP addresses are correctly matches with ranges
    in no_proxy variable.
    """

    def setUp(self):
        self.no_proxy_value = "192.168.0.0/24,127.0.0.1,localhost.localdomain,172.16.1.1"

    def test_bypass(self):
        urls = [
            "http://192.168.0.1:5000/",
            "http://192.168.0.1/",
            "http://172.16.1.1/",
            "http://172.16.1.1:5000/",
            "http://localhost.localdomain:5000/v1.0/",
        ]
        for env_var in ["no_proxy", "NO_PROXY"]:
            for url in urls:
                with self.subTest(env_var=env_var, url=url):
                    with patch.dict(os.environ, {env_var: self.no_proxy_value}):
                        self.assertEqual(get_environ_proxies(url, no_proxy=None), {})

    def test_not_bypass(self):
        urls = [
            "http://192.168.1.1:5000/",
            "http://192.168.1.1/",
            "http://www.requests.com/",
        ]
        for env_var in ["no_proxy", "NO_PROXY"]:
            for url in urls:
                with self.subTest(env_var=env_var, url=url):
                    with patch.dict(os.environ, {env_var: self.no_proxy_value}):
                        self.assertNotEqual(get_environ_proxies(url, no_proxy=None), {})

    def test_bypass_no_proxy_keyword(self):
        urls = [
            "http://192.168.1.1:5000/",
            "http://192.168.1.1/",
            "http://www.requests.com/",
        ]
        for env_var in ["no_proxy", "NO_PROXY"]:
            for url in urls:
                with self.subTest(env_var=env_var, url=url):
                    with patch.dict(os.environ, {env_var: self.no_proxy_value}):
                        no_proxy = "192.168.1.1,requests.com"
                        self.assertEqual(get_environ_proxies(url, no_proxy=no_proxy), {})

    def test_not_bypass_no_proxy_keyword(self):
        """This is testing that the 'no_proxy' argument overrides the
        environment variable 'no_proxy'
        """
        urls = [
            "http://192.168.0.1:5000/",
            "http://192.168.0.1/",
            "http://172.16.1.1/",
            "http://172.16.1.1:5000/",
            "http://localhost.localdomain:5000/v1.0/",
        ]
        for env_var in ["no_proxy", "NO_PROXY"]:
            for url in urls:
                with self.subTest(env_var=env_var, url=url):
                    env = {
                        env_var: self.no_proxy_value,
                        "http_proxy": "http://proxy.example.com:3128/"
                    }
                    with patch.dict(os.environ, env):
                        no_proxy = "192.168.1.1,requests.com"
                        self.assertNotEqual(get_environ_proxies(url, no_proxy=no_proxy), {})


class TestIsIPv4Address(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_ipv4_address("8.8.8.8"))

    def test_invalid(self):
        values = ("8.8.8.8.8", "localhost.localdomain")
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_ipv4_address(value))


class TestIsValidCIDR(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_valid_cidr("192.168.1.0/24"))

    def test_invalid(self):
        values = [
            "8.8.8.8",
            "192.168.1.0/a",
            "192.168.1.0/128",
            "192.168.1.0/-1",
            "192.168.1.999/24",
        ]
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_valid_cidr(value))


class TestAddressInNetwork(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(address_in_network("192.168.1.1", "192.168.1.0/24"))

    def test_invalid(self):
        self.assertFalse(address_in_network("172.16.0.1", "192.168.1.0/24"))


class TestGuessFilename(unittest.TestCase):
    def test_guess_filename_invalid(self):
        values = [1, type("Fake", (object,), {"name": 1})()]
        for value in values:
            with self.subTest(value=value):
                self.assertIsNone(guess_filename(value))

    def test_guess_filename_valid(self):
        test_cases = [
            (b"value", compat.bytes),
            (b"value".decode("utf-8"), compat.str),
        ]
        for value, expected_type in test_cases:
            with self.subTest(value=value, expected_type=expected_type):
                obj = type("Fake", (object,), {"name": value})()
                result = guess_filename(obj)
                self.assertEqual(result, value)
                self.assertIsInstance(result, expected_type)


class TestExtractZippedPaths(unittest.TestCase):
    def test_unzipped_paths_unchanged(self):
        # Note: We can't use pytest.__file__ in unittest, so we'll skip that test case
        paths = [
            "/",
            __file__,
            "/etc/invalid/location",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(path, extract_zipped_paths(path))

    def test_zipped_paths_extracted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            zipped_py = os.path.join(tmpdir, "test.zip")
            with zipfile.ZipFile(zipped_py, "w") as f:
                f.write(__file__)

            _, name = os.path.splitdrive(__file__)
            zipped_path = os.path.join(zipped_py, name.lstrip(r"\/"))
            extracted_path = extract_zipped_paths(zipped_path)

            self.assertNotEqual(extracted_path, zipped_path)
            self.assertTrue(os.path.exists(extracted_path))
            self.assertTrue(filecmp.cmp(extracted_path, __file__))

    def test_invalid_unc_path(self):
        path = r"\\localhost\invalid\location"
        self.assertEqual(extract_zipped_paths(path), path)


class TestContentEncodingDetection(unittest.TestCase):
    def test_none(self):
        encodings = get_encodings_from_content("")
        self.assertFalse(len(encodings))

    def test_pragmas(self):
        contents = [
            # HTML5 meta charset attribute
            '<meta charset="UTF-8">',
            # HTML4 pragma directive
            '<meta http-equiv="Content-type" content="text/html;charset=UTF-8">',
            # XHTML 1.x served with text/html MIME type
            '<meta http-equiv="Content-type" content="text/html;charset=UTF-8" />',
            # XHTML 1.x served as XML
            '<?xml version="1.0" encoding="UTF-8"?>',
        ]
        for content in contents:
            with self.subTest(content=content):
                encodings = get_encodings_from_content(content)
                self.assertEqual(len(encodings), 1)
                self.assertEqual(encodings[0], "UTF-8")

    def test_precedence(self):
        content = """
        <?xml version="1.0" encoding="XML"?>
        <meta charset="HTML5">
        <meta http-equiv="Content-type" content="text/html;charset=HTML4" />
        """.strip()
        self.assertEqual(get_encodings_from_content(content), ["HTML5", "HTML4", "XML"])


class TestGuessJSONUTF(unittest.TestCase):
    def test_encoded(self):
        encodings = [
            "utf-32",
            "utf-8-sig",
            "utf-16",
            "utf-8",
            "utf-16-be",
            "utf-16-le",
            "utf-32-be",
            "utf-32-le",
        ]
        for encoding in encodings:
            with self.subTest(encoding=encoding):
                data = "{}".encode(encoding)
                self.assertEqual(guess_json_utf(data), encoding)

    def test_bad_utf_like_encoding(self):
        self.assertIsNone(guess_json_utf(b"\x00\x00\x00\x00"))

    def test_guess_by_bom(self):
        test_cases = [
            ("utf-16-be", "utf-16"),
            ("utf-16-le", "utf-16"),
            ("utf-32-be", "utf-32"),
            ("utf-32-le", "utf-32"),
        ]
        for encoding, expected in test_cases:
            with self.subTest(encoding=encoding, expected=expected):
                data = "\ufeff{}".encode(encoding)
                self.assertEqual(guess_json_utf(data), expected)


USER = PASSWORD = "%!*'();:@&=+$,/?#[] "
ENCODED_USER = compat.quote(USER, "")
ENCODED_PASSWORD = compat.quote(PASSWORD, "")


class TestGetAuthFromUrl(unittest.TestCase):
    def test_get_auth_from_url(self):
        test_cases = [
            (
                f"http://{ENCODED_USER}:{ENCODED_PASSWORD}@request.com/url.html#test",
                (USER, PASSWORD),
            ),
            ("http://user:pass@complex.url.com/path?query=yes", ("user", "pass")),
            (
                "http://user:pass%20pass@complex.url.com/path?query=yes",
                ("user", "pass pass"),
            ),
            ("http://user:pass pass@complex.url.com/path?query=yes", ("user", "pass pass")),
            (
                "http://user%25user:pass@complex.url.com/path?query=yes",
                ("user%user", "pass"),
            ),
            (
                "http://user:pass%23pass@complex.url.com/path?query=yes",
                ("user", "pass#pass"),
            ),
            ("http://complex.url.com/path?query=yes", ("", "")),
        ]
        for url, auth in test_cases:
            with self.subTest(url=url, auth=auth):
                self.assertEqual(get_auth_from_url(url), auth)


class TestRequoteUri(unittest.TestCase):
    def test_requote_uri_with_unquoted_percents(self):
        """See: https://github.com/psf/requests/issues/2356"""
        test_cases = [
            (
                # Ensure requoting doesn't break expectations
                "http://example.com/fiz?buz=%25ppicture",
                "http://example.com/fiz?buz=%25ppicture",
            ),
            (
                # Ensure we handle unquoted percent signs in redirects
                "http://example.com/fiz?buz=%ppicture",
                "http://example.com/fiz?buz=%25ppicture",
            ),
        ]
        for uri, expected in test_cases:
            with self.subTest(uri=uri, expected=expected):
                self.assertEqual(requote_uri(uri), expected)


class TestUnquoteUnreserved(unittest.TestCase):
    def test_unquote_unreserved(self):
        test_cases = [
            (
                # Illegal bytes
                "http://example.com/?a=%--",
                "http://example.com/?a=%--",
            ),
            (
                # Reserved characters
                "http://example.com/?a=%300",
                "http://example.com/?a=00",
            ),
        ]
        for uri, expected in test_cases:
            with self.subTest(uri=uri, expected=expected):
                self.assertEqual(unquote_unreserved(uri), expected)


class TestDottedNetmask(unittest.TestCase):
    def test_dotted_netmask(self):
        test_cases = [
            (8, "255.0.0.0"),
            (24, "255.255.255.0"),
            (25, "255.255.255.128"),
        ]
        for mask, expected in test_cases:
            with self.subTest(mask=mask, expected=expected):
                self.assertEqual(dotted_netmask(mask), expected)


http_proxies = {
    "http": "http://http.proxy",
    "http://some.host": "http://some.host.proxy",
}
all_proxies = {
    "all": "socks5://http.proxy",
    "all://some.host": "socks5://some.host.proxy",
}
mixed_proxies = {
    "http": "http://http.proxy",
    "http://some.host": "http://some.host.proxy",
    "all": "socks5://http.proxy",
}


class TestSelectProxies(unittest.TestCase):
    def test_select_proxies(self):
        """Make sure we can select per-host proxies correctly."""
        test_cases = [
            ("hTTp://u:p@Some.Host/path", "http://some.host.proxy", http_proxies),
            ("hTTp://u:p@Other.Host/path", "http://http.proxy", http_proxies),
            ("hTTp:///path", "http://http.proxy", http_proxies),
            ("hTTps://Other.Host", None, http_proxies),
            ("file:///etc/motd", None, http_proxies),
            ("hTTp://u:p@Some.Host/path", "socks5://some.host.proxy", all_proxies),
            ("hTTp://u:p@Other.Host/path", "socks5://http.proxy", all_proxies),
            ("hTTp:///path", "socks5://http.proxy", all_proxies),
            ("hTTps://Other.Host", "socks5://http.proxy", all_proxies),
            ("http://u:p@other.host/path", "http://http.proxy", mixed_proxies),
            ("http://u:p@some.host/path", "http://some.host.proxy", mixed_proxies),
            ("https://u:p@other.host/path", "socks5://http.proxy", mixed_proxies),
            ("https://u:p@some.host/path", "socks5://http.proxy", mixed_proxies),
            ("https://", "socks5://http.proxy", mixed_proxies),
            # XXX: unsure whether this is reasonable behavior
            ("file:///etc/motd", "socks5://http.proxy", all_proxies),
        ]
        for url, expected, proxies in test_cases:
            with self.subTest(url=url, expected=expected, proxies=proxies):
                self.assertEqual(select_proxy(url, proxies), expected)


class TestParseDictHeader(unittest.TestCase):
    def test_parse_dict_header(self):
        test_cases = [
            ('foo="is a fish", bar="as well"', {"foo": "is a fish", "bar": "as well"}),
            ("key_without_value", {"key_without_value": None}),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertEqual(parse_dict_header(value), expected)


class TestParseContentTypeHeader(unittest.TestCase):
    def test__parse_content_type_header(self):
        test_cases = [
            ("application/xml", ("application/xml", {})),
            (
                "application/json ; charset=utf-8",
                ("application/json", {"charset": "utf-8"}),
            ),
            (
                "application/json ; Charset=utf-8",
                ("application/json", {"charset": "utf-8"}),
            ),
            ("text/plain", ("text/plain", {})),
            (
                "multipart/form-data; boundary = something ; boundary2='something_else' ; no_equals ",
                (
                    "multipart/form-data",
                    {
                        "boundary": "something",
                        "boundary2": "something_else",
                        "no_equals": True,
                    },
                ),
            ),
            (
                'multipart/form-data; boundary = something ; boundary2="something_else" ; no_equals ',
                (
                    "multipart/form-data",
                    {
                        "boundary": "something",
                        "boundary2": "something_else",
                        "no_equals": True,
                    },
                ),
            ),
            (
                "multipart/form-data; boundary = something ; 'boundary2=something_else' ; no_equals ",
                (
                    "multipart/form-data",
                    {
                        "boundary": "something",
                        "boundary2": "something_else",
                        "no_equals": True,
                    },
                ),
            ),
            (
                'multipart/form-data; boundary = something ; "boundary2=something_else" ; no_equals ',
                (
                    "multipart/form-data",
                    {
                        "boundary": "something",
                        "boundary2": "something_else",
                        "no_equals": True,
                    },
                ),
            ),
            ("application/json ; ; ", ("application/json", {})),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertEqual(_parse_content_type_header(value), expected)


class TestGetEncodingFromHeaders(unittest.TestCase):
    def test_get_encoding_from_headers(self):
        test_cases = [
            (CaseInsensitiveDict(), None),
            (
                CaseInsensitiveDict({"content-type": "application/json; charset=utf-8"}),
                "utf-8",
            ),
            (CaseInsensitiveDict({"content-type": "text/plain"}), "ISO-8859-1"),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertEqual(get_encoding_from_headers(value), expected)


class TestIterSlices(unittest.TestCase):
    def test_iter_slices(self):
        test_cases = [
            ("", 0),
            ("T", 1),
            ("Test", 4),
            ("Cont", 0),
            ("Other", -5),
            ("Content", None),
        ]
        for value, length in test_cases:
            with self.subTest(value=value, length=length):
                if length is None or (length <= 0 and len(value) > 0):
                    # Reads all content at once
                    self.assertEqual(len(list(iter_slices(value, length))), 1)
                else:
                    self.assertEqual(len(list(iter_slices(value, 1))), length)


class TestParseHeaderLinks(unittest.TestCase):
    def test_parse_header_links(self):
        test_cases = [
            (
                '<http:/.../front.jpeg>; rel=front; type="image/jpeg"',
                [{"url": "http:/.../front.jpeg", "rel": "front", "type": "image/jpeg"}],
            ),
            ("<http:/.../front.jpeg>", [{"url": "http:/.../front.jpeg"}]),
            ("<http:/.../front.jpeg>;", [{"url": "http:/.../front.jpeg"}]),
            (
                '<http:/.../front.jpeg>; type="image/jpeg",<http://.../back.jpeg>;',
                [
                    {"url": "http:/.../front.jpeg", "type": "image/jpeg"},
                    {"url": "http://.../back.jpeg"},
                ],
            ),
            ("", []),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertEqual(parse_header_links(value), expected)


class TestPrependSchemeIfNeeded(unittest.TestCase):
    def test_prepend_scheme_if_needed(self):
        test_cases = [
            ("example.com/path", "http://example.com/path"),
            ("//example.com/path", "http://example.com/path"),
            ("example.com:80", "http://example.com:80"),
            (
                "http://user:pass@example.com/path?query",
                "http://user:pass@example.com/path?query",
            ),
            ("http://user@example.com/path?query", "http://user@example.com/path?query"),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertEqual(prepend_scheme_if_needed(value, "http"), expected)


class TestToNativeString(unittest.TestCase):
    def test_to_native_string(self):
        test_cases = [
            ("T", "T"),
            (b"T", "T"),
            ("T", "T"),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertEqual(to_native_string(value), expected)


class TestUrldefragauth(unittest.TestCase):
    def test_urldefragauth(self):
        test_cases = [
            ("http://u:p@example.com/path?a=1#test", "http://example.com/path?a=1"),
            ("http://example.com/path", "http://example.com/path"),
            ("//u:p@example.com/path", "//example.com/path"),
            ("//example.com/path", "//example.com/path"),
            ("example.com/path", "//example.com/path"),
            ("scheme:u:p@example.com/path", "scheme://example.com/path"),
        ]
        for url, expected in test_cases:
            with self.subTest(url=url, expected=expected):
                self.assertEqual(urldefragauth(url), expected)


class TestShouldBypassProxies(unittest.TestCase):
    def test_should_bypass_proxies(self):
        """Tests for function should_bypass_proxies to check if proxy
        can be bypassed or not
        """
        test_cases = [
            ("http://192.168.0.1:5000/", True),
            ("http://192.168.0.1/", True),
            ("http://172.16.1.1/", True),
            ("http://172.16.1.1:5000/", True),
            ("http://localhost.localdomain:5000/v1.0/", True),
            ("http://google.com:6000/", True),
            ("http://172.16.1.12/", False),
            ("http://172.16.1.12:5000/", False),
            ("http://google.com:5000/v1.0/", False),
            ("file:///some/path/on/disk", True),
        ]
        env = {
            "no_proxy": "192.168.0.0/24,127.0.0.1,localhost.localdomain,172.16.1.1, google.com:6000",
            "NO_PROXY": "192.168.0.0/24,127.0.0.1,localhost.localdomain,172.16.1.1, google.com:6000",
        }
        for url, expected in test_cases:
            with self.subTest(url=url, expected=expected):
                with patch.dict(os.environ, env):
                    self.assertEqual(should_bypass_proxies(url, no_proxy=None), expected)

    def test_should_bypass_proxies_pass_only_hostname(self):
        """The proxy_bypass function should be called with a hostname or IP without
        a port number or auth credentials.
        """
        test_cases = [
            ("http://172.16.1.1/", "172.16.1.1"),
            ("http://172.16.1.1:5000/", "172.16.1.1"),
            ("http://user:pass@172.16.1.1", "172.16.1.1"),
            ("http://user:pass@172.16.1.1:5000", "172.16.1.1"),
            ("http://hostname/", "hostname"),
            ("http://hostname:5000/", "hostname"),
            ("http://user:pass@hostname", "hostname"),
            ("http://user:pass@hostname:5000", "hostname"),
        ]
        for url, expected in test_cases:
            with self.subTest(url=url, expected=expected):
                with patch("requests.utils.proxy_bypass") as proxy_bypass:
                    should_bypass_proxies(url, no_proxy=None)
                    proxy_bypass.assert_called_once_with(expected)


class TestAddDictToCookiejar(unittest.TestCase):
    def test_add_dict_to_cookiejar(self):
        """Ensure add_dict_to_cookiejar works for
        non-RequestsCookieJar CookieJars
        """
        cookiejars = [
            compat.cookielib.CookieJar(),
            RequestsCookieJar(),
        ]
        for cookiejar in cookiejars:
            with self.subTest(cookiejar=cookiejar):
                cookiedict = {"test": "cookies", "good": "cookies"}
                cj = add_dict_to_cookiejar(cookiejar, cookiedict)
                cookies = {cookie.name: cookie.value for cookie in cj}
                self.assertEqual(cookiedict, cookies)


class TestUnicodeIsAscii(unittest.TestCase):
    def test_unicode_is_ascii(self):
        test_cases = [
            ("test", True),
            ("æíöû", False),
            ("ジェーピーニック", False),
        ]
        for value, expected in test_cases:
            with self.subTest(value=value, expected=expected):
                self.assertIs(unicode_is_ascii(value), expected)


class TestShouldBypassProxiesNoProxy(unittest.TestCase):
    def test_should_bypass_proxies_no_proxy(self):
        """Tests for function should_bypass_proxies to check if proxy
        can be bypassed or not using the 'no_proxy' argument
        """
        test_cases = [
            ("http://192.168.0.1:5000/", True),
            ("http://192.168.0.1/", True),
            ("http://172.16.1.1/", True),
            ("http://172.16.1.1:5000/", True),
            ("http://localhost.localdomain:5000/v1.0/", True),
            ("http://172.16.1.12/", False),
            ("http://172.16.1.12:5000/", False),
            ("http://google.com:5000/v1.0/", False),
        ]
        no_proxy = "192.168.0.0/24,127.0.0.1,localhost.localdomain,172.16.1.1"
        for url, expected in test_cases:
            with self.subTest(url=url, expected=expected):
                # Test 'no_proxy' argument
                self.assertEqual(should_bypass_proxies(url, no_proxy=no_proxy), expected)


@unittest.skipIf(os.name != "nt", "Test only on Windows")
class TestShouldBypassProxiesWinRegistry(unittest.TestCase):
    def test_should_bypass_proxies_win_registry(self):
        """Tests for function should_bypass_proxies to check if proxy
        can be bypassed or not with Windows registry settings
        """
        test_cases = [
            ("http://192.168.0.1:5000/", True, None),
            ("http://192.168.0.1/", True, None),
            ("http://172.16.1.1/", True, None),
            ("http://172.16.1.1:5000/", True, None),
            ("http://localhost.localdomain:5000/v1.0/", True, None),
            ("http://172.16.1.22/", False, None),
            ("http://172.16.1.22:5000/", False, None),
            ("http://google.com:5000/v1.0/", False, None),
            ("http://mylocalhostname:5000/v1.0/", True, "<local>"),
            ("http://192.168.0.1/", False, ""),
        ]

        for url, expected, override in test_cases:
            with self.subTest(url=url, expected=expected, override=override):
                if override is None:
                    override = "192.168.*;127.0.0.1;localhost.localdomain;172.16.1.1"

                import winreg

                class RegHandle:
                    def Close(self):
                        pass

                ie_settings = RegHandle()
                proxyEnableValues = deque([1, "1"])

                def OpenKey(key, subkey):
                    return ie_settings

                def QueryValueEx(key, value_name):
                    if key is ie_settings:
                        if value_name == "ProxyEnable":
                            # this could be a string (REG_SZ) or a 32-bit number (REG_DWORD)
                            proxyEnableValues.rotate()
                            return [proxyEnableValues[0]]
                        elif value_name == "ProxyOverride":
                            return [override]

                env = {
                    "http_proxy": "",
                    "https_proxy": "",
                    "ftp_proxy": "",
                    "no_proxy": "",
                    "NO_PROXY": "",
                }
                with patch.dict(os.environ, env):
                    with patch.object(winreg, "OpenKey", OpenKey):
                        with patch.object(winreg, "QueryValueEx", QueryValueEx):
                            self.assertEqual(should_bypass_proxies(url, None), expected)

    def test_should_bypass_proxies_win_registry_bad_values(self):
        """Tests for function should_bypass_proxies to check if proxy
        can be bypassed or not with Windows invalid registry settings.
        """
        import winreg

        class RegHandle:
            def Close(self):
                pass

        ie_settings = RegHandle()

        def OpenKey(key, subkey):
            return ie_settings

        def QueryValueEx(key, value_name):
            if key is ie_settings:
                if value_name == "ProxyEnable":
                    # Invalid response; Should be an int or int-y value
                    return [""]
                elif value_name == "ProxyOverride":
                    return ["192.168.*;127.0.0.1;localhost.localdomain;172.16.1.1"]

        env = {
            "http_proxy": "",
            "https_proxy": "",
            "no_proxy": "",
            "NO_PROXY": "",
        }
        with patch.dict(os.environ, env):
            with patch.object(winreg, "OpenKey", OpenKey):
                with patch.object(winreg, "QueryValueEx", QueryValueEx):
                    self.assertFalse(should_bypass_proxies("http://172.16.1.1/", None))


class TestSetEnviron(unittest.TestCase):
    def test_set_environ(self):
        """Tests set_environ will set environ values and will restore the environ."""
        test_cases = [
            ("no_proxy", "192.168.0.0/24,127.0.0.1,localhost.localdomain"),
            ("no_proxy", None),
            ("a_new_key", "192.168.0.0/24,127.0.0.1,localhost.localdomain"),
            ("a_new_key", None),
        ]
        for env_name, value in test_cases:
            with self.subTest(env_name=env_name, value=value):
                environ_copy = copy.deepcopy(os.environ)
                with set_environ(env_name, value):
                    self.assertEqual(os.environ.get(env_name), value)

                self.assertEqual(os.environ, environ_copy)

    def test_set_environ_raises_exception(self):
        """Tests set_environ will raise exceptions in context when the
        value parameter is None."""
        with self.assertRaises(Exception) as context:
            with set_environ("test1", None):
                raise Exception("Expected exception")

        self.assertIn("Expected exception", str(context.exception))


if __name__ == '__main__':
    unittest.main()
