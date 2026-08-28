# Disconnected-Floor End-Face Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make valid centered peg-end/socket-floor Lock-and-key rotation work when the clicked floor is topologically disconnected from its side walls, without guessing spin or weakening existing wall-click validation.

**Architecture:** Preserve topology-local connector discovery as the primary path. Add a private, symmetric cold-path helper that spatially recovers exactly one coherent missing-side connector frame from source-derived bounds, then feeds those pairs through the existing rotation and validation pipeline. Region extraction widens to full coverage before spatial absence is trusted.

**Tech Stack:** Blender 5.0 Python API, `mathutils`, NumPy, existing MateSnap mesh-fit/Lock-and-key helpers, headless Blender regression scripts, PowerShell release builder.

## Global Constraints

- Blender 5.0+ only; keep the legacy `bl_info` add-on format.
- Keep Precision fit and Lock and key as separate solvers; do not merge `_plane_pairs` with `_connector_side_pairs` or their matchers.
- Do not change the shared `_mesh_fit_data` → `_grow_planar_patch` → `_candidate_patches` layer unless this plan explicitly requires it; it does not.
- Fail closed for ambiguous, curved, organic, incomplete, stale, or underconstrained geometry.
- Clicked normals constrain insertion alignment only; they must never generate spin.
- Explicit anchored wall clicks remain topology-local and continue to pin correspondence.
- Recovery must be symmetric when either source or target lacks the disconnected frame.
- Use `fit_tolerance` for clearance and separation; patch `tolerance` remains a flatness allowance.
- Never request a user model; diagnostics must explain recovery eligibility, filtering, frame count, and refusal reason.
- No new dependency, persistent scene-wide index, generic constraint framework, or ICP path.
- Run both Lock-and-key and Precision-fit regression suites.
- A manual real-figurine smoke test is required before a release claim.
- This fix releases as 2.2.1; do not overwrite `releases/MateSnap-2.2.0.zip`.

---

### Task 1: Lock down the disconnected-floor failure

**Files:**
- Modify: `tests/lock_key_regression.py:70-1100`

**Interfaces:**
- Consumes: `quicksnap_utils._mesh_fit_data`, `_seed_polygons`, `_connector_pairs`, and `compute_lock_key_transform(...)`.
- Produces: `disconnected_floored_lock(...)` fixture and `assert_disconnected_floor_end_face_rotation()` regression.

- [ ] **Step 1: Add a disconnected-floor fixture**

Create a rectangular socket fixture equivalent to the existing connected `floored_lock`, but duplicate the four floor vertices so the floor polygon shares no vertex or edge with any wall. Return the object and floor face index. Keep the existing connected fixture unchanged.

- [ ] **Step 2: Assert the exact pre-fix signature**

Within `assert_disconnected_floor_end_face_rotation()`, build a rectangular key and disconnected-floor lock, create world-space mesh-fit data and face seeds, and assert the ordinary topology-local connector search returns at least two independent source axes and zero target pairs. This assertion prevents a future fixture change from accidentally reconnecting the floor.

- [ ] **Step 3: Assert the user-visible behavior**

Apply a non-axis-aligned rigid transform to the key. Call `compute_lock_key_transform(..., allow_rotation=True, source_normal=world_normal(key, key_face), target_normal=world_normal(lock, floor_face))`. Assert the result is not `None`, finite, laterally centers the connector, preserves the target floor insertion coordinate, and brings the clicked face normals into opposition within the existing ten-degree allowance.

- [ ] **Step 4: Register the regression in `main()`**

Add the assertion and a `<case>: PASS` print beside the existing end-face case.

- [ ] **Step 5: Run the focused assertion and verify RED**

