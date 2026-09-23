"""Assembla il livello BeamNG terminal_isernia (v1.0) nella cartella mod/.

Prerequisiti (in ordine): blender_export.py, build_textures.py, build_terrain.py
Uso: python tools/build_level.py
"""
import os, sys, json, math, shutil, uuid, glob
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import vanilla_assets as va
from osm import OSM

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LV = os.path.join(ROOT, "mod", "levels", "terminal_isernia")
BUILD = os.path.join(ROOT, "build")
ORIG = os.path.join(ROOT, "_orig", "extracted", "levels", "terminal_isernia")
LVP = "/levels/terminal_isernia/"
T = LVP + "art/textures/"
AS = "/assets/materials/"
OLD_TERMINAL_OFFSET = (-0.939715743, 0.103312492, 0.165756345)   # posizione del TSStatic nel livello v0.3
rng = np.random.default_rng(1234)
IMPORTED = {}          # materiali copiati dai livelli ufficiali (un solo file, niente duplicati)


def uid(s):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "terminal_isernia/" + s))


def rot_list_from_yaw(a):
    """rotationMatrix BeamNG = assi locali X,Y,Z in sequenza (verificato sui guardrail di Italy)."""
    c, s = math.cos(a), math.sin(a)
    return [c, s, 0, -s, c, 0, 0, 0, 1]


def rotate_list(L, a):
    c, s = math.cos(a), math.sin(a)
    out = []
    for k in range(3):
        x, y, z = L[3 * k:3 * k + 3]
        out += [c * x - s * y, s * x + c * y, z]
    return out


def old_to_world(p):
    """posizione nel livello v0.3 -> nuovo sistema est/nord."""
    mx, my = p[0] - OLD_TERMINAL_OFFSET[0], p[1] - OLD_TERMINAL_OFFSET[1]
    x, y = geo.model2world(mx, my)
    return [x, y, p[2] - OLD_TERMINAL_OFFSET[2]]


# ====================================================================== terreno (per le quote)
M = np.load(os.path.join(BUILD, "terrain_masks.npz"))
TZ, TLAY, TFOREST = M["z"], M["lay"], M["forest"]
TDLOT, TDROAD, TRHW = M["d_lot"], M["d_road"], M["road_hw"]
TX0, TY0, TSQ = float(M["x0"]), float(M["y0"]), float(M["sq"])
TN = TZ.shape[0]
TINFO = json.load(open(os.path.join(BUILD, "terrain_info.json")))
TZF, TFARF = M["zf"], M["far_forest"]
TXF0, TSQF = float(M["xf0"]), float(M["sqf"])


def tzf(x, y):
    x, y = np.atleast_1d(x), np.atleast_1d(y)
    return ndimage.map_coordinates(TZF, [(y - TXF0) / TSQF, (x - TXF0) / TSQF], order=1, mode="nearest")


def tsample(arr, x, y, order=1):
    x, y = np.atleast_1d(x), np.atleast_1d(y)
    return ndimage.map_coordinates(arr, [(y - TY0) / TSQ, (x - TX0) / TSQ], order=order, mode="nearest")


def tz(x, y):
    return tsample(TZ, x, y)


# ====================================================================== oggetti livello
class Level:
    def __init__(self):
        self.groups = {}           # nome gruppo -> lista oggetti

    def add(self, group, obj):
        obj.setdefault("persistentId", uid(group + "/" + obj.get("name", "") + "/" + str(len(self.groups.get(group, [])))))
        obj["__parent"] = group.split("/")[-1]
        self.groups.setdefault(group, []).append(obj)

    def write(self):
        base = os.path.join(LV, "main")
        if os.path.isdir(base):
            shutil.rmtree(base)
        os.makedirs(os.path.join(base, "MissionGroup"))
        with open(os.path.join(base, "items.level.json"), "w") as f:
            f.write(json.dumps({"name": "MissionGroup", "class": "SimGroup", "persistentId": uid("MissionGroup"), "enabled": "1"}) + "\n")
        # gerarchia: MissionGroup/<g>/<sub>
        tops = {}
        for g in self.groups:
            parts = g.split("/")
            for i in range(len(parts)):
                tops.setdefault("/".join(parts[:i + 1]), None)
        for g in sorted(tops):
            parts = g.split("/")
            parent_dir = os.path.join(base, "MissionGroup", *parts[:-1])
            os.makedirs(os.path.join(parent_dir, parts[-1]), exist_ok=True)
            with open(os.path.join(parent_dir, "items.level.json"), "a") as f:
                f.write(json.dumps({"name": parts[-1], "class": "SimGroup", "persistentId": uid("grp/" + g),
                                    "__parent": parts[-2] if len(parts) > 1 else "MissionGroup"}) + "\n")
        for g, objs in self.groups.items():
            d = os.path.join(base, "MissionGroup", *g.split("/"))
            with open(os.path.join(d, "items.level.json"), "a") as f:
                for o in objs:
                    f.write(json.dumps(o) + "\n")


# ====================================================================== materiali delle mesh del terminal
def stage(**kw):
    return {k: v for k, v in kw.items() if v is not None}


def pbr(name, tex=None, ground="ASPHALT", layer2=None, **kw):
    s0 = {}
    if tex:
        s0.update(baseColorMap=tex + "_b.color.png", normalMap=tex + "_nm.normal.png",
                  roughnessMap=tex + "_r.data.png", ambientOcclusionMap=tex + "_ao.data.png")
    s0.update({k: v for k, v in kw.items() if not k.startswith("m_")})
    stages = [s0, layer2 or {}, {}, {}]
    m = {"name": name, "mapTo": name, "class": "Material", "persistentId": uid("mat/" + name),
         "Stages": stages, "version": 1.5, "groundType": ground, "materialTag0": "beamng", "materialTag1": "terminal_isernia",
         "translucentBlendOp": "None"}
    if layer2:
        m["activeLayers"] = 2
    for k, v in kw.items():
        if k.startswith("m_"):
            m[k[2:]] = v
    return name, m


def reeds_mat(name, color_tex, factor):
    G = AS + "foliage/grass/"
    return name, {"name": name, "mapTo": name, "class": "Material", "persistentId": uid("mat/" + name), "version": 1.5,
                  "Stages": [{"baseColorMap": G + f"{color_tex}/{color_tex}_b.color.png", "baseColorFactor": factor,
                              "opacityMap": G + "t_grass_green_long_01/t_grass_green_long_01_o.data.png",
                              "normalMap": G + "t_grass_green_long_01/t_grass_green_long_01_nm.normal.png",
                              "roughnessMap": G + "t_grass_green_long_01/t_grass_green_long_01_r.data.png",
                              "ambientOcclusionMap": G + "t_grass_green_long_01/t_grass_green_long_01_ao.data.png"}, {}, {}, {}],
                  "alphaRef": 60, "alphaTest": True, "doubleSided": True, "invertBackFaceNormals": True, "subSurface": True,
                  "subSurfaceIntensity": 1, "groundType": "GRASS", "annotation": "GRASS", "materialTag0": "beamng",
                  "translucentBlendOp": "None"}


