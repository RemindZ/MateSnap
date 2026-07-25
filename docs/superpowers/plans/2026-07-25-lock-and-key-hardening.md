# Lock and key hardening — implementation plan (v2, post-review)

Date: 2026-07-25
Branch: `quick-snap-neo`
Baseline commit: `8380c78` (worktree clean, all 9 `lock_key_regression` cases passing)

Fixes defects found reviewing the Lock and key feature. Findings were raised in review, then
independently verified by Codex (session `019f98d1`); v1 of this plan was then reviewed by Codex
(session `019f98e5`), which rejected four of eight phases with probe evidence. This is v2.

Sources: raw findings in `scratchpad/findings.md`; design spec
`docs/superpowers/specs/2026-07-23-lock-and-key-mode-design.md`; original plan
`docs/superpowers/plans/2026-07-23-lock-and-key-mode.md`.

---

## Reconciled finding set

| ID | Verdict | Note |
|---|---|---|
| C1 | CONFIRMED (scoped) | Only geometry-changing modifiers break it, not "entirely". |
| C2 | CONFIRMED | See discrepancy note below. |
| P1 | CONFIRMED | Round connectors are a design non-goal — fix is to fail **fast**, not to support them. |
| P2 | CONFIRMED | 111–150 ms per extraction, three per mate. |
| P3 | CONFIRMED | — |
| P4 | PARTIALLY CORRECT | `scene.ray_cast` is not a drop-in: no selected-only filter, always evaluated. My "fixes C1 for free" claim was wrong. |
| L1 | CONFIRMED | — |
| L2 | CONFIRMED | Spec line 54 allows a click on a connector "side, tip, or nearby rim"; line 38 makes the target header say "click inside the target lock". |
| L3 | CONFIRMED | — |
| D1–D4 | CONFIRMED | **Except `depth_hint`** — see D4 below. |
| D5 | PARTIALLY CORRECT | Zero-area guard is a spec requirement (line 74) — keep it. "~200 lines of duplication" **withdrawn**; the separation is deliberate per the approved design. No dedup refactor. |
| D4 (`depth_hint`) | **WITHDRAWN** | Spec line 76: "The normal sum is a depth-axis hint for tapered pairs." It is a spec-mandated field and is likely part of the missing Phase 5 orientation check. Do not remove. |
| N1 (new, from Codex) | CONFIRMED | Descendants of selected objects can be picked as the target lock and are then carried along by the mate. |

**C2 discrepancy.** The v1-plan review states "the authoritative prior verdict refuted C2". That is
contradicted by the verification pass's own table, which recorded C2 as **CONFIRMED** with the full
trace (`:908-915` → `:934-963` → `:30-137` → `:1044-1050` → `:730-733`, `np.empty` at
`quicksnap_snapdata.py:267`). The first verdict matches the source; C2 stays CONFIRMED. Noted here
so the disagreement is on the record rather than silently resolved.

### N1 in full

`raycast_lock_key_surface` (`quicksnap.py:596-605`) filters on `obj.name in self.selection_objects`
— direct names only — but `apply_world_delta_to_selection` (`:671-679`) moves selected **roots**, so
every descendant moves too. Codex probe: `DESCENDANT_TARGET_HIT=UnselectedChild`,
`DESCENDANT_MOVED_WITH_KEY=True`. The mirrored half: an unselected connector mesh parented to the
selected key **cannot** be clicked as the source, though it will move.

### Spec-coverage gap

Design spec regression item 9 — "non-uniform object transforms and evaluated modifiers produce
correct world-space results" — was never written. Every existing case passes
`SimpleNamespace(ignore_modifiers=True)` against modifier-free meshes. That is exactly how C1
shipped undetected.

---

## Design fork, resolved: Option A (hybrid)

v1 chose Option B (lock the feature to evaluated geometry, disable the *Ignore modifiers* toggle
while Lock and key is active). **Rejected.** Spec line 44 is an explicit contract:

> Use evaluated meshes unless `ignore_modifiers` is enabled. The face index used for feature
> extraction must come from the same raw/evaluated geometry that produced the stored hit.

Option B violates that and silently changes the global "Ignore modifiers (For heavy scenes)"
behaviour (`quicksnap.py:1457`). It would be an unapproved product change, not hardening.

**Chosen: Option A, hybrid.**
- `ignore_modifiers` off (default): evaluated geometry, fast paths as in Phase 2.
- `ignore_modifiers` on: base-mesh `BVHTree.FromPolygons` picking, so the index and the hit come
  from the same raw mesh the solver reads.

