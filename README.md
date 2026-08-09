# MateSnap

MateSnap is a Blender add-on for assembling dense-mesh figurine kits. Its
Lock and key connector mating workflow pairs complementary connectors, while
post-snap precision fit refines a completed snap into a precise fit. The
add-on is built to remain responsive on dense meshes.

## Install

1. Download the `MateSnap-<version>.zip` release archive.
2. In Blender, open **Edit > Preferences > Add-ons** and select **Install**.
3. Choose the downloaded zip, then enable MateSnap.

MateSnap uses **Ctrl+Shift+V** by default to open its snap workflow; use the
same shortcut again for its pie menu. Configure the shortcut and Lock and key
options in the add-on preferences.

## Migrating from QuickSnap-High-Poly

Disable or uninstall QuickSnap-High-Poly before enabling MateSnap. Both
add-ons use **Ctrl+Shift+V**, so leaving both enabled creates a hotkey
conflict. MateSnap has its own preferences, so settings from the old add-on do
not carry over and need to be set again.

If you have an older diagnostic export, its filename was
`quicksnap_lock_key_log.txt`; new reports use `matesnap_lock_key_log.txt`.

## Support

For a Lock and key refusal or unexpected result, include the Blender console
output and `matesnap_lock_key_log.txt` in your report. Never send model files:
figurine-kit models are often private, and MateSnap's diagnostics are designed
to make the failure understandable without them.

## Credits and license

MateSnap continues the MIT-licensed lineage of
[QuickSnap by Julien Heijmans](https://github.com/JulienHeijmans/quicksnap).
See [LICENSE.md](LICENSE.md) for the complete MIT license and copyright
notices.

## History

See [CHANGELOG.md](CHANGELOG.md) for release history, including the
QuickSnap-High-Poly history retained under its former name.
