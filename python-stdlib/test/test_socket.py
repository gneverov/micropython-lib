import unittest
from test import support

import errno
import io
import itertools
import socket
import select
import tempfile
import time
import queue
import sys
import os
import array
import contextlib
try:
    from weakref import proxy
except ImportError:
    pass
import signal
import math
import random
import shutil
import _thread as thread
import threading
try:
    import fcntl
except ImportError:
    fcntl = None

HOST = support.HOST
MSG = 'Michael Gilfix was here\u1234\r\n'.encode('utf-8') ## test unicode string and carriage return
MAIN_TIMEOUT = 60.0


def _is_fd_in_blocking_mode(sock):
    return not bool(
        fcntl.fcntl(sock, fcntl.F_GETFL, os.O_NONBLOCK) & os.O_NONBLOCK)


class SocketTCPTest(unittest.TestCase):

    def setUp(self):
        self.serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = support.bind_port(self.serv)
        self.serv.listen()

    def tearDown(self):
        self.serv.close()
        self.serv = None

class SocketUDPTest(unittest.TestCase):

    def setUp(self):
        self.serv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.port = support.bind_port(self.serv)

    def tearDown(self):
        self.serv.close()
        self.serv = None

class ThreadSafeCleanupTestCase(unittest.TestCase):
    """Subclass of unittest.TestCase with thread-safe cleanup methods.

    This subclass protects the addCleanup() and doCleanups() methods
    with a recursive lock.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cleanup_lock = threading.RLock()

    def addCleanup(self, *args, **kwargs):
        with self._cleanup_lock:
            return super().addCleanup(*args, **kwargs)

    def doCleanups(self, *args, **kwargs):
        with self._cleanup_lock:
            return super().doCleanups(*args, **kwargs)

class ThreadableTest:
    """Threadable Test class

    The ThreadableTest class makes it easy to create a threaded
    client/server pair from an existing unit test. To create a
    new threaded class from an existing unit test, use multiple
    inheritance:

        class NewClass (OldClass, ThreadableTest):
            pass

    This class defines two new fixture functions with obvious
    purposes for overriding:

        clientSetUp ()
        clientTearDown ()

    Any new test functions within the class must then define
    tests in pairs, where the test name is preceded with a
    '_' to indicate the client portion of the test. Ex:

        def testFoo(self):
            # Server portion

        def _testFoo(self):
            # Client portion

    Any exceptions raised by the clients during their tests
    are caught and transferred to the main thread to alert
    the testing framework.

    Note, the server setup function cannot call any blocking
    functions that rely on the client thread during setup,
    unless serverExplicitReady() is called just before
    the blocking call (such as in setting up a client/server
    connection and performing the accept() in setUp().
    """

    def __init__(self):
        # Swap the true setup function
        self.__setUp = self.setUp
        self.__tearDown = self.tearDown
        self.setUp = self._setUp
        self.tearDown = self._tearDown

    def serverExplicitReady(self):
        """This method allows the server to explicitly indicate that
        it wants the client thread to proceed. This is useful if the
        server is about to execute a blocking routine that is
        dependent upon the client thread during its setup routine."""
        self.server_ready.set()

    def _setUp(self):
        self.wait_threads = support.wait_threads_exit()
        self.wait_threads.__enter__()

        self.server_ready = threading.Event()
        self.client_ready = threading.Event()
        self.done = threading.Event()
        self.queue = queue.Queue(1)
        self.server_crashed = False

        # Do some munging to start the client test.
        methodname = self.id()
        i = methodname.rfind('.')
        methodname = methodname[i+1:]
        test_method = getattr(self, '_' + methodname)
        self.client_thread = thread.start_new_thread(
            self.clientRun, (test_method,))

        try:
            self.__setUp()
        except:
            self.server_crashed = True
            raise
        finally:
            self.server_ready.set()
        self.client_ready.wait()

    def _tearDown(self):
        self.__tearDown()
        self.done.wait()
        self.wait_threads.__exit__(None, None, None)

        if self.queue.qsize():
            exc = self.queue.get()
            raise exc

    def clientRun(self, test_func):
        self.server_ready.wait()
        try:
            self.clientSetUp()
        except BaseException as e:
            self.queue.put(e)
            self.clientTearDown()
            return
        finally:
            self.client_ready.set()
        if self.server_crashed:
            self.clientTearDown()
            return
        if not callable(test_func):
            raise TypeError("test_func must be a callable function")
        try:
            test_func()
        except BaseException as e:
            self.queue.put(e)
        finally:
            self.clientTearDown()

    def clientSetUp(self):
        raise NotImplementedError("clientSetUp must be implemented.")

    def clientTearDown(self):
        self.done.set()
        thread.exit()

class ThreadedTCPSocketTest(SocketTCPTest, ThreadableTest):

    def __init__(self, methodName='runTest'):
        SocketTCPTest.__init__(self, methodName=methodName)
        ThreadableTest.__init__(self)

    def clientSetUp(self):
        self.cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def clientTearDown(self):
        self.cli.close()
        self.cli = None
        ThreadableTest.clientTearDown(self)

class ThreadedUDPSocketTest(SocketUDPTest, ThreadableTest):

    def __init__(self, methodName='runTest'):
        SocketUDPTest.__init__(self, methodName=methodName)
        ThreadableTest.__init__(self)

    def clientSetUp(self):
        self.cli = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def clientTearDown(self):
        self.cli.close()
        self.cli = None
        ThreadableTest.clientTearDown(self)

class SocketConnectedTest(ThreadedTCPSocketTest):
    """Socket tests for client-server connection.

    self.cli_conn is a client socket connected to the server.  The
    setUp() method guarantees that it is connected to the server.
    """

    def __init__(self, methodName='runTest'):
        ThreadedTCPSocketTest.__init__(self, methodName=methodName)

    def setUp(self):
        ThreadedTCPSocketTest.setUp(self)
        # Indicate explicitly we're ready for the client thread to
        # proceed and then perform the blocking call to accept
        self.serverExplicitReady()
        conn, addr = self.serv.accept()
        self.cli_conn = conn

    def tearDown(self):
        self.cli_conn.close()
        self.cli_conn = None
        ThreadedTCPSocketTest.tearDown(self)

    def clientSetUp(self):
        ThreadedTCPSocketTest.clientSetUp(self)
        self.cli.connect((HOST, self.port))
        self.serv_conn = self.cli

    def clientTearDown(self):
        if hasattr(self, 'serv_conn'):
            self.serv_conn.close()
            self.serv_conn = None
        ThreadedTCPSocketTest.clientTearDown(self)

class SocketPairTest(unittest.TestCase, ThreadableTest):

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName=methodName)
        ThreadableTest.__init__(self)

    def setUp(self):
        self.serv, self.cli = socket.socketpair()

    def tearDown(self):
        self.serv.close()
        self.serv = None

    def clientSetUp(self):
        pass

    def clientTearDown(self):
        self.cli.close()
        self.cli = None
        ThreadableTest.clientTearDown(self)


# The following classes are used by the sendmsg()/recvmsg() tests.
# Combining, for instance, ConnectedStreamTestMixin and TCPTestBase
# gives a drop-in replacement for SocketConnectedTest, but different
# address families can be used, and the attributes serv_addr and
# cli_addr will be set to the addresses of the endpoints.

class SocketTestBase(unittest.TestCase):
    """A base class for socket tests.

    Subclasses must provide methods newSocket() to return a new socket
    and bindSock(sock) to bind it to an unused address.

    Creates a socket self.serv and sets self.serv_addr to its address.
    """

    def setUp(self):
        self.serv = self.newSocket()
        self.bindServer()

    def bindServer(self):
        """Bind server socket and set self.serv_addr to its address."""
        self.bindSock(self.serv)
        self.serv_addr = self.serv.getsockname()

    def tearDown(self):
        self.serv.close()
        self.serv = None


class SocketListeningTestMixin(SocketTestBase):
    """Mixin to listen on the server socket."""

    def setUp(self):
        super().setUp()
        self.serv.listen()


class ThreadedSocketTestMixin(ThreadSafeCleanupTestCase, SocketTestBase,
                              ThreadableTest):
    """Mixin to add client socket and allow client/server tests.

    Client socket is self.cli and its address is self.cli_addr.  See
    ThreadableTest for usage information.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ThreadableTest.__init__(self)

    def clientSetUp(self):
        self.cli = self.newClientSocket()
        self.bindClient()

    def newClientSocket(self):
        """Return a new socket for use as client."""
        return self.newSocket()

    def bindClient(self):
        """Bind client socket and set self.cli_addr to its address."""
        self.bindSock(self.cli)
        self.cli_addr = self.cli.getsockname()

    def clientTearDown(self):
        self.cli.close()
        self.cli = None
        ThreadableTest.clientTearDown(self)


class ConnectedStreamTestMixin(SocketListeningTestMixin,
                               ThreadedSocketTestMixin):
    """Mixin to allow client/server stream tests with connected client.

    Server's socket representing connection to client is self.cli_conn
    and client's connection to server is self.serv_conn.  (Based on
    SocketConnectedTest.)
    """

    def setUp(self):
        super().setUp()
        # Indicate explicitly we're ready for the client thread to
        # proceed and then perform the blocking call to accept
        self.serverExplicitReady()
        conn, addr = self.serv.accept()
        self.cli_conn = conn

    def tearDown(self):
        self.cli_conn.close()
        self.cli_conn = None
        super().tearDown()

    def clientSetUp(self):
        super().clientSetUp()
        self.cli.connect(self.serv_addr)
        self.serv_conn = self.cli

    def clientTearDown(self):
        try:
            self.serv_conn.close()
            self.serv_conn = None
        except AttributeError:
            pass
        super().clientTearDown()


class UnixSocketTestBase(SocketTestBase):
    """Base class for Unix-domain socket tests."""

    # This class is used for file descriptor passing tests, so we
    # create the sockets in a private directory so that other users
    # can't send anything that might be problematic for a privileged
    # user running the tests.

    def setUp(self):
        self.dir_path = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, self.dir_path)
        super().setUp()

    def bindSock(self, sock):
        path = tempfile.mktemp(dir=self.dir_path)
        support.bind_unix_socket(sock, path)
        self.addCleanup(support.unlink, path)

class UnixStreamBase(UnixSocketTestBase):
    """Base class for Unix-domain SOCK_STREAM tests."""

    def newSocket(self):
        return socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)


class InetTestBase(SocketTestBase):
    """Base class for IPv4 socket tests."""

    host = HOST

    def setUp(self):
        super().setUp()
        self.port = self.serv_addr[1]

    def bindSock(self, sock):
        support.bind_port(sock, host=self.host)

class TCPTestBase(InetTestBase):
    """Base class for TCP-over-IPv4 tests."""

    def newSocket(self):
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)

class UDPTestBase(InetTestBase):
    """Base class for UDP-over-IPv4 tests."""

    def newSocket(self):
        return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

class SCTPStreamBase(InetTestBase):
    """Base class for SCTP tests in one-to-one (SOCK_STREAM) mode."""

    def newSocket(self):
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM,
                             socket.IPPROTO_SCTP)


class Inet6TestBase(InetTestBase):
    """Base class for IPv6 socket tests."""

    host = support.HOSTv6

class UDP6TestBase(Inet6TestBase):
    """Base class for UDP-over-IPv6 tests."""

    def newSocket(self):
        return socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)


# Test-skipping decorators for use with ThreadableTest.

class wrap_callable:
    def __init__(self, f):
        self.f = f

    def __call__(self, *args, **kwargs):
        return self.f(*args, **kwargs)

def skipWithClientIf(condition, reason):
    """Skip decorated test if condition is true, add client_skip decorator.

    If the decorated object is not a class, sets its attribute
    "client_skip" to a decorator which will return an empty function
    if the test is to be skipped, or the original function if it is
    not.  This can be used to avoid running the client part of a
    skipped test when using ThreadableTest.
    """
    def client_pass(*args, **kwargs):
        pass
    def skipdec(obj):
        retval = unittest.skip(reason)(obj)
        if not isinstance(obj, type):
            retval = wrap_callable(retval)
            retval.client_skip = lambda f: client_pass
        return retval
    def noskipdec(obj):
        if not (isinstance(obj, type) or hasattr(obj, "client_skip")):
            obj = wrap_callable(obj)
            obj.client_skip = lambda f: f
        return obj
    return skipdec if condition else noskipdec


def requireAttrs(obj, *attributes):
    """Skip decorated test if obj is missing any of the given attributes.

    Sets client_skip attribute as skipWithClientIf() does.
    """
    missing = [name for name in attributes if not hasattr(obj, name)]
    return skipWithClientIf(
        missing, "don't have " + ", ".join(name for name in missing))


