import importlib.util
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import types

import bpy
from mathutils import Euler, Matrix, Vector
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


def assert_blender_5_metadata():
    package_spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    package = importlib.util.module_from_spec(package_spec)
    sys.modules[PACKAGE_NAME] = package
    reload_module = importlib.reload

    def reload_without_background_shader(module):
        if module.__name__ == RENDER_STUB.__name__:
            return module
        return reload_module(module)

    importlib.reload = reload_without_background_shader
    try:
        package_spec.loader.exec_module(package)
    finally:
        importlib.reload = reload_module
    if package.bl_info["blender"] != (5, 0, 0):
        raise AssertionError(
            f"expected Blender 5 baseline, got {package.bl_info['blender']!r}"
        )
    if package.bl_info["version"] != (2, 3, 1):
        raise AssertionError(
            f"expected MateSnap 2.3.0, got {package.bl_info['version']!r}"
        )


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
    # The default lock is 1.2 x 1.0 and the key 1.0 x 0.8, so a 90 degree turn also
    # seats the key exactly (1.0 into 1.0). That is a real second solution and the
    # solver rightly refuses to choose between them, which makes the default a poor
    # fixture for "there is one unique rotation". Narrow the lock so only the
    # intended orientation fits.
    kwargs.setdefault("target_half_height", 0.45)
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
    "lock_key_provider",
    "lock_key_mesh_data",
    "solve_lock_key",
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
    "lock_key_centre_hit",
    "record_lock_key_source",
    "apply_world_delta_to_selection",
    "log_lock_key_refusal",
    "lock_key_log_path",
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
        ignore_modifiers=ignore_modifiers, lock_and_key_rotate=False,
        lock_and_key_centre_picks=True,
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


def assert_realistic_clearance_mates():
    """Printed connectors are modelled with about 1% clearance, sometimes less.

    The clearance test used to run against the flatness tolerance, which scales
    with patch size and demanded roughly 2% on a 10-unit peg -- so well-modelled
    parts were refused for being too well fitted. Clearance is judged against how
    precisely the planes are defined instead.
    """
    def peg_and_socket(half, gap, depth):
        """Everything scales together, including where the user clicks."""
        key = make_mesh(
            "Key",
            [(-half,-half,-depth),(half,-half,-depth),(half,half,-depth),(-half,half,-depth),
             (-half,-half,0.0),(half,-half,0.0),(half,half,0.0),(-half,half,0.0)],
            [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],
        )
        outer = half + gap
        lock = make_mesh(
            "Lock",
            [(-outer,-outer,0.0),(outer,-outer,0.0),(outer,outer,0.0),(-outer,outer,0.0),
             (-outer,-outer,-depth*1.2),(outer,-outer,-depth*1.2),
             (outer,outer,-depth*1.2),(-outer,outer,-depth*1.2)],
            [(1,5,4,0),(2,6,5,1),(3,7,6,2),(0,4,7,3)],
        )
        key.location = (half * 8.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        return (key, 5, key.matrix_world @ Vector((-half, 0.0, -depth * 0.3)),
                lock, 3, lock.matrix_world @ Vector((-outer, 0.0, -depth * 0.4)))

    for gap_ratio in (0.05, 0.02, 0.01, 0.005, 0.002):
        for scale in (0.1, 1.0, 100.0):
            clear_scene()
            half = 0.5 * scale
            key, key_face, key_hit, lock, lock_face, lock_hit = peg_and_socket(
                half, half * gap_ratio, scale
            )
            delta = quicksnap_utils.compute_lock_key_transform(
                bpy.context, SimpleNamespace(ignore_modifiers=True),
                key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
                allow_rotation=False,
            )
            if delta is None:
                raise AssertionError(
                    f"a {gap_ratio:.1%} clearance connector at scale {scale} was "
                    f"refused; printed parts are modelled this tightly"
                )

    # A designer who built in no tolerance at all still gets a mate: a snug fit is
    # a real design, and its seated position is the most determined of any.
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = peg_and_socket(
        5.0, 0.0, 10.0
    )
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
        allow_rotation=False,
    )
    if delta is None:
        raise AssertionError("a snug zero-clearance connector should still mate")
    key.matrix_world = delta @ key.matrix_world
    centre = key.matrix_world.translation
    if abs(centre.x) > 1e-6 or abs(centre.y) > 1e-6:
        raise AssertionError(f"snug fit was not centred: {tuple(centre)}")

    # A key genuinely wider than its lock cannot be seated, and must fail closed.
    for gap in (-0.05, -0.5):
        clear_scene()
        key, key_face, key_hit, lock, lock_face, lock_hit = peg_and_socket(
            5.0, gap, 10.0
        )
        if quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
            allow_rotation=False,
        ) is not None:
            raise AssertionError(
                f"a key wider than its lock (gap {gap}) must fail closed"
            )


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


def make_floored_lock_scene(euler, disconnected_floor=False, taper=0.0):
    """A rotated key and a socket that has a floor, so the target click can land
    on the floor rather than on an inner wall."""
    slope = math.tan(math.radians(taper))
    key_tip_x, key_tip_y = 0.5 - slope, 0.4 - slope
    lock_tip_x, lock_tip_y = 0.6 - 1.2 * slope, 0.5 - 1.2 * slope
    key = make_mesh(
        "Key",
        [(-key_tip_x, -key_tip_y, -1), (key_tip_x, -key_tip_y, -1),
         (key_tip_x, key_tip_y, -1), (-key_tip_x, key_tip_y, -1),
         (-.5, -.4, 0), (.5, -.4, 0), (.5, .4, 0), (-.5, .4, 0)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    floor_vertices = [(-lock_tip_x, -lock_tip_y, -1.2),
                      (lock_tip_x, -lock_tip_y, -1.2),
                      (lock_tip_x, lock_tip_y, -1.2),
                      (-lock_tip_x, lock_tip_y, -1.2)]
    lock = make_mesh(
        "Lock",
        [(-.6, -.5, 0), (.6, -.5, 0), (.6, .5, 0), (-.6, .5, 0),
         *floor_vertices,
         *(floor_vertices if disconnected_floor else [])],
        [(1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3),
         (8, 9, 10, 11) if disconnected_floor else (4, 5, 6, 7)],
    )
    key.location = (2.0, -1.0, 0.0)
    key.rotation_euler = Euler(euler, 'XYZ')
    bpy.context.view_layer.update()
    return key, lock


def disconnected_floored_lock(euler=(0.35, -0.25, 0.5), taper=0.0):
    """A socket whose floor is a separate mesh island from its walls."""
    key, lock = make_floored_lock_scene(
        euler, disconnected_floor=True, taper=taper
    )
    return key, lock, 4


def world_normal(obj, face_index):
    normal = obj.matrix_world.to_3x3().inverted().transposed() @ obj.data.polygons[face_index].normal
    return normal.normalized()


def assert_disconnected_floor_end_face_rotation():
    """A disconnected socket floor must not make a valid end-face mate impossible."""
    clear_scene()
    key, lock, floor_face = disconnected_floored_lock()
    key_face = 0
    key_hit = key.matrix_world @ key.data.polygons[key_face].center
    floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
    source_normal = world_normal(key, key_face)
    target_normal = world_normal(lock, floor_face)

    source_data = quicksnap_utils._mesh_fit_data(key)
    source_pairs, _ = quicksnap_utils._connector_pairs(
        source_data,
        quicksnap_utils._seed_polygons(source_data, 'FACES', key_face),
        np.array(key_hit, dtype=np.float64), 'key',
    )
    source_axes = quicksnap_utils._independent_axis_count(source_pairs)
    if source_axes < 2:
        raise AssertionError(
            f"fixture exposed only {source_axes} independent source axes"
        )

    target_data = quicksnap_utils._mesh_fit_data(lock)
    target_pairs, _ = quicksnap_utils._connector_pairs(
        target_data,
        quicksnap_utils._seed_polygons(target_data, 'FACES', floor_face),
        np.array(floor_hit, dtype=np.float64), 'lock',
    )
    if target_pairs:
        raise AssertionError(
            f"fixture floor reconnected to {len(target_pairs)} target wall pairs"
        )

    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit, lock.name, floor_face, floor_hit,
        allow_rotation=True, source_normal=source_normal, target_normal=target_normal,
    )
    if delta is None:
        raise AssertionError(
            "a centered end-face/disconnected-floor mate returned no transform"
        )
    assert_matrix_finite(delta)
    landed_hit = delta @ key_hit
    if (landed_hit - floor_hit).length > 1e-6:
        raise AssertionError(
            f"end face did not preserve the target floor coordinate: {landed_hit[:]}"
        )
    key.matrix_world = delta @ key.matrix_world
    if abs(key.matrix_world.translation.x) > 1e-6 or abs(key.matrix_world.translation.y) > 1e-6:
        raise AssertionError(f"mate was not laterally centered: {key.matrix_world.translation[:]}")
    if (delta.to_3x3() @ source_normal).dot(target_normal) > -math.cos(math.radians(10.0)):
        raise AssertionError("clicked end and floor faces were not opposed within ten degrees")


def assert_disconnected_recovery_handles_draft_and_scale():
    for label, taper, scale in (
        ('drafted', 7.0, (1.0, 1.0, 1.0)),
        ('non-uniform', 0.0, (1.4, 0.8, 1.2)),
    ):
        clear_scene()
        key, lock, floor_face = disconnected_floored_lock(taper=taper)
        key.scale = scale
        lock.scale = scale
        bpy.context.view_layer.update()
        key_hit = key.matrix_world @ key.data.polygons[0].center
        floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 0, key_hit, lock.name, floor_face, floor_hit,
            allow_rotation=True,
            source_normal=world_normal(key, 0),
            target_normal=world_normal(lock, floor_face),
        )
        if delta is None:
            raise AssertionError(f"{label} disconnected-floor recovery was refused")
        assert_matrix_finite(delta)


def assert_disconnected_search_stops_when_saturated():
    clear_scene()
    _key, lock, floor_face = disconnected_floored_lock()
    floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
    mesh_data = quicksnap_utils._mesh_fit_data(lock)
    seeds = quicksnap_utils._seed_polygons(mesh_data, 'FACES', floor_face)
    calls = []
    original = quicksnap_utils._connector_walls

    def counting(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    quicksnap_utils._connector_walls = counting
    try:
        pairs, _reason = quicksnap_utils._connector_pairs(
            mesh_data, seeds, np.array(floor_hit, dtype=np.float64), 'lock'
        )
    finally:
        quicksnap_utils._connector_walls = original
    if pairs:
        raise AssertionError("disconnected floor unexpectedly found topology-local pairs")
    if len(calls) > 5:
        raise AssertionError(
            f"saturated disconnected search repeated {len(calls)} wall traversals"
        )


def make_spatial_recovery_decoy(kind):
    key, stale_lock = make_floored_lock_scene((0.35, -0.25, 0.5))
    bpy.data.objects.remove(stale_lock, do_unlink=True)
    vertices = []
    faces = []

    def quad(points):
        start = len(vertices)
        vertices.extend(points)
        faces.append(tuple(range(start, start + 4)))

    def cavity(x_half, y_half, z_low, z_high, x_span=None, y_span=None):
        x_low, x_high = x_span or (-x_half, x_half)
        y_low, y_high = y_span or (-y_half, y_half)
        quad([(-x_half, y_low, z_high), (-x_half, y_low, z_low),
              (-x_half, y_high, z_low), (-x_half, y_high, z_high)])
        quad([(x_half, y_high, z_high), (x_half, y_high, z_low),
              (x_half, y_low, z_low), (x_half, y_low, z_high)])
        quad([(x_high, -y_half, z_high), (x_high, -y_half, z_low),
              (x_low, -y_half, z_low), (x_low, -y_half, z_high)])
        quad([(x_low, y_half, z_high), (x_low, y_half, z_low),
              (x_high, y_half, z_low), (x_high, y_half, z_high)])

    if kind == 'cross':
        cavity(0.6, 0.5, -1.2, 0.0, x_span=(0.25, 0.75), y_span=(0.25, 0.75))
    elif kind == 'stacked':
        cavity(0.6, 0.5, -1.2, -0.7)
        cavity(0.6, 0.5, -0.5, 0.0)
    elif kind == 'fragmented':
        cavity(0.6, 0.5, -1.2, -0.6)
        cavity(0.6, 0.5, -0.6, 0.0)
    elif kind == 'one-axis':
        cavity(0.6, 0.5, -1.2, 0.0)
        del faces[2:]
        del vertices[8:]
    elif kind == 'remote':
        cavity(0.6, 0.5, -1.2, 0.0)
        vertices[:] = [(x + 3.0, y, z) for x, y, z in vertices]
    elif kind == 'behind':
        cavity(0.6, 0.5, -2.4, -1.4)
    elif kind == 'body':
        cavity(3.0, 2.0, -1.2, 0.0)
    elif kind == 'overlap':
        quad([(-0.6, -0.7, 0.0), (-0.6, -0.7, -1.2),
              (-0.6, 1.1, -1.2), (-0.6, 1.1, 0.0)])
        quad([(0.6, 1.1, 0.0), (0.6, 1.1, -1.2),
              (0.6, -0.7, -1.2), (0.6, -0.7, 0.0)])
        quad([(1.2, -0.65, 0.0), (1.2, -0.65, -1.2),
              (-0.8, -0.65, -1.2), (-0.8, -0.65, 0.0)])
        quad([(-0.8, 0.35, 0.0), (-0.8, 0.35, -1.2),
              (1.2, 0.35, -1.2), (1.2, 0.35, 0.0)])
    else:
        raise AssertionError(f"unknown spatial recovery decoy {kind!r}")

    floor_start = len(vertices)
    vertices.extend([(-0.2, -0.2, -1.2), (0.2, -0.2, -1.2),
                     (0.2, 0.2, -1.2), (-0.2, 0.2, -1.2)])
    faces.append(tuple(range(floor_start, floor_start + 4)))
    lock = make_mesh(f"SpatialRecovery{kind.title()}", vertices, faces)
    bpy.context.view_layer.update()
    return key, lock, len(faces) - 1


def assert_spatial_recovery_rejects_incoherent_frames():
    for kind in ('cross', 'stacked', 'overlap'):
        clear_scene()
        key, lock, floor_face = make_spatial_recovery_decoy(kind)
        key_hit = key.matrix_world @ key.data.polygons[0].center
        floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 0, key_hit, lock.name, floor_face, floor_hit,
            allow_rotation=True,
            source_normal=world_normal(key, 0),
            target_normal=world_normal(lock, floor_face),
        )
        if delta is not None:
            raise AssertionError(
                f"spatial recovery synthesized a connector from {kind} cavity walls"
            )


def assert_spatial_recovery_rejects_decoys():
    for kind in ('one-axis', 'remote', 'behind', 'body'):
        clear_scene()
        key, lock, floor_face = make_spatial_recovery_decoy(kind)
        key_hit = key.matrix_world @ key.data.polygons[0].center
        floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 0, key_hit, lock.name, floor_face, floor_hit,
            allow_rotation=True,
            source_normal=world_normal(key, 0),
            target_normal=world_normal(lock, floor_face),
        )
        if delta is not None:
            raise AssertionError(f"spatial recovery accepted the {kind} decoy")


