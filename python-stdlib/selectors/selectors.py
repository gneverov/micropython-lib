# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

"""Selectors module.

This module allows high-level and efficient I/O multiplexing, built upon the
`select` module primitives.
"""


from collections import namedtuple
from collections.abc import Mapping
import math
import select


# generic events, that must be mapped to implementation-specific ones
EVENT_READ = select.POLLIN
EVENT_WRITE = select.POLLOUT


def _fileobj_to_fd(fileobj):
    """Return a file descriptor from a file object.

    Parameters:
    fileobj -- file object or file descriptor

    Returns:
    corresponding file descriptor

    Raises:
    ValueError if the object is invalid
    """
    if isinstance(fileobj, int):
        fd = fileobj
    else:
        try:
            fd = int(fileobj.fileno())
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Invalid file object: "
                             "{!r}".format(fileobj)) from None
    if fd < 0:
        raise ValueError("Invalid file descriptor: {}".format(fd))
    return fd


SelectorKey = namedtuple('SelectorKey', ['fileobj', 'fd', 'events', 'data'])

# SelectorKey.__doc__ = """SelectorKey(fileobj, fd, events, data)

#     Object used to associate a file object to its backing
#     file descriptor, selected event mask, and attached data.
# """
# SelectorKey.fileobj.__doc__ = 'File object registered.'
# SelectorKey.fd.__doc__ = 'Underlying file descriptor.'
# SelectorKey.events.__doc__ = 'Events that must be waited for on this file object.'
# SelectorKey.data.__doc__ = ('''Optional opaque data associated to this file object.
# For example, this could be used to store a per-client session ID.''')


class _SelectorMapping(Mapping):
    """Mapping of file objects to selector keys."""

    def __init__(self, selector):
        self._selector = selector

    def __len__(self):
        return len(self._selector._fd_to_key)

    def get(self, fileobj, default=None):
        fd = self._selector._fileobj_lookup(fileobj)
        return self._selector._fd_to_key.get(fd, default)

    def __getitem__(self, fileobj):
        fd = self._selector._fileobj_lookup(fileobj)
        key = self._selector._fd_to_key.get(fd)
        if key is None:
            raise KeyError("{!r} is not registered".format(fileobj))
        return key

    def __iter__(self):
        return iter(self._selector._fd_to_key)
    

class BaseSelector:
    pass


