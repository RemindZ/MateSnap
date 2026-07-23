# Lock and Key Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a no-drag, two-surface-click Lock and key workflow that safely mates selected figurine connectors by translation/centering, with optional rigid rotation.

**Architecture:** The modal operator gets a separate raycast-only path and stores exact face hits without touching the existing SnapData workflow. `quicksnap_utils.py` reuses planar patch extraction, builds Lock-and-key-specific straight/tapered side-pair descriptors, solves one validated world delta matrix, and applies it to selected root objects only.

**Tech Stack:** Blender 5.0 headless runner, Blender Python API compatible with 2.93+, `mathutils`, NumPy, Python standard library.

## Global Constraints

- Work only on `quick-snap-neo`; do not modify `main`.
- Add no dependency and no ICP fallback.
- Object mode only; selected key hierarchy to unselected mesh lock.
- Use evaluated geometry unless `ignore_modifiers` is enabled.
- Standard vertex, midpoint, face-center, origin, and precision-fit workflows must remain unchanged.
- First click never moves geometry; any failure after the second click leaves the scene untouched.
- Translation-only is the default and preserves click-defined insertion depth.
- Rotation requires at least two independent matched directions and a unique validated proper rotation.
- Support clean planar rectangular, slot, and depth-tapered trapezoidal connectors; fail closed for round, organic, incomplete, stale, or ambiguous geometry.

---

### Task 1: Establish the Lock and key RED harness

**Files:**
- Create: `tests/lock_key_regression.py`
- Test: `tests/lock_key_regression.py`

**Interfaces:**
- Consumes: existing `_mesh_fit_data()`, `_seed_polygons()`, `_candidate_patches()`, and the synthetic mesh style in `tests/precision_fit_regression.py`.
- Produces: standalone Blender builders for straight and depth-tapered connector pairs plus `run_lock_key_case(...)`.

- [ ] **Step 1: Create the standalone Blender test loader**

Load `quicksnap_utils.py` directly and reuse the existing regression builders without registering the add-on:

```python
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("quicksnap_utils_under_test", ROOT / "quicksnap_utils.py")
quicksnap_utils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quicksnap_utils)
```

Define `make_straight_key_lock()`, `make_tapered_key_lock(taper_degrees)`, `assert_matrix_finite()`, and scene cleanup. Return raw face indices and exact world click points on the connector surfaces.

- [ ] **Step 2: Add the first translation-only RED**

Create an already-oriented rectangular key offset from its lock. Call the approved entry point:

```python
delta = quicksnap_utils.compute_lock_key_transform(
    bpy.context,
    SimpleNamespace(ignore_modifiers=True),
    key.name, key_face, key_hit,
    lock.name, lock_face, lock_hit,
    allow_rotation=False,
)
```

Apply `delta` to the key in the test and assert:

```python
assert delta is not None
assert_matrix_finite(delta)
assert abs(center_error_x) <= 1e-6
assert abs(center_error_y) <= 1e-6
assert abs(insertion_coordinate_after - insertion_coordinate_from_clicks) <= 1e-8
assert key.matrix_world.to_quaternion().rotation_difference(original_rotation).angle == 0.0
```

- [ ] **Step 3: Run and verify RED**