def assert_spatial_recovery_diagnostics_are_specific():
    for kind, expected in (
        ('remote', 'no bounded planar wall candidates'),
        ('stacked', 'distinct compatible frames'),
    ):
        clear_scene()
        key, lock, floor_face = make_spatial_recovery_decoy(kind)
        key_hit = key.matrix_world @ key.data.polygons[0].center
        floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 0, key_hit, lock.name, floor_face, floor_hit,
            allow_rotation=True,
            source_normal=world_normal(key, 0),
            target_normal=world_normal(lock, floor_face),
            diagnostics=diagnostics,
        )
        if delta is not None or not any(expected in note for note in diagnostics):
            raise AssertionError(
                f"{kind} recovery refusal was not diagnosed specifically: {diagnostics}"
            )


def assert_spatial_recovery_merges_touching_fragments():
    clear_scene()
    key, lock, floor_face = make_spatial_recovery_decoy('fragmented')
    key_hit = key.matrix_world @ key.data.polygons[0].center
    floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, 0, key_hit, lock.name, floor_face, floor_hit,
        allow_rotation=True,
        source_normal=world_normal(key, 0),
        target_normal=world_normal(lock, floor_face),
    )
    if delta is None:
        raise AssertionError("touching coplanar wall fragments did not recover one frame")
    assert_matrix_finite(delta)


def assert_spatial_recovery_is_symmetric():
    clear_scene()
    key, lock, floor_face = disconnected_floored_lock()
    key.matrix_world = Matrix.Identity(4)
    lock.location = (2.0, -1.0, 0.0)
    lock.rotation_euler = Euler((0.35, -0.25, 0.5), 'XYZ')
    bpy.context.view_layer.update()
    floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
    key_hit = key.matrix_world @ key.data.polygons[0].center
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        lock.name, floor_face, floor_hit, key.name, 0, key_hit,
        allow_rotation=True,
        source_normal=world_normal(lock, floor_face),
        target_normal=world_normal(key, 0),
    )
    if delta is None:
        raise AssertionError("spatial recovery failed when the disconnected socket moves")
    assert_matrix_finite(delta)


def assert_spatial_recovery_does_not_replace_ambiguity():
    def pair(axis, opening=math.pi, low_normal=None, high_normal=None):
        axis = np.array(axis, dtype=np.float64)
        low_normal = np.array(low_normal or -axis, dtype=np.float64)
        high_normal = np.array(high_normal or axis, dtype=np.float64)
        return {
            'axis': axis,
            'opening_angle': opening,
            'anchor_side': None,
            'low_patch': {'normal': low_normal},
            'high_patch': {'normal': high_normal},
        }

    known = [pair((1.0, 0.0, 0.0)), pair((0.0, 1.0, 0.0))]
    ambiguous = [
        pair((1.0, 0.0, 0.0)),
        pair((1.0, 0.0, 0.0), opening=math.radians(120.0)),
    ]
    reasons = []
    eligibility = quicksnap_utils._spatial_recovery_eligibility(
        known, ambiguous, (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), reasons
    )
    if eligibility is not None:
        raise AssertionError("ambiguous local walls were reinterpreted as missing geometry")
    if not any("ambiguous" in reason for reason in reasons):
        raise AssertionError(f"ambiguous recovery ineligibility was not diagnosed: {reasons}")

    three_axes = known + [pair((2 ** -0.5, 2 ** -0.5, 0.0))]
    reasons = []
    eligibility = quicksnap_utils._spatial_recovery_eligibility(
        three_axes, [], (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), reasons
    )
    if eligibility is not None:
        raise AssertionError("a third known lateral axis was silently discarded")
    if not any("more than two" in reason for reason in reasons):
        raise AssertionError(f"third-axis recovery ineligibility was not diagnosed: {reasons}")


def assert_spatial_recovery_is_isolated():
    """The disconnected-frame fallback must stay off ordinary solver paths."""
    recovery_name = "_recover_spatial_connector_frame"
    missing = object()
    original_recovery = getattr(quicksnap_utils, recovery_name, missing)

    def unexpected_recovery(*args, **kwargs):
        raise AssertionError("spatial recovery ran outside its cold-path eligibility")

    try:
        setattr(quicksnap_utils, recovery_name, unexpected_recovery)

        clear_scene()
        key, lock, floor_face = disconnected_floored_lock()
        key_hit = key.matrix_world @ key.data.polygons[0].center
        floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
        quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 0, key_hit, lock.name, floor_face, floor_hit,
            allow_rotation=False,
            source_normal=world_normal(key, 0),
            target_normal=world_normal(lock, floor_face),
        )

        clear_scene()
        key, key_face, key_hit, lock, lock_face, lock_hit = make_rotated_key_lock()
        kwargs = dict(
            allow_rotation=True,
            source_normal=world_normal(key, key_face),
            target_normal=world_normal(lock, lock_face),
        )
        setattr(quicksnap_utils, recovery_name, original_recovery)
        baseline = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit, **kwargs,
        )
        setattr(quicksnap_utils, recovery_name, unexpected_recovery)
        guarded = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit, **kwargs,
        )
        if baseline is None or guarded is None or not np.allclose(
            np.array(baseline), np.array(guarded), atol=1e-8, rtol=0.0
        ):
            raise AssertionError("anchored wall rotation changed under recovery guard")

        clear_scene()
        key, lock, floor_face = disconnected_floored_lock()
        key_hit = key.matrix_world @ key.data.polygons[0].center
        floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
        source_raycast_normal = world_normal(key, 0)
        target_raycast_normal = world_normal(lock, floor_face)
        original_clicked_normal = quicksnap_utils._clicked_face_normal
        quicksnap_utils._clicked_face_normal = lambda *args: None
        try:
            quicksnap_utils.compute_lock_key_transform(
                bpy.context, SimpleNamespace(ignore_modifiers=True),
                key.name, 0, key_hit, lock.name, floor_face, floor_hit,
                allow_rotation=True,
                source_normal=source_raycast_normal,
                target_normal=target_raycast_normal,
            )
        finally:
            quicksnap_utils._clicked_face_normal = original_clicked_normal

        clear_scene()
        key, lock = make_floored_lock_scene((0.35, -0.25, 0.5))
        key_hit = key.matrix_world @ key.data.polygons[0].center
        floor_hit = lock.matrix_world @ lock.data.polygons[4].center
        quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 0, key_hit, lock.name, 4, floor_hit,
            allow_rotation=True,
            source_normal=world_normal(key, 0),
            target_normal=world_normal(lock, 4),
        )
    finally:
        if original_recovery is missing:
            delattr(quicksnap_utils, recovery_name)
        else:
            setattr(quicksnap_utils, recovery_name, original_recovery)


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
    """Extraction is paid per object, never per solver consumer.

    The original regression paid the full extraction three times per mate --
    once per click plus once for the solver -- scaling with mesh size. A region
    provider may legitimately rebuild along its bounded widen chain (the
    fixture is smaller than any initial region, so it walks the whole chain),
    but the count is set by that chain, not by how many callers consume the
    data, and its bulk reads are cache-validated rather than re-extracted.
    """
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    operator = make_lock_key_operator([key.name], ignore_modifiers=True)
    counts = {}
    module = quicksnap.quicksnap_utils
    original = module._lock_key_fit_data

    def counting(obj, *args, **kwargs):
        counts[obj.name] = counts.get(obj.name, 0) + 1
        return original(obj, *args, **kwargs)

    module._lock_key_fit_data = counting
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
        module._lock_key_fit_data = original
    if not result:
        raise AssertionError("mate failed with the extraction cache enabled")
    # The widen chain is 0.05 -> 0.1 -> 0.2 -> full (0.4 exceeds the 0.3
    # ceiling and never serves as a region): at most 4 builds, 5 with slack.
    for name in (key.name, lock.name):
        if not 1 <= counts.get(name, 0) <= 5:
            raise AssertionError(
                f"expected a bounded handful of builds per object, got {counts}"
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


def assert_rotation_follows_the_clicked_walls():
    """Spec (amended 2026-08-09, third): wall clicks pin the wall correspondence.

    The GUI always passes both click normals, which enables the mixed wall/floor
    mapping -- and that licence used to free the enumeration to ignore the
    anchors even when BOTH clicks named a wall. On a near-square connector (a
    sculpted kit peg is never exactly square) every 90-degree seating then
    survived to the placement-signature tie and the mate was refused as
    ambiguous, so rotation was unusable on square-ish kit connectors however
    the user clicked. Field case: Cthulhu_Stand_Book_1 peg, 13.5965 x 13.5958.
    """
    def world_normal(obj, face):
        matrix = obj.matrix_world.to_3x3().inverted().transposed()
        return (matrix @ obj.data.polygons[face].normal).normalized()

    # The drafted variant mirrors the field kit (opening ~166 degrees): its
    # end-for-end flip candidate survives to the matcher and must die at the
    # opposed-normals gate, not by the signature dedup that only straight
    # synthetic walls can ever satisfy. Depth 1.5 keeps the box fixture honest:
    # a kit peg's end face has nothing opposed and parallel, but a closed box's
    # tip/base pair is a third connector the near-square lock would otherwise
    # accept sideways.
    for label, taper in (("straight", 0.0), ("drafted", 7.0)):
        clear_scene()
        key, key_face, key_hit, lock, lock_face, lock_hit = make_rotated_key_lock(
            taper_degrees=taper, source_depth=1.5,
            source_half_height=0.498, target_half_height=0.598,
        )
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
            allow_rotation=True,
            source_normal=world_normal(key, key_face),
            target_normal=world_normal(lock, lock_face),
        )
        if delta is None:
            raise AssertionError(
                f"{label}: wall clicks on a near-square connector must pin the"
                " mapping and mate")
        key.matrix_world = delta @ key.matrix_world
        if key.matrix_world.to_quaternion().angle > 1e-5:
            raise AssertionError(f"{label}: clicked walls were not mated upright")
        center = key.matrix_world.translation
        if abs(center.x) > 1e-5 or abs(center.y) > 1e-5:
            raise AssertionError(f"{label}: key was not centred: {tuple(center)}")

    # An end-face click names no wall, so rotation cannot know which way to turn
    # the key. The refusal must teach the gesture rather than blame penetration
    # for candidate rotations that were never enumerated. The key is an open
    # shell like a kit peg on its part: the tip face has nothing opposed and
    # parallel, so the click anchors no pair at all.
    clear_scene()
    key = make_mesh(
        "TipClickKey",
        [(-0.5, -0.498, -1.0), (0.5, -0.498, -1.0),
         (0.5, 0.498, -1.0), (-0.5, 0.498, -1.0),
         (-0.5, -0.498, 0.0), (0.5, -0.498, 0.0),
         (0.5, 0.498, 0.0), (-0.5, 0.498, 0.0)],
        [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    lock = make_mesh(
        "TipClickLock",
        [(-0.6, -0.598, 0.0), (0.6, -0.598, 0.0),
         (0.6, 0.598, 0.0), (-0.6, 0.598, 0.0),
         (-0.6, -0.598, -1.2), (0.6, -0.598, -1.2),
         (0.6, 0.598, -1.2), (-0.6, 0.598, -1.2)],
        [(1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3)],
    )
    key.location = (2.0, -1.0, 0.0)
    key.rotation_euler = Euler((0.35, -0.25, 0.5), 'XYZ')
    bpy.context.view_layer.update()
    lock_face = 3
    lock_hit = lock.matrix_world @ Vector((-0.6, 0.1, -0.5))
    tip_hit = key.matrix_world @ Vector((0.0, 0.0, -1.0))
    diagnostics = []
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, 0, tip_hit, lock.name, lock_face, lock_hit,
        allow_rotation=True,
        source_normal=world_normal(key, 0),
        target_normal=world_normal(lock, lock_face),
        diagnostics=diagnostics,
    )
    if delta is not None:
        raise AssertionError("an end-face click must not guess an orientation")
    if not any("side wall of the key's connector" in note for note in diagnostics):
        raise AssertionError(
            f"end-face click refusal does not teach the gesture: {diagnostics}")


def assert_end_face_clicks_align_the_mate():
    """Spec (amended 2026-08-09, fourth): the clicked faces carry the intent.

    The natural kit gesture is the top of the peg and the floor of the socket
    -- both faces point at the other part, and neither names a wall. Rotation
    now reads them directly: only rotations that bring the two clicked faces to
    rest against each other are enumerated, and the remaining spin is settled
    by the smallest rotation among seatings equivalent within measurement
    tolerance (byte-exact equivalence never fires on sculpted geometry). A
    connector whose alternative seatings genuinely differ still fails closed,
    and wall clicks still resolve it by naming the mapping.
    """
    def world_normal(obj, face):
        matrix = obj.matrix_world.to_3x3().inverted().transposed()
        return (matrix @ obj.data.polygons[face].normal).normalized()

    def boxed_key(half_width, half_height, depth, taper=0.0):
        slope = math.tan(math.radians(taper))
        tip_x, tip_y = half_width - depth * slope, half_height - depth * slope
        return make_mesh(
            "FaceKey",
            [(-tip_x, -tip_y, -depth), (tip_x, -tip_y, -depth),
             (tip_x, tip_y, -depth), (-tip_x, tip_y, -depth),
             (-half_width, -half_height, 0.0), (half_width, -half_height, 0.0),
             (half_width, half_height, 0.0), (-half_width, half_height, 0.0)],
            [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)],
        )

    def floored_lock(half_width, half_height, depth, taper=0.0):
        slope = math.tan(math.radians(taper))
        tip_x, tip_y = half_width - depth * slope, half_height - depth * slope
        return make_mesh(
            "FaceLock",
            [(-half_width, -half_height, 0.0), (half_width, -half_height, 0.0),
             (half_width, half_height, 0.0), (-half_width, half_height, 0.0),
             (-tip_x, -tip_y, -depth), (tip_x, -tip_y, -depth),
             (tip_x, tip_y, -depth), (-tip_x, tip_y, -depth)],
            [(1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3),
             (4, 5, 6, 7)],
        )

    def solve(key, key_face, key_hit, lock, lock_face, lock_hit, diagnostics=None):
        return quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
            allow_rotation=True,
            source_normal=world_normal(key, key_face),
            target_normal=world_normal(lock, lock_face),
            diagnostics=diagnostics,
        )

    # Near-square peg, top-of-peg and floor-of-socket clicks: the spin is
    # ambiguous only at a precision the parts are not built to, so the
    # smallest rotation (the user's rough placement) chooses -- straight, and
    # drafted like the field kit whose flips must die at the matcher.
    for label, taper in (("straight", 0.0), ("drafted", 7.0)):
        clear_scene()
        key = boxed_key(0.5, 0.498, 1.5, taper)
        lock = floored_lock(0.6, 0.598, 1.2, taper)
        key.location = (2.0, -1.0, 0.0)
        key.rotation_euler = Euler((0.35, -0.25, 0.5), 'XYZ')
        bpy.context.view_layer.update()
        tip_hit = key.matrix_world @ Vector((0.0, 0.0, -1.5))
        floor_hit = lock.matrix_world @ Vector((0.05, 0.1, -1.2))
        delta = solve(key, 0, tip_hit, lock, 4, floor_hit)
        if delta is None:
            raise AssertionError(
                f"{label}: top-of-peg and floor-of-socket clicks must mate")
        key.matrix_world = delta @ key.matrix_world
        if key.matrix_world.to_quaternion().angle > 1e-5:
            raise AssertionError(f"{label}: the smallest spin was not chosen")
        center = key.matrix_world.translation
        if abs(center.x) > 1e-5 or abs(center.y) > 1e-5:
            raise AssertionError(f"{label}: key was not centred: {tuple(center)}")
        if abs(center.z - 0.3) > 1e-5:
            raise AssertionError(
                f"{label}: clicked faces do not rest together: z={center.z}")

    # A rectangular peg in a square socket fits two genuinely different ways.
    # End-face clicks cannot decide that and must fail closed... (depth 1.4 so
    # the tip/base pair cannot fit the 1.0 opening: a snug-fitting depth pair
    # would anchor the tip click and re-enter the pinned path sideways)
    clear_scene()
    key = boxed_key(0.45, 0.25, 1.4)
    lock = floored_lock(0.5, 0.5, 1.2)
    key.location = (2.0, -1.0, 0.0)
    key.rotation_euler = Euler((0.35, -0.25, 0.5), 'XYZ')
    bpy.context.view_layer.update()
    tip_hit = key.matrix_world @ Vector((0.0, 0.0, -1.4))
    floor_hit = lock.matrix_world @ Vector((0.0, 0.1, -1.2))
    diagnostics = []
    delta = solve(key, 0, tip_hit, lock, 4, floor_hit, diagnostics)
    if delta is not None:
        raise AssertionError(
            "a rectangular peg in a square socket must not guess its seating")
    if not any("several rotations fit differently" in note for note in diagnostics):
        raise AssertionError(
            f"ambiguous seating refusal is not named: {diagnostics}")
    if not any(
        "apart against a tolerance of" in note or "no counterpart" in note
        for note in diagnostics
    ):
        raise AssertionError(
            f"ambiguous seating refusal does not say how far apart: {diagnostics}")

    # ...and wall clicks resolve exactly that ambiguity by naming the mapping.
    key_hit = key.matrix_world @ Vector((-0.45, 0.0, -0.3))
    lock_hit = lock.matrix_world @ Vector((-0.5, 0.1, -0.5))
    delta = solve(key, 5, key_hit, lock, 3, lock_hit)
    if delta is None:
        raise AssertionError("wall clicks must resolve the square-socket tie")
    key.matrix_world = delta @ key.matrix_world
    if key.matrix_world.to_quaternion().angle > 1e-5:
        raise AssertionError("wall clicks seated the rectangle the wrong way")


