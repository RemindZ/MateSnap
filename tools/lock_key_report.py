"""Report what Lock and key sees at your two clicks, on your own part.

Run this in Blender with your file open, on the pair that refuses to mate. It reads
geometry only -- nothing is moved, added or deleted -- and writes a text report you
can paste back.

    1. Select the key part (the one that should move).
    2. Open Scripting, Text > Open, pick this file, then press Run Script.
    3. Follow the printed instructions: it asks you to click each connector wall.

If you would rather not click, edit PICKS below with two (object name, face index)
pairs and run again -- the face index is shown in the N-panel Item tab when you
select a single face in Edit mode with the index overlay on.

The report lands next to your .blend as lock_key_report.txt, and in the console.
"""
import bpy
import bmesh
import numpy as np
from mathutils import Vector
from pathlib import Path
import sys

# Optional: (("KeyObjectName", face_index), ("LockObjectName", face_index))
PICKS = None

ADDON = None
for name, module in list(sys.modules.items()):
    if name.endswith('quicksnap_utils') and hasattr(module, '_connector_pairs'):
        ADDON = module
        break

LINES = []


def say(message):
    LINES.append(message)
    print(message)


def describe(obj, face_index, label):
    say(f"--- {label}: {obj.name}, face {face_index} ---")
    mesh = obj.data
    say(f"    object has {len(mesh.polygons)} polygons,"
        f" {len(obj.modifiers)} modifier(s)")
    scale = obj.matrix_world.to_scale()
    say(f"    scale {tuple(round(v, 4) for v in scale)}")
    if face_index < 0 or face_index >= len(mesh.polygons):
        say("    face index out of range -- the mesh changed since the pick")
        return
    polygon = mesh.polygons[face_index]
    say(f"    clicked polygon area {polygon.area:.6f},"
        f" normal {tuple(round(v, 4) for v in polygon.normal)}")

    if ADDON is None:
        say("    (QuickSnap not loaded, so no solver detail)")
        return

    data = ADDON._mesh_fit_data(obj)
    seeds = ADDON._seed_polygons(data, 'FACES', face_index)
    anchor = np.array(obj.matrix_world @ polygon.center, dtype=np.float64)

    raw = ADDON._candidate_patches(data, seeds, ADDON._CONNECTOR_MAX_HOPS)
    walls, clicked = ADDON._connector_walls(data, seeds, ADDON._CONNECTOR_MAX_HOPS)
    say(f"    at full depth: {len(raw)} raw patches -> {len(walls)} merged walls")
    if clicked is None:
        say("    the clicked face did not land in any merged wall")
        return
    say(f"    clicked wall: area {clicked['area']:.6f},"
        f" extent {clicked['extent']:.6f},"
        f" normal {tuple(round(float(v), 4) for v in clicked['normal'])}")

    facing = [
        wall for wall in walls
        if wall is not clicked
        and float(wall['normal'] @ clicked['normal']) < 0.0
    ]
    say(f"    {len(facing)} wall(s) face it at all;"
        f" {sum(1 for w in facing if float(w['normal'] @ clicked['normal']) < ADDON._WALL_MAX_OPPOSED_DOT)}"
        f" past the 95-degree bar")
    for wall in sorted(facing, key=lambda w: -float(w['area']))[:6]:
        opening = np.degrees(np.arccos(np.clip(
            float(wall['normal'] @ clicked['normal']), -1.0, 1.0)))
        gap = abs(float(clicked['normal'] @ (wall['point'] - clicked['point'])))
        say(f"        area {wall['area']:10.5f}  opening {opening:7.2f}d"
            f"  separation {gap:.6f}")

    # The biggest walls in reach, whether or not they face the click.
    say("    largest walls in reach:")
    for wall in sorted(walls, key=lambda w: -float(w['area']))[:6]:
        say(f"        area {wall['area']:10.5f}"
            f"  normal {tuple(round(float(v), 4) for v in wall['normal'])}")

    pairs, reason = ADDON._connector_pairs(data, seeds, anchor, label.lower())
    say(f"    opposed wall pairs: {len(pairs)}")
    for pair in pairs[:6]:
        say(f"        axis {tuple(round(float(v), 4) for v in pair['axis'])}"
            f"  width {pair['width']:.6f}"
            f"  opening {np.degrees(pair['opening_angle']):.2f}d")
    if reason:
        say(f"    refusal: {reason}")


def report(picks):
    say("=== Lock and key geometry report ===")
    say(f"Blender {bpy.app.version_string}")
    if ADDON is None:
        say("QuickSnap is not enabled -- enable it and run again for full detail.")
    for (name, face_index), label in zip(picks, ("KEY", "LOCK")):
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != 'MESH':
            say(f"--- {label}: object {name!r} not found or not a mesh ---")
            continue
        describe(obj, int(face_index), label)
        say("")

    blend = bpy.data.filepath
    out = (Path(blend).with_name("lock_key_report.txt") if blend
           else Path(bpy.app.tempdir) / "lock_key_report.txt")
    out.write_text("\n".join(LINES), encoding="utf-8")
    say(f"written to {out}")


class LOCKKEY_OT_report_pick(bpy.types.Operator):
    """Click the connector wall on each part, key first"""
    bl_idname = "lockkey.report_pick"
    bl_label = "Lock and key: pick the two connector walls"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.picks = []

    def invoke(self, context, event):
        self.picks = []
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set(
            "Lock and key report: click the KEY connector wall")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            context.area.header_text_set(None)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            hit = self.raycast(context, event)
            if hit is None:
                self.report({'WARNING'}, "nothing under the cursor -- click again")
                return {'RUNNING_MODAL'}
            self.picks.append(hit)
            if len(self.picks) == 1:
                context.area.header_text_set(
                    "Lock and key report: now click the LOCK connector wall")
                return {'RUNNING_MODAL'}
            context.area.header_text_set(None)
            report(self.picks)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}

    def raycast(self, context, event):
        from bpy_extras import view3d_utils
        region = context.region
        region3d = context.space_data.region_3d
        coord = (event.mouse_region_x, event.mouse_region_y)
        origin = view3d_utils.region_2d_to_origin_3d(region, region3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, region3d, coord)
        depsgraph = context.evaluated_depsgraph_get()
        hit, _, _, face_index, obj, _ = context.scene.ray_cast(
            depsgraph, origin, direction)
        if not hit or obj is None:
            return None
        return (obj.name, face_index)


def register():
    bpy.utils.register_class(LOCKKEY_OT_report_pick)


if PICKS:
    report(PICKS)
else:
    try:
        bpy.utils.unregister_class(LOCKKEY_OT_report_pick)
    except Exception:
        pass
    register()
    print("Move the mouse into the 3D viewport and run:")
    print("    bpy.ops.lockkey.report_pick('INVOKE_DEFAULT')")
    print("or set PICKS at the top of this file and run the script again.")
