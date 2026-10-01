"""Pure Python spatial hash for fast nearest neighbour queries.

Used for symmetry maps, position based weight transfer and closest point
lookups on point clouds of tens of thousands of points.
"""

import math


class SpatialHash(object):
    def __init__(self, points, cell_size=None):
        self.points = [tuple(p) for p in points]
        if not self.points:
            raise ValueError("SpatialHash needs at least one point")
        mins = [min(p[i] for p in self.points) for i in range(3)]
        maxs = [max(p[i] for p in self.points) for i in range(3)]
        self.mins = mins
        self.maxs = maxs
        if cell_size is None:
            extent = max(maxs[i] - mins[i] for i in range(3)) or 1.0
            cells_per_axis = max(1, int(round(len(self.points) ** (1.0 / 3.0))))
            cell_size = extent / cells_per_axis
        self.cell_size = max(cell_size, 1e-6)
        self.cells = {}
        for index, point in enumerate(self.points):
            self.cells.setdefault(self._key(point), []).append(index)
        span = max(maxs[i] - mins[i] for i in range(3))
        self.max_ring = int(math.ceil(span / self.cell_size)) + 2

    def _key(self, point):
        size = self.cell_size
        return (int(math.floor(point[0] / size)), int(math.floor(point[1] / size)),
                int(math.floor(point[2] / size)))

    def _shell(self, center, ring):
        cx, cy, cz = center
        if ring == 0:
            yield center
            return
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                edge_xy = abs(dx) == ring or abs(dy) == ring
                if edge_xy:
                    for dz in range(-ring, ring + 1):
                        yield (cx + dx, cy + dy, cz + dz)
                else:
                    yield (cx + dx, cy + dy, cz - ring)
                    yield (cx + dx, cy + dy, cz + ring)

    def nearest(self, point, max_distance=None):
        """Return ``(index, distance)`` of the closest point (or ``(-1, inf)``)."""
        center = self._key(point)
        best_index, best_sq = -1, float("inf")
        limit_sq = max_distance * max_distance if max_distance is not None else float("inf")
        px, py, pz = point
        # rings needed to cover the whole cloud from the query point
        offset = max(abs(point[i] - (self.mins[i] + self.maxs[i]) / 2.0) for i in range(3))
        max_ring = self.max_ring + int(math.ceil(offset / self.cell_size))
        for ring in range(max_ring + 1):
            for key in self._shell(center, ring):
                for index in self.cells.get(key, ()):
                    qx, qy, qz = self.points[index]
                    dist_sq = (qx - px) ** 2 + (qy - py) ** 2 + (qz - pz) ** 2
                    if dist_sq < best_sq:
                        best_index, best_sq = index, dist_sq
            reach = ring * self.cell_size
            if best_index != -1 and best_sq <= reach * reach:
                break
            if max_distance is not None and reach > max_distance:
                break
        if best_sq > limit_sq:
            return -1, float("inf")
        return best_index, math.sqrt(best_sq)

    def within(self, point, radius):
        """Indices of points closer than ``radius`` (unsorted)."""
        center = self._key(point)
        rings = int(math.ceil(radius / self.cell_size))
        radius_sq = radius * radius
        result = []
        px, py, pz = point
        for ring in range(rings + 1):
            for key in self._shell(center, ring):
                for index in self.cells.get(key, ()):
                    qx, qy, qz = self.points[index]
                    if (qx - px) ** 2 + (qy - py) ** 2 + (qz - pz) ** 2 <= radius_sq:
                        result.append(index)
        return result


def closest_indices(source_points, query_points):
    """For every query point the index of the nearest source point."""
    grid = SpatialHash(source_points)
    return [grid.nearest(p)[0] for p in query_points]