def make_round_key_lock(peg_radius=2.0, hole_radius=2.08, segments=256, rings=24):
    """A dense round peg and a blind round hole: no flat side wall anywhere.

    The peg's tip sits at its origin facing -Z with the body above; the hole's
    floor is at (0, 0, -3) facing +Z inside a block whose top is at z = 0.
    Dense facets and rings make the sides read as curved the way a sculpt does,
    so the wall solve refuses exactly as it did on the field signpost.
    """
    import bmesh

    def cylinder(name, radius, depth, lift):
        mesh = bmesh.new()
        bmesh.ops.create_cone(
            mesh, cap_ends=True, segments=segments, radius1=radius,
            radius2=radius, depth=depth,
        )
        bmesh.ops.translate(mesh, verts=mesh.verts, vec=(0.0, 0.0, lift))
        bmesh.ops.subdivide_edges(
            mesh,
            edges=[
                edge for edge in mesh.edges
                if abs(edge.verts[0].co.z - edge.verts[1].co.z) > 1.0
            ],
            cuts=rings, use_grid_fill=False,
        )
        data = bpy.data.meshes.new(name + "Mesh")
        mesh.to_mesh(data)
        mesh.free()
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        return obj

    key = cylinder("RoundKey", peg_radius, 8.0, 4.0)
    lock = make_mesh(
        "RoundLock",
        [(-6, -6, -6), (6, -6, -6), (6, 6, -6), (-6, 6, -6),
         (-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    cutter = cylinder("RoundCutter", hole_radius, 4.0, -1.0)
    modifier = lock.modifiers.new("cut", 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.object = cutter
    bpy.context.view_layer.objects.active = lock
    bpy.ops.object.modifier_apply(modifier="cut")
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.context.view_layer.update()

    def end_face(obj, normal):
        normal = Vector(normal)
        best = None
        for polygon in obj.data.polygons:
            world_normal = (obj.matrix_world.to_3x3() @ polygon.normal).normalized()
            if world_normal.dot(normal) < 0.999:
                continue
            centre = obj.matrix_world @ polygon.center
            # The clicked end is the one nearest the connector's own axis end.
            score = abs(centre.z) if normal.z < 0 else abs(centre.z + 3.0)
            if best is None or score < best[0]:
                best = (score, polygon.index)
        return best[1]

    return key, end_face(key, (0, 0, -1)), lock, end_face(lock, (0, 0, 1))


def make_d_key_lock(clearance=0.06, segments=48, rings=24):
    """A D-shaped peg and its blind socket: one flat side, one faceted round side.

    Modelled on the field cloth-back peg (2.3.0): the flat side faces a fan of
    round-side facets, so the pairs across the clicked end face share an axis
    but disagree on their walls -- the spatial recovery reads the axes as
    ambiguous and the wall solve refuses, though nothing is refused as curved.
    The peg's tip is at its origin facing -Z; the socket's floor is at
    (0, 0, -3) facing +Z inside a block whose top is at z = 0.
    """
    import bmesh

    def prism(name, grow, bottom, top):
        radius = 2.0 + grow
        flat = 1.0 + grow
        outline = [
            (radius * math.cos(step * math.pi / segments),
             -radius * math.sin(step * math.pi / segments))
            for step in range(segments + 1)
        ] + [(-radius, flat), (radius, flat)]
        mesh = bmesh.new()
        low = [mesh.verts.new((x, y, bottom)) for x, y in outline]
        high = [mesh.verts.new((x, y, top)) for x, y in outline]
        count = len(outline)
        for index in range(count):
            following = (index + 1) % count
            mesh.faces.new((low[index], low[following], high[following], high[index]))
        mesh.faces.new(list(reversed(low)))
        mesh.faces.new(high)
        bmesh.ops.recalc_face_normals(mesh, faces=mesh.faces)
        # Rings down the sides, as a sculpt has: the overlap test samples face
        # centres, and one face spanning the whole side samples nothing.
        bmesh.ops.subdivide_edges(
            mesh,
            edges=[
                edge for edge in mesh.edges
                if abs(edge.verts[0].co.z - edge.verts[1].co.z) > 1e-6
            ],
            cuts=rings, use_grid_fill=False,
        )
        data = bpy.data.meshes.new(name + "Mesh")
        mesh.to_mesh(data)
        mesh.free()
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        return obj

    key = prism("DKey", 0.0, 0.0, 6.0)
    lock = make_mesh(
        "DLock",
        [(-6, -6, -6), (6, -6, -6), (6, 6, -6), (-6, 6, -6),
         (-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    cutter = prism("DCutter", clearance, -3.0, 1.0)
    modifier = lock.modifiers.new("cut", 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.object = cutter
    bpy.context.view_layer.objects.active = lock
    bpy.ops.object.modifier_apply(modifier="cut")
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.context.view_layer.update()

    def cap(obj, normal, height):
        for polygon in obj.data.polygons:
            if (
                polygon.normal.dot(Vector(normal)) > 0.999
                and abs(polygon.center.z - height) < 1e-4
            ):
                return polygon.index
        raise AssertionError(f"no cap facing {normal} at z={height} on {obj.name}")

    return key, cap(key, (0, 0, -1), 0.0), lock, cap(lock, (0, 0, 1), -3.0)


def assert_round_connectors_slide_without_rotating():
    """A round peg in a round hole is seated by sliding, never rotated.

    Field report (2.2.1, Base_Signpost into Base): tip + floor clicks on a
    round post refused "the key click is on a curved surface ... rounded
    connectors are not supported", then a recovery-path line nobody could act
    on. A round peg needs no spin from its walls -- the end faces' centres lie
    on the peg's and the hole's axes, and sliding one onto the other is the
    mate, the user's orientation kept as it stands.
    """
    settings = SimpleNamespace(ignore_modifiers=False, lock_and_key_centre_picks=True)

    def solve(key, key_face, lock, lock_face, allow_rotation):
        bpy.context.view_layer.update()
        tip = key.matrix_world @ key.data.polygons[key_face].center
        floor = lock.matrix_world @ lock.data.polygons[lock_face].center
        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, settings,
            key.name, key_face, tip, lock.name, lock_face, floor,
            allow_rotation=allow_rotation,
            source_normal=key.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0)),
            target_normal=Vector((0.0, 0.0, 1.0)),
            diagnostics=diagnostics,
        )
        return delta, diagnostics

    clear_scene()
    key, key_face, lock, lock_face = make_round_key_lock()
    # Parked off to the side and spun about its own axis: the spin must be
    # kept, because a round peg has none to correct.
    spin = Matrix.Rotation(math.radians(37.0), 4, 'Z')
    key.matrix_world = Matrix.Translation((3.0, -2.0, 5.0)) @ spin
    bpy.context.view_layer.update()
    walls_only = {}
    if quicksnap_utils._compute_wall_lock_key_transform(
        bpy.context, settings, key.name, key_face,
        key.matrix_world @ key.data.polygons[key_face].center,
        lock.name, lock_face, Vector((0.0, 0.0, -3.0)), allow_rotation=True,
        source_normal=Vector((0.0, 0.0, -1.0)), target_normal=Vector((0.0, 0.0, 1.0)),
        round_evidence=walls_only,
    ) is not None or 'key' not in walls_only.get('curved', ()):
        raise AssertionError(
            "the fixture must reach the round fallback the way the field part"
            f" did: the wall solve refusing a curved key click ({walls_only.get('curved')!r})"
        )
    for allow_rotation in (False, True):
        delta, diagnostics = solve(key, key_face, lock, lock_face, allow_rotation)
        if delta is None:
            raise AssertionError(
                f"round peg refused (rotation {allow_rotation}): {diagnostics[-1:]!r}"
            )
        if max(
            abs(value) for row in (delta.to_3x3() - Matrix.Identity(3)) for value in row
        ) > 1e-9:
            raise AssertionError(f"round peg was rotated: {delta!r}")
        if (delta.translation - Vector((-3.0, 2.0, -8.0))).length > 1e-3:
            raise AssertionError(
                f"round peg not slid onto the floor's centre: {delta.translation!r}"
            )

    # Tilted past the parallel bar: sliding alone cannot seat it, so with
    # rotation off say so -- and with rotation on, lay the end face flat on
    # the floor first (field report 2.3.0: a saber lying 97 degrees off its
    # hand's socket, refused although rotation was on).
    tilt = Matrix.Rotation(math.radians(10.0), 4, 'X')
    key.matrix_world = Matrix.Translation((3.0, -2.0, 5.0)) @ tilt @ spin
    delta, diagnostics = solve(key, key_face, lock, lock_face, False)
    if delta is not None or "degrees from lying flat" not in diagnostics[-1]:
        raise AssertionError(f"tilted round peg must refuse by its tilt: {diagnostics[-1:]!r}")
    delta, diagnostics = solve(key, key_face, lock, lock_face, True)
    if delta is None:
        raise AssertionError(f"tilted round peg refused with rotation on: {diagnostics[-1:]!r}")
    seated = delta @ key.matrix_world
    tip = seated @ key.data.polygons[key_face].center
    facing = seated.to_3x3() @ Vector((0.0, 0.0, -1.0))
    if facing.angle(Vector((0.0, 0.0, -1.0))) > 1e-6 or (tip - Vector((0.0, 0.0, -3.0))).length > 1e-3:
        raise AssertionError(
            f"tilted round peg not laid flat on the floor's centre: tip {tip!r}, facing {facing!r}"
        )
    # The smallest turn that squares the end face keeps the user's spin.
    kept = seated.to_3x3() @ Vector((1.0, 0.0, 0.0))
    wanted = spin.to_3x3() @ Vector((1.0, 0.0, 0.0))
    if kept.angle(wanted) > 1e-6:
        raise AssertionError(f"squaring the round peg changed its spin: {kept!r} vs {wanted!r}")

    # A peg too fat for its hole buries its body in the wall and is refused,
    # with the depth against the allowance.
    clear_scene()
    key, key_face, lock, lock_face = make_round_key_lock(peg_radius=2.3)
    key.matrix_world = Matrix.Translation((3.0, -2.0, 5.0))
    delta, diagnostics = solve(key, key_face, lock, lock_face, True)
    if delta is not None or "buries the key" not in diagnostics[-1]:
        raise AssertionError(f"oversized round peg must refuse: {diagnostics[-1:]!r}")


def assert_rounded_end_faces_seat_square_or_refuse():
    """End-face clicks on a D-shaped peg: squared when rotation is on, never crooked.

    Field report (2.3.0, a cloth panel's peg into the legs): end face plus
    socket floor on a peg with one flat and one faceted round side refused
    "spatial recovery ineligible: the local wall axes are ambiguous". The
    sides' wall pairs share an axis but disagree on their walls, which is
    what marks the click as the end of a rounded connector, so the end-face
    seating takes it. Fixture checks on the same shape found the wall solve's
    translation path seating a tilted key as it stood -- 25 degrees crooked
    through a 0.06 clearance socket, released in 2.2.1 -- because the side
    walls it matched pin nothing about a tilt about their own axis.
    """
    settings = SimpleNamespace(ignore_modifiers=False, lock_and_key_centre_picks=True)

    def solve(tilt_degrees, spin_degrees, allow_rotation):
        clear_scene()
        key, key_face, lock, lock_face = make_d_key_lock()
        key.matrix_world = (
            Matrix.Translation((3.0, -2.0, 5.0))
            @ Matrix.Rotation(math.radians(tilt_degrees), 4, 'X')
            @ Matrix.Rotation(math.radians(spin_degrees), 4, 'Z')
        )
        bpy.context.view_layer.update()
        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, settings,
            key.name, key_face, key.matrix_world @ key.data.polygons[key_face].center,
            lock.name, lock_face, Vector((0.0, 0.0, -3.0)),
            allow_rotation=allow_rotation,
            source_normal=key.matrix_world.to_3x3() @ Vector((0.0, 0.0, -1.0)),
            target_normal=Vector((0.0, 0.0, 1.0)),
            diagnostics=diagnostics,
        )
        return key, delta, diagnostics

    # Tilted with the right spin and rotation on: squared onto the floor, the
    # flat side against the socket's flat side, the outline inside the hole.
    key, delta, diagnostics = solve(25.0, 0.0, True)
    if delta is None:
        raise AssertionError(f"tilted D peg refused with rotation on: {diagnostics[-1:]!r}")
    seated = delta @ key.matrix_world
    facing = seated.to_3x3() @ Vector((0.0, 0.0, -1.0))
    flat = seated.to_3x3() @ Vector((0.0, 1.0, 0.0))
    if facing.angle(Vector((0.0, 0.0, -1.0))) > 1e-6 or flat.angle(Vector((0.0, 1.0, 0.0))) > 1e-6:
        raise AssertionError(f"D peg not squared into its socket: facing {facing!r}, flat side {flat!r}")
    corners = [seated @ vertex.co for vertex in key.data.vertices]
    if (
        min(point.z for point in corners) < -3.0 - 1e-4
        or min(point.y for point in corners) < -2.06 - 1e-3
        or max(point.y for point in corners) > 1.06 + 1e-3
        or max(abs(point.x) for point in corners) > 2.06 + 1e-3
    ):
        raise AssertionError("seated D peg pokes out of its socket")

    # Turned the wrong way about its axis: buried, refused, depth named.
    _key, delta, diagnostics = solve(25.0, 180.0, True)
    if delta is not None or "buries the key" not in diagnostics[-1]:
        raise AssertionError(f"D peg spun 180 degrees must refuse: {diagnostics[-1:]!r}")

    # Rotation off: no slide may leave the key as crooked as it stands.
    for spin_degrees in (0.0, 8.0, 90.0):
        _key, delta, diagnostics = solve(15.0, spin_degrees, False)
        if delta is not None:
            raise AssertionError(
                f"D peg tilted 15 degrees (spin {spin_degrees}) was seated crooked"
                " with rotation off"
            )
        if "degrees from lying flat" not in diagnostics[-1]:
            raise AssertionError(
                f"crooked D peg refused without naming its tilt: {diagnostics[-1:]!r}"
            )


def assert_far_from_origin_spins_stay_equivalent():
    """Seating equivalence is measured at the walls, not from the world origin.

    Field report (2.2.1, Cthulhu kit parked ~330 units out): tip + floor clicks
    on a square drafted peg refused "several rotations fit differently" for
    every click, while the identical parts mated at the origin. A sculpt's spins
    differ in wall normal by hundredths of a degree, and comparing plane
    offsets from the origin multiplied that by the parts' distance from it.
    One wall here is drafted 0.2 degrees off its siblings -- sculpt-sized
    noise -- and the pair must mate the same way at the origin and far out.
    """
    def world_normal(obj, face):
        matrix = obj.matrix_world.to_3x3().inverted().transposed()
        return (matrix @ obj.data.polygons[face].normal).normalized()

    def drafted_key(half, depth, drafts):
        slopes = [math.tan(math.radians(draft)) for draft in drafts]
        x0, x1 = -half + depth * slopes[0], half - depth * slopes[1]
        y0, y1 = -half + depth * slopes[2], half - depth * slopes[3]
        return make_mesh(
            "FarKey",
            [(x0, y0, -depth), (x1, y0, -depth), (x1, y1, -depth),
             (x0, y1, -depth), (-half, -half, 0.0), (half, -half, 0.0),
             (half, half, 0.0), (-half, half, 0.0)],
            [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)],
        )

    def drafted_lock(half, depth, draft):
        tip = half - depth * math.tan(math.radians(draft))
        return make_mesh(
            "FarLock",
            [(-half, -half, 0.0), (half, -half, 0.0), (half, half, 0.0),
             (-half, half, 0.0), (-tip, -tip, -depth), (tip, -tip, -depth),
             (tip, tip, -depth), (-tip, tip, -depth)],
            [(1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3),
             (4, 5, 6, 7)],
        )

    def solve(key, lock, tip_xy, diagnostics):
        return quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            key.name, 0, key.matrix_world @ Vector((*tip_xy, -8.0)),
            lock.name, 4, lock.matrix_world @ Vector((0.05, 0.1, -7.0)),
            allow_rotation=True,
            source_normal=world_normal(key, 0),
            target_normal=world_normal(lock, 4),
            diagnostics=diagnostics,
        )

    seated = []
    for far in ((0.0, 0.0, 0.0), (-600.0, 400.0, 150.0)):
        clear_scene()
        key = drafted_key(1.8, 8.0, (5.92, 5.92, 5.92, 5.72))
        lock = drafted_lock(2.2, 7.0, 7.2)
        lock.location = far
        key.location = (far[0] + 20.0, far[1] - 10.0, far[2])
        key.rotation_euler = Euler((0.35, -0.25, 0.5), 'XYZ')
        bpy.context.view_layer.update()
        diagnostics = []
        delta = solve(key, lock, (0.03, 0.02), diagnostics)
        if delta is None:
            raise AssertionError(
                f"square peg {far} from the origin refused: {diagnostics}")
        key.matrix_world = delta @ key.matrix_world
        seated.append((
            key.matrix_world.to_quaternion(),
            key.matrix_world.translation - Vector(far),
        ))
    (near_spin, near_offset), (far_spin, far_offset) = seated
    if near_spin.rotation_difference(far_spin).angle > 1e-4:
        raise AssertionError("distance from the origin changed the chosen spin")
    if (near_offset - far_offset).length > 1e-3:
        raise AssertionError("distance from the origin changed the seating")

    # A tip click far off the peg's axis trips the anchor relocation cap on
    # every spin. The refusal must name that gate with its numbers, not only
    # count "uncentred" -- the field log that counted could not say why.
    key.matrix_world = delta.inverted() @ key.matrix_world
    bpy.context.view_layer.update()
    diagnostics = []
    if solve(key, lock, (0.9, 0.7), diagnostics) is not None:
        raise AssertionError("a tip click past the relocation cap mated")
    if not any(
        "nearest uncentred seating: centring moves the anchors" in note
        for note in diagnostics
    ):
        raise AssertionError(
            f"uncentred refusal does not name the cap: {diagnostics}")


def assert_surroundings_pick_the_spin():
    """Spec (amended 2026-08-10): the surroundings veto impossible spins.

    A square-ish peg fits its socket four ways and the walls cannot say which
    the sculptor meant; smallest-rotation follows the user's rough placement,
    which is wrong whenever the part was left nearest a wrong quarter-turn.
    The sculptor keys the intent into the parts around the connector: here the
    key carries a fin beside its peg and the lock leaves one bay clear with
    raised blocks at the other three positions, so every wrong quarter-turn
    drives the fin into a block. With the key parked 170 degrees around, the
    nearest seating is the wrong one -- the survey must override it.
    """
    def world_normal(obj, face):
        matrix = obj.matrix_world.to_3x3().inverted().transposed()
        return (matrix @ obj.data.polygons[face].normal).normalized()

    clear_scene()
    # Near-square peg (1.0 x 0.996), depth 1.4, plus a single-quad fin flag at
    # +X. A boxed fin would form its own wall pairs and collide with the
    # matcher's one-axis rule; a lone quad samples without pairing.
    key = make_mesh(
        "SpinKey",
        [(-0.5, -0.498, -1.4), (0.5, -0.498, -1.4),
         (0.5, 0.498, -1.4), (-0.5, 0.498, -1.4),
         (-0.5, -0.498, 0.0), (0.5, -0.498, 0.0),
         (0.5, 0.498, 0.0), (-0.5, 0.498, 0.0),
         (1.15, -0.2, 0.0), (1.15, 0.2, 0.0),
         (1.15, 0.2, 0.3), (1.15, -0.2, 0.3)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7), (8, 9, 10, 11)],
    )

    def box(centre_x, centre_y):
        base = len(lock_vertices)
        lock_vertices.extend([
            (centre_x - 0.25, centre_y - 0.25, 0.0),
            (centre_x + 0.25, centre_y - 0.25, 0.0),
            (centre_x + 0.25, centre_y + 0.25, 0.0),
            (centre_x - 0.25, centre_y + 0.25, 0.0),
            (centre_x - 0.25, centre_y - 0.25, 0.3),
            (centre_x + 0.25, centre_y - 0.25, 0.3),
            (centre_x + 0.25, centre_y + 0.25, 0.3),
            (centre_x - 0.25, centre_y + 0.25, 0.3),
        ])
        lock_faces.extend([
            (base + 0, base + 1, base + 2, base + 3),
            (base + 7, base + 6, base + 5, base + 4),
            (base + 0, base + 4, base + 5, base + 1),
            (base + 1, base + 5, base + 6, base + 2),
            (base + 2, base + 6, base + 7, base + 3),
            (base + 3, base + 7, base + 4, base + 0),
        ])

    lock_vertices = [
        (-0.55, -0.548, 0.0), (0.55, -0.548, 0.0),
        (0.55, 0.548, 0.0), (-0.55, 0.548, 0.0),
        (-0.55, -0.548, -1.4), (0.55, -0.548, -1.4),
        (0.55, 0.548, -1.4), (-0.55, 0.548, -1.4),
        (-0.55, -0.548, -1.4), (0.55, -0.548, -1.4),
        (0.55, 0.548, -1.4), (-0.55, 0.548, -1.4),
    ]
    lock_faces = [
        (1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3),
        (8, 9, 10, 11),
    ]
    for blocked in ((-1.15, 0.0), (0.0, 1.15), (0.0, -1.15)):
        box(*blocked)
    lock = make_mesh("SpinLock", lock_vertices, lock_faces)

    key.location = (2.0, -1.0, 0.0)
    key.rotation_euler = Euler((0.0, 0.0, math.radians(170.0)), 'XYZ')
    bpy.context.view_layer.update()
    tip_hit = key.matrix_world @ Vector((0.0, 0.0, -1.4))
    floor_hit = lock.matrix_world @ Vector((0.0, 0.05, -1.4))
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, 0, tip_hit, lock.name, 4, floor_hit,
        allow_rotation=True,
        source_normal=world_normal(key, 0),
        target_normal=world_normal(lock, 4),
    )
    if delta is None:
        raise AssertionError("the keyed spin fixture must mate")
    key.matrix_world = delta @ key.matrix_world
    angle = key.matrix_world.to_quaternion().angle
    if angle > 1e-5:
        raise AssertionError(
            "the fin was seated onto a block: the mate is"
            f" {math.degrees(angle):.1f} degrees off the keyed orientation")


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
    operator.can_initialize_lock_key = quicksnap.QuickVertexSnapOperator.__dict__[
        "can_initialize_lock_key"
    ].__func__
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


