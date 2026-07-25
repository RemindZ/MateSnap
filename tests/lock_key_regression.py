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


def make_singular_key_lock():
    key, key_face, _, lock, lock_face, lock_hit = make_straight_key_lock()
    key.scale.x = 0.0
    bpy.context.view_layer.update()
    key_hit = key.matrix_world @ Vector((-0.5, 0.0, -0.3))
    return key, key_face, key_hit, lock, lock_face, lock_hit


def assert_matrix_finite(matrix):
    values = np.array(matrix, dtype=np.float64)
    if values.shape != (4, 4) or not np.isfinite(values).all():
        raise AssertionError(f"expected finite 4x4 matrix, got {matrix!r}")


LOCK_KEY_OPERATOR_METHODS = (
    "lock_key_fit_object",
    "lock_key_mesh_data",
    "lock_key_neighborhood",
    "lock_key_geometry_signature",
    "reset_lock_key_source",
    "lock_key_moving_names",
    "lock_key_base_bvh",
    "lock_key_raycast_object",
    "lock_key_hit",
    "lock_key_ray_hits_bounds",
    "lock_key_raycast_scene",
    "lock_key_raycast_visible",
    "raycast_lock_key_surface",
    "record_lock_key_source",
    "apply_world_delta_to_selection",
    "finish_lock_key",
)

# Pulled from __dict__ so descriptors (staticmethod) survive; a plain getattr would
# rebind them as instance methods.
LockKeyStub = type("LockKeyStub", (), {
    name: quicksnap.QuickVertexSnapOperator.__dict__[name]
    for name in LOCK_KEY_OPERATOR_METHODS
})


def make_lock_key_operator(selection_names, ignore_modifiers=False):
    """A stub carrying just enough operator state to drive the real picking path."""
    operator = LockKeyStub()
    operator.report = lambda *args, **kwargs: None
    operator.settings = SimpleNamespace(
        ignore_modifiers=ignore_modifiers, lock_and_key_rotate=False
    )
    operator.selection_objects = list(selection_names)
    operator.lock_key_source_hit = None
    operator.lock_key_target_preview = None
    operator.lock_key_moving = None
    operator.lock_key_source_preview = None
    operator.current_state = quicksnap.State.IDLE
    operator._lock_key_bvh_cache = {}
    operator._lock_key_mesh_cache = {}
    operator._lock_key_patch_cache = {}
    return operator


def pick_surface(operator, origin, direction, selected_only):
    operator.mouse_position_world = Vector(origin)
    operator.mouse_vector = Vector(direction).normalized()
    return operator.raycast_lock_key_surface(
        bpy.context, selected_only=selected_only
    )


def make_modified_key_lock(modify_source=True, modify_target=False):
    """Straight connectors plus a planar topology change.

    TRIANGULATE keeps every wall flat, so the connector stays supported while the
    base and evaluated polygon indices diverge. That divergence is the whole point:
    it is what a raw/evaluated mismatch in the picking path looks like.
    """
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    if modify_source:
        key.modifiers.new("PlanarTopologyChange", 'TRIANGULATE')
    if modify_target:
        lock.modifiers.new("PlanarTopologyChange", 'TRIANGULATE')
    bpy.context.view_layer.update()
    return key, key_face, key_hit, lock, lock_face, lock_hit


def mate_through_picking_path(key, lock, ignore_modifiers):
    """Run the whole pipeline: raycast -> seed -> extraction -> transform."""
    operator = make_lock_key_operator([key.name], ignore_modifiers)
    source = pick_surface(
        operator, (-4.0, -1.0, -0.3), (1.0, 0.0, 0.0), selected_only=True
    )
    if source is None or source['object_name'] != key.name:
        raise AssertionError(
            f"source pick missed the key: {source!r} (ignore_modifiers={ignore_modifiers})"
        )
    target = pick_surface(
        operator, (0.0, 0.1, -0.5), (-1.0, 0.0, 0.0), selected_only=False
    )
    if target is None or target['object_name'] != lock.name:
        raise AssertionError(
            f"target pick missed the lock: {target!r} (ignore_modifiers={ignore_modifiers})"
        )
    return quicksnap_utils.compute_lock_key_transform(
        bpy.context,
        operator.settings,
        source['object_name'], source['face_index'], source['location'],
        target['object_name'], target['face_index'], target['location'],
        allow_rotation=False,
    )


