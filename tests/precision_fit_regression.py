import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Vector
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("quicksnap_utils_under_test", ROOT / "quicksnap_utils.py")
quicksnap_utils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(quicksnap_utils)


def make_mesh(name, vertices, faces, reverse_face_order=False):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(vertices, [], list(reversed(faces)) if reverse_face_order else faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


class MeshBuilder:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self._indices = {}

    @staticmethod
    def _key(point):
        return tuple(round(float(value), 6) for value in point)

    def vertex(self, point):
        key = self._key(point)
        index = self._indices.get(key)
        if index is None:
            index = len(self.vertices)
            self._indices[key] = index
            self.vertices.append(key)
        return index

    def index(self, point):
        return self._indices[self._key(point)]

    def quad_grid(self, p00, p10, p11, p01, subdivisions, triangulate=False, uneven=False):
        corners = tuple(Vector(point) for point in (p00, p10, p11, p01))
        grid = []
        for row in range(subdivisions + 1):
            v = row / subdivisions
            if uneven:
                v = v ** 1.5
            indices = []
            for column in range(subdivisions + 1):
                u = column / subdivisions
                if uneven:
                    u = u ** 2
                point = ((1 - u) * (1 - v) * corners[0] +
                         u * (1 - v) * corners[1] +
                         u * v * corners[2] +
                         (1 - u) * v * corners[3])
                indices.append(self.vertex(point))
            grid.append(indices)
        for row in range(subdivisions):
            for column in range(subdivisions):
                low_left = grid[row][column]
                low_right = grid[row][column + 1]
                high_right = grid[row + 1][column + 1]
                high_left = grid[row + 1][column]
                if not triangulate:
                    self.faces.append((low_left, low_right, high_right, high_left))
                elif (row + column) % 2 == 0:
                    self.faces.extend(((low_left, low_right, high_right),
                                       (low_left, high_right, high_left)))
                else:
                    self.faces.extend(((low_left, low_right, high_left),
                                       (low_right, high_right, high_left)))


def make_peg(subdivisions=1, reverse_face_order=False, triangulate=False, uneven=False):
    builder = MeshBuilder()
    quads = [
        ((-0.6, -0.7, -1.0), (-0.6, 0.5, -1.0), (0.4, 0.5, -1.0), (0.4, -0.7, -1.0)),
        ((-0.6, -0.7, 0.0), (0.4, -0.7, 0.0), (0.4, 0.5, 0.0), (-0.6, 0.5, 0.0)),
        ((-0.6, -0.7, -1.0), (0.4, -0.7, -1.0), (0.4, -0.7, 0.0), (-0.6, -0.7, 0.0)),
        ((0.4, -0.7, -1.0), (0.4, 0.5, -1.0), (0.4, 0.5, 0.0), (0.4, -0.7, 0.0)),
        ((0.4, 0.5, -1.0), (-0.6, 0.5, -1.0), (-0.6, 0.5, 0.0), (0.4, 0.5, 0.0)),
        ((-0.6, 0.5, -1.0), (-0.6, -0.7, -1.0), (-0.6, -0.7, 0.0), (-0.6, 0.5, 0.0)),
    ]
    for quad in quads:
        builder.quad_grid(*quad, subdivisions, triangulate, uneven)
    seed = builder.index((-0.6, -0.7, 0.0))
    return make_mesh("Peg", builder.vertices, builder.faces, reverse_face_order), seed


def make_socket(subdivisions=1, reverse_face_order=False,
                x_bounds=(-0.6, 0.6), y_bounds=(-0.7, 0.7),
                triangulate=False, uneven=False):
    builder = MeshBuilder()
    x_low, x_high = x_bounds
    y_low, y_high = y_bounds
    quads = [
        ((-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (x_high, y_low, 0.0), (x_low, y_low, 0.0)),
        ((2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (x_high, y_high, 0.0), (x_high, y_low, 0.0)),
        ((2.0, 2.0, 0.0), (-2.0, 2.0, 0.0), (x_low, y_high, 0.0), (x_high, y_high, 0.0)),
        ((-2.0, 2.0, 0.0), (-2.0, -2.0, 0.0), (x_low, y_low, 0.0), (x_low, y_high, 0.0)),
        ((x_low, y_low, 0.0), (x_high, y_low, 0.0), (x_high, y_low, -1.2), (x_low, y_low, -1.2)),
        ((x_high, y_low, 0.0), (x_high, y_high, 0.0), (x_high, y_high, -1.2), (x_high, y_low, -1.2)),
        ((x_high, y_high, 0.0), (x_low, y_high, 0.0), (x_low, y_high, -1.2), (x_high, y_high, -1.2)),
        ((x_low, y_high, 0.0), (x_low, y_low, 0.0), (x_low, y_low, -1.2), (x_low, y_high, -1.2)),
    ]
    for quad in quads:
        builder.quad_grid(*quad, subdivisions, triangulate, uneven)
    seed = builder.index((x_low, y_low, 0.0))
    return make_mesh("Socket", builder.vertices, builder.faces, reverse_face_order), seed


def make_wedge(angle_degrees):
    angle = math.radians(angle_degrees)
    direction = Vector((math.cos(angle), 0.0, math.sin(angle)))
    vertices = [
        (0.0, -0.7, 0.0), (0.0, 0.7, 0.0), (1.0, 0.7, 0.0), (1.0, -0.7, 0.0),
        tuple(direction), tuple(direction + Vector((0.0, 1.4, 0.0))),
    ]
    return make_mesh("Wedge", vertices, [(0, 1, 2, 3), (0, 4, 5, 1)]), 0


def make_irregular():
    vertices = [
        (0.0, 0.0, 0.0), (1.0, 0.0, 0.1), (0.2, 1.1, -0.1),
        (0.1, 0.2, 1.0),
    ]
    return make_mesh("Irregular", vertices, [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]), 0


def make_neighboring_sockets():
    builder = MeshBuilder()
    x_cuts = (-2.0, -0.6, 0.6, 1.4, 2.6, 4.0)
    for x_low, x_high in zip(x_cuts, x_cuts[1:]):
        builder.quad_grid(
            (x_low, -2.0, 0.0), (x_high, -2.0, 0.0),
            (x_high, -0.7, 0.0), (x_low, -0.7, 0.0), 1)
        builder.quad_grid(
            (x_low, 0.7, 0.0), (x_high, 0.7, 0.0),
            (x_high, 2.0, 0.0), (x_low, 2.0, 0.0), 1)
    for x_low, x_high in ((-2.0, -0.6), (0.6, 1.4), (2.6, 4.0)):
        builder.quad_grid(
            (x_low, -0.7, 0.0), (x_high, -0.7, 0.0),
            (x_high, 0.7, 0.0), (x_low, 0.7, 0.0), 1)
    for x_low, x_high in ((-0.6, 0.6), (1.4, 2.6)):
        walls = [
            ((x_low, -0.7, 0.0), (x_high, -0.7, 0.0), (x_high, -0.7, -1.2), (x_low, -0.7, -1.2)),
            ((x_high, -0.7, 0.0), (x_high, 0.7, 0.0), (x_high, 0.7, -1.2), (x_high, -0.7, -1.2)),
            ((x_high, 0.7, 0.0), (x_low, 0.7, 0.0), (x_low, 0.7, -1.2), (x_high, 0.7, -1.2)),
            ((x_low, 0.7, 0.0), (x_low, -0.7, 0.0), (x_low, -0.7, -1.2), (x_low, 0.7, -1.2)),
        ]
        for wall in walls:
            builder.quad_grid(*wall, 1)
    seed = builder.index((-0.6, -0.7, 0.0))
    return make_mesh("NeighboringSockets", builder.vertices, builder.faces), seed


def make_slot():
    builder = MeshBuilder()
    quads = [
        ((-0.6, -0.7, 0.0), (-0.6, -0.7, -1.2), (-0.6, 0.7, -1.2), (-0.6, 0.7, 0.0)),
        ((-0.6, -0.7, -1.2), (-0.6, 0.7, -1.2), (0.6, 0.7, -1.2), (0.6, -0.7, -1.2)),
        ((0.6, -0.7, -1.2), (0.6, -0.7, 0.0), (0.6, 0.7, 0.0), (0.6, 0.7, -1.2)),
    ]
    for quad in quads:
        builder.quad_grid(*quad, 1)
    seed = builder.index((-0.6, -0.7, 0.0))
    return make_mesh("Slot", builder.vertices, builder.faces), seed


def assert_vector_close(actual, expected, tolerance=1e-9):
    if actual is None or (actual - expected).length > tolerance:
        delta = None if actual is None else tuple(actual[index] - expected[index] for index in range(3))
        distance = None if actual is None else (actual - expected).length
        raise AssertionError(
            f"expected {tuple(expected)}, got {tuple(actual) if actual is not None else None}, "
            f"delta {delta}, distance {distance}, tolerance {tolerance}"
        )


def assert_patch_directions(obj, seed, expected_directions):
    mesh_data = quicksnap_utils._mesh_fit_data(obj)
    seeds = quicksnap_utils._seed_polygons(mesh_data, 'POINTS', seed)
    patches = quicksnap_utils._candidate_patches(mesh_data, seeds)
    normals = [Vector(patch['normal']) for patch in patches]
    for expected in expected_directions:
        if not any(normal.dot(expected) > 0.999 for normal in normals):
            raise AssertionError(f"missing patch normal {tuple(expected)}; got {[tuple(n) for n in normals]}")


def synthetic_pair(axis, low, high, tolerance, center, inward=False):
    axis = np.array(axis, dtype=np.float64)
    low_normal = axis if inward else -axis
    high_normal = -axis if inward else axis
    return {
        'axis': axis,
        'low_patch': {'normal': low_normal},
        'high_patch': {'normal': high_normal},
        'low': low,
        'high': high,
        'mid': 0.5 * (low + high),
        'center': np.array(center, dtype=np.float64),
        'separation': high - low,
        # Exactly opposed: these fixtures are about ambiguity, not about taper.
        'opening_angle': math.pi,
        'tolerance': tolerance,
        # These fixtures exist to pin the ambiguity rules, which read `tolerance`.
        # Keeping the two equal leaves the clearance gate deciding exactly what it
        # decided before it was moved onto the precision-based value.
        'fit_tolerance': tolerance,
    }


def assert_overlapping_target_ambiguity_rejected():
    source = synthetic_pair((1, 0, 0), -0.5, 0.5, 0.05, (0, 0, 0))
    targets = [
        synthetic_pair((1, 0, 0), -0.5, 0.7, 0.05, (0, 1.0, 0), inward=True),
        synthetic_pair((1, 0, 0), -0.5, 0.7, 0.05, (0, 1.15, 0), inward=True),
    ]
    matches = quicksnap_utils._match_plane_pairs([source], targets, np.zeros(3))
    if matches:
        raise AssertionError("overlapping target uncertainty bands must be ambiguous")


def assert_competing_source_pairs_rejected():
    sources = [
        synthetic_pair((1, 0, 0), -0.5, 0.5, 0.01, (0, 0, 0)),
        synthetic_pair((1, 0, 0), -0.4, 0.6, 0.01, (0.1, 0, 0)),
    ]
    target = synthetic_pair((1, 0, 0), -0.5, 0.7, 0.01, (0.1, 0, 0), inward=True)
    matches = quicksnap_utils._match_plane_pairs(sources, [target], np.zeros(3))
    if matches:
        raise AssertionError("competing source slabs on one axis must be ambiguous")


def assert_valid_axis_survives_other_axis_ambiguity():
    sources = [
        synthetic_pair((1, 0, 0), -0.5, 0.5, 0.01, (0, 0, 0)),
        synthetic_pair((1, 0, 0), -0.4, 0.6, 0.01, (0.1, 0, 0)),
        synthetic_pair((0, 1, 0), -0.5, 0.5, 0.01, (0, 0, 0)),
    ]
    targets = [
        synthetic_pair((1, 0, 0), -0.5, 0.7, 0.01, (0.1, 0, 0), inward=True),
        synthetic_pair((0, 1, 0), -0.5, 0.7, 0.01, (0, 0.1, 0), inward=True),
    ]
    matches = quicksnap_utils._match_plane_pairs(sources, targets, np.zeros(3))
    translation = quicksnap_utils._solve_pair_translation(matches)
    assert_vector_close(Vector(translation), Vector((0.0, 0.1, 0.0)), tolerance=1e-9)


def assert_chained_source_axis_ambiguity_rejected():
    axes = [
        (math.cos(math.radians(angle)), math.sin(math.radians(angle)), 0.0)
        for angle in (0.0, 4.0, 8.0)
    ]
    sources = [synthetic_pair(axis, -0.5, 0.5, 0.001, (0, 0, 0)) for axis in axes]
    targets = [
        synthetic_pair(axis, -0.5, 0.7, 0.001, (0, 0, distance), inward=True)
        for axis, distance in zip(axes, (1.0, 2.0, 3.0))
    ]
    matches = quicksnap_utils._match_plane_pairs(sources, targets, np.zeros(3))
    if matches:
        raise AssertionError("chained near-parallel source constraints must all be ambiguous")


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def run_corner_case(subdivisions, reverse_face_order):
    clear_scene()
    peg, peg_seed = make_peg(subdivisions, reverse_face_order)
    socket, socket_seed = make_socket(subdivisions, reverse_face_order)
    assert_patch_directions(peg, peg_seed, (
        Vector((1, 0, 0)), Vector((-1, 0, 0)),
        Vector((0, 1, 0)), Vector((0, -1, 0)),
        Vector((0, 0, 1)), Vector((0, 0, -1)),
    ))
    assert_patch_directions(socket, socket_seed, (
        Vector((1, 0, 0)), Vector((-1, 0, 0)),
        Vector((0, 1, 0)), Vector((0, -1, 0)),
        Vector((0, 0, 1)),
    ))
    contact = socket.matrix_world @ socket.data.vertices[socket_seed].co
    return quicksnap_utils.compute_precision_fit(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True),
        peg.name, 'POINTS', peg_seed,
        socket.name, 'POINTS', socket_seed,
        contact,
    )


def run_uneven_density_case():
    clear_scene()
    peg, peg_seed = make_peg(7, triangulate=True, uneven=True)
    socket, socket_seed = make_socket(11, triangulate=True, uneven=True)
    return run_pair(peg, peg_seed, socket, socket_seed)


def run_slot_case():
    clear_scene()
    peg, peg_seed = make_peg()
    slot, slot_seed = make_slot()
    contact = slot.matrix_world @ slot.data.vertices[slot_seed].co
    return quicksnap_utils.compute_precision_fit(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True),
        peg.name, 'POINTS', peg_seed,
        slot.name, 'POINTS', slot_seed,
        contact,
    )


def run_pair(source, source_seed, target, target_seed):
    contact = target.matrix_world @ target.data.vertices[target_seed].co
    return quicksnap_utils.compute_precision_fit(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True),
        source.name, 'POINTS', source_seed,
        target.name, 'POINTS', target_seed,
        contact,
    )


