# Disconnected-Floor End-Face Rotation Design

**Date:** 2026-08-23

## Problem

Lock and key supports the natural rotation gesture of clicking the moving connector's end face and the stationary socket's floor. The current implementation only reaches that face-to-face branch after topology-local connector extraction has produced two independent wall pairs on both parts. A socket floor that is a separate mesh island from its side walls therefore produces two source pairs and zero target pairs, and rotation is refused before the clicked face normals can constrain insertion orientation.

The user gesture is valid. Direct floor-to-wall edge connectivity is not a supported-shape requirement.

## Goals

- Mate a centered peg-end click to a centered socket-floor click when the floor is topologically disconnected from the side walls.
- Preserve the existing fail-closed rotation, clearance, ambiguity, insertion, and surroundings checks.
- Preserve explicit wall-click semantics and translation-only behavior.
- Avoid deriving spin from the two clicked normals alone.
- Avoid a scene-wide or persistent spatial index for this exceptional path.
- Make failure and latency diagnosable from MateSnap's console output.

## Non-goals

- Supporting round, organic, noisy, or incomplete connectors.
- Replacing topology-local connector discovery.
- Weakening `_connector_side_pairs()` or shared patch-growth rules.
- Adding iterative alignment or ICP.
- Choosing the nearest cavity when multiple compatible cavities are present.
- Changing Precision fit.

## Root cause

The ordinary connector search is intentionally topology-local. With a disconnected floor it cannot traverse to the socket walls and returns no target pairs. `_rotation_candidates()` then requires two pairs on both sides before it classifies an unanchored face-to-face gesture. The failure is therefore an ordering and discovery-boundary defect, not inaccurate clicking.

## Selected approach

Add one private cold-path spatial recovery adapter immediately before rotation candidate enumeration. Ordinary connector discovery and translation run unchanged. Recovery is eligible only for an unanchored face-to-face rotation gesture where exactly one side already has a trustworthy two-axis connector frame and the other side lacks one.

The adapter recovers one coherent flat-sided frame for the missing side, then hands its pairs to the existing rotation pipeline. It is not a second rotation solver.

This approach is preferred over:

- **Normals-only rotation:** clicked normals constrain insertion direction but leave spin underdetermined.
- **Globally spatial connector discovery:** this would admit unrelated body geometry into ordinary wall clicks and translation-only solves.
- **Weakening topology locality:** wall clicks deliberately use locality to pin the intended feature.

## Eligibility

Recovery runs only when all of these conditions hold:

1. Rotation is enabled.
2. The direct topology-local solve has not produced a valid mate.
3. Both clicked logical patches are clean and planar and provide finite patch normals from the exact mesh representation being solved.
4. Neither click anchors a surviving rotation-compatible wall pair.
5. Exactly one side has at least two independent, rotation-compatible lateral wall pairs after ordinary pruning.
6. Those known-side pair axes are compatible with its clicked end-face normal.
7. The missing side has fewer than two independent pairs.

The helper is symmetric: either source or target may be the missing side. Peg/socket role remains a geometric property rather than a click-order property.

A clicked end/base pair must not be mistaken for a lateral anchored wall pair. Eligibility is determined from pairs that can participate in the mate after the ordinary rotation pruning rules.

## Spatial recovery

### Search volume

The search volume is a world-space prism or cylinder centered on the missing side's clicked anchor and aligned to its clicked face normal. Its lateral and axial dimensions are derived from the known connector's measured pair widths, wall extents, end-face relationship, and existing fit/flatness tolerances. No fixed Blender-unit radius is introduced.

Candidate geometry must intersect the finite search volume. A centroid-only test is insufficient because a long socket wall can cross the volume while its centroid lies far away.

Candidate geometry must also:

- lie on the connector-interior side of the clicked floor within tolerance;
- overlap the shallow axial band where walls rise from that floor;
- remain below a source-derived size/reach ratio ceiling so a small key cannot discover a distant body-sized cavity.

All distances, extents, planes, and normals are evaluated in the existing world-space mesh-fit representation so non-uniform object transforms remain valid.

### Candidate patches and pairs

Spatial and normal filtering happens before coplanar merging. Each surviving planar patch is grown once and deduplicated by its logical patch identity. Candidate patches retain the ordinary requirements: finite nonzero area/extent, planarity, and cleanliness.

Recovered walls must be orientation-compatible with the known connector without assuming perfectly perpendicular walls. Compare rotation-invariant relationships:

- wall-normal and pair-axis relationships to each side's clicked face normal;
- opening angle and taper/depth-hint relationships;
- pair widths and relevant extents;
- opposite peg/socket roles and non-negative clearance under existing tolerances.

