# SPDX-FileCopyrightText: 2023 Python Software Foundation
# SPDX-License-Identifier: Python-2.0

import sys


"""Logging configuration."""


class Logger:
    def __init__(self, package):
        pass

    def debug(self, msg, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        pass

    def error(self, msg, *args, exc_info=None, **kwargs):
        print(msg % args)
        if exc_info:
            sys.print_exception(exc_info)


# Name the logger after the package.
logger = Logger(None)