Run:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --background --factory-startup --python-exit-code 1 --python tests\lock_key_regression.py
```

Expected: nonzero exit with `AttributeError: module ... has no attribute 'compute_lock_key_transform'`.

- [ ] **Step 4: Commit the RED harness**

```powershell
git add tests/lock_key_regression.py
git commit -m "test: cover Lock and key translation"
```

---

### Task 2: Solve straight and tapered translation-only mates

**Files:**
- Modify: `quicksnap_utils.py`
- Extend: `tests/lock_key_regression.py`

**Interfaces:**
- Produces:
  - `_connector_side_pairs(patches, anchor) -> list[dict]`
  - `_match_connector_pairs(source_pairs, target_pairs, rotation) -> list[dict]`
  - `_solve_lock_key_translation(matches, source_hit, target_hit) -> np.ndarray | None`
  - `_validate_lock_key_transform(matches, matrix, insertion_axis) -> bool`
  - `compute_lock_key_transform(context, settings, source_object_name, source_face_index, source_hit, target_object_name, target_face_index, target_hit, allow_rotation=False) -> Matrix | None`

- [ ] **Step 1: Add tapered and failure RED cases**

Extend the harness with:

```python
assert_tapered_translation(taper_degrees=15.0)
assert run_incompatible_taper_case() is None
assert run_equal_width_case() is None
assert run_organic_case() is None
assert run_stale_face_case() is None
assert run_missing_object_case() is None
```

The 15-degree taper must prove this path is separate from standard precision fit's 170-degree opposition rule.

- [ ] **Step 2: Build Lock-and-key side-pair descriptors**

For every patch pair with `dot(n1, n2) < 0`, canonicalize:

```python
lateral = n1 - n2
lateral /= np.linalg.norm(lateral)
depth_hint = n1 + n2
opening_angle = math.acos(np.clip(float(n1 @ n2), -1.0, 1.0))
```

Reject zero area/extent, unstable lateral vectors, and anchors outside the projected lateral interval plus patch tolerance. Store ordered patches, lateral axis, depth hint, opening angle, width at the anchor projection, tolerance, and patch IDs. Do not change `_plane_pairs()`.

- [ ] **Step 3: Match source and target pair descriptors**

Require:

```text
opening-angle difference <= 5 degrees
source lateral aligned to target lateral <= 5 degrees in translation-only mode
each source wall normal opposes its corresponding target wall normal <= 10 degrees
target width > source width + combined tolerance
correction <= min(0.25 * source width, 2 * clearance) + tolerance
```

Rank targets by full 3D pair-center distance to `target_hit`. Reject overlapping uncertainty bands and competing source pairs on the same lateral axis using the same pairwise peer rule as `_match_plane_pairs()`.

- [ ] **Step 4: Solve clearance balance after coarse point mapping**

Use `coarse = target_hit - source_hit`. For each matched target wall pair with inward normals `m_low`, `m_high`, calculate the two signed clearances after coarse translation and form:

```python
row = m_low - m_high
rhs = -(clearance_low - clearance_high)
```

Solve rows with `np.linalg.lstsq(..., rcond=0.1)`, retain the SVD row space, and return `coarse + lateral_correction`. Components not represented by retained rows stay exactly zero in the correction.

- [ ] **Step 5: Validate and return one delta matrix**

Recheck the same matched patches after translation: finite matrix, non-negative wall gaps within tolerance, reduced/final clearance imbalance, trust cap, and zero discarded-direction correction. Return:

```python
Matrix.Translation(Vector(translation))
```

Log a concise debug reason and return `None` on every failure stage.

- [ ] **Step 6: Run both Lock and key and standard regressions**

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --background --factory-startup --python-exit-code 1 --python tests\lock_key_regression.py
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --background --factory-startup --python-exit-code 1 --python tests\precision_fit_regression.py
```

Expected: both end in `PASS`.

- [ ] **Step 7: Commit translation solver**

```powershell
git add quicksnap_utils.py tests/lock_key_regression.py
git commit -m "feat: solve two-click connector translation"
```

---

### Task 3: Add optional rigid connector alignment

**Files:**
- Modify: `quicksnap_utils.py`
- Extend: `tests/lock_key_regression.py`

**Interfaces:**
- Produces:
  - `_rotation_candidates(source_pairs, target_pairs) -> list[dict]`
  - `_fit_connector_rotation(correspondences) -> Matrix | None`

- [ ] **Step 1: Add rotation RED cases**

Add a key rotated by a known non-axis-aligned quaternion and assert `allow_rotation=True` restores its connector frame and centers it. Add:

```python
assert run_single_direction_rotation_case() is None
assert run_incompatible_rotation_case() is None
assert_smallest_equivalent_rotation()
```

Also rerun the same rotated geometry with `allow_rotation=False` and assert `None`; translation-only must never silently rotate.

- [ ] **Step 2: Enumerate compatible pair mappings**

Require at least two independent source and target lateral directions. Enumerate pair permutations and low/high wall assignments only when opening angles and width ordering match within tolerance. Keep this local: typical connectors expose two lateral pairs, so exhaustive enumeration is bounded and clearer than a generic assignment framework.

- [ ] **Step 3: Fit a proper rotation from matched normals**

Build source normals `a` and opposing target normals `b`, calculate `H = a.T @ b`, and use SVD:

