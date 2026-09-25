"""Modelli aggiuntivi generati proceduralmente (riferimento: Street View 2022/2024, solo come guida visiva).

  ti_canopy.dae      pensiline a denti di sega sui due lati lunghi dell'edificio (travi verdi + pannelli traslucidi)
  ti_reeds.dae       ciuffo di canne (Arundo) alto 2.4-3.8 m, card con le texture d'erba lunga del gioco
  ti_lamp_globe.dae  lampione decorativo nero a due globi
  ti_lamp_pastorale.dae  lampione del piazzale (Street View 2022): palo conico zincato ~8.3 m, braccio curvo e
                     corpo illuminante piatto in punta (testa a y=1.62, z=9.1 nel sistema locale, braccio verso +Y)
  ti_grilles.dae     grate metalliche nei tre archi della facciata sud-est (misurati sulla mesh: luce 1.97 m,
                     imposta 2.20 m, chiave 3.08 m, muro a y modello -14.1..-13.35)
  ti_bacheca.dae     la bacheca del marciapiede sud-est
  ti_willow.dae      grande salice piangente oltre il marciapiede nord-ovest (Street View 2022): tronco e branche
                     con la corteccia di pioppo del gioco, chioma a cupola di ~13 m con "tende" di rametti pendenti

blender -b --factory-startup --python tools/blender_props.py -- build/shapes
"""
import bpy, math, os, sys, random
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import lot_layout as LL
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
    mat = "ti_reeds_dry" if random.random() < 0.12 else "ti_reeds"
    n = d.cross(UP).normalized().lerp(UP, 0.5).normalized()      # normali "morbide" verso l'alto, come l'erba vanilla
    quad(rmd, mat, p0, p1, p2, p3, uvs=[(u0, v0), (u1, v0), (u1, v1), (u0, v1)], n=n)
    if random.random() < 0.35:                                  # pennacchio in cima (Arundo in autunno, Street View 2022)
        k2 = random.randrange(4); pu0, pu1 = k2 / 4, (k2 + 1) / 4
        top = base + UP * H + lean; pw = random.uniform(0.3, 0.45); ph = random.uniform(0.45, 0.7)
        q0 = top - d * pw / 2 - UP * 0.1; q1 = top + d * pw / 2 - UP * 0.1
        quad(rmd, "ti_reed_plume", q0, q1, q1 + UP * ph + lean * 0.1, q0 + UP * ph + lean * 0.1,
             uvs=[(pu0, 0.0), (pu1, 0.0), (pu1, 1.0), (pu0, 1.0)], n=n)
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


# ----------------------------------------------------------------------------- grate negli archi
gmd = MeshData("grilles")
Y_MID = -13.73                                              # a meta' dello spessore del muro
for xa, xb in ((92.46, 94.42), (97.46, 99.40), (102.44, 104.40)):
    xc, r = (xa + xb) / 2, (xb - xa) / 2
    z_sp, z_cr = 2.20, 3.08
    arch = lambda x: z_sp + math.sqrt(max(0.0, r * r - (x - xc) ** 2)) * (z_cr - z_sp) / r
    # montanti tondi (sezione 22 mm) ogni 12 cm, tagliati sulla curva dell'arco
    for x in [xa + 0.07 + k * 0.12 for k in range(int((xb - xa - 0.1) / 0.12) + 1)]:
        if x > xb - 0.05:
            break
        box(gmd, "ti_grille", Vector((x, Y_MID, 0.12)), Vector((x, Y_MID, arch(x) - 0.03)), 0.022)
    # traversi piatti 50x10 mm
    for z in (0.22, 1.15, 2.12):
        box(gmd, "ti_grille", Vector((xa + 0.02, Y_MID, z)), Vector((xb - 0.02, Y_MID, z)), 0.012, 0.05)
    # telaio: montanti laterali e arco a segmenti
    box(gmd, "ti_grille", Vector((xa + 0.025, Y_MID, 0.1)), Vector((xa + 0.025, Y_MID, z_sp)), 0.04)
    box(gmd, "ti_grille", Vector((xb - 0.025, Y_MID, 0.1)), Vector((xb - 0.025, Y_MID, z_sp)), 0.04)
    pts = [Vector((xc - (r - 0.025) * math.cos(t), Y_MID, z_sp + (r - 0.025) * math.sin(t) * (z_cr - z_sp) / r)) for t in
           [math.pi * k / 16 for k in range(17)]]
    for p, q in zip(pts, pts[1:]):
        box(gmd, "ti_grille", p, q, 0.04)
