"""Arredo attorno al piazzale visto su Street View (settembre 2022 / giugno 2024), con le quote del terreno:

  - ringhiere a croce a pannelli colorati (rosso, giallo, verde, blu, bianco) lungo la Strada Comunale Rava a sud-ovest
    del piazzale: sul marciapiede sud-est (con il varco d'ingresso al "Parco calisthenics e fitness") e sul lato nord-ovest
  - all'ingresso del parco: due bacheche con la mappa e un cartello blu su due pali
  - il cubo di cemento con il murale sotto la pensilina, all'angolo sud-ovest dell'edificio

blender -b --factory-startup --python tools/build_extras.py -- build/shapes      (dopo build_terrain.py)
"""
import bpy, math, os, sys, json, random
import numpy as np
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import lot_layout as LL
from dae_writer import MeshData, write_dae

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD = os.path.join(ROOT, "build")
OUT = sys.argv[sys.argv.index("--") + 1]
GEO = Matrix.Translation((geo.MODEL_OFFSET[0], geo.MODEL_OFFSET[1], 0.0)) @ Matrix.Rotation(math.radians(geo.MODEL_ROT_DEG), 4, 'Z')
UP = Vector((0, 0, 1))

_M = np.load(os.path.join(BUILD, "terrain_masks.npz"))
TZ, X0, SQ = _M["z"], float(_M["x0"]), float(_M["sq"])


def tz_model(mx, my):
    """quota del terreno nel punto (x, y) del modello."""
    x, y = geo.model2world(mx, my)
    fx, fy = (x - X0) / SQ, (y - X0) / SQ
    i, j = int(np.clip(fx, 0, TZ.shape[1] - 2)), int(np.clip(fy, 0, TZ.shape[0] - 2))
    ax, ay = fx - i, fy - j
    return float(TZ[j, i] * (1 - ax) * (1 - ay) + TZ[j, i + 1] * ax * (1 - ay) + TZ[j + 1, i] * (1 - ax) * ay + TZ[j + 1, i + 1] * ax * ay)


def quad(md, mat, a, b, c, d, n=None, tile=1.0):
    n = n or (b - a).cross(d - a).normalized()
    t = (b - a).normalized(); bt = n.cross(t)
    uvs = [((p - a).dot(t) / tile, (p - a).dot(bt) / tile) for p in (a, b, c, d)]
    P = (a, b, c, d)
    for tri in ((0, 1, 2), (0, 2, 3)):
        md.add_tri(mat, [(P[k].copy(), n, uvs[k], (0.0, 0.0)) for k in tri])


