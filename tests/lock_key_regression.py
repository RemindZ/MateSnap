import importlib.util
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import types

import bpy
from mathutils import Euler, Vector
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "quicksnap_utils_under_test", ROOT / "quicksnap_utils.py"
)
quicksnap_utils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quicksnap_utils)

PACKAGE_NAME = "quicksnap_regression_package"
PACKAGE = types.ModuleType(PACKAGE_NAME)
PACKAGE.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = PACKAGE
RENDER_STUB = types.ModuleType(PACKAGE_NAME + ".quicksnap_render")
RENDER_STUB.add_draw_handlers = lambda *args, **kwargs: None
RENDER_STUB.remove_draw_handlers = lambda *args, **kwargs: None
sys.modules[RENDER_STUB.__name__] = RENDER_STUB
OPERATOR_SPEC = importlib.util.spec_from_file_location(
    PACKAGE_NAME + ".quicksnap", ROOT / "quicksnap.py"
)
quicksnap = importlib.util.module_from_spec(OPERATOR_SPEC)
sys.modules[OPERATOR_SPEC.name] = quicksnap
OPERATOR_SPEC.loader.exec_module(quicksnap)


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def make_mesh(name, vertices, faces):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def make_key_lock(
    taper_degrees=0.0,
    target_taper_degrees=None,
    source_half_width=0.5,
    source_half_height=0.4,
    source_depth=1.0,
    target_half_width=0.6,
    target_half_height=0.5,
    target_depth=1.2,
):
    target_taper_degrees = (
        taper_degrees if target_taper_degrees is None else target_taper_degrees
    )
    source_slope = math.tan(math.radians(taper_degrees))
    target_slope = math.tan(math.radians(target_taper_degrees))
    source_tip_x = source_half_width - source_depth * source_slope
    source_tip_y = source_half_height - source_depth * source_slope
    target_tip_x = target_half_width - target_depth * target_slope
    target_tip_y = target_half_height - target_depth * target_slope
    key = make_mesh(
        "Key",
        [
            (-source_tip_x, -source_tip_y, -source_depth),
            (source_tip_x, -source_tip_y, -source_depth),
            (source_tip_x, source_tip_y, -source_depth),
            (-source_tip_x, source_tip_y, -source_depth),
            (-source_half_width, -source_half_height, 0.0),
            (source_half_width, -source_half_height, 0.0),
            (source_half_width, source_half_height, 0.0),
            (-source_half_width, source_half_height, 0.0),
        ],
        [
            (0, 3, 2, 1), (4, 5, 6, 7),
            (0, 1, 5, 4), (1, 2, 6, 5),
            (2, 3, 7, 6), (3, 0, 4, 7),
        ],
    )
    lock = make_mesh(
        "Lock",
        [
            (-target_half_width, -target_half_height, 0.0),
            (target_half_width, -target_half_height, 0.0),
            (target_half_width, target_half_height, 0.0),
            (-target_half_width, target_half_height, 0.0),
            (-target_tip_x, -target_tip_y, -target_depth),
            (target_tip_x, -target_tip_y, -target_depth),
            (target_tip_x, target_tip_y, -target_depth),
            (-target_tip_x, target_tip_y, -target_depth),
        ],
        [
            (1, 5, 4, 0), (2, 6, 5, 1),
            (3, 7, 6, 2), (0, 4, 7, 3),
        ],
    )
    key.location = (2.0, -1.0, 0.0)
    bpy.context.view_layer.update()
    source_hit_z = -0.3
    target_hit_z = -0.5
    source_hit_x = -(source_half_width - source_slope * -source_hit_z)
    target_hit_x = -(target_half_width - target_slope * -target_hit_z)
    key_hit = key.matrix_world @ Vector((source_hit_x, 0.0, source_hit_z))
    lock_hit = lock.matrix_world @ Vector((target_hit_x, 0.1, target_hit_z))
    return key, 5, key_hit, lock, 3, lock_hit


