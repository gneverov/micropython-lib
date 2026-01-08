# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
Simple contextvars implementation for MicroPython
Compatible with Python's contextvars module API
"""

import threading

# Global context storage for the current thread
_context_storage = threading.local()

# Sentinel object for missing values
_MISSING = object()

class Token:
    """
    A token returned by ContextVar.set() that can be used to restore
    the previous value of the context variable.
    """
    
    def __init__(self, context_var, old_value):
        self.var = context_var
        self.old_value = old_value
    
    def __repr__(self):
        return f"<Token var={self.var!r} at {id(self):#x}>"

class ContextVar:
    """
    A context variable.
    
    Context variables are used to store context-local state that can be
    accessed from anywhere within the same execution context (like a thread
    or async task).
    """
    
    def __init__(self, name, *, default=_MISSING):
        self._name = name
        self._default = default
    
    @property
    def name(self):
        """The name of the context variable"""
        return self._name
    
    def get(self, default=_MISSING):
        """
        Get the current value of the context variable.
        
        Args:
            default: Default value to return if not set
            
        Returns:
            The current value of the context variable
            
        Raises:
            LookupError: If variable is not set and no default provided
        """
        context = _get_current_context()
        
        if self in context:
            return context[self]
        
        if default is not _MISSING:
            return default
        
        if self._default is not _MISSING:
            return self._default
        
        raise LookupError(f"context variable {self._name!r} not found")
    
    def set(self, value):
        """
        Set the value of the context variable.
        
        Args:
            value: The value to set
            
        Returns:
            A Token that can be used to restore the previous value
        """
        context = _get_current_context()
        old_value = context.get(self, _MISSING)
        context[self] = value
        return Token(self, old_value)
    
    def delete(self):
        """
        Delete the context variable from the current context.
        
        Raises:
            LookupError: If variable is not set in current context
        """
        context = _get_current_context()
        
        if self not in context:
            raise LookupError(f"context variable {self._name!r} not found")
        
        del context[self]
    
    def __repr__(self):
        return f"<ContextVar name={self._name!r} at {id(self):#x}>"

class Context:
    """
    A mapping-like object that represents the current context state.
    
    Context objects are immutable and can be used to capture the current
    context state and run code within that captured state.
    """
    
    def __init__(self, data=None):
        if data is None:
            data = {}
        # Create a copy to ensure immutability
        self._data = dict(data)
    
    def get(self, var, default=_MISSING):
        """
        Get the value of a context variable.
        
        Args:
            var: The ContextVar to get
            default: Default value if not found
            
        Returns:
            The value of the context variable
            
        Raises:
            LookupError: If variable not found and no default
        """
        if not isinstance(var, ContextVar):
            raise TypeError("Expected ContextVar instance")
        
        if var in self._data:
            return self._data[var]
        
        if default is not _MISSING:
            return default
        
        if var._default is not _MISSING:
            return var._default
        
        raise LookupError(f"context variable {var._name!r} not found")
    
    def run(self, callable, *args, **kwargs):
        """
        Run callable in this context.
        
        Args:
            callable: Function to run
            *args: Arguments to pass to callable
            **kwargs: Keyword arguments to pass to callable
            
        Returns:
            The result of calling callable(*args, **kwargs)
        """
        # Save current context
        old_context = _get_current_context_dict()
        
        try:
            # Set new context
            _set_current_context_dict(self._data)
            return callable(*args, **kwargs)
        finally:
            # Restore old context
            _set_current_context_dict(old_context)
    
    def copy(self):
        """
        Create a copy of this context.
        
        Returns:
            A new Context with the same variable values
        """
        return Context(self._data)
    
    def __getitem__(self, var):
        """Get a context variable value (raises KeyError if not found)"""
        if not isinstance(var, ContextVar):
            raise TypeError("Expected ContextVar instance")
        
        if var in self._data:
            return self._data[var]
        
        raise KeyError(var)
    
    def __contains__(self, var):
        """Check if a context variable is set in this context"""
        if not isinstance(var, ContextVar):
            return False
        return var in self._data
    
    def __iter__(self):
        """Iterate over context variables in this context"""
        return iter(self._data)
    
    def __len__(self):
        """Get the number of context variables in this context"""
        return len(self._data)
    
    def __repr__(self):
        return f"<Context at {id(self):#x} vars={len(self._data)}>"

def copy_context():
    """
    Copy the current context.
    
    Returns:
        A new Context object with the current context state
    """
    current = _get_current_context_dict()
    return Context(current)

def _get_current_context():
    """Get the current context as a mutable dict"""
    if not hasattr(_context_storage, 'context'):
        _context_storage.context = {}
    return _context_storage.context

def _get_current_context_dict():
    """Get the current context dict (for copying)"""
    if not hasattr(_context_storage, 'context'):
        return {}
    return dict(_context_storage.context)

def _set_current_context_dict(context_dict):
    """Set the current context dict"""
    _context_storage.context = dict(context_dict)

# Function to reset a token
def reset_var(token):
    """
    Reset a context variable to its previous value using a token.
    
    Args:
        token: Token returned by ContextVar.set()
    """
    if not isinstance(token, Token):
        raise TypeError("Expected Token instance")
    
    context = _get_current_context()
    
    if token.old_value is _MISSING:
        # Variable wasn't set before, so delete it
        context.pop(token.var, None)
    else:
        # Restore previous value
        context[token.var] = token.old_value

# Exception for context variable errors
class ContextVarError(Exception):
    """Base exception for context variable errors"""
    pass

# Export main symbols
__all__ = (
    'ContextVar', 'Context', 'Token', 'copy_context', 'reset_var', 'ContextVarError'
)