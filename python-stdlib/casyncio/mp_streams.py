# SPDX-FileCopyrightText: Gregory Neverov
# SPDX-License-Identifier: Python-2.0

from . import events
from . import futures


class StreamFuture(futures.Future):
    def __init__(self, reader, writer, func, *args, loop=None):
        super().__init__(loop=loop)
        self._reader = reader
        self._writer = writer
        self._func = func
        self._args = args

        self._run()
        if self.done():
            return        

        loop = self.get_loop()
        if reader is not None:
            loop.add_reader(reader, StreamFuture._callback, self)
        if writer is not None:
            loop.add_writer(writer, StreamFuture._callback, self)

    def _callback(self):
        if self.done():
            return
        
        self._run()

        if self.done():
            self._cleanup()

    def _run(self):
        try:
            ret = self._func(*self._args)
        except Exception as e:
            self.set_exception(e)
        else:
            if ret is not None:
                self.set_result(ret)

    def _cleanup(self):
        loop = self.get_loop()
        if self._reader is not None:
            loop.remove_reader(self._reader)
        if self._writer is not None:
            loop.remove_writer(self._writer)

class StreamWriteFuture(futures.Future):
    def __init__(self, writer, buf, size=None, loop=None):
        super().__init__(loop=loop)
        self._writer = writer
        self._buf = memoryview(buf)[:size]

        self._run()
        if self.done():
            return        

        loop = self.get_loop()
        loop.add_writer(writer, StreamWriteFuture._callback, self)

    def _callback(self):
        if self.done():
            return
        
        self._run()

        if self.done():
            self._cleanup()

    def _run(self):
        try:
            ret = self._writer.write(self._buf)
        except Exception as e:
            self.set_exception(e)
        else:
            if ret == len(self._buf):
                self.set_result(ret)
            elif ret is not None:
                self._buf = self._buf[ret:]

    def _cleanup(self):
        loop = self.get_loop()
        loop.remove_writer(self._writer)


stream_wait = StreamFuture

def stream_read(stream, size):
    return StreamFuture(stream, None, type(stream).read, stream, size)

def stream_readinto(stream, b):
    return StreamFuture(stream, None, type(stream).readinto, stream, b)

stream_write = StreamWriteFuture

class Stream:
    def __init__(self, stream, loop=None):
        self._loop = events.get_event_loop() if loop is None else loop
        self._stream = stream
        stream.settimeout(0)

    def close(self):
        return self._stream.close()
    
    def read(self, size):
        return StreamFuture(self._stream, None, type(self._stream).read, self._stream, size, loop=self._loop)

    def readinto(self, b):
        return StreamFuture(self._stream, None, type(self._stream).readinto, self._stream, b, loop=self._loop)
    
    def write(self, b, size=None):
        return StreamWriteFuture(self._stream, b, size, loop=self._loop)
