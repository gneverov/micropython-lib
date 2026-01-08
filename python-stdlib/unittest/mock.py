# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
Simple mock implementation for MicroPython
Compatible with Python's unittest.mock module API
"""

import sys
import re
import traceback
from types import FunctionType, MethodType

# Constants
DEFAULT = object()
sentinel = object()

class _CallList(list):
    """List that maintains call information"""
    
    def __contains__(self, value):
        return list.__contains__(self, value)

class _Call:
    """Represents a call to a mock object"""
    
    def __init__(self, name=None, parent=None, args=(), kwargs=None):
        self.name = name
        self.parent = parent
        self.args = args
        self.kwargs = kwargs or {}
    
    def __eq__(self, other):
        if not isinstance(other, _Call):
            return False
        return (self.name == other.name and 
                self.args == other.args and 
                self.kwargs == other.kwargs)
    
    def __repr__(self):
        name = self.name or 'call'
        args_repr = ', '.join(repr(arg) for arg in self.args)
        kwargs_repr = ', '.join(f'{k}={v!r}' for k, v in self.kwargs.items())
        all_args = ', '.join(filter(None, [args_repr, kwargs_repr]))
        return f"{name}({all_args})"

def call(*args, **kwargs):
    """Create a call object"""
    return _Call(args=args, kwargs=kwargs)

class _MockState:
    """Holds the state for a Mock object"""
    
    def __init__(self, mock):
        self.call_count = 0
        self.call_args = None
        self.call_args_list = _CallList()
        self.return_value = DEFAULT
        self.side_effect = None
        self.spec = None
        self.spec_set = None
        self.name = None
        self._children = {}
        self._parent = None
        self._mock_methods = {}
        self._mock_wraps = None
        self._side_effect_iterator = None

class NonCallableMock:
    """Base class for mock objects that cannot be called"""
    
    def __init__(self, spec=None, wraps=None, name=None, spec_set=None, 
                 parent=None, _spec_state=None, _spec_as_instance=False,
                 _eat_self=None, unsafe=False, **kwargs):
        self._mock_state = _MockState(self)
        self._mock_state.spec = spec
        self._mock_state.spec_set = spec_set
        self._mock_state.name = name
        self._mock_state._parent = parent
        self._mock_state._mock_wraps = wraps
        
        # Set up any attributes passed in kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __getattr__(self, name):
        """Create child mock attributes on demand"""
        if name.startswith('_'):
            raise AttributeError(name)
        
        if name in self._mock_state._children:
            return self._mock_state._children[name]
        
        # Create new child mock
        child = Mock(name=name, parent=self)
        self._mock_state._children[name] = child
        return child
    
    def __setattr__(self, name, value):
        if name.startswith('_mock_') or name in ('_mock_state',):
            super().__setattr__(name, value)
        else:
            super().__setattr__(name, value)
            # Store in children for consistent access
            if hasattr(self, '_mock_state'):
                self._mock_state._children[name] = value
    
    def __delattr__(self, name):
        if name in self._mock_state._children:
            del self._mock_state._children[name]
        super().__delattr__(name)
    
    def reset_mock(self, visited=None):
        """Reset all the calls and state on this mock"""
        if visited is None:
            visited = set()
        
        if id(self) in visited:
            return
        visited.add(id(self))
        
        self._mock_state.call_count = 0
        self._mock_state.call_args = None
        self._mock_state.call_args_list.clear()
        
        # Reset all children
        for child in self._mock_state._children.values():
            if hasattr(child, 'reset_mock'):
                child.reset_mock(visited)
    
    def configure_mock(self, **kwargs):
        """Configure the mock with keyword arguments"""
        for name, value in kwargs.items():
            # Handle nested attributes like 'foo.bar.baz'
            if '.' in name:
                parts = name.split('.')
                obj = self
                for part in parts[:-1]:
                    obj = getattr(obj, part)
                setattr(obj, parts[-1], value)
            else:
                setattr(self, name, value)
    
    def attach_mock(self, mock, attribute):
        """Attach a mock object as an attribute"""
        setattr(self, attribute, mock)
        mock._mock_state.name = attribute
        mock._mock_state._parent = self
    
    def mock_add_spec(self, spec, spec_set=False):
        """Add a spec to a mock"""
        self._mock_state.spec = spec
        if spec_set:
            self._mock_state.spec_set = spec
    
    @property
    def called(self):
        """True if the mock has been called at least once"""
        return self._mock_state.call_count > 0
    
    @property
    def call_count(self):
        """Number of times the mock has been called"""
        return self._mock_state.call_count
    
    @property
    def call_args(self):
        """Arguments from the last call"""
        return self._mock_state.call_args
    
    @property
    def call_args_list(self):
        """List of all calls made to the mock"""
        return self._mock_state.call_args_list
    
    @property
    def return_value(self):
        """The return value when the mock is called"""
        if self._mock_state.return_value is DEFAULT:
            # Create a new Mock as the default return value
            self._mock_state.return_value = Mock(name=f'{self._mock_state.name or "mock"}()')
        return self._mock_state.return_value
    
    @return_value.setter
    def return_value(self, value):
        self._mock_state.return_value = value
    
    @property
    def side_effect(self):
        """Side effect when the mock is called"""
        return self._mock_state.side_effect
    
    @side_effect.setter
    def side_effect(self, value):
        self._mock_state.side_effect = value
        # Reset iterator when side_effect changes
        self._mock_state._side_effect_iterator = None

class Mock(NonCallableMock):
    """Mock object that can be called"""
    
    def __call__(self, *args, **kwargs):
        """Make the mock callable"""
        self._mock_state.call_count += 1
        self._mock_state.call_args = _Call(args=args, kwargs=kwargs)
        self._mock_state.call_args_list.append(self._mock_state.call_args)
        
        # Handle side effect
        if self._mock_state.side_effect is not None:
            side_effect = self._mock_state.side_effect
            
            # Check if it's an exception class (type that is subclass of BaseException)
            if (isinstance(side_effect, type) and 
                issubclass(side_effect, BaseException)):
                raise side_effect()
            # Check if it's an exception instance
            elif isinstance(side_effect, BaseException):
                raise side_effect
            # Check if it's a callable (function, method, etc.)
            elif callable(side_effect):
                return side_effect(*args, **kwargs)
            # Check if it's an iterable (list, tuple, etc.)
            elif hasattr(side_effect, '__iter__'):
                # Create iterator once and reuse it
                if self._mock_state._side_effect_iterator is None:
                    self._mock_state._side_effect_iterator = iter(side_effect)
                try:
                    return next(self._mock_state._side_effect_iterator)
                except StopIteration:
                    pass
        
        # Return configured return value (property handles creating default Mock)
        return self.return_value
    
    def assert_called(self):
        """Assert the mock has been called at least once"""
        if not self.called:
            raise AssertionError(f"Expected '{self._mock_state.name or 'mock'}' to have been called")
    
    def assert_called_once(self):
        """Assert the mock has been called exactly once"""
        if not self.called:
            raise AssertionError(f"Expected '{self._mock_state.name or 'mock'}' to have been called")
        if self.call_count != 1:
            raise AssertionError(f"Expected '{self._mock_state.name or 'mock'}' to have been called once. Called {self.call_count} times.")
    
    def assert_called_with(self, *args, **kwargs):
        """Assert the mock was called with the specified arguments"""
        if not self.called:
            raise AssertionError(f"Expected '{self._mock_state.name or 'mock'}' to have been called")
        
        expected = _Call(args=args, kwargs=kwargs)
        actual = self.call_args
        
        if expected != actual:
            raise AssertionError(f"Expected call: {expected}\nActual call: {actual}")
    
    def assert_called_once_with(self, *args, **kwargs):
        """Assert the mock was called exactly once with the specified arguments"""
        self.assert_called_once()
        self.assert_called_with(*args, **kwargs)
    
    def assert_has_calls(self, calls, any_order=False):
        """Assert the mock has been called with the specified calls"""
        if not isinstance(calls, list):
            calls = list(calls)
        
        if any_order:
            # Check if all calls are present (order doesn't matter)
            for call in calls:
                if call not in self.call_args_list:
                    raise AssertionError(f"Expected call {call} not found in call list")
        else:
            # Check calls in order
            if len(calls) > len(self.call_args_list):
                raise AssertionError("Expected more calls than were made")
            
            for i, expected_call in enumerate(calls):
                if i >= len(self.call_args_list) or expected_call != self.call_args_list[i]:
                    raise AssertionError(f"Expected call {expected_call} at position {i}")
    
    def assert_not_called(self):
        """Assert the mock has never been called"""
        if self.called:
            raise AssertionError(f"Expected '{self._mock_state.name or 'mock'}' to not have been called")

class MagicMock(Mock):
    """Mock with magic methods pre-configured"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add common magic methods
        magic_methods = [
            '__str__', '__repr__', '__len__', '__iter__', '__next__',
            '__enter__', '__exit__', '__getitem__', '__setitem__', '__delitem__',
            '__contains__', '__bool__', '__int__', '__float__', '__hash__',
            '__eq__', '__ne__', '__lt__', '__le__', '__gt__', '__ge__',
            '__add__', '__sub__', '__mul__', '__div__', '__truediv__', '__floordiv__',
            '__mod__', '__pow__', '__and__', '__or__', '__xor__', '__lshift__', '__rshift__'
        ]
        
        for method in magic_methods:
            if not hasattr(self, method):
                mock_method = Mock(name=f'{self._mock_state.name}.{method}')
                setattr(self, method, mock_method)

