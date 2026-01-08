"""
Tests for the threading module.
"""

import test.support
from test.support import (verbose,)

import random
import sys
import _thread
import threading
import time
import unittest
import os
import signal

from test import lock_tests
from test import support


# A trivial mutable counter.
class Counter(object):
    def __init__(self):
        self.value = 0
    def inc(self):
        self.value += 1
    def dec(self):
        self.value -= 1
    def get(self):
        return self.value

class TestThread(threading.Thread):
    def __init__(self, name, testcase, sema, mutex, nrunning):
        threading.Thread.__init__(self, name=name)
        self.testcase = testcase
        self.sema = sema
        self.mutex = mutex
        self.nrunning = nrunning

    def run(self):
        delay = random.random() / 10000.0
        if verbose:
            print('task %s will run for %.1f usec' %
                  (self.name, delay * 1e6))

        # with self.sema:
            with self.mutex:
                self.nrunning.inc()
                if verbose:
                    print(self.nrunning.get(), 'tasks are running')
                # self.testcase.assertLessEqual(self.nrunning.get(), 3)

            time.sleep(delay)
            if verbose:
                print('task', self.name, 'done')

            with self.mutex:
                self.nrunning.dec()
                self.testcase.assertGreaterEqual(self.nrunning.get(), 0)
                if verbose:
                    print('%s is finished. %d tasks are running' %
                          (self.name, self.nrunning.get()))


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self._threads = test.support.threading_setup()

    def tearDown(self):
        test.support.threading_cleanup(*self._threads)
        test.support.reap_children()


