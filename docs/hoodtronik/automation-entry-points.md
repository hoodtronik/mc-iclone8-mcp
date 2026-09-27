# How do you get code INTO iClone? — measured entry-point findings

Recorded 2026-08-29 on the home PC (iClone **8.74.5527.1**, `C:\Program Files\Reallusion\iClone 8`).
Everything below was **tested**, not inferred. This exists because "just launch iClone.exe and run the
script" is the obvious first idea and it **does not work** — save the next agent the 30 minutes.

## TL;DR

| Route | Verdict |
|---|---|
| `iClone.exe -RunPython <script>` | ❌ **Does not execute.** 4 arg forms tried. |
| `iClonepy.exe` (headless RLPy) | ❌ **Access violation** on the first real API call. |
| `Bin64\OpenPlugin\<name>\main.py` auto-load | ✅ The real path — but the folder needs **admin** to write. |
| Menu **Script → Load Python** | ✅ Works, but needs a human. |

⇒ **Until the bridge exists, running a script is either a one-time elevated install into `OpenPlugin`
or a human clicking a menu.** That is not a detour: `OpenPlugin` is exactly where the embedded socket
server has to live anyway, so installing there IS step 1 of the MCP.

## 1. `-RunPython` — present in the binary, does not fire

`iClone.exe` (99 MB) contains a switch table with `-Test`, **`-RunPython`**, `-SilentMode`,
`-ImportProp`, `-ImportAvatar`, `-ImportAnimation`, `-ImportRLHead`, `--default-log-file`,
`--disable-logging`, plus a `CLoadScriptCmd` class symbol and `RLFailReturnAssert( LoadScript() )`.
Promising — but every invocation form was tested and **none executed the script**:

```
iClone.exe -RunPython "G:\path\script.py"      # quoted
iClone.exe -RunPython G:\path\script.py        # bare
iClone.exe -RunPython=G:\path\script.py        # = form (matches the -Test= pattern)
iClone.exe -SilentMode -RunPython G:\path\...  # with silent mode
```

**Test method (do it this way, it removes all ambiguity):** a *canary* script whose only job is to
write a file immediately — no RLPy, no rendering. If the canary file never appears, the switch never
fired; you are not debugging your real script.

```python
import os, sys, datetime
p = os.path.join(os.path.expanduser("~"), "Desktop", "icmcp_canary.txt")
with open(p, "w", encoding="utf-8") as f:
    f.write("FIRED %s\nexe=%s\n" % (datetime.datetime.now(), sys.executable))
    try:
        import RLPy; f.write("RLPy OK\n")
    except Exception as e: f.write("RLPy failed: %r\n" % (e,))
```

Each launch was given **200–300 s**. In every case iClone came up **healthy** — ~2.6 GB working set,
`Responding = True`, `MainWindowTitle = "iClone"`, no modal dialog (enumerated its visible windows to
rule out a hidden prompt) — and simply never ran the file.

**Best hypothesis:** the switch strings sit in a block immediately adjacent to
`Character Creator\5.0` / `CharacterCreator5Temp` / `iAvatar` / `iProject` strings, so `-RunPython`
likely belongs to a **shared Reallusion CT/Core library** (and may be a *Character Creator* switch, or
need a companion flag / licence tier we haven't identified). Worth one more probe from the CC5 side
before writing it off entirely.

## 2. `iClonepy.exe` — imports RLPy, then segfaults

`Bin64\iClonepy.exe` is plain **CPython 3.8.8**. With `PYTHONPATH=<install>\Bin64`:

- `import RLPy` → ✅ **succeeds**, `RLPy.RGlobal` resolves to a class.
- The **first real singleton call** (`RGlobal.GetFps()`) → 💥 process dies with
  **`0xC0000005` ACCESS_VIOLATION** (exit `-1073741819`).

⇒ The SWIG wrapper loads standalone but the C++ singletons are only bound inside the host app.
**There is no headless RLPy.** Anything that drives iClone must run *in-process*, which is precisely
why this project needs an embedded server rather than a CLI.

## 3. `OpenPlugin` — the auto-load path, needs elevation

`C:\Program Files\Reallusion\iClone 8\Bin64\OpenPlugin\` holds one folder per plugin; iClone loads them
at startup. Shipping examples: `AIRender`, `AIStudio`, `MotionLIVE`, `ICLiveLink`, `VideoMocap`,
`Blender Pipeline Plugin`, `IC8-Blender-Tools`. Most are compiled `.pyd`, but **`Blender Pipeline
Plugin` is a plain `main.py`** — proof that a readable `main.py` is a valid plugin.

🔴 The folder is **not writable without admin** (`Access to the path ... is denied`). So installing a
plugin — including this project's future bridge — needs **one elevated copy**, after which every
subsequent run is automatic and needs no human.

## 4. Practical consequence for this project

The MCP bridge plan in `HANDOFF.md` is unchanged and now better justified:

1. **One elevated install** of `OpenPlugin\iCloneMCP\main.py` (socket + non-blocking `select` +
   `QTimer` pump on the main thread, pattern from `Unity Pipeline Plugin\utp\link.py` — GPL, copy the
   *pattern*, not the source).
2. From then on the external MCP server talks to iClone over localhost, and no menu clicking, no
   `-RunPython`, and no elevation is ever needed again.

An interim trick worth trying: make that plugin's `main.py` also execute any script dropped at a known
path on startup — a poor-man's `-RunPython` that actually works, useful for running the PoC slice
unattended before the full socket server exists.
