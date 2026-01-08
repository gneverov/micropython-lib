# As a test suite for the os module, this is woefully inadequate, but this
# does add tests for a few functions which have been determined to be more
# portable than they had been thought to be.

import errno
import itertools
import os
try:
    import pickle
except ImportError:
    pickle = None
import shutil
import stat
import sys
import time
import unittest
from test import support

try:
    import pwd
    all_users = [u.pw_uid for u in pwd.getpwall()]
except (ImportError, AttributeError):
    all_users = []

from test.support import unix_shell, FakePath


root_in_posix = False
if hasattr(os, 'geteuid'):
    root_in_posix = (os.geteuid() == 0)


def create_file(filename, content=b'content'):
    with open(filename, "xb", 0) as fp:
        fp.write(content)

def needs_file_modes():
    return unittest.skipUnless(hasattr(os, 'chmod'), "Test needs file modes")

# Tests creating TESTFN
class FileTests(unittest.TestCase):
    def setUp(self):
        if os.path.lexists(support.TESTFN):
            os.unlink(support.TESTFN)
    tearDown = setUp

    @needs_file_modes()
    def test_access(self):
        f = os.open(support.TESTFN, os.O_CREAT|os.O_RDWR)
        os.close(f)
        self.assertTrue(os.access(support.TESTFN, os.W_OK))

    @unittest.skipUnless(hasattr(os, 'closerange'), "Test needs os.closerange()")
    def test_closerange(self):
        first = os.open(support.TESTFN, os.O_CREAT|os.O_RDWR)
        # We must allocate two consecutive file descriptors, otherwise
        # it will mess up other file descriptors (perhaps even the three
        # standard ones).
        second = os.dup(first)
        try:
            retries = 0
            while second != first + 1:
                os.close(first)
                retries += 1
                if retries > 10:
                    # XXX test skipped
                    self.skipTest("couldn't allocate two consecutive fds")
                first, second = second, os.dup(second)
        finally:
            os.close(second)
        # close a fd that is open, and one that isn't
        os.closerange(first, first + 2)
        self.assertRaises(OSError, os.write, first, b"a")

    def test_read(self):
        with open(support.TESTFN, "w+b") as fobj:
            fobj.write(b"spam")
            fobj.flush()
            fd = fobj.fileno()
            os.lseek(fd, 0, 0)
            s = os.read(fd, 4)
            self.assertEqual(type(s), bytes)
            self.assertEqual(s, b"spam")

    def test_write(self):
        # os.write() accepts bytes- and buffer-like objects but not strings
        fd = os.open(support.TESTFN, os.O_CREAT | os.O_WRONLY)
        self.assertRaises(TypeError, os.write, fd, "beans")
        os.write(fd, b"bacon\n")
        os.write(fd, bytearray(b"eggs\n"))
        os.write(fd, memoryview(b"spam\n"))
        os.close(fd)
        with open(support.TESTFN, "rb") as fobj:
            self.assertEqual(fobj.read().splitlines(),
                [b"bacon", b"eggs", b"spam"])

    def fdopen_helper(self, *args):
        fd = os.open(support.TESTFN, os.O_RDONLY)
        f = os.fdopen(fd, *args)
        f.close()

    def test_fdopen(self):
        fd = os.open(support.TESTFN, os.O_CREAT|os.O_RDWR)
        os.close(fd)

        self.fdopen_helper()
        self.fdopen_helper('r')
        self.fdopen_helper('r', 100)

    def test_replace(self):
        TESTFN2 = support.TESTFN + ".2"
        self.addCleanup(support.unlink, support.TESTFN)
        self.addCleanup(support.unlink, TESTFN2)

        create_file(support.TESTFN, b"1")
        create_file(TESTFN2, b"2")

        os.replace(support.TESTFN, TESTFN2)
        self.assertRaises(FileNotFoundError, os.stat, support.TESTFN)
        with open(TESTFN2, 'r') as f:
            self.assertEqual(f.read(), "1")

    def test_open_keywords(self):
        dir_fd = {}
        if os.open in os.supports_dir_fd:
            dir_fd = { 'dir_fd': None }
        f = os.open(path=__file__, flags=os.O_RDONLY, mode=0o777,
            **dir_fd)
        os.close(f)

    def test_symlink_keywords(self):
        symlink = support.get_attribute(os, "symlink")
        try:
            symlink(src='target', dst=support.TESTFN,
                target_is_directory=False, dir_fd=None)
        except (NotImplementedError, OSError):
            pass  # No OS support or unprivileged user


# Test attributes on return values from os.*stat* family.
class StatAttributeTests(unittest.TestCase):
    def setUp(self):
        self.fname = support.TESTFN
        self.addCleanup(support.unlink, self.fname)
        create_file(self.fname, b"ABC")

    @unittest.skipUnless(hasattr(os, 'stat'), 'test needs os.stat()')
    def check_stat_attributes(self, fname):
        result = os.stat(fname)

        # Make sure direct access works
        self.assertEqual(result[stat.ST_SIZE], 3)
        self.assertEqual(result.st_size, 3)

        # Make sure all the attributes are there
        members = dir(result)
        for name in dir(stat):
            if name[:3] == 'ST_':
                attr = name.lower()
                if name.endswith("TIME"):
                    def trunc(x): return int(x)
                else:
                    def trunc(x): return x
                self.assertEqual(trunc(getattr(result, attr)),
                                  result[getattr(stat, name)])
                self.assertIn(attr, members)

        # Make sure that the st_?time and st_?time_ns fields roughly agree
        # (they should always agree up to around tens-of-microseconds)
        for name in 'st_atime st_mtime st_ctime'.split():
            floaty = int(getattr(result, name) * 100000)
            nanosecondy = getattr(result, name + "_ns") // 10000
            self.assertAlmostEqual(floaty, nanosecondy, delta=2)

        try:
            result[200]
            self.fail("No exception raised")
        except IndexError:
            pass

        # Make sure that assignment fails
        try:
            result.st_mode = 1
            self.fail("No exception raised")
        except AttributeError:
            pass

        try:
            result.st_rdev = 1
            self.fail("No exception raised")
        except (AttributeError, TypeError):
            pass

        try:
            result.parrot = 1
            self.fail("No exception raised")
        except AttributeError:
            pass

    def test_stat_attributes(self):
        self.check_stat_attributes(self.fname)

    def test_stat_attributes_bytes(self):
        try:
            fname = self.fname.encode(sys.getfilesystemencoding())
        except UnicodeEncodeError:
            self.skipTest("cannot encode %a for the filesystem" % self.fname)
        self.check_stat_attributes(fname)

    @unittest.skipUnless(pickle, 'test needs pickle')
    def test_stat_result_pickle(self):
        result = os.stat(self.fname)
        for proto in range(pickle.HIGHEST_PROTOCOL + 1):
            p = pickle.dumps(result, proto)
            self.assertIn(b'stat_result', p)
            if proto < 4:
                self.assertIn(b'cos\nstat_result\n', p)
            unpickled = pickle.loads(p)
            self.assertEqual(result, unpickled)

    @unittest.skipUnless(hasattr(os, 'statvfs'), 'test needs os.statvfs()')
    def test_statvfs_attributes(self):
        result = os.statvfs(self.fname)

        # Make sure direct access works
        self.assertEqual(result.f_bfree, result[3])

        # Make sure all the attributes are there.
        members = ('bsize', 'frsize', 'blocks', 'bfree', 'bavail', 'files',
                    'ffree', 'favail', 'flag', 'namemax')
        for value, member in enumerate(members):
            self.assertEqual(getattr(result, 'f_' + member), result[value])

        # self.assertTrue(isinstance(result.f_fsid, int))

        # Test that the size of the tuple doesn't change
        self.assertEqual(len(result), 10)

        # Make sure that assignment really fails
        try:
            result.f_bfree = 1
            self.fail("No exception raised")
        except AttributeError:
            pass

        try:
            result.parrot = 1
            self.fail("No exception raised")
        except AttributeError:
            pass

    @unittest.skipUnless(hasattr(os, 'statvfs'),
                         "need os.statvfs()")
    @unittest.skipUnless(pickle, "need pickle")
    def test_statvfs_result_pickle(self):
        result = os.statvfs(self.fname)

        for proto in range(pickle.HIGHEST_PROTOCOL + 1):
            p = pickle.dumps(result, proto)
            self.assertIn(b'statvfs_result', p)
            if proto < 4:
                self.assertIn(b'cos\nstatvfs_result\n', p)
            unpickled = pickle.loads(p)
            self.assertEqual(result, unpickled)


