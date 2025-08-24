# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

"""Event loop using a selector and related classes.

A selector is a "notify-when-ready" multiplexer.  For a subclass which
also includes support for signal handling, see the unix_events sub-module.
"""

# import collections
# import errno
# import functools
import os
# import selectors
import socket
# import warnings
# import weakref
# try:
#     import ssl
# except ImportError:  # pragma: no cover
#     ssl = None
import selectors

from . import base_events

from . import constants
from . import events
from . import futures
from  .mp_streams import (StreamFuture)

# from . import protocols
from . import sslproto
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
            selector = selectors.DefaultSelector()
        logger.debug("Using selector: %s", selector.__class__.__name__)
        self._selector = selector
        self._make_self_pipe()

    def _make_socket_transport(self, sock, *,
                               extra=None, server=None):
        self._ensure_fd_no_transport(sock)
        if server is not None:
            server._attach(self)        
        transport = sock.makefile('r+b', buffering=0)
        sock.close()
        return transport

    def _make_ssl_transport(
            self, rawsock, sslcontext,
            *, server_side=False, server_hostname=None,
            extra=None, server=None,
            ssl_handshake_timeout=constants.SSL_HANDSHAKE_TIMEOUT,
    ):
        self._ensure_fd_no_transport(rawsock)

        if not sslcontext:
            sslcontext = sslproto._create_transport_context(
                server_side, server_hostname)
               
        sock = sslcontext.wrap_socket(rawsock, server_side=server_side, server_hostname=server_hostname if server_hostname and not server_side else None)
        return self._make_socket_transport(sock)

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
        self._ssock = open(os.eventfd(0, 0x02), "r+b", buffering=0)
        os.set_blocking(self._ssock, False)
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

    def _start_serving(self, protocol_factory, sock,
                       sslcontext=None, server=None, backlog=100,
                       ssl_handshake_timeout=constants.SSL_HANDSHAKE_TIMEOUT):
        self._add_reader(sock.fileno(), self._accept_connection,
                         protocol_factory, sock, sslcontext, server, backlog,
                         ssl_handshake_timeout)

    def _accept_connection(
            self, protocol_factory, sock,
            sslcontext=None, server=None, backlog=100,
            ssl_handshake_timeout=constants.SSL_HANDSHAKE_TIMEOUT):
        # This method is only called once for each event loop tick where the
        # listening socket has triggered an EVENT_READ. There may be multiple
        # connections waiting for an .accept() so it is called in a loop.
        # See https://bugs.python.org/issue27906 for more details.
        for _ in range(backlog):
            try:
                conn, addr = sock.accept()
                if self._debug:
                    logger.debug("%r got a new connection from %r: %r",
                                 server, addr, conn)
                conn.setblocking(False)
            except (BlockingIOError, InterruptedError, ConnectionAbortedError):
                # Early exit because the socket accept buffer is empty.
                return None
            except OSError as exc:
                # There's nowhere to send the error, so just log it.
                if exc.errno in (errno.EMFILE, errno.ENFILE,
                                 errno.ENOBUFS, errno.ENOMEM):
                    # Some platforms (e.g. Linux keep reporting the FD as
                    # ready, so we remove the read handler temporarily.
                    # We'll try again in a while.
                    self.call_exception_handler({
                        'message': 'socket.accept() out of system resource',
                        'exception': exc,
                        'socket': trsock.TransportSocket(sock),
                    })
                    self._remove_reader(sock.fileno())
                    self.call_later(constants.ACCEPT_RETRY_DELAY,
                                    self._start_serving,
                                    protocol_factory, sock, sslcontext, server,
                                    backlog, ssl_handshake_timeout)
                else:
                    raise  # The event loop will catch, log and ignore it.
            else:
                extra = {'peername': addr}
                accept = self._accept_connection2(
                    protocol_factory, conn, extra, sslcontext, server,
                    ssl_handshake_timeout)
                self.create_task(accept)

    async def _accept_connection2(
            self, protocol_factory, conn, extra,
            sslcontext=None, server=None,
            ssl_handshake_timeout=constants.SSL_HANDSHAKE_TIMEOUT):
        try:
            if sslcontext:
                transport = self._make_ssl_transport(
                    conn, sslcontext,
                    server_side=True, extra=extra, server=server,
                    ssl_handshake_timeout=ssl_handshake_timeout)
            else:
                transport = self._make_socket_transport(
                    conn, extra=extra,
                    server=server)

        except (SystemExit, KeyboardInterrupt):
            raise
        except BaseException as exc:
            if self._debug:
                context = {
                    'message':
                        'Error on transport creation for incoming connection',
                    'exception': exc,
                }
                self.call_exception_handler(context)
        
        try:
            return await protocol_factory(transport)
        finally:
            if server is not None:
                server._detach(transport)

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

    async def sock_connect(self, sock, address):
        """Connect to a remote socket at address.

        This method is a coroutine.
        """
        base_events._check_ssl_socket(sock)
        if self._debug and sock.gettimeout() != 0:
            raise ValueError("the socket must be non-blocking")

        if sock.family == socket.AF_INET or (
                base_events._HAS_IPv6 and sock.family == socket.AF_INET6):
            resolved = await self._ensure_resolved(
                address, family=sock.family, type=sock.type, proto=sock.proto,
                loop=self,
            )
            _, _, _, _, address = resolved[0]

        def connect_ex(sock, address):
            import errno
            err = sock.connect_ex(address)
            if err == errno.EINPROGRESS:
                return None
            elif err == 0 or err == errno.EISCONN:
                return 0
            else:
                raise OSError(err)
        return await StreamFuture(sock, None, connect_ex, sock, address)

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
                    
    def _stop_serving(self, sock):
        self._remove_reader(sock.fileno())
        sock.close()