def requireSocket(*args):
    """Skip decorated test if a socket cannot be created with given arguments.

    When an argument is given as a string, will use the value of that
    attribute of the socket module, or skip the test if it doesn't
    exist.  Sets client_skip attribute as skipWithClientIf() does.
    """
    err = None
    missing = [obj for obj in args if
               isinstance(obj, str) and not hasattr(socket, obj)]
    if missing:
        err = "don't have " + ", ".join(name for name in missing)
    else:
        callargs = [getattr(socket, obj) if isinstance(obj, str) else obj
                    for obj in args]
        try:
            s = socket.socket(*callargs)
        except OSError as e:
            # XXX: check errno?
            err = str(e)
        else:
            s.close()
    return skipWithClientIf(
        err is not None,
        "can't create socket({0}): {1}".format(
            ", ".join(str(o) for o in args), err))

skipWithClientIfMicropython = skipWithClientIf(support.is_micropython, 'does not work on MicroPython')

#######################################################################
## Begin Tests

class GeneralModuleTests(unittest.TestCase):

    def test_SocketType_is_socketobject(self):
        s = socket.socket()
        self.assertIsInstance(s, socket.SocketType)
        s.close()

    def test_repr(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with s:
            self.assertIn('fd=%i' % s.fileno(), repr(s))
            self.assertIn('family=%s' % socket.AF_INET, repr(s))
            self.assertIn('type=%s' % socket.SOCK_STREAM, repr(s))
            self.assertIn('proto=0', repr(s))
            self.assertNotIn('raddr', repr(s))
            s.bind(('127.0.0.1', 0))
            self.assertIn('laddr', repr(s))
            self.assertIn(str(s.getsockname()), repr(s))
        self.assertIn('[closed]', repr(s))
        self.assertNotIn('laddr', repr(s))

    @support.requires_weakref
    def test_weakref(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        p = proxy(s)
        self.assertEqual(p.fileno(), s.fileno())
        s.close()
        s = None
        try:
            p.fileno()
        except ReferenceError:
            pass
        else:
            self.fail('Socket proxy still exists')

    def testSocketError(self):
        # Testing socket module exceptions
        msg = "Error raising socket exception (%s)."
        with self.assertRaises(OSError, msg=msg % 'OSError'):
            raise OSError
        # with self.assertRaises(OSError, msg=msg % 'socket.herror'):
        #     raise socket.herror
        with self.assertRaises(OSError, msg=msg % 'socket.gaierror'):
            raise socket.gaierror

    def testSendtoErrors(self):
        # Testing that sendto doesn't mask failures. See #10169.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(s.close)
        s.bind(('', 0))
        sockname = s.getsockname()
        # 2 args
        with self.assertRaises(TypeError) as cm:
            s.sendto('\u2620', sockname)
        self.assertEqual(str(cm.exception),
                         "a bytes-like object is required, not 'str'")
        with self.assertRaises(TypeError) as cm:
            s.sendto(5j, sockname)
        self.assertEqual(str(cm.exception),
                         "a bytes-like object is required, not 'complex'")
        with self.assertRaises(TypeError) as cm:
            s.sendto(b'foo', None)
        # self.assertIn('not NoneType',str(cm.exception))
        # 3 args
        with self.assertRaises(TypeError) as cm:
            s.sendto('\u2620', 0, sockname)
        self.assertEqual(str(cm.exception),
                         "a bytes-like object is required, not 'str'")
        with self.assertRaises(TypeError) as cm:
            s.sendto(5j, 0, sockname)
        self.assertEqual(str(cm.exception),
                         "a bytes-like object is required, not 'complex'")
        with self.assertRaises(TypeError) as cm:
            s.sendto(b'foo', 0, None)
        # self.assertIn('not NoneType', str(cm.exception))
        with self.assertRaises(TypeError) as cm:
            s.sendto(b'foo', 'bar', sockname)
        # self.assertIn('an integer is required', str(cm.exception))
        with self.assertRaises(TypeError) as cm:
            s.sendto(b'foo', None, None)
        # self.assertIn('an integer is required', str(cm.exception))
        # wrong number of args
        with self.assertRaises(TypeError) as cm:
            s.sendto(b'foo')
        # self.assertIn('(1 given)', str(cm.exception))
        with self.assertRaises(TypeError) as cm:
            s.sendto(b'foo', 0, sockname, 4)
        # self.assertIn('(4 given)', str(cm.exception))

    def testCrucialConstants(self):
        # Testing for mission critical constants
        socket.AF_INET
        socket.SOCK_STREAM
        socket.SOCK_DGRAM
        socket.SOCK_RAW
        # socket.SOCK_RDM
        # socket.SOCK_SEQPACKET
        socket.SOL_SOCKET
        socket.SO_REUSEADDR

    @unittest.skip("requires dns server")
    def testHostnameRes(self):
        # Testing hostname resolution mechanisms
        hostname = socket.gethostname()
        try:
            ip = socket.gethostbyname(hostname)
        except OSError:
            # Probably name lookup wasn't set up right; skip this test
            self.skipTest('name lookup failure')
        self.assertTrue(ip.find('.') >= 0, "Error resolving host to ip.")
        try:
            hname, aliases, ipaddrs = socket.gethostbyaddr(ip)
        except OSError:
            # Probably a similar problem as above; skip this test
            self.skipTest('name lookup failure')
        all_host_names = [hostname, hname] + aliases
        fqhn = socket.getfqdn(ip)
        if not fqhn in all_host_names:
            self.fail("Error testing host resolution mechanisms. (fqdn: %s, all: %s)" % (fqhn, repr(all_host_names)))

    def test_host_resolution(self):
        for addr in [support.HOSTv4, '10.0.0.1', '255.255.255.255']:
            self.assertEqual(socket.gethostbyname(addr), addr)

        # we don't test support.HOSTv6 because there's a chance it doesn't have
        # a matching name entry (e.g. 'ip6-localhost')
        for host in [support.HOSTv4]:
            self.assertIn(host, socket.gethostbyaddr(host)[2])

    @unittest.skipUnless(hasattr(socket, 'sethostname'), "test needs socket.sethostname()")
    @unittest.skipUnless(hasattr(socket, 'gethostname'), "test needs socket.gethostname()")
    def test_sethostname(self):
        oldhn = socket.gethostname()
        try:
            socket.sethostname('new')
        except OSError as e:
            if e.errno == errno.EPERM:
                self.skipTest("test should be run as root")
            else:
                raise
        try:
            # running test as root!
            self.assertEqual(socket.gethostname(), 'new')
            # Should work with bytes objects too
            socket.sethostname(b'bar')
            self.assertEqual(socket.gethostname(), 'bar')
        finally:
            socket.sethostname(oldhn)

    @unittest.skipUnless(hasattr(socket, 'if_nameindex'),
                         'socket.if_nameindex() not available.')
    def testInterfaceNameIndex(self):
        interfaces = socket.if_nameindex()
        for index, name in interfaces:
            self.assertIsInstance(index, int)
            self.assertIsInstance(name, str)
            # interface indices are non-zero integers
            self.assertGreater(index, 0)
            _index = socket.if_nametoindex(name)
            self.assertIsInstance(_index, int)
            self.assertEqual(index, _index)
            _name = socket.if_indextoname(index)
            self.assertIsInstance(_name, str)
            self.assertEqual(name, _name)

    @unittest.skipUnless(hasattr(socket, 'if_nameindex'),
                         'socket.if_nameindex() not available.')
    def testInvalidInterfaceNameIndex(self):
        # test nonexistent interface index/name
        self.assertRaises(OSError, socket.if_indextoname, 0)
        self.assertRaises(OSError, socket.if_nametoindex, '_DEADBEEF')
        # test with invalid values
        self.assertRaises(TypeError, socket.if_nametoindex, 0)
        self.assertRaises(TypeError, socket.if_indextoname, '_DEADBEEF')

    def testInterpreterCrash(self):
        # Making sure getnameinfo doesn't crash the interpreter
        try:
            # On some versions, this crashes the interpreter.
            socket.getnameinfo(('x', 0, 0, 0), 0)
        except OSError:
            pass

    def testNtoH(self):
        # This just checks that htons etc. are their own inverse,
        # when looking at the lower 16 or 32 bits.
        sizes = {socket.htonl: 32, socket.ntohl: 32,
                 socket.htons: 16, socket.ntohs: 16}
        for func, size in sizes.items():
            mask = (1<<size) - 1
            for i in (0, 1, 0xffff, ~0xffff, 2, 0x01234567, 0x76543210):
                self.assertEqual(i & mask, func(func(i&mask)) & mask)

            swapped = func(mask)
            self.assertEqual(swapped & mask, mask)
            self.assertRaises(OverflowError, func, 1<<34)

    @unittest.skipUnless(hasattr(socket, 'getservbyname'), 'test needs socket.getservbyname()')
    @unittest.skipUnless(hasattr(socket, 'getservbyport'), 'test needs socket.getservbyport()')
    def testGetServBy(self):
        eq = self.assertEqual
        # Find one service that exists, then check all the related interfaces.
        # I've ordered this by protocols that have both a tcp and udp
        # protocol, at least for modern Linuxes.
        services = ('echo', 'daytime', 'domain')
        for service in services:
            try:
                port = socket.getservbyname(service, 'tcp')
                break
            except OSError:
                pass
        else:
            raise OSError
        # Try same call with optional protocol omitted
        port2 = socket.getservbyname(service)
        eq(port, port2)
        # Try udp, but don't barf if it doesn't exist
        try:
            udpport = socket.getservbyname(service, 'udp')
        except OSError:
            udpport = None
        else:
            eq(udpport, port)
        # Now make sure the lookup by port returns the same service name
        eq(socket.getservbyport(port2), service)
        eq(socket.getservbyport(port, 'tcp'), service)
        if udpport is not None:
            eq(socket.getservbyport(udpport, 'udp'), service)
        # Make sure getservbyport does not accept out of range ports.
        self.assertRaises(OverflowError, socket.getservbyport, -1)
        self.assertRaises(OverflowError, socket.getservbyport, 65536)

    def testDefaultTimeout(self):
        # Testing default timeout
        # The default timeout should initially be None
        self.assertEqual(socket.getdefaulttimeout(), None)
        s = socket.socket()
        self.assertEqual(s.gettimeout(), None)
        s.close()

        # Set the default timeout to 10, and see if it propagates
        socket.setdefaulttimeout(10)
        self.assertEqual(socket.getdefaulttimeout(), 10)
        s = socket.socket()
        self.assertEqual(s.gettimeout(), 10)
        s.close()

        # Reset the default timeout to None, and see if it propagates
        socket.setdefaulttimeout(None)
        self.assertEqual(socket.getdefaulttimeout(), None)
        s = socket.socket()
        self.assertEqual(s.gettimeout(), None)
        s.close()

        # Check that setting it to an invalid value raises ValueError
        self.assertRaises(ValueError, socket.setdefaulttimeout, -1)

        # Check that setting it to an invalid type raises TypeError
        self.assertRaises(TypeError, socket.setdefaulttimeout, "spam")

    @unittest.skipUnless(hasattr(socket, 'inet_aton'),
                         'test needs socket.inet_aton()')
    def testIPv4_inet_aton_fourbytes(self):
        # Test that issue1008086 and issue767150 are fixed.
        # It must return 4 bytes.
        self.assertEqual(b'\x00'*4, socket.inet_aton('0.0.0.0'))
        self.assertEqual(b'\xff'*4, socket.inet_aton('255.255.255.255'))

    @unittest.skipUnless(hasattr(socket, 'inet_pton'),
                         'test needs socket.inet_pton()')
    def testIPv4toString(self):
        from socket import inet_aton as f, inet_pton, AF_INET
        g = lambda a: inet_pton(AF_INET, a)

        assertInvalid = lambda func,a: self.assertRaises(
            (OSError, ValueError), func, a
        )

        self.assertEqual(b'\x00\x00\x00\x00', f('0.0.0.0'))
        self.assertEqual(b'\xff\x00\xff\x00', f('255.0.255.0'))
        self.assertEqual(b'\xaa\xaa\xaa\xaa', f('170.170.170.170'))
        self.assertEqual(b'\x01\x02\x03\x04', f('1.2.3.4'))
        self.assertEqual(b'\xff\xff\xff\xff', f('255.255.255.255'))
        # bpo-29972: inet_pton() doesn't fail on AIX
        if not sys.platform.startswith('aix'):
            assertInvalid(f, '0.0.0.')
        assertInvalid(f, '300.0.0.0')
        assertInvalid(f, 'a.0.0.0')
        assertInvalid(f, '1.2.3.4.5')
        assertInvalid(f, '::1')

        self.assertEqual(b'\x00\x00\x00\x00', g('0.0.0.0'))
        self.assertEqual(b'\xff\x00\xff\x00', g('255.0.255.0'))
        self.assertEqual(b'\xaa\xaa\xaa\xaa', g('170.170.170.170'))
        self.assertEqual(b'\xff\xff\xff\xff', g('255.255.255.255'))
        assertInvalid(g, '0.0.0.')
        assertInvalid(g, '300.0.0.0')
        assertInvalid(g, 'a.0.0.0')
        assertInvalid(g, '1.2.3.4.5')
        assertInvalid(g, '::1')

    @unittest.skipUnless(hasattr(socket, 'inet_pton'),
                         'test needs socket.inet_pton()')
    def testIPv6toString(self):
        try:
            from socket import inet_pton, AF_INET6, has_ipv6
            if not has_ipv6:
                self.skipTest('IPv6 not available')
        except ImportError:
            self.skipTest('could not import needed symbols from socket')

        f = lambda a: inet_pton(AF_INET6, a)
        assertInvalid = lambda a: self.assertRaises(
            (OSError, ValueError), f, a
        )

        self.assertEqual(b'\x00' * 16, f('::'))
        self.assertEqual(b'\x00' * 16, f('0::0'))
        self.assertEqual(b'\x00\x01' + b'\x00' * 14, f('1::'))
        self.assertEqual(
            b'\x45\xef\x76\xcb\x00\x1a\x56\xef\xaf\xeb\x0b\xac\x19\x24\xae\xae',
            f('45ef:76cb:1a:56ef:afeb:bac:1924:aeae')
        )
        self.assertEqual(
            b'\xad\x42\x0a\xbc' + b'\x00' * 4 + b'\x01\x27\x00\x00\x02\x54\x00\x02',
            f('ad42:abc::127:0:254:2')
        )
        self.assertEqual(b'\x00\x12\x00\x0a' + b'\x00' * 12, f('12:a::'))
        assertInvalid('0x20::')
        assertInvalid(':::')
        assertInvalid('::0::')
        assertInvalid('1::abc::')
        assertInvalid('1::abc::def')
        assertInvalid('1:2:3:4:5:6')
        assertInvalid('1:2:3:4:5:6:7:8:0')
        assertInvalid('1:2:3:4:5:6:')
        assertInvalid('1:2:3:4:5:6:7:8:')

        # The following tests are disabled because of bug in lwip?
        # self.assertEqual(b'\x00' * 12 + b'\xfe\x2a\x17\x40',
        #     f('::254.42.23.64')
        # )
        # self.assertEqual(
        #     b'\x00\x42' + b'\x00' * 8 + b'\xa2\x9b\xfe\x2a\x17\x40',
        #     f('42::a29b:254.42.23.64')
        # )
        self.assertEqual(
            b'\x00\x42\xa8\xb9\x00\x00\x00\x02\xff\xff\xa2\x9b\xfe\x2a\x17\x40',
            f('42:a8b9:0:2:ffff:a29b:254.42.23.64')
        )
        assertInvalid('255.254.253.252')
        assertInvalid('1::260.2.3.0')
        assertInvalid('1::0.be.e.0')
        assertInvalid('1:2:3:4:5:6:7:1.2.3.4')
        assertInvalid('::1.2.3.4:0')
        assertInvalid('0.100.200.0:3:4:5:6:7:8')

    @unittest.skipUnless(hasattr(socket, 'inet_ntop'),
                         'test needs socket.inet_ntop()')
    def testStringToIPv4(self):
        from socket import inet_ntoa as f, inet_ntop, AF_INET
        g = lambda a: inet_ntop(AF_INET, a)
        assertInvalid = lambda func,a: self.assertRaises(
            (OSError, ValueError), func, a
        )

        self.assertEqual('1.0.1.0', f(b'\x01\x00\x01\x00'))
        self.assertEqual('170.85.170.85', f(b'\xaa\x55\xaa\x55'))
        self.assertEqual('255.255.255.255', f(b'\xff\xff\xff\xff'))
        self.assertEqual('1.2.3.4', f(b'\x01\x02\x03\x04'))
        assertInvalid(f, b'\x00' * 3)
        assertInvalid(f, b'\x00' * 5)
        assertInvalid(f, b'\x00' * 16)
        self.assertEqual('170.85.170.85', f(bytearray(b'\xaa\x55\xaa\x55')))

        self.assertEqual('1.0.1.0', g(b'\x01\x00\x01\x00'))
        self.assertEqual('170.85.170.85', g(b'\xaa\x55\xaa\x55'))
        self.assertEqual('255.255.255.255', g(b'\xff\xff\xff\xff'))
        assertInvalid(g, b'\x00' * 3)
        assertInvalid(g, b'\x00' * 5)
        assertInvalid(g, b'\x00' * 16)
        self.assertEqual('170.85.170.85', g(bytearray(b'\xaa\x55\xaa\x55')))

    @unittest.skipUnless(hasattr(socket, 'inet_ntop'),
                         'test needs socket.inet_ntop()')
    def testStringToIPv6(self):
        try:
            from socket import inet_ntop, AF_INET6, has_ipv6
            if not has_ipv6:
                self.skipTest('IPv6 not available')
        except ImportError:
            self.skipTest('could not import needed symbols from socket')

        if sys.platform == "win32":
            try:
                inet_ntop(AF_INET6, b'\x00' * 16)
            except OSError as e:
                if e.winerror == 10022:
                    self.skipTest('IPv6 might not be supported')

        f = lambda a: inet_ntop(AF_INET6, a)
        assertInvalid = lambda a: self.assertRaises(
            (OSError, ValueError), f, a
        )

        self.assertEqual('::', f(b'\x00' * 16))
        self.assertEqual('::1', f(b'\x00' * 15 + b'\x01'))
        self.assertEqual(
            'aef:b01:506:1001:ffff:9997:55:170',
            f(b'\x0a\xef\x0b\x01\x05\x06\x10\x01\xff\xff\x99\x97\x00\x55\x01\x70')
        )
        self.assertEqual('::1', f(bytearray(b'\x00' * 15 + b'\x01')))

        assertInvalid(b'\x12' * 15)
        assertInvalid(b'\x12' * 17)
        assertInvalid(b'\x12' * 4)

    # XXX The following don't test module-level functionality...

    @unittest.skip("requires dns server")
    def testSockName(self):
        # Testing getsockname()
        port = support.find_unused_port()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        sock.bind(("0.0.0.0", port))
        name = sock.getsockname()
        # XXX(nnorwitz): http://tinyurl.com/os5jz seems to indicate
        # it reasonable to get the host's addr in addition to 0.0.0.0.
        # At least for eCos.  This is required for the S/390 to pass.
        try:
            my_ip_addr = socket.gethostbyname(socket.gethostname())
        except OSError:
            # Probably name lookup wasn't set up right; skip this test
            self.skipTest('name lookup failure')
        self.assertIn(name[0], ("0.0.0.0", my_ip_addr), '%s invalid' % name[0])
        self.assertEqual(name[1], port)

    def testGetSockOpt(self):
        # Testing getsockopt()
        # We know a socket should start without reuse==0
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        reuse = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
        self.assertFalse(reuse != 0, "initial mode is reuse")

    def testSetSockOpt(self):
        # Testing setsockopt()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reuse = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
        self.assertFalse(reuse == 0, "failed to set reuse mode")

    def testSendAfterClose(self):
        # testing send() after close() with timeout
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.close()
        self.assertRaises(OSError, sock.send, b"spam")

    def testCloseException(self):
        sock = socket.socket()
        sock.bind((support.HOSTv4, 0))
        socket.socket(fileno=sock.fileno()).close()
        try:
            sock.close()
        except OSError as err:
            # Winsock apparently raises ENOTSOCK
            self.assertIn(err.errno, (errno.EBADF, errno.ENOTSOCK))
        else:
            self.fail("close() should raise EBADF/ENOTSOCK")

    def testNewAttributes(self):
        # testing .family, .type and .protocol

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.assertEqual(sock.family, socket.AF_INET)
        if hasattr(socket, 'SOCK_CLOEXEC'):
            self.assertIn(sock.type,
                          (socket.SOCK_STREAM | socket.SOCK_CLOEXEC,
                           socket.SOCK_STREAM))
        else:
            self.assertEqual(sock.type, socket.SOCK_STREAM)
        self.assertEqual(sock.proto, 0)
        sock.close()

    def test_getsockaddrarg(self):
        sock = socket.socket()
        self.addCleanup(sock.close)
        port = support.find_unused_port()
        big_port = port + 65536
        neg_port = port - 65536
        self.assertRaises(OverflowError, sock.bind, (HOST, big_port))
        self.assertRaises(OverflowError, sock.bind, (HOST, neg_port))
        # Since find_unused_port() is inherently subject to race conditions, we
        # call it a couple times if necessary.
        for i in itertools.count():
            port = support.find_unused_port()
            try:
                sock.bind((HOST, port))
            except OSError as e:
                if e.errno != errno.EADDRINUSE or i == 5:
                    raise
            else:
                break

    def testGetaddrinfo(self):
        socket.getaddrinfo('localhost', 80)
        # len of every sequence is supposed to be == 5
        for info in socket.getaddrinfo(HOST, None):
            self.assertEqual(len(info), 5)
        # host can be a domain name, a string representation of an
        # IPv4/v6 address or None
        socket.getaddrinfo('localhost', 80)
        socket.getaddrinfo('127.0.0.1', 80)
        socket.getaddrinfo(None, 80)
        if support.IPV6_ENABLED:
            socket.getaddrinfo('::1', 80)
        # port can be a string service name such as "http", a numeric
        # port number or None
        # socket.getaddrinfo(HOST, "http")
        socket.getaddrinfo(HOST, 80)
        socket.getaddrinfo(HOST, None)
        # test family and socktype filters
        infos = socket.getaddrinfo(HOST, 80, socket.AF_INET, socket.SOCK_STREAM)
        for family, type, _, _, _ in infos:
            self.assertEqual(family, socket.AF_INET)
            # self.assertEqual(str(family), 'AddressFamily.AF_INET')
            self.assertEqual(type, socket.SOCK_STREAM)
            # self.assertEqual(str(type), 'SocketKind.SOCK_STREAM')
        infos = socket.getaddrinfo(HOST, None, 0, socket.SOCK_STREAM)
        for _, socktype, _, _, _ in infos:
            self.assertEqual(socktype, socket.SOCK_STREAM)
        # test proto and flags arguments
        socket.getaddrinfo(HOST, None, 0, 0, socket.IPPROTO_TCP)
        socket.getaddrinfo(HOST, None, 0, 0, 0, socket.AI_PASSIVE)
        # a server willing to support both IPv4 and IPv6 will
        # usually do this
        socket.getaddrinfo(None, 0, socket.AF_UNSPEC, socket.SOCK_STREAM, 0,
                           socket.AI_PASSIVE)
        # test keyword arguments
        a = socket.getaddrinfo(HOST, None)
        b = socket.getaddrinfo(host=HOST, port=None)
        self.assertEqual(a, b)
        a = socket.getaddrinfo(HOST, None, socket.AF_INET)
        b = socket.getaddrinfo(HOST, None, family=socket.AF_INET)
        self.assertEqual(a, b)
        a = socket.getaddrinfo(HOST, None, 0, socket.SOCK_STREAM)
        b = socket.getaddrinfo(HOST, None, type=socket.SOCK_STREAM)
        self.assertEqual(a, b)
        a = socket.getaddrinfo(HOST, None, 0, 0, socket.IPPROTO_TCP)
        b = socket.getaddrinfo(HOST, None, proto=socket.IPPROTO_TCP)
        self.assertEqual(a, b)
        a = socket.getaddrinfo(HOST, None, 0, 0, 0, socket.AI_PASSIVE)
        b = socket.getaddrinfo(HOST, None, flags=socket.AI_PASSIVE)
        self.assertEqual(a, b)
        a = socket.getaddrinfo(None, 0, socket.AF_UNSPEC, socket.SOCK_STREAM, 0,
                               socket.AI_PASSIVE)
        b = socket.getaddrinfo(host=None, port=0, family=socket.AF_UNSPEC,
                               type=socket.SOCK_STREAM, proto=0,
                               flags=socket.AI_PASSIVE)
        self.assertEqual(a, b)
        # Issue #6697.
        # self.assertRaises(UnicodeEncodeError, socket.getaddrinfo, 'localhost', '\uD800')

        # Issue 17269: test workaround for OS X platform bug segfault
        if hasattr(socket, 'AI_NUMERICSERV'):
            try:
                # The arguments here are undefined and the call may succeed
                # or fail.  All we care here is that it doesn't segfault.
                socket.getaddrinfo("localhost", None, 0, 0, 0,
                                   socket.AI_NUMERICSERV)
            except socket.gaierror:
                pass

    def test_getnameinfo(self):
        # only IP addresses are allowed
        self.assertRaises(OSError, socket.getnameinfo, ('mail.python.org',0), 0)

    @unittest.skip('idna not supported')
    @unittest.skipUnless(support.is_resource_enabled('network'),
                         'network is not enabled')
    def test_idna(self):
        # Check for internet access before running test
        # (issue #12804, issue #25138).
        with support.transient_internet('python.org'):
            socket.gethostbyname('python.org')

        # these should all be successful
        domain = 'испытание.pythontest.net'
        socket.gethostbyname(domain)
        socket.gethostbyname_ex(domain)
        socket.getaddrinfo(domain,0,socket.AF_UNSPEC,socket.SOCK_STREAM)
        # this may not work if the forward lookup chooses the IPv6 address, as that doesn't
        # have a reverse entry yet
        # socket.gethostbyaddr('испытание.python.org')

    def check_sendall_interrupted(self, with_timeout):
        # socketpair() is not strictly required, but it makes things easier.
        if not hasattr(signal, 'alarm') or not hasattr(socket, 'socketpair'):
            self.skipTest("signal.alarm and socket.socketpair required for this test")
        # Our signal handlers clobber the C errno by calling a math function
        # with an invalid domain value.
        def ok_handler(*args):
            self.assertRaises(ValueError, math.acosh, 0)
        def raising_handler(*args):
            self.assertRaises(ValueError, math.acosh, 0)
            1 // 0
        c, s = socket.socketpair()
        old_alarm = signal.signal(signal.SIGALRM, raising_handler)
        try:
            if with_timeout:
                # Just above the one second minimum for signal.alarm
                c.settimeout(1.5)
            with self.assertRaises(ZeroDivisionError):
                signal.alarm(1)
                c.sendall(b"x" * support.SOCK_MAX_SIZE)
            if with_timeout:
                signal.signal(signal.SIGALRM, ok_handler)
                signal.alarm(1)
                self.assertRaises(socket.timeout, c.sendall,
                                  b"x" * support.SOCK_MAX_SIZE)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_alarm)
            c.close()
            s.close()

    # def test_sendall_interrupted(self):
    #     self.check_sendall_interrupted(False)

    # def test_sendall_interrupted_with_timeout(self):
    #     self.check_sendall_interrupted(True)

    # def test_dealloc_warn(self):
    #     sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     r = repr(sock)
    #     with self.assertWarns(ResourceWarning) as cm:
    #         sock = None
    #         support.gc_collect()
    #     self.assertIn(r, str(cm.warning.args[0]))
    #     # An open socket file object gets dereferenced after the socket
    #     sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     f = sock.makefile('rb')
    #     r = repr(sock)
    #     sock = None
    #     support.gc_collect()
    #     with self.assertWarns(ResourceWarning):
    #         f = None
    #         support.gc_collect()

    def test_name_closed_socketio(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            fp = sock.makefile("rb")
            fp.close()
            # self.assertEqual(repr(fp), "<_io.BufferedReader name=-1>")

    def test_unusable_closed_socketio(self):
        with socket.socket() as sock:
            fp = sock.makefile("rb", buffering=0)
            self.assertTrue(fp.readable())
            self.assertFalse(fp.writable())
            self.assertFalse(fp.seekable())
            fp.close()
            self.assertRaises(ValueError, fp.readable)
            self.assertRaises(ValueError, fp.writable)
            self.assertRaises(ValueError, fp.seekable)

    def test_socket_close(self):
        sock = socket.socket()
        try:
            sock.bind((HOST, 0))
            socket.close(sock.fileno())
            with self.assertRaises(OSError):
                sock.listen(1)
        finally:
            with self.assertRaises(OSError):
                # sock.close() fails with EBADF
                sock.close()
        with self.assertRaises(TypeError):
            socket.close(None)
        with self.assertRaises(OSError):
            socket.close(-1)

    @support.skip_micropython
    def test_makefile_mode(self):
        for mode in 'r', 'rb', 'rw', 'w', 'wb':
            with self.subTest(mode=mode):
                with socket.socket() as sock:
                    with sock.makefile(mode) as fp:
                        self.assertEqual(fp.mode, mode)

    def test_makefile_invalid_mode(self):
        for mode in 'rt', 'x', '+', 'a':
            with self.subTest(mode=mode):
                with socket.socket() as sock:
                    with self.assertRaisesRegex(ValueError, 'invalid mode'):
                        sock.makefile(mode)

    def test_listen_backlog(self):
        for backlog in 0, -1:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
                srv.bind((HOST, 0))
                srv.listen(backlog)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.bind((HOST, 0))
            srv.listen()

    @unittest.skipUnless(support.IPV6_ENABLED, 'IPv6 required for this test.')
    def test_flowinfo(self):
        self.assertRaises(OverflowError, socket.getnameinfo,
                          (support.HOSTv6, 0, 0xffffffff), 0)
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            self.assertRaises(OverflowError, s.bind, (support.HOSTv6, 0, -10))

    @unittest.skipUnless(support.IPV6_ENABLED, 'IPv6 required for this test.')
    def test_getaddrinfo_ipv6_basic(self):
        ((*_, sockaddr),) = socket.getaddrinfo(
            'ff02::1de:c0:face:8D',  # Note capital letter `D`.
            1234, socket.AF_INET6,
            socket.SOCK_DGRAM,
            socket.IPPROTO_UDP
        )
        self.assertEqual(sockaddr, ('ff02::1de:c0:face:8d', 1234, 0, 0))

    @unittest.skipUnless(support.IPV6_ENABLED, 'IPv6 required for this test.')
    @unittest.skipUnless(
        hasattr(socket, 'if_nameindex'),
        'if_nameindex is not supported')
    def test_getaddrinfo_ipv6_scopeid_symbolic(self):
        # Just pick up any network interface (Linux, Mac OS X)
        (ifindex, test_interface) = socket.if_nameindex()[0]
        ((*_, sockaddr),) = socket.getaddrinfo(
            'ff02::1de:c0:face:8D%' + test_interface,
            1234, socket.AF_INET6,
            socket.SOCK_DGRAM,
            socket.IPPROTO_UDP
        )
        # Note missing interface name part in IPv6 address
        self.assertEqual(sockaddr, ('ff02::1de:c0:face:8d', 1234, 0, ifindex))

    @unittest.skipUnless(support.IPV6_ENABLED, 'IPv6 required for this test.')

    @unittest.skipUnless(support.IPV6_ENABLED, 'IPv6 required for this test.')
    @unittest.skipUnless(
        hasattr(socket, 'if_nameindex'),
        'if_nameindex is not supported')
    def test_getnameinfo_ipv6_scopeid_symbolic(self):
        # Just pick up any network interface.
        (ifindex, test_interface) = socket.if_nameindex()[0]
        sockaddr = ('ff02::1de:c0:face:8D', 1234, 0, ifindex)  # Note capital letter `D`.
        nameinfo = socket.getnameinfo(sockaddr, socket.NI_NUMERICHOST | socket.NI_NUMERICSERV)
        self.assertEqual(nameinfo, ('ff02::1de:c0:face:8d%' + test_interface, '1234'))

    @support.skip_micropython
    def test_str_for_enums(self):
        # Make sure that the AF_* and SOCK_* constants have enum-like string
        # reprs.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            self.assertEqual(str(s.family), 'AddressFamily.AF_INET')
            self.assertEqual(str(s.type), 'SocketKind.SOCK_STREAM')

    def test_socket_consistent_sock_type(self):
        SOCK_NONBLOCK = getattr(socket, 'SOCK_NONBLOCK', 0)
        SOCK_CLOEXEC = getattr(socket, 'SOCK_CLOEXEC', 0)
        sock_type = socket.SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC

        with socket.socket(socket.AF_INET, sock_type) as s:
            self.assertEqual(s.type, socket.SOCK_STREAM)
            s.settimeout(1)
            self.assertEqual(s.type, socket.SOCK_STREAM)
            s.settimeout(0)
            self.assertEqual(s.type, socket.SOCK_STREAM)
            s.setblocking(True)
            self.assertEqual(s.type, socket.SOCK_STREAM)
            s.setblocking(False)
            self.assertEqual(s.type, socket.SOCK_STREAM)

    @unittest.skipUnless(hasattr(socket, 'sendfile'),  'test needs socket.sendfile')
    def test__sendfile_use_sendfile(self):
        class File:
            def __init__(self, fd):
                self.fd = fd

            def fileno(self):
                return self.fd
        with socket.socket() as sock:
            fd = os.dup(0)
            os.close(fd)
            with self.assertRaises(Exception):
                sock.sendfile(File(fd))
            with self.assertRaises(OverflowError):
                sock.sendfile(File(2**1000))
            with self.assertRaises(TypeError):
                sock.sendfile(File(None))

    def _test_socket_fileno(self, s, family, stype):
        self.assertEqual(s.family, family)
        self.assertEqual(s.type, stype)

        fd = s.fileno()
        s2 = socket.socket(fileno=fd)
        self.addCleanup(s2.close)
        # detach old fd to avoid double close
        s.detach()
        self.assertEqual(s2.family, family)
        self.assertEqual(s2.type, stype)
        self.assertEqual(s2.fileno(), fd)

    def test_socket_fileno(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s.close)
        s.bind((support.HOST, 0))
        self._test_socket_fileno(s, socket.AF_INET, socket.SOCK_STREAM)

        if hasattr(socket, "SOCK_DGRAM"):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.addCleanup(s.close)
            s.bind((support.HOST, 0))
            self._test_socket_fileno(s, socket.AF_INET, socket.SOCK_DGRAM)

        if support.IPV6_ENABLED:
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            self.addCleanup(s.close)
            s.bind((support.HOSTv6, 0, 0, 0))
            self._test_socket_fileno(s, socket.AF_INET6, socket.SOCK_STREAM)

        if hasattr(socket, "AF_UNIX"):
            tmpdir = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, tmpdir)
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.addCleanup(s.close)
            s.bind(os.path.join(tmpdir, 'socket'))
            self._test_socket_fileno(s, socket.AF_UNIX, socket.SOCK_STREAM)


class BasicTCPTest(SocketConnectedTest):

    def __init__(self, methodName='runTest'):
        SocketConnectedTest.__init__(self, methodName=methodName)

    def testRecv(self):
        # Testing large receive over TCP
        msg = self.cli_conn.recv(1024)
        self.assertEqual(msg, MSG)

    def _testRecv(self):
        self.serv_conn.send(MSG)

    def testOverFlowRecv(self):
        # Testing receive in chunks over TCP
        seg1 = self.cli_conn.recv(len(MSG) - 3)
        seg2 = self.cli_conn.recv(1024)
        msg = seg1 + seg2
        self.assertEqual(msg, MSG)

    def _testOverFlowRecv(self):
        self.serv_conn.send(MSG)

    def testRecvFrom(self):
        # Testing large recvfrom() over TCP
        msg, addr = self.cli_conn.recvfrom(1024)
        self.assertEqual(msg, MSG)

    def _testRecvFrom(self):
        self.serv_conn.send(MSG)

    def testOverFlowRecvFrom(self):
        # Testing recvfrom() in chunks over TCP
        seg1, addr = self.cli_conn.recvfrom(len(MSG)-3)
        seg2, addr = self.cli_conn.recvfrom(1024)
        msg = seg1 + seg2
        self.assertEqual(msg, MSG)

    def _testOverFlowRecvFrom(self):
        self.serv_conn.send(MSG)

    def testSendAll(self):
        # Testing sendall() with a 2048 byte string over TCP
        msg = b''
        while 1:
            read = self.cli_conn.recv(512)
            if not read:
                break
            msg += read
        self.assertEqual(msg, b'f' * 1024)

    def _testSendAll(self):
        big_chunk = b'f' * 1024
        self.serv_conn.sendall(big_chunk)

    @unittest.skipUnless(hasattr(socket, 'fromfd'),  'test needs socket.fromfd')
    def testFromFd(self):
        # Testing fromfd()
        fd = self.cli_conn.fileno()
        sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        self.assertIsInstance(sock, socket.socket)
        msg = sock.recv(1024)
        self.assertEqual(msg, MSG)

    def _testFromFd(self):
        self.serv_conn.send(MSG)

    def testDup(self):
        # Testing dup()
        sock = self.cli_conn.dup()
        self.addCleanup(sock.close)
        msg = sock.recv(1024)
        self.assertEqual(msg, MSG)

    def _testDup(self):
        self.serv_conn.send(MSG)

    def testShutdown(self):
        # Testing shutdown()
        msg = self.cli_conn.recv(1024)
        self.assertEqual(msg, MSG)
        # wait for _testShutdown to finish: on OS X, when the server
        # closes the connection the client also becomes disconnected,
        # and the client's shutdown call will fail. (Issue #4397.)
        self.done.wait()

    def _testShutdown(self):
        self.serv_conn.send(MSG)
        self.serv_conn.shutdown(2)

    def testDetach(self):
        # Testing detach()
        fileno = self.cli_conn.fileno()
        f = self.cli_conn.detach()
        self.assertEqual(f, fileno)
        # cli_conn cannot be used anymore...
        self.assertTrue(self.cli_conn._closed)
        self.assertRaises(OSError, self.cli_conn.recv, 1024)
        self.cli_conn.close()
        # ...but we can create another socket using the (still open)
        # file descriptor
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, fileno=f)
        self.addCleanup(sock.close)
        msg = sock.recv(1024)
        self.assertEqual(msg, MSG)

    def _testDetach(self):
        self.serv_conn.send(MSG)


