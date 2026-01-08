# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

"""Thread module emulating a subset of Java's threading model."""

import sys as _sys
import _thread

from time import monotonic as _time
from collections import deque as _deque

__all__ = ('get_ident', 'active_count', 'Condition', 'current_thread',
           'enumerate', 'main_thread', 'TIMEOUT_MAX',
           'Event', 'Lock', 'RLock', 'Semaphore', 'BoundedSemaphore', 'Thread',
           'Barrier', 'BrokenBarrierError', 'Timer', 'ThreadError',
           'setprofile', 'settrace', 'local', 'stack_size')

# Rename some stuff so "from threading import *" is safe
_allocate_lock = _thread.allocate_lock
get_ident = _thread.get_ident
ThreadError = _thread.error
TIMEOUT_MAX = _thread.TIMEOUT_MAX
del _thread


# Support for profile and trace hooks

_profile_hook = None
_trace_hook = None

def setprofile(func):
    """Set a profile function for all threads started from the threading module.

    The func will be passed to sys.setprofile() for each thread, before its
    run() method is called.

    """
    global _profile_hook
    _profile_hook = func

def settrace(func):
    """Set a trace function for all threads started from the threading module.

    The func will be passed to sys.settrace() for each thread, before its run()
    method is called.

    """
    global _trace_hook
    _trace_hook = func

# Synchronization classes

Lock = _allocate_lock

from _thread import RLock


class Condition:
    """Class that implements a condition variable.

    A condition variable allows one or more threads to wait until they are
    notified by another thread.

    If the lock argument is given and not None, it must be a Lock or RLock
    object, and it is used as the underlying lock. Otherwise, a new RLock object
    is created and used as the underlying lock.

    """

    def __init__(self, lock=None):
        if lock is None:
            lock = RLock()
        self._lock = lock
        # Export the lock's acquire() and release() methods
        self.acquire = lock.acquire
        self.release = lock.release
        # If the lock defines _release_save() and/or _acquire_restore(),
        # these override the default implementations (which just call
        # release() and acquire() on the lock).  Ditto for _is_owned().
        try:
            self._release_save = lock._release_save
        except AttributeError:
            pass
        try:
            self._acquire_restore = lock._acquire_restore
        except AttributeError:
            pass
        try:
            self._is_owned = lock._is_owned
        except AttributeError:
            pass
        self._waiters = _deque()

    def __enter__(self):
        return self._lock.__enter__()

    def __exit__(self, *args):
        return self._lock.__exit__(*args)

    def __repr__(self):
        return "<Condition(%s, %d)>" % (self._lock, len(self._waiters))

    def _release_save(self):
        self._lock.release()           # No state to save

    def _acquire_restore(self, x):
        self._lock.acquire()           # Ignore saved state

    def _is_owned(self):
        # Return True if lock is owned by current_thread.
        # This method is called only if _lock doesn't have _is_owned().
        if self._lock.acquire(0):
            self._lock.release()
            return False
        else:
            return True

    def wait(self, timeout=None):
        """Wait until notified or until a timeout occurs.

        If the calling thread has not acquired the lock when this method is
        called, a RuntimeError is raised.

        This method releases the underlying lock, and then blocks until it is
        awakened by a notify() or notify_all() call for the same condition
        variable in another thread, or until the optional timeout occurs. Once
        awakened or timed out, it re-acquires the lock and returns.

        When the timeout argument is present and not None, it should be a
        floating point number specifying a timeout for the operation in seconds
        (or fractions thereof).

        When the underlying lock is an RLock, it is not released using its
        release() method, since this may not actually unlock the lock when it
        was acquired multiple times recursively. Instead, an internal interface
        of the RLock class is used, which really unlocks it even when it has
        been recursively acquired several times. Another internal interface is
        then used to restore the recursion level when the lock is reacquired.

        """
        if not self._is_owned():
            raise RuntimeError("cannot wait on un-acquired lock")
        waiter = _allocate_lock()
        waiter.acquire()
        self._waiters.append(waiter)
        saved_state = self._release_save()
        gotit = False
        try:    # restore state no matter what (e.g., KeyboardInterrupt)
            if timeout is None:
                waiter.acquire()
                gotit = True
            else:
                if timeout > 0:
                    gotit = waiter.acquire(True, timeout)
                else:
                    gotit = waiter.acquire(False)
            return gotit
        finally:
            self._acquire_restore(saved_state)
            if not gotit:
                try:
                    self._waiters.remove(waiter)
                except ValueError:
                    pass

    def wait_for(self, predicate, timeout=None):
        """Wait until a condition evaluates to True.

        predicate should be a callable which result will be interpreted as a
        boolean value.  A timeout may be provided giving the maximum time to
        wait.

        """
        endtime = None
        waittime = timeout
        result = predicate()
        while not result:
            if waittime is not None:
                if endtime is None:
                    endtime = _time() + waittime
                else:
                    waittime = endtime - _time()
                    if waittime <= 0:
                        break
            self.wait(waittime)
            result = predicate()
        return result

    def notify(self, n=1):
        """Wake up one or more threads waiting on this condition, if any.

        If the calling thread has not acquired the lock when this method is
        called, a RuntimeError is raised.

        This method wakes up at most n of the threads waiting for the condition
        variable; it is a no-op if no threads are waiting.

        """
        if not self._is_owned():
            raise RuntimeError("cannot notify on un-acquired lock")
        while n > 0 and self._waiters:
            waiter = self._waiters.popleft()
            waiter.release()
            n -= 1

    def notify_all(self):
        """Wake up all threads waiting on this condition.

        If the calling thread has not acquired the lock when this method
        is called, a RuntimeError is raised.

        """
        self.notify(len(self._waiters))