class UtimeTests(unittest.TestCase):
    def setUp(self):
        self.dirname = support.TESTFN
        self.fname = os.path.join(self.dirname, "f1")

        self.addCleanup(support.rmtree, self.dirname)
        os.mkdir(self.dirname)
        create_file(self.fname)

    def support_subsecond(self, filename):
        # Heuristic to check if the filesystem supports timestamp with
        # subsecond resolution: check if float and int timestamps are different
        st = os.stat(filename)
        return ((st.st_atime != st[7])
                or (st.st_mtime != st[8])
                or (st.st_ctime != st[9]))

    def _test_utime(self, set_time, filename=None):
        if not filename:
            filename = self.fname

        support_subsecond = self.support_subsecond(filename)
        if support_subsecond:
            # Timestamp with a resolution of 1 microsecond (10^-6).
            #
            # The resolution of the C internal function used by os.utime()
            # depends on the platform: 1 sec, 1 us, 1 ns. Writing a portable
            # test with a resolution of 1 ns requires more work:
            # see the issue #15745.
            atime_ns = 1002003000   # 1.002003 seconds
            mtime_ns = 4005006000   # 4.005006 seconds
        else:
            # use a resolution of 1 second
            atime_ns = time.mktime((2000, 1, 1, 0, 0, 5, 0, 0, 0)) * 1000000000
            mtime_ns = time.mktime((2000, 1, 1, 0, 0, 8, 0, 0, 0)) * 1000000000

        set_time(filename, (atime_ns, mtime_ns))
        st = os.stat(filename)

        if support_subsecond:
            # self.assertAlmostEqual(st.st_atime, atime_ns * 1e-9, delta=1e-6)
            self.assertAlmostEqual(st.st_mtime, mtime_ns * 1e-9, delta=1e-6)
        else:
            # self.assertEqual(st.st_atime, atime_ns * 1e-9)
            self.assertEqual(st.st_mtime, mtime_ns * 1e-9)
        # self.assertEqual(st.st_atime_ns, atime_ns)
        self.assertEqual(st.st_mtime_ns, mtime_ns)

    def test_utime(self):
        def set_time(filename, ns):
            # test the ns keyword parameter
            os.utime(filename, ns=ns)
        self._test_utime(set_time)

    @staticmethod
    def ns_to_sec(ns):
        # Convert a number of nanosecond (int) to a number of seconds (float).
        # Round towards infinity by adding 0.5 nanosecond to avoid rounding
        # issue, os.utime() rounds towards minus infinity.
        return (ns * 1e-9) + 0.5e-9

    def test_utime_by_indexed(self):
        # pass times as floating point seconds as the second indexed parameter
        def set_time(filename, ns):
            atime_ns, mtime_ns = ns
            atime = self.ns_to_sec(atime_ns)
            mtime = self.ns_to_sec(mtime_ns)
            # test utimensat(timespec), utimes(timeval), utime(utimbuf)
            # or utime(time_t)
            os.utime(filename, (atime, mtime))
        self._test_utime(set_time)

    def test_utime_by_times(self):
        def set_time(filename, ns):
            atime_ns, mtime_ns = ns
            atime = self.ns_to_sec(atime_ns)
            mtime = self.ns_to_sec(mtime_ns)
            # test the times keyword parameter
            os.utime(filename, times=(atime, mtime))
        self._test_utime(set_time)

    @unittest.skipUnless(os.utime in os.supports_follow_symlinks,
                         "follow_symlinks support for utime required "
                         "for this test.")
    def test_utime_nofollow_symlinks(self):
        def set_time(filename, ns):
            # use follow_symlinks=False to test utimensat(timespec)
            # or lutimes(timeval)
            os.utime(filename, ns=ns, follow_symlinks=False)
        self._test_utime(set_time)

    @unittest.skipUnless(os.utime in os.supports_fd,
                         "fd support for utime required for this test.")
    def test_utime_fd(self):
        def set_time(filename, ns):
            with open(filename, 'wb', 0) as fp:
                # use a file descriptor to test futimens(timespec)
                # or futimes(timeval)
                os.utime(fp.fileno(), ns=ns)
        self._test_utime(set_time)

    @unittest.skipUnless(os.utime in os.supports_dir_fd,
                         "dir_fd support for utime required for this test.")
    def test_utime_dir_fd(self):
        def set_time(filename, ns):
            dirname, name = os.path.split(filename)
            dirfd = os.open(dirname, os.O_RDONLY)
            try:
                # pass dir_fd to test utimensat(timespec) or futimesat(timeval)
                os.utime(name, dir_fd=dirfd, ns=ns)
            finally:
                os.close(dirfd)
        self._test_utime(set_time)

    def test_utime_directory(self):
        def set_time(filename, ns):
            # test calling os.utime() on a directory
            os.utime(filename, ns=ns)
        self._test_utime(set_time, filename=self.dirname)

    def _test_utime_current(self, set_time):
        # Get the system clock
        current = time.time()

        # Call os.utime() to set the timestamp to the current system clock
        set_time(self.fname)

        if not self.support_subsecond(self.fname):
            delta = 2.0
        else:
            # On Windows, the usual resolution of time.time() is 15.6 ms.
            # bpo-30649: Tolerate 50 ms for slow Windows buildbots.
            #
            # x86 Gentoo Refleaks 3.x once failed with dt=20.2 ms. So use
            # also 50 ms on other platforms.
            delta = 0.050
        st = os.stat(self.fname)
        msg = ("st_time=%r, current=%r, dt=%r"
               % (st.st_mtime, current, st.st_mtime - current))
        self.assertAlmostEqual(st.st_mtime, current,
                               delta=delta, msg=msg)

    def test_utime_current(self):
        def set_time(filename):
            # Set to the current time in the new way
            os.utime(self.fname)
        self._test_utime_current(set_time)

    def test_utime_current_old(self):
        def set_time(filename):
            # Set to the current time in the old explicit way.
            os.utime(self.fname, None)
        self._test_utime_current(set_time)

    def test_utime_invalid_arguments(self):
        # seconds and nanoseconds parameters are mutually exclusive
        with self.assertRaises(ValueError):
            os.utime(self.fname, (5, 5), ns=(5, 5))
        with self.assertRaises(TypeError):
            os.utime(self.fname, [5, 5])
        with self.assertRaises(TypeError):
            os.utime(self.fname, (5,))
        with self.assertRaises(TypeError):
            os.utime(self.fname, (5, 5, 5))
        with self.assertRaises(TypeError):
            os.utime(self.fname, ns=[5, 5])
        with self.assertRaises(TypeError):
            os.utime(self.fname, ns=(5,))
        with self.assertRaises(TypeError):
            os.utime(self.fname, ns=(5, 5, 5))

        # if os.utime not in os.supports_follow_symlinks:
        #     with self.assertRaises(NotImplementedError):
        #         os.utime(self.fname, (5, 5), follow_symlinks=False)
        # if os.utime not in os.supports_fd:
        #     with open(self.fname, 'wb', 0) as fp:
        #         with self.assertRaises(TypeError):
        #             os.utime(fp.fileno(), (5, 5))
        # if os.utime not in os.supports_dir_fd:
        #     with self.assertRaises(NotImplementedError):
        #         os.utime(self.fname, (5, 5), dir_fd=0)


from test import mapping_tests

class EnvironTests(mapping_tests.BasicTestMappingProtocol):
    """check that os.environ object conform to mapping protocol"""
    type2test = None

    def setUp(self):
        self.__save = dict(os.environ)
        if os.supports_bytes_environ:
            self.__saveb = dict(os.environb)
        for key, value in self._reference().items():
            os.environ[key] = value

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.__save)
        if os.supports_bytes_environ:
            os.environb.clear()
            os.environb.update(self.__saveb)

    def _reference(self):
        return {"KEY1":"VALUE1", "KEY2":"VALUE2", "KEY3":"VALUE3"}

    def _empty_mapping(self):
        os.environ.clear()
        return os.environ

    # Bug 1110478
    @unittest.skipUnless(unix_shell and os.path.exists(unix_shell),
                         'requires a shell')
    def test_update2(self):
        os.environ.clear()
        os.environ.update(HELLO="World")
        with os.popen("%s -c 'echo $HELLO'" % unix_shell) as popen:
            value = popen.read().strip()
            self.assertEqual(value, "World")

    @unittest.skipUnless(unix_shell and os.path.exists(unix_shell),
                         'requires a shell')
    def test_os_popen_iter(self):
        with os.popen("%s -c 'echo \"line1\nline2\nline3\"'"
                      % unix_shell) as popen:
            it = iter(popen)
            self.assertEqual(next(it), "line1\n")
            self.assertEqual(next(it), "line2\n")
            self.assertEqual(next(it), "line3\n")
            self.assertRaises(StopIteration, next, it)

    # Verify environ keys and values from the OS are of the
    # correct str type.
    def test_keyvalue_types(self):
        for key, val in os.environ.items():
            self.assertEqual(type(key), str)
            self.assertEqual(type(val), str)

    def test_items(self):
        for key, value in self._reference().items():
            self.assertEqual(os.environ.get(key), value)

    # Issue 7310
    # def test___repr__(self):
    #     """Check that the repr() of os.environ looks like environ({...})."""
    #     env = os.environ
    #     self.assertEqual(repr(env), 'environ({{{}}})'.format(', '.join(
    #         '{!r}: {!r}'.format(key, value)
    #         for key, value in env.items())))

    @unittest.skipUnless(hasattr(os, 'get_exec_path'), 'requires os.get_exec_path()')
    def test_get_exec_path(self):
        defpath_list = os.defpath.split(os.pathsep)
        test_path = ['/monty', '/python', '', '/flying/circus']
        test_env = {'PATH': os.pathsep.join(test_path)}

        saved_environ = os.environ
        try:
            os.environ = dict(test_env)
            # Test that defaulting to os.environ works.
            self.assertSequenceEqual(test_path, os.get_exec_path())
            self.assertSequenceEqual(test_path, os.get_exec_path(env=None))
        finally:
            os.environ = saved_environ

        # No PATH environment variable
        self.assertSequenceEqual(defpath_list, os.get_exec_path({}))
        # Empty PATH environment variable
        self.assertSequenceEqual(('',), os.get_exec_path({'PATH':''}))
        # Supplied PATH environment variable
        self.assertSequenceEqual(test_path, os.get_exec_path(test_env))

        if os.supports_bytes_environ:
            # env cannot contain 'PATH' and b'PATH' keys
            mixed_env = {'PATH': '1', b'PATH': b'2'}
            self.assertRaises(ValueError, os.get_exec_path, mixed_env)

            # bytes key and/or value
            self.assertSequenceEqual(os.get_exec_path({b'PATH': b'abc'}),
                ['abc'])
            self.assertSequenceEqual(os.get_exec_path({b'PATH': 'abc'}),
                ['abc'])
            self.assertSequenceEqual(os.get_exec_path({'PATH': b'abc'}),
                ['abc'])

    @unittest.skipUnless(os.supports_bytes_environ,
                         "os.environb required for this test.")
    def test_environb(self):
        # os.environ -> os.environb
        value = 'euro\u20ac'
        try:
            value_bytes = value.encode(sys.getfilesystemencoding(),
                                       'surrogateescape')
        except UnicodeEncodeError:
            msg = "U+20AC character is not encodable to %s" % (
                sys.getfilesystemencoding(),)
            self.skipTest(msg)
        os.environ['unicode'] = value
        self.assertEqual(os.environ['unicode'], value)
        self.assertEqual(os.environb[b'unicode'], value_bytes)

        # os.environb -> os.environ
        value = b'\xff'
        os.environb[b'bytes'] = value
        self.assertEqual(os.environb[b'bytes'], value)
        value_str = value.decode(sys.getfilesystemencoding(), 'surrogateescape')
        self.assertEqual(os.environ['bytes'], value_str)

    def test_key_type(self):
        missing = 'missingkey'
        self.assertNotIn(missing, os.environ)

        with self.assertRaises(KeyError) as cm:
            os.environ[missing]
        self.assertIs(cm.exception.args[0], missing)
        # self.assertTrue(cm.exception.__suppress_context__)

        with self.assertRaises(KeyError) as cm:
            del os.environ[missing]
        self.assertIs(cm.exception.args[0], missing)
        # self.assertTrue(cm.exception.__suppress_context__)

    def _test_environ_iteration(self, collection):
        iterator = iter(collection)
        new_key = "__new_key__"

        next(iterator)  # start iteration over os.environ.items

        # add a new key in os.environ mapping
        os.environ[new_key] = "test_environ_iteration"

        try:
            next(iterator)  # force iteration over modified mapping
            self.assertEqual(os.environ[new_key], "test_environ_iteration")
        finally:
            del os.environ[new_key]

    def test_iter_error_when_changing_os_environ(self):
        self._test_environ_iteration(os.environ)

    def test_iter_error_when_changing_os_environ_items(self):
        self._test_environ_iteration(os.environ.items())

    def test_iter_error_when_changing_os_environ_values(self):
        self._test_environ_iteration(os.environ.values())


