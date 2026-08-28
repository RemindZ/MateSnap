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
_FIT_ANGLE_5 = 5.0
_FIT_ABS_TOL = 1e-7


# Extraction dominates every mate on dense parts, and the same unmoved base was
# re-extracted for mate after mate -- 6.6s per click on a 5.5M-polygon figure.
# The topology and local geometry are cached across runs and revalidated
# bit-for-bit against the live mesh: coordinates and loop connectivity are
# re-read and compared, so an edit that keeps every element count (sculpting
# does) still invalidates. Never trusted without that comparison. World-space
# products are rebuilt per call, so a moved object reuses its topology at only
# the transform cost.
# ponytail: keeps the last three meshes (~150MB per million polygons); raise the
# limit if kits routinely juggle more parts than that.
_EXTRACTION_CACHE = {}
_EXTRACTION_CACHE_LIMIT = 3


def _local_mesh_data(obj):
    mesh = obj.data
    key = (obj.name, bool(getattr(obj, 'is_evaluated', False)))
    counts = (
        len(mesh.vertices), len(mesh.edges), len(mesh.polygons), len(mesh.loops)
    )
    vertex_count, edge_count, polygon_count, loop_count = counts

    vertices = np.empty(vertex_count * 3, dtype=np.float64)
    mesh.vertices.foreach_get('co', vertices)
    vertices.shape = (vertex_count, 3)
    loop_vertices = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get('vertex_index', loop_vertices)

    cached = _EXTRACTION_CACHE.get(key)
    if (
        cached is not None
        and cached['counts'] == counts
        and np.array_equal(cached['vertices'], vertices)
        and np.array_equal(cached['loop_vertices'], loop_vertices)
    ):
        _EXTRACTION_CACHE.pop(key)
        _EXTRACTION_CACHE[key] = cached
        return cached

    loop_edges = np.empty(loop_count, dtype=np.int32)
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
    edge_vertices = np.empty(edge_count * 2, dtype=np.int32)
    mesh.edges.foreach_get('vertices', edge_vertices)
    edge_vertices.shape = (edge_count, 2)

    loop_polygons = np.repeat(np.arange(polygon_count, dtype=np.int32), loop_totals)
    edge_order = np.argsort(loop_edges, kind='stable')
    edge_counts = np.bincount(loop_edges, minlength=edge_count)
    edge_starts = np.concatenate(([0], np.cumsum(edge_counts)))

    local = {
        'counts': counts,
        'vertices': vertices,
        'loop_vertices': loop_vertices,
        'loop_edges': loop_edges,
        'loop_starts': loop_starts,
        'loop_totals': loop_totals,
        'loop_polygons': loop_polygons,
        'centers': centers,
        'normals': normals,
        'edge_vertices': edge_vertices,
        'edge_polygons': loop_polygons[edge_order],
        'edge_starts': edge_starts,
    }
    _EXTRACTION_CACHE.pop(key, None)
    _EXTRACTION_CACHE[key] = local
    while len(_EXTRACTION_CACHE) > _EXTRACTION_CACHE_LIMIT:
        _EXTRACTION_CACHE.pop(next(iter(_EXTRACTION_CACHE)))
    return local


def _mesh_fit_data(obj):
    local = _local_mesh_data(obj)
    matrix = np.array(obj.matrix_world, dtype=np.float64)
    # An unmoved object -- the base a kit assembles onto, mate after mate --
    # reuses its whole world-space product, grown patches included: those are
    # deterministic in this data, so unchanged input means unchanged patches.
    matrix_key = matrix.tobytes()
    cached_world = local.get('world')
    if cached_world is not None and cached_world[0] == matrix_key:
        return cached_world[1]
    inverse = np.array(obj.matrix_world.inverted(), dtype=np.float64)
    # New arrays throughout -- the cached local geometry is never written to.
    vertices = local['vertices'] @ matrix[:3, :3].T + matrix[:3, 3]
    centers = local['centers'] @ matrix[:3, :3].T + matrix[:3, 3]
    normals = local['normals'] @ inverse[:3, :3]
    lengths = np.linalg.norm(normals, axis=1)
    lengths[lengths == 0] = 1.0
    normals /= lengths[:, None]
    edge_vertices = local['edge_vertices']
    edge_lengths = np.linalg.norm(
        vertices[edge_vertices[:, 0]] - vertices[edge_vertices[:, 1]], axis=1
    )

    world = {
        'vertices': vertices,
        'loop_vertices': local['loop_vertices'],
        'loop_edges': local['loop_edges'],
        'loop_starts': local['loop_starts'],
        'loop_totals': local['loop_totals'],
        'loop_polygons': local['loop_polygons'],
        'polygon_centers': centers,
        'polygon_normals': normals,
        'edge_lengths': edge_lengths,
        'edge_polygons': local['edge_polygons'],
        'edge_starts': local['edge_starts'],
        'polygon_geometry': {},
        'polygon_patches': {},
    }
    local['world'] = (matrix_key, world)
    return world


class LockKeyRegionTooSmall(Exception):
    """A patch or search reached the edge of a region extraction.

    Every measurement the solver reads -- areas, extents, centroids, reach --
    must come from whole patches, so the moment anything touches the region rim
    the region is too small to answer honestly. Carries the provider so the
    caller can widen and retry.
    """

    def __init__(self, provider):
        super().__init__("lock-key region too small")
        self.provider = provider


def _lock_key_bulk(obj):
    """The bulk reads a lock-key extraction needs, cached and revalidated.

    Everything here is position-independent, so it survives the object moving.
    Lock and key never seeds from edges, so Blender's edge tables -- the single
    most expensive reads -- are not fetched at all; edge connectivity is
    derived from the corner table when a region is built.
    """
    mesh = obj.data
    key = ('lock-key', obj.name, bool(getattr(obj, 'is_evaluated', False)))
    counts = (
        len(mesh.vertices), len(mesh.edges), len(mesh.polygons), len(mesh.loops)
    )
    vertex_count, _edge_count, polygon_count, loop_count = counts

    vertices = np.empty(vertex_count * 3, dtype=np.float64)
    mesh.vertices.foreach_get('co', vertices)
    vertices.shape = (vertex_count, 3)
    loop_vertices = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get('vertex_index', loop_vertices)

    cached = _EXTRACTION_CACHE.get(key)
    if (
        cached is not None
        and cached['counts'] == counts
        and np.array_equal(cached['vertices'], vertices)
        and np.array_equal(cached['loop_vertices'], loop_vertices)
    ):
        _EXTRACTION_CACHE.pop(key)
        _EXTRACTION_CACHE[key] = cached
        return cached

    loop_starts = np.empty(polygon_count, dtype=np.int32)
    loop_totals = np.empty(polygon_count, dtype=np.int32)
    mesh.polygons.foreach_get('loop_start', loop_starts)
    mesh.polygons.foreach_get('loop_total', loop_totals)
    extent_low = vertices.min(axis=0) if vertex_count else np.zeros(3)
    extent_high = vertices.max(axis=0) if vertex_count else np.zeros(3)
    bulk = {
        'counts': counts,
        'vertices': vertices,
        'loop_vertices': loop_vertices,
        'loop_starts': loop_starts,
        'loop_totals': loop_totals,
        'loop_polygons': np.repeat(
            np.arange(polygon_count, dtype=np.int32), loop_totals
        ),
        'bbox_diagonal': float(np.linalg.norm(extent_high - extent_low)),
    }
    _EXTRACTION_CACHE.pop(key, None)
    _EXTRACTION_CACHE[key] = bulk
    while len(_EXTRACTION_CACHE) > _EXTRACTION_CACHE_LIMIT:
        _EXTRACTION_CACHE.pop(next(iter(_EXTRACTION_CACHE)))
    return bulk


def _lock_key_fit_data(obj, bulk=None, centre_local=None, radius_local=None,
                       provider=None):
    """Lock-key mesh data, whole-mesh or restricted to a sphere about a click.

    Same dict shape as _mesh_fit_data with polygon indexing left global, but
    edges are synthesised from the corner table (their ids are private to this
    dict) and centers and normals are computed from coordinates -- for a region,
    only for the polygons it holds. Polygons with any vertex outside the sphere
    are included and marked in 'region_boundary'; growth raises
    LockKeyRegionTooSmall the moment it touches one.
    """
    if bulk is None:
        bulk = _lock_key_bulk(obj)
    loop_vertices = bulk['loop_vertices']
    loop_starts = bulk['loop_starts']
    loop_totals = bulk['loop_totals']
    polygon_count = len(loop_starts)

    matrix = np.array(obj.matrix_world, dtype=np.float64)
    vertices = bulk['vertices'] @ matrix[:3, :3].T + matrix[:3, 3]

    boundary = None
    if centre_local is not None and radius_local is not None:
        delta = bulk['vertices'] - np.asarray(centre_local, dtype=np.float64)
        vert_in = np.einsum('ij,ij->i', delta, delta) <= radius_local * radius_local
        loop_in = vert_in[loop_vertices].astype(np.int32)
        inside_counts = np.add.reduceat(
            loop_in, loop_starts.astype(np.int64)
        ) if polygon_count else np.zeros(0, dtype=np.int32)
        poly_any = inside_counts > 0
        subset = np.nonzero(poly_any)[0].astype(np.int32)
        if not len(subset):
            subset = np.zeros(0, dtype=np.int32)
        member = poly_any
        boundary = poly_any & (inside_counts < loop_totals)
    else:
        member = None
        subset = np.arange(polygon_count, dtype=np.int32)

    sub_counts = loop_totals[subset]
    slots = _csr_ranges(loop_starts[subset], sub_counts)
    sub_starts = np.cumsum(sub_counts) - sub_counts
    corner = loop_vertices[slots]
    successor = np.arange(len(slots), dtype=np.int64) + 1
    ends = sub_starts + sub_counts - 1
    successor[ends] = sub_starts
    corner_next = corner[successor]
    positions = vertices[corner]

    # Centers as the corner mean and normals by Newell's formula, both from
    # world coordinates: within float noise of Blender's own values, and they
    # never require reading 5.5M polygons the click will not look at.
    centers = np.zeros((polygon_count, 3), dtype=np.float64)
    normals = np.zeros((polygon_count, 3), dtype=np.float64)
    if len(subset):
        reduce_at = sub_starts.astype(np.int64)
        sums = np.add.reduceat(positions, reduce_at, axis=0)
        centers[subset] = sums / sub_counts[:, None]
        crosses = np.cross(positions, vertices[corner_next])
        newell = np.add.reduceat(crosses, reduce_at, axis=0)
        lengths = np.linalg.norm(newell, axis=1)
        lengths[lengths == 0] = 1.0
        normals[subset] = newell / lengths[:, None]

    low = np.minimum(corner, corner_next).astype(np.int64)
    high = np.maximum(corner, corner_next).astype(np.int64)
    keys = (low << 32) | high
    unique_keys, inverse = np.unique(keys, return_inverse=True)
    loop_edges = np.full(len(loop_vertices), -1, dtype=np.int32)
    loop_edges[slots] = inverse.astype(np.int32)
    edge_lengths = np.linalg.norm(
        vertices[(unique_keys >> 32)] - vertices[(unique_keys & 0xFFFFFFFF)],
        axis=1,
    )
    order = np.argsort(inverse, kind='stable')
    edge_polygons = bulk['loop_polygons'][slots][order]
    edge_counts = np.bincount(inverse, minlength=len(unique_keys))
    edge_starts = np.concatenate(([0], np.cumsum(edge_counts)))

    return {
        'vertices': vertices,
        'loop_vertices': loop_vertices,
        'loop_edges': loop_edges,
        'loop_starts': loop_starts,
        'loop_totals': loop_totals,
        'loop_polygons': bulk['loop_polygons'],
        'polygon_centers': centers,
        'polygon_normals': normals,
        'edge_lengths': edge_lengths,
        'edge_polygons': edge_polygons,
        'edge_starts': edge_starts,
        'polygon_geometry': {},
        'polygon_patches': {},
        'synthetic_edges': True,
        'region_member': member,
        'region_boundary': boundary,
        'region_provider': provider,
    }


