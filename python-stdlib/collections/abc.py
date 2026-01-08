# SPDX-FileCopyrightText: 2025 Gregory Neverov
# SPDX-License-Identifier: MIT

"""
Simple collections.abc implementation for MicroPython
Compatible with Python's collections.abc module API
"""

from abc import ABC, abstractmethod
import sys

# Container ABCs
class Container(ABC):
    """ABC for classes that provide __contains__"""
    
    @abstractmethod
    def __contains__(self, x):
        return False

class Hashable(ABC):
    """ABC for classes that provide __hash__"""
    
    @abstractmethod
    def __hash__(self):
        return 0

class Sized(ABC):
    """ABC for classes that provide __len__"""
    
    @abstractmethod
    def __len__(self):
        return 0

class Callable(ABC):
    """ABC for classes that provide __call__"""
    
    @abstractmethod
    def __call__(self, *args, **kwargs):
        return NotImplemented

class Iterator(ABC):
    """ABC for classes that provide __iter__ and __next__"""
    
    @abstractmethod
    def __iter__(self):
        return self
    
    @abstractmethod
    def __next__(self):
        raise StopIteration
    
    def __iter__(self):
        return self

class Iterable(ABC):
    """ABC for classes that provide __iter__"""
    
    @abstractmethod
    def __iter__(self):
        while False:
            yield None

class Reversible(Iterable):
    """ABC for classes that provide __reversed__"""
    
    @abstractmethod
    def __reversed__(self):
        while False:
            yield None

class Generator(Iterator):
    """ABC for generator objects"""
    
    def send(self, value):
        raise StopIteration
    
    def throw(self, typ, val=None, tb=None):
        if val is None:
            if tb is None:
                raise typ
            val = typ()
        if tb is not None:
            raise val.with_traceback(tb)
        raise val
    
    def close(self):
        try:
            self.throw(GeneratorExit)
        except (GeneratorExit, StopIteration):
            pass
        else:
            raise RuntimeError("generator ignored GeneratorExit")

class Coroutine(ABC):
    """ABC for coroutine objects"""
    
    @abstractmethod
    def send(self, value):
        raise StopIteration
    
    @abstractmethod
    def throw(self, typ, val=None, tb=None):
        if val is None:
            if tb is None:
                raise typ
            val = typ()
        if tb is not None:
            raise val.with_traceback(tb)
        raise val
    
    @abstractmethod
    def close(self):
        try:
            self.throw(GeneratorExit)
        except (GeneratorExit, StopIteration):
            pass
        else:
            raise RuntimeError("coroutine ignored GeneratorExit")

class AsyncIterable(ABC):
    """ABC for classes that provide __aiter__"""
    
    @abstractmethod
    def __aiter__(self):
        return NotImplemented

class AsyncIterator(AsyncIterable):
    """ABC for classes that provide __aiter__ and __anext__"""
    
    @abstractmethod
    def __anext__(self):
        return NotImplemented
    
    def __aiter__(self):
        return self

class AsyncGenerator(AsyncIterator):
    """ABC for async generator objects"""
    
    def asend(self, value):
        raise NotImplemented
    
    def athrow(self, typ, val=None, tb=None):
        raise NotImplemented
    
    def aclose(self):
        raise NotImplemented

# Sequence ABCs
class Sequence(Reversible, Container, Sized):
    """ABC for finite sequences"""
    
    @abstractmethod
    def __getitem__(self, index):
        raise IndexError
    
    def __iter__(self):
        i = 0
        try:
            while True:
                v = self[i]
                yield v
                i += 1
        except IndexError:
            return
    
    def __contains__(self, value):
        for v in self:
            if v == value:
                return True
        return False
    
    def __reversed__(self):
        for i in reversed(range(len(self))):
            yield self[i]
    
    def index(self, value, start=0, stop=None):
        if start is not None and start < 0:
            start = max(len(self) + start, 0)
        if stop is not None and stop < 0:
            stop += len(self)
        
        i = start
        while stop is None or i < stop:
            try:
                v = self[i]
                if v == value:
                    return i
            except IndexError:
                break
            i += 1
        raise ValueError
    
    def count(self, value):
        return sum(1 for v in self if v == value)