@unittest.skipUnless(hasattr(os, 'walk'), "Test needs os.walk()")
class WalkTests(unittest.TestCase):
    """Tests for os.walk()."""

    # Wrapper to hide minor differences between os.walk and os.fwalk
    # to tests both functions with the same code base
    def walk(self, top, **kwargs):
        if 'follow_symlinks' in kwargs:
            kwargs['followlinks'] = kwargs.pop('follow_symlinks')
        return os.walk(top, **kwargs)

    def setUp(self):
        join = os.path.join
        self.addCleanup(support.rmtree, support.TESTFN)

        # Build:
        #     TESTFN/
        #       TEST1/              a file kid and two directory kids
        #         tmp1
        #         SUB1/             a file kid and a directory kid
        #           tmp2
        #           SUB11/          no kids
        #         SUB2/             a file kid and a dirsymlink kid
        #           tmp3
        #           SUB21/          not readable
        #             tmp5
        #           link/           a symlink to TESTFN.2
        #           broken_link
        #           broken_link2
        #           broken_link3
        #       TEST2/
        #         tmp4              a lone file
        self.walk_path = join(support.TESTFN, "TEST1")
        self.sub1_path = join(self.walk_path, "SUB1")
        self.sub11_path = join(self.sub1_path, "SUB11")
        sub2_path = join(self.walk_path, "SUB2")
        sub21_path = join(sub2_path, "SUB21")
        tmp1_path = join(self.walk_path, "tmp1")
        tmp2_path = join(self.sub1_path, "tmp2")
        tmp3_path = join(sub2_path, "tmp3")
        tmp5_path = join(sub21_path, "tmp3")
        self.link_path = join(sub2_path, "link")
        t2_path = join(support.TESTFN, "TEST2")
        tmp4_path = join(support.TESTFN, "TEST2", "tmp4")
        broken_link_path = join(sub2_path, "broken_link")
        broken_link2_path = join(sub2_path, "broken_link2")
        broken_link3_path = join(sub2_path, "broken_link3")

        # Create stuff.
        os.makedirs(self.sub11_path)
        os.makedirs(sub2_path)
        os.makedirs(sub21_path)
        os.makedirs(t2_path)

        for path in tmp1_path, tmp2_path, tmp3_path, tmp4_path, tmp5_path:
            with open(path, "x") as f:
                f.write("I'm " + path + " and proud of it.  Blame test_os.\n")

        if support.can_symlink():
            os.symlink(os.path.abspath(t2_path), self.link_path)
            os.symlink('broken', broken_link_path, True)
            os.symlink(join('tmp3', 'broken'), broken_link2_path, True)
            os.symlink(join('SUB21', 'tmp5'), broken_link3_path, True)
            self.sub2_tree = (sub2_path, ["SUB21", "link"],
                              ["broken_link", "broken_link2", "broken_link3",
                               "tmp3"])
        else:
            self.sub2_tree = (sub2_path, ["SUB21"], ["tmp3"])

        os.chmod(sub21_path, 0)
        try:
            os.listdir(sub21_path)
        except PermissionError:
            self.addCleanup(os.chmod, sub21_path, stat.S_IRWXU)
        else:
            os.chmod(sub21_path, stat.S_IRWXU)
            os.unlink(tmp5_path)
            os.rmdir(sub21_path)
            del self.sub2_tree[1][:1]

    def test_walk_topdown(self):
        # Walk top-down.
        all = list(self.walk(self.walk_path))

        self.assertEqual(len(all), 4)
        # We can't know which order SUB1 and SUB2 will appear in.
        # Not flipped:  TESTFN, SUB1, SUB11, SUB2
        #     flipped:  TESTFN, SUB2, SUB1, SUB11
        flipped = all[0][1][0] != "SUB1"
        all[0][1].sort()
        all[3 - 2 * flipped][-1].sort()
        all[3 - 2 * flipped][1].sort()
        self.assertEqual(all[0], (self.walk_path, ["SUB1", "SUB2"], ["tmp1"]))
        self.assertEqual(all[1 + flipped], (self.sub1_path, ["SUB11"], ["tmp2"]))
        self.assertEqual(all[2 + flipped], (self.sub11_path, [], []))
        self.assertEqual(all[3 - 2 * flipped], self.sub2_tree)

    def test_walk_prune(self, walk_path=None):
        if walk_path is None:
            walk_path = self.walk_path
        # Prune the search.
        all = []
        for root, dirs, files in self.walk(walk_path):
            all.append((root, dirs, files))
            # Don't descend into SUB1.
            if 'SUB1' in dirs:
                # Note that this also mutates the dirs we appended to all!
                dirs.remove('SUB1')

        self.assertEqual(len(all), 2)
        self.assertEqual(all[0], (self.walk_path, ["SUB2"], ["tmp1"]))

        all[1][-1].sort()
        all[1][1].sort()
        self.assertEqual(all[1], self.sub2_tree)

    def test_file_like_path(self):
        self.test_walk_prune(FakePath(self.walk_path))

    def test_walk_bottom_up(self):
        # Walk bottom-up.
        all = list(self.walk(self.walk_path, topdown=False))

        self.assertEqual(len(all), 4, all)
        # We can't know which order SUB1 and SUB2 will appear in.
        # Not flipped:  SUB11, SUB1, SUB2, TESTFN
        #     flipped:  SUB2, SUB11, SUB1, TESTFN
        flipped = all[3][1][0] != "SUB1"
        all[3][1].sort()
        all[2 - 2 * flipped][-1].sort()
        all[2 - 2 * flipped][1].sort()
        self.assertEqual(all[3],
                         (self.walk_path, ["SUB1", "SUB2"], ["tmp1"]))
        self.assertEqual(all[flipped],
                         (self.sub11_path, [], []))
        self.assertEqual(all[flipped + 1],
                         (self.sub1_path, ["SUB11"], ["tmp2"]))
        self.assertEqual(all[2 - 2 * flipped],
                         self.sub2_tree)

    def test_walk_symlink(self):
        if not support.can_symlink():
            self.skipTest("need symlink support")

        # Walk, following symlinks.
        walk_it = self.walk(self.walk_path, follow_symlinks=True)
        for root, dirs, files in walk_it:
            if root == self.link_path:
                self.assertEqual(dirs, [])
                self.assertEqual(files, ["tmp4"])
                break
        else:
            self.fail("Didn't follow symlink with followlinks=True")

    def test_walk_bad_dir(self):
        # Walk top-down.
        errors = []
        walk_it = self.walk(self.walk_path, onerror=errors.append)
        root, dirs, files = next(walk_it)
        self.assertEqual(errors, [])
        dir1 = 'SUB1'
        path1 = os.path.join(root, dir1)
        path1new = os.path.join(root, dir1 + '.new')
        os.rename(path1, path1new)
        try:
            roots = [r for r, d, f in walk_it]
            self.assertTrue(errors)
            self.assertNotIn(path1, roots)
            self.assertNotIn(path1new, roots)
            for dir2 in dirs:
                if dir2 != dir1:
                    self.assertIn(os.path.join(root, dir2), roots)
        finally:
            os.rename(path1new, path1)

if isinstance(WalkTests, type):
    @unittest.skipUnless(hasattr(os, 'fwalk'), "Test needs os.fwalk()")
    class FwalkTests(WalkTests):
        """Tests for os.fwalk()."""

        def walk(self, top, **kwargs):
            for root, dirs, files, root_fd in self.fwalk(top, **kwargs):
                yield (root, dirs, files)

        def fwalk(self, *args, **kwargs):
            return os.fwalk(*args, **kwargs)

        def _compare_to_walk(self, walk_kwargs, fwalk_kwargs):
            """
            compare with walk() results.
            """
            walk_kwargs = walk_kwargs.copy()
            fwalk_kwargs = fwalk_kwargs.copy()
            for topdown, follow_symlinks in itertools.product((True, False), repeat=2):
                walk_kwargs.update(topdown=topdown, followlinks=follow_symlinks)
                fwalk_kwargs.update(topdown=topdown, follow_symlinks=follow_symlinks)

                expected = {}
                for root, dirs, files in os.walk(**walk_kwargs):
                    expected[root] = (set(dirs), set(files))

                for root, dirs, files, rootfd in self.fwalk(**fwalk_kwargs):
                    self.assertIn(root, expected)
                    self.assertEqual(expected[root], (set(dirs), set(files)))

        def test_compare_to_walk(self):
            kwargs = {'top': support.TESTFN}
            self._compare_to_walk(kwargs, kwargs)

        def test_dir_fd(self):
            try:
                fd = os.open(".", os.O_RDONLY)
                walk_kwargs = {'top': support.TESTFN}
                fwalk_kwargs = walk_kwargs.copy()
                fwalk_kwargs['dir_fd'] = fd
                self._compare_to_walk(walk_kwargs, fwalk_kwargs)
            finally:
                os.close(fd)

        def test_yields_correct_dir_fd(self):
            # check returned file descriptors
            for topdown, follow_symlinks in itertools.product((True, False), repeat=2):
                args = support.TESTFN, topdown, None
                for root, dirs, files, rootfd in self.fwalk(*args, follow_symlinks=follow_symlinks):
                    # check that the FD is valid
                    os.fstat(rootfd)
                    # redundant check
                    os.stat(rootfd)
                    # check that listdir() returns consistent information
                    self.assertEqual(set(os.listdir(rootfd)), set(dirs) | set(files))

        def test_fd_leak(self):
            # Since we're opening a lot of FDs, we must be careful to avoid leaks:
            # we both check that calling fwalk() a large number of times doesn't
            # yield EMFILE, and that the minimum allocated FD hasn't changed.
            minfd = os.dup(1)
            os.close(minfd)
            for i in range(256):
                for x in self.fwalk(support.TESTFN):
                    pass
            newfd = os.dup(1)
            self.addCleanup(os.close, newfd)
            self.assertEqual(newfd, minfd)

    @unittest.skipUnless(hasattr(os, 'walk'), "Test needs os.walk()")
    class BytesWalkTests(WalkTests):
        """Tests for os.walk() with bytes."""
        def walk(self, top, **kwargs):
            if 'follow_symlinks' in kwargs:
                kwargs['followlinks'] = kwargs.pop('follow_symlinks')
            for broot, bdirs, bfiles in os.walk(os.fsencode(top), **kwargs):
                root = os.fsdecode(broot)
                dirs = list(map(os.fsdecode, bdirs))
                files = list(map(os.fsdecode, bfiles))
                yield (root, dirs, files)
                bdirs[:] = list(map(os.fsencode, dirs))
                bfiles[:] = list(map(os.fsencode, files))

    @unittest.skipUnless(hasattr(os, 'fwalk'), "Test needs os.fwalk()")
    class BytesFwalkTests(FwalkTests):
        """Tests for os.walk() with bytes."""
        def fwalk(self, top='.', *args, **kwargs):
            for broot, bdirs, bfiles, topfd in os.fwalk(os.fsencode(top), *args, **kwargs):
                root = os.fsdecode(broot)
                dirs = list(map(os.fsdecode, bdirs))
                files = list(map(os.fsdecode, bfiles))
                yield (root, dirs, files, topfd)
                bdirs[:] = list(map(os.fsencode, dirs))
                bfiles[:] = list(map(os.fsencode, files))