def terminal_materials():
    det_concrete = dict(detailMap=AS + "breakup/t_detail_concrete_02/t_detail_concrete_02_detail_b.data.png",
                        detailBaseColorMapStrength=0.35, detailNormalMap=AS + "breakup/t_detail_concrete/t_detail_concrete_nm.normal.png",
                        detailNormalMapStrength=0.35, detailScale=[3, 3])
    galv = dict(baseColorMap=AS + "tileable/metal/metal_galvanized/t_metal_galvanized_01_b.color.png",
                roughnessMap=AS + "tileable/metal/metal_galvanized/t_metal_galvanized_02_r.data.png",
                metallicMap=AS + "tileable/metal/metal_galvanized/t_metal_galvanized_02_m.data.png", metallicFactor=1)
    paint = dict(baseColorMap=AS + "tileable/metal/metal_paint/metal_paint_d.color.png",
                 normalMap=AS + "tileable/metal/metal_paint/metal_paint_nm.normal.png", roughnessFactor=0.55, metallicFactor=0)
    mats = dict([
        pbr("ti_asphalt", T + "t_ti_asphalt", "ASPHALT",
            detailNormalMap=AS + "breakup/m_asphalt_02/t_asphalt_detail_01_nm.normal.png", detailNormalMapStrength=0.6, detailScale=[0.35, 0.35],
            layer2=stage(baseColorMap=T + "t_ti_asphalt_cracked_b.color.png", normalMap=T + "t_ti_asphalt_cracked_nm.normal.png",
                         roughnessMap=T + "t_ti_asphalt_cracked_r.data.png", ambientOcclusionMap=T + "t_ti_asphalt_cracked_ao.data.png",
                         opacityMap=T + "t_ti_asphalt_breakup_o.data.png", opacityMapUseUV=1, opacityFactor=0.8)),
        pbr("ti_pavers_moss", T + "t_ti_pavers_moss", "COBBLESTONE", **det_concrete),
        pbr("ti_pavers", T + "t_ti_pavers", "COBBLESTONE", **det_concrete),
        pbr("ti_curb", T + "t_ti_curb", "ASPHALT", **det_concrete),
        pbr("ti_planter_soil", None, "DIRT",
            baseColorMap=AS + "terrain/forest/t_forest_ground/t_forest_ground_b.png", normalMap=AS + "terrain/forest/t_forest_ground/t_forest_ground_nm.png",
            roughnessMap=AS + "terrain/forest/t_forest_ground/t_forest_ground_r.png", ambientOcclusionMap=AS + "terrain/forest/t_forest_ground/t_forest_ground_ao.png"),
        pbr("ti_railing", None, "METAL", baseColorMap=AS + "tileable/metal/metal_paint_peeling/paint_peeling_d.dds",
            normalMap=AS + "tileable/metal/metal_paint_peeling/paint_peeling_n.dds", baseColorFactor=[0.42, 0.22, 0.13, 1],
            roughnessFactor=0.75, metallicFactor=0.3),   # ringhiera verniciata marrone e arrugginita (Street View 2022)
        pbr("ti_lamp_pole", None, "METAL", baseColorFactor=[0.75, 0.76, 0.78, 1], **galv),
        pbr("ti_lamp_head", None, "METAL", baseColorFactor=[0.9, 0.88, 0.8, 1], roughnessFactor=0.25, metallicFactor=0,
            emissive=True, instanceEmissive=True, emissiveFactor=[1, 1, 1], emissiveIntensityNits=12000),
        pbr("ti_bench", None, "METAL", baseColorFactor=[0.16, 0.30, 0.24, 1], **paint),
        pbr("ti_shelter", None, "METAL", baseColorFactor=[0.14, 0.33, 0.27, 1], **paint),
        pbr("ti_bld_facade_arches", T + "t_ti_bld_arches", "ASPHALT", **det_concrete),
        pbr("ti_bld_plaster", T + "t_ti_plaster_yellow", "ASPHALT", **det_concrete),
        pbr("ti_bld_wall_left", T + "t_ti_bld_left", "ASPHALT", **det_concrete),
        pbr("ti_bld_wall_front", T + "t_ti_bld_front", "ASPHALT", **det_concrete),
        pbr("ti_bld_graffiti", T + "t_ti_bld_graffiti", "ASPHALT", **det_concrete),
        pbr("ti_bld_roof", T + "t_ti_roof", "ASPHALT"),
        pbr("ti_bld_frame", T + "t_ti_pillar", "ASPHALT", **det_concrete),   # pilastri in cemento chiaro
        pbr("ti_canopy_steel", None, "METAL", baseColorFactor=[0.10, 0.27, 0.17, 1], **paint),
        pbr("ti_canopy_panel", None, "PLASTIC", baseColorFactor=[0.84, 0.86, 0.80, 0.72], roughnessFactor=0.35, metallicFactor=0,
            detailMap=AS + "breakup/t_detail_concrete_02/t_detail_concrete_02_detail_b.data.png", detailBaseColorMapStrength=0.5,
            detailScale=[1, 1], m_translucent=True, m_translucentBlendOp="LerpAlpha", m_translucentZWrite=False,
            m_doubleSided=True, m_castShadows=True),
        pbr("ti_lamp_black", None, "METAL", baseColorFactor=[0.035, 0.035, 0.035, 1], **dict(paint, roughnessFactor=0.45)),
        pbr("ti_lamp_globe", None, "PLASTIC", baseColorFactor=[0.95, 0.95, 0.92, 1], roughnessFactor=0.15, metallicFactor=0,
            emissive=True, instanceEmissive=True, emissiveFactor=[1, 1, 1], emissiveIntensityNits=6000),
        pbr("ti_backdrop", None, "GRASS", baseColorMap=LVP + "art/terrains/t_ti_far_base_b.png",
            normalMap=LVP + "art/terrains/t_ti_far_base_nm.png", roughnessFactor=0.95, metallicFactor=0),
        reeds_mat("ti_reeds", "t_grass_green_long_03", [0.58, 0.74, 0.52, 1]),
        reeds_mat("ti_reeds_dry", "t_grass_dry_long_01", [0.78, 0.74, 0.62, 1]),
    ])
    return mats


# ====================================================================== terminal: mesh + lampioni
def place_terminal(L):
    shp = os.path.join(LV, "art", "shapes", "terminal")
    os.makedirs(shp, exist_ok=True)
    for f in glob.glob(os.path.join(BUILD, "shapes", "*.dae")):
        shutil.copy2(f, shp)
    json.dump(terminal_materials(), open(os.path.join(shp, "main.materials.json"), "w"), indent=1)
    for nm in ("ti_ground", "ti_building", "ti_railing", "ti_props", "ti_canopy"):
        L.add("terminal", {"name": nm.replace("ti_", "terminal_"), "class": "TSStatic", "position": [0, 0, 0], "shapeName": LVP + f"art/shapes/terminal/{nm}.dae",
                           "collisionType": "Visible Mesh Final", "decalType": "Visible Mesh", "useInstanceRenderData": True})
    meta = json.load(open(os.path.join(BUILD, "export_meta.json")))
    for i, lp in enumerate(meta["lamps"]):
        R = lp["rot"]
        rotl = [R[0][0], R[1][0], R[2][0], R[0][1], R[1][1], R[2][1], R[0][2], R[1][2], R[2][2]]
        light = f"ti_lamp_light_{i:02d}"
        L.add("terminal/lampioni", {"name": f"ti_lamp_{i:02d}", "class": "TSStatic", "position": lp["pos"], "rotationMatrix": rotl,
                                    "shapeName": LVP + "art/shapes/terminal/ti_lamp.dae", "collisionType": "Visible Mesh Final",
                                    "useInstanceRenderData": True, "instanceColor": [0, 0, 0, 1], "child": light})
        h = lp["head"]
        L.add("terminal/lampioni", {"name": light, "class": "SpotLight", "position": [h[0], h[1], h[2] - 0.15],
                                    "rotationMatrix": [1, 0, 0, 0, 0, -1, 0, 1, 0],     # asse Y locale verso il basso
                                    "color": [1, 0.72, 0.42, 1], "brightness": 3, "range": 22, "innerAngle": 60, "outerAngle": 125,
                                    "castShadows": i % 3 == 0, "isEnabled": False, "nightLight": True})
    # lampioni decorativi a due globi agli angoli delle pensiline (Street View 2022)
    for i, (mx, my, yaw) in enumerate([(88.9, -20.3, 20), (89.6, 3.9, -20)]):
        x, y = geo.model2world(mx, my)
        light = f"ti_globe_light_{i}"
        L.add("terminal/lampioni", {"name": f"ti_globe_{i}", "class": "TSStatic", "position": [x, y, 0.1],
                                    "rotationMatrix": rot_list_from_yaw(math.radians(yaw + geo.MODEL_ROT_DEG)),
                                    "shapeName": LVP + "art/shapes/terminal/ti_lamp_globe.dae", "collisionType": "Visible Mesh Final",
                                    "useInstanceRenderData": True, "instanceColor": [0, 0, 0, 1], "child": light})
        L.add("terminal/lampioni", {"name": light, "class": "PointLight", "position": [x, y, 3.2], "color": [1, 0.8, 0.55, 1],
                                    "brightness": 1.6, "radius": 12, "castShadows": False, "isEnabled": False, "nightLight": True})
    return meta