class MutableSequence(Sequence):
    """ABC for mutable sequences"""
    
    @abstractmethod
    def __setitem__(self, index, value):
        raise IndexError
    
    @abstractmethod
    def __delitem__(self, index):
        raise IndexError
    
    @abstractmethod
    def insert(self, index, value):
        raise IndexError
    
    def append(self, value):
        self.insert(len(self), value)
    
    def clear(self):
        try:
            while True:
                self.pop()
        except IndexError:
            pass
    
    def reverse(self):
        n = len(self)
        for i in range(n // 2):
            self[i], self[n - i - 1] = self[n - i - 1], self[i]
    
    def extend(self, values):
        for value in values:
            self.append(value)
    
    def pop(self, index=-1):
        v = self[index]
        del self[index]
        return v
    
    def remove(self, value):
        del self[self.index(value)]
    
    def __iadd__(self, values):
        self.extend(values)
        return self

# Set ABCs
class Set(Container, Sized, Iterable):
    """ABC for sets"""
    
    def __le__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        if len(self) > len(other):
            return False
        for elem in self:
            if elem not in other:
                return False
        return True
    
    def __lt__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        return len(self) < len(other) and self.__le__(other)
    
    def __gt__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        return len(self) > len(other) and self.__ge__(other)
    
    def __ge__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        if len(self) < len(other):
            return False
        for elem in other:
            if elem not in self:
                return False
        return True
    
    def __eq__(self, other):
        if not isinstance(other, Set):
            return NotImplemented
        return len(self) == len(other) and self.__le__(other)
    
    def __and__(self, other):
        if not isinstance(other, Iterable):
            return NotImplemented
        return self._from_iterable(value for value in other if value in self)
    
    def __or__(self, other):
        if not isinstance(other, Iterable):
            return NotImplemented
        chain = (e for s in (self, other) for e in s)
        return self._from_iterable(chain)
    
    def __sub__(self, other):
        if not isinstance(other, Set):
            if not isinstance(other, Iterable):
                return NotImplemented
            other = self._from_iterable(other)
        return self._from_iterable(value for value in self if value not in other)
    
    def __xor__(self, other):
        if not isinstance(other, Set):
            if not isinstance(other, Iterable):
                return NotImplemented
            other = self._from_iterable(other)
        return (self - other) | (other - self)
    
    def isdisjoint(self, other):
        for value in other:
            if value in self:
                return False
        return True
    
    @classmethod
    def _from_iterable(cls, it):
        return cls(it)

class MutableSet(Set):
    """ABC for mutable sets"""
    
    @abstractmethod
    def add(self, value):
        raise NotImplementedError
    
    @abstractmethod
    def discard(self, value):
        raise NotImplementedError
    
    def remove(self, value):
        if value not in self:
            raise KeyError(value)
        self.discard(value)
    
    def pop(self):
        it = iter(self)
        try:
            value = next(it)
        except StopIteration:
            raise KeyError
        self.discard(value)
        return value
    
    def clear(self):
        try:
            while True:
                self.pop()
        except KeyError:
            pass
    
    def __ior__(self, other):
        for value in other:
            self.add(value)
        return self
    
    def __iand__(self, other):
        for value in (self - other):
            self.discard(value)
        return self
    
    def __ixor__(self, other):
        if not isinstance(other, Set):
            other = self._from_iterable(other)
        for value in other:
            if value in self:
                self.discard(value)
            else:
                self.add(value)
        return self
    
    def __isub__(self, other):
        for value in other:
            self.discard(value)
        return self

# Mapping ABCs
class Mapping(Container, Sized, Iterable):
    """ABC for mappings (read-only)"""
    
    @abstractmethod
    def __getitem__(self, key):
        raise KeyError
    
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
    
    def __contains__(self, key):
        try:
            self[key]
        except KeyError:
            return False
        else:
            return True
    
    def keys(self):
        return KeysView(self)
    
    def items(self):
        return ItemsView(self)
    
    def values(self):
        return ValuesView(self)
    
    def __eq__(self, other):
        if not isinstance(other, Mapping):
            return NotImplemented
        return dict(self.items()) == dict(other.items())

class MutableMapping(Mapping):
    """ABC for mutable mappings"""
    
    @abstractmethod
    def __setitem__(self, key, value):
        raise KeyError
    
    @abstractmethod
    def __delitem__(self, key):
        raise KeyError
    
    def pop(self, key, *args):
        try:
            value = self[key]
        except KeyError:
            if args:
                return args[0]
            raise
        else:
            del self[key]
            return value
    
    def popitem(self):
        try:
            key = next(iter(self))
        except StopIteration:
            raise KeyError
        value = self[key]
        del self[key]
        return key, value
    
    def clear(self):
        try:
            while True:
                self.popitem()
        except KeyError:
            pass
    
    def update(self, other=(), **kwds):
        if hasattr(other, "keys"):
            for key in other:
                self[key] = other[key]
        else:
            for key, value in other:
                self[key] = value
        for key, value in kwds.items():
            self[key] = value
    
    def setdefault(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            self[key] = default
        return default

# View ABCs
class MappingView(Sized):
    """ABC for mapping views"""
    
    def __init__(self, mapping):
        self._mapping = mapping
    
    def __len__(self):
        return len(self._mapping)
    
    def __repr__(self):
        return f'{self.__class__.__name__}({self._mapping!r})'

class KeysView(MappingView, Set):
    """ABC for keys views"""
    
    def __contains__(self, key):
        return key in self._mapping
    
    def __iter__(self):
        yield from self._mapping

class ItemsView(MappingView, Set):
    """ABC for items views"""
    
    def __contains__(self, item):
        key, value = item
        try:
            v = self._mapping[key]
        except KeyError:
            return False
        else:
            return v == value
    
    def __iter__(self):
        for key in self._mapping:
            yield (key, self._mapping[key])

class ValuesView(MappingView):
    """ABC for values views"""
    
    def __contains__(self, value):
        for v in self:
            if v == value:
                return True
        return False
    
    def __iter__(self):
        for key in self._mapping:
            yield self._mapping[key]

# Register built-in types
# Hashable.register(object)
# Container.register(tuple)
# Container.register(frozenset)
# Container.register(list)
# Container.register(set)
# Container.register(dict)
# Container.register(str)
# Container.register(bytes)

# Sized.register(tuple)
# Sized.register(list)
# Sized.register(frozenset)
# Sized.register(set)
# Sized.register(dict)
# Sized.register(str)
# Sized.register(bytes)

# Sequence.register(tuple)
# Sequence.register(str)
# Sequence.register(bytes)
# Sequence.register(list)  # Also mutable, but registered here too

# MutableSequence.register(list)

# Set.register(frozenset)
# Set.register(set)

# MutableSet.register(set)

# Mapping.register(dict)
# MutableMapping.register(dict)

# Iterable.register(list)
# Iterable.register(tuple)
# Iterable.register(dict)
# Iterable.register(set)
# Iterable.register(frozenset)
# Iterable.register(str)
# Iterable.register(bytes)

# Iterator.register(type(iter('')))
# Iterator.register(type(iter([])))
# Iterator.register(type(iter({})))

# Export main symbols
# __all__ = [
#     # ABCs
#     'ABC', 'abstractmethod',
    
#     # Basic ABCs
#     'Container', 'Hashable', 'Sized', 'Callable',
#     'Iterator', 'Iterable', 'Reversible',
#     'Generator', 'Coroutine',
#     'AsyncIterable', 'AsyncIterator', 'AsyncGenerator',
    
#     # Sequence ABCs
#     'Sequence', 'MutableSequence',
    
#     # Set ABCs  
#     'Set', 'MutableSet',
    
#     # Mapping ABCs
#     'Mapping', 'MutableMapping',
#     'KeysView', 'ItemsView', 'ValuesView', 'MappingView',
# ]