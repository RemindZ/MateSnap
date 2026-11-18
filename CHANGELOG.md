# Changelog

## 2.3.1

### Fixed
- **Rounded connectors are squared up when rotation is on.** Clicking the flat end of a round peg and the floor of its hole used to refuse whenever the key was not already lying within 5 degrees of the socket -- a saber lying 97 degrees off its hand's socket refused although "Rotate key to match lock" was on. With rotation on, the key is now turned by the smallest rotation that lays its end face flat on the floor, then slid in; its spin about its own axis is kept as you placed it, and a spin that buries the key in the lock is still refused with the depth. With rotation off, the 5-degree rule stands and the refusal now says to turn rotation on.
- **Pegs with one flat and one rounded side seat by their end faces.** A peg-end + socket-floor click on a D-shaped or oval connector refused "spatial recovery ineligible: the local wall axes are ambiguous". When the walls around both clicked faces are facets of a curve, the end-face seating above now takes the mate.
- **A tilted key is no longer slid into its socket crooked.** End-face clicks on a key tilted up to 25 degrees about one of its wall pairs could be "mated" by sliding alone, leaving the key as tilted as it stood and cutting through the lock -- the side walls that were matched say nothing about a tilt about their own axis. A slide now requires the two clicked faces to rest against each other within 10 degrees, as the rotation path already did; otherwise rotation turns the key into line, or with rotation off the refusal names the angle. This was in every release up to 2.2.1.

## 2.3.0

### Added
- **Round pegs seat in round holes.** Click the flat end of a round peg and the flat floor of its hole, and Lock and key slides the peg in, centred on the hole, without rotating it -- your placement keeps its orientation, whatever the rotation setting. This used to refuse with "rounded connectors are not supported". It fails closed: the two faces must already lie within 5 degrees of flat against each other, and a peg that would end up inside the lock's material -- too fat for the hole, or turned the wrong way about a leaning post -- is refused with how deep it would sit against the allowance.

### Fixed
- **Square pegs no longer refuse as ambiguous just because the scene sits far from the world origin.** Lock and key decides whether a peg's four spins seat the walls identically by comparing where each spin leaves the mated walls. It compared the wall planes' offsets from the world origin, so the few hundredths of a degree by which a sculpt's walls always differ were multiplied by the parts' distance from the origin. A kit parked ~330 units out refused peg-tip + socket-floor clicks with "several rotations fit differently" every time, while the same parts mated at the origin. The planes are now compared at the walls themselves.
- **Rotation refusals carry their numbers.** "Several rotations fit differently" now lists the seatings' angles and how far apart they leave a mated wall against its tolerance. "No rotation seats the key" names the closest uncentred seating's failing check with its values, such as the anchor shift against the relocation cap. When the centred picks and the exact-click retry both refuse, the refusal log records both reasons instead of only the retry's.

## 2.2.1

### Fixed
- **Centered peg-end and socket-floor clicks now rotate across disconnected floor topology.** Some production sockets model the floor as a separate mesh island from their side walls. Lock and key now recovers one bounded, coherent wall frame around that floor and feeds it through the existing clearance, ambiguity, insertion, and surroundings checks. It still refuses underconstrained, overlapping, multiple-cavity, curved, or otherwise ambiguous geometry rather than guessing a spin.
- Disconnected topology searches stop as soon as their reachable patch set is saturated instead of repeating the same failed traversal through all 30 hop limits.

## 2.2.0

### Changed
- MateSnap now requires Blender 5.0 or newer; the obsolete legacy shader path has been removed.

## 2.1.0

### Added
- **The surroundings now pick the spin.** A square-ish peg fits its socket
  four ways and the connector walls cannot say which the sculptor meant, so
  the mate followed however you had roughly placed the part -- right when
  you had parked it within a quarter-turn, wrong otherwise. Rotation now
  surveys the area beside the clicks: samples of the key's surface near its
  click are tested against the lock's surface near its click under every
  candidate seating, and any seating that drives the surroundings into the
  other part's material is thrown out as physically impossible -- the fin
  lands in its bay, not on the boss next to it. When the surroundings have
  nothing to say (truly symmetric parts), the nearest rotation to your
  placement still decides, exactly as before; the survey can veto seatings
  but never refuse a mate. Every mate where the survey ruled something out
  logs one line saying how many seatings were offered, how many the
  surroundings eliminated, and how deep the worst overlap was.

## 2.0.7

### Added
- **Top-of-peg + floor-of-socket clicks now align the mate.** When neither
  click lands on a connector side wall, the clicked faces themselves carry
  the intent: rotation keeps only candidates that bring the clicked key face
  to rest against the clicked lock face, which pins the insertion alignment
  and discards every upside-down seating -- the job wall anchors do, done by
  the faces. This is the natural kit gesture (both faces point at the other
  part, so peg top, parting plane, floor and mouth rim all work), and it is
  exactly what the field kept clicking while the solver demanded side walls.

### Fixed
- **"Choose the smallest equivalent rotation" now fires on real parts.** Two
  seatings counted as equivalent only when byte-identical, which sculpted
  geometry never is -- so a near-square peg's interchangeable spins were
  refused as "several rotations fit differently" instead of letting the
  user's rough placement choose. Equivalence is now measured: seatings whose
  every mated wall plane matches within the flatness tolerance it was
  measured at are interchangeable, and the smallest rotation wins. A
  rectangular peg in a square socket still differs far beyond tolerance,
  still refuses, and is still resolvable by clicking the two mating walls.