# ====================================================================== vegetazione
FOREST_ITEMS = {
    "italy": ["holm_oak_city_small", "holm_oak_city_tall", "holm_oak_test", "cork_oak_large_1", "cork_oak_medium", "cypress_tree", "olive_tree",
              "generibush", "generibush_small", "fluffy_bush", "scraggly_bush", "scraggly_tree", "tall_plant", "tall_plant_bush", "holm_oak_bush"],
    "east_coast_usa": ["tree_beech_forest_group", "tree_aspen_forest_group", "tree_beech_small_forest_group", "tree_aspen_large_a", "tree_aspen_large_b", "tree_aspen_small_a", "tree_aspen_forest_a", "tree_beech_large_b",
                       "tree_beech_large_c", "tree_beech_forest_a", "tree_beech_forest_b", "tree_beech_small_b", "tree_beech_bush_a", "tree_beech_bush_b"],
    "west_coast_usa": ["oak_a_distant", "oak_dry_a", "oak_dry_b", "oak_dry_c", "oak_dry_d", "shrub_a", "shrub_c"],
}


def write_forest_defs():
    items, mats = {}, {}
    items["ti_reeds_clump"] = {"name": "ti_reeds_clump", "internalName": "ti_reeds_clump_int", "class": "ForestItemData",
                               "persistentId": uid("fid/reeds"), "annotation": "NATURE",
                               "shapeFile": LVP + "art/shapes/terminal/ti_reeds.dae", "windScale": 0.8, "trunkBendScale": 0.03,
                               "branchAmp": 0.08, "detailAmp": 0.35, "detailFreq": 0.9, "mass": 1}
    for lv, names in FOREST_ITEMS.items():
        fi = va.forest_items(lv)
        for n in names:
            d = dict(fi[n])
            sp = d["shapeFile"] if d["shapeFile"].startswith("/") else "/" + d["shapeFile"]
            d["shapeFile"] = sp
            items[n] = d
            va.collect(sp, va.level_of(sp) or lv, mats)
    fd = os.path.join(LV, "art", "forest")
    os.makedirs(fd, exist_ok=True)
    json.dump(items, open(os.path.join(fd, "managedItemData.json"), "w"), indent=1)
    for k, v in mats.items():
        IMPORTED.setdefault(k, v)
    return items


def poisson(mask_fn, x0, y0, x1, y1, spacing, max_tries=1):
    """campionamento a griglia con jitter (veloce, abbastanza uniforme)."""
    xs = np.arange(x0, x1, spacing); ys = np.arange(y0, y1, spacing)
    X, Y = np.meshgrid(xs, ys)
    X = X + rng.uniform(-0.45, 0.45, X.shape) * spacing
    Y = Y + rng.uniform(-0.45, 0.45, Y.shape) * spacing
    X, Y = X.ravel(), Y.ravel()
    keep = mask_fn(X, Y)
    return X[keep], Y[keep]


def make_forest(meta):
    inst = {}
    def put(kind, x, y, s_lo=0.85, s_hi=1.2, z_off=-0.05):
        z = tz(x, y) + z_off
        for xi, yi, zi in zip(np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z)):
            a = rng.uniform(0, 2 * math.pi)
            inst.setdefault(kind, []).append({"ctxid": 0, "pos": [round(float(xi), 3), round(float(yi), 3), round(float(zi), 3)],
                                              "rotationMatrix": [round(v, 6) for v in rot_list_from_yaw(a)],
                                              "scale": round(float(rng.uniform(s_lo, s_hi)), 4), "type": kind})
    # 1) aiuole del terminal: lecci da citta' al posto degli alberi originali
    for t in meta["trees"]:
        x, y = t["pos"]; h = t["height"]
        kind = "holm_oak_city_tall" if h > 5 else "holm_oak_city_small"
        z = 0.1
        a = rng.uniform(0, 2 * math.pi)
        inst.setdefault(kind, []).append({"ctxid": 0, "pos": [x, y, z], "rotationMatrix": rot_list_from_yaw(a),
                                          "scale": round(min(1.25, max(0.6, h / (7.5 if h > 5 else 4.5))), 3), "type": kind})
    # 2) boschi (dal terreno): specie in base alla vicinanza all'acqua e alla distanza
    osm = OSM()
    water = [osm.way_pts(w) for w, t in osm.ways_where(lambda t: "waterway" in t)]
    wpts = np.array([p for w in water for p in w]) if water else np.zeros((0, 2))
    from scipy.spatial import cKDTree
    wtree = cKDTree(wpts) if len(wpts) else None
    lim = 2030
    def forest_mask(X, Y):
        f = tsample(TFOREST.astype(np.float32), X, Y, 0) > 0.5
        f &= tsample(TDLOT, X, Y) > 7
        f &= tsample(TDROAD, X, Y) > tsample(TRHW, X, Y) + 2.5
        return f
    for (r0, r1, sp) in ((0, 500, 5.5), (500, 1100, 8.0), (1100, 3000, 11.0)):
        X, Y = poisson(forest_mask, -lim, -lim, lim, lim, sp)
        d = np.hypot(X, Y); sel = (d >= r0) & (d < r1); X, Y = X[sel], Y[sel]
        dw = wtree.query(np.stack([X, Y], 1))[0] if wtree else np.full(len(X), 1e4)
        u = rng.random(len(X))
        rip = dw < 30
        far = r0 >= 1100
        for i in range(len(X)):
            if rip[i]:
                k = ["tree_aspen_large_a", "tree_aspen_large_b", "tree_aspen_small_a", "tree_beech_large_b", "oak_dry_b"][min(4, int(u[i] * 5))]
            elif far:
                k = ["tree_beech_forest_a", "tree_beech_forest_b", "tree_aspen_forest_a", "oak_dry_a", "cork_oak_large_1"][min(4, int(u[i] * 5))]
            else:
                k = ["oak_dry_a", "oak_dry_b", "oak_dry_c", "oak_dry_d", "tree_beech_large_b", "tree_beech_large_c",
                     "cork_oak_large_1", "cork_oak_medium", "holm_oak_test", "tree_beech_small_b"][min(9, int(u[i] * 10))]
            put(k, X[i], Y[i])
        # sottobosco / margini
        if r0 < 1100:
            Xb, Yb = poisson(forest_mask, -r1, -r1, r1, r1, sp * 1.6)
            db = np.hypot(Xb, Yb); s2 = (db >= r0) & (db < r1)
            for x, y, uu in zip(Xb[s2], Yb[s2], rng.random(s2.sum())):
                put(["tree_beech_bush_a", "tree_beech_bush_b", "generibush", "fluffy_bush", "scraggly_bush", "holm_oak_bush"][min(5, int(uu * 6))], x, y, 0.7, 1.3)
    # 3) siepi e alberi isolati lungo strade e campi (paesaggio agricolo molisano)
    def hedge_mask(X, Y):
        dr = tsample(TDROAD, X, Y); hw = tsample(TRHW, X, Y)
        lay = tsample(TLAY.astype(np.float32), X, Y, 0).astype(int)
        return (dr > hw + 3) & (dr < hw + 9) & np.isin(lay, [0, 1, 7, 8]) & (tsample(TDLOT, X, Y) > 12)
    X, Y = poisson(hedge_mask, -1500, -1500, 1500, 1500, 9)
    for x, y, uu in zip(X, Y, rng.random(len(X))):
        if uu < 0.55:
            put(["generibush", "scraggly_bush", "tall_plant_bush", "tree_beech_bush_a"][int(uu / 0.55 * 4) % 4], x, y, 0.7, 1.3)
        elif uu < 0.72:
            put(["oak_dry_c", "oak_dry_d", "scraggly_tree", "tree_aspen_small_a"][int((uu - 0.55) / 0.17 * 4) % 4], x, y)
    def meadow_mask(X, Y):
        lay = tsample(TLAY.astype(np.float32), X, Y, 0).astype(int)
        return np.isin(lay, [0, 1, 8]) & (tsample(TDROAD, X, Y) > tsample(TRHW, X, Y) + 4) & (tsample(TDLOT, X, Y) > 15)
    X, Y = poisson(meadow_mask, -1700, -1700, 1700, 1700, 45)
    for x, y, uu in zip(X, Y, rng.random(len(X))):
        put(["oak_dry_a", "olive_tree", "tree_beech_large_c", "cork_oak_medium", "generibush"][int(uu * 5) % 5], x, y)
    # 4) uliveti su una parte dei campi (filari 6x6 m)
    def olive_mask(X, Y):
        lay = tsample(TLAY.astype(np.float32), X, Y, 0).astype(int)
        big = np.sin(X / 170.0) * np.cos(Y / 130.0) > 0.45
        return (lay == 7) & big & (tsample(TDROAD, X, Y) > tsample(TRHW, X, Y) + 4)
    xs = np.arange(-1600, 1600, 6.0); X, Y = np.meshgrid(xs, xs); X, Y = X.ravel(), Y.ravel()
    k = olive_mask(X, Y)
    for x, y in zip(X[k], Y[k]):
        put("olive_tree", x + rng.uniform(-0.4, 0.4), y + rng.uniform(-0.4, 0.4), 0.8, 1.1)
    # 4b) canneto (Arundo) lungo i bordi del piazzale, come in Street View 2022
    def reed_mask(X, Y):
        d = tsample(TDLOT, X, Y)
        dr = tsample(TDROAD, X, Y); hw = tsample(TRHW, X, Y)
        mx = np.array([geo.world2model(x, y)[0] for x, y in zip(X, Y)]) if len(X) else np.zeros(0)
        n = np.sin(X * 0.21) * np.cos(Y * 0.17) + np.sin(X * 0.05 + Y * 0.07)
        return (d > 2.0) & (d < 11 + 4 * n) & (dr > hw + 1.2) & (mx > -45) & (n > -1.1)
    X, Y = poisson(reed_mask, -250, -250, 250, 250, 1.6)
    for x, y in zip(X, Y):
        put("ti_reeds_clump", x, y, 0.8, 1.25, z_off=0.0)
    # 5) boschi sulle colline dell'orizzonte (fuori dal terreno principale), modelli leggeri per la distanza
    far_kinds = ["oak_a_distant", "tree_beech_forest_group", "tree_aspen_forest_group", "oak_a_distant", "tree_beech_small_forest_group"]
    for (r0, r1, sp) in ((2040, 3200, 26.0), (3200, 5000, 42.0)):
        X, Y = poisson(lambda X, Y: np.ones(len(X), bool), -r1, -r1, r1, r1, sp)
        cheb = np.maximum(np.abs(X), np.abs(Y)); keep = (cheb >= max(r0, 2040)) & (cheb < r1)
        X, Y = X[keep], Y[keep]
        f = ndimage.map_coordinates(TFARF.astype(np.float32), [(Y - TXF0) / TSQF, (X - TXF0) / TSQF], order=0, mode="nearest") > 0.5
        X, Y = X[f], Y[f]
        Z = tzf(X, Y) - 0.3
        for x, y, z, uu in zip(X, Y, Z, rng.random(len(X))):
            k = far_kinds[int(uu * len(far_kinds)) % len(far_kinds)]
            a = rng.uniform(0, 2 * math.pi)
            inst.setdefault(k, []).append({"ctxid": 0, "pos": [round(float(x), 2), round(float(y), 2), round(float(z), 2)],
                                           "rotationMatrix": [round(v, 5) for v in rot_list_from_yaw(a)],
                                           "scale": round(float(rng.uniform(0.9, 1.3)), 3), "type": k})
    fdir = os.path.join(LV, "forest")
    if os.path.isdir(fdir):
        shutil.rmtree(fdir)
    os.makedirs(fdir)
    tot = 0
    for kind, lst in inst.items():
        with open(os.path.join(fdir, kind + ".forest4.json"), "w") as f:
            for o in lst:
                f.write(json.dumps(o) + "\n")
        tot += len(lst)
    print("alberi/cespugli:", tot, {k: len(v) for k, v in sorted(inst.items(), key=lambda kv: -len(kv[1]))[:12]})


