import bpy, mathutils, logging
from mathutils import Vector
from enum import Enum
import itertools
import math
from bpy_extras import view3d_utils
import numpy as np

__name_addon__ = '.'.join(__name__.split('.')[:-1])
logger = logging.getLogger(__name_addon__)


class State(Enum):
    IDLE = 1
    SOURCE_PICKED = 2
    DESTINATION_PICKED = 3


def transform_worldspace_viewspace(world_space_coord, perspective_matrix):
    return perspective_matrix @ Vector((world_space_coord[0], world_space_coord[1], world_space_coord[2], 1.0))


def transform_viewspace_coord2d(view_space_coord, width_half, height_half):
    return Vector((width_half + width_half * (view_space_coord.x / view_space_coord.w),
                   height_half + height_half * (view_space_coord.y / view_space_coord.w),
                   ))


def transform_worldspace_coord2d(world_space_coord, region, region3d):
    return transform_viewspace_coord2d(transform_worldspace_viewspace(world_space_coord, region3d.perspective_matrix),
                                       region.width / 2.0, region.height / 2.0)


def get_selection_objects(context):
    if 'EDIT' in context.mode:
        return [obj for obj in context.selected_objects if obj.visible_get()]
    else:
        return [obj for obj in context.selected_objects if obj.visible_get()]


def get_scene_objects(exclude_selection=False):
    if exclude_selection:
        objects = [obj.name for obj in bpy.data.objects if
                   obj not in bpy.context.selected_objects and obj.visible_get()]
    else:
        objects = [obj.name for obj in bpy.data.objects if
                   obj.visible_get()]
    return objects


def include_children(objects, recursive_call=False):
    """
    Inputs a list of objects, outputs that list + children objects
    """

    result = []
    if type(objects) is list or type(objects) is set:
        if not recursive_call:
            objects = keep_only_parents(objects)
        for obj in objects:
            result.extend(include_children(obj, recursive_call=True))
    else:
        obj = objects
        result.append(obj)
        for child in obj.children:
            result.extend(include_children(child, recursive_call=True))
    return result


def keep_only_parents(objects):
    """
    Inputs a list of objects, outputs that list minus all children of objects in that list
    """
    objects = set(objects)
    return set([obj for obj in objects if not has_parent(obj, objects)])


def has_parent(obj, parent_list):
    """
    Returns True of the object has a parent among a list of objects
    """
    parent = obj.parent
    if parent == None:
        return False
    if parent in parent_list:
        return True
    return has_parent(parent, parent_list)


def set_object_mode_if_needed():
    """
    Set context to object mode, returns the previous mode.
    """
    # logger.info("entering object mode if needed")
    if bpy.context.active_object is not None:
        mode = f'{bpy.context.active_object.mode}'
    else:
        mode = 'OBJECT'
    if mode != 'OBJECT':
        # logger.info('Going to Object Mode')
        bpy.ops.object.mode_set(mode='OBJECT')
    return mode


def revert_mode(previous_mode):
    if bpy.context.active_object is not None and bpy.context.active_object.mode != previous_mode:
        bpy.ops.object.mode_set(mode=previous_mode)


def translate_object_worldspace(obj, translation):
    obj.matrix_world = translation @ obj.matrix_world


def translate_vertices_worldspace(obj, bmesh, backup_vertices, translation):
    if hasattr(bmesh.verts, "ensure_lookup_table"):
        bmesh.verts.ensure_lookup_table()
    world_matrix = obj.matrix_world
    world_matrix_inverted = world_matrix.copy().inverted()
    for (index, co, _, _, _, _) in backup_vertices:
        bmesh.verts[index].co = world_matrix_inverted @ translation @ world_matrix @ co
    bmesh.to_mesh(obj.data)


def dump(obj):
    print(f"\n\n=============== Dump({obj}) ===============")
    for attr in dir(obj):
        if hasattr(obj, attr):
            print(f'{attr} : {getattr(obj, attr)}')
    print(f"=============== END Dump({obj}) ===============\n\n")


def get_addon_settings():
    addon = bpy.context.preferences.addons.get(__name_addon__)
    if addon:
        return addon.preferences
    return None


def get_object_vertex_count(obj, depsgraph=None):
    """
    Vertex count used to gate the heavy-mesh paths. With a depsgraph and modifiers, returns the
    evaluated (displayed) count so subsurf/multires sculpts gate the same way they are ingested.
    """
    if obj is None or obj.type != 'MESH':
        return 0
    if depsgraph is not None and len(obj.modifiers) > 0:
        try:
            return len(obj.evaluated_get(depsgraph).data.vertices)
        except (RuntimeError, AttributeError):
            pass
    return len(obj.data.vertices)


def is_heavy_object(obj, settings=None, depsgraph=None):
    """True if the object is above the (user-set) vertex threshold and should use the heavy paths."""
    if settings is None:
        settings = get_addon_settings()
    if settings is None or not getattr(settings, "optimize_heavy_meshes", True):
        return False
    # Match ingestion: count evaluated verts unless modifiers are ignored.
    if getattr(settings, "ignore_modifiers", False):
        depsgraph = None
    return get_object_vertex_count(obj, depsgraph) >= settings.heavy_mesh_threshold * 1000


_FIT_COS_5 = math.cos(math.radians(5.0))
_FIT_ABS_TOL = 1e-7


def _mesh_fit_data(obj):
    mesh = obj.data
    vertex_count = len(mesh.vertices)
    polygon_count = len(mesh.polygons)
    loop_count = len(mesh.loops)
    edge_count = len(mesh.edges)

    vertices = np.empty(vertex_count * 3, dtype=np.float64)
    mesh.vertices.foreach_get('co', vertices)
    vertices.shape = (vertex_count, 3)
    matrix = np.array(obj.matrix_world, dtype=np.float64)
    inverse = np.array(obj.matrix_world.inverted(), dtype=np.float64)
    vertices = vertices @ matrix[:3, :3].T + matrix[:3, 3]

    loop_vertices = np.empty(loop_count, dtype=np.int32)
    loop_edges = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get('vertex_index', loop_vertices)
    mesh.loops.foreach_get('edge_index', loop_edges)

    loop_starts = np.empty(polygon_count, dtype=np.int32)
    loop_totals = np.empty(polygon_count, dtype=np.int32)
    centers = np.empty(polygon_count * 3, dtype=np.float64)
    normals = np.empty(polygon_count * 3, dtype=np.float64)
    mesh.polygons.foreach_get('loop_start', loop_starts)
    mesh.polygons.foreach_get('loop_total', loop_totals)
    mesh.polygons.foreach_get('center', centers)
    mesh.polygons.foreach_get('normal', normals)
    centers.shape = (polygon_count, 3)
    normals.shape = (polygon_count, 3)
    centers = centers @ matrix[:3, :3].T + matrix[:3, 3]
    normals = normals @ inverse[:3, :3]
    lengths = np.linalg.norm(normals, axis=1)
    lengths[lengths == 0] = 1.0
    normals /= lengths[:, None]

    edge_vertices = np.empty(edge_count * 2, dtype=np.int32)
    mesh.edges.foreach_get('vertices', edge_vertices)
    edge_vertices.shape = (edge_count, 2)
    edge_lengths = np.linalg.norm(vertices[edge_vertices[:, 0]] - vertices[edge_vertices[:, 1]], axis=1)

    loop_polygons = np.repeat(np.arange(polygon_count, dtype=np.int32), loop_totals)
    edge_order = np.argsort(loop_edges, kind='stable')
    edge_counts = np.bincount(loop_edges, minlength=edge_count)
    edge_starts = np.concatenate(([0], np.cumsum(edge_counts)))

    return {
        'mesh': mesh,
        'vertices': vertices,
        'loop_vertices': loop_vertices,
        'loop_edges': loop_edges,
        'loop_starts': loop_starts,
        'loop_totals': loop_totals,
        'loop_polygons': loop_polygons,
        'polygon_centers': centers,
        'polygon_normals': normals,
        'edge_lengths': edge_lengths,
        'edge_polygons': loop_polygons[edge_order],
        'edge_starts': edge_starts,
        'polygon_geometry': {},
        'polygon_patches': {},
    }


def _seed_polygons(mesh_data, snap_type, element_index):
    if element_index < 0:
        return []
    if snap_type == 'POINTS' and element_index < len(mesh_data['vertices']):
        mask = mesh_data['loop_vertices'] == element_index
        return np.unique(mesh_data['loop_polygons'][mask]).tolist()
    if snap_type == 'MIDPOINTS' and element_index < len(mesh_data['edge_lengths']):
        mask = mesh_data['loop_edges'] == element_index
        return np.unique(mesh_data['loop_polygons'][mask]).tolist()
    if snap_type == 'FACES' and element_index < len(mesh_data['loop_starts']):
        return [element_index]
    return []


def _polygon_geometry(mesh_data, polygon_index):
    cached = mesh_data['polygon_geometry'].get(polygon_index)
    if cached is not None:
        return cached
    start = int(mesh_data['loop_starts'][polygon_index])
    total = int(mesh_data['loop_totals'][polygon_index])
    vertex_indices = mesh_data['loop_vertices'][start:start + total]
    coordinates = mesh_data['vertices'][vertex_indices]
    if len(coordinates) < 3:
        area = 0.0
    else:
        triangles = np.cross(coordinates[1:-1] - coordinates[0], coordinates[2:] - coordinates[0])
        area = 0.5 * float(np.linalg.norm(triangles, axis=1).sum())
    cached = {
        'vertices': vertex_indices,
        'area': area,
        'center': mesh_data['polygon_centers'][polygon_index],
        'normal': mesh_data['polygon_normals'][polygon_index],
    }
    mesh_data['polygon_geometry'][polygon_index] = cached
    return cached


