import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import bpy
from mathutils import Matrix, Vector
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "legacy_snap_regression_package"
PACKAGE = types.ModuleType(PACKAGE_NAME)
PACKAGE.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = PACKAGE

UTILS_SPEC = importlib.util.spec_from_file_location(
    PACKAGE_NAME + ".quicksnap_utils", ROOT / "quicksnap_utils.py"
)
quicksnap_utils = importlib.util.module_from_spec(UTILS_SPEC)
sys.modules[UTILS_SPEC.name] = quicksnap_utils
UTILS_SPEC.loader.exec_module(quicksnap_utils)

SNAPDATA_SPEC = importlib.util.spec_from_file_location(
    PACKAGE_NAME + ".quicksnap_snapdata", ROOT / "quicksnap_snapdata.py"
)
quicksnap_snapdata = importlib.util.module_from_spec(SNAPDATA_SPEC)
sys.modules[SNAPDATA_SPEC.name] = quicksnap_snapdata
SNAPDATA_SPEC.loader.exec_module(quicksnap_snapdata)
ObjectPointData = quicksnap_snapdata.ObjectPointData
SnapData = quicksnap_snapdata.SnapData

SHADER_SPEC_NAME = PACKAGE_NAME + ".quicksnap_shader_gpu_module"
SHADER_STUB = types.ModuleType(SHADER_SPEC_NAME)
for name in (
    "shader_2d_image_color", "shader_2d_uniform_color", "shader_3d_uniform_color",
    "shader_3d_smooth_color", "shader_3d_polyline_smooth_color",
    "draw_line_3d_smooth_blend_versionized", "draw_polygon_smooth_blend_versionized",
):
    setattr(SHADER_STUB, name, None)
sys.modules[SHADER_SPEC_NAME] = SHADER_STUB
RENDER_SPEC = importlib.util.spec_from_file_location(
    PACKAGE_NAME + ".quicksnap_render", ROOT / "quicksnap_render.py"
)
quicksnap_render = importlib.util.module_from_spec(RENDER_SPEC)
sys.modules[RENDER_SPEC.name] = quicksnap_render
RENDER_SPEC.loader.exec_module(quicksnap_render)


def assert_dense_highlight_topology_indices():
    edges = np.array([[2, 0], [1, 2], [3, 2], [0, 1]], dtype=int)
    edge_indices, vertex_ranges = quicksnap_render._vertex_edge_ranges(edges, 5)
    expected_edges = [[0, 3], [1, 3], [0, 1, 2], [2], []]
    actual_edges = [edge_indices[vertex_ranges[i]:vertex_ranges[i + 1]].tolist() for i in range(5)]
    if actual_edges != expected_edges:
        raise AssertionError(f"vertex edge ranges: expected {expected_edges!r}, got {actual_edges!r}")

    triangle_polygons = np.array([2, 0, 2, 1, 0], dtype=int)
    triangle_indices, polygon_ranges = quicksnap_render._polygon_triangle_ranges(triangle_polygons, 4)
    expected_triangles = [[1, 4], [3], [0, 2], []]
    actual_triangles = [
        triangle_indices[polygon_ranges[i]:polygon_ranges[i + 1]].tolist() for i in range(4)
    ]
    if actual_triangles != expected_triangles:
        raise AssertionError(
            f"polygon triangle ranges: expected {expected_triangles!r}, got {actual_triangles!r}"
        )


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def make_identity_snapdata(scene_meshes, object_id):
    snapdata = SnapData.__new__(SnapData)
    snapdata.scene_meshes = scene_meshes
    snapdata.object_id = np.array([object_id], dtype=int)
    return snapdata


def assert_object_name_lookup():
    cases = [
        ([], -1, None, "cursor with no objects"),
        (["Only"], -1, None, "cursor with one object"),
        (["Only"], 1, None, "object ID at upper bound"),
        (["Only"], 0, "Only", "valid object ID"),
    ]
    for scene_meshes, object_id, expected, label in cases:
        snapdata = make_identity_snapdata(scene_meshes, object_id)
        actual = snapdata.get_object_name_at_index(0)
        if actual != expected:
            raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_find_closest_uses_safe_object_name():
    snapdata = make_identity_snapdata(["Only"], -1)
    snapdata.region_2d = np.array([[10.0, 10.0, 0.00000001]])
    snapdata.world_space = np.array([[0.0, 0.0, 0.0]])
    snapdata.indices = np.array([-1], dtype=int)
    snapdata.spline_index = np.array([-1], dtype=int)
    snapdata.origins_map = {}
    snapdata.use_numpy_query = False
    snapdata.snap_type = "POINTS"
    snapdata.last_query_ms = 0.0
    snapdata.kd = SimpleNamespace(find_range=lambda _mouse, _radius: [((10.0, 10.0, 0.00000001), 0, 0.0)])
    result = snapdata.find_closest((10.0, 10.0, 0.0))
    if result[2] is not None:
        raise AssertionError(f"cursor target should have no object, got {result[2]!r}")