# A region starts at this fraction of the part's bounding diagonal and doubles
# on each widen; past the ceiling the whole part is cheaper than another
# partial build, so it falls through to full coverage.
_REGION_INITIAL_FRACTION = 0.05
_REGION_MAX_FRACTION = 0.3


class LockKeyMeshProvider:
    """Serves one object's lock-key mesh data, region-first.

    The solver raises LockKeyRegionTooSmall through whatever call consumed the
    data; the caller widens this provider and retries. Once full coverage is
    reached nothing can raise, so every retry loop terminates.
    """

    def __init__(self, world_hit=None):
        self.world_hit = None if world_hit is None else np.array(
            world_hit, dtype=np.float64
        )
        self.fraction = _REGION_INITIAL_FRACTION
        self.full = self.world_hit is None
        self._built = None
        self._built_key = None

    def data(self, fit_obj):
        matrix = np.array(fit_obj.matrix_world, dtype=np.float64)
        key = (matrix.tobytes(), self.full, self.fraction)
        if self._built is not None and self._built_key == key:
            return self._built
        # Bulk fetch (and its revalidation reads) only on an actual rebuild.
        bulk = _lock_key_bulk(fit_obj)
        if self.full:
            built = _lock_key_fit_data(fit_obj, bulk, provider=self)
        else:
            inverse = np.array(fit_obj.matrix_world.inverted(), dtype=np.float64)
            centre_local = (
                inverse[:3, :3] @ self.world_hit + inverse[:3, 3]
            )
            built = _lock_key_fit_data(
                fit_obj, bulk,
                centre_local=centre_local,
                radius_local=self.fraction * bulk['bbox_diagonal'],
                provider=self,
            )
        self._built = built
        self._built_key = key
        return built

    def widen(self):
        if self.full:
            return False
        self.fraction *= 2.0
        if self.fraction > _REGION_MAX_FRACTION:
            self.full = True
        self._built = None
        self._built_key = None
        return True

    def force_full(self):
        """Full coverage immediately -- for paths that must never raise."""
        if not self.full:
            self.full = True
            self._built = None
            self._built_key = None


def _seed_polygons(mesh_data, snap_type, element_index):
    if element_index < 0:
        return []
    # Synthetic edge ids are private to lock-key data; a Blender edge index
    # means nothing against them.
    if snap_type == 'MIDPOINTS' and mesh_data.get('synthetic_edges'):
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


def _csr_ranges(starts, counts):
    """Flat indices covering [start, start + count) per row, without a Python loop."""
    total = int(counts.sum())
    if total == 0:
        return np.empty(0, dtype=np.int64)
    firsts = np.cumsum(counts) - counts
    offsets = np.arange(total, dtype=np.int64) - np.repeat(firsts, counts)
    return np.repeat(starts, counts).astype(np.int64) + offsets


def _polygon_areas(mesh_data, polygon_indices):
    """World-space areas of many polygons at once, grouped by vertex count.

    Same fan triangulation as _polygon_geometry, batched: a merged figurine wall
    holds hundreds of thousands of polygons and a per-polygon call is seconds of
    pure Python on the first click.
    """
    loop_starts = mesh_data['loop_starts'][polygon_indices]
    loop_totals = mesh_data['loop_totals'][polygon_indices]
    vertices = mesh_data['vertices']
    loop_vertices = mesh_data['loop_vertices']
    areas = np.zeros(len(polygon_indices), dtype=np.float64)
    for total in np.unique(loop_totals):
        if total < 3:
            continue
        rows = np.nonzero(loop_totals == total)[0]
        slots = loop_starts[rows][:, None] + np.arange(int(total))[None, :]
        coords = vertices[loop_vertices[slots]]
        fans = np.cross(coords[:, 1:-1] - coords[:, :1], coords[:, 2:] - coords[:, :1])
        areas[rows] = 0.5 * np.linalg.norm(fans, axis=2).sum(axis=1)
    return areas


