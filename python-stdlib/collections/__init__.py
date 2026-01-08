# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
Simple collections implementation for MicroPython
Compatible with Python's collections module API
"""

import sys

# Import any existing collections from ucollections if available
from ucollections import OrderedDict, deque, namedtuple

class defaultdict(dict):
    """Dictionary with default factory function"""
    
    def __init__(self, default_factory=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_factory = default_factory
    
    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            return self.__missing__(key)
    
    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value
    
    def __repr__(self):
        return f"defaultdict({self.default_factory!r}, {dict(self)!r})"
    
    def copy(self):
        return self.__copy__()
    
    def __copy__(self):
        return type(self)(self.default_factory, self)
    
    def __deepcopy__(self, memo):
        import copy
        return type(self)(self.default_factory,
                         copy.deepcopy(dict(self), memo))

class Counter(dict):
    """Dictionary for counting hashable items"""
    
    def __init__(self, iterable=None, **kwargs):
        super().__init__()
        self.update(iterable, **kwargs)
    
    def __missing__(self, key):
        return 0
    
    def most_common(self, n=None):
        """Return list of the n most common elements and their counts"""
        if n is None:
            return sorted(self.items(), key=lambda x: x[1], reverse=True)
        return sorted(self.items(), key=lambda x: x[1], reverse=True)[:n]
    
    def elements(self):
        """Return iterator over elements repeating each as many times as its count"""
        for elem, count in self.items():
            for _ in range(count):
                yield elem
    
    def total(self):
        """Sum of the counts"""
        return sum(self.values())
    
    def subtract(self, iterable=None, **kwargs):
        """Subtract counts"""
        if iterable is not None:
            self_get = self.get
            if isinstance(iterable, dict):
                for elem, count in iterable.items():
                    self[elem] = self_get(elem, 0) - count
            else:
                for elem in iterable:
                    self[elem] = self_get(elem, 0) - 1
        
        for elem, count in kwargs.items():
            self[elem] = self.get(elem, 0) - count
        
        # Remove zero and negative counts
        for elem in list(self.keys()):
            if self[elem] <= 0:
                del self[elem]
    
    def update(self, iterable=None, **kwargs):
        """Add counts"""
        if iterable is not None:
            self_get = self.get
            if isinstance(iterable, dict):
                for elem, count in iterable.items():
                    self[elem] = self_get(elem, 0) + count
            else:
                for elem in iterable:
                    self[elem] = self_get(elem, 0) + 1
        
        for elem, count in kwargs.items():
            self[elem] = self.get(elem, 0) + count
    
    def __add__(self, other):
        """Add counts from two counters"""
        if not isinstance(other, Counter):
            return NotImplemented
        result = Counter()
        for elem, count in self.items():
            result[elem] = count
        for elem, count in other.items():
            result[elem] = result.get(elem, 0) + count
        return result
    
    def __sub__(self, other):
        """Subtract counts"""
        if not isinstance(other, Counter):
            return NotImplemented
        result = Counter()
        for elem, count in self.items():
            newcount = count - other.get(elem, 0)
            if newcount > 0:
                result[elem] = newcount
        return result
    
    def __and__(self, other):
        """Intersection: min(c[x], d[x])"""
        if not isinstance(other, Counter):
            return NotImplemented
        result = Counter()
        for elem, count in self.items():
            other_count = other.get(elem, 0)
            if other_count > 0:
                result[elem] = min(count, other_count)
        return result
    
    def __or__(self, other):
        """Union: max(c[x], d[x])"""
        if not isinstance(other, Counter):
            return NotImplemented
        result = Counter()
        for elem, count in self.items():
            result[elem] = max(count, other.get(elem, 0))
        for elem, count in other.items():
            if elem not in result:
                result[elem] = count
        return result
    
    def __repr__(self):
        if not self:
            return f'{self.__class__.__name__}()'
        items = ', '.join(f'{k!r}: {v}' for k, v in self.most_common())
        return f"{self.__class__.__name__}({{'{items}'}})"

class ChainMap(dict):
    """Combine multiple mappings for sequential lookup"""
    
    def __init__(self, *maps):
        self.maps = list(maps) if maps else [{}]
    
    def __missing__(self, key):
        raise KeyError(key)
    
    def __getitem__(self, key):
        for mapping in self.maps:
            try:
                return mapping[key]
            except KeyError:
                pass
        return self.__missing__(key)
    
    def get(self, key, default=None):
        for mapping in self.maps:
            if key in mapping:
                return mapping[key]
        return default
    
    def __len__(self):
        return len(set().union(*self.maps))
    
    def __iter__(self):
        d = {}
        for mapping in reversed(self.maps):
            d.update(mapping)
        return iter(d)
    
    def __contains__(self, key):
        return any(key in m for m in self.maps)
    
    def __bool__(self):
        return any(self.maps)
    
    def __setitem__(self, key, value):
        self.maps[0][key] = value
    
    def __delitem__(self, key):
        try:
            del self.maps[0][key]
        except KeyError:
            raise KeyError(f'Key not found in the first mapping: {key!r}')
    
    def popitem(self):
        try:
            return self.maps[0].popitem()
        except KeyError:
            raise KeyError('No keys found in the first mapping.')
    
    def pop(self, key, *args):
        try:
            return self.maps[0].pop(key, *args)
        except KeyError:
            raise KeyError(f'Key not found in the first mapping: {key!r}')
    
    def clear(self):
        self.maps[0].clear()
    
    def new_child(self, m=None):
        """Create a new ChainMap with a new map followed by all previous maps"""
        if m is None:
            m = {}
        return self.__class__(m, *self.maps)
    
    @property
    def parents(self):
        """New ChainMap from maps[1:]"""
        return self.__class__(*self.maps[1:])
    
    def __repr__(self):
        return f'{self.__class__.__name__}({", ".join(map(repr, self.maps))})'

class UserDict:
    """Wrapper around dictionary objects for easier dict subclassing"""
    
    def __init__(self, dict=None, **kwargs):
        self.data = {}
        if dict is not None:
            self.update(dict, **kwargs)
        elif kwargs:
            self.update(kwargs)
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        if hasattr(self.__class__, "__missing__"):
            return self.__class__.__missing__(self, key)
        raise KeyError(key)
    
    def __setitem__(self, key, item):
        self.data[key] = item
    
    def __delitem__(self, key):
        del self.data[key]
    
    def __iter__(self):
        return iter(self.data)
    
    def __contains__(self, key):
        return key in self.data
    
    def __repr__(self):
        return repr(self.data)
    
    def get(self, key, default=None):
        return self.data.get(key, default)
    
    def keys(self):
        return self.data.keys()
    
    def items(self):
        return self.data.items()
    
    def values(self):
        return self.data.values()
    
    def clear(self):
        self.data.clear()
    
    def pop(self, key, *args):
        return self.data.pop(key, *args)
    
    def popitem(self):
        return self.data.popitem()
    
    def update(self, dict=None, **kwargs):
        if dict is not None:
            if hasattr(dict, "keys"):
                for key in dict:
                    self[key] = dict[key]
            else:
                for key, value in dict:
                    self[key] = value
        for key, value in kwargs.items():
            self[key] = value
    
    def setdefault(self, key, default=None):
        return self.data.setdefault(key, default)
    
    def copy(self):
        import copy
        return copy.copy(self)

class UserList:
    """Wrapper around list objects for easier list subclassing"""
    
    def __init__(self, initlist=None):
        self.data = []
        if initlist is not None:
            if type(initlist) == type(self.data):
                self.data[:] = initlist
            elif isinstance(initlist, UserList):
                self.data[:] = initlist.data[:]
            else:
                self.data = list(initlist)
    
    def __repr__(self):
        return repr(self.data)
    
    def __lt__(self, other):
        return self.data < self.__cast(other)
    
    def __le__(self, other):
        return self.data <= self.__cast(other)
    
    def __eq__(self, other):
        return self.data == self.__cast(other)
    
    def __gt__(self, other):
        return self.data > self.__cast(other)
    
    def __ge__(self, other):
        return self.data >= self.__cast(other)
    
    def __cast(self, other):
        return other.data if isinstance(other, UserList) else other
    
    def __contains__(self, item):
        return item in self.data
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, i):
        return self.data[i]
    
    def __setitem__(self, i, item):
        self.data[i] = item
    
    def __delitem__(self, i):
        del self.data[i]
    
    def __add__(self, other):
        if isinstance(other, UserList):
            return self.__class__(self.data + other.data)
        elif isinstance(other, type(self.data)):
            return self.__class__(self.data + other)
        return self.__class__(self.data + list(other))
    
    def __radd__(self, other):
        if isinstance(other, UserList):
            return self.__class__(other.data + self.data)
        elif isinstance(other, type(self.data)):
            return self.__class__(other + self.data)
        return self.__class__(list(other) + self.data)
    
    def __iadd__(self, other):
        if isinstance(other, UserList):
            self.data += other.data
        elif isinstance(other, type(self.data)):
            self.data += other
        else:
            self.data += list(other)
        return self
    
    def __mul__(self, n):
        return self.__class__(self.data * n)
    
    def __rmul__(self, n):
        return self.__class__(n * self.data)
    
    def __imul__(self, n):
        self.data *= n
        return self
    
    def append(self, item):
        self.data.append(item)
    
    def insert(self, i, item):
        self.data.insert(i, item)
    
    def pop(self, i=-1):
        return self.data.pop(i)
    
    def remove(self, item):
        self.data.remove(item)
    
    def clear(self):
        self.data.clear()
    
    def copy(self):
        return self.__class__(self)
    
    def count(self, item):
        return self.data.count(item)
    
    def index(self, item, *args):
        return self.data.index(item, *args)
    
    def reverse(self):
        self.data.reverse()
    
    def sort(self, *, key=None, reverse=False):
        self.data.sort(key=key, reverse=reverse)
    
    def extend(self, other):
        if isinstance(other, UserList):
            self.data.extend(other.data)
        else:
            self.data.extend(other)

class UserString:
    """Wrapper around string objects for easier string subclassing"""
    
    def __init__(self, seq=''):
        if isinstance(seq, str):
            self.data = seq
        elif isinstance(seq, UserString):
            self.data = seq.data[:]
        else:
            self.data = str(seq)
    
    def __str__(self):
        return str(self.data)
    
    def __repr__(self):
        return repr(self.data)
    
    def __int__(self):
        return int(self.data)
    
    def __float__(self):
        return float(self.data)
    
    def __complex__(self):
        return complex(self.data)
    
    def __hash__(self):
        return hash(self.data)
    
    def __getnewargs__(self):
        return (self.data[:],)
    
    def __eq__(self, string):
        if isinstance(string, UserString):
            return self.data == string.data
        return self.data == string
    
    def __lt__(self, string):
        if isinstance(string, UserString):
            return self.data < string.data
        return self.data < string
    
    def __le__(self, string):
        if isinstance(string, UserString):
            return self.data <= string.data
        return self.data <= string
    
    def __gt__(self, string):
        if isinstance(string, UserString):
            return self.data > string.data
        return self.data > string
    
    def __ge__(self, string):
        if isinstance(string, UserString):
            return self.data >= string.data
        return self.data >= string
    
    def __contains__(self, char):
        if isinstance(char, UserString):
            char = char.data
        return char in self.data
    
    def __len__(self):
        return len(self.data)
    
    def __getitem__(self, index):
        return self.__class__(self.data[index])
    
    def __add__(self, other):
        if isinstance(other, UserString):
            return self.__class__(self.data + other.data)
        elif isinstance(other, str):
            return self.__class__(self.data + other)
        return self.__class__(self.data + str(other))
    
    def __radd__(self, other):
        if isinstance(other, str):
            return self.__class__(other + self.data)
        return self.__class__(str(other) + self.data)
    
    def __mul__(self, n):
        return self.__class__(self.data * n)
    
    def __rmul__(self, n):
        return self.__class__(n * self.data)
    
    def __mod__(self, args):
        return self.__class__(self.data % args)
    
    # Delegate string methods to the data attribute
    def __getattr__(self, name):
        return getattr(self.data, name)

# Export main symbols
__all__ = (
    'deque', 'defaultdict', 'namedtuple', 'OrderedDict', 'Counter',
    'ChainMap', 'UserDict', 'UserList', 'UserString'
)