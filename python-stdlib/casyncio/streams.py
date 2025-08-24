# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0
# 

import collections
import socket
import sys
# import warnings
# import weakref

from . import coroutines
from . import events
from . import exceptions
from . import format_helpers
# from . import protocols
from .log import logger
from .mp_streams import (StreamReader, StreamWriter)
from .tasks import sleep


_DEFAULT_LIMIT = 2 ** 9  # 64 KiB


async def open_connection(host=None, port=None, *,
                          limit=_DEFAULT_LIMIT, **kwds):
    """A wrapper for create_connection() returning a (reader, writer) pair.

    The reader returned is a StreamReader instance; the writer is a
    StreamWriter instance.

    The arguments are all the usual arguments to create_connection()
    except protocol_factory; most common are positional host and port,
    with various optional keyword arguments following.

    Additional optional keyword arguments are loop (to set the event loop
    instance to use) and limit (to set the buffer limit passed to the
    StreamReader).

    (If you want to customize the StreamReader and/or
    StreamReaderProtocol classes, just copy the code -- there's
    really nothing special here except some convenience.)
    """
    loop = events.get_running_loop()
    stream = await loop.create_connection(host, port, **kwds)
    reader = StreamReader(stream, loop)
    writer = StreamWriter(stream, loop)
    return reader, writer


async def start_server(client_connected_cb, host=None, port=None, *,
                       limit=_DEFAULT_LIMIT, **kwds):
    """Start a socket server, call back for each client connected.

    The first parameter, `client_connected_cb`, takes two parameters:
    client_reader, client_writer.  client_reader is a StreamReader
    object, while client_writer is a StreamWriter object.  This
    parameter can either be a plain callback function or a coroutine;
    if it is a coroutine, it will be automatically converted into a
    Task.

    The rest of the arguments are all the usual arguments to
    loop.create_server() except protocol_factory; most common are
    positional host and port, with various optional keyword arguments
    following.  The return value is the same as loop.create_server().

    Additional optional keyword argument is limit (to set the buffer
    limit passed to the StreamReader).

    The return value is the same as loop.create_server(), i.e. a
    Server object which can be used to stop the service.
    """
    loop = events.get_running_loop()

    async def factory(transport):
        if client_connected_cb is not None:
            reader = StreamReader(transport, limit=limit, loop=loop)
            writer = StreamWriter(transport, loop=loop)
            res = client_connected_cb(reader, writer)
            if coroutines.iscoroutine(res):
                try:
                    await res
                except exceptions.CancelledError:
                    pass
                except BaseException as exc:
                    loop.call_exception_handler({
                        'message': 'Unhandled exception in client_connected_cb',
                        'exception': exc,
                        'transport': transport,
                    })
                finally:
                    transport.close()

    return await loop.create_server(factory, host, port, **kwds)