```python
u, _, vh = np.linalg.svd(h)
rotation = vh.T @ u.T
if np.linalg.det(rotation) < 0:
    vh[-1] *= -1
    rotation = vh.T @ u.T
```

Reject fewer than two independent directions, non-finite values, determinant outside `1 +/- 1e-8`, and angular residual above 5 degrees.

- [ ] **Step 4: Rank and validate candidates**

For each valid rotation, recompute source patch points/normals, match plane clearances, solve lateral translation, and validate. Rank geometrically equivalent transforms by quaternion angle from identity; reject tied non-equivalent transforms. Return:

```python
Matrix.Translation(target_hit + correction) @ rotation_matrix @ Matrix.Translation(-source_hit)
```

- [ ] **Step 5: Run RED cases GREEN plus standard regression**

Run both Blender commands from Task 2. Expected: exit `0` for both.

- [ ] **Step 6: Commit rotation support**

```powershell
git add quicksnap_utils.py tests/lock_key_regression.py
git commit -m "feat: optionally rotate Lock and key mates"
```

---

### Task 4: Add the no-drag modal workflow and atomic hierarchy transform

**Files:**
- Modify: `quicksnap.py`
- Extend: `tests/lock_key_regression.py`

**Interfaces:**
- Adds operator fields `lock_key_source_hit`, `lock_key_target_preview`, and `lock_key_original_matrices`.
- Produces private operator methods:
  - `raycast_lock_key_surface(context, selected_only) -> tuple | None`
  - `record_lock_key_source(hit) -> None`
  - `finish_lock_key(context, hit) -> bool`
  - `apply_world_delta_to_selection(delta) -> None`

- [ ] **Step 1: Add operator-state RED checks**

Instantiate the operator in Blender headless mode with selected parent/child meshes. Assert:

```python
before = {obj.name: obj.matrix_world.copy() for obj in selected}
operator.record_lock_key_source(source_hit)
assert all(obj.matrix_world == before[obj.name] for obj in selected)
operator.apply_world_delta_to_selection(delta)
assert parent.matrix_world == delta @ before[parent.name]
assert child.matrix_world == before[child.name]  # inherited once through the parent
```

Add a solver-`None` path and assert every original matrix is unchanged.

- [ ] **Step 2: Add consistent surface raycasting**

When Lock and key is active, bypass nearest-point update logic. Source raycast accepts only selected mesh objects. Target raycast temporarily hides selected roots, raycasts an unselected mesh, then restores visibility/selection in `finally`.

For `ignore_modifiers=False`, store evaluated face indices from `scene.ray_cast`. For `ignore_modifiers=True`, identify the object, transform the view ray into raw object space, call `obj.ray_cast`, and store the raw face index/hit.

- [ ] **Step 3: Wire the modal clicks without live apply**

In IDLE, left click records the source hit and changes state without calling `apply()`. In SOURCE_PICKED, mouse movement only updates target preview. The second valid click calls `compute_lock_key_transform(...)`; apply and finish only when it returns a matrix. On `None`, report `Lock and key: no safe connector match found` and keep the operator active for another target click.

Mode change, right-click, Esc, or termination clears stored hits and restores backed-up matrices.

- [ ] **Step 4: Apply one world delta to selected roots**

Use the existing `keep_only_parents()` result:

```python
roots = quicksnap_utils.keep_only_parents(
    [bpy.data.objects[name] for name in self.selection_objects]
)
for obj in roots:
    obj.matrix_world = delta @ obj.matrix_world
```

Do not call the standard live `apply()` or post-snap precision fit in this workflow.

- [ ] **Step 5: Update headers and object-mode guard**

Reject Lock and key invocation outside object mode with one warning. Use the two approved header strings. Axis keys, Shift pause, auto-merge, and free-space movement do not act in Lock and key mode.

- [ ] **Step 6: Run compile and both Blender regressions**

```powershell
python -m py_compile quicksnap.py quicksnap_utils.py tests\lock_key_regression.py
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --background --factory-startup --python-exit-code 1 --python tests\lock_key_regression.py
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --background --factory-startup --python-exit-code 1 --python tests\precision_fit_regression.py
```

- [ ] **Step 7: Commit modal workflow**

