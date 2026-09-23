"""Viadotti: i ponti OSM piu' lunghi di LONG_BRIDGE diventano una mesh (impalcato, cordoli New Jersey, pile).

I ponti corti li gestisce build_terrain.py come strada normale sul terreno spianato. Qui l'impalcato unisce in
pendenza costante le quote del terreno gia' spianato alle due estremita' (dove arrivano le strade vicine).
Scrive build/shapes/ti_bridges.dae e build/bridges.json (tracciato con quote dell'impalcato, per i DecalRoad).

blender -b --factory-startup --python tools/build_bridges.py -- build/shapes
"""
import bpy, math, os, sys, json
import numpy as np
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dae_writer import MeshData, write_dae
from osm import OSM

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD = os.path.join(ROOT, "build")
OUT = sys.argv[sys.argv.index("--") + 1]
LONG_BRIDGE = 70.0
HW = {"trunk": 5.5, "trunk_link": 4, "primary": 5, "primary_link": 3.5, "secondary": 4.5, "tertiary": 4,
      "unclassified": 3, "residential": 3, "living_street": 2.5, "service": 2.2, "track": 1.6, "construction": 3.5}

M = np.load(os.path.join(BUILD, "terrain_masks.npz"))
TZ, X0, SQ = M["z"], float(M["x0"]), float(M["sq"])


def tz(x, y):
    fx, fy = (x - X0) / SQ, (y - X0) / SQ
    i, j = int(np.clip(fx, 0, TZ.shape[1] - 2)), int(np.clip(fy, 0, TZ.shape[0] - 2))
    ax, ay = fx - i, fy - j
    return float(TZ[j, i] * (1 - ax) * (1 - ay) + TZ[j, i + 1] * ax * (1 - ay) + TZ[j + 1, i] * (1 - ax) * ay + TZ[j + 1, i + 1] * ax * ay)


def quad(md, mat, a, b, c, d, n, tile=2.0):
    t = (b - a).normalized(); bt = n.cross(t)
    uvs = [((p - a).dot(t) / tile, (p - a).dot(bt) / tile) for p in (a, b, c, d)]
    P = (a, b, c, d)
    for tri in ((0, 1, 2), (0, 2, 3)):
        md.add_tri(mat, [(P[k].copy(), n.copy(), uvs[k], (0.0, 0.0)) for k in tri])


def prism(md, mat, rings, open_last=False):
    """solido estruso: rings = lista di sezioni (liste di Vector, stesso numero di vertici).
    open_last: salta il lato che chiude la sezione (ultimo -> primo vertice)."""
    for r0, r1 in zip(rings, rings[1:]):
        k = len(r0)
        for i in range(k - 1 if open_last else k):
            a, b = r0[i], r0[(i + 1) % k]; c, d = r1[(i + 1) % k], r1[i]
            n = (b - a).cross(d - a)
            if n.length < 1e-9:
                continue
            quad(md, mat, a, b, c, d, n.normalized())