def assert_modifier_path_is_consistent():
    """The face index must come from the same geometry the solver reads.

    Design spec: "The face index used for feature extraction must come from the
    same raw/evaluated geometry that produced the stored hit."
    """
    for label, modify_source, modify_target in (
        ("source", True, False),
        ("target", False, True),
        ("both", True, True),
    ):
        for ignore_modifiers in (False, True):
            clear_scene()
            key, _, _, lock, _, _ = make_modified_key_lock(
                modify_source=modify_source, modify_target=modify_target
            )
            delta = mate_through_picking_path(key, lock, ignore_modifiers)
            if delta is None:
                raise AssertionError(
                    f"modified {label} mesh produced no mate "
                    f"(ignore_modifiers={ignore_modifiers})"
                )
            assert_matrix_finite(delta)
            key.matrix_world = delta @ key.matrix_world
            center = key.matrix_world.translation
            if abs(center.x) > 1e-6 or abs(center.y) > 1e-6:
                raise AssertionError(
                    f"modified {label} mesh was not centered laterally: "
                    f"{tuple(center)} (ignore_modifiers={ignore_modifiers})"
                )
            if abs(center.z - (-0.2)) > 1e-6:
                raise AssertionError(
                    f"modified {label} mesh lost its click-defined depth: "
                    f"{center.z} (ignore_modifiers={ignore_modifiers})"
                )


def make_hierarchy_scene():
    """A key with an unselected mesh child that blocks the ray to the lock."""
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    blocker = make_mesh(
        "KeyBlocker",
        [(0.0, -1.0, -1.5), (0.0, 1.0, -1.5), (0.0, 1.0, 1.5), (0.0, -1.0, 1.5)],
        [(0, 1, 2, 3)],
    )
    blocker.location = (5.0, 0.0, 0.0)
    blocker.parent = key
    blocker.matrix_parent_inverse = key.matrix_world.inverted()
    bpy.context.view_layer.update()
    return key, blocker, lock


def make_prism(name, sides, radius, depth):
    """A faceted round peg -- an explicit design non-goal, but users still click one."""
    vertices = []
    for offset in (0.0, -depth):
        for index in range(sides):
            angle = 2.0 * math.pi * index / sides
            vertices.append(
                (radius * math.cos(angle), radius * math.sin(angle), offset)
            )
    faces = [
        (index, (index + 1) % sides,
         sides + (index + 1) % sides, sides + index)
        for index in range(sides)
    ]
    faces.append(tuple(range(sides)))
    return make_mesh(name, vertices, faces)


def count_rotation_fits(callable_under_test):
    """Run something while counting Kabsch solves, the rotation search's work unit."""
    calls = []
    original = quicksnap_utils._fit_connector_rotation

    def counting(correspondences):
        calls.append(1)
        return original(correspondences)

    quicksnap_utils._fit_connector_rotation = counting
    try:
        result = callable_under_test()
    finally:
        quicksnap_utils._fit_connector_rotation = original
    return result, len(calls)


