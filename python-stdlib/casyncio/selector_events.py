# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

"""Event loop using a selector and related classes.

A selector is a "notify-when-ready" multiplexer.  For a subclass which
also includes support for signal handling, see the unix_events sub-module.
"""

# import collections
# import errno
# import functools
# import selectors
# import socket
# import warnings
# import weakref
# try:
#     import ssl
# except ImportError:  # pragma: no cover
#     ssl = None
import select as selectors

from . import base_events

# from . import constants
from . import events
from . import futures

# from . import protocols
# from . import sslproto
# from . import transports
# from . import trsock
from .log import logger


def _test_selector_event(selector, fd, event):
    # Test if the selector is monitoring 'event' events
    # for the file descriptor 'fd'.
    try:
        key = selector.get_key(fd)
    except KeyError:
        return False
    else:
        return bool(key.events & event)


class BaseSelectorEventLoop(base_events.BaseEventLoop):
    """Selector event loop.

    See events.EventLoop for API specification.
    """

    def __init__(self, selector=None):
        super().__init__()

        if selector is None:
            selector = selectors.Selector()
        logger.debug("Using selector: %s", selector.__class__.__name__)
        self._selector = selector
        self._make_self_pipe()

    def close(self):
        if self.is_running():
            raise RuntimeError("Cannot close a running event loop")
        if self.is_closed():
            return
        self._close_self_pipe()
        super().close()
        if self._selector is not None:
            self._selector.close()
            self._selector = None

    def _close_self_pipe(self):
        self._remove_reader(self._ssock)
        self._ssock.close()
        self._ssock = None

    def _make_self_pipe(self):
        # A self-socket, really. :-)
        self._ssock = selectors.Event()
        # self._ssock.setblocking(False)
        self._add_reader(self._ssock, self._read_from_self)

    def _process_self_data(self, data):
        pass

    def _read_from_self(self):
        while True:
            try:
                data = self._ssock.read(8)
                if not data:
                    break
                self._process_self_data(data)
            except InterruptedError:
                continue
            except BlockingIOError:
                break

    def _write_to_self(self):
        # This may be called from a different thread, possibly after
        # _close_self_pipe() has been called or even while it is
        # running.  Guard for self._csock being None or closed.  When
        # a socket is closed, send() raises OSError (with errno set to
        # EBADF, but let's not rely on the exact error code).
        csock = self._ssock
        if csock is None:
            return

        try:
            csock.write(b"\x01\0\0\0\0\0\0\0")
        except OSError:
            if self._debug:
                logger.debug("Fail to write a null byte into the self-pipe socket", exc_info=True)

    def _ensure_fd_no_transport(self, fd):
        pass

    def _add_reader(self, fd, callback, *args):
        self._check_closed()
        handle = events.Handle(callback, args, self, None)
        try:
            key = self._selector.get_key(fd)
        except KeyError:
            self._selector.register(fd, selectors.EVENT_READ, (handle, None))
        else:
            mask, (reader, writer) = key.events, key.data
            self._selector.modify(fd, mask | selectors.EVENT_READ, (handle, writer))
            if reader is not None:
                reader.cancel()
        return handle

    def _remove_reader(self, fd):
        if self.is_closed():
            return False
        try:
            key = self._selector.get_key(fd)
        except KeyError:
            return False
        else:
            mask, (reader, writer) = key.events, key.data
            mask &= ~selectors.EVENT_READ
            if not mask:
                self._selector.unregister(fd)
            else:
                self._selector.modify(fd, mask, (None, writer))

            if reader is not None:
                reader.cancel()
                return True
            else:
                return False

    def _add_writer(self, fd, callback, *args):
        self._check_closed()
        handle = events.Handle(callback, args, self, None)
        try:
            key = self._selector.get_key(fd)
        except KeyError:
            self._selector.register(fd, selectors.EVENT_WRITE, (None, handle))
        else:
            mask, (reader, writer) = key.events, key.data
            self._selector.modify(fd, mask | selectors.EVENT_WRITE, (reader, handle))
            if writer is not None:
                writer.cancel()
        return handle

    def _remove_writer(self, fd):
        """Remove a writer callback."""
        if self.is_closed():
            return False
        try:
            key = self._selector.get_key(fd)
        except KeyError:
            return False
        else:
            mask, (reader, writer) = key.events, key.data
            # Remove both writer and connector.
            mask &= ~selectors.EVENT_WRITE
            if not mask:
                self._selector.unregister(fd)
            else:
                self._selector.modify(fd, mask, (reader, None))

            if writer is not None:
                writer.cancel()
                return True
            else:
                return False

    def add_reader(self, fd, callback, *args):
        """Add a reader callback."""
        self._ensure_fd_no_transport(fd)
        self._add_reader(fd, callback, *args)

    def remove_reader(self, fd):
        """Remove a reader callback."""
        self._ensure_fd_no_transport(fd)
        return self._remove_reader(fd)

    def add_writer(self, fd, callback, *args):
        """Add a writer callback.."""
        self._ensure_fd_no_transport(fd)
        self._add_writer(fd, callback, *args)

    def remove_writer(self, fd):
        """Remove a writer callback."""
        self._ensure_fd_no_transport(fd)
        return self._remove_writer(fd)

    def _process_events(self, event_list):
        for key, mask in event_list:
            fileobj, (reader, writer) = key.fileobj, key.data
            if mask & ~selectors.EVENT_WRITE and reader is not None:
                if reader._cancelled:
                    self._remove_reader(fileobj)
                else:
                    self._add_callback(reader)
            if mask & ~selectors.EVENT_READ and writer is not None:
                if writer._cancelled:
                    self._remove_writer(fileobj)
                else:
                    self._add_callback(writer)
