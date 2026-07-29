# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Blender addon (legacy `bl_info` style, **not** an extension `blender_manifest.toml`), supporting Blender 2.93+. This repo is the **High-Poly fork** of [JulienHeijmans/quicksnap](https://github.com/JulienHeijmans/quicksnap): upstream's snapping behaviour plus optimizations for dense scenes and figurine-kit assembly features (post-snap precision fit, Lock and key).

## Commands

```bash
# Tests (headless Blender; there is no pytest/unittest runner)
blender -b --factory-startup --python tests/lock_key_regression.py
blender -b --factory-startup --python tests/precision_fit_regression.py

# Build a release zip -> releases/QuickSnap-<bl_info version>.zip
powershell -NoProfile -ExecutionPolicy Bypass -File ./build_release.ps1
```

Each test file is a plain script with a `main()` that raises `AssertionError` on failure and prints `<case>: PASS` per case. **There is no way to run a single case from the CLI** — comment out lines in `main()`, or call the individual `assert_*` / `run_*` function from your own throwaway script.

`build_release.ps1` reads the version from `bl_info` in `__init__.py`; that is the single source of truth for the version number. It also validates the archive contains the required entries, so a green build means the zip is well-formed.

There is no linter, formatter, type-checker, or CI in this repo. `python -m py_compile <files>` is the only syntax gate.

## Architecture

`__init__.py` registers modules by name from `modulesNames` and **`importlib.reload`s them on import** so the addon can be hot-reloaded in Blender. Order matters: `quicksnap` (the operator) must come after the modules it imports.

- **`quicksnap.py`** — `QuickVertexSnapOperator`, a modal operator, plus preferences, pie menu, and N-panel. All interaction state lives on the operator instance and is reset in `__init__`, `initialize`, and `terminate`. The modal has two entirely separate loops: the standard drag/two-click snap, and `modal_lock_key` for Lock and key mode.
- **`quicksnap_snapdata.py`** — `SnapData` ingests candidate points (verts / midpoints / face centers / origins) and answers nearest-point queries. It processes **progressively across modal iterations** (`process_iteration`, `keep_processing`) so a dense scene doesn't stall the first frame. Above `heavy_mesh_threshold` it skips the KDTree entirely and queries screen coords with numpy — the KDTree build itself is the stall being avoided.
- **`quicksnap_utils.py`** — geometry solvers, pure of operator state. Both fitting pipelines live here (below).
- **`quicksnap_render.py`** — viewport draw callbacks. Imports shaders from `quicksnap_shader_gpu_module` (Blender ≥ 3.4) or `quicksnap_shader_legacy` (older, uses `bgl`); keep any shader change in both.
- **`addon_updater*.py`** — vendored CGCookie updater. Treat as third-party; don't refactor.

### The two fitting pipelines are deliberately separate

`quicksnap_utils.py` contains two similar-looking but independent solvers. **Do not merge them** — a plan review already rejected that:

| | Precision fit (post-snap) | Lock and key (two-click mate) |
|---|---|---|
| Pair builder | `_plane_pairs` | `_connector_side_pairs` |
| Matcher | `_match_plane_pairs` | `_match_connector_pairs` |
| Entry point | `compute_precision_fit` | `compute_lock_key_transform` |

They share the patch layer only: `_mesh_fit_data` → `_grow_planar_patch` → `_candidate_patches`. Changing anything in that shared layer affects **both** features, so run both suites.

Design intent for both: **fail closed**. Ambiguous, organic, round, or stale geometry returns `None` and leaves the scene untouched rather than guessing. When adding a rejection path, record a reason via `_note_lock_key_skip` so the operator can tell the user what to do differently — a generic refusal is treated as a bug here.

## Gotchas that cost real debugging time

- **`Object.ray_cast` and `Scene.ray_cast` always return *evaluated* geometry**, whichever object you call them on. Honouring "Ignore modifiers" therefore needs a base-mesh `BVHTree.FromPolygons` (see `lock_key_base_bvh`). The face index and the hit point must come from the same mesh the solver will read, or you get an index into the wrong mesh.
- **Patch `tolerance` is a flatness allowance (0.5% of patch extent), not a fit tolerance.** Using it to judge clearance rejects well-modelled connectors. `fit_tolerance` is the precision-based value; use it for clearance comparisons.
- **`hide_set()` drops objects from the selection and unhiding does not restore it**, and it clobbers a pre-hidden object's state. Prefer advancing a ray past unwanted hits over hiding things.
- Blender does not expose a scene-wide "raw geometry" raycast, so raw-mode picking is a per-object loop with a world-AABB broad phase.
- Docs of record live in `docs/superpowers/specs/` (approved designs) and `docs/superpowers/plans/`. The specs are binding — several implementation choices here were reverted for contradicting them. Check the relevant spec before changing solver behaviour.

## Testing in headless Blender

The suites are unusual because Blender's background mode is restricted:

- **GPU shaders cannot be created in `-b` mode**, so `quicksnap_render` is stubbed in `sys.modules` before `quicksnap.py` is imported. Anything you add at render-module import time must tolerate that stub.
- The harness loads `quicksnap_utils` **twice** — once standalone as `quicksnap_utils_under_test`, once as `quicksnap.quicksnap_utils` via the package. `State.IDLE` from one is **not** the same object as from the other; compare against `quicksnap.State` when checking operator state. Monkeypatching must target the same instance the code under test imported.
- `terminate()` touches `bpy.context.window`, which is `None` in background mode. Logic that needs testing gets extracted into a small static method (e.g. `ensure_active_object`) rather than tested through `terminate`.
- Operator methods are exercised through a stub class built from `QuickVertexSnapOperator.__dict__` (`make_lock_key_operator`), pulled from `__dict__` so `staticmethod` descriptors survive. Add new operator methods to `LOCK_KEY_OPERATOR_METHODS` when tests need them.
- `bpy.ops.ed.undo()` fails its context poll headless, so **undo behaviour cannot be regression-tested** — it needs a manual check in the GUI. Manually verified working after a completed Lock and key mate (2026-07-30, 1.8.2); re-check by hand if the apply path changes.

## Diagnosing user reports

This addon ships publicly and users' models are often proprietary, so **a failure must be diagnosable from the addon's own log output** — never ask for a `.blend` or hand the user a script to run. `lock_key_diagnostic_report` in `quicksnap_utils.py` is the pattern: it runs only on the refusal path and dumps patches reached, walls recovered, facing counts, separations, and surviving pairs. Extend it rather than adding another one-line message. Needing the file means the logging is incomplete.

## Conventions

- Bump the **patch** component of `bl_info['version']` for fixes; reserve minor bumps for genuinely new features. Promote the CHANGELOG's top heading to match.
- `releases/*.zip` is gitignored. Never overwrite a previously published archive with different content — build under the new version number instead.
- The design spec requires a manual smoke test on a real figurine key/lock pair before any release claim; headless green is not sufficient.
