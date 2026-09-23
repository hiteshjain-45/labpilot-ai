"""LabPilot sandbox harness.

This file is NEVER imported by the web application. It is executed in a separate, short-lived
interpreter process:

    python -I -S harness.py <student_code_file> <config_json>

Layers of defence applied here (defence-in-depth, see docs/SECURITY.md for limitations):
  1. OS resource limits (address space, CPU time, file size, open files, no new processes)
  2. A capped stdout/stderr so a print-loop cannot flood memory or disk
  3. An import allow-list (no os, subprocess, socket, ctypes, pathlib, importlib, ...)
  4. open() is disabled; `sys` is replaced by a minimal shim for student code
  5. A static check that rejects the classic object-graph escapes (__subclasses__, __globals__, frame
     attributes, eval/exec/getattr, ...) with a readable message
  6. An audit hook that refuses starting processes, opening files or sockets, ctypes, frame access and
     similar operations at the moment they happen, however the student's code reached them. This is the
     layer that does not depend on guessing every trick.

None of this is a security boundary: see docs/SECURITY.md.

Only the standard library may be imported here.
"""
import ast
import builtins
import json
import linecache
import os
import sys
import traceback
import types

OUTPUT_LIMIT_EXIT_CODE = 3

ALLOWED_MODULES = {
    "math", "cmath", "random", "itertools", "collections", "functools", "heapq", "bisect",
    "string", "re", "statistics", "decimal", "fractions", "operator", "copy", "json",
    "typing", "dataclasses", "enum", "textwrap", "array", "time", "datetime", "numbers",
    "abc", "sys",
    "_strptime",  # datetime.strptime and time.strptime import it from C code
}


# ---- static check ---------------------------------------------------------------------------------------
# Builtins a lab program never needs and that make reflection tricks possible. Ignored when the program
# defines a variable or function with that name itself.
DENIED_NAMES = frozenset({
    "eval", "exec", "compile", "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "__builtins__", "__loader__", "__spec__",
})
# Attributes that lead from an ordinary object to the interpreter's internals.
DENIED_ATTRS = frozenset({
    "__bases__", "__base__", "__mro__", "__subclasses__", "__globals__", "__builtins__", "__code__",
    "__closure__", "__func__", "__self__", "__dict__", "__getattribute__", "__reduce__", "__reduce_ex__",
    "__traceback__", "__loader__", "__spec__", "__import__",
    "f_back", "f_builtins", "f_code", "f_globals", "f_locals", "f_trace", "tb_frame", "tb_next",
    "gi_frame", "gi_code", "gi_yieldfrom", "cr_frame", "cr_code", "cr_await", "ag_frame", "ag_code",
})


def find_violation(tree):
    """Return (line, message) for the first restricted construct in the parsed program, or None."""
    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            defined.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in DENIED_NAMES and node.id not in defined:
            return node.lineno, f"'{node.id}' is disabled in the LabPilot sandbox"
        if isinstance(node, ast.Attribute) and node.attr in DENIED_ATTRS:
            return node.lineno, f"access to '.{node.attr}' is disabled in the LabPilot sandbox"
    return None


# ---- audit hook -----------------------------------------------------------------------------------------
IMPORT_DENY = frozenset({
    "subprocess", "_posixsubprocess", "socket", "_socket", "ssl", "_ssl", "ctypes", "_ctypes", "pty", "shutil",
    "multiprocessing", "_multiprocessing", "asyncio", "http", "urllib", "smtplib", "ftplib", "telnetlib",
    "xmlrpc", "socketserver", "webbrowser", "pickle", "_pickle", "sqlite3", "_sqlite3", "code", "codeop",
    "pdb", "bdb", "runpy",
})
EVENT_DENY = frozenset({
    "os.chdir", "os.chmod", "os.chown", "os.chroot", "os.exec", "os.fork", "os.forkpty", "os.kill", "os.killpg",
    "os.link", "os.mkdir", "os.mkfifo", "os.mknod", "os.posix_spawn", "os.putenv", "os.remove", "os.removexattr",
    "os.rename", "os.rmdir", "os.setxattr", "os.spawn", "os.startfile", "os.symlink", "os.system", "os.truncate",
    "os.unsetenv", "os.utime", "os.add_dll_directory",
})
PREFIX_DENY = (
    "subprocess.", "socket.", "ctypes.", "shutil.", "urllib.", "http.", "smtplib.", "ftplib.", "telnetlib.",
    "imaplib.", "poplib.", "nntplib.", "winreg.", "msvcrt.", "gc.", "pty.", "webbrowser.", "multiprocessing.",
    "sqlite3.", "mmap.", "resource.", "code.", "sys.",
)
SOURCE_SUFFIXES = (".py", ".pyc", ".so", ".pyd")