## 2.0.6

### Fixed
- **Automatic rotation now follows the clicked walls.** Rotation enumerates
  which key wall maps to which lock wall, and the licence that lets a wall
  click pair with a floor click (which only the lock's own clicked-face
  normal can make safe) was granted whenever that normal was available --
  in the GUI, always. The enumeration was therefore free to ignore the
  clicks even when both landed on walls, and on a near-square connector
  (field case: a 13.5965 x 13.5958 peg) every 90-degree seating survived to
  the ambiguity tie, so the mate was refused however the user clicked. Wall
  clicks now pin the mapping: click a side wall of the key's connector and
  the lock wall it should rest against, and those two walls mate.
- **Rotation refusals name their cause.** "No rotation seats the key without
  penetrating the lock" covered five different failure gates -- including
  the field case where no candidate was ever enumerated because neither
  click landed on a connector side wall (a peg's end face or a socket's
  floor names no wall). That case now says to click a side wall; a clicked
  wall that fits nothing, and two clicked walls that cannot mate each
  other, say so; and the generic message now counts the candidates each
  gate discarded. The rotation-off nudge and the ambiguity refusal teach
  the same gesture.

## 2.0.5

### Fixed
- **A connector's extra wall pairs no longer veto its own mate.** A sculpted
  connector matches more pairs than a rigid translation can balance -- corner
  bevels, taper segments, near-parallel duplicates of a wall -- and the solver
  demanded every one of them centre within flatness tolerance at once, which
  refused honest parts on two kits ("4 matched wall pair(s) could not be
  centred within tolerance"). Centring now solves on the largest mutually
  consistent pairs, ordered by each pair's smaller wall, and pairs left out
  may sit un-centred in their designed clearance -- but must still clear
  their walls under the chosen seat, so a genuine clash still refuses. When
  centring does refuse, the reason now lists every matched pair's gaps,
  imbalance tolerance and anchor shift, so the log names which check refused
  instead of one sentence covering three causes.

## 2.0.4

### Fixed
- **Clicking key and lock on the same part no longer freezes Blender.** The
  mistake now refuses instantly with its own message -- "a mate moves the
  whole object, so it cannot mate with itself" -- instead of paying two full
  extractions, a wall search that misread identical walls as a taper
  mismatch, and a refusal report that surveyed the same dense part twice.
  The report's widening trace was the bulk of the stall on any refusal, not
  just this one: it re-ran an unbudgeted quadratic pairing at every radius,
  including identical re-runs after the reach stopped growing. It now pairs
  only the 40 largest walls per radius and ends at saturation, which cut a
  19-second refusal on a 200-face test part to instant; dense sculpts gain
  proportionally more.

## 2.0.3

### Fixed
- **Sculpt-dense fillets no longer swallow the connector walls they border.**
  Patch growth only compared each face with its neighbour, so once a fillet
  was tessellated finer than five degrees per face the crawl walked the whole
  arc, failed the flatness gate, and returned nothing -- the fillet became an
  impassable moat around the connector, and on denser sculpts the flat walls
  themselves drowned in the failed component. This is why a rectangular
  socket with generously rounded fillets reported "0 raw patches" at the
  click. Growth is now bounded to five degrees of drift from the clicked
  face's own normal, which never splits a flat wall (their normals wobble by
  fractions of a degree) and turns a dense fillet into a dozen strip patches
  at most -- stepping stones again. The search reach rises from ten hops to
  thirty to pay for crossing them. Genuinely round connectors still refuse,
  at every tessellation density, via the existing curve test.

## 2.0.2

### Fixed
- **A rounded connector is now named as the refusal, not talked around.** A
  curved peg or socket never survives flat-patch growth, so it was invisible
  to every refusal: clicking its side said "click flat on a connector wall"
  and clicking the flat face beside it said "click the side of the peg" --
  circular advice with no exit. Failed growths now leave a record, and both
  refusals report the curved region beside the click (faces, span) and say
  plainly that rounded connectors are not supported. The diagnostic report
  lists the nearest failed growths, and the widening trace prints openings
  widest-first, since "does a straighter pair ever come into reach" is the
  question it exists to answer.

## 2.0.1

### Fixed
- **Lock and key refusals on real kit parts are now diagnosable from the log
  alone.** A click whose flat growth fails now reports what it grew -- faces
  swallowed, span, and how far it bowed past the flatness allowance -- instead
  of a bare "0 raw patches", and the refusal one-liner carries the same
  numbers. The report also prints the anchor's distance from the clicked
  face's centre, every opposed wall pair rather than the first six, and a
  per-radius widening trace, so a pair that only exists beyond where the
  search stopped is visible in the log.

## 2.0.0

### Changed
- Renamed to MateSnap, formerly QuickSnap-High-Poly. The history below is
  unchanged under the old name.

## 1.8.18

### Fixed
- **The target preview dot shows where the mate will actually anchor.** With
  pick centring on, both clicks anchor at the middle of their walls -- but the
  hover dot was drawn at the raw hit under the cursor, so the shown point and
  the used point disagreed. Once the cursor rests for a fifth of a second the
  dot now slides to the hovered wall's centre. It is computed at rest rather
  than per move, so sweeping never stalls, and the extraction it needs is the
  same one the click would pay -- aiming now pre-pays the click.

## 1.8.17

