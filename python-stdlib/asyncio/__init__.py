# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

"""The asyncio package, tracking PEP 3156."""

import importlib
import sys

# This relies on each of the submodules having an __all__ variable.
def import_all(name):
    module = __import__(name, None, None, [''], 1)
    globals().update({k: getattr(module, k) for k in module.__all__})

import_all("base_events")
import_all("coroutines")
import_all("events")
import_all("futures")
import_all("locks")
import_all("protocols")
import_all("runners")
import_all("queues")
import_all("streams")
import_all("tasks")
import_all("transports")
import_all("unix_events")

# repl_runner = Runner(loop_factory=get_event_loop)