def groundcover(L):
    """erba e fiori: copia dei GroundCover di Italy con gli strati rimappati sui nostri materiali di terreno."""
    remap = {"Grass": "ti_t_grass", "Grass2": "ti_t_grass", "Grass3": "ti_t_weeds", "Grass4": "ti_t_weeds",
             "dirt_grass": "ti_t_grass_dry", "dirt_loose_dusty": "ti_t_dirt", "dirt_loose": "ti_t_dirt",
             "RockyDirt": "ti_t_rock", "forest_floor": "ti_t_forest"}
    import zipfile
    z, _ = va._zip_for("/levels/italy/info.json")
    mats_needed = set()
    for n in z.namelist():
        if n.startswith("levels/italy/main/") and n.endswith("items.level.json"):
            for l in z.read(n).decode().splitlines():
                if '"GroundCover"' not in l:
                    continue
                d = json.loads(l)
                types = []
                for t in d.get("Types", []):
                    t = dict(t)
                    if t.get("layer") in remap:
                        t["layer"] = remap[t["layer"]]
                    elif t.get("layer"):
                        t["layer"] = ""
                    types.append(t)
                d["Types"] = types
                d["position"] = [0, 0, 0]
                d.pop("__parent", None); d.pop("persistentId", None)
                mats_needed.add(d.get("material"))
                L.add("vegetation/erba", d)
    gm = json.loads(z.read("levels/italy/art/shapes/groundcover/main.materials.json"))
    out = {k: v for k, v in gm.items() if v.get("mapTo", k) in mats_needed or k in mats_needed}
    d = os.path.join(LV, "art", "shapes", "groundcover"); os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, "main.materials.json"), "w"), indent=1)


# ====================================================================== strade (decal su terreno)
ROAD_MATS = ["italy_road_edge_damage_wide_grassy", "italy_road_markings_line_thin", "italy_road_markings_center_line_broken_white",
             "italy_road_cracks", "italy_asphalt_overlay_light", "m_road_variation_01", "italy_road_edge_damage", "dirt_road_edge_grassy_d",
             "m_dirt_road_gravels", "italy_leaf_litter", "skidmarks_01", "skidmarks_02", "italy_road_markings_line_thin_yellow"]


def roads(L):
    mats = va.level_materials("italy")
    out = {}
    for m in ROAD_MATS:
        key, v = mats[m]
        out[key] = v
    d = os.path.join(LV, "art", "road"); os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, "main.materials.json"), "w"), indent=1)

    def offset_line(P, off):
        P = np.asarray(P)
        t = np.gradient(P[:, :2], axis=0); t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-9
        n = np.stack([-t[:, 1], t[:, 0]], 1)
        Q = P.copy(); Q[:, :2] += n * off
        return Q

    cnt = 0
    for r in TINFO["roads"]:
        P = np.array(r["pts"])
        if len(P) < 2:
            continue
        dist = np.hypot(P[:, 0], P[:, 1]).min()
        if dist > 1500:
            continue
        P[:, 2] = tz(P[:, 0], P[:, 1]) + 0.02
        hw = r["hw"]
        unpaved = r["type"] == "track" or r["surface"] in ("unpaved", "gravel", "dirt", "ground")
        def road(mat, pts, width, **kw):
            nonlocal cnt
            nodes = [[round(float(a), 3), round(float(b), 3), round(float(c), 3), width] for a, b, c in pts]
            o = {"class": "DecalRoad", "position": nodes[0][:3], "material": mat, "nodes": nodes, "improvedSpline": True,
                 "breakAngle": 5, "decalBias": 0.0015, "distanceFade": [120, 50], "startEndFade": [1, 1], "drivability": -1}
            o.update(kw)
            L.add("roads", o); cnt += 1
        ai = dict(drivability=0.4 if r["type"] in ("track", "service") else 1.0, oneWay=r.get("oneway", False))
        if unpaved:
            road("m_dirt_road_gravels", P, hw * 2, renderPriority=6, textureLength=7, **ai)
            continue
        road("m_road_variation_01", P, hw * 2, renderPriority=25, textureLength=112, **ai)
        near = dist < 900                     # dettagli solo vicino al terminal (tempi di caricamento)
        if near:
            road("italy_asphalt_overlay_light", P, hw * 2 - 0.4, renderPriority=20, textureLength=112)
        for s in (-1, 1):
            road("italy_road_edge_damage_wide_grassy", offset_line(P, s * (hw + 0.4)), 1.6, textureLength=8, distanceFade=[90, 30])
        if near and r["type"] in ("primary", "secondary", "tertiary", "trunk", "unclassified") and hw >= 3:
            for s in (-1, 1):
                road("italy_road_markings_line_thin", offset_line(P, s * (hw - 0.35)), 0.15, renderPriority=23, textureLength=4, distanceFade=[80, 40])
            road("italy_road_markings_center_line_broken_white", P, 0.15, renderPriority=24, textureLength=12, distanceFade=[80, 40])
        if near and rng.random() < 0.5:
            road("italy_road_cracks", P, hw * 2 - 0.6, renderPriority=26, textureLength=16, distanceFade=[80, 40])
    print("decal roads:", cnt)


