"""Lettura dei dati OpenStreetMap (c) OpenStreetMap contributors, licenza ODbL.

Il file src/osm/isernia_osm.json e' l'output grezzo di Overpass (out body; >; out skel qt).
"""
import json, os, math
import numpy as np
from geo import ll2en

HERE = os.path.dirname(os.path.abspath(__file__))
OSM_FILE = os.path.join(HERE, "..", "src", "osm", "isernia_osm.json")


class OSM:
    def __init__(self, path=OSM_FILE):
        d = json.load(open(path, encoding="utf8"))
        self.nodes, self.ways, self.rels = {}, {}, {}
        for e in d["elements"]:
            if e["type"] == "node":
                self.nodes[e["id"]] = e
            elif e["type"] == "way":
                self.ways[e["id"]] = e
            elif e["type"] == "relation":
                self.rels[e["id"]] = e
        self.en = {i: ll2en(n["lat"], n["lon"]) for i, n in self.nodes.items()}

    def way_pts(self, w):
        return [self.en[n] for n in w["nodes"] if n in self.en]

    def ways_where(self, fn):
        for w in self.ways.values():
            t = w.get("tags", {})
            if t and fn(t):
                yield w, t

    def polygons_where(self, fn):
        """poligoni (liste di punti EN) da way chiuse e da multipolygon (solo anelli esterni)."""
        for w, t in self.ways_where(fn):
            pts = self.way_pts(w)
            if len(pts) >= 4 and w["nodes"][0] == w["nodes"][-1]:
                yield pts, t
        for r in self.rels.values():
            t = r.get("tags", {})
            if not t or not fn(t):
                continue
            outers = [self.ways[m["ref"]] for m in r.get("members", [])
                      if m["type"] == "way" and m.get("role") in ("outer", "") and m["ref"] in self.ways]
            for ring in _join_rings(outers):
                pts = [self.en[n] for n in ring if n in self.en]
                if len(pts) >= 4:
                    yield pts, t


def _join_rings(ways):
    segs = [list(w["nodes"]) for w in ways]
    rings = []
    while segs:
        cur = segs.pop(0)
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == cur[-1]:
                    cur += s[1:]
                elif s[-1] == cur[-1]:
                    cur += s[::-1][1:]
                elif s[-1] == cur[0]:
                    cur = s[:-1] + cur
                elif s[0] == cur[0]:
                    cur = s[::-1][:-1] + cur
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        if cur[0] == cur[-1]:
            rings.append(cur)
    return rings


def obb(pts):
    """rettangolo orientato minimo di un poligono: (angolo, lato lungo, lato corto, centro)."""
    P = np.asarray(pts)[:-1] if np.allclose(pts[0], pts[-1]) else np.asarray(pts)
    best = None
    for i in range(len(P)):
        e = P[(i + 1) % len(P)] - P[i]
        if np.hypot(*e) < 0.5:
            continue
        a = math.atan2(e[1], e[0]); c, s = math.cos(a), math.sin(a)
        R = np.array([[c, s], [-s, c]]); Q = P @ R.T
        mn, mx = Q.min(0), Q.max(0); area = np.prod(mx - mn)
        if best is None or area < best[0]:
            ctr = ((mn + mx) / 2) @ R
            best = (area, a, mx - mn, ctr)
    if best is None:
        return None
    area, a, (L, W), ctr = best
    if W > L:
        L, W, a = W, L, a + math.pi / 2
    return a, L, W, ctr
