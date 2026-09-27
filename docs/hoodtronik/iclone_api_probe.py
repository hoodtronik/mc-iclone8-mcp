# iclone_api_probe.py
# Read-only introspection of iClone 8's RLPy API + Python runtime.
# Safe: it only READS the API (dir/inspect) and probes which modules import.
# It does NOT touch the open scene, create/delete objects, or change settings.
#
# HOW TO RUN (see chat for details):
#   iClone menu: Script > Load Python  ->  pick this file.
#   (Fallback: paste into iClone's Python console.)
#
# Output: <Desktop>\iclone_api_dump.json  +  a printed summary in iClone's console.

import inspect
import json
import os
import sys

import RLPy

# CLAUDE-NOTE: SWIG embeds real C++ signatures inside each method's __doc__,
# not in inspect.signature (which almost always fails for builtin SWIG methods).
# So we keep the FULL docstring (capped generously) — that's where the actual
# parameter/return types live. This is the single most valuable field in the dump.
DOC_CAP = 1200


def describe_callable(obj):
    info = {}
    try:
        info["params"] = str(inspect.signature(obj))
    except (ValueError, TypeError):
        info["params"] = "unknown"  # expected for most SWIG builtins
    doc = inspect.getdoc(obj)
    if doc:
        info["doc"] = doc[:DOC_CAP]
    return info


def dump_class(cls):
    methods = []
    for mname in sorted(dir(cls)):
        if mname.startswith("_"):
            continue
        try:
            member = getattr(cls, mname)
        except Exception as e:  # some SWIG props raise on class-level access
            methods.append({"name": mname, "params": "unreadable", "doc": str(e)[:120]})
            continue
        entry = {"name": mname}
        if callable(member):
            entry.update(describe_callable(member))
        else:
            entry["params"] = "<attribute>"
            entry["value"] = repr(member)[:160]
        methods.append(entry)
    return methods


api_dump = {}

for name in sorted(dir(RLPy)):
    if name.startswith("_"):
        continue
    try:
        obj = getattr(RLPy, name)
    except Exception as e:
        api_dump[name] = {"type": "unreadable", "error": str(e)[:160]}
        continue

    entry = {"type": type(obj).__name__}

    if inspect.isclass(obj):
        entry["methods"] = dump_class(obj)
        entry["method_count"] = len(entry["methods"])
    elif callable(obj):
        # Module-level SWIG free functions (RGlobal_*, RScene_*, etc.) live here —
        # these are the real static entry points.
        entry.update(describe_callable(obj))
    elif isinstance(obj, (int, float, str, bool)):
        entry["value"] = obj
    else:
        entry["value"] = repr(obj)[:160]

    api_dump[name] = entry

# ---- Networking / runtime probe (Phase 2b) -------------------------------
networking_modules = []
for mod_name in [
    "socket", "ssl", "select", "selectors", "socketserver",
    "http", "http.server", "xmlrpc", "xmlrpc.server",
    "asyncio", "json", "wsgiref", "ctypes",
    "requests", "websocket", "websockets", "flask", "zmq", "aiohttp",
    "PySide2.QtNetwork", "PySide2.QtWebSockets", "PySide2.QtCore",
]:
    try:
        __import__(mod_name)
        networking_modules.append(mod_name)
    except Exception:
        pass

runtime = {
    "python_version": sys.version,
    "python_executable": sys.executable,
    "sys_path_head": sys.path[:12],
    "available_networking_modules": networking_modules,
    "RLPy_file": getattr(RLPy, "__file__", "?"),
}

# ---- Summary -------------------------------------------------------------
classes = [k for k, v in api_dump.items() if v.get("type") == "type"]
functions = [k for k, v in api_dump.items()
             if v.get("type") in ("builtin_function_or_method", "function")]
constants = [k for k, v in api_dump.items()
             if v.get("type") in ("int", "float", "str", "bool")]
total_methods = sum(v.get("method_count", 0) for v in api_dump.values())

summary = {
    "total_names": len(api_dump),
    "classes": len(classes),
    "functions": len(functions),
    "constants": len(constants),
    "total_methods_across_classes": total_methods,
    "runtime": runtime,
}

out = {"_summary": summary, "_api": api_dump}

output_path = os.path.join(os.path.expanduser("~"), "Desktop", "iclone_api_dump.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)

print("=" * 60)
print("iClone API dump complete")
print("  ->", output_path)
print("  classes:    ", summary["classes"])
print("  functions:  ", summary["functions"])
print("  constants:  ", summary["constants"])
print("  methods:    ", summary["total_methods_across_classes"])
print("  python:     ", runtime["python_version"].split()[0])
print("  net modules:", ", ".join(networking_modules))
print("=" * 60)
