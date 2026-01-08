"""Supporting definitions for the Python regression tests."""

if __name__ != 'test.support':
    raise ImportError('support must be imported from the test package')

import collections.abc
import contextlib
import errno
import functools
import gc
import importlib
# import logging.handlers
import os
import platform
import re
import shutil
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
import types
import unittest
# import urllib.error
import warnings

from .testresult import get_test_runner

try:
    import multiprocessing.process
except ImportError:
    multiprocessing = None

try:
    import zlib
except ImportError:
    zlib = None

try:
    import gzip
except ImportError:
    gzip = None

try:
    import bz2
except ImportError:
    bz2 = None

try:
    import lzma
except ImportError:
    lzma = None

try:
    import resource
except ImportError:
    resource = None

try:
    import weakref
except ImportError:
    weakref = None

__all__ = (
    # globals
    "PIPE_MAX_SIZE", "verbose", "max_memuse", "use_resources", "failfast",
    # exceptions
    "Error", "TestFailed", "TestDidNotRun", "ResourceDenied",
    # imports
    "import_module", "import_fresh_module", "CleanImport",
    # modules
    "unload", "forget",
    # io
    "record_original_stdout", "get_original_stdout", "captured_stdout",
    "captured_stdin", "captured_stderr",
    # filesystem
    "TESTFN", "SAVEDCWD", "unlink", "rmtree", "temp_cwd", "findfile",
    "create_empty_file", "can_symlink", "fs_is_case_insensitive",
    # unittest
    "is_resource_enabled", "requires", "requires_freebsd_version",
    "requires_linux_version", "requires_mac_ver", "check_syntax_error",
    # "TransientResource", "time_out", "socket_peer_reset", "ioerror_peer_reset",
    "transient_internet", "BasicTestRunner", "run_unittest", "run_doctest",
    "skip_unless_symlink", "requires_gzip", "requires_bz2", "requires_lzma",
    "bigmemtest", "bigaddrspacetest", "cpython_only", "get_attribute",
    "requires_IEEE_754", "skip_unless_xattr", "requires_zlib",
    "anticipate_failure", "load_package_tests", "detect_api_mismatch",
    "check__all__", "skip_unless_bind_unix_socket",
    # sys
    "check_impl_detail", "unix_shell",
    "setswitchinterval",
    # network
    "HOST", "IPV6_ENABLED", "find_unused_port", "bind_port", "open_urlresource",
    "bind_unix_socket",
    # processes
    'temp_umask', "reap_children",
    # logging
    "TestHandler",
    # threads
    "threading_setup", "threading_cleanup", "reap_threads", "start_threads",
    # miscellaneous
    "check_warnings", "check_no_resource_warning", "EnvironmentVarGuard",
    "run_with_locale", "swap_item",
    "swap_attr", "Matcher", "set_memlimit", "SuppressCrashReport", "sortdict",
    "run_with_tz", "PGO", "fd_count",
    "ALWAYS_EQ", "LARGEST", "SMALLEST"
)

class Error(Exception):
    """Base class for regression test exceptions."""

class TestFailed(Error):
    """Test failed."""

class TestDidNotRun(Error):
    """Test did not run any subtests."""

class ResourceDenied(unittest.SkipTest):
    """Test skipped because it requested a disallowed resource.

    This is raised when a test calls requires() for a resource that
    has not be enabled.  It is used to distinguish between expected
    and unexpected skips.
    """

def import_module(name, deprecated=False, *, required_on=()):
    """Import and return the module to be tested, raising SkipTest if
    it is not available.

    If deprecated is True, any module or package deprecation messages
    will be suppressed. If a module is required on a platform but optional for
    others, set required_on to an iterable of platform prefixes which will be
    compared against sys.platform.
    """
    try:
        return importlib.import_module(name)
    except ImportError as msg:
        if sys.platform.startswith(tuple(required_on)):
            raise
        raise unittest.SkipTest(str(msg))


def _save_and_remove_module(name, orig_modules):
    """Helper function to save and remove a module from sys.modules

    Raise ImportError if the module can't be imported.
    """
    # try to import the module and raise an error if it can't be imported
    if name not in sys.modules:
        __import__(name)
        del sys.modules[name]
    for modname in list(sys.modules):
        if modname == name or modname.startswith(name + '.'):
            orig_modules[modname] = sys.modules[modname]
            del sys.modules[modname]

def _save_and_block_module(name, orig_modules):
    """Helper function to save and block a module in sys.modules

    Return True if the module was in sys.modules, False otherwise.
    """
    saved = True
    try:
        orig_modules[name] = sys.modules[name]
    except KeyError:
        saved = False
    sys.modules[name] = None
    return saved


def anticipate_failure(condition):
    """Decorator to mark a test that is known to be broken in some cases

       Any use of this decorator should have a comment identifying the
       associated tracker issue.
    """
    if condition:
        return unittest.expectedFailure
    return lambda f: f

def load_package_tests(pkg_dir, loader, standard_tests, pattern):
    """Generic load_tests implementation for simple test packages.

    Most packages can implement load_tests using this function as follows:

       def load_tests(*args):
           return load_package_tests(os.path.dirname(__file__), *args)
    """
    if pattern is None:
        pattern = "test*"
    top_dir = os.path.dirname(              # Lib
                  os.path.dirname(              # test
                      os.path.dirname(__file__)))   # support
    package_tests = loader.discover(start_dir=pkg_dir,
                                    top_level_dir=top_dir,
                                    pattern=pattern)
    standard_tests.addTests(package_tests)
    return standard_tests


def import_fresh_module(name, fresh=(), blocked=(), deprecated=False):
    """Import and return a module, deliberately bypassing sys.modules.

    This function imports and returns a fresh copy of the named Python module
    by removing the named module from sys.modules before doing the import.
    Note that unlike reload, the original module is not affected by
    this operation.

    *fresh* is an iterable of additional module names that are also removed
    from the sys.modules cache before doing the import.

    *blocked* is an iterable of module names that are replaced with None
    in the module cache during the import to ensure that attempts to import
    them raise ImportError.

    The named module and any modules named in the *fresh* and *blocked*
    parameters are saved before starting the import and then reinserted into
    sys.modules when the fresh import is complete.

    Module and package deprecation messages are suppressed during this import
    if *deprecated* is True.

    This function will raise ImportError if the named module cannot be
    imported.
    """
    # NOTE: test_heapq, test_json and test_warnings include extra sanity checks
    # to make sure that this utility function is working as expected
    with _ignore_deprecated_imports(deprecated):
        # Keep track of modules saved for later restoration as well
        # as those which just need a blocking entry removed
        orig_modules = {}
        names_to_remove = []
        _save_and_remove_module(name, orig_modules)
        try:
            for fresh_name in fresh:
                _save_and_remove_module(fresh_name, orig_modules)
            for blocked_name in blocked:
                if not _save_and_block_module(blocked_name, orig_modules):
                    names_to_remove.append(blocked_name)
            fresh_module = importlib.import_module(name)
        except ImportError:
            fresh_module = None
        finally:
            for orig_name, module in orig_modules.items():
                sys.modules[orig_name] = module
            for name_to_remove in names_to_remove:
                del sys.modules[name_to_remove]
        return fresh_module


def get_attribute(obj, name):
    """Get an attribute, raising SkipTest if AttributeError is raised."""
    try:
        attribute = getattr(obj, name)
    except AttributeError:
        raise unittest.SkipTest("object %r has no attribute %r" % (obj, name))
    else:
        return attribute

verbose = 1              # Flag set to 0 by regrtest.py
use_resources = None     # Flag set to [] by regrtest.py
max_memuse = 0           # Disable bigmem tests (they will still be run with
                         # small sizes, to make sure they work.)
real_max_memuse = 0
failfast = False

def record_original_stdout(stdout):
    pass

def get_original_stdout():
    return sys.stdout

def unload(name):
    try:
        del sys.modules[name]
    except KeyError:
        pass

def _force_run(path, func, *args):
    try:
        return func(*args)
    except OSError as err:
        # if verbose >= 2:
        #     print('%s: %s' % (err.__class__.__name__, err))
        #     print('re-run %s%r' % (func.__name__, args))
        # os.chmod(path, stat.S_IRWXU)
        # return func(*args)
        raise

_unlink = os.unlink
_rmdir = os.rmdir

