# iClone 8 Previz Field Guide (NotebookLM-generated)

<!-- CLAUDE-NOTE: Generated 2026-09-26 by querying the NotebookLM notebook below. Answers are NotebookLM syntheses of Reallusion's official tutorials + manual; bracketed [n] numbers map to the per-section "Sources cited" list. Verify against the live iClone UI / RLPy before hard-coding behavior. -->

- **Notebook:** "iClone 8 Previz Tutorials (Reallusion)" - https://notebooklm.google.com/notebook/c9c835c3-abb0-4332-be2c-8b7dbf4a683f
- **Notebook id:** `c9c835c3-abb0-4332-be2c-8b7dbf4a683f`
- **Sources:** 62 ready (YouTube tutorial transcripts from youtube.com/@Reallusion + iClone 8 online manual pages + IC8 Python API wiki + ComfyUI-Reallusion GitHub). Note: many camera/DOF/link tutorials are iClone 7.x-era but the features carry over to iClone 8.
- **Query it:** `nlm notebook query c9c835c3-abb0-4332-be2c-8b7dbf4a683f "<question>"` or MCP `notebook_query`.


---

## (a) Hand grabs / reaches another character's wrist or a prop

**Question asked:** Practical step-by-step in iClone 8: how do I make one character's hand grab or reach another character's wrist, or a prop, and keep it there while things move? Cover Reach Target panel (targets, effector dummies, reach/release keys, offsets, lock joints), Edit Motion Layer / IK effectors and pinning, and linking/attaching props to a hand (Link To / Attach). Include exact panel/button names, gotchas, and which sources say it.

To make one character's hand reach or grab another character's wrist (or a prop) and hold onto it dynamically as either subject moves, iClone 8 provides three complementary tools: the **Reach Target Panel**, the **Edit Motion Layer Panel** (with IK/FK modes and Pinning), and **Linking / Attaching** [1-3].

---

### Step-by-Step Guide: Hand Grabbing a Wrist or Prop

#### Method 1: The Reach Target Panel (Recommended for Dynamic Character-to-Character & Object Contact)
The **Reach Target** tool dynamically constrains a limb effector (such as a hand) to follow a target object or bone node on another character while driving Inverse Kinematics (IK) automatically [1, 4, 5].

1. **Navigate to the Contact Frame**:
   - Scrub the timeline to the exact frame where the grab or reach begins [5, 6].
2. **Open the Reach Target Panel**:
   - Select the reaching character in the viewport [5].
   - Go to the **Modify** panel >> **Animation** tab >> click **Edit Reach Target** [1, 2, 5].
3. **Select the Effector Point**:
   - On the human pictogram inside the Reach Target panel, click the effector node corresponding to the reaching hand (e.g., **Right Hand** or **Left Hand**) [1, 5, 7].
4. **Establish Target Selection**:
   - **To maintain current hand placement**: Click **Select Target and Keep Current Pose** (Maintain Object Offset) [1, 2, 7, 8]. This prevents the hand from snapping awkwardly to the target's origin pivot and maintains its exact visual offset [1, 8].
   - **To snap directly to a target**: Click **Select Target**, then click the target in the 3D viewport [5].
   - **Selecting a specific bone (e.g., wrist)**: Next to the Reach Target field, click the **ellipses button (...)** to open the target character's full bone hierarchy, then select the specific wrist or arm bone [8].
5. **Adjust Reach Offsets**:
   - Move or rotate the hand using the viewport transform gizmos [1, 7]. The **Reach Offset** values in the panel will update simultaneously to keep the grasp natural [1, 7].
6. **Set Reach/Release Keys & Transitions**:
   - Advance down the timeline to the point where the character should let go [5, 9, 10].
   - Click **Release** in the Reach Target panel [5, 7, 9, 10].
   - Open the **Timeline** (`F3`) and expand the character's **Reach Track** [9, 11].
   - **Transition Keys**: You will see triangle keys (marking the start/end of the reach) and extending rectangle gizmos (marking transition duration) [9, 12]. Drag the rectangle transition keys closer or further apart to lengthen or shorten the blend, preventing abrupt snaps or limb twisting [9, 10, 12].
7. **Using Effector Dummies**:
   - Click **Create Dummy** in the Reach Target panel to spawn a dummy mesh/gizmo at the hand effector [13]. Animating or attaching this dummy gizmo to props or scene elements drives complex character body motions [13, 14].
8. **Locking Joints**:
   - Click **Lock to Origin** to keep un-reaching joints (such as feet or non-reaching limbs) locked to their original position or grounded while the rest of the body moves [7, 15, 16].

---

#### Method 2: Edit Motion Layer Panel & IK Pinning (Best for Fixed World Locks or Surface Anchoring)
When you need to adjust or lock hand placement relative to world space or fixed body poses, use the **Edit Motion Layer** panel [17-19].

1. **Access the Panel**:
   - Select the character, then go to the **Modify** panel >> **Animation** tab >> **Edit Motion Layer** (or press shortcut `3` or `N`) [20, 21].
2. **IK vs. FK Modes**:
   - **IK Mode (Inverse Kinematics)**: Highlighted in blue [22]. Moving the hand effector drives parent joints (forearm, shoulder, torso) automatically while keeping the hand anchored [22, 23].
   - **FK Mode (Forward Kinematics)**: Highlighted in grey [22]. Rotating parent bones moves child bones down the chain [24, 25]. Use FK mode when you need to make rotation tweaks without triggering the IK floor detection or effector solver [26].
3. **Pinning Effectors (World Space Lock)**:
   - In the dummy pictogram, click the lock icon beside the hand effector [19]. 
   - Enabling **T** (Transform/Move) and **R** (Rotation) pins that hand firmly in 3D world space [19]. 
   - **Presets**: Choose **Pin Both Hands** or **Pin Limbs** at the bottom of the panel [19]. When the torso or hips move, pinned hands remain stationary where locked [18, 19].
4. **Full Body vs. Body Part Keying**:
   - **Full Body**: Generates keyframes across all body sub-tracks in the timeline when an edit is made [27, 28].
   - **Body Part**: Generates keyframes *only* on the selected limb sub-track (e.g., Right Arm) [28, 29]. Always switch to **Body Part mode** when fine-tuning a single hand or wrist to prevent setting excessive keys across unaffected body tracks [28-31].

---

#### Method 3: Linking vs. Attaching Props & Characters (`Link To` vs. `Attach`)
To make a character pick up, hold, or drop a prop, or carry another character (such as a puppet), you must understand the distinction between **Link To** and **Attach** [3, 32, 33].

| Feature | **Link To** (Linkage Section) [3, 32, 34] | **Attach** (Attach Section) [35-37] |
| :--- | :--- | :--- |
| **Location** | **Modify** panel >> **Attributes** tab >> **Linkage** [3, 32, 34] | **Modify** panel >> **Attributes** tab >> **Attach** [35, 36] |
| **Keyable / Animatable** | **Yes** (Shown in green text in UI; keyable on Timeline **Link track**) [38] | **No** (Shown in white text; static permanent hierarchy change) [36, 37] |
| **Pickup / Release** | **Yes**: Click `Link To` / `Pick Parent` at grab frame; click `Unlink` at drop frame [32, 34, 38, 39]. | **No**: Cannot be unlinked or detached mid-scene [32, 37]. |
| **Scaling Behavior** | Parent move/rotation affects child, but parent scale **does NOT** scale child [38]. | Child **scales automatically** along with parent scaling [36, 40]. |
| **Use Case** | Grabbing/throwing props, dynamic character-to-character pickup [32, 34, 41]. | Permanent accessories, clothing, attached gear [35, 42, 43]. |

- **Baking Constraint Animation**: Once a prop or limb is linked/constrained across a shot, go to the top **Animation** menu and select **Flatten All Motion with Constraints** to bake all link/reach relationships into a single clean motion clip [32, 44-46].

---

### Critical Gotchas & Troubleshooting

1. **Pre-existing Mocap/Video Mocap Finger Keys Overriding Gestures**:
   - *Issue*: You set a custom hand grip, but upon playback, the fingers snap back to their default state [35].
   - *Fix*: Open the **Animation Layer Panel** (`F11`), select the **Base Motion** layer, unlock it, select all pre-existing finger keyframes, and **delete them** so your custom gesture takes priority [2, 35, 47].
2. **Abrupt Snapping or Bone Twisting during Release**:
   - *Issue*: Limb snaps or flips unnaturally when the reach ends [9, 12].
   - *Fix*: Select the release key in the **Reach track** on the Timeline and drag the rectangle **Transition End** key closer or further to adjust the transition duration [9, 12].
3. **Prop Won't Detach / Drop**:
   - *Issue*: Clicking detach doesn't release a prop [32, 37].
   - *Fix*: You used **Attach** instead of **Link To** [32, 37]. Re-parent the prop using **Linkage >> Link To** so keyframes appear on the Timeline's **Link track** [32, 34, 38].
4. **Pinning Doesn't Auto-Create Timeline Keys**:
   - *Issue*: Enabling `T`/`R` locks pins the hand in the viewport, but no key is placed on the timeline [26].
   - *Fix*: Pinning assists viewport pose editing [26]. You must transform a bone or click **Set Key** to store the transform keyframe on the timeline [31, 48].

---

### Source & Tutorial Mapping Reference

