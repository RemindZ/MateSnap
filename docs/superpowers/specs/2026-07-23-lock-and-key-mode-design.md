# Lock and Key Mode Design

Date: 2026-07-23
Status: Approved

## Purpose

Add a figurine-oriented two-click workflow to QuickSnap. A selected key part remains stationary while the user marks its connector, then a second click inside an unselected lock connector applies one safe, atomic mate transform.

"Key" and "lock" name the two clicks, not the two shapes: the first click is always on the moving selection and the second on the stationary part. Either may carry the peg or the socket -- see the matching rule below.

This is a separate workflow, not another source/target element type. Standard vertex, midpoint, face-center, and origin snapping remain unchanged.

## Interaction

### Selection wheel

Add a wide bottom pie entry named `Lock and key`. It toggles a persistent `lock_and_key_mode` preference. While active, the independent `Snap From` and `Snap To` columns remain visible but disabled, making it clear that this mode controls both picks.

Clicking `Lock and key` again restores standard snapping. Changing workflow while a partial pick is active resets the operator to its untouched starting state.

Add `Rotate key to match lock` to the QuickSnap N-panel and add-on preferences. Store it as `lock_and_key_rotate`, default `False`. Existing JSON settings persistence automatically preserves both properties.

### Preconditions

- Object mode only.
- One or more moving objects are already selected, following normal QuickSnap selection rules.
- The first hit must be a mesh face on the selected key hierarchy.
- The second hit must be a mesh face on an unselected target object.
- Each click must be on the actual connector feature, not merely somewhere on the figurine part.

### Two-click flow

1. The first click records the source object, evaluated/raw face index, exact world hit point, and face normal. Draw a persistent red 3D dot at that point.
2. Until the second click, mouse movement may preview the target surface but must not translate, rotate, or hide the selected part. Do not draw the standard rubber band.
3. The second click records the same data for the target connector.
4. Compute and validate one transform. Apply it to the selected root objects inside the existing undoable modal operation, then finish.
5. Right-click or Esc cancels without changing any object transform.

Headers say `Lock and key: click the connector on the selected key` and then `Lock and key: click inside the target lock`.

## Surface hits

Lock and key bypasses `SnapData` point ingestion and nearest vertex/edge/face-center search. It uses viewport surface raycasts, so dense connector meshes do not require a KD-tree build.

Use evaluated meshes unless `ignore_modifiers` is enabled. The face index used for feature extraction must come from the same raw/evaluated geometry that produced the stored hit. A stale face index, missing object, non-mesh hit, or changed topology fails closed.

## Connector geometry

Reuse the existing deterministic helpers:

- `_mesh_fit_data()`;
- `_seed_polygons(..., 'FACES', face_index)`;
- `_candidate_patches()`.

The clicked patch plus the existing two patch-boundary hops define the local connector. This lets a click on a connector side, tip, or nearby rim reach its other walls without searching the whole object.

Amended 2026-07-29: two hops is the starting radius, not a fixed one. Lock and key widens up to ten when a click yields no opposed wall pair at all, and stops at the first radius that yields one. Two hops reaches the far wall of a plain box peg, but every chamfer or fillet ring around an edge inserts another hop, so a well-modelled connector -- the common case in a real kit -- put its opposite wall permanently out of reach and reported that the click had landed on nothing.

Reaching across trim is not the same as mating against it. Only patches at least a tenth the area of the clicked one may form a pair: traversal still crosses the fillet strips, but a sliver never becomes a connector wall. Without that rule the strips dominate. A rounded edge yields dozens of them, each a plausible opposed pair on its own diagonal axis, and because a candidate whose two best targets tie is discarded as ambiguous, near-identical slivers tie constantly and delete the real wall match. The observed effect was a mate refused for holding thirteen matched pairs, not one of which involved an actual wall.

Two bounds keep the widened walk honest. It stops once it has reached several hundred patches without success, so a dense part cannot be made to grow half its mesh at click time. And a radius that produces more than a few dozen opposed pairs is a curve rather than a flat-sided connector, and fails closed immediately -- a rounded click otherwise reaches the far side of its own curvature and generates them by the thousand, which is meaningless and quadratic in the matcher.

Standard precision fit is unaffected: `_candidate_patches` keeps its two-hop default and its unfiltered patch list.

### Supported shapes

- rectangular/prismatic pegs and sockets;
- flat-sided slots;
- flat-sided pegs and sockets that taper along insertion depth, including trapezoidal profiles.

Round, cylindrical, spherical, noisy organic, incomplete, and ambiguous connectors are non-goals for this version.

### Side-pair descriptors

Standard precision fit keeps its strict 170-degree opposed-wall rule. Lock and key uses a separate connector-pair descriptor so it can recognize stronger depth taper without weakening standard snapping.

Form a connector side pair when:

- both patches are clean and planar;
- their outward normals face generally away from one another (`dot < 0`), excluding adjacent faces;
- their normal difference defines a stable lateral direction;
- the clicked point projects within the pair's lateral interval plus flatness tolerance;
- neither patch has zero area or extent.

Store the canonical lateral direction, pair opening angle, plane/centroid geometry, area, extent, and patch IDs. The normal sum is a depth-axis hint for tapered pairs; for straight pairs it may be zero.