class BasicUDPTest(ThreadedUDPSocketTest):

    def __init__(self, methodName='runTest'):
        ThreadedUDPSocketTest.__init__(self, methodName=methodName)

    def testSendtoAndRecv(self):
        # Testing sendto() and Recv() over UDP
        msg = self.serv.recv(len(MSG))
        self.assertEqual(msg, MSG)

    def _testSendtoAndRecv(self):
        self.cli.sendto(MSG, 0, (HOST, self.port))

    def testRecvFrom(self):
        # Testing recvfrom() over UDP
        msg, addr = self.serv.recvfrom(len(MSG))
        self.assertEqual(msg, MSG)

    def _testRecvFrom(self):
        self.cli.sendto(MSG, 0, (HOST, self.port))

    def testRecvFromNegative(self):
        # Negative lengths passed to recvfrom should give ValueError.
        self.assertRaises(ValueError, self.serv.recvfrom, -1)

    def _testRecvFromNegative(self):
        self.cli.sendto(MSG, 0, (HOST, self.port))


# Test interrupting the interruptible send/receive methods with a
# signal when a timeout is set.  These tests avoid having multiple
# threads alive during the test so that the OS cannot deliver the
# signal to the wrong one.

class InterruptedTimeoutBase(unittest.TestCase):
    # Base class for interrupted send/receive tests.  Installs an
    # empty handler for SIGALRM and removes it on teardown, along with
    # any scheduled alarms.

    def setUp(self):
        super().setUp()
        orig_alrm_handler = signal.signal(signal.SIGALRM,
                                          lambda signum, frame: 1 / 0)
        self.addCleanup(signal.signal, signal.SIGALRM, orig_alrm_handler)

    # Timeout for socket operations
    timeout = 4.0

    # Provide setAlarm() method to schedule delivery of SIGALRM after
    # given number of seconds, or cancel it if zero, and an
    # appropriate time value to use.  Use setitimer() if available.
    if hasattr(signal, "setitimer"):
        alarm_time = 0.05

        def setAlarm(self, seconds):
            signal.setitimer(signal.ITIMER_REAL, seconds)
    else:
        # Old systems may deliver the alarm up to one second early
        alarm_time = 2

        def setAlarm(self, seconds):
            signal.alarm(seconds)


