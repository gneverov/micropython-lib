import _thread


class Thread:
    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None):
        self.target = target
        self._name = name
        self.args = args
        self.kwargs = {} if kwargs is None else kwargs
        self._ident = None
        self.alive = False
        self.lock = _thread.allocate_lock()

    def start(self):
        self._ident = _thread.start_new_thread(self.run, ())
        self.lock.acquire()
        self.alive = True

    def run(self):
        try:
            self.target(*self.args, **self.kwargs)
        finally:
            self.alive = False
            self.lock.release()

    def join(self, timeout=None):
        if self._ident is None:
            raise RuntimeError()
        
        self.lock.acquire()
        self.lock.release()
        
    @property
    def name(self):
        return self._name
    
    @property
    def ident(self):
        return self._ident
    
    def is_alive(self):
        return self.alive
