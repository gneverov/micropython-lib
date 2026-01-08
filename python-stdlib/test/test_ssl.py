# Test the support for SSL and sockets

import sys
import unittest
from test import support
import socket
import select
import time
import datetime
import gc
import os
import errno
class pprint:
    pformat = str
import urllib.request
import threading
import traceback
try:
    import weakref
except ImportError:
    weakref = None
import platform
import functools
import functools
try:
    import ctypes
except ImportError:
    ctypes = None

ssl = support.import_module("ssl")


PROTOCOLS = [ssl.PROTOCOL_TLS_CLIENT, ssl.PROTOCOL_TLS_SERVER]
HOST = support.HOST
IS_LIBRESSL = ssl.OPENSSL_VERSION.startswith('LibreSSL')
IS_OPENSSL_1_1_0 = False
IS_OPENSSL_1_1_1 = False

def data_file(*name):
    return os.path.join(os.path.dirname(__file__), *name)

# The custom key and certificate files used in test_ssl are generated
# using Lib/test/make_ssl_certs.py.
# Other certificates are simply fetched from the Internet servers they
# are meant to authenticate.

CERTFILE = data_file("keycert.pem")
BYTES_CERTFILE = os.fsencode(CERTFILE)
ONLYCERT = data_file("ssl_cert.pem")
ONLYKEY = data_file("ssl_key.pem")
BYTES_ONLYCERT = os.fsencode(ONLYCERT)
BYTES_ONLYKEY = os.fsencode(ONLYKEY)
# CERTFILE_PROTECTED = data_file("keycert.passwd.pem")
# ONLYKEY_PROTECTED = data_file("ssl_key.passwd.pem")
KEY_PASSWORD = "somepass"
CAPATH = data_file("capath")
BYTES_CAPATH = os.fsencode(CAPATH)
CAFILE_NEURONIO = data_file("capath", "4e1295a3.0")
# CAFILE_CACERT = data_file("capath", "5ed36f99.0")

CERTFILE_INFO = {
    'issuer': ((('countryName', 'XY'),),
               (('localityName', 'Castle Anthrax'),),
               (('organizationName', 'Python Software Foundation'),),
               (('commonName', 'localhost'),)),
    'notAfter': 'Aug 26 14:23:15 2028 GMT',
    'notBefore': 'Aug 29 14:23:15 2018 GMT',
    'serialNumber': '98A7CF88C74A32ED',
    'subject': ((('countryName', 'XY'),),
             (('localityName', 'Castle Anthrax'),),
             (('organizationName', 'Python Software Foundation'),),
             (('commonName', 'localhost'),)),
    'subjectAltName': (('DNS', 'localhost'),),
    'version': 3
}

# empty CRL
CRLFILE = data_file("revocation.crl")

# Two keys and certs signed by the same CA (for SNI tests)
SIGNED_CERTFILE = data_file("keycert3.pem")
SIGNED_CERTFILE_HOSTNAME = 'localhost'

SIGNED_CERTFILE_INFO = {
    'OCSP': ('http://testca.pythontest.net/testca/ocsp/',),
    'caIssuers': ('http://testca.pythontest.net/testca/pycacert.cer',),
    'crlDistributionPoints': ('http://testca.pythontest.net/testca/revocation.crl',),
    'issuer': ((('countryName', 'XY'),),
            (('organizationName', 'Python Software Foundation CA'),),
            (('commonName', 'our-ca-server'),)),
    'notAfter': 'Jul  7 14:23:16 2028 GMT',
    'notBefore': 'Aug 29 14:23:16 2018 GMT',
    'serialNumber': 'CB2D80995A69525C',
    'subject': ((('countryName', 'XY'),),
             (('localityName', 'Castle Anthrax'),),
             (('organizationName', 'Python Software Foundation'),),
             (('commonName', 'localhost'),)),
    'subjectAltName': (('DNS', 'localhost'),),
    'version': 3
}

SIGNED_CERTFILE2 = data_file("keycert4.pem")
SIGNED_CERTFILE2_HOSTNAME = 'fakehostname'
SIGNED_CERTFILE_ECC = data_file("keycertecc.pem")
SIGNED_CERTFILE_ECC_HOSTNAME = 'localhost-ecc'

# Same certificate as pycacert.pem, but without extra text in file
SIGNING_CA = data_file("capath", "ceff1710.0")
# cert with all kinds of subject alt names
ALLSANFILE = data_file("allsans.pem")
IDNSANSFILE = data_file("idnsans.pem")

REMOTE_HOST = "self-signed.pythontest.net"

EMPTYCERT = data_file("nullcert.pem")
BADCERT = data_file("badcert.pem")
NONEXISTINGCERT = data_file("XXXnonexisting.pem")
BADKEY = data_file("badkey.pem")
NOKIACERT = data_file("nokia.pem")
NULLBYTECERT = data_file("nullbytecert.pem")
TALOS_INVALID_CRLDP = data_file("talos-2019-0758.pem")

DHFILE = data_file("ffdh3072.pem")
BYTES_DHFILE = os.fsencode(DHFILE)

# Not defined in all versions of OpenSSL
OP_NO_COMPRESSION = getattr(ssl, "OP_NO_COMPRESSION", 0)
OP_SINGLE_DH_USE = getattr(ssl, "OP_SINGLE_DH_USE", 0)
OP_SINGLE_ECDH_USE = getattr(ssl, "OP_SINGLE_ECDH_USE", 0)
OP_CIPHER_SERVER_PREFERENCE = getattr(ssl, "OP_CIPHER_SERVER_PREFERENCE", 0)
OP_ENABLE_MIDDLEBOX_COMPAT = getattr(ssl, "OP_ENABLE_MIDDLEBOX_COMPAT", 0)

def seclevel_workaround(*ctxs):
    pass


def has_tls_version(version):
    """Check if a TLS/SSL version is enabled

    :param version: TLS version name or ssl.TLSVersion member
    :return: bool
    """
    return getattr(ssl, f'HAS_{version}', False)