def assert_rotation_search_is_bounded():
    """The rotation enumeration is quadratic in each pair list.

    A 16-sided peg produced 61 pairs and took ~20 seconds to reject before this was
    bounded -- a synchronous freeze inside the modal. Asserted on solve count rather
    than wall time so the bound cannot go flaky.
    """
    clear_scene()
    key = make_prism("RoundKey", 16, 0.50, 1.0)
    lock = make_prism("RoundLock", 16, 0.62, 1.2)
    key.location = (4.0, 0.0, 0.0)
    key.rotation_euler = Euler((0.0, 0.0, math.radians(7.0)), 'XYZ')
    bpy.context.view_layer.update()
    key_hit = key.matrix_world @ Vector((0.50, 0.0, -0.3))
    lock_hit = lock.matrix_world @ Vector((0.62, 0.0, -0.3))

    delta, fits = count_rotation_fits(
        lambda: quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 0, key_hit, lock.name, 0, lock_hit,
            allow_rotation=True,
        )
    )
    if delta is not None:
        raise AssertionError("round connector must fail closed, not mate")
    if fits != 0:
        raise AssertionError(
            f"round connector should be rejected before any rotation solve, "
            f"got {fits}"
        )

    # ...and the supported shape must still resolve, with bounded work.
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_rotated_key_lock()
    delta, fits = count_rotation_fits(
        lambda: quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
            allow_rotation=True,
        )
    )
    if delta is None:
        raise AssertionError("bounding the search broke the supported connector")
    if fits > 64:
        raise AssertionError(f"rotation search is not bounded: {fits} solves")


def make_floored_lock_scene(euler):
    """A rotated key and a socket that has a floor, so the target click can land
    on the floor rather than on an inner wall."""
    key = make_mesh(
        "Key",
        [(-.5, -.4, -1), (.5, -.4, -1), (.5, .4, -1), (-.5, .4, -1),
         (-.5, -.4, 0), (.5, -.4, 0), (.5, .4, 0), (-.5, .4, 0)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    lock = make_mesh(
        "Lock",
        [(-.6, -.5, 0), (.6, -.5, 0), (.6, .5, 0), (-.6, .5, 0),
         (-.6, -.5, -1.2), (.6, -.5, -1.2), (.6, .5, -1.2), (-.6, .5, -1.2)],
        [(1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3), (4, 5, 6, 7)],
    )
    key.location = (2.0, -1.0, 0.0)
    key.rotation_euler = Euler(euler, 'XYZ')
    bpy.context.view_layer.update()
    return key, lock


def assert_insertion_direction_is_constrained():
    """A rigid candidate must never seat the key pointing out of the socket.

    Lateral clearance says nothing about the insertion axis. With the key starting
    near a flipped orientation, the end-for-end solution is the *smallest* rotation,
    so smallest-angle ranking alone will happily pick a key inserted backwards.
    """
    for label, euler in (
        ("upright", (0.35, -0.25, 0.5)),
        ("near-flipped", (math.pi - 0.2, -0.1, 0.2)),
    ):
        clear_scene()
        key, lock = make_floored_lock_scene(euler)
        source_hit = key.matrix_world @ Vector((-0.5, 0.0, -0.3))
        floor_hit = Vector((-0.5, 0.0, -1.2))
        floor_normal = Vector((0.0, 0.0, 1.0))
        insertion = key.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0))

        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 5, source_hit, lock.name, 4, floor_hit,
            allow_rotation=True, target_normal=floor_normal,
        )
        if delta is not None:
            seated = delta.to_3x3() @ insertion
            if seated.z >= 0.0:
                raise AssertionError(
                    f"{label}: mate seats the key pointing out of the socket "
                    f"(insertion z={seated.z:+.3f})"
                )

        # Without a target normal nothing can constrain the insertion axis, so the
        # mixed wall/floor mapping must not be enumerated at all.
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 5, source_hit, lock.name, 4, floor_hit,
            allow_rotation=True,
        )
        if delta is not None:
            seated = delta.to_3x3() @ insertion
            if seated.z >= 0.0:
                raise AssertionError(
                    f"{label}: unguarded mate seats the key pointing out of the "
                    f"socket (insertion z={seated.z:+.3f})"
                )