def _edge_neighbors(mesh_data, edge_index):
    start = int(mesh_data['edge_starts'][edge_index])
    end = int(mesh_data['edge_starts'][edge_index + 1])
    return mesh_data['edge_polygons'][start:end]


def _grow_planar_patch(mesh_data, seed_polygon, cos_planar=_FIT_COS_5):
    if seed_polygon in mesh_data['polygon_patches']:
        return mesh_data['polygon_patches'][seed_polygon]

    component = {int(seed_polygon)}
    queue = [int(seed_polygon)]
    while queue:
        polygon_index = queue.pop()
        start = int(mesh_data['loop_starts'][polygon_index])
        total = int(mesh_data['loop_totals'][polygon_index])
        normal = mesh_data['polygon_normals'][polygon_index]
        center = mesh_data['polygon_centers'][polygon_index]
        for edge_index in mesh_data['loop_edges'][start:start + total]:
            tolerance = max(0.005 * float(mesh_data['edge_lengths'][edge_index]), _FIT_ABS_TOL)
            for neighbor in _edge_neighbors(mesh_data, int(edge_index)):
                neighbor = int(neighbor)
                if neighbor in component:
                    continue
                neighbor_normal = mesh_data['polygon_normals'][neighbor]
                if float(normal @ neighbor_normal) < cos_planar:
                    continue
                neighbor_center = mesh_data['polygon_centers'][neighbor]
                if abs(float((neighbor_center - center) @ normal)) > tolerance:
                    continue
                if abs(float((center - neighbor_center) @ neighbor_normal)) > tolerance:
                    continue
                component.add(neighbor)
                queue.append(neighbor)

    polygon_indices = np.array(sorted(component), dtype=np.int32)
    geometry = [_polygon_geometry(mesh_data, int(index)) for index in polygon_indices]
    areas = np.array([item['area'] for item in geometry], dtype=np.float64)
    total_area = float(areas.sum())
    patch = None
    if total_area > 0:
        point = (mesh_data['polygon_centers'][polygon_indices] * areas[:, None]).sum(axis=0) / total_area
        normal = (mesh_data['polygon_normals'][polygon_indices] * areas[:, None]).sum(axis=0)
        normal_length = float(np.linalg.norm(normal))
        if normal_length > 0:
            normal /= normal_length
            vertex_indices = np.unique(np.concatenate([item['vertices'] for item in geometry]))
            coordinates = mesh_data['vertices'][vertex_indices]
            extent = float(np.linalg.norm(coordinates.max(axis=0) - coordinates.min(axis=0)))
            tolerance = max(0.005 * extent, _FIT_ABS_TOL)
            residual = float(np.max(np.abs((mesh_data['polygon_centers'][polygon_indices] - point) @ normal)))
            if extent > 0 and residual <= tolerance:
                boundary_edges = set()
                for polygon_index in polygon_indices:
                    start = int(mesh_data['loop_starts'][polygon_index])
                    total = int(mesh_data['loop_totals'][polygon_index])
                    for edge_index in mesh_data['loop_edges'][start:start + total]:
                        neighbors = _edge_neighbors(mesh_data, int(edge_index))
                        if any(int(neighbor) not in component for neighbor in neighbors):
                            boundary_edges.add(int(edge_index))
                patch = {
                    'id': tuple(int(index) for index in polygon_indices),
                    'polygons': component,
                    'boundary_edges': tuple(sorted(boundary_edges)),
                    'point': point,
                    'normal': normal,
                    'area': total_area,
                    'extent': extent,
                    'residual': residual,
                    'tolerance': tolerance,
                    # How precisely this plane is defined, as opposed to how big it
                    # is. 'tolerance' is a flatness allowance scaled to the patch
                    # size and is far too coarse to judge whether a fit clearance is
                    # real: on a 10-unit peg it demands ~2% clearance, while printed
                    # connectors are modelled at 1% or less.
                    'fit_tolerance': max(
                        residual, 1e-6 * extent, _FIT_ABS_TOL
                    ),
                }

    for polygon_index in component:
        mesh_data['polygon_patches'][polygon_index] = patch
    return patch


def _patch_sort_key(patch):
    normal = patch['normal'].copy()
    dominant = int(np.argmax(np.abs(normal)))
    if normal[dominant] < 0:
        normal *= -1.0
    return tuple(np.round(normal, 9)) + (
        round(float(normal @ patch['point']), 9),
        round(float(patch['area']), 9),
    )


def _candidate_patches(mesh_data, seed_polygons, hops=2):
    """Patches within `hops` patch-boundary crossings of the clicked one.

    Two hops is the historic radius and the default every caller but Lock and key
    still uses; changing it here would move standard precision fit too.
    """
    patches = {}
    frontier = []
    for polygon_index in seed_polygons:
        patch = _grow_planar_patch(mesh_data, int(polygon_index))
        if patch is not None and patch['id'] not in patches:
            patches[patch['id']] = patch
            frontier.append(patch)

    for _ in range(hops):
        next_frontier = []
        for patch in frontier:
            for edge_index in patch['boundary_edges']:
                for polygon_index in _edge_neighbors(mesh_data, edge_index):
                    polygon_index = int(polygon_index)
                    if polygon_index in patch['polygons']:
                        continue
                    neighbor = _grow_planar_patch(mesh_data, polygon_index)
                    if neighbor is not None and neighbor['id'] not in patches:
                        patches[neighbor['id']] = neighbor
                        next_frontier.append(neighbor)
        frontier = next_frontier
    return sorted(patches.values(), key=_patch_sort_key)


def _plane_pairs(patches, contact):
    opposed_limit = math.cos(math.radians(170.0))
    pairs = []
    for i, first in enumerate(patches):
        for second in patches[i + 1:]:
            if float(first['normal'] @ second['normal']) > opposed_limit:
                continue
            axis = first['normal'] - second['normal']
            length = float(np.linalg.norm(axis))
            if length == 0:
                continue
            axis /= length
            dominant = int(np.argmax(np.abs(axis)))
            if axis[dominant] < 0:
                axis *= -1.0
            first_d = float(axis @ first['point'])
            second_d = float(axis @ second['point'])
            if first_d <= second_d:
                low, high = first, second
                low_d, high_d = first_d, second_d
            else:
                low, high = second, first
                low_d, high_d = second_d, first_d
            tolerance = first['tolerance'] + second['tolerance']
            separation = high_d - low_d
            contact_d = float(axis @ contact)
            if separation <= tolerance:
                continue
            if contact_d < low_d - tolerance or contact_d > high_d + tolerance:
                continue
            pairs.append({
                'axis': axis,
                'low_patch': low,
                'high_patch': high,
                'low': low_d,
                'high': high_d,
                'mid': 0.5 * (low_d + high_d),
                'center': 0.5 * (low['point'] + high['point']),
                'separation': separation,
                'tolerance': tolerance,
            })
    return sorted(pairs, key=lambda pair: tuple(np.round(pair['axis'], 9)) + (round(pair['mid'], 9),))


def _match_plane_pairs(source_pairs, target_pairs, contact):
    opposed_limit = math.cos(math.radians(170.0))
    matches = []
    for source in source_pairs:
        candidates = []
        for target in target_pairs:
            if float(source['axis'] @ target['axis']) < _FIT_COS_5:
                continue
            if float(source['low_patch']['normal'] @ target['low_patch']['normal']) > opposed_limit:
                continue
            if float(source['high_patch']['normal'] @ target['high_patch']['normal']) > opposed_limit:
                continue
            tolerance = source['tolerance'] + target['tolerance']
            clearance = target['separation'] - source['separation']
            if clearance <= tolerance:
                continue
            delta = target['mid'] - source['mid']
            if abs(delta) > min(0.25 * source['separation'], 2.0 * clearance) + tolerance:
                continue
            distance = float(np.linalg.norm(target['center'] - contact))
            candidates.append((distance, tolerance, target, clearance, delta))
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[0])
        if len(candidates) > 1 and candidates[1][0] - candidates[0][0] <= candidates[0][1] + candidates[1][1]:
            continue
        _, tolerance, target, clearance, delta = candidates[0]
        matches.append({
            'axis': source['axis'],
            'source': source,
            'target': target,
            'clearance': clearance,
            'delta': delta,
            'tolerance': tolerance,
        })

    # Competing source slabs on one axis are ambiguous; never let polygon order choose one.
    return [
        match for index, match in enumerate(matches)
        if not any(
            index != other_index and abs(float(match['axis'] @ other['axis'])) >= _FIT_COS_5
            for other_index, other in enumerate(matches)
        )
    ]


