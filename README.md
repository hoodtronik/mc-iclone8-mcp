# mc-iclone8-mcp

[Français](README.fr.md)

A local MCP server for controlling iClone 8 through its official Python API.

The iClone plugin provides a small start/stop window. The MCP endpoint is local
only and defaults to `http://127.0.0.1:8766/mcp`. All iClone commands are sent
back to iClone's main thread before they run.

## Requirements

- iClone 8 on Windows.
- A client supporting Streamable HTTP MCP, such as Codex.

## Install the iClone plugin

1. Copy this repository folder to:

   ```text
   <iClone 8>\Bin64\OpenPlugin\mc-iclone8-mcp
   ```

2. Start iClone 8 and load the plugin.
3. Open **Plugins → mc-iclone8-mcp → Open MCP server**.
4. Select **Start**. The status must show `http://127.0.0.1:8766/mcp`.

The server deliberately binds to `127.0.0.1`: it is intended for the computer
running iClone, not for a network connection.

## Install as a Codex MCP server

Keep iClone open and start the server first. Then run:

```powershell
codex mcp add mc-iclone8-mcp --url http://127.0.0.1:8766/mcp
```

Restart Codex (or start a new task) after adding it. Confirm the configuration
with:

```powershell
codex mcp list
```

Alternatively, add the following to `%USERPROFILE%\.codex\config.toml` (or to
the project’s `.codex\config.toml`):

```toml
[mcp_servers.mc-iclone8-mcp]
url = "http://127.0.0.1:8766/mcp"
startup_timeout_sec = 15
tool_timeout_sec = 60
```

An identical ready-to-copy sample is available at
[`examples/codex-config.toml`](examples/codex-config.toml).

Configuration examples for Claude Code, Pi coding agent, OpenClaw, Hermes, and
VS Code are collected in [`docs/agent-configs.en.md`](docs/agent-configs.en.md).
The reusable expert skill is available in
[`skills/iclone8-mcp`](skills/iclone8-mcp).

Prompts with scene prerequisites are available in
[`docs/usage-examples.en.md`](docs/usage-examples.en.md) and
[`docs/exemples-utilisation.fr.md`](docs/exemples-utilisation.fr.md).

Detailed setup instructions for Claude Code, Pi coding agent, OpenClaw, Hermes,
and VS Code are available in [`docs/agent-configs.en.md`](docs/agent-configs.en.md)
and [`docs/agent-configs.fr.md`](docs/agent-configs.fr.md).

## Updating the plugin and clients

