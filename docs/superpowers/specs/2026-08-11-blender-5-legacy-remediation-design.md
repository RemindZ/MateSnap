# Blender 5-Only Legacy Remediation Design

## Status

Approved for autonomous implementation on 2026-08-11.

## Goal

Make MateSnap require Blender 5.0 or newer, remove obsolete pre-5.0 compatibility code, fix the confirmed legacy QuickSnap correctness defects found by the whole-codebase audit, and apply only the confirmed low-risk performance improvements.

## Scope

### Platform baseline

- Set `bl_info["blender"]` to `(5, 0, 0)`.
- Remove `quicksnap_shader_legacy.py` and the runtime Blender-version shader branch.
- Use Blender 5 APIs directly; do not preserve compatibility shims for Blender 2.93–4.x.
- Bump MateSnap to version `2.2.0`, because dropping older Blender releases is an intentional compatibility break.

### Correctness fixes

1. Treat cursor and other negative object IDs as unattributed snap points. Never index `scene_meshes` with a sentinel.
2. Size source SnapData arrays from the same raw or evaluated geometry that ingestion uses.
3. Compute edit-mode polygon reduction starts from preceding polygon sizes and handle zero-polygon meshes as an empty candidate set.
4. Do not enqueue unsupported curve MIDPOINTS/FACES data.
5. Restore selected-object visibility and selection on every progressive-ingestion exit, including time-budget returns and exceptions.
6. Validate Lock-and-key preconditions before mutating Local View visibility.
7. Make the direct Ignore Modifiers hotkey rebuild SnapData through the same path as the pie-menu setting change.
8. Put timer and draw-handler removal behind exception-safe termination cleanup.
9. Initialize all view-change sentinels during startup so the first ordinary event does not rebuild unchanged data.
10. Use world-space camera position for orthographic camera culling.
11. Remove the exact/unrotated orthographic constraint prechecks and rely on existing intersection failure handling.

### Confirmed performance fixes

1. Delete the unused full-capacity SnapData depth array and its writes.
2. Replace scalar `np.full` object-ID batches with NumPy scalar broadcasting.
3. Cache scene object-name indices instead of repeated `list.index` scans.
4. Free and clear Edit Mode BMesh backups after restoration is complete.
5. Remove duplicate modern shader creation.
6. Replace repeated dense-highlight topology scans with indexed lookup only after the correctness slices pass; keep this as a separate performance slice so it can be reverted independently if viewport behavior changes.

## Explicit non-goals

- Do not merge Precision fit and Lock and key.
- Do not refactor vendored `addon_updater*.py` internals.
- Do not change mesh-extraction cache validation, zero-scale handling, or modern polyline uniform behavior unless a new regression test first reproduces the suspected defect.
- Do not add abstractions or dependencies for future compatibility.
- Do not rewrite the modal operator or SnapData architecture.

## Behavioral invariants

- Both fitting pipelines continue to fail closed and leave the scene untouched on refusal.
- Standard snapping to the 3D cursor remains supported, but cursor snaps carry no object attribution and cannot trigger Precision fit.
- Ignore Modifiers consistently selects the same geometry for capacity sizing, ingestion, highlighting, and fit seeds.
- Progressive processing remains bounded; state restoration is guaranteed around any temporary Blender scene mutation.
- Existing raw/evaluated Lock-and-key picking behavior remains unchanged.

## Testing

### Headless Blender regressions

Extend the existing plain-script suites or add one focused legacy regression script when isolation is materially clearer. Cover:

- cursor sentinel with and without eligible scene objects;
- mixed triangle/quad face-selection masks;
- polygonless face snapping;
- raw source mesh with topology-reducing modifier and Ignore Modifiers enabled;
- unsupported curve snap modes not entering processing queues;
- time-budget return restoring visibility and selection;
- orthographic anti-parallel and rotated-local constraints;
- first-event view sentinels and direct modifier-toggle rebuild through extracted testable helpers;
- dead depth-buffer removal through successful dense ingestion.

### Static compatibility checks

- Assert `bl_info["blender"] == (5, 0, 0)` and version is `(2, 2, 0)`.
- Assert the render module imports only the modern shader module.
- Assert the legacy shader file is absent from the release archive.

### GUI smoke tests

Document and perform where feasible:

- failed Lock-and-key invocation in Local View leaves global visibility unchanged;
- cancellation after a forced termination exception leaves no handlers or timer;
- Ignore Modifiers hotkey immediately changes highlighted/raw geometry;
- dense vertex and face highlights remain responsive;
- Edit Mode undo/redo remains correct after explicit BMesh freeing;
- standard snap and Lock-and-key interaction in Blender 5.

## Release verification

- Run `python -m py_compile` on all first-party Python and regression files.
- Run both existing Blender regression suites plus any new legacy suite.
- Build `releases/MateSnap-2.2.0.zip` once all checks pass.
- Verify required archive entries and confirm `quicksnap_shader_legacy.py` is absent.
- Do not claim release readiness without the required real figurine key/lock smoke test.

## Adversarial refinement

The initial design proposed implementing every audit item in one pass. The skeptical review narrowed it:

- Dropped repair of the legacy shader path entirely; deletion is safer under the Blender 5 baseline.
- Excluded three plausible findings without reproductions to avoid speculative solver/render changes.
- Rejected setting `keep_processing=False` when target queues empty because targets discover objects lazily.
- Rejected changing direct-hit discovery because the exact mouse ray is already part of nearby-object discovery.
- Kept dense highlight indexing because the audit established repeated full-array scans, but isolated it after all correctness work so it cannot obscure behavioral regressions.
- Required root-cause tests around temporary visibility mutation rather than patching only one return statement.
- Clarified that a passing headless suite is not a release claim: Blender 5 GUI checks and the real figurine mate remain mandatory.