# Require siginterrupt() in order to ensure that system calls are
# interrupted by default.
@requireAttrs(signal, "siginterrupt")
@unittest.skipUnless(hasattr(signal, "alarm") or hasattr(signal, "setitimer"),
                     "Don't have signal.alarm or signal.setitimer")
class InterruptedRecvTimeoutTest(InterruptedTimeoutBase, UDPTestBase):
    # Test interrupting the recv*() methods with signals when a
    # timeout is set.

    def setUp(self):
        super().setUp()
        self.serv.settimeout(self.timeout)

    def checkInterruptedRecv(self, func, *args, **kwargs):
        # Check that func(*args, **kwargs) raises
        # errno of EINTR when interrupted by a signal.
        try:
            self.setAlarm(self.alarm_time)
            with self.assertRaises(ZeroDivisionError) as cm:
                func(*args, **kwargs)
        finally:
            self.setAlarm(0)

    def testInterruptedRecvTimeout(self):
        self.checkInterruptedRecv(self.serv.recv, 1024)

    def testInterruptedRecvIntoTimeout(self):
        self.checkInterruptedRecv(self.serv.recv_into, bytearray(1024))

    def testInterruptedRecvfromTimeout(self):
        self.checkInterruptedRecv(self.serv.recvfrom, 1024)

    def testInterruptedRecvfromIntoTimeout(self):
        self.checkInterruptedRecv(self.serv.recvfrom_into, bytearray(1024))

    @requireAttrs(socket.socket, "recvmsg")
    def testInterruptedRecvmsgTimeout(self):
        self.checkInterruptedRecv(self.serv.recvmsg, 1024)

    @requireAttrs(socket.socket, "recvmsg_into")
    def testInterruptedRecvmsgIntoTimeout(self):
        self.checkInterruptedRecv(self.serv.recvmsg_into, [bytearray(1024)])