Cost is paid only when the user explicitly asks for raw geometry, and is bounded by a world-AABB
ray broad-phase plus lazy per-object BVH construction. Local-space BVHs survive object moves and are
invalidated on topology change. Codex probe B confirms the mechanism: base 6 polys / evaluated 12,
`Object.ray_cast` → face 11 (raw seed count 0, solver returns `None`), base BVH → face **5** at the
identical world point.

---

## Phase 1 — Regression coverage that actually reproduces C1

v1 was NEEDS CHANGE: `SUBSURF`/`BEVEL` can turn a supported planar connector into unsupported
rounded geometry, and asserting only "the index resolves to a real seed" misses C1's
wrong-but-in-range and wrong-anchor modes.

1. Use a **planar topology-changing** modifier — `TRIANGULATE` — so the connector stays supported
   while base and evaluated indices diverge (probe B: 6 → 12 polygons).
2. `assert_modifier_path_is_consistent()`: capture index *and* location from the actual operator
   raycast path, then run the **complete** pipeline (raycast → seed → extraction → transform) and
   assert the final transform, not index validity. Exercise modifiers independently on the source
   and on the target.
3. `assert_non_uniform_transform_mate()`: non-uniform scale on the key, mate within tolerance
   (spec item 9, second half).

**These must be RED before Phase 2.** That failure is the C1 reproduction.

## Phase 2 — C1 + P4 + N1: surface picking

v1 was WRONG on two counts (spec-breaking geometry choice; unsafe modal hide sequence). Rewritten.

1. **Moving set.** In `initialize_lock_key`, compute once:
   `lock_key_moving = {roots} ∪ {every descendant}` via `keep_only_parents` + `children_recursive`.
   Store names. Fixes both halves of N1.
2. **No hide/unhide.** v1 proposed the `quicksnap.py:496-512` hide dance. Rejected — spec line 33
   forbids hiding the selected part between clicks, and Codex probe A shows the mechanism is unsafe
   regardless: hiding drops objects from the selection, unhiding does **not** restore it
   (`UNHIDE_BEFORE_RESELECT selected=[]`), and unconditional `hide_set(False)` wrongly reveals a
   descendant that was already hidden (`PREHIDDEN_DESCENDANT ... after_hide_true_false=False`).
   Instead: **advance the ray.** Call `scene.ray_cast`; if the hit object is in `lock_key_moving`,
   restart the cast from just past the hit point and repeat, bounded by a small iteration cap. No
   scene state is mutated, so nothing needs restoring and no `finally` can be forgotten.
3. **Source phase** keeps the per-object loop (the moving set is small and `scene.ray_cast` cannot
   filter to it), iterating `lock_key_moving` rather than `selection_objects`.
4. **Geometry source** per the hybrid: evaluated `ray_cast` when `ignore_modifiers` is off; cached
   base-mesh `BVHTree.FromPolygons` in local space when it is on. Target phase gets a world-AABB
   ray-slab broad-phase before any BVH is built.
5. **Store the hit normal.** Spec line 32 requires the recorded hit to include the face normal;
   the implementation currently discards it (`quicksnap.py:617-629` stores name/index/location
   only). Record the world-space normal on both clicks. Phase 5 depends on this.

Tests: Phase 1 goes GREEN; plus separate cases for source-descendant **acceptance** and
target-descendant **rejection**; plus a case asserting no object's `hide_get()` or `select_get()`
changes across a preview raycast.

## Phase 3 — P2 + P3: cache for solving, never for validation

v1 was WRONG: it had the finish-time signature read from the cached extraction, so a changed source
would compare equal to itself and the stale-geometry guard would never fire — contradicting
`quicksnap.py:533-592` and the existing mutation test at `tests/lock_key_regression.py:374`.

1. Cache the source extraction **for solving only**: `{'mesh_data'}` keyed by object name, cleared
   in `initialize_lock_key` and `terminate`.
2. Before reusing it, compute a **fresh, cheap fingerprint** read directly from the live mesh —
   vertex/edge/polygon/loop counts plus the relevant polygon's vertex coordinates and the world
   matrix — and discard the cache on mismatch. Cheap and current, never derived from the cache.
3. `compute_lock_key_transform` gains optional `source_mesh_data` / `target_mesh_data` parameters so
   `quicksnap_utils` stays free of operator state.
4. `finish_lock_key`: guard the `current_signature` call behind
   `if source.get('geometry_signature') is not None:` (P3).

Target: one full source extraction plus one cheap fresh validation per mate, down from three full
extractions. Test: the existing mutation case must still fail closed **with the cache enabled**,
plus a monkeypatched counter asserting one `_mesh_fit_data` call per object per mate.

## Phase 4 — P1: bound the rotation search

