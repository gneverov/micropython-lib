# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

"""Logging configuration."""

import logging
import sys


class Logger:
    def __init__(self, package):
        pass

    def info(self, msg, *args, **kwargs):
        pass

    def debug(self, msg, *args, **kwargs):
        print(msg % args)

    def warning(self, msg, *args, **kwargs):
        print(msg % args)

    def error(self, msg, *args, exc_info=None, **kwargs):
        print(msg % args)
        if exc_info:
            sys.print_exception(exc_info)


def __thaw__(self):
    # Name the logger after the package.
    self.logger = logging.getLogger("asyncio")