def _solve_pair_translation(matches):
    if not matches:
        return None
    axes = np.array([match['axis'] for match in matches], dtype=np.float64)
    deltas = np.array([match['delta'] for match in matches], dtype=np.float64)
    try:
        translation = np.linalg.lstsq(axes, deltas, rcond=0.1)[0]
        _, singular, vh = np.linalg.svd(axes, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    if len(singular) == 0 or singular[0] <= 0:
        return None
    basis = vh[singular >= 0.1 * singular[0]]
    if len(basis) == 0:
        return None
    translation = basis.T @ (basis @ translation)
    scale = max(match['target']['separation'] for match in matches)
    if not np.isfinite(translation).all() or float(np.linalg.norm(translation)) <= 1e-12 * scale:
        return None
    return translation


def _validate_pair_translation(matches, translation):
    for match in matches:
        source = match['source']
        target = match['target']
        shift = float(match['axis'] @ translation)
        low_before = source['low'] - target['low']
        high_before = target['high'] - source['high']
        low_after = source['low'] + shift - target['low']
        high_after = target['high'] - source['high'] - shift
        tolerance = match['tolerance']
        if low_after < -tolerance or high_after < -tolerance:
            return False
        if abs(low_after - high_after) >= abs(low_before - high_before):
            return False
        if abs(low_after - high_after) > tolerance:
            return False
    return True


def compute_precision_fit(context, settings,
                          source_object_name, source_snap_type, source_element_index,
                          target_object_name, target_snap_type, target_element_index,
                          contact_point):
    """Center clean opposed plane pairs seeded by the user's source and target snap elements."""
    source_obj = bpy.data.objects.get(source_object_name)
    target_obj = bpy.data.objects.get(target_object_name)
    if source_obj is None or target_obj is None or source_obj.type != 'MESH' or target_obj.type != 'MESH':
        logger.debug("Precision fit skipped: source or target mesh is unavailable")
        return None
    depsgraph = context.evaluated_depsgraph_get()
    ignore_modifiers = getattr(settings, 'ignore_modifiers', False)
    source_fit = source_obj if ignore_modifiers else source_obj.evaluated_get(depsgraph)
    target_fit = target_obj if ignore_modifiers else target_obj.evaluated_get(depsgraph)
    if len(source_fit.data.polygons) == 0 or len(target_fit.data.polygons) == 0:
        logger.debug("Precision fit skipped: source or target mesh is empty")
        return None

    contact = np.array(contact_point, dtype=np.float64)
    source_data = _mesh_fit_data(source_fit)
    target_data = _mesh_fit_data(target_fit)
    source_seeds = _seed_polygons(source_data, source_snap_type, source_element_index)
    target_seeds = _seed_polygons(target_data, target_snap_type, target_element_index)
    if not source_seeds or not target_seeds:
        logger.debug("Precision fit skipped: snap element is stale or unsupported")
        return None
    source_patches = _candidate_patches(source_data, source_seeds)
    target_patches = _candidate_patches(target_data, target_seeds)
    source_pairs = _plane_pairs(source_patches, contact)
    target_pairs = _plane_pairs(target_patches, contact)
    matches = _match_plane_pairs(source_pairs, target_pairs, contact)
    translation = _solve_pair_translation(matches)
    if translation is None:
        logger.debug("Precision fit skipped: no unambiguous clearance pair")
        return None
    if not _validate_pair_translation(matches, translation):
        logger.debug("Precision fit skipped: proposed translation failed pair validation")
        return None
    return Vector(tuple(float(value) for value in translation))


# Two walls count as opposed only past this opening angle. A bare "their normals
# point away from each other at all" admits numerically-orthogonal neighbours, which
# are corners rather than connector walls.
_WALL_MIN_OPENING = math.radians(95.0)
_WALL_MAX_OPPOSED_DOT = math.cos(_WALL_MIN_OPENING)


def _connector_side_pairs(patches, anchor):
    """Describe clean opposed connector walls at the user's surface hit."""
    anchor = np.array(anchor, dtype=np.float64)
    pairs = []
    for index, first in enumerate(patches):
        for second in patches[index + 1:]:
            normal_dot = float(first['normal'] @ second['normal'])
            # Perpendicular walls are not opposed walls. On clean geometry their
            # dot is exactly zero and a bare `< 0` excludes them, but a wall with
            # any modelling noise lands either side of zero, so half of every
            # corner in the neighbourhood becomes a plausible pair on a 45-degree
            # axis. They crowd out the real walls and, because the search stops at
            # the first radius that yields any pair, they also stop it widening to
            # reach the far wall it was looking for.
            if normal_dot >= _WALL_MAX_OPPOSED_DOT:
                continue
            lateral = first['normal'] - second['normal']
            length = float(np.linalg.norm(lateral))
            if length <= 1e-12:
                continue
            lateral /= length
            dominant = int(np.argmax(np.abs(lateral)))
            if lateral[dominant] < 0:
                lateral *= -1.0

            crossings = []
            for patch in (first, second):
                denominator = float(patch['normal'] @ lateral)
                if abs(denominator) < 0.5:
                    crossings = []
                    break
                distance = float(patch['normal'] @ (patch['point'] - anchor)) / denominator
                crossings.append((distance, patch))
            if not crossings:
                continue
            crossings.sort(key=lambda item: item[0])
            (low_distance, low_patch), (high_distance, high_patch) = crossings
            tolerance = first['tolerance'] + second['tolerance']
            fit_tolerance = first['fit_tolerance'] + second['fit_tolerance']
            width = high_distance - low_distance
            if (
                first['area'] <= 0.0 or second['area'] <= 0.0
                or first['extent'] <= 0.0 or second['extent'] <= 0.0
                # Whether a wall separation is real is a question about precision,
                # not about patch size. The flatness allowance is 0.5% of a patch's
                # extent, so on a broad thin tab it exceeds the tab's own thickness
                # and throws away the one pair that matters -- the thin axis is
                # exactly the axis such a connector needs centred.
                or width <= fit_tolerance
                or low_distance > tolerance or high_distance < -tolerance
            ):
                continue
            if abs(low_distance) <= tolerance:
                anchor_side = 'low'
            elif abs(high_distance) <= tolerance:
                anchor_side = 'high'
            else:
                anchor_side = None
            depth_hint = first['normal'] + second['normal']
            depth_length = float(np.linalg.norm(depth_hint))
            if depth_length > 1e-12:
                depth_hint /= depth_length
            else:
                depth_hint = np.zeros(3, dtype=np.float64)
            pairs.append({
                'axis': lateral,
                'low_patch': low_patch,
                'high_patch': high_patch,
                'low': low_distance,
                'high': high_distance,
                'center': anchor + 0.5 * (low_distance + high_distance) * lateral,
                'anchor': anchor,
                'anchor_side': anchor_side,
                'width': width,
                'opening_angle': math.acos(np.clip(normal_dot, -1.0, 1.0)),
                'depth_hint': depth_hint,
                'tolerance': tolerance,
                'fit_tolerance': fit_tolerance,
            })
    return sorted(
        pairs,
        key=lambda pair: tuple(np.round(pair['axis'], 9))
        + (round(pair['opening_angle'], 9), round(pair['width'], 9)),
    )


def clicked_patch_centre(mesh_data, face_index):
    """World-space centre of the flat wall a click landed on.

    This is the patch's own area-weighted centroid, so it is the same point the
    solver already uses as that plane's reference -- centring on it moves the anchor
    within the plane, which leaves every measured wall width untouched and only
    settles where along the free axes the parts come to rest.

    Returns None when the click is not on a clean flat patch, which is exactly when
    centring would be a guess; the caller keeps the exact hit in that case.
    """
    if mesh_data is None:
        return None
    index = int(face_index)
    if index < 0 or index >= len(mesh_data['polygon_normals']):
        return None
    try:
        patch = _grow_planar_patch(mesh_data, index)
    except Exception:
        return None
    if patch is None:
        return None
    return Vector(tuple(float(value) for value in patch['point']))


# A plain box peg reaches its far wall in two patch hops. Every chamfer or fillet
# ring around an edge inserts another one, so a well-modelled connector puts its
# opposite wall out of reach and the click looks like it landed on nothing at all.
_CONNECTOR_MAX_HOPS = 10
# Hops are cheap to ask for and expensive to grow: each one pulls in a ring of new
# patches, and growing a patch across a dense flat wall is the single most expensive
# thing here. Bound the walk by how much it has already turned up rather than by
# radius alone, so a dense part cannot be made to grow half its mesh.
_CONNECTOR_MAX_PATCHES = 400
# Reaching across a fillet is not the same as mating against it. A bevel strip is a
# sliver next to the wall it softens, and a rounded edge makes a dozen of them, each
# forming plausible-looking opposed pairs on its own diagonal axis. They outnumber
# the real walls and crowd them out: the matcher discards a candidate whose two best
# targets tie, and near-identical bevel strips tie constantly. The click names the
# wall that matters, so anything far smaller than it is trim, not a connector wall.
_CONNECTOR_MIN_WALL_FRACTION = 0.1
# A flat-sided connector has a handful of opposed wall pairs; a rectangular one has
# three. A rounded click reaches the far side of the curve once the radius is wide
# enough and produces them by the thousand, which is both meaningless and quadratic
# in the matcher. Past this many, the click was not on a flat-sided connector.
_CONNECTOR_MAX_WALL_PAIRS = 32


def _merge_coplanar_patches(patches):
    """Collapse patches lying on one plane into a single logical wall.

    A wall that arrives triangulated, decimated or sculpted comes back as dozens of
    fragments whose normals differ by a fraction of a degree. The growth step will
    not merge them because its offset allowance scales with edge length, and a
    finely cut wall has tiny edges, so sub-millimetre wobble is enough to stop it.

    To the pairing rules those fragments are not a wall at all: the click lands on
    one of them, every neighbour faces the same way, and the opposite wall is
    hundreds of fragments away -- further than any affordable search. Grouping by
    plane restores the wall the modeller drew, and it is the plane that all the
    downstream geometry is actually about.

    Tolerances are recomputed from the merged wall: its residual is the real spread
    of its fragments about the plane, which is a better precision estimate than any
    single fragment could give.
    """
    if len(patches) < 2:
        return list(patches)
    points = np.array([patch['point'] for patch in patches], dtype=np.float64)
    span = float(np.linalg.norm(points.max(axis=0) - points.min(axis=0)))
    plane_tolerance = max(0.005 * span, _FIT_ABS_TOL)

    groups = []
    # Largest first, so a group's plane is anchored on its most reliable member.
    for patch in sorted(patches, key=lambda item: -float(item['area'])):
        for group in groups:
            if float(patch['normal'] @ group['normal']) < _FIT_COS_5:
                continue
            offset = float(group['normal'] @ (patch['point'] - group['point']))
            if abs(offset) > plane_tolerance:
                continue
            group['members'].append(patch)
            break
        else:
            groups.append({
                'normal': np.array(patch['normal'], dtype=np.float64),
                'point': np.array(patch['point'], dtype=np.float64),
                'members': [patch],
            })

    merged = []
    for group in groups:
        members = group['members']
        if len(members) == 1:
            merged.append(members[0])
            continue
        areas = np.array([float(item['area']) for item in members])
        total = float(areas.sum())
        if total <= 0.0:
            continue
        centres = np.array([item['point'] for item in members], dtype=np.float64)
        normals = np.array([item['normal'] for item in members], dtype=np.float64)
        point = (centres * areas[:, None]).sum(axis=0) / total
        normal = (normals * areas[:, None]).sum(axis=0)
        length = float(np.linalg.norm(normal))
        if length <= 1e-12:
            continue
        normal /= length
        spread = float(np.linalg.norm(centres.max(axis=0) - centres.min(axis=0)))
        extent = spread + max(float(item['extent']) for item in members)
        if extent <= 0.0:
            continue
        residual = float(np.max(np.abs((centres - point) @ normal)))
        polygons = set()
        for item in members:
            polygons |= set(item['polygons'])
        merged.append({
            'id': tuple(sorted(polygons)),
            'polygons': polygons,
            'point': point,
            'normal': normal,
            'area': total,
            'extent': extent,
            'residual': residual,
            'tolerance': max(0.005 * extent, _FIT_ABS_TOL),
            'fit_tolerance': max(residual, 1e-6 * extent, _FIT_ABS_TOL),
        })
    return sorted(merged, key=_patch_sort_key)


def _connector_walls(mesh_data, seeds, hops):
    """The logical walls near a click: patches reached, then merged per plane."""
    merged = _merge_coplanar_patches(_candidate_patches(mesh_data, seeds, hops))
    clicked = None
    if seeds:
        seed = int(seeds[0])
        for patch in merged:
            if seed in patch['polygons']:
                clicked = patch
                break
    return merged, clicked


def _connector_pairs(mesh_data, seeds, anchor, label='key'):
    """Opposed wall pairs at a click, widening the search only when it finds none.

    Returns `(pairs, reason)`; `reason` is a specific refusal when there is one to
    give, and None when the caller should describe the empty result itself.

    Widening costs patches quadratically, so stop at the first radius that sees any
    opposed pair: that is the tightest neighbourhood which still describes the
    connector, and it leaves plain connectors on exactly the patch set they had.
    Traversal still crosses the trim -- only pairing ignores it -- so a fillet stays
    a stepping stone to the far wall without becoming a wall itself.
    """
    # Ignoring trim is a preference, not a rule. A connector whose far wall really is
    # much smaller than the clicked one -- or whose clicked patch merged with a large
    # coplanar body face, inflating the floor -- would otherwise be refused outright
    # for the sake of a filter that exists only to keep bevel slivers out.
    searched = (2, 0, False)
    for fraction in (_CONNECTOR_MIN_WALL_FRACTION, 0.0):
        for hops in range(2, _CONNECTOR_MAX_HOPS + 1):
            reached, clicked = _connector_walls(mesh_data, seeds, hops)
            # Measured against the merged wall, not a fragment of it. A floor set by
            # one sliver of a cut-up wall admits every other sliver and means nothing.
            floor = fraction * (0.0 if clicked is None else float(clicked['area']))
            walls = [
                patch for patch in reached if float(patch['area']) >= floor
            ]
            # Record the floored pass only. The fallback runs afterwards and used to
            # overwrite this, so the refusal described a neighbourhood assembled
            # under different rules from the search that actually failed -- and
            # reported a budget that no longer constrains the pass being described.
            if fraction > 0.0:
                searched = (hops, len(reached), False)
            pairs = _connector_side_pairs(walls, anchor)
            if len(pairs) > _CONNECTOR_MAX_WALL_PAIRS:
                # Only the floored pass can call something a curve. The fallback
                # below re-admits every sliver, so its pair count measures how
                # finely the part is cut up, not how round it is -- claiming a
                # curve from that number would be a confident wrong answer.
                if fraction > 0.0:
                    return [], (
                        f"the {label} click is on a curved surface -- it offers"
                        f" {len(pairs)} opposed wall pairs where a flat-sided"
                        " connector has a handful, and rounded connectors are not"
                        " supported"
                    )
                break
            if pairs:
                return pairs, None
            # The patch budget guards the unfloored fallback, whose pairing is
            # quadratic in every sliver it re-admits. The floored pass only ever
            # pairs substantial walls -- a handful even on a part with thousands of
            # patches -- so budgeting it by total patch count stopped the walk long
            # before it could cross to the far wall, on exactly the dense parts that
            # need the reach most.
            if fraction <= 0.0 and len(reached) >= _CONNECTOR_MAX_PATCHES:
                break
        if fraction <= 0.0:
            break
    advice = (
        "click flat on a connector wall, not a rounded or angled face"
        if label == 'key' else "click flat on an inner wall of the socket"
    )
    return [], (
        f"no opposed wall pair at the {label} click -- {advice} ("
        + _describe_missing_wall_pair(mesh_data, seeds, anchor, searched, label)
        + ")"
    )


def _describe_missing_wall_pair(mesh_data, seeds, anchor, searched, label='key'):
    """Say what the click did find, so a refusal is diagnosable rather than flat.

    "No opposed wall pair" covers every way the search can come up empty, and the
    shapes that reach it are exactly the ones nobody can picture from a description.
    Counting where the candidates fell out turns the next report into evidence.

    `searched` is the radius the search actually reached, not the radius it is
    allowed. Describing the wider one reports geometry that was never considered,
    which reads as evidence and is not. Only ever runs on the failure path.
    """
    hops, _total, _unused = searched
    # Describe the merged walls, since those are what pairing was given. Counting
    # raw fragments would describe a neighbourhood the solver never saw.
    patches, clicked = _connector_walls(mesh_data, seeds, hops)
    if clicked is None:
        return "the clicked face is not part of a flat patch"
    anchor = np.array(anchor, dtype=np.float64)
    facing = skewed = behind = 0
    for patch in patches:
        if patch['id'] == clicked['id']:
            continue
        if float(patch['normal'] @ clicked['normal']) >= 0.0:
            continue
        facing += 1
        lateral = clicked['normal'] - patch['normal']
        length = float(np.linalg.norm(lateral))
        if length <= 1e-12:
            continue
        lateral /= length
        # Canonicalise exactly as _connector_side_pairs does, or the sign of the
        # crossing distance flips and this reports the opposite of what happened.
        dominant = int(np.argmax(np.abs(lateral)))
        if lateral[dominant] < 0:
            lateral *= -1.0
        denominator = float(patch['normal'] @ lateral)
        if abs(float(clicked['normal'] @ lateral)) < 0.5 or abs(denominator) < 0.5:
            skewed += 1
            continue
        clicked_denominator = float(clicked['normal'] @ lateral)
        near = float(
            clicked['normal'] @ (clicked['point'] - anchor)
        ) / clicked_denominator
        far = float(patch['normal'] @ (patch['point'] - anchor)) / denominator
        if min(near, far) > 0.0 or max(near, far) < 0.0:
            behind += 1
    substantial = sum(
        1 for patch in patches
        if float(patch['area']) >= _CONNECTOR_MIN_WALL_FRACTION
        * float(clicked['area'])
    )
    parts = [
        f"searched {hops} patch hops from the {label} click and reached"
        f" {len(patches)} flat patches, {substantial} of them a tenth the clicked"
        f" wall or bigger"
    ]
    if not facing:
        parts.append("none facing the clicked wall")
    else:
        parts.append(f"{facing} facing it")
        if skewed:
            parts.append(f"{skewed} at too shallow an angle")
        if behind:
            parts.append(f"{behind} not spanning the click")
    if hops >= _CONNECTOR_MAX_HOPS:
        parts.append(
            "the walk reached its full depth, so the facing wall is further from"
            " this click than the connector should be -- try clicking nearer the"
            " opening, or on the opposite wall"
        )
    # A flat wall broken into dozens of slivers by triangulation or a boolean reads
    # exactly like a curve to the pairing rules, and the two need different fixes.
    if len(patches) >= 12 and substantial <= 2:
        parts.append(
            "the wall may be fragmented rather than flat -- try Ignore modifiers, or"
            " merge coplanar faces on the connector"
        )
    return ", ".join(parts)


def _pair_is_female(pair):
    """True when the walls face each other (a socket), false when they face out (a peg).

    _connector_side_pairs only forms a pair when each wall's normal has at least a 0.5
    component along the lateral axis, so this sign is never marginal. It also survives
    _rotate_connector_pairs, which negates the axis and swaps the two walls together.
    """
    return float(pair['low_patch']['normal'] @ pair['axis']) > 0.0


def _pair_clearance(source, target):
    """Room the socket leaves around the peg, whichever half the user clicked first.

    Which part is the socket is a fact about the wall normals, not about click order.
    Some assemblies can only be built by moving the socket onto a fixed peg, and that
    describes the same seated result, so the mate must not depend on which half was
    picked as the mover. Returns None for two pegs or two sockets, which no rotation
    can ever seat.
    """
    source_female = _pair_is_female(source)
    if source_female == _pair_is_female(target):
        return None
    if source_female:
        return source['width'] - target['width']
    return target['width'] - source['width']


def _match_connector_pairs(source_pairs, target_pairs):
    """Match compatible male/female wall pairs without guessing through ambiguity."""
    angle_tolerance = math.radians(5.0)
    opposed_limit = math.cos(math.radians(170.0))
    matches = []
    for source in source_pairs:
        candidates = []
        for target in target_pairs:
            if float(source['axis'] @ target['axis']) < _FIT_COS_5:
                continue
            if abs(source['opening_angle'] - target['opening_angle']) > angle_tolerance:
                continue
            if float(source['low_patch']['normal'] @ target['low_patch']['normal']) > opposed_limit:
                continue
            if float(source['high_patch']['normal'] @ target['high_patch']['normal']) > opposed_limit:
                continue
            tolerance = source['tolerance'] + target['tolerance']
            # Judge clearance against how precisely the planes are defined. The
            # flatness tolerance scales with patch size and would demand roughly 2%
            # clearance on a 10-unit peg, rejecting realistic printed fits.
            clearance = _pair_clearance(source, target)
            if (
                clearance is None
                or clearance < -(source['fit_tolerance'] + target['fit_tolerance'])
            ):
                continue
            distance = float(np.linalg.norm(target['center'] - target['anchor']))
            candidates.append((distance, tolerance, target, clearance))
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[0])
        if (
            len(candidates) > 1
            and candidates[1][0] - candidates[0][0]
            <= candidates[0][1] + candidates[1][1]
        ):
            continue
        _, tolerance, target, clearance = candidates[0]
        matches.append({
            'axis': source['axis'],
            'source': source,
            'target': target,
            'clearance': clearance,
            'tolerance': tolerance,
        })

    return [
        match for index, match in enumerate(matches)
        if not any(
            index != other_index
            and abs(float(match['axis'] @ other['axis'])) >= _FIT_COS_5
            for other_index, other in enumerate(matches)
        )
    ]


