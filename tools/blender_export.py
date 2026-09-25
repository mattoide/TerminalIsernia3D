"""Esporta il modello Blender del terminal nei .dae della mod (sistema georeferenziato).

Uso (headless):
  blender -b src/blender/terminal.blend --python tools/blender_export.py -- <cartella_output_shapes> <file_meta.json>

Cosa fa:
  * applica i modificatori e porta tutto nel sistema est/nord del livello (geo.MODEL_ROT_DEG / MODEL_OFFSET)
  * sostituisce il rettangolo d'asfalto unico con una griglia tagliata al perimetro reale del piazzale
  * rigenera le UV in scala reale (metri) per i materiali ripetibili e aggiunge una UV1 "macro" sul piazzale
  * rinomina i materiali col prefisso ti_ (evita conflitti con altre mod)
  * separa lampioni (istanze), arredi, ringhiera, edificio, pavimentazioni
  * scrive posizioni di lampioni e alberi in un json per build_level.py
Blender 5.x non ha piu' l'esportatore Collada, quindi il .dae e' scritto a mano (sotto).
"""
import bpy, bmesh, math, json, os, sys
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
from dae_writer import MeshData, write_dae

argv = sys.argv[sys.argv.index("--") + 1:]
OUT_DIR, META_FILE = argv[0], argv[1]
os.makedirs(OUT_DIR, exist_ok=True)

GEO = Matrix.Translation((geo.MODEL_OFFSET[0], geo.MODEL_OFFSET[1], 0.0)) @ Matrix.Rotation(math.radians(geo.MODEL_ROT_DEG), 4, 'Z')

# ---------------------------------------------------------------- materiali
# nome originale -> (nuovo nome, modo UV, lato tessera in metri)
#   modo "keep"  = UV originali (texture fotografiche/atlas)
#   modo "plan"  = proiezione planare/box in metri, nel sistema del modello (allineata al piazzale)
MATS = {
    "AsfaltoTerminal":          ("ti_asphalt",       "plan", 3.0),
    "MarciapiediExtraExterni":  ("ti_pavers_moss",   "plan", 1.6),
    "MarciapiediExterni":       ("ti_pavers_moss",   "plan", 1.6),
    "Marciapiedi":              ("ti_island_soil",   "plan", 2.0),   # isole diagonali: terra ed erba secca (Street View 2022)
    "BordoMarciapiediInterni":  ("ti_curb",          "plan", 1.0),
    "prato":                    ("ti_planter_soil",  "plan", 2.0),
    "Parapetto":                ("ti_railing",       "plan", 1.0),
    "PaloLuce":                 ("ti_lamp_pole",     "plan", 1.0),
    "ScompartoLuce":            ("ti_lamp_head",     "plan", 0.5),
    "Panchina":                 ("ti_bench",         "plan", 1.0),
    "ProtezionePanchina":       ("ti_shelter",       "plan", 1.0),
    "MuraEdificioDestra.001":   ("ti_bld_facade_arches", "keep", 0),
    "MuraEdificioDestra":       ("ti_bld_plaster",   "plan", 2.0),
    "MuraEdificioSinistra":     ("ti_bld_wall_left", "keep", 0),
    "MuroEdificioDietro":       ("ti_bld_wall_front","keep", 0),
    "PareteGraffito":           ("ti_bld_graffiti",  "keep", 0),
    "TettoEdificio":            ("ti_bld_roof",      "plan", 2.0),
    "PilastriEdificio":         ("ti_bld_frame",     "plan", 1.0),
}

# il piazzale vero finisce al vialetto pedonale di x ~ -36.6 (ortofoto, OSM, utente): il rettangolo del modello v0.3
# piu' a sud-ovest (fino a x -95) nella realta' e' bosco, prato e un cantiere -> tutto cio' che sta a x < X_CUT non si esporta
X_CUT = -37.0
cut_keep = lambda new, pts: sum(p.x for p in pts) / 3 >= X_CUT

# UV1 macro: quadrato che contiene tutto il piazzale (coordinate modello)
MACRO_X0, MACRO_Y0, MACRO_SIZE = -100.0, -115.0, 230.0


def map_material(m):
    if m is None:
        return ("ti_curb", "plan", 1.0)
    return MATS.get(m.name, ("ti_curb", "plan", 1.0))


