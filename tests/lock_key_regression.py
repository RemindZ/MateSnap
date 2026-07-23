import importlib.util
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Vector
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "quicksnap_utils_under_test", ROOT / "quicksnap_utils.py"
)
quicksnap_utils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quicksnap_utils)


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


def make_straight_key_lock():
    key = make_mesh(
        "Key",
        [
            (-0.5, -0.4, -1.0), (0.5, -0.4, -1.0),
            (0.5, 0.4, -1.0), (-0.5, 0.4, -1.0),
            (-0.5, -0.4, 0.0), (0.5, -0.4, 0.0),
            (0.5, 0.4, 0.0), (-0.5, 0.4, 0.0),
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
            (-0.6, -0.5, 0.0), (0.6, -0.5, 0.0),
            (0.6, 0.5, 0.0), (-0.6, 0.5, 0.0),
            (-0.6, -0.5, -1.2), (0.6, -0.5, -1.2),
            (0.6, 0.5, -1.2), (-0.6, 0.5, -1.2),
        ],
        [
            (0, 4, 5, 1), (1, 5, 6, 2),
            (2, 6, 7, 3), (3, 7, 4, 0),
        ],
    )
    key.location = (2.0, -1.0, 0.0)
    bpy.context.view_layer.update()
    key_hit = key.matrix_world @ Vector((-0.5, 0.0, -0.3))
    lock_hit = lock.matrix_world @ Vector((-0.6, 0.1, -0.7))
    return key, 5, key_hit, lock, 3, lock_hit


def make_tapered_key_lock(taper_degrees):
    raise NotImplementedError


def assert_matrix_finite(matrix):
    values = np.array(matrix, dtype=np.float64)
    if values.shape != (4, 4) or not np.isfinite(values).all():
        raise AssertionError(f"expected finite 4x4 matrix, got {matrix!r}")


def run_lock_key_case():
    clear_scene()
    key, key_face, key_hit, lock, lock_face, lock_hit = make_straight_key_lock()
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


def main():
    run_lock_key_case()
    print("straight translation: PASS")
    print("lock_key_regression: PASS")


if __name__ == "__main__":
    main()