def requires_tls_version(version):
    """Decorator to skip tests when a required TLS version is not available

    :param version: TLS version name or ssl.TLSVersion member
    :return:
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            if not has_tls_version(version):
                raise unittest.SkipTest(f"{version} is not available.")
            else:
                return func(*args, **kw)
        return wrapper
    return decorator


requires_minimum_version = unittest.skipUnless(
    hasattr(ssl.SSLContext, 'minimum_version'),
    "required OpenSSL >= 1.1.0g"
)


def handle_error(prefix):
    exc_format = ' '.join(traceback.format_exception(*sys.exc_info()))
    if support.verbose:
        sys.stdout.write(prefix + exc_format)

def can_clear_options():
    # 0.9.8m or higher
    return False

def no_sslv2_implies_sslv3_hello():
    # 0.9.7h or higher
    return False

def have_verify_flags():
    # 0.9.8 or higher
    return False

def _have_secp_curves():
    if not ssl.HAS_ECDH:
        return False
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ctx.set_ecdh_curve("secp384r1")
    except ValueError:
        return False
    else:
        return True


HAVE_SECP_CURVES = _have_secp_curves()


def utc_offset(): #NOTE: ignore issues like #1647654
    # local time = utc time + utc offset
    if time.daylight and time.localtime().tm_isdst > 0:
        return -time.altzone  # seconds
    return -time.timezone

def asn1time(cert_time):
    # Some versions of OpenSSL ignore seconds, see #18207
    # 0.9.8.i
    if ssl._OPENSSL_API_VERSION == (0, 9, 8, 9, 15):
        fmt = "%b %d %H:%M:%S %Y GMT"
        dt = datetime.datetime.strptime(cert_time, fmt)
        dt = dt.replace(second=0)
        cert_time = dt.strftime(fmt)
        # %d adds leading zero but ASN1_TIME_print() uses leading space
        if cert_time[4] == "0":
            cert_time = cert_time[:4] + " " + cert_time[5:]

    return cert_time

needs_sni = unittest.skipUnless(ssl.HAS_SNI, "SNI support needed for this test")


def test_wrap_socket(sock, *,
                     cert_reqs=ssl.CERT_NONE, ca_certs=None,
                     ciphers=None, certfile=None, keyfile=None,
                     **kwargs):
    if not kwargs.get("server_side"):
        kwargs["server_hostname"] = SIGNED_CERTFILE_HOSTNAME
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if cert_reqs is not None:
        if cert_reqs == ssl.CERT_NONE:
            context.check_hostname = False
        context.verify_mode = cert_reqs
    if ca_certs is not None:
        context.load_verify_locations(ca_certs)
    if certfile is not None or keyfile is not None:
        context.load_cert_chain(certfile, keyfile)
    if ciphers is not None:
        context.set_ciphers(ciphers)
    return context.wrap_socket(sock, **kwargs)


def testing_context(server_cert=SIGNED_CERTFILE):
    """Create context

    client_context, server_context, hostname = testing_context()
    """
    if server_cert == SIGNED_CERTFILE:
        hostname = SIGNED_CERTFILE_HOSTNAME
    elif server_cert == SIGNED_CERTFILE2:
        hostname = SIGNED_CERTFILE2_HOSTNAME
    else:
        raise ValueError(server_cert)

    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.load_verify_locations(SIGNING_CA)

    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(server_cert)
    server_context.load_verify_locations(SIGNING_CA)

    return client_context, server_context, hostname


class BasicSocketTests(unittest.TestCase):

    def test_constants(self):
        ssl.CERT_NONE
        ssl.CERT_OPTIONAL
        ssl.CERT_REQUIRED
        ssl.OP_CIPHER_SERVER_PREFERENCE
        # ssl.OP_SINGLE_DH_USE
        if ssl.HAS_ECDH:
            ssl.OP_SINGLE_ECDH_USE
        if ssl.OPENSSL_VERSION_INFO >= (1, 0):
            ssl.OP_NO_COMPRESSION
        self.assertIn(ssl.HAS_SNI, {True, False})
        self.assertIn(ssl.HAS_ECDH, {True, False})

    def test_private_init(self):
        with self.assertRaises(TypeError):
            with socket.socket() as s:
                ssl.SSLSocket(s)

    @support.skip_micropython
    def test_str_for_enums(self):
        # Make sure that the PROTOCOL_* constants have enum-like string
        # reprs.
        proto = ssl.PROTOCOL_TLS
        self.assertEqual(str(proto), '_SSLMethod.PROTOCOL_TLS')
        ctx = ssl.SSLContext(proto)
        self.assertIs(ctx.protocol, proto)

    @unittest.skipUnless(hasattr(ssl, 'RAND_status'), "needs RAND_status")
    def test_random(self):
        v = ssl.RAND_status()
        if support.verbose:
            sys.stdout.write("\n RAND_status is %d (%s)\n"
                             % (v, (v and "sufficient randomness") or
                                "insufficient randomness"))

        data, is_cryptographic = ssl.RAND_pseudo_bytes(16)
        self.assertEqual(len(data), 16)
        self.assertEqual(is_cryptographic, v == 1)
        if v:
            data = ssl.RAND_bytes(16)
            self.assertEqual(len(data), 16)
        else:
            self.assertRaises(ssl.SSLError, ssl.RAND_bytes, 16)

        # negative num is invalid
        self.assertRaises(ValueError, ssl.RAND_bytes, -5)
        self.assertRaises(ValueError, ssl.RAND_pseudo_bytes, -5)

        if hasattr(ssl, 'RAND_egd'):
            self.assertRaises(TypeError, ssl.RAND_egd, 1)
            self.assertRaises(TypeError, ssl.RAND_egd, 'foo', 1)
        ssl.RAND_add("this is a random string", 75.0)
        ssl.RAND_add(b"this is a random bytes object", 75.0)
        ssl.RAND_add(bytearray(b"this is a random bytearray object"), 75.0)

    maxDiff = None

    @unittest.skip("signature algorithm not supported")
    def test_DER_to_PEM(self):
        with open(CAFILE_CACERT, 'r') as f:
            pem = f.read()
        d1 = ssl.PEM_cert_to_DER_cert(pem)
        p2 = ssl.DER_cert_to_PEM_cert(d1)
        d2 = ssl.PEM_cert_to_DER_cert(p2)
        self.assertEqual(d1, d2)
        if not p2.startswith(ssl.PEM_HEADER + '\n'):
            self.fail("DER-to-PEM didn't include correct header:\n%r\n" % p2)
        if not p2.endswith('\n' + ssl.PEM_FOOTER + '\n'):
            self.fail("DER-to-PEM didn't include correct footer:\n%r\n" % p2)

    def test_openssl_version(self):
        n = ssl.OPENSSL_VERSION_NUMBER
        t = ssl.OPENSSL_VERSION_INFO
        s = ssl.OPENSSL_VERSION
        self.assertIsInstance(n, int)
        self.assertIsInstance(t, tuple)
        self.assertIsInstance(s, str)
        # Some sanity checks follow
        # >= 0.9
        self.assertGreaterEqual(n, 0x900000)
        # < 4.0
        self.assertLess(n, 0x40000000)
        major, minor, fix, patch, status = t
        self.assertGreaterEqual(major, 1)
        self.assertLess(major, 4)
        self.assertGreaterEqual(minor, 0)
        self.assertLess(minor, 256)
        self.assertGreaterEqual(fix, 0)
        self.assertLess(fix, 256)
        self.assertGreaterEqual(patch, 0)
        self.assertLessEqual(patch, 63)
        self.assertGreaterEqual(status, 0)
        self.assertLessEqual(status, 15)
        # Version string as returned by {Open,Libre}SSL, the format might change
        self.assertTrue(s.startswith("Mbed TLS {:d}.{:d}.{:d}".format(major, minor, fix)),
                        (s, t, hex(n)))

    def test_wrapped_unconnected(self):
        # Methods on an unconnected SSLSocket propagate the original
        # OSError raise by the underlying socket object.
        s = socket.socket(socket.AF_INET)
        with test_wrap_socket(s) as ss:
            self.assertRaises(OSError, ss.recv, 1)
            self.assertRaises(OSError, ss.recv_into, bytearray(b'x'))
            self.assertRaises(OSError, ss.recvfrom, 1)
            self.assertRaises(OSError, ss.recvfrom_into, bytearray(b'x'), 1)
            self.assertRaises(OSError, ss.send, b'x')
            self.assertRaises(OSError, ss.sendto, b'x', ('0.0.0.0', 0))
            # self.assertRaises(NotImplementedError, ss.dup)
            # self.assertRaises(NotImplementedError, ss.sendmsg,
            #                   [b'x'], (), 0, ('0.0.0.0', 0))
            # self.assertRaises(NotImplementedError, ss.recvmsg, 100)
            # self.assertRaises(NotImplementedError, ss.recvmsg_into,
            #                   [bytearray(100)])

    def test_timeout(self):
        # Issue #8524: when creating an SSL socket, the timeout of the
        # original socket should be retained.
        for timeout in (None, 0.0, 5.0):
            s = socket.socket(socket.AF_INET)
            s.settimeout(timeout)
            with test_wrap_socket(s) as ss:
                self.assertEqual(timeout, ss.gettimeout())

    @unittest.skipUnless(hasattr(ssl, 'wrap_socket'), "needs wrap_socket")
    def test_errors_sslwrap(self):
        sock = socket.socket()
        self.assertRaisesRegex(ValueError,
                        "certfile must be specified",
                        ssl.wrap_socket, sock, keyfile=CERTFILE)
        self.assertRaisesRegex(ValueError,
                        "certfile must be specified for server-side operations",
                        ssl.wrap_socket, sock, server_side=True)
        self.assertRaisesRegex(ValueError,
                        "certfile must be specified for server-side operations",
                         ssl.wrap_socket, sock, server_side=True, certfile="")
        with ssl.wrap_socket(sock, server_side=True, certfile=CERTFILE) as s:
            self.assertRaisesRegex(ValueError, "can't connect in server-side mode",
                                     s.connect, (HOST, 8080))
        with self.assertRaises(OSError) as cm:
            with socket.socket() as sock:
                ssl.wrap_socket(sock, certfile=NONEXISTINGCERT)
        # self.assertEqual(cm.exception.errno, errno.ENOENT)
        with self.assertRaises(OSError) as cm:
            with socket.socket() as sock:
                ssl.wrap_socket(sock,
                    certfile=CERTFILE, keyfile=NONEXISTINGCERT)
        # self.assertEqual(cm.exception.errno, errno.ENOENT)
        with self.assertRaises(OSError) as cm:
            with socket.socket() as sock:
                ssl.wrap_socket(sock,
                    certfile=NONEXISTINGCERT, keyfile=NONEXISTINGCERT)
        # self.assertEqual(cm.exception.errno, errno.ENOENT)

    def bad_cert_test(self, certfile):
        """Check that trying to use the given client certificate fails"""
        certfile = os.path.join(os.path.dirname(__file__) or os.curdir,
                                   certfile)
        sock = socket.socket()
        self.addCleanup(sock.close)
        with self.assertRaises(ssl.SSLError):
            test_wrap_socket(sock,
                             certfile=certfile)

    def test_empty_cert(self):
        """Wrapping with an empty cert file"""
        self.bad_cert_test("nullcert.pem")

    def test_malformed_cert(self):
        """Wrapping with a badly formatted certificate (syntax error)"""
        self.bad_cert_test("badcert.pem")

    def test_malformed_key(self):
        """Wrapping with a badly formatted key (syntax error)"""
        self.bad_cert_test("badkey.pem")

    def test_server_side(self):
        # server_hostname doesn't work for server sockets
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        with socket.socket() as sock:
            self.assertRaises(ValueError, ctx.wrap_socket, sock, True,
                              server_hostname="some.hostname")

    def test_unknown_channel_binding(self):
        # should raise ValueError for unknown type
        s = socket.socket(socket.AF_INET)
        s.bind(('127.0.0.1', 0))
        s.listen()
        c = socket.socket(socket.AF_INET)
        c.connect(s.getsockname())
        with test_wrap_socket(c, do_handshake_on_connect=False) as ss:
            with self.assertRaises(ValueError):
                ss.get_channel_binding("unknown-type")
        s.close()

    @unittest.skipUnless("tls-unique" in ssl.CHANNEL_BINDING_TYPES,
                         "'tls-unique' channel binding not available")
    def test_tls_unique_channel_binding(self):
        # unconnected should return None for known type
        s = socket.socket(socket.AF_INET)
        with test_wrap_socket(s) as ss:
            self.assertIsNone(ss.get_channel_binding("tls-unique"))
        # the same for server-side
        s = socket.socket(socket.AF_INET)
        with test_wrap_socket(s, server_side=True, certfile=CERTFILE) as ss:
            self.assertIsNone(ss.get_channel_binding("tls-unique"))

    @support.skip_micropython
    def test_dealloc_warn(self):
        ss = test_wrap_socket(socket.socket(socket.AF_INET))
        r = repr(ss)
        with self.assertWarns(ResourceWarning) as cm:
            ss = None
            support.gc_collect()
        self.assertIn(r, str(cm.warning.args[0]))

    @unittest.skipUnless(hasattr(ssl, 'get_default_verify_paths'), "needs get_default_verify_paths")
    def test_get_default_verify_paths(self):
        paths = ssl.get_default_verify_paths()
        self.assertEqual(len(paths), 6)
        self.assertIsInstance(paths, ssl.DefaultVerifyPaths)

        with support.EnvironmentVarGuard() as env:
            env["SSL_CERT_DIR"] = CAPATH
            env["SSL_CERT_FILE"] = CERTFILE
            paths = ssl.get_default_verify_paths()
            self.assertEqual(paths.cafile, CERTFILE)
            self.assertEqual(paths.capath, CAPATH)

    def test_unsupported_dtls(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(s.close)
        with self.assertRaises(Exception) as cx:
            test_wrap_socket(s, cert_reqs=ssl.CERT_NONE)
        # self.assertEqual(str(cx.exception), "only stream sockets are supported")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with self.assertRaises(Exception) as cx:
            ctx.wrap_socket(s)
        # self.assertEqual(str(cx.exception), "only stream sockets are supported")

    def cert_time_ok(self, timestring, timestamp):
        self.assertEqual(ssl.cert_time_to_seconds(timestring), timestamp)

    def cert_time_fail(self, timestring):
        with self.assertRaises(ValueError):
            ssl.cert_time_to_seconds(timestring)

    @unittest.skipUnless(hasattr(ssl, 'cert_time_to_seconds'), "needs cert_time_to_seconds")
    @unittest.skipUnless(utc_offset(),
                         'local time needs to be different from UTC')
    def test_cert_time_to_seconds_timezone(self):
        # Issue #19940: ssl.cert_time_to_seconds() returns wrong
        #               results if local timezone is not UTC
        self.cert_time_ok("May  9 00:00:00 2007 GMT", 1178668800.0)
        self.cert_time_ok("Jan  5 09:34:43 2018 GMT", 1515144883.0)

    @unittest.skipUnless(hasattr(ssl, 'cert_time_to_seconds'), "needs cert_time_to_seconds")
    def test_cert_time_to_seconds(self):
        timestring = "Jan  5 09:34:43 2018 GMT"
        ts = 1515144883.0
        self.cert_time_ok(timestring, ts)
        # accept keyword parameter, assert its name
        self.assertEqual(ssl.cert_time_to_seconds(cert_time=timestring), ts)
        # accept both %e and %d (space or zero generated by strftime)
        self.cert_time_ok("Jan 05 09:34:43 2018 GMT", ts)
        # case-insensitive
        self.cert_time_ok("JaN  5 09:34:43 2018 GmT", ts)
        self.cert_time_fail("Jan  5 09:34 2018 GMT")     # no seconds
        self.cert_time_fail("Jan  5 09:34:43 2018")      # no GMT
        self.cert_time_fail("Jan  5 09:34:43 2018 UTC")  # not GMT timezone
        self.cert_time_fail("Jan 35 09:34:43 2018 GMT")  # invalid day
        self.cert_time_fail("Jon  5 09:34:43 2018 GMT")  # invalid month
        self.cert_time_fail("Jan  5 24:00:00 2018 GMT")  # invalid hour
        self.cert_time_fail("Jan  5 09:60:43 2018 GMT")  # invalid minute

        newyear_ts = 1230768000.0
        # leap seconds
        self.cert_time_ok("Dec 31 23:59:60 2008 GMT", newyear_ts)
        # same timestamp
        self.cert_time_ok("Jan  1 00:00:00 2009 GMT", newyear_ts)

        self.cert_time_ok("Jan  5 09:34:59 2018 GMT", 1515144899)
        #  allow 60th second (even if it is not a leap second)
        self.cert_time_ok("Jan  5 09:34:60 2018 GMT", 1515144900)
        #  allow 2nd leap second for compatibility with time.strptime()
        self.cert_time_ok("Jan  5 09:34:61 2018 GMT", 1515144901)
        self.cert_time_fail("Jan  5 09:34:62 2018 GMT")  # invalid seconds

        # no special treatment for the special value:
        #   99991231235959Z (rfc 5280)
        self.cert_time_ok("Dec 31 23:59:59 9999 GMT", 253402300799.0)

    @unittest.skipUnless(hasattr(ssl, 'cert_time_to_seconds'), "needs cert_time_to_seconds")
    def test_cert_time_to_seconds_locale(self):
        # `cert_time_to_seconds()` should be locale independent

        def local_february_name():
            return time.strftime('%b', (1, 2, 3, 4, 5, 6, 0, 0, 0))

        if local_february_name().lower() == 'feb':
            self.skipTest("locale-specific month name needs to be "
                          "different from C locale")

        # locale-independent
        self.cert_time_ok("Feb  9 00:00:00 2007 GMT", 1170979200.0)
        self.cert_time_fail(local_february_name() + "  9 00:00:00 2007 GMT")

    def test_connect_ex_error(self):
        server = socket.socket(socket.AF_INET)
        self.addCleanup(server.close)
        port = support.bind_port(server)  # Reserve port but don't listen
        s = test_wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED)
        self.addCleanup(s.close)
        rc = s.connect_ex((HOST, port))
        # Issue #19919: Windows machines or VMs hosted on Windows
        # machines sometimes return EWOULDBLOCK.
        errors = (
            errno.ECONNREFUSED, errno.EHOSTUNREACH, errno.ETIMEDOUT,
            errno.EWOULDBLOCK,
        )
        self.assertIn(rc, errors)


class ContextTests(unittest.TestCase):

    def test_constructor(self):
        for protocol in PROTOCOLS:
            with support.check_warnings():
                ctx = ssl.SSLContext(protocol)
            self.assertEqual(ctx.protocol, protocol)
        self.assertRaises(ValueError, ssl.SSLContext, -1)
        self.assertRaises(ValueError, ssl.SSLContext, 42)

    def test_protocol(self):
        for proto in PROTOCOLS:
            ctx = ssl.SSLContext(proto)
            self.assertEqual(ctx.protocol, proto)

    def test_ciphers(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_ciphers("ALL")
        with self.assertRaisesRegex(ssl.SSLError, "No cipher can be selected"):
            ctx.set_ciphers("^$:,;?*'dorothyx")

    @unittest.skipUnless(True,
                         "Test applies only to Python default ciphers")
    def test_python_ciphers(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ciphers = ctx.get_ciphers()
        for suite in ciphers:
            name = suite['name']
            self.assertNotIn("PSK", name)
            self.assertNotIn("SRP", name)
            self.assertNotIn("MD5", name)
            self.assertNotIn("RC4", name)
            self.assertNotIn("3DES", name)

    def test_get_ciphers(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_ciphers('ALL')
        names = set(d['name'] for d in ctx.get_ciphers())
        self.assertTrue(any((name.endswith('AES-256-GCM-SHA384') for name in names)))
        self.assertTrue(any((name.endswith('AES-128-GCM-SHA256') for name in names)))

    @unittest.skipUnless(hasattr(ssl.SSLContext, 'options'), "needs options")
    def test_options(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        # OP_ALL | OP_NO_SSLv2 | OP_NO_SSLv3 is the default value
        default = ssl.OP_ALL
        # SSLContext also enables these by default
        default |= (OP_NO_COMPRESSION | OP_CIPHER_SERVER_PREFERENCE |
                    OP_SINGLE_DH_USE | OP_SINGLE_ECDH_USE |
                    OP_ENABLE_MIDDLEBOX_COMPAT)
        self.assertEqual(default, ctx.options)
        if can_clear_options():
            ctx.options = 0
            # Ubuntu has OP_NO_SSLv3 forced on by default
            self.assertEqual(0, ctx.options)
        else:
            with self.assertRaises(ValueError):
                ctx.options = 0

    def test_verify_mode_protocol(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # Default value
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        self.assertFalse(ctx.check_hostname)
        ctx.verify_mode = ssl.CERT_OPTIONAL
        self.assertEqual(ctx.verify_mode, ssl.CERT_OPTIONAL)
        ctx.verify_mode = ssl.CERT_REQUIRED
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        ctx.verify_mode = ssl.CERT_NONE
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        with self.assertRaises(TypeError):
            ctx.verify_mode = None
        with self.assertRaises(ValueError):
            ctx.verify_mode = 42

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    @unittest.skipUnless(hasattr(ssl.SSLContext, 'hostname_checks_common_name'), "needs hostname_checks_common_name")
    def test_hostname_checks_common_name(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertTrue(ctx.hostname_checks_common_name)
        if ssl.HAS_NEVER_CHECK_COMMON_NAME:
            ctx.hostname_checks_common_name = True
            self.assertTrue(ctx.hostname_checks_common_name)
            ctx.hostname_checks_common_name = False
            self.assertFalse(ctx.hostname_checks_common_name)
            ctx.hostname_checks_common_name = True
            self.assertTrue(ctx.hostname_checks_common_name)
        else:
            with self.assertRaises(AttributeError):
                ctx.hostname_checks_common_name = True

    @requires_minimum_version
    def test_min_max_version(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # OpenSSL default is MINIMUM_SUPPORTED, however some vendors like
        # Fedora override the setting to TLS 1.0.
        minimum_range = {
            # stock OpenSSL
            ssl.TLSVersion.MINIMUM_SUPPORTED,
            # Fedora 29 uses TLS 1.0 by default
            ssl.TLSVersion.TLSv1,
            # RHEL 8 uses TLS 1.2 by default
            ssl.TLSVersion.TLSv1_2
        }
        maximum_range = {
            # stock OpenSSL
            ssl.TLSVersion.MAXIMUM_SUPPORTED,
            # Fedora 32 uses TLS 1.3 by default
            ssl.TLSVersion.TLSv1_3
        }

        self.assertIn(
            ctx.minimum_version, minimum_range
        )
        self.assertIn(
            ctx.maximum_version, maximum_range
        )

        ctx.minimum_version = ssl.TLSVersion.TLSv1_1
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        self.assertEqual(
            ctx.minimum_version, ssl.TLSVersion.TLSv1_1
        )
        self.assertEqual(
            ctx.maximum_version, ssl.TLSVersion.TLSv1_2
        )

        ctx.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
        ctx.maximum_version = ssl.TLSVersion.TLSv1
        self.assertEqual(
            ctx.minimum_version, ssl.TLSVersion.MINIMUM_SUPPORTED
        )
        self.assertEqual(
            ctx.maximum_version, ssl.TLSVersion.TLSv1
        )

        ctx.maximum_version = ssl.TLSVersion.MAXIMUM_SUPPORTED
        self.assertEqual(
            ctx.maximum_version, ssl.TLSVersion.MAXIMUM_SUPPORTED
        )

        ctx.maximum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
        self.assertIn(
            ctx.maximum_version,
            {ssl.TLSVersion.TLSv1, ssl.TLSVersion.TLSv1_1, ssl.TLSVersion.SSLv3}
        )

        ctx.minimum_version = ssl.TLSVersion.MAXIMUM_SUPPORTED
        self.assertIn(
            ctx.minimum_version,
            {ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3}
        )

        with self.assertRaises(ValueError):
            ctx.minimum_version = 42

    @unittest.skipUnless(have_verify_flags(),
                         "verify_flags need OpenSSL > 0.9.8")
    def test_verify_flags(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # default value
        tf = getattr(ssl, "VERIFY_X509_TRUSTED_FIRST", 0)
        self.assertEqual(ctx.verify_flags, ssl.VERIFY_DEFAULT | tf)
        ctx.verify_flags = ssl.VERIFY_CRL_CHECK_LEAF
        self.assertEqual(ctx.verify_flags, ssl.VERIFY_CRL_CHECK_LEAF)
        ctx.verify_flags = ssl.VERIFY_CRL_CHECK_CHAIN
        self.assertEqual(ctx.verify_flags, ssl.VERIFY_CRL_CHECK_CHAIN)
        ctx.verify_flags = ssl.VERIFY_DEFAULT
        self.assertEqual(ctx.verify_flags, ssl.VERIFY_DEFAULT)
        # supports any value
        ctx.verify_flags = ssl.VERIFY_CRL_CHECK_LEAF | ssl.VERIFY_X509_STRICT
        self.assertEqual(ctx.verify_flags,
                         ssl.VERIFY_CRL_CHECK_LEAF | ssl.VERIFY_X509_STRICT)
        with self.assertRaises(TypeError):
            ctx.verify_flags = None

    def test_load_cert_chain(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # Combined key and cert in a single file
        ctx.load_cert_chain(CERTFILE, keyfile=None)
        ctx.load_cert_chain(CERTFILE, keyfile=CERTFILE)
        self.assertRaises(TypeError, ctx.load_cert_chain, keyfile=CERTFILE)
        with self.assertRaises(OSError) as cm:
            ctx.load_cert_chain(NONEXISTINGCERT)
        # self.assertEqual(cm.exception.errno, errno.ENOENT)
        with self.assertRaises(ssl.SSLError):
            ctx.load_cert_chain(BADCERT)
        with self.assertRaises(ssl.SSLError):
            ctx.load_cert_chain(EMPTYCERT)
        # Separate key and cert
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(ONLYCERT, ONLYKEY)
        ctx.load_cert_chain(certfile=ONLYCERT, keyfile=ONLYKEY)
        ctx.load_cert_chain(certfile=BYTES_ONLYCERT, keyfile=BYTES_ONLYKEY)
        with self.assertRaises(ssl.SSLError):
            ctx.load_cert_chain(ONLYCERT)
        with self.assertRaises(ssl.SSLError):
            ctx.load_cert_chain(ONLYKEY)
        with self.assertRaises(ssl.SSLError):
            ctx.load_cert_chain(certfile=ONLYKEY, keyfile=ONLYCERT)
        # Mismatching key and cert
        # signature algorithm not supported
        # ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # with self.assertRaisesRegex(ssl.SSLError, "key values mismatch"):
        #     ctx.load_cert_chain(CAFILE_CACERT, ONLYKEY)
        # Password protected key and cert
        # passwords not supported
        # ctx.load_cert_chain(CERTFILE_PROTECTED, password=KEY_PASSWORD)
        # ctx.load_cert_chain(CERTFILE_PROTECTED, password=KEY_PASSWORD.encode())
        # ctx.load_cert_chain(CERTFILE_PROTECTED,
        #                     password=bytearray(KEY_PASSWORD.encode()))
        # ctx.load_cert_chain(ONLYCERT, ONLYKEY_PROTECTED, KEY_PASSWORD)
        # ctx.load_cert_chain(ONLYCERT, ONLYKEY_PROTECTED, KEY_PASSWORD.encode())
        # ctx.load_cert_chain(ONLYCERT, ONLYKEY_PROTECTED,
        #                     bytearray(KEY_PASSWORD.encode()))
        # with self.assertRaisesRegex(TypeError, "should be a string"):
        #     ctx.load_cert_chain(CERTFILE_PROTECTED, password=True)
        # with self.assertRaises(ssl.SSLError):
        #     ctx.load_cert_chain(CERTFILE_PROTECTED, password="badpass")
        # with self.assertRaisesRegex(ValueError, "cannot be longer"):
        #     # openssl has a fixed limit on the password buffer.
        #     # PEM_BUFSIZE is generally set to 1kb.
        #     # Return a string larger than this.
        #     ctx.load_cert_chain(CERTFILE_PROTECTED, password=b'a' * 102400)
        # # Password callback
        # def getpass_unicode():
        #     return KEY_PASSWORD
        # def getpass_bytes():
        #     return KEY_PASSWORD.encode()
        # def getpass_bytearray():
        #     return bytearray(KEY_PASSWORD.encode())
        # def getpass_badpass():
        #     return "badpass"
        # def getpass_huge():
        #     return b'a' * (1024 * 1024)
        # def getpass_bad_type():
        #     return 9
        # def getpass_exception():
        #     raise Exception('getpass error')
        # class GetPassCallable:
        #     def __call__(self):
        #         return KEY_PASSWORD
        #     def getpass(self):
        #         return KEY_PASSWORD
        # ctx.load_cert_chain(CERTFILE_PROTECTED, password=getpass_unicode)
        # ctx.load_cert_chain(CERTFILE_PROTECTED, password=getpass_bytes)
        # ctx.load_cert_chain(CERTFILE_PROTECTED, password=getpass_bytearray)
        # ctx.load_cert_chain(CERTFILE_PROTECTED, password=GetPassCallable())
        # ctx.load_cert_chain(CERTFILE_PROTECTED,
        #                     password=GetPassCallable().getpass)
        # with self.assertRaises(ssl.SSLError):
        #     ctx.load_cert_chain(CERTFILE_PROTECTED, password=getpass_badpass)
        # with self.assertRaisesRegex(ValueError, "cannot be longer"):
        #     ctx.load_cert_chain(CERTFILE_PROTECTED, password=getpass_huge)
        # with self.assertRaisesRegex(TypeError, "must return a string"):
        #     ctx.load_cert_chain(CERTFILE_PROTECTED, password=getpass_bad_type)
        # with self.assertRaisesRegex(Exception, "getpass error"):
        #     ctx.load_cert_chain(CERTFILE_PROTECTED, password=getpass_exception)
        # # Make sure the password function isn't called if it isn't needed
        # ctx.load_cert_chain(CERTFILE, password=getpass_exception)

    def test_load_verify_locations(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_verify_locations(CERTFILE)
        ctx.load_verify_locations(cafile=CERTFILE, capath=None)
        ctx.load_verify_locations(BYTES_CERTFILE)
        ctx.load_verify_locations(cafile=BYTES_CERTFILE, capath=None)
        self.assertRaises(TypeError, ctx.load_verify_locations)
        self.assertRaises(TypeError, ctx.load_verify_locations, None, None, None)
        with self.assertRaises(OSError) as cm:
            ctx.load_verify_locations(NONEXISTINGCERT)
        # self.assertEqual(cm.exception.errno, errno.ENOENT)
        with self.assertRaises(ssl.SSLError):
            ctx.load_verify_locations(BADCERT)
        ctx.load_verify_locations(CERTFILE, CAPATH)
        ctx.load_verify_locations(CERTFILE, capath=BYTES_CAPATH)

        # Issue #10989: crash if the second argument type is invalid
        self.assertRaises(TypeError, ctx.load_verify_locations, None, True)

    @unittest.skip("signature algorithm not supported")
    def test_load_verify_cadata(self):
        # test cadata
        with open(CAFILE_CACERT) as f:
            cacert_pem = f.read()
        cacert_der = ssl.PEM_cert_to_DER_cert(cacert_pem)
        with open(CAFILE_NEURONIO) as f:
            neuronio_pem = f.read()
        neuronio_der = ssl.PEM_cert_to_DER_cert(neuronio_pem)

        # test PEM
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 0)
        ctx.load_verify_locations(cadata=cacert_pem)
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 1)
        ctx.load_verify_locations(cadata=neuronio_pem)
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 2)
        # cert already in hash table
        ctx.load_verify_locations(cadata=neuronio_pem)
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 2)

        # combined
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        combined = "\n".join((cacert_pem, neuronio_pem))
        ctx.load_verify_locations(cadata=combined)
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 2)

        # with junk around the certs
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        combined = ["head", cacert_pem, "other", neuronio_pem, "again",
                    neuronio_pem, "tail"]
        ctx.load_verify_locations(cadata="\n".join(combined))
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 2)

        # test DER
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(cadata=cacert_der)
        ctx.load_verify_locations(cadata=neuronio_der)
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 2)
        # cert already in hash table
        ctx.load_verify_locations(cadata=cacert_der)
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 2)

        # combined
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        combined = b"".join((cacert_der, neuronio_der))
        ctx.load_verify_locations(cadata=combined)
        self.assertEqual(ctx.cert_store_stats()["x509_ca"], 2)

        # error cases
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertRaises(TypeError, ctx.load_verify_locations, cadata=object)

        with self.assertRaisesRegex(ssl.SSLError, "no start line"):
            ctx.load_verify_locations(cadata="broken")
        with self.assertRaisesRegex(ssl.SSLError, "not enough data"):
            ctx.load_verify_locations(cadata=b"broken")


    @unittest.skipUnless(hasattr(ssl.SSLContext, 'load_dh_params'), "needs load_dh_params")
    def test_load_dh_params(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_dh_params(DHFILE)
        ctx.load_dh_params(BYTES_DHFILE)
        self.assertRaises(TypeError, ctx.load_dh_params)
        self.assertRaises(TypeError, ctx.load_dh_params, None)
        with self.assertRaises(FileNotFoundError) as cm:
            ctx.load_dh_params(NONEXISTINGCERT)
        self.assertEqual(cm.exception.errno, errno.ENOENT)
        with self.assertRaises(ssl.SSLError) as cm:
            ctx.load_dh_params(CERTFILE)

    @unittest.skipUnless(hasattr(ssl.SSLContext, 'session_stats'), "needs session_stats")
    def test_session_stats(self):
        for proto in PROTOCOLS:
            ctx = ssl.SSLContext(proto)
            self.assertEqual(ctx.session_stats(), {
                'number': 0,
                'connect': 0,
                'connect_good': 0,
                'connect_renegotiate': 0,
                'accept': 0,
                'accept_good': 0,
                'accept_renegotiate': 0,
                'hits': 0,
                'misses': 0,
                'timeouts': 0,
                'cache_full': 0,
            })

    def test_set_default_verify_paths(self):
        # There's not much we can do to test that it acts as expected,
        # so just check it doesn't crash or raise an exception.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.set_default_verify_paths()

    @unittest.skipUnless(ssl.HAS_ECDH, "ECDH disabled on this OpenSSL build")
    def test_set_ecdh_curve(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.set_ecdh_curve("secp256r1")
        ctx.set_ecdh_curve(b"secp256r1")
        self.assertRaises(TypeError, ctx.set_ecdh_curve)
        self.assertRaises(TypeError, ctx.set_ecdh_curve, None)
        self.assertRaises(ValueError, ctx.set_ecdh_curve, "foo")
        self.assertRaises(ValueError, ctx.set_ecdh_curve, b"foo")

    @needs_sni
    def test_sni_callback(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)

        # set_servername_callback expects a callable, or None
        self.assertRaises(TypeError, ctx.set_servername_callback)
        self.assertRaises(TypeError, ctx.set_servername_callback, 4)
        self.assertRaises(TypeError, ctx.set_servername_callback, "")
        self.assertRaises(TypeError, ctx.set_servername_callback, ctx)

        def dummycallback(sock, servername, ctx):
            pass
        ctx.set_servername_callback(None)
        ctx.set_servername_callback(dummycallback)

    @needs_sni
    def test_sni_callback_refcycle(self):
        # Reference cycles through the servername callback are detected
        # and cleared.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        def dummycallback(sock, servername, ctx, cycle=ctx):
            pass
        ctx.set_servername_callback(dummycallback)
        wr = weakref.ref(ctx)
        del ctx, dummycallback
        gc.collect()
        self.assertIs(wr(), None)

    def test_cert_store_stats(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(ctx.cert_store_stats(),
            {'x509_ca': 0, 'crl': 0, 'x509': 0})
        ctx.load_cert_chain(CERTFILE)
        self.assertEqual(ctx.cert_store_stats(),
            {'x509_ca': 0, 'crl': 0, 'x509': 0})
        ctx.load_verify_locations(CERTFILE)
        self.assertEqual(ctx.cert_store_stats(),
            {'x509_ca': 0, 'crl': 0, 'x509': 1})
        # signature algorithm not supported
        # ctx.load_verify_locations(CAFILE_CACERT)
        # self.assertEqual(ctx.cert_store_stats(),
        #     {'x509_ca': 1, 'crl': 0, 'x509': 2})

    @unittest.skip("signature algorithm not supported")
    def test_get_ca_certs(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(ctx.get_ca_certs(), [])
        # CERTFILE is not flagged as X509v3 Basic Constraints: CA:TRUE
        ctx.load_verify_locations(CERTFILE)
        self.assertEqual(ctx.get_ca_certs(), [])
        # but CAFILE_CACERT is a CA cert
        ctx.load_verify_locations(CAFILE_CACERT)
        self.assertEqual(ctx.get_ca_certs(),
            [{'issuer': ((('organizationName', 'Root CA'),),
                         (('organizationalUnitName', 'http://www.cacert.org'),),
                         (('commonName', 'CA Cert Signing Authority'),),
                         (('emailAddress', 'support@cacert.org'),)),
              'notAfter': asn1time('Mar 29 12:29:49 2033 GMT'),
              'notBefore': asn1time('Mar 30 12:29:49 2003 GMT'),
              'serialNumber': '00',
              'crlDistributionPoints': ('https://www.cacert.org/revoke.crl',),
              'subject': ((('organizationName', 'Root CA'),),
                          (('organizationalUnitName', 'http://www.cacert.org'),),
                          (('commonName', 'CA Cert Signing Authority'),),
                          (('emailAddress', 'support@cacert.org'),)),
              'version': 3}])

        with open(CAFILE_CACERT) as f:
            pem = f.read()
        der = ssl.PEM_cert_to_DER_cert(pem)
        self.assertEqual(ctx.get_ca_certs(True), [der])

    def test_load_default_certs(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_default_certs()

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_default_certs(ssl.Purpose.SERVER_AUTH)
        ctx.load_default_certs()

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_default_certs(ssl.Purpose.CLIENT_AUTH)

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertRaises(TypeError, ctx.load_default_certs, None)
        self.assertRaises(TypeError, ctx.load_default_certs, 'SERVER_AUTH')

    @support.skip_micropython
    def test_load_default_certs_env(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with support.EnvironmentVarGuard() as env:
            env["SSL_CERT_DIR"] = CAPATH
            env["SSL_CERT_FILE"] = CERTFILE
            ctx.load_default_certs()
            self.assertEqual(ctx.cert_store_stats(), {"crl": 0, "x509": 1, "x509_ca": 0})

    def _assert_context_options(self, ctx):
        if OP_NO_COMPRESSION != 0:
            self.assertEqual(ctx.options & OP_NO_COMPRESSION,
                             OP_NO_COMPRESSION)
        if OP_SINGLE_DH_USE != 0:
            self.assertEqual(ctx.options & OP_SINGLE_DH_USE,
                             OP_SINGLE_DH_USE)
        if OP_SINGLE_ECDH_USE != 0:
            self.assertEqual(ctx.options & OP_SINGLE_ECDH_USE,
                             OP_SINGLE_ECDH_USE)
        if OP_CIPHER_SERVER_PREFERENCE != 0:
            self.assertEqual(ctx.options & OP_CIPHER_SERVER_PREFERENCE,
                             OP_CIPHER_SERVER_PREFERENCE)

    def test_create_default_context(self):
        ctx = ssl.create_default_context()

        self.assertEqual(ctx.protocol, ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)
        self._assert_context_options(ctx)

        with open(SIGNING_CA) as f:
            cadata = f.read()
        ctx = ssl.create_default_context(cafile=SIGNING_CA, capath=CAPATH,
                                         cadata=cadata)
        self.assertEqual(ctx.protocol, ssl.PROTOCOL_TLS_CLIENT)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self._assert_context_options(ctx)

        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        self.assertEqual(ctx.protocol, ssl.PROTOCOL_TLS_SERVER)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        self._assert_context_options(ctx)

    def test_check_hostname(self):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)

        # Auto set CERT_REQUIRED
        ctx.check_hostname = True
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

        # Changing verify_mode does not affect check_hostname
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.check_hostname = False
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        # Auto set
        ctx.check_hostname = True
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_OPTIONAL
        ctx.check_hostname = False
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_OPTIONAL)
        # keep CERT_OPTIONAL
        ctx.check_hostname = True
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_OPTIONAL)

        # Cannot set CERT_NONE with check_hostname enabled
        with self.assertRaises(ValueError):
            ctx.verify_mode = ssl.CERT_NONE
        ctx.check_hostname = False
        self.assertFalse(ctx.check_hostname)
        ctx.verify_mode = ssl.CERT_NONE
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)

    def test_context_client_server(self):
        # PROTOCOL_TLS_CLIENT has sane defaults
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

        # PROTOCOL_TLS_SERVER has different but also sane defaults
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)

    @unittest.skipUnless(hasattr(ssl, 'wrap_bio'), "requires wrap_bio")
    def test_context_custom_class(self):
        class MySSLSocket(ssl.SSLSocket):
            pass

        class MySSLObject(ssl.SSLObject):
            pass

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.sslsocket_class = MySSLSocket
        ctx.sslobject_class = MySSLObject

        with ctx.wrap_socket(socket.socket(), server_side=True) as sock:
            self.assertIsInstance(sock, MySSLSocket)
        obj = ctx.wrap_bio(ssl.MemoryBIO(), ssl.MemoryBIO())
        self.assertIsInstance(obj, MySSLObject)


class SSLErrorTests(unittest.TestCase):

    @support.skip_micropython
    def test_str(self):
        # The str() of a SSLError doesn't include the errno
        e = ssl.SSLError(1, "foo")
        self.assertEqual(str(e), "foo")
        self.assertEqual(e.errno, 1)
        # Same for a subclass
        e = ssl.SSLZeroReturnError(1, "foo")
        self.assertEqual(str(e), "foo")
        self.assertEqual(e.errno, 1)

    @unittest.skipUnless(hasattr(ssl.SSLContext, 'load_dh_params'), "needs load_dh_params")
    def test_lib_reason(self):
        # Test the library and reason attributes
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with self.assertRaises(ssl.SSLError) as cm:
            ctx.load_dh_params(CERTFILE)
        # self.assertEqual(cm.exception.library, 'PEM')
        # self.assertEqual(cm.exception.reason, 'NO_START_LINE')
        s = str(cm.exception)
        self.assertTrue(s.startswith("[PEM: NO_START_LINE] no start line"), s)

    def test_subclass(self):
        # Check that the appropriate SSLError subclass is raised
        # (this only tests one of them)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            c = socket.socket()
            c.connect(s.getsockname())
            c.setblocking(False)
            with ctx.wrap_socket(c, False, do_handshake_on_connect=False) as c:
                with self.assertRaises(OSError) as cm:
                    c.do_handshake()
                s = str(cm.exception)
                # self.assertTrue(s.startswith("The operation did not complete (read)"), s)


    @unittest.skipUnless(hasattr(ssl, 'wrap_bio'), "requires wrap_bio")
    def test_bad_server_hostname(self):
        ctx = ssl.create_default_context()
        with self.assertRaises(ValueError):
            ctx.wrap_bio(ssl.MemoryBIO(), ssl.MemoryBIO(),
                         server_hostname="")
        with self.assertRaises(ValueError):
            ctx.wrap_bio(ssl.MemoryBIO(), ssl.MemoryBIO(),
                         server_hostname=".example.org")
        with self.assertRaises(TypeError):
            ctx.wrap_bio(ssl.MemoryBIO(), ssl.MemoryBIO(),
                         server_hostname="example.org\x00evil.com")


@unittest.skipUnless(hasattr(ssl, 'wrap_bio'), "requires wrap_bio")
class MemoryBIOTests(unittest.TestCase):

    def test_read_write(self):
        bio = ssl.MemoryBIO()
        bio.write(b'foo')
        self.assertEqual(bio.read(), b'foo')
        self.assertEqual(bio.read(), b'')
        bio.write(b'foo')
        bio.write(b'bar')
        self.assertEqual(bio.read(), b'foobar')
        self.assertEqual(bio.read(), b'')
        bio.write(b'baz')
        self.assertEqual(bio.read(2), b'ba')
        self.assertEqual(bio.read(1), b'z')
        self.assertEqual(bio.read(1), b'')

    def test_eof(self):
        bio = ssl.MemoryBIO()
        self.assertFalse(bio.eof)
        self.assertEqual(bio.read(), b'')
        self.assertFalse(bio.eof)
        bio.write(b'foo')
        self.assertFalse(bio.eof)
        bio.write_eof()
        self.assertFalse(bio.eof)
        self.assertEqual(bio.read(2), b'fo')
        self.assertFalse(bio.eof)
        self.assertEqual(bio.read(1), b'o')
        self.assertTrue(bio.eof)
        self.assertEqual(bio.read(), b'')
        self.assertTrue(bio.eof)

    def test_pending(self):
        bio = ssl.MemoryBIO()
        self.assertEqual(bio.pending, 0)
        bio.write(b'foo')
        self.assertEqual(bio.pending, 3)
        for i in range(3):
            bio.read(1)
            self.assertEqual(bio.pending, 3-i-1)
        for i in range(3):
            bio.write(b'x')
            self.assertEqual(bio.pending, i+1)
        bio.read()
        self.assertEqual(bio.pending, 0)

    def test_buffer_types(self):
        bio = ssl.MemoryBIO()
        bio.write(b'foo')
        self.assertEqual(bio.read(), b'foo')
        bio.write(bytearray(b'bar'))
        self.assertEqual(bio.read(), b'bar')
        bio.write(memoryview(b'baz'))
        self.assertEqual(bio.read(), b'baz')

    def test_error_types(self):
        bio = ssl.MemoryBIO()
        self.assertRaises(TypeError, bio.write, 'foo')
        self.assertRaises(TypeError, bio.write, None)
        self.assertRaises(TypeError, bio.write, True)
        self.assertRaises(TypeError, bio.write, 1)


@unittest.skipUnless(hasattr(ssl, 'wrap_bio'), "requires wrap_bio")
class SSLObjectTests(unittest.TestCase):
    def test_private_init(self):
        bio = ssl.MemoryBIO()
        with self.assertRaisesRegex(TypeError, "public constructor"):
            ssl.SSLObject(bio, bio)

    def test_unwrap(self):
        client_ctx, server_ctx, hostname = testing_context()
        c_in = ssl.MemoryBIO()
        c_out = ssl.MemoryBIO()
        s_in = ssl.MemoryBIO()
        s_out = ssl.MemoryBIO()
        client = client_ctx.wrap_bio(c_in, c_out, server_hostname=hostname)
        server = server_ctx.wrap_bio(s_in, s_out, server_side=True)

        # Loop on the handshake for a bit to get it settled
        for _ in range(5):
            try:
                client.do_handshake()
            except ssl.SSLWantReadError:
                pass
            if c_out.pending:
                s_in.write(c_out.read())
            try:
                server.do_handshake()
            except ssl.SSLWantReadError:
                pass
            if s_out.pending:
                c_in.write(s_out.read())
        # Now the handshakes should be complete (don't raise WantReadError)
        client.do_handshake()
        server.do_handshake()

        # Now if we unwrap one side unilaterally, it should send close-notify
        # and raise WantReadError:
        with self.assertRaises(ssl.SSLWantReadError):
            client.unwrap()

        # But server.unwrap() does not raise, because it reads the client's
        # close-notify:
        s_in.write(c_out.read())
        server.unwrap()

        # And now that the client gets the server's close-notify, it doesn't
        # raise either.
        c_in.write(s_out.read())
        client.unwrap()

class SimpleBackgroundTests(unittest.TestCase):
    """Tests that connect to a simple server running in the background"""

    def setUp(self):
        server = ThreadedEchoServer(SIGNED_CERTFILE)
        self.server_addr = (HOST, server.port)
        server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)

    def test_connect(self):
        with test_wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_NONE) as s:
            s.connect(self.server_addr)
            # self.assertEqual({}, s.getpeercert())
            self.assertFalse(s.server_side)

        # this should succeed because we specify the root cert
        with test_wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED,
                            ca_certs=SIGNING_CA) as s:
            s.connect(self.server_addr)
            self.assertTrue(s.getpeercert())
            self.assertFalse(s.server_side)

    def test_connect_fail(self):
        # This should fail because we have no verification certs. Connection
        # failure crashes ThreadedEchoServer, so run this in an independent
        # test method.
        s = test_wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED)
        self.addCleanup(s.close)
        self.assertRaises(ssl.SSLError, s.connect, self.server_addr)

    def test_connect_ex(self):
        # Issue #11326: check connect_ex() implementation
        s = test_wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED,
                            ca_certs=SIGNING_CA)
        self.addCleanup(s.close)
        self.assertEqual(0, s.connect_ex(self.server_addr))
        self.assertTrue(s.getpeercert())

    def test_non_blocking_connect_ex(self):
        # Issue #11326: non-blocking connect_ex() should allow handshake
        # to proceed after the socket gets ready.
        s = test_wrap_socket(socket.socket(socket.AF_INET),
                            cert_reqs=ssl.CERT_REQUIRED,
                            ca_certs=SIGNING_CA,
                            do_handshake_on_connect=False)
        self.addCleanup(s.close)
        s.setblocking(False)
        rc = s.connect_ex(self.server_addr)
        # EWOULDBLOCK under Windows, EINPROGRESS elsewhere
        self.assertIn(rc, (0, errno.EINPROGRESS, errno.EWOULDBLOCK))
        # Wait for connect to finish
        select.select([], [s], [], 5.0)
        # Non-blocking handshake
        while True:
            try:
                s.do_handshake()
                break
            except ssl.SSLWantReadError:
                select.select([s], [], [], 5.0)
            except ssl.SSLWantWriteError:
                select.select([], [s], [], 5.0)
        # SSL established
        self.assertTrue(s.getpeercert())

    def test_connect_with_context(self):
        # Same as test_connect, but with a separately created context
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with ctx.wrap_socket(socket.socket(socket.AF_INET)) as s:
            s.connect(self.server_addr)
            # self.assertEqual({}, s.getpeercert())
        # Same with a server hostname
        with ctx.wrap_socket(socket.socket(socket.AF_INET),
                            server_hostname="dummy") as s:
            s.connect(self.server_addr)
        ctx.verify_mode = ssl.CERT_REQUIRED
        # This should succeed because we specify the root cert
        ctx.load_verify_locations(SIGNING_CA)
        with ctx.wrap_socket(socket.socket(socket.AF_INET)) as s:
            s.connect(self.server_addr)
            cert = s.getpeercert()
            self.assertTrue(cert)

    def test_connect_with_context_fail(self):
        # This should fail because we have no verification certs. Connection
        # failure crashes ThreadedEchoServer, so run this in an independent
        # test method.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        s = ctx.wrap_socket(
            socket.socket(socket.AF_INET),
            server_hostname=SIGNED_CERTFILE_HOSTNAME
        )
        self.addCleanup(s.close)
        self.assertRaises(ssl.SSLError, s.connect, self.server_addr)

    def test_connect_capath(self):
        # Verify server certificates using the `capath` argument
        # NOTE: the subject hashing algorithm has been changed between
        # OpenSSL 0.9.8n and 1.0.0, as a result the capath directory must
        # contain both versions of each certificate (same content, different
        # filename) for this test to be portable across OpenSSL releases.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(capath=CAPATH)
        with ctx.wrap_socket(socket.socket(socket.AF_INET),
                             server_hostname=SIGNED_CERTFILE_HOSTNAME) as s:
            s.connect(self.server_addr)
            cert = s.getpeercert()
            self.assertTrue(cert)

        # Same with a bytes `capath` argument
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(capath=BYTES_CAPATH)
        with ctx.wrap_socket(socket.socket(socket.AF_INET),
                             server_hostname=SIGNED_CERTFILE_HOSTNAME) as s:
            s.connect(self.server_addr)
            cert = s.getpeercert()
            self.assertTrue(cert)

    @unittest.skipUnless(hasattr(ssl, 'PEM_cert_to_DER_cert'), "needs PEM_cert_to_DER_cert")
    def test_connect_cadata(self):
        with open(SIGNING_CA) as f:
            pem = f.read()
        der = ssl.PEM_cert_to_DER_cert(pem)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(cadata=pem)
        with ctx.wrap_socket(socket.socket(socket.AF_INET),
                             server_hostname=SIGNED_CERTFILE_HOSTNAME) as s:
            s.connect(self.server_addr)
            cert = s.getpeercert()
            self.assertTrue(cert)

        # same with DER
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(cadata=der)
        with ctx.wrap_socket(socket.socket(socket.AF_INET),
                             server_hostname=SIGNED_CERTFILE_HOSTNAME) as s:
            s.connect(self.server_addr)
            cert = s.getpeercert()
            self.assertTrue(cert)

    def test_makefile_close(self):
        # Issue #5238: creating a file-like object with makefile() shouldn't
        # delay closing the underlying "real socket" (here tested with its
        # file descriptor, hence skipping the test under Windows).
        ss = test_wrap_socket(socket.socket(socket.AF_INET))
        ss.connect(self.server_addr)
        fd = ss.fileno()
        f = ss.makefile()
        f.close()
        # The fd is still open
        os.read(fd, 0)
        # Closing the SSL socket should close the fd too
        ss.close()
        gc.collect()
        with self.assertRaises(OSError) as e:
            os.read(fd, 0)
        self.assertEqual(e.exception.errno, errno.EBADF)

    def test_non_blocking_handshake(self):
        s = socket.socket(socket.AF_INET)
        s.connect(self.server_addr)
        s.setblocking(False)
        s = test_wrap_socket(s,
                            cert_reqs=ssl.CERT_NONE,
                            do_handshake_on_connect=False)
        self.addCleanup(s.close)
        count = 0
        while True:
            try:
                count += 1
                s.do_handshake()
                break
            except ssl.SSLWantReadError:
                select.select([s], [], [])
            except ssl.SSLWantWriteError:
                select.select([], [s], [])
        if support.verbose:
            sys.stdout.write("\nNeeded %d calls to do_handshake() to establish session.\n" % count)

    def test_get_server_certificate(self):
        _test_get_server_certificate(self, *self.server_addr, cert=SIGNING_CA)

    def test_get_server_certificate_fail(self):
        # Connection failure crashes ThreadedEchoServer, so run this in an
        # independent test method
        _test_get_server_certificate_fail(self, *self.server_addr)

    def test_ciphers(self):
        with test_wrap_socket(socket.socket(socket.AF_INET),
                             cert_reqs=ssl.CERT_NONE, ciphers="ALL") as s:
            s.connect(self.server_addr)
        # Error checking can happen at instantiation or when connecting
        with self.assertRaisesRegex(ssl.SSLError, "No cipher can be selected"):
            with socket.socket(socket.AF_INET) as sock:
                s = test_wrap_socket(sock,
                                    cert_reqs=ssl.CERT_NONE, ciphers="^$:,;?*'dorothyx")
                s.connect(self.server_addr)

    def test_get_ca_certs_capath(self):
        # capath certs are loaded on request
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(capath=CAPATH)
        self.assertEqual(ctx.get_ca_certs(), [])
        with ctx.wrap_socket(socket.socket(socket.AF_INET),
                             server_hostname='localhost') as s:
            s.connect(self.server_addr)
            cert = s.getpeercert()
            self.assertTrue(cert)
        self.assertEqual(len(ctx.get_ca_certs()), 1)

    @needs_sni
    def test_context_setget(self):
        # Check that the context of a connected socket can be replaced.
        ctx1 = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx1.load_verify_locations(capath=CAPATH)
        ctx2 = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx2.load_verify_locations(capath=CAPATH)
        s = socket.socket(socket.AF_INET)
        with ctx1.wrap_socket(s, server_hostname='localhost') as ss:
            ss.connect(self.server_addr)
            self.assertIs(ss.context, ctx1)
            self.assertIs(ss._sslobj.context, ctx1)
            ss.context = ctx2
            self.assertIs(ss.context, ctx2)
            self.assertIs(ss._sslobj.context, ctx2)

    def ssl_io_loop(self, sock, incoming, outgoing, func, *args, **kwargs):
        # A simple IO loop. Call func(*args) depending on the error we get
        # (WANT_READ or WANT_WRITE) move data between the socket and the BIOs.
        timeout = kwargs.get('timeout', 10)
        deadline = time.monotonic() + timeout
        count = 0
        while True:
            if time.monotonic() > deadline:
                self.fail("timeout")
            errno = None
            count += 1
            try:
                ret = func(*args)
            except ssl.SSLError as e:
                if e.errno not in (ssl.SSL_ERROR_WANT_READ,
                                   ssl.SSL_ERROR_WANT_WRITE):
                    raise
                errno = e.errno
            # Get any data from the outgoing BIO irrespective of any error, and
            # send it to the socket.
            buf = outgoing.read()
            sock.sendall(buf)
            # If there's no error, we're done. For WANT_READ, we need to get
            # data from the socket and put it in the incoming BIO.
            if errno is None:
                break
            elif errno == ssl.SSL_ERROR_WANT_READ:
                buf = sock.recv(32768)
                if buf:
                    incoming.write(buf)
                else:
                    incoming.write_eof()
        if support.verbose:
            sys.stdout.write("Needed %d calls to complete %s().\n"
                             % (count, func.__name__))
        return ret

    @unittest.skipUnless(hasattr(ssl, 'wrap_bio'), "requires wrap_bio")
    def test_bio_handshake(self):
        sock = socket.socket(socket.AF_INET)
        self.addCleanup(sock.close)
        sock.connect(self.server_addr)
        incoming = ssl.MemoryBIO()
        outgoing = ssl.MemoryBIO()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        ctx.load_verify_locations(SIGNING_CA)
        sslobj = ctx.wrap_bio(incoming, outgoing, False,
                              SIGNED_CERTFILE_HOSTNAME)
        self.assertIs(sslobj._sslobj.owner, sslobj)
        self.assertIsNone(sslobj.cipher())
        self.assertIsNone(sslobj.version())
        self.assertIsNotNone(sslobj.shared_ciphers())
        self.assertRaises(ValueError, sslobj.getpeercert)
        if 'tls-unique' in ssl.CHANNEL_BINDING_TYPES:
            self.assertIsNone(sslobj.get_channel_binding('tls-unique'))
        self.ssl_io_loop(sock, incoming, outgoing, sslobj.do_handshake)
        self.assertTrue(sslobj.cipher())
        self.assertIsNotNone(sslobj.shared_ciphers())
        self.assertIsNotNone(sslobj.version())
        self.assertTrue(sslobj.getpeercert())
        if 'tls-unique' in ssl.CHANNEL_BINDING_TYPES:
            self.assertTrue(sslobj.get_channel_binding('tls-unique'))
        try:
            self.ssl_io_loop(sock, incoming, outgoing, sslobj.unwrap)
        except ssl.SSLSyscallError:
            # If the server shuts down the TCP connection without sending a
            # secure shutdown message, this is reported as SSL_ERROR_SYSCALL
            pass
        self.assertRaises(ssl.SSLError, sslobj.write, b'foo')

    @unittest.skipUnless(hasattr(ssl, 'wrap_bio'), "requires wrap_bio")
    def test_bio_read_write_data(self):
        sock = socket.socket(socket.AF_INET)
        self.addCleanup(sock.close)
        sock.connect(self.server_addr)
        incoming = ssl.MemoryBIO()
        outgoing = ssl.MemoryBIO()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.verify_mode = ssl.CERT_NONE
        sslobj = ctx.wrap_bio(incoming, outgoing, False)
        self.ssl_io_loop(sock, incoming, outgoing, sslobj.do_handshake)
        req = b'FOO\n'
        self.ssl_io_loop(sock, incoming, outgoing, sslobj.write, req)
        buf = self.ssl_io_loop(sock, incoming, outgoing, sslobj.read, 256)
        self.assertEqual(buf, b'foo\n')
        self.ssl_io_loop(sock, incoming, outgoing, sslobj.unwrap)


@support.requires_resource('network')
class NetworkedTests(unittest.TestCase):

    def test_timeout_connect_ex(self):
        # Issue #12065: on a timeout, connect_ex() should return the original
        # errno (mimicking the behaviour of non-SSL sockets).
        with support.transient_internet(REMOTE_HOST):
            s = test_wrap_socket(socket.socket(socket.AF_INET),
                                cert_reqs=ssl.CERT_REQUIRED,
                                do_handshake_on_connect=False)
            self.addCleanup(s.close)
            s.settimeout(0.0000001)
            rc = s.connect_ex((REMOTE_HOST, 443))
            if rc == 0:
                self.skipTest("REMOTE_HOST responded too quickly")
            self.assertIn(rc, (errno.EAGAIN, errno.EWOULDBLOCK))

    @unittest.skipUnless(support.IPV6_ENABLED, 'Needs IPv6')
    def test_get_server_certificate_ipv6(self):
        with support.transient_internet('ipv6.google.com'):
            _test_get_server_certificate(self, 'ipv6.google.com', 443)
            _test_get_server_certificate_fail(self, 'ipv6.google.com', 443)


@unittest.skipUnless(hasattr(ssl, 'get_server_certificate'), " needs get_server_certificate")
def _test_get_server_certificate(test, host, port, cert=None):
    pem = ssl.get_server_certificate((host, port))
    if not pem:
        test.fail("No server certificate on %s:%s!" % (host, port))

    pem = ssl.get_server_certificate((host, port), ca_certs=cert)
    if not pem:
        test.fail("No server certificate on %s:%s!" % (host, port))
    if support.verbose:
        sys.stdout.write("\nVerified certificate for %s:%s is\n%s\n" % (host, port ,pem))

@unittest.skipUnless(hasattr(ssl, 'get_server_certificate'), " needs get_server_certificate")
def _test_get_server_certificate_fail(test, host, port):
    try:
        pem = ssl.get_server_certificate((host, port), ca_certs=CERTFILE)
    except ssl.SSLError as x:
        #should fail
        if support.verbose:
            sys.stdout.write("%s\n" % x)
    else:
        test.fail("Got server certificate %s for %s:%s!" % (pem, host, port))


from test.ssl_servers import make_https_server

class ThreadedEchoServer(threading.Thread):

    class ConnectionHandler(threading.Thread):

        """A mildly complicated class, because we want it to work both
        with and without the SSL wrapper around the socket connection, so
        that we can test the STARTTLS functionality."""

        def __init__(self, server, connsock, addr):
            self.server = server
            self.running = False
            self.sock = connsock
            self.addr = addr
            self.sock.setblocking(1)
            self.sslconn = None
            threading.Thread.__init__(self)
            self.daemon = True

        def wrap_conn(self):
            try:
                self.sslconn = self.server.context.wrap_socket(
                    self.sock, server_side=True)
                self.server.selected_alpn_protocols.append(self.sslconn.selected_alpn_protocol())
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError) as e:
                # We treat ConnectionResetError as though it were an
                # SSLError - OpenSSL on Ubuntu abruptly closes the
                # connection when asked to use an unsupported protocol.
                #
                # BrokenPipeError is raised in TLS 1.3 mode, when OpenSSL
                # tries to send session tickets after handshake.
                # https://github.com/openssl/openssl/issues/6342
                #
                # ConnectionAbortedError is raised in TLS 1.3 mode, when OpenSSL
                # tries to send session tickets after handshake when using WinSock.
                self.server.conn_errors.append(str(e))
                if self.server.chatty:
                    handle_error("\n server:  bad connection attempt from " + repr(self.addr) + ":\n")
                self.running = False
                self.close()
                return False
            except (ssl.SSLError, OSError) as e:
                # OSError may occur with wrong protocols, e.g. both
                # sides use PROTOCOL_TLS_SERVER.
                #
                # XXX Various errors can have happened here, for example
                # a mismatching protocol version, an invalid certificate,
                # or a low-level bug. This should be made more discriminating.
                #
                # bpo-31323: Store the exception as string to prevent
                # a reference leak: server -> conn_errors -> exception
                # -> traceback -> self (ConnectionHandler) -> server
                self.server.conn_errors.append(str(e))
                if self.server.chatty:
                    handle_error("\n server:  bad connection attempt from " + repr(self.addr) + ":\n")
                self.running = False
                self.server.stop()
                self.close()
                return False
            else:
                # self.server.shared_ciphers.append(self.sslconn.shared_ciphers())
                if self.server.context.verify_mode == ssl.CERT_REQUIRED:
                    cert = self.sslconn.getpeercert()
                    if support.verbose and self.server.chatty:
                        sys.stdout.write(" client cert is " + pprint.pformat(cert) + "\n")
                    cert_binary = self.sslconn.getpeercert(True)
                    if support.verbose and self.server.chatty:
                        sys.stdout.write(" cert binary is " + str(len(cert_binary)) + " bytes\n")
                cipher = self.sslconn.cipher()
                if support.verbose and self.server.chatty:
                    sys.stdout.write(" server: connection cipher is now " + str(cipher) + "\n")
                return True

        def read(self):
            if self.sslconn:
                return self.sslconn.recv(256)
            else:
                return self.sock.recv(256)

        def write(self, bytes):
            if self.sslconn:
                return self.sslconn.send(bytes)
            else:
                return self.sock.send(bytes)

        def close(self):
            if self.sslconn:
                self.sslconn.close()
            else:
                self.sock.close()

        def run(self):
            self.running = True
            if not self.server.starttls_server:
                if not self.wrap_conn():
                    return
            while self.running:
                try:
                    msg = self.read()
                    stripped = msg.strip()
                    if not stripped:
                        # eof, so quit this handler
                        self.running = False
                        try:
                            self.sock = self.sslconn.unwrap()
                        except (OSError, AttributeError):
                            # Many tests shut the TCP connection down
                            # without an SSL shutdown. This causes
                            # unwrap() to raise OSError with errno=0!
                            pass
                        else:
                            self.sslconn = None
                        self.close()
                    elif stripped == b'over':
                        if support.verbose and self.server.connectionchatty:
                            sys.stdout.write(" server: client closed connection\n")
                        self.close()
                        return
                    elif (self.server.starttls_server and
                          stripped == b'STARTTLS'):
                        if support.verbose and self.server.connectionchatty:
                            sys.stdout.write(" server: read STARTTLS from client, sending OK...\n")
                        self.write(b"OK\n")
                        if not self.wrap_conn():
                            return
                    elif (self.server.starttls_server and self.sslconn
                          and stripped == b'ENDTLS'):
                        if support.verbose and self.server.connectionchatty:
                            sys.stdout.write(" server: read ENDTLS from client, sending OK...\n")
                        self.write(b"OK\n")
                        self.sock = self.sslconn.unwrap()
                        self.sslconn = None
                        if support.verbose and self.server.connectionchatty:
                            sys.stdout.write(" server: connection is now unencrypted...\n")
                    elif stripped == b'CB tls-unique':
                        if support.verbose and self.server.connectionchatty:
                            sys.stdout.write(" server: read CB tls-unique from client, sending our CB data...\n")
                        data = self.sslconn.get_channel_binding("tls-unique")
                        self.write(repr(data).encode("us-ascii") + b"\n")
                    elif stripped == b'PHA':
                        if support.verbose and self.server.connectionchatty:
                            sys.stdout.write(" server: initiating post handshake auth\n")
                        try:
                            self.sslconn.verify_client_post_handshake()
                        except ssl.SSLError as e:
                            self.write(repr(e).encode("us-ascii") + b"\n")
                        else:
                            self.write(b"OK\n")
                    elif stripped == b'HASCERT':
                        if self.sslconn.getpeercert() is not None:
                            self.write(b'TRUE\n')
                        else:
                            self.write(b'FALSE\n')
                    elif stripped == b'GETCERT':
                        cert = self.sslconn.getpeercert()
                        self.write(repr(cert).encode("us-ascii") + b"\n")
                    else:
                        if (support.verbose and
                            self.server.connectionchatty):
                            ctype = (self.sslconn and "encrypted") or "unencrypted"
                            sys.stdout.write(" server: read %r (%s), sending back %r (%s)...\n"
                                             % (msg, ctype, msg.lower(), ctype))
                        self.write(msg.lower())
                except (ConnectionResetError, ConnectionAbortedError):
                    # XXX: OpenSSL 1.1.1 sometimes raises ConnectionResetError
                    # when connection is not shut down gracefully.
                    if self.server.chatty and support.verbose:
                        sys.stdout.write(
                            " Connection reset by peer: {}\n".format(
                                self.addr)
                        )
                    self.close()
                    self.running = False
                except OSError:
                    if self.server.chatty:
                        handle_error("Test server failure:\n")
                    self.close()
                    self.running = False

                    # normally, we'd just stop here, but for the test
                    # harness, we want to stop the server
                    self.server.stop()

    def __init__(self, certificate=None, ssl_version=None,
                 certreqs=None, cacerts=None,
                 chatty=True, connectionchatty=False, starttls_server=False,
                 alpn_protocols=None,
                 ciphers=None, context=None):
        if context:
            self.context = context
        else:
            self.context = ssl.SSLContext(ssl_version
                                          if ssl_version is not None
                                          else ssl.PROTOCOL_TLS_SERVER)
            self.context.verify_mode = (certreqs if certreqs is not None
                                        else ssl.CERT_NONE)
            if cacerts:
                self.context.load_verify_locations(cacerts)
            if certificate:
                self.context.load_cert_chain(certificate)
            if alpn_protocols:
                self.context.set_alpn_protocols(alpn_protocols)
            if ciphers:
                self.context.set_ciphers(ciphers)
        self.chatty = chatty
        self.connectionchatty = connectionchatty
        self.starttls_server = starttls_server
        self.sock = socket.socket()
        self.port = support.bind_port(self.sock)
        self.flag = None
        self.active = False
        self.selected_alpn_protocols = []
        # self.shared_ciphers = []
        self.conn_errors = []
        threading.Thread.__init__(self)
        self.daemon = True

    def __enter__(self):
        self.start(threading.Event())
        self.flag.wait()
        return self

    def __exit__(self, *args):
        self.stop()
        self.join()

    def start(self, flag=None):
        self.flag = flag
        threading.Thread.start(self)

    def run(self):
        self.sock.settimeout(0.05)
        self.sock.listen()
        self.active = True
        if self.flag:
            # signal an event
            self.flag.set()
        while self.active:
            try:
                newconn, connaddr = self.sock.accept()
                if support.verbose and self.chatty:
                    sys.stdout.write(' server:  new connection from '
                                     + repr(connaddr) + '\n')
                handler = self.ConnectionHandler(self, newconn, connaddr)
                handler.start()
                handler.join()
            except socket.timeout:
                pass
            except KeyboardInterrupt:
                self.stop()
            except BaseException as e:
                if support.verbose and self.chatty:
                    sys.stdout.write(
                        ' connection handling failed: ' + repr(e) + '\n')

        self.sock.close()

    def stop(self):
        self.active = False

@support.skip_micropython
class AsyncoreEchoServer(threading.Thread):
    pass

#     # this one's based on asyncore.dispatcher

#     class EchoServer (asyncore.dispatcher):

#         class ConnectionHandler(asyncore.dispatcher_with_send):

#             def __init__(self, conn, certfile):
#                 self.socket = test_wrap_socket(conn, server_side=True,
#                                               certfile=certfile,
#                                               do_handshake_on_connect=False)
#                 asyncore.dispatcher_with_send.__init__(self, self.socket)
#                 self._ssl_accepting = True
#                 self._do_ssl_handshake()

#             def readable(self):
#                 if isinstance(self.socket, ssl.SSLSocket):
#                     while self.socket.pending() > 0:
#                         self.handle_read_event()
#                 return True

#             def _do_ssl_handshake(self):
#                 try:
#                     self.socket.do_handshake()
#                 except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
#                     return
#                 except ssl.SSLEOFError:
#                     return self.handle_close()
#                 except ssl.SSLError:
#                     raise
#                 except OSError as err:
#                     if err.args[0] == errno.ECONNABORTED:
#                         return self.handle_close()
#                 else:
#                     self._ssl_accepting = False

#             def handle_read(self):
#                 if self._ssl_accepting:
#                     self._do_ssl_handshake()
#                 else:
#                     data = self.recv(256)
#                     if support.verbose:
#                         sys.stdout.write(" server:  read %s from client\n" % repr(data))
#                     if not data:
#                         self.close()
#                     else:
#                         self.send(data.lower())

#             def handle_close(self):
#                 self.close()
#                 if support.verbose:
#                     sys.stdout.write(" server:  closed connection %s\n" % self.socket)

#             def handle_error(self):
#                 raise

#         def __init__(self, certfile):
#             self.certfile = certfile
#             sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             self.port = support.bind_port(sock, '')
#             asyncore.dispatcher.__init__(self, sock)
#             self.listen(5)

#         def handle_accepted(self, sock_obj, addr):
#             if support.verbose:
#                 sys.stdout.write(" server:  new connection from %s:%s\n" %addr)
#             self.ConnectionHandler(sock_obj, self.certfile)

#         def handle_error(self):
#             raise

#     def __init__(self, certfile):
#         self.flag = None
#         self.active = False
#         self.server = self.EchoServer(certfile)
#         self.port = self.server.port
#         threading.Thread.__init__(self)
#         self.daemon = True

#     def __str__(self):
#         return "<%s %s>" % (self.__class__.__name__, self.server)

#     def __enter__(self):
#         self.start(threading.Event())
#         self.flag.wait()
#         return self

#     def __exit__(self, *args):
#         if support.verbose:
#             sys.stdout.write(" cleanup: stopping server.\n")
#         self.stop()
#         if support.verbose:
#             sys.stdout.write(" cleanup: joining server thread.\n")
#         self.join()
#         if support.verbose:
#             sys.stdout.write(" cleanup: successfully joined.\n")
#         # make sure that ConnectionHandler is removed from socket_map
#         asyncore.close_all(ignore_all=True)

#     def start (self, flag=None):
#         self.flag = flag
#         threading.Thread.start(self)

#     def run(self):
#         self.active = True
#         if self.flag:
#             self.flag.set()
#         while self.active:
#             try:
#                 asyncore.loop(1)
#             except:
#                 pass

#     def stop(self):
#         self.active = False
#         self.server.close()

def server_params_test(client_context, server_context, indata=b"FOO\n",
                       chatty=True, connectionchatty=False, sni_name=None,
                       session=None):
    """
    Launch a server, connect a client to it and try various reads
    and writes.
    """
    stats = {}
    server = ThreadedEchoServer(context=server_context,
                                chatty=chatty,
                                connectionchatty=False)
    with server:
        with client_context.wrap_socket(socket.socket(),
                server_hostname=sni_name, session=session) as s:
            s.connect((HOST, server.port))
            for arg in [indata, bytearray(indata), memoryview(indata)]:
                if connectionchatty:
                    if support.verbose:
                        sys.stdout.write(
                            " client:  sending %r...\n" % indata)
                s.send(arg)
                outdata = s.recv(256)
                if connectionchatty:
                    if support.verbose:
                        sys.stdout.write(" client:  read %r\n" % outdata)
                if outdata != indata.lower():
                    raise AssertionError(
                        "bad data <<%r>> (%d) received; expected <<%r>> (%d)\n"
                        % (outdata[:20], len(outdata),
                           indata[:20].lower(), len(indata)))
            s.send(b"over\n")
            if connectionchatty:
                if support.verbose:
                    sys.stdout.write(" client:  closing connection.\n")
            stats.update({
                'compression': s.compression(),
                'cipher': s.cipher(),
                'peercert': s.getpeercert(),
                'client_alpn_protocol': s.selected_alpn_protocol(),
                'version': s.version(),
                'session_reused': getattr(s, 'session_reused', False),
                'session': getattr(s, 'session', None),
            })
            s.close()
        stats['server_alpn_protocols'] = server.selected_alpn_protocols
        # stats['server_shared_ciphers'] = server.shared_ciphers
    return stats

def try_protocol_combo(server_protocol, client_protocol, expect_success,
                       certsreqs=None, server_options=0, client_options=0):
    """
    Try to SSL-connect using *client_protocol* to *server_protocol*.
    If *expect_success* is true, assert that the connection succeeds,
    if it's false, assert that the connection fails.
    Also, if *expect_success* is a string, assert that it is the protocol
    version actually used by the connection.
    """
    if certsreqs is None:
        certsreqs = ssl.CERT_NONE
    certtype = {
        ssl.CERT_NONE: "CERT_NONE",
        ssl.CERT_OPTIONAL: "CERT_OPTIONAL",
        ssl.CERT_REQUIRED: "CERT_REQUIRED",
    }[certsreqs]
    if support.verbose:
        formatstr = (expect_success and " %s->%s %s\n") or " {%s->%s} %s\n"
        sys.stdout.write(formatstr %
                         (ssl.get_protocol_name(client_protocol),
                          ssl.get_protocol_name(server_protocol),
                          certtype))
    client_context = ssl.SSLContext(client_protocol)
    client_context.options |= client_options
    server_context = ssl.SSLContext(server_protocol)
    server_context.options |= server_options

    # NOTE: we must enable "ALL" ciphers on the client, otherwise an
    # SSLv23 client will send an SSLv3 hello (rather than SSLv2)
    # starting from OpenSSL 1.0.0 (see issue #8322).
    if client_context.protocol == ssl.PROTOCOL_TLS_CLIENT:
        client_context.set_ciphers("ALL")

    seclevel_workaround(server_context, client_context)

    for ctx in (client_context, server_context):
        ctx.verify_mode = certsreqs
        ctx.load_cert_chain(SIGNED_CERTFILE)
        ctx.load_verify_locations(SIGNING_CA)
    try:
        stats = server_params_test(client_context, server_context,
                                   chatty=False, connectionchatty=False)
    # Protocol mismatch can result in either an SSLError, or a
    # "Connection reset by peer" error.
    except ssl.SSLError:
        if expect_success:
            raise
    except OSError as e:
        if expect_success or e.errno != errno.ECONNRESET:
            raise
    else:
        if not expect_success:
            raise AssertionError(
                "Client protocol %s succeeded with server protocol %s!"
                % (ssl.get_protocol_name(client_protocol),
                   ssl.get_protocol_name(server_protocol)))
        elif (expect_success is not True
              and expect_success != stats['version']):
            raise AssertionError("version mismatch: expected %r, got %r"
                                 % (expect_success, stats['version']))


@unittest.skip("work in progress")
class ThreadedTests(unittest.TestCase):

    def test_echo(self):
        """Basic test of an SSL client connecting to a server"""
        if support.verbose:
            sys.stdout.write("\n")
        for protocol in PROTOCOLS:
            if protocol in {ssl.PROTOCOL_TLS_CLIENT, ssl.PROTOCOL_TLS_SERVER}:
                continue
            with self.subTest(protocol=ssl._PROTOCOL_NAMES[protocol]):
                context = ssl.SSLContext(protocol)
                context.load_cert_chain(CERTFILE)
                seclevel_workaround(context)
                server_params_test(context, context,
                                   chatty=True, connectionchatty=True)

        client_context, server_context, hostname = testing_context()

        with self.subTest(client=ssl.PROTOCOL_TLS_CLIENT, server=ssl.PROTOCOL_TLS_SERVER):
            server_params_test(client_context=client_context,
                               server_context=server_context,
                               chatty=True, connectionchatty=True,
                               sni_name=hostname)

        client_context.check_hostname = False
        with self.subTest(client=ssl.PROTOCOL_TLS_SERVER, server=ssl.PROTOCOL_TLS_CLIENT):
            with self.assertRaises(ssl.SSLError) as e:
                server_params_test(client_context=server_context,
                                   server_context=client_context,
                                   chatty=True, connectionchatty=True,
                                   sni_name=hostname)
            self.assertIn('called a function you should not call',
                          str(e.exception))

        with self.subTest(client=ssl.PROTOCOL_TLS_SERVER, server=ssl.PROTOCOL_TLS_SERVER):
            with self.assertRaises(ssl.SSLError) as e:
                server_params_test(client_context=server_context,
                                   server_context=server_context,
                                   chatty=True, connectionchatty=True)
            self.assertIn('called a function you should not call',
                          str(e.exception))

        with self.subTest(client=ssl.PROTOCOL_TLS_CLIENT, server=ssl.PROTOCOL_TLS_CLIENT):
            with self.assertRaises(ssl.SSLError) as e:
                server_params_test(client_context=server_context,
                                   server_context=client_context,
                                   chatty=True, connectionchatty=True)
            self.assertIn('called a function you should not call',
                          str(e.exception))

    def test_getpeercert(self):
        if support.verbose:
            sys.stdout.write("\n")

        client_context, server_context, hostname = testing_context()
        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            do_handshake_on_connect=False,
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                # getpeercert() raise ValueError while the handshake isn't
                # done.
                with self.assertRaises(ValueError):
                    s.getpeercert()
                s.do_handshake()
                cert = s.getpeercert()
                self.assertTrue(cert, "Can't get peer certificate.")
                cipher = s.cipher()
                if support.verbose:
                    sys.stdout.write(pprint.pformat(cert) + '\n')
                    sys.stdout.write("Connection cipher is " + str(cipher) + '.\n')
                if 'subject' not in cert:
                    self.fail("No subject field in certificate: %s." %
                              pprint.pformat(cert))
                if ((('organizationName', 'Python Software Foundation'),)
                    not in cert['subject']):
                    self.fail(
                        "Missing or invalid 'organizationName' field in certificate subject; "
                        "should be 'Python Software Foundation'.")
                self.assertIn('notBefore', cert)
                self.assertIn('notAfter', cert)
                before = ssl.cert_time_to_seconds(cert['notBefore'])
                after = ssl.cert_time_to_seconds(cert['notAfter'])
                self.assertLess(before, after)

    @unittest.skipUnless(have_verify_flags(),
                        "verify_flags need OpenSSL > 0.9.8")
    def test_crl_check(self):
        if support.verbose:
            sys.stdout.write("\n")

        client_context, server_context, hostname = testing_context()

        tf = getattr(ssl, "VERIFY_X509_TRUSTED_FIRST", 0)
        self.assertEqual(client_context.verify_flags, ssl.VERIFY_DEFAULT | tf)

        # VERIFY_DEFAULT should pass
        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                cert = s.getpeercert()
                self.assertTrue(cert, "Can't get peer certificate.")

        # VERIFY_CRL_CHECK_LEAF without a loaded CRL file fails
        client_context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF

        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                with self.assertRaisesRegex(ssl.SSLError,
                                            "certificate verify failed"):
                    s.connect((HOST, server.port))

        # now load a CRL file. The CRL file is signed by the CA.
        client_context.load_verify_locations(CRLFILE)

        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                cert = s.getpeercert()
                self.assertTrue(cert, "Can't get peer certificate.")

    def test_check_hostname(self):
        if support.verbose:
            sys.stdout.write("\n")

        client_context, server_context, hostname = testing_context()

        # correct hostname should verify
        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                cert = s.getpeercert()
                self.assertTrue(cert, "Can't get peer certificate.")

        # incorrect hostname should raise an exception
        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname="invalid") as s:
                with self.assertRaises(ssl.CertificateError):
                    s.connect((HOST, server.port))

        # missing server_hostname arg should cause an exception, too
        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with socket.socket() as s:
                with self.assertRaisesRegex(ValueError,
                                            "check_hostname requires server_hostname"):
                    client_context.wrap_socket(s)

    def test_ecc_cert(self):
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_context.load_verify_locations(SIGNING_CA)
        client_context.set_ciphers('TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-ECDSA-WITH-AES-128-GCM-SHA256')
        hostname = SIGNED_CERTFILE_ECC_HOSTNAME

        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # load ECC cert
        server_context.load_cert_chain(SIGNED_CERTFILE_ECC)

        # correct hostname should verify
        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                cert = s.getpeercert()
                self.assertTrue(cert, "Can't get peer certificate.")
                cipher = s.cipher()[0].split('-')
                self.assertTrue(cipher[:2], ('ECDHE', 'ECDSA'))

    def test_dual_rsa_ecc(self):
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_context.load_verify_locations(SIGNING_CA)
        # only ECDSA certs
        client_context.set_ciphers('TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-ECDSA-WITH-AES-128-GCM-SHA256')
        hostname = SIGNED_CERTFILE_ECC_HOSTNAME

        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # load ECC and RSA key/cert pairs
        server_context.load_cert_chain(SIGNED_CERTFILE_ECC)
        server_context.load_cert_chain(SIGNED_CERTFILE)

        # correct hostname should verify
        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                cert = s.getpeercert()
                self.assertTrue(cert, "Can't get peer certificate.")
                cipher = s.cipher()[0].split('-')
                self.assertTrue(cipher[:2], ('ECDHE', 'ECDSA'))

    @support.skip_micropython
    def test_check_hostname_idn(self):
        if support.verbose:
            sys.stdout.write("\n")

        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(IDNSANSFILE)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.load_verify_locations(SIGNING_CA)

        # correct hostname should verify, when specified in several
        # different ways
        idn_hostnames = [
            ('könig.idn.pythontest.net',
             'xn--knig-5qa.idn.pythontest.net'),
            ('xn--knig-5qa.idn.pythontest.net',
             'xn--knig-5qa.idn.pythontest.net'),
            (b'xn--knig-5qa.idn.pythontest.net',
             'xn--knig-5qa.idn.pythontest.net'),

            ('königsgäßchen.idna2003.pythontest.net',
             'xn--knigsgsschen-lcb0w.idna2003.pythontest.net'),
            ('xn--knigsgsschen-lcb0w.idna2003.pythontest.net',
             'xn--knigsgsschen-lcb0w.idna2003.pythontest.net'),
            (b'xn--knigsgsschen-lcb0w.idna2003.pythontest.net',
             'xn--knigsgsschen-lcb0w.idna2003.pythontest.net'),

            # ('königsgäßchen.idna2008.pythontest.net',
            #  'xn--knigsgchen-b4a3dun.idna2008.pythontest.net'),
            ('xn--knigsgchen-b4a3dun.idna2008.pythontest.net',
             'xn--knigsgchen-b4a3dun.idna2008.pythontest.net'),
            (b'xn--knigsgchen-b4a3dun.idna2008.pythontest.net',
             'xn--knigsgchen-b4a3dun.idna2008.pythontest.net'),

        ]
        for server_hostname, expected_hostname in idn_hostnames:
            server = ThreadedEchoServer(context=server_context, chatty=True)
            with server:
                with context.wrap_socket(socket.socket(),
                                         server_hostname=server_hostname) as s:
                    self.assertEqual(s.server_hostname, expected_hostname)
                    s.connect((HOST, server.port))
                    cert = s.getpeercert()
                    self.assertEqual(s.server_hostname, expected_hostname)
                    self.assertTrue(cert, "Can't get peer certificate.")

        # incorrect hostname should raise an exception
        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with context.wrap_socket(socket.socket(),
                                     server_hostname="python.example.org") as s:
                with self.assertRaises(ssl.CertificateError):
                    s.connect((HOST, server.port))

    def test_wrong_cert_tls12(self):
        """Connecting when the server rejects the client's certificate

        Launch a server with CERT_REQUIRED, and check that trying to
        connect to it with a wrong client certificate fails.
        """
        client_context, server_context, hostname = testing_context()
        # load client cert that is not signed by trusted CA
        client_context.load_cert_chain(CERTFILE)
        # require TLS client authentication
        server_context.verify_mode = ssl.CERT_REQUIRED
        # TLS 1.3 has different handshake
        # client_context.maximum_version = ssl.TLSVersion.TLSv1_2

        server = ThreadedEchoServer(
            context=server_context, chatty=True, connectionchatty=True,
        )

        with server, \
                client_context.wrap_socket(socket.socket(),
                                           server_hostname=hostname) as s:
            try:
                # Expect either an SSL error about the server rejecting
                # the connection, or a low-level connection reset (which
                # sometimes happens on Windows)
                s.connect((HOST, server.port))
            except ssl.SSLError as e:
                if support.verbose:
                    sys.stdout.write("\nSSLError is %r\n" % e)
            except OSError as e:
                if e.errno != errno.ECONNRESET:
                    raise
                if support.verbose:
                    sys.stdout.write("\nsocket.error is %r\n" % e)
            else:
                self.fail("Use of invalid cert should have failed!")

    @requires_tls_version('TLSv1_3')
    def test_wrong_cert_tls13(self):
        client_context, server_context, hostname = testing_context()
        # load client cert that is not signed by trusted CA
        client_context.load_cert_chain(CERTFILE)
        server_context.verify_mode = ssl.CERT_REQUIRED
        server_context.minimum_version = ssl.TLSVersion.TLSv1_3
        client_context.minimum_version = ssl.TLSVersion.TLSv1_3

        server = ThreadedEchoServer(
            context=server_context, chatty=True, connectionchatty=True,
        )
        with server, \
             client_context.wrap_socket(socket.socket(),
                                        server_hostname=hostname) as s:
            # TLS 1.3 perform client cert exchange after handshake
            s.connect((HOST, server.port))
            try:
                s.send(b'data')
                s.recv(4)
            except ssl.SSLError as e:
                if support.verbose:
                    sys.stdout.write("\nSSLError is %r\n" % e)
            except OSError as e:
                if e.errno != errno.ECONNRESET:
                    raise
                if support.verbose:
                    sys.stdout.write("\nsocket.error is %r\n" % e)
            else:
                self.fail("Use of invalid cert should have failed!")

    def test_rude_shutdown(self):
        """A brutal shutdown of an SSL server should raise an OSError
        in the client when attempting handshake.
        """
        listener_ready = threading.Event()
        listener_gone = threading.Event()

        s = socket.socket()
        port = support.bind_port(s, HOST)

        # `listener` runs in a thread.  It sits in an accept() until
        # the main thread connects.  Then it rudely closes the socket,
        # and sets Event `listener_gone` to let the main thread know
        # the socket is gone.
        def listener():
            s.listen()
            listener_ready.set()
            newsock, addr = s.accept()
            newsock.close()
            s.close()
            listener_gone.set()

        def connector():
            listener_ready.wait()
            with socket.socket() as c:
                c.connect((HOST, port))
                listener_gone.wait()
                try:
                    ssl_sock = test_wrap_socket(c)
                except OSError:
                    pass
                else:
                    self.fail('connecting to closed SSL socket should have failed')

        t = threading.Thread(target=listener)
        t.start()
        try:
            connector()
        finally:
            t.join()

    def test_ssl_cert_verify_error(self):
        if support.verbose:
            sys.stdout.write("\n")

        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(SIGNED_CERTFILE)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

        server = ThreadedEchoServer(context=server_context, chatty=True)
        with server:
            with context.wrap_socket(socket.socket(),
                                     server_hostname=SIGNED_CERTFILE_HOSTNAME) as s:
                try:
                    s.connect((HOST, server.port))
                except ssl.SSLError as e:
                    msg = 'unable to get local issuer certificate'
                    self.assertIsInstance(e, ssl.SSLCertVerificationError)
                    self.assertEqual(e.verify_code, 20)
                    self.assertEqual(e.verify_message, msg)
                    self.assertIn(msg, repr(e))
                    self.assertIn('certificate verify failed', repr(e))

    def test_starttls(self):
        """Switching from clear text to encrypted and back again."""
        msgs = (b"msg 1", b"MSG 2", b"STARTTLS", b"MSG 3", b"msg 4", b"ENDTLS", b"msg 5", b"msg 6")

        server = ThreadedEchoServer(CERTFILE,
                                    starttls_server=True,
                                    chatty=True,
                                    connectionchatty=True)
        wrapped = False
        with server:
            s = socket.socket()
            s.setblocking(1)
            s.connect((HOST, server.port))
            if support.verbose:
                sys.stdout.write("\n")
            for indata in msgs:
                if support.verbose:
                    sys.stdout.write(
                        " client:  sending %r...\n" % indata)
                if wrapped:
                    conn.write(indata)
                    outdata = conn.read()
                else:
                    s.send(indata)
                    outdata = s.recv(256)
                msg = outdata.strip().lower()
                if indata == b"STARTTLS" and msg.startswith(b"ok"):
                    # STARTTLS ok, switch to secure mode
                    if support.verbose:
                        sys.stdout.write(
                            " client:  read %r from server, starting TLS...\n"
                            % msg)
                    conn = test_wrap_socket(s)
                    wrapped = True
                elif indata == b"ENDTLS" and msg.startswith(b"ok"):
                    # ENDTLS ok, switch back to clear text
                    if support.verbose:
                        sys.stdout.write(
                            " client:  read %r from server, ending TLS...\n"
                            % msg)
                    s = conn.unwrap()
                    wrapped = False
                else:
                    if support.verbose:
                        sys.stdout.write(
                            " client:  read %r from server\n" % msg)
            if support.verbose:
                sys.stdout.write(" client:  closing connection.\n")
            if wrapped:
                conn.write(b"over\n")
            else:
                s.send(b"over\n")
            if wrapped:
                conn.close()
            else:
                s.close()

    def test_socketserver(self):
        """Using socketserver to create and manage SSL connections."""
        server = make_https_server(self, certfile=SIGNED_CERTFILE)
        # try to connect
        if support.verbose:
            sys.stdout.write('\n')
        with open(CERTFILE, 'rb') as f:
            d1 = f.read()
        d2 = ''
        # now fetch the same data from the HTTPS server
        url = 'https://localhost:%d/%s' % (
            server.port, os.path.split(CERTFILE)[1])
        context = ssl.create_default_context(cafile=SIGNING_CA)
        f = urllib.request.urlopen(url, context=context)
        try:
            dlen = f.info().get("content-length")
            if dlen and (int(dlen) > 0):
                d2 = f.read(int(dlen))
                if support.verbose:
                    sys.stdout.write(
                        " client: read %d bytes from remote server '%s'\n"
                        % (len(d2), server))
        finally:
            f.close()
        self.assertEqual(d1, d2)

    def test_asyncore_server(self):
        """Check the example asyncore integration."""
        if support.verbose:
            sys.stdout.write("\n")

        indata = b"FOO\n"
        server = AsyncoreEchoServer(CERTFILE)
        with server:
            s = test_wrap_socket(socket.socket())
            s.connect(('127.0.0.1', server.port))
            if support.verbose:
                sys.stdout.write(
                    " client:  sending %r...\n" % indata)
            s.send(indata)
            outdata = s.recv(256)
            if support.verbose:
                sys.stdout.write(" client:  read %r\n" % outdata)
            if outdata != indata.lower():
                self.fail(
                    "bad data <<%r>> (%d) received; expected <<%r>> (%d)\n"
                    % (outdata[:20], len(outdata),
                       indata[:20].lower(), len(indata)))
            s.send(b"over\n")
            if support.verbose:
                sys.stdout.write(" client:  closing connection.\n")
            s.close()
            if support.verbose:
                sys.stdout.write(" client:  connection closed.\n")

    def test_recv_send(self):
        """Test recv(), send() and friends."""
        if support.verbose:
            sys.stdout.write("\n")

        server = ThreadedEchoServer(CERTFILE,
                                    certreqs=ssl.CERT_NONE,
                                    ssl_version=ssl.PROTOCOL_TLS_SERVER,
                                    cacerts=CERTFILE,
                                    chatty=True,
                                    connectionchatty=False)
        with server:
            s = test_wrap_socket(socket.socket(),
                                server_side=False,
                                certfile=CERTFILE,
                                ca_certs=CERTFILE,
                                cert_reqs=ssl.CERT_NONE)
            s.connect((HOST, server.port))
            # helper methods for standardising recv* method signatures
            def _recv_into():
                b = bytearray(b"\0"*100)
                count = s.recv_into(b)
                return b[:count]

            def _recvfrom_into():
                b = bytearray(b"\0"*100)
                count, addr = s.recvfrom_into(b)
                return b[:count]

            # (name, method, expect success?, *args, return value func)
            send_methods = [
                ('send', s.send, True, [], len),
                ('sendto', s.sendto, False, ["some.address"], len),
                ('sendall', s.sendall, True, [], lambda x: None),
            ]
            # (name, method, whether to expect success, *args)
            recv_methods = [
                ('recv', s.recv, True, []),
                ('recvfrom', s.recvfrom, False, ["some.address"]),
                ('recv_into', _recv_into, True, []),
                ('recvfrom_into', _recvfrom_into, False, []),
            ]
            data_prefix = "PREFIX_"

            for (meth_name, send_meth, expect_success, args,
                    ret_val_meth) in send_methods:
                indata = (data_prefix + meth_name).encode('ascii')
                try:
                    ret = send_meth(indata, *args)
                    msg = "sending with {}".format(meth_name)
                    self.assertEqual(ret, ret_val_meth(indata), msg=msg)
                    outdata = s.recv(256)
                    if outdata != indata.lower():
                        self.fail(
                            "While sending with <<{name:s}>> bad data "
                            "<<{outdata:r}>> ({nout:d}) received; "
                            "expected <<{indata:r}>> ({nin:d})\n".format(
                                name=meth_name, outdata=outdata[:20],
                                nout=len(outdata),
                                indata=indata[:20], nin=len(indata)
                            )
                        )
                except ValueError as e:
                    if expect_success:
                        self.fail(
                            "Failed to send with method <<{name:s}>>; "
                            "expected to succeed.\n".format(name=meth_name)
                        )
                    if not str(e).startswith(meth_name):
                        self.fail(
                            "Method <<{name:s}>> failed with unexpected "
                            "exception message: {exp:s}\n".format(
                                name=meth_name, exp=e
                            )
                        )

            for meth_name, recv_meth, expect_success, args in recv_methods:
                indata = (data_prefix + meth_name).encode('ascii')
                try:
                    s.send(indata)
                    outdata = recv_meth(*args)
                    if outdata != indata.lower():
                        self.fail(
                            "While receiving with <<{name:s}>> bad data "
                            "<<{outdata:r}>> ({nout:d}) received; "
                            "expected <<{indata:r}>> ({nin:d})\n".format(
                                name=meth_name, outdata=outdata[:20],
                                nout=len(outdata),
                                indata=indata[:20], nin=len(indata)
                            )
                        )
                except ValueError as e:
                    if expect_success:
                        self.fail(
                            "Failed to receive with method <<{name:s}>>; "
                            "expected to succeed.\n".format(name=meth_name)
                        )
                    if not str(e).startswith(meth_name):
                        self.fail(
                            "Method <<{name:s}>> failed with unexpected "
                            "exception message: {exp:s}\n".format(
                                name=meth_name, exp=e
                            )
                        )
                    # consume data
                    s.recv(256)

            # read(-1, buffer) is supported, even though read(-1) is not
            data = b"data"
            s.send(data)
            buffer = bytearray(len(data))
            self.assertEqual(s.recv_into(buffer), len(data))
            self.assertEqual(buffer, data)

            # sendall accepts bytes-like objects
            if ctypes is not None:
                ubyte = ctypes.c_ubyte * len(data)
                byteslike = ubyte.from_buffer_copy(data)
                s.sendall(byteslike)
                self.assertEqual(s.recv(256), data)

            # Make sure sendmsg et al are disallowed to avoid
            # inadvertent disclosure of data and/or corruption
            # of the encrypted data stream
            self.assertRaises(NotImplementedError, s.dup)
            self.assertRaises(NotImplementedError, s.sendmsg, [b"data"])
            self.assertRaises(NotImplementedError, s.recvmsg, 100)
            self.assertRaises(NotImplementedError,
                              s.recvmsg_into, [bytearray(100)])
            s.send(b"over\n")

            self.assertRaises(ValueError, s.recv, -1)

            s.close()

    def test_recv_zero(self):
        server = ThreadedEchoServer(CERTFILE)
        server.__enter__()
        self.addCleanup(server.__exit__, None, None)
        s = socket.create_connection((HOST, server.port))
        self.addCleanup(s.close)
        s = test_wrap_socket(s, suppress_ragged_eofs=False)
        self.addCleanup(s.close)

        # recv/read(0) should return no data
        s.send(b"data")
        self.assertEqual(s.recv(0), b"")
        self.assertEqual(s.recv(256), b"data")

        # Should not block if the other end sends no data
        s.setblocking(False)
        self.assertEqual(s.recv(0), b"")
        self.assertEqual(s.recv_into(bytearray()), 0)

    def test_nonblocking_send(self):
        server = ThreadedEchoServer(CERTFILE,
                                    certreqs=ssl.CERT_NONE,
                                    ssl_version=ssl.PROTOCOL_TLS_SERVER,
                                    cacerts=CERTFILE,
                                    chatty=True,
                                    connectionchatty=False)
        with server:
            s = test_wrap_socket(socket.socket(),
                                server_side=False,
                                certfile=CERTFILE,
                                ca_certs=CERTFILE,
                                cert_reqs=ssl.CERT_NONE)
            s.connect((HOST, server.port))
            s.setblocking(False)

            # If we keep sending data, at some point the buffers
            # will be full and the call will block
            buf = bytearray(8192)
            def fill_buffer():
                while True:
                    s.send(buf)
            self.assertRaises((ssl.SSLWantWriteError,
                               ssl.SSLWantReadError), fill_buffer)

            # Now read all the output and discard it
            s.setblocking(True)
            s.close()

    def test_handshake_timeout(self):
        # Issue #5103: SSL handshake must respect the socket timeout
        server = socket.socket(socket.AF_INET)
        host = "127.0.0.1"
        port = support.bind_port(server)
        started = threading.Event()
        finish = False

        def serve():
            server.listen()
            started.set()
            conns = []
            while not finish:
                r, w, e = select.select([server], [], [], 0.1)
                if server in r:
                    # Let the socket hang around rather than having
                    # it closed by garbage collection.
                    conns.append(server.accept()[0])
            for sock in conns:
                sock.close()

        t = threading.Thread(target=serve)
        t.start()
        started.wait()

        try:
            try:
                c = socket.socket(socket.AF_INET)
                c.settimeout(0.2)
                c.connect((host, port))
                # Will attempt handshake and time out
                self.assertRaisesRegex(socket.timeout, "timed out",
                                       test_wrap_socket, c)
            finally:
                c.close()
            try:
                c = socket.socket(socket.AF_INET)
                c = test_wrap_socket(c)
                c.settimeout(0.2)
                # Will attempt handshake and time out
                self.assertRaisesRegex(socket.timeout, "timed out",
                                       c.connect, (host, port))
            finally:
                c.close()
        finally:
            finish = True
            t.join()
            server.close()

    def test_server_accept(self):
        # Issue #16357: accept() on a SSLSocket created through
        # SSLContext.wrap_socket().
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(SIGNING_CA)
        context.load_cert_chain(SIGNED_CERTFILE)
        server = socket.socket(socket.AF_INET)
        host = "127.0.0.1"
        port = support.bind_port(server)
        server = context.wrap_socket(server, server_side=True)
        self.assertTrue(server.server_side)

        evt = threading.Event()
        remote = None
        peer = None
        def serve():
            nonlocal remote, peer
            server.listen()
            # Block on the accept and wait on the connection to close.
            evt.set()
            remote, peer = server.accept()
            remote.send(remote.recv(4))

        t = threading.Thread(target=serve)
        t.start()
        # Client wait until server setup and perform a connect.
        evt.wait()
        client = context.wrap_socket(socket.socket())
        client.connect((host, port))
        client.send(b'data')
        client.recv()
        client_addr = client.getsockname()
        client.close()
        t.join()
        remote.close()
        server.close()
        # Sanity checks.
        self.assertIsInstance(remote, ssl.SSLSocket)
        self.assertEqual(peer, client_addr)

    def test_getpeercert_enotconn(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        with context.wrap_socket(socket.socket()) as sock:
            with self.assertRaises(OSError) as cm:
                sock.getpeercert()
            self.assertEqual(cm.exception.errno, errno.ENOTCONN)

    def test_do_handshake_enotconn(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        with context.wrap_socket(socket.socket()) as sock:
            with self.assertRaises(OSError) as cm:
                sock.do_handshake()
            self.assertEqual(cm.exception.errno, errno.ENOTCONN)

    def test_no_shared_ciphers(self):
        client_context, server_context, hostname = testing_context()
        # Force different suites on client and master
        client_context.set_ciphers("TLS-ECDHE-ECDSA-WITH-AES-128-GCM-SHA256:TLS-ECDHE-RSA-WITH-AES-128-GCM-SHA256")
        server_context.set_ciphers("TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384")
        with ThreadedEchoServer(context=server_context) as server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                with self.assertRaises(OSError):
                    s.connect((HOST, server.port))

    def test_version_basic(self):
        """
        Basic tests for SSLSocket.version().
        More tests are done in the test_protocol_*() methods.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with ThreadedEchoServer(CERTFILE,
                                ssl_version=ssl.PROTOCOL_TLS_SERVER,
                                chatty=False) as server:
            with context.wrap_socket(socket.socket()) as s:
                self.assertIs(s.version(), None)
                s.connect((HOST, server.port))
                if IS_OPENSSL_1_1_1 and has_tls_version('TLSv1_3'):
                    self.assertEqual(s.version(), 'TLSv1.3')
                elif ssl.OPENSSL_VERSION_INFO >= (1, 0, 2):
                    self.assertEqual(s.version(), 'TLSv1.2')
                else:  # 0.9.8 to 1.0.1
                    self.assertIn(s.version(), ('TLSv1', 'TLSv1.2'))
            self.assertIs(s.version(), None)

    @requires_tls_version('TLSv1_3')
    def test_tls1_3(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(CERTFILE)
        context.options |= 0
        with ThreadedEchoServer(context=context) as server:
            with context.wrap_socket(socket.socket()) as s:
                s.connect((HOST, server.port))
                self.assertIn(s.cipher()[0], {
                    'TLS_AES_256_GCM_SHA384',
                    'TLS_CHACHA20_POLY1305_SHA256',
                    'TLS_AES_128_GCM_SHA256',
                })
                self.assertEqual(s.version(), 'TLSv1.3')

    @requires_minimum_version
    @requires_tls_version('TLSv1_2')
    def test_min_max_version_tlsv1_2(self):
        client_context, server_context, hostname = testing_context()
        # client TLSv1.0 to 1.2
        client_context.minimum_version = ssl.TLSVersion.TLSv1
        client_context.maximum_version = ssl.TLSVersion.TLSv1_2
        # server only TLSv1.2
        server_context.minimum_version = ssl.TLSVersion.TLSv1_2
        server_context.maximum_version = ssl.TLSVersion.TLSv1_2

        with ThreadedEchoServer(context=server_context) as server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                self.assertEqual(s.version(), 'TLSv1.2')

    @requires_minimum_version
    @requires_tls_version('TLSv1_2')
    def test_min_max_version_mismatch(self):
        client_context, server_context, hostname = testing_context()
        # client 1.0, server 1.2 (mismatch)
        server_context.minimum_version = ssl.TLSVersion.TLSv1_2
        server_context.maximum_version = ssl.TLSVersion.TLSv1_2
        client_context.minimum_version = ssl.TLSVersion.TLSv1
        client_context.maximum_version = ssl.TLSVersion.TLSv1
        seclevel_workaround(client_context, server_context)

        with ThreadedEchoServer(context=server_context) as server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                with self.assertRaises(ssl.SSLError) as e:
                    s.connect((HOST, server.port))
                self.assertIn("alert", str(e.exception))

    @unittest.skipUnless(ssl.HAS_ECDH, "test requires ECDH-enabled OpenSSL")
    def test_default_ecdh_curve(self):
        # Issue #21015: elliptic curve-based Diffie Hellman key exchange
        # should be enabled by default on SSL contexts.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.load_cert_chain(CERTFILE)
        # TLSv1.3 defaults to PFS key agreement and no longer has KEA in
        # cipher name.
        context.options |= 0
        with ThreadedEchoServer(context=context) as server:
            with context.wrap_socket(socket.socket()) as s:
                s.connect((HOST, server.port))
                self.assertIn("ECDH", s.cipher()[0])

    @unittest.skipUnless("tls-unique" in ssl.CHANNEL_BINDING_TYPES,
                         "'tls-unique' channel binding not available")
    def test_tls_unique_channel_binding(self):
        """Test tls-unique channel binding."""
        if support.verbose:
            sys.stdout.write("\n")

        client_context, server_context, hostname = testing_context()

        server = ThreadedEchoServer(context=server_context,
                                    chatty=True,
                                    connectionchatty=False)

        with server:
            with client_context.wrap_socket(
                    socket.socket(),
                    server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                # get the data
                cb_data = s.get_channel_binding("tls-unique")
                if support.verbose:
                    sys.stdout.write(
                        " got channel binding data: {0!r}\n".format(cb_data))

                # check if it is sane
                self.assertIsNotNone(cb_data)
                if s.version() == 'TLSv1.3':
                    self.assertEqual(len(cb_data), 48)
                else:
                    self.assertEqual(len(cb_data), 12)  # True for TLSv1

                # and compare with the peers version
                s.send(b"CB tls-unique\n")
                peer_data_repr = s.recv(256).strip()
                self.assertEqual(peer_data_repr,
                                 repr(cb_data).encode("us-ascii"))

            # now, again
            with client_context.wrap_socket(
                    socket.socket(),
                    server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                new_cb_data = s.get_channel_binding("tls-unique")
                if support.verbose:
                    sys.stdout.write(
                        "got another channel binding data: {0!r}\n".format(
                            new_cb_data)
                    )
                # is it really unique
                self.assertNotEqual(cb_data, new_cb_data)
                self.assertIsNotNone(cb_data)
                if s.version() == 'TLSv1.3':
                    self.assertEqual(len(cb_data), 48)
                else:
                    self.assertEqual(len(cb_data), 12)  # True for TLSv1
                s.send(b"CB tls-unique\n")
                peer_data_repr = s.recv(256).strip()
                self.assertEqual(peer_data_repr,
                                 repr(new_cb_data).encode("us-ascii"))

    def test_compression(self):
        client_context, server_context, hostname = testing_context()
        stats = server_params_test(client_context, server_context,
                                   chatty=True, connectionchatty=True,
                                   sni_name=hostname)
        if support.verbose:
            sys.stdout.write(" got compression: {!r}\n".format(stats['compression']))
        self.assertIn(stats['compression'], { None, 'ZLIB', 'RLE' })

    @unittest.skipUnless(hasattr(ssl, 'OP_NO_COMPRESSION'),
                         "ssl.OP_NO_COMPRESSION needed for this test")
    def test_compression_disabled(self):
        client_context, server_context, hostname = testing_context()
        client_context.options |= ssl.OP_NO_COMPRESSION
        server_context.options |= ssl.OP_NO_COMPRESSION
        stats = server_params_test(client_context, server_context,
                                   chatty=True, connectionchatty=True,
                                   sni_name=hostname)
        self.assertIs(stats['compression'], None)

    @unittest.skipUnless(hasattr(ssl.SSLContext, 'load_dh_params'), "needs load_dh_params")
    def test_dh_params(self):
        # Check we can get a connection with ephemeral Diffie-Hellman
        client_context, server_context, hostname = testing_context()
        # test scenario needs TLS <= 1.2
        server_context.load_dh_params(DHFILE)
        server_context.set_ciphers("kEDH")
        stats = server_params_test(client_context, server_context,
                                   chatty=True, connectionchatty=True,
                                   sni_name=hostname)
        cipher = stats["cipher"][0]
        parts = cipher.split("-")
        if "ADH" not in parts and "EDH" not in parts and "DHE" not in parts:
            self.fail("Non-DH cipher: " + cipher[0])

    @unittest.skipUnless(HAVE_SECP_CURVES, "needs secp384r1 curve support")
    @unittest.skipIf(IS_OPENSSL_1_1_1, "TODO: Test doesn't work on 1.1.1")
    def test_ecdh_curve(self):
        # server secp384r1, client auto
        client_context, server_context, hostname = testing_context()

        server_context.set_ecdh_curve("secp384r1")
        server_context.set_ciphers("ALL")
        stats = server_params_test(client_context, server_context,
                                   chatty=True, connectionchatty=True,
                                   sni_name=hostname)

        # server auto, client secp384r1
        client_context, server_context, hostname = testing_context()
        client_context.set_ecdh_curve("secp384r1")
        server_context.set_ciphers("ALL")
        stats = server_params_test(client_context, server_context,
                                   chatty=True, connectionchatty=True,
                                   sni_name=hostname)

        # server / client curve mismatch
        client_context, server_context, hostname = testing_context()
        client_context.set_ecdh_curve("secp256r1")
        server_context.set_ecdh_curve("secp384r1")
        server_context.set_ciphers("ALL")
        try:
            stats = server_params_test(client_context, server_context,
                                       chatty=True, connectionchatty=True,
                                       sni_name=hostname)
        except ssl.SSLError:
            pass
        else:
            # OpenSSL 1.0.2 does not fail although it should.
            if IS_OPENSSL_1_1_0:
                self.fail("mismatch curve did not fail")

    def test_selected_alpn_protocol(self):
        # selected_alpn_protocol() is None unless ALPN is used.
        client_context, server_context, hostname = testing_context()
        stats = server_params_test(client_context, server_context,
                                   chatty=True, connectionchatty=True,
                                   sni_name=hostname)
        self.assertIs(stats['client_alpn_protocol'], None)

    @unittest.skipUnless(ssl.HAS_ALPN, "ALPN support required")
    def test_selected_alpn_protocol_if_server_uses_alpn(self):
        # selected_alpn_protocol() is None unless ALPN is used by the client.
        client_context, server_context, hostname = testing_context()
        server_context.set_alpn_protocols(['foo', 'bar'])
        stats = server_params_test(client_context, server_context,
                                   chatty=True, connectionchatty=True,
                                   sni_name=hostname)
        self.assertIs(stats['client_alpn_protocol'], None)

    @unittest.skipUnless(ssl.HAS_ALPN, "ALPN support needed for this test")
    def test_alpn_protocols(self):
        server_protocols = ['foo', 'bar', 'milkshake']
        protocol_tests = [
            (['foo', 'bar'], 'foo'),
            (['bar', 'foo'], 'foo'),
            (['milkshake'], 'milkshake'),
            (['http/3.0', 'http/4.0'], None)
        ]
        for client_protocols, expected in protocol_tests:
            client_context, server_context, hostname = testing_context()
            server_context.set_alpn_protocols(server_protocols)
            client_context.set_alpn_protocols(client_protocols)

            try:
                stats = server_params_test(client_context,
                                           server_context,
                                           chatty=True,
                                           connectionchatty=True,
                                           sni_name=hostname)
            except ssl.SSLError as e:
                stats = e

            if (expected is None and IS_OPENSSL_1_1_0
                    and ssl.OPENSSL_VERSION_INFO < (1, 1, 0, 6)):
                # OpenSSL 1.1.0 to 1.1.0e raises handshake error
                self.assertIsInstance(stats, ssl.SSLError)
            else:
                msg = "failed trying %s (s) and %s (c).\n" \
                    "was expecting %s, but got %%s from the %%s" \
                        % (str(server_protocols), str(client_protocols),
                            str(expected))
                client_result = stats['client_alpn_protocol']
                self.assertEqual(client_result, expected,
                                 msg % (client_result, "client"))
                server_result = stats['server_alpn_protocols'][-1] \
                    if len(stats['server_alpn_protocols']) else 'nothing'
                self.assertEqual(server_result, expected,
                                 msg % (server_result, "server"))

    def sni_contexts(self):
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(SIGNED_CERTFILE)
        other_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        other_context.load_cert_chain(SIGNED_CERTFILE2)
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_context.load_verify_locations(SIGNING_CA)
        return server_context, other_context, client_context

    def check_common_name(self, stats, name):
        cert = stats['peercert']
        self.assertIn((('commonName', name),), cert['subject'])

    @needs_sni
    def test_sni_callback(self):
        calls = []
        server_context, other_context, client_context = self.sni_contexts()

        client_context.check_hostname = False

        def servername_cb(ssl_sock, server_name, initial_context):
            calls.append((server_name, initial_context))
            if server_name is not None:
                ssl_sock.context = other_context
        server_context.set_servername_callback(servername_cb)

        stats = server_params_test(client_context, server_context,
                                   chatty=True,
                                   sni_name='supermessage')
        # The hostname was fetched properly, and the certificate was
        # changed for the connection.
        self.assertEqual(calls, [("supermessage", server_context)])
        # CERTFILE4 was selected
        self.check_common_name(stats, 'fakehostname')

        calls = []
        # The callback is called with server_name=None
        stats = server_params_test(client_context, server_context,
                                   chatty=True,
                                   sni_name=None)
        self.assertEqual(calls, [(None, server_context)])
        self.check_common_name(stats, SIGNED_CERTFILE_HOSTNAME)

        # Check disabling the callback
        calls = []
        server_context.set_servername_callback(None)

        stats = server_params_test(client_context, server_context,
                                   chatty=True,
                                   sni_name='notfunny')
        # Certificate didn't change
        self.check_common_name(stats, SIGNED_CERTFILE_HOSTNAME)
        self.assertEqual(calls, [])

    @needs_sni
    def test_sni_callback_alert(self):
        # Returning a TLS alert is reflected to the connecting client
        server_context, other_context, client_context = self.sni_contexts()

        def cb_returning_alert(ssl_sock, server_name, initial_context):
            return ssl.ALERT_DESCRIPTION_ACCESS_DENIED
        server_context.set_servername_callback(cb_returning_alert)
        with self.assertRaises(ssl.SSLError) as cm:
            stats = server_params_test(client_context, server_context,
                                       chatty=False,
                                       sni_name='supermessage')
        # self.assertEqual(cm.exception.reason, 'TLSV1_ALERT_ACCESS_DENIED')

    @needs_sni
    def test_sni_callback_raising(self):
        # Raising fails the connection with a TLS handshake failure alert.
        server_context, other_context, client_context = self.sni_contexts()

        def cb_raising(ssl_sock, server_name, initial_context):
            1/0
        server_context.set_servername_callback(cb_raising)

        with self.assertRaises(ssl.SSLError) as cm, \
             support.captured_stderr() as stderr:
            stats = server_params_test(client_context, server_context,
                                       chatty=False,
                                       sni_name='supermessage')
        # self.assertEqual(cm.exception.reason, 'SSLV3_ALERT_HANDSHAKE_FAILURE')
        self.assertIn("ZeroDivisionError", stderr.getvalue())

    @needs_sni
    def test_sni_callback_wrong_return_type(self):
        # Returning the wrong return type terminates the TLS connection
        # with an internal error alert.
        server_context, other_context, client_context = self.sni_contexts()

        def cb_wrong_return_type(ssl_sock, server_name, initial_context):
            return "foo"
        server_context.set_servername_callback(cb_wrong_return_type)

        with self.assertRaises(ssl.SSLError) as cm, \
             support.captured_stderr() as stderr:
            stats = server_params_test(client_context, server_context,
                                       chatty=False,
                                       sni_name='supermessage')
        # self.assertEqual(cm.exception.reason, 'TLSV1_ALERT_INTERNAL_ERROR')
        self.assertIn("TypeError", stderr.getvalue())

    def test_shared_ciphers(self):
        client_context, server_context, hostname = testing_context()
        client_context.set_ciphers("ALL")
        server_context.set_ciphers("TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384:TLS-ECDHE-RSA-WITH-AES-256-GCM-SHA384")
        expected_algs = [
            "AES256", "AES-256",
            # TLS 1.3 ciphers are always enabled
            "TLS_CHACHA20", "TLS_AES",
        ]

        stats = server_params_test(client_context, server_context,
                                   sni_name=hostname)
        # ciphers = stats['server_shared_ciphers'][0]
        # self.assertGreater(len(ciphers), 0)
        for name, tls_version, bits in ciphers:
            if not any(alg in name for alg in expected_algs):
                self.fail(name)

    def test_read_write_after_close_raises_valuerror(self):
        client_context, server_context, hostname = testing_context()
        server = ThreadedEchoServer(context=server_context, chatty=False)

        with server:
            s = client_context.wrap_socket(socket.socket(),
                                           server_hostname=hostname)
            s.connect((HOST, server.port))
            s.close()

            self.assertRaises(ValueError, s.recv, 256)
            self.assertRaises(ValueError, s.send, b'hello')

    def test_sendfile(self):
        TEST_DATA = b"x" * 512
        with open(support.TESTFN, 'wb') as f:
            f.write(TEST_DATA)
        self.addCleanup(support.unlink, support.TESTFN)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(SIGNING_CA)
        context.load_cert_chain(SIGNED_CERTFILE)
        server = ThreadedEchoServer(context=context, chatty=False)
        with server:
            with context.wrap_socket(socket.socket()) as s:
                s.connect((HOST, server.port))
                with open(support.TESTFN, 'rb') as file:
                    s.sendfile(file)
                    self.assertEqual(s.recv(256), TEST_DATA)

    @unittest.skipUnless(hasattr(ssl, 'SSLSession'), "needs SSLSession")
    def test_session(self):
        client_context, server_context, hostname = testing_context()

        # first connection without session
        stats = server_params_test(client_context, server_context,
                                   sni_name=hostname)
        session = stats['session']
        self.assertTrue(session.id)
        self.assertGreater(session.time, 0)
        self.assertGreater(session.timeout, 0)
        self.assertTrue(session.has_ticket)
        if ssl.OPENSSL_VERSION_INFO > (1, 0, 1):
            self.assertGreater(session.ticket_lifetime_hint, 0)
        self.assertFalse(stats['session_reused'])
        sess_stat = server_context.session_stats()
        self.assertEqual(sess_stat['accept'], 1)
        self.assertEqual(sess_stat['hits'], 0)

        # reuse session
        stats = server_params_test(client_context, server_context,
                                   session=session, sni_name=hostname)
        sess_stat = server_context.session_stats()
        self.assertEqual(sess_stat['accept'], 2)
        self.assertEqual(sess_stat['hits'], 1)
        self.assertTrue(stats['session_reused'])
        session2 = stats['session']
        self.assertEqual(session2.id, session.id)
        self.assertEqual(session2, session)
        self.assertIsNot(session2, session)
        self.assertGreaterEqual(session2.time, session.time)
        self.assertGreaterEqual(session2.timeout, session.timeout)

        # another one without session
        stats = server_params_test(client_context, server_context,
                                   sni_name=hostname)
        self.assertFalse(stats['session_reused'])
        session3 = stats['session']
        self.assertNotEqual(session3.id, session.id)
        self.assertNotEqual(session3, session)
        sess_stat = server_context.session_stats()
        self.assertEqual(sess_stat['accept'], 3)
        self.assertEqual(sess_stat['hits'], 1)

        # reuse session again
        stats = server_params_test(client_context, server_context,
                                   session=session, sni_name=hostname)
        self.assertTrue(stats['session_reused'])
        session4 = stats['session']
        self.assertEqual(session4.id, session.id)
        self.assertEqual(session4, session)
        self.assertGreaterEqual(session4.time, session.time)
        self.assertGreaterEqual(session4.timeout, session.timeout)
        sess_stat = server_context.session_stats()
        self.assertEqual(sess_stat['accept'], 4)
        self.assertEqual(sess_stat['hits'], 2)

    @unittest.skipUnless(hasattr(ssl, 'SSLSession'), "needs SSLSession")
    def test_session_handling(self):
        client_context, server_context, hostname = testing_context()
        client_context2, _, _ = testing_context()

        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                # session is None before handshake
                self.assertEqual(s.session, None)
                self.assertEqual(s.session_reused, None)
                s.connect((HOST, server.port))
                session = s.session
                self.assertTrue(session)
                with self.assertRaises(TypeError) as e:
                    s.session = object
                self.assertEqual(str(e.exception), 'Value is not a SSLSession.')

            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                # cannot set session after handshake
                with self.assertRaises(ValueError) as e:
                    s.session = session
                self.assertEqual(str(e.exception),
                                 'Cannot set session after handshake.')

            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                # can set session before handshake and before the
                # connection was established
                s.session = session
                s.connect((HOST, server.port))
                self.assertEqual(s.session.id, session.id)
                self.assertEqual(s.session, session)
                self.assertEqual(s.session_reused, True)

            with client_context2.wrap_socket(socket.socket(),
                                             server_hostname=hostname) as s:
                # cannot re-use session with a different SSLContext
                with self.assertRaises(ValueError) as e:
                    s.session = session
                    s.connect((HOST, server.port))
                self.assertEqual(str(e.exception),
                                 'Session refers to a different SSLContext.')


@unittest.skipUnless(has_tls_version('TLSv1_3'), "Test needs TLS 1.3")
class TestPostHandshakeAuth(unittest.TestCase):
    def test_pha_setter(self):
        protocols = [
            ssl.PROTOCOL_TLS_SERVER, ssl.PROTOCOL_TLS_CLIENT
        ]
        for protocol in protocols:
            ctx = ssl.SSLContext(protocol)
            self.assertEqual(ctx.post_handshake_auth, False)

            ctx.post_handshake_auth = True
            self.assertEqual(ctx.post_handshake_auth, True)

            ctx.verify_mode = ssl.CERT_REQUIRED
            self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
            self.assertEqual(ctx.post_handshake_auth, True)

            ctx.post_handshake_auth = False
            self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
            self.assertEqual(ctx.post_handshake_auth, False)

            ctx.verify_mode = ssl.CERT_OPTIONAL
            ctx.post_handshake_auth = True
            self.assertEqual(ctx.verify_mode, ssl.CERT_OPTIONAL)
            self.assertEqual(ctx.post_handshake_auth, True)

    def test_pha_required(self):
        client_context, server_context, hostname = testing_context()
        server_context.post_handshake_auth = True
        server_context.verify_mode = ssl.CERT_REQUIRED
        client_context.post_handshake_auth = True
        client_context.load_cert_chain(SIGNED_CERTFILE)

        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'FALSE\n')
                s.send(b'PHA')
                self.assertEqual(s.recv(256), b'OK\n')
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'TRUE\n')
                # PHA method just returns true when cert is already available
                s.send(b'PHA')
                self.assertEqual(s.recv(256), b'OK\n')
                s.send(b'GETCERT')
                cert_text = s.recv(4096).decode('us-ascii')
                self.assertIn('Python Software Foundation CA', cert_text)

    def test_pha_required_nocert(self):
        client_context, server_context, hostname = testing_context()
        server_context.post_handshake_auth = True
        server_context.verify_mode = ssl.CERT_REQUIRED
        client_context.post_handshake_auth = True

        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                s.send(b'PHA')
                # receive CertificateRequest
                self.assertEqual(s.recv(256), b'OK\n')
                # send empty Certificate + Finish
                s.send(b'HASCERT')
                # receive alert
                with self.assertRaisesRegex(
                        ssl.SSLError,
                        'tlsv13 alert certificate required'):
                    s.recv(256)

    def test_pha_optional(self):
        if support.verbose:
            sys.stdout.write("\n")

        client_context, server_context, hostname = testing_context()
        server_context.post_handshake_auth = True
        server_context.verify_mode = ssl.CERT_REQUIRED
        client_context.post_handshake_auth = True
        client_context.load_cert_chain(SIGNED_CERTFILE)

        # check CERT_OPTIONAL
        server_context.verify_mode = ssl.CERT_OPTIONAL
        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'FALSE\n')
                s.send(b'PHA')
                self.assertEqual(s.recv(256), b'OK\n')
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'TRUE\n')

    def test_pha_optional_nocert(self):
        if support.verbose:
            sys.stdout.write("\n")

        client_context, server_context, hostname = testing_context()
        server_context.post_handshake_auth = True
        server_context.verify_mode = ssl.CERT_OPTIONAL
        client_context.post_handshake_auth = True

        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'FALSE\n')
                s.send(b'PHA')
                self.assertEqual(s.recv(256), b'OK\n')
                # optional doesn't fail when client does not have a cert
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'FALSE\n')

    def test_pha_no_pha_client(self):
        client_context, server_context, hostname = testing_context()
        server_context.post_handshake_auth = True
        server_context.verify_mode = ssl.CERT_REQUIRED
        client_context.load_cert_chain(SIGNED_CERTFILE)

        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                with self.assertRaisesRegex(ssl.SSLError, 'not server'):
                    s.verify_client_post_handshake()
                s.send(b'PHA')
                self.assertIn(b'extension not received', s.recv(256))

    def test_pha_no_pha_server(self):
        # server doesn't have PHA enabled, cert is requested in handshake
        client_context, server_context, hostname = testing_context()
        server_context.verify_mode = ssl.CERT_REQUIRED
        client_context.post_handshake_auth = True
        client_context.load_cert_chain(SIGNED_CERTFILE)

        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'TRUE\n')
                # PHA doesn't fail if there is already a cert
                s.send(b'PHA')
                self.assertEqual(s.recv(256), b'OK\n')
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'TRUE\n')

    def test_pha_not_tls13(self):
        # TLS 1.2
        client_context, server_context, hostname = testing_context()
        server_context.verify_mode = ssl.CERT_REQUIRED
        client_context.maximum_version = ssl.TLSVersion.TLSv1_2
        client_context.post_handshake_auth = True
        client_context.load_cert_chain(SIGNED_CERTFILE)

        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                # PHA fails for TLS != 1.3
                s.send(b'PHA')
                self.assertIn(b'WRONG_SSL_VERSION', s.recv(256))

    def test_bpo37428_pha_cert_none(self):
        # verify that post_handshake_auth does not implicitly enable cert
        # validation.
        hostname = SIGNED_CERTFILE_HOSTNAME
        client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_context.post_handshake_auth = True
        client_context.load_cert_chain(SIGNED_CERTFILE)
        # no cert validation and CA on client side
        client_context.check_hostname = False
        client_context.verify_mode = ssl.CERT_NONE

        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(SIGNED_CERTFILE)
        server_context.load_verify_locations(SIGNING_CA)
        server_context.post_handshake_auth = True
        server_context.verify_mode = ssl.CERT_REQUIRED

        server = ThreadedEchoServer(context=server_context, chatty=False)
        with server:
            with client_context.wrap_socket(socket.socket(),
                                            server_hostname=hostname) as s:
                s.connect((HOST, server.port))
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'FALSE\n')
                s.send(b'PHA')
                self.assertEqual(s.recv(256), b'OK\n')
                s.send(b'HASCERT')
                self.assertEqual(s.recv(256), b'TRUE\n')
                # server cert has not been validated
                self.assertEqual(s.getpeercert(), {})


def setUpModule():
    if support.verbose:
        plat = repr(platform.platform())
        print("test_ssl: testing with %r %r" %
            (ssl.OPENSSL_VERSION, ssl.OPENSSL_VERSION_INFO))
        print("          under %s" % plat)
        print("          HAS_SNI = %r" % ssl.HAS_SNI)
        print("          OP_ALL = 0x%8x" % ssl.OP_ALL)

    for filename in [
        CERTFILE, BYTES_CERTFILE,
        ONLYCERT, ONLYKEY, BYTES_ONLYCERT, BYTES_ONLYKEY,
        SIGNED_CERTFILE, SIGNED_CERTFILE2, SIGNING_CA,
        BADCERT, BADKEY, EMPTYCERT]:
        if not os.path.exists(filename):
            raise support.TestFailed("Can't read certificate file %r" % filename)

    global _thread_info
    _thread_info = support.threading_setup()

def tearDownModule():
    support.threading_cleanup(*_thread_info)

if __name__ == "__main__":
    unittest.main()