class Semaphore:
    """This class implements semaphore objects.

    Semaphores manage a counter representing the number of release() calls minus
    the number of acquire() calls, plus an initial value. The acquire() method
    blocks if necessary until it can return without making the counter
    negative. If not given, value defaults to 1.

    """

    # After Tim Peters' semaphore class, but not quite the same (no maximum)

    def __init__(self, value=1):
        if value < 0:
            raise ValueError("semaphore initial value must be >= 0")
        self._cond = Condition(Lock())
        self._value = value

    def acquire(self, blocking=True, timeout=None):
        """Acquire a semaphore, decrementing the internal counter by one.

        When invoked without arguments: if the internal counter is larger than
        zero on entry, decrement it by one and return immediately. If it is zero
        on entry, block, waiting until some other thread has called release() to
        make it larger than zero. This is done with proper interlocking so that
        if multiple acquire() calls are blocked, release() will wake exactly one
        of them up. The implementation may pick one at random, so the order in
        which blocked threads are awakened should not be relied on. There is no
        return value in this case.

        When invoked with blocking set to true, do the same thing as when called
        without arguments, and return true.

        When invoked with blocking set to false, do not block. If a call without
        an argument would block, return false immediately; otherwise, do the
        same thing as when called without arguments, and return true.

        When invoked with a timeout other than None, it will block for at
        most timeout seconds.  If acquire does not complete successfully in
        that interval, return false.  Return true otherwise.

        """
        if not blocking and timeout is not None:
            raise ValueError("can't specify timeout for non-blocking acquire")
        rc = False
        endtime = None
        with self._cond:
            while self._value == 0:
                if not blocking:
                    break
                if timeout is not None:
                    if endtime is None:
                        endtime = _time() + timeout
                    else:
                        timeout = endtime - _time()
                        if timeout <= 0:
                            break
                self._cond.wait(timeout)
            else:
                self._value -= 1
                rc = True
        return rc

    __enter__ = acquire

    def release(self):
        """Release a semaphore, incrementing the internal counter by one.

        When the counter is zero on entry and another thread is waiting for it
        to become larger than zero again, wake up that thread.

        """
        with self._cond:
            self._value += 1
            self._cond.notify()

    def __exit__(self, t, v, tb):
        self.release()