### Fixed
- **The picker opens instantly on dense scenes.** Starting Lock and key ran a
  preview raycast before the modal was live, and the first ray against a dense
  part makes Blender build its internal picking BVH -- seconds of dead viewport
  between the hotkey and the crosshair. The modal refreshes the preview on
  every mouse move and again on click before using it, so that eager raycast
  bought nothing; it is gone, and the one-time build now happens under the
  first mouse move. The opening and the first hover both report their time to
  the console when they exceed a quarter second.

## 1.8.16

### Fixed
- **The cold click extracts a region around the cursor, not the whole part.**
  Lock and key now reads a sphere around the click -- starting at 5% of the
  part's size and widening whenever any patch it needs got cut open by the
  sphere, so every measurement still comes from whole patches and the mate is
  identical to full coverage (regression-tested for delta equality). Lock-key
  extraction also stops reading Blender's edge tables entirely, deriving edge
  connectivity from the corner table instead; that alone trims the fallback
  that still covers clicks on large flat faces, which by design widen to the
  whole part. Measured at 1.8M triangles: 1.75s cold before, 1.10s after --
  the remaining cost is Blender's bulk coordinate and corner reads themselves.

## 1.8.15

### Fixed
- **Dense parts are no longer re-extracted for every mate.** The stage timers
  named the stall: 6.6s to extract a 5.5M-polygon figure, paid again on every
  mate, plus 2.9s for the unmoved base it assembles onto. Extraction is now
  cached across mates and revalidated bit-for-bit against the live mesh --
  coordinates and connectivity are re-read and compared, so an edit that keeps
  every element count (sculpting does) still rebuilds. An unmoved part reuses
  everything, grown patches included, at only the validation cost; a moved part
  additionally pays one transform pass.
- **The solve no longer spends seconds regrouping walls.** Merging coplanar
  patches ran a Python loop of every patch against every group once per search
  radius per click -- ~1800 patches against ~240 groups on the reported base.
  Each patch now tests all groups in one numpy pass.
- **The could-not-centre refusal names 'Centre picks' when it is off.**
  Far-apart clicks are exactly what pick centring absorbs, and the reported
  refusal (5 matched pairs, centring past tolerance) had it disabled -- the
  message now says to turn it back on instead of only describing the symptom.

## 1.8.14

### Fixed
- **A slow pick now names its stage in the console.** A report of "the first
  click takes forever" could not be pinned to a stage from here, and users'
  models are proprietary, so the log has to do the measuring: mesh extraction,
  clicked-wall growth, neighbourhood growth, raw-mesh picking tree, and the
  mate solve each print a warning with their time and size whenever they exceed
  a quarter second, plus a total for anything they do not cover.

## 1.8.13

### Fixed
- **A click on the mouth chamfer names its wall.** Clicking the chamfered lip of
  a socket left the anchor laterally outside the walls, so the real wall pair
  could not span the click and only the chamfer's own ~100-degree pair survived:
  a fitting, correctly rotated part was refused for "a chamfer or a taper rather
  than the straight wall" -- or, when a perpendicular pair still matched, silently
  seated half a chamfer off. Such a click is now promoted to the wall the chamfer
  softens (part of the pick-centring preference); when more than one wall fits
  differently, the mate still fails closed.
- **First Lock and key click no longer stalls on dense parts.** Growing the
  clicked wall walked polygon by polygon in Python -- 6.5 seconds on a 200k-face
  wall, minutes on a real figurine half -- and fingerprinting the click's
  neighbourhood added seconds more. The growth now walks whole frontiers as
  numpy batches (0.19s on the same wall) and the fingerprint samples a bounded
  stride of the neighbourhood instead of every polygon.
- **No more console spam when the snap point is behind the view.** The 2D draw
  callback subscripted a projection that is None for points behind the view
  plane, throwing a TypeError every redraw.

## 1.8.12

### Fixed
- **Drafted connectors centre.** Precision fit demanded the two walls be within
  10 degrees of parallel, so any part with draft on it -- which is every printed
  part -- was invisible and the fit silently did nothing. The bar is now 95
  degrees, the one that separates opposed walls from corners. Two things follow:
  each wall is measured where it crosses the axis *through the snapped point*
  rather than by its plane offset (identical arithmetic when the walls are
  parallel, but a plane offset is not a width on a tapered wall), and the two
  tapers must agree within 10 degrees so a straight wall cannot centre against a
  chamfered lead-in.

## 1.8.11

### Fixed
Post-snap precision fit now uses Lock and key's wall-finding, and inherits the
two fixes that came out of it:

- **Fragmented walls are rebuilt.** A wall that arrives triangulated, decimated
  or sculpted comes back as dozens of fragments whose normals differ by a
  fraction of a degree, and they do not merely go unrecognised -- each pairs with
  each fragment opposite, and the matcher discards a candidate whose two best
  targets tie, so the axis is deleted outright. Measured on a socket wall cut
  into 64 quads with 0.002 of wobble: 55 patches, 600 competing pairs on that
  axis, no fit at all. Grouped by plane: 5 walls, and the fit lands.
- **Snug fits are no longer refused.** Separation and clearance were judged
  against the flatness allowance, which is 0.5% of a patch's extent -- roughly 2%
  clearance demanded on a 10-unit peg, far more than a printed fit has, and on a
  broad thin tab more than the tab's own thickness. Both now use the
  precision-based tolerance, as Lock and key already did.

Lock and key's trim floor and widening search are deliberately not adopted: the
floor is measured against the wall that was *clicked*, and a snap element usually
sits on a body face, where it deleted the socket walls themselves.

## 1.8.10

