# MateSnap

MateSnap is a Blender add-on to quickly snap objects/vertices/points to object
origins/vertices/points, similar to how vertex snap works in Maya/3ds Max —
extended into an assembly tool for 3D-printed figurine and model kits: it
mates connector pairs with a two-click **Lock and key** workflow, refines
completed snaps with a **precision fit**, and stays responsive on
multi-million-polygon parts.

## What's new compared to QuickSnap

Everything QuickSnap does still works the same way. MateSnap adds:

### Lock and key: two-click connector mating

* **Click the key, click the lock, done.** Click a connector on the part you
  want to move, then the matching connector on the part it plugs into. MateSnap
  measures both connectors and seats the key in one step. There is no dragging,
  and a single undo takes the mate back.
* **Handles the connectors kits actually use:** square and rectangular pegs,
  slots, tapered pegs, round pegs, and D-shaped or oval pegs (flat on one side,
  round on the other). It copes with sculpt-dense meshes, rounded edges,
  chamfered socket mouths, and sockets whose floor is a separate piece of mesh.
* **Corrects rough clicks.** Each click is moved to the centre of the wall it
  landed on, and the preview dot shows the exact point the mate will use.
  You can switch this off with **Centre picks on the wall**.
* **Can rotate the key into place.** With **Rotate key to match lock** on
  (press **R** while picking to toggle it), the key is turned to fit the socket.
  The easiest way to use it is to click the end of the peg, then the floor of
  the socket. When a square peg would fit several ways round, MateSnap checks
  the surrounding geometry and throws out any rotation that would push the part
  into its neighbour. If several rotations are still possible, it keeps the one
  closest to how you placed the part.
* **Round pegs slide straight in.** Click the end of a round peg and the floor
  of its hole: the peg is centred and pushed in without being spun. If rotation
  is on, the peg is first tilted the shortest way so it lines up with the hole.
  Its spin around its own axis stays as you placed it.
* **Never guesses.** If a mate is unclear or would push the key into the lock's
  material, nothing moves. The status bar says why and what to try instead.
  The full measurements behind the decision go to the console and to
  `matesnap_lock_key_log.txt`, saved next to your .blend file.

### Precision fit after a normal snap

* After an ordinary Object-mode snap between vertices, edge midpoints or face
  centres, MateSnap looks for the matching flat walls of a connector and
  centres the part inside the gap the designer left. It also works on tapered
  connectors. It only slides the part sideways — how deep it sits stays where
  you snapped it — and it does nothing if it finds no clean connector walls.

### Built for very dense meshes

* Snapping stays smooth on parts with millions of polygons. Snap points load in
  the background over a few frames, and heavy meshes skip the lookup structures
  that would freeze the viewport.
* Dense objects show their wireframe only around the cursor, not across the
  whole mesh. You can set the radius, colour, opacity and see-through mode, and
  choose the size at which this kicks in.
* Lock and key reads only the area around your click on a dense part and
  remembers what it has read for the next mate.

### Easier picking

* **Prefer corners:** corners of pegs and sockets are easier to grab than
  points on flat areas around them.
* **Hide dragged objects over the target:** the parts you are moving disappear
  while the mouse is over the target, so you can see what you are snapping to.
* **Pause snapping with Shift or by orbiting:** hold Shift or the middle mouse
  button to look around the target without snapping to anything.
* **N-panel toggles:** a MateSnap tab in the 3D view sidebar holds the
  everyday switches — Lock and key, rotation, centring, precision fit, prefer
  corners and hide dragged objects.

### Other changes

