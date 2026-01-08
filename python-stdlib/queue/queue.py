# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT
 
"""
Pure Python implementation of the queue module
Uses collections.deque for data structure and threading.Event for synchronization
Compatible with Python's queue module API
"""

import threading
import time
from collections import deque
import heapq

# Exception classes
class Empty(Exception):
    """Exception raised by Queue.get(block=0)/get_nowait()."""
    pass

class Full(Exception):
    """Exception raised by Queue.put(block=0)/put_nowait()."""
    pass

# Base Queue class
class Queue:
    """Create a queue object with a given maximum size.

    If maxsize is <= 0, the queue size is infinite.
    """

    def __init__(self, maxsize=0):
        self._maxsize = maxsize
        self._init(maxsize)
        
        # Synchronization primitives
        self._mutex = threading.RLock()
        
        # Events for blocking operations
        self._not_empty = threading.Event()
        self._not_full = threading.Event()
        
        # Task tracking for join()
        self._unfinished_tasks = 0
        self._finished = threading.Event()
        self._finished.set()  # Initially no unfinished tasks
        
    def task_done(self):
        """Indicate that a formerly enqueued task is complete.

        Used by Queue consumer threads. For each get() used to fetch a task,
        a subsequent call to task_done() tells the queue that the processing
        on the task is complete.

        If a join() is currently blocking, it will resume when all items
        have been processed (meaning that a task_done() call was received
        for every item that had been put() into the queue).

        Raises a ValueError if called more times than there were items
        placed in the queue.
        """
        with self._mutex:
            if self._unfinished_tasks <= 0:
                raise ValueError('task_done() called too many times')
            self._unfinished_tasks -= 1
            if self._unfinished_tasks == 0:
                self._finished.set()

    def join(self):
        """Blocks until all items in the Queue have been gotten and processed.

        The count of unfinished tasks goes up whenever an item is added to the
        queue. The count goes down whenever a consumer calls task_done() to
        indicate the item was retrieved and all work on it is complete.

        When the count of unfinished tasks drops to zero, join() unblocks.
        """
        with self._mutex:
            while self._unfinished_tasks:
                self._mutex.release()
                try:
                    self._finished.wait()
                finally:
                    assert self._mutex.acquire()

    def qsize(self):
        """Return the approximate size of the queue."""
        with self._mutex:
            return len(self._deque)

    def empty(self):
        """Return True if the queue is empty, False otherwise.

        If empty() returns True it doesn't guarantee that a subsequent call to
        put() will not block. Similarly, if empty() returns False it doesn't
        guarantee that a subsequent call to get() will not block.
        """
        with self._mutex:
            return not self._deque

    def full(self):
        """Return True if the queue is full, False otherwise.

        If full() returns True it doesn't guarantee that a subsequent call to
        get() will not block. Similarly, if full() returns False it doesn't
        guarantee that a subsequent call to put() will not block.
        """
        with self._mutex:
            if self._maxsize <= 0:
                return False
            return len(self._deque) >= self._maxsize

    def put(self, item, block=True, timeout=None):
        """Put an item into the queue.

        If optional args 'block' is true and 'timeout' is None (the default),
        block if necessary until a free slot is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the Full exception if no free slot was available within that time.
        Otherwise ('block' is false), put an item on the queue if a free slot
        is immediately available, else raise the Full exception ('timeout'
        is ignored in that case).
        """
        if not block:
            return self.put_nowait(item)
        
        end_time = None
        if timeout is not None:
            if timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            end_time = time.time() + timeout

        with self._mutex:
            while True:
                # Check if we can put the item
                if self._maxsize <= 0 or len(self._deque) < self._maxsize:
                    self._put(item)
                    self._unfinished_tasks += 1
                    self._finished.clear()
                    self._not_empty.set()
                    return
                
                # Queue is full, need to wait
                if timeout is not None:
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        raise Full
                    wait_time = remaining
                else:
                    wait_time = None
                
                # Wait for space to become available
                self._not_full.clear()
                self._mutex.release()
                try:
                    if not self._not_full.wait(wait_time):
                        raise Full
                finally:
                    assert self._mutex.acquire()

    def get(self, block=True, timeout=None):
        """Remove and return an item from the queue.

        If optional args 'block' is true and 'timeout' is None (the default),
        block if necessary until an item is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the Empty exception if no item was available within that time.
        Otherwise ('block' is false), return an item if one is immediately
        available, raise the Empty exception ('timeout' is ignored in that case).
        """
        if not block:
            return self.get_nowait()
        
        end_time = None
        if timeout is not None:
            if timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            end_time = time.time() + timeout

        with self._mutex:
            while True:
                # Check if we can get an item
                if self._deque:
                    item = self._get()
                    self._not_full.set()
                    return item
                
                # Queue is empty, need to wait
                if timeout is not None:
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        raise Empty
                    wait_time = remaining
                else:
                    wait_time = None
                
                # Wait for an item to become available
                self._not_empty.clear()
                self._mutex.release()
                try:
                    if not self._not_empty.wait(wait_time):
                        raise Empty
                finally:
                    assert self._mutex.acquire()

    def put_nowait(self, item):
        """Put an item into the queue without blocking.

        Only enqueue the item if a free slot is immediately available.
        Otherwise raise the Full exception.
        """
        with self._mutex:
            if self._maxsize > 0 and len(self._deque) >= self._maxsize:
                raise Full
            
            self._put(item)
            self._unfinished_tasks += 1
            self._finished.clear()
            self._not_empty.set()

    def get_nowait(self):
        """Remove and return an item if one is immediately available,
        else raise the Empty exception.
        """
        with self._mutex:
            if not self._deque:
                raise Empty
            
            item = self._get()
            self._not_full.set()
            return item

    # Subclass override points
    def _init(self, maxsize):
        """Initialize the queue representation."""
        self._deque = deque()

    def _put(self, item):
        """Put a new item in the queue."""
        self._deque.append(item)

    def _get(self):
        """Get an item from the queue."""
        return self._deque.popleft()