class MakedirTests(unittest.TestCase):
    def setUp(self):
        os.mkdir(support.TESTFN)

    def test_makedir(self):
        base = support.TESTFN
        path = os.path.join(base, 'dir1', 'dir2', 'dir3')
        os.makedirs(path)             # Should work
        path = os.path.join(base, 'dir1', 'dir2', 'dir3', 'dir4')
        os.makedirs(path)

        # Try paths with a '.' in them
        self.assertRaises(OSError, os.makedirs, os.curdir)
        path = os.path.join(base, 'dir1', 'dir2', 'dir3', 'dir4', 'dir5', os.curdir)
        os.makedirs(path)
        path = os.path.join(base, 'dir1', os.curdir, 'dir2', 'dir3', 'dir4',
                            'dir5', 'dir6')
        os.makedirs(path)

    @needs_file_modes()
    def test_mode(self):
        with support.temp_umask(0o002):
            base = support.TESTFN
            parent = os.path.join(base, 'dir1')
            path = os.path.join(parent, 'dir2')
            os.makedirs(path, 0o555)
            self.assertTrue(os.path.exists(path))
            self.assertTrue(os.path.isdir(path))
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o555)
            self.assertEqual(os.stat(parent).st_mode & 0o777, 0o775)

    def test_exist_ok_existing_directory(self):
        path = os.path.join(support.TESTFN, 'dir1')
        mode = 0o777
        # old_mask = os.umask(0o022)
        os.makedirs(path, mode)
        self.assertRaises(OSError, os.makedirs, path, mode)
        self.assertRaises(OSError, os.makedirs, path, mode, exist_ok=False)
        os.makedirs(path, 0o776, exist_ok=True)
        os.makedirs(path, mode=mode, exist_ok=True)
        # os.umask(old_mask)

        # Issue #25583: A drive root could raise PermissionError on Windows
        os.makedirs(os.path.abspath('/'), exist_ok=True)

    @needs_file_modes()
    def test_exist_ok_s_isgid_directory(self):
        path = os.path.join(support.TESTFN, 'dir1')
        S_ISGID = stat.S_ISGID
        mode = 0o777
        old_mask = os.umask(0o022)
        try:
            existing_testfn_mode = stat.S_IMODE(
                    os.lstat(support.TESTFN).st_mode)
            try:
                os.chmod(support.TESTFN, existing_testfn_mode | S_ISGID)
            except PermissionError:
                raise unittest.SkipTest('Cannot set S_ISGID for dir.')
            if (os.lstat(support.TESTFN).st_mode & S_ISGID != S_ISGID):
                raise unittest.SkipTest('No support for S_ISGID dir mode.')
            # The os should apply S_ISGID from the parent dir for us, but
            # this test need not depend on that behavior.  Be explicit.
            os.makedirs(path, mode | S_ISGID)
            # http://bugs.python.org/issue14992
            # Should not fail when the bit is already set.
            os.makedirs(path, mode, exist_ok=True)
            # remove the bit.
            os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) & ~S_ISGID)
            # May work even when the bit is not already set when demanded.
            os.makedirs(path, mode | S_ISGID, exist_ok=True)
        finally:
            os.umask(old_mask)

    def test_exist_ok_existing_regular_file(self):
        base = support.TESTFN
        path = os.path.join(support.TESTFN, 'dir1')
        f = open(path, 'w')
        f.write('abc')
        f.close()
        self.assertRaises(OSError, os.makedirs, path)
        self.assertRaises(OSError, os.makedirs, path, exist_ok=False)
        self.assertRaises(OSError, os.makedirs, path, exist_ok=True)
        os.remove(path)

    def tearDown(self):
        path = os.path.join(support.TESTFN, 'dir1', 'dir2', 'dir3',
                            'dir4', 'dir5', 'dir6')
        # If the tests failed, the bottom-most directory ('../dir6')
        # may not have been created, so we look for the outermost directory
        # that exists.
        while not os.path.exists(path) and path != support.TESTFN:
            path = os.path.dirname(path)

        os.removedirs(path)


@unittest.skipUnless(hasattr(os, 'chown'), "Test needs chown")
class ChownFileTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.mkdir(support.TESTFN)

    def test_chown_uid_gid_arguments_must_be_index(self):
        stat = os.stat(support.TESTFN)
        uid = stat.st_uid
        gid = stat.st_gid
        for value in (-1.0, -1j):
            self.assertRaises(TypeError, os.chown, support.TESTFN, value, gid)
            self.assertRaises(TypeError, os.chown, support.TESTFN, uid, value)
        self.assertIsNone(os.chown(support.TESTFN, uid, gid))
        self.assertIsNone(os.chown(support.TESTFN, -1, -1))

    @unittest.skipUnless(hasattr(os, 'getgroups'), 'need os.getgroups')
    def test_chown_gid(self):
        groups = os.getgroups()
        if len(groups) < 2:
            self.skipTest("test needs at least 2 groups")

        gid_1, gid_2 = groups[:2]
        uid = os.stat(support.TESTFN).st_uid

        os.chown(support.TESTFN, uid, gid_1)
        gid = os.stat(support.TESTFN).st_gid
        self.assertEqual(gid, gid_1)

        os.chown(support.TESTFN, uid, gid_2)
        gid = os.stat(support.TESTFN).st_gid
        self.assertEqual(gid, gid_2)

    @unittest.skipUnless(root_in_posix and len(all_users) > 1,
                         "test needs root privilege and more than one user")
    def test_chown_with_root(self):
        uid_1, uid_2 = all_users[:2]
        gid = os.stat(support.TESTFN).st_gid
        os.chown(support.TESTFN, uid_1, gid)
        uid = os.stat(support.TESTFN).st_uid
        self.assertEqual(uid, uid_1)
        os.chown(support.TESTFN, uid_2, gid)
        uid = os.stat(support.TESTFN).st_uid
        self.assertEqual(uid, uid_2)

    @unittest.skipUnless(not root_in_posix and len(all_users) > 1,
                         "test needs non-root account and more than one user")
    def test_chown_without_permission(self):
        uid_1, uid_2 = all_users[:2]
        gid = os.stat(support.TESTFN).st_gid
        with self.assertRaises(PermissionError):
            os.chown(support.TESTFN, uid_1, gid)
            os.chown(support.TESTFN, uid_2, gid)

    @classmethod
    def tearDownClass(cls):
        os.rmdir(support.TESTFN)


class RemoveDirsTests(unittest.TestCase):
    def setUp(self):
        os.makedirs(support.TESTFN)

    def tearDown(self):
        support.rmtree(support.TESTFN)

    def test_remove_all(self):
        dira = os.path.join(support.TESTFN, 'dira')
        os.mkdir(dira)
        dirb = os.path.join(dira, 'dirb')
        os.mkdir(dirb)
        os.removedirs(dirb)
        self.assertFalse(os.path.exists(dirb))
        self.assertFalse(os.path.exists(dira))
        self.assertFalse(os.path.exists(support.TESTFN))

    def test_remove_partial(self):
        dira = os.path.join(support.TESTFN, 'dira')
        os.mkdir(dira)
        dirb = os.path.join(dira, 'dirb')
        os.mkdir(dirb)
        create_file(os.path.join(dira, 'file.txt'))
        os.removedirs(dirb)
        self.assertFalse(os.path.exists(dirb))
        self.assertTrue(os.path.exists(dira))
        self.assertTrue(os.path.exists(support.TESTFN))

    def test_remove_nothing(self):
        dira = os.path.join(support.TESTFN, 'dira')
        os.mkdir(dira)
        dirb = os.path.join(dira, 'dirb')
        os.mkdir(dirb)
        create_file(os.path.join(dirb, 'file.txt'))
        with self.assertRaises(OSError):
            os.removedirs(dirb)
        self.assertTrue(os.path.exists(dirb))
        self.assertTrue(os.path.exists(dira))
        self.assertTrue(os.path.exists(support.TESTFN))


class DevNullTests(unittest.TestCase):
    def test_devnull(self):
        with open(os.devnull, 'wb', 0) as f:
            f.write(b'hello')
            f.close()
        with open(os.devnull, 'rb') as f:
            self.assertEqual(f.read(), b'')


class URandomTests(unittest.TestCase):
    def test_urandom_length(self):
        self.assertEqual(len(os.urandom(0)), 0)
        self.assertEqual(len(os.urandom(1)), 1)
        self.assertEqual(len(os.urandom(10)), 10)
        self.assertEqual(len(os.urandom(100)), 100)
        self.assertEqual(len(os.urandom(1000)), 1000)

    def test_urandom_value(self):
        data1 = os.urandom(16)
        self.assertIsInstance(data1, bytes)
        data2 = os.urandom(16)
        self.assertNotEqual(data1, data2)


@unittest.skipUnless(hasattr(os, 'getrandom'), 'need os.getrandom()')
class GetRandomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            os.getrandom(1)
        except OSError as exc:
            if exc.errno == errno.ENOSYS:
                # Python compiled on a more recent Linux version
                # than the current Linux kernel
                raise unittest.SkipTest("getrandom() syscall fails with ENOSYS")
            else:
                raise

    def test_getrandom_type(self):
        data = os.getrandom(16)
        self.assertIsInstance(data, bytes)
        self.assertEqual(len(data), 16)

    def test_getrandom0(self):
        empty = os.getrandom(0)
        self.assertEqual(empty, b'')

    def test_getrandom_random(self):
        self.assertTrue(hasattr(os, 'GRND_RANDOM'))

        # Don't test os.getrandom(1, os.GRND_RANDOM) to not consume the rare
        # resource /dev/random

    def test_getrandom_nonblock(self):
        # The call must not fail. Check also that the flag exists
        try:
            os.getrandom(1, os.GRND_NONBLOCK)
        except BlockingIOError:
            # System urandom is not initialized yet
            pass

    def test_getrandom_value(self):
        data1 = os.getrandom(16)
        data2 = os.getrandom(16)
        self.assertNotEqual(data1, data2)


