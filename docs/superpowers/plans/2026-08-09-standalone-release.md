# Standalone release plan (working name: PartSnap)

2026-08-09. Goal: release this fork as its own addon with its own name, repo,
and update channel. Upstream QuickSnap (MIT, Julien Heijmans) appears
abandoned; this fork has diverged into a different product (connector mating
and precision fit for dense figurine kits). The name is a placeholder until
the collision research settles it; every step below is name-agnostic.

## 0. Decisions to settle first

- **Final name** — pending web collision research (PartSnap, KitSnap, SnapFit,
  MateSnap). PartSnap is the working favourite.
- **Version**: 2.0.0. Continues the lineage honestly (CHANGELOG keeps the
  1.x history under a "formerly QuickSnap-High-Poly" note) while signalling
  the break.
- **Repo name**: `RemindZ/<Name>` (match the addon name, case as branded).

## 1. New repository, history kept

- Create `RemindZ/<Name>` on GitHub; push the full existing history (the
  lineage is the provenance and the changelog backs it). Default branch
  `main`; retire the `quick-snap-neo` working-branch name at the same time.
- `RemindZ/QuickSnap-High-Poly` stays up but frozen: final commit updates its
  README to point at the new repo ("continued as <Name>"). Do not delete it —
  released zips and old links reference it.

## 2. Identity rename in code

The rename surface, verified against the code:

| What | Where | Note |
|---|---|---|
| Staged module folder `QuickSnap/` | `build_release.ps1` (stage root, required-entries list, zip name `QuickSnap-$version.zip`) | The installed folder name IS the addon identity: preferences `bl_idname = __name_addon__` derives from it, so prefs rename automatically. |
| `bl_info` | `__init__.py` | New name + description; author "RemindZ, based on QuickSnap by Julien Heijmans"; version 2.0.0; update `tracker_url`/`doc_url` to the new repo. |
| Operator idnames | `object.quicksnap`, `quicksnap.toggle_lock_key`, `quicksnap.open_settings` | New prefix (`<name>.` / `object.<name>`). Changing them lets old and new addons coexist during migration. |
| Menu/panel idnames | `VIEW3D_MT_PIE_quicksnap` (+ two `call_menu_pie` call sites), `QUICKSNAP_PT_toolbar` | Same reason. |
| Keymaps | `addon_keymaps` registration + `detect_hotkey` | Follow the idnames; no hardcoded names besides those. |
| User-facing strings | header texts, `self.report` prefixes, log lines starting "QuickSnap:" | "Lock and key:" prefixes stay as-is. |
| Refusal log filename | `quicksnap_lock_key_log.txt` (`lock_key_log_path`) | Rename; mention the old name once in the README for people with saved logs. |
| Icons `QUICKSNAP_*.tif` | loaded by snap-type key | Deliberately NOT renamed: filenames are internal, invisible to users, and the snap-type strings double as icon keys. Touching them is risk for zero benefit. |
| Class names (`QuickVertexSnapOperator`, ...) | internal only | Optional cosmetic pass; tests build stubs from `QuickVertexSnapOperator.__dict__`, so if renamed, rename in `tests/` too. Fine to defer. |

Docs: `CLAUDE.md` references (commands, module names), README rewrite.
Specs and plans in `docs/superpowers/` are historical records — do not
rewrite them; the new README states the lineage.

## 3. Own update channel

- The vendored CGCookie updater currently points at
  `JulienHeijmans/quicksnap` (`addon_updater_ops.py:1381-1385`) — a live
  footgun: any upstream release would offer to overwrite this fork. Repoint
  `updater.user` / `updater.repo` to the new repo. This is configuration, not
  a refactor of the vendored module.
- The updater installs from GitHub release tags. Process per release: tag
  `v<version>`, create a GitHub Release, attach `<Name>-<version>.zip`.
- **Verification before trusting it**: publish a `v2.0.0-rc1` pre-release
  tag, install the previous build in a clean Blender, and confirm the updater
  finds, downloads, and installs it with the right folder name. The updater
  unpacks the tag's source zip, so the repo layout (addon files at root) must
  install correctly through it — that is exactly what the rc round proves.
  If it misbehaves, fall back to removing the updater UI and shipping manual
  zips only; do not ship a half-working updater.

## 4. Packaging and docs

- `build_release.ps1`: new folder/zip names; keep the required-entries
  validation and the `bl_info` version source of truth.
- README: what it is (kit/figurine assembly: Lock and key, precision fit,
  dense-mesh performance), install, quick start, the diagnose-from-logs
  support policy (console + refusal log, never ask for models), credits and
  MIT lineage, migration note from QuickSnap-High-Poly.
- LICENSE.md: keep the MIT text and Julien Heijmans' copyright line; add a
  second copyright line for the fork.
- CHANGELOG: new top section `2.0.0` ("renamed; formerly QuickSnap-High-Poly
  1.8.x, history below unchanged").

## 5. Migration and coexistence

- New module + idnames mean old and new can be installed side by side, but
  both bind Ctrl+Shift+V — README tells migrators to disable/uninstall the
  old addon first.
- Preferences are stored per module name and will not carry over; settings
  are few (snap types, Lock and key toggles, log level) — a one-time manual
  re-set, stated in the README. No settings importer (not worth the code).

## 6. Verification gate before calling 2.0.0 released

1. `python -m py_compile` on every module.
2. Both regression suites green.
3. Build the zip; install in a clean Blender (factory prefs): register,
   hotkey, pie menu, one standard snap, one Lock and key mate.
4. Updater rc round (step 3 above).
5. The spec-mandated manual smoke test on a real figurine key/lock pair —
   this is the release bar, headless green is not.

## 7. Courtesy

Open an issue or note to Julien Heijmans: the fork is renamed to avoid
confusion with his project, credits retained. Not legally required (MIT);
good form given how much architecture survives.

## Effort

Rename + build script: 1-2h. Repo + updater rc verification: ~1h. README +
docs: ~1h. Manual smoke test: user's hands. Nothing here blocks on anything
external except the name decision.