def _fit_connector_rotation(correspondences):
    if len(correspondences) < 4:
        return None
    source = np.array([item[0] for item in correspondences], dtype=np.float64)
    target = np.array([item[1] for item in correspondences], dtype=np.float64)
    if (
        not np.isfinite(source).all() or not np.isfinite(target).all()
        or np.linalg.matrix_rank(source, tol=math.sin(math.radians(5.0))) < 2
    ):
        return None
    try:
        u, _, vh = np.linalg.svd(source.T @ target)
    except np.linalg.LinAlgError:
        return None
    rotation = vh.T @ u.T
    if np.linalg.det(rotation) < 0.0:
        vh[-1] *= -1.0
        rotation = vh.T @ u.T
    if (
        not np.isfinite(rotation).all()
        or abs(float(np.linalg.det(rotation)) - 1.0) > 1e-8
    ):
        return None
    residuals = np.clip(
        np.sum((source @ rotation.T) * target, axis=1), -1.0, 1.0
    )
    if float(np.min(residuals)) < _FIT_COS_5:
        return None
    return rotation


# Pair formation only requires the two walls to face away from each other at all,
# so numerically-orthogonal neighbours (90.000001 degrees) qualify. They are not
# opposed connector walls and they inflate the enumeration below quadratically.
_ROTATION_MIN_OPENING = _WALL_MIN_OPENING
# Above this many plausible pairs the connector is not the flat-sided kind this
# feature supports (a faceted round peg reaches dozens), and the enumeration is
# quadratic in each list. Fail closed rather than freeze the modal.
_ROTATION_MAX_PAIRS = 8