# ====================================================================== edifici attorno (OSM + modelli di Italy)
TOWN = [f"italy_town_bld{i}" for i in range(1, 17)]
IND = ["ind_bld_8x8", "ind_bld_12x10", "ind_bld_12x12", "ind_bld_12x15", "ind_bld_12x20", "ind_bld_12x24", "ind_bld_12x30", "ind_bld_24x60"]
BIG = ["italy_bld_20x12_apartment", "italy_village_hotel"]


def obb(pts):
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


def buildings(L):
    dims = json.load(open(os.path.join(BUILD, "bld_dims.json")))
    osm = OSM()
    ind_area = []
    for pts, t in osm.polygons_where(lambda t: t.get("landuse") in ("industrial", "construction")):
        ind_area.append(np.asarray(pts))
    from matplotlib.path import Path as MPath
    ind_paths = [MPath(p) for p in ind_area]
    used, placed = set(), 0

    def place(shape, cx, cy, yaw, Lseg, W, zs=None, levels=None):
        nonlocal placed
        mn, mx = np.array(dims[shape]["min"]), np.array(dims[shape]["max"])
        sx0, sy0 = mx[:2] - mn[:2]
        if sx0 >= sy0:
            a, scx, scy = yaw, Lseg / sx0, W / sy0
        else:
            a, scx, scy = yaw + math.pi / 2, W / sx0, Lseg / sy0
        scx, scy = float(np.clip(scx, 0.65, 1.6)), float(np.clip(scy, 0.65, 1.6))
        if levels:
            sz = float(np.clip(levels * 3.1 / max(4.0, mx[2]), 0.5, 2.0))
        else:
            sz = zs or float(np.clip(math.sqrt(scx * scy), 0.85, 1.2))
        lc = (mn[:2] + mx[:2]) / 2 * [scx, scy]
        c, s = math.cos(a), math.sin(a)
        off = np.array([c * lc[0] - s * lc[1], s * lc[0] + c * lc[1]])
        px, py = cx - off[0], cy - off[1]
        # quota: minimo del terreno sotto l'impronta
        hx, hy = np.array([-1, 1, 1, -1, 0]) * Lseg / 2, np.array([-1, -1, 1, 1, 0]) * W / 2
        ca, sa = math.cos(yaw), math.sin(yaw)
        z = float(tz(cx + ca * hx - sa * hy, cy + sa * hx + ca * hy).min()) - 0.1
        L.add("dintorni/edifici", {"class": "TSStatic", "position": [round(px, 3), round(py, 3), round(z, 3)],
                                    "rotationMatrix": [round(v, 6) for v in rot_list_from_yaw(a)], "scale": [scx, scy, sz],
                                    "shapeName": f"/levels/italy/art/shapes/buildings/{shape}.dae", "collisionType": "Collision Mesh",
                                    "decalType": "Collision Mesh", "useInstanceRenderData": True})
        used.add(shape); placed += 1

    for pts, t in osm.polygons_where(lambda t: "building" in t):
        P = np.asarray(pts)
        ctr0 = P.mean(0)
        if np.hypot(*ctr0) > 1400:
            continue
        if tsample(TDLOT, ctr0[0], ctr0[1])[0] < 25:          # l'edificio del terminal e' gia' il nostro modello
            continue
        o = obb(pts)
        if o is None:
            continue
        yaw, Lb, Wb, ctr = o
        area = Lb * Wb
        if area < 12:
            continue
        kind = t.get("building", "yes")
        levels = None
        try:
            levels = float(t.get("building:levels")) if t.get("building:levels") else None
        except ValueError:
            pass
        industrial = kind in ("industrial", "warehouse", "manufacture", "hangar", "shed", "barn", "farm_auxiliary", "garage",
                              "garages", "service", "roof", "greenhouse") or any(pp.contains_point(ctr) for pp in ind_paths)
        h = int(abs(hash((round(ctr[0]), round(ctr[1])))))
        if kind in ("church", "chapel") or t.get("amenity") == "place_of_worship":
            place("italy_bld_church_village", ctr[0], ctr[1], yaw, Lb, Wb)
        elif area < 30:
            place("s_quarry_worker_shed_6x4", ctr[0], ctr[1], yaw, Lb, Wb, zs=1.0)
        elif industrial:
            # capannone con proporzioni piu' vicine; oltre 60 m lo spezzo
            nseg = max(1, int(round(Lb / 45)))
            for k in range(nseg):
                segL = Lb / nseg; off = (k + 0.5) * segL - Lb / 2
                cx, cy = ctr[0] + math.cos(yaw) * off, ctr[1] + math.sin(yaw) * off
                best = min(IND, key=lambda n: abs(math.log((dims[n]["max"][0] - dims[n]["min"][0]) / segL)) +
                           abs(math.log((dims[n]["max"][1] - dims[n]["min"][1]) / Wb)))
                place(best, cx, cy, yaw, segL, Wb, levels=levels)
        elif area > 380 and Wb > 14:
            nseg = max(1, int(round(Lb / 22)))
            for k in range(nseg):
                segL = Lb / nseg; off = (k + 0.5) * segL - Lb / 2
                place(BIG[(h + k) % 2], ctr[0] + math.cos(yaw) * off, ctr[1] + math.sin(yaw) * off, yaw, segL, Wb, levels=levels)
        else:
            nseg = max(1, int(round(Lb / 13))) if Lb > 20 else 1
            for k in range(nseg):
                segL = Lb / nseg; off = (k + 0.5) * segL - Lb / 2
                place(TOWN[(h + 7 * k) % len(TOWN)], ctr[0] + math.cos(yaw) * off, ctr[1] + math.sin(yaw) * off, yaw, segL, Wb, levels=levels)
    mats = {}
    for shp in used:
        va.collect(f"/levels/italy/art/shapes/buildings/{shp}.dae", "italy", mats)
    for k, v in mats.items():
        IMPORTED.setdefault(k, v)
    print("edifici:", placed, "modelli:", len(used), "materiali:", len(mats))


# ====================================================================== dettagli del piazzale: decal e sgommate
DECALS = ["repair_patch_decal", "pothole_decal", "eca_decals_concrete_damage_decal", "italy_ground_parts_decal",
          "nat_decals_fallen_leaves_01_decal", "ind_stuff_02"]