# Require siginterrupt() in order to ensure that system calls are
# interrupted by default.
@requireAttrs(signal, "siginterrupt")
@unittest.skipUnless(hasattr(signal, "alarm") or hasattr(signal, "setitimer"),
                     "Don't have signal.alarm or signal.setitimer")
class InterruptedSendTimeoutTest(InterruptedTimeoutBase,
                                 ThreadSafeCleanupTestCase,
                                 SocketListeningTestMixin, TCPTestBase):
    # Test interrupting the interruptible send*() methods with signals
    # when a timeout is set.

    def setUp(self):
        super().setUp()
        self.serv_conn = self.newSocket()
        self.addCleanup(self.serv_conn.close)
        # Use a thread to complete the connection, but wait for it to
        # terminate before running the test, so that there is only one
        # thread to accept the signal.
        cli_thread = threading.Thread(target=self.doConnect)
        cli_thread.start()
        self.cli_conn, addr = self.serv.accept()
        self.addCleanup(self.cli_conn.close)
        cli_thread.join()
        self.serv_conn.settimeout(self.timeout)

    def doConnect(self):
        self.serv_conn.connect(self.serv_addr)

    def checkInterruptedSend(self, func, *args, **kwargs):
        # Check that func(*args, **kwargs), run in a loop, raises
        # OSError with an errno of EINTR when interrupted by a
        # signal.
        try:
            with self.assertRaises(ZeroDivisionError) as cm:
                while True:
                    self.setAlarm(self.alarm_time)
                    func(*args, **kwargs)
        finally:
            self.setAlarm(0)


@unittest.skip("unclear purpose")
class TCPCloserTest(ThreadedTCPSocketTest):

    def testClose(self):
        conn, addr = self.serv.accept()
        conn.close()

        sd = self.cli
        read, write, err = select.select([sd], [], [], 1.0)
        self.assertEqual(read, [sd])
        self.assertEqual(sd.recv(1), b'')

        # Calling close() many times should be safe.
        conn.close()
        conn.close()

    def _testClose(self):
        self.cli.connect((HOST, self.port))
        time.sleep(1.0)


@unittest.skipUnless(hasattr(socket, 'socketpair'),  'test needs socket.socketpair')
class BasicSocketPairTest(SocketPairTest):

    def __init__(self, methodName='runTest'):
        SocketPairTest.__init__(self, methodName=methodName)

    def _check_defaults(self, sock):
        self.assertIsInstance(sock, socket.socket)
        if hasattr(socket, 'AF_UNIX'):
            self.assertEqual(sock.family, socket.AF_UNIX)
        else:
            self.assertEqual(sock.family, socket.AF_INET)
        self.assertEqual(sock.type, socket.SOCK_STREAM)
        self.assertEqual(sock.proto, 0)

    def _testDefaults(self):
        self._check_defaults(self.cli)

    def testDefaults(self):
        self._check_defaults(self.serv)

    def testRecv(self):
        msg = self.serv.recv(1024)
        self.assertEqual(msg, MSG)

    def _testRecv(self):
        self.cli.send(MSG)

    def testSend(self):
        self.serv.send(MSG)

    def _testSend(self):
        msg = self.cli.recv(1024)
        self.assertEqual(msg, MSG)


class NonBlockingTCPTests(ThreadedTCPSocketTest):

    def __init__(self, methodName='runTest'):
        self.event = threading.Event()
        ThreadedTCPSocketTest.__init__(self, methodName=methodName)

    def testSetBlocking(self):
        # Testing whether set blocking works
        self.serv.setblocking(True)
        self.assertIsNone(self.serv.gettimeout())
        self.assertTrue(self.serv.getblocking())
        if fcntl:
            self.assertTrue(_is_fd_in_blocking_mode(self.serv))

        self.serv.setblocking(False)
        self.assertEqual(self.serv.gettimeout(), 0.0)
        self.assertFalse(self.serv.getblocking())
        if fcntl:
            self.assertFalse(_is_fd_in_blocking_mode(self.serv))

        self.serv.settimeout(None)
        self.assertTrue(self.serv.getblocking())
        if fcntl:
            self.assertTrue(_is_fd_in_blocking_mode(self.serv))

        self.serv.settimeout(0)
        self.assertFalse(self.serv.getblocking())
        self.assertEqual(self.serv.gettimeout(), 0)
        if fcntl:
            self.assertFalse(_is_fd_in_blocking_mode(self.serv))

        self.serv.settimeout(10)
        self.assertTrue(self.serv.getblocking())
        self.assertEqual(self.serv.gettimeout(), 10)

        self.serv.settimeout(0)
        self.assertFalse(self.serv.getblocking())
        if fcntl:
            self.assertFalse(_is_fd_in_blocking_mode(self.serv))

        start = time.time()
        try:
            self.serv.accept()
        except OSError:
            pass
        end = time.time()
        self.assertTrue((end - start) < 1.0, "Error setting non-blocking mode.")

    def _testSetBlocking(self):
        pass

    @unittest.skipUnless(hasattr(socket, 'SOCK_NONBLOCK'),
                         'test needs socket.SOCK_NONBLOCK')
    def testInitNonBlocking(self):
        # reinit server socket
        self.serv.close()
        self.serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM |
                                                  socket.SOCK_NONBLOCK)
        self.assertFalse(self.serv.getblocking())
        self.assertEqual(self.serv.gettimeout(), 0)
        self.port = support.bind_port(self.serv)
        self.serv.listen()
        # actual testing
        start = time.time()
        try:
            self.serv.accept()
        except OSError:
            pass
        end = time.time()
        self.assertTrue((end - start) < 1.0, "Error creating with non-blocking mode.")

    def _testInitNonBlocking(self):
        pass

    def testInheritFlags(self):
        # Issue #7995: when calling accept() on a listening socket with a
        # timeout, the resulting socket should not be non-blocking.
        self.serv.settimeout(10)
        try:
            conn, addr = self.serv.accept()
            message = conn.recv(len(MSG))
        finally:
            conn.close()
            self.serv.settimeout(None)

    def _testInheritFlags(self):
        time.sleep(0.1)
        self.cli.connect((HOST, self.port))
        time.sleep(0.5)
        self.cli.send(MSG)

    def testAccept(self):
        # Testing non-blocking accept
        self.serv.setblocking(0)

        # connect() didn't start: non-blocking accept() fails
        with self.assertRaises(BlockingIOError):
            conn, addr = self.serv.accept()

        self.event.set()

        read, write, err = select.select([self.serv], [], [], MAIN_TIMEOUT)
        if self.serv not in read:
            self.fail("Error trying to do accept after select.")

        # connect() completed: non-blocking accept() doesn't block
        conn, addr = self.serv.accept()
        self.addCleanup(conn.close)
        self.assertIsNone(conn.gettimeout())

    def _testAccept(self):
        # don't connect before event is set to check
        # that non-blocking accept() raises BlockingIOError
        self.event.wait()

        self.cli.connect((HOST, self.port))

    def testConnect(self):
        # Testing non-blocking connect
        conn, addr = self.serv.accept()
        conn.close()

    def _testConnect(self):
        self.cli.settimeout(10)
        self.cli.connect((HOST, self.port))

    def testRecv(self):
        # Testing non-blocking recv
        conn, addr = self.serv.accept()
        self.addCleanup(conn.close)
        conn.setblocking(0)

        # the server didn't send data yet: non-blocking recv() fails
        with self.assertRaises(BlockingIOError):
            msg = conn.recv(len(MSG))

        self.event.set()

        read, write, err = select.select([conn], [], [], MAIN_TIMEOUT)
        if conn not in read:
            self.fail("Error during select call to non-blocking socket.")

        # the server sent data yet: non-blocking recv() doesn't block
        msg = conn.recv(len(MSG))
        self.assertEqual(msg, MSG)

    def _testRecv(self):
        self.cli.connect((HOST, self.port))

        # don't send anything before event is set to check
        # that non-blocking recv() raises BlockingIOError
        self.event.wait()

        # send data: recv() will no longer block
        self.cli.sendall(MSG)


