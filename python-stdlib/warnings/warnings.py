class Warning(Exception):
    pass

def warn(msg, cat=None, stacklevel=1):
    print("%s: %s" % ("Warning" if cat is None else cat.__name__, msg))

def simplefilter(action, category=Warning, lineno=0, append=False):
    pass


class DeprecationWarning(Warning):
    pass
class PendingDeprecationWarning(Warning):
    pass
class RuntimeWarning(Warning):
    pass
class SyntaxWarning(Warning):
    pass
class UserWarning(Warning):
    pass
class FutureWarning(Warning):
    pass
class ImportWarning(Warning):
    pass
class UnicodeWarning(Warning):
    pass
class BytesWarning(Warning):
    pass
class ResourceWarning(Warning):
    pass