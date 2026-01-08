from collections import deque
import unittest
from test import support, seq_tests
try:
    import weakref
except ImportError:
    pass
import random

BIG = 100

def fail():
    raise SyntaxError
    yield 1

class BadCmp:
    def __eq__(self, other):
        raise RuntimeError

class MutateCmp:
    def __init__(self, deque, result):
        self.deque = deque
        self.result = result
    def __eq__(self, other):
        self.deque.clear()
        return self.result
    
has_maxlen = False
skip_maxlen = unittest.skipUnless(has_maxlen, 'maxlen not supported')

class TestBasic(unittest.TestCase):

    def test_basics(self):
        d = deque(range(200))
        for i in range(200, 400):
            d.append(i)
        for i in reversed(range(-200, 0)):
            d.appendleft(i)
        self.assertEqual(list(d), list(range(-200, 400)))
        self.assertEqual(len(d), 600)

        left = [d.popleft() for i in range(250)]
        self.assertEqual(left, list(range(-200, 50)))
        self.assertEqual(list(d), list(range(50, 400)))

        right = [d.pop() for i in range(250)]
        right.reverse()
        self.assertEqual(right, list(range(150, 400)))
        self.assertEqual(list(d), list(range(50, 150)))

    @skip_maxlen
    def test_maxlen(self):
        self.assertRaises(ValueError, deque, 'abc', -1)
        self.assertRaises(ValueError, deque, 'abc', -2)
        it = iter(range(10))
        d = deque(it, maxlen=3)
        self.assertEqual(list(it), [])
        self.assertEqual(repr(d), 'deque([7, 8, 9], maxlen=3)')
        self.assertEqual(list(d), [7, 8, 9])
        self.assertEqual(d, deque(range(10), 3))
        d.append(10)
        self.assertEqual(list(d), [8, 9, 10])
        d.appendleft(7)
        self.assertEqual(list(d), [7, 8, 9])
        d.extend([10, 11])
        self.assertEqual(list(d), [9, 10, 11])
        d.extendleft([8, 7])
        self.assertEqual(list(d), [7, 8, 9])
        if not support.is_micropython:
            d = deque(range(200), maxlen=10)
            d.append(d)
            self.assertEqual(repr(d)[-30:], ', 198, 199, [...]], maxlen=10)')
        d = deque(range(10), maxlen=None)
        self.assertEqual(repr(d), 'deque([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])')

    @skip_maxlen
    def test_maxlen_zero(self):
        it = iter(range(100))
        deque(it, maxlen=0)
        self.assertEqual(list(it), [])

        it = iter(range(100))
        d = deque(maxlen=0)
        d.extend(it)
        self.assertEqual(list(it), [])

        it = iter(range(100))
        d = deque(maxlen=0)
        d.extendleft(it)
        self.assertEqual(list(it), [])

    @skip_maxlen
    def test_maxlen_attribute(self):
        self.assertEqual(deque().maxlen, None)
        self.assertEqual(deque('abc').maxlen, None)
        self.assertEqual(deque('abc', maxlen=4).maxlen, 4)
        self.assertEqual(deque('abc', maxlen=2).maxlen, 2)
        self.assertEqual(deque('abc', maxlen=0).maxlen, 0)
        with self.assertRaises(AttributeError):
            d = deque('abc')
            d.maxlen = 10

    def test_count(self):
        for s in ('', 'abracadabra', 'simsalabim'*5+'abc'):
            s = list(s)
            d = deque(s)
            for letter in 'abcdefghijklmnopqrstuvwxyz':
                self.assertEqual(s.count(letter), d.count(letter), (s, d, letter))
        self.assertRaises(TypeError, d.count)       # too few args
        self.assertRaises(TypeError, d.count, 1, 2) # too many args
        class BadCompare:
            def __eq__(self, other):
                raise ArithmeticError
        d = deque([1, 2, BadCompare(), 3])
        self.assertRaises(ArithmeticError, d.count, 2)
        d = deque([1, 2, 3])
        self.assertRaises(ArithmeticError, d.count, BadCompare())
        class MutatingCompare:
            def __eq__(self, other):
                self.d.pop()
                return True
        m = MutatingCompare()
        d = deque([1, 2, 3, m, 4, 5])
        m.d = d
        self.assertRaises(RuntimeError, d.count, 3)

        # test issue11004
        # block advance failed after rotation aligned elements on right side of block
        d = deque([None]*16)
        for i in range(len(d)):
            d.rotate(-1)
        d.rotate(1)
        self.assertEqual(d.count(1), 0)
        self.assertEqual(d.count(None), 16)

    @support.skip_micropython
    def test_comparisons(self):
        d = deque('xabc')
        d.popleft()
        for e in [d, deque('abc'), deque('ab'), deque(), list(d)]:
            self.assertEqual(d==e, type(d)==type(e) and list(d)==list(e))
            self.assertEqual(d!=e, not(type(d)==type(e) and list(d)==list(e)))

        args = map(deque, ('', 'a', 'b', 'ab', 'ba', 'abc', 'xba', 'xabc', 'cba'))
        for x in args:
            for y in args:
                self.assertEqual(x == y, list(x) == list(y), (x,y))
                self.assertEqual(x != y, list(x) != list(y), (x,y))
                self.assertEqual(x <  y, list(x) <  list(y), (x,y))
                self.assertEqual(x <= y, list(x) <= list(y), (x,y))
                self.assertEqual(x >  y, list(x) >  list(y), (x,y))
                self.assertEqual(x >= y, list(x) >= list(y), (x,y))

    def test_contains(self):
        n = 200

        d = deque(range(n))
        for i in range(n):
            self.assertTrue(i in d)
        self.assertTrue((n+1) not in d)

        # Test detection of mutation during iteration
        d = deque(range(n))
        d[n//2] = MutateCmp(d, False)
        with self.assertRaises(RuntimeError):
            n in d

        # Test detection of comparison exceptions
        d = deque(range(n))
        d[n//2] = BadCmp()
        with self.assertRaises(RuntimeError):
            n in d

    def test_extend(self):
        d = deque('a')
        self.assertRaises(TypeError, d.extend, 1)
        d.extend('bcd')
        self.assertEqual(list(d), list('abcd'))
        d.extend(d)
        self.assertEqual(list(d), list('abcdabcd'))

    @support.skip_micropython
    def test_add(self):
        d = deque()
        e = deque('abc')
        f = deque('def')
        self.assertEqual(d + d, deque())
        self.assertEqual(e + f, deque('abcdef'))
        self.assertEqual(e + e, deque('abcabc'))
        self.assertEqual(e + d, deque('abc'))
        self.assertEqual(d + e, deque('abc'))
        self.assertIsNot(d + d, deque())
        self.assertIsNot(e + d, deque('abc'))
        self.assertIsNot(d + e, deque('abc'))

        if has_maxlen:
            g = deque('abcdef', maxlen=4)
            h = deque('gh')
            self.assertEqual(g + h, deque('efgh'))

        with self.assertRaises(TypeError):
            deque('abc') + 'def'

    @support.skip_micropython
    def test_iadd(self):
        d = deque('a')
        d += 'bcd'
        self.assertEqual(list(d), list('abcd'))
        d += d
        self.assertEqual(list(d), list('abcdabcd'))

    def test_extendleft(self):
        d = deque('a')
        self.assertRaises(TypeError, d.extendleft, 1)
        d.extendleft('bcd')
        self.assertEqual(list(d), list(reversed('abcd')))
        d.extendleft(d)
        self.assertEqual(list(d), list('abcddcba'))
        d = deque()
        d.extendleft(range(100))
        self.assertEqual(list(d), list(reversed(range(100))))
        self.assertRaises(SyntaxError, d.extendleft, fail())

    def test_getitem(self):
        n = 100
        d = deque(range(n))
        l = list(range(n))
        for i in range(n):
            d.popleft()
            l.pop(0)
            if random.random() < 0.5:
                d.append(i)
                l.append(i)
            for j in range(1-len(l), len(l)):
                assert d[j] == l[j]

        d = deque('superman')
        self.assertEqual(d[0], 's')
        self.assertEqual(d[-1], 'n')
        d = deque()
        def __getitem__(i):
            return d[i]
        self.assertRaises(IndexError, __getitem__, 0)
        self.assertRaises(IndexError, __getitem__, -1)

    def test_index(self):
        for n in 1, 2, 20:

            d = deque(range(n))
            for i in range(n):
                self.assertEqual(d.index(i), i)

            with self.assertRaises(ValueError):
                d.index(n+1)

            # Test detection of mutation during iteration
            d = deque(range(n))
            d[n//2] = MutateCmp(d, False)
            with self.assertRaises(RuntimeError):
                d.index(n)

            # Test detection of comparison exceptions
            d = deque(range(n))
            d[n//2] = BadCmp()
            with self.assertRaises(RuntimeError):
                d.index(n)

        # Test start and stop arguments behavior matches list.index()
        elements = 'ABCDEFGHI'
        nonelement = 'Z'
        d = deque(elements * 2)
        s = list(elements * 2)
        for start in range(-1 - len(s), 1 + len(s)):
            for stop in range(-1 - len(s), 1 + len(s)):
                for element in elements + 'Z':
                    try:
                        target = s.index(element, start, stop)
                    except ValueError:
                        with self.assertRaises(ValueError):
                            d.index(element, start, stop)
                    else:
                        self.assertEqual(d.index(element, start, stop), target)

    def test_index_bug_24913(self):
        d = deque('A' * 3)
        with self.assertRaises(ValueError):
            i = d.index("Hello world", 0, 4)

    def test_insert(self):
        # Test to make sure insert behaves like lists
        elements = 'ABCDEFGHI'
        for i in range(-1 - len(elements), 1 + len(elements)):
            d = deque('ABCDEFGHI')
            s = list('ABCDEFGHI')
            d.insert(i, 'Z')
            s.insert(i, 'Z')
            self.assertEqual(list(d), s)

    @skip_maxlen
    def test_insert_bug_26194(self):
        data = 'ABC'
        d = deque(data, maxlen=len(data))
        with self.assertRaises(IndexError):
            d.insert(2, None)

        elements = 'ABCDEFGHI'
        for i in range(-len(elements), len(elements)):
            d = deque(elements, maxlen=len(elements)+1)
            d.insert(i, 'Z')
            if i >= 0:
                self.assertEqual(d[i], 'Z')
            else:
                self.assertEqual(d[i-1], 'Z')

    @support.skip_micropython
    @skip_maxlen
    def test_imul(self):
        for n in (-10, -1, 0, 1, 2, 10, 1000):
            d = deque()
            d *= n
            self.assertEqual(d, deque())
            self.assertIsNone(d.maxlen)

        for n in (-10, -1, 0, 1, 2, 10, 1000):
            d = deque('a')
            d *= n
            self.assertEqual(d, deque('a' * n))
            self.assertIsNone(d.maxlen)

        for n in (-10, -1, 0, 1, 2, 10, 499, 500, 501, 1000):
            d = deque('a', 500)
            d *= n
            self.assertEqual(d, deque('a' * min(n, 500)))
            self.assertEqual(d.maxlen, 500)

        for n in (-10, -1, 0, 1, 2, 10, 1000):
            d = deque('abcdef')
            d *= n
            self.assertEqual(d, deque('abcdef' * n))
            self.assertIsNone(d.maxlen)

        for n in (-10, -1, 0, 1, 2, 10, 499, 500, 501, 1000):
            d = deque('abcdef', 500)
            d *= n
            self.assertEqual(d, deque(('abcdef' * n)[-500:]))
            self.assertEqual(d.maxlen, 500)

    @support.skip_micropython
    def test_mul(self):
        d = deque('abc')
        self.assertEqual(d * -5, deque())
        self.assertEqual(d * 0, deque())
        self.assertEqual(d * 1, deque('abc'))
        self.assertEqual(d * 2, deque('abcabc'))
        self.assertEqual(d * 3, deque('abcabcabc'))
        self.assertIsNot(d * 1, d)

        self.assertEqual(deque() * 0, deque())
        self.assertEqual(deque() * 1, deque())
        self.assertEqual(deque() * 5, deque())

        self.assertEqual(-5 * d, deque())
        self.assertEqual(0 * d, deque())
        self.assertEqual(1 * d, deque('abc'))
        self.assertEqual(2 * d, deque('abcabc'))
        self.assertEqual(3 * d, deque('abcabcabc'))

        if has_maxlen:
            d = deque('abc', maxlen=5)
            self.assertEqual(d * -5, deque())
            self.assertEqual(d * 0, deque())
            self.assertEqual(d * 1, deque('abc'))
            self.assertEqual(d * 2, deque('bcabc'))
            self.assertEqual(d * 30, deque('bcabc'))

    def test_setitem(self):
        n = 200
        d = deque(range(n))
        for i in range(n):
            d[i] = 10 * i
        self.assertEqual(list(d), [10*i for i in range(n)])
        l = list(d)
        for i in range(1-n, 0, -1):
            d[i] = 7*i
            l[i] = 7*i
        self.assertEqual(list(d), l)

    def test_delitem(self):
        n = 50         # O(n**2) test, don't make this too big
        d = deque(range(n))
        def __delitem__(i):
            del d[i]
        self.assertRaises(IndexError, __delitem__, -n-1)
        self.assertRaises(IndexError, __delitem__, n)
        for i in range(n):
            self.assertEqual(len(d), n-i)
            j = random.randrange(-len(d), len(d))
            val = d[j]
            self.assertIn(val, d)
            del d[j]
            self.assertNotIn(val, d)
        self.assertEqual(len(d), 0)

    def test_reverse(self):
        n = 50         # O(n**2) test, don't make this too big
        data = [random.random() for i in range(n)]
        for i in range(n):
            d = deque(data[:i])
            r = d.reverse()
            self.assertEqual(list(d), list(reversed(data[:i])))
            self.assertIs(r, None)
            d.reverse()
            self.assertEqual(list(d), data[:i])
        self.assertRaises(TypeError, d.reverse, 1)          # Arity is zero

    def test_rotate(self):
        s = tuple('abcde')
        n = len(s)

        d = deque(s)
        d.rotate(1)             # verify rot(1)
        self.assertEqual(''.join(d), 'eabcd')

        d = deque(s)
        d.rotate(-1)            # verify rot(-1)
        self.assertEqual(''.join(d), 'bcdea')
        d.rotate()              # check default to 1
        self.assertEqual(tuple(d), s)

        for i in range(n*3):
            d = deque(s)
            e = deque(d)
            d.rotate(i)         # check vs. rot(1) n times
            for j in range(i):
                e.rotate(1)
            self.assertEqual(tuple(d), tuple(e))
            d.rotate(-i)        # check that it works in reverse
            self.assertEqual(tuple(d), s)
            e.rotate(n-i)       # check that it wraps forward
            self.assertEqual(tuple(e), s)

        for i in range(n*3):
            d = deque(s)
            e = deque(d)
            d.rotate(-i)
            for j in range(i):
                e.rotate(-1)    # check vs. rot(-1) n times
            self.assertEqual(tuple(d), tuple(e))
            d.rotate(i)         # check that it works in reverse
            self.assertEqual(tuple(d), s)
            e.rotate(i-n)       # check that it wraps backaround
            self.assertEqual(tuple(e), s)

        d = deque(s)
        e = deque(s)
        e.rotate(BIG+17)        # verify on long series of rotates
        dr = d.rotate
        for i in range(BIG+17):
            dr()
        self.assertEqual(tuple(d), tuple(e))

        self.assertRaises(TypeError, d.rotate, 'x')   # Wrong arg type
        self.assertRaises(TypeError, d.rotate, 1, 10) # Too many args

        d = deque()
        d.rotate()              # rotate an empty deque
        self.assertEqual(d, deque())

    def test_len(self):
        d = deque('ab')
        self.assertEqual(len(d), 2)
        d.popleft()
        self.assertEqual(len(d), 1)
        d.pop()
        self.assertEqual(len(d), 0)
        self.assertRaises(IndexError, d.pop)
        self.assertEqual(len(d), 0)
        d.append('c')
        self.assertEqual(len(d), 1)
        d.appendleft('d')
        self.assertEqual(len(d), 2)
        d.clear()
        self.assertEqual(len(d), 0)

    def test_underflow(self):
        d = deque()
        self.assertRaises(IndexError, d.pop)
        self.assertRaises(IndexError, d.popleft)

    def test_clear(self):
        d = deque(range(100))
        self.assertEqual(len(d), 100)
        d.clear()
        self.assertEqual(len(d), 0)
        self.assertEqual(list(d), [])
        d.clear()               # clear an empty deque
        self.assertEqual(list(d), [])

    def test_remove(self):
        d = deque('abcdefghcij')
        d.remove('c')
        self.assertEqual(d, deque('abdefghcij'))
        d.remove('c')
        self.assertEqual(d, deque('abdefghij'))
        self.assertRaises(ValueError, d.remove, 'c')
        self.assertEqual(d, deque('abdefghij'))

        # Handle comparison errors
        d = deque(['a', 'b', BadCmp(), 'c'])
        e = deque(d)
        self.assertRaises(RuntimeError, d.remove, 'c')
        for x, y in zip(d, e):
            # verify that original order and values are retained.
            self.assertTrue(x is y)

        if not support.is_micropython:
            # Handle evil mutator
            for match in (True, False):
                d = deque(['ab'])
                d.extend([MutateCmp(d, match), 'c'])
                self.assertRaises(IndexError, d.remove, 'c')
                self.assertEqual(d, deque())

    def test_init(self):
        self.assertRaises(TypeError, deque, 'abc', 2, 3)
        self.assertRaises(TypeError, deque, 1)

    def test_hash(self):
        self.assertRaises(TypeError, hash, deque('abc'))

    def test_long_steadystate_queue_popleft(self):
        for size in (0, 1, 2, 100):
            d = deque(range(size))
            append, pop = d.append, d.popleft
            for i in range(size, BIG):
                append(i)
                x = pop()
                if x != i - size:
                    self.assertEqual(x, i-size)
            self.assertEqual(list(d), list(range(BIG-size, BIG)))

    def test_long_steadystate_queue_popright(self):
        for size in (0, 1, 2, 100):
            d = deque(reversed(range(size)))
            append, pop = d.appendleft, d.pop
            for i in range(size, BIG):
                append(i)
                x = pop()
                if x != i - size:
                    self.assertEqual(x, i-size)
            self.assertEqual(list(reversed(list(d))),
                             list(range(BIG-size, BIG)))

    def test_big_queue_popleft(self):
        pass
        d = deque()
        append, pop = d.append, d.popleft
        for i in range(BIG):
            append(i)
        for i in range(BIG):
            x = pop()
            if x != i:
                self.assertEqual(x, i)

    def test_big_queue_popright(self):
        d = deque()
        append, pop = d.appendleft, d.pop
        for i in range(BIG):
            append(i)
        for i in range(BIG):
            x = pop()
            if x != i:
                self.assertEqual(x, i)

    def test_big_stack_right(self):
        d = deque()
        append, pop = d.append, d.pop
        for i in range(BIG):
            append(i)
        for i in reversed(range(BIG)):
            x = pop()
            if x != i:
                self.assertEqual(x, i)
        self.assertEqual(len(d), 0)

    def test_big_stack_left(self):
        d = deque()
        append, pop = d.appendleft, d.popleft
        for i in range(BIG):
            append(i)
        for i in reversed(range(BIG)):
            x = pop()
            if x != i:
                self.assertEqual(x, i)
        self.assertEqual(len(d), 0)

    def test_roundtrip_iter_init(self):
        d = deque(range(200))
        e = deque(d)
        self.assertNotEqual(id(d), id(e))
        self.assertEqual(list(d), list(e))

    def test_copy_method(self):
        mut = [10]
        d = deque([mut])
        e = d.copy()
        self.assertEqual(list(d), list(e))
        mut[0] = 11
        self.assertNotEqual(id(d), id(e))
        self.assertEqual(list(d), list(e))

    def test_reversed(self):
        for s in ('abcd', range(200)):
            self.assertEqual(list(reversed(deque(s))), list(reversed(s)))

    def test_reversed_new(self):
        klass = type(reversed(deque()))
        for s in ('abcd', range(200)):
            self.assertEqual(list(klass(deque(s))), list(reversed(s)))

    def test_gc_doesnt_blowup(self):
        import gc
        # This used to assert-fail in deque_traverse() under a debug
        # build, or run wild with a NULL pointer in a release build.
        d = deque()
        for i in range(100):
            d.append(1)
            gc.collect()

class TestVariousIteratorArgs(unittest.TestCase):

    def test_constructor(self):
        for s in ("123", "", range(100), ('do', 1.2), range(2000,2200,5)):
            for g in (seq_tests.Sequence, seq_tests.IterFunc,
                      seq_tests.IterGen, seq_tests.IterFuncStop,
                      seq_tests.itermulti, seq_tests.iterfunc):
                self.assertEqual(list(deque(g(s))), list(g(s)))
            self.assertRaises(TypeError, deque, seq_tests.IterNextOnly(s))
            self.assertRaises(TypeError, deque, seq_tests.IterNoNext(s))
            self.assertRaises(ZeroDivisionError, deque, seq_tests.IterGenExc(s))

    def test_iter_with_altered_data(self):
        d = deque('abcdefg')
        it = iter(d)
        d.pop()
        self.assertRaises(RuntimeError, next, it)

    def test_runtime_error_on_empty_deque(self):
        d = deque()
        it = iter(d)
        d.append(10)
        self.assertRaises(RuntimeError, next, it)

class Deque(deque):
    pass

class DequeWithBadIter(deque):
    def __iter__(self):
        raise TypeError

class TestSubclass(unittest.TestCase):

    def test_basics(self):
        d = Deque(range(200))
        for i in range(200, 400):
            d.append(i)
        for i in reversed(range(-200, 0)):
            d.appendleft(i)
        self.assertEqual(list(d), list(range(-200, 400)))
        self.assertEqual(len(d), 600)

        left = [d.popleft() for i in range(250)]
        self.assertEqual(left, list(range(-200, 50)))
        self.assertEqual(list(d), list(range(50, 400)))

        right = [d.pop() for i in range(250)]
        right.reverse()
        self.assertEqual(right, list(range(150, 400)))
        self.assertEqual(list(d), list(range(50, 150)))

        d.clear()
        self.assertEqual(len(d), 0)

    @support.requires_weakref
    def test_weakref(self):
        d = deque('gallahad')
        p = weakref.proxy(d)
        self.assertEqual(str(p), str(d))
        d = None
        self.assertRaises(ReferenceError, str, p)

    def test_strange_subclass(self):
        class X(deque):
            def __iter__(self):
                return iter([])
        d1 = X([1,2,3])
        d2 = X([4,5,6])
        d1 == d2   # not clear if this is supposed to be True or False,
                   # but it used to give a SystemError

class SubclassWithKwargs(deque):
    def __init__(self, newarg=1):
        super(deque, self).__init__()

@support.skip_micropython
class TestSubclassWithKwargs(unittest.TestCase):
    def test_subclass_with_kwargs(self):
        # SF bug #1486663 -- this used to erroneously raise a TypeError
        SubclassWithKwargs(newarg=1)

@support.skip_micropython
class TestSequence(seq_tests.CommonTest):
    type2test = deque

    def test_getitem(self):
        # For now, bypass tests that require slicing
        pass

    def test_getslice(self):
        # For now, bypass tests that require slicing
        pass

    def test_subscript(self):
        # For now, bypass tests that require slicing
        pass

    def test_free_after_iterating(self):
        # For now, bypass tests that require slicing
        self.skipTest("Exhausted deque iterator doesn't free a deque")


#==============================================================================


if __name__ == "__main__":
    unittest.main()