write_dae(os.path.join(OUT, "ti_grilles.dae"), [gmd], GEO)

# ----------------------------------------------------------------------------- salice piangente
def tube(md, mat, p0, p1, r0, r1, seg=8, v0=0.0):
    """tronco/ramo conico da p0 a p1 (uv: u attorno, v lungo in metri/1.5)."""
    ax = (p1 - p0); L = ax.length; ax = ax.normalized()
    s = ax.cross(UP if abs(ax.dot(UP)) < 0.95 else Vector((1, 0, 0))).normalized(); u = ax.cross(s).normalized()
    for i in range(seg):
        t0, t1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        a0 = s * math.cos(t0) + u * math.sin(t0); a1 = s * math.cos(t1) + u * math.sin(t1)
        q = [p0 + a0 * r0, p0 + a1 * r0, p1 + a1 * r1, p1 + a0 * r1]
        n = [a0, a1, a1, a0]
        uv = [(i / seg, v0), ((i + 1) / seg, v0), ((i + 1) / seg, v0 + L / 1.5), (i / seg, v0 + L / 1.5)]
        for tri in ((0, 1, 2), (0, 2, 3)):
            md.add_tri(mat, [(q[k].copy(), n[k].copy(), uv[k], (0.0, 0.0)) for k in tri])
    return v0 + L / 1.5


def limb(md, pts, r0, r1, seg):
    v = 0.0
    for k in range(len(pts) - 1):
        a = r0 + (r1 - r0) * k / (len(pts) - 1); b = r0 + (r1 - r0) * (k + 1) / (len(pts) - 1)
        v = tube(md, "ti_willow_bark", pts[k], pts[k + 1], a, b, seg, v)


random.seed(11)
wmd = MeshData("willow")
# tronco leggermente inclinato, poi 5 branche principali che salgono e si aprono
base_lean = Vector((0.25, -0.1, 0))
limb(wmd, [Vector((0, 0, -0.3)), Vector((0, 0, 1.2)) + base_lean * 0.4, Vector((0, 0, 2.5)) + base_lean], 0.40, 0.31, 12)
top = Vector((0, 0, 2.5)) + base_lean
tips = []
for i in range(5):
    a = 2 * math.pi * i / 5 + random.uniform(-0.3, 0.3)
    d = Vector((math.cos(a), math.sin(a), 0))
    el = math.radians(random.uniform(38, 58)); Ll = random.uniform(5.0, 6.5)
    p1 = top + d * 0.3 + UP * 0.2
    p2 = p1 + (d * math.cos(el) + UP * math.sin(el)) * Ll * 0.45
    p3 = p2 + (d * math.cos(el * 0.8) + UP * math.sin(el * 0.8)) * Ll * 0.35
    p4 = p3 + (d * 0.9 + UP * 0.25).normalized() * Ll * 0.25
    limb(wmd, [p1, p2, p3, p4], 0.21, 0.06, 8)
    for k in range(3):                                         # rami secondari ad arco
        t = random.uniform(0.35, 0.9)
        q0 = p2.lerp(p3, t) if t < 0.7 else p3.lerp(p4, (t - 0.7) / 0.3)
        b = a + random.uniform(-0.9, 0.9); e = Vector((math.cos(b), math.sin(b), 0))
        q1 = q0 + (e * 0.8 + UP * 0.6).normalized() * random.uniform(1.0, 1.6)
        q2 = q1 + (e * 1.0 + UP * 0.05).normalized() * random.uniform(1.0, 1.8)
        q3 = q2 + (e * 0.8 - UP * 0.5).normalized() * random.uniform(0.6, 1.2)
        limb(wmd, [q0, q1, q2, q3], 0.055, 0.02, 5)
        tips.append(q2)
    tips.append(p4)

# chioma: cupola (raggio orizzontale ~6.6 m, cima ~10.3 m) da cui pendono le tende di rametti
C0 = Vector((0.2, -0.1, 5.4)); RH, RV = 6.6, 4.9
NCOL = 8