class PropertyMock(Mock):
    """Mock for properties"""
    
    def __init__(self, return_value=DEFAULT, **kwargs):
        super().__init__(**kwargs)
        if return_value is not DEFAULT:
            self.return_value = return_value
    
    def __get__(self, obj, obj_type=None):
        return self()
    
    def __set__(self, obj, value):
        self(value)
    
    def __delete__(self, obj):
        self()

class AsyncMock(Mock):
    """Mock for async functions (simplified version)"""
    
    async def __call__(self, *args, **kwargs):
        """Async version of Mock.__call__"""
        result = super().__call__(*args, **kwargs)
        return result

# Patch functionality
class _patch:
    """Context manager and decorator for patching"""
    
    def __init__(self, getter, attribute, new=DEFAULT, spec=None, 
                 create=False, spec_set=None, autospec=None, new_callable=None,
                 **kwargs):
        if new_callable is not None:
            if new is not DEFAULT:
                raise ValueError("Cannot use 'new' and 'new_callable' together")
            new = new_callable
        
        if new is DEFAULT:
            new = Mock(spec=spec, spec_set=spec_set, **kwargs)
        
        self.getter = getter
        self.attribute = attribute
        self.new = new
        self.create = create
        self.orig_value = None
        self.is_local = False
    
    def __enter__(self):
        """Enter the patch context"""
        original = self.getter()
        
        if not hasattr(original, self.attribute):
            if not self.create:
                raise AttributeError(f"'{original}' does not have attribute '{self.attribute}'")
            self.is_local = True
        else:
            self.orig_value = getattr(original, self.attribute)
        
        setattr(original, self.attribute, self.new)
        return self.new
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the patch context"""
        original = self.getter()
        
        if self.is_local:
            if hasattr(original, self.attribute):
                delattr(original, self.attribute)
        else:
            setattr(original, self.attribute, self.orig_value)
    
    def __call__(self, func):
        """Use as decorator"""
        if hasattr(func, '__self__'):
            # Method
            def wrapper(*args, **kwargs):
                with self:
                    return func(*args, **kwargs)
        else:
            # Function
            def wrapper(*args, **kwargs):
                with self:
                    return func(*args, **kwargs)
        return wrapper

def patch(target, new=DEFAULT, spec=None, create=False, spec_set=None,
          autospec=None, new_callable=None, **kwargs):
    """Patch an object"""
    try:
        # Parse target string like 'module.attribute'
        parts = target.rsplit('.', 1)
        if len(parts) == 1:
            raise ValueError(f"Need a '.' in target: {target}")
        
        module_name, attribute = parts
        
        def getter():
            # Import the module
            if module_name in sys.modules:
                return sys.modules[module_name]
            else:
                return __import__(module_name)
        
        return _patch(getter, attribute, new, spec, create, spec_set,
                     autospec, new_callable, **kwargs)
    
    except (ImportError, AttributeError, ValueError) as e:
        raise ValueError(f"Invalid patch target: {target}") from e

def patch_object(target, attribute, new=DEFAULT, spec=None, create=False,
                spec_set=None, autospec=None, new_callable=None, **kwargs):
    """Patch an attribute on an object"""
    def getter():
        return target
    
    return _patch(getter, attribute, new, spec, create, spec_set,
                 autospec, new_callable, **kwargs)

# Add patch.object as an attribute of the patch function  
# patch.object = patch_object

def mock_open(mock=None, read_data=''):
    """Create a mock that can be used to patch open()"""
    if mock is None:
        mock = MagicMock(name='open')
    
    handle = MagicMock()
    handle.read.return_value = read_data
    handle.readline.return_value = read_data
    handle.readlines.return_value = read_data.splitlines(True)
    handle.__iter__ = Mock(return_value=iter(read_data.splitlines(True)))
    
    mock.return_value = handle
    return mock

def create_autospec(spec, spec_set=False, instance=False, **kwargs):
    """Create a mock with automatic spec from an object"""
    if spec is None:
        return Mock(**kwargs)
    
    # Simple implementation - just create a mock with the same attributes
    mock_obj = Mock(**kwargs)
    
    if hasattr(spec, '__dict__'):
        for name in dir(spec):
            if not name.startswith('_'):
                attr = getattr(spec, name)
                if callable(attr):
                    setattr(mock_obj, name, Mock())
                else:
                    setattr(mock_obj, name, Mock())
    
    return mock_obj

# Sentinel object for unique default values
class SentinelObject:
    """A sentinel object"""
    __immutable__ = True
    
    def __init__(self, name):
        self.name = name
    
    def __repr__(self):
        return f'sentinel.{self.name}'

class _SentinelObject:
    """Factory for sentinel objects"""
    __immutable__ = True
    
    def __getattr__(self, name):
        return SentinelObject(name)

sentinel = _SentinelObject()

# Remove the circular reference - MagicMock class is already defined above

# Aliases for compatibility
NonCallableMagicMock = MagicMock

# Export main symbols
__all__ = (
    'Mock', 'MagicMock', 'NonCallableMock', 'PropertyMock', 'AsyncMock',
    'patch', 'patch_object', 'mock_open', 'create_autospec',
    'call', 'sentinel', 'DEFAULT'
)