def install_audit_hook():
    """Refuse dangerous operations at the moment they happen, however the student's code reached them.

    Object-graph tricks and module attributes can hand a program the real `os` or `io`. An audit hook does not
    care how it got there: starting a process, opening a file or a socket, using ctypes or reading stack frames
    raises PermissionError. Only read access to the interpreter's own library files is left, which the import
    system needs. The hook cannot be removed from Python code.
    """
    normcase, realpath, sep, fsdecode = os.path.normcase, os.path.realpath, os.sep, os.fsdecode
    roots = tuple(sorted({
        normcase(realpath(p))
        for p in (sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix, os.path.dirname(os.__file__))
    }))
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    event_deny, prefix_deny, import_deny, suffixes = EVENT_DENY, PREFIX_DENY, IMPORT_DENY, SOURCE_SUFFIXES
    permission_error, value_error, import_error = PermissionError, ValueError, ImportError

    def in_library(path):
        try:
            resolved = normcase(realpath(fsdecode(path)))
        except Exception:
            return False
        return any(resolved == r or resolved.startswith(r + sep) for r in roots)

    def hook(event, args):
        if event == "open":
            path, mode, flags = args
            writing = (isinstance(flags, int) and bool(flags & write_flags)) or (isinstance(mode, str) and any(c in mode for c in "wax+"))
            if not writing and isinstance(path, (str, bytes)) and in_library(path) and fsdecode(path).endswith(suffixes):
                return
            raise permission_error("File access is disabled in the LabPilot sandbox")
        if event == "import":
            if str(args[0]).split(".")[0] in import_deny:
                raise import_error(f"Import of '{args[0]}' is disabled in the LabPilot sandbox")
            return
        if event in ("os.listdir", "os.scandir"):
            path = args[0] if args else None
            if path is None or (isinstance(path, (str, bytes)) and in_library(path)):
                return  # the import system lists library folders
            raise permission_error("File access is disabled in the LabPilot sandbox")
        if event == "sys._getframe":  # the standard library catches ValueError here (namedtuple, enum, warnings)
            raise value_error("call stack access is disabled in the LabPilot sandbox")
        if event in ("sys.excepthook", "sys.unraisablehook", "sys._getframemodulename"):
            return  # the last one returns only a module name (namedtuple, enum and typing use it), never a frame
        if event in event_deny or event.startswith(prefix_deny):
            raise permission_error(f"{event} is disabled in the LabPilot sandbox")

    sys.addaudithook(hook)


class OutputLimitExceeded(Exception):
    pass


class CappedStream:
    """Text stream that refuses to write more than `limit` characters."""

    def __init__(self, raw, limit):
        self._raw = raw
        self._limit = limit
        self._written = 0
        self.encoding = "utf-8"

    def write(self, text):
        if not isinstance(text, str):
            raise TypeError("write() argument must be str")
        self._written += len(text)
        if self._written > self._limit:
            raise OutputLimitExceeded("Program produced more output than the sandbox allows")
        return self._raw.write(text)

    def flush(self):
        self._raw.flush()

    def writable(self):
        return True

    def isatty(self):
        return False

    def __getattr__(self, name):
        if name in ("buffer", "fileno", "detach"):
            raise AttributeError(name)
        return getattr(self._raw, name)


def apply_resource_limits(cfg):
    """Best effort: returns silently on platforms without the `resource` module (Windows)."""
    try:
        import resource
    except ImportError:
        return

    def limit(name, soft, hard=None):
        try:
            resource.setrlimit(getattr(resource, name), (soft, soft if hard is None else hard))
        except (ValueError, OSError, AttributeError):
            pass

    memory = int(cfg.get("memory_mb", 256)) * 1024 * 1024
    cpu = max(1, int(cfg.get("cpu_seconds", 3)))
    out_bytes = int(cfg.get("max_output_chars", 64000)) * 4 + 16384
    limit("RLIMIT_AS", memory)
    limit("RLIMIT_CPU", cpu, cpu + 1)
    limit("RLIMIT_FSIZE", out_bytes)  # stdout/stderr are files owned by the parent
    limit("RLIMIT_NOFILE", 64)
    limit("RLIMIT_CORE", 0)
    limit("RLIMIT_NPROC", 0)  # no fork/exec/threads for non-root users


