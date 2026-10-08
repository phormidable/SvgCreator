# model.py
"""Qt-free model for the drawing tool.

- Point: a coordinate. That's all it is.
- Junction: a set of >= 2 extremity points that share a position.
- Curve: a Bezier of degree 1, 2 or 3, holding 2 extremities + 0/1/2 controls.
- Document: owns the lists and keeps the invariants.

A point does not know which junction or curve it belongs to. Those are
lookups on the Document. Invariants (maintained by Document operations):
- All points in a junction are coincident.
- No two curves share the same extremity pair.
"""


class Point:
    _next_id = 1

    def __init__(self, x, y):
        self.id = Point._next_id
        Point._next_id += 1
        self.x = x
        self.y = y

    def __repr__(self):
        return f"P{self.id}({self.x:.1f},{self.y:.1f})"


class Junction:
    _next_id = 1

    def __init__(self, points):
        self.id = Junction._next_id
        Junction._next_id += 1
        self.points = list(points)

    def __repr__(self):
        return f"J{self.id}{[p.id for p in self.points]}"


class Curve:
    _next_id = 1

    def __init__(self, extremities, controls, degree):
        self.id = Curve._next_id
        Curve._next_id += 1
        self.extremities = tuple(extremities)   # (P0, P1)
        self.controls = list(controls)          # 0, 1 or 2 points
        self.degree = degree

    def other_end(self, pt):
        a, b = self.extremities
        return b if pt is a else a

    def __repr__(self):
        return f"C{self.id}[{self.extremities[0].id}->{self.extremities[1].id}]"

class Shape:
    _next_id = 1

    def __init__(self, curves):
        self.id = Shape._next_id
        Shape._next_id += 1
        self.name = f"Shape {self.id}"
        self.curves = list(curves)      # cyclic order
        self.color = None

    def __repr__(self):
        return f"Shape{self.id}{[c.id for c in self.curves]}"

class Chain:
    _next_id = 1

    def __init__(self, curves):
        self.id = Chain._next_id
        Chain._next_id += 1
        self.name = f"Chain {self.id}"
        self.curves = list(curves)      # no ordering promise: chains may branch

    def __repr__(self):
        return f"Chain{self.id}{[c.id for c in self.curves]}"