def assert_extra_pairs_yield_to_the_walls():
    """Centring solves on the walls; lesser pairs may sit un-centred but never clash.

    A sculpted connector matches more pairs than a translation can balance --
    corner bevels, taper segments, near-parallel duplicates -- and demanding
    every match centre within flatness tolerance refused honest kit parts
    (field logs 2026-08-09, Faye and Guts kits: 4 matched pairs, refused).
    The consistent-subset solve must mate on the wall pairs when the extras
    are merely un-centred, and still refuse when an excluded pair would
    interpenetrate -- that backstop is what keeps the relaxation fail-closed.
    """
    counter = iter(range(1000))

    def patch(normal, point, area):
        normal = np.array(normal, dtype=np.float64)
        return {
            'normal': normal / np.linalg.norm(normal),
            'point': np.array(point, dtype=np.float64),
            'area': float(area),
            'extent': 2.0,
            'tolerance': 0.01,
            'fit_tolerance': 0.002,
            'id': next(counter),
            'polygons': set(),
        }

    diagonal = np.array([1.0, 1.0, 0.0]) / math.sqrt(2.0)

    def peg_patches():
        return [
            patch((1, 0, 0), (0.5, 0, 0), 10.0),
            patch((-1, 0, 0), (-0.5, 0, 0), 10.0),
            patch((0, 1, 0), (0, 0.5, 0), 10.0),
            patch((0, -1, 0), (0, -0.5, 0), 10.0),
            patch(diagonal, 0.75 * diagonal, 2.0),
            patch(-diagonal, -0.75 * diagonal, 2.0),
        ]

    def socket_patches(centre, diagonal_half, diagonal_shift):
        centre = np.array(centre, dtype=np.float64)
        return [
            patch((1, 0, 0), centre + (-0.56, 0, 0), 12.0),
            patch((-1, 0, 0), centre + (0.56, 0, 0), 12.0),
            patch((0, 1, 0), centre + (0, -0.56, 0), 12.0),
            patch((0, -1, 0), centre + (0, 0.56, 0), 12.0),
            patch(diagonal,
                  centre + (diagonal_shift - diagonal_half) * diagonal, 2.4),
            patch(-diagonal,
                  centre + (diagonal_shift + diagonal_half) * diagonal, 2.4),
        ]

    source_anchor = np.zeros(3)
    target_anchor = np.array([3.0, 0.0, 0.0])

    def matches_for(diagonal_half, diagonal_shift):
        source_pairs = quicksnap_utils._connector_side_pairs(
            peg_patches(), source_anchor
        )
        target_pairs = quicksnap_utils._connector_side_pairs(
            socket_patches(target_anchor, diagonal_half, diagonal_shift),
            target_anchor,
        )
        return quicksnap_utils._match_connector_pairs(source_pairs, target_pairs)

    # A loose diagonal pair whose centre disagrees with the walls by 0.3: the
    # full set must fail (this is the field case), the subset must mate.
    matches = matches_for(0.95, 0.15)
    if len(matches) < 3:
        raise AssertionError(f"fixture matched only {len(matches)} pairs")
    full = quicksnap_utils._solve_lock_key_translation(
        matches, source_anchor, target_anchor
    )
    if full is not None and quicksnap_utils._validate_lock_key_transform(matches, full):
        raise AssertionError(
            "the fixture is consistent; it does not exercise the subset solve"
        )
    translation, used = quicksnap_utils._centreable_matches(
        matches, source_anchor, target_anchor
    )
    if translation is None:
        raise AssertionError("an un-centred loose pair blocked an honest mate")
    if float(np.linalg.norm(translation - target_anchor)) > 1e-6:
        raise AssertionError(
            f"the walls did not decide the seat: translation {translation}"
        )
    if len(used) >= len(matches):
        raise AssertionError("no pair was excluded; the subset solve never ran")

    # A snug diagonal pair the walls' seat would drive into the material must
    # still refuse: exclusion may waive centring, never interpenetration.
    matches = matches_for(0.76, 0.30)
    if len(matches) < 3:
        raise AssertionError(f"snug fixture matched only {len(matches)} pairs")
    translation, _ = quicksnap_utils._centreable_matches(
        matches, source_anchor, target_anchor
    )
    if translation is not None:
        raise AssertionError(
            "an excluded pair was left interpenetrating: fail-closed backstop lost"
        )


