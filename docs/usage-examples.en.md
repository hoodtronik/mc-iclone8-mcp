# iClone 8 MCP usage examples

Each prompt below tells the agent what to inspect before changing the scene. Use exact names returned by `list_objects`; do not assume that `Preview Camera` can be animated.

## Diagnostics and scene inspection

Prerequisites: iClone 8 is open, the plugin is loaded, and the MCP server shows `http://127.0.0.1:8766/mcp`.

Prompt:

> Check the MCP connection and iClone 8 API version. Then list cameras, props, avatars, lights, and paths without modifying the scene.

## Primitives and layout

Prerequisites: an open project; choose a clear area or explicitly provide the origin and units.

Prompt:

> Inspect the scene first. Create a box named `Test_Box` at `(0, 0, 50)`, scale it to `(100, 100, 100)`, create a floor below it, and verify the names, bounds, and transforms. Do not delete existing objects.

## Materials and textures

Prerequisites: the target object exists and `get_materials` can identify its material index; texture paths must be local files.

Prompt:

> Find the exact prop named `Test_Box`, list its materials, set material 0 diffuse color to red `(1, 0, 0)`, keep the texture visible unless it prevents the color from showing, then read the material back to verify the result.

## Lights

Prerequisites: at least one compatible light exists; provide its exact name and avoid changing unrelated lights.

Prompt:

> List the scene lights and inspect `Key_Light`. Increase its intensity to 2.0, set a warm color, enable shadows, and verify the resulting light properties. Do not create a new light.

## Cameras and filming

Prerequisites: a real scene camera such as `Camera1`; the subject name and frame range are required.

Prompt:

> Inspect `Camera1` and `Orbit_Sphere`. Animate the camera at frames 0, 300, and 600 with a smooth relative offset, aim it at the sphere at each key, make `Camera1` the active camera, and verify the camera keys. Do not use `Preview Camera`.

## Object animation and paths

Prerequisites: the object exists; an iClone path must already exist because public Python API does not reliably create or edit path curve points.

Prompt:

> First remove only the object transform animation from `Orbit_Sphere` while preserving its current position. Then inspect existing paths, follow the path named `Orbit_Path` from frame 0 to 600, and verify representative transforms at frames 0, 300, and 600.

## Avatars, expressions, and voice

Prerequisites: a compatible avatar exists; for vocal loading, provide a local WAV/MP3 path. Native motion files are preferred for body movement.

Prompt:

> Inspect avatar `Eddy` to confirm it has face and viseme components. Keep its current anchor position, enable auto blink, add a neutral-to-smile expression sequence from frames 0 to 120, and report any unsupported facial API operation instead of inventing a fallback.

## Import, export, and project saving

Prerequisites: source files exist locally and the destination folder already exists. Export operations are experimental in the official API.

Prompt:

> Verify that `C:\\Assets\\chair.iProp` exists, import it, report the newly created object name and bounds, save the current project to `C:\\Projects\\shot.iProject`, and export the imported object as FBX to `C:\\Exports\\chair.fbx`. Do not overwrite an existing file without confirmation.

## Rendering

Prerequisites: an active real camera, a configured project, and an explicit output path. Rendering changes external files and requires confirmation.

Prompt:

> Read the render settings and active camera, report the frame range and output resolution, and wait for my confirmation before rendering to `C:\\Renders\\shot.mp4`.

## Important limitations

- The plugin targets iClone 8 only; no iClone 7 motion-bone API is used.
- Path creation and curve-point editing are not exposed reliably by the public Python API.
- OBJ, GLB, Alembic, facial/viseme, and several light/material operations are experimental and must be verified in the installed iClone build.
- Mesh vertex/edge/face editing, arbitrary parent attachment, and native physics/path constraint authoring are not exposed as reliable public operations.