- **Reach Target Panel, Target Selection, & Transitions**: *"How to Use Reach Target for Different Scenarios for Interactive 3D Animation"* [86–91], *"iClone 8 Online Manual - Introducing Reach Target Panel / Using the Reach Target Panel"* [5, 7, 12].
- **Effector Dummies & Offset Fixes**: *"iClone 8 Online Manual - How to create body motions with effector dummies"* [13], *"Mocap Motion Fix - Holding Accessories with 2 Hands"* [112–114], *"Ways to Maintain Target Reach Offset for Object Movement"* [49].
- **Edit Motion Layer, IK/FK, & Pinning**: *"How to Edit Different 3D Motions in the Same Motion Clip"* [57–66], *"How to Empower your 3D Animation Workspace with FK/IK Modes"* [72–74], *"iClone 8 Online Manual - How to use Edit Motion Layer panel / How to Use IK"* [163, 170–171].
- **Link To vs. Attach & Flattening Constraints**: *"iClone 7 Basics Tutorial - Linking and Attaching"* [139–148], *"Making Character Interaction with Scenes and Props Possible"* [32], *"iClone Tutorial - Character 'Link to' Character"* [197–200], *"Using reach target to animate hammering and sawing"* [46, 50].

---

Would you like to explore setting up a **Curve Editor** workflow for smoothing the reach transition curves, or setting up physics-based object releases?

### Sources cited

- [1, 4, 8, 9, 10] How to Use Reach Target for Different Scenarios for Interactive 3D Animation | iClone 8 Tutorial
- [2, 6, 35, 47] Mocap Motion Fix - Holding Accessories with 2 Hands | iClone 8 Tutorial
- [3, 36, 37, 38, 40, 42, 43] iClone 7 Basics Tutorial - Linking and Attaching
- [5, 12] iClone 8 Online Manual - Using the Reach Target Panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Reach_Target/Using_the_Reach_Target_Panel.htm
- [7] iClone 8 Online Manual - Introducing Reach Target Panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Reach_Target/Introducing_the_Reach_Target_Panel.htm
- [11] How to Correct Footsteps & Hand Positions for 3D Motion Design | iClone 8 Tutorial
- [13] iClone 8 Online Manual - How to create body motions with effector dummies - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Reach_Target/Creating_Body_Motions_with_Effector.htm
- [14, 15] Advanced Look-At Driven Animation | iClone 8 Tutorial
- [16, 45] Using Puppet Tool to animate rifle fire kickback | Mocap Animation Course | iClone 8
- [17] Getting Start with iClone 8 - Easy Character Animation Workflow | iClone 8 Tutorial
- [18, 19, 20, 23, 24, 25] How to Edit Different 3D Motions in the Same Motion Clip | iClone 8 Tutorial
- [21, 28] iClone 8 Online Manual - How to use Edit Motion Layer panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Motion-Layer/Using_Body_Key_Editor.htm
- [22, 27, 29] How to Empower your 3D Animation Workspace with FK/IK Modes | Mocap Animation Course | iClone 8
- [26, 44, 48] How to adjust contact points for climbing and falling motions | Mocap Animation Course | iClone 8
- [30] How to tailor time curves on motion clips for impactful motions | Mocap Animation Course | iClone 8
- [31] Motion Clip Editing & Basic Timeline Features | iClone 8 Tutorial
- [32] Making Character Interaction with Scenes and Props Possible | Mocap Animation Course | iClone 8
- [33, 41] iClone Tutorial - Character "Link to" Character
- [34, 39] How to Throw Objects with Physics to Create 3D Animation | 3D Mocap Animation Course | iClone 8
- [46, 50] Using reach target to animate hammering and sawing | Mocap animation course | iClone 8
- [49] Ways to Maintain Target Reach Offset for Object Movement | Mocap Animation Course | iClone 8

---

## (b) Keying cameras and camera switching for multi-shot sequences

**Question asked:** Practical step-by-step in iClone 8 for multi-shot previz: how do I create cameras, key camera position/rotation/lens (focal length) over time, animate DOF focus, use camera Look At, and cut between several cameras over the sequence using the Camera Switcher / Switcher track on the Project track? Include exact panel/button/track names, how to preview/render through the switcher, and gotchas.

Here is a complete step-by-step workflow in **iClone 8** for setting up multi-shot camera previz, keyframing lens parameters, animating Depth of Field (DOF), configuring Look At tracking, and cutting shots on the Camera Switcher track.

---

### Step 1: Creating and Managing Custom Cameras
In iClone, the **Preview Camera** is non-recordable and intended for free viewport navigation without leaving unwanted keyframes [1]. For previz, you must create dedicated custom cameras.

1. **Create Custom Cameras**:
   - Go to the top menu: **Create** >> **Camera** >> choose **Linear Camera** or **Orbit Camera** [1, 2].
   - *Alternative*: Open **Content Manager** >> **Stage** tab >> **Camera** library, and double-click a preset template [3, 4].
2. **Rename Cameras**:
   - Open the **Scene Manager**, double-click each new camera, and give it a clear shot name (e.g., `Cam_Wide`, `Cam_OverShoulder`, `Cam_CloseUp`) [1, 3].
3. **Viewport Viewport & Hotkeys**:
   - Switch between cameras using the **Camera List** dropdown at the top of the 3D viewport toolbar [1, 4] (or press hotkey `U` to toggle between the last selected object and camera) [1].
   - **Navigation Shortcuts**: Hold `Alt` + **Left Mouse Button (LMB)** to Pan; `Alt` + **Right Mouse Button (RMB)** to Orbit; `Alt` + **Both Mouse Buttons** (or scroll wheel) to Zoom [5]. Hold `Shift` with any tool to accelerate movement speed [78–79].

---

### Step 2: Keyframing Position, Rotation, & Focal Length (Lensing)
Camera movements and focal length changes auto-keyframe on the timeline whenever adjusted at a non-zero timecode [6, 7].

1. **Position & Rotation Keyframing**:
   - Select your custom camera from the viewport dropdown list [4, 7].
   - Open the **Timeline** (`F3`) and scrub the playhead to your desired frame [7, 8].
   - Transform the camera in the viewport using movement gizmos (`W` to move, `E` to rotate) [7, 9, 10]. A keyframe will automatically appear on the camera’s **Transform** track [6, 7].
   - *Tip*: Right-click between transform keyframes to apply **Transition Curves** (e.g., *Ease In/Ease Out*, *Accelerate*, *Decelerate*) to smooth or stylize camera moves [11].
2. **Keyframing Focal Length / Angle of View**:
   - Select the camera and open the **Modify** panel >> **Camera** section [80–81].
   - **Lens Presets**: Click any quick-select lens button (e.g., `20mm`, `35mm`, `50mm`, `80mm`, `105mm`) [1, 12].
   - **Custom Lensing**: Pull the **Focal Length** slider or **Angle of View** slider to manually adjust the lens FOV [12, 13].
   - Adjusting these sliders at different frames automatically writes keyframes to the camera’s timeline track [6, 7].

---

### Step 3: Depth of Field (DOF) & Rack Focus Animation
Depth of field directs the viewer's attention by blurring foreground and background elements around a sharp focus plane [14, 15].

1. **Activate DOF**:
   - Select your camera -> **Modify** panel >> **Camera** section >> **Depth of Field** group -> check **Activate** [13, 16, 17].
2. **Set Focal Distance**:
   - **Pick Target**: Click the **Pick Target** button, then click on a character or object in the 3D viewport [13, 16-18].
   - **Manual Distance**: Drag the **Focus Distance** slider for fine adjustments [17-19].
3. **Visualize Focus Planes**:
   - Click **View DOF Regions** [13, 20, 21]. The viewport highlights focus zones in color:
     - **Red**: Sharp in-focus region (*Perfect Focus Range*) [13, 14, 22].
     - **Blue**: Near blur region [14, 22].
     - **Green**: Far blur region [14, 22].
     - **Purple / Orange**: Transition blending regions [22, 23].
4. **Refine Focus Range & Blurring**:
   - Adjust **Focus Range** (or **Perfect Focus Range**) to widen or narrow the sharp area [19, 20, 24].
   - Tweak **Near Blur** / **Far Blur** and **Near Transition** / **Far Transition** sliders for realistic camera optical falloff [119, 122–123].
5. **Animating a Rack Focus**:
   - Open the **Timeline** (`F3`), select your camera, click **Track List** >> expand sub-tracks >> enable the **Depth of Field** sub-track [25].
   - Move the playhead to Frame A -> click **Pick Target** on Subject 1 [18, 26].
   - Move the playhead to Frame B -> click **Pick Target** on Subject 2 [18, 26]. iClone generates smooth rack-focus keyframes between Frame A and Frame B [24, 26, 27].

---

### Step 4: Camera Look At Constraint (Target Tracking)
Instead of manually keyframing complex camera panning to follow moving characters, assign a **Look At** constraint [28].

1. **Assign Look At Target**:
   - Select your camera in the **Scene Manager** or viewport [28].
   - Go to **Modify** panel >> **Look At** section -> click **Pick Target** [28, 29].
   - In the 3D viewport, click the character or object the camera should track [28, 29].
   - Now, as the subject moves across the timeline, the camera automatically rotates to keep them centered in the frame [28, 30].
2. **Time Range & Release**:
   - To have the camera follow a target only during a specific time window, set the target at the start frame, and click **Set Free** at the frame where tracking should stop [28].