* Requires **Blender 5.0 or newer**; the old pre-3.4 drawing code is gone.
* Updates come from this project's own
  [Release Page](https://github.com/RemindZ/MateSnap/releases).

The full history is in [CHANGELOG.md](CHANGELOG.md).

## About

MateSnap continues [QuickSnap by Julien Heijmans](https://github.com/JulienHeijmans/quicksnap)
(MIT). The presentation video below demonstrates the inherited core snapping
interaction; MateSnap adds its own defaults and post-snap assembly behavior:

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
* Constrain the translation with **X/Y/Z** for an axis or
  **Shift+X/Shift+Y/Shift+Z** for a plane.
* Automatic wireframe display of the object you snap onto, target
  highlighting, snapping to hidden points, orthographic and local view
  support.

### Kit assembly (MateSnap)

* **Lock and key** — mate two parts with two clicks: one on the moving key's
  connector, one inside the stationary lock. The solver measures the
  connector walls and applies one consistent transform to the selected roots.
  It centres sloppy picks on their walls (the preview dot slides to the point
  it will actually use), forgives clicks on a connector's chamfer, and can rotate the key to
  match the lock (toggle with **R** during the pick, or in the settings).
  Flat-sided, tapered, round and D-shaped pegs are supported. When a mate
  cannot be computed safely it refuses with a reason, and writes a full
  geometric report to the console and to `matesnap_lock_key_log.txt` — it
  never guesses.
* **Precision fit** — after an unconstrained Object-mode snap between geometry
  points, midpoints, or face centres, opposed connector walls are detected and
  the part is centred within its designed clearance, including drafted
  (tapered) connectors as found on printed parts. Origin snaps and Edit mode do
  not run this refinement.
* **Built for dense meshes** — Lock and key starts with click-local extraction
  and widens to full coverage when needed, while standard snapping processes
  dense data progressively to keep the viewport responsive.

### Updates

* The add-on includes the [Blender Addon Updater](https://github.com/CGCookie/blender-addon-updater):
  check for and install MateSnap updates from within Blender, with optional
  notifications. Enable/disable this in the add-on preferences.

## Installation

1. Download `MateSnap-<version>.zip` from the
   [Release Page](https://github.com/RemindZ/MateSnap/releases).
2. In Blender, go to **Edit > Preferences > Add-ons**, open the menu in the
   top-right, choose **Install from Disk**, and pick the downloaded archive.
3. Enable MateSnap.

### Migrating from QuickSnap-High-Poly

MateSnap includes all of QuickSnap-High-Poly's snapping features. Disable or
uninstall QuickSnap-High-Poly first — both use **Ctrl+Shift+V** by default, so
running both creates a hotkey conflict. MateSnap keeps its own preferences, so
add-on settings once after installing.

## Hotkey and settings

* Enable the tool with **Ctrl+Shift+V** (for Vertex) by default. Watch out if
  you use multiple keyboard layouts: Ctrl+Shift may cycle the active layout
  in Windows.
* The same hotkey opens the pie menu while the tool is active.
* Change the hotkey and discover the rest in the add-on settings.

## Using the tool

* In Object mode, selecting an object first is optional: with no selection,
  MateSnap can pick the object under the mouse. In Edit mode, select the
  vertices/edges/faces/curve points you want to move.
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
* For automatic rotation, the natural gesture is the centered end face of the
  peg followed by the centered floor of the socket. The floor may be a separate
  mesh island from its side walls. Click matching side walls instead when you
  need to disambiguate a connector with several genuinely different seatings.
  The preview dot shows the anchor the mate will use.
* **Round and D-shaped pegs:** click the flat end of the peg and the flat floor
  of its hole. The peg slides in centred and keeps the spin you gave it, so
  turn it roughly the right way round first. With rotation on, a tilted peg is
  first lined up with the hole; with rotation off, the end of the peg and the
  floor must already be within 5° of each other.
* If a mate is refused, the status bar states why. The full report goes to the
  console and is added to `matesnap_lock_key_log.txt`, next to the .blend file
  (or in Blender's temp folder for an unsaved file).

## Performance notes

Unlike the original QuickSnap, MateSnap is built for very dense scenes:
snapping data is processed progressively, heavy meshes skip index structures
that would stall the viewport, and Lock and key starts with a click-local
region before widening to full coverage when necessary. Instrumented Lock and
key stages print their timings to the console when they exceed their warning
thresholds; include those lines in performance reports.

## Updating the add-on

* In the add-on preferences, click **Check now for MateSnap update**.
* If the button changes to **Update now to (x.y.z)**, click it and restart
  Blender.

## Bug reports

* First make sure you are on the latest version (see above).
* Open an issue at https://github.com/RemindZ/MateSnap/issues with what you
  did, what you expected, and what happened.
* For Lock and key refusals or wrong mates, paste the matching entries from
  `matesnap_lock_key_log.txt` (next to your .blend) or the Blender console
  output.
  **Never send your model files** — kit models are usually private, and
  MateSnap's diagnostics are designed to make the failure understandable
  without them.

## Known issues / limitations

* Target highlighting does not work with 'Ignore modifiers' enabled.
* In Edit mode the tool always uses the original points of the mesh (without
  modifiers).
* Lock and key mates a round peg only from clicks on its flat end and the
  hole's flat floor; clicking its curved side is refused. A round peg's spin
  about its own axis comes from how you placed it, so turn a peg with a
  matching shape (a D-peg, or a post with a slanted tip) roughly into place
  first.
* Organic contact surfaces, or connectors that fit several genuinely different
  ways, are refused rather than guessed at.

## Version support

* Blender 5.0 and newer.

## Credits and license

MateSnap is based on [QuickSnap](https://github.com/JulienHeijmans/quicksnap)
by Julien Heijmans, whose snapping core and demo material live on here. MIT
licensed — see [LICENSE.md](LICENSE.md) for both copyright notices. Release
history, including the pre-rename 1.8.x line, is in
[CHANGELOG.md](CHANGELOG.md).