class TestInvalidFD(unittest.TestCase):
    singles = ["fchdir", "dup", "fdopen", "fdatasync", "fstat",
               "fstatvfs", "fsync", "tcgetpgrp", "ttyname"]
    #singles.append("close")
    #We omit close because it doesn't raise an exception on some platforms
    def get_single(f):
        def helper(self):
            if  hasattr(os, f):
                self.check(getattr(os, f))
        return helper
    for f in singles:
        locals()["test_"+f] = get_single(f)

    def check(self, f, *args):
        try:
            f(support.make_bad_fd(), *args)
        except OSError as e:
            self.assertEqual(e.errno, errno.EBADF)
        else:
            self.fail("%r didn't raise an OSError with a bad file descriptor"
                      % f)

    @unittest.skipUnless(hasattr(os, 'isatty'), 'test needs os.isatty()')
    def test_isatty(self):
        self.assertEqual(os.isatty(support.make_bad_fd()), False)

    @unittest.skipUnless(hasattr(os, 'closerange'), 'test needs os.closerange()')
    def test_closerange(self):
        fd = support.make_bad_fd()
        # Make sure none of the descriptors we are about to close are
        # currently valid (issue 6542).
        for i in range(10):
            try: os.fstat(fd+i)
            except OSError:
                pass
            else:
                break
        if i < 2:
            raise unittest.SkipTest(
                "Unable to acquire a range of invalid file descriptors")
        self.assertEqual(os.closerange(fd, fd + i-1), None)

    @unittest.skipUnless(hasattr(os, 'dup2'), 'test needs os.dup2()')
    def test_dup2(self):
        self.check(os.dup2, 20)

    @unittest.skipUnless(hasattr(os, 'fchmod'), 'test needs os.fchmod()')
    def test_fchmod(self):
        self.check(os.fchmod, 0)

    @unittest.skipUnless(hasattr(os, 'fchown'), 'test needs os.fchown()')
    def test_fchown(self):
        self.check(os.fchown, -1, -1)

    @unittest.skipUnless(hasattr(os, 'fpathconf'), 'test needs os.fpathconf()')
    def test_fpathconf(self):
        self.check(os.pathconf, "PC_NAME_MAX")
        self.check(os.fpathconf, "PC_NAME_MAX")

    @unittest.skipUnless(hasattr(os, 'ftruncate'), 'test needs os.ftruncate()')
    def test_ftruncate(self):
        self.check(os.truncate, 0)
        self.check(os.ftruncate, 0)

    @unittest.skipUnless(hasattr(os, 'lseek'), 'test needs os.lseek()')
    def test_lseek(self):
        self.check(os.lseek, 0, 0)

    @unittest.skipUnless(hasattr(os, 'read'), 'test needs os.read()')
    def test_read(self):
        self.check(os.read, 1)

    @unittest.skipUnless(hasattr(os, 'readv'), 'test needs os.readv()')
    def test_readv(self):
        buf = bytearray(10)
        self.check(os.readv, [buf])

    @unittest.skipUnless(hasattr(os, 'tcsetpgrp'), 'test needs os.tcsetpgrp()')
    def test_tcsetpgrpt(self):
        self.check(os.tcsetpgrp, 0)

    @unittest.skipUnless(hasattr(os, 'write'), 'test needs os.write()')
    def test_write(self):
        self.check(os.write, b" ")

    @unittest.skipUnless(hasattr(os, 'writev'), 'test needs os.writev()')
    def test_writev(self):
        self.check(os.writev, [b'abc'])

    @unittest.skipUnless(hasattr(os, 'get_blocking'),
                         'needs os.get_blocking() and os.set_blocking()')
    def test_blocking(self):
        self.check(os.get_blocking)
        self.check(os.set_blocking, True)


@unittest.skipUnless(hasattr(os, 'link'), 'test needs os.link()')
class LinkTests(unittest.TestCase):
    def setUp(self):
        self.file1 = support.TESTFN
        self.file2 = os.path.join(support.TESTFN + "2")

    def tearDown(self):
        for file in (self.file1, self.file2):
            if os.path.exists(file):
                os.unlink(file)

    def _test_link(self, file1, file2):
        create_file(file1)

        try:
            os.link(file1, file2)
        except PermissionError as e:
            self.skipTest('os.link(): %s' % e)
        with open(file1, "r") as f1, open(file2, "r") as f2:
            self.assertTrue(os.path.sameopenfile(f1.fileno(), f2.fileno()))

    def test_link(self):
        self._test_link(self.file1, self.file2)

    def test_link_bytes(self):
        self._test_link(bytes(self.file1, sys.getfilesystemencoding()),
                        bytes(self.file2, sys.getfilesystemencoding()))

    def test_unicode_name(self):
        try:
            os.fsencode("\xf1")
        except UnicodeError:
            raise unittest.SkipTest("Unable to encode for this platform.")

        self.file1 += "\xf1"
        self.file2 = self.file1 + "2"
        self._test_link(self.file1, self.file2)


class PosixUidGidTests(unittest.TestCase):
    # uid_t and gid_t are 32-bit unsigned integers on Linux
    UID_OVERFLOW = (1 << 32)
    GID_OVERFLOW = (1 << 32)

    @unittest.skipUnless(hasattr(os, 'setuid'), 'test needs os.setuid()')
    def test_setuid(self):
        if os.getuid() != 0:
            self.assertRaises(OSError, os.setuid, 0)
        self.assertRaises(TypeError, os.setuid, 'not an int')
        self.assertRaises(OverflowError, os.setuid, self.UID_OVERFLOW)

    @unittest.skipUnless(hasattr(os, 'setgid'), 'test needs os.setgid()')
    def test_setgid(self):
        if os.getuid() != 0:
            self.assertRaises(OSError, os.setgid, 0)
        self.assertRaises(TypeError, os.setgid, 'not an int')
        self.assertRaises(OverflowError, os.setgid, self.GID_OVERFLOW)

    @unittest.skipUnless(hasattr(os, 'seteuid'), 'test needs os.seteuid()')
    def test_seteuid(self):
        if os.getuid() != 0:
            self.assertRaises(OSError, os.seteuid, 0)
        self.assertRaises(TypeError, os.setegid, 'not an int')
        self.assertRaises(OverflowError, os.seteuid, self.UID_OVERFLOW)

    @unittest.skipUnless(hasattr(os, 'setegid'), 'test needs os.setegid()')
    def test_setegid(self):
        if os.getuid() != 0:
            self.assertRaises(OSError, os.setegid, 0)
        self.assertRaises(TypeError, os.setegid, 'not an int')
        self.assertRaises(OverflowError, os.setegid, self.GID_OVERFLOW)

    @unittest.skipUnless(hasattr(os, 'setreuid'), 'test needs os.setreuid()')
    def test_setreuid(self):
        if os.getuid() != 0:
            self.assertRaises(OSError, os.setreuid, 0, 0)
        self.assertRaises(TypeError, os.setreuid, 'not an int', 0)
        self.assertRaises(TypeError, os.setreuid, 0, 'not an int')
        self.assertRaises(OverflowError, os.setreuid, self.UID_OVERFLOW, 0)
        self.assertRaises(OverflowError, os.setreuid, 0, self.UID_OVERFLOW)

    @unittest.skipUnless(hasattr(os, 'setregid'), 'test needs os.setregid()')
    def test_setregid(self):
        if os.getuid() != 0:
            self.assertRaises(OSError, os.setregid, 0, 0)
        self.assertRaises(TypeError, os.setregid, 'not an int', 0)
        self.assertRaises(TypeError, os.setregid, 0, 'not an int')
        self.assertRaises(OverflowError, os.setregid, self.GID_OVERFLOW, 0)
        self.assertRaises(OverflowError, os.setregid, 0, self.GID_OVERFLOW)


class Pep383Tests(unittest.TestCase):
    def setUp(self):
        if support.TESTFN_UNENCODABLE:
            self.dir = support.TESTFN_UNENCODABLE
        elif support.TESTFN_NONASCII:
            self.dir = support.TESTFN_NONASCII
        else:
            self.dir = support.TESTFN
        self.bdir = os.fsencode(self.dir)

        bytesfn = []
        def add_filename(fn):
            try:
                fn = os.fsencode(fn)
            except UnicodeEncodeError:
                return
            bytesfn.append(fn)
        add_filename(support.TESTFN_UNICODE)
        if support.TESTFN_UNENCODABLE:
            add_filename(support.TESTFN_UNENCODABLE)
        if support.TESTFN_NONASCII:
            add_filename(support.TESTFN_NONASCII)
        if not bytesfn:
            self.skipTest("couldn't create any non-ascii filename")

        self.unicodefn = set()
        os.mkdir(self.dir)
        try:
            for fn in bytesfn:
                support.create_empty_file(os.path.join(self.bdir, fn))
                fn = os.fsdecode(fn)
                if fn in self.unicodefn:
                    raise ValueError("duplicate filename")
                self.unicodefn.add(fn)
        except:
            shutil.rmtree(self.dir)
            raise

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_listdir(self):
        expected = self.unicodefn
        found = set(os.listdir(self.dir))
        self.assertEqual(found, expected)
        # test listdir without arguments
        current_directory = os.getcwd()
        try:
            os.chdir(os.sep)
            self.assertEqual(set(os.listdir()), set(os.listdir(os.sep)))
        finally:
            os.chdir(current_directory)

    def test_open(self):
        for fn in self.unicodefn:
            f = open(os.path.join(self.dir, fn), 'rb')
            f.close()

    @unittest.skipUnless(hasattr(os, 'statvfs'),
                            "need os.statvfs()")
    def test_statvfs(self):
        # issue #9645
        for fn in self.unicodefn:
            # should not fail with file not found error
            fullname = os.path.join(self.dir, fn)
            os.statvfs(fullname)

    def test_stat(self):
        for fn in self.unicodefn:
            os.stat(os.path.join(self.dir, fn))


@support.skip_unless_symlink
class NonLocalSymlinkTests(unittest.TestCase):

    def setUp(self):
        r"""
        Create this structure:

        base
         \___ some_dir
        """
        os.makedirs('base/some_dir')

    def tearDown(self):
        shutil.rmtree('base')

    def test_directory_link_nonlocal(self):
        """
        The symlink target should resolve relative to the link, not relative
        to the current directory.

        Then, link base/some_link -> base/some_dir and ensure that some_link
        is resolved as a directory.

        In issue13772, it was discovered that directory detection failed if
        the symlink target was not specified relative to the current
        directory, which was a defect in the implementation.
        """
        src = os.path.join('base', 'some_link')
        os.symlink('some_dir', src)
        assert os.path.isdir(src)