def _grow_planar_patch(mesh_data, seed_polygon, cos_planar=_FIT_COS_5):
    if seed_polygon in mesh_data['polygon_patches']:
        return mesh_data['polygon_patches'][seed_polygon]
    # A seed the region does not even hold has no connectivity here at all --
    # not boundary-marked, just absent -- so it must widen, not grow garbage.
    region_member = mesh_data.get('region_member')
    if region_member is not None and not region_member[int(seed_polygon)]:
        raise LockKeyRegionTooSmall(mesh_data['region_provider'])

    normals = mesh_data['polygon_normals']
    centers = mesh_data['polygon_centers']
    loop_starts = mesh_data['loop_starts']
    loop_totals = mesh_data['loop_totals']
    loop_edges = mesh_data['loop_edges']
    edge_starts = mesh_data['edge_starts']
    edge_polygons = mesh_data['edge_polygons']
    edge_lengths = mesh_data['edge_lengths']

    # The fill walks whole frontiers as numpy batches. Membership is the same
    # fixpoint as the polygon-at-a-time walk -- a polygon joins when any accepted
    # polygon reaches it across a qualifying edge -- but a dense figurine wall
    # spans hundreds of thousands of faces, and per-polygon Python took seconds
    # per click on meshes this fork exists for.
    in_component = np.zeros(len(loop_starts), dtype=bool)
    in_component[int(seed_polygon)] = True
    frontier = np.array([int(seed_polygon)], dtype=np.int64)
    while frontier.size:
        edges = loop_edges[_csr_ranges(loop_starts[frontier], loop_totals[frontier])]
        sources = np.repeat(frontier, loop_totals[frontier])
        fanout = edge_starts[edges + 1] - edge_starts[edges]
        neighbors = edge_polygons[_csr_ranges(edge_starts[edges], fanout)]
        sources = np.repeat(sources, fanout)
        edges = np.repeat(edges, fanout)
        candidate = ~in_component[neighbors]
        neighbors = neighbors[candidate]
        sources = sources[candidate]
        edges = edges[candidate]
        if not neighbors.size:
            break
        tolerance = np.maximum(0.005 * edge_lengths[edges], _FIT_ABS_TOL)
        source_normals = normals[sources]
        neighbor_normals = normals[neighbors]
        separation = centers[neighbors] - centers[sources]
        keep = (
            (np.einsum('ij,ij->i', source_normals, neighbor_normals) >= cos_planar)
            # Bounded against the seed, not only the previous face: pairwise
            # steps admit unlimited cumulative drift, and on a sculpt-dense
            # fillet (adjacent faces under 5 degrees apart) the crawl walks the
            # whole arc, fails the global flatness gate, and takes the flat
            # wall down with it. A flat wall's own normals wobble a fraction of
            # a degree, so the seed bound never splits one.
            & (neighbor_normals @ normals[int(seed_polygon)] >= cos_planar)
            & (np.abs(np.einsum('ij,ij->i', separation, source_normals)) <= tolerance)
            & (np.abs(np.einsum('ij,ij->i', separation, neighbor_normals)) <= tolerance)
        )
        frontier = np.unique(neighbors[keep])
        in_component[frontier] = True

    polygon_indices = np.nonzero(in_component)[0].astype(np.int32)
    # Region extraction: a patch touching a polygon the sphere cut open would
    # report truncated measurements, and everything downstream reads them.
    region_boundary = mesh_data.get('region_boundary')
    if region_boundary is not None and region_boundary[polygon_indices].any():
        raise LockKeyRegionTooSmall(mesh_data['region_provider'])
    component = {int(index) for index in polygon_indices}
    areas = _polygon_areas(mesh_data, polygon_indices)
    total_area = float(areas.sum())
    patch = None
    # A failed growth is invisible in the refusal log -- "0 raw patches" cannot
    # say whether the click was on a curve, a sliver, or the wrong mesh -- so
    # keep its measurements for lock_key_diagnostic_report.
    failure = {'faces': len(component), 'area': total_area}
    if total_area > 0:
        point = (mesh_data['polygon_centers'][polygon_indices] * areas[:, None]).sum(axis=0) / total_area
        normal = (mesh_data['polygon_normals'][polygon_indices] * areas[:, None]).sum(axis=0)
        normal_length = float(np.linalg.norm(normal))
        if normal_length > 0:
            normal /= normal_length
            loop_slots = _csr_ranges(
                mesh_data['loop_starts'][polygon_indices],
                mesh_data['loop_totals'][polygon_indices],
            )
            vertex_indices = np.unique(mesh_data['loop_vertices'][loop_slots])
            coordinates = mesh_data['vertices'][vertex_indices]
            extent = float(np.linalg.norm(coordinates.max(axis=0) - coordinates.min(axis=0)))
            tolerance = max(0.005 * extent, _FIT_ABS_TOL)
            residual = float(np.max(np.abs((mesh_data['polygon_centers'][polygon_indices] - point) @ normal)))
            failure.update(
                extent=extent, residual=residual, tolerance=tolerance,
                centre=point,
            )
            if extent > 0 and residual <= tolerance:
                # An edge is boundary when any polygon it carries fell outside the
                # component; edges owned by the mesh border alone never qualify,
                # exactly as before.
                component_edges = np.unique(mesh_data['loop_edges'][loop_slots])
                fanout = (
                    mesh_data['edge_starts'][component_edges + 1]
                    - mesh_data['edge_starts'][component_edges]
                )
                adjacent = mesh_data['edge_polygons'][_csr_ranges(
                    mesh_data['edge_starts'][component_edges], fanout
                )]
                outside = ~in_component[adjacent]
                boundary_edges = np.unique(
                    np.repeat(component_edges, fanout)[outside]
                )
                patch = {
                    'id': tuple(int(index) for index in polygon_indices),
                    'polygons': component,
                    'boundary_edges': tuple(int(edge) for edge in boundary_edges),
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
    if patch is None:
        failures = mesh_data.setdefault('patch_failures', {})
        for polygon_index in component:
            failures[polygon_index] = failure
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
    contact = np.array(contact, dtype=np.float64)
    pairs = []
    for i, first in enumerate(patches):
        for second in patches[i + 1:]:
            normal_dot = float(first['normal'] @ second['normal'])
            # Every printed connector carries draft, so demanding the two walls be
            # within 10 degrees of parallel meant precision fit simply did not see
            # them. Lock and key's 95-degree bar is the one that separates opposed
            # walls from corners; below it the axis is a bisector of a corner and
            # the "width" it measures means nothing.
            if normal_dot >= _WALL_MAX_OPPOSED_DOT:
                continue
            axis = first['normal'] - second['normal']
            length = float(np.linalg.norm(axis))
            if length == 0:
                continue
            axis /= length
            dominant = int(np.argmax(np.abs(axis)))
            if axis[dominant] < 0:
                axis *= -1.0
            # Measure each wall where it crosses the axis through the snapped
            # point, not by its plane offset. For parallel walls these are the same
            # number -- exactly, not approximately -- but on a tapered wall a plane
            # offset is not a width at all, and the pair it describes is fictional.
            contact_d = float(axis @ contact)
            crossings = []
            for patch in (first, second):
                denominator = float(patch['normal'] @ axis)
                if abs(denominator) < 0.5:
                    crossings = []
                    break
                crossings.append(
                    contact_d
                    + float(patch['normal'] @ (patch['point'] - contact)) / denominator
                )
            if not crossings:
                continue
            (low_d, low), (high_d, high) = sorted(
                zip(crossings, (first, second)), key=lambda item: item[0]
            )
            tolerance = first['tolerance'] + second['tolerance']
            fit_tolerance = first['fit_tolerance'] + second['fit_tolerance']
            separation = high_d - low_d
            contact_d = float(axis @ contact)
            # Whether a separation is real is a question about precision, not about
            # patch size. The flatness allowance is 0.5% of a patch's extent, so on
            # a broad thin tab it exceeds the tab's own thickness and discards the
            # one pair that matters. Same mistake, same fix as Lock and key.
            if separation <= fit_tolerance:
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
                'opening_angle': math.acos(np.clip(normal_dot, -1.0, 1.0)),
                'tolerance': tolerance,
                'fit_tolerance': fit_tolerance,
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
            # Now that tapered walls are admitted, the two tapers have to agree --
            # otherwise a straight wall centres against a chamfered lead-in, which
            # is the mistake this same test was added to Lock and key to prevent.
            if (
                abs(source['opening_angle'] - target['opening_angle'])
                > _CONNECTOR_TAPER_TOLERANCE
            ):
                continue
            tolerance = source['tolerance'] + target['tolerance']
            clearance = target['separation'] - source['separation']
            # Judge the clearance against how precisely the planes are defined, not
            # against how large they are: the flatness allowance demands roughly 2%
            # clearance on a 10-unit peg, which is far more than a printed fit has.
            if clearance <= source['fit_tolerance'] + target['fit_tolerance']:
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


def _fit_walls(mesh_data, seeds):
    """The logical walls around a snap element, as Lock and key sees them.

    A wall that arrives triangulated, decimated or sculpted comes back as dozens
    of fragments whose normals differ by a fraction of a degree, and to the pairing
    rules those fragments are not a wall at all: the seed lands on one of them,
    every neighbour faces the same way, and the opposite wall is hundreds of
    fragments away. Grouping by plane restores the wall the modeller drew.

    Lock and key's other two habits do not transfer. Its trim floor is measured
    against the wall that was clicked, and a snap element usually sits on a body
    face instead -- measured against that, the floor deleted the socket walls
    themselves. And its widening walk is affordable because it is a deliberate
    two-click action; this runs after every snap.
    """
    return _merge_coplanar_patches(_candidate_patches(mesh_data, seeds))


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
    source_patches = _fit_walls(source_data, source_seeds)
    target_patches = _fit_walls(target_data, target_seeds)
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
    except LockKeyRegionTooSmall:
        raise
    except Exception:
        return None
    if patch is None:
        return None
    return Vector(tuple(float(value) for value in patch['point']))


def _clicked_face_normal(mesh_data, face_index):
    """The clicked wall's plane normal, from the same mesh the solver reads.

    The raycast normal is one face of sculpt noise, and promotion forwards it
    unchanged when it moves the click to a different face; the patch normal is
    area-averaged and recomputed for whichever face the solve actually uses.
    """
    if mesh_data is None:
        return None
    index = int(face_index)
    if index < 0 or index >= len(mesh_data['polygon_normals']):
        return None
    try:
        patch = _grow_planar_patch(mesh_data, index)
    except LockKeyRegionTooSmall:
        raise
    except Exception:
        return None
    if patch is None:
        return None
    return np.array(patch['normal'], dtype=np.float64)


# A mouth chamfer or lead-in is a narrow strip whose plane sits roughly midway
# between the corner faces it replaced. A connector wall never reads this way:
# it meets its neighbours near 90 degrees, and an angled wall someone modelled
# on purpose -- a dovetail flank, a V-groove side -- is broad, not a strip.
# The strip's mean width is its area over its extent; a square patch fails the
# quarter-extent bar while anything longer than about four times its width
# passes.
_TRIM_BISECT_MIN_DOT = math.cos(math.radians(65.0))
_TRIM_BISECT_MAX_DOT = math.cos(math.radians(25.0))
_TRIM_MAX_WIDTH_FRACTION = 0.25
_TRIM_MIN_NEIGHBOUR_RATIO = 2.0


def trim_click_promotions(mesh_data, face_index):
    """The walls a click on edge trim could have meant, largest first.

    A click on a chamfer names the wall the chamfer softens, not the strip
    itself: the strip's own plane mates with nothing, and an anchor on it sits
    laterally outside the walls, so the real pair cannot span it. Which of the
    two bisected faces was meant cannot be read locally -- the strip splits
    their corner symmetrically -- so every candidate comes back and the caller
    lets the mate decide, failing closed when more than one fits differently.
    Returns [] whenever the clicked patch is not such trim.
    """
    index = int(face_index)
    if index < 0 or index >= len(mesh_data['polygon_normals']):
        return []
    try:
        clicked = _grow_planar_patch(mesh_data, index)
    except LockKeyRegionTooSmall:
        raise
    except Exception:
        return []
    if clicked is None:
        return []
    extent = float(clicked['extent'])
    area = float(clicked['area'])
    if extent <= 0.0 or area <= 0.0:
        return []
    if area / extent > _TRIM_MAX_WIDTH_FRACTION * extent:
        return []
    neighbours = {}
    for edge_index in clicked['boundary_edges']:
        for polygon_index in _edge_neighbors(mesh_data, int(edge_index)):
            polygon_index = int(polygon_index)
            if polygon_index in clicked['polygons']:
                continue
            patch = _grow_planar_patch(mesh_data, polygon_index)
            if patch is not None and patch['id'] != clicked['id']:
                neighbours[patch['id']] = patch
    bisected = [
        patch for patch in neighbours.values()
        if float(patch['area']) >= _TRIM_MIN_NEIGHBOUR_RATIO * area
        and _TRIM_BISECT_MIN_DOT
        <= float(patch['normal'] @ clicked['normal'])
        <= _TRIM_BISECT_MAX_DOT
    ]
    return [
        {
            'face_index': int(min(patch['polygons'])),
            'location': Vector(tuple(float(value) for value in patch['point'])),
        }
        for patch in sorted(bisected, key=lambda patch: -float(patch['area']))
    ]


# A plain box peg reaches its far wall in two patch hops. Every chamfer or fillet
# ring around an edge inserts another one, so a well-modelled connector puts its
# opposite wall out of reach and the click looks like it landed on nothing at all.
# Deep enough to cross two sculpt-dense fillets. Growth is bounded to 5 degrees
# of drift from its seed, so a 90-degree fillet is at worst ~a dozen strip
# patches however finely it is cut, and wall-to-opposite-wall runs two fillets
# plus the faces between. Ten hops covered a modelled bevel of a few segments
# but not a sculptor's rounding.
_CONNECTOR_MAX_HOPS = 30
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
# Curvature is a fact about the wall that was clicked, so it is measured there. A
# flat-sided connector's wall faces one other wall, or a few in a stepped slot; a
# rounded one faces half the facets of its own curve. Counting every pair in the
# neighbourhood instead measures how detailed the surrounding part is -- a socket in
# a busy part clears any such threshold without being remotely round.
_CONNECTOR_MAX_CLICKED_PAIRS = 8
# How large a facing wall must be, relative to the clicked one, to count as a peer
# rather than as incidental detail. A curve's facets are all of a size.
_CONNECTOR_PEER_FRACTION = 0.5
# A separate, far looser guard on total pairs, purely for cost: the matcher is
# quadratic in them, and a rounded click that reaches its own far side can produce
# them by the thousand.
_CONNECTOR_MAX_WALL_PAIRS = 400


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
    # One row per group, so each patch tests every group in one numpy pass: this
    # runs once per search radius per click, and a dense part reaches ~1800
    # patches against ~240 groups, which a Python inner loop paid in seconds.
    group_normals = np.empty((0, 3), dtype=np.float64)
    group_offsets = np.empty(0, dtype=np.float64)
    # Largest first, so a group's plane is anchored on its most reliable member.
    for patch in sorted(patches, key=lambda item: -float(item['area'])):
        if groups:
            dots = group_normals @ patch['normal']
            offsets = group_normals @ patch['point'] - group_offsets
            fits = np.nonzero(
                (dots >= _FIT_COS_5) & (np.abs(offsets) <= plane_tolerance)
            )[0]
        else:
            fits = np.empty(0, dtype=np.int64)
        if len(fits):
            groups[int(fits[0])]['members'].append(patch)
        else:
            normal = np.array(patch['normal'], dtype=np.float64)
            point = np.array(patch['point'], dtype=np.float64)
            groups.append({'members': [patch]})
            group_normals = np.vstack((group_normals, normal))
            group_offsets = np.append(group_offsets, normal @ point)

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


def _independent_axis_count(pairs):
    """How many distinct lateral directions these pairs actually constrain."""
    axes = []
    for pair in pairs:
        if not any(
            abs(float(pair['axis'] @ axis)) >= _FIT_COS_5 for axis in axes
        ):
            axes.append(pair['axis'])
    return len(axes)


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
    best = []
    trimmed = []
    for fraction in (_CONNECTOR_MIN_WALL_FRACTION, 0.0):
        previous_reached = None
        for hops in range(2, _CONNECTOR_MAX_HOPS + 1):
            reached, clicked = _connector_walls(mesh_data, seeds, hops)
            reached_ids = frozenset(patch['id'] for patch in reached)
            if reached_ids == previous_reached:
                break
            previous_reached = reached_ids
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
            # Count only partners of comparable size. A curve's facets are all much
            # the same area, so a rounded click is faced by many of them; a flat peg
            # standing on an organic body is faced by a crowd of body facets far
            # smaller than itself, and counting those calls the peg a curve.
            clicked_pairs = 0 if clicked is None else sum(
                1 for pair in pairs
                for side, other in (('low_patch', 'high_patch'),
                                    ('high_patch', 'low_patch'))
                if pair[side]['id'] == clicked['id']
                and float(pair[other]['area'])
                >= _CONNECTOR_PEER_FRACTION * float(clicked['area'])
            )
            if (
                clicked_pairs > _CONNECTOR_MAX_CLICKED_PAIRS
                or len(pairs) > _CONNECTOR_MAX_WALL_PAIRS
            ):
                # Only the floored pass can call something a curve. The fallback
                # below re-admits every sliver, so its counts measure how finely the
                # part is cut up, not how round it is -- claiming a curve from those
                # numbers would be a confident wrong answer.
                if fraction > 0.0:
                    return [], (
                        f"the {label} click is on a curved surface -- the wall you"
                        f" clicked is faced by {clicked_pairs} others, where a"
                        " flat-sided connector's wall faces one or a few, and"
                        " rounded connectors are not supported"
                    )
                break
            # The trimmed pass pairs only substantial walls, so whatever it found is
            # the connector the modeller drew. The fallback re-admits every sliver,
            # and a chamfer ring around a socket mouth offers pairs on two directions
            # at once -- enough to look complete and replace a real wall pair with
            # facets that share no taper with the key. Let it add directions the real
            # walls left unconstrained; never let it overwrite them.
            if fraction <= 0.0 and trimmed:
                pairs = trimmed + [
                    pair for pair in pairs
                    if not any(
                        abs(float(pair['axis'] @ kept['axis'])) >= _FIT_COS_5
                        for kept in trimmed
                    )
                ]
            # Returning at the first radius that yields any pair hands back
            # whichever single wall pair came into view first. Centring wants two
            # independent lateral directions and rotation flatly requires them, so
            # keep widening until the picture is complete -- while keeping the best
            # seen, since a slot legitimately constrains only one direction.
            if _independent_axis_count(pairs) > _independent_axis_count(best):
                best = pairs
            if _independent_axis_count(best) >= 2:
                return best, None
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
        trimmed = best
    if best:
        return best, None
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
        failure = (
            mesh_data.get('patch_failures', {}).get(int(seeds[0]))
            if seeds else None
        )
        if failure and failure.get('residual') is not None:
            return (
                "the clicked face is not part of a flat patch -- flat growth from"
                f" it swallowed {failure['faces']} face(s) and bowed"
                f" {failure['residual']:.5f} against a flatness allowance of"
                f" {failure['tolerance']:.5f}, so the surface there curves"
            )
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
    curves = [
        failure for failure in _curved_growths(mesh_data, anchor)
        if float(np.linalg.norm(failure['centre'] - anchor))
        <= float(clicked['extent'])
    ]
    if curves:
        rounded = max(curves, key=lambda item: item['faces'])
        parts.append(
            f"flat growth failed on {len(curves)} curved region(s) beside the"
            f" click, the biggest {rounded['faces']} faces spanning"
            f" {rounded['extent']:.4g} -- if that curve is the connector, it is"
            " rounded, and rounded connectors are not supported"
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


# How closely the key's taper must match the lock's. Matching already allows each
# wall 10 degrees from anti-parallel, and an opening is the difference of two such
# measurements, so requiring the openings themselves to agree within 5 was stricter
# than the test it accompanies. On a small connector, whose walls are a handful of
# merged fragments each, half a dozen degrees of disagreement is measurement rather
# than shape, and it refused connectors that plainly mate -- including on the
# rotation path, which needs two matched pairs and so fails entirely on one. It
# still fails closed on what this test exists for: a chamfered lead-in reads 40 to
# 60 degrees away from the straight wall it sits on.
_CONNECTOR_TAPER_TOLERANCE = math.radians(10.0)


def _match_connector_pairs(source_pairs, target_pairs):
    """Match compatible male/female wall pairs without guessing through ambiguity."""
    angle_tolerance = _CONNECTOR_TAPER_TOLERANCE
    opposed_limit = math.cos(math.radians(170.0))
    matches = []
    for source in source_pairs:
        candidates = []
        for target in target_pairs:
            if (
                source.get('_spatial_axis_rank') is not None
                and target.get('_spatial_axis_rank') is not None
                and source['_spatial_axis_rank'] != target['_spatial_axis_rank']
            ):
                continue
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
        (
            source.get('_spatial_axis_rank') is None
            or target.get('_spatial_axis_rank') is None
            or source['_spatial_axis_rank'] == target['_spatial_axis_rank']
        )
        and
        clearance is not None
        and abs(source['opening_angle'] - target['opening_angle'])
        <= _CONNECTOR_TAPER_TOLERANCE
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


# How closely a candidate rotation must bring the clicked key face to face the
# clicked lock face when the clicks, not anchors, carry the orientation intent.
# Sculpted end faces and parting planes sit within a few degrees of square to
# their connector; ten matches the taper tolerance used everywhere else.
_CLICK_FACES_OPPOSED_COS = math.cos(math.radians(10.0))


def _spatial_recovery_eligibility(
        source_pairs, target_pairs, source_click, target_click, reasons=None):
    """Name the one side whose disconnected lateral frame may be recovered."""
    def reject(reason):
        if reasons is not None:
            reasons.append(f"spatial recovery ineligible: {reason}")
        return None

    if source_click is None or target_click is None:
        return reject("exact planar clicked patches are unavailable")
    if (
        any(pair['anchor_side'] for pair in source_pairs)
        and any(pair['anchor_side'] for pair in target_pairs)
    ):
        return reject("explicit wall clicks keep the topology-local mapping")

    def lateral(pairs, click_normal):
        normal = np.array(click_normal, dtype=np.float64)
        length = float(np.linalg.norm(normal))
        if length <= 1e-12 or not np.isfinite(normal).all():
            return None, "a clicked patch normal is invalid"
        normal /= length
        result = [
            pair for pair in pairs
            if pair['opening_angle'] >= _ROTATION_MIN_OPENING
            and abs(float(pair['axis'] @ normal))
            <= math.sin(math.radians(10.0))
        ]
        if len(result) > _ROTATION_MAX_PAIRS:
            return None, "the local wall-pair budget was exceeded"
        if _rotation_axis_ambiguous(result):
            return None, "the local wall axes are ambiguous"
        return result, None

    source_lateral, source_reason = lateral(source_pairs, source_click)
    target_lateral, target_reason = lateral(target_pairs, target_click)
    if source_reason is not None or target_reason is not None:
        return reject(source_reason or target_reason)
    source_axes = _independent_axis_count(source_lateral)
    target_axes = _independent_axis_count(target_lateral)
    if source_axes > 2 or target_axes > 2:
        return reject("more than two independent lateral axes were measured")
    if source_axes >= 2 and target_axes >= 2:
        return reject("both sides already have complete topology-local frames")
    if source_axes < 2 and target_axes < 2:
        return reject("neither side supplies a trustworthy two-axis frame")
    if any(pair['anchor_side'] for pair in source_lateral + target_lateral):
        return reject("a surviving wall anchor makes face-to-face recovery unsafe")

    def independent_frame(pairs):
        frame = []
        for pair in pairs:
            if not any(
                abs(float(pair['axis'] @ kept['axis'])) >= _FIT_COS_5
                for kept in frame
            ):
                frame.append(pair)
                if len(frame) == 2:
                    break
        return frame

    if source_axes >= 2:
        if any(pair['anchor_side'] for pair in target_pairs):
            return reject("the missing target side still contains an anchored wall")
        return 'target', independent_frame(source_lateral), target_lateral
    if any(pair['anchor_side'] for pair in source_pairs):
        return reject("the missing source side still contains an anchored wall")
    return 'source', independent_frame(target_lateral), source_lateral


def _recover_spatial_connector_frame(
        mesh_data, anchor, click_normal, known_pairs, known_click_normal,
        missing_side):
    """Recover one bounded, measured two-axis frame across a topology break."""
    provider = mesh_data.get('region_provider')
    if provider is not None and not provider.full:
        raise LockKeyRegionTooSmall(provider)

    anchor = np.array(anchor, dtype=np.float64)
    click_normal = np.array(click_normal, dtype=np.float64)
    normal_length = float(np.linalg.norm(click_normal))
    if normal_length <= 1e-12 or not np.isfinite(click_normal).all():
        return [], "spatial recovery refused: the disconnected click has no finite plane normal"
    click_normal /= normal_length
    known_click_normal = np.array(known_click_normal, dtype=np.float64)
    known_normal_length = float(np.linalg.norm(known_click_normal))
    if known_normal_length <= 1e-12 or not np.isfinite(known_click_normal).all():
        return [], "spatial recovery refused: the known connector has no finite end-face normal"
    known_click_normal /= known_normal_length

    known = []
    for pair in known_pairs:
        if not any(
            abs(float(pair['axis'] @ kept['axis'])) >= _FIT_COS_5
            for kept in known
        ):
            known.append(pair)
    if len(known) < 2:
        return [], "spatial recovery refused: the known connector has fewer than two independent axes"
    known = known[:2]
    if any(
        abs(float(pair['axis'] @ known_click_normal))
        > math.sin(math.radians(10.0))
        for pair in known
    ):
        return [], "spatial recovery refused: the known walls do not form an end-face frame"
    known_roles = {_pair_is_female(pair) for pair in known}
    if len(known_roles) != 1:
        return [], "spatial recovery refused: the known connector has inconsistent wall roles"
    axial_direction = 1.0 if not next(iter(known_roles)) else -1.0
    widths = np.array([float(pair['width']) for pair in known])
    extents = np.array([
        float(patch['extent'])
        for pair in known for patch in (pair['low_patch'], pair['high_patch'])
    ])
    areas = np.array([
        float(patch['area'])
        for pair in known for patch in (pair['low_patch'], pair['high_patch'])
    ])
    if (
        not np.isfinite(widths).all() or not np.isfinite(extents).all()
        or not np.isfinite(areas).all() or np.any(widths <= 0.0)
        or np.any(extents <= 0.0) or np.any(areas <= 0.0)
    ):
        return [], "spatial recovery refused: the known connector dimensions are invalid"

    fit_tolerance = max(float(pair['fit_tolerance']) for pair in known)
    lateral_reach = 0.625 * float(np.linalg.norm(widths)) + fit_tolerance
    axial_reach = float(max(extents.max(), widths.max())) + fit_tolerance
    extent_ceiling = 2.0 * float(max(extents.max(), widths.max()))
    area_ceiling = 4.0 * float(areas.max())

    basis_u = np.cross(click_normal, (1.0, 0.0, 0.0))
    if float(np.linalg.norm(basis_u)) <= 1e-8:
        basis_u = np.cross(click_normal, (0.0, 1.0, 0.0))
    basis_u /= np.linalg.norm(basis_u)
    basis_v = np.cross(click_normal, basis_u)

    loop_totals = mesh_data['loop_totals'].astype(np.int64)
    polygon_indices = np.nonzero(loop_totals > 0)[0]
    if not len(polygon_indices):
        return [], "spatial recovery found no polygons on the disconnected side"
    counts = loop_totals[polygon_indices]
    slots = _csr_ranges(mesh_data['loop_starts'][polygon_indices], counts)
    coordinates = mesh_data['vertices'][mesh_data['loop_vertices'][slots]] - anchor
    starts = np.concatenate(([0], np.cumsum(counts)[:-1])).astype(np.int64)
    projected_u = coordinates @ basis_u
    projected_v = coordinates @ basis_v
    projected_z = coordinates @ click_normal
    u_min = np.minimum.reduceat(projected_u, starts)
    u_max = np.maximum.reduceat(projected_u, starts)
    v_min = np.minimum.reduceat(projected_v, starts)
    v_max = np.maximum.reduceat(projected_v, starts)
    z_min = np.minimum.reduceat(projected_z, starts)
    z_max = np.maximum.reduceat(projected_z, starts)
    nearest_u = np.maximum(np.maximum(u_min, -u_max), 0.0)
    nearest_v = np.maximum(np.maximum(v_min, -v_max), 0.0)
    intersects_lateral = np.hypot(nearest_u, nearest_v) <= lateral_reach
    side_min, side_max = (
        (z_min, z_max) if axial_direction > 0.0 else (-z_max, -z_min)
    )
    intersects_axial = (
        (side_max >= -fit_tolerance) & (side_min <= axial_reach)
    )
    normals = mesh_data['polygon_normals'][polygon_indices]
    wall_like = np.abs(normals @ click_normal) <= math.sin(math.radians(15.0))
    raw_extent = np.sqrt(
        (u_max - u_min) ** 2 + (v_max - v_min) ** 2 + (z_max - z_min) ** 2
    )
    candidate_indices = polygon_indices[
        intersects_lateral & intersects_axial & wall_like
        & np.isfinite(raw_extent) & (raw_extent <= extent_ceiling)
    ]
    if not len(candidate_indices):
        return [], "spatial recovery found no bounded planar wall candidates"

    candidate_areas = _polygon_areas(mesh_data, candidate_indices)
    candidate_indices = candidate_indices[
        (candidate_areas > 0.0) & (candidate_areas <= area_ceiling)
    ]

    def patch_interval(patch, axis):
        polygon_indices = np.fromiter(
            patch['polygons'], dtype=np.int64, count=len(patch['polygons'])
        )
        slots = _csr_ranges(
            mesh_data['loop_starts'][polygon_indices],
            mesh_data['loop_totals'][polygon_indices],
        )
        coordinates = mesh_data['vertices'][mesh_data['loop_vertices'][slots]]
        projection = coordinates @ axis
        return float(projection.min()), float(projection.max())

    patches = {}
    for polygon_index in candidate_indices:
        patch = _grow_planar_patch(mesh_data, int(polygon_index))
        if patch is None:
            continue
        if (
            float(patch['extent']) > extent_ceiling
            or float(patch['area']) > area_ceiling
            or abs(float(patch['normal'] @ click_normal))
            > math.sin(math.radians(15.0))
        ):
            continue
        patches[patch['id']] = patch

    groups = []
    for patch in sorted(patches.values(), key=lambda item: -float(item['area'])):
        matched = None
        for group in groups:
            reference = group[0]
            tolerance = max(
                float(patch['tolerance']),
                *(float(member['tolerance']) for member in group),
            )
            if (
                float(reference['normal'] @ patch['normal']) < _FIT_COS_5
                or abs(float(reference['normal'] @ (patch['point'] - reference['point'])))
                > tolerance
            ):
                continue
            tangent = np.cross(click_normal, reference['normal'])
            tangent_length = float(np.linalg.norm(tangent))
            if tangent_length <= 1e-12:
                continue
            tangent /= tangent_length

            def touches(member):
                member_tangent = patch_interval(member, tangent)
                patch_tangent = patch_interval(patch, tangent)
                member_axial = patch_interval(member, click_normal)
                patch_axial = patch_interval(patch, click_normal)
                return (
                    member_tangent[0] <= patch_tangent[1] + tolerance
                    and patch_tangent[0] <= member_tangent[1] + tolerance
                    and member_axial[0] <= patch_axial[1] + tolerance
                    and patch_axial[0] <= member_axial[1] + tolerance
                )

            if any(touches(member) for member in group):
                matched = group
                break
        if matched is None:
            groups.append([patch])
        else:
            matched.append(patch)

    patches = []
    for group in groups:
        patches.extend(_merge_coplanar_patches(group))
    patches = [
        patch for patch in patches
        if float(patch['extent']) <= extent_ceiling
        and float(patch['area']) <= area_ceiling
    ]
    recovered = [
        pair for pair in _connector_side_pairs(patches, anchor)
        if abs(float(pair['axis'] @ click_normal))
        <= math.sin(math.radians(10.0))
        and any(
            _rotation_compatible(pair, other)
            if missing_side == 'source'
            else _rotation_compatible(other, pair)
            for other in known
        )
    ]
    if len(recovered) > _ROTATION_MAX_PAIRS:
        return [], (
            f"spatial recovery refused {len(recovered)} opposed wall pairs;"
            f" the safe limit is {_ROTATION_MAX_PAIRS}"
        )

    def coherent_frame(first, second):
        frame_patches = (
            first['low_patch'], first['high_patch'],
            second['low_patch'], second['high_patch'],
        )
        tolerance = max(
            fit_tolerance, *(float(patch['tolerance']) for patch in frame_patches)
        )
        axial = [patch_interval(patch, click_normal) for patch in frame_patches]
        if max(low for low, _high in axial) > min(high for _low, high in axial) + tolerance:
            return False

        def spans(pair, other):
            positions = [
                float(other['axis'] @ other['low_patch']['point']),
                float(other['axis'] @ other['high_patch']['point']),
            ]
            required_low, required_high = min(positions), max(positions)
            for patch in (pair['low_patch'], pair['high_patch']):
                low, high = patch_interval(patch, other['axis'])
                if required_low < low - tolerance or required_high > high + tolerance:
                    return False
            return True

        return spans(first, second) and spans(second, first)

    frames = {}
    for first, second in itertools.combinations(recovered, 2):
        if abs(float(first['axis'] @ second['axis'])) >= _FIT_COS_5:
            continue
        if not coherent_frame(first, second):
            continue
        mappings = (
            _rotation_compatible(first, known[0])
            and _rotation_compatible(second, known[1])
            if missing_side == 'source' else
            _rotation_compatible(known[0], first)
            and _rotation_compatible(known[1], second)
        ) or (
            _rotation_compatible(first, known[1])
            and _rotation_compatible(second, known[0])
            if missing_side == 'source' else
            _rotation_compatible(known[1], first)
            and _rotation_compatible(known[0], second)
        )
        if not mappings:
            continue
        rows = np.array([first['axis'], second['axis']], dtype=np.float64)
        values = np.array([
            float(first['axis'] @ (first['center'] - anchor)),
            float(second['axis'] @ (second['center'] - anchor)),
        ])
        try:
            center_offset = np.linalg.lstsq(rows, values, rcond=0.1)[0]
        except np.linalg.LinAlgError:
            continue
        center_tolerance = 0.25 * float(widths.min()) + fit_tolerance
        if (
            not np.isfinite(center_offset).all()
            or float(np.linalg.norm(center_offset)) > center_tolerance
        ):
            continue
        inferred_center = anchor + center_offset
        if any(
            float(np.max(np.abs(rows @ (
                0.5 * (pair['low_patch']['point'] + pair['high_patch']['point'])
                - inferred_center
            )))) > center_tolerance
            for pair in (first, second)
        ):
            continue
        frame_key = frozenset((first['low_patch']['id'], first['high_patch']['id'],
                               second['low_patch']['id'], second['high_patch']['id']))
        frames[frame_key] = [first, second]
    if not frames:
        return [], (
            f"spatial recovery found {len(patches)} bounded wall patch(es) and"
            f" {len(recovered)} compatible pair(s), but no coherent two-axis frame"
        )
    if len(frames) != 1:
        return [], f"spatial recovery found {len(frames)} distinct compatible frames"
    frame = next(iter(frames.values()))
    if (
        abs(known[0]['width'] - known[1]['width'])
        > known[0]['fit_tolerance'] + known[1]['fit_tolerance']
        and abs(frame[0]['width'] - frame[1]['width'])
        > frame[0]['fit_tolerance'] + frame[1]['fit_tolerance']
    ):
        for rank, pair in enumerate(sorted(known, key=lambda item: item['width'])):
            pair['_spatial_axis_rank'] = rank
        for rank, pair in enumerate(sorted(frame, key=lambda item: item['width'])):
            pair['_spatial_axis_rank'] = rank
    return frame, None


def _rotation_candidates(
        source_pairs, target_pairs, allow_mixed_anchor=False, diagnostics=None,
        click_normals=None):
    """Enumerate compatible source/target wall mappings.

    `allow_mixed_anchor` pairs a wall click against a floor click. That mapping is
    only safe when the caller also supplies the target face normal, because nothing
    else constrains the insertion axis and an end-for-end flip otherwise satisfies
    every lateral test. The two travel together deliberately.

    `click_normals` is the (key, lock) pair of clicked-face plane normals. When
    NEITHER click lands on a connector wall -- the natural kit gesture is the top
    of the peg and the floor of the socket, and every such face points at the
    other part -- the two faces themselves carry the orientation intent: only
    rotations that bring them to rest facing each other are enumerated, which
    pins the insertion alignment and discards every end-for-end flip, exactly
    the job the anchors do for wall clicks. The remaining spin is settled
    downstream by the smallest-rotation rule over equivalent seatings.
    """
    if len(source_pairs) < 2 or len(target_pairs) < 2:
        _note_lock_key_skip(
            diagnostics,
            "rotation needs two independent wall pairs on each part and found"
            f" {len(source_pairs)} on the key / {len(target_pairs)} on the lock --"
            " click flat on a connector wall rather than a rim or a rounded face")
        return []
    clicked_a_key_wall = any(pair['anchor_side'] for pair in source_pairs)
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
    sources_anchored = any(pair['anchor_side'] for pair in source_pairs)
    targets_anchored = any(pair['anchor_side'] for pair in target_pairs)
    # Judged after pruning: a click on the peg's end face anchors the tip/base
    # pair of a plated part, but that pair can never drive this mate -- what
    # matters is that no SURVIVING pair carries the click, so the faces
    # themselves are the only orientation intent on offer.
    face_to_face = (
        not sources_anchored and not targets_anchored
        and click_normals is not None
    )
    if not sources_anchored and not face_to_face:
        # Every mapping below requires an anchored key pair, so enumerating
        # without one only ever produces an empty list -- and the fallback
        # message then blames penetration for a mate that was never attempted.
        if clicked_a_key_wall:
            _note_lock_key_skip(
                diagnostics,
                "the clicked key wall fits none of the lock's walls (width or"
                " taper) -- click the two walls that should rest against each"
                " other, or check that the parts are the same scale")
        else:
            _note_lock_key_skip(
                diagnostics,
                "rotation reads which face each click lands on to decide which"
                " way to turn the key, and the key click did not land on one of"
                " its connector's side walls -- click flat on a side wall of"
                " the key's connector and on the lock wall it should rest"
                " against, or click the key's end face and the lock's floor"
                " and the two faces will be brought to rest together")
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
                    > _CONNECTOR_TAPER_TOLERANCE
                    or clearance is None
                    or clearance < -tolerance
                    or (
                        bool(source['anchor_side'])
                        != bool(target['anchor_side'])
                        # Mixed pairing exists only for a floor click. When both
                        # parts carry a wall click, the clicks name the wall
                        # correspondence, and enumerating past them resurrects
                        # the near-square ambiguity ("several rotations fit
                        # differently") that anchoring exists to resolve.
                        and (
                            not allow_mixed_anchor
                            or (sources_anchored and targets_anchored)
                        )
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
                if not face_to_face and not any(
                    source['anchor_side'] for source in sources
                ):
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
                    if rotation is None:
                        continue
                    if face_to_face:
                        source_click, target_click = click_normals
                        if (
                            float((rotation @ source_click) @ target_click)
                            > -_CLICK_FACES_OPPOSED_COS
                        ):
                            continue
                    if any(
                        np.allclose(
                            rotation, item['rotation'], atol=1e-8, rtol=0.0
                        )
                        for item in candidates
                    ):
                        continue
                    candidates.append({'rotation': rotation})
    if not candidates:
        if face_to_face:
            _note_lock_key_skip(
                diagnostics,
                "no rotation rests the clicked key face against the clicked"
                " lock face with the connector walls fitting (width or taper)"
                " -- if those are not the two faces that should touch, click"
                " the two mating walls instead")
        elif targets_anchored:
            _note_lock_key_skip(
                diagnostics,
                "the clicked key wall and the clicked lock wall cannot rest"
                " against each other (width or taper mismatch) -- rotation"
                " follows the clicked walls, so click the two walls that"
                " should mate")
        else:
            _note_lock_key_skip(
                diagnostics,
                "no pairing of the key's walls onto the lock's walls fits"
                " (width or taper)")
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


def _centreable_matches(matches, source_hit, target_hit):
    """A translation from the matches a rigid move can actually balance.

    A sculpted connector offers more matched pairs than a translation has
    freedoms -- corner bevels, taper segments, near-parallel duplicates of a
    wall -- and their centres never agree to within flatness tolerance the way
    a symmetric test part's do. Demanding every match centre at once refused
    honest parts. When the full set fails, re-solve on the largest mutually
    consistent pairs, ordered by each pair's smaller wall: a pair is only as
    reliable as its lesser wall, so a disagreement between a wall pair and a
    corner-bevel pair is the wall's to win, never an ambiguity between peers.
    Excluded pairs still must not interpenetrate under the chosen translation,
    so a genuine clash fails closed; left un-centred but clear, they are
    designed clearance, not error.

    Returns (translation, used_matches); (None, ()) when nothing balances.
    """
    if not matches:
        return None, ()
    translation = _solve_lock_key_translation(matches, source_hit, target_hit)
    if translation is not None and _validate_lock_key_transform(matches, translation):
        return translation, tuple(matches)
    ranked = sorted(
        matches,
        key=lambda match: -min(
            float(match['source']['low_patch']['area']),
            float(match['source']['high_patch']['area']),
        ),
    )
    kept = []
    solution = None
    for match in ranked:
        candidate = kept + [match]
        attempt = _solve_lock_key_translation(candidate, source_hit, target_hit)
        if attempt is not None and _validate_lock_key_transform(candidate, attempt):
            kept = candidate
            solution = attempt
    if solution is None:
        return None, ()
    for match in matches:
        # Identity, not equality: these dicts hold numpy arrays.
        if any(match is used for used in kept):
            continue
        low_gap, high_gap = _connector_gaps(match, solution)
        if low_gap < -match['tolerance'] or high_gap < -match['tolerance']:
            return None, ()
    return solution, tuple(kept)


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
    """Where a candidate actually leaves the mated walls, as world planes.

    Two candidates are geometrically equivalent only when they seat the mated walls
    identically -- that is what makes a symmetric connector's alternative solutions
    interchangeable, and it is the only case where the design allows preferring the
    smaller rotation. Each plane carries the tolerance it was measured at, because
    "identically" is judged by _equivalent_seatings at that tolerance.
    """
    planes = []
    for match in matches:
        source = match['source']
        for name in ('low_patch', 'high_patch'):
            patch = source[name]
            normal = np.array(patch['normal'], dtype=np.float64)
            point = patch['point'] + translation
            planes.append((
                normal, float(normal @ point), float(match['tolerance']),
            ))
    return planes


def _equivalent_seatings(first, second):
    """True when two candidates seat the mated walls in the same planes,
    to within the tolerance each plane is measured at.

    Byte-exact plane equality decides this for ideal synthetic walls but never
    for sculpted ones: a near-square peg's four spins differ in the fourth
    decimal, far inside the flatness tolerance the planes were built with, so
    exact comparison turned "choose the smallest equivalent rotation" into a
    refusal on every real part. Seatings whose every wall plane has a
    counterpart within tolerance are indistinguishable at the precision the
    solver claims; a plane with no counterpart is a genuinely different
    seating and stays ambiguous.
    """
    def covered(planes, others):
        for normal, offset, tolerance in planes:
            if not any(
                float(normal @ other_normal) >= _FIT_COS_5
                and abs(offset - other_offset) <= max(tolerance, other_tolerance)
                for other_normal, other_offset, other_tolerance in others
            ):
                return False
        return True

    return covered(first, second) and covered(second, first)


# Surroundings survey: how far around each click the parts are compared, as a
# multiple of the widest matched pair, with hard caps bounding the work on
# dense sculpts. A sample buried deeper than the penetration factor times the
# seating's measurement tolerance is a physical impossibility, not sculpt
# noise; the depth reached is logged on every survey so field reports can
# judge the factor.
_SURVEY_RADIUS_WIDTHS = 2.5
_SURVEY_MAX_SAMPLES = 512
_SURVEY_MAX_POLYGONS = 20000
_SURVEY_PENETRATION_FACTOR = 4.0


def _survey_ring(mesh_data, anchor, radius, cap):
    """Polygon ids within radius of the anchor, nearest first.

    Raises LockKeyRegionTooSmall when the region does not cover the sphere, so
    the survey never reads cut-open data -- a truncated region would hide the
    very material an impossible seating penetrates.
    """
    centers = mesh_data['polygon_centers']
    member = mesh_data.get('region_member')
    mask = (
        np.ones(len(centers), dtype=bool) if member is None
        else np.asarray(member, dtype=bool)
    )
    delta = centers - anchor
    distances = np.einsum('ij,ij->i', delta, delta)
    within = mask & (distances <= radius * radius)
    boundary = mesh_data.get('region_boundary')
    if boundary is not None and bool(np.any(within & boundary)):
        raise LockKeyRegionTooSmall(mesh_data['region_provider'])
    ids = np.nonzero(within)[0]
    if len(ids) > cap:
        ids = ids[np.argsort(distances[ids], kind='stable')[:cap]]
    return ids


def _survey_obstacle_tree(mesh_data, polygon_ids):
    """A BVH of just the polygons near the target click, indices compacted."""
    from mathutils.bvhtree import BVHTree
    loop_vertices = mesh_data['loop_vertices']
    loop_starts = mesh_data['loop_starts']
    loop_totals = mesh_data['loop_totals']
    corners = [
        loop_vertices[loop_starts[index]:loop_starts[index] + loop_totals[index]]
        for index in map(int, polygon_ids)
    ]
    if not corners:
        return None
    used = np.unique(np.concatenate(corners))
    remap = np.full(int(used.max()) + 1, -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    vertices = [tuple(map(float, vertex)) for vertex in mesh_data['vertices'][used]]
    polygons = [tuple(int(remap[corner]) for corner in face) for face in corners]
    return BVHTree.FromPolygons(vertices, polygons)


def _survey_point_inside(tree, point, direction, limit):
    """Ray-parity containment: odd crossings along `direction` means inside.

    Signed distance off the nearest face misreads open shells -- the back of a
    socket wall claims the whole half-space behind it -- while parity reads a
    thin shell's free side as outside and a block's interior as inside, and is
    direction-independent on the closed manifolds real parts are.
    """
    origin = Vector(tuple(float(value) for value in point))
    epsilon = 1e-4 * limit
    remaining = limit
    crossings = 0
    for _ in range(64):
        location, _normal, _index, distance = tree.ray_cast(
            origin, direction, remaining
        )
        if location is None:
            break
        crossings += 1
        advance = distance + epsilon
        origin = location + direction * epsilon
        remaining -= advance
        if remaining <= 0.0:
            break
    return crossings % 2 == 1


def _survey_equivalent_seatings(
        source_data, target_data, source_anchor, target_anchor,
        seatings, radius, tolerance, direction):
    """Let the surroundings veto spin-equivalent seatings.

    A square-ish connector fits several ways and its walls cannot say which
    the sculptor meant -- but the parts around it can: under a wrong
    quarter-turn the sculpted surfaces beside the key drive into the lock's
    material, while the intended seating rests them together. Samples of the
    key's surface near its click are tested against the lock's surface near
    its click under each candidate, and a seating that buries a sample deeper
    than the allowance is physically impossible and discarded.

    This never creates a transform: every candidate comes from the connector
    walls, enumerated and solved as ever. It iterates nothing and runs on a
    bounded sample count -- a veto, not the ICP fallback the design forbids.
    Connector samples score identically under equivalent seatings, so every
    difference comes from the surroundings; when all seatings survive, the
    surroundings had nothing to say and the smallest rotation keeps deciding.

    Returns (kept_seatings, log_note); kept order preserves the caller's.
    """
    sample_ids = _survey_ring(
        source_data, source_anchor, radius, _SURVEY_MAX_SAMPLES
    )
    obstacle_ids = _survey_ring(
        target_data, target_anchor, radius, _SURVEY_MAX_POLYGONS
    )
    if not len(sample_ids) or not len(obstacle_ids):
        return seatings, None
    tree = _survey_obstacle_tree(target_data, obstacle_ids)
    if tree is None:
        return seatings, None
    samples = source_data['polygon_centers'][sample_ids]
    ray = Vector(tuple(float(value) for value in direction)).normalized()
    allowance = _SURVEY_PENETRATION_FACTOR * tolerance
    reach = 4.0 * radius
    kept = []
    deepest = 0.0
    for seating in seatings:
        matrix = np.array(seating[1], dtype=np.float64)
        moved = samples @ matrix[:3, :3].T + matrix[:3, 3]
        depth = 0.0
        for point in moved:
            near = tree.find_nearest(
                Vector(tuple(float(value) for value in point)), radius
            )
            if near[0] is None or near[3] <= allowance:
                # Nothing nearby, or too shallow to be a violation even if
                # buried -- parity is only worth its ray casts past that.
                continue
            if _survey_point_inside(tree, point, ray, reach):
                depth = max(depth, float(near[3]))
                if depth > allowance:
                    break
        deepest = max(deepest, depth)
        if depth <= allowance:
            kept.append(seating)
    if not kept:
        # The surroundings reject everything: broad noisy contact, not
        # information. Withdraw rather than turn a working mate into a refusal.
        return seatings, (
            f"surroundings overlap under all {len(seatings)} equivalent"
            f" seatings (deepest {deepest:.4f} vs allowance {allowance:.4f});"
            " keeping the nearest rotation")
    note = None
    if len(kept) < len(seatings):
        note = (
            f"{len(seatings)} seatings fit the connector equally; the"
            f" surroundings rule out {len(seatings) - len(kept)} (deepest"
            f" overlap {deepest:.4f} vs allowance {allowance:.4f}); keeping"
            f" the nearest of the {len(kept)} possible")
    return kept, note


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
    # With centre picks the anchor legitimately moves along the wall, but a
    # distance on the order of the part itself means the face index and the hit
    # came from different meshes -- the one failure the numbers below cannot show.
    say(f"anchor is {float(np.linalg.norm(anchor - mesh_data['polygon_centers'][index])):.5f}"
        " from the clicked face's centre")
    try:
        raw = _candidate_patches(mesh_data, seeds, _CONNECTOR_MAX_HOPS)
        walls, clicked = _connector_walls(mesh_data, seeds, _CONNECTOR_MAX_HOPS)
    except Exception as error:
        say(f"patch extraction failed: {error}")
        return lines
    say(f"at full depth: {len(raw)} raw patches -> {len(walls)} merged walls")
    curves = _curved_growths(mesh_data, anchor)
    if curves:
        say(f"failed (curved) flat growths recorded on this part: {len(curves)},"
            " nearest first:")
        for failure in curves[:3]:
            say(f"    {failure['faces']} face(s) spanning {failure['extent']:.5f},"
                f" bowed {failure['residual']:.5f} vs allowance"
                f" {failure['tolerance']:.5f},"
                f" centred {float(np.linalg.norm(failure['centre'] - anchor)):.5f}"
                " from the anchor")
    if clicked is None:
        say("the clicked face did not land in any merged wall")
        failure = mesh_data.get('patch_failures', {}).get(index)
        if failure and failure.get('residual') is not None:
            say(f"flat growth from it swallowed {failure['faces']} face(s)"
                f" spanning {failure['extent']:.5f} and bowed"
                f" {failure['residual']:.5f} against a flatness allowance of"
                f" {failure['tolerance']:.5f} -- the surface there curves"
                " (rounded geometry, or a smoothing modifier: try Ignore"
                " modifiers)")
        elif failure:
            say(f"flat growth from it found {failure['faces']} face(s) with no"
                f" usable area or normal (area {failure['area']:.9f})")
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
    # A taper-mismatch refusal quotes the closest pair combination, which need
    # not be among the largest; a short preview can hide exactly the pair the
    # refusal was measured against.
    for pair in pairs[:24]:
        # Which side is the socket is read off the wall normals, not off click
        # order, and it decides which way the clearance is subtracted -- so a
        # width mismatch cannot be read at all without it.
        say(f"    axis {tuple(round(float(v), 4) for v in pair['axis'])}"
            f" width {pair['width']:.6f}"
            f" opening {math.degrees(pair['opening_angle']):.2f}deg"
            f" {'socket' if _pair_is_female(pair) else 'peg'}"
            f" anchor_side {pair['anchor_side']}")
        # Which two walls a pair is made of decides whether it is the connector or a
        # chamfer facet next to it, and a pair line without them cannot be told
        # apart from a good one -- which cost a full round of diagnosis.
        for side in ('low_patch', 'high_patch'):
            wall = pair[side]
            say(f"        {side[:-6]:>4} wall area {wall['area']:10.5f}"
                f" normal {tuple(round(float(v), 4) for v in wall['normal'])}")
    if len(pairs) > 24:
        say(f"    ... and {len(pairs) - 24} more")
    # The pairs above come from the widening search, which stops at the first
    # radius offering two independent axes -- walls listed "in reach" at full
    # depth can still be absent from them. This trace shows what was pairable at
    # each radius, so a pair that only exists beyond the stop is visible.
    # Pairing is quadratic and this report runs on the refusal path of dense
    # parts, so each radius pairs only the largest walls -- slivers are never
    # the question the trace answers -- and the loop ends once the reach stops
    # growing, since every later radius would repeat the same line.
    say("widening trace (pairs among the 40 largest walls per radius):")
    previous = None
    for hop in range(2, _CONNECTOR_MAX_HOPS + 1):
        try:
            reached, _clicked = _connector_walls(mesh_data, seeds, hop)
            if previous is not None and len(reached) == previous:
                say(f"    hops {hop:>2}+: reach saturated at {previous} walls")
                break
            previous = len(reached)
            largest = sorted(
                reached, key=lambda item: -float(item['area'])
            )[:40]
            unfloored = _connector_side_pairs(largest, anchor)
        except Exception as error:
            say(f"    hops {hop:>2}: failed: {error}")
            break
        # Widest first: the question this trace answers is whether a
        # straighter pair than the returned ones ever comes into reach, and
        # ascending order buried it under the noise floor at 95.
        openings = sorted({
            round(math.degrees(item['opening_angle']), 1) for item in unfloored
        }, reverse=True)
        say(f"    hops {hop:>2}: {len(reached):>3} walls, {len(unfloored):>3}"
            f" pairs, {_independent_axis_count(unfloored)} independent axes,"
            f" openings (widest first) {openings[:12]}")
    if reason:
        say(f"refused: {reason}")
    return lines


def _closest_orientation_miss(source_pairs, target_pairs):
    """The combination that came nearest to facing, and by how much it missed.

    "None facing each other" over a thousand combinations says nothing about
    whether the parts are a few degrees out or structurally unrelated, and those
    want opposite advice. Returns (axis degrees apart, worst wall angle from
    anti-parallel, source pair, target pair), or None when either side has no pairs.
    """
    best = None
    for source in source_pairs:
        for target in target_pairs:
            axis = math.degrees(math.acos(abs(float(
                np.clip(source['axis'] @ target['axis'], -1.0, 1.0)
            ))))
            walls = max(
                180.0 - math.degrees(math.acos(float(np.clip(
                    source[side]['normal'] @ target[side]['normal'], -1.0, 1.0
                ))))
                for side in ('low_patch', 'high_patch')
            )
            if best is None or axis + walls < best[0] + best[1]:
                best = (axis, walls, source, target)
    return best


def _pairs_share_an_axis(source_pairs, target_pairs):
    """True when the two clicks agree on at least one lateral direction."""
    return any(
        abs(float(source['axis'] @ target['axis'])) >= _FIT_COS_5
        for source in source_pairs
        for target in target_pairs
    )


def _curved_growths(mesh_data, anchor):
    """Distinct failed flat growths with a measurable centre, nearest first.

    A rounded connector never becomes a wall: its growth fails the flatness gate
    and vanishes from every list a refusal prints, so the refusals around one
    read as if the connector did not exist -- clicking its side says to click
    flat, clicking the flat beside it says to click the side. These records are
    the only trace the curve leaves.
    """
    anchor = np.array(anchor, dtype=np.float64)
    distinct = {}
    for failure in mesh_data.get('patch_failures', {}).values():
        if failure.get('centre') is not None:
            distinct[id(failure)] = failure
    return sorted(
        distinct.values(),
        key=lambda item: float(np.linalg.norm(item['centre'] - anchor)),
    )


# A connector wall faces another wall of comparable size -- that is what makes it a
# connector. A parting plane, a base or a body face has nothing facing it, and the
# only candidates are incidental detail orders of magnitude smaller.
_CONNECTOR_MIN_FACING_FRACTION = 0.02


def _clicked_wall_is_not_a_connector(mesh_data, seeds, anchor, label, pairs=()):
    """A refusal for a click on a big flat face rather than on a connector.

    This is the commonest way to misread the feature: on a split figurine the two
    halves meet at a parting plane, and clicking that plane looks entirely
    reasonable. It has no opposite wall, so the solver falls back on whatever
    incidental detail is nearby and then reports an angle between two things that
    were never connector walls. Returns None when the click does have a real
    opposite and the ordinary refusals should speak instead.
    """
    walls, clicked = _connector_walls(mesh_data, seeds, _CONNECTOR_MAX_HOPS)
    if clicked is None:
        return None
    area = float(clicked['area'])
    if area <= 0.0:
        return None
    # Two substantial walls facing each other near the click are a connector, and
    # it makes no difference whether the clicked wall is one of them: a neck or a
    # shoulder is cut flat across, and clicking that cut still reaches the peg
    # beside it -- centring even puts the anchor between its walls. Only when the
    # click has nothing facing it AND nothing connector-sized within reach is it
    # fair to say it landed on bare plate. Judging the click alone made this
    # verdict unfalsifiable whenever the parts were not already aligned, which is
    # exactly when the user needs to hear about rotation instead.
    if any(
        min(float(pair['low_patch']['area']), float(pair['high_patch']['area']))
        >= _CONNECTOR_MIN_WALL_FRACTION * area
        for pair in pairs
    ):
        return None
    facing = [
        float(wall['area']) for wall in walls
        if wall['id'] != clicked['id']
        and float(wall['normal'] @ clicked['normal']) < _WALL_MAX_OPPOSED_DOT
    ]
    biggest = max(facing) if facing else 0.0
    # Nothing facing at all is a different story -- the opposite wall may simply be
    # out of reach -- and the reach message says that better than this one would.
    if biggest <= 0.0 or biggest >= _CONNECTOR_MIN_FACING_FRACTION * area:
        return None
    # Telling the user to click the connector instead is circular when the
    # connector beside this face is rounded: its side refuses with "click flat".
    # Only the failed growths know the curve is there at all.
    anchor = np.array(anchor, dtype=np.float64)
    curves = [
        failure for failure in _curved_growths(mesh_data, anchor)
        if float(np.linalg.norm(failure['centre'] - anchor))
        <= float(clicked['extent'])
    ]
    hint = (
        ". On a split part, click the side of the peg or the inner wall of the"
        " socket, not the flat face they sit on"
    )
    if curves:
        rounded = max(curves, key=lambda item: item['faces'])
        hint = (
            f". Beside it, flat growth failed on {len(curves)} curved region(s),"
            f" the biggest {rounded['faces']} faces spanning"
            f" {rounded['extent']:.4g} -- if that curve is the connector, it is"
            " rounded, and rounded connectors are not supported"
        )
    return (
        f"the {label} click is on a large flat face rather than a connector -- the"
        f" wall you clicked measures {area:.4g} and the biggest wall facing it"
        f" measures {biggest:.4g}, so there is nothing here to mate into" + hint
    )


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
        diagnostics=None, allow_promotion=True):
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
    if source_object_name == target_object_name:
        # Cheap and first: the geometry downstream would refuse anyway, but only
        # after paying two full extractions and a wall search whose refusal then
        # misdescribes the mistake as a taper mismatch between identical walls.
        _note_lock_key_skip(
            diagnostics,
            "both clicks are on the same object -- a mate moves the whole"
            " object, so it cannot mate with itself. Click the key on the"
            " moving part and the lock on the part it joins")
        return None
    depsgraph = context.evaluated_depsgraph_get()
    ignore_modifiers = getattr(settings, 'ignore_modifiers', False)
    source_fit = source_obj if ignore_modifiers else source_obj.evaluated_get(depsgraph)
    target_fit = target_obj if ignore_modifiers else target_obj.evaluated_get(depsgraph)
    source_data = (
        _lock_key_fit_data(source_fit) if source_mesh_data is None
        else source_mesh_data
    )
    target_data = (
        _lock_key_fit_data(target_fit) if target_mesh_data is None
        else target_mesh_data
    )
    source_seeds = _seed_polygons(source_data, 'FACES', source_face_index)
    target_seeds = _seed_polygons(target_data, 'FACES', target_face_index)
    if not source_seeds or not target_seeds:
        _note_lock_key_skip(diagnostics, "the clicked face no longer exists; pick again")
        return None
    # A click on mouth trim must be promoted BEFORE the direct solve, not retried
    # after it: an anchor on the chamfer can also succeed wrongly -- a
    # perpendicular pair still matches while the clicked axis silently comes from
    # the trim -- and that mate never reaches any retry. Promotion is part of pick
    # centring ("move the pick to the feature it names"), so it obeys the same
    # preference.
    if allow_promotion and getattr(settings, 'lock_and_key_centre_picks', True):
        source_options = [(source_face_index, source_hit)] + [
            (promotion['face_index'], promotion['location'])
            for promotion in trim_click_promotions(source_data, source_face_index)
        ]
        target_options = [(target_face_index, target_hit)] + [
            (promotion['face_index'], promotion['location'])
            for promotion in trim_click_promotions(target_data, target_face_index)
        ]
        if len(source_options) > 1 or len(target_options) > 1:
            deltas = []
            for source_at, (source_face, source_point) in enumerate(source_options):
                for target_at, (target_face, target_point) in enumerate(target_options):
                    if source_at == 0 and target_at == 0:
                        continue
                    candidate = compute_lock_key_transform(
                        context, settings,
                        source_object_name, source_face, source_point,
                        target_object_name, target_face, target_point,
                        allow_rotation=allow_rotation,
                        source_mesh_data=source_data, target_mesh_data=target_data,
                        source_normal=source_normal, target_normal=target_normal,
                        diagnostics=None, allow_promotion=False,
                    )
                    if candidate is not None:
                        deltas.append(candidate)
            if deltas:
                first = np.array(deltas[0], dtype=np.float64)
                if all(
                    float(np.max(np.abs(np.array(other, dtype=np.float64) - first)))
                    <= 1e-5
                    for other in deltas[1:]
                ):
                    return deltas[0]
                _note_lock_key_skip(
                    diagnostics,
                    "the click landed on the chamfer between two walls and each"
                    " wall gives a different mate -- click the connector wall"
                    " itself, past the chamfer")
                return None
            # No promoted mate: fall through to the direct solve, whose refusals
            # name what to do differently.
    source_anchor = np.array(source_hit, dtype=np.float64)
    target_anchor = np.array(target_hit, dtype=np.float64)
    source_pairs, source_reason = _connector_pairs(
        source_data, source_seeds, source_anchor, 'key'
    )
    target_pairs, target_reason = _connector_pairs(
        target_data, target_seeds, target_anchor, 'lock'
    )
    matches = _match_connector_pairs(source_pairs, target_pairs)
    translation, _used = _centreable_matches(matches, source_anchor, target_anchor)
    if translation is not None:
        return mathutils.Matrix.Translation(
            Vector(tuple(float(value) for value in translation))
        )
    if not allow_rotation:
        # Two clicks whose wall pairs agree on a lateral direction have found the
        # connector, whatever refuses further down: a flat face with nothing facing
        # it cannot produce one. Telling the user they clicked a parting plane when
        # the two connectors line up to a degree sends them at the wrong thing.
        not_a_connector = None if _pairs_share_an_axis(source_pairs, target_pairs) else (
            _clicked_wall_is_not_a_connector(
                source_data, source_seeds, source_anchor, 'key', source_pairs)
            or _clicked_wall_is_not_a_connector(
                target_data, target_seeds, target_anchor, 'lock', target_pairs)
        )
        if not source_pairs and not_a_connector is None:
            _note_lock_key_skip(diagnostics, source_reason)
        elif not target_pairs and not_a_connector is None:
            _note_lock_key_skip(diagnostics, target_reason)
        # Both clicks produced pairs, so nothing here is merely out of reach --
        # which makes it worth asking whether either click was on a connector at
        # all. Reporting an angle between two walls that were never connector walls
        # is worse than useless: it reads as a measurement.
        elif not_a_connector is not None:
            _note_lock_key_skip(diagnostics, not_a_connector)
        elif not matches:
            # Matching needs the walls anti-parallel within 10 degrees and the
            # lateral axes aligned within 5, so a key that is not already rotated
            # into place can never match however well the parts actually fit.
            # Distinguish that from parts that face each other but do not fit.
            facing = _orientation_compatible_pairs(source_pairs, target_pairs)
            miss = _closest_orientation_miss(source_pairs, target_pairs)
            if not facing and miss is not None and miss[0] <= _FIT_ANGLE_5:
                # The axes agree, so the parts are not turned the wrong way and no
                # amount of rotating will help. What differs is the shape of the two
                # walls themselves -- typically a straight peg measured against the
                # chamfered mouth of its socket, whose facets are the only pair the
                # search reached.
                _note_lock_key_skip(
                    diagnostics,
                    "the key and the lock line up on the same axis but their walls"
                    " are not parallel -- the key's walls open"
                    f" {math.degrees(miss[2]['opening_angle']):.1f} degrees where the"
                    f" lock's open {math.degrees(miss[3]['opening_angle']):.1f}, so"
                    " one of the two is a chamfer or a taper rather than the"
                    " straight wall of the connector. Click further along the wall,"
                    " past any chamfer at its mouth")
            elif not facing:
                nearest = "" if miss is None else (
                    f"; nearest combination is {miss[0]:.1f} degrees off on the"
                    f" wall direction and {miss[1]:.1f} degrees from facing"
                )
                _note_lock_key_skip(
                    diagnostics,
                    "the key is not aligned with the lock -- turn on 'Rotate key to"
                    " match lock' and click a side wall of the key's connector plus"
                    " the lock wall it should rest against, or rotate the key"
                    " roughly into place first"
                    f" ({len(source_pairs)} key / {len(target_pairs)} lock wall"
                    f" pairs, none facing each other{nearest})")
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
            # Far-apart clicks are exactly what pick centring exists to absorb,
            # so when it is off, name the setting rather than only the symptom.
            centring_hint = (
                "" if getattr(settings, 'lock_and_key_centre_picks', True)
                else ", or turn 'Centre picks' back on so both clicks move to"
                " the middle of their walls"
            )
            # Name which check refused each pair, under the full-set solve:
            # "could not be centred" covers gap imbalance, interpenetration and
            # the anchor relocation cap, and they call for different fixes.
            details = []
            full_translation = _solve_lock_key_translation(
                matches, source_anchor, target_anchor
            )
            if full_translation is not None:
                correction = full_translation - (target_anchor - source_anchor)
                for match in matches:
                    low_gap, high_gap = _connector_gaps(match, full_translation)
                    tolerance = match['tolerance']
                    along = abs(float(match['axis'] @ correction))
                    cap = 0.25 * match['source']['width'] + tolerance
                    details.append(
                        f" [axis {tuple(round(float(v), 3) for v in match['axis'])}"
                        f" gaps {low_gap:+.4f}/{high_gap:+.4f} tol {tolerance:.4f}"
                        f" anchor-shift {along:.4f} cap {cap:.4f}]"
                    )
            _note_lock_key_skip(
                diagnostics,
                f"{len(matches)} matched wall pair(s) could not be centred within"
                " tolerance -- the two clicks may be too far apart, or enable"
                f" 'Rotate key to match lock'{centring_hint}"
                + "".join(details))
        return None

    valid = []
    allow_mixed_anchor = target_normal is not None
    explained = 0 if diagnostics is None else len(diagnostics)

    def _click_normal(patch_normal, raycast_normal):
        normal = patch_normal
        if normal is None and raycast_normal is not None:
            normal = np.array(raycast_normal, dtype=np.float64)
            length = float(np.linalg.norm(normal))
            normal = normal / length if length > 1e-12 else None
        return normal

    source_patch_click = _clicked_face_normal(source_data, source_face_index)
    target_patch_click = _clicked_face_normal(target_data, target_face_index)
    source_click = _click_normal(source_patch_click, source_normal)
    target_click = _click_normal(target_patch_click, target_normal)
    click_normals = (
        (source_click, target_click)
        if source_click is not None and target_click is not None else None
    )
    recovery_click_normals = (
        (source_patch_click, target_patch_click)
        if source_patch_click is not None and target_patch_click is not None
        else None
    )
    recovery_reasons = []
    if recovery_click_normals is None:
        recovery_reasons.append(
            "spatial recovery ineligible: exact planar clicked patches are unavailable"
        )
        recovery = None
    else:
        recovery = _spatial_recovery_eligibility(
            source_pairs, target_pairs, source_patch_click, target_patch_click,
            recovery_reasons,
        )
    if recovery is not None:
        missing_side, known_pairs, _missing_pairs = recovery
        if missing_side == 'source':
            recovered, reason = _recover_spatial_connector_frame(
                source_data, source_anchor, source_patch_click, known_pairs,
                target_patch_click, missing_side,
            )
            source_pairs = recovered
            target_pairs = known_pairs
        else:
            recovered, reason = _recover_spatial_connector_frame(
                target_data, target_anchor, target_patch_click, known_pairs,
                source_patch_click, missing_side,
            )
            source_pairs = known_pairs
            target_pairs = recovered
        if not recovered:
            _note_lock_key_skip(diagnostics, reason)
            return None
    candidates = _rotation_candidates(
        source_pairs, target_pairs, allow_mixed_anchor=allow_mixed_anchor,
        diagnostics=diagnostics, click_normals=click_normals,
    )
    if not candidates and recovery_reasons:
        _note_lock_key_skip(diagnostics, recovery_reasons[-1])
    # Which gate discarded each candidate. A refusal that cannot say is the
    # bug class this log exists to prevent: an empty enumeration spent weeks
    # in the field misreported as "penetrating the lock".
    killed = {'unmatched': 0, 'uncentred': 0, 'one-axis': 0, 'insertion-guard': 0}
    for candidate in candidates:
        rotation = candidate['rotation']
        rotated_pairs = _rotate_connector_pairs(source_pairs, rotation)
        rotated_anchor = rotation @ source_anchor
        rotated_matches = _match_connector_pairs(rotated_pairs, target_pairs)
        if len(rotated_matches) < 2:
            killed['unmatched'] += 1
            continue
        rotated_translation, rotated_used = _centreable_matches(
            rotated_matches, rotated_anchor, target_anchor
        )
        if rotated_translation is None or len(rotated_used) < 2:
            killed['uncentred'] += 1
            continue
        # Rank the axes of the pairs that actually constrained the solve: a
        # rotation held by one balanced axis plus discarded extras is held by
        # one axis, however many pairs matched.
        axes = np.array([match['axis'] for match in rotated_used])
        if np.linalg.matrix_rank(axes, tol=math.sin(math.radians(5.0))) < 2:
            killed['one-axis'] += 1
            continue
        # The insertion-axis guard reads the half-space off the socket's clicked
        # face, so which half is the socket decides which click it reads and which
        # pairs it tests. The matcher has already agreed on the roles by this point.
        if _pair_is_female(rotated_used[0]['source']):
            socket_normal = (
                None if source_normal is None
                else rotation @ np.array(source_normal, dtype=np.float64)
            )
            if socket_normal is None and allow_mixed_anchor:
                # Mixed anchors put the end-for-end flip back on the table, and only
                # the socket's own click can discard it. Fail closed rather than seat
                # a candidate that nothing constrained.
                killed['insertion-guard'] += 1
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
            killed['insertion-guard'] += 1
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
                    rotated_used, rotated_translation
                ),
                max(match['source']['width'] for match in rotated_used),
                max(match['tolerance'] for match in rotated_used),
            ))
    if not valid:
        # Only fall back to the generic seating message when the enumeration has not
        # already said something more useful -- the caller surfaces the last note, so
        # appending here would bury "this connector has too many walls to search".
        if diagnostics is None or len(diagnostics) == explained:
            autopsy = ", ".join(
                f"{count} {gate}" for gate, count in killed.items() if count
            )
            _note_lock_key_skip(
                diagnostics,
                "no rotation seats the key without penetrating the lock"
                + (f" ({len(candidates)} candidate rotation(s) discarded:"
                   f" {autopsy})" if autopsy else ""))
        return None
    # Smallest-angle ranking is only legitimate between candidates that seat the
    # mated walls identically within measurement tolerance. Candidates that seat
    # them differently are a genuine ambiguity, and preferring the nearer one
    # would silently pick an orientation the geometry never justified.
    valid.sort(key=lambda item: item[0])
    if any(
        not _equivalent_seatings(valid[0][2], item[2]) for item in valid[1:]
    ):
        _note_lock_key_skip(
            diagnostics,
            "several rotations fit differently; too ambiguous to choose --"
            " click the key on a side wall of its connector and the lock on"
            " the wall it should rest against, so the clicks decide the"
            " orientation")
        return None
    if len(valid) > 1 and target_click is not None:
        # The connector cannot tell equivalent seatings apart, but the parts
        # around it usually can -- a wrong quarter-turn drives the sculpted
        # surroundings into the other part's material.
        valid, survey_note = _survey_equivalent_seatings(
            source_data, target_data, source_anchor, target_anchor, valid,
            _SURVEY_RADIUS_WIDTHS * max(item[3] for item in valid),
            max(item[4] for item in valid),
            target_click,
        )
        if survey_note:
            logger.warning(f"Lock and key: {survey_note}")
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

        point2 = origin + world_matrix @ offset_vector
        result = mathutils.geometry.intersect_line_line(camera_position, camera_point_b, origin, point2)
        if result is None:
            return origin
        return result[1]

    # Planar constraint
    if len(snapping) == 2:
        if snapping == 'XY':
            point2 = origin + world_matrix @ Vector((1000, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 1000, 0))
        elif snapping == 'YZ':
            point2 = origin + world_matrix @ Vector((0, 1000, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1000))
        else:
            point2 = origin + world_matrix @ Vector((1000, 0, 0))
            point3 = origin + world_matrix @ Vector((0, 0, 1000))

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



