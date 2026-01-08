# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
Simple unittest implementation for MicroPython
Compatible with Python's unittest module API
"""

import gc
import re
import sys
import traceback
import time

# Exception classes
class TestFailed(Exception):
    """Exception raised when a test assertion fails"""
    pass

class SkipTest(Exception):
    """Exception raised to skip a test"""
    pass

# Test result tracking
class TestResult:
    """Holds the results of a set of tests"""
    
    def __init__(self):
        self.testsRun = 0
        self.failures = []
        self.errors = []
        self.skipped = []
        self.start_time = None
        self.stop_time = None
    
    def startTest(self, test):
        """Called when a test is about to be run"""
        self.testsRun += 1
    
    def stopTest(self, test):
        """Called when a test has completed"""
        pass
    
    def addError(self, test, error):
        """Called when a test raises an unexpected exception"""
        self.errors.append((str(test), error))
    
    def addFailure(self, test, failure):
        """Called when a test assertion fails"""
        self.failures.append((str(test), failure))
    
    def addSkip(self, test, reason):
        """Called when a test is skipped"""
        self.skipped.append((str(test), reason))
    
    def addSuccess(self, test):
        """Called when a test succeeds"""
        pass

    def startTestRun(self):
        """Called once before any tests are executed"""
        self.start_time = time.time()
    
    def stopTestRun(self):
        """Called once after all tests are executed"""
        self.stop_time = time.time()
    
    def wasSuccessful(self):
        """Return True if all tests passed"""
        return len(self.failures) == 0 and len(self.errors) == 0

# Base test case class
class TestCase:
    """Base class for individual test cases"""
    
    def __init__(self, methodName='runTest'):
        self.method_name = methodName
        self._test_method = getattr(self, methodName)
        self._cleanup_stack = []

    def setUp(self):
        """Method called to prepare the test fixture"""
        pass
    
    def tearDown(self):
        """Method called immediately after the test method"""
        pass
    
    @classmethod
    def setUpClass(cls):
        """Method called to prepare the test class fixture"""
        pass
    
    @classmethod
    def tearDownClass(cls):
        """Method called to tear down the test class fixture"""
        pass
    
    def run(self, result=None):
        """Run the test case"""
        if result is None:
            result = TestResult()
        
        result.startTest(self)
        
        try:
            self.setUp()
        except SkipTest as e:
            result.addSkip(self, str(e))
            return result
        except Exception as e:
            result.addError(self, self._format_exception(e))
            return result
        
        try:
            self._test_method()
        except SkipTest as e:
            result.addSkip(self, str(e))
        except TestFailed as e:
            result.addFailure(self, self._format_exception(e))
        except Exception as e:
            result.addError(self, self._format_exception(e))
        else:
            result.addSuccess(self)
        finally:
            try:
                self.tearDown()
            except Exception as e:
                result.addError(self, self._format_exception(e))
            finally:
                # Clean up all registered cleanup items
                self._run_cleanups(result)
        
        result.stopTest(self)
        return result
    
    def _format_exception(self, exc):
        """Format exception information"""
        try:
            # Try to get traceback if available
            return ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        except:
            # Fallback to simple string representation
            return f"{type(exc).__name__}: {exc}"
    
    def debug(self):
        """Run the test without collecting errors in a TestResult"""
        self.setUp()
        try:
            self._test_method()
        finally:
            self.tearDown()
            self._run_cleanups()
    
    def __str__(self):
        return f"{self.method_name} ({self.__class__.__module__}.{self.__class__.__name__})"
    
    def __repr__(self):
        return f"<{self.__class__.__name__} testMethod={self.method_name}>"
    
    def id(self):
        """Return a string identifying the specific test case"""
        return f"{self.__class__.__module__}.{self.__class__.__name__}.{self.method_name}"
    
    def enterContext(self, context_manager):
        """Enter a context manager and ensure it gets cleaned up after the test"""
        try:
            result = context_manager.__enter__()
            self._cleanup_stack.append((context_manager.__exit__, [None, None, None], {}))
            return result
        except Exception:
            # If __enter__ fails, we still need to call __exit__
            try:
                context_manager.__exit__(*sys.exc_info())
            except Exception:
                pass  # Ignore exceptions from __exit__
            raise
    
    def addCleanup(self, function, *args, **kwargs):
        """Add a function to be called to clean up after the test"""
        self._cleanup_stack.append((function, args, kwargs))
    
    def _run_cleanups(self, result=None):
        """Run all cleanup items in reverse order (LIFO)"""
        while self._cleanup_stack:
            cleanup_item = self._cleanup_stack.pop()
            try:
                function, args, kwargs = cleanup_item
                function(*args, **kwargs)
            except Exception as e:
                if result is not None:
                    result.addError(self, self._format_exception(e))
    
    def subTest(self, msg=None, **params):
        """Return a context manager which executes a subtest"""
        return _SubTest(self, msg, params)
    
    def assertRaisesRegex(self, exception_class, regex, callable_obj=None, *args, **kwargs):
        """Check that an exception is raised and matches a regex pattern"""
        import re
        
        if callable_obj is None:
            # Used as context manager
            return _AssertRaisesContext(exception_class, regex)
        
        # Used as method call
        try:
            callable_obj(*args, **kwargs)
        except exception_class as e:
            if not re.search(regex, str(e)):
                raise TestFailed(f"Exception message '{e}' does not match regex '{regex}'")
            return  # Expected exception with matching message
        except Exception as e:
            raise TestFailed(f"Expected {exception_class.__name__}, got {type(e).__name__}: {e}")
        else:
            raise TestFailed(f"Expected {exception_class.__name__} to be raised")
    
    # Assertion methods
    def fail(self, msg=None):
        """Fail immediately with the given message"""
        raise TestFailed(msg or "Test failed")
    
    def assertTrue(self, expr, msg=None):
        """Check that the expression is true"""
        if not expr:
            msg = msg or f"{expr} is not true"
            raise TestFailed(msg)
    
    def assertFalse(self, expr, msg=None):
        """Check that the expression is false"""
        if expr:
            msg = msg or f"{expr} is not false"
            raise TestFailed(msg)
    
    def assertEqual(self, first, second, msg=None):
        """Check that first == second"""
        if first != second:
            msg = msg or f"{first!r} != {second!r}"
            raise TestFailed(msg)
    
    def assertNotEqual(self, first, second, msg=None):
        """Check that first != second"""
        if first == second:
            msg = msg or f"{first!r} == {second!r}"
            raise TestFailed(msg)
    
    def assertIs(self, first, second, msg=None):
        """Check that first is second"""
        if first is not second:
            msg = msg or f"{first!r} is not {second!r}"
            raise TestFailed(msg)
    
    def assertIsNot(self, first, second, msg=None):
        """Check that first is not second"""
        if first is second:
            msg = msg or f"{first!r} is {second!r}"
            raise TestFailed(msg)
    
    def assertIsNone(self, expr, msg=None):
        """Check that expr is None"""
        if expr is not None:
            msg = msg or f"{expr!r} is not None"
            raise TestFailed(msg)
    
    def assertIsNotNone(self, expr, msg=None):
        """Check that expr is not None"""
        if expr is None:
            msg = msg or "unexpectedly None"
            raise TestFailed(msg)
    
    def assertIn(self, member, container, msg=None):
        """Check that member is in container"""
        if member not in container:
            msg = msg or f"{member!r} not found in {container!r}"
            raise TestFailed(msg)
    
    def assertNotIn(self, member, container, msg=None):
        """Check that member is not in container"""
        if member in container:
            msg = msg or f"{member!r} unexpectedly found in {container!r}"
            raise TestFailed(msg)
    
    def assertGreater(self, first, second, msg=None):
        """Check that first > second"""
        if not first > second:
            msg = msg or f"{first!r} not greater than {second!r}"
            raise TestFailed(msg)
    
    def assertGreaterEqual(self, first, second, msg=None):
        """Check that first >= second"""
        if not first >= second:
            msg = msg or f"{first!r} not greater than or equal to {second!r}"
            raise TestFailed(msg)
    
    def assertLess(self, first, second, msg=None):
        """Check that first < second"""
        if not first < second:
            msg = msg or f"{first!r} not less than {second!r}"
            raise TestFailed(msg)
    
    def assertLessEqual(self, first, second, msg=None):
        """Check that first <= second"""
        if not first <= second:
            msg = msg or f"{first!r} not less than or equal to {second!r}"
            raise TestFailed(msg)
    
    def assertRaises(self, exception_class, callable_obj=None, *args, **kwargs):
        """Check that an exception is raised"""
        if callable_obj is None:
            # Used as context manager (simplified version)
            return _AssertRaisesContext(exception_class)
        
        # Used as method call
        try:
            callable_obj(*args, **kwargs)
        except exception_class:
            return  # Expected exception was raised
        except Exception as e:
            raise TestFailed(f"Expected {exception_class.__name__}, got {type(e).__name__}: {e}")
        else:
            raise TestFailed(f"Expected {exception_class.__name__} to be raised")
    
    def assertIsInstance(self, obj, cls, msg=None):
        """Check that obj is an instance of cls"""
        if not isinstance(obj, cls):
            if isinstance(cls, tuple):
                cls_name = ', '.join(c.__name__ for c in cls)
            else:
                cls_name = cls.__name__
            msg = msg or f"{obj!r} is not an instance of {cls_name}"
            raise TestFailed(msg)
    
    def assertIsNotInstance(self, obj, cls, msg=None):
        """Check that obj is not an instance of cls"""
        if isinstance(obj, cls):
            if isinstance(cls, tuple):
                cls_name = ', '.join(c.__name__ for c in cls)
            else:
                cls_name = cls.__name__
            msg = msg or f"{obj!r} is an instance of {cls_name}"
            raise TestFailed(msg)

    def assertAlmostEqual(self, first, second, places=None, msg=None, delta=None):
        """Check that first and second are approximately equal.

        If delta is provided, checks that abs(first - second) <= delta.
        Otherwise, checks that the values are equal when rounded to 'places' decimal places (default 7).
        """
        if delta is not None and places is not None:
            raise TypeError("specify delta or places not both")

        if delta is not None:
            # Use delta for comparison
            diff = abs(first - second)
            if diff > delta:
                msg = msg or f"{first!r} != {second!r} within {delta!r} delta ({diff!r} difference)"
                raise TestFailed(msg)
        else:
            # Use places for comparison (default 7)
            if places is None:
                places = 7

            # Round to the specified number of places
            diff = abs(first - second)
            if round(diff, places) != 0:
                msg = msg or f"{first!r} != {second!r} within {places} places ({diff!r} difference)"
                raise TestFailed(msg)

    def assertNotAlmostEqual(self, first, second, places=None, msg=None, delta=None):
        """Check that first and second are NOT approximately equal.

        If delta is provided, checks that abs(first - second) > delta.
        Otherwise, checks that the values differ when rounded to 'places' decimal places (default 7).
        """
        if delta is not None and places is not None:
            raise TypeError("specify delta or places not both")

        if delta is not None:
            # Use delta for comparison
            diff = abs(first - second)
            if diff <= delta:
                msg = msg or f"{first!r} == {second!r} within {delta!r} delta ({diff!r} difference)"
                raise TestFailed(msg)
        else:
            # Use places for comparison (default 7)
            if places is None:
                places = 7

            # Round to the specified number of places
            diff = abs(first - second)
            if round(diff, places) == 0:
                msg = msg or f"{first!r} == {second!r} within {places} places"
                raise TestFailed(msg)

    def assertCountEqual(self, first, second, msg=None):
        """Check that len(first) == len(second)"""
        if len(first) != len(second):
            msg = msg or f"len({first!r}) != len({second!r})"
            raise TestFailed(msg)

    def skipTest(self, reason):
        """Skip this test with the given reason"""
        raise SkipTest(reason)

# Context manager for assertRaises
class _AssertRaisesContext:
    """Context manager for assertRaises"""
    
    def __init__(self, expected_exception, regex=None):
        self.expected_exception = expected_exception
        self.regex = regex
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is None:
            raise TestFailed(f"Expected {self.expected_exception.__name__} to be raised")
        self.exception = exc_value
        if not issubclass(exc_type, self.expected_exception):
            # Let the exception propagate
            return False
        
        # Check if exception message matches regex
        if self.regex and not re.search(self.regex, str(exc_value)):
            raise TestFailed(f"Exception message '{exc_value}' does not match regex '{self.regex}'")
        
        # Exception was expected and message matches, suppress it
        return True

# Context manager for subTest
class _SubTest:
    """Context manager for subTest"""
    
    def __init__(self, test_case, msg, params):
        self.test_case = test_case
        self.msg = msg
        self.params = params
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None and issubclass(exc_type, (TestFailed, Exception)):
            # Format subtest failure message
            param_str = ', '.join(f'{k}={v!r}' for k, v in self.params.items())
            subtest_msg = f"SubTest"
            if self.msg:
                subtest_msg += f" ({self.msg})"
            if param_str:
                subtest_msg += f" [{param_str}]"
            
            # Create a modified exception with subtest information
            if isinstance(exc_value, TestFailed):
                original_msg = str(exc_value)
                new_msg = f"{subtest_msg}: {original_msg}" if original_msg else subtest_msg
                raise TestFailed(new_msg) from exc_value
            else:
                # For other exceptions, let them propagate but add context
                return False
        
        return False

# Test suite class
class TestSuite:
    """A collection of test cases"""

    def __init__(self, tests=(), _setUp=None, _tearDown=None):
        self._test_generators = []
        self._setUp = _setUp
        self._tearDown = _tearDown
        if tests:
            self.addTests(tests)
    
    def addTest(self, test):
        """Add a single test case or suite"""
        if hasattr(test, '__iter__') and not isinstance(test, TestCase):
            # It's iterable (like another suite)
            self._test_generators.append(test)
        else:
            # It's a single test case
            self._test_generators.append([test])
    
    def addTests(self, tests):
        """Add multiple test cases"""
        self._test_generators.append(tests)
    
    def run(self, result=None):
        """Run all tests in the suite"""
        if result is None:
            result = TestResult()

        # Call setUp if provided
        if self._setUp is not None:
            try:
                self._setUp()
            except SkipTest as e:
                result.addSkip(self, str(e))
                return result                
            except Exception as e:
                result.addError(self, str(e))
                return result

        try:
            for test in self:
                test.run(result)
        finally:
            # Call tearDown if provided
            if self._tearDown is not None:
                try:
                    self._tearDown()
                except Exception as e:
                    result.addError(self, str(e))

        return result
    
    def __iter__(self):
        """Iterate through all tests lazily"""
        for test_gen in self._test_generators:
            for test in test_gen:
                yield test
    
    def countTestCases(self):
        """Return the number of test cases in this suite"""
        count = 0
        for test in self:
            count += 1
        return count

# Test loader class
class TestLoader:
    """Load test cases and suites from classes and modules"""
    
    def __init__(self):
        self.test_method_prefix = 'test'
    
    def loadTestsFromTestCase(self, testcase_class):
        """Load all test methods from a TestCase class"""
        # Get setUpClass and tearDownClass if they exist
        setUp = getattr(testcase_class, 'setUpClass', None)
        tearDown = getattr(testcase_class, 'tearDownClass', None)
        return TestSuite(_TestCaseIterator(testcase_class, self), _setUp=setUp, _tearDown=tearDown)
       
    def loadTestsFromModule(self, module):
        """Load all TestCase classes from a module"""
        # Get setUpModule and tearDownModule if they exist
        setUp = getattr(module, 'setUpModule', None)
        tearDown = getattr(module, 'tearDownModule', None)
        suite = TestSuite(_ModuleTestIterator(module, self), _setUp=setUp, _tearDown=tearDown)
        return suite

# Iterator classes for memory-efficient test loading
class _TestCaseIterator:
    """Iterator that yields TestCase instances one at a time"""
    
    def __init__(self, testcase_class, loader):
        self.testcase_class = testcase_class
        self.loader = loader
    
    def __iter__(self):
        for name in dir(self.testcase_class):
            if name.startswith(self.loader.test_method_prefix):
                yield self.testcase_class(name)

class _ModuleTestIterator:
    """Iterator that yields TestCase iterators from a module"""
    
    def __init__(self, module, loader):
        self.module = module
        self.loader = loader
    
    def __iter__(self):
        for name in dir(self.module):
            obj = getattr(self.module, name)
            if isinstance(obj, type) and issubclass(obj, TestCase):
                yield self.loader.loadTestsFromTestCase(obj)

class TextTestResult(TestResult):
    def __init__(self, stream, verbosity):
        super().__init__()
        self.stream = stream
        self.verbosity = verbosity

    def startTest(self, test):
        super().startTest(test)
        if self.verbosity > 1:
            self.stream.write(f"{test} ... ")

    def stopTest(self, test):
        super().stopTest(test)
        gc.collect()

    def stopTestRun(self):
        super().stopTestRun()
        if self.verbosity == 1:
            self.stream.write("\n")

    def addError(self, test, error):
        super().addError(test, error)
        if self.verbosity:
            self.stream.write("ERROR\n" if self.verbosity > 1 else "E")
            if self.verbosity > 2:
                self.stream.write(f"{error}\n")
            self.stream.flush()
    
    def addFailure(self, test, failure):
        super().addFailure(test, failure)
        if self.verbosity:
            self.stream.write("FAIL\n" if self.verbosity > 1 else "F")
            if self.verbosity > 2:
                self.stream.write(f"{failure}\n")
            self.stream.flush()
    
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        if self.verbosity:
            self.stream.write(f"skipped {reason!r}\n" if self.verbosity > 1 else "s")
            self.stream.flush()
    
    def addSuccess(self, test):
        super().addSuccess(test)
        if self.verbosity:
            self.stream.write("ok\n" if self.verbosity > 1 else ".")
            self.stream.flush()

# Test runner class
class TextTestRunner:
    """A test runner class that displays results in textual form"""
    
    def __init__(self, stream=None, verbosity=1):
        self.stream = stream or sys.stdout
        self.verbosity = verbosity
    
    def run(self, test):
        """Run the given test case or test suite"""
        result = TextTestResult(self.stream, self.verbosity)
        result.startTestRun()

        test.run(result)

        result.stopTestRun()
        self._print_results(result)
        return result
    
    def _print_results(self, result):
        """Print test results"""
        if self.verbosity > 0:
            # Print errors
            for test, error in result.errors:
                self.stream.write(f"{'='*70}\n")
                self.stream.write(f"ERROR: {test}\n")
                self.stream.write(f"{'-'*70}\n")
                self.stream.write(f"{error}\n")

            # Print failures
            for test, failure in result.failures:
                self.stream.write(f"{'='*70}\n")
                self.stream.write(f"FAIL: {test}\n")
                self.stream.write(f"{'-'*70}\n")
                self.stream.write(f"{failure}\n")

            self.stream.write(f"{'-'*70}\n")
            self.stream.write(f"Ran {result.testsRun} test(s) ")
            if result.start_time and result.stop_time:
                elapsed = result.stop_time - result.start_time
                self.stream.write(f"in {elapsed:.3f}s\n\n")
            else:
                self.stream.write("\n\n")
            
            if result.wasSuccessful():
                self.stream.write("OK")
            else:
                self.stream.write("FAILED")
                
            # Print summary
            fail_count = len(result.failures)
            error_count = len(result.errors)
            skip_count = len(result.skipped)
            
            summary = []
            if fail_count:
                summary.append(f"failures={fail_count}")
            if error_count:
                summary.append(f"errors={error_count}")
            if skip_count:
                summary.append(f"skipped={skip_count}")
            
            if summary:
                self.stream.write(f" ({', '.join(summary)})\n")
            else:
                self.stream.write("\n")

# Module-level convenience functions
def main(module='__main__', exit=False, verbosity=1, argv=None):
    """Main entry point for running tests"""
    if isinstance(module, str):
        # Import module by name
        if module == '__main__':
            import __main__ as test_module
        else:
            test_module = __import__(module, None, None, [''])
    else:
        test_module = module
    
    loader = TestLoader()
    suite = loader.loadTestsFromModule(test_module)
    runner = TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    if exit:
        sys.exit(0 if result.was_successful() else 1)
    
    return result

# Create default test loader
defaultTestLoader = None
# Skip decorator
def skip(reason):
    """Skip a test with the given reason"""
    def decorator(test_func):
        def wrapper(*args, **kwargs):
            raise SkipTest(reason)
        return wrapper
    return decorator

def skipIf(condition, reason):
    """Skip a test if condition is true"""
    def decorator(test_func):
        if condition:
            return skip(reason)(test_func)
        return test_func
    return decorator

def skipUnless(condition, reason):
    """Skip a test unless condition is true"""
    return skipIf(not condition, reason)

# Export main symbols
__all__ = (
    'TestCase', 'TestResult', 'TestSuite', 'TextTestRunner', 'TestLoader',
    'main', 'skip', 'skipIf', 'skipUnless', 'SkipTest'
)

def __thaw__(self):
    # Name the logger after the package.
    self.defaultTestLoader = TestLoader()