def _rmtree(path):
    try:
        shutil.rmtree(path)
        return
    except OSError:
        pass

    def _rmtree_inner(path):
        for name in _force_run(path, os.listdir, path):
            fullname = os.path.join(path, name)
            try:
                mode = os.lstat(fullname).st_mode
            except OSError:
                mode = 0
            if stat.S_ISDIR(mode):
                _rmtree_inner(fullname)
                _force_run(path, os.rmdir, fullname)
            else:
                _force_run(path, os.unlink, fullname)
    _rmtree_inner(path)
    os.rmdir(path)

def _longpath(path):
    return path

def unlink(filename):
    try:
        _unlink(filename)
    except (FileNotFoundError, NotADirectoryError):
        pass

def rmdir(dirname):
    try:
        _rmdir(dirname)
    except FileNotFoundError:
        pass

def rmtree(path):
    try:
        _rmtree(path)
    except FileNotFoundError:
        pass

def forget(modname):
    """'Forget' a module was ever imported.

    This removes the module from sys.modules and deletes any PEP 3147/488 or
    legacy .pyc files.
    """
    unload(modname)
    for dirname in sys.path:
        source = os.path.join(dirname, modname + '.py')
        # It doesn't matter if they exist or not, unlink all possible
        # combinations of PEP 3147/488 and legacy pyc files.
        unlink(source + 'c')

# Check whether a gui is actually available
class _is_gui_available:
    def __bool__(self):
        return _is_gui_available.result

    reason = "there's no gui"
    result = False

def is_resource_enabled(resource):
    """Test whether a resource is enabled.

    Known resources are set by regrtest.py.  If not running under regrtest.py,
    all resources are assumed enabled unless use_resources has been set.
    """
    return use_resources is None or resource in use_resources

def requires(resource, msg=None):
    """Raise ResourceDenied if the specified resource is not available."""
    if not is_resource_enabled(resource):
        if msg is None:
            msg = "Use of the %r resource not enabled" % resource
        raise ResourceDenied(msg)
    if resource == 'gui' and not _is_gui_available():
        raise ResourceDenied(_is_gui_available.reason)


HOST = "localhost"
HOSTv4 = "127.0.0.1"
HOSTv6 = "::1"


def find_unused_port(family=socket.AF_INET, socktype=socket.SOCK_STREAM):
    """Returns an unused port that should be suitable for binding.  This is
    achieved by creating a temporary socket with the same family and type as
    the 'sock' parameter (default is AF_INET, SOCK_STREAM), and binding it to
    the specified host address (defaults to 0.0.0.0) with the port set to 0,
    eliciting an unused ephemeral port from the OS.  The temporary socket is
    then closed and deleted, and the ephemeral port is returned.

    Either this method or bind_port() should be used for any tests where a
    server socket needs to be bound to a particular port for the duration of
    the test.  Which one to use depends on whether the calling code is creating
    a python socket, or if an unused port needs to be provided in a constructor
    or passed to an external program (i.e. the -accept argument to openssl's
    s_server mode).  Always prefer bind_port() over find_unused_port() where
    possible.  Hard coded ports should *NEVER* be used.  As soon as a server
    socket is bound to a hard coded port, the ability to run multiple instances
    of the test simultaneously on the same host is compromised, which makes the
    test a ticking time bomb in a buildbot environment. On Unix buildbots, this
    may simply manifest as a failed test, which can be recovered from without
    intervention in most cases, but on Windows, the entire python process can
    completely and utterly wedge, requiring someone to log in to the buildbot
    and manually kill the affected process.

    (This is easy to reproduce on Windows, unfortunately, and can be traced to
    the SO_REUSEADDR socket option having different semantics on Windows versus
    Unix/Linux.  On Unix, you can't have two AF_INET SOCK_STREAM sockets bind,
    listen and then accept connections on identical host/ports.  An EADDRINUSE
    OSError will be raised at some point (depending on the platform and
    the order bind and listen were called on each socket).

    However, on Windows, if SO_REUSEADDR is set on the sockets, no EADDRINUSE
    will ever be raised when attempting to bind two identical host/ports. When
    accept() is called on each socket, the second caller's process will steal
    the port from the first caller, leaving them both in an awkwardly wedged
    state where they'll no longer respond to any signals or graceful kills, and
    must be forcibly killed via OpenProcess()/TerminateProcess().

    The solution on Windows is to use the SO_EXCLUSIVEADDRUSE socket option
    instead of SO_REUSEADDR, which effectively affords the same semantics as
    SO_REUSEADDR on Unix.  Given the propensity of Unix developers in the Open
    Source world compared to Windows ones, this is a common mistake.  A quick
    look over OpenSSL's 0.9.8g source shows that they use SO_REUSEADDR when
    openssl.exe is called with the 's_server' option, for example. See
    http://bugs.python.org/issue2550 for more info.  The following site also
    has a very thorough description about the implications of both REUSEADDR
    and EXCLUSIVEADDRUSE on Windows:
    http://msdn2.microsoft.com/en-us/library/ms740621(VS.85).aspx)

    XXX: although this approach is a vast improvement on previous attempts to
    elicit unused ports, it rests heavily on the assumption that the ephemeral
    port returned to us by the OS won't immediately be dished back out to some
    other process when we close and delete our temporary socket but before our
    calling code has a chance to bind the returned port.  We can deal with this
    issue if/when we come across it.
    """

    tempsock = socket.socket(family, socktype)
    port = bind_port(tempsock)
    tempsock.close()
    del tempsock
    return port

def bind_port(sock, host=HOST):
    """Bind the socket to a free port and return the port number.  Relies on
    ephemeral ports in order to ensure we are using an unbound port.  This is
    important as many tests may be running simultaneously, especially in a
    buildbot environment.  This method raises an exception if the sock.family
    is AF_INET and sock.type is SOCK_STREAM, *and* the socket has SO_REUSEADDR
    or SO_REUSEPORT set on it.  Tests should *never* set these socket options
    for TCP/IP sockets.  The only case for setting these options is testing
    multicasting via multiple UDP sockets.

    Additionally, if the SO_EXCLUSIVEADDRUSE socket option is available (i.e.
    on Windows), it will be set on the socket.  This will prevent anyone else
    from bind()'ing to our host/port for the duration of the test.
    """

    if sock.family == socket.AF_INET and sock.type == socket.SOCK_STREAM:
        if hasattr(socket, 'SO_REUSEADDR'):
            if sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 1:
                raise TestFailed("tests should never set the SO_REUSEADDR "   \
                                 "socket option on TCP/IP sockets!")
        if hasattr(socket, 'SO_REUSEPORT'):
            try:
                if sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT) == 1:
                    raise TestFailed("tests should never set the SO_REUSEPORT "   \
                                     "socket option on TCP/IP sockets!")
            except OSError:
                # Python's socket module was compiled using modern headers
                # thus defining SO_REUSEPORT but this process is running
                # under an older kernel that does not support SO_REUSEPORT.
                pass
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)

    sock.bind((host, 0))
    port = sock.getsockname()[1]
    return port

def bind_unix_socket(sock, addr):
    """Bind a unix socket, raising SkipTest if PermissionError is raised."""
    assert sock.family == socket.AF_UNIX
    try:
        sock.bind(addr)
    except PermissionError:
        sock.close()
        raise unittest.SkipTest('cannot bind AF_UNIX sockets')

def _is_ipv6_enabled():
    """Check whether IPv6 is enabled on this host."""
    if socket.has_ipv6:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            sock.bind((HOSTv6, 0))
            return True
        except OSError:
            pass
        finally:
            if sock:
                sock.close()
    return False

IPV6_ENABLED = _is_ipv6_enabled()