def assert_source_mesh_extracted_once():
    """Extraction dominates the cost on dense meshes: one per object per mate."""
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    operator = make_lock_key_operator([key.name], ignore_modifiers=True)
    counts = {}
    module = quicksnap.quicksnap_utils
    original = module._mesh_fit_data

    def counting(obj):
        counts[obj.name] = counts.get(obj.name, 0) + 1
        return original(obj)

    module._mesh_fit_data = counting
    try:
        operator.record_lock_key_source(
            {
                'object_name': key.name,
                'face_index': key_face,
                'location': key_hit,
            },
            bpy.context,
        )
        result = operator.finish_lock_key(bpy.context, {
            'object_name': lock.name,
            'face_index': lock_face,
            'location': lock_hit,
        })
    finally:
        module._mesh_fit_data = original
    if not result:
        raise AssertionError("mate failed with the extraction cache enabled")
    if counts.get(key.name) != 1 or counts.get(lock.name) != 1:
        raise AssertionError(
            f"expected one extraction per object per mate, got {counts}"
        )


def assert_moving_hierarchy_is_handled():
    """Descendants ride along with the key, so they are source-pickable and
    must never be accepted as the stationary lock."""
    clear_scene()
    key, blocker, lock = make_hierarchy_scene()
    operator = make_lock_key_operator([key.name])

    moving = operator.lock_key_moving_names()
    if moving != {key.name, blocker.name}:
        raise AssertionError(f"moving set wrong: {moving!r}")

    source = pick_surface(
        operator, (10.0, 0.1, -0.5), (-1.0, 0.0, 0.0), selected_only=True
    )
    if source is None or source['object_name'] != blocker.name:
        raise AssertionError(
            f"unselected descendant of the key was not source-pickable: {source!r}"
        )

    target = pick_surface(
        operator, (10.0, 0.1, -0.5), (-1.0, 0.0, 0.0), selected_only=False
    )
    if target is None:
        raise AssertionError("target pick found nothing behind the moving child")
    if target['object_name'] != lock.name:
        raise AssertionError(
            f"target pick accepted part of the moving hierarchy: {target!r}"
        )


def assert_preview_does_not_mutate_scene():
    """Spec: mouse movement must not translate, rotate or hide the selected part.

    Hiding also drops objects from the selection without restoring it, so the
    preview raycast must leave visibility and selection completely alone.
    """
    clear_scene()
    key, blocker, lock = make_hierarchy_scene()
    key.select_set(True)
    blocker.hide_set(True)
    bpy.context.view_layer.update()

    watched = [key, blocker, lock]
    before = [
        (obj.name, obj.hide_get(), obj.select_get(), obj.matrix_world.copy())
        for obj in watched
    ]
    operator = make_lock_key_operator([key.name])
    for selected_only in (True, False):
        pick_surface(
            operator, (10.0, 0.1, -0.5), (-1.0, 0.0, 0.0),
            selected_only=selected_only,
        )
    after = [
        (obj.name, obj.hide_get(), obj.select_get(), obj.matrix_world.copy())
        for obj in watched
    ]
    if before != after:
        raise AssertionError(
            f"preview raycast mutated scene state:\n  before={before}\n  after={after}"
        )


def assert_non_uniform_transform_mate():
    """Non-uniform object scale still produces a correct world-space mate."""
    for ignore_modifiers in (False, True):
        clear_scene()
        key, _, _, lock, _, _ = make_straight_key_lock()
        key.scale = (0.8, 0.6, 1.0)
        bpy.context.view_layer.update()
        delta = mate_through_picking_path(key, lock, ignore_modifiers)
        if delta is None:
            raise AssertionError(
                f"non-uniform scale produced no mate "
                f"(ignore_modifiers={ignore_modifiers})"
            )
        assert_matrix_finite(delta)
        key.matrix_world = delta @ key.matrix_world
        center = key.matrix_world.translation
        if abs(center.x) > 1e-6 or abs(center.y) > 1e-6:
            raise AssertionError(
                f"non-uniformly scaled key was not centered: {tuple(center)} "
                f"(ignore_modifiers={ignore_modifiers})"
            )


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

    operator = make_lock_key_operator(
        [parent.name, child.name], ignore_modifiers=True
    )
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

    quicksnap.quicksnap_utils.compute_lock_key_transform = (
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad mesh"))
    )
    logger_disabled = quicksnap.logger.disabled
    quicksnap.logger.disabled = True
    try:
        result = operator.finish_lock_key(bpy.context, {
            'object_name': lock.name,
            'face_index': lock_face,
            'location': lock_hit,
        })
    finally:
        quicksnap.quicksnap_utils.compute_lock_key_transform = original_solver
        quicksnap.logger.disabled = logger_disabled
    if result or parent.matrix_world != before_parent:
        raise AssertionError("solver exception did not fail closed")