class Document:
    def __init__(self):
        self.extremities = []
        self.controls = []
        self.curves = []
        self.junctions = []
        self.shapes = []
        self.chains = []

    # ------------------------------------------------------------
    #  Lookups
    # ------------------------------------------------------------
    def junction_that_contains(self, pt):
        for j in self.junctions:
            if pt in j.points:
                return j
        return None

    def neighbours(self, pt):
        """Extremity points reachable from pt in one hop: its junction-mates'
        partners on their own curves. Returns the points at the *far* end of
        each attached curve (excluding pt itself)."""
        result = []
        j = self.junction_that_contains(pt)
        siblings = j.points if j is not None else [pt]
        for s in siblings:
            curve = self.parent_curve(s)
            if curve is None:
                continue
            result.append(curve.other_end(s))
        return result

    def parent_curve(self, pt):
        for c in self.curves:
            if pt is c.extremities[0] or pt is c.extremities[1] or pt in c.controls:
                return c
        return None

    def curve_between(self, a, b):
        for c in self.curves:
            if {c.extremities[0], c.extremities[1]} == {a, b}:
                return c
        return None

    # ------------------------------------------------------------
    #  Creation
    # ------------------------------------------------------------
    def add_curve(self, p0_xy, p1_xy, control_xys, degree):
        p0 = self._new_extremity(*p0_xy)
        p1 = self._new_extremity(*p1_xy)
        controls = [self._new_control(*xy) for xy in control_xys]
        curve = Curve((p0, p1), controls, degree)
        self.curves.append(curve)
        return curve

    def _new_extremity(self, x, y):
        pt = Point(x, y)
        self.extremities.append(pt)
        return pt

    def _new_control(self, x, y):
        pt = Point(x, y)
        self.controls.append(pt)
        return pt

    # ------------------------------------------------------------
    #  Deletion
    # ------------------------------------------------------------
    def delete_curve(self, curve):
        for pt in curve.extremities:
            self.unlink(pt)
            self.extremities.remove(pt)
        for pt in curve.controls:
            self.controls.remove(pt)
        self.curves.remove(curve)

    # ------------------------------------------------------------
    #  Linking
    # ------------------------------------------------------------
    def link(self, a, b):
        """Put a and b in the same junction, merging junctions as needed."""
        ja = self.junction_that_contains(a)
        jb = self.junction_that_contains(b)

        if ja is not None and jb is not None:
            if ja is jb:
                return ja
            # Merge jb into ja.
            ja.points.extend(jb.points)
            self.junctions.remove(jb)
            return ja

        if ja is not None:
            ja.points.append(b)
            return ja

        if jb is not None:
            jb.points.append(a)
            return jb

        j = Junction([a, b])
        self.junctions.append(j)
        return j

    def unlink(self, pt):
        j = self.junction_that_contains(pt)
        if j is None:
            return
        j.points.remove(pt)
        if len(j.points) < 2:
            self.junctions.remove(j)

    # ------------------------------------------------------------
    #  Movement
    # ------------------------------------------------------------
    def move_point(self, pt, x, y):
        """Move pt; if it's in a junction, move its siblings with it."""
        j = self.junction_that_contains(pt)
        if j is None:
            pt.x, pt.y = x, y
        else:
            for each_point in j.points:
                each_point.x, each_point.y = x, y

    def shape_through(self, start_curve):
        """Shortest closed loop of curves containing start_curve. Returns
        the loop as a list of curves, or None if start_curve is not part
        of a cycle. Junctions of any size are tolerated: for a T-junction
        or figure-8, returns the shortest loop containing start_curve."""
        from collections import deque

        j_start = self.junction_that_contains(start_curve.extremities[0])
        j_goal = self.junction_that_contains(start_curve.extremities[1])
        if j_start is None or j_goal is None:
            return None
        if j_start is j_goal:
            return [start_curve]        # teardrop

        queue = deque([(j_start, [start_curve])])
        visited = {id(j_start)}
        while queue:
            j, path = queue.popleft()
            for c in self.curves:
                if c is start_curve or c in path:
                    continue
                jc0 = self.junction_that_contains(c.extremities[0])
                jc1 = self.junction_that_contains(c.extremities[1])
                if jc0 is j:
                    next_j = jc1
                elif jc1 is j:
                    next_j = jc0
                else:
                    continue
                if next_j is None:
                    continue
                new_path = path + [c]
                if next_j is j_goal:
                    return new_path
                if id(next_j) not in visited:
                    visited.add(id(next_j))
                    queue.append((next_j, new_path))
        return None

    def detect_shapes(self):
        """Recompute shapes from topology. Identity (id, name, color) is
        preserved across calls: a shape whose curve set is unchanged keeps
        its Shape object. A shape whose curve set changed dissolves and
        a new one takes its place."""
        # 1. Detect loops (each curve belongs to at most one).
        detected = []
        seen = set()
        for curve in self.curves:
            if curve in seen:
                continue
            loop = self.shape_through(curve)
            if loop is None:
                continue
            seen.update(loop)
            detected.append(loop)

        # 2. Match against existing shapes by curve set.
        existing_by_key = {
            frozenset(c.id for c in s.curves): s
            for s in self.shapes
        }

        # 3. Reuse or create.
        new_shapes = []
        for loop in detected:
            key = frozenset(c.id for c in loop)
            old = existing_by_key.get(key)
            if old is not None:
                old.curves = list(loop)  # refresh order; same set
                new_shapes.append(old)
            else:
                new_shapes.append(Shape(loop))

        # 4. Replace in place — keep list identity for anything holding it.
        self.shapes[:] = new_shapes

    def detect_chains(self):
        """Recompute chains from topology. A chain is a maximal connected
        component of curves that is not already part of a shape.

        Identity survives edits:
        - extension (new curve joins): original ID kept
        - split: the side that matches more of the old chain keeps the ID
                 (ties broken by smallest curve id in the piece)
        - merge: the larger donor chain keeps its ID
        """
        shape_curves = set()
        for s in self.shapes:
            shape_curves.update(s.curves)

        detected = []
        seen = set()
        for curve in self.curves:
            if curve in seen or curve in shape_curves:
                continue
            component = self._component_from(curve, skip=shape_curves)
            seen.update(component)
            detected.append(set(component))

        # Score all (existing, detected) pairings by overlap.
        # (overlap_size, detected_size, detected_index, existing_chain)
        # Score all (existing, detected) pairings by overlap, comparing
        # curve IDs (not objects) so identity survives across mirrors.
        triples = []
        for i, new in enumerate(detected):
            new_ids = {c.id for c in new}
            for old in self.chains:
                old_ids = {c.id for c in old.curves}
                overlap = len(new_ids & old_ids)
                if overlap > 0:
                    triples.append((overlap, len(new), i, old))
        triples.sort(key=lambda t: (t[0], t[1]), reverse=True)

        used_detected = set()
        used_existing = set()
        result = [None] * len(detected)
        for _overlap, _size, i, old in triples:
            if i in used_detected or old in used_existing:
                continue
            old.curves = list(detected[i])
            result[i] = old
            used_detected.add(i)
            used_existing.add(old)

        for i in range(len(detected)):
            if result[i] is None:
                result[i] = Chain(list(detected[i]))

        self.chains[:] = result

    def _component_from(self, seed, skip=frozenset()):
        """BFS through junctions, skipping `skip` curves."""
        stack = [seed]
        seen = {seed}
        component = [seed]
        while stack:
            c = stack.pop()
            for end in c.extremities:
                j = self.junction_that_contains(end)
                if j is None:
                    continue
                for pt in j.points:
                    if pt is end:
                        continue
                    other = self.parent_curve(pt)
                    if other is None or other in seen or other in skip:
                        continue
                    seen.add(other)
                    component.append(other)
                    stack.append(other)
        return component