def make_modifier_fixture():
    mesh = bpy.data.meshes.new("RawSourceMesh")
    mesh.from_pydata(
        [
            (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5),
            (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
            (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5),
            (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
        ],
        [],
        [
            (0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
            (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7),
        ],
    )
    mesh.update()
    obj = bpy.data.objects.new("RawSource", mesh)
    bpy.context.collection.objects.link(obj)
    modifier = obj.modifiers.new("Reduce", "DECIMATE")
    modifier.ratio = 0.1
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.context.view_layer.update()
    return obj


def assert_object_mode_source_ignore_modifiers_capacity():
    clear_scene()
    obj = make_modifier_fixture()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_count = len(obj.evaluated_get(depsgraph).data.vertices)
    raw_count = len(obj.data.vertices)
    if evaluated_count >= raw_count:
        raise AssertionError("fixture modifier did not reduce topology")

    snapdata = SnapData.__new__(SnapData)
    snapdata.is_origin_snapdata = True
    snapdata.no_selection = False
    snapdata.object_mode = True
    snapdata.snap_type = "POINTS"
    snapdata.settings = SimpleNamespace(ignore_modifiers=True)
    capacity = snapdata.get_max_vertex_count(bpy.context, [obj.name], [])

    snapdata.processed = set()
    snapdata.to_process_selected = []
    snapdata.to_process_scene = []
    snapdata.objects_point_data = {}
    snapdata.selected_ids = {}
    snapdata.scene_meshes = [obj.name]
    snapdata.scene_object_indices = {obj.name: 0}
    snapdata.perspective_matrix = Matrix.Identity(4)
    snapdata.width = 100
    snapdata.height = 100
    snapdata.width_half = 50
    snapdata.height_half = 50
    snapdata.view_location = (0.0, 0.0, 10.0)
    snapdata.world_space = np.empty((capacity, 3), dtype=np.float64)
    snapdata.region_2d = np.empty((capacity, 3), dtype=np.float64)
    snapdata.indices = np.empty(capacity, dtype=int)
    snapdata.spline_index = np.empty(capacity, dtype=int)
    snapdata.object_id = np.empty(capacity, dtype=int)
    snapdata.in_query = np.zeros(capacity, dtype=bool)
    snapdata.added_points_np = 1

    snapdata.add_object_data(obj.name, is_selected=True, depsgraph=depsgraph)
    if hasattr(snapdata, "depth"):
        raise AssertionError("SnapData retained the removed duplicate depth buffer")
    while not snapdata.objects_point_data[obj.name].completed:
        snapdata.process_points_data_batch(obj.name, 1000)

    added_indices = snapdata.indices[1:snapdata.added_points_np]
    if len(added_indices) != raw_count:
        raise AssertionError(f"expected {raw_count} raw vertices, ingested {len(added_indices)}")
    if len(added_indices) and int(np.max(added_indices)) >= raw_count:
        raise AssertionError("ingested index does not fit raw source topology")


def make_mixed_faces():
    mesh = bpy.data.meshes.new("MixedFacesMesh")
    mesh.from_pydata(
        [(-0.8, -0.8, 0.0), (0.0, -0.8, 0.0), (-0.4, 0.0, 0.0),
         (0.1, -0.8, 0.0), (0.8, -0.8, 0.0), (0.8, 0.0, 0.0), (0.1, 0.0, 0.0)],
        [],
        [(0, 1, 2), (3, 4, 5, 6)],
    )
    mesh.update()
    obj = bpy.data.objects.new("MixedFaces", mesh)
    bpy.context.collection.objects.link(obj)
    for index, vertex in enumerate(mesh.vertices):
        vertex.select = index < 3
    return obj


def face_data(obj, filter_selected=True):
    return ObjectPointData(
        obj, 0, Matrix.Identity(4), 100, 100, 50, 50, (0.0, 0.0, 10.0),
        check_select=True, filter_selected=filter_selected, snap_type="FACES",
    )


def assert_mixed_face_selection_masks():
    clear_scene()
    obj = make_mixed_faces()
    selected = face_data(obj)
    unselected = face_data(obj, filter_selected=False)
    if selected.indices.tolist() != [0]:
        raise AssertionError(f"selected face candidates should be [0], got {selected.indices.tolist()}")
    if unselected.indices.tolist() != [1]:
        raise AssertionError(f"unselected face candidates should be [1], got {unselected.indices.tolist()}")


def assert_polygonless_faces_are_empty():
    clear_scene()
    mesh = bpy.data.meshes.new("PolygonlessMesh")
    mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
    obj = bpy.data.objects.new("Polygonless", mesh)
    bpy.context.collection.objects.link(obj)
    data = face_data(obj)
    if not data.completed:
        raise AssertionError("polygonless FACES data should complete without candidates")


def make_curve():
    curve = bpy.data.curves.new("UnsupportedCurveData", "CURVE")
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    obj = bpy.data.objects.new("UnsupportedCurve", curve)
    bpy.context.collection.objects.link(obj)
    return obj


def make_queue_snapdata(obj, snap_type):
    snapdata = SnapData.__new__(SnapData)
    snapdata.processed = set()
    snapdata.to_process_selected = []
    snapdata.to_process_scene = []
    snapdata.objects_point_data = {}
    snapdata.selected_ids = {}
    snapdata.is_origin_snapdata = False
    snapdata.object_mode = True
    snapdata.no_selection = False
    snapdata.snap_type = snap_type
    snapdata.settings = SimpleNamespace(ignore_modifiers=True)
    snapdata.scene_object_indices = {obj.name: 0}
    snapdata.perspective_matrix = Matrix.Identity(4)
    snapdata.width = 100
    snapdata.height = 100
    snapdata.width_half = 50
    snapdata.height_half = 50
    snapdata.view_location = (0.0, 0.0, 10.0)
    return snapdata


def assert_unsupported_curve_types_skip_queues():
    clear_scene()
    curve = make_curve()
    for snap_type in ("MIDPOINTS", "FACES"):
        snapdata = make_queue_snapdata(curve, snap_type)
        snapdata.add_object_data(curve.name, is_selected=True, depsgraph=None)
        snapdata.add_object_data(curve.name, is_selected=False, depsgraph=None)
        if snapdata.to_process_selected or snapdata.to_process_scene:
            raise AssertionError(f"{snap_type} curve must not enter a processing queue")


def make_visibility_object(name, hidden, selected):
    mesh = bpy.data.meshes.new(name + "Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.hide_set(False)
    obj.select_set(selected)
    obj.hide_set(hidden)
    return obj


def visibility_state(objects):
    return [(obj.hide_get(), obj.select_get()) for obj in objects]


def assert_progressive_timeout_restores_visibility():
    clear_scene()
    selected = [
        make_visibility_object("VisibleSelected", False, True),
        make_visibility_object("PreHidden", True, False),
    ]
    target = make_visibility_object("Target", False, False)
    before = visibility_state(selected)

    snapdata = SnapData.__new__(SnapData)
    snapdata.keep_processing = True
    snapdata.is_origin_snapdata = False
    snapdata.object_mode = True
    snapdata.to_process_selected = []
    snapdata.to_process_scene = [target.name]
    snapdata.meshes_selection = [obj.name for obj in selected]
    snapdata.objects_point_data = {target.name: SimpleNamespace(completed=False)}
    snapdata.added_points_np = 0
    snapdata.processed = set()
    snapdata.world_space = np.empty((1, 3))
    snapdata.process_points_data_batch = lambda _name, _count: None
    snapdata.balance_tree = lambda *_args: None

    original_counter = quicksnap_snapdata.time.perf_counter
    ticks = iter((0.0, 0.0, 1.0))
    quicksnap_snapdata.time.perf_counter = lambda: next(ticks)
    try:
        still_processing = snapdata.process_iteration(bpy.context, max_run_duration=0.01)
    finally:
        quicksnap_snapdata.time.perf_counter = original_counter
    if not still_processing:
        raise AssertionError("unfinished target ingestion should exhaust the time budget")
    if visibility_state(selected) != before:
        raise AssertionError(f"timeout changed visibility/selection: {before!r} -> {visibility_state(selected)!r}")


def assert_nearby_exception_restores_visibility():
    clear_scene()
    processed = [
        make_visibility_object("ProcessedVisible", False, True),
        make_visibility_object("ProcessedHidden", True, False),
    ]
    before = visibility_state(processed)
    snapdata = SnapData.__new__(SnapData)
    snapdata.processed = {obj.name for obj in processed}

    original_check = quicksnap_utils.check_close_objects
    quicksnap_utils.check_close_objects = lambda *_args: (_ for _ in ()).throw(RuntimeError("injected"))
    try:
        try:
            snapdata.add_nearby_objects(bpy.context, None, None, (0, 0))
        except RuntimeError as exc:
            if str(exc) != "injected":
                raise
        else:
            raise AssertionError("injected nearby-discovery exception did not propagate")
    finally:
        quicksnap_utils.check_close_objects = original_check
    if visibility_state(processed) != before:
        raise AssertionError(f"exception changed visibility/selection: {before!r} -> {visibility_state(processed)!r}")


def assert_free_target_constraints_use_world_axes():
    origin = Vector((0.0, 0.0, 0.0))

    anti_parallel = quicksnap_utils.get_target_free(
        origin, Vector((2.0, 3.0, 5.0)), Vector((0.0, 0.0, -1.0)), "XY",
        is_ortho=True,
    )
    if anti_parallel is None or not np.allclose(anti_parallel, (2.0, 3.0, 0.0)):
        raise AssertionError(f"anti-parallel orthographic plane target: {anti_parallel!r}")

    obj = SimpleNamespace(matrix_world=Matrix.Rotation(np.pi / 2.0, 4, "Z"))
    local_plane = quicksnap_utils.get_target_free(
        origin, Vector((3.0, 2.0, 5.0)), Vector((-1.0, 0.0, -1.0)), "XZ", obj,
    )
    if local_plane is None or not np.allclose(local_plane, (0.0, 2.0, 2.0), atol=1e-6):
        raise AssertionError(f"rotated local plane target: {local_plane!r}")

    local_axis = quicksnap_utils.get_target_free(
        origin, Vector((5.0, 2.0, 3.0)), Vector((-1.0, 0.0, 0.0)), "X", obj,
    )
    if local_axis is None or not np.allclose(local_axis, (0.0, 2.0, 0.0), atol=1e-6):
        raise AssertionError(f"rotated local axis target: {local_axis!r}")


def assert_parented_ortho_camera_uses_world_location():
    clear_scene()
    parent = bpy.data.objects.new("CameraParent", None)
    camera_data = bpy.data.cameras.new("ParentedOrthoData")
    camera = bpy.data.objects.new("ParentedOrtho", camera_data)
    bpy.context.collection.objects.link(parent)
    bpy.context.collection.objects.link(camera)
    camera.parent = parent
    parent.location = (0.0, 0.0, 10.0)
    camera.location = (0.0, 0.0, -5.0)
    bpy.context.view_layer.update()

    snapdata = SnapData.__new__(SnapData)
    snapdata.perspective_matrix = Matrix.Identity(4)
    snapdata.width = snapdata.height = 100
    snapdata.width_half = snapdata.height_half = 50
    snapdata.added_points_np = 0
    snapdata.world_space = np.empty((1, 3), dtype=np.float64)
    snapdata.region_2d = np.empty((1, 3), dtype=np.float64)
    snapdata.indices = np.empty(1, dtype=int)
    snapdata.object_id = np.empty(1, dtype=int)
    snapdata.in_query = np.zeros(1, dtype=bool)
    snapdata.kd = SimpleNamespace(insert=lambda *_args: None)

    region3d = SimpleNamespace(view_perspective="CAMERA", is_perspective=False)
    context = SimpleNamespace(
        space_data=SimpleNamespace(region_3d=region3d, camera=camera),
        region=SimpleNamespace(),
    )
    original_vector = quicksnap_snapdata.view3d_utils.region_2d_to_vector_3d
    quicksnap_snapdata.view3d_utils.region_2d_to_vector_3d = lambda *_args: Vector((0.0, 0.0, -1.0))
    try:
        added = snapdata.add_point(context, Vector((0.0, 0.0, 0.0)), Matrix.Identity(4), 0)
    finally:
        quicksnap_snapdata.view3d_utils.region_2d_to_vector_3d = original_vector
    if not added:
        raise AssertionError(
            f"point in front of parented camera at {camera.matrix_world.translation!r} was culled")


def main():
    assert_dense_highlight_topology_indices()
    print("dense highlight topology indices: PASS")
    assert_object_name_lookup()
    print("snapdata object-name bounds: PASS")
    assert_find_closest_uses_safe_object_name()
    print("snapdata cursor result identity: PASS")
    assert_object_mode_source_ignore_modifiers_capacity()
    print("snapdata raw modifier capacity: PASS")
    assert_mixed_face_selection_masks()
    print("snapdata mixed face selection: PASS")
    assert_polygonless_faces_are_empty()
    print("snapdata polygonless faces: PASS")
    assert_unsupported_curve_types_skip_queues()
    print("snapdata unsupported curve queues: PASS")
    assert_progressive_timeout_restores_visibility()
    print("snapdata progressive timeout visibility: PASS")
    assert_nearby_exception_restores_visibility()
    print("snapdata nearby exception visibility: PASS")
    assert_free_target_constraints_use_world_axes()
    print("free target world-space constraints: PASS")
    assert_parented_ortho_camera_uses_world_location()
    print("parented orthographic camera culling: PASS")


if __name__ == "__main__":
    main()