### Added
- **R toggles "Rotate key to match lock" during the mate**, and retries the pick
  straight away. The refusal that asks for rotation was asking the user to leave
  the modal, find a checkbox that is only drawn while Lock and key is on, and
  start both picks over. Rotation stays opt-in -- consent is now a keystroke,
  offered where the refusal happens. The header shows which way it is set.

### Fixed
- A cut face with its connector beside it is no longer called a parting plane. A
  neck or a shoulder is cut flat across, so the clicked wall has nothing facing
  it -- but the peg is right there, and centring even puts the anchor between its
  walls. Judging the clicked wall alone made that verdict unfalsifiable whenever
  the parts were not already aligned, which is precisely when the user needed to
  hear about rotation instead. It now also requires nothing connector-sized
  within reach.
- The settings backup no longer overwrites preferences you have set. It is
  written when the addon is unregistered, so a session that ended in a crash
  leaves it stale, and it was then restored wholesale on the next start -- which
  reads as a setting that will not stay ticked. It now fills in only what this
  install has never set, which is the fresh-install case it exists for.

## 1.8.9

### Changed
- The key's taper may now differ from the lock's by 10 degrees rather than 5.
  Matching already allows each wall 10 degrees from anti-parallel, and an opening
  is the difference of two such measurements, so the old figure was stricter than
  the test it accompanied. On a small connector -- a hair peg reading 141.8 degrees
  against a head socket's 147.3 -- that is measurement, not shape, and it refused
  the mate. Worse on the rotation path, which needs two matched pairs and so failed
  outright when one dropped out. A chamfer still reads 40 to 60 degrees away and is
  still refused.

### Added
- The diagnostic report says whether each wall pair is a peg or a socket. Which
  side is which is read off the wall normals, and a width mismatch cannot be read
  at all without it.

## 1.8.8

### Fixed
- The chamfer around a socket mouth no longer replaces the socket's own walls. Both
  search passes restart close to the click, and the trim there is opposed on two
  directions of its own -- enough to look like a complete picture and be returned
  before the search ever reached the far wall. The matcher was then handed walls
  opening 110 degrees against a key opening 180 and refused the mate. The trimmed
  pass now keeps what it found; the fallback may only add a direction it lacked.
- A click is no longer called a parting plane when both clicks did find a connector.
  Wall pairs from the two clicks that agree on a direction are the connector, and
  telling the user to click somewhere else sent them at the wrong thing entirely.

### Added
- A refusal for walls that line up but are not parallel: "the key's walls open 174
  degrees where the lock's open 127". That is a chamfer measured against a straight
  wall, and no amount of rotating fixes it, which is what the old message advised.
- The diagnostic report names the two walls behind every pair it lists. Without
  them a chamfer facet and a connector wall read identically on the page, which
  cost a full round of diagnosis.

## 1.8.7

### Added
- Clicking the flat face two halves meet on is now named as such. On a split
  figurine that plane looks like the obvious thing to click, but it has no
  opposite wall, so the solver fell back on whatever incidental detail was nearby
  and reported an angle between two things that were never connector walls -- a
  number that reads as a measurement and is not. The refusal now says the wall you
  clicked measures X, the biggest wall facing it measures Y, and to click the side
  of the peg or the inner wall of the socket instead.

### Changed
- Curvature counts only facing walls of comparable size. A flat peg standing on an
  organic body is faced by a crowd of body facets far smaller than itself, and
  counting those called the peg a curve.

## 1.8.6

### Fixed
- The wall search no longer stops at whichever single pair it saw first. Centring
  wants two independent lateral directions and rotation flatly requires them, so
  returning the first pair found made "Rotate key to match lock" refuse with
  "needs two independent wall pairs" on parts that plainly have them one hop
  further out. It now keeps widening until it has two, while keeping the best it
  has seen -- a slot legitimately constrains only one direction. Measured on a
  fragmented peg: one pair became three, and rotation reaches the solver.

## 1.8.5

### Changed
- "None facing each other" now says by how much the nearest combination missed,
  in degrees on the wall direction and degrees from facing. The count of tried
  combinations cannot distinguish a part a few degrees out of true from one that
  is structurally unrelated, and those want opposite advice.

## 1.8.4

### Fixed
- A flat socket in a detailed part is no longer called a curve. Curvature was
  judged from the total number of opposed wall pairs in the neighbourhood, but
  pairing runs over every wall against every other, so that count tracks how
  detailed the surrounding geometry is rather than how round the connector is --
  a perfectly flat socket reported 36 where the limit was 32. It is now judged at
  the wall that was actually clicked: a flat-sided wall faces one other, or a few
  in a stepped slot, where a rounded one faces half the facets of its own curve.
  A 32-sided cylinder still fails closed, now reported as "faced by 15 others".

## 1.8.3

### Added
- Refusal reports are also appended to `quicksnap_lock_key_log.txt`, next to the
  .blend when it is saved and in Blender's temp folder otherwise. The console dies
  with Blender, and a crash part-way through a batch is exactly when the report
  was worth keeping.

## 1.8.2

### Added
- A refused mate writes the full geometry behind it to the console: patches
  reached, walls recovered, which walls face the click and by how much, the
  separations, and every surviving wall pair. Nothing to run and nothing to
  reproduce -- open the system console and it is there. The status bar holds one
  line, and one line has repeatedly turned out to describe the wrong thing.

## 1.8.1

