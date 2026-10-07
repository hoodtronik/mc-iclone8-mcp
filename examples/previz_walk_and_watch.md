# Recipe: "she walks the route, he watches, two cameras cut" (hoodtronik fork tools)

Proven end to end on iClone 8.75.5630.1 (2026-10-07) using only MCP tools. Every tool returns its own proof; stop if
any `ok` is false.

| # | Tool call | Proof returned |
| --- | --- | --- |
| 1 | `new_project {}` | tracked project saved first, scene empty |
| 2 | `set_project_fps {"fps": 24}` | fps read back 24, length rescaled |
| 3 | `set_timeline_range {"project_length": 20, "end": 20, "unit": "seconds"}` | frames read back |
| 4 | load avatars (python_exec: `RScene.ClearSelectObjects()` before EACH `RFileIO.LoadFile(...iavatar)`) | both names listed |
| 5 | `place_object` for each avatar (position, heading) | position read back |
| 6 | `menu_action "Create > Camera > Linear Camera"` ×2 | cameras listed |
| 7 | `aim_camera` wide camera (high, whole route in frame), `make_current: true` | — |
| 8 | `draw_path {"name": "Route", "points": [...]}` | start/end error ≤ 1 cm, height deviation 0 cm |
| 9 | `walk_path {"avatar": "Party_F_0001", "path": "Route", "start_frame": 24, "speed_cm_s": 120}` | end 0 cm, facing 6°, tilt 0° |
| 10 | `set_look_at {"avatar": "Party_M_0001", "target": "Party_F_0001", "frame": 24, ...}` | head turn degrees |
| 11 | `aim_camera` second camera, then `track_target {"camera": ..., "target": "Party_F_0001", "end_frame": 300}` | aim error 0° |
| 12 | `camera_cuts {"cuts": [{"frame": 0, "camera": "Camera"}, {"frame": 96, "camera": "Camera_0"}, {"frame": 200, "camera": "Camera"}]}` | live camera per shot |
| 13 | `render_snapshot` one frame per shot (or `render_video`) | files written |

Traps this recipe avoids (details in `docs/hoodtronik/ICLONE8_AGENT_REFERENCE.md` §8):
- Loading an `.iavatar` while another avatar is selected REPLACES that avatar instead of adding one.
- `draw_path` needs every point visible in the current view camera; it hides props/avatars while clicking.
- Cuts only show in renders once the toolbar camera list is on "Switch" (`camera_cuts` does it).