```powershell
git add quicksnap.py tests/lock_key_regression.py
git commit -m "feat: add two-click Lock and key workflow"
```

---

### Task 5: Add pie, settings, and viewport feedback

**Files:**
- Modify: `quicksnap.py`
- Modify: `quicksnap_render.py`
- Extend: `tests/lock_key_regression.py`

**Interfaces:**
- Adds preferences `lock_and_key_mode: BoolProperty` and `lock_and_key_rotate: BoolProperty`.
- Adds operator `QUICKSNAP_OT_toggle_lock_key` with `bl_idname = 'quicksnap.toggle_lock_key'`.

- [ ] **Step 1: Add settings persistence RED check**

Exercise the existing property enumeration used by `save_settings()` and assert both property identifiers are present and boolean. Reload saved values through `load_settings()` and assert they round-trip.

- [ ] **Step 2: Add preferences and toggle operator**

Define both booleans default `False`. The toggle operator flips `lock_and_key_mode`. Register it in `blender_classes`.

- [ ] **Step 3: Place Lock and key in the bottom pie slot**

Keep source and target as the first west/east pie entries. Set both columns' `enabled` value to `not settings.lock_and_key_mode`. Use the third/south slot for a wide boxed toggle operator labeled `Lock and key`, with depressed state reflecting the preference. Move `Open Addon Settings` to a later free pie slot; keep `ignore_modifiers` accessible.

- [ ] **Step 4: Add N-panel and preferences controls**

Show `Lock and key` and, conditionally when enabled, `Rotate key to match lock`. Do not add geometry threshold controls.

- [ ] **Step 5: Draw surface feedback**

In `draw_callback_3d`, branch early for Lock and key. Draw `lock_key_source_hit` as a red point with `draw_points_3d(..., color=(1, 0, 0, 1), point_width=8, depth_test=False)`. Draw a smaller target preview point when present. Suppress standard source squares, rubber band, and snap-axis guides.

- [ ] **Step 6: Run compile and regressions**

Run the three commands from Task 4. Expected: all exit `0`.

- [ ] **Step 7: Commit UI and feedback**

```powershell
git add quicksnap.py quicksnap_render.py tests/lock_key_regression.py
git commit -m "feat: expose Lock and key mode"
```

---

### Task 6: Build the overnight test artifact and final branch verification

**Files:**
- Modify only if needed for truthful documentation: `CHANGELOG.md`
- Test: `tests/lock_key_regression.py`
- Test: `tests/precision_fit_regression.py`

**Interfaces:**
- Produces ignored test artifact `releases/QuickSnap-1.5.13.zip` on `quick-snap-neo`.

- [ ] **Step 1: Document branch-test behavior**

Add an `Unreleased - QuickSnap Neo` changelog section describing the two-click workflow, translation-only default, optional rotation, tapered connector support, and fail-closed scope. Do not bump the stable version or rename the add-on before real-part validation.

- [ ] **Step 2: Run the complete verification gate**

```powershell
python -m py_compile __init__.py quicksnap.py quicksnap_utils.py quicksnap_snapdata.py quicksnap_render.py tests\precision_fit_regression.py tests\lock_key_regression.py
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --background --factory-startup --python-exit-code 1 --python tests\precision_fit_regression.py
& 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' --background --factory-startup --python-exit-code 1 --python tests\lock_key_regression.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_release.ps1
git diff --check
git status --short
```

Expected: both Blender scripts end in `PASS`, the archive validates, diff check is empty, and only intended tracked changes appear before commit.

- [ ] **Step 3: Inspect the ZIP and hash it**

Assert `QuickSnap/__init__.py`, `QuickSnap/quicksnap.py`, and `QuickSnap/quicksnap_utils.py` exist; no tests/docs/build scripts are present. Record SHA-256 with `Get-FileHash`.

- [ ] **Step 4: Commit documentation**

```powershell
git add CHANGELOG.md docs/superpowers/plans/2026-07-23-lock-and-key-mode.md
git commit -m "docs: describe Lock and key branch preview"
```

- [ ] **Step 5: Verify committed branch and preserve it for testing**

Rerun Step 2, confirm `git status --short` is clean, and keep the `quick-snap-neo` worktree plus ignored ZIP available. Do not merge to `main` or claim release readiness before the manual real-figurine smoke test.