class FSEncodingTests(unittest.TestCase):
    def test_nop(self):
        self.assertEqual(os.fsencode(b'abc\xff'), b'abc\xff')
        self.assertEqual(os.fsdecode('abc\u0141'), 'abc\u0141')

    def test_identity(self):
        # assert fsdecode(fsencode(x)) == x
        for fn in ('unicode\u0141', 'latin\xe9', 'ascii'):
            try:
                bytesfn = os.fsencode(fn)
            except UnicodeEncodeError:
                continue
            self.assertEqual(os.fsdecode(bytesfn), fn)


# The introduction of this TestCase caused at least two different errors on
# *nix buildbots. Temporarily skip this to let the buildbots move along.
@unittest.skip("Skip due to platform/environment differences on *NIX buildbots")
@unittest.skipUnless(hasattr(os, 'getlogin'), "test needs os.getlogin")
class LoginTests(unittest.TestCase):
    def test_getlogin(self):
        user_name = os.getlogin()
        self.assertNotEqual(len(user_name), 0)


@unittest.skipUnless(hasattr(os, 'getpriority') and hasattr(os, 'setpriority'),
                     "needs os.getpriority and os.setpriority")
class ProgramPriorityTests(unittest.TestCase):
    """Tests for os.getpriority() and os.setpriority()."""

    def test_set_get_priority(self):

        base = os.getpriority(os.PRIO_PROCESS, os.getpid())
        os.setpriority(os.PRIO_PROCESS, os.getpid(), base + 1)
        try:
            new_prio = os.getpriority(os.PRIO_PROCESS, os.getpid())
            if base >= 19 and new_prio <= 19:
                raise unittest.SkipTest("unable to reliably test setpriority "
                                        "at current nice level of %s" % base)
            else:
                self.assertEqual(new_prio, base + 1)
        finally:
            try:
                os.setpriority(os.PRIO_PROCESS, os.getpid(), base)
            except OSError as err:
                if err.errno != errno.EACCES:
                    raise


# class SendfileTestServer(asyncore.dispatcher, threading.Thread):

#     class Handler(asynchat.async_chat):

#         def __init__(self, conn):
#             asynchat.async_chat.__init__(self, conn)
#             self.in_buffer = []
#             self.accumulate = True
#             self.closed = False
#             self.push(b"220 ready\r\n")

#         def handle_read(self):
#             data = self.recv(4096)
#             if self.accumulate:
#                 self.in_buffer.append(data)

#         def get_data(self):
#             return b''.join(self.in_buffer)

#         def handle_close(self):
#             self.close()
#             self.closed = True

#         def handle_error(self):
#             raise

#     def __init__(self, address):
#         threading.Thread.__init__(self)
#         asyncore.dispatcher.__init__(self)
#         self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
#         self.bind(address)
#         self.listen(5)
#         self.host, self.port = self.socket.getsockname()[:2]
#         self.handler_instance = None
#         self._active = False
#         self._active_lock = threading.Lock()

#     # --- public API

#     @property
#     def running(self):
#         return self._active

#     def start(self):
#         assert not self.running
#         self.__flag = threading.Event()
#         threading.Thread.start(self)
#         self.__flag.wait()

#     def stop(self):
#         assert self.running
#         self._active = False
#         self.join()

#     def wait(self):
#         # wait for handler connection to be closed, then stop the server
#         while not getattr(self.handler_instance, "closed", False):
#             time.sleep(0.001)
#         self.stop()

#     # --- internals

#     def run(self):
#         self._active = True
#         self.__flag.set()
#         while self._active and asyncore.socket_map:
#             self._active_lock.acquire()
#             asyncore.loop(timeout=0.001, count=1)
#             self._active_lock.release()
#         asyncore.close_all()

#     def handle_accept(self):
#         conn, addr = self.accept()
#         self.handler_instance = self.Handler(conn)

#     def handle_connect(self):
#         self.close()
#     handle_read = handle_connect

#     def writable(self):
#         return 0

#     def handle_error(self):
#         raise


# @unittest.skipUnless(hasattr(os, 'sendfile'), "test needs os.sendfile()")
# class TestSendfile(unittest.TestCase):

#     DATA = b"12345abcde" * 16 * 1024  # 160 KiB
#     SUPPORT_HEADERS_TRAILERS = not sys.platform.startswith("linux") and \
#                                not sys.platform.startswith("solaris") and \
#                                not sys.platform.startswith("sunos")
#     requires_headers_trailers = unittest.skipUnless(SUPPORT_HEADERS_TRAILERS,
#             'requires headers and trailers support')
#     requires_32b = unittest.skipUnless(sys.maxsize < 2**32,
#             'test is only meaningful on 32-bit builds')

#     @classmethod
#     def setUpClass(cls):
#         cls.key = support.threading_setup()
#         create_file(support.TESTFN, cls.DATA)

#     @classmethod
#     def tearDownClass(cls):
#         support.threading_cleanup(*cls.key)
#         support.unlink(support.TESTFN)

#     def setUp(self):
#         self.server = SendfileTestServer((support.HOST, 0))
#         self.server.start()
#         self.client = socket.socket()
#         self.client.connect((self.server.host, self.server.port))
#         self.client.settimeout(1)
#         # synchronize by waiting for "220 ready" response
#         self.client.recv(1024)
#         self.sockno = self.client.fileno()
#         self.file = open(support.TESTFN, 'rb')
#         self.fileno = self.file.fileno()

#     def tearDown(self):
#         self.file.close()
#         self.client.close()
#         if self.server.running:
#             self.server.stop()
#         self.server = None

#     def sendfile_wrapper(self, *args, **kwargs):
#         """A higher level wrapper representing how an application is
#         supposed to use sendfile().
#         """
#         while True:
#             try:
#                 return os.sendfile(*args, **kwargs)
#             except OSError as err:
#                 if err.errno == errno.ECONNRESET:
#                     # disconnected
#                     raise
#                 elif err.errno in (errno.EAGAIN, errno.EBUSY):
#                     # we have to retry send data
#                     continue
#                 else:
#                     raise

#     def test_send_whole_file(self):
#         # normal send
#         total_sent = 0
#         offset = 0
#         nbytes = 4096
#         while total_sent < len(self.DATA):
#             sent = self.sendfile_wrapper(self.sockno, self.fileno, offset, nbytes)
#             if sent == 0:
#                 break
#             offset += sent
#             total_sent += sent
#             self.assertTrue(sent <= nbytes)
#             self.assertEqual(offset, total_sent)

#         self.assertEqual(total_sent, len(self.DATA))
#         self.client.shutdown(socket.SHUT_RDWR)
#         self.client.close()
#         self.server.wait()
#         data = self.server.handler_instance.get_data()
#         self.assertEqual(len(data), len(self.DATA))
#         self.assertEqual(data, self.DATA)

#     def test_send_at_certain_offset(self):
#         # start sending a file at a certain offset
#         total_sent = 0
#         offset = len(self.DATA) // 2
#         must_send = len(self.DATA) - offset
#         nbytes = 4096
#         while total_sent < must_send:
#             sent = self.sendfile_wrapper(self.sockno, self.fileno, offset, nbytes)
#             if sent == 0:
#                 break
#             offset += sent
#             total_sent += sent
#             self.assertTrue(sent <= nbytes)

#         self.client.shutdown(socket.SHUT_RDWR)
#         self.client.close()
#         self.server.wait()
#         data = self.server.handler_instance.get_data()
#         expected = self.DATA[len(self.DATA) // 2:]
#         self.assertEqual(total_sent, len(expected))
#         self.assertEqual(len(data), len(expected))
#         self.assertEqual(data, expected)

#     def test_offset_overflow(self):
#         # specify an offset > file size
#         offset = len(self.DATA) + 4096
#         try:
#             sent = os.sendfile(self.sockno, self.fileno, offset, 4096)
#         except OSError as e:
#             # Solaris can raise EINVAL if offset >= file length, ignore.
#             if e.errno != errno.EINVAL:
#                 raise
#         else:
#             self.assertEqual(sent, 0)
#         self.client.shutdown(socket.SHUT_RDWR)
#         self.client.close()
#         self.server.wait()
#         data = self.server.handler_instance.get_data()
#         self.assertEqual(data, b'')

#     def test_invalid_offset(self):
#         with self.assertRaises(OSError) as cm:
#             os.sendfile(self.sockno, self.fileno, -1, 4096)
#         self.assertEqual(cm.exception.errno, errno.EINVAL)

#     def test_keywords(self):
#         # Keyword arguments should be supported
#         os.sendfile(out=self.sockno, offset=0, count=4096,
#             **{'in': self.fileno})
#         if self.SUPPORT_HEADERS_TRAILERS:
#             os.sendfile(self.sockno, self.fileno, offset=0, count=4096,
#                 headers=(), trailers=(), flags=0)

#     # --- headers / trailers tests

#     @requires_headers_trailers
#     def test_headers(self):
#         total_sent = 0
#         expected_data = b"x" * 512 + b"y" * 256 + self.DATA[:-1]
#         sent = os.sendfile(self.sockno, self.fileno, 0, 4096,
#                             headers=[b"x" * 512, b"y" * 256])
#         self.assertLessEqual(sent, 512 + 256 + 4096)
#         total_sent += sent
#         offset = 4096
#         while total_sent < len(expected_data):
#             nbytes = min(len(expected_data) - total_sent, 4096)
#             sent = self.sendfile_wrapper(self.sockno, self.fileno,
#                                                     offset, nbytes)
#             if sent == 0:
#                 break
#             self.assertLessEqual(sent, nbytes)
#             total_sent += sent
#             offset += sent

#         self.assertEqual(total_sent, len(expected_data))
#         self.client.close()
#         self.server.wait()
#         data = self.server.handler_instance.get_data()
#         self.assertEqual(hash(data), hash(expected_data))

#     @requires_headers_trailers
#     def test_trailers(self):
#         TESTFN2 = support.TESTFN + "2"
#         file_data = b"abcdef"

#         self.addCleanup(support.unlink, TESTFN2)
#         create_file(TESTFN2, file_data)

#         with open(TESTFN2, 'rb') as f:
#             os.sendfile(self.sockno, f.fileno(), 0, 5,
#                         trailers=[b"123456", b"789"])
#             self.client.close()
#             self.server.wait()
#             data = self.server.handler_instance.get_data()
#             self.assertEqual(data, b"abcde123456789")

#     @requires_headers_trailers
#     @requires_32b
#     def test_headers_overflow_32bits(self):
#         self.server.handler_instance.accumulate = False
#         with self.assertRaises(OSError) as cm:
#             os.sendfile(self.sockno, self.fileno, 0, 0,
#                         headers=[b"x" * 2**16] * 2**15)
#         self.assertEqual(cm.exception.errno, errno.EINVAL)