class PriorityQueue(Queue):
    """Variant of Queue that retrieves open entries in priority order (lowest first).

    Entries are typically tuples of the form: (priority number, data).
    """

    def _init(self, maxsize):
        self._deque = []

    def _put(self, item):
        heapq.heappush(self._deque, item)

    def _get(self):
        return heapq.heappop(self._deque)


class LifoQueue(Queue):
    """Variant of Queue that retrieves most recently added entries first (LIFO)."""

    def _get(self):
        return self._deque.pop()


class SimpleQueue:
    """Simple, unbounded FIFO queue.

    This pure Python implementation is not reentrant.
    """

    def __init__(self):
        self._deque = deque()
        self._count = threading.Semaphore(0)

    def put(self, item, block=True, timeout=None):
        """Put the item on the queue.

        The optional 'block' and 'timeout' arguments are ignored, as this method
        never blocks. They are provided for compatibility with the Queue class.
        """
        self._deque.append(item)
        self._count.release()

    def get(self, block=True, timeout=None):
        """Remove and return an item from the queue.

        If optional args 'block' is true and 'timeout' is None (the default),
        block if necessary until an item is available. If 'timeout' is
        a non-negative number, it blocks at most 'timeout' seconds and raises
        the Empty exception if no item was available within that time.
        Otherwise ('block' is false), return an item if one is immediately
        available, raise the Empty exception ('timeout' is ignored in that case).
        """
        if not block:
            return self.get_nowait()
        
        if timeout is None:
            self._count.acquire()
        else:
            if timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            if not self._count.acquire(timeout=timeout):
                raise Empty
        
        return self._deque.popleft()

    def put_nowait(self, item):
        """Put an item into the queue without blocking.

        This is exactly equivalent to `put(item)`.
        """
        return self.put(item, block=False)

    def get_nowait(self):
        """Remove and return an item if one is immediately available,
        else raise the Empty exception.
        """
        if not self._count.acquire(blocking=False):
            raise Empty
        return self._deque.popleft()

    def empty(self):
        """Return True if the queue is empty, False otherwise."""
        return len(self._deque) == 0

    def qsize(self):
        """Return the approximate size of the queue."""
        return len(self._deque)


# Aliases for compatibility
FIFO = Queue
LIFO = LifoQueue