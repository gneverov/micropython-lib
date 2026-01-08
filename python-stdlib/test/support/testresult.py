'''Test runner and result class for the regression test suite.

'''

import functools
import io
import sys
import time
import traceback
import unittest

from datetime import datetime

def get_test_runner_class(verbosity, buffer=False):
    if verbosity:
        return functools.partial(unittest.TextTestRunner,
                                 verbosity=verbosity)
    return functools.partial(unittest.TextTestRunner)

def get_test_runner(stream, verbosity, capture_output=False):
    return get_test_runner_class(verbosity, capture_output)(stream)

if __name__ == '__main__':
    class TestTests(unittest.TestCase):
        def test_pass(self):
            pass

        def test_pass_slow(self):
            time.sleep(1.0)

        def test_fail(self):
            print('stdout', file=sys.stdout)
            print('stderr', file=sys.stderr)
            self.fail('failure message')

        def test_error(self):
            print('stdout', file=sys.stdout)
            print('stderr', file=sys.stderr)
            raise RuntimeError('error message')

    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestTests))
    stream = io.StringIO()
    runner_cls = get_test_runner_class(sum(a == '-v' for a in sys.argv))
    runner = runner_cls(sys.stdout)
    result = runner.run(suite)
    print('Output:', stream.getvalue())
    print('XML: ', end='')
    for s in ET.tostringlist(result.get_xml_element()):
        print(s.decode(), end='')
    print()