# ---------------------------------------------------------------- estrazione mesh
def planar_uv(p_model, n_model, tile):
    """proiezione in metri: facce orizzontali -> XY del modello, verticali -> (orizzontale, Z)."""
    if abs(n_model.z) > 0.6:
        return (p_model.x / tile, p_model.y / tile)
    h = Vector((-n_model.y, n_model.x, 0.0))
    if h.length < 1e-6:
        h = Vector((1, 0, 0))
    h.normalize()
    return (p_model.dot(h) / tile, p_model.z / tile)


def extract(obj, md, xform_model=None, keep_filter=None):
    """aggiunge i triangoli di obj a md. xform_model: matrice verso lo spazio 'modello'
    (default matrix_world); lo spazio finale e' GEO @ modello (o solo modello per le istanze)."""
    dg = bpy.context.evaluated_depsgraph_get()
    oe = obj.evaluated_get(dg)
    me = oe.to_mesh()
    me.calc_loop_triangles()
    M = xform_model if xform_model is not None else obj.matrix_world
    Mn = M.to_3x3().inverted().transposed()
    uv_src = me.uv_layers.active.data if me.uv_layers.active else None
    try:
        cn = me.corner_normals
        cnv = lambda li: cn[li].vector
    except AttributeError:
        cnv = lambda li: me.loops[li].normal
    for lt in me.loop_triangles:
        mat = me.materials[lt.material_index] if me.materials else None
        new, mode, tile = map_material(mat)
        pts = [M @ me.vertices[v].co for v in lt.vertices]
        if new == "ti_pavers_moss" and sum(p.y for p in pts) / 3 < -40:
            new = "ti_pavers_grey"          # Street View 2022: lungo la ringhiera sud-est autobloccanti grigi, altrove rossastri
        if keep_filter and not keep_filter(new, pts):
            continue
        fn = (Mn @ lt.normal).normalized()
        corners = []
        for k in range(3):
            li = lt.loops[k]
            p = pts[k]
            n = (Mn @ cnv(li)).normalized()
            if mode == "keep" and uv_src:
                uv = tuple(uv_src[li].uv)
            else:
                uv = planar_uv(p, fn, tile)
            uv1 = ((p.x - MACRO_X0) / MACRO_SIZE, (p.y - MACRO_Y0) / MACRO_SIZE)
            corners.append((p.copy(), n, uv, uv1))
        md.add_tri(new, corners)
    oe.to_mesh_clear()


# ---------------------------------------------------------------- asfalto a griglia tagliata
def nw_strip_edge(fp_obj):
    """per ogni x (1 m) la y massima del marciapiede nord-ovest (bordo esterno)."""
    dg = bpy.context.evaluated_depsgraph_get()
    oe = fp_obj.evaluated_get(dg)
    me = oe.to_mesh()
    edge = {}
    for p in me.polygons:
        c = fp_obj.matrix_world @ p.center
        if c.y < 12 or c.x < -24:
            continue
        ws = [fp_obj.matrix_world @ me.vertices[v].co for v in p.vertices]
        for k in range(int(math.floor(min(w.x for w in ws))), int(math.ceil(max(w.x for w in ws))) + 1):
            x = k + 0.5
            for a, b in zip(ws, ws[1:] + ws[:1]):       # intersezione con la retta X = x
                if (a.x - x) * (b.x - x) <= 0 and abs(b.x - a.x) > 1e-6:
                    y = a.y + (b.y - a.y) * (x - a.x) / (b.x - a.x)
                    edge[k] = max(edge.get(k, -1e9), y)
    oe.to_mesh_clear()
    return edge