def run_wedge_case(angle_degrees):
    clear_scene()
    peg, peg_seed = make_peg()
    wedge, wedge_seed = make_wedge(angle_degrees)
    return run_pair(peg, peg_seed, wedge, wedge_seed)


def run_organic_case():
    clear_scene()
    source, source_seed = make_irregular()
    target, target_seed = make_irregular()
    return run_pair(source, source_seed, target, target_seed)


def run_width_case(x_bounds, y_bounds):
    clear_scene()
    peg, peg_seed = make_peg()
    socket, socket_seed = make_socket(x_bounds=x_bounds, y_bounds=y_bounds)
    return run_pair(peg, peg_seed, socket, socket_seed)


def run_stale_index_case():
    clear_scene()
    peg, _ = make_peg()
    socket, socket_seed = make_socket()
    contact = socket.matrix_world @ socket.data.vertices[socket_seed].co
    return quicksnap_utils.compute_precision_fit(
        bpy.context,
        SimpleNamespace(ignore_modifiers=True),
        peg.name, 'POINTS', 10_000,
        socket.name, 'POINTS', socket_seed,
        contact,
    )


def run_neighboring_socket_case():
    clear_scene()
    peg, peg_seed = make_peg()
    sockets, socket_seed = make_neighboring_sockets()
    return run_pair(peg, peg_seed, sockets, socket_seed)