def _rotation_compatible(source, target):
    """Could this source/target mapping ever fit? Rotation-invariant tests only."""
    clearance = _pair_clearance(source, target)
    return (
        clearance is not None
        and abs(source['opening_angle'] - target['opening_angle']) <= math.radians(5.0)
        and clearance >= -(source['fit_tolerance'] + target['fit_tolerance'])
    )


def _rotation_axis_ambiguous(pairs):
    """True when one axis carries two pairs that would constrain it differently."""
    for index, first in enumerate(pairs):
        for second in pairs[index + 1:]:
            if abs(float(first['axis'] @ second['axis'])) < _FIT_COS_5:
                continue
            if (
                abs(first['opening_angle'] - second['opening_angle'])
                > math.radians(5.0)
                or float(
                    first['low_patch']['normal'] @ second['low_patch']['normal']
                ) < _FIT_COS_5
                or float(
                    first['high_patch']['normal'] @ second['high_patch']['normal']
                ) < _FIT_COS_5
            ):
                return True
    return False


def _prune_rotation_pairs(source_pairs, target_pairs, diagnostics=None):
    """Reduce both lists to pairs that could plausibly drive a rotation.

    Every test here is rotation-invariant, so pruning can never prefer one
    orientation over another. Returns None when the input is too ambiguous or too
    large to decide safely; rotation then fails closed, which is what the design
    asks for on round, noisy, and ambiguous connectors.
    """
    sources = [
        pair for pair in source_pairs
        if pair['opening_angle'] >= _ROTATION_MIN_OPENING
    ]
    targets = [
        pair for pair in target_pairs
        if pair['opening_angle'] >= _ROTATION_MIN_OPENING
    ]
    sources = [
        source for source in sources
        if any(_rotation_compatible(source, target) for target in targets)
    ]
    targets = [
        target for target in targets
        if any(_rotation_compatible(source, target) for source in sources)
    ]
    for label, pairs in (('key', sources), ('lock', targets)):
        if len(pairs) > _ROTATION_MAX_PAIRS:
            _note_lock_key_skip(
                diagnostics,
                f"the {label} offers {len(pairs)} candidate wall pairs and rotation"
                f" searches at most {_ROTATION_MAX_PAIRS} -- this is built for"
                " flat-sided connectors, and rounded ones reach dozens")
            return None
        if _rotation_axis_ambiguous(pairs):
            _note_lock_key_skip(
                diagnostics,
                f"two {label} wall pairs share an axis but would seat the mate"
                " differently -- click on one clean connector wall")
            return None
    return sources, targets


def _rotation_candidates(
        source_pairs, target_pairs, allow_mixed_anchor=False, diagnostics=None):
    """Enumerate compatible source/target wall mappings.

    `allow_mixed_anchor` pairs a wall click against a floor click. That mapping is
    only safe when the caller also supplies the target face normal, because nothing
    else constrains the insertion axis and an end-for-end flip otherwise satisfies
    every lateral test. The two travel together deliberately.
    """
    if len(source_pairs) < 2 or len(target_pairs) < 2:
        _note_lock_key_skip(
            diagnostics,
            "rotation needs two independent wall pairs on each part and found"
            f" {len(source_pairs)} on the key / {len(target_pairs)} on the lock --"
            " click flat on a connector wall rather than a rim or a rounded face")
        return []
    pruned = _prune_rotation_pairs(source_pairs, target_pairs, diagnostics)
    if pruned is None:
        return []
    source_pairs, target_pairs = pruned
    if len(source_pairs) < 2 or len(target_pairs) < 2:
        _note_lock_key_skip(
            diagnostics,
            "after discarding the wall pairs that can never fit, too few remain to"
            f" pin a rotation ({len(source_pairs)} key / {len(target_pairs)} lock)"
            " -- check that the two parts are the same scale")
        return []
    candidates = []
    # Combinations, not permutations: the target side already enumerates both
    # mappings, so (b,a)x(d,c) only repeats (a,b)x(c,d) and is discarded by the
    # dedup below -- after paying for its SVD.
    for sources in itertools.combinations(source_pairs, 2):
        if abs(float(sources[0]['axis'] @ sources[1]['axis'])) >= _FIT_COS_5:
            continue
        for targets in itertools.permutations(target_pairs, 2):
            if abs(float(targets[0]['axis'] @ targets[1]['axis'])) >= _FIT_COS_5:
                continue
            swap_options = []
            for source, target in zip(sources, targets):
                tolerance = source['fit_tolerance'] + target['fit_tolerance']
                clearance = _pair_clearance(source, target)
                if (
                    abs(source['opening_angle'] - target['opening_angle'])
                    > math.radians(5.0)
                    or clearance is None
                    or clearance < -tolerance
                    or (
                        not allow_mixed_anchor
                        and bool(source['anchor_side'])
                        != bool(target['anchor_side'])
                    )
                ):
                    break
                # Anchoring only pins the wall correspondence when BOTH clicks
                # landed on a wall. The documented target click is "inside the
                # lock", which may be its floor, so a mixed pairing enumerates both
                # mappings and leans on the insertion-axis guard to discard the
                # flipped one.
                if source['anchor_side'] and target['anchor_side']:
                    swap_options.append((
                        source['anchor_side'] != target['anchor_side'],
                    ))
                else:
                    swap_options.append((False, True))
            else:
                if not any(source['anchor_side'] for source in sources):
                    continue
                for swaps in itertools.product(*swap_options):
                    correspondences = []
                    for source, target, swap in zip(sources, targets, swaps):
                        target_low = (
                            target['high_patch'] if swap else target['low_patch']
                        )
                        target_high = (
                            target['low_patch'] if swap else target['high_patch']
                        )
                        correspondences.extend((
                            (source['low_patch']['normal'], -target_low['normal']),
                            (source['high_patch']['normal'], -target_high['normal']),
                        ))
                    rotation = _fit_connector_rotation(correspondences)
                    if rotation is None or any(
                        np.allclose(
                            rotation, item['rotation'], atol=1e-8, rtol=0.0
                        )
                        for item in candidates
                    ):
                        continue
                    candidates.append({'rotation': rotation})
    return candidates