def assert_failures_report_a_specific_reason():
    """One generic message for eight causes leaves nothing to try differently."""
    cases = []

    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    cases.append(("missing object", "MissingKey", key_face, key_hit,
                  lock.name, lock_face, lock_hit, "not a mesh object"))
    cases.append(("stale face", key.name, 10_000, key_hit,
                  lock.name, lock_face, lock_hit, "no longer exists"))
    # Both clicks on one object froze the UI in the field: the solver refused
    # only after two full extractions and a wall search, then misdescribed the
    # mistake as a taper mismatch between identical walls, and the refusal
    # report surveyed the same dense part twice.
    cases.append(("same object", key.name, key_face, key_hit,
                  key.name, key_face, key_hit, "cannot mate with itself"))

    reasons = {}
    for label, source_name, source_face, source_hit, \
            target_name, target_face, target_hit, expected in cases:
        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, SimpleNamespace(ignore_modifiers=True),
            source_name, source_face, source_hit,
            target_name, target_face, target_hit,
            allow_rotation=False, diagnostics=diagnostics,
        )
        if delta is not None:
            raise AssertionError(f"{label}: expected a refusal")
        if not diagnostics:
            raise AssertionError(f"{label}: refused without recording a reason")
        if expected not in diagnostics[-1]:
            raise AssertionError(
                f"{label}: reason {diagnostics[-1]!r} does not mention {expected!r}"
            )
        reasons[label] = diagnostics[-1]

    # A misaligned key is the common cause of "no correspondence", and translation
    # alone can never fix it, so the message has to point at the rotate option.
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_rotated_key_lock(
        euler=(0.0, 0.0, math.radians(20.0))
    )
    diagnostics = []
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
        allow_rotation=False, diagnostics=diagnostics,
    )
    if delta is not None:
        raise AssertionError("a 20 degree misaligned key should not translate-mate")
    if "Rotate key to match lock" not in diagnostics[-1]:
        raise AssertionError(
            f"misalignment reason does not point at the rotate option: "
            f"{diagnostics[-1]!r}"
        )
    # ...and the same geometry must actually mate once rotation is allowed,
    # otherwise the advice is wrong.
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
        allow_rotation=True,
    )
    if delta is None:
        raise AssertionError(
            "the message advises enabling rotation, but rotation does not mate this"
        )

    # An incompatible pair must not reuse a different stage's wording.
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_key_lock(
        target_half_width=0.4, target_half_height=0.3
    )
    diagnostics = []
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
        allow_rotation=False, diagnostics=diagnostics,
    )
    if delta is not None or not diagnostics:
        raise AssertionError("an oversized key should refuse with a reason")
    if "does not fit inside the lock" not in diagnostics[-1]:
        raise AssertionError(
            f"oversized-key reason is not specific: {diagnostics[-1]!r}"
        )
    if "Rotate key to match lock" in diagnostics[-1]:
        raise AssertionError(
            "an aligned-but-unfitting pair was wrongly blamed on rotation: "
            f"{diagnostics[-1]!r}"
        )
    if diagnostics[-1] in reasons.values():
        raise AssertionError("distinct causes reported the same reason")

    # A healthy mate must record nothing.
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    diagnostics = []
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
        allow_rotation=False, diagnostics=diagnostics,
    )
    if delta is None or diagnostics:
        raise AssertionError(f"successful mate recorded a reason: {diagnostics}")


def assert_modal_lifecycle_helpers():
    """Initialization and teardown must be transactional at their external edges."""
    operator_type = quicksnap.QuickVertexSnapOperator

    can_initialize = operator_type.__dict__["can_initialize_lock_key"].__func__
    hidden = []
    visible = SimpleNamespace(name="visible", hide_get=lambda: False)
    ignored = SimpleNamespace(
        name="ignored", hide_get=lambda: False,
        hide_set=lambda value: hidden.append(value),
    )
    context = SimpleNamespace(
        space_data=SimpleNamespace(local_view=object()),
        view_layer=SimpleNamespace(objects=[visible, ignored]),
        visible_objects=[visible],
    )
    if can_initialize(False, False) or can_initialize(True, True):
        raise AssertionError("invalid Lock and key state passed preflight")
    if hidden:
        raise AssertionError("preflight mutated Local View visibility")

    capture = operator_type.__dict__["capture_view_state"].__func__
    view_matrix = Matrix.Identity(4)
    perspective = Matrix.Translation((1.0, 2.0, 3.0))
    state = capture(SimpleNamespace(
        view_matrix=view_matrix,
        perspective_matrix=perspective,
        view_distance=12.5,
        view_camera_zoom=3.25,
    ))
    if state[1:] != (12.5, 3.25, perspective):
        raise AssertionError(f"view sentinels were not captured together: {state!r}")

    changed = operator_type.__dict__["geometry_settings_changed"].__func__
    settings = SimpleNamespace(
        ignore_modifiers=False, snap_source_type="VERT", snap_target_type="FACE",
    )
    if changed(settings, False, "VERT", "FACE"):
        raise AssertionError("unchanged geometry settings requested a rebuild")
    settings.ignore_modifiers = True
    if not changed(settings, False, "VERT", "FACE"):
        raise AssertionError("direct Ignore Modifiers change skipped SnapData rebuild")

    calls = []
    operator = SimpleNamespace(
        _restore_scene=lambda context, revert: (_ for _ in ()).throw(RuntimeError("restore failed")),
        cleanup_modal_resources=lambda context: calls.append("cleanup"),
    )
    terminate = operator_type.__dict__["terminate"]
    try:
        terminate(operator, SimpleNamespace(), revert=False)
    except RuntimeError as exc:
        if str(exc) != "restore failed":
            raise
    else:
        raise AssertionError("scene restoration failure was swallowed")
    if calls != ["cleanup"]:
        raise AssertionError(f"cleanup was not guaranteed after restoration failure: {calls}")

    cleanup = operator_type.__dict__["cleanup_modal_resources"]
    original_remove_handlers = quicksnap.quicksnap_render.remove_draw_handlers
    try:
        timer = object()
        remove_calls = []
        cleanup_operator = SimpleNamespace(snapdata_target=None, _timer=timer)
        cleanup_context = SimpleNamespace(window_manager=SimpleNamespace(
            event_timer_remove=lambda value: remove_calls.append(value)
        ))
        quicksnap.quicksnap_render.remove_draw_handlers = lambda: (_ for _ in ()).throw(
            RuntimeError("handler removal failed")
        )
        try:
            cleanup(cleanup_operator, cleanup_context)
        except RuntimeError as exc:
            if str(exc) != "handler removal failed":
                raise
        else:
            raise AssertionError("handler removal failure was swallowed")
        if remove_calls != [timer] or cleanup_operator._timer is not None:
            raise AssertionError("handler failure prevented timer cleanup")

        class FailingSnapData:
            @property
            def is_enabled(self):
                return True

            @is_enabled.setter
            def is_enabled(self, value):
                raise RuntimeError("snapdata disable failed")

        timer = object()
        remove_calls = []
        cleanup_operator = SimpleNamespace(snapdata_target=FailingSnapData(), _timer=timer)
        quicksnap.quicksnap_render.remove_draw_handlers = lambda: None
        try:
            cleanup(cleanup_operator, cleanup_context)
        except RuntimeError as exc:
            if str(exc) != "snapdata disable failed":
                raise
        else:
            raise AssertionError("snapdata disable failure was swallowed")
        if remove_calls != [timer] or cleanup_operator._timer is not None:
            raise AssertionError("snapdata failure prevented timer cleanup")

        timer = object()
        remove_calls = []
        attempts = {"count": 0}

        def remove_timer(value):
            remove_calls.append(value)
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("timer removal failed")

        cleanup_operator = SimpleNamespace(snapdata_target=None, _timer=timer)
        cleanup_context = SimpleNamespace(window_manager=SimpleNamespace(
            event_timer_remove=remove_timer
        ))
        try:
            cleanup(cleanup_operator, cleanup_context)
        except RuntimeError as exc:
            if str(exc) != "timer removal failed":
                raise
        else:
            raise AssertionError("timer removal failure was swallowed")
        if cleanup_operator._timer is not timer:
            raise AssertionError("failed timer removal lost the retry handle")
        cleanup(cleanup_operator, cleanup_context)
        cleanup(cleanup_operator, cleanup_context)
        if remove_calls != [timer, timer] or cleanup_operator._timer is not None:
            raise AssertionError(f"timer cleanup was not retry-safe: {remove_calls!r}")
    finally:
        quicksnap.quicksnap_render.remove_draw_handlers = original_remove_handlers


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
    touched = set()
    settings = SimpleNamespace(
        bl_rna=SimpleNamespace(properties=properties),
        lock_and_key_mode=True,
        lock_and_key_rotate=False,
        is_property_set=lambda identifier: identifier in touched,
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
            # Set by hand since the backup was written: the backup is only saved on
            # unregister, so after a crash it is stale, and restoring it wholesale
            # quietly undid the user's own settings on the next start.
            settings.lock_and_key_rotate = True
            touched.add("lock_and_key_rotate")
            quicksnap.load_settings()
        finally:
            quicksnap.quicksnap_utils.get_addon_settings = original_get_settings
            quicksnap.settings_file_path = original_path
    if settings.lock_and_key_mode is not True:
        raise AssertionError("an untouched preference was not restored from backup")
    if settings.lock_and_key_rotate is not True:
        raise AssertionError("the backup overwrote a preference the user had set")


def assert_either_half_may_move():
    """Click order must not decide which half is allowed to be the socket.

    Plenty of kits can only be assembled by moving the socket onto a fixed peg. That
    is the same seated result as moving the peg, so both orders must mate and the two
    deltas must be inverses of each other. Deciding the roles from the wall normals
    instead of the click order is what makes that true.
    """
    settings = SimpleNamespace(ignore_modifiers=True)

    def both_orders(builder, allow_rotation):
        clear_scene()
        key, key_face, key_hit, lock, lock_face, lock_hit = builder()
        results = {}
        for label, args in (
            ('peg first', (key.name, key_face, key_hit,
                           lock.name, lock_face, lock_hit)),
            ('socket first', (lock.name, lock_face, lock_hit,
                              key.name, key_face, key_hit)),
        ):
            diagnostics = []
            results[label] = quicksnap_utils.compute_lock_key_transform(
                bpy.context, settings, *args,
                allow_rotation=allow_rotation, diagnostics=diagnostics,
            )
            results[label + ' reason'] = (
                diagnostics[-1] if diagnostics else 'no reason given'
            )
        return results

    for allow_rotation in (False, True):
        mode = 'rotation on' if allow_rotation else 'rotation off'
        results = both_orders(
            lambda: make_key_lock(target_half_height=0.45), allow_rotation
        )
        forward = results['peg first']
        reverse = results['socket first']
        if forward is None:
            raise AssertionError(
                f"the peg-first order stopped mating ({mode}): "
                f"{results['peg first reason']}"
            )
        if reverse is None:
            raise AssertionError(
                f"moving the socket onto the peg was refused ({mode}): "
                f"{results['socket first reason']}"
            )
        assert_matrix_finite(reverse)
        # Same seated assembly from either end: one delta moves the peg, the other
        # moves the socket, so composing them has to land back on identity.
        residual = reverse @ forward
        for row in range(4):
            for column in range(4):
                expected = 1.0 if row == column else 0.0
                if abs(residual[row][column] - expected) > 1e-6:
                    raise AssertionError(
                        f"the two click orders seat the parts differently ({mode}): "
                        f"{[list(line) for line in residual]}"
                    )

    # The safety half has to survive: a peg genuinely wider than its socket is still
    # refused whichever end the user picks first.
    results = both_orders(
        lambda: make_key_lock(target_half_width=0.4, target_half_height=0.3),
        False,
    )
    for label in ('peg first', 'socket first'):
        if results[label] is not None:
            raise AssertionError(f"an oversized peg mated anyway ({label})")


def assert_picks_centre_on_their_wall():
    """A pick lands on the middle of the wall, so sloppy clicks still agree.

    That repeatability is the whole point of centring. It must also never become a
    restriction: with the preference off the exact click still decides, and the exact
    click is retried whenever the wall centres fail to mate.
    """
    key_normal = Vector((-1.0, 0.0, 0.0))
    lock_normal = Vector((1.0, 0.0, 0.0))

    def mate(source_offset, target_offset, centre_picks=True):
        clear_scene()
        key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
        operator = make_lock_key_operator([key.name])
        operator.settings.lock_and_key_centre_picks = centre_picks
        operator.record_lock_key_source(
            LockKeyStub.lock_key_hit(
                key.name, key_face, key_hit + source_offset, key_normal
            ),
            bpy.context,
        )
        mated = operator.finish_lock_key(
            bpy.context,
            LockKeyStub.lock_key_hit(
                lock.name, lock_face, lock_hit + target_offset, lock_normal
            ),
        )
        return mated, key.matrix_world.copy(), operator.lock_key_source_hit

    # The key's clicked wall is one quad spanning z -1..0 and y -0.4..0.4 at x=-0.5,
    # and the key sits at (2, -1, 0), so its centre is world (1.5, -1, -0.5).
    mated, _, source = mate(Vector((0.0, 0.2, -0.4)), Vector((0.0, -0.3, 0.3)))
    if not mated:
        raise AssertionError("an off-centre click stopped mating")
    # Blender stores mesh coordinates as float32, so compare at that precision.
    for axis, expected in enumerate((1.5, -1.0, -0.5)):
        if abs(source['location'][axis] - expected) > 1e-6:
            raise AssertionError(
                f"the pick did not centre on its wall: {source['location'][:]}"
            )
    if abs(source['raw_location'][1] - -0.8) > 1e-6:
        raise AssertionError(
            f"the exact click was not kept: {source['raw_location'][:]}"
        )

    # Two clicks on the same two walls, far apart, must seat the parts identically.
    _, sloppy, _ = mate(Vector((0.0, 0.3, -0.5)), Vector((0.0, -0.4, 0.4)))
    _, tidy, _ = mate(Vector((0.0, -0.3, 0.2)), Vector((0.0, 0.4, -0.6)))
    for row in range(4):
        for column in range(4):
            if abs(sloppy[row][column] - tidy[row][column]) > 1e-9:
                raise AssertionError(
                    "centred picks still depend on where the user clicked"
                )

    # With the preference off, click-controlled insertion depth must come back --
    # otherwise the toggle is a lie. Vary only depth here: clicking far apart across
    # a *constrained* axis pushes the lateral correction past the relocation cap and
    # refuses the mate outright, which is the fiddliness centring exists to remove.
    mated_a, loose_a, source_a = mate(
        Vector((0.0, 0.0, -0.5)), Vector((0.0, 0.0, 0.4)), centre_picks=False
    )
    mated_b, loose_b, _ = mate(
        Vector((0.0, 0.0, 0.2)), Vector((0.0, 0.0, -0.6)), centre_picks=False
    )
    if not (mated_a and mated_b):
        raise AssertionError("an exact-click mate stopped working with centring off")
    if abs(source_a['location'][2] - source_a['raw_location'][2]) > 1e-12:
        raise AssertionError("the pick was centred while the preference was off")
    if all(
        abs(loose_a[row][column] - loose_b[row][column]) <= 1e-9
        for row in range(4) for column in range(4)
    ):
        raise AssertionError(
            "turning centring off changed nothing about where the parts land"
        )


def make_filleted_pair(
        segments, bevel=0.06, half=0.5, depth=2.0, clearance=0.06,
        with_body=False):
    """A rectangular peg and socket with filleted edges, the way a kit is modelled.

    Each fillet ring inserts another patch hop between a wall and its opposite, which
    is exactly what puts the far wall out of reach of a fixed-radius search.
    """
    def block(name, x_half, y_half, z_half, location):
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=location)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = (x_half, y_half, z_half)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        if bevel > 0.0:
            modifier = obj.modifiers.new("bevel", 'BEVEL')
            modifier.width = bevel
            modifier.segments = segments
            bpy.ops.object.modifier_apply(modifier="bevel")
        return obj

    key = block("Key", half, half, depth * 0.5, (6.0, 0.0, 0.0))
    if with_body:
        # A peg welded to a body plate, the way a kit part actually arrives.
        plate = block(
            "Plate", half * 3, half * 3, depth * 0.125,
            (6.0, 0.0, -depth * 0.575),
        )
        union = key.modifiers.new("union", 'BOOLEAN')
        union.operation = 'UNION'
        union.object = plate
        bpy.context.view_layer.objects.active = key
        bpy.ops.object.modifier_apply(modifier="union")
        bpy.data.objects.remove(plate, do_unlink=True)
    lock = block(
        "Lock", (half + clearance) * 2.2, (half + clearance) * 2.2, depth * 0.6,
        (0.0, 0.0, 0.0),
    )
    cutter = block(
        "Cutter", half + clearance, half + clearance, depth * 0.7,
        (0.0, 0.0, depth * 0.3),
    )
    modifier = lock.modifiers.new("cut", 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.object = cutter
    bpy.context.view_layer.objects.active = lock
    bpy.ops.object.modifier_apply(modifier="cut")
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.context.view_layer.update()

    def wall(obj, axis, inward):
        axis = np.array(axis, dtype=np.float64)
        matrix = np.array(obj.matrix_world, dtype=np.float64)
        best, best_area = None, -1.0
        for polygon in obj.data.polygons:
            normal = matrix[:3, :3] @ np.array(polygon.normal)
            normal /= max(float(np.linalg.norm(normal)), 1e-12)
            if float(normal @ axis) < 0.99:
                continue
            centre = matrix[:3, :3] @ np.array(polygon.center) + matrix[:3, 3]
            # A socket's inner wall faces the cavity; its outer wall faces away.
            offset = float((centre - matrix[:3, 3]) @ axis)
            if (offset > 0.0) if inward else (offset < 0.0):
                continue
            if polygon.area > best_area:
                best, best_area = polygon.index, polygon.area
        return best

    key_face = wall(key, (-1.0, 0.0, 0.0), inward=False)
    lock_face = wall(lock, (1.0, 0.0, 0.0), inward=True)
    if key_face is None or lock_face is None:
        raise AssertionError("the filleted fixture has no clickable connector wall")
    return (
        key, key_face, key.matrix_world @ key.data.polygons[key_face].center,
        lock, lock_face, lock.matrix_world @ lock.data.polygons[lock_face].center,
    )


def assert_filleted_connectors_mate():
    """A well-modelled peg must not be harder to mate than a crude one.

    A plain box peg reaches its far wall in two patch hops. Every chamfer or fillet
    ring inserts another, so a fixed two-hop neighbourhood never sees the opposite
    wall of a nicely modelled connector and the click looks like it landed on
    nothing. The search now widens when it finds no opposed pair at all.

    The dense counts are the sculpted regime: once adjacent fillet faces differ
    by under five degrees, an unbounded pairwise crawl walks the whole fillet,
    fails the global flatness gate, and the fillet becomes an impassable moat --
    or, denser still, the crawl crosses the wall boundary and the walls
    themselves drown in the failed component (12 and 64 segments respectively,
    on this fixture).
    """
    settings = SimpleNamespace(ignore_modifiers=True)
    for segments, with_body in (
            (1, False), (3, False), (5, False), (3, True),
            (12, False), (64, False)):
        clear_scene()
        key, key_face, key_hit, lock, lock_face, lock_hit = make_filleted_pair(
            segments, with_body=with_body
        )

        # The fillet strips must stay stepping stones to the far wall, never become
        # walls themselves. A rounded edge makes dozens of slivers, each forming
        # plausible opposed pairs on its own diagonal axis; they outnumber the real
        # walls and crowd them out, because the matcher discards a candidate whose
        # two best targets tie and near-identical slivers tie constantly.
        key_data = quicksnap_utils._mesh_fit_data(key)
        seeds = quicksnap_utils._seed_polygons(key_data, 'FACES', key_face)
        clicked = quicksnap_utils._grow_planar_patch(key_data, key_face)
        pairs, _ = quicksnap_utils._connector_pairs(
            key_data, seeds, np.array(key_hit, dtype=np.float64)
        )
        if not pairs:
            raise AssertionError(
                f"a {segments}-segment filleted key exposed no wall pair"
            )
        if len(pairs) > 8:
            raise AssertionError(
                f"a {segments}-segment filleted key produced {len(pairs)} wall"
                " pairs; fillet slivers are being treated as connector walls"
            )
        for pair in pairs:
            for side in ('low_patch', 'high_patch'):
                if pair[side]['area'] < 0.1 * clicked['area']:
                    raise AssertionError(
                        f"a wall pair is built on a sliver: {pair[side]['area']:.4f}"
                        f" against a clicked wall of {clicked['area']:.4f}"
                    )

        for allow_rotation in (False, True):
            diagnostics = []
            delta = quicksnap_utils.compute_lock_key_transform(
                bpy.context, settings,
                key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
                allow_rotation=allow_rotation,
                source_normal=Vector((-1.0, 0.0, 0.0)),
                target_normal=Vector((1.0, 0.0, 0.0)),
                diagnostics=diagnostics,
            )
            if delta is None:
                raise AssertionError(
                    f"a {segments}-segment filleted connector was refused"
                    f" (rotation {'on' if allow_rotation else 'off'}): "
                    f"{diagnostics[-1] if diagnostics else 'no reason given'}"
                )
            assert_matrix_finite(delta)

    # Prove the widening is what carries it: pinned back to the historic two-hop
    # radius, this same pair is refused for want of any opposed wall pair at all.
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_filleted_pair(3)
    original = quicksnap_utils._CONNECTOR_MAX_HOPS
    try:
        quicksnap_utils._CONNECTOR_MAX_HOPS = 2
        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, settings,
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
            allow_rotation=False, diagnostics=diagnostics,
        )
    finally:
        quicksnap_utils._CONNECTOR_MAX_HOPS = original
    if delta is not None:
        raise AssertionError(
            "the two-hop radius mates filleted connectors, so this guards nothing"
        )
    if "no opposed wall pair" not in diagnostics[-1]:
        raise AssertionError(
            f"the two-hop radius failed for a different reason: {diagnostics[-1]!r}"
        )


