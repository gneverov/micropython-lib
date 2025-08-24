# SPDX-FileCopyrightText: Gregory Neverov
# SPDX-License-Identifier: Python-2.0

from . import events
from . import deque
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


class StreamReader:
    def __init__(self, stream, limit=None, loop=None):
        self._loop = events.get_event_loop() if loop is None else loop
        self._stream = stream
        self._queue = deque.deque()
        self._eof = False

    def _callback(self):
        while self._queue:
            fut, func, args = self._queue.popleft()
            try:
                ret = func(*args)
            except Exception as e:
                fut.set_exception(e)
                continue
            if ret is None:
                self._queue.appendleft((fut, func, args))
                return
            else:
                if len(ret) == 0:
                    self._eof = True
                fut.set_result(ret)

        self._loop.remove_reader(self._stream)

    def feed_eof(self):
        pass

    def _sync(self, ret, n):
        if ret is None or 0 < len(ret) < n:
            self._loop.add_reader(self._stream, StreamReader._callback, self)
            return False
        if len(ret) == 0:
            self._eof = True
        return True

    async def read(self, n=-1):
        if not self._queue:
            data = self._stream.read(n)
            if self._sync(data, 1):
                return data
        
        fut = self._loop.create_future()
        self._queue.append((fut, type(self._stream).read, (self._stream, n)))
        return await fut
        

    async def readline(self):
        if not self._queue:
            data = self._stream.readline()
            if self._sync(data, 1):
                return data
        
        fut = self._loop.create_future()
        self._queue.append((fut, type(self._stream).readline, (self._stream,)))
        return await fut

    @staticmethod
    def _readexactly(stream, chunks):
        remaining = chunks[0]
        chunk = stream.read(remaining)
        if chunk is None:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
        chunks[0] = remaining
        if remaining > 0:
            return None
        else:
            return b''.join(chunks[1:])


    async def readexactly(self, n):
        data = None
        if not self._queue:
            data = self._stream.read(n)
            if self._sync(data, n):
                return data
        if data is None:
            chunks = [n]
        else:
            chunks = [n - len(data), data]
        fut = self._loop.create_future()
        self._queue.append((fut, type(self)._readexactly, (self._stream, chunks)))
        return await fut

    def at_eof(self):
        return self._eof


class StreamWriter:
    def __init__(self, stream, loop=None):
        self._loop = events.get_event_loop() if loop is None else loop
        self._stream = stream
        self._queue = deque.deque()
        self._closing = False
        self._closed = None

    def _close(self):
        try:
            self._stream.close()
        except Exception as e:
            if self._closed:
                self._closed.set_exception(e)
        else:
            if self._closed:
                self._closed.set_result(None)

    def _callback(self):
        last_exc = None
        while self._queue:          
            data = self._queue.popleft()
            if asyncio.isfuture(data):
                if last_exc is None:
                    data.set_result(None)
                else:
                    data.set_exception(last_exc)
                continue

            try:
                n = self._stream.write(data)
            except Exception as e:
                last_exc = e
                continue
            if n is None:
                self._queue.appendleft(data)
                return
            elif n < len(data):
                self._queue.appendleft(data[n:])
                return

        self._loop.remove_writer(self._stream)
        if self._closing:
            self._close()

    def write(self, data):
        if self._queue:
            self._queue.append(data)
            return
        
        n = self._stream.write(data)
        if n is None:
            self._queue.append(data)
        elif n < len(data):
            self._queue.append(data[n:])
        else:
            return
        
        self._loop.add_writer(self._stream, StreamWriter._callback, self)

    def writelines(self, data):
        for line in data:
            self.write(line)
        
    def close(self):
        if self._closing:
            return
        self._closing = True
        if not self._queue:
            self._close()

    def can_write_eof(self):
        return False

    # def write_eof():
    #     pass

    def get_extra_info(self, name, default=None):
        return default

    async def drain(self):
        if not self._queue:
            return
        drained = futures.Future(loop=self._loop)
        self._queue.append(drained)
        await drained

    def is_closing(self):
        return self._closing
    
    async def wait_closed(self):
        if not self._closed:
            if self._closing and not self._queue:
                return
            self._closed = self._loop.create_future()
        await self._closed