### Fixed
- A refusal described the wrong search. Two passes run -- one that ignores trim and
  a fallback that does not -- and the fallback's numbers overwrote the first's, so
  the message reported a neighbourhood assembled under different rules from the
  search that actually failed, and cited a patch budget that no longer constrains
  the pass being described. It now reports the pass whose failure caused the
  refusal, and says when that search reached its full depth, which is the case
  where the facing wall is genuinely further away than a connector should be.

## 1.8.0

### Added
- Connector walls are rebuilt from their fragments. A wall that arrives
  triangulated, decimated or sculpted comes back as dozens or hundreds of patches
  whose normals differ by a fraction of a degree -- the growth step will not merge
  them, because its offset allowance scales with edge length and a finely cut wall
  has tiny edges. To the pairing rules those fragments were not a wall at all: the
  click landed on one sliver, every neighbour faced the same way, and the opposite
  wall sat hundreds of fragments away, further than any affordable search. Patches
  are now grouped by plane first. Measured on a subdivided, jittered peg: 108
  patches become 6 walls, and the clicked wall comes back at its full area rather
  than as the 3% sliver that was hit.

### Fixed
- Perpendicular walls are no longer paired as opposed ones. Pairing asked only
  that two normals point away from each other at all, which excludes a clean
  corner exactly (its dot is zero) but admits a noisy one, whose dot lands either
  side of zero. Half the corners in a neighbourhood therefore became plausible
  pairs on 45-degree axes -- crowding out the real walls and, since the search
  stops at the first radius that yields any pair, stopping it widening to reach
  the far wall it was looking for. Walls must now be at least 95 degrees apart,
  the same bar the rotation search already applied.

## 1.7.6

### Fixed
- A dense neighbourhood no longer cuts the connector search short. The walk stopped
  once it had reached a few hundred patches, which was meant to bound a quadratic
  cost -- but that cost only exists in the unfloored fallback, which re-admits
  every sliver. The floored pass pairs substantial walls only, a handful even on a
  part with thousands of patches, so the budget was stopping it long before it
  could cross to the far wall on exactly the dense parts that need the reach most.
  It now applies to the fallback alone.

### Changed
- A refusal describes the radius the search actually reached, and says when the
  budget stopped it. It previously reported the neighbourhood at the maximum
  allowed radius, which the search often never reaches -- so it described geometry
  that was never considered, which reads as evidence and is not.

## 1.7.5

### Fixed
- Broad thin connectors keep their thin axis. Whether two walls are measurably
  apart was judged against the flatness allowance, which is 0.5% of the patch
  extent -- so on a tab broader than roughly 150:1 the allowance exceeds the tab's
  own thickness and the thin-axis wall pair was discarded as noise. That is the
  one axis such a connector needs centred. Worse than a refusal, the mate then
  still succeeded on the remaining axes and left the part silently uncentred; a
  600:1 tab was judged against a tolerance of 1.206 for a 0.200 thickness. The
  question is now asked of the precision tolerance instead. Flatness still governs
  what it should: whether the click lies within the pair's lateral interval.

## 1.7.4

### Fixed
- Only the floored search may call a connector curved. The unfloored fallback
  added in 1.7.3 re-admits every bevel sliver, so its pair count measures how
  finely the part is cut up rather than how round it is -- and a flat-sided key
  whose walls are fragmented was confidently reported as "on a curved surface".
  It now falls through to the descriptive refusal instead.

### Changed
- The descriptive refusal reports how many of the patches in reach are a tenth
  the clicked wall or bigger, and says outright when a wall looks fragmented
  rather than flat. Triangulated, decimated and booleaned parts break a flat wall
  into slivers that read exactly like a curve to the pairing rules, and the two
  need different fixes.

## 1.7.3

### Fixed
- Ignoring trim is now a preference rather than a rule. The area floor added in
  1.7.2 is tried first and dropped if it leaves the click with nothing, so a
  connector whose far wall is genuinely much smaller than the clicked one -- or
  whose clicked patch merged with a large coplanar body face, inflating the floor
  -- is no longer refused for the sake of a filter that exists only to keep bevel
  slivers out. A tab flush with a body plate mates again.

### Changed
- "No opposed wall pair" now reports what the click actually found: how many flat
  patches were within reach, how many face the clicked wall, and how many were
  rejected for a shallow angle or for not spanning the click. The shapes that
  reach this message are the ones nobody can picture from a description, so the
  refusal now carries its own evidence.
- A click on a curved surface says so, instead of claiming no opposed wall pair
  was found. It had in fact found hundreds -- a 32-sided cylinder yields 273 --
  which is what identifies it as a curve.

## 1.7.2

### Fixed
- Fillet strips are no longer mistaken for connector walls. Reaching the far wall
  of a rounded connector means walking across its trim, which 1.7.1 enabled, but
  the trim was then treated as mateable geometry. A rounded edge yields dozens of
  slivers, each a plausible opposed pair on its own diagonal axis, and since the
  matcher discards a candidate whose two best targets tie, near-identical slivers
  tie constantly and delete the real wall match. Mates were refused holding a
  dozen matched pairs, not one of which involved an actual wall. Only patches at
  least a tenth the area of the clicked one may now form a pair; traversal still
  crosses the trim. Measured on a filleted peg and socket: 36 key / 89 lock pairs
  became 2 and 2, and a peg welded to a body plate went from zero matches to two,
  centred exactly.
- The widened search now reaches ten hops rather than four. Once trim correctly
  stops counting as a wall, a 5-segment fillet needs more rings crossed before
  the real opposite wall comes into view.