def build_asphalt_grid(md, rect_obj, edge):
    bb = [rect_obj.matrix_world @ Vector(c) for c in rect_obj.bound_box]
    x0, x1 = min(v.x for v in bb), max(v.x for v in bb)
    y0, y1 = min(v.y for v in bb), max(v.y for v in bb)
    z = max(v.z for v in bb)
    step = 2.0
    nx, ny = int(math.ceil((x1 - x0) / step)), int(math.ceil((y1 - y0) / step))
    xs = [x0 + min(i * step, x1 - x0) for i in range(nx + 1)]
    ys = [y0 + min(j * step, y1 - y0) for j in range(ny + 1)]
    new, mode, tile = MATS["AsfaltoTerminal"]
    up = Vector((0, 0, 1))
    kept = 0

    def keep(cx, cy):
        if cx > 118.3 or cx < X_CUT:         # oltre il bordo nord-est: bosco; a sud-ovest del vialetto: non c'e' piazzale
            return False
        if cx >= -20.5:                      # sopra il marciapiede nord-ovest: prato/bosco
            lim = max(edge.get(int(math.floor(cx)) + d, -1e9) for d in (-1, 0, 1))
            if lim > -1e8 and cy > lim - 1.2:
                return False
        return True

    for i in range(nx):
        for j in range(ny):
            ax, bx, ay, by = xs[i], xs[i + 1], ys[j], ys[j + 1]
            if not keep((ax + bx) / 2, (ay + by) / 2):
                continue
            kept += 1
            quad = [Vector((ax, ay, z)), Vector((bx, ay, z)), Vector((bx, by, z)), Vector((ax, by, z))]
            for tri in ((0, 1, 2), (0, 2, 3)):
                corners = []
                for k in tri:
                    p = quad[k]
                    corners.append((p, up, planar_uv(p, up, tile),
                                    ((p.x - MACRO_X0) / MACRO_SIZE, (p.y - MACRO_Y0) / MACRO_SIZE)))
                md.add_tri(new, corners)
    return kept


# ---------------------------------------------------------------- fondo del piazzale ricostruito (lot_layout.py)
import lot_layout as LL
UP = Vector((0, 0, 1))
Z_CURB, Z_WALK = 0.13, 0.12          # cordolo e marciapiedi sopra l'asfalto (z 0)
CURB_W = 0.15


def uvs_for(p, n, tile):
    return planar_uv(p, n, tile), ((p.x - MACRO_X0) / MACRO_SIZE, (p.y - MACRO_Y0) / MACRO_SIZE)


def add_quad(md, mat, a, b, c, d, tile, n=None):
    n = n or (b - a).cross(d - a).normalized()
    for tri in ((a, b, c), (a, c, d)):
        md.add_tri(mat, [(p.copy(), n.copy(), *uvs_for(p, n, tile)) for p in tri])


