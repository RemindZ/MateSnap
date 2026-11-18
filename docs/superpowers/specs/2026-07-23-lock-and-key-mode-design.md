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

Amended 2026-08-07 (evening): lock-key mesh data is extracted region-first. A sphere around the click, starting at 5% of the part's bounding diagonal, is extracted instead of the whole mesh; any patch or seed that touches polygons the sphere cut open raises a widen signal, the radius doubles, and past 30% the build falls through to full coverage -- so every measurement the solver reads always comes from whole patches and the region is behaviour-invisible, verified by a regression test asserting delta equality against full coverage. Lock-key data also stops reading Blender's edge tables entirely (the single most expensive reads): edges are synthesised from the corner table and centers and normals are computed from coordinates, for the region's polygons only. Their ids are private to that extraction, so MIDPOINT seeds are refused against it; lock and key seeds faces only. Clicks on large flat faces widen to full coverage by design -- the surrounding organic surface is what keeps a figurine connector's region small. Measured at 1.8M triangles: 1.75s whole-mesh before, 1.10s region cold click after, at the floor set by Blender's bulk coordinate and corner reads.

Amended 2026-07-29: two hops is the starting radius, not a fixed one. Lock and key widens up to ten when a click yields no opposed wall pair at all, and stops at the first radius that yields one. Two hops reaches the far wall of a plain box peg, but every chamfer or fillet ring around an edge inserts another hop, so a well-modelled connector -- the common case in a real kit -- put its opposite wall permanently out of reach and reported that the click had landed on nothing.

Amended 2026-08-09: patch growth is bounded to five degrees of drift from its seed's normal, and the widening limit rises from ten hops to thirty. The pairwise-only crawl admitted unlimited cumulative drift, so once a sculptor's fillet was tessellated finer than five degrees per face the crawl walked the whole arc, failed the global flatness gate, and returned nothing -- making the fillet an impassable moat around the connector, or, denser still, drowning the flat walls themselves in the failed component (a field-reported rectangular socket with generously rounded fillets produced zero patches at its click). With the bound, a fillet fragments into strip patches of at most ~10 degrees of arc regardless of tessellation -- stepping stones again, exactly as the sliver-floor rule above assumes -- but crossing two such fillets wall-to-wall costs ~two dozen hops, which is what the raised limit pays for. A flat wall's own normals wobble by fractions of a degree, so the bound never splits a wall; genuinely curved surfaces still fail closed, now as strips caught by the too-many-pairs curve test instead of as silent absences.

Reaching across trim is not the same as mating against it. Patches at least a tenth the area of the clicked one are preferred when forming a pair: traversal still crosses the fillet strips, but a sliver does not become a connector wall. That floor is a preference, not a rule -- it is dropped if it leaves the click with no pair at all, since a connector whose far wall is genuinely much smaller, or whose clicked patch merged with a large coplanar body face, must not be refused for the sake of a filter that exists only to exclude bevel slivers. Without that rule the strips dominate. A rounded edge yields dozens of them, each a plausible opposed pair on its own diagonal axis, and because a candidate whose two best targets tie is discarded as ambiguous, near-identical slivers tie constantly and delete the real wall match. The observed effect was a mate refused for holding thirteen matched pairs, not one of which involved an actual wall.

Amended 2026-08-03: a click is called "on a flat face rather than a connector" only when nothing of comparable size faces it AND nothing connector-sized is within reach. Two substantial walls facing each other near the click are a connector whether or not the clicked wall is one of them -- a neck or a shoulder is cut flat across, and clicking that cut still reaches the peg beside it, with centring putting the anchor between its walls. Judging the clicked wall alone made the verdict unfalsifiable whenever the parts were not yet aligned, since any flat cut has nothing facing it; the refusal then blamed the click in exactly the case where the user needed to be told to rotate.

Amended 2026-08-03: rotation stays opt-in, but the consent is a keystroke. R during the mate toggles "Rotate key to match lock" and retries immediately. The refusal that asks for rotation otherwise asks the user to leave the modal, find a checkbox that is only drawn while Lock and key is enabled, and repeat both picks.

Amended 2026-08-03: the fallback may add a lateral direction the floored pass left unconstrained; it may never replace what that pass found. Both passes restart at two hops, so the fallback can complete its picture close to the click while the floored pass needed six or eight hops to cross to the far wall -- and the trim near a socket mouth is opposed on two axes of its own. Preferring the fallback wholesale therefore handed the matcher a chamfer ring opening 110 degrees in place of the wall pair opening 180 that the floored pass had already found, and the mate was refused for a taper mismatch between a real wall and a lead-in.