def _rotate_connector_pairs(pairs, rotation):
    result = []
    for pair in pairs:
        rotated = dict(pair)
        rotated['anchor'] = rotation @ pair['anchor']
        rotated['center'] = rotation @ pair['center']
        rotated['axis'] = rotation @ pair['axis']
        rotated['depth_hint'] = rotation @ pair['depth_hint']
        rotated['low_patch'] = dict(pair['low_patch'])
        rotated['high_patch'] = dict(pair['high_patch'])
        for name in ('low_patch', 'high_patch'):
            rotated[name]['point'] = rotation @ pair[name]['point']
            rotated[name]['normal'] = rotation @ pair[name]['normal']
        dominant = int(np.argmax(np.abs(rotated['axis'])))
        if rotated['axis'][dominant] < 0.0:
            rotated['axis'] *= -1.0
            rotated['low_patch'], rotated['high_patch'] = (
                rotated['high_patch'], rotated['low_patch']
            )
            rotated['low'], rotated['high'] = -pair['high'], -pair['low']
            if pair['anchor_side'] == 'low':
                rotated['anchor_side'] = 'high'
            elif pair['anchor_side'] == 'high':
                rotated['anchor_side'] = 'low'
        result.append(rotated)
    return result


def _connector_gaps(match, translation):
    source = match['source']
    target = match['target']
    low_normal = target['low_patch']['normal']
    high_normal = target['high_patch']['normal']
    low_gap = float(
        low_normal @ (
            source['low_patch']['point'] + translation - target['low_patch']['point']
        )
    )
    high_gap = float(
        high_normal @ (
            source['high_patch']['point'] + translation - target['high_patch']['point']
        )
    )
    return low_gap, high_gap


