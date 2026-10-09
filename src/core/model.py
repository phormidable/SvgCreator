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
        existing_by_key = {frozenset(c.id for c in s.curves): s for s in self.shapes}

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