def run_non_uniform_scale_case(apply_scale):
    clear_scene()
    peg, peg_seed = make_peg()
    socket, socket_seed = make_socket()
    for obj in (peg, socket):
        obj.scale = (2.0, 0.5, 1.5)
        obj.select_set(True)
    if apply_scale:
        bpy.context.view_layer.objects.active = peg
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()
    return run_pair(peg, peg_seed, socket, socket_seed)


def run_modifier_case(ignore_modifiers):
    clear_scene()
    peg, peg_seed = make_peg()
    slot, slot_seed = make_slot()
    high_wall = slot.vertex_groups.new(name="HighWall")
    high_wall.add(
        [vertex.index for vertex in slot.data.vertices if vertex.co.x > 0.59],
        1.0,
        'REPLACE',
    )
    modifier = slot.modifiers.new(name="WidenSlot", type='DISPLACE')
    modifier.direction = 'X'
    modifier.strength = 0.2
    modifier.mid_level = 0.0
    modifier.vertex_group = high_wall.name
    bpy.context.view_layer.update()
    contact = slot.matrix_world @ slot.data.vertices[slot_seed].co
    return quicksnap_utils.compute_precision_fit(
        bpy.context,
        SimpleNamespace(ignore_modifiers=ignore_modifiers),
        peg.name, 'POINTS', peg_seed,
        slot.name, 'POINTS', slot_seed,
        contact,
    )