def make_tab_and_slot(thickness, width, height=12.0, clearance=1.12):
    """A broad thin tab and the channel it slides into.

    The shape that exposes the difference between a flatness allowance and a fit
    tolerance: 0.5% of the tab's width dwarfs the tab's own thickness.
    """
    # A closed box: bottom ring first, so face 5 is its outward-facing -X wall.
    tx, ty = thickness * 0.5, width * 0.5
    tab = make_mesh(
        "Key",
        [(-tx, -ty, -height), (tx, -ty, -height),
         (tx, ty, -height), (-tx, ty, -height),
         (-tx, -ty, 0.0), (tx, -ty, 0.0), (tx, ty, 0.0), (-tx, ty, 0.0)],
        [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    tab.location = (width * 1.5, 0.0, 0.0)
    # An open channel: top ring first, so face 3 is its inward-facing -X wall. The
    # ring order and the winding travel together -- swap one and the walls face out.
    sx, sy, sz = thickness * clearance * 0.5, width * 0.51, height * 1.2
    slot = make_mesh(
        "Lock",
        [(-sx, -sy, 0.0), (sx, -sy, 0.0), (sx, sy, 0.0), (-sx, sy, 0.0),
         (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz)],
        [(1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3)],
    )
    bpy.context.view_layer.update()
    return (
        tab, 5, tab.matrix_world @ Vector((-thickness * 0.5, 0.0, -height * 0.35)),
        slot, 3,
        slot.matrix_world @ Vector(
            (-thickness * clearance * 0.5, 0.0, -height * 0.4)
        ),
    )


def assert_thin_tabs_keep_their_thin_axis():
    """A broad thin tab must still be centred across its thickness.

    Whether a wall separation is real is a question about precision, not about how
    big the patch is. Judging it with the flatness allowance -- 0.5% of the patch
    extent -- discards the thin axis of any tab broader than roughly 150:1, which is
    the one axis such a connector actually needs centred. The mate then still
    "succeeds" on the remaining axes, silently leaving the tab uncentred.
    """
    settings = SimpleNamespace(ignore_modifiers=True)
    for thickness, width in ((2.0, 10.0), (0.4, 60.0), (0.2, 120.0)):
        clear_scene()
        tab, tab_face, tab_hit, slot, slot_face, slot_hit = make_tab_and_slot(
            thickness, width
        )
        tab_data = quicksnap_utils._mesh_fit_data(tab)
        pairs, _ = quicksnap_utils._connector_pairs(
            tab_data,
            quicksnap_utils._seed_polygons(tab_data, 'FACES', tab_face),
            np.array(tab_hit, dtype=np.float64),
        )
        if not any(abs(float(pair['axis'][0])) > 0.99 for pair in pairs):
            raise AssertionError(
                f"a {width / thickness:.0f}:1 tab lost its thin-axis wall pair;"
                " the flatness allowance is being used to judge a fit"
            )

        before = tab.matrix_world.translation.x
        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, settings,
            tab.name, tab_face, tab_hit, slot.name, slot_face, slot_hit,
            allow_rotation=False, diagnostics=diagnostics,
        )
        if delta is None:
            raise AssertionError(
                f"a {width / thickness:.0f}:1 tab was refused: "
                f"{diagnostics[-1] if diagnostics else 'no reason given'}"
            )
        # Centred across the thickness means landing on the slot's mid-plane, which
        # sits at x = 0. Anything else means the thin pair was found but not used.
        landed = before + delta.translation.x
        if abs(landed) > 0.02 * thickness:
            raise AssertionError(
                f"a {width / thickness:.0f}:1 tab seated at x={landed:.5f} rather"
                f" than centred on the slot"
            )


def assert_patch_budget_does_not_cut_the_search_short():
    """A dense neighbourhood must not stop the search reaching the far wall.

    The patch budget guards the unfloored fallback, whose pairing is quadratic in
    every sliver it re-admits. The floored pass only ever pairs substantial walls --
    a handful even on a part with thousands of patches -- so budgeting it by total
    patch count stopped the walk long before it could cross to the far wall, on
    exactly the dense parts that need the reach most.

    Driving the budget to 1 stands in for that part: the walk must still get there.
    """
    settings = SimpleNamespace(ignore_modifiers=True)
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_filleted_pair(3)
    original = quicksnap_utils._CONNECTOR_MAX_PATCHES
    try:
        quicksnap_utils._CONNECTOR_MAX_PATCHES = 1
        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, settings,
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
            allow_rotation=False, diagnostics=diagnostics,
        )
    finally:
        quicksnap_utils._CONNECTOR_MAX_PATCHES = original
    if delta is None:
        raise AssertionError(
            "the patch budget stopped the floored search reaching the far wall: "
            f"{diagnostics[-1] if diagnostics else 'no reason given'}"
        )

    # And a refusal must describe the radius it actually searched, not the radius it
    # was allowed -- reporting geometry that was never considered reads as evidence
    # and is not.
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
    diagnostics = []
    quicksnap_utils.compute_lock_key_transform(
        bpy.context, settings,
        key.name, key_face, key_hit, lock.name, lock_face,
        # A click out in space belongs to no connector, so this refuses and reports.
        Vector((500.0, 500.0, 500.0)),
        allow_rotation=False, diagnostics=diagnostics,
    )
    if diagnostics and "searched" in diagnostics[-1]:
        if "patch hops" not in diagnostics[-1]:
            raise AssertionError(
                f"the refusal does not name its search radius: {diagnostics[-1]!r}"
            )


def make_fragmented_pair(cuts, wobble, half=0.5, depth=2.0, clearance=0.06):
    """A peg whose flat walls arrive cut into fragments, as modelled parts do.

    Subdivision plus sub-degree normal noise is what a sculpted, decimated or
    scanned part looks like: geometrically flat walls that the patch growth step
    refuses to merge, because its offset allowance scales with edge length and a
    finely cut wall has tiny edges.
    """
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(5.0, 0.0, 0.0))
    key = bpy.context.active_object
    key.name = "Key"
    key.scale = (half, half, depth * 0.5)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    modifier = key.modifiers.new("sub", 'SUBSURF')
    modifier.subdivision_type = 'SIMPLE'
    modifier.levels = cuts
    bpy.ops.object.modifier_apply(modifier="sub")
    if wobble:
        rng = np.random.default_rng(11)
        jitter = rng.normal(0.0, wobble, (len(key.data.vertices), 3))
        for vertex, offset in zip(key.data.vertices, jitter):
            vertex.co += Vector(offset.tolist())
        key.data.update()

    lock_half = half + clearance
    lock = make_mesh(
        "Lock",
        [(-lock_half, -lock_half, 0.0), (lock_half, -lock_half, 0.0),
         (lock_half, lock_half, 0.0), (-lock_half, lock_half, 0.0),
         (-lock_half, -lock_half, -depth * 0.6),
         (lock_half, -lock_half, -depth * 0.6),
         (lock_half, lock_half, -depth * 0.6),
         (-lock_half, lock_half, -depth * 0.6)],
        [(1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3)],
    )
    bpy.context.view_layer.update()

    # Both clicks at the same depth, so the coarse translation is purely lateral.
    key_hit = key.matrix_world @ Vector((-half, 0.0, -depth * 0.25))
    key_face = min(
        (p.index for p in key.data.polygons if p.normal.x < -0.9),
        key=lambda index: (
            key.matrix_world @ key.data.polygons[index].center - key_hit
        ).length,
    )
    lock_hit = lock.matrix_world @ Vector((-lock_half, 0.0, -depth * 0.25))
    return key, key_face, key_hit, lock, 3, lock_hit


def assert_fragmented_walls_are_rebuilt():
    """A wall cut into fragments must still behave as one wall.

    Without merging, the click lands on a fragment, every neighbour faces the same
    way, and the opposite wall sits hundreds of fragments away -- further than any
    affordable search. The reported signature was exactly that: a tiny clicked
    patch, every neighbour a similar size, and nothing facing back after 8 hops.
    """
    settings = SimpleNamespace(ignore_modifiers=True)
    clear_scene()
    clean_key, clean_face, clean_hit, _, _, _ = make_fragmented_pair(3, 0.0)
    clean_data = quicksnap_utils._mesh_fit_data(clean_key)
    reach = quicksnap_utils._CONNECTOR_MAX_HOPS
    _, clean_wall = quicksnap_utils._connector_walls(
        clean_data, quicksnap_utils._seed_polygons(clean_data, 'FACES', clean_face),
        reach,
    )
    whole_wall = float(clean_wall['area'])

    for cuts, wobble in ((3, 0.0015), (3, 0.004), (4, 0.002)):
        clear_scene()
        key, key_face, key_hit, lock, lock_face, lock_hit = make_fragmented_pair(
            cuts, wobble
        )
        data = quicksnap_utils._mesh_fit_data(key)
        seeds = quicksnap_utils._seed_polygons(data, 'FACES', key_face)
        # At the radius the search can actually reach; a fixed small radius has not
        # yet crossed the wall, so the merged wall is legitimately partial there.
        raw = quicksnap_utils._candidate_patches(data, seeds, reach)
        merged, clicked = quicksnap_utils._connector_walls(data, seeds, reach)
        if clicked is None:
            raise AssertionError("the clicked fragment did not land in any wall")
        if len(raw) < 3 * len(merged):
            raise AssertionError(
                f"the fixture is not fragmented enough to test merging:"
                f" {len(raw)} patches, {len(merged)} walls"
            )
        # The clicked wall must come back whole, not as the sliver that was hit.
        if float(clicked['area']) < 0.8 * whole_wall:
            raise AssertionError(
                f"the clicked wall stayed fragmented: {clicked['area']:.4f} of"
                f" {whole_wall:.4f}"
            )

        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, settings,
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
            allow_rotation=False, diagnostics=diagnostics,
        )
        if delta is None:
            raise AssertionError(
                f"a fragmented peg ({cuts} cuts, {wobble} wobble) was refused: "
                f"{diagnostics[-1] if diagnostics else 'no reason given'}"
            )
        assert_matrix_finite(delta)


