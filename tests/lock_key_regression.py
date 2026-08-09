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
    assert_failures_report_a_specific_reason()
    print("specific failure reasons: PASS")
    assert_terminate_survives_empty_selection()
    print("terminate with empty selection: PASS")
    assert_lock_key_settings_persist()
    print("Lock and key settings: PASS")
    print("lock_key_regression: PASS")


if __name__ == "__main__":
    main()