def make_tapered_pair(taper_degrees=8.0):
    """A drafted peg and its drafted socket -- the shape every printed part has."""
    slope = math.tan(math.radians(taper_degrees))

    def box(x_low, x_high, y_low, y_high, depth):
        inset = slope * depth
        return [
            (x_low + inset, y_low + inset, -depth),
            (x_high - inset, y_low + inset, -depth),
            (x_high - inset, y_high - inset, -depth),
            (x_low + inset, y_high - inset, -depth),
            (x_low, y_low, 0.0), (x_high, y_low, 0.0),
            (x_high, y_high, 0.0), (x_low, y_high, 0.0),
        ]

    peg = make_mesh(
        "TaperedPeg", box(-0.6, 0.4, -0.7, 0.5, 1.0),
        [(0, 3, 2, 1), (4, 5, 6, 7),
         (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    walls = box(-0.6, 0.6, -0.7, 0.7, 1.2)
    socket = make_mesh(
        "TaperedSocket", walls[4:] + walls[:4],
        [(1, 5, 4, 0), (2, 6, 5, 1), (3, 7, 6, 2), (0, 4, 7, 3)],
    )
    bpy.context.view_layer.update()
    return peg, 4, socket, 0


def assert_drafted_connectors_centre():
    """Draft is not a defect, it is how the part comes out of the mould.

    Precision fit demanded the two walls be within 10 degrees of parallel, so a
    connector with any draft on it was invisible and the fit silently did nothing.
    Lock and key's 95-degree bar plus measuring each wall where it crosses the axis
    through the snapped point -- a plane offset is not a width on a tapered wall --
    is what makes these mate.
    """
    clear_scene()
    peg, peg_seed, socket, socket_seed = make_tapered_pair(8.0)
    contact = np.array(socket.matrix_world @ socket.data.vertices[socket_seed].co)
    data = quicksnap_utils._mesh_fit_data(peg)
    seeds = quicksnap_utils._seed_polygons(data, 'POINTS', peg_seed)
    openings = [
        math.degrees(pair['opening_angle'])
        for pair in quicksnap_utils._plane_pairs(
            quicksnap_utils._fit_walls(data, seeds), contact)
        if abs(float(pair['axis'][0])) > 0.99
    ]
    if not openings or min(openings) > 170.0:
        raise AssertionError(
            f"the fixture is not drafted enough to prove anything: {openings}"
        )
    assert_vector_close(
        run_pair(peg, peg_seed, socket, socket_seed),
        Vector((0.1, 0.1, 0.0)),
        tolerance=1e-6,
    )


def assert_fragmented_walls_are_rebuilt():
    """A finely cut, slightly wobbly wall must still read as one wall.

    Lock and key learned this first: the growth step's offset allowance scales with
    edge length, so a wall cut this fine stops merging on sub-millimetre wobble and
    arrives as dozens of fragments. To the pairing rules those are not a wall at
    all, and precision fit simply gave up on any decimated or sculpted part.
    """
    clear_scene()
    peg, peg_seed = make_peg()
    socket, socket_seed = make_socket(subdivisions=8)
    moved = 0
    for vertex in socket.data.vertices:
        if abs(vertex.co.x) > 0.59 and -1.19 < vertex.co.z < -0.01:
            vertex.co.x += 0.002 * (vertex.index % 3 - 1)
            moved += 1
    if not moved:
        raise AssertionError("the fixture wobbled nothing")
    socket.data.update()
    bpy.context.view_layer.update()
    contact = np.array(socket.matrix_world @ socket.data.vertices[socket_seed].co)
    peg_data = quicksnap_utils._mesh_fit_data(peg)
    peg_seeds = quicksnap_utils._seed_polygons(peg_data, 'POINTS', peg_seed)
    socket_data = quicksnap_utils._mesh_fit_data(socket)
    socket_seeds = quicksnap_utils._seed_polygons(socket_data, 'POINTS', socket_seed)

    def centres_x(gather):
        matches = quicksnap_utils._match_plane_pairs(
            quicksnap_utils._plane_pairs(gather(peg_data, peg_seeds), contact),
            quicksnap_utils._plane_pairs(gather(socket_data, socket_seeds), contact),
            contact,
        )
        return any(abs(float(match['axis'][0])) > 0.99 for match in matches)

    # Fragments do not merely go unrecognised, they actively delete the axis: each
    # one pairs with each fragment opposite, and a candidate whose two best targets
    # tie is discarded as ambiguous. Measured here: 55 patches, 600 competing X
    # pairs, no X match at all.
    if centres_x(quicksnap_utils._candidate_patches):
        raise AssertionError("the fixture is not fragmented; the test proves nothing")
    if not centres_x(quicksnap_utils._fit_walls):
        raise AssertionError("merging did not rebuild the wobbly wall")
    # The rebuilt plane is the area-weighted average of the fragments, so it lands
    # within a fraction of the wobble rather than exactly on it: 8e-6 recovered
    # from a wobble of 0.002.
    assert_vector_close(
        run_pair(peg, peg_seed, socket, socket_seed),
        Vector((0.1, 0.1, 0.0)),
        tolerance=1e-4,
    )


def run_snug_clearance_case():
    clear_scene()
    peg, peg_seed = make_peg()
    # A printed fit, not a modelling allowance: 1% on a 1-unit peg. The flatness
    # allowance is 0.5% of a patch's extent and was being used as the clearance
    # test, so it demanded roughly twice this and refused every snug connector.
    socket, socket_seed = make_socket(x_bounds=(-0.61, 0.40), y_bounds=(-0.71, 0.50))
    return run_pair(peg, peg_seed, socket, socket_seed)


def main():
    assert_overlapping_target_ambiguity_rejected()
    print("target ambiguity: PASS")
    assert_competing_source_pairs_rejected()
    print("source ambiguity: PASS")
    assert_valid_axis_survives_other_axis_ambiguity()
    print("partial ambiguity: PASS")
    assert_chained_source_axis_ambiguity_rejected()
    print("chained ambiguity: PASS")
    coarse_fit = None
    for subdivisions, reverse_face_order in ((1, False), (8, False), (8, True)):
        fit = run_corner_case(subdivisions, reverse_face_order)
        assert_vector_close(fit, Vector((0.1, 0.1, 0.0)), tolerance=1e-7)
        if coarse_fit is None:
            coarse_fit = fit
        print(f"corner subdivisions={subdivisions} reverse={reverse_face_order}: PASS")
    uneven_fit = run_uneven_density_case()
    assert_vector_close(uneven_fit, coarse_fit, tolerance=1.4e-9)
    if uneven_fit.z != 0.0:
        raise AssertionError(f"unconstrained Z changed: {uneven_fit.z}")
    print("uneven triangulation: PASS")
    assert_vector_close(run_slot_case(), Vector((0.1, 0.0, 0.0)), tolerance=1e-7)
    print("slot: PASS")
    assert run_wedge_case(120) is None
    assert run_wedge_case(150) is None
    print("wedges: PASS")
    assert run_organic_case() is None
    print("organic: PASS")
    assert run_width_case((-0.6, 0.4), (-0.7, 0.5)) is None
    assert run_width_case((-0.6, 0.3), (-0.7, 0.4)) is None
    print("impossible fits: PASS")
    assert run_stale_index_case() is None
    print("stale index: PASS")
    assert_vector_close(
        run_snug_clearance_case(), Vector((-0.005, -0.005, 0.0)), tolerance=1e-7
    )
    print("snug printed clearance: PASS")
    assert_fragmented_walls_are_rebuilt()
    print("fragmented walls are rebuilt: PASS")
    assert_drafted_connectors_centre()
    print("drafted connectors centre: PASS")
    assert_vector_close(run_neighboring_socket_case(), Vector((0.1, 0.1, 0.0)), tolerance=1e-7)
    print("neighboring socket: PASS")
    scaled = run_non_uniform_scale_case(apply_scale=False)
    applied = run_non_uniform_scale_case(apply_scale=True)
    assert_vector_close(scaled, Vector((0.2, 0.05, 0.0)), tolerance=1e-7)
    assert_vector_close(applied, scaled, tolerance=1e-7)
    print("non-uniform scale: PASS")
    assert_vector_close(run_modifier_case(ignore_modifiers=False), Vector((0.2, 0.0, 0.0)), tolerance=1e-7)
    assert_vector_close(run_modifier_case(ignore_modifiers=True), Vector((0.1, 0.0, 0.0)), tolerance=1e-7)
    print("modifiers: PASS")
    print("precision_fit_regression: PASS")


if __name__ == "__main__":
    main()