class PollSelector(BaseSelector):
    """Poll-based selector.
    
    A selector supports registering file objects to be monitored for specific
    I/O events.

    A file object is a file descriptor or any object with a `fileno()` method.
    An arbitrary object can be attached to the file object, which can be used
    for example to store context information, a callback, etc.
    """
    def __init__(self):
        # this maps file descriptors to keys
        self._fd_to_key = {}
        # read-only mapping returned by get_map()
        self._map = _SelectorMapping(self)
        self._selector = select.poll()

    def _fileobj_lookup(self, fileobj):
        """Return a file descriptor from a file object.

        This wraps _fileobj_to_fd() to do an exhaustive search in case
        the object is invalid but we still have it in our map.  This
        is used by unregister() so we can unregister an object that
        was previously registered even if it is closed.  It is also
        used by _SelectorMapping.
        """
        try:
            return _fileobj_to_fd(fileobj)
        except ValueError:
            # Do an exhaustive search.
            for key in self._fd_to_key.values():
                if key.fileobj is fileobj:
                    return key.fd
            # Raise ValueError after all.
            raise

    def register(self, fileobj, events, data=None):
        """Register a file object.

        Parameters:
        fileobj -- file object or file descriptor
        events  -- events to monitor (bitwise mask of EVENT_READ|EVENT_WRITE)
        data    -- attached data

        Returns:
        SelectorKey instance

        Raises:
        ValueError if events is invalid
        KeyError if fileobj is already registered
        OSError if fileobj is closed or otherwise is unacceptable to
                the underlying system call (if a system call is made)

        Note:
        OSError may or may not be raised
        """
        if (not events) or (events & ~(EVENT_READ | EVENT_WRITE)):
            raise ValueError("Invalid events: {!r}".format(events))

        key = SelectorKey(fileobj, self._fileobj_lookup(fileobj), events, data)

        if key.fd in self._fd_to_key:
            raise KeyError("{!r} (FD {}) is already registered"
                           .format(fileobj, key.fd))

        self._fd_to_key[key.fd] = key
            
        try:
            self._selector.register(key.fd, events)
        except:
            del self._fd_to_key[key.fd]
            raise
        return key

    def unregister(self, fileobj):
        """Unregister a file object.

        Parameters:
        fileobj -- file object or file descriptor

        Returns:
        SelectorKey instance

        Raises:
        KeyError if fileobj is not registered

        Note:
        If fileobj is registered but has since been closed this does
        *not* raise OSError (even if the wrapped syscall does)
        """
        try:
            key = self._fd_to_key.pop(self._fileobj_lookup(fileobj))
        except KeyError:
            raise KeyError("{!r} is not registered".format(fileobj)) from None
    
        try:
            self._selector.unregister(key.fd)
        except OSError:
            # This can happen if the FD was closed since it
            # was registered.
            pass
        return key

    def modify(self, fileobj, events, data=None):
        """Change a registered file object monitored events or attached data.

        Parameters:
        fileobj -- file object or file descriptor
        events  -- events to monitor (bitwise mask of EVENT_READ|EVENT_WRITE)
        data    -- attached data

        Returns:
        SelectorKey instance

        Raises:
        Anything that unregister() or register() raises
        """
        try:
            key = self._fd_to_key[self._fileobj_lookup(fileobj)]
        except KeyError:
            raise KeyError(f"{fileobj!r} is not registered") from None

        changed = False
        if events != key.events:
            try:
                self._selector.modify(key.fd, events)
            except:
                del self._fd_to_key[key.fd]
                raise
            changed = True
        if data != key.data:
            changed = True

        if changed:
            key = SelectorKey(key.fileobj, key.fd, events, data)
            self._fd_to_key[key.fd] = key
        return key

    def select(self, timeout=None):
        """Perform the actual selection, until some monitored file objects are
        ready or a timeout expires.

        Parameters:
        timeout -- if timeout > 0, this specifies the maximum wait time, in
                   seconds
                   if timeout <= 0, the select() call won't block, and will
                   report the currently ready file objects
                   if timeout is None, select() will block until a monitored
                   file object becomes ready

        Returns:
        list of (key, events) for ready file objects
        `events` is a bitwise mask of EVENT_READ|EVENT_WRITE
        """
        # This is shared between poll() and epoll().
        # epoll() has a different signature and handling of timeout parameter.
        if timeout is None:
            timeout = None
        elif timeout <= 0:
            timeout = 0
        else:
            # poll() has a resolution of 1 millisecond, round away from
            # zero to wait *at least* timeout seconds.
            timeout = math.ceil(timeout * 1e3)
        ready = []
        fd_event_list = self._selector.poll(timeout)

        fd_to_key_get = self._fd_to_key.get
        for fd, events in fd_event_list:
            key = fd_to_key_get(fd)
            if key:
                ready.append((key, events & key.events))
        return ready

    def close(self):
        """Close the selector.

        This must be called to make sure that any underlying resource is freed.
        """
        self._fd_to_key.clear()
        self._map = None

    def get_key(self, fileobj):
        """Return the key associated to a registered file object.

        Returns:
        SelectorKey for this file object
        """
        mapping = self.get_map()
        if mapping is None:
            raise RuntimeError('Selector is closed')
        try:
            return mapping[fileobj]
        except KeyError:
            raise KeyError("{!r} is not registered".format(fileobj)) from None

    def get_map(self):
        """Return a mapping of file objects to selector keys."""
        return self._map

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

DefaultSelector = PollSelector