def lot_details(L, meta):
    # definizioni decal + materiali da Italy
    md = json.loads(va.read("/levels/italy/art/decals/managedDecalData.json"))
    dm = json.loads(va.read("/levels/italy/art/decals/main.materials.json"))
    out_md = {k: md[k] for k in DECALS}
    need = {md[k]["material"] for k in DECALS}
    out_m = {k: v for k, v in dm.items() if v.get("mapTo", k) in need or k in need}
    d = os.path.join(LV, "art", "decals"); os.makedirs(d, exist_ok=True)
    json.dump(out_md, open(os.path.join(d, "managedDecalData.json"), "w"), indent=1)
    json.dump(out_m, open(os.path.join(d, "main.materials.json"), "w"), indent=1)
    # maschera dell'asfalto dalla mesh
    from build_terrain import dae_triangles, Raster
    R = Raster(-200, -200, 400, 400, 0.5)
    asph = R.polys([[tuple(p[:2]) for p in tri] for mat, tri in dae_triangles(os.path.join(BUILD, "shapes", "ti_ground.dae")) if mat == "ti_asphalt"], 1) > 0
    asph_full = asph.copy()
    asph = ndimage.binary_erosion(asph, iterations=6)          # almeno 3 m dai cordoli
    ys, xs = np.nonzero(asph)

    def rnd_pts(n):
        i = rng.integers(0, len(xs), n)
        return R.x0 + (xs[i] + 0.5) * R.res, R.y0 + (ys[i] + 0.5) * R.res

    inst = {}
    def dec(name, x, y, size, rect=0, z=0.0):
        a = rng.uniform(0, 2 * math.pi)
        inst.setdefault(name, []).append([int(rect), round(float(size), 3), 0, round(float(x), 3), round(float(y), 3), z, 0, 0, 1,
                                          round(math.cos(a), 5), round(math.sin(a), 5), 0, int(rng.integers(1, 2 ** 31))])
    for x, y in zip(*rnd_pts(60)):
        dec("repair_patch_decal", x, y, rng.uniform(2.2, 5.5), rng.integers(0, 4))
    for x, y in zip(*rnd_pts(14)):
        dec("pothole_decal", x, y, rng.uniform(0.7, 1.5), rng.integers(0, 4))
    for x, y in zip(*rnd_pts(6)):
        dec("eca_decals_concrete_damage_decal", x, y, rng.uniform(3, 6))
    for x, y in zip(*rnd_pts(40)):
        dec("ind_stuff_02", x, y, rng.uniform(1.5, 3.5))                # macchie d'olio
    for x, y in zip(*rnd_pts(8)):
        dec("italy_ground_parts_decal", x, y, 0.9, rng.integers(0, 4))   # tombini/caditoie
    for t in meta["trees"]:
        for k in range(4):
            dec("nat_decals_fallen_leaves_01_decal", t["pos"][0] + rng.normal(0, 3), t["pos"][1] + rng.normal(0, 3), rng.uniform(2, 4))
    json.dump({"header": {"name": "DecalData File", "comments": "// Instances format: rectIdx, size, renderPriority, position.x, position.y, "
                          "position.z, normal.x, normal.y, normal.z, tangent.x, tangent.y, tangent.z, uid", "version": 2},
               "instances": inst}, open(os.path.join(LV, "main.decals.json"), "w"), indent=1)

    # crepe lunghe: giunzione centrale del piazzale (Street View 2022) e crepe sparse
    def crack(P, w=1.2):
        L.add("piazzale/crepe", {"class": "DecalRoad", "position": P[0], "material": "italy_road_cracks",
                                 "nodes": [[round(p[0], 3), round(p[1], 3), 0.01, w] for p in P], "overObjects": True,
                                 "improvedSpline": True, "renderPriority": 26, "textureLength": 16, "decalBias": 0.0015,
                                 "startEndFade": [2, 2], "distanceFade": [90, 40], "drivability": -1})
    seam = [geo.model2world(mx, 1.5 + 0.6 * math.sin(mx / 9.0)) for mx in np.arange(-85, 112, 6)]
    crack(seam, 1.6)
    for k in range(26):
        x, y = rnd_pts(1); x, y = float(x[0]), float(y[0])
        a = rng.uniform(0, math.pi); Lc = rng.uniform(8, 26)
        P = [[x + math.cos(a) * t + rng.normal(0, 0.4), y + math.sin(a) * t + rng.normal(0, 0.4)] for t in np.linspace(0, Lc, 5)]
        crack(P, rng.uniform(0.9, 1.6))
    # sgommate: cerchi, otto e archi nelle zone libere (DecalRoad sopra la mesh)
    def ring(cx, cy, r, turns=1.0, wobble=0.6, n=40):
        t = np.linspace(0, 2 * math.pi * turns, int(n * turns) + 1)
        rr = r + wobble * np.sin(t * 2.3 + rng.uniform(0, 6))
        return np.stack([cx + rr * np.cos(t), cy + rr * np.sin(t), np.full_like(t, 0.02)], 1)
    spots = [(20, -8), (60, 8), (-30, -20), (-70, -10), (5, 22)]
    for i, (mx, my) in enumerate(spots):
        cx, cy = geo.model2world(mx, my)
        for k in range(3):
            P = ring(cx + rng.normal(0, 0.8), cy + rng.normal(0, 0.8), rng.uniform(6.5, 9.5), turns=rng.uniform(0.7, 1.6))
            mat = "skidmarks_01" if (i + k) % 2 == 0 else "skidmarks_02"
            L.add("piazzale/sgommate", {"class": "DecalRoad", "position": P[0].tolist(), "material": mat,
                                        "nodes": [[*map(lambda v: round(float(v), 3), p), 1.5] for p in P], "overObjects": True,
                                        "improvedSpline": True, "renderPriority": 30, "textureLength": 10, "decalBias": 0.0015,
                                        "startEndFade": [3, 3], "distanceFade": [150, 60], "drivability": -1})
    # otto lungo il piazzale
    c0 = np.array(geo.model2world(35, -5)); c1 = np.array(geo.model2world(-5, -5))
    for c in (c0, c1):
        P = ring(c[0], c[1], 11, turns=1.0, wobble=1.0)
        L.add("piazzale/sgommate", {"class": "DecalRoad", "position": P[0].tolist(), "material": "skidmarks_02",
                                    "nodes": [[*map(lambda v: round(float(v), 3), p), 1.6] for p in P], "overObjects": True,
                                    "improvedSpline": True, "renderPriority": 30, "textureLength": 10, "decalBias": 0.0015,
                                    "startEndFade": [3, 3], "distanceFade": [150, 60], "drivability": -1})
    # strisce gialle sbiadite dei posti auto lungo il marciapiede nord-ovest (Street View 2022)
    def is_asph(mx, my):
        x, y = geo.model2world(mx, my)
        i, j = int((x - R.x0) / R.res), int((y - R.y0) / R.res)
        return 0 <= i < R.w and 0 <= j < R.h and asph_full[j, i]
    n_st = 0
    for mx in np.arange(4, 104, 2.6):
        my = next((yy for yy in np.arange(46, 10, -0.25) if is_asph(mx, yy)), None)
        if my is None or rng.random() < 0.12:                          # qualche striscia ormai cancellata
            continue
        a, b = geo.model2world(mx, my - 0.4), geo.model2world(mx, my - 5.2)
        L.add("piazzale/segnaletica", {"class": "DecalRoad", "position": [a[0], a[1], 0.01],
                                       "material": "italy_road_markings_line_thin_yellow",
                                       "nodes": [[a[0], a[1], 0.01, 0.12], [b[0], b[1], 0.01, 0.12]], "overObjects": True,
                                       "renderPriority": 23, "textureLength": 4, "decalBias": 0.0015, "distanceFade": [80, 40],
                                       "drivability": -1})
        n_st += 1
    print("decal:", {k: len(v) for k, v in inst.items()}, "strisce gialle:", n_st)