#     @requires_headers_trailers
#     @requires_32b
#     def test_trailers_overflow_32bits(self):
#         self.server.handler_instance.accumulate = False
#         with self.assertRaises(OSError) as cm:
#             os.sendfile(self.sockno, self.fileno, 0, 0,
#                         trailers=[b"x" * 2**16] * 2**15)
#         self.assertEqual(cm.exception.errno, errno.EINVAL)

#     @requires_headers_trailers
#     @unittest.skipUnless(hasattr(os, 'SF_NODISKIO'),
#                          'test needs os.SF_NODISKIO')
#     def test_flags(self):
#         try:
#             os.sendfile(self.sockno, self.fileno, 0, 4096,
#                         flags=os.SF_NODISKIO)
#         except OSError as err:
#             if err.errno not in (errno.EBUSY, errno.EAGAIN):
#                 raise


@unittest.skipUnless(hasattr(os, 'get_terminal_size'), "requires os.get_terminal_size")
class TermsizeTests(unittest.TestCase):
    def test_does_not_crash(self):
        """Check if get_terminal_size() returns a meaningful value.

        There's no easy portable way to actually check the size of the
        terminal, so let's check if it returns something sensible instead.
        """
        try:
            size = os.get_terminal_size()
        except OSError as e:
            if e.errno in (errno.EINVAL, errno.ENOTTY):
                self.skipTest("failed to query terminal size")
            raise

        self.assertGreaterEqual(size.columns, 0)
        self.assertGreaterEqual(size.lines, 0)


class OSErrorTests(unittest.TestCase):
    def setUp(self):
        # class Str(str):
        #     pass

        self.bytes_filenames = []
        self.unicode_filenames = []
        if support.TESTFN_UNENCODABLE is not None:
            decoded = support.TESTFN_UNENCODABLE
        else:
            decoded = support.TESTFN
        self.unicode_filenames.append(decoded)
        # self.unicode_filenames.append(Str(decoded))
        if support.TESTFN_UNDECODABLE is not None:
            encoded = support.TESTFN_UNDECODABLE
        else:
            encoded = os.fsencode(support.TESTFN)
        self.bytes_filenames.append(encoded)

        self.filenames = self.bytes_filenames + self.unicode_filenames

    def test_oserror_filename(self):
        funcs = [
            (self.filenames, os.chdir,),
            (self.filenames, os.lstat,),
            (self.filenames, os.open, os.O_RDONLY),
            (self.filenames, os.rmdir,),
            (self.filenames, os.stat,),
            (self.filenames, os.unlink,),
        ]
        funcs.extend((
            (self.filenames, os.listdir,),
            (self.filenames, os.rename, "dst"),
            (self.filenames, os.replace, "dst"),
        ))
        if hasattr(os, "chmod"):
            funcs.append((self.filenames, os.chmod, 0o777))
        if hasattr(os, "chown"):
            funcs.append((self.filenames, os.chown, 0, 0))
        if hasattr(os, "lchown"):
            funcs.append((self.filenames, os.lchown, 0, 0))
        if hasattr(os, "truncate"):
            funcs.append((self.filenames, os.truncate, 0))
        if hasattr(os, "chflags"):
            funcs.append((self.filenames, os.chflags, 0))
        if hasattr(os, "lchflags"):
            funcs.append((self.filenames, os.lchflags, 0))
        if hasattr(os, "chroot"):
            funcs.append((self.filenames, os.chroot,))
        if hasattr(os, "link"):
            funcs.append((self.filenames, os.link, "dst"))
        if hasattr(os, "listxattr"):
            funcs.extend((
                (self.filenames, os.listxattr,),
                (self.filenames, os.getxattr, "user.test"),
                (self.filenames, os.setxattr, "user.test", b'user'),
                (self.filenames, os.removexattr, "user.test"),
            ))
        if hasattr(os, "lchmod"):
            funcs.append((self.filenames, os.lchmod, 0o777))
        if hasattr(os, "readlink"):
            funcs.append((self.filenames, os.readlink,))


        for filenames, func, *func_args in funcs:
            for name in filenames:
                try:
                    func(name, *func_args)
                except OSError as err:
                    self.assertIs(err.filename, name, str(func))
                except UnicodeDecodeError:
                    pass
                else:
                    self.fail("No exception thrown by {}".format(func))

class CPUCountTests(unittest.TestCase):
    def test_cpu_count(self):
        cpus = os.cpu_count()
        if cpus is not None:
            self.assertIsInstance(cpus, int)
            self.assertGreater(cpus, 0)
        else:
            self.skipTest("Could not determine the number of CPUs")


@unittest.skipUnless(hasattr(os, 'fspath'), "requires os.fspath")
class PathTConverterTests(unittest.TestCase):
    # tuples of (function name, allows fd arguments, additional arguments to
    # function, cleanup function)
    functions = [
        ('stat', True, (), None),
        ('lstat', False, (), None),
        ('access', False, (0,), None),
        ('chflags', False, (0,), None),
        ('lchflags', False, (0,), None),
        ('open', False, (0,), getattr(os, 'close', None)),
    ]

    def test_path_t_converter(self):
        str_filename = support.TESTFN
        bytes_filename = support.TESTFN.encode('ascii')
        bytes_fspath = FakePath(bytes_filename)
        fd = os.open(FakePath(str_filename), os.O_WRONLY|os.O_CREAT)
        self.addCleanup(support.unlink, support.TESTFN)
        self.addCleanup(os.close, fd)

        int_fspath = FakePath(fd)
        str_fspath = FakePath(str_filename)

        for name, allow_fd, extra_args, cleanup_fn in self.functions:
            with self.subTest(name=name):
                try:
                    fn = getattr(os, name)
                except AttributeError:
                    continue

                for path in (str_filename, bytes_filename, str_fspath,
                             bytes_fspath):
                    if path is None:
                        continue
                    with self.subTest(name=name, path=path):
                        result = fn(path, *extra_args)
                        if cleanup_fn is not None:
                            cleanup_fn(result)

                with self.assertRaisesRegex(
                        TypeError, 'to return str or bytes'):
                    fn(int_fspath, *extra_args)

                if allow_fd:
                    result = fn(fd, *extra_args)  # should not fail
                    if cleanup_fn is not None:
                        cleanup_fn(result)
                else:
                    with self.assertRaisesRegex(
                            TypeError,
                            'os.PathLike'):
                        fn(fd, *extra_args)

    def test_path_t_converter_and_custom_class(self):
        msg = r'__fspath__\(\) to return str or bytes, not %s'
        with self.assertRaisesRegex(TypeError, msg % r'int'):
            os.stat(FakePath(2))
        with self.assertRaisesRegex(TypeError, msg % r'float'):
            os.stat(FakePath(2.34))
        with self.assertRaisesRegex(TypeError, msg % r'object'):
            os.stat(FakePath(object()))


@unittest.skipUnless(hasattr(os, 'get_blocking'),
                     'needs os.get_blocking() and os.set_blocking()')
