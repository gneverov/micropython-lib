import freeze
freeze.import_modules(
    'unittest', 'unittest.mock', 'unittest.freeze', 
    'operator', 'queue', 'selectors', 'shutil', 
    'http.client', 'http.cookiejar', 'urllib.parse', 
    'test.support', 'test.support.script_helper',
)

import gc
import os
import sys
import test, test.support
import unittest

test.support.use_resources = []

def main(start=None, **kwargs):
    for file in os.scandir(test.__path__):
        if file.is_file() and file.name.startswith('test_') and file.name.endswith('.mpy'):
            name = file.name[:-4]
            if start is not None and name != start:
                continue
            start = None
            full_name = f"{test.__name__}.{name}"
            print(f"Testing module '{name}'...")
            r = unittest.main(full_name, **kwargs)
            if not r.wasSuccessful():
                return r
            del sys.modules[full_name]
            delattr(test, name)
            gc.collect()
    if start is not None:
        raise FileNotFoundError(start)