# ====================================================================== arredo urbano
def street_furniture(L, meta):
    lit = 0; poles = 0
    types = ("residential", "tertiary", "unclassified", "secondary", "primary", "trunk_link", "primary_link", "living_street")
    for ri, r in enumerate(TINFO["roads"]):
        if r["type"] not in types:
            continue
        P = np.array(r["pts"])[:, :2]
        if len(P) < 2 or np.hypot(P[:, 0], P[:, 1]).min() > 700:
            continue
        seg = np.hypot(*np.diff(P, axis=0).T); Ls = np.concatenate([[0], np.cumsum(seg)])
        side = 1 if ri % 2 else -1
        for s in np.arange(12, Ls[-1] - 5, 31.0):
            x, y = np.interp(s, Ls, P[:, 0]), np.interp(s, Ls, P[:, 1])
            k = min(np.searchsorted(Ls, s), len(P) - 1)
            t = P[k] - P[max(k - 1, 0)]; t = t / (np.hypot(*t) + 1e-9)
            n = np.array([-t[1], t[0]]) * side
            px, py = x + n[0] * (r["hw"] + 1.3), y + n[1] * (r["hw"] + 1.3)
            if np.hypot(px, py) > 700 or tsample(TDLOT, px, py)[0] < 10:
                continue
            if tsample(TDROAD, px, py)[0] < r["hw"] + 0.8:      # un'altra strada troppo vicina (incroci)
                continue
            d = -n                                              # verso la carreggiata
            a = math.atan2(d[0], -d[1])
            z = float(tz(px, py)[0])
            name = f"lamp_street_{poles:03d}"
            obj = {"name": name, "class": "TSStatic", "position": [round(px, 3), round(py, 3), round(z, 3)],
                   "rotationMatrix": [round(v, 6) for v in rot_list_from_yaw(a)], "annotation": "POLE",
                   "shapeName": "/levels/italy/art/shapes/buildings/italy_light_single.dae", "useInstanceRenderData": True}
            if np.hypot(px, py) < 350:
                light = f"lamp_street_light_{poles:03d}"
                obj["child"] = light
                hx, hy = px + d[0] * 0.45, py + d[1] * 0.45
                L.add("dintorni/illuminazione", {"name": light, "class": "SpotLight", "position": [round(hx, 3), round(hy, 3), round(z + 8.1, 3)],
                                                 "rotationMatrix": [1, 0, 0, 0, 0, -1, 0, 1, 0], "color": [1, 0.75, 0.48, 1],
                                                 "brightness": 3, "range": 20, "innerAngle": 70, "outerAngle": 130,
                                                 "castShadows": False, "isEnabled": False, "nightLight": True})
                lit += 1
            L.add("dintorni/illuminazione", obj)
            poles += 1
    # fermata e cestini alle pensiline del terminal
    for i, (x, y, z) in enumerate(meta["benches"][::2]):
        L.add("terminal/arredo", {"class": "TSStatic", "position": [x + 2.2, y + 0.4, 0.1], "shapeName": "/art/shapes/objects/s_sign_busstop.dae",
                                  "rotationMatrix": rot_list_from_yaw(math.radians(geo.MODEL_ROT_DEG)), "annotation": "TRAFFIC_SIGNS"})
        L.add("terminal/arredo", {"class": "TSStatic", "position": [x - 2.4, y - 0.6, 0.1],
                                  "shapeName": "/levels/italy/art/shapes/buildings/italy_city_extras_trash_bin.dae",
                                  "rotationMatrix": rot_list_from_yaw(math.radians(geo.MODEL_ROT_DEG + 180))})
    mats = {}
    for shp in ("italy_light_single", "italy_city_extras_trash_bin"):
        va.collect(f"/levels/italy/art/shapes/buildings/{shp}.dae", "italy", mats)
    for k, v in mats.items():
        IMPORTED.setdefault(k, v)
    print("lampioni stradali:", poles, "con luce:", lit)


# ====================================================================== abbandono: rifiuti e oggetti come nella foto
def clutter(L):
    B = "/levels/italy/art/shapes/buildings/"
    door = np.array([45.51, 40.98]); n = np.array([0.74, 0.67]); t = np.array([-0.67, 0.74])   # facciata della foto (NE)
    def put(shape, along, out, yaw_deg, z=0.1, tilt=None, scale=1.0):
        p = door + t * along + n * out
        a = math.radians(yaw_deg)
        rot = rot_list_from_yaw(a)
        if tilt:                               # oggetto rovesciato: ruoto l'asse Z locale verso l'orizzontale
            c, s = math.cos(a), math.sin(a)
            rot = [c, s, 0, 0, 0, 1, s, -c, 0]
        L.add("terminal/abbandono", {"class": "TSStatic", "position": [round(float(p[0]), 3), round(float(p[1]), 3), z],
                                     "rotationMatrix": [round(v, 6) for v in rot], "scale": [scale] * 3, "shapeName": B + shape + ".dae",
                                     "collisionType": "Collision Mesh", "useInstanceRenderData": True})
        return shape
    used = [put("italy_clutter_plastic_chair_a", -0.3, 1.1, 20, z=0.35, tilt=True),
            put("italy_clutter_trashbag", 0.9, 0.6, 40), put("italy_clutter_trashbag", 1.4, 0.9, 110),
            put("italy_clutter_trashbag", -1.6, 0.5, 200), put("italy_clutter_concbag_pile", 3.5, 0.9, 15),
            put("italy_clutter_pallet", -3.2, 0.35, 80, z=0.1), put("italy_clutter_metal_drum", 5.0, 1.2, 0),
            put("italy_clutter_rubble_dumpster", 9.0, 5.5, 45)]
    # cassonetto e fusti sul piazzale, vicino al bordo nord-ovest
    for (mx, my, yaw, shp) in [(70, 34, 44.5, "italy_clutter_dumpster"), (72.5, 34.5, 10, "italy_clutter_metal_drum"),
                               (-20, 41, 44.5, "italy_clutter_dumpster"), (30, 44, 0, "italy_clutter_sorting_bin")]:
        x, y = geo.model2world(mx, my)
        L.add("terminal/abbandono", {"class": "TSStatic", "position": [round(x, 3), round(y, 3), 0.1],
                                     "rotationMatrix": rot_list_from_yaw(math.radians(yaw)), "shapeName": B + shp + ".dae",
                                     "collisionType": "Collision Mesh", "useInstanceRenderData": True})
        used.append(shp)
    # barriere New Jersey di plastica rosse e idranti (Street View 2022)
    for (mx, my, yaw, shp) in [(60, 22, 44.5, "italy_newjersey_plastic.DAE"), (61.2, 22.3, 50, "italy_newjersey_plastic.DAE"),
                               (72, -12, 10, "italy_newjersey_plastic.DAE"), (96, 26, 80, "italy_newjersey_plastic.DAE"),
                               (-5, 38, 30, "italy_newjersey_plastic.DAE"), (112, 20, 100, "italy_newjersey_plastic.DAE"),
                               (58, -14.8, 0, "italy_clutter_fire_hydrant.DAE"), (25, 27.5, 0, "italy_clutter_fire_hydrant.DAE"),
                               (-30, -22, 0, "italy_clutter_fire_hydrant.DAE")]:
        x, y = geo.model2world(mx, my)
        L.add("terminal/abbandono", {"class": "TSStatic", "position": [round(x, 3), round(y, 3), 0.0],
                                     "rotationMatrix": rot_list_from_yaw(math.radians(yaw)), "shapeName": B + shp,
                                     "collisionType": "Collision Mesh", "useInstanceRenderData": True})
        used.append(shp)
    mats = {}
    for shp in set(used):
        va.collect(B + (shp if shp.lower().endswith(".dae") else shp + ".dae"), "italy", mats)
    for k, v in mats.items():
        IMPORTED.setdefault(k, v)


