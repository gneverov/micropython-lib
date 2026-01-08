# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
Functions to unfreeze frozen objects (i.e., modules and classes) so that they can be mutated in tests.

Follows a similar interface to unittest.mock.patch.
"""
import contextlib
import freeze
import sys

from  . import mock


def _unfreeze(value):
    mod_type = type(freeze)
    if not freeze.isfrozen(value):
        uvalue = value
    elif isinstance(value, mod_type):
        uvalue = mod_type(value.__name__)
        uvalue.__dict__.update(value.__dict__)
    if isinstance(value, type):
        uvalue = type(value.__name__, value.__bases__, dict(value.__dict__))
    else:
        TypeError(f"cannot unfreeze '{type(value)}'")
    return uvalue

# @contextlib.contextmanager
# def unfreeze_object(target, attribute):
#     value = getattr(target, attribute)
#     uvalue =_unfreeze(value)
#     setattr(target, attribute, uvalue)
#     mock.patch_object()
#     yield uvalue
#     setattr(target, attribute, value)

# @contextlib.contextmanager
# def unfreeze(target):
#     parts = target.rsplit('.', 1)
#     if len(parts) == 1:
#         mod = __import__(parts[0])
#         umod = _unfreeze(mod)
#         sys.modules[mod.__name__] = umod
#         yield umod
#         sys.modules[mod.__name__] = mod
#     else:
#         with unfreeze(parts[0]) as inner_value:
#             with unfreeze_object(inner_value, parts[1]) as value:
#                 yield value

# @contextlib.contextmanager
# def unfreeze_dict(in_dict, keys):
#     values = {}
#     for k in keys:
#         v = _unfreeze(in_dict[k])
#         in_dict[k] = v
#         values[k] = v
#     yield in_dict
#     for k in keys:
#         in_dict[k] = values[k]


@contextlib.contextmanager
def patch(target, *args, **kwargs):
    parts = target.split('.')
    if not parts:
        raise ValueError()

    def setmod(value):
        sys.modules[value.__name__] = value
    restore = None

    obj = __import__(parts[0])
    u = _unfreeze(obj)
    if u is not obj:
        sys.modules[obj.__name__] = u
        restore = setmod, [obj]
    obj = u

    for i in range(1, len(parts) - 1):
        subobj = getattr(obj, parts[i])
        u = _unfreeze(subobj)
        if u is not obj:
            setattr(obj, parts[i], u)
            if restore is None:
                restore = setattr, [obj, parts[i], subobj]
        elif restore is not None:
            restore[0](*restore[1])
            restore = None
        obj = u

    with mock.patch_object(obj, parts[-1], *args, **kwargs) as patch:
        yield patch

    restore[0](*restore[1])    