Run a throwaway Blender script that imports `tests/lock_key_regression.py` and calls only `assert_disconnected_floor_end_face_rotation()`:

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python-expr "exec(open('tests/lock_key_regression.py').read().replace('main()', 'assert_disconnected_floor_end_face_rotation()', 1))"
```

If that expression proves brittle because of the file's final `main()` call, create a temporary script outside the repository that imports the module and calls the assertion. Expected: FAIL because the transform is `None` after the direct `2 source / 0 target` result.

- [ ] **Step 6: Commit**

```bash
git add tests/lock_key_regression.py
git commit -m "test: reproduce disconnected socket floor rotation"
```

---

### Task 2: Recover one coherent missing connector frame

**Files:**
- Modify: `quicksnap_utils.py:1020-1900,2678-2860`
- Test: `tests/lock_key_regression.py:850-1150`

**Interfaces:**
- Consumes: existing connector pair descriptors, `_connector_side_pairs(patches, anchor)`, `_independent_axis_count(pairs)`, `_prune_rotation_pairs(...)`, patch-plane tolerances, and `LockKeyRegionTooSmall`.
- Produces: private `_recover_spatial_connector_frame(...) -> (pairs, reason)` and an eligibility helper returning the known/missing side or no recovery.

- [ ] **Step 1: Add recovery isolation regressions**

Add tests that monkeypatch `_recover_spatial_connector_frame` to raise if called and prove it is not called for:

- rotation disabled;
- an anchored wall-to-wall rotation;
- missing clicked patch normals;
- a directly connected end-face/floor fixture whose ordinary search already has two axes on both sides.

For the anchored case, capture the baseline delta before monkeypatching and assert the guarded call produces the same delta.

- [ ] **Step 2: Add eligibility helper**

Implement a private helper immediately before rotation enumeration that receives the pruned source/target pairs and clicked patch normals. It returns recovery metadata only when rotation is enabled, neither click anchors a usable lateral pair, exactly one side has at least two independent axes, the other side does not, and the known axes are compatible with the known clicked end-face normal. Exclude end/base pairs by applying the existing rotation pruning before classifying anchors.

- [ ] **Step 3: Derive a bounded world-space search volume**

From the known-side pairs, compute finite lateral and axial reaches using measured widths, extents, clicked-face relationships, and existing tolerances. Refuse inconsistent/ambiguous known dimensions rather than averaging them. Represent the volume as a clicked-normal-aligned finite prism or cylinder and use polygon/patch bounds intersection rather than centroid inclusion.

- [ ] **Step 4: Spatially prefilter candidate patches**

For the missing side, collect clean planar geometry that intersects the volume, lies on the connector-interior side of the clicked face, overlaps the floor-adjacent axial band, and passes source-derived reach/size ceilings. Apply spatial and normal filters before coplanar merging. Grow each surviving patch once and deduplicate it.

Do not change `_candidate_patches()` or `_connector_pairs()`.

- [ ] **Step 5: Reuse connector pairing rules**

Call `_connector_side_pairs()` on bounded candidate groups. Filter the resulting pairs against the known frame using opening angle, wall/end-normal relationships, taper/depth hint, width/extent, opposite peg/socket role, and non-negative clearance under existing `fit_tolerance` rules. Require at least two independent axes.

- [ ] **Step 6: Form coherent frame hypotheses**

Group compatible pairs by common inferred lateral center, floor-relative axial overlap, dimensions, taper, and role. Prevent axes from separate cavities or body panels from entering one frame. Deduplicate geometrically equivalent frames using plane normals, offsets, centers, and measured plane tolerances. Return pairs only if exactly one measured-distinct frame remains; otherwise return a specific absence/incompatibility/ambiguity reason.

- [ ] **Step 7: Insert the cold-path adapter**

In `compute_lock_key_transform()`, after ordinary discovery/direct solving and before `_rotation_candidates()`, invoke recovery only when the eligibility helper allows it. Replace only the missing side's pair list. Then run existing pruning, `_rotation_candidates()`, Kabsch, face opposition, centering/clearance, insertion guard, seating equivalence, and surroundings veto unchanged.

- [ ] **Step 8: Request complete extraction before trusting absence**

If recovery is eligible while the provider data is partial, raise the existing widen signal so `finish_lock_key()` retries through `LockKeyMeshProvider`. Require full coverage before returning “no spatial frame.” Reuse the provider retry loop; do not add a second extraction mechanism.

- [ ] **Step 9: Stop repeated doomed topology work**

Once the disconnected end-face/floor eligibility signature is established, route to the bounded recovery path rather than repeating identical 2-to-30-hop searches or centered/raw retries that cannot cross mesh islands. Preserve ordinary widening for connected topology.

- [ ] **Step 10: Run the focused regression and isolation tests**

Run the focused Blender import script. Expected: disconnected-floor case PASS; all recovery-not-invoked assertions PASS.

- [ ] **Step 11: Commit**

```bash
git add quicksnap_utils.py tests/lock_key_regression.py
git commit -m "fix: recover disconnected socket wall frames"
```

---

### Task 3: Prove recovery stays fail-closed

**Files:**
- Modify: `tests/lock_key_regression.py:850-1250`
- Modify if a verified defect requires it: `quicksnap_utils.py:1020-1900,2678-2860`

**Interfaces:**
- Consumes: `_recover_spatial_connector_frame(...)` and `compute_lock_key_transform(...)` from Task 2.
- Produces: adversarial geometry regressions defining the recovery safety boundary.

- [ ] **Step 1: Add underconstraint and decoy tests**

Add fixtures/assertions proving recovery refuses:

- only one independent recovered direction;
- remote parallel walls outside the source-derived volume;
- walls behind the floor on the material side;
- a body shell larger than the allowed connector reach;
- curved/faceted surrounds that exceed existing candidate/pair caps.

- [ ] **Step 2: Add frame-coherence tests**

Add geometry where one candidate axis comes from each of two nearby cavities and assert no hybrid frame is synthesized. Add two complete, compatible, differently centered cavities and assert ambiguity returns `None` rather than selecting the nearest.

- [ ] **Step 3: Add fragmentation test**

Split each logical socket wall into coplanar disconnected fragments within one bounded cavity. Assert recovery deduplicates them to one frame and produces the same seated transform as the unsplit fixture within measured tolerances.

- [ ] **Step 4: Add taper, reversed-order, and transform tests**

Cover a drafted disconnected socket, reversed moving peg/socket order, and non-uniform object transforms. Assert each returns a finite valid transform and preserves the ordinary clearance/insertion invariants.

- [ ] **Step 5: Preserve ambiguity and surroundings contracts**

Reuse or extend the existing rectangle-in-square and surroundings-veto fixtures so recovered pairs reach the same gates. Assert non-equivalent spins still refuse and equivalent spins remain subject to the surroundings veto.

- [ ] **Step 6: Add region/full equivalence**

Exercise the operator/provider seam with a long disconnected wall crossing the initial region. Assert partial recovery requests widening and the final region-first delta equals forced-full extraction.

- [ ] **Step 7: Run the Lock-and-key suite**

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python tests/lock_key_regression.py
```