class FileObjectClassTestCase(SocketConnectedTest):
    """Unit tests for the object returned by socket.makefile()

    self.read_file is the io object returned by makefile() on
    the client connection.  You can read from this file to
    get output from the server.

    self.write_file is the io object returned by makefile() on the
    server connection.  You can write to this file to send output
    to the client.
    """

    bufsize = -1 # Use default buffer size
    encoding = 'utf-8'
    errors = 'strict'
    newline = None

    read_mode = 'rb'
    read_msg = MSG
    write_mode = 'wb'
    write_msg = MSG

    def __init__(self, methodName='runTest'):
        SocketConnectedTest.__init__(self, methodName=methodName)

    def setUp(self):
        self.evt1, self.evt2, self.serv_finished, self.cli_finished = [
            threading.Event() for i in range(4)]
        SocketConnectedTest.setUp(self)
        self.read_file = self.cli_conn.makefile(
            self.read_mode, self.bufsize,
            encoding = self.encoding,
            errors = self.errors,
            newline = self.newline)

    def tearDown(self):
        self.serv_finished.set()
        self.read_file.close()
        self.assertTrue(self.read_file.closed)
        self.read_file = None
        SocketConnectedTest.tearDown(self)

    def clientSetUp(self):
        SocketConnectedTest.clientSetUp(self)
        self.write_file = self.serv_conn.makefile(
            self.write_mode, self.bufsize,
            encoding = self.encoding,
            errors = self.errors,
            newline = self.newline)

    def clientTearDown(self):
        self.cli_finished.set()
        if hasattr(self, 'write_file'):
            self.write_file.close()
            self.assertTrue(self.write_file.closed)
            self.write_file = None
        SocketConnectedTest.clientTearDown(self)

    def testReadAfterTimeout(self):
        # Issue #7322: A file object must disallow further reads
        # after a timeout has occurred.
        self.cli_conn.settimeout(1)
        self.read_file.read(3)
        # First read raises a timeout
        self.assertRaises(socket.timeout, self.read_file.read, 1)
        # Second read is disallowed
        with self.assertRaises(OSError) as ctx:
            self.read_file.read(1)
        # self.assertIn("cannot read from timed out object", str(ctx.exception))

    def _testReadAfterTimeout(self):
        self.write_file.write(self.write_msg[0:3])
        self.write_file.flush()
        self.serv_finished.wait()

    def testSmallRead(self):
        # Performing small file read test
        first_seg = self.read_file.read(len(self.read_msg)-3)
        second_seg = self.read_file.read(3)
        msg = first_seg + second_seg
        self.assertEqual(msg, self.read_msg)

    def _testSmallRead(self):
        self.write_file.write(self.write_msg)
        self.write_file.flush()

    def testFullRead(self):
        # read until EOF
        msg = self.read_file.read()
        self.assertEqual(msg, self.read_msg)

    def _testFullRead(self):
        self.write_file.write(self.write_msg)
        self.write_file.close()

    def testUnbufferedRead(self):
        # Performing unbuffered file read test
        buf = type(self.read_msg)()
        while 1:
            char = self.read_file.read(1)
            if not char:
                break
            buf += char
        self.assertEqual(buf, self.read_msg)

    def _testUnbufferedRead(self):
        self.write_file.write(self.write_msg)
        self.write_file.flush()

    def testReadline(self):
        # Performing file readline test
        line = self.read_file.readline()
        self.assertEqual(line, self.read_msg)

    def _testReadline(self):
        self.write_file.write(self.write_msg)
        self.write_file.flush()

    def testCloseAfterMakefile(self):
        # The file returned by makefile should keep the socket open.
        self.cli_conn.close()
        # read until EOF
        msg = self.read_file.read()
        self.assertEqual(msg, self.read_msg)

    def _testCloseAfterMakefile(self):
        self.write_file.write(self.write_msg)
        self.write_file.flush()

    def testMakefileAfterMakefileClose(self):
        self.read_file.close()
        msg = self.cli_conn.recv(len(MSG))
        if isinstance(self.read_msg, str):
            msg = msg.decode()
        self.assertEqual(msg, self.read_msg)

    def _testMakefileAfterMakefileClose(self):
        self.write_file.write(self.write_msg)
        self.write_file.flush()

    def testClosedAttr(self):
        self.assertTrue(not self.read_file.closed)

    def _testClosedAttr(self):
        self.assertTrue(not self.write_file.closed)

    @skipWithClientIfMicropython
    def testAttributes(self):
        self.assertEqual(self.read_file.mode, self.read_mode)
        self.assertEqual(self.read_file.name, self.cli_conn.fileno())

    @testAttributes.client_skip
    def _testAttributes(self):
        self.assertEqual(self.write_file.mode, self.write_mode)
        self.assertEqual(self.write_file.name, self.serv_conn.fileno())

    def testRealClose(self):
        self.read_file.close()
        self.assertRaises(ValueError, self.read_file.fileno)
        self.cli_conn.close()
        self.assertRaises(OSError, self.cli_conn.getsockname)

    def _testRealClose(self):
        pass


class UnbufferedFileObjectClassTestCase(FileObjectClassTestCase):

    """Repeat the tests from FileObjectClassTestCase with bufsize==0.

    In this case (and in this case only), it should be possible to
    create a file object, read a line from it, create another file
    object, read another line from it, without loss of data in the
    first file object's buffer.  Note that http.client relies on this
    when reading multiple requests from the same socket."""

    bufsize = 0 # Use unbuffered mode

    def testUnbufferedReadline(self):
        # Read a line, create a new file object, read another line with it
        line = self.read_file.readline() # first line
        self.assertEqual(line, b"A. " + self.write_msg) # first line
        self.read_file = self.cli_conn.makefile('rb', 0)
        line = self.read_file.readline() # second line
        self.assertEqual(line, b"B. " + self.write_msg) # second line

    def _testUnbufferedReadline(self):
        self.write_file.write(b"A. " + self.write_msg)
        self.write_file.write(b"B. " + self.write_msg)
        self.write_file.flush()

    @skipWithClientIfMicropython
    def testMakefileClose(self):
        # The file returned by makefile should keep the socket open...
        self.cli_conn.close()
        msg = self.cli_conn.recv(1024)
        self.assertEqual(msg, self.read_msg)
        # ...until the file is itself closed
        self.read_file.close()
        self.assertRaises(OSError, self.cli_conn.recv, 1024)

    @testMakefileClose.client_skip
    def _testMakefileClose(self):
        self.write_file.write(self.write_msg)
        self.write_file.flush()

    # Non-blocking ops
    # NOTE: to set `read_file` as non-blocking, we must call
    # `cli_conn.setblocking` and vice-versa (see setUp / clientSetUp).

    def testSmallReadNonBlocking(self):
        self.cli_conn.setblocking(False)
        self.assertEqual(self.read_file.readinto(bytearray(10)), None)
        self.assertEqual(self.read_file.read(len(self.read_msg) - 3), None)
        self.evt1.set()
        self.evt2.wait(1.0)
        first_seg = self.read_file.read(len(self.read_msg) - 3)
        while first_seg is None:
            # Data not arrived (can happen under Windows), wait a bit
            time.sleep(0.5)
            first_seg = self.read_file.read(len(self.read_msg) - 3)
        buf = bytearray(10)
        n = self.read_file.readinto(buf)
        self.assertEqual(n, 3)
        msg = first_seg + buf[:n]
        self.assertEqual(msg, self.read_msg)
        self.assertEqual(self.read_file.readinto(bytearray(16)), None)
        self.assertEqual(self.read_file.read(1), None)

    def _testSmallReadNonBlocking(self):
        self.evt1.wait(1.0)
        self.write_file.write(self.write_msg)
        self.write_file.flush()
        self.evt2.set()
        # Avoid closing the socket before the server test has finished,
        # otherwise system recv() will return 0 instead of EWOULDBLOCK.
        self.serv_finished.wait(5.0)

    def testWriteNonBlocking(self):
        self.cli_finished.wait(5.0)
        # The client thread can't skip directly - the SkipTest exception
        # would appear as a failure.
        if self.serv_skipped:
            self.skipTest(self.serv_skipped)

    def _testWriteNonBlocking(self):
        self.serv_skipped = None
        self.serv_conn.setblocking(False)
        # Try to saturate the socket buffer pipe with repeated large writes.
        BIG = b"x" * support.SOCK_MAX_SIZE
        LIMIT = 1000
        # The first write() succeeds since a chunk of data can be buffered
        n = self.write_file.write(BIG)
        self.assertGreater(n, 0)
        for i in range(LIMIT):
            n = self.write_file.write(BIG)
            if n is None:
                # Succeeded
                break
            self.assertGreater(n, 0)
        else:
            # Let us know that this test didn't manage to establish
            # the expected conditions. This is not a failure in itself but,
            # if it happens repeatedly, the test should be fixed.
            self.serv_skipped = "failed to saturate the socket buffer"


class LineBufferedFileObjectClassTestCase(FileObjectClassTestCase):

    bufsize = 1 # Default-buffered for reading; line-buffered for writing


class SmallBufferedFileObjectClassTestCase(FileObjectClassTestCase):

    bufsize = 2 # Exercise the buffering code


class UnicodeReadFileObjectClassTestCase(FileObjectClassTestCase):
    """Tests for socket.makefile() in text mode (rather than binary)"""

    read_mode = 'r'
    read_msg = MSG.decode('utf-8')
    write_mode = 'wb'
    write_msg = MSG
    newline = ''


class UnicodeWriteFileObjectClassTestCase(FileObjectClassTestCase):
    """Tests for socket.makefile() in text mode (rather than binary)"""

    read_mode = 'rb'
    read_msg = MSG
    write_mode = 'w'
    write_msg = MSG.decode('utf-8')
    newline = ''


class UnicodeReadWriteFileObjectClassTestCase(FileObjectClassTestCase):
    """Tests for socket.makefile() in text mode (rather than binary)"""

    read_mode = 'r'
    read_msg = MSG.decode('utf-8')
    write_mode = 'w'
    write_msg = MSG.decode('utf-8')
    newline = ''


class NetworkConnectionTest(object):
    """Prove network connection."""

    def clientSetUp(self):
        # We're inherited below by BasicTCPTest2, which also inherits
        # BasicTCPTest, which defines self.port referenced below.
        self.cli = socket.create_connection((HOST, self.port))
        self.serv_conn = self.cli

class BasicTCPTest2(NetworkConnectionTest, BasicTCPTest):
    """Tests that NetworkConnection does not break existing TCP functionality.
    """

class NetworkConnectionNoServer(unittest.TestCase):

    class MockSocket(socket.socket):
        def connect(self, *args):
            raise socket.timeout('timed out')

    @contextlib.contextmanager
    def mocked_socket_module(self):
        """Return a socket which times out on connect"""
        old_socket = socket.socket
        socket.socket = self.MockSocket
        try:
            yield
        finally:
            socket.socket = old_socket

    def test_connect(self):
        port = support.find_unused_port()
        cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(cli.close)
        with self.assertRaises(OSError) as cm:
            cli.connect((HOST, port))
        self.assertEqual(cm.exception.errno, errno.ECONNREFUSED)

    def test_create_connection(self):
        # Issue #9792: errors raised by create_connection() should have
        # a proper errno attribute.
        port = support.find_unused_port()
        with self.assertRaises(OSError) as cm:
            socket.create_connection((HOST, port))

        # Issue #16257: create_connection() calls getaddrinfo() against
        # 'localhost'.  This may result in an IPV6 addr being returned
        # as well as an IPV4 one:
        #   >>> socket.getaddrinfo('localhost', port, 0, SOCK_STREAM)
        #   >>> [(2,  2, 0, '', ('127.0.0.1', 41230)),
        #        (26, 2, 0, '', ('::1', 41230, 0, 0))]
        #
        # create_connection() enumerates through all the addresses returned
        # and if it doesn't successfully bind to any of them, it propagates
        # the last exception it encountered.
        expected_errnos = support.get_socket_conn_refused_errs()
        self.assertIn(cm.exception.errno, expected_errnos)

    @support.skip_micropython
    def test_create_connection_timeout(self):
        # Issue #9792: create_connection() should not recast timeout errors
        # as generic socket errors.
        with self.mocked_socket_module():
            with self.assertRaises(socket.timeout):
                socket.create_connection((HOST, 1234))


