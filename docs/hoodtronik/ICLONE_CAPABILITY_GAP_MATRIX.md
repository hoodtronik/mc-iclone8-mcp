# iClone Capability Gap Matrix

This is the living backlog for capabilities that matter to the creator's actual iClone previz workflow.

Read ICLONE_AUTOMATION_ARCHAEOLOGY_STRATEGY.md before editing this file.

## Status vocabulary

- SUPPORTED: current MCP tool exists and is runtime-proven on a documented build.
- PARTIAL: some required behavior exists but the workflow is incomplete.
- RLPY-CANDIDATE: installed/official RLPy appears to expose it; wrapper/runtime proof still needed.
- QT-CANDIDATE: likely accessible through a stable in-process Qt/UI command; proof needed.
- NATIVE-CANDIDATE: public/local Python surfaces appear insufficient; targeted native archaeology may be justified.
- BLOCKED: no safe route currently known.
- NEEDS-CREATOR: technical options exist but creator workflow/taste must choose.
- UNKNOWN: not audited yet.

## Priority

- P0: blocks active creator work.
- P1: high-frequency/high-leverage previz automation.
- P2: valuable but not currently blocking.
- P3: exploratory/nice-to-have.

## Matrix

| Capability | Human UI? | Current MCP | Official/local RLPy | Qt route | Native route | Tier target | Priority | Evidence / next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Inspect/follow/release existing paths and set path position/offset | Yes | PARTIAL | Partial | UNKNOWN | UNKNOWN | OFFICIAL/OBSERVED | P1 | Existing MCP covers existing paths but not authoring. |
| Create a new path | Yes | NO | Public API documented as missing | UNKNOWN | UNKNOWN | QT or INTERNAL | P1 | Start with Qt action discovery; native archaeology only if Qt route fails. |
| Edit path curve/control points | Yes | NO | Public API documented as missing | UNKNOWN | UNKNOWN | QT or INTERNAL | P1 | Audit exact UI operation and scene/state delta. |

## Audit queue

Add creator-important features here before deep work. Do not mark a feature as missing from RLPy until installed RLPy.py, official docs, samples, and runtime have been checked.

Candidate categories to audit:
- Motion Layer editing
- Reach / IK authoring
- clip creation / split / merge / reposition / transition editing
- animation curve editing
- timeline track editing
- camera creation / switch tracks / deeper camera controls
- Motion Director
- Crowd Simulation
- physics / constraints
- facial editing
- render settings / passes
- retargeting / motion conversion
- Content Manager operations

These are audit categories, not claims that the APIs are missing.