3. **Smooth Dolly Shot Trick (Look At Dummy)**:
   - For ultra-smooth tracking shots, create a simple Primitive/Dummy prop (or helper object) [31-33].
   - Set the camera to **Look At** the dummy object, then animate the dummy along a path or timeline. This eliminates camera rotational jitter [32].

---

### Step 5: Multi-Shot Sequence Cuts via Camera Switcher
To sequence cuts between multiple cameras across your timeline, use the **Switcher** track on the **Project** track [2, 16, 34, 35].

1. **Set Up the Workspace & Mini Viewport**:
   - Switch workspace to **Animation** (`Ctrl + 3`) or **Standard** [36, 37].
   - Press `F8` to toggle the **Mini Viewport** [34, 38]. Set the Mini Viewport to view your active cut sequence or individual cameras while editing [34].
2. **Open the Switcher Track**:
   - Open the **Timeline** (`F3`) [7, 8].
   - On the top-left of the Timeline, click the **Track List** menu button -> expand **Project** -> check **Switcher** [2, 16, 34, 35].
3. **Add Camera Cut Keys**:
   - Move the Timeline playhead to the frame where Shot 1 starts [2, 34].
   - Right-click on the **Switcher** track at that frame -> select your first camera (e.g., `Cam_Wide`) from the context menu [2, 34, 39].
   - Scrub to the frame for Shot 2 -> right-click on the **Switcher** track -> select `Cam_OverShoulder` [2, 34, 39].
   - Repeat across the sequence. Colored block markers appear on the Switcher track indicating active camera spans [2, 34, 39]. You can drag these key blocks to adjust cut timing [34, 39].
4. **Enable Viewport Switcher Mode**:
   - Go to the top viewport toolbar camera selection dropdown and select **Switch** [2, 16, 34].
   - Press `Spacebar` to play back. The main 3D viewport will now dynamically cut between your cameras in real time [84–85, 159]!

---

### Step 6: Previewing & Rendering the Previz Sequence

1. **Pre-Render Checklist**:
   - Ensure the camera selector dropdown above the 3D viewer is set to **Switch** [2, 16, 34].
   - Verify physical camera dummies in the viewport are hidden in the **Scene Manager** so they don't render [40, 41].
2. **Configure Render Settings**:
   - Go to top menu **Render** >> **Render Video** (or click the **Render** icon on the Project Toolbar) [42-44].
   - **Format**: Select **MP4 (H.264)** or **AVI** [42, 44].
   - **Frame Rate**: Set to `24`, `30`, or `60 FPS` [42, 44].
   - **Quality**: Select **Final Render** mode to enable hardware Anti-aliasing for clean geometry edges [42].
   - **Depth of Field Check**: In the Render panel options, ensure the **Activate Depth of Field** checkbox is checked so real-time DOF renders into the video file [42].
   - **Output Range**: Set to **All** or define specific frame markers using **Range** (**Mark-In** / **Mark-Out**) [43-45].
   - Click **Export** to render out your multi-shot previz video [42].

---

### Critical Gotchas & Troubleshooting

1. **Accidental Camera Keyframes**:
   - *Issue*: Orbiting or panning in the viewport while viewing a custom camera at frame 50 creates unintended movement keyframes.
   - *Fix*: Always switch back to the **Preview Camera** when freely inspecting or setting up scene props [1]. If unintended keys are set, right-click the camera in the timeline or Modify panel and select **Remove Animation** [10].
2. **Pick Target Focus Distance Doesn't Dynamic-Track**:
   - *Issue*: Clicking `Pick Target` sets the numeric focus distance for that single frame; if the character walks away, they go out of focus [17].
   - *Fix*: You must re-pick the target at subsequent keyframes along the timeline to create a focus tracking animation [129–131, 147].
3. **Viewport Switcher Render Failures**:
   - *Issue*: Final render outputs only Shot 1 instead of cutting between cameras.
   - *Fix*: Ensure the viewport camera selection dropdown is explicitly toggled to **Switch** (not set to `Cam_01` or `Preview`) before clicking Export in the Render Panel [2, 16, 34].
4. **DOF Edge Artifacts / Jagged Foreground Objects**:
   - *Issue*: Foreground objects in focus exhibit sharp or harsh edge bleeding against blurred backgrounds [13, 46].
   - *Fix*: In the camera Modify panel, check **Ignore Background** [13]. For higher quality edge blending, enable **Soften Edge / Blur Edge Sample Scale** under **Preferences** [47]. *(Note: keep this off during rough blocking as it increases GPU rendering overhead, but enable it for final exports)* [125–126].

---

### Source Citation Mapping

- **Camera Creation, Hotkeys, & Lensing**: *"Intro to Cameras"* [78–82], *"iClone 7 Tutorial - Real Camera System"* [110–112], *"iClone 8 Online Manual - Creating and Manipulating Custom Camera"* [4].
- **Depth of Field (DOF) Setup, Rack Focus, & Visualizers**: *"Getting Start with iClone 8"* [16, 42], *"Intro to Cameras"* [13], *"iClone 7.1 Tutorial - Depth of Field Basic Intro / How to Focus / Animation"* [117–125, 128–131], *"iClone 8 Online Manual - DOF"* [146–147].
- **Look At Target Constraints & Smooth Track Dummies**: *"Advanced Look-At Driven Animation"* [29, 31], *"Getting Started with Look-At Driven Animation"* [25–26], *"How To Create Fast Camera Blocking..."* [32], *"iClone 8 Online Manual - Camera - Look At"* [28].
- **Camera Switcher Track, Mini Viewport, & Rendering**: *"Getting Start with iClone 8"* [21–24], *"Intro to Cameras"* [83–85], *"iClone 8 Online Manual - Multiple Camera Switcher / Project Level Tracks / Render Panel"* [2, 35, 43, 44].

---

Would you like to explore setting up **Camera Path Animation** (constraining cameras to move along bezier curves) or exporting camera data via FBX to external software like Maya or Unreal Engine?

### Sources cited

- [1, 5, 7, 13, 34, 40] Intro to Cameras
- [2] iClone 8 Online Manual - Multiple Camera Switcher - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/20-Scene/Camera/Multiple_Camera_Switcher.htm
- [3, 12, 41] iClone 7 Tutorial - Real Camera System
- [4] iClone 8 Online Manual - Creating and Manipulating Custom Camera - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/20-Scene/Camera/Creating_and_Manipulating_Custom_Camera.htm
- [6, 8, 16, 36, 39, 42, 45] Getting Start with iClone 8 - Easy Character Animation Workflow | iClone 8 Tutorial
- [9, 10, 32] How To Create Fast Camera Blocking for Previsualization Using iClone With Shot Designer
- [11] iClone 7 Tutorial - Timeline: Transition Curves
- [14, 18, 19, 20, 22, 23, 46, 47] iClone 7.1 Tutorial - DOF Basic Intro
- [15, 21, 25, 26] iClone 7.1 Tutorial - Depth of Field Animation
- [17, 24] iClone 8 Online Manual - DOF - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/20-Scene/Camera/DOF.htm
- [27] iClone 7.1 Tutorial - Depth of Field - How to Focus
- [28] iClone 8 Online Manual - Camera - Look At - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/54-Look-At/Camera_Look_At.htm
- [29, 31] Advanced Look-At Driven Animation | iClone 8 Tutorial
- [30] Getting Started with Look-At Driven Animation | iClone 8 Tutorial
- [33] Mastering the look-at constraint for gear shifting animation | Mocap Animation Training | iClone 8
- [35] iClone 8 Online Manual - Project Level Tracks - https://manual.reallusion.com/iclone-8/content/enu/8.0/51-animation-timeline-editing/Project_Level_Tracks.htm
- [37] How to Empower your 3D Animation Workspace with FK/IK Modes | Mocap Animation Course | iClone 8
- [38] iClone 8 Online Manual - Timeline Operation - Basic - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/51-Animation-Timeline-Editing/Timeline-Operation-Basic.htm
- [43] iClone 8 Online Manual - Render Panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/03-Introducing-the-User-Interface/Render_Panel.htm
- [44] iClone 8 Online Manual - Rendering - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/80-Export/Exporting.htm

---

## (c) Blending / chaining motion clips on one character and trimming

**Question asked:** Practical step-by-step in iClone 8: how do I chain several motion clips on one character's timeline, blend/transition between them (transition curves, blend length, bidirectional blending, auto motion alignment, align to previous clip), trim/break/split clips, change clip speed, loop a clip, and layer corrections on top (Edit Motion Layer, animation layers). Exact names and gotchas.

### Part 1: Timeline Motion Editing, Chaining, Blending, & Layering

#### 1. Chaining Clips & Motion Alignment
When chaining multiple motion clips on one character, iClone 8 provides automated and manual alignment tools to prevent unnatural pops or foot sliding [1, 2].

* **Applying Sequential Clips**:
  * Apply clips consecutively from the Content Manager or Smart Gallery [2]. By default, **Autoplay Motion Clip** places the playhead at the end of the previous clip so subsequent motions attach seamlessly [3].
* **Auto Motion Alignment**:
  * Access via the Timeline toolbar button or **Animation** menu >> **Auto Motion Alignment** [2, 4].
  * **Align Position and Direction** *(Default)*: Inherits both the end 3D position and rotation angle of the previous clip [2].
  * **Align Position Only**: Keeps the end position from the previous clip but strips varying rotation variables, forcing the sequence into a straight line [62–63].
  * **No Alignment**: Plays raw motion data from its original world coordinate offsets [5].