Two bounds keep the widened walk honest. The unfloored fallback stops once it has reached several hundred patches without success, since its pairing is quadratic in every sliver it re-admits. That budget does not apply to the floored pass, whose pairing only ever sees substantial walls -- a handful even on a part with thousands of patches -- and which was otherwise stopped long before it could cross to the far wall, on exactly the dense parts that need the reach most. And a radius that produces more than a few dozen opposed pairs is a curve rather than a flat-sided connector, and fails closed immediately -- a rounded click otherwise reaches the far side of its own curvature and generates them by the thousand, which is meaningless and quadratic in the matcher.

Standard precision fit is unaffected: `_candidate_patches` keeps its two-hop default and its unfiltered patch list.

### Supported shapes

- rectangular/prismatic pegs and sockets;
- flat-sided slots;
- flat-sided pegs and sockets that taper along insertion depth, including trapezoidal profiles.

Round, cylindrical, spherical, noisy organic, incomplete, and ambiguous connectors are non-goals for this version.

Amended 2026-11-11: one exception -- a round peg clicked on its flat end and seated on the flat floor of a round hole is mated by sliding alone; see the (sixth) amendment under the transform. Amended 2026-11-12: with rotation on it is first squared onto the floor by the smallest turn; see the (seventh) amendment. Solving a round connector's axis or spin remains a non-goal.

### Side-pair descriptors

Standard precision fit keeps its strict 170-degree opposed-wall rule. Lock and key uses a separate connector-pair descriptor so it can recognize stronger depth taper without weakening standard snapping.

Form a connector side pair when:

- both patches are clean and planar;
- their outward normals face away from one another by at least 95 degrees, excluding adjacent faces;
- their normal difference defines a stable lateral direction;
- the clicked point projects within the pair's lateral interval plus flatness tolerance;
- neither patch has zero area or extent.

Amended 2026-08-03: the key's taper must agree with the lock's within 10 degrees, not 5. Each wall is already allowed 10 degrees from anti-parallel, and an opening is the difference of two such measurements, so the tighter figure was stricter than the test beside it and rejected connectors whose walls are a handful of merged fragments each. The rotation path suffered twice over: it needs two matched pairs, so one pair dropping out on a few degrees of measurement failed the whole mate. A chamfered lead-in still reads 40 to 60 degrees from the wall it sits on and is still refused.

Amended 2026-07-29: the opposition rule carries a 95-degree margin rather than asking only for a negative dot. A clean corner has a dot of exactly zero and was excluded by arithmetic alone; a corner with any modelling noise lands either side of zero, so half the corners in a neighbourhood became plausible pairs on 45-degree axes. They crowd out the real walls, and because the search stops at the first radius that yields any pair, they also stop it widening to reach the far wall.

Amended 2026-07-29: patches are grouped by plane before pairing, so a wall that arrives cut into fragments is treated as the single wall the modeller drew. The growth step cannot do this on its own -- its offset allowance scales with edge length, and a finely cut wall has tiny edges, so sub-millimetre wobble stops it merging. Without grouping, a click on a fragmented wall lands on one sliver, every neighbour faces the same way, and the opposite wall is hundreds of fragments away: further than any affordable search, and indistinguishable from a curve. Merged walls recompute their own tolerances, whose residual is the real spread of the fragments about the plane.

Amended 2026-07-29: whether the two walls are measurably apart is judged against the precision tolerance, not the flatness allowance. The allowance is 0.5% of a patch's extent, so on a broad thin tab it exceeds the tab's own thickness and discards the thin-axis pair -- the one axis such a connector needs centred. The mate then still succeeds on the remaining axes and silently leaves the part uncentred, which is worse than refusing. Flatness still governs the questions it belongs to: whether the click lies within the pair's lateral interval, and how far a wall may sit off its plane.

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

Amended 2026-08-07: a click on mouth trim is promoted to the wall the trim softens, as part of the same centring preference. A chamfer or lead-in is a narrow strip -- its mean width no more than a quarter of its extent -- whose plane roughly bisects a much larger neighbouring face (25 to 65 degrees off, at least twice its area); a dovetail flank or V-groove side is broad and never qualifies. An anchor left on such a strip sits laterally outside the walls, so the real pair cannot span the click and only the trim's own pair survives: the reported failure measured a straight key against the chamfer's 100-degree opening and refused a fitting part -- or worse, mated on a perpendicular axis alone and silently seated the key half a chamfer off. Promotion therefore runs BEFORE the direct solve, not as a retry after it, because the wrong mate never reaches a retry. Which bisected face was meant cannot be read locally -- the strip splits its corner symmetrically -- so every candidate wall is tried and the mate decides: one seating wins, several different seatings fail closed, and none at all falls through to the direct solve and its existing refusals. Turning `lock_and_key_centre_picks` off disables promotion with the rest of pick centring.