def make_straight_key_lock():
    return make_key_lock()


def make_tapered_key_lock(taper_degrees):
    return make_key_lock(taper_degrees=taper_degrees)


def make_rotated_key_lock(euler=(0.35, -0.25, 0.5), **kwargs):
    key, key_face, _, lock, lock_face, lock_hit = make_key_lock(**kwargs)
    key.rotation_euler = Euler(euler, 'XYZ')
    bpy.context.view_layer.update()
    source_hit_z = -0.3
    source_slope = math.tan(math.radians(kwargs.get("taper_degrees", 0.0)))
    half_width = kwargs.get("source_half_width", 0.5)
    source_hit_x = -(half_width - source_slope * -source_hit_z)
    key_hit = key.matrix_world @ Vector((source_hit_x, 0.0, source_hit_z))
    return key, key_face, key_hit, lock, lock_face, lock_hit


def make_single_direction_pair():
    source = make_mesh(
        "SlotKey",
        [
            (-0.5, -0.5, -1), (-0.5, 0.5, -1),
            (-0.5, -0.5, 0), (-0.5, 0.5, 0),
            (0.5, -0.5, -1), (0.5, 0.5, -1),
            (0.5, -0.5, 0), (0.5, 0.5, 0),
        ],
        [(0, 2, 3, 1), (4, 5, 7, 6), (2, 6, 7, 3)],
    )
    target = make_mesh(
        "SlotLock",
        [
            (-0.6, -0.5, -1.2), (-0.6, 0.5, -1.2),
            (-0.6, -0.5, 0), (-0.6, 0.5, 0),
            (0.6, -0.5, -1.2), (0.6, 0.5, -1.2),
            (0.6, -0.5, 0), (0.6, 0.5, 0),
        ],
        [(1, 3, 2, 0), (6, 7, 5, 4), (3, 7, 6, 2)],
    )
    source.location = (2, -1, 0)
    source.rotation_euler = Euler((0.2, -0.3, 0.4), 'XYZ')
    bpy.context.view_layer.update()
    source_hit = source.matrix_world @ Vector((-0.5, 0, -0.3))
    target_hit = target.matrix_world @ Vector((-0.6, 0.1, -0.5))
    return source, 0, source_hit, target, 0, target_hit


def assert_matrix_finite(matrix):
    values = np.array(matrix, dtype=np.float64)
    if values.shape != (4, 4) or not np.isfinite(values).all():
        raise AssertionError(f"expected finite 4x4 matrix, got {matrix!r}")


def run_lock_key_case(builder=make_straight_key_lock):
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = builder()
    original_rotation = key.matrix_world.to_quaternion()
    original_center = key.matrix_world.translation.copy()
    coarse = lock_hit - key_hit

    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit,
        lock.name, lock_face, lock_hit,
        allow_rotation=False,
    )

    if delta is None:
        raise AssertionError("expected a safe straight connector transform")
    assert_matrix_finite(delta)
    key.matrix_world = delta @ key.matrix_world
    center = key.matrix_world.translation
    if abs(center.x) > 1e-6 or abs(center.y) > 1e-6:
        raise AssertionError(f"key was not centered laterally: {tuple(center)}")
    expected_depth = original_center.z + coarse.z
    if abs(center.z - expected_depth) > 1e-8:
        raise AssertionError(
            f"insertion depth changed: expected {expected_depth}, got {center.z}"
        )
    angle = key.matrix_world.to_quaternion().rotation_difference(original_rotation).angle
    if abs(angle) > 1e-12:
        raise AssertionError(f"translation-only mode rotated the key by {angle}")


def compute_case(
    builder, source_face=None, target_face=None, source_name=None, allow_rotation=False
):
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = builder()
    return quicksnap_utils.compute_lock_key_transform(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True),
        source_name or key.name,
        key_face if source_face is None else source_face,
        key_hit,
        lock.name,
        lock_face if target_face is None else target_face,
        lock_hit,
        allow_rotation=allow_rotation,
    )