* **Align to Previous Clip / Align to Part**:
  * Right-click the clip on the timeline >> select **Align** [6, 7].
  * Choose **Align Direction to Previous Clip** and set the alignment reference bone (e.g., **Left Foot**, **Left Toe**, or **Root**) [6, 7]. Aligning to the foot planted on the ground at the transition frame eliminates foot sliding during direction changes or climbing steps [6, 7].
* **Motion Direction Control**:
  * Right-click the clip >> select **Motion Direction Control** (or click the Motion Direction Control toolbar icon) [4, 6].
  * Color-coded directional arrows will appear in the viewport matching the timeline clip colors [6]. Rotate these arrows to redirect character movement [6]. Ensure **Align Direction** is set to **Previous Clip** with both **Transform** and **Rotate** enabled so local transformations inherit correctly without affecting global scene transforms [56, 58–59].

---

#### 2. Clip Blending & Transitions

* **Blend Length / Cross Transition**:
  * Click and drag the second clip backward on the timeline so it overlaps the first clip [8, 9]. A white crossed-out transition region will appear representing the blend zone [8, 9].
* **Bidirectional Blending**:
  * Each clip features small triangle gizmos at its corners inside the transition zone [10].
  * **Upper Triangle (First Clip)**: Dragging this earlier initiates the transition into the second clip sooner, establishing the end pose of the first clip earlier [10].
  * **Lower Triangle (Second Clip)**: Dragging this rightward holds the final pose of the first clip longer before blending into the second [51–52].
* **Transition Curve Presets**:
  * Right-click the transition area or motion clip >> select **Transition Curve Presets** [11, 12].
  * Choose from presets such as **Ease In**, **Ease Out**, **Accelerate**, **Decelerate**, **Gain Momentum**, **Elastic End**, or **Damp** to adjust blend acceleration and momentum [53, 129–130].

---

#### 3. Trimming, Splitting (Break), Speed, & Looping

* **Looping Clips**:
  * Enable the **Loop** button on the Timeline toolbar [13, 14]. Click and drag the right edge of a loopable motion clip (like a walk cycle) rightward to tile it [13-15].
* **Changing Clip Speed**:
  * Enable the **Speed** button on the Timeline toolbar (disables Loop mode) [13, 14]. Drag the right edge of the clip leftward to accelerate or rightward to decelerate (speed percentage displays in the clip label) [13, 14].
* **Splitting Clips (Break)**:
  * Place the playhead at the cut frame, select the clip, and click **Break** on the toolbar or press **Ctrl + B** [16, 17].
  * **Break (Ctrl + B)**: Non-destructive split (hidden motion data can be recovered by extending clip bounds) [17].
  * **Break Flatten**: Destructive split (strips data outside the visible clip boundary) [17].
* **Resizing / Trimming Clips**:
  * Enable **Resize Clip** on the timeline toolbar to crop extraneous clip tails without retiming the motion rate [14, 16].

---

#### 4. Layering Corrections (Edit Motion Layer & Animation Layers)

* **Edit Motion Layer Panel**:
  * Go to **Modify** panel >> **Animation** tab >> **Edit Motion Layer** (or press shortcut **3** / **N**) [8, 18, 19].
  * Click **Set Key** on the timeline or move an IK/FK effector in the viewport to set an edit keyframe [18, 20].
  * **Body Part Mode**: Always switch to **Body Part mode** when making isolated limb edits to avoid placing unnecessary keyframes across unaffected body sub-tracks [20, 21].
  * Click **Reset** to restore the selected limb back to the base motion pose at that frame [18, 22].
* **Animation Layer Panel (`F11`)**:
  * Open via **Window** menu >> **Animation Layer** or shortcut **F11** [23, 24].
  * Adds non-destructive correction layers on top of the locked **Base Motion** layer [8, 23].
  * **Merging Layers**: Select multiple layers in the panel and click **Merge** (**Optimized Merge** for key reduction, or **Merge Per Frame** for exact frame fidelity) [25].

---

### Part 2: Sitting, Falling, Stumbling, & Aligning Character to Seats/Props

#### Option Comparison & Workflows

| Method | Best Use Case | Key Features & Steps | Primary Gotchas |
| :--- | :--- | :--- | :--- |
| **MD Props (Motion Director System)** | Interactive sitting, standing, and point-and-click seat navigation [14–15]. | Drag MD Chair prop into viewport [26]. Click chair in Play Mode -> radial menu -> select **Sit on Chair** [27]. Character uses NavMesh to walk over, sit down, and link to prop [27, 28]. | NavMesh must cover the MD prop's position point dummy gizmo, or actor cannot trigger interaction [28]. |
| **Reach Target Panel** | Anchoring hips, hands, or feet to seats, climbing surfaces, or ground during stumbles [29-31]. | Select character -> **Modify** >> **Animation** >> **Edit Reach Target** [29, 32]. Click body node (e.g. Hips or Hand) -> **Select Target and Keep Current Pose** -> click chair/surface [29, 32]. | Hips moving without footnote locks will pull feet off ground unless **Lock to Original** or **Pin Feet** is active [29, 31]. |
| **Edit Motion Layer & Contact Points** | Adjusting impact frames, fall height, and floor contact during falls/stumbles [31, 33, 34]. | Switch Foot IK to **FK mode** [31, 33]. Enable **Foot Contact** and **Hand Contact** in Edit Motion Layer panel [30, 35, 36]. Set Z-height keys for hips and apply **Gain Momentum** transition curves [77–78]. | Always execute **Flatten All Motion with Constraints** before adding manual layer edits over constraint tracks [31, 36, 37]. |
| **Physics (Rigid Body Dynamics)** | Interactive tumbling props or objects falling/bouncing alongside character [66–68, 140–141]. | Set floor to Static / Physics Plane [38, 39]. Set prop to **Kinematic** while held/linked, then keyframe to **Dynamic** at release frame [40, 41]. Adjust mass, friction, elasticity, and initial force [38, 42, 43]. | Physics simulation bakes keys directly into transform tracks; turn off prop physics afterwards if manually editing curves in Curve Editor [39]. |

---

### Part 3: Multi-Shot Previz Camera Setup, Animations, & Camera Switcher

#### Step-by-Step Multi-Camera Previz Workflow

#### 1. Creating & Keying Cameras
1. **Create Custom Cameras**:
   * Go to top menu **Create** >> **Camera** >> select **Linear Camera** or **Orbit Camera** [44, 45].
   * Rename each camera in the **Scene Manager** (e.g., `Cam_Wide`, `Cam_CloseUp`) [44, 46].
2. **Keying Camera Position & Rotation**:
   * Select a custom camera in the viewport dropdown list [44, 46].
   * Open the Timeline (**F3**), move the playhead to a desired frame, and transform the camera in the viewport (or tweak Transform values in **Modify** panel) to automatically set a keyframe in the camera's **Transform** track [87–88].
3. **Setting Focal Length / Lens Presets**:
   * Select the camera -> **Modify** panel >> **Camera** section [44, 47].
   * Choose focal length presets (e.g., 35mm, 50mm, 80mm) or pull the **Focal Length** slider [44, 47].

---

#### 2. Animating Depth of Field (DOF)
1. Select camera -> **Modify** panel >> **Depth of Field** section >> check **Activate** [48-50].
2. Click **Pick Target** and click an actor or object in the viewport to set the **Focus Distance** [48-50].
3. Click **View DOF Regions** to toggle colored focus guides (red = sharp focus, blue = near blur, green = far blur) [49, 51].
4. Open Timeline (**F3**), select the camera, expand its subtracts, and show the **Depth of Field** track [52].
5. Move playhead to subsequent frames and re-click **Pick Target** or adjust **Focus Distance** / **Perfect Focus Range** sliders to keyframe dynamic focus pulls [154–157, 170–171].

---

#### 3. Using Camera Look At Constraint
1. Select camera -> **Modify** panel >> **Look At** section >> click **Pick Target** [53, 54].
2. Click the target character or moving prop in the viewport [54]. The camera will automatically rotate to track the target as it moves [54].
3. To stop tracking, set a keyframe and click **Set Free** on the Look At panel [54].

---

#### 4. Cutting Between Cameras via Camera Switcher
1. Open Timeline (**F3**) -> click the **Track List** (or Track Menu List) icon in the top left of the timeline [45, 55, 56].
2. Expand **Project** main track >> enable the **Switcher** track [45, 55-57].
3. Right-click on frame 1 in the **Switcher** track >> select your starting camera (e.g., `Cam_Wide`) [45, 55, 57].
4. Move playhead to the next cut frame, right-click in the **Switcher** track >> select the next camera (e.g., `Cam_CloseUp`) [45, 55, 57].
5. In the viewport camera dropdown list (top left of viewport), select **Switch** to preview the sequence cuts [45, 55, 57].
6. **Mini Viewport Preview**: Press **F8** to open the Mini Viewport, set Mini Viewport view to **Switch**, and keep the main viewport on **Preview Camera** to tweak scene animation while monitoring cuts simultaneously [55, 58].
7. **Rendering Output**: Open **Render** panel (**Render** >> **Render Video**) [59, 60]. Ensure output camera is set to **Switch** so exported media renders camera cuts from the Switcher track [55, 57].

---

### Critical Gotchas Across Motion & Camera Workflows