def main():
    osm = OSM()
    md = MeshData("bridges")
    out = []
    for w, t in osm.ways_where(lambda t: t.get("highway") in HW and t.get("bridge") and t.get("bridge") != "no"):
        pts = np.array(osm.way_pts(w))
        if len(pts) < 2:
            continue
        seg = np.hypot(*np.diff(pts, axis=0).T); L = np.concatenate([[0], np.cumsum(seg)])
        if L[-1] <= LONG_BRIDGE or np.abs(pts).max() > 2000:
            continue
        s = np.arange(0, L[-1] + 1e-6, 2.0)
        if s[-1] < L[-1]:
            s = np.append(s, L[-1])
        P = np.stack([np.interp(s, L, pts[:, 0]), np.interp(s, L, pts[:, 1])], 1)
        z0, z1 = tz(*P[0]), tz(*P[-1])
        zd = z0 + (z1 - z0) * s / s[-1] + 0.6 * np.sin(np.pi * s / s[-1])   # leggera schiena d'asino
        hw = HW[t["highway"]] + 0.6
        tan = np.gradient(P, axis=0); tan /= np.linalg.norm(tan, axis=1, keepdims=True)
        nor = np.stack([-tan[:, 1], tan[:, 0]], 1)
        deck, parL, parR = [], [], []
        for p, n, z in zip(P, nor, zd):
            c = Vector((p[0], p[1], z)); nn = Vector((n[0], n[1], 0))
            e = hw + 0.45
            # sezione impalcato (piano stradale a z, spessore 1.3 m, sbalzi laterali)
            deck.append([c - nn * e + Vector((0, 0, -0.02)), c - nn * e + Vector((0, 0, -0.5)), c - nn * (hw - 1.2) + Vector((0, 0, -1.3)),
                         c + nn * (hw - 1.2) + Vector((0, 0, -1.3)), c + nn * e + Vector((0, 0, -0.5)), c + nn * e + Vector((0, 0, -0.02))])
            for side, lst in ((-1, parL), (1, parR)):          # cordolo New Jersey 0.9 m
                o = c + nn * side * (hw + 0.05)
                q = [o + nn * side * 0.0, o + nn * side * 0.0 + Vector((0, 0, 0.9)), o + nn * side * 0.2 + Vector((0, 0, 0.9)),
                     o + nn * side * 0.4 + Vector((0, 0, 0.0))]
                lst.append(q[::-1] if side > 0 else q)            # facce verso l'esterno
        prism(md, "ti_bridge_concrete", deck, open_last=True)     # il piano stradale e' un quad a parte
        prism(md, "ti_bridge_concrete", parL); prism(md, "ti_bridge_concrete", parR)
        # piano stradale (lo copre il DecalRoad) e testate
        for k in range(len(P) - 1):
            a, b = deck[k], deck[k + 1]
            quad(md, "ti_bridge_deck", a[0], b[0], b[5], a[5], Vector((0, 0, 1)), tile=4.0)
        for ring, sgn in ((deck[0], -1), (deck[-1], 1)):
            c = sum(ring, Vector()) / len(ring)
            for i in range(len(ring)):
                a, b = ring[i], ring[(i + 1) % len(ring)]
                n = (b - a).cross(c - a)
                nn_ = Vector((0, 0, 1)) if n.length < 1e-9 else n.normalized()
                for tri in ((a, b, c), (a, c, b)):              # testata visibile da entrambi i lati
                    md.add_tri("ti_bridge_concrete", [(tri[0].copy(), nn_, (0, 0), (0.0, 0.0)), (tri[1].copy(), nn_, (1, 0), (0.0, 0.0)),
                                                       (tri[2].copy(), nn_, (0.5, 1), (0.0, 0.0))])
        # pile ogni ~32 m dove l'impalcato e' alto sul terreno
        npile = 0
        for sp in np.arange(24, s[-1] - 20, 32.0):
            k = int(np.searchsorted(s, sp)); p = P[k]; z = zd[k]
            g = tz(*p)
            if z - g < 3.0:
                continue
            tt = Vector((tan[k][0], tan[k][1], 0)); nn = Vector((nor[k][0], nor[k][1], 0))
            for off in (-hw * 0.45, hw * 0.45):
                c = Vector((p[0], p[1], 0)) + nn * off
                ring = lambda zz: [c + tt * -0.8 + nn * -0.6 + Vector((0, 0, zz)), c + tt * 0.8 + nn * -0.6 + Vector((0, 0, zz)),
                                   c + tt * 0.8 + nn * 0.6 + Vector((0, 0, zz)), c + tt * -0.8 + nn * 0.6 + Vector((0, 0, zz))]
                prism(md, "ti_bridge_concrete", [ring(g - 1.5), ring(z - 1.25)])
            npile += 1
        out.append({"type": t["highway"], "name": t.get("name", ""), "hw": HW[t["highway"]], "oneway": t.get("oneway") == "yes",
                    "pts": [[float(p[0]), float(p[1]), float(z)] for p, z in zip(P[::2], zd[::2])] + [[float(P[-1][0]), float(P[-1][1]), float(zd[-1])]]})
        print("viadotto", t["highway"], t.get("name", ""), "L=%.0f" % L[-1], "pile", npile)
    write_dae(os.path.join(OUT, "ti_bridges.dae"), [md], Matrix.Identity(4))
    json.dump(out, open(os.path.join(BUILD, "bridges.json"), "w"), indent=1)
    print("BRIDGES_OK", len(out), md.tri_count())


main()
