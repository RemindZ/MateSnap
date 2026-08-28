# Blender 5 Legacy Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require Blender 5.0+, remove obsolete compatibility code, fix confirmed legacy snapping defects, and reduce proven dense-scene overhead without changing the fitting designs.

**Architecture:** Keep the existing modules and repair root causes in place. Land correctness in isolated test-first slices, then make mechanical memory cleanups, and leave dense render indexing until the behavioral baseline is green.

**Tech Stack:** Blender 5 Python API, NumPy, mathutils, bmesh, existing plain-script headless Blender regressions, PowerShell release build.

## Global Constraints

- Minimum Blender version is exactly `(5, 0, 0)`.
- Release version is exactly `(2, 2, 0)` and CHANGELOG's top heading must match.
- Precision fit and Lock and key remain separate pipelines.
- Vendored `addon_updater*.py` internals are unchanged.
- No new dependencies or compatibility shims.
- New rejection paths remain fail-closed and diagnosable.
- A real figurine key/lock GUI smoke test is required before any release-readiness claim.

---

### Task 1: Establish Blender 5 Baseline

**Files:**
- Modify: `__init__.py`
- Modify: `quicksnap_render.py:15-18`
- Delete: `quicksnap_shader_legacy.py`
- Modify: `CHANGELOG.md`
- Test: `tests/lock_key_regression.py`

**Interfaces:**
- Produces: package metadata `bl_info["blender"] == (5, 0, 0)` and `bl_info["version"] == (2, 2, 0)`; render imports modern shader symbols directly.

- [ ] Add a metadata regression that loads `__init__.py` with the existing package harness and asserts Blender/version tuples.
- [ ] Run the regression and verify it fails on `(2, 93, 0)` / `(2, 1, 0)`.
- [ ] Update metadata and CHANGELOG; replace the render version branch with one modern import; delete the legacy shader file.
- [ ] Run `python -m py_compile __init__.py quicksnap_render.py quicksnap_shader_gpu_module.py` and both Blender suites.

### Task 2: Repair SnapData Identity and Geometry Selection

**Files:**
- Modify: `quicksnap_snapdata.py:217-475, 704-962`
- Test: `tests/lock_key_regression.py` or create `tests/legacy_snap_regression.py`

**Interfaces:**
- Produces: `SnapData.object_name(index) -> str | None` used by `find_closest()` and `get_object_name_at_index()`; `self.scene_object_indices: dict[str, int]`.

- [ ] Add failing cases for cursor target with one object, cursor target with no object, `object_id == len(scene_meshes)`, and a valid object ID.
- [ ] Add a failing Object-mode source case using a topology-reducing modifier with Ignore Modifiers enabled; exhaust ingestion and assert raw indices fit.
- [ ] Implement one bounds-safe object-name lookup and route both result paths through it.
- [ ] Build `scene_object_indices` once and replace repeated `scene_meshes.index` calls.
- [ ] Make capacity counting call the same raw/evaluated choice used by ingestion.
- [ ] Run the focused legacy regression and both fitting suites.

### Task 3: Repair Face and Curve Candidate Construction

**Files:**
- Modify: `quicksnap_snapdata.py:26-210, 345-420`
- Test: `tests/legacy_snap_regression.py`

**Interfaces:**
- Produces: `ObjectPointData` that treats unsupported object/snap combinations as empty and never enters a processing queue.

- [ ] Add failing mixed triangle/quad face-selection cases for selected source and unselected target masks.
- [ ] Add a failing polygonless mesh FACES case that expects zero candidates without an exception.
- [ ] Add failing curve MIDPOINTS/FACES cases asserting no selected or scene queue entry.
- [ ] Correct polygon starts to use preceding loop totals and guard the empty case.
- [ ] Make `add_object_data` skip queue insertion when construction is already completed/unsupported.
- [ ] Run focused and full Blender regressions.

### Task 4: Make Progressive Visibility Transactional

**Files:**
- Modify: `quicksnap_snapdata.py:574-642, 909-923`
- Test: `tests/legacy_snap_regression.py`

**Interfaces:**
- Produces: temporary visibility helper that records and restores `(hide_get(), select_get())` for touched objects in `finally`.

- [ ] Add a failing time-budget case where target ingestion remains unfinished and assert hide/selection state is unchanged after the call.
- [ ] Add an injected-exception case and assert the same restoration.
- [ ] Replace blind hide/unhide blocks in progressive ingestion and nearby discovery with the smallest shared state-preserving helper/context manager.
- [ ] Run focused and full Blender regressions.

