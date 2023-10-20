# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

"""The asyncio package, tracking PEP 3156."""

# This relies on each of the submodules having an __all__ variable.
from .base_events import BaseEventLoop
from .coroutines import iscoroutine
from .events import (
    Handle,
    TimerHandle,
    get_event_loop,
    set_event_loop,
    new_event_loop,
    get_running_loop,
)
from .exceptions import (
    BrokenBarrierError,
    CancelledError,
    InvalidStateError,
    TimeoutError,
    IncompleteReadError,
    LimitOverrunError,
)
from .futures import (
    Future,
    isfuture,
)
from .locks import Lock, Event, Condition, Semaphore, BoundedSemaphore, Barrier

# from .protocols import *
from .runners import Runner, run
from .queues import Queue, PriorityQueue, LifoQueue, QueueFull, QueueEmpty
from .mp_streams import stream_wait, stream_read, stream_readinto, stream_write, Stream

# from .subprocess import *
from .tasks import (
    Task,
    create_task,
    FIRST_COMPLETED,
    FIRST_EXCEPTION,
    ALL_COMPLETED,
    wait,
    wait_for,
    as_completed,
    sleep,
    gather,
    shield,
    ensure_future,
    run_coroutine_threadsafe,
    current_task,
    all_tasks,
    _register_task,
    _unregister_task,
    _enter_task,
    _leave_task,
)
from .taskgroups import TaskGroup
from .timeouts import (
    Timeout,
    timeout,
    timeout_at,
)

# from .threads import *
# from .transports import *

from .mp_events import *

repl_runner = Runner(loop_factory=get_event_loop)