Expected: every case prints `PASS`; process exits 0.

- [ ] **Step 8: Run the Precision-fit suite**

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python tests/precision_fit_regression.py
```

Expected: every case prints `PASS`; process exits 0.

- [ ] **Step 9: Commit**

```bash
git add quicksnap_utils.py tests/lock_key_regression.py
git commit -m "test: keep spatial connector recovery fail closed"
```

---

### Task 4: Make recovery failures diagnosable

**Files:**
- Modify: `quicksnap_utils.py:2387-2677`
- Modify: `quicksnap.py:1079-1215`
- Test: `tests/lock_key_regression.py`

**Interfaces:**
- Consumes: recovery metadata/reasons from `_recover_spatial_connector_frame(...)`.
- Produces: recovery diagnostic fields in the existing diagnostics dictionary and refusal report; no new log file.

- [ ] **Step 1: Add diagnostic regressions**

Capture diagnostics for an absent-frame fixture and a multiple-frame fixture. Assert the former names recovery absence and the latter names multiple measured-distinct frames. Assert reports include recovery eligibility, widening/full-coverage state, considered/surviving counts, pair/axis counts, and frame count.

- [ ] **Step 2: Record bounded recovery telemetry**

Extend the existing diagnostics dictionary with recovery fields at each filter boundary: eligibility reason, extraction coverage/widening, geometry considered, clean patches, side/normal/dimension survivors, opposed pairs, independent axes, coherent frames, and terminal reason.

- [ ] **Step 3: Extend the existing refusal report**

Update `lock_key_diagnostic_report` and `log_lock_key_refusal` to print the recovery section only when recovery was eligible or attempted. Keep ordinary refusals concise. Ensure a recovery refusal does not fall back to only the generic two-pair advice.

- [ ] **Step 4: Add timing around the cold path**

Use the existing Lock-and-key timing style to report slow spatial recovery and full extraction. Do not add per-polygon logging or hover-time work.

- [ ] **Step 5: Run syntax and both solver suites**

```bash
python -m py_compile __init__.py quicksnap.py quicksnap_utils.py quicksnap_snapdata.py quicksnap_render.py
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python tests/lock_key_regression.py
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python tests/precision_fit_regression.py
```

Expected: compilation exit 0 and both suites print only passing cases.

- [ ] **Step 6: Commit**

```bash
git add quicksnap.py quicksnap_utils.py tests/lock_key_regression.py
git commit -m "fix: explain disconnected connector recovery refusals"
```

---

### Task 5: Patch release and full verification

**Files:**
- Modify: `__init__.py:1-20`
- Modify: `CHANGELOG.md:1-20`
- Generated, gitignored: `releases/MateSnap-2.2.1.zip`

**Interfaces:**
- Consumes: the completed solver and regression changes.
- Produces: MateSnap version `2.2.1` and validated release archive.

- [ ] **Step 1: Bump version metadata**

Change `bl_info['version']` from `(2, 2, 0)` to `(2, 2, 1)`. Promote the CHANGELOG top heading to `2.2.1` and document that centered end-face/socket-floor rotation now recovers disconnected side walls spatially while preserving fail-closed ambiguity and wall-click behavior.

- [ ] **Step 2: Run all three regression suites**

```bash
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python tests/lock_key_regression.py
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python tests/precision_fit_regression.py
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" -b --factory-startup --python tests/legacy_snap_regression.py
```

Expected: all cases print `PASS`; every process exits 0.

- [ ] **Step 3: Run the syntax gate**

```bash
python -m py_compile __init__.py quicksnap.py quicksnap_utils.py quicksnap_snapdata.py quicksnap_render.py quicksnap_shader_gpu_module.py
```

Expected: exit 0.

- [ ] **Step 4: Build the new archive**

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File ./build_release.ps1
```

Expected: `releases/MateSnap-2.2.1.zip` is created and the builder reports a valid archive. Verify `MateSnap-2.2.0.zip` was not modified.

- [ ] **Step 5: Inspect release contents**

Confirm the archive contains the required runtime files, tests are excluded, `quicksnap_shader_gpu_module.py` is present, and the deleted legacy shader is absent.

- [ ] **Step 6: Record the manual gate honestly**

If the real figurine smoke test has not been performed in Blender's GUI, report the archive as built and automated checks as passing, but do not claim the release is field-verified or ready to publish.

- [ ] **Step 7: Commit**

```bash
git add __init__.py CHANGELOG.md
git commit -m "chore: prepare MateSnap 2.2.1"
```