1. **Accidental Camera Keying**:
   * *Issue*: Orbiting or panning in the main viewport while a custom camera is selected accidentally overwrites its animation keyframes [44, 46].
   * *Fix*: Always switch the main viewport camera back to **Preview Camera** before freely navigating or orbiting the 3D scene [44].
2. **Camera Dummies Appearing in Viewport**:
   * *Issue*: Physical camera dummy icons clutter viewport previews or screen captures [61].
   * *Fix*: Hide camera objects in the **Scene Manager** or toggle object visibility before rendering [61].
3. **Static Pick Target Focus Decay**:
   * *Issue*: **Pick Target** for DOF sets a static numerical focus distance at that specific frame; it does *not* continuously lock to a moving target automatically [50].
   * *Fix*: Keyframe the **Focus Distance** across multiple frames or re-click **Pick Target** down the timeline as the target moves [155–156, 170].
4. **Resizing Looped Motion Clips**:
   * *Issue*: Using the **Resize Clip** tool on a looped motion clip truncates each successive loop cycle [16].
   * *Fix*: Only use **Resize Clip** on single non-looped motion clips; use **Speed** or **Loop** tools for looped animations [100–101].

---

Would you like to explore setting up custom camera transition curves in the **Curve Editor** for smooth camera dollies, or setting up AI Render workflows for your previz cuts?

### Sources cited

- [1, 6, 9] How to Simplify Character Animation by using Motion Direction Control | iClone 8 Tutorial
- [2, 5, 7, 15] How to Simply Animate Characters? Auto Motion Alignment | iClone 8 Tutorial
- [3, 13, 16, 20] Motion Clip Editing & Basic Timeline Features | iClone 8 Tutorial
- [4, 14, 17] iClone 8 Online Manual - Timeline Operation - Basic - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/51-Animation-Timeline-Editing/Timeline-Operation-Basic.htm
- [8, 10, 11] How to Simplify Character Animation by using Bidirectional Blending | iClone 8 Tutorial
- [12] iClone 7 Tutorial - Timeline: Transition Curves
- [18, 48, 57] Getting Start with iClone 8 - Easy Character Animation Workflow | iClone 8 Tutorial
- [19] iClone 8 Online Manual - How to use Edit Motion Layer panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Motion-Layer/Using_Body_Key_Editor.htm
- [21, 22, 36] How to tailor time curves on motion clips for impactful motions | Mocap Animation Course | iClone 8
- [23, 25] 3D Animation Basics - Nonlinear Motion Editing with Animation Layers | iClone 8 Tutorial
- [24] Using reach target to animate hammering and sawing | Mocap animation course | iClone 8
- [26, 27, 28] Getting Started with MD Props | iClone 8 Tutorial
- [29] Advanced Look-At Driven Animation | iClone 8 Tutorial
- [30, 33, 35] How to Correct Foot and Hand Contact on Mocap Animation | Mocap Animation Course | iClone 8
- [31, 34, 37] How to adjust contact points for climbing and falling motions | Mocap Animation Course | iClone 8
- [32] How to Use Reach Target for Different Scenarios for Interactive 3D Animation | iClone 8 Tutorial
- [38, 40, 41, 42] How to Throw Objects with Physics to Create 3D Animation | 3D Mocap Animation Course | iClone 8
- [39, 43] iClone 7.1 Tutorial - Curve Editor: Physics Animation with Curve Editor Manipulation
- [44, 49, 55, 61] Intro to Cameras
- [45] iClone 8 Online Manual - Multiple Camera Switcher - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/20-Scene/Camera/Multiple_Camera_Switcher.htm
- [46] iClone 8 Online Manual - Creating and Manipulating Custom Camera - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/20-Scene/Camera/Creating_and_Manipulating_Custom_Camera.htm
- [47, 59] iClone 7 Tutorial - Real Camera System
- [50] iClone 8 Online Manual - DOF - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/20-Scene/Camera/DOF.htm
- [51] iClone 7.1 Tutorial - DOF Basic Intro
- [52] iClone 7.1 Tutorial - Depth of Field Animation
- [53] Getting Started with Look-At Driven Animation | iClone 8 Tutorial
- [54] iClone 8 Online Manual - Camera - Look At - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/54-Look-At/Camera_Look_At.htm
- [56] iClone 8 Online Manual - Project Level Tracks - https://manual.reallusion.com/iclone-8/content/enu/8.0/51-animation-timeline-editing/Project_Level_Tracks.htm
- [58] iClone 8 Online Manual - Camera - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/20-Scene/Camera/Camera.htm
- [60] iClone 8 Online Manual - Render Panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/03-Introducing-the-User-Interface/Render_Panel.htm

---

## (d) Making a character fall / sit onto a seat

**Question asked:** In iClone 8, how would I make a character fall, stumble, or sit down onto a seat/chair and stay aligned to it? Compare options found in the sources: Motion Director / MD Props (sit interactions, placement points), Reach Target or effector contact points for hips/feet/hands, Edit Motion Layer adjustments, adjusting contact points for climbing and falling motions, and physics (rigid body, throw objects). Which is most practical and what are the steps and gotchas?

In iClone 8, getting a character to fall, stumble, or sit down on a chair while staying properly aligned involves five main approaches from your sources. Below is a comparison of these options, followed by step-by-step procedures, gotchas, and source references for each.

---

### Comparison & Practical Recommendation

| Method | Best Use Case | Precision & Control | Setup Effort |
| :--- | :--- | :--- | :--- |
| **1. Motion Director / MD Props** | **Standard/Routine Sitting**: Interactive point-and-click sitting/standing. | High (pre-aligned by prop placement point). | **Lowest** (turnkey system). |
| **2. Reach Target / Contact Points** | **Custom Sitting / Hand & Hip Anchoring**: Anchoring hips or hands to chair arms/seat or other characters. | **Highest** (dynamic constraint solver). | Medium (requires setting reach/release keys). |
| **3. Edit Motion Layer & Pinning** | **Pose Fine-Tuning & World Locking**: Grounding feet on the floor while lowering pelvis onto seat. | High (direct bone/IK/FK control). | Medium (frame-by-frame keying). |
| **4. Contact Points for Climbing/Falling** | **Stumbling & Fall Impacts**: High drops, stumble impacts, adding weight/momentum. | High (blends height keys, transition curves & hand prints). | High (requires timing and layer flattening). |
| **5. Physics (Rigid Body)** | **Prop Collisions & Dynamic Throwing**: Falling props, objects bouncing off surfaces. | Low for characters (unpredictable ragdoll alignment). | High tuning required. |

#### **Which is most practical?**
* **For a standard sit action**: **Motion Director with MD Props** is the most practical. The character automatically pathfinds, aligns to the seat’s placement point gizmo, and triggers the sitting state change cleanly [40–42].
* **For a custom stumble, fall, or non-standard sit**: A combination of **Reach Target** (anchoring hips/hands) + **Edit Motion Layer** (pinning feet and enabling foot/hand contact) + **Transition Curves** (adding momentum to the fall) gives complete creative control and prevents body clipping [92–95, 171–178].
* **Physics** is **not practical** for character sitting alignment because rigid body dynamics cannot easily enforce precise character seating postures without clipping or ragdoll instability [160–161].

---

### Detailed Method Breakdown: Steps & Gotchas

#### Method 1: Motion Director & MD Props (Sit Interactions & Placement Points)
MD Props utilize state-change behaviors, trigger ranges, and position dummy gizmos to handle interactive character alignment automatically [40–42].

* **Step-by-Step**:
  1. **Add MD Prop**: Drag a sit-enabled MD Prop (such as an MD bench or chair) from Content Manager (`Props >> MD Props`) into the viewport [1].
  2. **Verify Placement Gizmo**: In the **MD** tab of the **Modify** panel, click **Edit Structure** to view the **Position Point Dummy Gizmo**. Align this gizmo where the character’s hips should rest on the seat [2, 3].
  3. **Generate NavMesh**: Go to `Create >> Nav Mesh`. Ensure the NavMesh covers the area leading up to and including the position dummy gizmo so the character can pathfind to the seat [4].
  4. **Trigger Interaction**: Enter **Motion Director Play Mode**. Mouse over the chair to display the radial menu, and select **Sit on Chair** [5]. The character will navigate to the placement point and execute the sitting animation [5].
  5. **Replace Dummy Mesh**: Right-click and drag your custom chair mesh from Content Manager directly onto the MD Prop thumbnail (or attach it to the parent MD Prop item in Scene Manager) to replace the placeholder mesh without breaking the position gizmo hierarchy [41–42].
* **Gotchas**:
  * **NavMesh Blockade**: If the NavMesh does not reach the position point dummy gizmo, the character will be blocked from triggering the sit action [4].
  * **Replacing Dummy Hierarchy**: Avoid attaching replacement meshes directly to the child sample dummy mesh in Scene Manager; attach them to the parent MD Prop item so you can hide the dummy mesh without hiding your chair [2, 6].

---

#### Method 2: Reach Target Panel (Anchoring Hips, Feet, or Hands)
The Reach Target tool drives IK by constraining specific limb effectors or hips to target objects, specific bones, or dummy gizmos [7-9].

