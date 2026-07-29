# mc-iclone8-mcp v0.1.2

## Validation

- Confirmed `ping_iclone` and `get_api_version` against iClone 8 RLPy.
- Confirmed 95 MCP tools are exposed after restarting the plugin.
- Read-only scene inventory succeeded for avatars, props, cameras, lights, and paths.
- Confirmed the installed scene contains Eddy, Shadow Catcher, Preview Camera, four lights, and no paths.
- Confirmed Eddy currently exposes no morph targets.
- Confirmed Preview Camera is readable but cannot be transform-animated; use a real scene camera for camera animation.

## Fixes and additions

- Fixed `list_objects` for iClone builds returning nested lists from `FindObjects`.
- Added audio source validation and audio tracks on props/avatars.
- Added specialized file saving for iAvatar, iProp, motion, iTalk, and iMotionPlus.
- Added experimental USD export options.
- Added morph weight keys and controlled morph-key removal.
- Added experimental viseme clip creation and removal.
- Updated the English/French guides and the reusable iClone 8 agent skill.

## Known limitations

Audio attachment, specialized saves, USD/GLB/OBJ/Alembic exports, morphs, and
viseme clip editing remain experimental and must be tested with compatible
assets in the installed iClone build. Paths can be controlled when they exist,
but public Python API support does not provide reliable path creation or curve
point editing.