def strand(md, p, L, w, facing, mat="ti_willow_leaves"):
    """una tenda: due quad verticali che scendono per L metri dal punto p, rivolti verso 'facing'."""
    col = random.randrange(NCOL); u0, u1 = col / NCOL, (col + 1) / NCOL
    t = UP.cross(facing).normalized()
    bow = facing * random.uniform(0.15, 0.45)                  # la tenda si allarga un po' verso il basso
    sway = t * random.uniform(-0.2, 0.2)
    mid = p - UP * (L * 0.5) + bow * 0.6 + sway * 0.5
    bot = p - UP * L + bow + sway
    vt, vb = 1.0, max(0.0, 1.0 - L / 6.5)                      # la texture copre 6.5 m di tenda
    vm = (vt + vb) / 2
    nrm = (facing * 0.7 + UP * 0.3).normalized()               # normali morbide verso fuori, come il fogliame vanilla
    rows = [(p, vt), (mid, vm), (bot, vb)]
    for (a, va), (b, vb2) in zip(rows, rows[1:]):
        q = [a - t * w / 2, a + t * w / 2, b + t * w / 2, b - t * w / 2]
        uv = [(u0, va), (u1, va), (u1, vb2), (u0, vb2)]
        for tri in ((0, 3, 2), (0, 2, 1)):
            md.add_tri(mat, [(q[k].copy(), nrm.copy(), uv[k], (0.0, 0.0)) for k in tri])


def dome_point(theta, phi, shrink=1.0):
    """theta: azimut, phi: 0 = equatore .. pi/2 = cima."""
    r = RH * shrink * (1 + 0.12 * math.sin(3 * theta + 1.3) + 0.06 * math.sin(7 * theta) + 0.05 * math.sin(2 * theta + 0.4))
    return C0 + Vector((math.cos(theta) * math.cos(phi) * r, math.sin(theta) * math.cos(phi) * r, math.sin(phi) * RV * shrink))


n_str = 0
clumps = [(random.uniform(0, 2 * math.pi), math.asin(random.uniform(-0.05, 0.95)), random.uniform(0.9, 1.08)) for _ in range(80)]
for i in range(560):                                           # tende esterne, a ciocche (varchi scuri tra una e l'altra)
    cth, cph, cr = clumps[random.randrange(len(clumps))]
    th = cth + random.gauss(0, 0.09)
    ph = min(1.35, max(-0.05, cph + random.gauss(0, 0.07)))
    p = dome_point(th, ph, shrink=cr)
    face = Vector((math.cos(th), math.sin(th), 0))
    # dall'alto scendono piu' lunghe: il bordo della tenda arriva a 0.6-1.8 m da terra
    L = max(1.2, p.z - random.uniform(0.15, 0.9)) * random.uniform(0.82, 1.0)   # la tenda arriva quasi a terra
    if ph > 1.1:
        L = random.uniform(1.5, 3.0)                           # in cima solo ciuffi corti
    w = random.uniform(0.7, 1.1)
    strand(wmd, p, L, w, face)
    face2 = (face + UP.cross(face) * random.choice([-1, 1]) * 1.2).normalized()   # seconda card incrociata
    strand(wmd, p + face * 0.1, L * random.uniform(0.7, 0.95), w * 0.8, face2)
    n_str += 2
for i in range(140):                                           # riempimento interno (chioma meno trasparente)
    th = random.uniform(0, 2 * math.pi); ph = random.uniform(0.2, 1.2)
    p = dome_point(th, ph, shrink=random.uniform(0.45, 0.8))
    face = Vector((math.cos(th), math.sin(th), 0))
    strand(wmd, p, random.uniform(1.5, 3.5), random.uniform(0.8, 1.2), face)
    n_str += 1
write_dae(os.path.join(OUT, "ti_willow.dae"), [wmd], Matrix.Identity(4))

# ----------------------------------------------------------------------------- lampione a pastorale
pmd = MeshData("lamp_pastorale")
tube(pmd, "ti_lamp_pole", Vector((0, 0, 0)), Vector((0, 0, 0.45)), 0.13, 0.12, 12)           # collare alla base
tube(pmd, "ti_lamp_pole", Vector((0, 0, 0.45)), Vector((0, 0, 8.3)), 0.085, 0.056, 12)        # palo conico
arc = [Vector((0, 1.0 - math.cos(t), 8.3 + math.sin(t))) for t in [math.radians(a) for a in range(0, 86, 5)]]
tip = arc[-1] + Vector((0, 0.62, -0.05))
for a, b in zip(arc + [tip][:0], arc[1:]):
    tube(pmd, "ti_lamp_pole", a, b, 0.05, 0.047, 10)