- A click that turns up more than a few dozen opposed pairs fails closed as a
  curve instead of grinding. Widening let a rounded click reach the far side of
  its own curvature: a 96-segment sphere produced 1468 pairs and fed a matcher
  that is quadratic in them. It now yields 21, in 110 ms.
- The walk also stops after several hundred patches without success, so a dense
  part cannot be made to grow half its mesh at click time.

## 1.7.1

### Fixed
- Chamfered and filleted connectors mate. The neighbourhood search around a click
  was a fixed two patch hops, which reaches the far wall of a plain box peg but
  not of one whose edges are rounded -- every fillet ring inserts another hop. The
  opposite wall was never found, and a nicely modelled key reported "no opposed
  wall pair at the key click" however obvious the fit was. The search now widens
  to at most four hops, and only when it would otherwise find nothing, so plain
  connectors keep the patch set and the cost they had. Measured on a rectangular
  peg and socket: 3- and 5-segment fillets went from refused to mated, in both
  rotation modes, in 8-15 ms. Standard precision fit is untouched.

## 1.7.0

### Added
- `Centre picks on the wall` (on by default) moves each Lock and key pick to the
  middle of the flat wall it landed on, so the same two walls always mate the same
  way however carelessly they were clicked. Sliding the pick inside its own plane
  cannot change a measured wall width, so this only settles the axes the solver
  leaves free. Turn it off to set the insertion depth by clicking deeper or
  shallower.
- Centring is never a restriction: if the wall centres do not mate, the exact
  click points are retried before anything is refused.

### Fixed
- Two clicks placed far apart on a constrained axis could drive the lateral
  correction past the relocation cap and refuse a mate that was perfectly
  buildable. Centred picks remove that failure by construction.

## 1.6.2

### Fixed
- Lock and key works whichever half you move. Which part is the socket is now
  read from the wall normals instead of the click order, so moving a socket onto
  a fixed peg mates exactly as moving the peg into the socket does -- the two
  produce inverse deltas for the same seated assembly. Previously the second
  click had to be the socket, and the reverse order was refused with "the key
  does not fit inside the lock" no matter how well the parts fitted. A pairing of
  two pegs or two sockets is still rejected, as is a peg genuinely wider than its
  socket.
- The insertion-axis guard follows the same rule and reads its half-space from
  whichever click landed on the socket. Reading it from the peg's click rejected
  every honest mate, because the socket wall on the far side of the peg
  legitimately sits behind that plane.

### Changed
- "The key does not fit inside the lock" now reports both measurements, so a
  scale mistake can be told apart from a taper mismatch or an overgrown patch.
- Rotation search failures say what actually stopped them -- too many candidate
  wall pairs, competing pairs on one axis, or too few pairs to pin a rotation --
  instead of always blaming seating. Those causes previously went to the debug
  log only, and the user saw "no rotation seats the key without penetrating the
  lock" regardless.

## 1.6.1

### Fixed
- Lock and key mates connectors that were modelled with no clearance at all. A
  snug fit is a legitimate design and its seated position is the most determined
  of any, but the solver demanded strictly positive clearance and refused it.
  The approved design asks for clearance "non-negative within flatness
  tolerance", which is what is now applied. A key genuinely wider than its lock
  still fails closed.
- The relocation cap no longer collapses on a snug fit. It was bounded by twice
  the clearance, which is zero for a press fit, so no correction was permitted at
  all. Over-sliding is already caught by the wall gap checks.

## 1.6.0 - QuickSnap Neo

### Added
- Lock and key mode provides a no-drag, two-surface-click workflow for
  selected figurine connectors. The first click records the key without
  moving it; the second applies one validated transform into the lock.
- Translation-only centering is the default and preserves the insertion depth
  defined by the two clicks. An optional setting also aligns a uniquely
  constrained connector rotation.
- Clean rectangular, slot, and depth-tapered trapezoidal connectors are
  supported. Round, organic, stale, incompatible, or ambiguous geometry fails
  closed without changing the selected hierarchy.

### Fixed
- Lock and key honours "Ignore modifiers" again. Surface picking reported
  evaluated geometry while the solver read the base mesh, so on any object with a
  geometry-changing modifier the face index belonged to a different mesh than the
  one being measured. Raw picking now uses a cached base-mesh BVH, so the index and
  the hit always come from the geometry the solver reads.
- A rigid match can no longer seat the key pointing out of its socket. Clearance
  only constrains the matched lateral walls, so an end-for-end flip satisfied every
  test and, with the key starting near that orientation, was also the smallest
  rotation. The clicked target face normal now constrains the insertion axis, and
  candidates that seat the mated walls differently are rejected as ambiguous.
- Optional rotation no longer freezes Blender on unsupported connectors. The
  candidate search was quadratic in both pair lists; a 16-sided peg took roughly 20
  seconds to reject and larger ones far longer. Implausible pairs are now discarded
  up front and oversized or ambiguous sets fail closed, rejecting the same peg in
  under a millisecond.
- Descendants of the selected key can no longer be picked as the target lock. They
  move with the key, so the computed mate was never achieved. They are now
  pickable as the source, which they previously were not.
- Switching Lock and key off after picking a connector no longer leaves stale snap
  state behind, which made the next mouse move translate the selection by an
  uninitialised value. Switching the mode on when it cannot be entered now declines
  and leaves the operator running instead of cancelling in-progress work.
- Backspace re-picks the key after the source connector changes; the warning
  previously asked for something the modal offered no way to do.