### Task 5: Repair Standard Constraint and Camera Math

**Files:**
- Modify: `quicksnap_utils.py:2523-2563`
- Modify: `quicksnap_snapdata.py:479-500`
- Test: `tests/legacy_snap_regression.py`

**Interfaces:**
- Consumes: existing `intersect_line_plane` / axis-target functions.
- Produces: valid orthographic anti-parallel and rotated-local movement; world-space camera culling.

- [ ] Add failing pure geometry cases for anti-parallel plane view and rotated local plane/axis.
- [ ] Add a parented orthographic camera case using `matrix_world.translation` as expected world position.
- [ ] Delete the redundant exact orthographic prechecks and rely on existing intersection `None` handling.
- [ ] Use camera world translation in culling.
- [ ] Run focused and full Blender regressions.

### Task 6: Harden Modal Initialization, Preference Rebuild, and Cleanup

**Files:**
- Modify: `quicksnap.py:70-120, 1260-1370, 1722-1826, 1880-1920`
- Test: `tests/lock_key_regression.py`

**Interfaces:**
- Produces: small static/testable helpers for Lock-and-key preflight ordering, view sentinel capture, and geometry-setting change detection; termination always removes resources.

- [ ] Add failing helper-level regressions proving invalid Lock-and-key preflight occurs before Local View mutation, all view sentinels are captured, and direct Ignore Modifiers changes require SnapData rebuild.
- [ ] Move preflight before visibility mutation.
- [ ] Initialize `view_distance` and `view_camera_zoom` with the other view state.
- [ ] Route direct `M` handling through the existing setting-change rebuild path.
- [ ] Put draw-handler and timer removal in idempotent `finally` cleanup.
- [ ] Add a regression for cleanup helper invocation when scene restoration raises; leave full window/timer behavior as a GUI smoke test.
- [ ] Run both Blender suites.

### Task 7: Remove Proven Allocation Waste

**Files:**
- Modify: `quicksnap_snapdata.py:253-275, 522-550`
- Modify: `quicksnap.py:1764-1826`
- Modify: `quicksnap_shader_gpu_module.py:1-60`
- Test: existing suites

**Interfaces:**
- Produces: no `SnapData.depth`; scalar object-ID broadcast; freed `self.bmeshs`; one polyline shader object.

- [ ] Remove the unused depth allocation/write and replace `np.full` with scalar broadcast.
- [ ] Free each BMesh only after all revert/apply work and clear the dictionary.
- [ ] Delete duplicate shader creation.
- [ ] Run syntax compilation and both Blender suites.

### Task 8: Index Dense Highlight Topology

**Files:**
- Modify: `quicksnap_render.py:900-1040`
- Test: add pure helper assertions to `tests/legacy_snap_regression.py`

**Interfaces:**
- Produces: compact adjacency builders returning vertex-to-edge and polygon-to-loop-triangle ranges; draw path caches one index per target mesh topology.

- [ ] Extract pure NumPy adjacency grouping from the current render path and add small known-topology assertions.
- [ ] Replace per-hover full edge scans with direct indexed incident-edge lookup.
- [ ] Replace per-hover `argwhere` over all loop triangles with polygon range lookup.
- [ ] Keep cache ownership and invalidation aligned with existing target-object highlight cache; do not introduce global persistence.
- [ ] Run focused regression, both Blender suites, and perform a Blender 5 dense-highlight GUI smoke test if interactive context is available.

### Task 9: Release Verification

**Files:**
- Modify: `README.md` if it states older Blender support
- Modify: `docs/superpowers/specs/2026-08-11-blender-5-legacy-remediation-design.md` only if implementation forced a documented correction
- Create: `releases/MateSnap-2.2.0.zip` via build script

- [ ] Search first-party docs/code for obsolete Blender minimums and legacy shader references; update only user-facing support claims.
- [ ] Run `python -m py_compile` over every first-party Python and regression file.
- [ ] Run all headless Blender regression scripts.
- [ ] Run `build_release.ps1`; inspect archive entries and assert `quicksnap_shader_legacy.py` is absent.
- [ ] Run `git diff --check` and inspect `git status --short`, preserving the pre-existing untracked `releases/pycompile-cache/`.
- [ ] Perform an adversarial code review of the completed diff and fix verified findings.
- [ ] Record that real figurine mating and GUI-only checks remain required before release readiness if they could not be executed.