# ------------------------------------------------------------
#  Smoke test
# ------------------------------------------------------------
if __name__ == "__main__":
    doc = Document()
    # --- shapes ---

    # Rebuild the triangle cleanly.
    Point._next_id = 1
    Junction._next_id = 1
    Curve._next_id = 1
    Shape._next_id = 1
    doc = Document()
    A, B, C = (-80, 40), (80, 40), (0, -80)
    c1 = doc.add_curve(A, B, [(0, 40)], degree=2)
    c2 = doc.add_curve(B, C, [(40, -20)], degree=2)
    c3 = doc.add_curve(C, A, [(-40, -20)], degree=2)
    doc.link(c1.extremities[1], c2.extremities[0])
    doc.link(c2.extremities[1], c3.extremities[0])
    doc.link(c3.extremities[1], c1.extremities[0])
    doc.detect_shapes()
    assert len(doc.shapes) == 1 and len(doc.shapes[0].curves) == 3
    print("triangle ->", doc.shapes)

    # --- teardrop ---
    Point._next_id = 1;
    Junction._next_id = 1;
    Curve._next_id = 1
    Shape._next_id = 1
    doc = Document()
    t = doc.add_curve((0, 0), (100, 0), [(50, 80)], degree=2)
    doc.link(t.extremities[0], t.extremities[1])
    doc.detect_shapes()
    assert len(doc.shapes) == 1 and len(doc.shapes[0].curves) == 1
    print("teardrop ->", doc.shapes)

    # --- figure-8 (two triangles sharing one junction) ---
    Point._next_id = 1
    Junction._next_id = 1
    Curve._next_id = 1
    Shape._next_id = 1
    doc = Document()
    # Left triangle: S=(-100,0), P=(-50,-80), Q=(-50,80)
    l1 = doc.add_curve((-100, 0), (-50, -80), [(-75, -40)], degree=2)
    l2 = doc.add_curve((-50, -80), (-50, 80), [(-30, 0)], degree=2)
    l3 = doc.add_curve((-50, 80), (-100, 0), [(-75, 40)], degree=2)
    # Right triangle: S=(same as left's S junction), R=(100,0), T=(50,-80), U=(50,80)
    r1 = doc.add_curve((-100, 0), (50, -80), [(0, -60)], degree=2)
    r2 = doc.add_curve((50, -80), (50, 80), [(70, 0)], degree=2)
    r3 = doc.add_curve((50, 80), (-100, 0), [(0, 60)], degree=2)
    # Link left
    doc.link(l1.extremities[1], l2.extremities[0])
    doc.link(l2.extremities[1], l3.extremities[0])
    doc.link(l3.extremities[1], l1.extremities[0])
    # Link right (sharing l1.extremities[0] as the common vertex)
    doc.link(r1.extremities[0], l1.extremities[0])
    doc.link(r1.extremities[1], r2.extremities[0])
    doc.link(r2.extremities[1], r3.extremities[0])
    doc.link(r3.extremities[1], r1.extremities[0])
    doc.detect_shapes()
    print("figure-8 shapes ->", doc.shapes)
    assert len(doc.shapes) == 2

    # --- open chain (L) ---
    Point._next_id = 1;
    Junction._next_id = 1;
    Curve._next_id = 1
    Shape._next_id = 1
    doc = Document()
    s1 = doc.add_curve((-50, -50), (-50, 50), [(-50, 0)], degree=2)
    s2 = doc.add_curve((-50, 50), (50, 50), [(0, 50)], degree=2)
    doc.link(s1.extremities[1], s2.extremities[0])
    doc.detect_shapes()
    assert len(doc.shapes) == 0
    print("open L ->", doc.shapes)

    # --- chains ---

    # Open L: no shape, one chain.
    Point._next_id = 1; Junction._next_id = 1; Curve._next_id = 1
    Shape._next_id = 1; Chain._next_id = 1
    doc = Document()
    s1 = doc.add_curve((-50, -50), (-50, 50), [(-50, 0)], degree=2)
    s2 = doc.add_curve((-50, 50), (50, 50), [(0, 50)], degree=2)
    doc.link(s1.extremities[1], s2.extremities[0])
    doc.detect_shapes(); doc.detect_chains()
    assert len(doc.chains) == 1 and len(doc.chains[0].curves) == 2
    original_id = doc.chains[0].id
    print("L ->", doc.chains)

    # Extension: add a third curve onto the end, chain ID should survive.
    s3 = doc.add_curve((50, 50), (50, -50), [(50, 0)], degree=2)
    doc.link(s2.extremities[1], s3.extremities[0])
    doc.detect_shapes(); doc.detect_chains()
    assert len(doc.chains) == 1 and doc.chains[0].id == original_id
    print("L extended ->", doc.chains)

    # Split: delete the middle curve, chain becomes two pieces.
    # The side that doesn't contain s3 should win the ID by the tiebreak rule
    # only if it has a smaller min curve id — actually here s1 has the smaller id,
    # so it wins.
    doc.delete_curve(s2)
    doc.detect_shapes(); doc.detect_chains()
    assert len(doc.chains) == 2
    print("L split ->", doc.chains)
    # s1 (the earlier curve) is in the piece that kept the ID.
    keeper = next(c for c in doc.chains if c.id == original_id)
    assert s1 in keeper.curves

    # Merge: link two chains back together, larger donor keeps its ID.
    Point._next_id = 1; Junction._next_id = 1; Curve._next_id = 1
    Shape._next_id = 1; Chain._next_id = 1
    doc = Document()
    a1 = doc.add_curve((0, 0), (50, 0), [(25, 0)], degree=2)
    a2 = doc.add_curve((50, 0), (100, 0), [(75, 0)], degree=2)
    doc.link(a1.extremities[1], a2.extremities[0])
    b1 = doc.add_curve((200, 0), (250, 0), [(225, 0)], degree=2)
    b2 = doc.add_curve((250, 0), (300, 0), [(275, 0)], degree=2)
    b3 = doc.add_curve((300, 0), (350, 0), [(325, 0)], degree=2)
    doc.link(b1.extremities[1], b2.extremities[0])
    doc.link(b2.extremities[1], b3.extremities[0])
    doc.detect_shapes(); doc.detect_chains()
    assert len(doc.chains) == 2
    # b-chain (size 3) has the larger id currently since it was created second.
    chain_a = next(c for c in doc.chains if a1 in c.curves)
    chain_b = next(c for c in doc.chains if b1 in c.curves)
    id_a, id_b = chain_a.id, chain_b.id
    # Merge them by linking a2's end to b1's start.
    doc.link(a2.extremities[1], b1.extremities[0])
    doc.detect_shapes(); doc.detect_chains()
    assert len(doc.chains) == 1
    assert doc.chains[0].id == id_b   # larger donor kept its id
    assert id_a not in [c.id for c in doc.chains]
    print("merged ->", doc.chains)

    print("ok")