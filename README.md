# MateSnap

MateSnap is a Blender add-on to quickly snap objects/vertices/points to object
origins/vertices/points, similar to how vertex snap works in Maya/3ds Max —
extended into an assembly tool for 3D-printed figurine and model kits: it
mates connector pairs with a two-click **Lock and key** workflow, refines
completed snaps with a **precision fit**, and stays responsive on
multi-million-polygon parts.

MateSnap continues [QuickSnap by Julien Heijmans](https://github.com/JulienHeijmans/quicksnap)
(MIT). The presentation video below is from QuickSnap — the base snapping
workflow is unchanged:

https://user-images.githubusercontent.com/35562774/195340412-6931d8f0-045d-4c4d-badd-96b94ef7f1cc.mp4

If the video is not playing for you, you can watch it here: https://youtu.be/9cWV0JELM88

## Update notes

Check the [Release Page](https://github.com/RemindZ/MateSnap/releases) to
learn about the latest updates.

## Features

### Snapping

* Snap From/To:
  * Scene cursor
  * Object origins
  * Vertices and curve points
  * Edge mid-points
  * Face centers
* Change the snap target type using hotkeys — 1: Vertices/curve points,
  2: Edge centers, 3: Face centers, O: Origins — with an icon next to the
  mouse showing the current type (always visible, fading, or disabled):

    ![hotkey-icon](https://user-images.githubusercontent.com/35562774/199265091-24b63cdf-780b-4aa1-847c-cfb486469356.gif)

* Snap by click-and-drag, or with two separate clicks (you can move the
  camera between the two):

    ![two-click-workflow](https://user-images.githubusercontent.com/35562774/199266031-7d27c422-83dd-4f15-a051-341dd86d6d93.gif)

* Works with no selection: in Object mode the object under the mouse is
  moved; in Edit mode the points under the mouse are moved (and merged when
  auto-merge is enabled).
* A pie menu (same hotkey as the tool) switches what you snap from/to:

    ![pie-menu](https://user-images.githubusercontent.com/35562774/196196537-82078f77-70ab-4929-a36a-6aaf6fe3bfde.gif)

* Optional vertex auto-merge after a snap in Edit mode.
* Constrain the translation to an axis or plane with (Shift+)X, Y, Z.
* Automatic wireframe display of the object you snap onto, target
  highlighting, snapping to hidden points, orthographic and local view
  support.

### Kit assembly (MateSnap)

* **Lock and key** — mate two parts with two clicks: one on the moving key's
  connector, one inside the stationary lock. The solver measures the
  connector walls and applies one safe, atomic transform. It centres sloppy
  picks on their walls (the preview dot slides to the point it will actually
  use), forgives clicks on a connector's chamfer, and can rotate the key to
  match the lock (toggle with **R** during the pick, or in the settings).
  When a mate cannot be computed safely it refuses with a reason and prints a
  full geometric report to the console — it never guesses.
* **Precision fit** — after a normal snap, opposed connector walls are
  detected and the part is centred within its designed clearance, including
  drafted (tapered) connectors as found on printed parts.
* **Built for dense meshes** — extraction is region-based around your click
  and cached across mates, so multi-million-polygon figure parts stay
  interactive. The first contact with a dense part pays a one-time cost of
  about a second; anything slower names its stage in the console.

### Updates

* The add-on includes the [Blender Addon Updater](https://github.com/CGCookie/blender-addon-updater):
  check for and install MateSnap updates from within Blender, with optional
  notifications. Enable/disable this in the add-on preferences.

## Installation

1. Download `MateSnap-<version>.zip` from the
   [Release Page](https://github.com/RemindZ/MateSnap/releases).
2. In Blender, go to **Edit > Preferences > Add-ons**, click **Install...**
   in the top-right, and pick the downloaded archive.
3. Enable MateSnap.

### Migrating from QuickSnap

MateSnap includes all of QuickSnap's snapping features. Disable or uninstall
QuickSnap first — both use **Ctrl+Shift+V** by default, so running both
creates a hotkey conflict. MateSnap keeps its own preferences, so revisit the
add-on settings once after installing.

## Hotkey and settings

* Enable the tool with **Ctrl+Shift+V** (for Vertex) by default. Watch out if
  you use multiple keyboard layouts: Ctrl+Shift may cycle the active layout
  in Windows.
* The same hotkey opens the pie menu while the tool is active.
* Change the hotkey and discover the rest in the add-on settings.

## Using the tool

* Select the object (or vertices/edges/faces/curve points) you want to move.
* Enable the tool (**Ctrl+Shift+V**).
* Pick the snap type by hotkey (1/2/3/O) or through the pie menu.
* Snap by click-and-drag, or with two clicks (FROM, then TO).
* **Right mouse button** or **ESC** cancels.

### Using Lock and key

* Enable **Lock and key** in the pie menu or the N-panel.
* Select the key — the part that will move — and start the tool.
* Click the key's connector (a wall of its peg or socket), then click inside
  the matching connector on the stationary part. The mate applies instantly.
* **R** toggles "Rotate key to match lock" during the pick; **Backspace**
  un-picks the key; right-click or ESC cancels.
* Click connector walls rather than large flat faces — the preview dot shows
  the anchor the mate will use. If a mate is refused, the status bar states
  why and the console holds the full report.

## Performance notes

Unlike the original QuickSnap, MateSnap is built for very dense scenes:
snapping data is processed progressively, heavy meshes skip index structures
that would stall the viewport, and Lock and key extracts only a region around
your click. If anything takes longer than a quarter second, MateSnap prints
which stage and how long to the console — include those lines in any
performance report.

## Updating the add-on

* In the add-on preferences, click **Check now for MateSnap update**.
* If the button changes to **Update now to (x.y.z)**, click it and restart
  Blender.

## Bug reports

* First make sure you are on the latest version (see above).
* Open an issue at https://github.com/RemindZ/MateSnap/issues with what you
  did, what you expected, and what happened.
* For Lock and key refusals or wrong mates, paste the Blender console output
  and attach `matesnap_lock_key_log.txt` (saved next to your .blend, or in
  the temp folder for unsaved files). **Never send your model files** — kit
  models are usually private, and MateSnap's diagnostics are designed to make
  the failure understandable without them.

## Known issues / limitations

* Target highlighting does not work with 'Ignore modifiers' enabled.
* In Edit mode the tool always uses the original points of the mesh (without
  modifiers).
* Lock and key supports flat-sided connectors; rounded connectors are
  refused by design rather than guessed at.

## Version support

* Blender 2.93 and newer.

## Credits and license

MateSnap is based on [QuickSnap](https://github.com/JulienHeijmans/quicksnap)
by Julien Heijmans, whose snapping core and demo material live on here. MIT
licensed — see [LICENSE.md](LICENSE.md) for both copyright notices. Release
history, including the pre-rename 1.8.x line, is in
[CHANGELOG.md](CHANGELOG.md).
