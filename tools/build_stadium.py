"""Stadio Mario Lancellotta e campo d'allenamento (600 m a nord-est del terminal), dalla geometria OSM e dal satellite /
Street View (giugno 2024):

  - campo in erba 103 x 66 m (OSM) con le righe regolamentari e le porte, pista d'atletica a 6 corsie grigia (400 m)
    con la lunetta nord in tartan rosso e quella sud grigia con la buca del salto in lungo
  - recinzione in rete attorno alla pista (OSM), muretto di cemento con recinzione a sbarre sul perimetro (OSM)
  - tribuna ovest coperta a gradoni, gradinate est con copertura leggera (edifici OSM building=stadium / yes)
  - quattro torri faro a traliccio
  - campo d'allenamento in terra battuta a sud-ovest, con righe sbiadite e porte

blender -b --factory-startup --python tools/build_stadium.py -- build/shapes      (dopo build_terrain.py)
Scrive build/shapes/ti_stadium.dae (coordinate mondo) e build/stadium.json (posizioni delle torri faro per le luci).
"""
import bpy, math, os, sys, json
import numpy as np
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dae_writer import MeshData, write_dae
from osm import OSM, obb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD = os.path.join(ROOT, "build")
OUT = sys.argv[sys.argv.index("--") + 1]
UP = Vector((0, 0, 1))
_M = np.load(os.path.join(BUILD, "terrain_masks.npz"))
TZ, X0, SQ = _M["z"], float(_M["x0"]), float(_M["sq"])


def tz(x, y):
    fx, fy = (x - X0) / SQ, (y - X0) / SQ
    i, j = int(np.clip(fx, 0, TZ.shape[1] - 2)), int(np.clip(fy, 0, TZ.shape[0] - 2))
    ax, ay = fx - i, fy - j
    return float(TZ[j, i] * (1 - ax) * (1 - ay) + TZ[j, i + 1] * ax * (1 - ay) + TZ[j + 1, i] * (1 - ax) * ay + TZ[j + 1, i + 1] * ax * ay)


def quad(md, mat, a, b, c, d, tile=1.0, two=False, n=None):
    n = n or (b - a).cross(d - a).normalized()
    t = (b - a).normalized() if (b - a).length > 1e-6 else Vector((1, 0, 0)); bt = n.cross(t)
    uv = [((p - a).dot(t) / tile, (p - a).dot(bt) / tile) for p in (a, b, c, d)]
    P = (a, b, c, d)
    for tri in ((0, 1, 2), (0, 2, 3)):
        md.add_tri(mat, [(P[k].copy(), n, uv[k], (0.0, 0.0)) for k in tri])
    if two:
        for tri in ((2, 1, 0), (3, 2, 0)):
            md.add_tri(mat, [(P[k].copy(), -n, uv[k], (0.0, 0.0)) for k in tri])


def tri_up(md, mat, a, b, c, tile):
    if (b - a).cross(c - a).z < 0:
        b, c = c, b
    md.add_tri(mat, [(p.copy(), UP.copy(), (p.x / tile, p.y / tile), (0.0, 0.0)) for p in (a, b, c)])