* **Step-by-Step**:
  1. Go to the frame where contact with the chair/seat or stumble surface begins.
  2. Select the character, go to **Modify** panel >> **Animation** tab >> click **Edit Reach Target** [7, 8].
  3. Select the effector node on the pictogram (e.g., **Hip/Pelvis**, **Left Hand**, or **Right Hand**) [7, 8, 10].
  4. Click **Select Target and Keep Current Pose** (Maintain Object Offset) and pick the chair or target object in the viewport. This establishes the constraint without causing the body part to snap awkwardly to the target’s origin pivot [7, 8, 10].
  5. **Adjust Offset**: Use the viewport transform gizmos to adjust the exact position/rotation of the hand or hip relative to the seat [7, 8, 10].
  6. **Release Constraint**: Go forward to the release frame, click **Release** in the Reach Target panel [9, 11].
  7. **Refine Transitions**: Open the **Timeline** (`F3`) and expand the **Reach track**. Click on the reach/release keys and drag the rectangle **Transition End/Start** handles closer or farther to lengthen or shorten the blend duration, preventing popping or limb twisting [166, 334–335].
* **Gotchas**:
  * **Direct Snap vs Offset**: Clicking **Select Target** without using *Keep Current Pose* causes hips or hands to instantly snap directly to the target’s pivot center [7-9].
  * **Joint Twisting on Release**: Abrupt release snapping occurs if transition keys are too short. Drag the rectangle transition handles in the Reach track to smooth the release [11, 12].

---

#### Method 3: Edit Motion Layer & IK Pinning (Fixed Seat / Floor Locks)
Edit Motion Layer uses HumanIK to allow manual pose keyframing, effector pinning, and automatic floor/surface contact detection [92–93, 120, 315–316].

* **Step-by-Step**:
  1. Select the character and press shortcut **`3`** or **`N`** (or go to **Modify** panel >> **Animation** tab >> **Edit Motion Layer**) [13, 14].
  2. **Enable Contact**: Check **Foot Contact** and **Hand Contact** in the Modify panel / Edit Motion Layer panel to prevent limbs from penetrating the floor or seat plane [92–94, 316].
  3. **Pin Feet/Limbs**: Click the lock icon (`T` for Transform, `R` for Rotation) beside the feet in the dummy pictogram (or select the **Pin Limbs** preset at the bottom). This pins the feet firmly in world space [15, 16].
  4. **Lower Pelvis**: Select the **Hip** control point and drag it down onto the seat. Inverse Kinematics (IK) will naturally flex the knees while the feet stay anchored to the floor [126–127, 129].
  5. **Use Body Part Mode**: Switch the mode at the top from *Full Body* to **Body Part** before setting fine keys on the arms/torso. This ensures keys are set only on the modified limb sub-tracks rather than setting redundant keys across every bone in the timeline [139–140, 185, 317].
* **Gotchas**:
  * **Pinning Viewport vs Timeline**: Viewport pinning assists pose editing, but it does *not* automatically save keyframes to the timeline [17]. You must transform a bone or click **Set Key** to store timeline keys [16, 18].
  * **Over-keying**: Editing in *Full Body mode* inserts keys into every body sub-track simultaneously, making later timing adjustments rigid and mechanical [139–141, 185, 317].

---

#### Method 4: Adjusting Contact Points for Climbing, Stumbling, & Falling Motions
When a character stumbles or falls heavily onto a chair or floor, you need to adjust impact timing, height drops, and transition momentum [171–178].

* **Step-by-Step**:
  1. **Height Elevation**: Locate the frame where the stumble or fall begins and set a transform key. Go to the impact frame where the character hits the seat/floor, and lower the Z-axis position [19].
  2. **Transition Curves (Momentum & Weight)**: Right-click the clip or transform key in the timeline and apply transition curve presets such as **Gain Momentum**, **Ease Out**, or **Ease In** to add impact weight and realistic bounce upon landing [145, 177, 264–265].
  3. **Motion Correction Tool**: Right-click the motion clip and select **Motion Correction**. Choose presets like **Hands** or **Feet** and hit **Correct** [97–98, 174]. This automatically places contact prints on collision surfaces using Reach Target constraints [20-22].
  4. **Bake / Flatten Motion**: Once reach targets and contact points are set across clips, go to the top menu: **Animation >> Flatten All Motion with Constraints** to bake all constraints and layers into a single clean motion clip [17, 18, 23].
* **Gotchas**:
  * **IK Floor Detection Interference**: When adjusting severe fall or stumble heights, IK effectors can conflict with floor detection. Temporarily switch foot IK to FK or turn off IK effectors while lowering hip transform positions, then re-enable contact [17, 24, 25].

---

#### Method 5: Physics (Rigid Body Simulation)
Physics uses iClone's rigid body simulation for gravity and bouncing dynamics [26, 27].

* **Step-by-Step**:
  1. Go to **Create >> Physics Plane** to establish a collision floor [26].
  2. Select props (e.g. chair or falling object) and enable **Activate Physics** in the Modify panel >> Physics tab, setting collision state to **Rigid Body** [26, 27].
  3. **Kinematic to Dynamic State Switch**: Set physics to **Kinematic** at frame 1 so animation/linking drives the object. Advance to the exact impact/release frame, and switch state to **Dynamic** so physics takes over [28, 29].
  4. Adjust **Elasticity** (bounce), **Friction**, and **Mass** parameters in the Physics tab to tune collision behavior [26, 27].
* **Gotchas**:
  * **Unsuitable for Seating Alignment**: Pure dynamic physics cannot align a character’s posture accurately to a chair seat. Leaving physics set to *Dynamic* from frame 1 causes objects or ragdolls to fall immediately under gravity before the intended frame [28].

---

### Source Reference Mapping

1. **Motion Director & MD Props**:
   * *"Getting Started with MD Props | iClone 8 Tutorial"* [40–46]
   * *"How to Customize 3D Animation in Seconds: Getting Started with Motion Director | iClone 8 Tutorial"* [103–119]
2. **Reach Target & Effector Targets**:
   * *"How to Use Reach Target for Different Scenarios for Interactive 3D Animation | iClone 8 Tutorial"* [165–170]
   * *"iClone 8 Online Manual - Introducing Reach Target Panel"* / *"Using the Reach Target Panel"* [318, 320, 334–335]
   * *"iClone 8 Online Manual - How to create body motions with effector dummies"* [30]
3. **Edit Motion Layer, IK/FK, & Pinning**:
   * *"How to Edit Different 3D Motions in the Same Motion Clip | iClone 8 Tutorial"* [120–131]
   * *"How to Empower your 3D Animation Workspace with FK/IK Modes | Mocap Animation Course | iClone 8"* [138–140]
   * *"iClone 8 Online Manual - How to use Edit Motion Layer panel"* / *"How to Use IK"* [309, 315–317]
4. **Climbing/Falling Contact Points & Motion Correction**:
   * *"How to adjust contact points for climbing and falling motions | Mocap Animation Course | iClone 8"* [171–179]
   * *"How to Correct Foot and Hand Contact on Mocap Animation | Mocap Animation Course | iClone 8"* [92–95]
   * *"How to Correct Footsteps & Hand Positions for 3D Motion Design | iClone 8 Tutorial"* [97–102]
   * *"iClone 7 Tutorial - Timeline: Transition Curves"* [263–265]
5. **Physics (Rigid Body & Constraints)**:
   * *"How to Throw Objects with Physics to Create 3D Animation | 3D Mocap Animation Course | iClone 8"* [159–163]
   * *"iClone 7.1 Tutorial - Curve Editor: Physics Animation with Curve Editor Manipulation"* [278–280]

---

Would you like to explore using the **Curve Editor** to fine-tune the acceleration and bounce curves on a stumble or fall animation?

### Sources cited

- [1, 2, 3, 4, 5, 6] Getting Started with MD Props | iClone 8 Tutorial
- [7] Advanced Look-At Driven Animation | iClone 8 Tutorial
- [8, 11] How to Use Reach Target for Different Scenarios for Interactive 3D Animation | iClone 8 Tutorial
- [9, 12] iClone 8 Online Manual - Using the Reach Target Panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Reach_Target/Using_the_Reach_Target_Panel.htm
- [10] iClone 8 Online Manual - Introducing Reach Target Panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Reach_Target/Introducing_the_Reach_Target_Panel.htm
- [13, 15] How to Edit Different 3D Motions in the Same Motion Clip | iClone 8 Tutorial
- [14, 16] iClone 8 Online Manual - How to use Edit Motion Layer panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Motion-Layer/Using_Body_Key_Editor.htm
- [17, 19, 22, 23] How to adjust contact points for climbing and falling motions | Mocap Animation Course | iClone 8
- [18] Motion Clip Editing & Basic Timeline Features | iClone 8 Tutorial
- [20, 21] How to Correct Footsteps & Hand Positions for 3D Motion Design | iClone 8 Tutorial
- [24, 25] How to tailor time curves on motion clips for impactful motions | Mocap Animation Course | iClone 8
- [26, 28, 29] How to Throw Objects with Physics to Create 3D Animation | 3D Mocap Animation Course | iClone 8
- [27] iClone 7.1 Tutorial - Curve Editor: Physics Animation with Curve Editor Manipulation
- [30] iClone 8 Online Manual - How to create body motions with effector dummies - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/50-Animation/Reach_Target/Creating_Body_Motions_with_Effector.htm

---

## (e) AI Render control passes and output