# ====================================================================== cielo, luce, terreno, spawn
def environment(L):
    L.add("Level_objects", {"name": "theLevelInfo", "class": "LevelInfo", "canvasClearColor": [1, 1, 1, 255],
                            "fogAtmosphereHeight": 600, "fogColor": [0.66, 0.74, 0.84, 1], "fogDensity": 0.00012,
                            "globalEnviromentMap": "cubemap_italy_reflection", "gravity": -9.81, "visibleDistance": 16000,
                            "temperatureCurveC": [0, 16, 0.25, 12, 0.5, 8, 0.75, 10, 1, 16]})
    # ora reale: 12 ottobre, 15:30 (time 0 = mezzogiorno), sole calcolato da lat/lon di Isernia
    L.add("Level_objects", {"name": "tod", "class": "TimeOfDay", "position": [0, 0, 50], "axisTilt": 23.44, "dayLength": 1800,
                            "play": False, "startTime": 0.146, "time": 0.146, "latitude": geo.LAT0, "longitude": geo.LON0,
                            "year": 2025, "month": 10, "day": 12, "utcOffset": 2, "dstRule": "eu", "version": 2})
    L.add("Level_objects", {"name": "sunsky", "class": "ScatterSky", "position": [0, 0, 60],
                            "ambientScale": [0.992, 0.89, 0.776, 1], "ambientScaleGradientFile": "art/sky_gradients/default/gradient_ambient.png",
                            "colorize": [0.3137, 0.3372, 0.6862, 1], "colorizeGradientFile": "art/sky_gradients/default/gradient_colorize.png",
                            "enableFogFallBack": False, "flareScale": 5, "flareType": "BNG_Sunflare_3",
                            "fogScale": [0.396, 0.667, 1, 1], "fogScaleGradientFile": "art/sky_gradients/default/gradient_fog.png",
                            "mieScattering": 0.00072, "moonMat": "Moon_Glow_Mat", "moonScale": 0.05, "nightColor": [0, 0, 0, 1],
                            "nightCubemap": "nightCubemap", "nightFogColor": [0, 0, 0, 1],
                            "nightFogGradientFile": "art/sky_gradients/default/gradient_fog.png", "nightGradientFile": "art/sky_gradients/default/gradient_ambient.png",
                            "occlusionScale": 0.025, "shadowDarkenColor": [0, 0, 0, 0], "shadowDistance": 1600, "shadowSoftness": 0.15,
                            "logWeight": 0.98, "texSize": 4096, "lastSplitTerrainOnly": False, "skyBrightness": 40,
                            "sunScale": [0.996, 0.80, 0.66, 1], "sunScaleGradientFile": "art/sky_gradients/default/gradient_sunscale.png",
                            "useNightCubemap": True})
    L.add("Level_objects", {"name": "clouds1", "class": "CloudLayer", "position": [0, 0, 0], "Textures": [{}, {}, {}], "coverage": 0.55,
                            "exposure": 1.3, "height": 7, "texture": "levels/italy/art/skies/SkyNormals_05.dds", "windSpeed": 0.12})
    L.add("Level_objects", {"class": "ForestWindEmitter", "position": [0, 0, 0], "strength": 0.6, "windDirection": [0.7, 0.3, 0]})
    L.add("Level_objects", {"name": "theForest", "class": "Forest", "lodReflectScalar": 0})
    mi = TINFO["main"]
    L.add("terrain", {"name": "theTerrain", "class": "TerrainBlock", "position": mi["position"], "maxHeight": mi["maxHeight"],
                      "squareSize": mi["squareSize"], "baseTexSize": 4096, "materialTextureSet": "ti_TerrainMaterialTextureSet",
                      "terrainFile": LVP + "terrain_main.ter", "minimapImage": LVP + "terminal_isernia_minimap.png"})
    L.add("terrain", {"name": "sfondo_colline", "class": "TSStatic", "position": [0, 0, 0], "collisionType": "None",
                      "shapeName": LVP + "art/shapes/terminal/ti_backdrop.dae", "useInstanceRenderData": True})


def spawns_and_vehicles(L):
    old = os.path.join(ORIG, "main", "MissionGroup")
    for grp in ("SimGroup_n",):
        for l in open(os.path.join(old, grp, "items.level.json"), encoding="utf8"):
            d = json.loads(l)
            d["position"] = old_to_world(d["position"])
            if "rotationMatrix" in d:
                d["rotationMatrix"] = rotate_list(d["rotationMatrix"], math.radians(geo.MODEL_ROT_DEG))
            d.pop("__parent", None)
            L.add("veicoli/" + ("parcheggiati" if grp == "SimGroup_n" else "noi"), d)
    sp = json.loads(open(os.path.join(old, "PlayerDropPoints", "items.level.json")).read())
    sp["position"] = old_to_world(sp["position"]); sp["position"][2] = 0.6
    sp["rotationMatrix"] = rotate_list(sp["rotationMatrix"], math.radians(geo.MODEL_ROT_DEG))
    sp.pop("__parent", None)
    L.add("PlayerDropPoints", sp)
    # spawn extra: davanti all'edificio e all'ingresso sud-ovest
    for name, (mx, my, yaw) in {"spawn_edificio": (78, -30, 180), "spawn_ingresso": (-70, 20, -30)}.items():
        x, y = geo.model2world(mx, my)
        L.add("PlayerDropPoints", {"name": name, "class": "SpawnSphere", "position": [x, y, 0.6], "dataBlock": "SpawnSphereMarker",
                                   "radius": 5, "rotationMatrix": rot_list_from_yaw(math.radians(yaw + geo.MODEL_ROT_DEG)),
                                   "autoplaceOnSpawn": "0", "sphereWeight": "1"})
    # inquadrature per screenshot/test
    def bookmark(name, cam, target):
        cx, cy = geo.model2world(cam[0], cam[1]); tx_, ty_ = geo.model2world(target[0], target[1])
        f = np.array([tx_ - cx, ty_ - cy, target[2] - cam[2]]); f /= np.linalg.norm(f)
        r = np.cross(f, [0, 0, 1]); r /= np.linalg.norm(r); u = np.cross(r, f)
        L.add("CameraBookmarks", {"name": name, "internalName": name, "class": "CameraBookmark", "position": [cx, cy, cam[2]],
                                  "dataBlock": "CameraBookmarkMarker", "rotationMatrix": [*r, *f, *u]})
    bookmark("foto_facciata", (99, -34, 1.7), (99, -8, 2.2))
    bookmark("vista_piazzale", (-40, -35, 4), (60, 5, 0))
    bookmark("aereo", (-120, -150, 90), (40, 0, 0))
    bookmark("pensilina", (55, -24, 1.7), (62.6, -13.8, 1.2))
    bookmark("ingresso", (-95, 30, 2), (0, -10, 1))


def info_and_misc():
    info = {"title": "Terminal Isernia", "description": "L'ex terminal bus di Isernia (localita' Le Piane), ricostruito in scala reale: "
            "altimetria vera, strade e boschi da OpenStreetMap, materiali PBR fotografici. Perfetto per sgommare.",
            "previews": ["terminal_isernia_preview.jpg"], "size": [4096, 4096], "biome": "Collina appenninica",
            "roads": "Piazzale in asfalto, strade comunali", "suitablefor": "Drift, sgommate, giro libero",
            "features": "Terreno reale 4 km + orizzonte 33 km, luci notturne", "isAuxiliary": False, "authors": "Matto",
            "defaultSpawnPointName": "spawn_default", "spawnPoints": [
                {"translationId": "Piazzale", "objectname": "spawn_default", "preview": "terminal_isernia_preview.jpg"},
                {"translationId": "Edificio", "objectname": "spawn_edificio", "preview": "terminal_isernia_preview.jpg"},
                {"translationId": "Ingresso", "objectname": "spawn_ingresso", "preview": "terminal_isernia_preview.jpg"}]}
    json.dump(info, open(os.path.join(LV, "info.json"), "w"), indent=2)
    for f in ("terminal_isernia_preview.jpg",):
        if not os.path.exists(os.path.join(LV, f)):
            shutil.copy2(os.path.join(ORIG, f), os.path.join(LV, f))


def minimap():
    from PIL import Image
    b = Image.open(os.path.join(LV, "art", "terrains", "t_ti_terrain_base_b.png")).resize((1024, 1024), Image.LANCZOS)
    b.save(os.path.join(LV, "terminal_isernia_minimap.png"), optimize=True)


def main():
    L = Level()
    environment(L)
    meta = place_terminal(L)
    write_forest_defs()
    make_forest(meta)
    groundcover(L)
    roads(L)
    buildings(L)
    street_furniture(L, meta)
    clutter(L)
    lot_details(L, meta)
    spawns_and_vehicles(L)
    info_and_misc()
    minimap()
    # materiali importati: un unico file (le cartelle vecchie vengono rimosse)
    for old in ("art/forest/main.materials.json", "art/shapes/buildings", "art/shapes/arredo"):
        p = os.path.join(LV, old)
        if os.path.isdir(p): shutil.rmtree(p)
        elif os.path.exists(p): os.remove(p)
    d = os.path.join(LV, "art", "imported"); os.makedirs(d, exist_ok=True)
    cub = json.loads(va.read("/levels/italy/art/cubemaps/cubemap_italy_reflection/main.materials.json"))
    for k, v in cub.items():
        IMPORTED.setdefault(k, v)
    json.dump(IMPORTED, open(os.path.join(d, "main.materials.json"), "w"), indent=1)
    print("materiali importati:", len(IMPORTED))
    L.write()
    print("LEVEL_OK", {g: len(o) for g, o in L.groups.items()})


if __name__ == "__main__":
    main()