def system_must_validate_cert(f):
    """Skip the test on TLS certificate validation failures."""
    @functools.wraps(f)
    def dec(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except OSError as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                raise unittest.SkipTest("system does not contain "
                                        "necessary certificates")
            raise
    return dec

# A constant likely larger than the underlying OS pipe buffer size, to
# make writes blocking.
# Windows limit seems to be around 512 B, and many Unix kernels have a
# 64 KiB pipe buffer size or 16 * PAGE_SIZE: take a few megs to be sure.
# (see issue #17835 for a discussion of this number).
PIPE_MAX_SIZE = 512 + 1

# A constant likely larger than the underlying OS socket buffer size, to make
# writes blocking.
# The socket buffer sizes can usually be tuned system-wide (e.g. through sysctl
# on Linux), or on a per-socket basis (SO_SNDBUF/SO_RCVBUF). See issue #18643
# for a discussion of this number).
SOCK_MAX_SIZE = 512 + 1

# decorator for skipping tests on non-IEEE 754 platforms
requires_IEEE_754 = unittest.skipUnless(False, "test requires IEEE 754 doubles")

requires_zlib = unittest.skipUnless(zlib, 'requires zlib')

requires_gzip = unittest.skipUnless(gzip, 'requires gzip')

requires_bz2 = unittest.skipUnless(bz2, 'requires bz2')

requires_lzma = unittest.skipUnless(lzma, 'requires lzma')

requires_weakref = unittest.skipUnless(weakref, 'requires weakref')

skip_micropython = unittest.skip('does not work on MicroPython')

is_micropython = True

unix_shell = None

# Filename used for testing
TESTFN = '@test'

# Define the URL of a dedicated HTTP server for the network tests.
# The URL must use clear-text HTTP: no redirection to encrypted HTTPS.
TEST_HTTP_URL = "http://www.pythontest.net"

# FS_NONASCII: non-ASCII character encodable by os.fsencode(),
# or None if there is no such character.
FS_NONASCII = None
for character in (
    # First try printable and common characters to have a readable filename.
    # For each character, the encoding list are just example of encodings able
    # to encode the character (the list is not exhaustive).

    # U+00E6 (Latin Small Letter Ae): cp1252, iso-8859-1
    '\u00E6',
    # U+0130 (Latin Capital Letter I With Dot Above): cp1254, iso8859_3
    '\u0130',
    # U+0141 (Latin Capital Letter L With Stroke): cp1250, cp1257
    '\u0141',
    # U+03C6 (Greek Small Letter Phi): cp1253
    '\u03C6',
    # U+041A (Cyrillic Capital Letter Ka): cp1251
    '\u041A',
    # U+05D0 (Hebrew Letter Alef): Encodable to cp424
    '\u05D0',
    # U+060C (Arabic Comma): cp864, cp1006, iso8859_6, mac_arabic
    '\u060C',
    # U+062A (Arabic Letter Teh): cp720
    '\u062A',
    # U+0E01 (Thai Character Ko Kai): cp874
    '\u0E01',

    # Then try more "special" characters. "special" because they may be
    # interpreted or displayed differently depending on the exact locale
    # encoding and the font.

    # U+00A0 (No-Break Space)
    '\u00A0',
    # U+20AC (Euro Sign)
    '\u20AC',
):
    try:
        # If Python is set up to use the legacy 'mbcs' in Windows,
        # 'replace' error mode is used, and encode() returns b'?'
        # for characters missing in the ANSI codepage
        if os.fsdecode(os.fsencode(character)) != character:
            raise UnicodeError
    except UnicodeError:
        pass
    else:
        FS_NONASCII = character
        break

# TESTFN_UNICODE is a non-ascii filename
TESTFN_UNICODE = TESTFN + "-\xe0\xf2\u0258\u0141\u011f"
TESTFN_ENCODING = sys.getfilesystemencoding()

# TESTFN_UNENCODABLE is a filename (str type) that should *not* be able to be
# encoded by the filesystem encoding (in strict mode). It can be None if we
# cannot generate such filename.
TESTFN_UNENCODABLE = None

# TESTFN_UNDECODABLE is a filename (bytes type) that should *not* be able to be
# decoded from the filesystem encoding (in strict mode). It can be None if we
# cannot generate such filename (ex: the latin1 encoding can decode any byte
# sequence). On UNIX, TESTFN_UNDECODABLE can be decoded by os.fsdecode() thanks
# to the surrogateescape error handler (PEP 383), but not from the filesystem
# encoding in strict mode.
TESTFN_UNDECODABLE = None

if FS_NONASCII:
    TESTFN_NONASCII = TESTFN + '-' + FS_NONASCII
else:
    TESTFN_NONASCII = None

# Save the initial cwd
SAVEDCWD = os.getcwd()

# Set by libregrtest/main.py so we can skip tests that are not
# useful for PGO
PGO = False

@contextlib.contextmanager
def temp_dir(path=None, quiet=False):
    """Return a context manager that creates a temporary directory.

    Arguments:

      path: the directory to create temporarily.  If omitted or None,
        defaults to creating a temporary directory using tempfile.mkdtemp.

      quiet: if False (the default), the context manager raises an exception
        on error.  Otherwise, if the path is specified and cannot be
        created, only a warning is issued.

    """
    dir_created = False
    if path is None:
        path = tempfile.mkdtemp()
        dir_created = True
        path = os.path.realpath(path)
    else:
        try:
            os.mkdir(path)
            dir_created = True
        except OSError as exc:
            if not quiet:
                raise
            warnings.warn(f'tests may fail, unable to create temporary directory {path!r}: {exc}',
                          RuntimeWarning, stacklevel=3)
    if dir_created:
        pid = os.getpid()
    try:
        yield path
    finally:
        # In case the process forks, let only the parent remove the
        # directory. The child has a different process id. (bpo-30028)
        if dir_created and pid == os.getpid():
            rmtree(path)

@contextlib.contextmanager
def change_cwd(path, quiet=False):
    """Return a context manager that changes the current working directory.

    Arguments:

      path: the directory to use as the temporary current working directory.

      quiet: if False (the default), the context manager raises an exception
        on error.  Otherwise, it issues only a warning and keeps the current
        working directory the same.

    """
    saved_dir = os.getcwd()
    try:
        os.chdir(path)
    except OSError as exc:
        if not quiet:
            raise
        warnings.warn(f'tests may fail, unable to change the current working directory to {path!r}: {exc}',
                      RuntimeWarning, stacklevel=3)
    try:
        yield os.getcwd()
    finally:
        os.chdir(saved_dir)


@contextlib.contextmanager
def temp_cwd(name='tempcwd', quiet=False):
    """
    Context manager that temporarily creates and changes the CWD.

    The function temporarily changes the current working directory
    after creating a temporary directory in the current directory with
    name *name*.  If *name* is None, the temporary directory is
    created using tempfile.mkdtemp.

    If *quiet* is False (default) and it is not possible to
    create or change the CWD, an error is raised.  If *quiet* is True,
    only a warning is raised and the original CWD is used.

    """
    with temp_dir(path=name, quiet=quiet) as temp_path:
        with change_cwd(temp_path, quiet=quiet) as cwd_dir:
            yield cwd_dir

if hasattr(os, "umask"):
    @contextlib.contextmanager
    def temp_umask(umask):
        """Context manager that temporarily sets the process umask."""
        oldmask = os.umask(umask)
        try:
            yield
        finally:
            os.umask(oldmask)

# TEST_HOME_DIR refers to the top level directory of the "test" package
# that contains Python's regression test suite
TEST_SUPPORT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_HOME_DIR = os.path.dirname(TEST_SUPPORT_DIR)

# TEST_DATA_DIR is used as a target download location for remote resources
TEST_DATA_DIR = os.path.join(TEST_HOME_DIR, "data")

def findfile(filename, subdir=None):
    """Try to find a file on sys.path or in the test directory.  If it is not
    found the argument passed to the function is returned (this does not
    necessarily signal failure; could still be the legitimate path).

    Setting *subdir* indicates a relative path to use to find the file
    rather than looking directly in the path directories.
    """
    if os.path.isabs(filename):
        return filename
    if subdir is not None:
        filename = os.path.join(subdir, filename)
    path = [TEST_HOME_DIR] + sys.path
    for dn in path:
        fn = os.path.join(dn, filename)
        if os.path.exists(fn): return fn
    return filename

def create_empty_file(filename):
    """Create an empty file. If the file already exists, truncate it."""
    fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    os.close(fd)

def sortdict(dict):
    "Like repr(dict), but in sorted order."
    items = sorted(dict.items())
    reprpairs = ["%r: %r" % pair for pair in items]
    withcommas = ", ".join(reprpairs)
    return "{%s}" % withcommas

def make_bad_fd():
    """
    Create an invalid file descriptor by opening and closing a file and return
    its fd.
    """
    file = open(TESTFN, "wb")
    try:
        return file.fileno()
    finally:
        file.close()
        unlink(TESTFN)

def check_syntax_error(testcase, statement, *, lineno=None, offset=None):
    with testcase.assertRaises(SyntaxError) as cm:
        compile(statement, '<test string>', 'exec')
    err = cm.exception
    testcase.assertIsNotNone(err.lineno)
    if lineno is not None:
        testcase.assertEqual(err.lineno, lineno)
    testcase.assertIsNotNone(err.offset)
    if offset is not None:
        testcase.assertEqual(err.offset, offset)

def open_urlresource(url, *args, **kw):
    import urllib.request, urllib.parse

    check = kw.pop('check', None)

    filename = urllib.parse.urlparse(url)[2].split('/')[-1] # '/': it's URL!

    fn = os.path.join(TEST_DATA_DIR, filename)

    def check_valid_file(fn):
        f = open(fn, *args, **kw)
        if check is None:
            return f
        elif check(f):
            f.seek(0)
            return f
        f.close()

    if os.path.exists(fn):
        f = check_valid_file(fn)
        if f is not None:
            return f
        unlink(fn)

    # Verify the requirement before downloading the file
    requires('urlfetch')

    if verbose:
        print('\tfetching %s ...' % url, file=get_original_stdout())
    opener = urllib.request.build_opener()
    if gzip:
        opener.addheaders.append(('Accept-Encoding', 'gzip'))
    f = opener.open(url, timeout=15)
    if gzip and f.headers.get('Content-Encoding') == 'gzip':
        f = gzip.GzipFile(fileobj=f)
    try:
        with open(fn, "wb") as out:
            s = f.read()
            while s:
                out.write(s)
                s = f.read()
    finally:
        f.close()

    f = check_valid_file(fn)
    if f is not None:
        return f
    raise TestFailed('invalid resource %r' % fn)


class WarningsRecorder(object):
    """Convenience wrapper for the warnings list returned on
       entry to the warnings.catch_warnings() context manager.
    """
    def __init__(self, warnings_list):
        self._warnings = warnings_list
        self._last = 0

    def __getattr__(self, attr):
        if len(self._warnings) > self._last:
            return getattr(self._warnings[-1], attr)
        elif attr in warnings.WarningMessage._WARNING_DETAILS:
            return None
        raise AttributeError("%r has no attribute %r" % (self, attr))

    @property
    def warnings(self):
        return self._warnings[self._last:]

    def reset(self):
        self._last = len(self._warnings)


@contextlib.contextmanager
def check_warnings(*filters, **kwargs):
    """Context manager to silence warnings.

    Accept 2-tuples as positional arguments:
        ("message regexp", WarningCategory)

    Optional argument:
     - if 'quiet' is True, it does not fail if a filter catches nothing
        (default True without argument,
         default False if some filters are defined)

    Without argument, it defaults to:
        check_warnings(("", Warning), quiet=True)
    """
    yield


@contextlib.contextmanager
def check_no_resource_warning(testcase):
    """Context manager to check that no ResourceWarning is emitted.

    Usage:

        with check_no_resource_warning(self):
            f = open(...)
            ...
            del f

    You must remove the object which may emit ResourceWarning before
    the end of the context manager.
    """
    yield


class CleanImport(object):
    """Context manager to force import to return a new module reference.

    This is useful for testing module-level behaviours, such as
    the emission of a DeprecationWarning on import.

    Use like this:

        with CleanImport("foo"):
            importlib.import_module("foo") # new reference
    """

    def __init__(self, *module_names):
        self.original_modules = sys.modules.copy()
        for module_name in module_names:
            if module_name in sys.modules:
                module = sys.modules[module_name]
                # It is possible that module_name is just an alias for
                # another module (e.g. stub for modules renamed in 3.x).
                # In that case, we also need delete the real module to clear
                # the import cache.
                if module.__name__ != module_name:
                    del sys.modules[module.__name__]
                del sys.modules[module_name]

    def __enter__(self):
        return self

    def __exit__(self, *ignore_exc):
        sys.modules.update(self.original_modules)


class EnvironmentVarGuard(collections.abc.MutableMapping):

    """Class to help protect the environment variable properly.  Can be used as
    a context manager."""

    def __init__(self):
        self._environ = os.environ
        self._changed = {}

    def __getitem__(self, envvar):
        return self._environ[envvar]

    def __setitem__(self, envvar, value):
        # Remember the initial value on the first access
        if envvar not in self._changed:
            self._changed[envvar] = self._environ.get(envvar)
        self._environ[envvar] = value

    def __delitem__(self, envvar):
        # Remember the initial value on the first access
        if envvar not in self._changed:
            self._changed[envvar] = self._environ.get(envvar)
        if envvar in self._environ:
            del self._environ[envvar]

    def keys(self):
        return self._environ.keys()

    def __iter__(self):
        return iter(self._environ)

    def __len__(self):
        return len(self._environ)

    def set(self, envvar, value):
        self[envvar] = value

    def unset(self, envvar):
        del self[envvar]

    def __enter__(self):
        return self

    def __exit__(self, *ignore_exc):
        for (k, v) in self._changed.items():
            if v is None:
                if k in self._environ:
                    del self._environ[k]
            else:
                self._environ[k] = v
        # os.environ = self._environ


class DirsOnSysPath(object):
    """Context manager to temporarily add directories to sys.path.

    This makes a copy of sys.path, appends any directories given
    as positional arguments, then reverts sys.path to the copied
    settings when the context ends.

    Note that *all* sys.path modifications in the body of the
    context manager, including replacement of the object,
    will be reverted at the end of the block.
    """

    def __init__(self, *paths):
        self.original_value = sys.path[:]
        self.original_object = sys.path
        sys.path.extend(paths)

    def __enter__(self):
        return self

    def __exit__(self, *ignore_exc):
        sys.path = self.original_object
        sys.path[:] = self.original_value


# class TransientResource(object):

#     """Raise ResourceDenied if an exception is raised while the context manager
#     is in effect that matches the specified exception and attributes."""

#     def __init__(self, exc, **kwargs):
#         self.exc = exc
#         self.attrs = kwargs

#     def __enter__(self):
#         return self

#     def __exit__(self, type_=None, value=None, traceback=None):
#         """If type_ is a subclass of self.exc and value has attributes matching
#         self.attrs, raise ResourceDenied.  Otherwise let the exception
#         propagate (if any)."""
#         if type_ is not None and issubclass(self.exc, type_):
#             for attr, attr_value in self.attrs.items():
#                 if not hasattr(value, attr):
#                     break
#                 if getattr(value, attr) != attr_value:
#                     break
#             else:
#                 raise ResourceDenied("an optional resource is not available")

# # Context managers that raise ResourceDenied when various issues
# # with the Internet connection manifest themselves as exceptions.
# # XXX deprecate these and use transient_internet() instead
# time_out = TransientResource(OSError, errno=errno.ETIMEDOUT)
# socket_peer_reset = TransientResource(OSError, errno=errno.ECONNRESET)
# ioerror_peer_reset = TransientResource(OSError, errno=errno.ECONNRESET)


def get_socket_conn_refused_errs():
    """
    Get the different socket error numbers ('errno') which can be received
    when a connection is refused.
    """
    errors = [errno.ECONNREFUSED]
    if hasattr(errno, 'ENETUNREACH'):
        # On Solaris, ENETUNREACH is returned sometimes instead of ECONNREFUSED
        errors.append(errno.ENETUNREACH)
    if hasattr(errno, 'EADDRNOTAVAIL'):
        # bpo-31910: socket.create_connection() fails randomly
        # with EADDRNOTAVAIL on Travis CI
        errors.append(errno.EADDRNOTAVAIL)
    if hasattr(errno, 'EHOSTUNREACH'):
        # bpo-37583: The destination host cannot be reached
        errors.append(errno.EHOSTUNREACH)
    return errors


@contextlib.contextmanager
def transient_internet(resource_name, *, timeout=30.0, errnos=()):
    """Return a context manager that raises ResourceDenied when various issues
    with the Internet connection manifest themselves as exceptions."""
    default_errnos = [
        ('ECONNREFUSED', 111),
        ('ECONNRESET', 104),
        ('EHOSTUNREACH', 113),
        ('ENETUNREACH', 101),
        ('ETIMEDOUT', 110),
        # socket.create_connection() fails randomly with
        # EADDRNOTAVAIL on Travis CI.
        ('EADDRNOTAVAIL', 99),
    ]
    default_gai_errnos = [
        ('EAI_AGAIN', -3),
        ('EAI_FAIL', -4),
        ('EAI_NONAME', -2),
        ('EAI_NODATA', -5),
        # Encountered when trying to resolve IPv6-only hostnames
        ('WSANO_DATA', 11004),
    ]

    denied = ResourceDenied("Resource %r is not available" % resource_name)
    captured_errnos = errnos
    gai_errnos = []
    if not captured_errnos:
        captured_errnos = [getattr(errno, name, num)
                           for (name, num) in default_errnos]
        gai_errnos = [getattr(socket, name, num)
                      for (name, num) in default_gai_errnos]

    def filter_error(err):
        n = getattr(err, 'errno', None)
        if (isinstance(err, TimeoutError) or
            (isinstance(err, socket.gaierror) and n in gai_errnos) or
            # (isinstance(err, urllib.error.HTTPError) and
            #  500 <= err.code <= 599) or
            # (isinstance(err, urllib.error.URLError) and
            #      (("ConnectionRefusedError" in err.reason) or
            #       ("TimeoutError" in err.reason) or
            #       ("EOFError" in err.reason))) or
            n in captured_errnos):
            if not verbose:
                sys.stderr.write(denied.args[0] + "\n")
            raise denied from err

    old_timeout = socket.getdefaulttimeout()
    try:
        if timeout is not None:
            socket.setdefaulttimeout(timeout)
        yield
    except OSError as err:
        # urllib can wrap original socket errors multiple times (!), we must
        # unwrap to get at the original error.
        while True:
            a = err.args
            if len(a) >= 1 and isinstance(a[0], OSError):
                err = a[0]
            # The error can also be wrapped as args[1]:
            #    except socket.error as msg:
            #        raise OSError('socket error', msg).with_traceback(sys.exc_info()[2])
            elif len(a) >= 2 and isinstance(a[1], OSError):
                err = a[1]
            else:
                break
        filter_error(err)
        raise
    # XXX should we catch generic exceptions and look for their
    # __cause__ or __context__?
    finally:
        socket.setdefaulttimeout(old_timeout)


@skip_micropython
@contextlib.contextmanager
def captured_output(stream_name):
    """Return a context manager used by captured_stdout/stdin/stderr
    that temporarily replaces the sys stream *stream_name* with a StringIO."""
    import io
    orig_stdout = getattr(sys, stream_name)
    setattr(sys, stream_name, io.StringIO())
    try:
        yield getattr(sys, stream_name)
    finally:
        setattr(sys, stream_name, orig_stdout)

def captured_stdout():
    """Capture the output of sys.stdout:

       with captured_stdout() as stdout:
           print("hello")
       self.assertEqual(stdout.getvalue(), "hello\\n")
    """
    return captured_output("stdout")

def captured_stderr():
    """Capture the output of sys.stderr:

       with captured_stderr() as stderr:
           print("hello", file=sys.stderr)
       self.assertEqual(stderr.getvalue(), "hello\\n")
    """
    return captured_output("stderr")

def captured_stdin():
    """Capture the input to sys.stdin:

       with captured_stdin() as stdin:
           stdin.write('hello\\n')
           stdin.seek(0)
           # call test code that consumes from sys.stdin
           captured = input()
       self.assertEqual(captured, "hello")
    """
    return captured_output("stdin")


def gc_collect():
    """Force as many objects as possible to be collected.

    In non-CPython implementations of Python, this is needed because timely
    deallocation is not guaranteed by the garbage collector.  (Even in CPython
    this can be the case in case of reference cycles.)  This means that __del__
    methods may be called later than expected and weakrefs may remain alive for
    longer than expected.  This function tries its best to force all garbage
    objects to disappear.
    """
    gc.collect()

@contextlib.contextmanager
def disable_gc():
    have_gc = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if have_gc:
            gc.enable()

#=======================================================================
# Decorator for running a function in a different locale, correctly resetting
# it afterwards.

def run_with_locale(catstr, *locales):
    @skip_micropython
    def decorator(func):
        def inner(*args, **kwds):
            try:
                import locale
                category = getattr(locale, catstr)
                orig_locale = locale.setlocale(category)
            except AttributeError:
                # if the test author gives us an invalid category string
                raise
            except:
                # cannot retrieve original locale, so do nothing
                locale = orig_locale = None
            else:
                for loc in locales:
                    try:
                        locale.setlocale(category, loc)
                        break
                    except:
                        pass

            # now run the function, resetting the locale on exceptions
            try:
                return func(*args, **kwds)
            finally:
                if locale and orig_locale:
                    locale.setlocale(category, orig_locale)
        inner.__name__ = func.__name__
        inner.__doc__ = func.__doc__
        return inner
    return decorator

#=======================================================================
# Decorator for running a function in a specific timezone, correctly
# resetting it afterwards.

def run_with_tz(tz):
    def decorator(func):
        def inner(*args, **kwds):
            try:
                tzset = time.tzset
            except AttributeError:
                raise unittest.SkipTest("tzset required")
            if 'TZ' in os.environ:
                orig_tz = os.environ['TZ']
            else:
                orig_tz = None
            os.environ['TZ'] = tz
            tzset()

            # now run the function, resetting the tz on exceptions
            try:
                return func(*args, **kwds)
            finally:
                if orig_tz is None:
                    del os.environ['TZ']
                else:
                    os.environ['TZ'] = orig_tz
                time.tzset()

        inner.__name__ = func.__name__
        inner.__doc__ = func.__doc__
        return inner
    return decorator

#=======================================================================
# Big-memory-test support. Separate from 'resources' because memory use
# should be configurable.

# Some handy shorthands. Note that these are used for byte-limits as well
# as size-limits, in the various bigmem tests
_1M = 1024*1024
_1G = 1024 * _1M
_2G = 2 * _1G
_4G = 4 * _1G

MAX_Py_ssize_t = sys.maxsize

def set_memlimit(limit):
    global max_memuse
    global real_max_memuse
    sizes = {
        'k': 1024,
        'm': _1M,
        'g': _1G,
        't': 1024*_1G,
    }
    m = re.match(r'(\d+(\.\d+)?) (K|M|G|T)b?$', limit,
                 re.IGNORECASE | re.VERBOSE)
    if m is None:
        raise ValueError('Invalid memory limit %r' % (limit,))
    memlimit = int(float(m.group(1)) * sizes[m.group(3).lower()])
    real_max_memuse = memlimit
    if memlimit > MAX_Py_ssize_t:
        memlimit = MAX_Py_ssize_t
    if memlimit < _2G - 1:
        raise ValueError('Memory limit %r too low to be useful' % (limit,))
    max_memuse = memlimit

def bigmemtest(size, memuse, dry_run=True):
    """Decorator for bigmem tests.

    'size' is a requested size for the test (in arbitrary, test-interpreted
    units.) 'memuse' is the number of bytes per unit for the test, or a good
    estimate of it. For example, a test that needs two byte buffers, of 4 GiB
    each, could be decorated with @bigmemtest(size=_4G, memuse=2).

    The 'size' argument is normally passed to the decorated test method as an
    extra argument. If 'dry_run' is true, the value passed to the test method
    may be less than the requested value. If 'dry_run' is false, it means the
    test doesn't support dummy runs when -M is not specified.
    """
    def decorator(f):
        def wrapper(self):
            size = wrapper.size
            memuse = wrapper.memuse
            if not real_max_memuse:
                maxsize = 5147
            else:
                maxsize = size

            if ((real_max_memuse or not dry_run)
                and real_max_memuse < maxsize * memuse):
                raise unittest.SkipTest(
                    "not enough memory: %.1fG minimum needed"
                    % (size * memuse / (1024 ** 3)))

            if real_max_memuse and verbose:
                print()
                print(" ... expected peak memory use: {peak:.1f}G"
                      .format(peak=size * memuse / (1024 ** 3)))

            return f(self, maxsize)

        wrapper.size = size
        wrapper.memuse = memuse
        return wrapper
    return decorator

def bigaddrspacetest(f):
    """Decorator for tests that fill the address space."""
    def wrapper(self):
        if max_memuse < MAX_Py_ssize_t:
            if MAX_Py_ssize_t >= 2**63 - 1 and max_memuse >= 2**31:
                raise unittest.SkipTest(
                    "not enough memory: try a 32-bit build instead")
            else:
                raise unittest.SkipTest(
                    "not enough memory: %.1fG minimum needed"
                    % (MAX_Py_ssize_t / (1024 ** 3)))
        else:
            return f(self)
    return wrapper

#=======================================================================
# unittest integration.

class BasicTestRunner:
    def run(self, test):
        result = unittest.TestResult()
        test(result)
        return result

def _id(obj):
    return obj

def requires_resource(resource):
    if resource == 'gui' and not _is_gui_available():
        return unittest.skip(_is_gui_available.reason)
    if is_resource_enabled(resource):
        return _id
    else:
        return unittest.skip("resource {0!r} is not enabled".format(resource))

def cpython_only(test):
    """
    Decorator for tests only applicable on CPython.
    """
    return impl_detail(cpython=True)(test)

def impl_detail(msg=None, **guards):
    if check_impl_detail(**guards):
        return _id
    if msg is None:
        guardnames, default = _parse_guards(guards)
        if default:
            msg = "implementation detail not available on {0}"
        else:
            msg = "implementation detail specific to {0}"
        guardnames = sorted(guardnames.keys())
        msg = msg.format(' or '.join(guardnames))
    return unittest.skip(msg)

def _parse_guards(guards):
    # Returns a tuple ({platform_name: run_me}, default_value)
    if not guards:
        return ({'cpython': True}, False)
    is_true = list(guards.values())[0]
    assert list(guards.values()) == [is_true] * len(guards)   # all True or all False
    return (guards, not is_true)

# Use the following check to guard CPython's implementation-specific tests --
# or to run them only on the implementation(s) guarded by the arguments.
def check_impl_detail(**guards):
    """This function returns True or False depending on the host platform.
       Examples:
          if check_impl_detail():               # only on CPython (default)
          if check_impl_detail(jython=True):    # only on Jython
          if check_impl_detail(cpython=False):  # everywhere except on CPython
    """
    guards, default = _parse_guards(guards)
    return guards.get('micropython', default)


def no_tracing(func):
    """Decorator to temporarily turn off tracing for the duration of a test."""
    if not hasattr(sys, 'gettrace'):
        return func
    else:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            original_trace = sys.gettrace()
            try:
                sys.settrace(None)
                return func(*args, **kwargs)
            finally:
                sys.settrace(original_trace)
        return wrapper


def refcount_test(test):
    """Decorator for tests which involve reference counting.

    To start, the decorator does not run the test if is not run by CPython.
    After that, any trace function is unset during the test to prevent
    unexpected refcounts caused by the trace function.

    """
    return no_tracing(cpython_only(test))


def _filter_suite(suite, pred):
    """Recursively filter test cases in a suite based on a predicate."""
    newtests = []
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            _filter_suite(test, pred)
            newtests.append(test)
        else:
            if pred(test):
                newtests.append(test)
    suite.__init__(newtests)

def _run_suite(suite):
    """Run tests from a unittest.TestSuite-derived class."""
    runner = get_test_runner(sys.stdout,
                             verbosity=verbose,
                             capture_output=False)

    result = runner.run(suite)

    if not result.testsRun and not result.skipped:
        raise TestDidNotRun
    if not result.wasSuccessful():
        if len(result.errors) == 1 and not result.failures:
            err = result.errors[0][1]
        elif len(result.failures) == 1 and not result.errors:
            err = result.failures[0][1]
        else:
            err = "multiple errors occurred"
            if not verbose: err += "; run in verbose mode for details"
        raise TestFailed(err)


# By default, don't filter tests
_match_test_func = None

_accept_test_patterns = None
_ignore_test_patterns = None


def match_test(test):
    # Function used by support.run_unittest() and regrtest --list-cases
    if _match_test_func is None:
        return True
    else:
        return _match_test_func(test.id())


def run_unittest(*classes):
    """Run tests from unittest.TestCase-derived classes."""
    valid_types = (unittest.TestSuite, unittest.TestCase)
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    for cls in classes:
        if isinstance(cls, str):
            if cls in sys.modules:
                suite.addTest(loader.loadTestsFromModule(sys.modules[cls]))
            else:
                raise ValueError("str arguments must be keys in sys.modules")
        elif isinstance(cls, valid_types):
            suite.addTest(cls)
        else:
            suite.addTest(loader.loadTestsFromTestCase(cls))
    _filter_suite(suite, match_test)
    _run_suite(suite)

#=======================================================================
# Check for the presence of docstrings.

# Rather than trying to enumerate all the cases where docstrings may be
# disabled, we just check for that directly

MISSING_C_DOCSTRINGS = True

HAVE_DOCSTRINGS = False

requires_docstrings = unittest.skipUnless(HAVE_DOCSTRINGS,
                                          "test requires docstrings")


#=======================================================================
# doctest driver.

def run_doctest(module, verbosity=None, optionflags=0):
    """Run doctest on the given module.  Return (#failures, #tests).

    If optional argument verbosity is not specified (or is None), pass
    support's belief about verbosity on to doctest.  Else doctest's
    usual behavior is used (it searches sys.argv for -v).
    """

    import doctest

    if verbosity is None:
        verbosity = verbose
    else:
        verbosity = None

    f, t = doctest.testmod(module, verbose=verbosity, optionflags=optionflags)
    if f:
        raise TestFailed("%d of %d doctests failed" % (f, t))
    if verbose:
        print('doctest (%s) ... %d tests with zero failures' %
              (module.__name__, t))
    return f, t


#=======================================================================
# Support for saving and restoring the imported modules.

def modules_setup():
    return sys.modules.copy(),

def modules_cleanup(oldmodules):
    # Encoders/decoders are registered permanently within the internal
    # codec cache. If we destroy the corresponding modules their
    # globals will be set to None which will trip up the cached functions.
    encodings = [(k, v) for k, v in sys.modules.items()
                 if k.startswith('encodings.')]
    sys.modules.clear()
    sys.modules.update(encodings)
    # XXX: This kind of problem can affect more than just encodings. In particular
    # extension modules (such as _ssl) don't cope with reloading properly.
    # Really, test modules should be cleaning out the test specific modules they
    # know they added (ala test_runpy) rather than relying on this function (as
    # test_importhooks and test_pkg do currently).
    # Implicitly imported *real* modules should be left alone (see issue 10556).
    sys.modules.update(oldmodules)

#=======================================================================
# Threading support to prevent reporting refleaks when running regrtest.py -R

# Flag used by saved_test_environment of test.libregrtest.save_env,
# to check if a test modified the environment. The flag should be set to False
# before running a new test.
#
# For example, threading_cleanup() sets the flag is the function fails
# to cleanup threads.
environment_altered = False

# NOTE: we use thread._count() rather than threading.enumerate() (or the
# moral equivalent thereof) because a threading.Thread object is still alive
# until its __bootstrap() method has returned, even after it has been
# unregistered from the threading module.
# thread._count(), on the other hand, only gets decremented *after* the
# __bootstrap() method has returned, which gives us reliable reference counts
# at the end of a test run.

def threading_setup():
    return {t for t in threading.enumerate() if t.is_alive()}

def threading_cleanup(*original_values):
    global environment_altered
    original_values = set(original_values)

    _MAX_COUNT = 100

    for count in range(_MAX_COUNT):
        values = threading_setup()
        if values == original_values:
            break

        if not count:
            # Display a warning at the first iteration
            environment_altered = True
            dangling_threads = values - original_values
            print("Warning -- threading_cleanup() failed to cleanup "
                  "%s threads (count: %s, dangling: %s)"
                  % (len(values) - len(original_values),
                     len(values), len(dangling_threads)),
                  file=sys.stderr)
            for thread in dangling_threads:
                print(f"Dangling thread: {thread!r}", file=sys.stderr)
            sys.stderr.flush()

            # Don't hold references to threads
            dangling_threads = None
        values = None

        time.sleep(0.01)
        gc_collect()


def reap_threads(func):
    """Use this function when threads are being used.  This will
    ensure that the threads are cleaned up even when the test fails.
    """
    @functools.wraps(func)
    def decorator(*args):
        key = threading_setup()
        try:
            return func(*args)
        finally:
            threading_cleanup(*key)
    return decorator


@contextlib.contextmanager
def wait_threads_exit(timeout=60.0):
    """
    bpo-31234: Context manager to wait until all threads created in the with
    statement exit.

    Use _thread.count() to check if threads exited. Indirectly, wait until
    threads exit the internal t_bootstrap() C function of the _thread module.

    threading_setup() and threading_cleanup() are designed to emit a warning
    if a test leaves running threads in the background. This context manager
    is designed to cleanup threads started by the _thread.start_new_thread()
    which doesn't allow to wait for thread exit, whereas thread.Thread has a
    join() method.
    """
    old_count = threading_setup()
    try:
        yield
    finally:
        start_time = time.monotonic()
        deadline = start_time + timeout
        while True:
            count = threading_setup()
            if count <= old_count:
                break
            if time.monotonic() > deadline:
                dt = time.monotonic() - start_time
                msg = (f"wait_threads() failed to cleanup {count - old_count} threads after {dt:.1f} seconds (count: {count}, old count: {old_count})")
                raise AssertionError(msg)
            time.sleep(0.010)
            gc_collect()


def join_thread(thread, timeout=30.0):
    """Join a thread. Raise an AssertionError if the thread is still alive
    after timeout seconds.
    """
    thread.join(timeout)
    if thread.is_alive():
        msg = f"failed to join the thread in {timeout:.1f} seconds"
        raise AssertionError(msg)


def reap_children():
    """Use this function at the end of test_main() whenever sub-processes
    are started.  This will help ensure that no extra children (zombies)
    stick around to hog resources and create problems when looking
    for refleaks.
    """
    global environment_altered

    # Need os.waitpid(-1, os.WNOHANG): Windows is not supported
    if not (hasattr(os, 'waitpid') and hasattr(os, 'WNOHANG')):
        return

    # Reap all our dead child processes so we don't leave zombies around.
    # These hog resources and might be causing some of the buildbots to die.
    while True:
        try:
            # Read the exit status of any child process which already completed
            pid, status = os.waitpid(-1, os.WNOHANG)
        except OSError:
            break

        if pid == 0:
            break

        print("Warning -- reap_children() reaped child process %s"
              % pid, file=sys.stderr)
        environment_altered = True


@contextlib.contextmanager
def start_threads(threads, unlock=None):
    threads = list(threads)
    started = []
    try:
        try:
            for t in threads:
                t.start()
                started.append(t)
        except:
            if verbose:
                print("Can't start %d threads, only %d threads started" %
                      (len(threads), len(started)))
            raise
        yield
    finally:
        try:
            if unlock:
                unlock()
            endtime = starttime = time.monotonic()
            for timeout in range(1, 16):
                endtime += 60
                for t in started:
                    t.join(max(endtime - time.monotonic(), 0.01))
                started = [t for t in started if t.is_alive()]
                if not started:
                    break
                if verbose:
                    print('Unable to join %d threads during a period of '
                          '%d minutes' % (len(started), timeout))
        finally:
            started = [t for t in started if t.is_alive()]
            if started:
                raise AssertionError('Unable to join %d threads' % len(started))

@contextlib.contextmanager
def swap_attr(obj, attr, new_val):
    """Temporary swap out an attribute with a new object.

    Usage:
        with swap_attr(obj, "attr", 5):
            ...

        This will set obj.attr to 5 for the duration of the with: block,
        restoring the old value at the end of the block. If `attr` doesn't
        exist on `obj`, it will be created and then deleted at the end of the
        block.

        The old value (or None if it doesn't exist) will be assigned to the
        target of the "as" clause, if there is one.
    """
    if hasattr(obj, attr):
        real_val = getattr(obj, attr)
        setattr(obj, attr, new_val)
        try:
            yield real_val
        finally:
            setattr(obj, attr, real_val)
    else:
        setattr(obj, attr, new_val)
        try:
            yield
        finally:
            if hasattr(obj, attr):
                delattr(obj, attr)

@contextlib.contextmanager
def swap_item(obj, item, new_val):
    """Temporary swap out an item with a new object.

    Usage:
        with swap_item(obj, "item", 5):
            ...

        This will set obj["item"] to 5 for the duration of the with: block,
        restoring the old value at the end of the block. If `item` doesn't
        exist on `obj`, it will be created and then deleted at the end of the
        block.

        The old value (or None if it doesn't exist) will be assigned to the
        target of the "as" clause, if there is one.
    """
    if item in obj:
        real_val = obj[item]
        obj[item] = new_val
        try:
            yield real_val
        finally:
            obj[item] = real_val
    else:
        obj[item] = new_val
        try:
            yield
        finally:
            if item in obj:
                del obj[item]

#============================================================
# Support for assertions about logging.
#============================================================

# class TestHandler(logging.handlers.BufferingHandler):
#     def __init__(self, matcher):
#         # BufferingHandler takes a "capacity" argument
#         # so as to know when to flush. As we're overriding
#         # shouldFlush anyway, we can set a capacity of zero.
#         # You can call flush() manually to clear out the
#         # buffer.
#         logging.handlers.BufferingHandler.__init__(self, 0)
#         self.matcher = matcher

#     def shouldFlush(self):
#         return False

#     def emit(self, record):
#         self.format(record)
#         self.buffer.append(record.__dict__)

#     def matches(self, **kwargs):
#         """
#         Look for a saved dict whose keys/values match the supplied arguments.
#         """
#         result = False
#         for d in self.buffer:
#             if self.matcher.matches(d, **kwargs):
#                 result = True
#                 break
#         return result

class Matcher(object):

    _partial_matches = ('msg', 'message')

    def matches(self, d, **kwargs):
        """
        Try to match a single dict with the supplied arguments.

        Keys whose values are strings and which are in self._partial_matches
        will be checked for partial (i.e. substring) matches. You can extend
        this scheme to (for example) do regular expression matching, etc.
        """
        result = True
        for k in kwargs:
            v = kwargs[k]
            dv = d.get(k)
            if not self.match_value(k, dv, v):
                result = False
                break
        return result

    def match_value(self, k, dv, v):
        """
        Try to match a single stored value (dv) with a supplied value (v).
        """
        if type(v) != type(dv):
            result = False
        elif type(dv) is not str or k not in self._partial_matches:
            result = (v == dv)
        else:
            result = dv.find(v) >= 0
        return result


_can_symlink = None
def can_symlink():
    global _can_symlink
    if _can_symlink is not None:
        return _can_symlink
    symlink_path = TESTFN + "can_symlink"
    try:
        os.symlink(TESTFN, symlink_path)
        can = True
    except (OSError, NotImplementedError, AttributeError):
        can = False
    else:
        os.remove(symlink_path)
    _can_symlink = can
    return can

def skip_unless_symlink(test):
    """Skip decorator for tests that require functional symlink"""
    ok = can_symlink()
    msg = "Requires functional symlink implementation"
    return test if ok else unittest.skip(msg)(test)

_can_xattr = None
def can_xattr():
    global _can_xattr
    if _can_xattr is not None:
        return _can_xattr
    if not hasattr(os, "setxattr"):
        can = False
    else:
        tmp_dir = tempfile.mkdtemp()
        tmp_fp, tmp_name = tempfile.mkstemp(dir=tmp_dir)
        try:
            with open(TESTFN, "wb") as fp:
                try:
                    # TESTFN & tempfile may use different file systems with
                    # different capabilities
                    os.setxattr(tmp_fp, b"user.test", b"")
                    os.setxattr(tmp_name, b"trusted.foo", b"42")
                    os.setxattr(fp.fileno(), b"user.test", b"")
                    # Kernels < 2.6.39 don't respect setxattr flags.
                    kernel_version = platform.release()
                    m = re.match(r"2.6.(\d{1,2})", kernel_version)
                    can = m is None or int(m.group(1)) >= 39
                except OSError:
                    can = False
        finally:
            unlink(TESTFN)
            unlink(tmp_name)
            rmdir(tmp_dir)
    _can_xattr = can
    return can

def skip_unless_xattr(test):
    """Skip decorator for tests that require functional extended attributes"""
    ok = can_xattr()
    msg = "no non-broken extended attribute support"
    return test if ok else unittest.skip(msg)(test)

_bind_nix_socket_error = None
def skip_unless_bind_unix_socket(test):
    """Decorator for tests requiring a functional bind() for unix sockets."""
    if not hasattr(socket, 'AF_UNIX'):
        return unittest.skip('No UNIX Sockets')(test)
    global _bind_nix_socket_error
    if _bind_nix_socket_error is None:
        path = TESTFN + "can_bind_unix_socket"
        with socket.socket(socket.AF_UNIX) as sock:
            try:
                sock.bind(path)
                _bind_nix_socket_error = False
            except OSError as e:
                _bind_nix_socket_error = e
            finally:
                unlink(path)
    if _bind_nix_socket_error:
        msg = 'Requires a functional unix bind(): %s' % _bind_nix_socket_error
        return unittest.skip(msg)(test)
    else:
        return test


def fs_is_case_insensitive(directory):
    """Detects if the file system for the specified directory is case-insensitive."""
    with tempfile.NamedTemporaryFile(dir=directory) as base:
        base_path = base.name
        case_path = base_path.upper()
        if case_path == base_path:
            case_path = base_path.lower()
        try:
            return os.path.samefile(base_path, case_path)
        except FileNotFoundError:
            return False


def detect_api_mismatch(ref_api, other_api, *, ignore=()):
    """Returns the set of items in ref_api not in other_api, except for a
    defined list of items to be ignored in this check.

    By default this skips private attributes beginning with '_' but
    includes all magic methods, i.e. those starting and ending in '__'.
    """
    missing_items = set(dir(ref_api)) - set(dir(other_api))
    if ignore:
        missing_items -= set(ignore)
    missing_items = set(m for m in missing_items
                        if not m.startswith('_') or m.endswith('__'))
    return missing_items


def check__all__(test_case, module, name_of_module=None, extra=(),
                 blacklist=()):
    """Assert that the __all__ variable of 'module' contains all public names.

    The module's public names (its API) are detected automatically based on
    whether they match the public name convention and were defined in
    'module'.

    The 'name_of_module' argument can specify (as a string or tuple thereof)
    what module(s) an API could be defined in in order to be detected as a
    public API. One case for this is when 'module' imports part of its public
    API from other modules, possibly a C backend (like 'csv' and its '_csv').

    The 'extra' argument can be a set of names that wouldn't otherwise be
    automatically detected as "public", like objects without a proper
    '__module__' attribute. If provided, it will be added to the
    automatically detected ones.

    The 'blacklist' argument can be a set of names that must not be treated
    as part of the public API even though their names indicate otherwise.

    Usage:
        import bar
        import foo
        import unittest
        from test import support

        class MiscTestCase(unittest.TestCase):
            def test__all__(self):
                support.check__all__(self, foo)

        class OtherTestCase(unittest.TestCase):
            def test__all__(self):
                extra = {'BAR_CONST', 'FOO_CONST'}
                blacklist = {'baz'}  # Undocumented name.
                # bar imports part of its API from _bar.
                support.check__all__(self, bar, ('bar', '_bar'),
                                     extra=extra, blacklist=blacklist)

    """

    if name_of_module is None:
        name_of_module = (module.__name__, )
    elif isinstance(name_of_module, str):
        name_of_module = (name_of_module, )

    expected = set(extra)

    for name in dir(module):
        if name.startswith('_') or name in blacklist:
            continue
        obj = getattr(module, name)
        if (getattr(obj, '__module__', None) in name_of_module or
                (not hasattr(obj, '__module__') and
                 not isinstance(obj, types.ModuleType))):
            expected.add(name)
    test_case.assertCountEqual(module.__all__, expected)


class SuppressCrashReport:
    """Try to prevent a crash report from popping up.
    """
    def __enter__(self):
        return self

    def __exit__(self, *ignore_exc):
        pass


def patch(test_instance, object_to_patch, attr_name, new_value):
    """Override 'object_to_patch'.'attr_name' with 'new_value'.

    Also, add a cleanup procedure to 'test_instance' to restore
    'object_to_patch' value for 'attr_name'.
    The 'attr_name' should be a valid attribute for 'object_to_patch'.

    """
    # check that 'attr_name' is a real attribute for 'object_to_patch'
    # will raise AttributeError if it does not exist
    getattr(object_to_patch, attr_name)

    # keep a copy of the old value
    attr_is_local = False
    try:
        old_value = object_to_patch.__dict__[attr_name]
    except (AttributeError, KeyError):
        old_value = getattr(object_to_patch, attr_name, None)
    else:
        attr_is_local = True

    # restore the value when the test is done
    def cleanup():
        if attr_is_local:
            setattr(object_to_patch, attr_name, old_value)
        else:
            delattr(object_to_patch, attr_name)

    test_instance.addCleanup(cleanup)

    # actually override the attribute
    setattr(object_to_patch, attr_name, new_value)


def run_in_subinterp(code):
    """
    Run code in a subinterpreter. Raise unittest.SkipTest if the tracemalloc
    module is enabled.
    """
    # Issue #10915, #15751: PyGILState_*() functions don't work with
    # sub-interpreters, the tracemalloc module uses these functions internally
    try:
        import tracemalloc
    except ImportError:
        pass
    else:
        if tracemalloc.is_tracing():
            raise unittest.SkipTest("run_in_subinterp() cannot be used "
                                     "if tracemalloc module is tracing "
                                     "memory allocations")
    import _testcapi
    return _testcapi.run_in_subinterp(code)


def check_free_after_iterating(test, iter, cls, args=()):
    class A(cls):
        def __del__(self):
            nonlocal done
            done = True
            try:
                next(it)
            except StopIteration:
                pass

    done = False
    it = iter(A(*args))
    # Issue 26494: Shouldn't crash
    test.assertRaises(StopIteration, next, it)
    # The sequence should be deallocated just after the end of iterating
    gc_collect()
    test.assertTrue(done)


def setswitchinterval(interval):
    # Setting a very low gil interval on the Android emulator causes python
    # to hang (issue #26939).
    return sys.setswitchinterval(interval)


@contextlib.contextmanager
def disable_faulthandler():
    try:
        yield
    finally:
        pass

def fd_count():
    """Count the number of open file descriptors.
    """
    MAXFD = 256
    if hasattr(os, 'sysconf'):
        try:
            MAXFD = os.sysconf("SC_OPEN_MAX")
        except OSError:
            pass

    try:
        count = 0
        for fd in range(MAXFD):
            try:
                # Prefer dup() over fstat(). fstat() can require input/output
                # whereas dup() doesn't.
                fd2 = os.dup(fd)
            except OSError as e:
                if e.errno != errno.EBADF:
                    raise
            else:
                os.close(fd2)
                count += 1
    finally:
        pass

    return count


class SaveSignals:
    """
    Save an restore signal handlers.

    This class is only able to save/restore signal handlers registered
    by the Python signal module: see bpo-13285 for "external" signal
    handlers.
    """

    def __init__(self):
        import signal
        self.signal = signal
        self.signals = list(range(1, signal.NSIG))
        # SIGKILL and SIGSTOP signals cannot be ignored nor caught
        for signame in ('SIGKILL', 'SIGSTOP'):
            try:
                signum = getattr(signal, signame)
            except AttributeError:
                continue
            self.signals.remove(signum)
        self.handlers = {}

    def save(self):
        for signum in self.signals:
            handler = self.signal.getsignal(signum)
            if handler is None:
                # getsignal() returns None if a signal handler was not
                # registered by the Python signal module,
                # and the handler is not SIG_DFL nor SIG_IGN.
                #
                # Ignore the signal: we cannot restore the handler.
                continue
            self.handlers[signum] = handler

    def restore(self):
        for signum, handler in self.handlers.items():
            self.signal.signal(signum, handler)


def with_pymalloc():
    import _testcapi
    return _testcapi.WITH_PYMALLOC


@unittest.skipUnless(hasattr(os, 'PathLike'), 'needs path protocol')
class FakePath:
    """Simple implementing of the path protocol.
    """
    def __init__(self, path):
        self.path = path

    def __repr__(self):
        return f'<FakePath {self.path!r}>'

    def __fspath__(self):
        if (isinstance(self.path, BaseException) or
            isinstance(self.path, type) and
                issubclass(self.path, BaseException)):
            raise self.path
        else:
            return self.path


class _ALWAYS_EQ:
    __immutable__ = True
    """
    Object that is equal to anything.
    """
    def __eq__(self, other):
        return True
    def __ne__(self, other):
        return False

ALWAYS_EQ = _ALWAYS_EQ()

class _LARGEST:
    __immutable__ = True
    """
    Object that is greater than anything (except itself).
    """
    def __eq__(self, other):
        return isinstance(other, _LARGEST)
    def __ne__(self, other):
        return not isinstance(other, _LARGEST)    
    def __lt__(self, other):
        return False
    def __le__(self, other):
        return self.__eq__(other)
    def __gt__(self, other):
        return self.__ne__(other)
    def __ge__(self, other):
        return True

LARGEST = _LARGEST()

class _SMALLEST:
    __immutable__ = True
    """
    Object that is less than anything (except itself).
    """
    def __eq__(self, other):
        return isinstance(other, _SMALLEST)
    def __ne__(self, other):
        return not isinstance(other, _SMALLEST)    
    def __lt__(self, other):
        return self.__ne__(other)
    def __le__(self, other):
        return True
    def __gt__(self, other):
        return False
    def __ge__(self, other):
        return self.__eq__(other)
SMALLEST = _SMALLEST()

@contextlib.contextmanager
def adjust_int_max_str_digits(max_digits):
    """Temporarily change the integer string conversion length limit."""
    current = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(max_digits)
        yield
    finally:
        sys.set_int_max_str_digits(current)