class BoundedSemaphore(Semaphore):
    """Implements a bounded semaphore.

    A bounded semaphore checks to make sure its current value doesn't exceed its
    initial value. If it does, ValueError is raised. In most situations
    semaphores are used to guard resources with limited capacity.

    If the semaphore is released too many times it's a sign of a bug. If not
    given, value defaults to 1.

    Like regular semaphores, bounded semaphores manage a counter representing
    the number of release() calls minus the number of acquire() calls, plus an
    initial value. The acquire() method blocks if necessary until it can return
    without making the counter negative. If not given, value defaults to 1.

    """

    def __init__(self, value=1):
        Semaphore.__init__(self, value)
        self._initial_value = value

    def release(self):
        """Release a semaphore, incrementing the internal counter by one.

        When the counter is zero on entry and another thread is waiting for it
        to become larger than zero again, wake up that thread.

        If the number of releases exceeds the number of acquires,
        raise a ValueError.

        """
        with self._cond:
            if self._value >= self._initial_value:
                raise ValueError("Semaphore released too many times")
            self._value += 1
            self._cond.notify()


class Event:
    """Class implementing event objects.

    Events manage a flag that can be set to true with the set() method and reset
    to false with the clear() method. The wait() method blocks until the flag is
    true.  The flag is initially false.

    """

    # After Tim Peters' event class (without is_posted())

    def __init__(self):
        self._cond = Condition(Lock())
        self._flag = False

    def is_set(self):
        """Return true if and only if the internal flag is true."""
        return self._flag

    def set(self):
        """Set the internal flag to true.

        All threads waiting for it to become true are awakened. Threads
        that call wait() once the flag is true will not block at all.

        """
        with self._cond:
            self._flag = True
            self._cond.notify_all()

    def clear(self):
        """Reset the internal flag to false.

        Subsequently, threads calling wait() will block until set() is called to
        set the internal flag to true again.

        """
        with self._cond:
            self._flag = False

    def wait(self, timeout=None):
        """Block until the internal flag is true.

        If the internal flag is true on entry, return immediately. Otherwise,
        block until another thread calls set() to set the flag to true, or until
        the optional timeout occurs.

        When the timeout argument is present and not None, it should be a
        floating point number specifying a timeout for the operation in seconds
        (or fractions thereof).

        This method returns the internal flag on exit, so it will always return
        True except if a timeout is given and the operation times out.

        """
        with self._cond:
            signaled = self._flag
            if not signaled:
                signaled = self._cond.wait(timeout)
            return signaled


