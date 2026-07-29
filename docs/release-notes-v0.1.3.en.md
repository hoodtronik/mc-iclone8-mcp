# mc-iclone8-mcp v0.1.3

## Code-review fixes

- `camera.set_camera` now uses the shared `current_time()` helper.
- `follow_path`, `release_path`, `set_path_position`, and `set_path_offset` now use the shared `current_frame()` helper.
- Rectangular light dimensions now use `require_success` for consistent status handling.
- `diagnostics._call` no longer swallows unexpected exceptions; only missing/invalid API access types receive the fallback value.
- The no-light case already returns a clear `ValueError` instead of a later attribute error.

## Verification

- Python compilation succeeded.
- All 4 MCP unit tests passed.
- Corrected files were copied to the iClone 8 plugin directory.
- No iClone 7 references were introduced.

Experimental iClone operations still require validation with compatible assets
inside the installed iClone 8 build.
