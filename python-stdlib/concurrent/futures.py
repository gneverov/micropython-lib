# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
Simple concurrent.futures implementation for MicroPython
Compatible with Python's concurrent.futures module API
"""

import threading
import time
from collections import deque

# Future states
PENDING = 'PENDING'
RUNNING = 'RUNNING'
CANCELLED = 'CANCELLED'
CANCELLED_AND_NOTIFIED = 'CANCELLED_AND_NOTIFIED'
FINISHED = 'FINISHED'

# Module-level constants
FIRST_COMPLETED = 'FIRST_COMPLETED'
FIRST_EXCEPTION = 'FIRST_EXCEPTION'
ALL_COMPLETED = 'ALL_COMPLETED'

class Error(Exception):
    """Base class for all concurrent.futures exceptions"""
    pass

class CancelledError(Error):
    """The Future was cancelled"""
    pass

class TimeoutError(Error):
    """The operation exceeded the given deadline"""
    pass

class InvalidStateError(Error):
    """The Future is not in a valid state for this operation"""
    pass

class Future:
    """
    Represents the result of an asynchronous computation.
    """
    
    def __init__(self):
        self._condition = threading.Condition()
        self._state = PENDING
        self._result = None
        self._exception = None
        self._done_callbacks = []
        
    def __repr__(self):
        with self._condition:
            if self._state == FINISHED:
                if self._exception:
                    return f'<Future at {id(self):#x} state=finished raised {self._exception.__class__.__name__}>'
                else:
                    return f'<Future at {id(self):#x} state=finished returned {type(self._result).__name__}>'
            return f'<Future at {id(self):#x} state={self._state}>'
    
    def cancel(self):
        """Cancel the future if possible"""
        with self._condition:
            if self._state != PENDING:
                return False
            
            self._state = CANCELLED
            self._condition.notify_all()
            
        self._invoke_callbacks()
        return True
    
    def cancelled(self):
        """Return True if the future was cancelled"""
        with self._condition:
            return self._state in [CANCELLED, CANCELLED_AND_NOTIFIED]
    
    def running(self):
        """Return True if the future is currently running"""
        with self._condition:
            return self._state == RUNNING
    
    def done(self):
        """Return True if the future is done (completed, cancelled, or failed)"""
        with self._condition:
            return self._state in [CANCELLED, CANCELLED_AND_NOTIFIED, FINISHED]
    
    def result(self, timeout=None):
        """Return the result of the future"""
        with self._condition:
            if self._state in [CANCELLED, CANCELLED_AND_NOTIFIED]:
                raise CancelledError()
            elif self._state == FINISHED:
                if self._exception:
                    raise self._exception
                else:
                    return self._result
            
            self._condition.wait(timeout)
            
            if self._state in [CANCELLED, CANCELLED_AND_NOTIFIED]:
                raise CancelledError()
            elif self._state == FINISHED:
                if self._exception:
                    raise self._exception
                else:
                    return self._result
            else:
                raise TimeoutError()
    
    def exception(self, timeout=None):
        """Return the exception raised by the future"""
        with self._condition:
            if self._state in [CANCELLED, CANCELLED_AND_NOTIFIED]:
                raise CancelledError()
            elif self._state == FINISHED:
                return self._exception
            
            self._condition.wait(timeout)
            
            if self._state in [CANCELLED, CANCELLED_AND_NOTIFIED]:
                raise CancelledError()
            elif self._state == FINISHED:
                return self._exception
            else:
                raise TimeoutError()
    
    def add_done_callback(self, fn):
        """Add a callback to be called when the future is done"""
        with self._condition:
            if self._state not in [CANCELLED, CANCELLED_AND_NOTIFIED, FINISHED]:
                self._done_callbacks.append(fn)
                return
        
        # Future is already done, call callback immediately
        try:
            fn(self)
        except Exception:
            # Ignore exceptions in callbacks
            pass
    
    def remove_done_callback(self, fn):
        """Remove a callback from the future"""
        with self._condition:
            try:
                self._done_callbacks.remove(fn)
                return True
            except ValueError:
                return False
    
    def set_result(self, result):
        """Set the result of the future"""
        with self._condition:
            if self._state != PENDING:
                raise InvalidStateError()
            self._result = result
            self._state = FINISHED
            self._condition.notify_all()
        
        self._invoke_callbacks()
    
    def set_exception(self, exception):
        """Set the exception of the future"""
        with self._condition:
            if self._state != PENDING:
                raise InvalidStateError()
            self._exception = exception
            self._state = FINISHED
            self._condition.notify_all()
        
        self._invoke_callbacks()
    
    def set_running_or_notify_cancel(self):
        """Mark the future as running or handle cancellation"""
        with self._condition:
            if self._state == CANCELLED:
                self._state = CANCELLED_AND_NOTIFIED
                self._condition.notify_all()
                return False
            elif self._state == PENDING:
                self._state = RUNNING
                return True
            else:
                raise InvalidStateError()
    
    def _invoke_callbacks(self):
        """Invoke all done callbacks"""
        for callback in self._done_callbacks:
            try:
                callback(self)
            except Exception:
                # Ignore exceptions in callbacks
                pass

class Executor:
    """Abstract base class for executors"""
    
    def submit(self, fn, *args, **kwargs):
        """Submit a callable to be executed"""
        raise NotImplementedError()
    
    def map(self, func, *iterables, timeout=None, chunksize=1):
        """Return an iterator over the results of applying func to each element"""
        if timeout is not None:
            end_time = time.time() + timeout
        
        futures = [self.submit(func, *args) for args in zip(*iterables)]
        
        for future in futures:
            if timeout is not None:
                remaining_timeout = end_time - time.time()
                if remaining_timeout <= 0:
                    raise TimeoutError()
            else:
                remaining_timeout = None
            
            yield future.result(remaining_timeout)
    
    def shutdown(self, wait=True):
        """Shutdown the executor"""
        pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown(wait=True)

class ThreadPoolExecutor(Executor):
    """Executor that uses a pool of threads"""
    
    def __init__(self, max_workers=None, thread_name_prefix='', initializer=None, initargs=()):
        if max_workers is None:
            # Default to number of processors, but at least 1
            max_workers = min(32, (threading.active_count() or 1) + 4)
        
        if max_workers <= 0:
            raise ValueError("max_workers must be greater than 0")
        
        self._max_workers = max_workers
        self._threads = set()
        self._thread_name_prefix = thread_name_prefix
        self._initializer = initializer
        self._initargs = initargs
        self._work_queue = deque()
        self._threads_queues = {}
        self._shutdown = False
        self._shutdown_lock = threading.Lock()
        self._queue_condition = threading.Condition()
    
    def submit(self, fn, *args, **kwargs):
        """Submit a callable to be executed"""
        with self._shutdown_lock:
            if self._shutdown:
                raise RuntimeError('cannot schedule new futures after shutdown')
            
            future = Future()
            work_item = _WorkItem(future, fn, args, kwargs)
            
            with self._queue_condition:
                self._work_queue.append(work_item)
                self._adjust_thread_count()
                self._queue_condition.notify()
            
            return future
    
    def _adjust_thread_count(self):
        """Adjust the number of worker threads"""
        # Remove dead threads
        for t in list(self._threads):
            if not t.is_alive():
                self._threads.discard(t)
        
        # Start new threads if needed
        if len(self._work_queue) > 0 and len(self._threads) < self._max_workers:
            thread_name = f'{self._thread_name_prefix}Thread-{len(self._threads)}'
            t = threading.Thread(target=self._worker, name=thread_name, daemon=True)
            t.start()
            self._threads.add(t)
    
    def _worker(self):
        """Worker thread function"""
        if self._initializer is not None:
            try:
                self._initializer(*self._initargs)
            except BaseException:
                # If initialization fails, don't process any work items
                return
        
        while True:
            with self._queue_condition:
                # Wait for work or shutdown
                while not self._work_queue and not self._shutdown:
                    self._queue_condition.wait()
                
                if self._shutdown:
                    break
                
                if self._work_queue:
                    work_item = self._work_queue.popleft()
                else:
                    continue
            
            # Execute the work item
            work_item.run()
    
    def shutdown(self, wait=True):
        """Shutdown the executor"""
        with self._shutdown_lock:
            self._shutdown = True
            
        with self._queue_condition:
            self._queue_condition.notify_all()
        
        if wait:
            for t in self._threads:
                t.join()

class _WorkItem:
    """Represents a work item to be executed by a worker thread"""
    
    def __init__(self, future, fn, args, kwargs):
        self.future = future
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        """Execute the work item"""
        if not self.future.set_running_or_notify_cancel():
            return
        
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.future.set_result(result)
        except BaseException as exc:
            self.future.set_exception(exc)

def as_completed(fs, timeout=None):
    """Return an iterator over the given futures as they complete"""
    if timeout is not None:
        end_time = time.time() + timeout
    
    # Convert to set for faster removal
    pending = set(fs)
    
    while pending:
        if timeout is not None:
            remaining_timeout = end_time - time.time()
            if remaining_timeout <= 0:
                raise TimeoutError()
        else:
            remaining_timeout = None
        
        # Simple polling approach - in real implementation this would be more efficient
        for future in list(pending):
            if future.done():
                pending.remove(future)
                yield future
                break
        else:
            # No futures completed, sleep briefly
            time.sleep(0.001)

def wait(fs, timeout=None, return_when=ALL_COMPLETED):
    """Wait for futures to complete"""
    if return_when not in [FIRST_COMPLETED, FIRST_EXCEPTION, ALL_COMPLETED]:
        raise ValueError(f"Invalid return_when value: {return_when}")
    
    if timeout is not None:
        end_time = time.time() + timeout
    
    pending = set(fs)
    done = set()
    
    while pending:
        if timeout is not None:
            remaining_timeout = end_time - time.time()
            if remaining_timeout <= 0:
                break
        
        # Check for completed futures
        for future in list(pending):
            if future.done():
                pending.remove(future)
                done.add(future)
                
                if return_when == FIRST_COMPLETED:
                    return done, pending
                elif return_when == FIRST_EXCEPTION and future.exception():
                    return done, pending
        
        if return_when == ALL_COMPLETED and not pending:
            break
        
        # Sleep briefly to avoid busy waiting
        time.sleep(0.001)
    
    return done, pending

# Export main symbols
__all__ = [
    'FIRST_COMPLETED', 'FIRST_EXCEPTION', 'ALL_COMPLETED',
    'CancelledError', 'TimeoutError', 'InvalidStateError',
    'Future', 'Executor', 'ThreadPoolExecutor',
    'as_completed', 'wait'
]