Once a bounded candidate wall set exists, reuse `_connector_side_pairs()` for opposition, canonical direction, anchor-span, separation, taper, and tolerance calculations. Do not duplicate those rules.

### Coherent frame hypotheses

Nearby patches are not flattened into one unrestricted pair list. Recovered pairs are grouped into coherent frame hypotheses. Each frame must have:

- at least two independent lateral axes under the existing rank threshold;
- a common inferred lateral center near the clicked anchor;
- compatible axial extent relative to the clicked floor;
- dimensions, taper, role, and clearance compatible with the known-side frame.

This prevents walls from separate cavities, a body shell, or unrelated panels being combined into a synthetic connector.

Frames are deduplicated geometrically using measured plane normals, offsets, centers, and existing plane tolerances—not polygon IDs or byte equality. Coplanar fragmented walls may describe one frame. Two dimensionally identical cavities at different centers remain distinct.

Recovery succeeds only when exactly one measured-distinct compatible frame remains. Zero frames or multiple frames return no result; it never chooses nearest, largest, lowest polygon ID, or smallest rotation.

## Region extraction and bounds

Disconnected walls outside a partial extraction can produce a false absence without touching the extraction boundary. Therefore, when spatial recovery is eligible on partial region data, it must request widening through the existing provider retry mechanism and reach full coverage before concluding that no frame exists. This cost is limited to the exceptional fallback.

Recovery remains bounded:

- one spatial/normal prefilter over extracted geometry;
- each unique patch grown once;
- area, side, normal, and dimension filters applied before pairwise pairing;
- existing connector-pair and rotation-candidate caps retained;
- no hover-time recovery;
- no persistent scene-wide index.

The valid disconnected-floor path must not continue the current repeated doomed 2-to-30-hop topology searches after eligibility is established.

## Existing solver remains authoritative

Recovered pairs enter the unchanged validation pipeline:

1. ordinary rotation-pair pruning;
2. mapping enumeration and proper Kabsch rotation;
3. clicked face-to-face opposition;
4. centering and clearance validation;
5. insertion half-space guard;
6. measured seating equivalence and fail-closed ambiguity handling;
7. surroundings veto for equivalent seatings.

The clicked normals constrain insertion alignment only. They never generate spin, and one recovered lateral pair remains insufficient.

Explicit anchored wall clicks never invoke spatial recovery and continue to pin correspondence exactly as before.

## Diagnostics

The refusal report must state:

- why spatial recovery was or was not eligible;
- whether extraction widened to full coverage;
- polygons and patches considered spatially;
- walls surviving side, normal, and dimension filters;
- opposed pairs and independent axes recovered;
- coherent frame hypothesis count;
- whether refusal was absence, incompatibility, pair/candidate budget, or multiple measured-distinct frames.

After recovery runs, the old generic `rotation needs two independent wall pairs` message alone is insufficient.

## Regression coverage

The headless Lock-and-key suite must add:

1. A socket whose floor duplicates its boundary vertices and shares no topology with its walls. Before recovery, direct extraction must demonstrate two usable source pairs and zero target pairs.
2. A successful centered end-face/floor mate from an arbitrary three-dimensional starting rotation, verifying opposed clicked faces, lateral centering, preserved insertion depth, and finite transform.
3. A drafted/tapered disconnected-floor variant.
4. Reversed moving peg/socket order, proving symmetric missing-side recovery.
5. An anchored wall-click test that makes recovery raise if invoked and verifies the existing delta is unchanged.
6. Rotation-disabled and missing/invalid-click-normal cases that refuse without recovery.
7. A one-axis recovered frame that remains insufficient.
8. Remote, behind-floor, body-shell, and curved/faceted decoys that are rejected.
9. Separate nearby walls that cannot combine into a cross-cavity hybrid.
10. Two compatible but differently located cavities that fail closed as multiple frames.
11. Fragmented coplanar walls that deduplicate to one frame.
12. Region-first versus forced-full delta equivalence, including a long wall crossing the region boundary.
13. Non-uniform object transforms.
14. The existing rectangular-peg-in-square-socket ambiguity refusal.
15. Existing surroundings-veto behavior on recovered pairs.
16. Distinct diagnostic reasons for absent and ambiguous recovery.

Run both Lock-and-key and Precision-fit suites. A manual smoke test on the real figurine key/lock pair remains required before any release claim.

## Release

This is a bug fix. Bump `bl_info['version']` from `2.2.0` to `2.2.1`, promote the CHANGELOG heading, and build `releases/MateSnap-2.2.1.zip`. Never overwrite the existing `2.2.0` archive.