def box(md, mat, p0, p1, w, h=None, tile=1.0):
    h = h or w
    ax = p1 - p0; L = ax.length
    if L < 1e-6:
        return
    ax.normalize()
    s = ax.cross(UP) if abs(ax.dot(UP)) < 0.95 else ax.cross(Vector((1, 0, 0)))
    s.normalize(); u = s.cross(ax).normalized()
    c = [p0 + s * sx * w / 2 + u * uy * h / 2 for sx, uy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    e = [q + ax * L for q in c]
    ctr = p0 + ax * (L / 2)
    for a, b, cc, d in [(c[i], c[(i + 1) % 4], e[(i + 1) % 4], e[i]) for i in range(4)] + [(c[3], c[2], c[1], c[0]), (e[0], e[1], e[2], e[3])]:
        n = (b - a).cross(d - a).normalized()
        if n.dot((a + cc) / 2 - ctr) < 0:
            a, b, cc, d = d, cc, b, a; n = -n
        quad(md, mat, a, b, cc, d, tile, n=n)


def ribbon(md, mat, P, w, z, closed=False, tile=1.0):
    """striscia orizzontale larga w lungo la polilinea P (liste di Vector/tuple 2D, gia' in mondo)."""
    P = [Vector((p[0], p[1], 0)) for p in P]
    if closed:
        P = P + [P[0]]
    for a, b in zip(P, P[1:]):
        t = (b - a); L = t.length
        if L < 1e-6:
            continue
        t /= L; n = Vector((-t.y, t.x, 0)) * (w / 2)
        quad(md, mat, a - n + UP * z, b - n + UP * z, b + n + UP * z, a + n + UP * z, tile, n=UP.copy())


class Frame:
    """sistema locale dello stadio: u lungo il campo (verso nord), v di traverso (verso ovest, la tribuna)."""
    def __init__(self, ctr, yaw, z):
        self.c = Vector((ctr[0], ctr[1], 0)); self.U = Vector((math.cos(yaw), math.sin(yaw), 0)); self.V = Vector((-math.sin(yaw), math.cos(yaw), 0))
        self.z = z

    def w(self, u, v, dz=0.0):
        p = self.c + self.U * u + self.V * v
        return Vector((p.x, p.y, self.z + dz))

    def uv(self, p):
        d = Vector((p[0], p[1], 0)) - self.c
        return d.dot(self.U), d.dot(self.V)


def oval(L2, r, n=24):
    """contorno di una pista: rettilinei lunghi 2*L2 a v = +-r e curve di raggio r (antiorario)."""
    pts = []
    for k in range(n + 1):                                   # curva nord (u > 0)
        a = -math.pi / 2 + math.pi * k / n
        pts.append((L2 + r * math.cos(a), r * math.sin(a)))
    for k in range(n + 1):                                   # curva sud
        a = math.pi / 2 + math.pi * k / n
        pts.append((-L2 + r * math.cos(a), r * math.sin(a)))
    return pts


def fill_fan(md, mat, F, P, dz, tile, ctr=(0.0, 0.0)):
    c = F.w(ctr[0], ctr[1], dz)
    Q = [F.w(u, v, dz) for u, v in P]
    for a, b in zip(Q, Q[1:] + Q[:1]):
        tri_up(md, mat, c, a, b, tile)


def ring(md, mat, F, P_in, P_out, dz, tile):
    A = [F.w(u, v, dz) for u, v in P_in]; B = [F.w(u, v, dz) for u, v in P_out]
    for i in range(len(A)):
        j = (i + 1) % len(A)
        a, b, c, d = A[i], A[j], B[j], B[i]
        if (b - a).cross(d - a).z < 0:
            a, b, c, d = d, c, b, a
        quad(md, mat, a, b, c, d, tile, n=UP.copy())


def pitch_lines(md, F, L, W, dz, mat="ti_line_white", lw=0.12):
    """righe regolamentari di un campo L x W centrato in (0, 0) del sistema F."""
    def poly(P, closed=False):
        ribbon(md, mat, [F.w(u, v) for u, v in P], lw, F.z + dz, closed)
    def arc(cu, cv, r, a0, a1, n=28):
        return [(cu + r * math.cos(a0 + (a1 - a0) * k / n), cv + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]
    hl, hw = L / 2, W / 2
    poly([(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)], True)
    poly([(0, -hw), (0, hw)])
    poly(arc(0, 0, 9.15, 0, 2 * math.pi, 48))
    for s in (-1, 1):
        x0 = s * hl
        poly([(x0, -20.16), (x0 - s * 16.5, -20.16), (x0 - s * 16.5, 20.16), (x0, 20.16)])
        poly([(x0, -9.16), (x0 - s * 5.5, -9.16), (x0 - s * 5.5, 9.16), (x0, 9.16)])
        a = math.acos(5.5 / 9.15)
        cu = x0 - s * 11.0
        poly(arc(cu, 0, 9.15, (math.pi if s > 0 else 0) - a, (math.pi if s > 0 else 0) + a, 12))
        for sv in (-1, 1):                                    # bandierine d'angolo
            poly(arc(x0, sv * hw, 1.0, math.pi / 2 * (0 if (s < 0 and sv < 0) else 1 if (s > 0 and sv < 0) else 3 if (s < 0 and sv > 0) else 2),
                     math.pi / 2 * (1 if (s < 0 and sv < 0) else 2 if (s > 0 and sv < 0) else 4 if (s < 0 and sv > 0) else 3), 6))
        for pu in (cu,):
            c = F.w(pu, 0, dz + 0.001)
            box(md, mat, c - F.U * 0.11, c + F.U * 0.11, 0.22, 0.002)
    c = F.w(0, 0, dz + 0.001)
    box(md, mat, c - F.U * 0.15, c + F.U * 0.15, 0.3, 0.002)


def goal(md, F, u, s, mat="ti_goal_white", net="ti_goal_net"):
    """porta 7.32 x 2.44 sulla linea di fondo u (s = +-1 verso l'esterno), con rete."""
    for v in (-3.66, 3.66):
        box(md, mat, F.w(u, v, 0), F.w(u, v, 2.44), 0.12)
        box(md, mat, F.w(u + s * 2.0, v, 0), F.w(u + s * 2.0, v, 1.5), 0.05)
        box(md, mat, F.w(u, v, 2.44), F.w(u + s * 1.0, v, 2.44), 0.05)
        box(md, mat, F.w(u + s * 1.0, v, 2.44), F.w(u + s * 2.0, v, 1.5), 0.05)
    box(md, mat, F.w(u, -3.72, 2.44), F.w(u, 3.72, 2.44), 0.12)
    box(md, mat, F.w(u + s * 2.0, -3.66, 0.02), F.w(u + s * 2.0, 3.66, 0.02), 0.05)
    a, b = F.w(u + s * 1.0, -3.66, 2.44), F.w(u + s * 1.0, 3.66, 2.44)
    c_, d_ = F.w(u + s * 2.0, 3.66, 1.5), F.w(u + s * 2.0, -3.66, 1.5)
    quad(md, net, a, b, F.w(u, 3.66, 2.44), F.w(u, -3.66, 2.44), 0.5, True)       # tetto della rete
    quad(md, net, d_, c_, b, a, 0.5, True)
    quad(md, net, F.w(u + s * 2.0, -3.66, 0), F.w(u + s * 2.0, 3.66, 0), c_, d_, 0.5, True)
    for v in (-3.66, 3.66):
        quad(md, net, F.w(u, v, 0), F.w(u + s * 2.0, v, 0), F.w(u + s * 2.0, v, 1.5), F.w(u, v, 2.44), 0.5, True)


def chain_fence(md, P, zf, h=1.2, step=2.5):
    """rete metallica su pali lungo la polilinea P (mondo), zf(x, y) quota."""
    for a, b in zip(P, P[1:]):
        A = Vector((a[0], a[1], zf(*a))); B = Vector((b[0], b[1], zf(*b)))
        L = (B - A).length
        n = max(1, int(round(L / step)))
        for k in range(n):
            p = A.lerp(B, k / n); q = A.lerp(B, (k + 1) / n)
            box(md, "ti_fence_post", p - UP * 0.3, p + UP * h, 0.06)
            quad(md, "ti_chainlink", p + UP * 0.05, q + UP * 0.05, q + UP * (h - 0.05), p + UP * (h - 0.05), 1.0, True)
            box(md, "ti_fence_post", p + UP * h, q + UP * h, 0.04)


def bar_wall(md, P, zf, wall_h=0.7, bar_h=2.3, pitch=0.3):
    """muretto di cemento con recinzione a sbarre piatte verticali (Street View giugno 2024)."""
    for a, b in zip(P, P[1:]):
        A = Vector((a[0], a[1], zf(*a))); B = Vector((b[0], b[1], zf(*b)))
        L = (B - A).length
        if L < 0.05:
            continue
        t = (B - A).normalized(); t.z = 0; t.normalize(); s = Vector((-t.y, t.x, 0))
        box(md, "ti_stadium_concrete", A + UP * (wall_h / 2 - 0.4), B + UP * (wall_h / 2 - 0.4), 0.3, wall_h + 0.8, 1.5)
        for zz in (wall_h + 0.1, wall_h + bar_h - 0.15):
            box(md, "ti_fence_bar", A + UP * zz, B + UP * zz, 0.05, 0.04)
        n = max(1, int(L / pitch))
        for k in range(n):
            p = A.lerp(B, (k + 0.5) / n) + UP * wall_h
            quad(md, "ti_fence_bar", p - t * 0.03, p + t * 0.03, p + t * 0.03 + UP * bar_h, p - t * 0.03 + UP * bar_h, 1.0, True)


def terrace(md, F, u0, u1, v0, v1, rows, rise, base, roof_h=None, roof_mat="ti_stand_roof", cols=6):
    """gradinata da v0 (fronte, verso il campo) a v1 (retro) tra u0 e u1 nel sistema F; roof_h: copertura."""
    sgn = 1 if v1 > v0 else -1
    dv = (v1 - v0) / rows
    front = F.w(u0, v0, 0), F.w(u1, v0, 0)
    quad(md, "ti_stadium_concrete", front[0] - UP * 0.3, front[1] - UP * 0.3, front[1] + UP * base, front[0] + UP * base, 1.5, True)
    for k in range(rows):
        za, zb = base + rise * k, base + rise * (k + 1)
        va, vb = v0 + dv * k, v0 + dv * (k + 1)
        quad(md, "ti_stadium_concrete", F.w(u0, va, za), F.w(u1, va, za), F.w(u1, va, zb), F.w(u0, va, zb), 1.5, True)      # alzata
        quad(md, "ti_stand_step", F.w(u0, va, zb), F.w(u1, va, zb), F.w(u1, vb, zb), F.w(u0, vb, zb), 1.5, True)            # pedata
        box(md, "ti_stand_seat", F.w(u0 + 0.3, va + dv * 0.35, zb + 0.22), F.w(u1 - 0.3, va + dv * 0.35, zb + 0.22), abs(dv) * 0.35, 0.08)
    top = base + rise * rows
    quad(md, "ti_stadium_concrete", F.w(u0, v1, -0.3), F.w(u1, v1, -0.3), F.w(u1, v1, top + 1.1), F.w(u0, v1, top + 1.1), 1.5, True)   # muro di fondo
    for u in (u0, u1):                                                                                                     # testate
        pts = [F.w(u, v0, -0.3), F.w(u, v1, -0.3), F.w(u, v1, top + 1.1), F.w(u, v0, base)]
        quad(md, "ti_stadium_concrete", *pts, 1.5, True)
    if roof_h:
        over = 2.5 * -sgn
        r = [F.w(u0 - 0.5, v0 + over, roof_h), F.w(u1 + 0.5, v0 + over, roof_h), F.w(u1 + 0.5, v1, roof_h + 0.8), F.w(u0 - 0.5, v1, roof_h + 0.8)]
        quad(md, roof_mat, *r, 2.0, True)
        box(md, "ti_fence_post", r[0], r[1], 0.25, 0.4)
        for k in range(cols + 1):
            u = u0 + (u1 - u0) * k / cols
            box(md, "ti_stand_column", F.w(u, v1 - sgn * 0.3, -0.3), F.w(u, v1 - sgn * 0.3, roof_h + 0.8), 0.3)
            box(md, "ti_stand_column", F.w(u, v1 - sgn * 0.3, roof_h + 0.8), F.w(u, v0 + over, roof_h), 0.2, 0.35)


def lattice_tower(md, base, H=28.0, look=None):
    """torre faro a traliccio con la batteria di proiettori in cima, rivolta verso 'look'."""
    legs = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        a = base + Vector((sx * 1.1, sy * 1.1, -0.5)); b = base + Vector((sx * 0.35, sy * 0.35, H))
        box(md, "ti_tower_steel", a, b, 0.14); legs.append((a, b))
    for k in range(9):
        t0, t1 = k / 9, (k + 1) / 9
        for i in range(4):
            a0, b0 = legs[i]; a1, b1 = legs[(i + 1) % 4]
            p, q = a0.lerp(b0, t0), a1.lerp(b1, t1)
            box(md, "ti_tower_steel", p, q, 0.06)
            box(md, "ti_tower_steel", a0.lerp(b0, t1), a1.lerp(b1, t1), 0.07)
    top = base + Vector((0, 0, H))
    d = (look - top) if look is not None else Vector((1, 0, 0)); d.z = 0; d.normalize()
    s = Vector((-d.y, d.x, 0))
    head = top + UP * 1.2 + d * 0.6
    box(md, "ti_tower_steel", top, head, 0.2)
    for r in range(3):
        for c in range(5):
            p = head + s * (c - 2) * 0.9 + UP * (r - 1) * 0.8
            box(md, "ti_tower_steel", p - d * 0.25, p + d * 0.25, 0.7, 0.6)
            quad(md, "ti_floodlight", p + d * 0.26 - s * 0.3 - UP * 0.25, p + d * 0.26 + s * 0.3 - UP * 0.25,
                 p + d * 0.26 + s * 0.3 + UP * 0.25, p + d * 0.26 - s * 0.3 + UP * 0.25, 1.0, n=d.copy())
    return head + d * 0.5


def inside(poly, x, y):
    """punto nel poligono (ray casting; nel Python di Blender non c'e' matplotlib)."""
    P = np.asarray(poly, float); xs, ys = P[:, 0], P[:, 1]
    xj, yj = np.roll(xs, 1), np.roll(ys, 1)
    cross = ((ys > y) != (yj > y)) & (x < (xj - xs) * (y - ys) / (yj - ys + 1e-12) + xs)
    return bool(np.count_nonzero(cross) % 2)


def main():
    osm = OSM()
    ways = list(osm.ways_where(lambda t: True))
    main_p = next((w, t) for w, t in ways if t.get("leisure") == "pitch" and "Lancellotta" in t.get("name", ""))
    P = np.array(osm.way_pts(main_p[0]))
    yaw, L, W, ctr = obb(P)
    if L < W:
        L, W, yaw = W, L, yaw + math.pi / 2
    # l'asse u deve puntare verso nord (lunetta rossa sulla curva nord)
    if math.sin(yaw) < 0:
        yaw += math.pi
    zs = [tz(ctr[0] + dx, ctr[1] + dy) for dx in range(-40, 41, 8) for dy in range(-40, 41, 8)]
    z0 = float(np.median(zs))
    F = Frame(ctr, yaw, z0)
    md = MeshData("stadium")
    L2, R_IN, LANES, LW = 84.39 / 2, 36.5, 6, 1.22
    R_OUT = R_IN + LANES * LW
    # campo e anello interno in erba, strisce di taglio sul campo
    fill_fan(md, "ti_pitch_grass", F, oval(L2, R_IN), 0.03, 3.0)
    n_str = 12
    for k in range(n_str):
        if k % 2:
            continue
        ua, ub = -L / 2 + L * k / n_str, -L / 2 + L * (k + 1) / n_str
        quad(md, "ti_pitch_grass_b", F.w(ua, -W / 2, 0.032), F.w(ub, -W / 2, 0.032), F.w(ub, W / 2, 0.032), F.w(ua, W / 2, 0.032), 3.0, n=UP.copy())
    # lunette: nord in tartan rosso, sud grigia con la buca del salto
    for s, mat in ((1, "ti_tartan_red"), (-1, "ti_track")):
        u_cut = s * (L / 2 + 3.0)
        arc = [(u, v) for u, v in oval(L2, R_IN, 48) if s * u > abs(u_cut) - 0.01]
        arc = sorted(arc, key=lambda p: s * math.atan2(p[1], s * (p[0] - s * L2)))       # in ordine lungo la curva
        fill_fan(md, mat, F, [(u_cut, arc[0][1])] + arc + [(u_cut, arc[-1][1])], 0.034, 2.0, ctr=(u_cut + s * 8.0, 0.0))
    for sv in (-1, 1):
        a = F.w(-L / 2 - 9.0, sv * 12.0, 0.036)
        quad(md, "ti_sand", a, a - F.U * 8.0, a - F.U * 8.0 + F.V * 2.8 * sv, a + F.V * 2.8 * sv, 2.0, two=True)
    # pista a 6 corsie con le righe e il traguardo
    ring(md, "ti_track", F, oval(L2, R_IN), oval(L2, R_OUT), 0.04, 3.0)
    for k in range(LANES + 1):
        ribbon(md, "ti_line_white", [F.w(u, v) for u, v in oval(L2, R_IN + k * LW, 36)], 0.05, z0 + 0.046, closed=True)
    ribbon(md, "ti_line_white", [F.w(L2, R_IN), F.w(L2, R_OUT)], 0.05, z0 + 0.047)
    pitch_lines(md, F, L, W, 0.036)
    for s in (-1, 1):
        goal(md, F, s * L / 2, s)
    # recinzione della pista (OSM) e muro di cinta con le sbarre (OSM)
    rings = [(w, t, np.array(osm.way_pts(w))) for w, t in ways if t.get("barrier") in ("fence", "wall")]
    zf = lambda x, y: max(tz(x, y), z0) if abs(tz(x, y) - z0) < 1.5 else tz(x, y)
    track_fence = max((r for r in rings if r[1]["barrier"] == "fence" and inside(r[2], ctr[0], ctr[1])), key=lambda r: len(r[2]), default=None)
    if track_fence is not None:
        chain_fence(md, [tuple(p) for p in track_fence[2]], lambda x, y: z0 + 0.02)
    outer = [r for r in rings if r[1]["barrier"] == "wall" and inside(r[2], ctr[0], ctr[1])]
    wall_pts = None
    if outer:
        wall_pts = max(outer, key=lambda r: len(r[2]))[2]
        bar_wall(md, [tuple(p) for p in wall_pts], zf)
    # tribune: edifici OSM dentro il muro di cinta
    stands = []
    for w, t in ways:
        if "building" not in t:
            continue
        Q = np.array(osm.way_pts(w))
        if len(Q) < 3 or wall_pts is None or not inside(wall_pts, *Q.mean(0)):
            continue
        by, bl, bw, bc = obb(Q)
        u_c, v_c = F.uv(bc)
        if bl < bw:
            bl, bw, by = bw, bl, by + math.pi / 2
        stands.append((t.get("building"), u_c, v_c, bl, bw))
    for kind, u_c, v_c, bl, bw in stands:
        if bl < 15:                                                          # gabbiotto
            p = F.w(u_c, v_c, 0)
            box(md, "ti_stadium_concrete", p - F.U * bl / 2 + UP * 1.4, p + F.U * bl / 2 + UP * 1.4, bw, 3.4, 1.5)
            continue
        sgn = 1 if v_c > 0 else -1                                           # il retro e' lontano dal campo
        v0, v1 = v_c - sgn * bw / 2, v_c + sgn * bw / 2
        if bw > 12:                                                          # tribuna principale coperta
            terrace(md, F, u_c - bl / 2, u_c + bl / 2, v0, v1, rows=14, rise=0.42, base=1.3, roof_h=11.5, cols=8)
        else:                                                                # gradinate con copertura leggera
            terrace(md, F, u_c - bl / 2, u_c + bl / 2, v0, v1, rows=max(4, int(bw / 0.8)), rise=0.38, base=0.8, roof_h=5.4,
                    roof_mat="ti_stand_roof_light", cols=max(3, int(bl / 8)))
    # torri faro ai quattro angoli, dentro il muro di cinta
    towers = []
    for su, sv in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        for k in range(12):
            u, v = su * (L2 + R_OUT * 0.72 + 6 - k), sv * (R_OUT + 5 - k * 0.3)
            p = F.w(u, v, 0)
            if wall_pts is None or inside(wall_pts, p.x, p.y):
                break
        p.z = zf(p.x, p.y)
        head = lattice_tower(md, p, 28.0, look=F.w(0, 0, 0))
        towers.append([round(head.x, 2), round(head.y, 2), round(head.z, 2)])
    # campo d'allenamento in terra battuta (OSM, a sud-ovest)
    tp = next(((w, t) for w, t in ways if t.get("leisure") == "pitch" and t is not main_p[1] and "name" not in t
               and np.hypot(*(np.array(osm.way_pts(w)).mean(0) - np.array(ctr))) < 160), None)
    if tp is not None:
        Q = np.array(osm.way_pts(tp[0])); ty, tl, tw, tc = obb(Q)
        if tl < tw:
            tl, tw, ty = tw, tl, ty + math.pi / 2
        zt = float(np.median([tz(tc[0] + dx, tc[1] + dy) for dx in range(-30, 31, 6) for dy in range(-20, 21, 5)]))
        G = Frame(tc, ty, zt)
        quad(md, "ti_dirt_pitch", G.w(-tl / 2 - 3, -tw / 2 - 3, 0.03), G.w(tl / 2 + 3, -tw / 2 - 3, 0.03),
             G.w(tl / 2 + 3, tw / 2 + 3, 0.03), G.w(-tl / 2 - 3, tw / 2 + 3, 0.03), 4.0, n=UP.copy())
        pitch_lines(md, G, tl, tw, 0.034, mat="ti_line_faded", lw=0.1)
        for s in (-1, 1):
            goal(md, G, s * tl / 2, s)
    write_dae(os.path.join(OUT, "ti_stadium.dae"), [md], Matrix.Identity(4))
    json.dump({"center": [ctr[0], ctr[1], z0], "towers": towers, "look": [ctr[0], ctr[1], z0]},
              open(os.path.join(BUILD, "stadium.json"), "w"), indent=1)
    print("STADIUM_OK tribune", len(stands), "torri", len(towers), "triangoli", md.tri_count(), "quota", round(z0, 2))


main()