def make_irregular_pair():
    source = make_mesh(
        "OrganicKey",
        [(0, 0, 0), (1, 0, 0.1), (0.2, 1.1, -0.1), (0.1, 0.2, 1)],
        [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)],
    )
    target = make_mesh(
        "OrganicLock",
        [(2, 0, 0), (3, 0, 0.1), (2.2, 1.1, -0.1), (2.1, 0.2, 1)],
        [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)],
    )
    return source, 0, Vector((0.3, 0.3, 0)), target, 0, Vector((2.3, 0.3, 0))


def assert_rotated_alignment():
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_rotated_key_lock()
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit,
        lock.name, lock_face, lock_hit,
        allow_rotation=True,
    )
    if delta is None:
        raise AssertionError("expected a unique rigid connector transform")
    assert_matrix_finite(delta)
    key.matrix_world = delta @ key.matrix_world
    if key.matrix_world.to_quaternion().angle > 1e-6:
        raise AssertionError("rigid alignment did not restore the connector frame")
    center = key.matrix_world.translation
    if abs(center.x) > 1e-6 or abs(center.y) > 1e-6:
        raise AssertionError(f"rotated key was not centered: {tuple(center)}")
    if abs(center.z - (-0.2)) > 1e-6:
        raise AssertionError(f"rotation changed click-defined insertion depth: {center.z}")


def assert_smallest_equivalent_rotation():
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_rotated_key_lock(
        euler=(0.0, 0.0, math.radians(100.0)),
        source_half_height=0.5,
        source_depth=1.4,
        target_half_height=0.6,
        target_depth=1.6,
    )
    lock_face = 0
    lock_hit = lock.matrix_world @ Vector((0.0, -0.6, -0.5))
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit,
        lock.name, lock_face, lock_hit,
        allow_rotation=True,
    )
    if delta is None:
        raise AssertionError("expected a symmetric square connector transform")
    angle = delta.to_quaternion().angle
    if abs(angle - math.radians(10.0)) > 1e-6:
        raise AssertionError(f"expected the smallest 10 degree rotation, got {math.degrees(angle)}")


def assert_atomic_hierarchy_transform():
    clear_scene()
    parent, _, source_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    child = make_mesh(
        "KeyChild",
        [(0, 0, 0), (0.1, 0, 0), (0, 0.1, 0)],
        [(0, 1, 2)],
    )
    child.matrix_world.translation = (2.0, -1.0, 0.5)
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    parent.select_set(True)
    child.select_set(True)
    before_parent = parent.matrix_world.copy()
    before_child = child.matrix_world.copy()
    before_child_basis = child.matrix_basis.copy()

    operator = SimpleNamespace(report=lambda *args, **kwargs: None)
    for method_name in (
        "record_lock_key_source",
        "apply_world_delta_to_selection",
        "finish_lock_key",
    ):
        method = getattr(quicksnap.QuickVertexSnapOperator, method_name)
        setattr(operator, method_name, types.MethodType(method, operator))
    operator.selection_objects = [parent.name, child.name]
    operator.record_lock_key_source({
        'object_name': parent.name,
        'face_index': 5,
        'location': source_hit,
    })
    if parent.matrix_world != before_parent or child.matrix_world != before_child:
        raise AssertionError("recording the source surface moved the hierarchy")

    delta = quicksnap_utils.mathutils.Matrix.Translation((0.25, -0.5, 0.75))
    operator.apply_world_delta_to_selection(delta)
    bpy.context.view_layer.update()
    if parent.matrix_world != delta @ before_parent:
        raise AssertionError("selected root did not receive the world delta")
    if child.matrix_world != delta @ before_child:
        raise AssertionError("selected child did not inherit the root delta exactly once")
    if child.matrix_basis != before_child_basis:
        raise AssertionError("selected child was transformed directly as well as through its parent")

    parent.matrix_world = before_parent
    child.matrix_world = before_child
    operator.settings = SimpleNamespace(
        ignore_modifiers=True, lock_and_key_rotate=False
    )
    original_solver = quicksnap.quicksnap_utils.compute_lock_key_transform
    quicksnap.quicksnap_utils.compute_lock_key_transform = lambda *args, **kwargs: None
    try:
        result = operator.finish_lock_key(bpy.context, {
            'object_name': lock.name,
            'face_index': lock_face,
            'location': lock_hit,
        })
    finally:
        quicksnap.quicksnap_utils.compute_lock_key_transform = original_solver
    if result:
        raise AssertionError("solver failure was reported as a successful mate")
    if parent.matrix_world != before_parent or child.matrix_world != before_child:
        raise AssertionError("solver failure changed the selected hierarchy")


