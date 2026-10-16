# Stock content on a default install

Library root: `%PUBLIC%\Documents\Reallusion` (e.g. `C:\Users\Public\Documents\Reallusion`). The other workstation keeps a
larger library on `F:\iCLONE` (`ICMCP_CONTENT_ROOT`); never assume it exists - check with `os.path.isfile`.
Search: `find "$PUBLIC/Documents/Reallusion" -iname "*sit*.rlMotion"` etc. Counts here: 55 .iAvatar, ~670 .iMotion,
186 .rlMotion, 118 .rlPose, 11 .iSky.

| Need | Path (under the library root) |
|---|---|
| Business avatars (full CC) | `Reallusion Templates\Actor\Character\Business\Business_{M,F}_00NN.iAvatar` |
| Crowd (light) actors | `Reallusion Templates\Actor\Character\ActorCore Crowd\Casual_{M,F}_E000N.iAvatar` |
| Sit + talk | `Reallusion Templates\Animation\Motion\{1.Human Male,2.Human Female}\Perform\Sit Talk.rlMotion` |
| Stand talk / transitions | `...\Perform\Stand Talk.rlMotion`, `Stand to Sit`, `Sit to Stand`, `Talk Serious` |
| Root-motion walk (walk_to) | `Template\iClone 7 Template\iClone Template\Motion\{03_CC MixMove_Male,04_CC MixMove_Female}\Walk.iMotion` |
| Idle (stand) | same folders, `Stand00.iMotion` |
| In-place walk loops | `Reallusion Templates\Animation\Motion\*\Move\Walk_2Loop.rlMotion` (barely moves legs on ActorCore) |
| Poses | `Reallusion Templates\Animation\Pose\{1.Male Pose,2.Female Pose,Samples}\*.rlPose` |
| Skies | `Template\iClone 7 Template\iClone Template\Sky\*.iSky` |
| Mograph sit set (female CC) | `Template\iClone 7 Template\iClone Template\MographMotion\00_Female (CC)\Sit*.iMotion` |

Windows TTS voices for dialog: "Microsoft David Desktop" (male), "Microsoft Zira Desktop" (female).