**Question asked:** Explain Reallusion AI Render for iClone 8: installation (ComfyUI + plugin), what control passes it exports (Pose/OpenPose, Depth, Normal, Canny, style/IPAdapter), how to choose and weight them, image-to-image vs video-to-video workflows, output resolution/frames, where outputs go, custom workflows (FLUX), and gotchas. Exact panel and node names.

### Part 1: iClone 8 Project Frame Rate, Total Frames, Render Settings, & Python API

#### 1. Setting Project Frame Rate (FPS) and Total Frames
* **Accessing Panel**: Go to the top menu **Edit** >> **Project Settings** (or open the **Project Setting Panel**) [1, 2].
* **Time Unit Section**:
  * **FPS**: Choose the project frame rate from the dropdown list (standard options include `12`, `24`, `25`, `30`, and `60` FPS; default is `60 FPS`) [3-5].
  * **Total Frames**: Displays the project length in total frame count [5].
    * **Default Length**: **1,800 frames** (30 seconds at 60 FPS) [5, 6].
    * **Maximum Length**: **54,000 frames** [5].
  * **Time Unit**: Toggle to display the timeline in **Time** format (milliseconds/seconds) or **Frame** count [5].
* **Setting Cue In/Out Marks on Timeline**:
  * Select motion clips on the timeline and click **Set Start / End Frame to Current Selection** to automatically trim the project play/render range to match the selected clip bounds [21–22, 66, 139].

---

#### 2. Rendering & Exporting the Final Result
* **Accessing Panel**: Open the **Render Panel** via top menu **Render** >> **Render Video** / **Render Image**, or click the **Render** icon on the **Project Toolbar** [3, 4, 7, 8].
* **Format Section**:
  * **Video Format**: Radio button **Video** >> select format (**MP4 [H.264]**, **AVI**, **WMV**, or **WAV**) [3, 4, 9]. Adjust **Video** and **Audio** quality sliders to maximum [4, 9].
  * **Image Sequence Format**: Radio button **Sequence** >> select format (**PNG [32-bit]**, **JPG**, **BMP**, **TGA [32-bit]**, or **EXR**) [4, 7, 10, 11].
* **Output Size Section**:
  * Choose preset frame dimensions (e.g., `1080p`, `720p`, or Square) or manually input custom X/Y pixel counts with **Lock Ratio** enabled [4, 12, 13].
* **Render Quality Section**:
  * Set to **Final Render** mode to enable hardware Anti-Aliasing (eliminates jagged edges) [3, 10, 11].
  * Check **Activate Depth of Field** if your scene uses camera DOF [3].
* **Output Range Section**:
  * Choose **All** (full project length), **Range** (bounded by Mark-In / Mark-Out flags), or **Current Frame** (`F10` quick preview) [4, 8, 11, 12, 14].
* **Transparent Background Exports (Alpha PNG/Video)**:
  * Select **PNG** or **Alpha Video** in the Render Panel [4, 10].
  * Go to **Project Settings** >> **2D Background** section and uncheck **Active Image** to render a transparent alpha background [1, 10].

---

#### 3. FPS-Related Gotchas
* **Default Output Mismatch**: iClone’s viewport defaults to **60 FPS** [3], while standard video deliverables use **24 FPS** or **30 FPS** [9]. Verify export FPS in the Render Panel before rendering to avoid speed or duration discrepancies.
* **AI Video Generation Limitation**: When exporting animations for AI Video-to-Video workflows, setting frame rates above **24 FPS** exponentially increases AI processing time and GPU VRAM usage. Reallusion recommends exporting at **24 FPS or lower** [15].

---

#### 4. Python API (`RLPy`) Automation
* **Environment**: iClone 8 uses **Python 3.8** and **Qt 5.15.2 (PySide2)** [16].
* **Core API Namespace**: Scripting uses the **`RLPy`** module (`RApplication`, `RGlobal`, `RTime`, `RFileIO`, `RScene`, `RlClip`, `RICamera`) [17, 18].
* **Custom FPS Handling**: `RLPy` provides explicit classes like `RTime` to calculate time codes and handle custom FPS re-sampling programmatically (`Dealing with Custom FPS`) [17, 18].
* **Deprecated Functions**: In iClone 8, the legacy iClone 7 motion bone structure was removed (`GetMotionBones()` removed from `RISkeletonComponent`) [58–59].

---

### Part 2: Reallusion AI Render for iClone 8 & Character Creator

#### 1. System Requirements & Installation
* **System Requirements**: Windows 10/11, NVIDIA RTX GPU (RTX 3070 with 8GB+ VRAM recommended), **80 GB free disk space** (for ComfyUI server and AI models), iClone v8.54+ / CC v4.54+ [19].
* **Step-by-Step Setup**:
  1. Unzip the installation package containing the installer, required patch file, and plugin [19].
  2. **First**, run the **patch installer**; **second**, run the **AI Render plugin installer** [19].
  3. Launch iClone -> open the **AI Render Panel** -> go to **Settings** >> **Connection** tab -> click **Launch** [19].
  4. A **Command Prompt window** will launch to run the backend ComfyUI server [19].
  5. **Gotcha**: **Do NOT close the Command Prompt window** while using AI Render, or the backend connection will disconnect [19]. Once the indicator turns green, required models auto-download on first render preview [19].

---

#### 2. Control Passes Exported & Reallusion Custom Nodes
AI Render extracts structured 3D scene data from the viewport and sends it to backend ComfyUI nodes [152–153]:

* **Exported Control Passes (ControlNet Types)**:
  * **Pose / OpenPose**: Character bone hierarchy and skeletal joints [20, 21].
  * **Depth**: Grayscale distance map defining character shapes and scene depth relative to the camera [21-23].
  * **Normal**: Surface geometry normals [21].
  * **Canny**: Edge/silhouette line detection map [21].
  * **Style / IPAdapter (Additional Image Node)**: Inputs overlay style reference images with linear blending or style transfer weights [24].
  * **LoRA Integration (Power LoRA Loader)**: Loads lightweight identity LoRAs (trained via FluxGym/RunPod from 3D staged character photos) to lock facial and body character features [25, 26].

* **Reallusion Custom Nodes in ComfyUI** (found by searching `RL` or in `ComfyUI/custom_nodes/ComfyUI-Reallusion`) [4–5, 31]:
  * **`RL AI Render UI Core`**: Master bridge passing prompts, seed, steps, CFG scale, denoising strength, and audio path from iClone to ComfyUI [5–6, 30]. Reads viewport image (`render_image.png`) and latent VAE dimensions [6–7].
  * **`RL Set ControlNet`**: Converts 3D control maps (e.g., `render_image_depth.png`, `render_image_pose.png`) into ControlNet inputs for Flux or Stable Diffusion models [7–8, 30].
  * **`Upscale Data Node`**: Configures output upscale resolution passed from iClone [24].

---

#### 3. Choosing and Weighting Parameters
* **ControlNet Weights**: Adjust **Strength**, **Start Percent**, and **End Percent** on the ControlNet node to balance structural adherence vs. AI creativity [20, 21].
* **Prompt Influence / CFG Scale**: Higher influence forces the model to adhere strictly to written text descriptions [15, 21].
* **Denoising Strength**: Lower values retain more of the 3D viewport look; higher values let AI re-imagine textures and details [21].
* **Seed Lock**: Use **Random** seed to explore visual styles, then switch to **Fixed** seed to maintain visual consistency across camera angles and animation frames [22, 27].
* **Aspect Ratio**: SD 1.5 presets perform best at a **1:1 square canvas** (`512x512`) [15, 22].

---

#### 4. Image-to-Image vs. Video-to-Video Workflows
* **Image-to-Image (I2I)**:
  * Converts low-poly 3D models or staged scenes into high-detail renders [22].
  * Click **Capture Viewport** to auto-generate a text description of the viewport, add custom keywords, preview, and upscale [15, 22].
* **Video-to-Video (V2V)**:
  * Applies AI style transformation across full animation sequences [15, 23].
  * **Performance Switch ("Always Render New")**: Uncheck **Always Render New** when tweaking prompts or samplers. As long as frame count, resolution, and ControlNets remain unchanged, existing control passes won't re-render, dramatically speeding up iterations [27].

---

#### 5. Output Paths & Custom Workflows (FLUX)
* **Output Storage**: Rendered images, video outputs, and ComfyUI workflow JSON files are saved in the **History folder** (access by right-clicking the preview thumbnail >> **Browse**) [19].
* **Custom FLUX Workflows**:
  1. Build a custom workflow in ComfyUI (e.g., using `FluxDev` base templates + `RL AI Render UI Core` + `RL Set ControlNet`) [4–8].
  2. Save the workflow API as a `.json` file to the `AI Render / Custom Workflows` directory [28].
  3. Open iClone's AI Render panel -> click **Add Tool** -> import the custom FLUX workflow JSON to expose custom parameters and LoRAs directly in the iClone UI [28].

---

#### Gotchas & Troubleshooting
1. **Closing Command Prompt**: Closing the backend ComfyUI command prompt window kills the AI Render connection immediately [19].
2. **Vague Depth Maps**: In wide or mid-shots, depth maps can look vague; switch camera framing to portrait/close-up or manually tweak depth adjustment sliders in the AI Render panel [22, 23].
3. **Floating Characters**: If AI renders show un-grounded or floating characters, import environment props (floors or blocks) into iClone so the depth map captures physical contact planes [16–17].
4. **V2V Frame Rate Limits**: Rendering V2V sequences above 24 FPS causes extreme render times; keep video export frame rates at **24 FPS or lower** [15].