def _blocked_open(*_args, **_kwargs):
    raise PermissionError("File access is disabled in the LabPilot sandbox")


def build_sys_shim(real_sys):
    shim = types.ModuleType("sys")
    shim.stdin = real_sys.stdin
    shim.stdout = real_sys.stdout
    shim.stderr = real_sys.stderr
    shim.argv = ["main.py"]
    shim.maxsize = real_sys.maxsize
    shim.version = real_sys.version
    shim.version_info = real_sys.version_info
    shim.float_info = real_sys.float_info
    shim.exit = real_sys.exit
    shim.getrecursionlimit = real_sys.getrecursionlimit

    def setrecursionlimit(n):
        real_sys.setrecursionlimit(max(50, min(int(n), 20000)))

    shim.setrecursionlimit = setrecursionlimit
    return shim


def make_import_guard(real_import, student_globals, shim_sys):
    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        # Only imports issued by the student's own code are checked; the standard library may
        # freely import its own dependencies.
        if globals is None or globals is student_globals:
            top = name.split(".")[0]
            if top == "sys":
                return shim_sys
            if top not in ALLOWED_MODULES:
                raise ImportError(f"Import of '{name}' is disabled in the LabPilot sandbox")
        return real_import(name, globals, locals, fromlist, level)

    return guarded_import


def main():
    code_path, cfg_json = sys.argv[1], sys.argv[2]
    cfg = json.loads(cfg_json)
    with open(code_path, encoding="utf-8") as handle:
        source = handle.read()

    apply_resource_limits(cfg)

    limit = int(cfg.get("max_output_chars", 64000))
    real_stderr = sys.__stderr__
    for stream, newline in ((sys.stdin, None), (sys.stdout, "\n"), (sys.stderr, "\n")):
        try:
            if newline is None:
                stream.reconfigure(encoding="utf-8", errors="replace")
            else:  # no "\r\n" translation on Windows: the captured output is compared and shown as written
                stream.reconfigure(encoding="utf-8", errors="replace", newline=newline)
        except Exception:
            pass
    sys.stdout = CappedStream(sys.__stdout__, limit)
    sys.stderr = CappedStream(sys.__stderr__, limit)

    student_globals = {"__name__": "__main__", "__doc__": None}
    shim = build_sys_shim(sys)
    real_import = builtins.__import__
    builtins.__import__ = make_import_guard(real_import, student_globals, shim)
    builtins.open = _blocked_open
    for name in ("breakpoint", "help"):
        if hasattr(builtins, name):
            delattr(builtins, name)
    builtins.exit = builtins.quit = lambda code=None: sys.exit(code)

    linecache.cache["<student>"] = (len(source), None, source.splitlines(True), "<student>")
    try:
        tree = compile(source, "<student>", "exec", ast.PyCF_ONLY_AST)  # syntax errors are reported as before
        violation = find_violation(tree)
        if violation:
            real_stderr.write(f"SandboxRestriction: line {violation[0]}: {violation[1]}\n")
            return 1
        program = compile(tree, "<student>", "exec")
        install_audit_hook()  # from here on the operations listed above are refused
        exec(program, student_globals)
        return 0
    except SystemExit as exc:
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        real_stderr.write(str(exc.code) + "\n")
        return 1
    except OutputLimitExceeded as exc:
        real_stderr.write(f"OutputLimitExceeded: {exc}\n")
        return OUTPUT_LIMIT_EXIT_CODE
    except BaseException as exc:  # noqa: BLE001 - report any student error
        # Show only the student's own frames: never leak harness internals or host paths.
        frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == "<student>"]
        parts = []
        if frames:
            parts.append("Traceback (most recent call last):\n")
            parts.extend(traceback.format_list(frames))
        parts.extend(traceback.format_exception_only(type(exc), exc))
        real_stderr.write("".join(parts)[-4000:])
        return 1
    finally:
        try:
            sys.__stdout__.flush()
            real_stderr.flush()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
