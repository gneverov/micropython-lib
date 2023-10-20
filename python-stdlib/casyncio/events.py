# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

"""Event loop and event loop policy."""
from . import format_helpers


class Handle:
    """Object returned by callback registration methods."""

    def __init__(self, callback, args, loop, context=None):
        # if context is None:
        # context = contextvars.copy_context()
        # self._context = context
        self._loop = loop
        self._callback = callback
        self._args = args
        self._cancelled = False
        self._repr = None
        if self._loop.get_debug():
            self._source_traceback = format_helpers.extract_stack()
        else:
            self._source_traceback = None

    def _repr_info(self):
        info = [self.__class__.__name__]
        if self._cancelled:
            info.append("cancelled")
        if self._callback is not None:
            info.append(format_helpers._format_callback_source(self._callback, self._args))
        if self._source_traceback:
            frame = self._source_traceback[-1]
            info.append(f"created at {frame[0]}:{frame[1]}")
        return info

    def __repr__(self):
        if self._repr is not None:
            return self._repr
        info = self._repr_info()
        return "<{}>".format(" ".join(info))

    def cancel(self):
        if not self._cancelled:
            self._cancelled = True
            if self._loop.get_debug():
                # Keep a representation in debug mode to keep callback and
                # parameters. For example, to log the warning
                # "Executing <Handle...> took 2.5 second"
                self._repr = repr(self)
            self._callback = None
            self._args = None

    def cancelled(self):
        return self._cancelled

    def _run(self):
        try:
            # self._context.run(self._callback, *self._args)
            self._callback(*self._args)
        except (SystemExit, KeyboardInterrupt):
            raise
        except BaseException as exc:
            cb = format_helpers._format_callback_source(self._callback, self._args)
            msg = f"Exception in callback {cb}"
            context = {
                "message": msg,
                "exception": exc,
                "handle": self,
            }
            if self._source_traceback:
                context["source_traceback"] = self._source_traceback
            self._loop.call_exception_handler(context)
        self = None  # Needed to break cycles when an exception occurs.


class TimerHandle(Handle):
    """Object returned by timed callback registration methods."""

    def __init__(self, when, callback, args, loop, context=None):
        super().__init__(callback, args, loop, context)
        if self._source_traceback:
            del self._source_traceback[-1]
        self._when = when
        self._scheduled = False

    def _repr_info(self):
        info = super()._repr_info()
        pos = 2 if self._cancelled else 1
        info.insert(pos, f"when={self._when}")
        return info

    def __hash__(self):
        return hash(self._when)

    def __lt__(self, other):
        if isinstance(other, TimerHandle):
            return self._when < other._when
        return NotImplemented

    def __le__(self, other):
        if isinstance(other, TimerHandle):
            return self._when < other._when or self.__eq__(other)
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, TimerHandle):
            return self._when > other._when
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, TimerHandle):
            return self._when > other._when or self.__eq__(other)
        return NotImplemented

    def __eq__(self, other):
        if isinstance(other, TimerHandle):
            return (
                self._when == other._when
                and self._callback == other._callback
                and self._args == other._args
                and self._cancelled == other._cancelled
            )
        return NotImplemented

    def cancel(self):
        if not self._cancelled:
            self._loop._timer_handle_cancelled(self)
        super().cancel()

    def when(self):
        """Return a scheduled callback time.

        The time is an absolute timestamp, using the same time
        reference as loop.time().
        """
        return self._when


class AbstractEventLoop:
    """Abstract event loop."""


# A TLS for the running event loop, used by _get_running_loop.
class _RunningLoop:
    loop_pid = None


_running_loop = _RunningLoop()


def get_running_loop():
    """Return the running event loop.  Raise a RuntimeError if there is none.

    This function is thread-specific.
    """
    # NOTE: this function is implemented in C (see _asynciomodule.c)
    loop = _get_running_loop()
    if loop is None:
        raise RuntimeError("no running event loop")
    return loop


def _get_running_loop():
    """Return the running event loop or None.

    This is a low-level function intended to be used by event loops.
    This function is thread-specific.
    """
    # NOTE: this function is implemented in C (see _asynciomodule.c)
    running_loop = _running_loop.loop_pid
    if running_loop is not None:
        return running_loop


def _set_running_loop(loop):
    """Set the running event loop.

    This is a low-level function intended to be used by event loops.
    This function is thread-specific.
    """
    # NOTE: this function is implemented in C (see _asynciomodule.c)
    _running_loop.loop_pid = loop


class _Local:
    _loop = None
    _set_called = False


_local = _Local()


def get_event_loop():
    """Return an asyncio event loop.

    When called from a coroutine or a callback (e.g. scheduled with call_soon
    or similar API), this function will always return the running event loop.

    If there is no running event loop set, the function will return
    the result of `get_event_loop_policy().get_event_loop()` call.
    """
    current_loop = _get_running_loop()
    if current_loop is not None:
        return current_loop

    if (_local._loop is None and
            not _local._set_called):
        set_event_loop(new_event_loop())

    if _local._loop is None:
        raise RuntimeError('There is no current event loop in thread %r.')

    return _local._loop


def set_event_loop(loop):
    """Equivalent to calling get_event_loop_policy().set_event_loop(loop)."""
    _local._set_called = True
    if loop is not None and not isinstance(loop, AbstractEventLoop):
        raise TypeError(f"loop must be an instance of AbstractEventLoop or None, not '{type(loop).__name__}'")
    _local._loop = loop


def new_event_loop():
    """Equivalent to calling get_event_loop_policy().new_event_loop()."""
    from . import MicroPythonEventLoop

    return MicroPythonEventLoop()