- Finishing a snap that started with nothing selected no longer raises
  IndexError out of the modal. With no active object and an empty selection
  there is nothing to make active, and cleanup aborted partway through.

### Changed
- Well-fitted connectors are no longer rejected for fitting too well. Clearance
  was judged against the flatness allowance, which scales with patch size and
  demanded roughly 2% clearance on a 10-unit peg -- printed parts are modelled
  at 1% or less, so real connectors were refused. Clearance is now measured
  against how precisely the mating planes are defined. Zero-clearance and
  ambiguous geometry still fail closed.
- A refused mate distinguishes a key that is not rotated into place (which the
  "Rotate key to match lock" option fixes) from parts that face each other but
  do not fit. Translation-only matching needs the key aligned to within about
  five degrees, which was not stated anywhere.
- A refused mate now names its cause -- no opposed wall pair at a click,
  mismatched wall pairs, a mate that cannot be centred, a stale face -- instead
  of one generic "no safe connector match found" covering every failure.
- The two clicks extract each connector mesh once instead of three times, and the
  target-side preview raycast uses the scene BVH. Staleness is still checked
  against live mesh data on every click.

## 1.5.13

### Changed
- Post-snap precision fit now uses the exact snapped source and target elements
  as datum seeds, then centers clean opposed plane pairs. Rectangular pegs and
  slots fit deterministically regardless of mesh density or polygon order,
  while insertion depth and every other unconstrained direction stay fixed.
- Ambiguous, organic, stale, equal-width, or impossible geometry is safely
  skipped instead of falling back to surface-distance fitting. The obsolete
  fit sample-count setting has been removed.

## 1.5.12

### Fixed
- Precision fit rebuilt for sculpted kit parts (organic surfaces, fur, shells
  that overlap by design, with clean rectangular pegs for assembly). The fit
  now only acts on clean mating faces: large, flat, direction-coherent contact
  clusters whose normals oppose almost exactly. Rough organic contact and
  designed shell overlaps are ignored entirely, and the correction is
  restricted to the axes that opposing faces actually constrain, so insertion
  depth always stays exactly where the snap put it. When no clean bilateral
  feature is found near the snap, the part is not moved at all.

### Added
- QuickSnap panel in the 3D view sidebar (N panel) with the per-session
  toggles: post-snap precision fit, prefer corners, hide dragged over target.
- Holding middle mouse (orbit) now also pauses snapping and hides the dragged
  objects, like Shift, so navigating around the target stays light and clear.

## 1.5.11

### Added
- Hold Shift after picking the source point to pause snapping: nothing under
  the cursor is loaded, searched or highlighted while held, so the mouse stays
  light around dense targets, and the dragged objects stay hidden (with the
  hide option on) so the target's interior is visible. Release Shift to resume
  snapping; the header shows when snapping is paused.

## 1.5.10

### Fixed
- Precision fit no longer moves a part too far, e.g. carrying a key across the
  slot until its left wall touches the lock's right wall. The fit now solves on
  one robust value per mating face instead of per sample, so the balance
  depends on the geometry rather than on how many samples happen to land on
  each wall (uneven sampling used to drag the part towards the better-sampled
  side). Faces close to where the user placed the part anchor the fit while
  far matches (such as a neighboring identical slot) lose influence, and the
  maximum correction is much tighter: the fit refines placement, it never
  relocates the part.

## 1.5.9

### Fixed
- Settings now survive version upgrades. Blender wipes addon preferences when
  an addon is removed, and keys them to the install folder name, so upgrading
  via remove+install (or installing a differently named zip) lost all settings.
  The addon now backs its preferences up to quicksnap_settings.json in
  Blender's config folder (on every tool session end and on disable) and
  restores them when enabled, so settings persist across reinstalls, renamed
  installs and Blender upgrades.

## 1.5.8

### Fixed
- Precision fit now handles parts with built-in tolerances (a designed air gap
  between key and lock) correctly: the part is centered so the gap is even on
  all sides, instead of sometimes being pushed against a wall. A gap now only
  constrains the fit when another surface opposes its direction: opposed gaps
  are balanced, unopposed gaps are treated as designed standoffs and left
  alone, and penetration always resolves. The final check is a safety check
  (reject corrections that leave the parts sitting worse) rather than an
  improvement demand, since balancing a clearance barely changes the total
  error while clearly improving the fit.

## 1.5.7

### Fixed
- Stop "ReferenceError: StructRNA ... has been removed" spam from the viewport
  draw callbacks. If the tool operator is ever freed without a clean shutdown
  (a mid-session error, a script reload), its draw handlers no longer keep
  firing against the dead operator: the handlers are tracked centrally, the
  draw callbacks detect a freed operator and unregister themselves, and any
  leftover handlers are purged when the addon is disabled or reloaded.
- Corner-preferring vertex snapping can no longer raise during a snap; on any
  unexpected error it is skipped for that query instead of ending the tool.

## 1.5.6

### Fixed
- Fix a crash on tool start (NameError: numpy was not imported in the operator
  module) introduced with corner-preferring vertex snapping in 1.5.5.

## 1.5.5

### Added
- **Prefer corners (vertex snapping)** (toggleable, on by default): when picking
  vertices, corner vertices (peg/socket corners, crease ends, borders) get a
  scoring bonus over vertices on flat or gently curved areas near the cursor,
  making the corners of mating features much easier to grab. Cornerness comes
  from the mesh topology (how strongly a vertex's edge directions point into
  the surface), is computed only for the few candidates under the cursor and
  cached, and applies to both the source and the destination pick. Vertex/curve
  point mode only; curve points are unaffected.