Amended 2026-08-08: the target preview dot slides to the hovered wall's centre once the cursor rests for 0.2s, so the point shown is the anchor a centred mate will actually use. It is computed at rest rather than per move -- sweeping never stalls -- and the extraction it needs is the same one the click would pay, so aiming pre-pays the click. With centring off, or where no clean patch exists, the raw dot was already honest and stays.

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

Amended 2026-11-12 (seventh): the end-face seating squares the key when rotation is on, admits connectors with faceted rounded sides, and the wall solve's translation path no longer seats a tilted key. Field reports on 2.3.0: a saber's hilt end clicked onto the floor of its hand's socket refused because the saber lay 97 degrees off, with rotation on; a cloth panel's peg end clicked onto its socket floor in the legs refused "spatial recovery ineligible: the local wall axes are ambiguous". With rotation on, the key is now turned by the smallest rotation that lays its end face antiparallel to the floor -- the rotation path's own requirement that the clicked faces rest against each other -- about the end face's centre, then slid as before; the smallest turn keeps the user's spin about the axis, which is still never solved, so a wrong spin is refused by the overlap test exactly as a wrong slide is (field cloth peg: as placed 0.008 against 0.128; spun 90 degrees, buried 1.70; 180, 2.38). With rotation off the five-degree tilt bar is unchanged. Admission also accepts an end-face click whose lateral wall pairs -- those across the clicked normal -- are ambiguous in the rotation path's sense: two pairs on one axis disagreeing on their walls is a flat side opposed by a fan of facets, the sides of a rounded connector seen from its end. Checking that on a D-shaped fixture found a fail-open in every release to 2.2.1: matched side walls pin nothing about a tilt about their own axis, so the translation path seated a key tilted 25 degrees as it stood, through a 0.06 clearance socket. A translation keeps orientation, so it is now accepted only when the clicked patch faces rest against each other within ten degrees, the bar the rotation path applies to its candidates; otherwise rotation, when on, takes over, and when off the refusal names the angle. A slide within the ten degrees still keeps the residual tilt, as it always has.

Amended 2026-11-11 (sixth): round connectors clicked end face to end face are seated by sliding, never rotated. Field report: a signpost's round post clicked on its flat end and its base's round hole clicked on its flat floor refused "the key click is on a curved surface ... rounded connectors are not supported", then a recovery-path line the user could not act on -- while the parts had been placed correctly and only needed pushing together. A round peg needs nothing the wall solve provides: the centroids of the clicked end faces lie on the peg's and the hole's axes, so sliding one onto the other centres and seats it, and the user's orientation is kept as it stands whatever the rotation setting -- a round connector has no spin to correct, and one cut on the slant (the field post leans about forty degrees through both flat faces) has a spin only the user's placement knows. Admission is narrow and runs only after the wall solve has refused: at least one click must have been refused as curved, both clicked faces must be flat patches lying face to face within five degrees, and the translated key, sampled over twice its end face's extent, must stay out of the lock's material within the surroundings survey's allowance (four times the larger end face's flatness tolerance). Containment is a two-of-three ray-parity vote, because the lock's surface is cut out of a larger part and one ray can leave through that cut. The outline's roundness is deliberately not judged: a sculpted floor ringed by a fillet measured twenty percent off an ellipse, as far as a square does, while a wrong seating of a non-round peg buries its corners and is refused by the overlap test. Every refusal names its gate with numbers -- tilt against the five degrees, or the buried depth and sample count against the allowance -- and replaces the wall solve's reason, which cannot speak to a round connector. Measured on the field pair: as placed, deepest contact 0.087 against 0.122 (the post's rim on the floor fillet); turned twenty degrees about the face normal, buried 1.53; ninety, 3.70; tilted ten, refused by tilt. It never generates a rotation and iterates nothing, so it is not the ICP fallback the design forbids.

