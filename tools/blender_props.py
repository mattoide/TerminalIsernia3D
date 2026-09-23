"""Modelli aggiuntivi generati proceduralmente (riferimento: Street View 2022/2024, solo come guida visiva).

  ti_canopy.dae      pensiline a denti di sega sui due lati lunghi dell'edificio (travi verdi + pannelli traslucidi)
  ti_reeds.dae       ciuffo di canne (Arundo) alto 2.4-3.8 m, card con le texture d'erba lunga del gioco
  ti_lamp_globe.dae  lampione decorativo nero a due globi

blender -b --factory-startup --python tools/blender_props.py -- build/shapes
"""
import bpy, math, os, sys, random
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
from dae_writer import MeshData, write_dae

OUT = sys.argv[sys.argv.index("--") + 1]
os.makedirs(OUT, exist_ok=True)
GEO = Matrix.Translation((geo.MODEL_OFFSET[0], geo.MODEL_OFFSET[1], 0.0)) @ Matrix.Rotation(math.radians(geo.MODEL_ROT_DEG), 4, 'Z')
UP = Vector((0, 0, 1))


def quad(md, mat, a, b, c, d, uvs=None, n=None, tile=1.0, ref=None):
    n = n or (b - a).cross(d - a).normalized()
    if ref is not None and n.dot((a + b + c + d) / 4 - ref) < 0:     # normale verso l'esterno
        a, b, c, d = d, c, b, a
        n = -n
    if uvs is None:                                   # proiezione in metri sul piano del quad
        t = (b - a).normalized(); bt = n.cross(t)
        uvs = [((p - a).dot(t) / tile, (p - a).dot(bt) / tile) for p in (a, b, c, d)]
    P = (a, b, c, d)
    for tri in ((0, 1, 2), (0, 2, 3)):
        md.add_tri(mat, [(P[k].copy(), n, uvs[k], (0.0, 0.0)) for k in tri])


def box(md, mat, p0, p1, w, h=None, up=UP):
    """trave a sezione rettangolare w x h dal punto p0 al punto p1."""
    h = h or w
    ax = (p1 - p0)
    L = ax.length
    ax.normalize()
    s = ax.cross(up)
    if s.length < 1e-4:
        s = ax.cross(Vector((1, 0, 0)))
    s.normalize(); u = s.cross(ax).normalized()
    c = [p0 + s * sx * w / 2 + u * uy * h / 2 for sx, uy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    e = [q + ax * L for q in c]
    ctr = p0 + ax * (L / 2)
    for i in range(4):
        j = (i + 1) % 4
        quad(md, mat, c[i], c[j], e[j], e[i], ref=ctr)
    quad(md, mat, c[3], c[2], c[1], c[0], ref=ctr); quad(md, mat, e[0], e[1], e[2], e[3], ref=ctr)


# ----------------------------------------------------------------------------- pensiline
def canopy(md, origin, u, n, length, depth, z0, pitch=1.95, tooth_h=0.95, start=-0.8):
    """origin: punto sul muro (coordinate modello) all'inizio della fila di telai; u lungo la facciata, n verso l'esterno."""
    O = Vector((origin[0], origin[1], z0)); U = Vector((u[0], u[1], 0)); N = Vector((n[0], n[1], 0))
    teeth = max(1, int(round(length / pitch)))
    pitch = length / teeth
    for k in range(teeth):
        a = O + U * (start + k * pitch); m = a + U * (pitch / 2) + UP * tooth_h; b = a + U * pitch
        for (p, q) in ((a, m), (m, b)):                       # due falde traslucide per dente
            quad(md, "ti_canopy_panel", p, q, q + N * depth, p + N * depth, tile=2.0)
        for (p, q) in ((a, m), (m, b)):                       # telaio verde: falde, colmo e compluvio
            box(md, "ti_canopy_steel", p, q, 0.08)
            box(md, "ti_canopy_steel", p + N * depth, q + N * depth, 0.08)
        box(md, "ti_canopy_steel", m, m + N * depth, 0.08)
        box(md, "ti_canopy_steel", a, a + N * depth, 0.10)
        # arcarecci intermedi
        for f in (0.33, 0.66):
            box(md, "ti_canopy_steel", a + N * depth * f, m + N * depth * f, 0.05)
            box(md, "ti_canopy_steel", m + N * depth * f, b + N * depth * f, 0.05)
    end = O + U * (start + length)
    box(md, "ti_canopy_steel", end, end + N * depth, 0.10)
    # trave reticolare verde sulla linea dei pilastri e lungo il muro
    for off, hgt in ((depth - 0.25, 0.45), (0.15, 0.3)):
        base = O + N * off
        top = base + UP * hgt
        a0, a1 = base + U * start, base + U * (start + length)
        box(md, "ti_canopy_steel", a0, a1, 0.09)
        box(md, "ti_canopy_steel", a0 + UP * hgt, a1 + UP * hgt, 0.09)
        nseg = int(length / 0.9)
        for i in range(nseg):
            p = a0 + U * (length * i / nseg); q = a0 + U * (length * (i + 1) / nseg)
            box(md, "ti_canopy_steel", p if i % 2 == 0 else p + UP * hgt, q + UP * hgt if i % 2 == 0 else q, 0.04)


cmd = MeshData("canopy")
a = math.radians(-2.606)                                     # rotazione dell'edificio nel modello
U = (math.cos(a), math.sin(a))
# lato sud-est (facciata ad archi): muro a y~-13.37 in x=90.33, pilastri verso -y
canopy(cmd, (90.33, -13.37), U, (math.sin(a), -math.cos(a)), 17.6, 5.85, 5.19)
# lato nord-ovest: muro a y~-2.58 in x=91.06, pilastri verso +y
canopy(cmd, (91.06, -2.58), U, (-math.sin(a), math.cos(a)), 17.6, 5.85, 5.19)
write_dae(os.path.join(OUT, "ti_canopy.dae"), [cmd], GEO)

# ----------------------------------------------------------------------------- canne
random.seed(7)
rmd = MeshData("reeds")
for i in range(30):
    r = 0.95 * math.sqrt(random.random()); t = random.uniform(0, 2 * math.pi)
    base = Vector((r * math.cos(t), r * math.sin(t), -0.05))
    yaw = random.uniform(0, math.pi)
    d = Vector((math.cos(yaw), math.sin(yaw), 0)); w = random.uniform(0.55, 0.85)
    H = random.uniform(2.4, 3.8)
    lean = Vector((random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), 0))
    k = random.randrange(5); row = random.randrange(2)
    u0, u1 = k / 5, (k + 1) / 5; v0 = 0.5 * (1 - row); v1 = v0 + 0.5
    p0 = base - d * w / 2; p1 = base + d * w / 2
    p2 = p1 + UP * H + lean; p3 = p0 + UP * H + lean
    mat = "ti_reeds_dry" if random.random() < 0.25 else "ti_reeds"
    n = d.cross(UP).normalized().lerp(UP, 0.5).normalized()      # normali "morbide" verso l'alto, come l'erba vanilla
    quad(rmd, mat, p0, p1, p2, p3, uvs=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], n=n)