v1 step 1 was sound; steps 2–3 were WRONG. Codex probe C: nearest-only bucketing returned **zero**
matches where the existing code returned one — the nearest pair had insufficient clearance and the
farther one was the only viable match. Probe D: a clean rotated rectangle yields **9 pairs / 6
buckets**, not the 2–3 I claimed, because orthogonal normals land at `90.000001°` and pass the
strict `dot < 0` test.

1. `itertools.combinations(source_pairs, 2)`, target side stays `permutations`. Behaviour-preserving,
   exactly 2× saving (the mirrored ordering is currently discarded by the `np.allclose` dedup only
   *after* paying for the SVD).
2. Reject near-adjacent normals by **angular tolerance** rather than strict `dot < 0`. Apply this in
   the rotation pre-filter only, not inside `_connector_side_pairs`, so the translation path is
   untouched.
3. Apply cheap rotation-invariant compatibility checks — opening angle, positive clearance —
   **before** any bucketing.
4. If more than one viable non-equivalent pair remains on an axis, **fail the whole rotation
   closed**. Do not pick the nearest; do not drop the constraint.
5. If either resulting list still exceeds 8 pairs, `return []`. Never truncate and continue.

Test: a deterministic bound on `_fit_connector_rotation` call count (timing stays a probe, not a
flaky assertion). All 9 existing cases must resolve identically.

## Phase 5 — L2: the floor click, without accepting a flipped key

v1 was WRONG, and this is the most serious item. Dropping the mixed-anchor break does admit the
intended source-wall/target-floor case — but Codex probe E shows it also admits an
**insertion-axis-flipped** rotation, and since ranking is by smallest angle, a key that starts near
the flipped orientation makes the wrong answer win:

```
NORMAL_START   valid=[(39.5°, depth (0,0,-1)), (157.2°, depth (0,0,+1))]  chosen depth=(0,0,-1)  correct
FLIPPED_START  valid=[(16.8°, depth (0,0,+1)), (169.2°, depth (0,0,-1))]  chosen depth=(0,0,+1)  WRONG
```

That is a key pointing out of the socket, and it violates spec line 96: smallest-angle ranking
applies only to *geometrically equivalent* candidates; a non-equivalent ambiguity must fail closed.

1. Relax the mixed-anchor gate: when either side lacks `anchor_side`, enumerate both swap options —
   the branch the both-`None` case already uses. Keep the `!=` swap when both are anchored, and keep
   the "at least one source pair is anchored" guard.
2. **Add an insertion-direction constraint before ranking**, using the world-space hit normals stored
   in Phase 2 (and `depth_hint`, which spec line 76 defines for exactly this): reject any candidate
   whose rotated source insertion direction opposes the target's floor/rim normal.
3. If no reliable depth cue is available for a given pair, the floor case **stays fail-closed**. A
   feature that silently does nothing is acceptable; one that inserts the key backwards is not.

Tests: floor-click positive case resolving to the same transform as the wall click, **and** a
flipped-insertion negative case asserting `None` (the `FLIPPED_START` fixture above).

## Phase 6 — L1 + L3 + C2: recovery paths

v1 NEEDS CHANGE on both mechanics.

1. **L1.** Auto-reset to `State.IDLE` and clear `lock_key_source_hit` when `finish_lock_key` fails on
   a changed signature. Add **`BACKSPACE`** as the explicit un-pick transition and put it in the
   header text. Not a second `ESC` — spec line 36 reserves `ESC` for cancelling the operation.
2. **L3.** v1 restored the preference *after* teardown, which cannot revive already-destroyed modal
   state (`switch_lock_key_mode:934-946` reverts data and clears SnapData before calling
   `initialize()`). Make the switch **transactional**: preflight the requested mode — mode, selection,
   and anything else `initialize` would reject — and bail before any teardown, leaving the live
   SnapData and preference untouched.
3. **C2.** Reset `current_state`, `closest_source_id`, `closest_actionable` in `switch_lock_key_mode`
   after preflight succeeds and before normal `initialize()` calls `update()`. Kept in
   `switch_lock_key_mode` rather than `initialize()` so the normal invoke path is untouched.

Test: a failed switch preserves the original live SnapData, the preference value, and modal state;
a successful switch resets all three fields.

## Phase 7 — D1–D3: dead code

Remove `lock_key_original_matrices` (both sites), `_match_connector_pairs`' unused `rotation=None`,
`_validate_lock_key_transform`'s unused `insertion_axis=None`, and the connector `'mid'` field.

**Keep** the zero-area/extent guard (spec line 74) and **keep `depth_hint`** (spec line 76 — it is
the tapered-pair depth-axis hint and is load-bearing for Phase 5). No dedup refactor.