def add_poly(md, mat, pts2d, z, tile):
    """poligono orizzontale (antiorario) triangolato da Blender: bordi esatti, niente scalini."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z)) for x, y in pts2d]
    f = bm.faces.new(vs)
    bmesh.ops.triangulate(bm, faces=[f], quad_method='BEAUTY', ngon_method='BEAUTY')
    for face in bm.faces:
        tri = [Vector(v.co) for v in face.verts]
        if (tri[1] - tri[0]).cross(tri[2] - tri[0]).z < 0:
            tri = tri[::-1]
        md.add_tri(mat, [(p, UP.copy(), *uvs_for(p, UP, tile)) for p in tri])
    bm.free()


def vertex_normals(P, closed=False):
    """normali a sinistra per vertice (bisettrice), scalate per mantenere la larghezza negli spigoli."""
    n = len(P); out = []
    for i in range(n):
        segs = []
        if i > 0 or closed:
            a, b = P[i - 1], P[i]; segs.append(Vector((b[0] - a[0], b[1] - a[1], 0)).normalized())
        if i < n - 1 or closed:
            a, b = P[i], P[(i + 1) % n]; segs.append(Vector((b[0] - a[0], b[1] - a[1], 0)).normalized())
        t = sum(segs, Vector()).normalized()
        nl = Vector((-t.y, t.x, 0))
        k = 1.0 / max(0.5, nl.dot(Vector((-segs[0].y, segs[0].x, 0))))
        out.append(nl * k)
    return out


def ribbon(md, mat, P, o0, o1, z, tile, closed=False):
    """striscia orizzontale tra gli offset o0 < o1 (a sinistra della polilinea)."""
    N = vertex_normals(P, closed)
    idx = list(range(len(P))) + ([0] if closed else [])
    for i, j in zip(idx, idx[1:]):
        pa, pb = Vector((*P[i], z)), Vector((*P[j], z))
        add_quad(md, mat, pa + N[i] * o0, pb + N[j] * o0, pb + N[j] * o1, pa + N[i] * o1, tile, UP)


def curb(md, P, closed=False, walk=None):
    """cordolo sul lato sinistro della polilinea (asfalto a destra): faccia verticale verso l'asfalto e sommita'.
    walk = (larghezza, materiale): marciapiede oltre il cordolo."""
    N = vertex_normals(P, closed)
    idx = list(range(len(P))) + ([0] if closed else [])
    for i, j in zip(idx, idx[1:]):
        a0, b0 = Vector((*P[i], 0)), Vector((*P[j], 0))
        # faccia verso l'asfalto (leggermente smussata in cima)
        add_quad(md, "ti_curb", a0, b0, b0 + UP * (Z_CURB - 0.02), a0 + UP * (Z_CURB - 0.02), 1.0)
        add_quad(md, "ti_curb", a0 + UP * (Z_CURB - 0.02), b0 + UP * (Z_CURB - 0.02),
                 b0 + N[j] * 0.03 + UP * Z_CURB, a0 + N[i] * 0.03 + UP * Z_CURB, 1.0)
        add_quad(md, "ti_curb", a0 + N[i] * 0.03 + UP * Z_CURB, b0 + N[j] * 0.03 + UP * Z_CURB,
                 b0 + N[j] * CURB_W + UP * Z_CURB, a0 + N[i] * CURB_W + UP * Z_CURB, 1.0, UP)
    if not walk:
        # retro del cordolo fin sotto il suolo: il terreno (celle da 2 m) resta un po' piu' basso dietro ai cordoli
        for i, j in zip(idx, idx[1:]):
            a1 = Vector((*P[i], 0)) + N[i] * CURB_W; b1 = Vector((*P[j], 0)) + N[j] * CURB_W
            add_quad(md, "ti_curb", b1 + UP * -0.3, a1 + UP * -0.3, a1 + UP * Z_CURB, b1 + UP * Z_CURB, 1.0)
    if walk:
        w, mat = walk
        ribbon(md, mat, P, CURB_W, CURB_W + w, Z_WALK, 1.6, closed)
        # bordo esterno del marciapiede verso il terreno
        for i, j in zip(idx, idx[1:]):
            a1 = Vector((*P[i], 0)) + N[i] * (CURB_W + w); b1 = Vector((*P[j], 0)) + N[j] * (CURB_W + w)
            add_quad(md, "ti_curb", b1 + UP * (Z_WALK - 0.25), a1 + UP * (Z_WALK - 0.25), a1 + UP * Z_WALK, b1 + UP * Z_WALK, 1.0)


def polyline_between(xa, xb, step=2.0):
    """tratto del cordolo nord-ovest tra xa e xb, campionato."""
    xs = [xa + (xb - xa) * k / max(1, int(abs(xb - xa) / step)) for k in range(int(abs(xb - xa) / step) + 1)]
    for x, _ in LL.NW_CURB:
        if xa < x < xb:
            xs.append(x)
    return [(x, LL.nw_curb_y(x)) for x in sorted(set(xs))]


def median_ring():
    """contorno antiorario della fascia centrale: rettangolo lungo la sua linea con testate arrotondate."""
    x0, x1, h = LL.MED_X0, LL.MED_X1, LL.MED_HALF
    ang = math.atan(0.0348); t = Vector((math.cos(ang), math.sin(ang), 0)); nv = Vector((-t.y, t.x, 0))
    c0 = Vector((x0, LL.median_y(x0), 0)) + t * h; c1 = Vector((x1, LL.median_y(x1), 0)) - t * h
    pts = []
    for k in range(9):                                   # testata est (da destra a sinistra)
        a = -math.pi / 2 + math.pi * k / 8
        p = c1 + t * (h * math.cos(a)) + nv * (h * math.sin(a)); pts.append((p.x, p.y))
    for k in range(9):                                   # testata ovest
        a = math.pi / 2 + math.pi * k / 8
        p = c0 + t * (h * math.cos(a)) + nv * (h * math.sin(a)); pts.append((p.x, p.y))
    return pts, t, nv


def railing(md, P, h=1.02, bay=2.0):
    """ringhiera a croce di Sant'Andrea (Street View 2022): montanti ogni 2 m, correnti alto e basso, diagonali a X."""
    L = [0.0]
    for a, b in zip(P, P[1:]):
        L.append(L[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    def at(sv):
        for k in range(len(P) - 1):
            if sv <= L[k + 1] or k == len(P) - 2:
                u = (sv - L[k]) / max(1e-6, L[k + 1] - L[k])
                return Vector((P[k][0] + (P[k + 1][0] - P[k][0]) * u, P[k][1] + (P[k + 1][1] - P[k][1]) * u, 0))
    nb = max(1, int(round(L[-1] / bay)))
    pts = [at(L[-1] * k / nb) for k in range(nb + 1)]
    for k, p in enumerate(pts):
        rbox(md, p, p + UP * h, 0.05)
        if k < nb:
            q = pts[k + 1]
            rbox(md, p + UP * 0.12, q + UP * 0.12, 0.04)
            rbox(md, p + UP * (h - 0.03), q + UP * (h - 0.03), 0.05)
            rbox(md, p + UP * 0.14, q + UP * (h - 0.05), 0.03)
            rbox(md, q + UP * 0.14, p + UP * (h - 0.05), 0.03)


def rbox(md, p0, p1, w):
    ax = p1 - p0; Lh = ax.length; ax.normalize()
    sv = ax.cross(UP) if abs(ax.dot(UP)) < 0.95 else ax.cross(Vector((1, 0, 0)))
    sv.normalize(); uv_ = sv.cross(ax).normalized()
    c = [p0 + sv * sx * w / 2 + uv_ * uy * w / 2 for sx, uy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    e = [q + ax * Lh for q in c]
    ctr = p0 + ax * (Lh / 2)
    for i in range(4):
        j = (i + 1) % 4
        a_, b_, c_, d_ = c[i], c[j], e[j], e[i]
        n = (b_ - a_).cross(d_ - a_).normalized()
        if n.dot((a_ + c_) / 2 - ctr) < 0:
            a_, b_, c_, d_ = d_, c_, b_, a_; n = -n
        add_quad(md, "ti_railing", a_, b_, c_, d_, 1.0, n)


objs = {o.name: o for o in bpy.data.objects}
visible = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_get() and not o.hide_render]
meta = {"shapes": {}, "lamps": [], "trees": [], "benches": []}


def island_matrix():
    a = math.radians(LL.ISL_ROT_DEG)
    return Matrix.Translation((LL.ISL_T[0], LL.ISL_T[1], 0)) @ Matrix.Rotation(a, 4, 'Z')


# 1) pavimentazioni: asfalto sul contorno vero, isole riposizionate, fascia centrale, marciapiedi e cordoli nuovi
ground = MeshData("ground")
outline = LL.lot_outline()
add_poly(ground, "ti_asphalt", outline, 0.0, 3.0)
ISL = island_matrix()
for nm in ("Plane.001", "Plane.002", "Plane.003", "Plane.004", "Plane.005", "Plane.006", "Plane.007", "Plane.008", "Plane.009", "Plane.010"):
    extract(objs[nm], ground, xform_model=ISL @ objs[nm].matrix_world)       # isole diagonali: al loro posto vero
extract(objs["Plane.011"], ground)                                            # piattaforma dell'edificio
# a sud-est dell'edificio la v0.3 aveva un'isola a "E" in autobloccanti: dal satellite e' una lastra piatta di asfalto
# piu' scuro con un bordino chiaro (vecchia banchina dei bus), a filo del piazzale
sx0, sy0, sx1, sy1 = LL.EAST_SLAB
add_poly(ground, "ti_slab", [(sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1)], 0.012, 3.0)
for (ax, ay), (bx, by) in (((sx0, sy0), (sx1, sy0)), ((sx1, sy0), (sx1, sy1)), ((sx1, sy1), (sx0, sy1)), ((sx0, sy1), (sx0, sy0))):
    dx, dy = bx - ax, by - ay; ln = math.hypot(dx, dy); nx, ny = -dy / ln * 0.09, dx / ln * 0.09
    add_poly(ground, "ti_curb", [(ax - nx, ay - ny), (bx - nx, by - ny), (bx + nx, by + ny), (ax + nx, ay + ny)], 0.02, 1.0)
# fascia centrale: cordolo tutto attorno, autobloccanti rossastri verso la strada, terra ed erba verso il piazzale
ring, t_med, n_med = median_ring()
curb(ground, ring, closed=True)
inner = [(x - 0, y) for x, y in ring]
Nr = vertex_normals(ring, True)
inner = [(x + nv.x * CURB_W, y + nv.y * CURB_W) for (x, y), nv in zip(ring, Nr)]
paver_w = 1.6
xs = [LL.MED_X0 + 1.2 + k * 2.0 for k in range(int((LL.MED_X1 - LL.MED_X0 - 2.4) / 2.0) + 1)]
def med_pt(x, off):
    c = Vector((x, LL.median_y(x), 0)); return (c + n_med * off)
soil = [med_pt(x, -LL.MED_HALF + CURB_W + paver_w) for x in xs] + [med_pt(x, LL.MED_HALF - CURB_W) for x in reversed(xs)]
pav = [med_pt(x, -LL.MED_HALF + CURB_W) for x in xs] + [med_pt(x, -LL.MED_HALF + CURB_W + paver_w) for x in reversed(xs)]
add_poly(ground, "ti_pavers_moss", [(p.x, p.y) for p in pav], Z_WALK, 1.6)
add_poly(ground, "ti_island_soil", [(p.x, p.y) for p in soil], Z_WALK - 0.01, 2.0)
# riempimento delle testate arrotondate (terra)
for sign, x in ((1, LL.MED_X0), (-1, LL.MED_X1)):
    cap = [p for p in inner if (p[0] - x) * sign < LL.MED_HALF + 1.3]
    if len(cap) >= 3:
        cx_ = sum(p[0] for p in cap) / len(cap); cy_ = sum(p[1] for p in cap) / len(cap)
        for p, q in zip(cap, cap[1:]):
            a_, b_, c_ = Vector((cx_, cy_, Z_WALK - 0.012)), Vector((p[0], p[1], Z_WALK - 0.012)), Vector((q[0], q[1], Z_WALK - 0.012))
            tri = [a_, b_, c_] if (b_ - a_).cross(c_ - a_).z > 0 else [a_, c_, b_]
            ground.add_tri("ti_island_soil", [(v, UP.copy(), *uvs_for(v, UP, 2.0)) for v in tri])
# marciapiede sud-est (grigio, ringhiera sul bordo esterno): polilinea verso ovest, marciapiede a sinistra
se_line = [(LL.NE_X, LL.SE_CURB_Y), (LL.SW_X, LL.SE_CURB_Y)]
curb(ground, se_line, walk=(abs(LL.SE_RAIL_Y - LL.SE_CURB_Y) - CURB_W, "ti_pavers_grey"))
# testata nord-est (solo cordolo): dall'angolo sud-est su fino al raccordo col bordo nord-ovest
ne = [p for p in outline if p[0] >= LL.NE_X - 5.01 and p[1] > LL.SE_CURB_Y + 0.1]
ne_line = list(reversed(ne)) + [(LL.NE_X, LL.SE_CURB_Y)]       # verso sud: cordolo a sinistra = fuori (+x)
curb(ground, ne_line)
# bordo nord-ovest: marciapiede da NW_WALK_FROM al raccordo; tra la stradina dell'autolavaggio e i casotti solo cordolo
curb(ground, polyline_between(LL.NW_WALK_FROM, 114.0), walk=(LL.NW_WALK, "ti_pavers_moss"))
curb(ground, polyline_between(-21.0, LL.NW_WALK_FROM))
curb(ground, polyline_between(LL.SW_X, -31.0))
# bordo sud-ovest: marciapiede verso l'esterno, con il varco della Strada Comunale Rava (y < -34)
sw_line = [(LL.SW_X, -34.0), (LL.SW_X, LL.NW_CURB[0][1])]
curb(ground, sw_line, walk=(LL.SW_WALK, "ti_pavers_moss"))
n, m = write_dae(os.path.join(OUT_DIR, "ti_ground.dae"), [ground], GEO)
meta["shapes"]["ti_ground.dae"] = {"tris": n, "materials": m}
meta["layout"] = {"median_ring": ring}

# 2) edificio
bld = MeshData("building")
extract(objs["Plane.015"], bld)
n, m = write_dae(os.path.join(OUT_DIR, "ti_building.dae"), [bld], GEO)
meta["shapes"]["ti_building.dae"] = {"tris": n, "materials": m}

# 3) ringhiera
rail = MeshData("railing")
railing(rail, [(LL.SW_X - 0.1, LL.SE_RAIL_Y), (LL.NE_X, LL.SE_RAIL_Y)])
nw_rail = [(x, y + CURB_W + LL.NW_WALK) for x, y in polyline_between(LL.NW_WALK_FROM, 112.0, 4.0)]
railing(rail, nw_rail)
n, m = write_dae(os.path.join(OUT_DIR, "ti_railing.dae"), [rail], GEO)
meta["shapes"]["ti_railing.dae"] = {"tris": n, "materials": m}

# 4) panchine e pensiline
props = MeshData("props")
bench_objs = [o for o in visible if o.name.startswith(("Panchina", "ProtezionePanchina"))]
bb_center = lambda o: o.matrix_world @ Vector(o.bound_box[0]).lerp(Vector(o.bound_box[6]), 0.5)
# la pensilina della fascia centrale si sposta in blocco (panchina + tettoia) dove l'ortofoto mostra la tettoia
med = [bb_center(o) for o in bench_objs if LL.in_old_median(bb_center(o).x, bb_center(o).y)]
med_c = sum(med, Vector((0, 0, 0))) / len(med) if med else None
for o in bench_objs:
    if True:
        c0 = bb_center(o)
        if c0.x < X_CUT:
            continue
        if med_c is not None and LL.in_old_median(c0.x, c0.y):
            nx_, ny_ = c0.x + LL.MEDIAN_SHELTER[0] - med_c.x, c0.y + LL.MEDIAN_SHELTER[1] - med_c.y
        else:
            nx_, ny_ = LL.relocate(c0.x, c0.y)
        if LL.in_carwash_road(nx_, ny_):          # la panchina dell'angolo nord-ovest finirebbe sulla stradina
            continue
        T = Matrix.Translation((nx_ - c0.x, ny_ - c0.y, 0.0))
        extract(o, props, xform_model=T @ o.matrix_world)
        c = GEO @ Vector((nx_, ny_, c0.z))
        meta["benches"].append([c.x, c.y, c.z])
n, m = write_dae(os.path.join(OUT_DIR, "ti_props.dae"), [props], GEO)
meta["shapes"]["ti_props.dae"] = {"tris": n, "materials": m}

# 5) lampione: una sola mesh nello spazio del suo Empty, poi istanze
tmpl = objs["Lampione.015"]
inv = tmpl.matrix_world.inverted()
lamp = MeshData("lamp")
extract(objs["Palo.001"], lamp, xform_model=inv @ objs["Palo.001"].matrix_world)
extract(objs["Luce.001"], lamp, xform_model=inv @ objs["Luce.001"].matrix_world)
n, m = write_dae(os.path.join(OUT_DIR, "ti_lamp.dae"), [lamp], Matrix.Identity(4))
meta["shapes"]["ti_lamp.dae"] = {"tris": n, "materials": m}
for o in bpy.data.objects:
    if o.type == 'EMPTY' and o.name.startswith("Lampione"):
        has_pole = any(c.name.startswith("Palo") for c in o.children)
        if not has_pole:
            continue
        if o.matrix_world.translation.x < X_CUT:
            continue
        p0 = o.matrix_world.translation
        nx_, ny_ = LL.relocate(p0.x, p0.y)
        W = GEO @ Matrix.Translation((nx_ - p0.x, ny_ - p0.y, 0.0)) @ o.matrix_world
        head = W @ (inv @ objs["Luce.001"].matrix_world).translation
        meta["lamps"].append({"pos": list(W.translation), "rot": [list(r) for r in W.to_3x3()], "head": list(head)})

# 6) alberi: solo posizioni (sostituiti da alberi vanilla con LOD e vento)
seen = set()
for o in bpy.data.objects:
    if o.type == 'MESH' and o.name.startswith("tree"):
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        cx = sum(v.x for v in bb) / 8; cy = sum(v.y for v in bb) / 8
        h = max(v.z for v in bb)
        key = (round(cx, 1), round(cy, 1))
        if key in seen or cx < X_CUT:
            continue
        seen.add(key)
        if h > 15:                                   # il grande salice della v0.3: sostituito da ti_willow
            continue
        cx, cy = LL.snap_tree(*LL.relocate(cx, cy))
        w = GEO @ Vector((cx, cy, 0))
        meta["trees"].append({"pos": [w.x, w.y], "height": h})

json.dump(meta, open(META_FILE, "w"), indent=1)
print("EXPORT_OK", json.dumps({k: v["tris"] for k, v in meta["shapes"].items()}), "lamps", len(meta["lamps"]), "trees", len(meta["trees"]))
