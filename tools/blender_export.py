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


# ---------------------------------------------------------------- main
objs = {o.name: o for o in bpy.data.objects}
visible = [o for o in bpy.data.objects if o.type == 'MESH' and not o.hide_get() and not o.hide_render]
meta = {"shapes": {}, "lamps": [], "trees": [], "benches": []}

# 1) pavimentazioni: griglia d'asfalto + marciapiedi, aiuole, cordoli
ground = MeshData("ground")
edge = nw_strip_edge(objs["BaseTerminal"])
kept = build_asphalt_grid(ground, objs["Plane"], edge)
for o in visible:
    if o.name == "BaseTerminal" or o.name == "Prato" or (o.name.startswith("Plane.0") and o.name != "Plane.015"):
        extract(o, ground, keep_filter=cut_keep)
n, m = write_dae(os.path.join(OUT_DIR, "ti_ground.dae"), [ground], GEO)
meta["shapes"]["ti_ground.dae"] = {"tris": n, "materials": m, "asphalt_cells": kept}

# 2) edificio
bld = MeshData("building")
extract(objs["Plane.015"], bld)
n, m = write_dae(os.path.join(OUT_DIR, "ti_building.dae"), [bld], GEO)
meta["shapes"]["ti_building.dae"] = {"tris": n, "materials": m}

# 3) ringhiera
rail = MeshData("railing")
for nm in ("Cube", "Cube.001", "Cube.002"):
    extract(objs[nm], rail, keep_filter=cut_keep)
n, m = write_dae(os.path.join(OUT_DIR, "ti_railing.dae"), [rail], GEO)
meta["shapes"]["ti_railing.dae"] = {"tris": n, "materials": m}

# 4) panchine e pensiline
props = MeshData("props")
for o in visible:
    if o.name.startswith(("Panchina", "ProtezionePanchina")):
        if (o.matrix_world @ Vector(o.bound_box[0]).lerp(Vector(o.bound_box[6]), 0.5)).x < X_CUT:
            continue
        extract(o, props)
        c = GEO @ (o.matrix_world @ Vector(o.bound_box[0]).lerp(Vector(o.bound_box[6]), 0.5))
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
        W = GEO @ o.matrix_world
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
        w = GEO @ Vector((cx, cy, 0))
        meta["trees"].append({"pos": [w.x, w.y], "height": h})

json.dump(meta, open(META_FILE, "w"), indent=1)
print("EXPORT_OK", json.dumps({k: v["tris"] for k, v in meta["shapes"].items()}), "lamps", len(meta["lamps"]), "trees", len(meta["trees"]))