def assert_changed_source_face_rejected():
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    operator = make_lock_key_operator([key.name], ignore_modifiers=True)
    signature = operator.lock_key_geometry_signature(
        bpy.context, key.name, key_face
    )
    operator.record_lock_key_source({
        'object_name': key.name,
        'face_index': key_face,
        'location': key_hit,
        'geometry_signature': signature,
    })
    before = key.matrix_world.copy()
    key.data.vertices[1].co.x += 0.2
    key.data.update()
    original_solver = quicksnap.quicksnap_utils.compute_lock_key_transform
    quicksnap.quicksnap_utils.compute_lock_key_transform = (
        lambda *args, **kwargs:
        quicksnap_utils.mathutils.Matrix.Translation((1, 0, 0))
    )
    try:
        result = operator.finish_lock_key(bpy.context, {
            'object_name': lock.name,
            'face_index': lock_face,
            'location': lock_hit,
        })
    finally:
        quicksnap.quicksnap_utils.compute_lock_key_transform = original_solver
    if result or key.matrix_world != before:
        raise AssertionError("changed in-range source face did not fail closed")


def make_switch_stub(calls, lock_and_key_mode, object_mode=True, no_selection=False):
    operator = SimpleNamespace(
        set_selection_hidden=lambda hidden: calls.append(("hidden", hidden)),
        revert_data=lambda context, apply=False: calls.append(("revert", apply)),
        set_object_display=lambda *args: calls.append(("display", args)),
        initialize=lambda context: calls.append(("initialize", None)) or True,
        update_header=lambda context: calls.append(("header", None)),
        report=lambda *args, **kwargs: calls.append(("report", args)),
        settings=SimpleNamespace(lock_and_key_mode=lock_and_key_mode),
        object_mode=object_mode,
        no_selection=no_selection,
        snapdata_source="live-source",
        snapdata_target=None,
        current_state=quicksnap.State.SOURCE_PICKED,
        closest_source_id=5000,
        closest_target_id=17,
        closest_actionable=True,
    )
    for method_name in ("can_enter_lock_key_mode", "switch_lock_key_mode"):
        method = quicksnap.QuickVertexSnapOperator.__dict__[method_name]
        setattr(operator, method_name, types.MethodType(method, operator))
    return operator


def assert_mode_switch_reinitializes_in_place():
    calls = []
    operator = make_switch_stub(calls, lock_and_key_mode=False)
    if not operator.switch_lock_key_mode(None):
        raise AssertionError("pie workflow change did not reinitialize in place")
    if ("revert", True) not in calls or ("initialize", None) not in calls:
        raise AssertionError("pie workflow change did not reset and reinitialize in place")
    # The normal initialize() never resets these; a stale SOURCE_PICKED with a stale
    # id makes the next apply() read rows numpy never wrote.
    if (
        operator.current_state is not quicksnap.State.IDLE
        or operator.closest_source_id != -1
        or operator.closest_target_id != -1
        or operator.closest_actionable
    ):
        raise AssertionError(
            "mode switch left stale snap state behind: "
            f"state={operator.current_state} source={operator.closest_source_id} "
            f"target={operator.closest_target_id} actionable={operator.closest_actionable}"
        )


