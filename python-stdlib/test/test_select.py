import errno
import os
import select
import sys
import unittest
from test import support

class SelectTestCase(unittest.TestCase):

    class Nope:
        pass

    class Almost:
        def fileno(self):
            return 'fileno'

    def test_error_conditions(self):
        self.assertRaises(TypeError, select.select, 1, 2, 3)
        self.assertRaises(TypeError, select.select, [self.Nope()], [], [])
        self.assertRaises(TypeError, select.select, [self.Almost()], [], [])
        self.assertRaises(TypeError, select.select, [], [], [], "not a number")
        self.assertRaises(ValueError, select.select, [], [], [], -1)

    def test_errno(self):
        with open(__file__, 'rb') as fp:
            fd = fp.fileno()
            fp.close()
            try:
                select.select([fd], [], [], 0)
            except OSError as err:
                self.assertEqual(err.errno, errno.EBADF)
            else:
                self.fail("exception not raised")

    def test_returned_list_identity(self):
        # See issue #8329
        r, w, x = select.select([], [], [], 1)
        self.assertIsNot(r, w)
        self.assertIsNot(r, x)
        self.assertIsNot(w, x)

    # Issue 16230: Crash on select resized list
    @support.skip_micropython
    def test_select_mutated(self):
        a = []
        class F:
            def fileno(self):
                del a[-1]
                return sys.stdout.fileno()
        a[:] = [F()] * 10
        self.assertEqual(select.select([], a, []), ([], a[:5], []))

def tearDownModule():
    support.reap_children()

if __name__ == "__main__":
    unittest.main()