write_dae(os.path.join(OUT, "ti_reeds.dae"), [rmd], Matrix.Identity(4))

# ----------------------------------------------------------------------------- lampione a due globi
lmd = MeshData("lamp_globe")
def cyl(md, mat, z0, z1, r0, r1, seg=10, cx=0.0):
    C = Vector((cx, 0, 0))
    for i in range(seg):
        t0, t1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        a0 = Vector((math.cos(t0), math.sin(t0), 0)); a1 = Vector((math.cos(t1), math.sin(t1), 0))
        quad(md, mat, C + a0 * r0 + UP * z0, C + a1 * r0 + UP * z0, C + a1 * r1 + UP * z1, C + a0 * r1 + UP * z1,
             uvs=[(i / seg, z0), ((i + 1) / seg, z0), ((i + 1) / seg, z1), (i / seg, z1)], n=((a0 + a1) / 2).normalized())
def sphere(md, mat, c, r, seg=12, rings=8):
    for j in range(rings):
        p0, p1 = math.pi * j / rings - math.pi / 2, math.pi * (j + 1) / rings - math.pi / 2
        for i in range(seg):
            t0, t1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            v = [Vector((math.cos(pp) * math.cos(tt), math.cos(pp) * math.sin(tt), math.sin(pp))) for pp, tt in ((p0, t0), (p0, t1), (p1, t1), (p1, t0))]
            P = [c + q * r for q in v]
            for tri in ((0, 1, 2), (0, 2, 3)):
                md.add_tri(mat, [(P[k], v[k], (i / seg, j / rings), (0.0, 0.0)) for k in tri])
cyl(lmd, "ti_lamp_black", 0.0, 0.45, 0.13, 0.10)
cyl(lmd, "ti_lamp_black", 0.45, 3.35, 0.065, 0.05)
cyl(lmd, "ti_lamp_black", 3.35, 3.55, 0.05, 0.02)
for s in (-1, 1):
    pts = [Vector((0, 0, 3.15)), Vector((s * 0.22, 0, 3.32)), Vector((s * 0.42, 0, 3.42)), Vector((s * 0.52, 0, 3.36))]
    for p, q in zip(pts, pts[1:]):
        box(lmd, "ti_lamp_black", p, q, 0.035)
    c = Vector((s * 0.52, 0, 3.13))
    sphere(lmd, "ti_lamp_globe", c, 0.19)
    cyl(lmd, "ti_lamp_black", 3.28, 3.38, 0.14, 0.05, cx=s * 0.52)   # cappello del globo
write_dae(os.path.join(OUT, "ti_lamp_globe.dae"), [lmd], Matrix.Identity(4))
print("PROPS_OK", cmd.tri_count(), rmd.tri_count(), lmd.tri_count())