class ThreadTests(BaseTestCase):

    # Create a bunch of threads, let each do some work, wait until all are
    # done.
    def test_various_ops(self):
        # This takes about n/3 seconds to run (about n/3 clumps of tasks,
        # times about 1 second per clump).
        NUMTASKS = 10

        # no more than 3 of the 10 can run at once
        # sema = threading.BoundedSemaphore(value=3)
        sema = None
        mutex = threading.RLock()
        numrunning = Counter()

        threads = []

        for i in range(NUMTASKS):
            t = TestThread("<thread %d>"%i, self, sema, mutex, numrunning)
            threads.append(t)
            self.assertIsNone(t.ident)
            # self.assertRegex(repr(t), r'^<TestThread\(.*, initial\)>$')
            t.start()

        if verbose:
            print('waiting for all tasks to complete')
        for t in threads:
            t.join()
            self.assertFalse(t.is_alive())
            self.assertNotEqual(t.ident, 0)
            self.assertIsNotNone(t.ident)
            # self.assertRegex(repr(t), r'^<TestThread\(.*, stopped -?\d+\)>$')
        if verbose:
            print('all tasks done')
        self.assertEqual(numrunning.get(), 0)

    # run with a small(ish) thread stack size (256 KiB)
    @unittest.skip("default stack size is already minimum needed for test")
    def test_various_ops_small_stack(self):
        if verbose:
            print('with 256 KiB thread stack size...')
        try:
            threading.stack_size(2048)
        except _thread.error:
            raise unittest.SkipTest(
                'platform does not support changing thread stack size')
        try:
            self.test_various_ops()
        finally:
            threading.stack_size(0)

    # run with a large thread stack size (1 MiB)
    def test_various_ops_large_stack(self):
        if verbose:
            print('with 1 MiB thread stack size...')
        try:
            threading.stack_size(8192)
        except _thread.error:
            raise unittest.SkipTest(
                'platform does not support changing thread stack size')
        try:
            self.test_various_ops()
        finally:
            threading.stack_size(0)

    def test_foreign_thread(self):
        # Check that a "foreign" thread can use the threading module.
        def f(mutex):
            # Calling current_thread() forces an entry for the foreign
            # thread to get made in the threading._active map.
            threading.current_thread()
            mutex.release()

        mutex = threading.Lock()
        mutex.acquire()
        with support.wait_threads_exit():
            tid = _thread.start_new_thread(f, (mutex,))
            # Wait for the thread to finish.
            mutex.acquire()

    def test_enumerate_after_join(self):
        # Try hard to trigger #1703448: a thread is still returned in
        # threading.enumerate() after it has been join()ed.
        enum = threading.enumerate
        t = threading.Thread(target=lambda: None)
        t.start()
        t.join()
        l = enum()
        self.assertNotIn(t, l)

    def test_main_thread(self):
        main = threading.main_thread()
        self.assertEqual(main.name, 'MainThread')
        self.assertEqual(main.ident, threading.current_thread().ident)
        self.assertEqual(main.ident, threading.get_ident())

        def f():
            self.assertNotEqual(threading.main_thread().ident,
                                threading.current_thread().ident)
        th = threading.Thread(target=f)
        th.start()
        th.join()

    def test_repr_stopped(self):
        # Verify that "stopped" shows up in repr(Thread) appropriately.
        started = _thread.allocate_lock()
        finish = _thread.allocate_lock()
        started.acquire()
        finish.acquire()
        def f():
            started.release()
            finish.acquire()
        t = threading.Thread(target=f)
        t.start()
        started.acquire()
        self.assertIn("started", repr(t))
        finish.release()
        # "stopped" should appear in the repr in a reasonable amount of time.
        # Implementation detail:  as of this writing, that's trivially true
        # if .join() is called, and almost trivially true if .is_alive() is
        # called.  The detail we're testing here is that "stopped" shows up
        # "all on its own".
        LOOKING_FOR = "stopped"
        for i in range(500):
            if LOOKING_FOR in repr(t):
                break
            time.sleep(0.01)
        self.assertIn(LOOKING_FOR, repr(t)) # we waited at least 5 seconds
        t.join()

    @unittest.skipUnless(hasattr(threading, 'BoundedSemaphore'), 'requires BoundedSemaphore')
    def test_BoundedSemaphore_limit(self):
        # BoundedSemaphore should raise ValueError if released too often.
        for limit in range(1, 10):
            bs = threading.BoundedSemaphore(limit)
            threads = [threading.Thread(target=bs.acquire)
                       for _ in range(limit)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            threads = [threading.Thread(target=bs.release)
                       for _ in range(limit)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertRaises(ValueError, bs.release)


class ThreadingExceptionTests(BaseTestCase):
    # A RuntimeError should be raised if Thread.start() is called
    # multiple times.
    def test_start_thread_again(self):
        thread = threading.Thread()
        thread.start()
        self.assertRaises(RuntimeError, thread.start)
        thread.join()

    def test_joining_current_thread(self):
        current_thread = threading.current_thread()
        self.assertRaises(RuntimeError, current_thread.join);

    def test_joining_inactive_thread(self):
        thread = threading.Thread()
        self.assertRaises(RuntimeError, thread.join)

    def test_releasing_unacquired_lock(self):
        lock = threading.Lock()
        self.assertRaises(RuntimeError, lock.release)

    def test_bare_raise_in_brand_new_thread(self):
        def bare_raise():
            raise

        class Issue27558(threading.Thread):
            exc = None
            def __init__(self):
                threading.Thread.__init__(self)

            def run(self):
                try:
                    bare_raise()
                except Exception as exc:
                    self.exc = exc

        thread = Issue27558()
        thread.start()
        thread.join()
        self.assertIsNotNone(thread.exc)
        self.assertIsInstance(thread.exc, RuntimeError)
        # explicitly break the reference cycle to not leak a dangling thread
        thread.exc = None

if hasattr(threading, 'Timer'):
    class TimerTests(BaseTestCase):

        def setUp(self):
            BaseTestCase.setUp(self)
            self.callback_args = []
            self.callback_event = threading.Event()

        def test_init_immutable_default_args(self):
            # Issue 17435: constructor defaults were mutable objects, they could be
            # mutated via the object attributes and affect other Timer objects.
            timer1 = threading.Timer(0.01, self._callback_spy)
            timer1.start()
            self.callback_event.wait()
            timer1.args.append("blah")
            timer1.kwargs["foo"] = "bar"
            self.callback_event.clear()
            timer2 = threading.Timer(0.01, self._callback_spy)
            timer2.start()
            self.callback_event.wait()
            self.assertEqual(len(self.callback_args), 2)
            self.assertEqual(self.callback_args, [((), {}), ((), {})])
            timer1.join()
            timer2.join()

        def _callback_spy(self, *args, **kwargs):
            self.callback_args.append((args[:], kwargs.copy()))
            self.callback_event.set()

if hasattr(threading, 'Lock'):
    class LockTests(lock_tests.LockTests):
        locktype = staticmethod(threading.Lock)

if hasattr(threading, 'RLock'):
    class RLockTests(lock_tests.RLockTests):
        locktype = staticmethod(threading.RLock)

if hasattr(threading, 'Event'):
    class EventTests(lock_tests.EventTests):
        eventtype = staticmethod(threading.Event)

if hasattr(threading, 'Condition'):
    class ConditionAsRLockTests(lock_tests.RLockTests):
        # Condition uses an RLock by default and exports its API.
        locktype = staticmethod(threading.Condition)

    class ConditionTests(lock_tests.ConditionTests):
        condtype = staticmethod(threading.Condition)

if hasattr(threading, 'Semaphore'):
    class SemaphoreTests(lock_tests.SemaphoreTests):
        semtype = staticmethod(threading.Semaphore)

if hasattr(threading, 'BoundedSemaphore'):
    class BoundedSemaphoreTests(lock_tests.BoundedSemaphoreTests):
        semtype = staticmethod(threading.BoundedSemaphore)

if hasattr(threading, 'Barrier'):
    class BarrierTests(lock_tests.BarrierTests):
        barriertype = staticmethod(threading.Barrier)


# class MiscTestCase(unittest.TestCase):
#     def test__all__(self):
#         extra = {"ThreadError"}
#         blacklist = {'currentThread', 'activeCount'}
#         support.check__all__(self, threading, ('threading', '_thread'),
#                              extra=extra, blacklist=blacklist)

class InterruptMainTests(unittest.TestCase):
    def test_interrupt_main_subthread(self):
        # Calling start_new_thread with a function that executes interrupt_main
        # should raise KeyboardInterrupt upon completion.
        def call_interrupt():
            _thread.interrupt_main()
        t = threading.Thread(target=call_interrupt)
        with self.assertRaises(KeyboardInterrupt):
            t.start()
            time.sleep(1)
        t.join()

    def test_interrupt_main_mainthread(self):
        # Make sure that if interrupt_main is called in main thread that
        # KeyboardInterrupt is raised instantly.
        with self.assertRaises(KeyboardInterrupt):
            _thread.interrupt_main()

    def test_interrupt_main_noerror(self):
        handler = signal.getsignal(signal.SIGINT)
        try:
            # No exception should arise.
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            _thread.interrupt_main()

            signal.signal(signal.SIGINT, signal.SIG_DFL)
            _thread.interrupt_main()
        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, handler)


if __name__ == "__main__":
    unittest.main()
