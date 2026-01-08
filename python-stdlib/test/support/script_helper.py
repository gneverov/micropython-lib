# Common utility functions used by various script execution tests
#  e.g. test_cmd_line, test_cmd_line_script and test_runpy

import collections
import importlib
import sys
import os


class _PythonRunResult(collections.namedtuple("_PythonRunResult",
                                          ("rc", "out", "err"))):
    """Helper for reporting Python subprocess run results"""
    def fail(self, cmd_line):
        """Provide helpful details about failed subcommand runs"""
        # Limit to 80 lines to ASCII characters
        maxlen = 80 * 100
        out, err = self.out, self.err
        if len(out) > maxlen:
            out = b'(... truncated stdout ...)' + out[-maxlen:]
        if len(err) > maxlen:
            err = b'(... truncated stderr ...)' + err[-maxlen:]
        out = out.decode('ascii', 'replace').rstrip()
        err = err.decode('ascii', 'replace').rstrip()
        raise AssertionError("Process return code is %d\n"
                             "command line: %r\n"
                             "\n"
                             "stdout:\n"
                             "---\n"
                             "%s\n"
                             "---\n"
                             "\n"
                             "stderr:\n"
                             "---\n"
                             "%s\n"
                             "---"
                             % (self.rc, cmd_line,
                                out,
                                err))


# Executing the interpreter in a subprocess
def run_python_until_end(*args, **env_vars):
    assert len(args) == 2
    assert args[0] == "-c"
    assert len(env_vars) == 0
    cmd_line = ''
    try:
        exec(args[1])
    except Exception as exc:
        return _PythonRunResult(1, b'', str(exc).encode()), cmd_line
    else:    
        return _PythonRunResult(0, b'', b''), cmd_line

def _assert_python(expected_success, *args, **env_vars):
    res, cmd_line = run_python_until_end(*args, **env_vars)
    if (res.rc and expected_success) or (not res.rc and not expected_success):
        res.fail(cmd_line)
    return res

def assert_python_ok(*args, **env_vars):
    """
    Assert that running the interpreter with `args` and optional environment
    variables `env_vars` succeeds (rc == 0) and return a (return code, stdout,
    stderr) tuple.

    If the __cleanenv keyword is set, env_vars is used as a fresh environment.

    Python is started in isolated mode (command line option -I),
    except if the __isolated keyword is set to False.
    """
    return _assert_python(True, *args, **env_vars)

def assert_python_failure(*args, **env_vars):
    """
    Assert that running the interpreter with `args` and optional environment
    variables `env_vars` fails (rc != 0) and return a (return code, stdout,
    stderr) tuple.

    See assert_python_ok() for more options.
    """
    return _assert_python(False, *args, **env_vars)

def make_script(script_dir, script_basename, source, omit_suffix=False):
    script_filename = script_basename
    if not omit_suffix:
        script_filename += os.extsep + 'py'
    script_name = os.path.join(script_dir, script_filename)
    # The script should be encoded to UTF-8, the default string encoding
    script_file = open(script_name, 'w', encoding='utf-8')
    script_file.write(source)
    script_file.close()
    importlib.invalidate_caches()
    return script_name