tube(pmd, "ti_lamp_pole", arc[-1], tip, 0.047, 0.045, 10)
# corpo illuminante: scatola piatta 0.65 x 0.28 x 0.11, sotto il diffusore emissivo
hc = Vector((0, 1.62, 9.18))
hx, hy, hz = 0.14, 0.33, 0.055
V = lambda sx, sy, sz: hc + Vector((sx * hx, sy * hy, sz * hz))
c = [V(-1, -1, -1), V(1, -1, -1), V(1, 1, -1), V(-1, 1, -1), V(-1, -1, 1), V(1, -1, 1), V(1, 1, 1), V(-1, 1, 1)]
quad(pmd, "ti_lamp_pole", c[4], c[5], c[6], c[7], ref=hc)                                     # coperchio
for i in range(4):
    j = (i + 1) % 4
    quad(pmd, "ti_lamp_pole", c[i], c[j], c[j + 4], c[i + 4], ref=hc)
quad(pmd, "ti_lamp_head", c[3], c[2], c[1], c[0], ref=hc)                                     # diffusore (sotto)
write_dae(os.path.join(OUT, "ti_lamp_pastorale.dae"), [pmd], Matrix.Identity(4))

# ----------------------------------------------------------------------------- lucernario a piramide sul tetto
# Street View set 2022: piramide di vetro chiaro al centro della copertura (tetto a z 5.2, centro x 98.75 y -8.3)
smd = MeshData("skylight")
sc, sb, sh = Vector((98.75, -8.3, 5.2)), 1.7, 3.6            # la punta supera i denti delle pensiline (foto)
base4 = [sc + Vector((sx * sb, sy * sb, 0)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
apex = sc + Vector((0, 0, sh))
for i in range(4):
    a, b = base4[i], base4[(i + 1) % 4]
    n = (b - a).cross(apex - a).normalized()
    if n.dot((a + b + apex) / 3 - sc) < 0:
        a, b, n = b, a, -n
    smd.add_tri("ti_skylight_glass", [(a.copy(), n, (0, 0), (0.0, 0.0)), (b.copy(), n, (1, 0), (0.0, 0.0)), (apex.copy(), n, (0.5, 1), (0.0, 0.0))])
    box(smd, "ti_skylight_frame", a, apex, 0.07)                       # costoloni
    box(smd, "ti_skylight_frame", a, b, 0.09)                          # telaio di base
    for t in (0.33, 0.66):                                             # traversi intermedi
        box(smd, "ti_skylight_frame", a.lerp(apex, t), b.lerp(apex, t), 0.04)
box(smd, "ti_skylight_frame", sc + Vector((0, 0, -0.3)), sc + Vector((0, 0, 0.05)), 3.5, 3.5)   # zoccolo
write_dae(os.path.join(OUT, "ti_skylight.dae"), [smd], GEO)

# ----------------------------------------------------------------------------- linea elettrica lungo il lato sud-est
# Street View set 2022: pali di cemento chiari appena oltre la ringhiera sud-est, un cavo solo
emd = MeshData("powerline")
tops = []
for x in [-30 + 37.0 * k for k in range(5)]:
    b = Vector((x, LL.se_rail_y(x) - 0.8, -0.4))                       # appena oltre la ringhiera, nel verde
    tube(emd, "ti_pole_concrete", b - Vector((0, 0, 1.2)), b + Vector((0, 0, 9.4)), 0.14, 0.08, 8)   # interrato: il terreno scende
    box(emd, "ti_pole_concrete", b + Vector((-0.02, -0.45, 9.0)), b + Vector((-0.02, 0.45, 9.0)), 0.08)   # mensola
    for off in (-0.35, 0.35):
        tube(emd, "ti_lamp_black", b + Vector((0, off, 9.04)), b + Vector((0, off, 9.2)), 0.03, 0.03, 6)   # isolatori
    tops.append(b + Vector((0, 0.35, 9.18)))
for a, b in zip(tops, tops[1:]):                                       # catenaria
    pts = [a.lerp(b, t) - Vector((0, 0, 0.55 * 4 * t * (1 - t))) for t in [i / 12 for i in range(13)]]
    for p, q in zip(pts, pts[1:]):
        tube(emd, "ti_lamp_black", p, q, 0.012, 0.012, 4)
write_dae(os.path.join(OUT, "ti_powerline.dae"), [emd], GEO)

# ----------------------------------------------------------------------------- bacheca (Street View 2022)
# sul marciapiede sud-est: due montanti e telaio arrugginiti, pannello bianco sbiadito, tettuccio
kmd = MeshData("bacheca")
bx, by = LL.NOTICE_BOARD
for sx in (-0.75, 0.75):
    box(kmd, "ti_railing", Vector((bx + sx, by, 0.0)), Vector((bx + sx, by, 2.25)), 0.07)
box(kmd, "ti_railing", Vector((bx - 0.82, by, 1.05)), Vector((bx + 0.82, by, 1.05)), 0.08, 0.06)
box(kmd, "ti_railing", Vector((bx - 0.82, by, 2.05)), Vector((bx + 0.82, by, 2.05)), 0.08, 0.06)
box(kmd, "ti_notice_panel", Vector((bx - 0.78, by, 1.55)), Vector((bx + 0.78, by, 1.55)), 0.03, 0.96)
quad(kmd, "ti_railing", Vector((bx - 0.9, by + 0.3, 2.28)), Vector((bx + 0.9, by + 0.3, 2.28)),
     Vector((bx + 0.9, by - 0.25, 2.18)), Vector((bx - 0.9, by - 0.25, 2.18)))            # tettuccio
quad(kmd, "ti_railing", Vector((bx - 0.9, by - 0.25, 2.17)), Vector((bx + 0.9, by - 0.25, 2.17)),
     Vector((bx + 0.9, by + 0.3, 2.27)), Vector((bx - 0.9, by + 0.3, 2.27)))
write_dae(os.path.join(OUT, "ti_bacheca.dae"), [kmd], GEO)

# ----------------------------------------------------------------------------- autolavaggio (OSM way 1238868719)
# tettoia 35.6 x 7.1 m con 6 piste (ortofoto: copertura bianca), nel sistema locale: x lungo la tettoia, centro in 0;
# build_level la posa al centro OSM con la sua rotazione e alla quota del piazzale
cmd_ = MeshData("carwash")
CL, CW, CH = 35.6, 7.1, 4.3
nb = 6
for k in range(nb + 1):                                         # colonne sui due lati lunghi
    x = -CL / 2 + CL * k / nb
    for y in (-CW / 2 + 0.15, CW / 2 - 0.15):
        box(cmd_, "ti_lamp_pole", Vector((x, y, 0)), Vector((x, y, CH)), 0.22)
    if 0 < k < nb:                                              # pannelli divisori tra le piste
        box(cmd_, "ti_carwash_panel", Vector((x, -CW / 2 + 0.6, 0.3)), Vector((x, CW / 2 - 0.6, 0.3)), 0.06, 0.6)
        for zz in (1.2, 2.1, 3.0):
            box(cmd_, "ti_carwash_panel", Vector((x, -CW / 2 + 0.6, zz)), Vector((x, CW / 2 - 0.6, zz)), 0.05, 0.9)
    if k < nb:                                                  # braccio della lancia e box gettoniera per pista
        xc = -CL / 2 + CL * (k + 0.5) / nb
        box(cmd_, "ti_carwash_blue", Vector((xc + 2.2, CW / 2 - 0.35, 0)), Vector((xc + 2.2, CW / 2 - 0.35, 1.5)), 0.5, 0.35)
        box(cmd_, "ti_lamp_pole", Vector((xc, 0, CH - 0.1)), Vector((xc + 1.2, 0, CH - 0.1)), 0.06)
roof0, roof1 = CH, CH + 0.45
c8 = [Vector((sx * CL / 2, sy * CW / 2, z)) for z in (roof0, roof1) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
ctr_ = Vector((0, 0, (roof0 + roof1) / 2))
quad(cmd_, "ti_carwash_roof", c8[4], c8[5], c8[6], c8[7], ref=ctr_)
quad(cmd_, "ti_carwash_roof", c8[3], c8[2], c8[1], c8[0], ref=ctr_)
for i in range(4):
    j = (i + 1) % 4
    quad(cmd_, "ti_carwash_blue", c8[i], c8[j], c8[j + 4], c8[i + 4], ref=ctr_)      # fascia blu sul bordo
box(cmd_, "ti_curb", Vector((-CL / 2 - 0.5, 0, -0.3)), Vector((CL / 2 + 0.5, 0, -0.3)), CW + 1.0, 0.36)   # platea in cemento
write_dae(os.path.join(OUT, "ti_carwash.dae"), [cmd_], Matrix.Identity(4))

print("PROPS_OK", cmd.tri_count(), rmd.tri_count(), lmd.tri_count(), wmd.tri_count(), "tende", n_str, "grate", gmd.tri_count(), "lampione", pmd.tri_count())