## Phase 8 — Verification

1. `python -m py_compile` on every changed file.
2. `blender -b --factory-startup --python tests/lock_key_regression.py` — all cases, old and new.
3. `blender -b --factory-startup --python tests/precision_fit_regression.py` — no regression in the
   shipped feature.
4. Timing/behaviour probes: rotation-work call-count bound, one-extraction-per-object-per-mate,
   phase-2 raycast cost, no hide/selection mutation during preview.
5. `git diff --check`, then `git status --short`.
6. CHANGELOG.md under `Unreleased - QuickSnap Neo`: a `### Fixed` block covering the raw/evaluated
   mismatch, the mode-switch state leak, the moving-descendant target, the rotation freeze, and the
   floor-click rotation rejection.
7. Leave the work **uncommitted, with only intended changes**, for manual smoke testing on a real
   figurine key/lock pair — the design spec requires that before any release claim. Do not push, do
   not open a PR.

---

## Order and rationale

Phase 1 first so C1 has a genuine RED. Phase 2 carries the geometry contract and stores the normals
Phase 5 needs. Phases 3–4 are contained. Phase 5 is gated on Phase 2's normals and Phase 4's bound.
Phase 6 folds C2 in where it belongs. Phase 7 is cosmetic and last so it never obscures a real diff.
Every phase ends green before the next starts.

## Explicitly out of scope

- Supporting round/cylindrical connectors (design non-goal; Phase 4 only makes them fail fast).
- Refactoring the connector helpers against the precision-fit helpers (withdrawn after review).
- Removing `depth_hint` (withdrawn — spec-mandated).
- Any push, PR, or release packaging.

## Implementation outcome (2026-07-25)

All eight phases implemented. `lock_key_regression` 17/17 and `precision_fit_regression`
17/17 green on Blender 5.0.1; `py_compile` and `git diff --check` clean.

Measured:

| | before | after |
|---|---|---|
| rotation search, 16-sided peg | 19,660 ms | 0.08 ms (0 Kabsch solves) |
| rotation search, 32-sided peg | > 10 min | 0.54 ms |
| source mesh extractions per mate | 3 | 1 |
| target preview raycast, 400 objects | 1.10 ms | 0.16 ms |

### Where implementation diverged from the plan

**Phase 5 — the floor click still fails closed.** The plan intended to enable it.
Implementing it revealed the actual blocker is not the anchor gate but
`_validate_lock_key_transform`'s lateral-correction cap
(`min(0.25 * source_width, 2 * clearance)`): a click on a connector wall and a click
on a socket floor are far enough apart laterally that the required correction
exceeds the cap. Raising that cap is what lets the tool slide a key somewhere the
user did not point at, so it was left alone — that is a design change, not
hardening.

What did ship from Phase 5, and why it still matters:

- The mixed-anchor gate is relaxed, but only when the caller supplies the target
  face normal (`allow_mixed_anchor=target_normal is not None`). Without a normal
  nothing constrains the insertion axis, and a probe confirmed the flipped
  candidate is accepted (`depth_z=+1.000`) if the relaxation runs unguarded. The
  relaxation and its guard are coupled in code so the safety property cannot be
  lost by a caller omitting an optional argument.
- `_buries_key_behind_target` rejects candidates that seat the connector behind the
  clicked surface.
- Smallest-angle ranking now only applies between candidates that seat the *mated
  walls* identically; anything else fails closed as ambiguous. Keying this on all
  source pairs (rather than matched ones) was tried first and wrongly rejected the
  legitimate wall click, because it included pairs that play no part in the mate.
- The header no longer says "click inside the target lock". It names the connector
  wall, which is what reliably works, and mentions Backspace.

Net: the P0 in this area — a rigid match seating the key pointing out of its socket
— is fixed and regression-tested. L2 remains a feature that fails closed on a floor
click, but it now does so honestly and the UI no longer directs users to it.

**D4 withdrawn.** `depth_hint` is kept: spec line 76 defines it as the tapered-pair
depth-axis hint. The zero-area guard is kept for the same reason (spec line 74).

**Not attempted.** Option A's world-AABB broad phase is implemented for raw picking,
but raw-mode BVHs are only built for objects the ray actually crosses; a scene swept
end to end can still accumulate one tree per base mesh. That is the bounded cost the
review accepted, not an unbounded one, but it is worth watching on very large scenes.

## Known unverified

Undo-stack restoration after the modal completes could not be verified headless
(`bpy.ops.ed.undo()` fails its context poll in background mode). The operator declares
`{'REGISTER', 'UNDO'}` and the matrix write precedes the `FINISHED` return, which is the documented
requirement, but this needs the manual smoke test to confirm.