def assert_curvature_is_judged_at_the_click():
    """Only the clicked wall decides whether a click is on a curve.

    Pairing runs over every wall in the neighbourhood, so the total pair count
    tracks how detailed the surrounding part is, not how round the connector is: a
    flat socket in a busy part clears any such threshold without being remotely
    curved. A flat-sided wall faces one other wall, or a few in a stepped slot; a
    rounded one faces half the facets of its own curve.
    """
    def pairs_at(obj, face, hit):
        data = quicksnap_utils._mesh_fit_data(obj)
        seeds = quicksnap_utils._seed_polygons(data, 'FACES', face)
        return quicksnap_utils._connector_pairs(
            data, seeds, np.array(hit, dtype=np.float64), 'lock'
        )

    # A flat socket cut into a finely divided block: many walls in reach, but the
    # clicked wall still faces just its opposite.
    clear_scene()
    _, _, _, lock, lock_face, lock_hit = make_fragmented_pair(3, 0.002)
    pairs, reason = pairs_at(lock, lock_face, lock_hit)
    if reason and "curved surface" in reason:
        raise AssertionError(f"a flat socket was called a curve: {reason}")
    if not pairs:
        raise AssertionError(f"a flat socket found no wall pair: {reason}")

    # A genuinely round connector must still fail closed. The dense counts are
    # the regime the seed drift bound changed: under five degrees per facet the
    # curve used to vanish into one failed growth, whereas bounded growth turns
    # it into strip patches -- which must be caught as a curve, never paired.
    for vertices in (32, 96, 192):
        clear_scene()
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=vertices, radius=0.5, depth=2.0
        )
        cylinder = bpy.context.active_object
        side = min(
            (p.index for p in cylinder.data.polygons if abs(p.normal.z) < 0.1),
            key=lambda index: cylinder.data.polygons[index].center.x,
        )
        _, reason = pairs_at(
            cylinder, side,
            cylinder.matrix_world @ cylinder.data.polygons[side].center,
        )
        if not reason or "curved surface" not in reason:
            raise AssertionError(
                f"a round connector ({vertices} verts) was not refused: {reason!r}"
            )


def assert_alignment_refusal_reports_how_far_off():
    """"None facing each other" must say by how much.

    Over a thousand tried combinations, the count alone cannot distinguish a part
    that is a few degrees out from one that is structurally unrelated, and those
    want opposite advice.
    """
    settings = SimpleNamespace(ignore_modifiers=True)
    for degrees in (8.0, 20.0):
        clear_scene()
        key, key_face, _, lock, lock_face, lock_hit = make_key_lock()
        key.rotation_euler = Euler((0.0, 0.0, math.radians(degrees)))
        bpy.context.view_layer.update()
        key_hit = key.matrix_world @ Vector((-0.5, 0.0, -0.3))
        diagnostics = []
        delta = quicksnap_utils.compute_lock_key_transform(
            bpy.context, settings,
            key.name, key_face, key_hit, lock.name, lock_face, lock_hit,
            allow_rotation=False, diagnostics=diagnostics,
        )
        if delta is not None:
            raise AssertionError(f"a {degrees} degree tilt should not translate-mate")
        message = diagnostics[-1]
        if "nearest combination is" not in message:
            raise AssertionError(f"no near-miss reported: {message!r}")
        reported = float(message.split("nearest combination is ")[1].split()[0])
        if abs(reported - degrees) > 0.5:
            raise AssertionError(
                f"a {degrees} degree tilt was reported as {reported}: {message!r}"
            )


def assert_search_widens_for_a_second_axis():
    """The search must not stop at whichever single wall pair it saw first.

    Centring wants two independent lateral directions and rotation flatly requires
    them, so returning the first pair found leaves rotation refusing "needs two
    independent wall pairs" on parts that plainly have them a hop further out.
    """
    clear_scene()
    key, key_face, key_hit, _, _, _ = make_fragmented_pair(3, 0.002)
    data = quicksnap_utils._mesh_fit_data(key)
    seeds = quicksnap_utils._seed_polygons(data, 'FACES', key_face)
    pairs, reason = quicksnap_utils._connector_pairs(
        data, seeds, np.array(key_hit, dtype=np.float64), 'key'
    )
    axes = quicksnap_utils._independent_axis_count(pairs)
    if axes < 2:
        raise AssertionError(
            f"the search stopped on {axes} independent axis/axes"
            f" ({len(pairs)} pairs): {reason}"
        )


def make_cut_face_with_a_peg():
    """A part cut flat across, with its peg standing on the cut.

    A neck or a shoulder: the click lands on the cut, which has nothing facing it,
    while the peg beside it is plainly a connector -- and centring puts the anchor
    between the peg's walls. The stray downward facet at the rim is the modelling
    junk every real mesh carries; it is what makes the click look, to a test that
    only measures the clicked wall, like a parting plane.
    """
    obj = make_mesh(
        "CutFace",
        [
            (-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (-2.0, 2.0, 0.0),
            (-0.6, -0.6, 0.0), (0.6, -0.6, 0.0), (0.6, 0.6, 0.0), (-0.6, 0.6, 0.0),
            (-0.6, -0.6, 3.0), (0.6, -0.6, 3.0), (0.6, 0.6, 3.0), (-0.6, 0.6, 3.0),
            (0.6, -0.75, 3.05), (-0.6, -0.75, 3.05),
        ],
        [
            (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),  # the cut face
            (4, 5, 9, 8), (5, 6, 10, 9), (6, 7, 11, 10), (7, 4, 8, 11),  # the peg
            (8, 9, 12, 13),  # a stray lip that faces the cut, and nothing else
        ],
    )
    bpy.context.view_layer.update()
    return obj, 0


def assert_a_connector_in_reach_is_not_called_a_flat_face():
    """A cut face with its peg on it is not a parting plane.

    Judging the click alone made that verdict unfalsifiable: a click on any flat
    cut has nothing facing it, so whenever the parts were not already aligned the
    refusal blamed the click instead of naming the rotation the user needed.
    """
    clear_scene()
    obj, face = make_cut_face_with_a_peg()
    data = quicksnap_utils._mesh_fit_data(obj)
    seeds = quicksnap_utils._seed_polygons(data, 'FACES', face)
    anchor = np.array(
        quicksnap_utils.clicked_patch_centre(data, face), dtype=np.float64
    )
    pairs, reason = quicksnap_utils._connector_pairs(data, seeds, anchor, 'key')
    if not pairs:
        raise AssertionError(f"the fixture's peg was not found at all: {reason}")
    # Teeth: without the pairs, the clicked wall alone still reads as a flat face,
    # so this fixture does reproduce the reported verdict.
    if quicksnap_utils._clicked_wall_is_not_a_connector(
        data, seeds, anchor, 'key', ()
    ) is None:
        raise AssertionError("the fixture no longer reproduces the flat-face verdict")
    verdict = quicksnap_utils._clicked_wall_is_not_a_connector(
        data, seeds, anchor, 'key', pairs
    )
    if verdict is not None:
        raise AssertionError(f"a peg in reach was called a flat face: {verdict}")


def make_chamfered_socket():
    """A socket whose mouth trim spans two directions before its far wall is reached.

    The shape from the reported log: the two real walls are four patch hops apart
    (across the lips and the rim between them), while the chamfer at the mouth and
    the lead-ins at the ends are one hop from the click and already opposed on two
    axes of their own. Their walls open around 120 degrees where the real ones open
    180, so a key measured against them can never match.
    """
    obj = make_mesh(
        "ChamferedSocket",
        [
            (-5.0, -1.0, -4.0), (5.0, -1.0, -4.0), (5.0, -1.0, 0.0), (-5.0, -1.0, 0.0),
            (-5.0, 1.0, -4.0), (5.0, 1.0, -4.0), (5.0, 1.0, 0.0), (-5.0, 1.0, 0.0),
            (-5.0, -1.15, 0.1), (5.0, -1.15, 0.1),
            (-5.0, 1.15, 0.1), (5.0, 1.15, 0.1),
            (-5.0, -1.12, -4.09), (5.0, -1.12, -4.09),
            (-5.2, -0.6, -4.0), (-5.2, -0.6, 0.0),
            (5.2, -0.6, -4.0), (5.2, -0.6, 0.0),
        ],
        [
            (3, 2, 1, 0),      # the clicked wall
            (4, 5, 6, 7),      # its opposite, four hops away
            (8, 9, 2, 3),      # chamfer at the mouth
            (7, 6, 11, 10),
            (0, 1, 13, 12),    # lip at the far end
            (8, 9, 11, 10),    # rim across the mouth
            (14, 15, 3, 0),    # lead-in at each end of the clicked wall
            (1, 2, 17, 16),
        ],
    )
    bpy.context.view_layer.update()
    return obj, 0, Vector((0.0, -1.0, -2.0))


def assert_trim_does_not_outvote_the_real_walls():
    """The sliver fallback may add a direction; it may not replace the walls.

    The trimmed pass pairs only substantial walls, so what it finds is the connector
    the modeller drew. The fallback re-admits every sliver, and a chamfer ring is
    opposed on two axes at once a hop from the click -- enough to look complete and
    return before the search ever reaches the far wall.
    """
    clear_scene()
    socket, face, hit = make_chamfered_socket()
    data = quicksnap_utils._mesh_fit_data(socket)
    seeds = quicksnap_utils._seed_polygons(data, 'FACES', face)
    pairs, reason = quicksnap_utils._connector_pairs(
        data, seeds, np.array(hit, dtype=np.float64), 'lock'
    )
    real = [
        pair for pair in pairs
        if min(float(pair['low_patch']['area']), float(pair['high_patch']['area']))
        >= 10.0
    ]
    if not real:
        openings = [
            round(math.degrees(pair['opening_angle']), 1) for pair in pairs
        ]
        raise AssertionError(
            "the mouth trim replaced the connector walls:"
            f" {len(pairs)} pair(s) opening {openings}, none between real walls"
            f" ({reason})"
        )


def make_chamfered_slot_pair():
    """A drafted bar key and a slot whose mouth carries a generous chamfer.

    The shape from the reported log: the key's walls open 170.6 degrees where
    the lock offered only its mouth chamfer's pair at about 100. A click on the
    chamfer strip puts the anchor laterally outside the slot walls, so the real
    wall pair cannot span it and only the trim survives -- and the slot has no
    second lateral axis to rescue a partial match.
    """
    slope = math.tan(math.radians(4.7))
    key = make_mesh(
        "Key",
        [
            (-(0.55 - slope), -0.9, -1.0), (0.55 - slope, -0.9, -1.0),
            (0.55 - slope, 0.9, -1.0), (-(0.55 - slope), 0.9, -1.0),
            (-0.55, -0.9, 0.0), (0.55, -0.9, 0.0),
            (0.55, 0.9, 0.0), (-0.55, 0.9, 0.0),
        ],
        [
            (0, 3, 2, 1), (4, 5, 6, 7),
            (0, 1, 5, 4), (1, 2, 6, 5),
            (2, 3, 7, 6), (3, 0, 4, 7),   # face 5: the drafted low-x wall
        ],
    )
    key.location = (2.5, -1.0, 0.0)
    chamfer = 0.15 * math.tan(math.radians(40.0))
    lip = 0.6 + chamfer
    lock = make_mesh(
        "Lock",
        [
            (-1.1, -1.0, 0.0), (-lip, -1.0, 0.0), (-lip, 1.0, 0.0), (-1.1, 1.0, 0.0),
            (1.1, -1.0, 0.0), (lip, -1.0, 0.0), (lip, 1.0, 0.0), (1.1, 1.0, 0.0),
            (-0.6, -1.0, -0.15), (-0.6, 1.0, -0.15),
            (0.6, -1.0, -0.15), (0.6, 1.0, -0.15),
            (-0.6, -1.0, -1.2), (-0.6, 1.0, -1.2),
            (0.6, -1.0, -1.2), (0.6, 1.0, -1.2),
        ],
        [
            (0, 1, 2, 3),          # top strip beside the low-x lip
            (5, 4, 7, 6),          # top strip beside the high-x lip
            (1, 8, 9, 2),          # face 2: low-x mouth chamfer (clicked)
            (10, 5, 6, 11),        # high-x mouth chamfer
            (8, 12, 13, 9),        # face 4: low-x slot wall
            (14, 10, 11, 15),      # high-x slot wall
            (12, 14, 15, 13),      # slot floor
        ],
    )
    bpy.context.view_layer.update()
    key_hit = key.matrix_world @ Vector((-(0.55 - slope * 0.4), 0.0, -0.4))
    chamfer_hit = lock.matrix_world @ Vector((-(0.6 + chamfer * 0.5), 0.05, -0.075))
    wall_centre = lock.matrix_world @ Vector((-0.6, 0.0, -0.675))
    return key, 5, key_hit, lock, 2, chamfer_hit, 4, wall_centre


def assert_chamfer_click_names_its_wall():
    """A click on the mouth chamfer mates as if the wall itself had been named.

    From a real kit report: the parts fit and were rotated correctly, yet the
    mate was refused for a taper mismatch between a straight wall and the
    chamfer's own 100-degree pair. The trim knows which corner it softened, so
    the click is promoted to the wall -- and with centring off the pick is the
    user's exact point again, so only the honest refusal remains.
    """
    clear_scene()
    key, key_face, key_hit, lock, chamfer_face, chamfer_hit, wall_face, \
        wall_centre = make_chamfered_slot_pair()
    settings = SimpleNamespace(ignore_modifiers=True)

    # Teeth: with promotion off (centring off), the chamfer click reproduces the
    # reported refusal, naming the two openings.
    diagnostics = []
    refused = quicksnap_utils.compute_lock_key_transform(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True, lock_and_key_centre_picks=False),
        "Key", key_face, key_hit, "Lock", chamfer_face, chamfer_hit,
        diagnostics=diagnostics,
    )
    if refused is not None:
        raise AssertionError(
            "the fixture no longer reproduces the chamfer-click refusal"
        )
    if not any("are not parallel" in line for line in diagnostics):
        raise AssertionError(
            f"expected the taper-mismatch refusal, got: {diagnostics}"
        )

    control = quicksnap_utils.compute_lock_key_transform(
        bpy.context, settings,
        "Key", key_face, key_hit, "Lock", wall_face, wall_centre,
    )
    if control is None:
        raise AssertionError("the wall-centre control click failed to mate")
    promoted = quicksnap_utils.compute_lock_key_transform(
        bpy.context, settings,
        "Key", key_face, key_hit, "Lock", chamfer_face, chamfer_hit,
    )
    if promoted is None:
        raise AssertionError("the chamfer click was not promoted to its wall")
    difference = max(
        abs(promoted[row][column] - control[row][column])
        for row in range(4) for column in range(4)
    )
    if difference > 1e-5:
        raise AssertionError(
            "promotion seated the key differently from naming the wall:"
            f" {tuple(promoted.to_translation())} vs"
            f" {tuple(control.to_translation())}"
        )