1. Stop the MCP server with iClone’s **Stop** button.
2. Close or reload the iClone plugin if required by the installed build.
3. Download the new version from the [latest GitHub release](https://github.com/gorbabor/mc-iclone8-mcp/releases).
4. Replace the complete plugin folder:

   ```text
   <iClone 8>\Bin64\OpenPlugin\mc-iclone8-mcp
   ```

   Do not mix old files from `tools` with the new release.
5. Restart iClone 8, load the plugin, and click **Start**.
6. Confirm the local URL and restart/reload the MCP client so it refreshes the
   tool list.

The client configurations normally remain unchanged because they continue to
use `http://127.0.0.1:8766/mcp`. Restart the client or MCP session after an
update to avoid a stale tool list. Test new experimental operations in the
installed iClone build before using them on an important scene.

## Available capabilities

The current development line adds the documented iClone 8 camera, material,
light, facial/viseme, content-browser, import, export, and thumbnail operations
to the previous `v0.1.1` baseline. The source registry currently defines 90 MCP
tools; experimental operations must still be checked against the installed
iClone build after restarting the plugin.

| Category | Tools | What they do |
| --- | --- | --- |
| Diagnostics | `ping_iclone`, `get_api_version`, `get_runtime_diagnostics`, `get_application_info`, `list_content_folders`, `list_content_files` | Check connectivity, iClone 8 version/paths, and browse Smart Content folders/files. |
| Scene and objects | `list_objects`, `get_selection`, `select_object`, `set_visibility`, `delete_object`, `clone_object`, `link_object`, `unlink_object`, `align_object`, `set_static` | Inspect, select, show/hide, delete, clone, link, unlink, and align objects. |
| Projects and assets | `create_primitive`, `save_project`, `get_project_info`, `import_asset`, `load_object`, `load_alembic`, `load_motion`, `preload_motion`, `load_substance_painter_textures`, `export_fbx`, `export_obj`, `export_glb`, `save_thumbnail` | Create primitives, import objects/Alembic, load motions, apply textures, save projects, extract thumbnails, and export FBX/OBJ/GLB. OBJ/GLB/Alembic are experimental; OBJ is documented mainly for CC3. |
| Transforms | `get_transform`, `get_object_bounds`, `set_transform`, `delete_transform_key`, `move_transform_key`, `set_transform_key_transition`, `clear_transform_keys` | Read world-space bounds, position, rotation, scale, and animation keys. |
| Paths | `list_paths`, `get_path_info`, `follow_path`, `release_path`, `set_path_position`, `set_path_offset`, `clear_path_keys` | Inspect and control an existing iClone path. Curve-point editing is not exposed by the public Python API; a path can be created by importing a template `.iPath` (`find_content` kind `path`) and fitting it with `set_transform`. Measured on 8.75 (hoodtronik fork): `set_path_position` returns success but creates no key, so followers stay at the path start; use the fork's `path_position_key` (percent, via the Modify panel) instead. |
| Timeline | `get_timeline`, `set_timeline`, `play_timeline`, `pause_timeline`, `stop_timeline`, `clear_scene_animations` | Control playback, the playhead, and scene-animation removal. |
| Cameras | `get_camera`, `get_camera_capabilities`, `set_camera`, `set_camera_transform`, `set_camera_focal_key`, `set_camera_dof`, `remove_camera_dof_keys`, `remove_camera_focal_keys`, `set_current_camera`, `set_camera_look_at` | Inspect and animate cameras, set focal length, clipping, depth of field, the active camera, and object tracking. |
| Materials | `get_materials`, `set_material_color`, `set_material_color_channel`, `set_material_texture`, `set_texture_weight`, `set_uv_data`, `load_video_texture`, `set_material_value`, `set_material_attribute` | Inspect materials, animate color channels/UVs/texture weights, load video textures, and change documented tessellation attributes. |
| Lights | `get_light`, `set_light` | Inspect and change activation, color, intensity, range, shadows, spot beam, IES, and rectangular/tube light settings. |
| Avatars | `get_avatar_info`, `get_avatar_capabilities`, `get_skin_bones`, `get_animation_clips`, `set_clip_speed`, `set_clip_loop_count` | Inspect avatars, bones, components, and clips, then set clip speed and looping. Measured on 8.75 (hoodtronik fork): `RIClip.SetLoopCount` does not exist, so `set_clip_loop_count` raises; extend a clip with `SetLength` (see `walk_to`) instead. |
| Morphs | `list_morphs`, `get_morph_weight`, `set_morph_weight` | List, read, and animate morph weights on compatible props and avatars. |
| Face and voice | `get_face_info`, `set_auto_blink`, `set_face_expressiveness`, `add_expression_keys`, `get_viseme_info`, `add_viseme_key`, `load_vocal` | Inspect and key documented facial expressions/visemes and load vocal audio; these APIs are experimental and may be limited by the iClone build. |
| Rendering | `get_render_settings`, `render_video` | Read the output resolution and start video rendering after explicit confirmation. |
| Mocap and networking | `get_mocap_status`, `get_network_capabilities` | Diagnose the mocap manager and native TCP/UDP availability. |

These tools can be used to:

- inspect, select, transform, show, and remove scene objects;
- create official iClone primitives, import assets, and save projects;
- control the timeline, cameras, and lights;
- inspect and change materials, colors, texture maps, opacity, glossiness, and self-illumination;
- inspect avatar components, skin bones, animation clips, loop counts, and morphs;
- load or pre-load motions, apply Substance Painter texture folders, and export a single object as FBX;
- inspect the current render size and start a render only after explicit confirmation;
- inspect iClone mocap state and native TCP/UDP availability without opening external connections.

The plugin targets iClone 8 exclusively through its official Python API.


## Expanding beyond the public Python API

This fork has a documented capability-expansion path for operations that iClone can perform in the UI but the current MCP or public RLPy API cannot yet automate.

Read:

- [iClone Automation Archaeology Strategy](docs/hoodtronik/ICLONE_AUTOMATION_ARCHAEOLOGY_STRATEGY.md)
- [iClone Capability Gap Matrix](docs/hoodtronik/ICLONE_CAPABILITY_GAP_MATRIX.md)
- [iClone 8 Agent Reference](docs/hoodtronik/ICLONE8_AGENT_REFERENCE.md)
- [Measured automation entry points](docs/hoodtronik/automation-entry-points.md)

The development ladder is:

```text
official RLPy
    -> installed/local RLPy surface
    -> Qt/UI introspection
    -> targeted native archaeology
    -> version-aware native bridge
    -> MCP tool with runtime proof
```

Agents should work one creator-visible capability at a time, prefer the least invasive route, checkpoint before risky operations, and never treat a successful return value as proof unless the scene/timeline/render actually changed.

The first recommended milestone is a full capability-gap audit: compare the installed `RLPy.py`, official Reallusion docs/samples, and the current MCP registry, then rank the highest-value missing previz operations before attempting native reverse engineering.

First results of that audit (2026-10-07): avatar **Look At** — `set_look_at` makes an avatar look at a prop, camera or another avatar's head bone, with a timed release, and reports the measured head-bone turn as proof — and **in-session project control**: `load_project` opens an `.iProject` without relaunching iClone and `new_project` starts an empty scene; both save the current project first because iClone discards unsaved work without asking — `set_timeline_range` for the project length, play range and preview range in frames or seconds, with read-back, `edit_clip` for break / merge / mirror / delete on a motion track with before/after proof, `load_audio` / `render_audio` to put a sound file on an object's track (proven by rendering the window before and after) and export the mixed scene audio, `set_project_fps`, the first Qt-tier tool: it drives the Project panel's FPS combo because RLPy has no setter, and proves the change by reading the fps back, and `walk_to`, a blocking move that walks an avatar in a straight line between two points using a root-motion walk clip (calibrated on the avatar, chained for long distances, trimmed to arrive) and proves arrival by hip position, `track_target`, which makes a camera or spotlight follow a moving actor over a frame range, `camera_cuts`, which writes multi-camera cuts and switches the view to follow them, `draw_path`, which draws a new path through ground points by projecting them into the viewport and posting clicks to iClone's view window only, `walk_path`, which makes an avatar walk that path facing its direction of travel, `set_burn_in`, which stamps scene/take/timecode/lens/notes onto review renders, `video_plate`, which puts reference footage on a camera-facing plate, `timeline_clip_action`, which runs any Timeline clip right-click command (flatten, smooth, mirror, root motion, time warp, ...), and `convert_external_motion`, which runs iClone's own Convert External Motion flow (auto-detected Mixamo/Rokoko/Xsens profile) on an FBX/BVH and returns the `.rlMotion`. The ranked backlog lives in the gap matrix.

## Example instructions for an agent

Give the agent a clear objective, object names, and numeric values. The agent
can inspect the scene first and then call the appropriate MCP tools.

| Category | Example instruction |
| --- | --- |
| Scene | “List the props in the scene, then select `MCP8_Live_Test_Box`.” |
| Creation | “Create a red box named `Logo_Block` at X=0, Y=0, Z=20, and add a floor beneath it.” |
| Transform | “Move `Logo_Block` to X=200 at frame 120 and scale it to 150%.” |
| Materials | “List the materials on `Logo_Block`, then set material 0 to royal blue and hide its diffuse texture.” |
| Texture maps | “Apply `C:\\Assets\\logo_basecolor.png` as the diffuse texture of material 0 on `Logo_Block`.” |
| Material animation | “At frame 300, set `Logo_Block` material 0 opacity to 0.25 and self-illumination to 0.8.” |
| Timeline | “Set the playhead to frame 0, play frames 0 through 300, then stop.” |
| Camera | “Read the active camera's focal length and set it to 50 mm.” |
| Animation | “Animate `Orbit_Sphere` around `Center_Cube` using transform keys at frames 0, 150, 300, 450, and 600.” |
| Avatar | “List the skin bones and animation clips on avatar `Character1`.” |
| Avatar playback | “Inspect `Character1` capabilities, then set clip 0 to loop three times at 1.2× speed.” |
| Morphs | “List the morphs on `Character1`, then set the specified facial morph to weight 0.5 at the current frame.” |
| Import/export | “Import this `.iProp` file, save the project, then export the selected object as FBX.” |
| Render | “Read the render dimensions. Only when I confirm, render the video using the project’s current iClone settings.” |
| Mocap | “Check whether iClone mocap is running; do not change or connect any device.” |

For a camera follow shot, use a real scene camera rather than the iClone
Preview Camera: “Create or activate `Camera1`, then key its transform at the
same frames as the subject, with a consistent relative offset.”

## Development

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
```

The main technical reference is the official [iClone 8 Python API
documentation](https://wiki.reallusion.com/IC8_Python_API).