def assert_refused_mode_switch_is_transactional():
    """A refused switch must not tear anything down.

    initialize() destroys the live SnapData, so refusing after the fact would leave
    nothing to fall back to and discard an in-progress snap over a pie click.
    """
    for label, object_mode, no_selection in (
        ("edit mode", False, False),
        ("empty selection", True, True),
    ):
        calls = []
        operator = make_switch_stub(
            calls, lock_and_key_mode=True,
            object_mode=object_mode, no_selection=no_selection,
        )
        if not operator.switch_lock_key_mode(None):
            raise AssertionError(f"{label}: refused switch cancelled the operator")
        if any(name in ("revert", "initialize", "display") for name, _ in calls):
            raise AssertionError(
                f"{label}: refused switch tore down modal state: {calls}"
            )
        if operator.snapdata_source != "live-source":
            raise AssertionError(f"{label}: refused switch dropped the live SnapData")
        if operator.settings.lock_and_key_mode:
            raise AssertionError(f"{label}: refused switch left the preference on")
        if operator.current_state is not quicksnap.State.SOURCE_PICKED:
            raise AssertionError(f"{label}: refused switch disturbed the modal state")


def assert_terminate_survives_empty_selection():
    """Finishing with nothing selected must not crash the modal.

    Running the tool with no selection and clicking without picking anything
    leaves both the active object and the selection empty. Indexing
    selected_objects[0] there raised IndexError out of modal(), aborting cleanup
    partway through.
    """
    ensure_active = quicksnap.QuickVertexSnapOperator.__dict__[
        "ensure_active_object"
    ].__func__

    class FakeContext:
        """active_object tracks view_layer.objects.active, as Blender's does."""

        def __init__(self, selected, active):
            self.selected_objects = list(selected)
            self.view_layer = SimpleNamespace(
                objects=SimpleNamespace(active=active)
            )

        @property
        def active_object(self):
            return self.view_layer.objects.active

    context = FakeContext([], None)
    if ensure_active(context) is not False:
        raise AssertionError("empty selection should report no active object")
    if context.view_layer.objects.active is not None:
        raise AssertionError("nothing should have been promoted to active")

    clear_scene()
    key, _, _, lock, _, _ = make_straight_key_lock()
    context = FakeContext([key, lock], None)
    if ensure_active(context) is not True:
        raise AssertionError("a selection should yield an active object")
    if context.view_layer.objects.active is not key:
        raise AssertionError("first selected object was not promoted to active")

    context = FakeContext([key, lock], lock)
    if ensure_active(context) is not True:
        raise AssertionError("an existing active object should be kept")
    if context.view_layer.objects.active is not lock:
        raise AssertionError("an existing active object must not be replaced")


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
    assert compute_case(make_singular_key_lock) is None
    assert_smallest_equivalent_rotation()
    print("optional rotation: PASS")
    assert_modifier_path_is_consistent()
    print("raw/evaluated picking path: PASS")
    assert_non_uniform_transform_mate()
    print("non-uniform transform: PASS")
    assert_rotation_search_is_bounded()
    print("bounded rotation search: PASS")
    assert_insertion_direction_is_constrained()
    print("insertion direction constrained: PASS")
    assert_source_mesh_extracted_once()
    print("single extraction per object: PASS")
    assert_moving_hierarchy_is_handled()
    print("moving hierarchy: PASS")
    assert_preview_does_not_mutate_scene()
    print("preview leaves scene untouched: PASS")
    assert_atomic_hierarchy_transform()
    print("atomic hierarchy transform: PASS")
    assert_changed_source_face_rejected()
    print("changed source face: PASS")
    assert_mode_switch_reinitializes_in_place()
    print("mode switch: PASS")
    assert_refused_mode_switch_is_transactional()
    print("refused mode switch is transactional: PASS")
    assert_terminate_survives_empty_selection()
    print("terminate with empty selection: PASS")
    assert_lock_key_settings_persist()
    print("Lock and key settings: PASS")
    print("lock_key_regression: PASS")


if __name__ == "__main__":
    main()