# A barrier class.  Inspired in part by the pthread_barrier_* api and
# the CyclicBarrier class from Java.  See
# http://sourceware.org/pthreads-win32/manual/pthread_barrier_init.html and
# http://java.sun.com/j2se/1.5.0/docs/api/java/util/concurrent/
#        CyclicBarrier.html
# for information.
# We maintain two main states, 'filling' and 'draining' enabling the barrier
# to be cyclic.  Threads are not allowed into it until it has fully drained
# since the previous cycle.  In addition, a 'resetting' state exists which is
# similar to 'draining' except that threads leave with a BrokenBarrierError,
# and a 'broken' state in which all threads get the exception.
class Barrier:
    """Implements a Barrier.

    Useful for synchronizing a fixed number of threads at known synchronization
    points.  Threads block on 'wait()' and are simultaneously awoken once they
    have all made that call.

    """

    def __init__(self, parties, action=None, timeout=None):
        """Create a barrier, initialised to 'parties' threads.

        'action' is a callable which, when supplied, will be called by one of
        the threads after they have all entered the barrier and just prior to
        releasing them all. If a 'timeout' is provided, it is used as the
        default for all subsequent 'wait()' calls.

        """
        self._cond = Condition(Lock())
        self._action = action
        self._timeout = timeout
        self._parties = parties
        self._state = 0 #0 filling, 1, draining, -1 resetting, -2 broken
        self._count = 0

    def wait(self, timeout=None):
        """Wait for the barrier.

        When the specified number of threads have started waiting, they are all
        simultaneously awoken. If an 'action' was provided for the barrier, one
        of the threads will have executed that callback prior to returning.
        Returns an individual index number from 0 to 'parties-1'.

        """
        if timeout is None:
            timeout = self._timeout
        with self._cond:
            self._enter() # Block while the barrier drains.
            index = self._count
            self._count += 1
            try:
                if index + 1 == self._parties:
                    # We release the barrier
                    self._release()
                else:
                    # We wait until someone releases us
                    self._wait(timeout)
                return index
            finally:
                self._count -= 1
                # Wake up any threads waiting for barrier to drain.
                self._exit()

    # Block until the barrier is ready for us, or raise an exception
    # if it is broken.
    def _enter(self):
        while self._state in (-1, 1):
            # It is draining or resetting, wait until done
            self._cond.wait()
        #see if the barrier is in a broken state
        if self._state < 0:
            raise BrokenBarrierError
        assert self._state == 0

    # Optionally run the 'action' and release the threads waiting
    # in the barrier.
    def _release(self):
        try:
            if self._action:
                self._action()
            # enter draining state
            self._state = 1
            self._cond.notify_all()
        except:
            #an exception during the _action handler.  Break and reraise
            self._break()
            raise

    # Wait in the barrier until we are released.  Raise an exception
    # if the barrier is reset or broken.
    def _wait(self, timeout):
        if not self._cond.wait_for(lambda : self._state != 0, timeout):
            #timed out.  Break the barrier
            self._break()
            raise BrokenBarrierError
        if self._state < 0:
            raise BrokenBarrierError
        assert self._state == 1

    # If we are the last thread to exit the barrier, signal any threads
    # waiting for the barrier to drain.
    def _exit(self):
        if self._count == 0:
            if self._state in (-1, 1):
                #resetting or draining
                self._state = 0
                self._cond.notify_all()

    def reset(self):
        """Reset the barrier to the initial state.

        Any threads currently waiting will get the BrokenBarrier exception
        raised.

        """
        with self._cond:
            if self._count > 0:
                if self._state == 0:
                    #reset the barrier, waking up threads
                    self._state = -1
                elif self._state == -2:
                    #was broken, set it to reset state
                    #which clears when the last thread exits
                    self._state = -1
            else:
                self._state = 0
            self._cond.notify_all()

    def abort(self):
        """Place the barrier into a 'broken' state.

        Useful in case of error.  Any currently waiting threads and threads
        attempting to 'wait()' will have BrokenBarrierError raised.

        """
        with self._cond:
            self._break()

    def _break(self):
        # An internal error was detected.  The barrier is set to
        # a broken state all parties awakened.
        self._state = -2
        self._cond.notify_all()

    @property
    def parties(self):
        """Return the number of threads required to trip the barrier."""
        return self._parties

    @property
    def n_waiting(self):
        """Return the number of threads currently waiting at the barrier."""
        # We don't need synchronization here since this is an ephemeral result
        # anyway.  It returns the correct value in the steady state.
        if self._state == 0:
            return self._count
        return 0

    @property
    def broken(self):
        """Return True if the barrier is in a broken state."""
        return self._state == -2

# exception raised by the Barrier class
class BrokenBarrierError(RuntimeError):
    pass


from _thread import Thread


# The timer class was contributed by Itamar Shtull-Trauring

class Timer(Thread):
    """Call a function after a specified number of seconds:

            t = Timer(30.0, f, args=None, kwargs=None)
            t.start()
            t.cancel()     # stop the timer's action if it's still waiting

    """

    def __init__(self, interval, function, args=None, kwargs=None):
        Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
        self.finished = Event()

    def cancel(self):
        """Stop the timer if it hasn't finished yet."""
        self.finished.set()

    def run(self):
        self.finished.wait(self.interval)
        if not self.finished.is_set():
            self.function(*self.args, **self.kwargs)
        self.finished.set()


# Global API functions

from _thread import current_thread, enumerate, stack_size, main_thread

# current_thread.__doc__ = """Return the current Thread object, corresponding to the caller's thread of control.

#     If the caller's thread of control was not created through the threading
#     module, a dummy thread object with limited functionality is returned.
#     """

def active_count():
    """Return the number of Thread objects currently alive.

    The returned count is equal to the length of the list returned by
    enumerate().
    """
    return len(enumerate())

# enumerate.__doc__ = """Return a list of all Thread objects currently alive.

#     The list includes daemonic threads, dummy thread objects created by
#     current_thread(), and the main thread. It excludes terminated threads and
#     threads that have not yet been started.
#     """

# main_thread.__doc__ = """Return the main thread object.

#     In normal conditions, the main thread is the thread from which the
#     Python interpreter was started.
#     """

# Thread local storage

from _thread import local