---

Would you like to explore setting up custom **FLUX LoRA dataset generation** using Character Creator staged renders, or configuring cloud GPU rendering with RunPod for AI Render?

### Sources cited

- [1, 2, 5] iClone 8 Online Manual - Time Unit Section - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/03-Introducing-the-User-Interface/Project_Settings_Time_Unit.htm
- [3, 14] Getting Start with iClone 8 - Easy Character Animation Workflow | iClone 8 Tutorial
- [4] iClone 8 Online Manual - Rendering - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/80-Export/Exporting.htm
- [6] iClone 8 Online Manual - Timeline Operation - Basic - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/51-Animation-Timeline-Editing/Timeline-Operation-Basic.htm
- [7, 9, 10, 11, 12] Rendering Settings
- [8] iClone 8 Online Manual - Render Panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/03-Introducing-the-User-Interface/Render_Panel.htm
- [13] iClone 7 Tutorial - Real Camera System
- [15, 23, 27] AI Render Video To Video Workflow | iClone & CC Tutorial
- [16, 17, 18] IC8 Python API - Reallusion Wiki! - https://wiki.reallusion.com/IC_8_Python_API
- [19] AI Render Installation Guide for iC & CC | iClone & CC Tutorial
- [20, 25, 28] AI Render Custom Workflow with FLUX | iClone & CC Tutorial
- [21, 24] GitHub - reallusion/ComfyUI-Reallusion · GitHub - https://github.com/reallusion/ComfyUI-Reallusion
- [22] AI Render Image To Image Workflow | iClone & CC Tutorial
- [26] iClone Delivers Production-Level Control for AI Generation - Reallusion Magazine - https://magazine.reallusion.com/2025/08/08/iclone-delivers-production-level-control-for-ai-generation/

---

## (f) Project FPS / length and render output

**Question asked:** In iClone 8, how do I set project frame rate (fps) and project length/total frames (Project Settings, Time Unit), what are defaults and max, and how do I render/export the final result: Render panel, video vs image sequence, output range, resolution, frame rate at export, and any fps-related gotchas (e.g. motion clips at 60 vs 30 fps)? Also mention anything about the Python API (RLPy) for automating this.

### 1. Setting Project Frame Rate & Length (Project Settings)

To configure your project's duration and frame rate in **iClone 8**:

* **Accessing Project Settings**:
  * Go to the top menu: **Edit** >> **Project Settings** (or open the **Project Setting Panel** from the docking area / Project Toolbar) [1, 2].
* **Time Unit Section Parameters**:
  * **FPS (Frames Per Second)**: Use the drop-down list to set the project's base playback frame rate [3]. The default playback and viewport frame rate in iClone 8 is **60 FPS** [4].
  * **Total Frames**: Defines the total project duration in frame count [3].
    * **Default Length**: **1,800 frames** (equivalent to 30 seconds at 60 FPS or 60 seconds at 30 FPS) [3, 5].
    * **Maximum Limit**: **54,000 frames** (equivalent to 15 minutes at 60 FPS or 30 minutes at 30 FPS) [3].
  * **Time Unit**: Choose between displaying the timeline in **Time** (timecode format: `MM:SS:FF`) or **Frame** (raw frame numbers) [3].
  * **Time Mode**: Switches physics evaluation between **Realtime** and **By Frame** (evaluates physics deterministically frame-by-frame) [3].
  * **Play Mode**: Toggles timeline playback looping [3].

---

### 2. Rendering & Exporting the Final Result

* **Accessing the Render Panel**:
  * Go to top menu **Render** >> **Render Video** / **Render Image**, or click the **Render** icon on the **Project Toolbar** [6-8].
* **Format Section (Media Types)**:
  * **Video**: Exports as **MP4 (H.264)**, **AVI** (uncompressed Lossless RAW or compressed), **WMV**, or **WAV** audio [8, 9].
  * **Image Stills**: Exports single frames as **PNG** (32-bit with alpha transparency), **JPG**, **BMP**, **TGA**, or **EXR** [8, 10].
  * **Image Sequence**: Toggle **Sequence** mode under Image format to export numbered frame files into a designated folder [8, 11].
* **Output Size Section**:
  * **Resolution Presets**: Select from standard aspect ratios and resolutions (e.g., 1080p Full HD, 720p, 4K, or Square 512 for AI workflows) [8, 12].
  * **Custom Dimensions**: Manually input pixel counts for horizontal (\\(X\\)) and vertical (\\(Y\\)) axes [12, 13]. Check **Lock Ratio** to maintain aspect proportions automatically [12].
  * **Camera Ratio & Film Gate**: Go to **Edit** >> **Preferences** and enable **Show Camera Ratio** to view film gate padding or cropping relative to output size [13].
* **Export Frame Rate**:
  * Select from the **Frame Rate** drop-down: **12**, **24**, **25**, **30**, or **60 FPS** [8]. (30 or 60 FPS are standard for video; 24 FPS is standard for film/cinematic exports) [4, 9].
* **Output Range Section**:
  * **All**: Exports the entire project from frame 1 to Total Frames [14].
  * **Range / Playback Range**: Restricts rendering to specific Start and End frame numbers or between the timeline **Mark-In** and **Mark-Out** flags [14, 15].
* **Render Quality & Post Options**:
  * Set **Quality Compressor** sliders for video/audio to maximum [8, 9].
  * Choose **Final Render** mode to enable hardware **Anti-aliasing** (eliminates jagged geometry edges) and ensure **Shader Quality** is set to High [4, 9].
  * Check **Activate Depth of Field** if your project incorporates focal camera blurs [4].

---

### 3. FPS & Frame Rate Gotchas

1. **iClone 60 FPS Internal Timing vs. Motion Clips**:
   * iClone calculates keyframe interpolations natively at high temporal resolution. When applying motion clips recorded at 30 FPS (such as raw mocap data), iClone automatically interpolates the motion to match the project’s 60 FPS base without shortening or altering real-time playback speed [4, 16].
2. **Exporting at Different Frame Rates**:
   * Changing the export FPS in the Render Panel (e.g., exporting a 60 FPS project at 24 FPS or 30 FPS) re-samples the output frames accordingly without altering the animation's real-world timing or pitch [8, 11].
3. **AI Render / ComfyUI Workflows**:
   * When using the **AI Render** video-to-video plugin, rendering at high frame rates (like 60 FPS) generates an excessive number of image frames for ComfyUI to process [17]. Reallusion explicitly recommends setting the video render frame rate to **24 FPS** (or lower) to prevent extreme GPU rendering overhead [17].
4. **Physics Evaluation in "By Frame" Mode**:
   * If physics simulation is set to **By Frame** in Project Settings, changing the project frame rate alters the time-delta calculated per simulation step, which can cause rigid bodies or cloth to behave differently unless baked to keys [3, 18].

---

### 4. Automation via the Python API (`RLPy`)

iClone 8 includes an embedded Python scripting engine (**Python 3.8** with **PySide2** / Qt 5.15.2) [19]:

* **Core Module (`RLPy`)**:
  * **`RLPy.RTime`**: Handles time calculations. In iClone's Python convention, **1 Time Unit = 1 millisecond** (\\(1,000 \text{ time units} = 1 \text{ second}\\)) [19].
  * **`RLPy.RApplication` & `RLPy.RGlobal`**: Provide methods for accessing application settings, project properties, and triggering render routines programmatically [20, 21].
  * **`RLPy.RFileIO` & `RLPy.RScene`**: Manage opening, saving, and loading scene assets programmatically [21].
* **Handling Custom FPS in Code**:
  * The API includes specialized modules like `Dealing with Custom FPS` to calculate frame step intervals when setting transform or camera keys via script [20].
* **Reallusion ComfyUI / AI Render Integration**:
  * Backend plugins (such as `ComfyUI-Reallusion`) are written entirely in Python, utilizing custom nodes (`RL AI Render UI Core`) to pass frame rates, image dimensions, output paths, and seeds directly between iClone and external AI pipelines [4, 25–27].

---

Would you like to explore setting up a **Batch Rendering** queue or writing a custom Python script to automate scene batching?

### Sources cited

- [1, 7] iClone 8 Online Manual - Render Panel - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/03-Introducing-the-User-Interface/Render_Panel.htm
- [2, 3] iClone 8 Online Manual - Time Unit Section - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/03-Introducing-the-User-Interface/Project_Settings_Time_Unit.htm
- [4, 14] Getting Start with iClone 8 - Easy Character Animation Workflow | iClone 8 Tutorial
- [5, 15] iClone 8 Online Manual - Timeline Operation - Basic - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/51-Animation-Timeline-Editing/Timeline-Operation-Basic.htm
- [6, 9, 10, 11, 12] Rendering Settings
- [8] iClone 8 Online Manual - Rendering - https://manual.reallusion.com/iClone-8/Content/ENU/8.0/80-Export/Exporting.htm
- [13] iClone 7 Tutorial - Real Camera System
- [16] Motion Clip Editing & Basic Timeline Features | iClone 8 Tutorial
- [17] AI Render Video To Video Workflow | iClone & CC Tutorial
- [18] iClone 7.1 Tutorial - Curve Editor: Physics Animation with Curve Editor Manipulation
- [19, 20, 21] IC8 Python API - Reallusion Wiki! - https://wiki.reallusion.com/IC_8_Python_API
