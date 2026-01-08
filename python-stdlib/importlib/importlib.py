# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
Simple importlib implementation for MicroPython
Compatible with Python's importlib module API
"""

import sys

# Store original built-in __import__ function
_builtin_import = __import__

def __import__(name, globals=None, locals=None, fromlist=(), level=0):
    """
    Import a module.
    
    Args:
        name: The name of the module to import
        globals: Global namespace (usually not used in basic cases)
        locals: Local namespace (usually not used in basic cases)
        fromlist: List of names to import from the module (for 'from x import y')
        level: Relative import level (0 = absolute, >0 = relative)
    
    Returns:
        The imported module object
    """
    return _builtin_import(name, globals, locals, fromlist, level)

def import_module(name, package=None):
    """
    Import a module by name.
    
    This is equivalent to calling __import__(name, fromlist=['']) but is 
    cleaner and more explicit.
    
    Args:
        name: The name of the module to import. Can be relative (starting with .)
              if package is provided.
        package: The package name for relative imports. If name starts with a dot,
                this must be provided.
    
    Returns:
        The imported module object
    
    Raises:
        ImportError: If the module cannot be found or loaded
        ValueError: For invalid relative import specifications
    """
    # Handle relative imports
    if name.startswith('.'):
        if package is None:
            raise ValueError("attempted relative import with no known parent package")
        
        # Count leading dots to determine level
        level = 0
        for char in name:
            if char == '.':
                level += 1
            else:
                break
        
        # Get the relative module name (after the dots)
        relative_name = name[level:]
        
        # Create globals dict with package info for __import__
        globals_dict = {'__name__': package}
        
        return __import__(relative_name, globals_dict, None, [''], level)
    
    else:
        # Absolute import - use fromlist=[''] to get the actual module
        return __import__(name, None, None, [''])

def reload(module):
    """
    Reload a previously imported module.
    
    This removes the module from sys.modules and re-imports it, which causes
    the module's code to be re-executed.
    
    Args:
        module: The module object to reload
    
    Returns:
        The reloaded module object
    
    Raises:
        ImportError: If the module cannot be reloaded
        AttributeError: If the module doesn't have a __name__ attribute
    """
    if not hasattr(module, '__name__'):
        raise AttributeError("module must have a __name__ attribute")
    
    name = module.__name__
    
    # Handle built-in modules - they cannot be reloaded
    if name in sys.builtin_module_names:
        raise ImportError(f"cannot reload built-in module '{name}'")
    
    # Save reference to avoid issues if reload fails
    old_module = sys.modules.get(name)
    
    try:
        # Remove from sys.modules to force reload
        if name in sys.modules:
            del sys.modules[name]
        
        # Re-import the module
        new_module = import_module(name)
        
        # Update the existing module object's __dict__ instead of replacing it
        # This helps maintain references to the module object
        module.__dict__.clear()
        module.__dict__.update(new_module.__dict__)
        
        return module
    
    except Exception:
        # Restore old module if reload failed
        if old_module is not None:
            sys.modules[name] = old_module
        raise