def assert_lock_key_settings_persist():
    annotations = quicksnap.QuickVertexSnapPreference.__annotations__
    for identifier in ("lock_and_key_mode", "lock_and_key_rotate"):
        prop = annotations.get(identifier)
        if prop is None or prop.function is not bpy.props.BoolProperty:
            raise AssertionError(f"{identifier} is not a Boolean preference")
        if prop.keywords.get("default") is not False:
            raise AssertionError(f"{identifier} must default off")

    properties = [
        SimpleNamespace(
            identifier="lock_and_key_mode", is_readonly=False
        ),
        SimpleNamespace(
            identifier="lock_and_key_rotate", is_readonly=False
        ),
    ]
    settings = SimpleNamespace(
        bl_rna=SimpleNamespace(properties=properties),
        lock_and_key_mode=True,
        lock_and_key_rotate=False,
    )
    original_get_settings = quicksnap.quicksnap_utils.get_addon_settings
    original_path = quicksnap.settings_file_path
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "quicksnap_settings.json")
        quicksnap.quicksnap_utils.get_addon_settings = lambda: settings
        quicksnap.settings_file_path = lambda: path
        try:
            quicksnap.save_settings()
            settings.lock_and_key_mode = False
            settings.lock_and_key_rotate = True
            quicksnap.load_settings()
        finally:
            quicksnap.quicksnap_utils.get_addon_settings = original_get_settings
            quicksnap.settings_file_path = original_path
    if (
        settings.lock_and_key_mode is not True
        or settings.lock_and_key_rotate is not False
    ):
        raise AssertionError("Lock and key preferences did not round-trip")


def main():
    run_lock_key_case()
    print("straight translation: PASS")
    run_lock_key_case(lambda: make_tapered_key_lock(15.0))
    print("tapered translation: PASS")
    assert compute_case(
        lambda: make_key_lock(taper_degrees=15.0, target_taper_degrees=5.0)
    ) is None
    assert compute_case(
        lambda: make_key_lock(target_half_width=0.5, target_half_height=0.4)
    ) is None
    assert compute_case(make_irregular_pair) is None
    assert compute_case(make_straight_key_lock, source_face=10_000) is None
    assert compute_case(make_straight_key_lock, source_name="MissingKey") is None
    print("fail-closed cases: PASS")
    assert compute_case(make_rotated_key_lock) is None
    assert_rotated_alignment()
    assert compute_case(make_single_direction_pair, allow_rotation=True) is None
    assert compute_case(
        lambda: make_rotated_key_lock(
            taper_degrees=15.0, target_taper_degrees=5.0
        ),
        allow_rotation=True,
    ) is None
    assert_smallest_equivalent_rotation()
    print("optional rotation: PASS")
    assert_atomic_hierarchy_transform()
    print("atomic hierarchy transform: PASS")
    assert_lock_key_settings_persist()
    print("Lock and key settings: PASS")
    print("lock_key_regression: PASS")


if __name__ == "__main__":
    main()