def _solve_lock_key_translation(matches, source_hit, target_hit):
    if not matches:
        return None
    coarse = np.array(target_hit, dtype=np.float64) - np.array(source_hit, dtype=np.float64)
    rows = []
    right_hand_side = []
    for match in matches:
        low_gap, high_gap = _connector_gaps(match, coarse)
        rows.append(
            match['target']['low_patch']['normal']
            - match['target']['high_patch']['normal']
        )
        right_hand_side.append(-(low_gap - high_gap))
    rows = np.array(rows, dtype=np.float64)
    right_hand_side = np.array(right_hand_side, dtype=np.float64)
    try:
        correction = np.linalg.lstsq(rows, right_hand_side, rcond=0.1)[0]
        _, singular, vh = np.linalg.svd(rows, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    if len(singular) == 0 or singular[0] <= 0.0:
        return None
    basis = vh[singular >= 0.1 * singular[0]]
    if len(basis) == 0:
        return None
    correction = basis.T @ (basis @ correction)
    translation = coarse + correction
    if not np.isfinite(translation).all():
        return None
    return translation


def _validate_lock_key_transform(matches, translation):
    translation = np.array(translation, dtype=np.float64)
    if not np.isfinite(translation).all():
        return False
    for match in matches:
        low_gap, high_gap = _connector_gaps(match, translation)
        tolerance = match['tolerance']
        if low_gap < -tolerance or high_gap < -tolerance:
            return False
        if abs(low_gap - high_gap) > tolerance:
            return False
        coarse = match['target']['anchor'] - match['source']['anchor']
        correction = translation - coarse
        # Guard against relocating the part, not against using its slack: a snug fit
        # has no slack, yet its seated position is the most determined of all, and
        # a cap of 2*clearance would collapse to zero and reject it. Over-sliding is
        # already caught by the gap checks above.
        cap = 0.25 * match['source']['width'] + tolerance
        if abs(float(match['axis'] @ correction)) > cap:
            return False
    return True


def _buries_key_behind_target(peg_pairs, peg_offset, face_point, face_normal):
    """True when a candidate seats the peg behind the socket face that was clicked.

    Clearance validation only constrains the matched lateral axes; the insertion
    axis is left free. Without this, a rigid candidate can rotate the key end for
    end and sink it through the floor of the socket while every lateral test still
    passes. The clicked socket face normal points out of its material, so every
    part of the mated peg has to stay on that side of it.

    Either half may be the one that moves, so the caller passes whichever pairs
    belong to the peg plus the offset that lands them in their final place, and the
    socket's clicked face expressed in that same final frame. Reading the half-space
    off the peg's own click instead would reject every honest mate: the socket wall
    on the far side of the peg legitimately sits behind that plane.
    """
    if face_normal is None:
        return False
    normal = np.array(face_normal, dtype=np.float64)
    length = float(np.linalg.norm(normal))
    if length <= 1e-12:
        return False
    normal /= length
    anchor = np.array(face_point, dtype=np.float64)
    offset = np.array(peg_offset, dtype=np.float64)
    for pair in peg_pairs:
        tolerance = pair['tolerance']
        for name in ('low_patch', 'high_patch'):
            point = pair[name]['point'] + offset
            if float(normal @ (point - anchor)) < -tolerance:
                return True
    return False


def _connector_placement_signature(matches, translation):
    """Where a candidate actually leaves the mated walls, as a set of world planes.

    Two candidates are geometrically equivalent only when they seat the mated walls
    identically -- that is what makes a symmetric connector's alternative solutions
    interchangeable, and it is the only case where the design allows preferring the
    smaller rotation. Anything else is a different seating and must fail closed.
    """
    planes = []
    for match in matches:
        source = match['source']
        for name in ('low_patch', 'high_patch'):
            patch = source[name]
            normal = patch['normal']
            point = patch['point'] + translation
            planes.append(
                tuple(np.round(normal, 6).tolist())
                + (round(float(normal @ point), 6),)
            )
    return tuple(sorted(planes))


def _orientation_compatible_pairs(source_pairs, target_pairs):
    """Every wall pairing already facing the right way, ignoring size.

    Separates "the key is not rotated into place" from "the parts do not fit":
    rotation can fix orientation, and can never fix missing clearance. Only the
    orientation filters from _match_connector_pairs are applied here.
    """
    opposed_limit = math.cos(math.radians(170.0))
    facing = []
    for source in source_pairs:
        for target in target_pairs:
            if float(source['axis'] @ target['axis']) < _FIT_COS_5:
                continue
            if float(
                source['low_patch']['normal'] @ target['low_patch']['normal']
            ) > opposed_limit:
                continue
            if float(
                source['high_patch']['normal'] @ target['high_patch']['normal']
            ) > opposed_limit:
                continue
            facing.append((source, target))
    return facing


def lock_key_diagnostic_report(mesh_data, face_index, anchor, label):
    """Every geometric fact behind a refused mate, as lines for the console.

    A refusal has one line of room in the status bar, and the shapes that reach it
    cannot be pictured from one line -- several rounds of this feature were
    diagnosed from summaries that turned out to describe the wrong thing. Writing
    the full picture on every refusal costs nothing on the success path and means
    a report never has to be reproduced by hand.
    """
    lines = []

    def say(message):
        lines.append(f"    {message}")

    lines.append(f"  {label}:")
    if mesh_data is None:
        say("no mesh data (object missing, not a mesh, or extraction failed)")
        return lines
    index = int(face_index)
    if index < 0 or index >= len(mesh_data['polygon_normals']):
        say(f"face {index} is out of range; the mesh changed since the click")
        return lines

    seeds = _seed_polygons(mesh_data, 'FACES', index)
    anchor = np.array(anchor, dtype=np.float64)
    say(f"clicked face {index}, anchor "
        f"{tuple(round(float(value), 5) for value in anchor)}")
    try:
        raw = _candidate_patches(mesh_data, seeds, _CONNECTOR_MAX_HOPS)
        walls, clicked = _connector_walls(mesh_data, seeds, _CONNECTOR_MAX_HOPS)
    except Exception as error:
        say(f"patch extraction failed: {error}")
        return lines
    say(f"at full depth: {len(raw)} raw patches -> {len(walls)} merged walls")
    if clicked is None:
        say("the clicked face did not land in any merged wall")
        return lines
    say(f"clicked wall: area {clicked['area']:.6f} extent {clicked['extent']:.6f}"
        f" normal {tuple(round(float(v), 4) for v in clicked['normal'])}")

    facing = [
        wall for wall in walls
        if wall['id'] != clicked['id']
        and float(wall['normal'] @ clicked['normal']) < 0.0
    ]
    opposed = [
        wall for wall in facing
        if float(wall['normal'] @ clicked['normal']) < _WALL_MAX_OPPOSED_DOT
    ]
    say(f"{len(facing)} wall(s) face it at all, {len(opposed)} past the"
        f" {math.degrees(_WALL_MIN_OPENING):.0f}-degree bar")
    for wall in sorted(facing, key=lambda item: -float(item['area']))[:6]:
        opening = math.degrees(math.acos(
            float(np.clip(wall['normal'] @ clicked['normal'], -1.0, 1.0))
        ))
        separation = abs(float(
            clicked['normal'] @ (wall['point'] - clicked['point'])
        ))
        say(f"    facing wall area {wall['area']:10.5f} opening {opening:7.2f}deg"
            f" separation {separation:.6f}")
    say("largest walls in reach:")
    for wall in sorted(walls, key=lambda item: -float(item['area']))[:6]:
        say(f"    area {wall['area']:10.5f}"
            f" normal {tuple(round(float(v), 4) for v in wall['normal'])}")

    pairs, reason = _connector_pairs(mesh_data, seeds, anchor, label.lower())
    say(f"opposed wall pairs: {len(pairs)}")
    for pair in pairs[:6]:
        say(f"    axis {tuple(round(float(v), 4) for v in pair['axis'])}"
            f" width {pair['width']:.6f}"
            f" opening {math.degrees(pair['opening_angle']):.2f}deg"
            f" anchor_side {pair['anchor_side']}")
    if reason:
        say(f"refused: {reason}")
    return lines


def _note_lock_key_skip(diagnostics, message):
    """Record why a mate was refused.

    One generic 'no safe connector match found' covers eight distinct causes, which
    tells the user nothing about what to do differently. The caller surfaces this.
    """
    logger.debug(f"Lock and key skipped: {message}")
    if diagnostics is not None:
        diagnostics.append(message)


def compute_lock_key_transform(
        context, settings,
        source_object_name, source_face_index, source_hit,
        target_object_name, target_face_index, target_hit,
        allow_rotation=False,
        source_mesh_data=None, target_mesh_data=None,
        source_normal=None, target_normal=None,
        diagnostics=None):
    """Return one safe world delta for a two-surface-click connector mate.

    The caller may hand in already-extracted mesh data; extraction dominates the
    cost on dense meshes and the operator has usually paid for it already.
    """
    source_obj = bpy.data.objects.get(source_object_name)
    target_obj = bpy.data.objects.get(target_object_name)
    if (
        source_obj is None or target_obj is None
        or source_obj.type != 'MESH' or target_obj.type != 'MESH'
    ):
        _note_lock_key_skip(diagnostics, "source or target is not a mesh object")
        return None
    if (
        abs(source_obj.matrix_world.to_3x3().determinant()) <= 1e-12
        or abs(target_obj.matrix_world.to_3x3().determinant()) <= 1e-12
    ):
        _note_lock_key_skip(diagnostics, "source or target has a flattened (singular) transform")
        return None
    depsgraph = context.evaluated_depsgraph_get()
    ignore_modifiers = getattr(settings, 'ignore_modifiers', False)
    source_fit = source_obj if ignore_modifiers else source_obj.evaluated_get(depsgraph)
    target_fit = target_obj if ignore_modifiers else target_obj.evaluated_get(depsgraph)
    source_data = (
        _mesh_fit_data(source_fit) if source_mesh_data is None else source_mesh_data
    )
    target_data = (
        _mesh_fit_data(target_fit) if target_mesh_data is None else target_mesh_data
    )
    source_seeds = _seed_polygons(source_data, 'FACES', source_face_index)
    target_seeds = _seed_polygons(target_data, 'FACES', target_face_index)
    if not source_seeds or not target_seeds:
        _note_lock_key_skip(diagnostics, "the clicked face no longer exists; pick again")
        return None
    source_anchor = np.array(source_hit, dtype=np.float64)
    target_anchor = np.array(target_hit, dtype=np.float64)
    source_pairs, source_reason = _connector_pairs(
        source_data, source_seeds, source_anchor, 'key'
    )
    target_pairs, target_reason = _connector_pairs(
        target_data, target_seeds, target_anchor, 'lock'
    )
    matches = _match_connector_pairs(source_pairs, target_pairs)
    translation = _solve_lock_key_translation(matches, source_anchor, target_anchor)
    if translation is not None and _validate_lock_key_transform(matches, translation):
        return mathutils.Matrix.Translation(
            Vector(tuple(float(value) for value in translation))
        )
    if not allow_rotation:
        if not source_pairs:
            _note_lock_key_skip(diagnostics, source_reason)
        elif not target_pairs:
            _note_lock_key_skip(diagnostics, target_reason)
        elif not matches:
            # Matching needs the walls anti-parallel within 10 degrees and the
            # lateral axes aligned within 5, so a key that is not already rotated
            # into place can never match however well the parts actually fit.
            # Distinguish that from parts that face each other but do not fit.
            facing = _orientation_compatible_pairs(source_pairs, target_pairs)
            if not facing:
                _note_lock_key_skip(
                    diagnostics,
                    "the key is not aligned with the lock -- turn on 'Rotate key to"
                    " match lock', or rotate the key roughly into place first"
                    f" ({len(source_pairs)} key / {len(target_pairs)} lock wall"
                    " pairs, none facing each other)")
            else:
                # Report the near-miss that came closest to fitting, with both
                # measurements: "wider than" alone leaves the user unable to tell a
                # scale mistake from a taper mismatch or a wrongly-grown patch.
                _, peg, socket = max(
                    (
                        (_pair_clearance(source, target) or 0.0,)
                        + ((target, source) if _pair_is_female(source)
                           else (source, target))
                        for source, target in facing
                    ),
                    key=lambda item: item[0],
                )
                _note_lock_key_skip(
                    diagnostics,
                    "the key does not fit inside the lock -- the peg measures"
                    f" {peg['width']:.4g} across where the socket measures"
                    f" {socket['width']:.4g}, or their tapers differ"
                    f" ({len(source_pairs)} key / {len(target_pairs)} lock"
                    " wall pairs)")
        else:
            _note_lock_key_skip(
                diagnostics,
                f"{len(matches)} matched wall pair(s) could not be centred within"
                " tolerance -- the two clicks may be too far apart, or enable"
                " 'Rotate key to match lock'")
        return None

    valid = []
    allow_mixed_anchor = target_normal is not None
    explained = 0 if diagnostics is None else len(diagnostics)
    candidates = _rotation_candidates(
        source_pairs, target_pairs, allow_mixed_anchor=allow_mixed_anchor,
        diagnostics=diagnostics,
    )
    for candidate in candidates:
        rotation = candidate['rotation']
        rotated_pairs = _rotate_connector_pairs(source_pairs, rotation)
        rotated_anchor = rotation @ source_anchor
        rotated_matches = _match_connector_pairs(rotated_pairs, target_pairs)
        if len(rotated_matches) < 2:
            continue
        axes = np.array([match['axis'] for match in rotated_matches])
        if np.linalg.matrix_rank(axes, tol=math.sin(math.radians(5.0))) < 2:
            continue
        rotated_translation = _solve_lock_key_translation(
            rotated_matches, rotated_anchor, target_anchor
        )
        if rotated_translation is None or not _validate_lock_key_transform(
            rotated_matches, rotated_translation
        ):
            continue
        # The insertion-axis guard reads the half-space off the socket's clicked
        # face, so which half is the socket decides which click it reads and which
        # pairs it tests. The matcher has already agreed on the roles by this point.
        if _pair_is_female(rotated_matches[0]['source']):
            socket_normal = (
                None if source_normal is None
                else rotation @ np.array(source_normal, dtype=np.float64)
            )
            if socket_normal is None and allow_mixed_anchor:
                # Mixed anchors put the end-for-end flip back on the table, and only
                # the socket's own click can discard it. Fail closed rather than seat
                # a candidate that nothing constrained.
                continue
            buried = _buries_key_behind_target(
                target_pairs, np.zeros(3),
                rotated_anchor + rotated_translation, socket_normal,
            )
        else:
            buried = _buries_key_behind_target(
                rotated_pairs, rotated_translation,
                target_anchor, target_normal,
            )
        if buried:
            continue
        rotation_matrix = mathutils.Matrix.Identity(4)
        for row in range(3):
            for column in range(3):
                rotation_matrix[row][column] = float(rotation[row, column])
        delta = mathutils.Matrix.Translation(
            Vector(tuple(float(value) for value in rotated_translation))
        ) @ rotation_matrix
        angle = delta.to_quaternion().angle
        if not any(
            np.allclose(
                np.array(delta), np.array(item[1]), atol=1e-7, rtol=0.0
            )
            for item in valid
        ):
            valid.append((
                angle, delta,
                _connector_placement_signature(
                    rotated_matches, rotated_translation
                ),
            ))
    if not valid:
        # Only fall back to the generic seating message when the enumeration has not
        # already said something more useful -- the caller surfaces the last note, so
        # appending here would bury "this connector has too many walls to search".
        if diagnostics is None or len(diagnostics) == explained:
            _note_lock_key_skip(
                diagnostics,
                "no rotation seats the key without penetrating the lock")
        return None
    # Smallest-angle ranking is only legitimate between candidates that seat the
    # mated walls identically. Candidates that seat them differently are a genuine
    # ambiguity, and preferring the nearer one would silently pick an orientation
    # the geometry never justified.
    if len({item[2] for item in valid}) > 1:
        _note_lock_key_skip(diagnostics, "several rotations fit differently; too ambiguous to choose")
        return None
    valid.sort(key=lambda item: item[0])
    return valid[0][1]


def get_axis_target(origin, target, axis_constraint, obj=None):
    """
    Returns the snapping target taking into account constrain options
    if obj is not None the constraint will be calculated in object space.
    """
    if len(axis_constraint) == 0:
        return target
    if obj is None:
        world_matrix = mathutils.Matrix.Identity(4)
    else:
        world_matrix = obj.matrix_world.to_quaternion()

    # Axis constraint
    if len(axis_constraint) == 1:
        if axis_constraint == 'X':
            point2 = origin + world_matrix @ Vector((1, 0, 0))
        elif axis_constraint == 'Y':
            point2 = origin + world_matrix @ Vector((0, 1, 0))
        else:
            point2 = origin + world_matrix @ Vector((0, 0, 1))
        return mathutils.geometry.intersect_point_line(target, origin, point2)[0]

    # Planar constraint
    if len(axis_constraint) == 2:
        if axis_constraint == 'XY':
            point2 = origin + world_matrix @ Vector((1, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 1, 0))
        elif axis_constraint == 'YZ':
            point2 = origin + world_matrix @ Vector((0, 1, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1))
        else:
            point2 = origin + world_matrix @ Vector((1, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1))

        normal = mathutils.geometry.normal(origin, point2, point3)
        if not normal.dot(origin - target) > 0:  # flip normal if it is pointing the wrong direction
            normal = -1 * normal
        new_target = mathutils.geometry.intersect_ray_tri(origin, point2, point3, normal, target, False)
        return new_target


def get_target_free(origin, camera_position, camera_vector, snapping, obj=None, is_ortho=False):
    """
    Get the target position if there is no target point, taking constraint into consideration.
    If obj is not None the constraint will be calculated in object space.
    """
    camera_point_b = camera_position + camera_vector

    # If no constraint target will be the intersection between the mouse ray and the plane perpendicular to camera
    # at origin position
    if len(snapping) == 0:
        return mathutils.geometry.intersect_line_plane(camera_position, camera_point_b, origin, camera_vector * -1)
    if obj is None:
        world_matrix = mathutils.Matrix.Identity(4)
    else:
        world_matrix = obj.matrix_world.to_quaternion()

    # Axis constraint
    if len(snapping) == 1:
        if snapping == 'X':
            offset_vector = Vector((1, 0, 0))
        elif snapping == 'Y':
            offset_vector = Vector((0, 1, 0))
        else:
            offset_vector = Vector((0, 0, 1))

        if abs(camera_vector.normalized().dot(offset_vector)) == 1:
            return origin

        point2 = origin + world_matrix @ offset_vector
        result = mathutils.geometry.intersect_line_line(camera_position, camera_point_b, origin, point2)
        if result is None:
            return origin
        return result[1]

    # Planar constraint
    if len(snapping) == 2:
        if snapping == 'XY':
            axis_vector = Vector((0, 0, 1))
            point2 = origin + world_matrix @ Vector((1000, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 1000, 0))
        elif snapping == 'YZ':
            axis_vector = Vector((1, 0, 0))
            point2 = origin + world_matrix @ Vector((0, 1000, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1000))
        else:
            axis_vector = Vector((0, 1, 0))
            point2 = origin + world_matrix @ Vector((1000, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1000))

        if is_ortho and camera_vector.normalized().dot(axis_vector) != 1:
            return origin

        normal = mathutils.geometry.normal(origin, point2, point3)
        new_target = mathutils.geometry.intersect_line_plane(camera_position, camera_point_b, origin, normal, False)
        if new_target is None:
            return origin
        return new_target


def display_keymap(kmi, layout):
    """
    Display keymap in UILayout
    """
    layout.emboss = 'NORMAL'
    if kmi is None:
        return
    map_type = kmi.map_type

    row = layout.row()
    row.prop(kmi, "active", text="", emboss=False)
    row.alignment = 'EXPAND'
    label_container = row.row().row()
    label_container.alignment = 'LEFT'
    label_container.emboss = 'NONE'
    label_container.enabled = False
    label_container.operator(kmi.idname, text=kmi.name)

    split = row.split()
    row = split.row()
    row.alignment = 'RIGHT'
    insert_prop_with_width(kmi, "map_type", row, text="", size=5)
    if map_type == 'KEYBOARD':
        insert_prop_with_width(kmi, "type", row, text="", size=8, full_event=True)
    elif map_type == 'MOUSE':
        insert_prop_with_width(kmi, "type", row, text="", size=8, full_event=True)
    elif map_type == 'NDOF':
        insert_prop_with_width(kmi, "type", row, text="", size=8, full_event=True)
    elif map_type == 'TWEAK':
        subrow = row.row()
        insert_prop_with_width(kmi, "type", subrow, text="", size=4)
        insert_prop_with_width(kmi, "value", subrow, text="", size=4)
    elif map_type == 'TIMER':
        insert_prop_with_width(kmi, "type", row, text="", size=8)
    else:
        insert_prop_with_width(kmi, "type", row, text="", size=8)


def insert_prop_with_width(property_object, property_name, layout, align='CENTER', text=None, icon='NONE',
                           expand=False, slider=False, icon_only=False, toggle=False, size=5, enabled=True,
                           full_event=False):
    """
    Insert UILayout prop with a fixed width
    """
    ui_container = layout.row()
    ui_container.alignment = align
    ui_container.ui_units_x = size
    if not enabled:
        ui_container.enabled = False
    ui_container.prop(property_object, property_name, icon=icon, toggle=toggle, text=text, expand=expand, slider=slider,
                      icon_only=icon_only, full_event=full_event)


icons_list = bpy.types.UILayout.bl_rna.functions[
            "prop"].parameters["icon"].enum_items.keys()


def insert_ui_hotkey(container, key, description, control=False, shift=False, alt=False):
    """
    Insert UI hotkey information: KeyMap icons + description
    """
    line = container.row(align=True)
    container_description = line.split(factor=0.39)
    row = container_description.row(align=True)
    row.alignment = 'RIGHT'


    if alt:
        row.label(text="", icon="EVENT_ALT")
    if control:
        row.label(text="", icon="EVENT_CTRL")
    if shift:
        row.label(text="", icon="EVENT_SHIFT")

    if key == "EVENT_RIGHTMOUSE":
        key = "MOUSE_RMB"
    elif key == "EVENT_LEFTMOUSE":
        key = "MOUSE_LMB"
    elif key == "EVENT_MIDDLEMOUSE":
        key = "MOUSE_MMB"
        
    if key in icons_list:
        row.label(text="", icon=key)
    else:
        row.label(text=f"[{key.replace('EVENT_','')}]")
    container_description.label(text=description)


def flatten(nested_list):
    """
    Flattens nested lists
    """
    return [item for sublist in nested_list for item in sublist]


def translate_curvepoints_worldspace(obj, backup_data, translation):
    """
    Apply translation to curve points
    """
    curve_data = obj.data
    for (curve_index, index, co, bezier, left, right) in backup_data:
        if bezier:
            curve_data.splines[curve_index].bezier_points[index].co = translation @ co.copy()
            curve_data.splines[curve_index].bezier_points[index].handle_left = translation @ left.copy()
            curve_data.splines[curve_index].bezier_points[index].handle_right = translation @ right.copy()
        else:
            original_point = Vector((co[0], co[1], co[2]))
            target_position = translation @ original_point
            curve_data.splines[curve_index].points[index].co = (target_position[0],
                                                                target_position[1],
                                                                target_position[2],
                                                                0)
    pass


def has_points_selected(selected_meshes):
    """
    Returns True if any point of the selected meshes is selected.
    """

    for obj_name in selected_meshes:
        obj = bpy.data.objects[obj_name]
        data = obj.data
        if obj.type == 'MESH':
            if data.total_vert_sel>0:
                return True
        elif obj.type == 'CURVE':
            for spline in data.splines:
                for point in spline.bezier_points:
                    if point.select_control_point:
                        return True
                for point in spline.points:
                    if point.select:
                        return True
    return False


mouse_pointer_offsets = [
    Vector((-40, -40)),
    Vector((-40, 0)),
    Vector((-40, 40)),
    Vector((0, 40)),
    Vector((40, 40)),
    Vector((40, 0)),
    Vector((40, -40)),
    Vector((0, -40))
]


def check_close_objects(context, region, depsgraph, mouse_position):
    """
    Cast 8 rays around the mouse, returns the hit objects.
    """
    mouse_position = Vector(mouse_position)
    points = [mouse_position]
    points.extend([mouse_position + point for point in mouse_pointer_offsets])
    hit_objects = []
    # logger.info(f"check_close_objects: {points}")
    for point in points:
        if region.data.view_perspective == 'CAMERA' and not region.data.is_perspective:
            depth_location = context.space_data.camera.location
            view_position = view3d_utils.region_2d_to_location_3d(region, region.data, point,
                                                                  depth_location)
        else:
            view_position = view3d_utils.region_2d_to_origin_3d(region, region.data, point)
        # view_position = view3d_utils.region_2d_to_origin_3d(region, context.space_data.region_3d, point)
        mouse_vector = view3d_utils.region_2d_to_vector_3d(region, context.space_data.region_3d, point)
        (hit, _, _, _, obj, *_) = context.scene.ray_cast(depsgraph, origin=view_position,
                                                         direction=mouse_vector)
        if hit:
            hit_objects.append(obj)
    # logger.info(f"hit_objects: {hit_objects}")
    return hit_objects


def set_select_all_points(object_names, selected=False):
    for obj_name in object_names:
        obj = bpy.data.objects[obj_name]
        if obj.type == 'MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
            obj.data.polygons.foreach_set('select', np.full(len(obj.data.polygons), selected))
            obj.data.edges.foreach_set('select', np.full(len(obj.data.edges), selected))
            obj.data.vertices.foreach_set('select', np.full(len(obj.data.vertices), selected))
            bpy.ops.object.mode_set(mode='EDIT')
            pass
        elif obj.type == 'CURVE':
            for spline in obj.data.splines:
                spline.points.foreach_set('select', np.full(len(spline.points), selected))
                spline.bezier_points.foreach_set('select_control_point', np.full(len(spline.bezier_points), selected))
            pass



