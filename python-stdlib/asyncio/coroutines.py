# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

__all__ = 'coroutine', 'iscoroutinefunction', 'iscoroutine'

def _is_debug_mode():
    return False


def coroutine(func):
    """Decorator to mark coroutines.

    If the coroutine is not yielded from before it is destroyed,
    an error message is logged.
    """
    return func


def iscoroutinefunction(func):
    """Return True if func is a decorated coroutine function."""
    return False


def iscoroutine(obj):
    """Return True if obj is a coroutine object."""
    return type(obj).__name__ == 'generator'


def _format_coroutine(coro):
    assert iscoroutine(coro)

    def get_name(coro):
        # Coroutines compiled with Cython sometimes don't have
        # proper __qualname__ or __name__.  While that is a bug
        # in Cython, asyncio shouldn't crash with an AttributeError
        # in its __repr__ functions.
        if hasattr(coro, '__qualname__') and coro.__qualname__:
            coro_name = coro.__qualname__
        elif hasattr(coro, '__name__') and coro.__name__:
            coro_name = coro.__name__
        else:
            # Stop masking Cython bugs, expose them in a friendly way.
            coro_name = f'<{type(coro).__name__} without __name__>'
        return f'{coro_name}()'

    def is_running(coro):
        try:
            return coro.cr_running
        except AttributeError:
            try:
                return coro.gi_running
            except AttributeError:
                return False

    coro_name = get_name(coro)

    # Built-in types might not have __qualname__ or __name__.
    if is_running(coro):
        return f'{coro_name} running'
    else:
        return coro_name