class NetworkConnectionAttributesTest(SocketTCPTest, ThreadableTest):

    def __init__(self, methodName='runTest'):
        SocketTCPTest.__init__(self, methodName=methodName)
        ThreadableTest.__init__(self)

    def clientSetUp(self):
        self.source_port = support.find_unused_port()

    def clientTearDown(self):
        self.cli.close()
        self.cli = None
        ThreadableTest.clientTearDown(self)

    def _justAccept(self):
        conn, addr = self.serv.accept()
        conn.close()

    testFamily = _justAccept
    def _testFamily(self):
        self.cli = socket.create_connection((HOST, self.port), timeout=30)
        self.addCleanup(self.cli.close)
        self.assertEqual(self.cli.family, 2)

    testSourceAddress = _justAccept
    def _testSourceAddress(self):
        self.cli = socket.create_connection((HOST, self.port), timeout=30,
                source_address=('', self.source_port))
        self.addCleanup(self.cli.close)
        self.assertEqual(self.cli.getsockname()[1], self.source_port)
        # The port number being used is sufficient to show that the bind()
        # call happened.

    testTimeoutDefault = _justAccept
    def _testTimeoutDefault(self):
        # passing no explicit timeout uses socket's global default
        self.assertTrue(socket.getdefaulttimeout() is None)
        socket.setdefaulttimeout(42)
        try:
            self.cli = socket.create_connection((HOST, self.port))
            self.addCleanup(self.cli.close)
        finally:
            socket.setdefaulttimeout(None)
        self.assertEqual(self.cli.gettimeout(), 42)

    testTimeoutNone = _justAccept
    def _testTimeoutNone(self):
        # None timeout means the same as sock.settimeout(None)
        self.assertTrue(socket.getdefaulttimeout() is None)
        socket.setdefaulttimeout(30)
        try:
            self.cli = socket.create_connection((HOST, self.port), timeout=None)
            self.addCleanup(self.cli.close)
        finally:
            socket.setdefaulttimeout(None)
        self.assertEqual(self.cli.gettimeout(), None)

    testTimeoutValueNamed = _justAccept
    def _testTimeoutValueNamed(self):
        self.cli = socket.create_connection((HOST, self.port), timeout=30)
        self.assertEqual(self.cli.gettimeout(), 30)

    testTimeoutValueNonamed = _justAccept
    def _testTimeoutValueNonamed(self):
        self.cli = socket.create_connection((HOST, self.port), 30)
        self.addCleanup(self.cli.close)
        self.assertEqual(self.cli.gettimeout(), 30)


class NetworkConnectionBehaviourTest(SocketTCPTest, ThreadableTest):

    def __init__(self, methodName='runTest'):
        SocketTCPTest.__init__(self, methodName=methodName)
        ThreadableTest.__init__(self)

    def clientSetUp(self):
        pass

    def clientTearDown(self):
        self.cli.close()
        self.cli = None
        ThreadableTest.clientTearDown(self)

    def testInsideTimeout(self):
        conn, addr = self.serv.accept()
        self.addCleanup(conn.close)
        time.sleep(3)
        conn.send(b"done!")
    testOutsideTimeout = testInsideTimeout

    def _testInsideTimeout(self):
        self.cli = sock = socket.create_connection((HOST, self.port))
        data = sock.recv(5)
        self.assertEqual(data, b"done!")

    def _testOutsideTimeout(self):
        self.cli = sock = socket.create_connection((HOST, self.port), timeout=1)
        self.assertRaises(socket.timeout, lambda: sock.recv(5))


class TCPTimeoutTest(SocketTCPTest):

    def testTCPTimeout(self):
        def raise_timeout(*args, **kwargs):
            self.serv.settimeout(1.0)
            self.serv.accept()
        self.assertRaises(socket.timeout, raise_timeout,
                              "Error generating a timeout exception (TCP)")

    def testTimeoutZero(self):
        ok = False
        try:
            self.serv.settimeout(0.0)
            foo = self.serv.accept()
        except socket.timeout:
            self.fail("caught timeout instead of error (TCP)")
        except OSError:
            ok = True
        except:
            self.fail("caught unexpected exception (TCP)")
        if not ok:
            self.fail("accept() returned success when we did not expect it")

    @unittest.skipUnless(hasattr(signal, 'alarm'),
                         'test needs signal.alarm()')
    def testInterruptedTimeout(self):
        # XXX I don't know how to do this test on MSWindows or any other
        # platform that doesn't support signal.alarm() or os.kill(), though
        # the bug should have existed on all platforms.
        self.serv.settimeout(5.0)   # must be longer than alarm
        class Alarm(Exception):
            pass
        def alarm_handler(signal, frame):
            raise Alarm
        old_alarm = signal.signal(signal.SIGALRM, alarm_handler)
        try:
            try:
                signal.alarm(2)    # POSIX allows alarm to be up to 1 second early
                foo = self.serv.accept()
            except socket.timeout:
                self.fail("caught timeout instead of Alarm")
            except Alarm:
                pass
            except Exception as exc:
                self.fail("caught other exception instead of Alarm: %s" % exc)
            else:
                self.fail("nothing caught")
            finally:
                signal.alarm(0)         # shut off alarm
        except Alarm:
            self.fail("got Alarm in wrong place")
        finally:
            # no alarm can be pending.  Safe to restore old handler.
            signal.signal(signal.SIGALRM, old_alarm)

class UDPTimeoutTest(SocketUDPTest):

    def testUDPTimeout(self):
        def raise_timeout(*args, **kwargs):
            self.serv.settimeout(1.0)
            self.serv.recv(1024)
        self.assertRaises(socket.timeout, raise_timeout,
                              "Error generating a timeout exception (UDP)")

    def testTimeoutZero(self):
        ok = False
        try:
            self.serv.settimeout(0.0)
            foo = self.serv.recv(1024)
        except socket.timeout:
            self.fail("caught timeout instead of error (UDP)")
        except OSError:
            ok = True
        except:
            self.fail("caught unexpected exception (UDP)")
        if not ok:
            self.fail("recv() returned success when we did not expect it")

class TestExceptions(unittest.TestCase):

    def testExceptionTree(self):
        self.assertTrue(issubclass(OSError, Exception))
        # self.assertTrue(issubclass(socket.herror, OSError))
        self.assertTrue(issubclass(socket.gaierror, OSError))
        self.assertTrue(issubclass(socket.timeout, OSError))

    def test_setblocking_invalidfd(self):
        # Regression test for issue #28471

        sock0 = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM, 0, sock0.fileno())
        sock0.close()
        self.addCleanup(sock.detach)

        with self.assertRaises(OSError):
            sock.setblocking(False)


