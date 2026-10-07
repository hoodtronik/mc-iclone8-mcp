# iClone MCP Capability Expansion & Software-Archaeology Strategy

**Status:** Active strategy for the hoodtronik fork.

## Mission

Grow this MCP beyond the currently documented public Python surface without turning it into a brittle collection of guessed calls.

The target is an iClone Agent Automation Layer:

~~~text
official RLPy
+ installed RLPy/SWIG surface
+ Qt/UI introspection where useful
+ runtime observation
+ targeted native archaeology
+ version-aware native bridges when justified
+ MCP tools with evidence and safety metadata
~~~

This is a capability-discovery strategy, not a mandate to reverse engineer all of iClone.

## 1. One missing capability at a time

Do not begin with "reverse engineer iClone." Begin with one concrete user-visible operation such as creating a path, editing path points, changing a Motion Layer key, or performing a specific Reach/IK operation. Find the smallest subsystem that owns that behavior and stop when a safe, testable automation route exists.

## 2. Source-of-truth order

1. Installed iClone runtime and observed RLPy behavior.
2. Installed Bin64/RLPy.py SWIG wrapper and local prototypes.
3. Official Reallusion iClone 8 Python documentation and official samples.
4. Current MCP source and tests.
5. Qt/PySide2 runtime/UI surfaces exposed inside iClone.
6. Targeted native runtime/static archaeology.
7. Agent reports and guesses.

If sources conflict, record the conflict. Do not silently reconcile it.

Read these before capability work:
- docs/hoodtronik/ICLONE8_AGENT_REFERENCE.md
- docs/hoodtronik/automation-entry-points.md
- docs/hoodtronik/HANDOFF_iCloneMCP_research.md
- docs/hoodtronik/ICLONE_CAPABILITY_GAP_MATRIX.md

## 3. Do not assume iClone is Unity

Treat iClone as a native/proprietary Windows application unless concrete evidence proves otherwise. Current local evidence already shows that RLPy.py is a SWIG-style wrapper over native functionality, host-dependent calls require the live iClone process, real C++ prototypes can leak through wrapper errors, and the UI is accessible through PySide2/Qt. That makes native archaeology relevant, but it does not justify inventing an internal architecture.

## 4. Capability escalation ladder

Always use the least invasive layer that solves the problem.

### Tier A: OFFICIAL
Use documented and runtime-verified RLPy. Highest expected stability.

### Tier B: OBSERVED / LOCAL-STUB
Use functionality present in the installed RLPy.py, official samples, runtime introspection, or experimental API surfaces that are not fully documented.
Requirements: verify the symbol/signature against the installed build, exercise it on a disposable scene, verify the actual scene effect rather than only a return status, and record the exact iClone build.

### Tier C: UI / QT SURFACE
If public Python does not expose the operation, inspect whether iClone's Qt/PySide2 UI exposes a stable QAction, widget, command, signal, or Python-visible object that performs it.
Prefer named actions and stable object names. Avoid absolute screen coordinates, blind mouse macros, and timing-only automation.

### Tier D: NATIVE INTERNAL
Use targeted native archaeology only when A-C cannot provide the requested capability and the creator value justifies the maintenance cost.

Typical path:
~~~text
manual operation
  -> observe strings / UI action / state change
  -> identify owning module
  -> trace xrefs / callers / callees
  -> characterize function + required object state
  -> build smallest safe native bridge
  -> expose a narrow Python/MCP wrapper
~~~

Do not expose arbitrary raw addresses as normal MCP tools. Prefer a project-owned native bridge that fingerprints the iClone build, resolves signatures safely, refuses unknown builds, validates objects, and fails closed.

### Tier E: UNSAFE_EXPERIMENTAL
A call can be triggered but ownership, lifecycle, object validity, or failure behavior is not understood. Never run automatically on a valuable scene. Require a checkpoint and disposable test project.

## 5. Tool roles

- python_exec: fastest in-process probe for RLPy/Qt behavior before formalizing a tool.
- Existing diagnostics/tests: establish exact build and protect current behavior.
- REA / Universal Modder when available: workflow, evidence, runtime observation, prior-art reconnaissance.
- Ghidra MCP when available: broad native strings/xrefs/call graphs/decompilation/data-flow/type recovery.
- IDA MCP when available: difficult native functions, type recovery, decompiler comparison, independent confirmation.
- ILSpy / Cpp2IL: not first-line for iClone itself unless a specific component proves to be managed/.NET or Unity IL2CPP.

Choose tools for the target subsystem, not because they are fashionable.