class BlockingTests(unittest.TestCase):
    def test_blocking(self):
        fd = os.open(__file__, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        self.assertEqual(os.get_blocking(fd), True)

        os.set_blocking(fd, False)
        self.assertEqual(os.get_blocking(fd), False)

        os.set_blocking(fd, True)
        self.assertEqual(os.get_blocking(fd), True)



@unittest.skipUnless(hasattr(os, '__all__'), 'needs os.__all__')
class ExportsTests(unittest.TestCase):
    def test_os_all(self):
        self.assertIn('open', os.__all__)
        self.assertIn('walk', os.__all__)


class TestScandir(unittest.TestCase):
    check_no_resource_warning = support.check_no_resource_warning
    supports_follow_symlinks = os.stat in os.supports_follow_symlinks

    def setUp(self):
        self.path = os.path.realpath(support.TESTFN)
        self.bytes_path = os.fsencode(self.path)
        self.addCleanup(support.rmtree, self.path)
        os.mkdir(self.path)

    def create_file(self, name="file.txt"):
        path = self.bytes_path if isinstance(name, bytes) else self.path
        filename = os.path.join(path, name)
        create_file(filename, b'python')
        return filename

    def get_entries(self, names):
        entries = dict((entry.name, entry)
                       for entry in os.scandir(self.path))
        self.assertEqual(sorted(entries.keys()), names)
        return entries

    def assert_stat_equal(self, stat1, stat2, skip_fields):
        if skip_fields:
            for attr in dir(stat1):
                if not attr.startswith("st_"):
                    continue
                if attr in ("st_dev", "st_ino", "st_nlink"):
                    continue
                self.assertEqual(getattr(stat1, attr),
                                 getattr(stat2, attr),
                                 (stat1, stat2, attr))
        else:
            self.assertEqual(stat1, stat2)

    def check_entry(self, entry, name, is_dir, is_file, is_symlink):
        self.assertIsInstance(entry, os.DirEntry)
        self.assertEqual(entry.name, name)
        self.assertEqual(entry.path, os.path.join(self.path, name))
        if self.supports_follow_symlinks:
            self.assertEqual(entry.inode(),
                         os.stat(entry.path, follow_symlinks=False).st_ino)

        entry_stat = os.stat(entry.path)
        self.assertEqual(entry.is_dir(),
                         stat.S_ISDIR(entry_stat.st_mode))
        self.assertEqual(entry.is_file(),
                         stat.S_ISREG(entry_stat.st_mode))
        if self.supports_follow_symlinks:
            self.assertEqual(entry.is_symlink(),
                         os.path.islink(entry.path))

        if self.supports_follow_symlinks:
            entry_lstat = os.stat(entry.path, follow_symlinks=False)
            self.assertEqual(entry.is_dir(follow_symlinks=False),
                            stat.S_ISDIR(entry_lstat.st_mode))
            self.assertEqual(entry.is_file(follow_symlinks=False),
                            stat.S_ISREG(entry_lstat.st_mode))

        self.assert_stat_equal(entry.stat(),
                               entry_stat,
                               False)
        if self.supports_follow_symlinks:
            self.assert_stat_equal(entry.stat(follow_symlinks=False),
                               entry_lstat,
                               False)

    def test_attributes(self):
        link = hasattr(os, 'link')
        symlink = support.can_symlink()

        dirname = os.path.join(self.path, "dir")
        os.mkdir(dirname)
        filename = self.create_file("file.txt")
        if link:
            try:
                os.link(filename, os.path.join(self.path, "link_file.txt"))
            except PermissionError as e:
                self.skipTest('os.link(): %s' % e)
        if symlink:
            os.symlink(dirname, os.path.join(self.path, "symlink_dir"),
                       target_is_directory=True)
            os.symlink(filename, os.path.join(self.path, "symlink_file.txt"))

        names = ['dir', 'file.txt']
        if link:
            names.append('link_file.txt')
        if symlink:
            names.extend(('symlink_dir', 'symlink_file.txt'))
        entries = self.get_entries(names)

        entry = entries['dir']
        self.check_entry(entry, 'dir', True, False, False)

        entry = entries['file.txt']
        self.check_entry(entry, 'file.txt', False, True, False)

        if link:
            entry = entries['link_file.txt']
            self.check_entry(entry, 'link_file.txt', False, True, False)

        if symlink:
            entry = entries['symlink_dir']
            self.check_entry(entry, 'symlink_dir', True, False, True)

            entry = entries['symlink_file.txt']
            self.check_entry(entry, 'symlink_file.txt', False, True, True)

    def get_entry(self, name):
        path = self.bytes_path if isinstance(name, bytes) else self.path
        entries = list(os.scandir(path))
        self.assertEqual(len(entries), 1)

        entry = entries[0]
        self.assertEqual(entry.name, name)
        return entry

    def create_file_entry(self, name='file.txt'):
        filename = self.create_file(name=name)
        return self.get_entry(os.path.basename(filename))

    def test_current_directory(self):
        filename = self.create_file()
        old_dir = os.getcwd()
        try:
            os.chdir(self.path)

            # call scandir() without parameter: it must list the content
            # of the current directory
            entries = dict((entry.name, entry) for entry in os.scandir())
            self.assertEqual(sorted(entries.keys()),
                             [os.path.basename(filename)])
        finally:
            os.chdir(old_dir)

    def test_repr(self):
        entry = self.create_file_entry()
        self.assertEqual(repr(entry), "<DirEntry 'file.txt'>")

    @unittest.skipUnless(hasattr(os, 'PathLike'), 'needs path protocol')
    def test_fspath_protocol(self):
        entry = self.create_file_entry()
        self.assertEqual(os.fspath(entry), os.path.join(self.path, 'file.txt'))

    @unittest.skipUnless(hasattr(os, 'PathLike'), 'needs path protocol')
    def test_fspath_protocol_bytes(self):
        bytes_filename = os.fsencode('bytesfile.txt')
        bytes_entry = self.create_file_entry(name=bytes_filename)
        fspath = os.fspath(bytes_entry)
        self.assertIsInstance(fspath, bytes)
        self.assertEqual(fspath,
                         os.path.join(os.fsencode(self.path),bytes_filename))

    def test_removed_dir(self):
        path = os.path.join(self.path, 'dir')

        os.mkdir(path)
        entry = self.get_entry('dir')
        os.rmdir(path)

        # On POSIX, is_dir() result depends if scandir() filled d_type or not
        self.assertFalse(entry.is_file())
        if self.supports_follow_symlinks:
            self.assertFalse(entry.is_symlink())
        # self.assertGreater(entry.inode(), 0)
        self.assertRaises(FileNotFoundError, entry.stat)
        if self.supports_follow_symlinks:
            self.assertRaises(FileNotFoundError, entry.stat, follow_symlinks=False)

    def test_removed_file(self):
        entry = self.create_file_entry()
        os.unlink(entry.path)

        self.assertFalse(entry.is_dir())
        # On POSIX, is_dir() result depends if scandir() filled d_type or not
        if self.supports_follow_symlinks:
            self.assertFalse(entry.is_symlink())
        # self.assertGreater(entry.inode(), 0)
        self.assertRaises(FileNotFoundError, entry.stat)
        if self.supports_follow_symlinks:
            self.assertRaises(FileNotFoundError, entry.stat, follow_symlinks=False)

    def test_broken_symlink(self):
        if not support.can_symlink():
            return self.skipTest('cannot create symbolic link')

        filename = self.create_file("file.txt")
        os.symlink(filename,
                   os.path.join(self.path, "symlink.txt"))
        entries = self.get_entries(['file.txt', 'symlink.txt'])
        entry = entries['symlink.txt']
        os.unlink(filename)

        # self.assertGreater(entry.inode(), 0)
        self.assertFalse(entry.is_dir())
        self.assertFalse(entry.is_file())  # broken symlink returns False
        self.assertFalse(entry.is_dir(follow_symlinks=False))
        self.assertFalse(entry.is_file(follow_symlinks=False))
        self.assertTrue(entry.is_symlink())
        self.assertRaises(FileNotFoundError, entry.stat)
        # don't fail
        entry.stat(follow_symlinks=False)

    def test_bytes(self):
        self.create_file("file.txt")

        path_bytes = os.fsencode(self.path)
        entries = list(os.scandir(path_bytes))
        self.assertEqual(len(entries), 1, entries)
        entry = entries[0]

        self.assertEqual(entry.name, b'file.txt')
        self.assertEqual(entry.path,
                         os.fsencode(os.path.join(self.path, 'file.txt')))

    @unittest.skipUnless(os.listdir in os.supports_fd,
                         'fd support for listdir required for this test.')
    def test_fd(self):
        self.assertIn(os.scandir, os.supports_fd)
        self.create_file('file.txt')
        expected_names = ['file.txt']
        if support.can_symlink():
            os.symlink('file.txt', os.path.join(self.path, 'link'))
            expected_names.append('link')

        fd = os.open(self.path, os.O_RDONLY)
        try:
            with os.scandir(fd) as it:
                entries = list(it)
            names = [entry.name for entry in entries]
            self.assertEqual(sorted(names), expected_names)
            self.assertEqual(names, os.listdir(fd))
            for entry in entries:
                self.assertEqual(entry.path, entry.name)
                self.assertEqual(os.fspath(entry), entry.name)
                if self.supports_follow_symlinks:
                    self.assertEqual(entry.is_symlink(), entry.name == 'link')
                if os.stat in os.supports_dir_fd:
                    st = os.stat(entry.name, dir_fd=fd)
                    self.assertEqual(entry.stat(), st)
                    if self.supports_follow_symlinks:
                        st = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                        self.assertEqual(entry.stat(follow_symlinks=False), st)
        finally:
            os.close(fd)

    def test_empty_path(self):
        self.assertRaises(FileNotFoundError, os.scandir, '')

    def test_consume_iterator_twice(self):
        self.create_file("file.txt")
        iterator = os.scandir(self.path)

        entries = list(iterator)
        self.assertEqual(len(entries), 1, entries)

        # check than consuming the iterator twice doesn't raise exception
        entries2 = list(iterator)
        self.assertEqual(len(entries2), 0, entries2)

    def test_bad_path_type(self):
        for obj in [1.234, {}, []]:
            self.assertRaises(TypeError, os.scandir, obj)

    def test_close(self):
        self.create_file("file.txt")
        self.create_file("file2.txt")
        iterator = os.scandir(self.path)
        next(iterator)
        iterator.close()
        # multiple closes
        iterator.close()
        with self.check_no_resource_warning():
            del iterator

    def test_context_manager(self):
        self.create_file("file.txt")
        self.create_file("file2.txt")
        with os.scandir(self.path) as iterator:
            next(iterator)
        with self.check_no_resource_warning():
            del iterator

    def test_context_manager_close(self):
        self.create_file("file.txt")
        self.create_file("file2.txt")
        with os.scandir(self.path) as iterator:
            next(iterator)
            iterator.close()

    def test_context_manager_exception(self):
        self.create_file("file.txt")
        self.create_file("file2.txt")
        with self.assertRaises(ZeroDivisionError):
            with os.scandir(self.path) as iterator:
                next(iterator)
                1/0
        with self.check_no_resource_warning():
            del iterator

    # def test_resource_warning(self):
    #     self.create_file("file.txt")
    #     self.create_file("file2.txt")
    #     iterator = os.scandir(self.path)
    #     next(iterator)
    #     with self.assertWarns(ResourceWarning):
    #         del iterator
    #         support.gc_collect()
    #     # exhausted iterator
    #     iterator = os.scandir(self.path)
    #     list(iterator)
    #     with self.check_no_resource_warning():
    #         del iterator


@unittest.skipUnless(hasattr(os, 'fspath'), "requires os.fspath")
class TestPEP519(unittest.TestCase):

    # Abstracted so it can be overridden to test pure Python implementation
    # if a C version is provided.
    fspath = staticmethod(getattr(os, 'fspath', None))

    def test_return_bytes(self):
        for b in b'hello', b'goodbye', b'some/path/and/file':
            self.assertEqual(b, self.fspath(b))

    def test_return_string(self):
        for s in 'hello', 'goodbye', 'some/path/and/file':
            self.assertEqual(s, self.fspath(s))

    def test_fsencode_fsdecode(self):
        for p in "path/like/object", b"path/like/object":
            pathlike = FakePath(p)

            self.assertEqual(p, self.fspath(pathlike))
            self.assertEqual(b"path/like/object", os.fsencode(pathlike))
            self.assertEqual("path/like/object", os.fsdecode(pathlike))

    @unittest.skipUnless(hasattr(os, 'PathLike'), 'needs path protocol')
    def test_pathlike(self):
        self.assertEqual('#feelthegil', self.fspath(FakePath('#feelthegil')))
        self.assertTrue(issubclass(FakePath, os.PathLike))
        self.assertTrue(isinstance(FakePath('x'), os.PathLike))

    def test_garbage_in_exception_out(self):
        vapor = type('blah', (), {})
        for o in int, type, os, vapor():
            self.assertRaises(TypeError, self.fspath, o)

    def test_argument_required(self):
        self.assertRaises(TypeError, self.fspath)

    def test_bad_pathlike(self):
        # __fspath__ returns a value other than str or bytes.
        self.assertRaises(TypeError, self.fspath, FakePath(42))
        # __fspath__ attribute that is not callable.
        c = type('foo', (), {})
        c.__fspath__ = 1
        self.assertRaises(TypeError, self.fspath, c())
        # __fspath__ raises an exception.
        self.assertRaises(ZeroDivisionError, self.fspath,
                          FakePath(ZeroDivisionError()))

    @unittest.skipUnless(hasattr(os, 'PathLike'), 'needs path protocol')
    def test_pathlike_subclasshook(self):
        # bpo-38878: subclasshook causes subclass checks
        # true on abstract implementation.
        class A(os.PathLike):
            pass
        self.assertFalse(issubclass(FakePath, A))
        self.assertTrue(issubclass(FakePath, os.PathLike))


class TimesTests(unittest.TestCase):
    def test_times(self):
        times = os.times()
        # self.assertIsInstance(times, os.times_result)

        for field in ('user', 'system', 'children_user', 'children_system',
                      'elapsed'):
            value = getattr(times, field)
            self.assertIsInstance(value, float)


if __name__ == "__main__":
    unittest.main()