## 1.5.4

### Added
- **Wireframe style** preference: choose how the target/hover wireframe is
  drawn. "Automatic" keeps the vertex-threshold behavior, "Cursor-local always"
  never shows a full object wireframe regardless of mesh size, "Native always"
  restores the original overlay everywhere.
- **Hide dragged objects over the target** (object mode, on by default): while
  picking the snap destination, the objects being moved are hidden whenever the
  mouse is over another object so the target geometry is unobstructed. They
  reappear as soon as the mouse leaves the target, and on confirm/cancel.

## 1.5.3

Performance and accuracy pass over the 1.5.x additions, driven by a full audit.

### Performance
- While a heavy object's points are still loading, the closest-point query now
  scans only the newly loaded points on each tick instead of everything so far
  (a per-tick cost that grew with mesh size is now near constant).
- The wireframe's edge-adjacency and grid builds use the default sort instead of
  a stable one (order within a bucket never mattered): roughly halves the
  one-time build per heavy object and the per-orbit rebuild.
- Vertex coordinates are read in float32 (matching Blender's storage, enabling
  the bulk copy path) for the wireframe build and the precision-fit sampling.
- The near-cursor wireframe batch is cached: redraws with an unchanged mouse and
  view reuse the built GPU batch instead of recomputing everything each frame,
  and the batch uploads from numpy directly where supported.
- The wire cache keeps only the objects being displayed (was up to four) and
  never evicts one that is on screen, avoiding repeated multi-second rebuilds
  when sweeping across many heavy objects.

### Fixed
- Precision fit: a part hovering at a uniform standoff over a single flat
  surface is no longer pulled down to touch (indistinguishable from a designed
  offset, so the snap stays exact). Multi-wall seating is unchanged.
- Precision fit: normals are now transformed by the inverse transpose, so
  non-uniformly scaled objects filter and fit correctly.
- The cursor wireframe hides during orbit/zoom instead of drawing a patch
  frozen to the pre-navigation view (it reappears on the next mouse move).
- The grid cell size and the snap search radius are tied to one constant so
  they cannot drift apart.

## 1.5.2

### Fixed
- Precision fit no longer moves a snap that is already aligned. Matches now
  require genuinely opposing surfaces, gap errors are trimmed hard so designed
  clearances and shoulder gaps cannot pull the part (penetrations are kept and
  weighted higher, since those are never by design), and the correction is only
  applied when re-measuring shows the parts actually seat better than before.

## 1.5.1

### Added
- Post-snap precision fit (object mode, toggleable, on by default): after a snap
  confirms, the selection is nudged (translation only, no rotation) so the
  geometry around the snapped point seats onto the target surface. Intended for
  assembling kit parts where peg and hole vertices do not correspond exactly.
  - Sampling is anchored to the snapped point, matches are only accepted near
    the contact area and between surfaces facing each other, so complex
    geometry around the mating features does not affect the fit.
  - The correction is capped relative to the sampled area, applied within the
    same undo step, and skipped when an axis constraint is active or the target
    is an origin/cursor/free-space point.
  - New preferences under "Precision fit": enable toggle and sample count.

## 1.5.0

High-poly performance pass. The tool stays usable on objects in the
millions-of-vertices range, without changing which elements are snappable or
altering behavior on light meshes. Every heavy-mesh path is gated behind a
configurable vertex threshold, so meshes below it keep the previous behavior
exactly. The gate counts evaluated vertices, so sculpts whose density comes
from a subsurf/multires modifier are detected too.

### Added
- Cursor-local wireframe: for objects above the vertex threshold, the native
  full-object wireframe overlay (which redraws every edge each frame) is
  replaced by a wireframe limited to the edges near the cursor. Edges with one
  endpoint near the cursor are drawn in full, it works for all snap types, and
  it is occluded by the mesh by default (optional x-ray). The mesh data is
  fetched once per object and lookups go through a screen-space grid plus a
  vertex-to-edge adjacency, so per-frame cost only depends on what is drawn.
- New preferences under "High-poly performance":
  - **Optimize high-poly meshes**: master toggle for the optimized paths.
  - **High-poly vertex threshold (x1000)**: objects with at least this many
    thousand vertices use the optimized paths (default 500, i.e. 500,000).
  - **Cursor wireframe radius (px)**: pixel radius of the cursor-local
    wireframe (default 60).
  - **Cursor wireframe color / opacity**: look of the cursor-local wireframe
    (default white at 0.9).
  - **Wireframe through geometry (x-ray)**: draw the cursor wireframe through
    the mesh instead of occluding it (default off).
- Debug HUD (shown when the log level is set to Debug): point count, query
  mode, query/wireframe frame timings and total ingestion time. Useful for
  before/after performance comparisons.

### Changed
- Closest-point lookup on heavy scenes now uses a screen-space grid query
  instead of building a spatial tree over millions of points, removing the
  upfront stall and the associated memory spike when a heavy object enters snap
  range, and keeping per-move lookups cheap afterwards. Snap results are
  identical to the previous method.
- The near-point display (edge midpoints / face centers / vertices around the
  hovered face) now uses a binary search instead of a linear scan through the
  object's point indices, which removes a per-frame cost that grew with vertex
  count.

### Notes
- Snap targets are always the real mesh elements; no decimated proxy is used.
- Light meshes use the original code paths unchanged.