## 6. Runtime observation workflow

When the creator says, "I can do this manually in iClone. Figure out how to expose it":

1. Record exact iClone build.
2. Save a disposable project before the operation.
3. Capture relevant scene/timeline/UI state.
4. Perform the operation manually once.
5. Capture state again.
6. Diff scene objects, timeline/clip state, useful serialized state, Qt objects/actions, logs/callbacks, and native observations where available.
7. Form the smallest testable hypothesis.
8. Reproduce through RLPy first, then local/observed APIs, then Qt, then native bridge.
9. Verify by reading back state and/or rendering a visual proof.
10. Record evidence in the capability matrix.

## 7. Capability Gap Audit

Maintain docs/hoodtronik/ICLONE_CAPABILITY_GAP_MATRIX.md before adding random new tools.

For every capability, answer:
- Can a human do it in the iClone UI?
- Can the current MCP do it?
- Is it in official RLPy docs?
- Is it present in the installed RLPy.py?
- Is a stable Qt action/widget available?
- Does native archaeology appear necessary?
- How valuable is it to the creator's real previz workflow?
- What is the crash/data-loss risk?
- What evidence supports the status?

Prioritize roughly by creator workflow value x frequency x automation leverage divided by implementation/risk cost.

Known example already documented in the repo: path creation and curve-point editing are not exposed by the public Python API.

Do not infer other gaps merely because the MCP does not yet wrap them. Audit first.

## 8. Recommended first milestone

Before deep native reverse engineering, complete an official/local-surface gap audit:

1. inventory installed RLPy.py;
2. inventory current MCP tools;
3. compare against official iClone 8 docs and samples;
4. identify public/local symbols not yet wrapped;
5. identify creator-important UI features genuinely absent from RLPy;
6. populate the capability gap matrix;
7. rank the top five missing capabilities;
8. choose one for an end-to-end proof.

The audit itself should not modify iClone binaries or perform broad decompilation.

## 9. Safe native-bridge architecture

~~~text
AI client
  -> MCP
  -> Python plugin / dispatcher
  -> project-owned native bridge
  -> validated internal call boundary
  -> iClone
~~~

The native bridge should have a narrow typed API, explicit version/signature handling, structured errors, sanity checks, logging, tests, and fail-closed behavior on unknown versions. Do not turn python_exec into a generic native-memory manipulation endpoint.

## 10. Checkpoints

Checkpoint before operations that can modify animation/timeline structures, create/delete scene structures, change project-global settings, invoke undocumented/internal behavior, or trigger crash-prone rendering/export. Extend the existing checkpoint conventions in main.py rather than bypassing them.

## 11. Evidence labels

Use PROVEN-RUNTIME, PROVEN-SOURCE, PROVEN-FILESYSTEM, PROVEN-TEST, PROVEN-BUILD, DOC-SUPPORTED, INFERRED, UNVERIFIED, and CONFLICT.

Hard rule: **code that looks correct is not runtime proof.** A successful RLPy status object is not proof if the scene did not actually change.

## 12. Formalizing a discovered capability

Before merging a new tool:
1. name the user-visible capability;
2. document the discovery path;
3. record capability tier;
4. record exact tested iClone build(s);
5. implement the smallest wrapper;
6. add readback/verification where possible;
7. add checkpoint requirement where appropriate;
8. add tests that can run outside iClone where feasible;
9. add a runtime test recipe;
10. update README and the capability matrix;
11. preserve the upstream-isolation conventions in AGENTS.md.

## 13. Stop conditions

Stop autonomous work and ask for creator judgment when:
- the remaining decision is animation feel, cinematic taste, or workflow preference;
- a paid tool/license is required;
- the native route would require destructive modification of installed iClone files;
- the operation would bypass licensing, DRM, or access controls;
- two materially different technical approaches fail;
- the only proposed solution is broad blind memory scanning without a bounded target;
- the work is turning into a general iClone replacement rather than MCP automation;
- a Reallusion update invalidates a version-sensitive internal route.

## 14. Success criterion

The desired decision flow is:

~~~text
user request
  -> current MCP supports it? use it
  -> official/local RLPy available? wrap + verify
  -> stable Qt/internal UI command? expose carefully
  -> important enough for native archaeology?
  -> targeted Ghidra/IDA/runtime investigation
  -> version-aware bridge
  -> MCP tool
~~~

The goal is not to prove that an agent can reverse engineer software. The goal is to let the creator say, "I can do this manually in iClone. Make the agent able to do it safely and repeatably," and provide a disciplined path to a verified capability.