@unittest.skipUnless(hasattr(socket, 'AF_UNIX'), 'test needs socket.AF_UNIX')
class TestUnixDomain(unittest.TestCase):

    def setUp(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    def tearDown(self):
        self.sock.close()

    def encoded(self, path):
        # Return the given path encoded in the file system encoding,
        # or skip the test if this is not possible.
        try:
            return os.fsencode(path)
        except UnicodeEncodeError:
            self.skipTest(
                "Pathname {0!a} cannot be represented in file "
                "system encoding {1!r}".format(
                    path, sys.getfilesystemencoding()))

    def bind(self, sock, path):
        # Bind the socket
        try:
            support.bind_unix_socket(sock, path)
        except OSError as e:
            if str(e) == "AF_UNIX path too long":
                self.skipTest(
                    "Pathname {0!a} is too long to serve as an AF_UNIX path"
                    .format(path))
            else:
                raise

    def testUnbound(self):
        # Issue #30205 (note getsockname() can return None on OS X)
        self.assertIn(self.sock.getsockname(), ('', None))

    def testStrAddr(self):
        # Test binding to and retrieving a normal string pathname.
        path = os.path.abspath(support.TESTFN)
        self.bind(self.sock, path)
        self.addCleanup(support.unlink, path)
        self.assertEqual(self.sock.getsockname(), path)

    def testBytesAddr(self):
        # Test binding to a bytes pathname.
        path = os.path.abspath(support.TESTFN)
        self.bind(self.sock, self.encoded(path))
        self.addCleanup(support.unlink, path)
        self.assertEqual(self.sock.getsockname(), path)

    def testSurrogateescapeBind(self):
        # Test binding to a valid non-ASCII pathname, with the
        # non-ASCII bytes supplied using surrogateescape encoding.
        path = os.path.abspath(support.TESTFN_UNICODE)
        b = self.encoded(path)
        self.bind(self.sock, b.decode("ascii", "surrogateescape"))
        self.addCleanup(support.unlink, path)
        self.assertEqual(self.sock.getsockname(), path)

    def testUnencodableAddr(self):
        # Test binding to a pathname that cannot be encoded in the
        # file system encoding.
        if support.TESTFN_UNENCODABLE is None:
            self.skipTest("No unencodable filename available")
        path = os.path.abspath(support.TESTFN_UNENCODABLE)
        self.bind(self.sock, path)
        self.addCleanup(support.unlink, path)
        self.assertEqual(self.sock.getsockname(), path)


class BufferIOTest(SocketConnectedTest):
    """
    Test the buffer versions of socket.recv() and socket.send().
    """
    def __init__(self, methodName='runTest'):
        SocketConnectedTest.__init__(self, methodName=methodName)

    def testRecvIntoArray(self):
        buf = array.array("B", [0] * len(MSG))
        nbytes = self.cli_conn.recv_into(buf)
        self.assertEqual(nbytes, len(MSG))
        buf = bytes(buf)
        msg = buf[:len(MSG)]
        self.assertEqual(msg, MSG)

    def _testRecvIntoArray(self):
        buf = bytes(MSG)
        self.serv_conn.send(buf)

    def testRecvIntoBytearray(self):
        buf = bytearray(1024)
        nbytes = self.cli_conn.recv_into(buf)
        self.assertEqual(nbytes, len(MSG))
        msg = buf[:len(MSG)]
        self.assertEqual(msg, MSG)

    _testRecvIntoBytearray = _testRecvIntoArray

    def testRecvIntoMemoryview(self):
        buf = bytearray(1024)
        nbytes = self.cli_conn.recv_into(memoryview(buf))
        self.assertEqual(nbytes, len(MSG))
        msg = buf[:len(MSG)]
        self.assertEqual(msg, MSG)

    _testRecvIntoMemoryview = _testRecvIntoArray

    def testRecvFromIntoArray(self):
        buf = array.array("B", [0] * len(MSG))
        nbytes, addr = self.cli_conn.recvfrom_into(buf)
        self.assertEqual(nbytes, len(MSG))
        buf = bytes(buf)
        msg = buf[:len(MSG)]
        self.assertEqual(msg, MSG)

    def _testRecvFromIntoArray(self):
        buf = bytes(MSG)
        self.serv_conn.send(buf)

    def testRecvFromIntoBytearray(self):
        buf = bytearray(1024)
        nbytes, addr = self.cli_conn.recvfrom_into(buf)
        self.assertEqual(nbytes, len(MSG))
        msg = buf[:len(MSG)]
        self.assertEqual(msg, MSG)

    _testRecvFromIntoBytearray = _testRecvFromIntoArray

    def testRecvFromIntoMemoryview(self):
        buf = bytearray(1024)
        nbytes, addr = self.cli_conn.recvfrom_into(memoryview(buf))
        self.assertEqual(nbytes, len(MSG))
        msg = buf[:len(MSG)]
        self.assertEqual(msg, MSG)

    _testRecvFromIntoMemoryview = _testRecvFromIntoArray

    def testRecvFromIntoSmallBuffer(self):
        # See issue #20246.
        buf = bytearray(8)
        self.assertRaises(ValueError, self.cli_conn.recvfrom_into, buf, 1024)

    def _testRecvFromIntoSmallBuffer(self):
        self.serv_conn.send(MSG)

    def testRecvFromIntoEmptyBuffer(self):
        buf = bytearray()
        self.cli_conn.recvfrom_into(buf)
        self.cli_conn.recvfrom_into(buf, 0)

    _testRecvFromIntoEmptyBuffer = _testRecvFromIntoArray


class ContextManagersTest(ThreadedTCPSocketTest):

    def _testSocketClass(self):
        # base test
        with socket.socket() as sock:
            self.assertFalse(sock._closed)
        self.assertTrue(sock._closed)
        # close inside with block
        with socket.socket() as sock:
            sock.close()
        self.assertTrue(sock._closed)
        # exception inside with block
        with socket.socket() as sock:
            self.assertRaises(OSError, sock.sendall, b'foo')
        self.assertTrue(sock._closed)

    def testCreateConnectionBase(self):
        conn, addr = self.serv.accept()
        self.addCleanup(conn.close)
        data = conn.recv(1024)
        conn.sendall(data)

    def _testCreateConnectionBase(self):
        address = self.serv.getsockname()
        with socket.create_connection(address) as sock:
            self.assertFalse(sock._closed)
            sock.sendall(b'foo')
            self.assertEqual(sock.recv(1024), b'foo')
        self.assertTrue(sock._closed)

    def testCreateConnectionClose(self):
        conn, addr = self.serv.accept()
        self.addCleanup(conn.close)
        data = conn.recv(1024)
        conn.sendall(data)

    def _testCreateConnectionClose(self):
        address = self.serv.getsockname()
        with socket.create_connection(address) as sock:
            sock.close()
        self.assertTrue(sock._closed)
        self.assertRaises(OSError, sock.sendall, b'foo')


@unittest.skipUnless(hasattr(socket, "SOCK_NONBLOCK"),
                     "SOCK_NONBLOCK not defined")
class NonblockConstantTest(unittest.TestCase):
    def checkNonblock(self, s, nonblock=True, timeout=0.0):
        if nonblock:
            self.assertEqual(s.type, socket.SOCK_STREAM)
            self.assertEqual(s.gettimeout(), timeout)
            self.assertTrue(
                fcntl.fcntl(s, fcntl.F_GETFL, os.O_NONBLOCK) & os.O_NONBLOCK)
            if timeout == 0:
                # timeout == 0: means that getblocking() must be False.
                self.assertFalse(s.getblocking())
            else:
                # If timeout > 0, the socket will be in a "blocking" mode
                # from the standpoint of the Python API.  For Python socket
                # object, "blocking" means that operations like 'sock.recv()'
                # will block.  Internally, file descriptors for
                # "blocking" Python sockets *with timeouts* are in a
                # *non-blocking* mode, and 'sock.recv()' uses 'select()'
                # and handles EWOULDBLOCK/EAGAIN to enforce the timeout.
                self.assertTrue(s.getblocking())
        else:
            self.assertEqual(s.type, socket.SOCK_STREAM)
            self.assertEqual(s.gettimeout(), None)
            self.assertFalse(
                fcntl.fcntl(s, fcntl.F_GETFL, os.O_NONBLOCK) & os.O_NONBLOCK)
            self.assertTrue(s.getblocking())

    def test_SOCK_NONBLOCK(self):
        # a lot of it seems silly and redundant, but I wanted to test that
        # changing back and forth worked ok
        with socket.socket(socket.AF_INET,
                           socket.SOCK_STREAM | socket.SOCK_NONBLOCK) as s:
            self.checkNonblock(s)
            s.setblocking(1)
            self.checkNonblock(s, nonblock=False)
            s.setblocking(0)
            self.checkNonblock(s)
            s.settimeout(None)
            self.checkNonblock(s, nonblock=False)
            s.settimeout(2.0)
            self.checkNonblock(s, timeout=2.0)
            s.setblocking(1)
            self.checkNonblock(s, nonblock=False)
        # defaulttimeout
        t = socket.getdefaulttimeout()
        socket.setdefaulttimeout(0.0)
        with socket.socket() as s:
            self.checkNonblock(s)
        socket.setdefaulttimeout(None)
        with socket.socket() as s:
            self.checkNonblock(s, False)
        socket.setdefaulttimeout(2.0)
        with socket.socket() as s:
            self.checkNonblock(s, timeout=2.0)
        socket.setdefaulttimeout(None)
        with socket.socket() as s:
            self.checkNonblock(s, False)
        socket.setdefaulttimeout(t)


@unittest.skipUnless(hasattr(socket.socket, 'sendfile'), 'test needs socket.sendfile')
class SendfileUsingSendTest(ThreadedTCPSocketTest):
    """
    Test the send() implementation of socket.sendfile().
    """

    FILESIZE = (10 * 1024 * 1024)  # 10 MiB
    BUFSIZE = 8192
    FILEDATA = b""
    TIMEOUT = 2

    @classmethod
    def setUpClass(cls):
        def chunks(total, step):
            assert total >= step
            while total > step:
                yield step
                total -= step
            if total:
                yield total

        chunk = b"".join([random.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ').encode()
                          for i in range(cls.BUFSIZE)])
        with open(support.TESTFN, 'wb') as f:
            for csize in chunks(cls.FILESIZE, cls.BUFSIZE):
                f.write(chunk)
        with open(support.TESTFN, 'rb') as f:
            cls.FILEDATA = f.read()
            assert len(cls.FILEDATA) == cls.FILESIZE

    @classmethod
    def tearDownClass(cls):
        support.unlink(support.TESTFN)

    def accept_conn(self):
        self.serv.settimeout(MAIN_TIMEOUT)
        conn, addr = self.serv.accept()
        conn.settimeout(self.TIMEOUT)
        self.addCleanup(conn.close)
        return conn

    def recv_data(self, conn):
        received = []
        while True:
            chunk = conn.recv(self.BUFSIZE)
            if not chunk:
                break
            received.append(chunk)
        return b''.join(received)

    def meth_from_sock(self, sock):
        # Depending on the mixin class being run return either send()
        # or sendfile() method implementation.
        return sock.sendfile

    # regular file

    def _testRegularFile(self):
        address = self.serv.getsockname()
        file = open(support.TESTFN, 'rb')
        with socket.create_connection(address) as sock, file as file:
            meth = self.meth_from_sock(sock)
            sent = meth(file)
            self.assertEqual(sent, self.FILESIZE)
            self.assertEqual(file.tell(), self.FILESIZE)

    def testRegularFile(self):
        conn = self.accept_conn()
        data = self.recv_data(conn)
        self.assertEqual(len(data), self.FILESIZE)
        self.assertEqual(data, self.FILEDATA)

    # non regular file

    def _testNonRegularFile(self):
        address = self.serv.getsockname()
        file = io.BytesIO(self.FILEDATA)
        with socket.create_connection(address) as sock, file as file:
            sent = sock.sendfile(file)
            self.assertEqual(sent, self.FILESIZE)
            self.assertEqual(file.tell(), self.FILESIZE)
            self.assertRaises(socket._GiveupOnSendfile,
                              sock.sendfile, file)

    def testNonRegularFile(self):
        conn = self.accept_conn()
        data = self.recv_data(conn)
        self.assertEqual(len(data), self.FILESIZE)
        self.assertEqual(data, self.FILEDATA)

    # empty file

    def _testEmptyFileSend(self):
        address = self.serv.getsockname()
        filename = support.TESTFN + "2"
        with open(filename, 'wb'):
            self.addCleanup(support.unlink, filename)
        file = open(filename, 'rb')
        with socket.create_connection(address) as sock, file as file:
            meth = self.meth_from_sock(sock)
            sent = meth(file)
            self.assertEqual(sent, 0)
            self.assertEqual(file.tell(), 0)

    def testEmptyFileSend(self):
        conn = self.accept_conn()
        data = self.recv_data(conn)
        self.assertEqual(data, b"")

    # offset

    def _testOffset(self):
        address = self.serv.getsockname()
        file = open(support.TESTFN, 'rb')
        with socket.create_connection(address) as sock, file as file:
            meth = self.meth_from_sock(sock)
            sent = meth(file, offset=5000)
            self.assertEqual(sent, self.FILESIZE - 5000)
            self.assertEqual(file.tell(), self.FILESIZE)

    def testOffset(self):
        conn = self.accept_conn()
        data = self.recv_data(conn)
        self.assertEqual(len(data), self.FILESIZE - 5000)
        self.assertEqual(data, self.FILEDATA[5000:])

    # count

    def _testCount(self):
        address = self.serv.getsockname()
        file = open(support.TESTFN, 'rb')
        with socket.create_connection(address, timeout=2) as sock, file as file:
            count = 5000007
            meth = self.meth_from_sock(sock)
            sent = meth(file, count=count)
            self.assertEqual(sent, count)
            self.assertEqual(file.tell(), count)

    def testCount(self):
        count = 5000007
        conn = self.accept_conn()
        data = self.recv_data(conn)
        self.assertEqual(len(data), count)
        self.assertEqual(data, self.FILEDATA[:count])

    # count small

    def _testCountSmall(self):
        address = self.serv.getsockname()
        file = open(support.TESTFN, 'rb')
        with socket.create_connection(address, timeout=2) as sock, file as file:
            count = 1
            meth = self.meth_from_sock(sock)
            sent = meth(file, count=count)
            self.assertEqual(sent, count)
            self.assertEqual(file.tell(), count)

    def testCountSmall(self):
        count = 1
        conn = self.accept_conn()
        data = self.recv_data(conn)
        self.assertEqual(len(data), count)
        self.assertEqual(data, self.FILEDATA[:count])

    # count + offset

    def _testCountWithOffset(self):
        address = self.serv.getsockname()
        file = open(support.TESTFN, 'rb')
        with socket.create_connection(address, timeout=2) as sock, file as file:
            count = 100007
            meth = self.meth_from_sock(sock)
            sent = meth(file, offset=2007, count=count)
            self.assertEqual(sent, count)
            self.assertEqual(file.tell(), count + 2007)

    def testCountWithOffset(self):
        count = 100007
        conn = self.accept_conn()
        data = self.recv_data(conn)
        self.assertEqual(len(data), count)
        self.assertEqual(data, self.FILEDATA[2007:count+2007])

    # non blocking sockets are not supposed to work

    def _testNonBlocking(self):
        address = self.serv.getsockname()
        file = open(support.TESTFN, 'rb')
        with socket.create_connection(address) as sock, file as file:
            sock.setblocking(False)
            meth = self.meth_from_sock(sock)
            self.assertRaises(ValueError, meth, file)
            self.assertRaises(ValueError, sock.sendfile, file)

    def testNonBlocking(self):
        conn = self.accept_conn()
        if conn.recv(8192):
            self.fail('was not supposed to receive any data')

    # timeout (non-triggered)

    def _testWithTimeout(self):
        address = self.serv.getsockname()
        file = open(support.TESTFN, 'rb')
        with socket.create_connection(address, timeout=2) as sock, file as file:
            meth = self.meth_from_sock(sock)
            sent = meth(file)
            self.assertEqual(sent, self.FILESIZE)

    def testWithTimeout(self):
        conn = self.accept_conn()
        data = self.recv_data(conn)
        self.assertEqual(len(data), self.FILESIZE)
        self.assertEqual(data, self.FILEDATA)

    # timeout (triggered)

    def _testWithTimeoutTriggeredSend(self):
        address = self.serv.getsockname()
        with open(support.TESTFN, 'rb') as file:
            with socket.create_connection(address) as sock:
                sock.settimeout(0.01)
                meth = self.meth_from_sock(sock)
                self.assertRaises(socket.timeout, meth, file)

    def testWithTimeoutTriggeredSend(self):
        conn = self.accept_conn()
        conn.recv(88192)

    # errors

    def _test_errors(self):
        pass

    def test_errors(self):
        with open(support.TESTFN, 'rb') as file:
            with socket.socket(type=socket.SOCK_DGRAM) as s:
                meth = self.meth_from_sock(s)
                self.assertRaisesRegex(
                    ValueError, "SOCK_STREAM", meth, file)
        with open(support.TESTFN, 'rt') as file:
            with socket.socket() as s:
                meth = self.meth_from_sock(s)
                self.assertRaisesRegex(
                    ValueError, "binary mode", meth, file)
        with open(support.TESTFN, 'rb') as file:
            with socket.socket() as s:
                meth = self.meth_from_sock(s)
                self.assertRaisesRegex(TypeError, "positive integer",
                                       meth, file, count='2')
                self.assertRaisesRegex(TypeError, "positive integer",
                                       meth, file, count=0.1)
                self.assertRaisesRegex(ValueError, "positive integer",
                                       meth, file, count=0)
                self.assertRaisesRegex(ValueError, "positive integer",
                                       meth, file, count=-1)


def setUpModule():
    global _thread_info
    _thread_info = support.threading_setup()

def tearDownModule():
    support.threading_cleanup(*_thread_info)

if __name__ == "__main__":
    unittest.main()