Amended 2026-08-10 (fifth): among seatings the connector cannot tell apart, the surroundings hold the veto. Field followup to (fourth): a square-ish peg's equivalent spins resolved to the user's rough placement, which is wrong whenever the part was parked nearest a wrong quarter-turn -- and the sculptor keys the intended spin into the parts around the connector, not into its walls. When more than one equivalent seating survives, up to 512 samples of the key's surface within 2.5 matched-widths of its click are tested against a BVH of the lock's surface within the same reach of its click, under each candidate's full transform. A sample buried inside the lock's material deeper than four times the seating's measurement tolerance makes that seating physically impossible and discards it; the smallest rotation then chooses among the possible. Containment is ray-parity along the lock's clicked-face direction, because signed distance off the nearest face claims the whole half-space behind an open shell's wall. Boundaries of the rule: it is a veto, never a generator -- every candidate still comes from the connector walls, nothing iterates, and the sample count is bounded, so this is not the ICP fallback the design forbids. The survey joins the region contract (a sample sphere touching cut-open data raises the widen signal rather than reading it), and it never refuses: if the surroundings reject every seating they are noise, the survey withdraws, and behaviour is exactly (fourth). Every survey that rules anything out logs one line -- seatings offered, ruled out, deepest overlap vs allowance -- because a wrong spin is a success-path failure the refusal log would otherwise never see.

Amended 2026-08-09 (fourth): when NEITHER click lands on a surviving pair's wall, the clicked faces themselves carry the orientation intent. The natural kit gesture -- reported from the field within an hour of (third) shipping -- is the top of the peg and the floor of the socket; every such face points at the other part (peg top or surrounding parting plane, floor or mouth rim -- all four combinations oppose when mated, which is what makes the gesture forgiving). In that case the enumeration drops the anchored-pair requirement and instead keeps only rotations that bring the clicked key face to rest against the clicked lock face within ten degrees: that pins the insertion alignment and discards every end-for-end flip regardless of taper -- the anchors' job, done by the faces. The face normals are read from the clicked patch (area-averaged, recomputed per face through promotion), not the raycast. The remaining spin falls to step 5, whose equivalence test is now measured, not byte-exact: two candidates are equivalent when every mated wall plane of one has a counterpart in the other within the flatness tolerance that plane was measured at. Exact plane equality never fires on sculpted geometry, so the "choose the smallest equivalent rotation" rule had been dead code in the field; at measured tolerance it does its intended work -- a near-square peg's spins are interchangeable at the precision the parts are built to and the smallest rotation (the user's rough placement) chooses, while a rectangular peg in a square socket still differs by far more than tolerance and still fails closed, resolvable by wall clicks pinning the mapping per (third). Precedence: anchored wall clicks are explicit intent and pin the mapping; face-to-face plus smallest-equivalent is the rough-placement fallback.

Amended 2026-08-09 (third): wall clicks pin the wall correspondence in step 2. A pair is "anchored" when the click landed on one of its two walls; a mapping that pairs an anchored pair with an unanchored one is enumerated only when one of the two parts has no anchored pair at all -- that licence exists solely for the documented floor click inside the lock, whose insertion-axis guard discards the end-for-end flip. It was previously granted whenever the target normal was available, which in the GUI is always, so the enumeration was free to ignore the anchors even when both clicks named a wall -- and on a near-square connector (a sculpted kit peg is never exactly square, so no two of its seatings are ever byte-equivalent under step 5) every 90-degree seating survived to the tie and the mate was refused as ambiguous however the user clicked. With the pin, the clicks are the disambiguation: click a side wall of the key's connector and the lock wall it should rest against. Three refusals now name their cause instead of falling through to the generic seating message: a key click that anchors no pair (an end face or parting plane names no wall) is told to click a side wall; a clicked key wall that fits no lock wall, and a clicked pair of walls that cannot mate each other, are told so; and the generic message itself now appends how many candidate rotations were enumerated and which gate discarded them, because an empty enumeration spent a field session misreported as "penetrating the lock".

Amended 2026-08-09 (second): the solve balances the largest mutually consistent subset of the matches, not necessarily all of them. A sculpted connector matches more pairs than a rigid translation has freedoms -- corner bevels, taper segments, near-parallel duplicates of a wall -- and their centres never agree to within flatness tolerance the way a symmetric test part's do; demanding every match centre at once refused honest kit parts on two kits in one day (four matched pairs each, axes agreeing to a degree). When the full set fails validation, pairs are re-admitted greedily in order of each pair's smaller wall -- a pair is only as reliable as its lesser wall, so a disagreement between a wall pair and a corner-bevel pair is the wall's to win, never an ambiguity between peers; a genuinely ambiguous same-rank alternative feature is already discarded by the matcher's tie rule. "Validate against the exact patch correspondences used to solve" below therefore reads: clearance imbalance must finish within tolerance for the pairs used to solve; every matched pair, used or excluded, must still hold non-negative clearance under the final translation -- an excluded pair left un-centred is designed clearance, an excluded pair driven into the material fails the mate. Rotation candidates rank their two-independent-axes requirement over the used subset, since a rotation held by one balanced axis plus discarded extras is held by one axis.

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