def make_regioned_pair():
    """A long socket under a dense bumpy plate, and the peg that fits it.

    The socket's clicked wall spans further than the initial region radius, so
    the first extraction must raise and widen exactly once -- and the plate
    (disconnected, fragmented by its bumps the way an organic surround is)
    makes the mesh large enough that the settled region stays partial.
    """
    import math as _math
    cells = 120
    half = 50.0
    step = 2.0 * half / cells
    verts = [
        (
            -half + column * step,
            -half + row * step,
            0.3 * _math.sin((-half + column * step) * 0.6)
            * _math.sin((-half + row * step) * 0.6),
        )
        for row in range(cells + 1)
        for column in range(cells + 1)
    ]
    faces = [
        (
            row * (cells + 1) + column,
            row * (cells + 1) + column + 1,
            (row + 1) * (cells + 1) + column + 1,
            (row + 1) * (cells + 1) + column,
        )
        for row in range(cells)
        for column in range(cells)
    ]
    base = len(verts)
    # The socket island floats beneath the plate, disconnected: a tub of four
    # walls and a floor, 20 long by 3 wide, walls facing inward.
    verts += [
        (-10.0, -1.5, -1.0), (10.0, -1.5, -1.0),
        (10.0, 1.5, -1.0), (-10.0, 1.5, -1.0),
        (-10.0, -1.5, -3.0), (10.0, -1.5, -3.0),
        (10.0, 1.5, -3.0), (-10.0, 1.5, -3.0),
    ]
    socket_faces = [
        (0, 1, 5, 4),      # low-y wall (clicked)
        (2, 3, 7, 6),      # high-y wall
        (1, 2, 6, 5),      # high-x end
        (3, 0, 4, 7),      # low-x end
        (4, 5, 6, 7),      # floor
    ]
    lock_wall_face = len(faces)
    faces += [tuple(base + index for index in quad) for quad in socket_faces]
    lock = make_mesh("Lock", verts, faces)

    key = make_mesh(
        "Key",
        [
            (-9.0, -1.2, 0.0), (9.0, -1.2, 0.0),
            (9.0, 1.2, 0.0), (-9.0, 1.2, 0.0),
            (-9.0, -1.2, 2.0), (9.0, -1.2, 2.0),
            (9.0, 1.2, 2.0), (-9.0, 1.2, 2.0),
        ],
        [
            (3, 2, 1, 0), (4, 5, 6, 7),
            (0, 1, 5, 4),      # low-y wall (clicked)
            (2, 3, 7, 6),
            (1, 2, 6, 5), (3, 0, 4, 7),
        ],
    )
    key.location = (30.0, 40.0, 10.0)
    bpy.context.view_layer.update()
    key_hit = key.matrix_world @ Vector((0.0, -1.2, 1.0))
    lock_hit = lock.matrix_world @ Vector((0.0, -1.5, -2.0))
    return key, 2, key_hit, lock, lock_wall_face, lock_hit


def assert_region_extraction_matches_full():
    """A dense part mates from a click-local region, and identically.

    Region extraction must be behaviour-invisible: any patch touching the
    sphere's rim widens it, so every measurement the solver reads comes from
    whole patches. The fixture's clicked wall overruns the first radius, so
    this exercises the raise-and-widen path, the settled partial region, and
    delta equality against full coverage in one pass.
    """
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_regioned_pair()
    settings = SimpleNamespace(ignore_modifiers=True)
    full = quicksnap_utils.compute_lock_key_transform(
        bpy.context, settings,
        "Key", key_face, key_hit, "Lock", lock_face, lock_hit,
    )
    if full is None:
        raise AssertionError("the full-coverage control failed to mate")

    key_provider = quicksnap_utils.LockKeyMeshProvider(key_hit)
    lock_provider = quicksnap_utils.LockKeyMeshProvider(lock_hit)
    while True:
        try:
            delta = quicksnap_utils.compute_lock_key_transform(
                bpy.context, settings,
                "Key", key_face, key_hit, "Lock", lock_face, lock_hit,
                source_mesh_data=key_provider.data(bpy.data.objects["Key"]),
                target_mesh_data=lock_provider.data(bpy.data.objects["Lock"]),
            )
            break
        except quicksnap_utils.LockKeyRegionTooSmall as region:
            if not region.provider.widen():
                raise AssertionError(
                    "full coverage raised the widen signal"
                )
    if delta is None:
        raise AssertionError("the region path refused a mate full coverage found")
    if lock_provider.full:
        raise AssertionError("the lock region ballooned to full coverage")
    if lock_provider.fraction <= quicksnap_utils._REGION_INITIAL_FRACTION:
        raise AssertionError("the widen path was never exercised")
    difference = max(
        abs(delta[row][column] - full[row][column])
        for row in range(4) for column in range(4)
    )
    if difference > 1e-5:
        raise AssertionError(
            f"region mate differs from full coverage by {difference}"
        )


def assert_disconnected_recovery_widens_to_full():
    clear_scene()
    key, lock, floor_face = disconnected_floored_lock()
    key_face = 0
    key_hit = key.matrix_world @ key.data.polygons[key_face].center
    floor_hit = lock.matrix_world @ lock.data.polygons[floor_face].center
    settings = SimpleNamespace(ignore_modifiers=True)
    kwargs = dict(
        allow_rotation=True,
        source_normal=world_normal(key, key_face),
        target_normal=world_normal(lock, floor_face),
    )
    full = quicksnap_utils.compute_lock_key_transform(
        bpy.context, settings,
        key.name, key_face, key_hit, lock.name, floor_face, floor_hit,
        **kwargs,
    )
    if full is None:
        raise AssertionError("full disconnected-floor control failed")

    key_provider = quicksnap_utils.LockKeyMeshProvider(key_hit)
    lock_provider = quicksnap_utils.LockKeyMeshProvider(floor_hit)
    while True:
        try:
            delta = quicksnap_utils.compute_lock_key_transform(
                bpy.context, settings,
                key.name, key_face, key_hit, lock.name, floor_face, floor_hit,
                source_mesh_data=key_provider.data(key),
                target_mesh_data=lock_provider.data(lock),
                **kwargs,
            )
            break
        except quicksnap_utils.LockKeyRegionTooSmall as region:
            if not region.provider.widen():
                raise AssertionError("disconnected recovery could not widen to full")
    if delta is None or not lock_provider.full:
        raise AssertionError("disconnected spatial absence was trusted before full coverage")
    if not np.allclose(np.array(delta), np.array(full), atol=1e-6, rtol=0.0):
        raise AssertionError("region-first disconnected recovery differs from full coverage")


def assert_parting_plane_click_is_named():
    """Clicking the flat face two halves meet on must say so.

    The commonest way to misread the feature. That plane has no opposite wall, so
    the solver falls back on whatever incidental detail is nearby and reports an
    angle between two things that were never connector walls -- which reads as a
    measurement and sent several rounds of diagnosis the wrong way.
    """
    def dome_half(name, location, peg):
        """An organic half with one flat parting plane carrying a connector.

        Unlike a plate it has no parallel back face, so the parting plane has
        nothing facing it -- which is the shape in the reported log.
        """
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=96, ring_count=48, radius=40, location=location)
        blob = bpy.context.active_object
        blob.name = name
        bpy.ops.mesh.primitive_cube_add(
            size=2.0, location=(location[0], location[1], location[2] + 40))
        cutter = bpy.context.active_object
        cutter.scale = (60, 60, 40)
        bpy.ops.object.transform_apply(
            location=False, rotation=False, scale=True)
        modifier = blob.modifiers.new("cut", 'BOOLEAN')
        modifier.operation = 'DIFFERENCE'
        modifier.object = cutter
        bpy.context.view_layer.objects.active = blob
        bpy.ops.object.modifier_apply(modifier="cut")
        bpy.data.objects.remove(cutter, do_unlink=True)
        # The connector itself, so the neighbourhood yields wall pairs exactly as a
        # real part does -- the point is that the *plane* is not one of them.
        bpy.ops.mesh.primitive_cube_add(
            size=2.0,
            location=(location[0], location[1], location[2] + (2 if peg else -2)),
        )
        tool = bpy.context.active_object
        tool.scale = (3.0, 3.0, 4.0) if peg else (3.36, 3.36, 4.0)
        bpy.ops.object.transform_apply(
            location=False, rotation=False, scale=True)
        modifier = blob.modifiers.new("connector", 'BOOLEAN')
        modifier.operation = 'UNION' if peg else 'DIFFERENCE'
        modifier.object = tool
        bpy.context.view_layer.objects.active = blob
        bpy.ops.object.modifier_apply(modifier="connector")
        bpy.data.objects.remove(tool, do_unlink=True)
        bpy.context.view_layer.update()
        return blob

    def flat_top(obj):
        return max(
            (p.index for p in obj.data.polygons if p.normal.z > 0.95),
            key=lambda index: obj.data.polygons[index].area,
        )

    clear_scene()
    lower = dome_half("Lower", (0.0, 0.0, 0.0), peg=True)
    upper = dome_half("Upper", (150.0, 0.0, 0.0), peg=False)
    key_face, lock_face = flat_top(lower), flat_top(upper)
    diagnostics = []
    delta = quicksnap_utils.compute_lock_key_transform(
        bpy.context, SimpleNamespace(ignore_modifiers=True),
        lower.name, key_face,
        lower.matrix_world @ lower.data.polygons[key_face].center,
        upper.name, lock_face,
        upper.matrix_world @ upper.data.polygons[lock_face].center,
        allow_rotation=False, diagnostics=diagnostics,
    )
    if delta is not None:
        raise AssertionError("two flat faces have no lateral constraint to mate on")
    if "large flat face rather than a connector" not in diagnostics[-1]:
        raise AssertionError(
            f"a parting-plane click was not named as one: {diagnostics[-1]!r}"
        )


def main():
    assert_blender_5_metadata()
    print("Blender 5 metadata: PASS")
    run_lock_key_case()
    print("straight translation: PASS")
    run_lock_key_case(lambda: make_tapered_key_lock(15.0))
    print("tapered translation: PASS")
    assert compute_case(
        lambda: make_key_lock(taper_degrees=15.0, target_taper_degrees=5.0)
    ) is None
    # ...but a few degrees is measurement rather than shape. Each wall carries its
    # own error, and matching already allows every one of them 10 degrees from
    # anti-parallel, so demanding their difference agree within 5 refused real
    # connectors -- and refused them twice over on the rotation path, which needs
    # two matched pairs and so fails entirely when one drops out.
    assert compute_case(
        lambda: make_key_lock(taper_degrees=15.0, target_taper_degrees=12.0)
    ) is not None
    # A key wider than its lock cannot be seated. (Equal widths are a snug fit and
    # do mate -- see assert_realistic_clearance_mates.)
    assert compute_case(
        lambda: make_key_lock(target_half_width=0.4, target_half_height=0.3)
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
    assert_rotation_follows_the_clicked_walls()
    assert_end_face_clicks_align_the_mate()
    assert_far_from_origin_spins_stay_equivalent()
    assert_round_connectors_slide_without_rotating()
    assert_rounded_end_faces_seat_square_or_refuse()
    assert_surroundings_pick_the_spin()
    print("optional rotation: PASS")
    assert_modifier_path_is_consistent()
    print("raw/evaluated picking path: PASS")
    assert_non_uniform_transform_mate()
    print("non-uniform transform: PASS")
    assert_realistic_clearance_mates()
    print("realistic print clearances: PASS")
    assert_either_half_may_move()
    print("either half may move: PASS")
    assert_picks_centre_on_their_wall()
    print("picks centre on their wall: PASS")
    assert_filleted_connectors_mate()
    print("filleted connectors mate: PASS")
    assert_thin_tabs_keep_their_thin_axis()
    print("thin tabs keep their thin axis: PASS")
    assert_patch_budget_does_not_cut_the_search_short()
    print("patch budget does not cut the search short: PASS")
    assert_fragmented_walls_are_rebuilt()
    print("fragmented walls are rebuilt: PASS")
    assert_curvature_is_judged_at_the_click()
    print("curvature judged at the click: PASS")
    assert_alignment_refusal_reports_how_far_off()
    print("alignment refusal reports how far off: PASS")
    assert_search_widens_for_a_second_axis()
    print("search widens for a second axis: PASS")
    assert_parting_plane_click_is_named()
    print("parting plane click is named: PASS")
    assert_a_connector_in_reach_is_not_called_a_flat_face()
    print("a peg in reach is not a flat face: PASS")
    assert_trim_does_not_outvote_the_real_walls()
    print("mouth trim does not outvote the real walls: PASS")
    assert_chamfer_click_names_its_wall()
    print("chamfer click names its wall: PASS")
    assert_region_extraction_matches_full()
    print("region extraction matches full coverage: PASS")
    assert_disconnected_recovery_widens_to_full()
    print("disconnected recovery widens to full coverage: PASS")
    assert_rotation_search_is_bounded()
    print("bounded rotation search: PASS")
    assert_insertion_direction_is_constrained()
    print("insertion direction constrained: PASS")
    assert_disconnected_floor_end_face_rotation()
    print("disconnected floor end-face rotation: PASS")
    assert_disconnected_recovery_handles_draft_and_scale()
    print("disconnected recovery handles draft and scale: PASS")
    assert_disconnected_search_stops_when_saturated()
    print("disconnected wall search stops when saturated: PASS")
    assert_spatial_recovery_rejects_incoherent_frames()
    print("spatial recovery rejects incoherent frames: PASS")
    assert_spatial_recovery_rejects_decoys()
    print("spatial recovery rejects decoys: PASS")
    assert_spatial_recovery_diagnostics_are_specific()
    print("spatial recovery diagnostics are specific: PASS")
    assert_spatial_recovery_merges_touching_fragments()
    print("spatial recovery merges touching fragments: PASS")
    assert_spatial_recovery_is_symmetric()
    print("spatial recovery is symmetric: PASS")
    assert_spatial_recovery_does_not_replace_ambiguity()
    print("spatial recovery preserves ambiguity: PASS")
    assert_spatial_recovery_is_isolated()
    print("spatial recovery isolation: PASS")
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
    assert_extra_pairs_yield_to_the_walls()
    print("extra pairs yield to the walls: PASS")
    assert_failures_report_a_specific_reason()
    print("specific failure reasons: PASS")
    assert_modal_lifecycle_helpers()
    print("modal lifecycle helpers: PASS")
    assert_terminate_survives_empty_selection()
    print("terminate with empty selection: PASS")
    assert_lock_key_settings_persist()
    print("Lock and key settings: PASS")
    print("lock_key_regression: PASS")


if __name__ == "__main__":
    main()
