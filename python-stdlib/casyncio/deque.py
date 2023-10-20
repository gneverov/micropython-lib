class deque:
    def __init__(self, iterable=None):
        if iterable is None:
            self.q = []
        else:
            self.q = list(iterable)

    def append(self, a):
        return self.q.append(a)

    def appendleft(self, a):
        return self.q.insert(0, a)

    def clear(self):
        return self.q.clear()

    def copy(self):
        return self.q.copy()
    
    def count(self, a):
        return self.q.count(a)

    def extend(self, a):
        return self.q.extend(a)
    
    def index(self, a, *args):
        return self.q.index(a, *args)

    def pop(self):
        return self.q.pop()

    def popleft(self):
        return self.q.pop(0)
    
    def remove(self, a):
        return self.q.remove(a);

    def reverse(self):
        return self.q.reverse();
        
    def __len__(self):
        return len(self.q)

    def __bool__(self):
        return bool(self.q)

    def __iter__(self):
        return iter(self.q)

    def __str__(self):
        return "deque({})".format(self.q)