def box(md, mat, p0, p1, w, h=None, tile=1.0, top_mat=None):
    """trave w x h da p0 a p1 (tutte le facce verso l'esterno)."""
    h = h or w
    ax = p1 - p0; L = ax.length; ax.normalize()
    s = ax.cross(UP) if abs(ax.dot(UP)) < 0.95 else ax.cross(Vector((1, 0, 0)))
    s.normalize(); u = s.cross(ax).normalized()
    c = [p0 + s * sx * w / 2 + u * uy * h / 2 for sx, uy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    e = [q + ax * L for q in c]
    ctr = p0 + ax * (L / 2)
    faces = [(c[i], c[(i + 1) % 4], e[(i + 1) % 4], e[i]) for i in range(4)] + [(c[3], c[2], c[1], c[0]), (e[0], e[1], e[2], e[3])]
    for k, (a, b, cc, d) in enumerate(faces):
        n = (b - a).cross(d - a).normalized()
        if n.dot((a + cc) / 2 - ctr) < 0:
            a, b, cc, d = d, cc, b, a; n = -n
        quad(md, top_mat if (top_mat and n.z > 0.9) else mat, a, b, cc, d, n, tile)


COLORS = ["ti_rail_red", "ti_rail_yellow", "ti_rail_green", "ti_rail_blue", "ti_rail_white"]


def color_railing(md, P, zf, h=1.0, bay=2.0, gaps=(), seed=1):
    """ringhiera a croce fatta di telai indipendenti, ognuno dipinto di un colore (Street View 2024).
    P: polilinea nel modello; zf(x, y): quota della base; gaps: intervalli di x senza ringhiera (varchi)."""
    rnd = random.Random(seed)
    L = [0.0]
    for a, b in zip(P, P[1:]):
        L.append(L[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))

    def at(sv):
        for k in range(len(P) - 1):
            if sv <= L[k + 1] or k == len(P) - 2:
                u = (sv - L[k]) / max(1e-6, L[k + 1] - L[k])
                return (P[k][0] + (P[k + 1][0] - P[k][0]) * u, P[k][1] + (P[k + 1][1] - P[k][1]) * u)
    nb = max(1, int(round(L[-1] / bay)))
    last = None
    n = 0
    for k in range(nb):
        a, b = at(L[-1] * k / nb), at(L[-1] * (k + 1) / nb)
        if any(g0 < (a[0] + b[0]) / 2 < g1 for g0, g1 in gaps):
            continue
        col = rnd.choice([c for c in COLORS if c != last]); last = col
        t = Vector((b[0] - a[0], b[1] - a[1], 0)).normalized()
        pa = Vector((a[0], a[1], zf(*a))) + t * 0.03
        pb = Vector((b[0], b[1], zf(*b))) - t * 0.03
        for p in (pa, pb):
            box(md, col, p - UP * 0.3, p + UP * h, 0.05)
        box(md, col, pa + UP * 0.1, pb + UP * 0.1, 0.04)
        box(md, col, pa + UP * (h - 0.03), pb + UP * (h - 0.03), 0.05)
        box(md, col, pa + UP * 0.13, pb + UP * (h - 0.06), 0.035)
        box(md, col, pb + UP * 0.13, pa + UP * (h - 0.06), 0.035)
        n += 1
    return n


def board(md, c, z0, face=Vector((0, 1, 0)), w=1.0, hh=1.25, zc=1.35, panel="ti_map_panel", post="ti_lamp_pole", post_h=2.1):
    """pannello su due pali, rivolto verso 'face' (la strada)."""
    s = face.cross(UP).normalized()
    for sx in (-1, 1):
        p = c + s * sx * (w / 2 + 0.05)
        box(md, post, Vector((p.x, p.y, z0 - 0.3)), Vector((p.x, p.y, z0 + post_h)), 0.06)
    ctr = Vector((c.x, c.y, z0 + zc))
    box(md, panel, ctr - s * w / 2, ctr + s * w / 2, 0.03, hh)
    box(md, "ti_lamp_pole", ctr - s * (w / 2 + 0.02) + UP * (hh / 2), ctr + s * (w / 2 + 0.02) + UP * (hh / 2), 0.05)   # cornice alta


def main():
    md = MeshData("extras")
    rava = next(r for r in json.load(open(os.path.join(BUILD, "terrain_info.json")))["roads"] if r.get("name") == "Strada Comunale Rava")
    C = np.array([geo.world2model(p[0], p[1]) for p in rava["pts"]])
    order = np.argsort(C[:, 0]); C = C[order]
    hw = rava["hw"]

    def rava_y(x):
        return float(np.interp(x, C[:, 0], C[:, 1]))
    # 1) lato sud-est: la ringhiera del marciapiede sud-est diventa colorata da x -25 verso ovest, varco al parco
    se = [(x, LL.se_rail_y(x)) for x in np.arange(LL.SE_COLOR_FROM_X, LL.SE_WEST_X - 0.01, -2.0)]
    n_se = color_railing(md, se, lambda x, y: 0.0, gaps=[LL.PARK_GAP], seed=3)
    # 2) lato nord-ovest della Rava, dall'angolo sud-ovest del piazzale verso ovest, subito oltre il ciglio
    nw = [(x, rava_y(x) + hw + 1.3) for x in np.arange(LL.NW_COLOR_FROM_X, LL.NW_COLOR_TO_X - 0.01, -2.0)]
    n_nw = color_railing(md, nw, lambda x, y: tz_model(x, y), seed=7)
    # 3) ingresso del parco: due bacheche con la mappa e il cartello blu, rivolti verso la strada (+y)
    for bx in LL.PARK_BOARDS_X:
        by = LL.se_rail_y(bx) - 1.8
        board(md, Vector((bx, by, 0)), tz_model(bx, by))
    sx, sy = LL.PARK_SIGN
    board(md, Vector((sx, sy, 0)), tz_model(sx, sy), w=1.5, hh=0.95, zc=2.0, panel="ti_sign_blue", post_h=2.5)
    # 4) cubo di cemento col murale sotto la pensilina (Street View 2022), sulla piattaforma dell'edificio (z 0.1)
    cx, cy = LL.GRAFFITI_CUBE
    box(md, "ti_bld_graffiti", Vector((cx, cy, 0.05)), Vector((cx, cy, 1.9)), 1.3, 1.3, tile=1.8, top_mat="ti_curb")
    # 5) cantiere a ovest della stradina dell'autolavaggio (satellite 2026): platea di fondazione con cordolo e travi
    from osm import OSM, obb
    osm = OSM()
    best = None
    for w, t in osm.ways_where(lambda t: "building" in t):
        Q = np.array(osm.way_pts(w))
        if len(Q) < 3:
            continue
        m = np.array([geo.world2model(*p) for p in Q]).mean(0)
        dd = math.hypot(m[0] - LL.CANTIERE_AT[0], m[1] - LL.CANTIERE_AT[1])
        if dd < 20 and (best is None or dd < best[0]):
            best = (dd, obb(Q))
    if best:
        yaw, BL, BW, bc = best[1]                                             # obb in coordinate mondo -> modello
        yaw -= math.radians(geo.MODEL_ROT_DEG)
        u = Vector((math.cos(yaw), math.sin(yaw), 0)); v = Vector((-math.sin(yaw), math.cos(yaw), 0))
        c = Vector((*geo.world2model(bc[0], bc[1]), 0))
        zs = [tz_model(*(c + u * a + v * b).xy) for a in (-BL / 2, 0, BL / 2) for b in (-BW / 2, 0, BW / 2)]
        z0 = float(np.median(zs)) + 0.35
        W = lambda a, b, dz=0.0: c + u * a + v * b + Vector((0, 0, z0 + dz))
        box(md, "ti_stadium_concrete", W(-BL / 2, 0, -0.6), W(BL / 2, 0, -0.6), BW, 1.3, tile=3.0, top_mat="ti_slab_concrete")
        for a in np.linspace(-BL / 2 + 0.3, BL / 2 - 0.3, 7):                  # travi di fondazione e cordolo
            box(md, "ti_stadium_concrete", W(a, -BW / 2 + 0.3, 0.2), W(a, BW / 2 - 0.3, 0.2), 0.5, 0.4, tile=2.0)
        for b in np.linspace(-BW / 2 + 0.3, BW / 2 - 0.3, 4):
            box(md, "ti_stadium_concrete", W(-BL / 2 + 0.3, b, 0.2), W(BL / 2 - 0.3, b, 0.2), 0.5, 0.4, tile=2.0)
        for a in np.linspace(-BL / 2 + 0.3, BL / 2 - 0.3, 7):                  # ferri di ripresa sui pilastri
            for b in np.linspace(-BW / 2 + 0.3, BW / 2 - 0.3, 4):
                for dx, dy in ((-0.12, -0.12), (0.12, -0.12), (0.12, 0.12), (-0.12, 0.12)):
                    p0 = W(a + dx, b + dy, 0.4)
                    box(md, "ti_rebar", p0, p0 + Vector((0, 0, 1.1)), 0.025)
        print("cantiere: platea", round(BL, 1), "x", round(BW, 1), "a quota", round(z0, 2))
    write_dae(os.path.join(OUT, "ti_extras.dae"), [md], GEO)
    print("EXTRAS_OK ringhiera sud-est", n_se, "telai, nord-ovest", n_nw, "telai, triangoli", md.tri_count())


main()
