"""Rectangle helpers shared by the backends (pure; tested on every OS)."""
from __future__ import annotations


def merge_rects(rects, limit=12):
    """Union overlapping / touching rects; when more than `limit` remain, merge the closest pairs until they fit."""
    rs = [tuple(r) for r in rects if r[2] > r[0] and r[3] > r[1]]
    changed = True
    while changed:
        changed = False
        out = []
        while rs:
            a = rs.pop()
            i = 0
            while i < len(rs):
                b = rs[i]
                if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                    a = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                    rs.pop(i)
                    changed = True
                else:
                    i += 1
            out.append(a)
        rs = out
    while len(rs) > limit:
        best = None
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                u = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                cost = (u[2] - u[0]) * (u[3] - u[1]) - (a[2] - a[0]) * (a[3] - a[1]) - (b[2] - b[0]) * (b[3] - b[1])
                if best is None or cost < best[0]:
                    best = (cost, i, j, u)
        _, i, j, u = best
        rs = [r for k, r in enumerate(rs) if k not in (i, j)] + [u]
    return rs


def tile_keys(rects, w, h, tile=128):
    """The (tx, ty) origins of every `tile`-sized tile the rects touch, clipped to a w x h surface (the macOS arena window
    re-uploads exactly these)."""
    keys = set()
    for x0, y0, x1, y1 in rects:
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
        if x1 <= x0 or y1 <= y0:
            continue
        for ty in range((y0 // tile) * tile, y1, tile):
            for tx in range((x0 // tile) * tile, x1, tile):
                keys.add((tx, ty))
    return keys