Match source pairs to target pairs by opening angle, lateral width, patch adjacency, extent, and face-normal opposition. Clearance must be non-negative within flatness tolerance. Tied or incompatible candidates are discarded rather than resolved by polygon IDs.

Which half of a matched pairing is the socket is read from the wall normals -- walls that face each other are a socket, walls that face outward are a peg -- and never from click order. Clearance is then measured as socket width minus peg width in either direction, and a pairing of two pegs or two sockets is rejected outright, since no rotation can seat it. Amended 2026-07-27: the original wording tied the socket role to the target click, which made an assembly buildable only by moving the peg. Kits exist whose parts can only be positioned by moving the socket half onto a fixed peg; both orders describe the same seated result, so both must mate and their deltas must be inverses. The insertion-axis guard follows the same rule: it reads its half-space from whichever click landed on the socket.

## Transform solve

### Translation-only default

1. Define the coarse translation as `target_hit - source_hit`.
2. Evaluate the matched source planes after that translation against their corresponding target planes.
3. For each matched side pair, balance the two signed wall clearances. The difference of the paired target normals defines the centering equation, which cancels the common depth component of symmetric tapered walls.
4. Solve only the retained lateral row space using the existing relative SVD cutoff (`0.1`). Unobserved directions remain zero.
5. Add the lateral correction to the coarse translation. The click-defined insertion depth is unchanged.

Amended 2026-07-29: each click is first moved to the area-weighted centroid of the flat patch it landed on, under a `lock_and_key_centre_picks` preference defaulting to on. The anchor only moves inside its own plane, so no measured wall width changes and step 5 still holds -- what changes is that "click-defined" now means "defined by which wall was clicked" rather than "by where on it". Two clicks far apart on a constrained axis otherwise drive the lateral correction past the relocation cap and refuse an honest mate. Centring is never a restriction: when the wall centres fail to mate, the exact hit points are retried before anything is refused, and turning the preference off restores click-defined depth.

The centering correction retains the existing local trust principle: it may balance designed clearance but may not relocate the key to a different feature.

### Optional rigid alignment

When `lock_and_key_rotate` is enabled:

1. Require at least two independent matched wall directions.
2. Enumerate the small set of geometrically compatible source/target pair mappings.
3. Solve a proper rotation (`determinant +1`) from source outward normals to the opposing target inward normals using SVD/Kabsch.
4. Reject candidates whose angular, taper, width, or plane residual exceeds the feature tolerances.
5. For geometrically equivalent candidates, choose the smallest rotation from the current orientation. A tied non-equivalent result is ambiguous and fails closed.
6. Rotate around the stored source hit, map that hit to the target hit, then solve the same lateral clearance correction.

Return one world-space delta matrix:

```text
T(target_hit + lateral_correction) * R * T(-source_hit)
```

Apply it only to the selected root objects so child transforms are not doubled.

## Validation and failure behavior

Validate against the exact patch correspondences used to solve:

- every paired wall retains non-negative clearance within flatness tolerance;
- clearance imbalance decreases and finishes within tolerance;
- translation-only mode has zero correction in discarded directions;
- rotation mode keeps the source/target normal residual within tolerance;
- the source anchor preserves the target click's insertion coordinate;
- all values and matrices are finite.

If extraction, matching, solving, or validation fails, apply neither the coarse translation nor a partial rotation. Leave the scene untouched and report `Lock and key: no safe connector match found`.

## Code shape

- `quicksnap.py`
  - add the two preferences and pie/N-panel controls;
  - add the two-click modal state and surface-hit handling;
  - apply the returned delta matrix to selected roots.
- `quicksnap_render.py`
  - draw the persistent red source dot and optional target preview without standard snap guides.
- `quicksnap_utils.py`
  - add private connector-pair, correspondence, translation, rotation, and validation helpers;
  - expose one `compute_lock_key_transform(...) -> Matrix | None` entry point.
- `tests/lock_key_regression.py`
  - build synthetic connector meshes and exercise the solver plus operator-state invariants in Blender headless mode.

Do not add a dependency, global registration system, generic constraint framework, or fallback ICP path.

## Regression coverage

The Blender-headless harness must cover:

1. first click stores a surface hit and does not move the key;
2. rectangular connector translation maps the anchor, centers X/Y, and preserves insertion depth;
3. a stronger depth-tapered trapezoid centers laterally without being rejected as a wedge;
4. translation-only mode preserves the original rotation bit-for-bit;
5. rotation mode aligns a deliberately rotated rectangular connector and then centers it;
6. one matched direction is insufficient for rotation and returns `None`;
7. ambiguous rotational symmetry chooses the smallest equivalent rotation or rejects a non-equivalent tie;
8. stale face indices, organic geometry, incompatible taper, equal/negative clearance, and missing objects return `None`;
9. non-uniform object transforms and evaluated modifiers produce correct world-space results;
10. all selected root objects receive the same delta while child transforms are applied once;
11. standard precision-fit regressions remain green;
12. Lock and key mode settings survive the existing save/load mechanism.

Before release, manually smoke-test at least one real figurine key/lock pair. The overnight branch build remains a test artifact, not a release claim.

## Deferred extensions

- analytic cylindrical connector alignment;
- noisy scan plane fitting;
- automatic connector discovery from arbitrary clicks on the whole figurine;
- deliberate insertion-depth inference from a rim or hard stop;
- separate QuickSnap Neo branding or parallel-install packaging.
