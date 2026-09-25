"""Assembla il livello BeamNG terminal_isernia (v1.0) nella cartella mod/.

Prerequisiti (in ordine): blender_export.py, build_textures.py, build_terrain.py
Uso: python tools/build_level.py
"""
import os, sys, json, math, shutil, uuid, glob
import numpy as np
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo
import lot_layout as LL
import vanilla_assets as va
from osm import OSM, obb

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


_GZ = {}


def ground_z(x, y):
    """quota del suolo in (x, y): la mesh del piazzale (asfalto 0, marciapiedi e isole 0.1) o il terreno."""
    if "r" not in _GZ:
        from build_terrain import dae_triangles
        from PIL import Image, ImageDraw
        x0, y0, res, n = -200.0, -200.0, 0.25, 1600
        im = Image.new("F", (n, n), -99.0); d = ImageDraw.Draw(im)
        for m, tri in dae_triangles(os.path.join(BUILD, "shapes", "ti_ground.dae")):
            d.polygon([((p[0] - x0) / res, (p[1] - y0) / res) for p in tri], fill=float(max(p[2] for p in tri)))
        _GZ["r"] = (np.asarray(im), x0, y0, res, n)
    a, x0, y0, res, n = _GZ["r"]
    i, j = int((x - x0) / res), int((y - y0) / res)
    if 0 <= i < n and 0 <= j < n and a[j, i] > -50:
        return float(a[j, i])
    return float(tz(x, y)[0])


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
        # detailMap su UV1 (230 m): variazione macro, corsie consumate e bordi sporchi; rompe la ripetizione dei 3 m
        pbr("ti_asphalt", T + "t_ti_asphalt", "ASPHALT",
            detailMap=T + "t_ti_asphalt_macro_detail_b.data.png", detailMapUseUV=1, detailScale=[1, 1], detailBaseColorMapStrength=1.0,
            layer2=stage(baseColorMap=T + "t_ti_asphalt_cracked_b.color.png", normalMap=T + "t_ti_asphalt_cracked_nm.normal.png",
                         roughnessMap=T + "t_ti_asphalt_cracked_r.data.png", ambientOcclusionMap=T + "t_ti_asphalt_cracked_ao.data.png",
                         opacityMap=T + "t_ti_asphalt_breakup_o.data.png", opacityMapUseUV=1, opacityFactor=0.5)),
        pbr("ti_pavers_moss", T + "t_ti_pavers_moss", "COBBLESTONE", **det_concrete),
        pbr("ti_pavers", T + "t_ti_pavers", "COBBLESTONE", **det_concrete),
        pbr("ti_pavers_grey", T + "t_ti_pavers_grey", "COBBLESTONE", **det_concrete),
        ("ti_reed_plume", dict(reeds_mat("ti_reed_plume", "t_grass_dry_long_01", [1, 1, 1, 1])[1],
                               Stages=[{"baseColorMap": T + "t_ti_reed_plume_b.color.png", "opacityMap": T + "t_ti_reed_plume_o.data.png",
                                        "roughnessFactor": 0.8}, {}, {}, {}], alphaRef=70)),
        pbr("ti_skylight_glass", None, "GLASS", baseColorFactor=[0.78, 0.82, 0.82, 0.55], roughnessFactor=0.2, metallicFactor=0,
            detailMap=AS + "breakup/t_detail_concrete_02/t_detail_concrete_02_detail_b.data.png", detailBaseColorMapStrength=0.6,
            detailScale=[1, 1], m_translucent=True, m_translucentBlendOp="LerpAlpha", m_translucentZWrite=False, m_doubleSided=True),
        pbr("ti_skylight_frame", None, "METAL", baseColorFactor=[0.55, 0.57, 0.55, 1], **dict(paint, roughnessFactor=0.6)),
        pbr("ti_pole_concrete", T + "t_ti_pillar", "ASPHALT", **det_concrete),
        pbr("ti_curb", T + "t_ti_curb", "ASPHALT", **det_concrete),
        pbr("ti_planter_soil", None, "DIRT",
            baseColorMap=AS + "terrain/forest/t_forest_ground/t_forest_ground_b.png", normalMap=AS + "terrain/forest/t_forest_ground/t_forest_ground_nm.png",
            roughnessMap=AS + "terrain/forest/t_forest_ground/t_forest_ground_r.png", ambientOcclusionMap=AS + "terrain/forest/t_forest_ground/t_forest_ground_ao.png"),
        pbr("ti_railing", None, "METAL", baseColorMap=AS + "tileable/metal/metal_paint_peeling/paint_peeling_d.dds",
            normalMap=AS + "tileable/metal/metal_paint_peeling/paint_peeling_n.dds", baseColorFactor=[0.19, 0.085, 0.05, 1],
            roughnessFactor=0.82, metallicFactor=0.1),   # ringhiera verniciata marrone scuro e arrugginita (Street View 2022)
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
        pbr("ti_canopy_panel", None, "PLASTIC", baseColorFactor=[0.50, 0.55, 0.50, 0.58], roughnessFactor=0.55, metallicFactor=0,
            detailMap=AS + "breakup/t_detail_concrete_02/t_detail_concrete_02_detail_b.data.png", detailBaseColorMapStrength=0.8,
            detailScale=[1, 1], m_translucent=True, m_translucentBlendOp="LerpAlpha", m_translucentZWrite=False,
            m_doubleSided=True, m_castShadows=True),
        pbr("ti_lamp_black", None, "METAL", baseColorFactor=[0.035, 0.035, 0.035, 1], **dict(paint, roughnessFactor=0.45)),
        pbr("ti_lamp_globe", None, "PLASTIC", baseColorFactor=[0.95, 0.95, 0.92, 1], roughnessFactor=0.15, metallicFactor=0,
            emissive=True, instanceEmissive=True, emissiveFactor=[1, 1, 1], emissiveIntensityNits=6000),
        pbr("ti_backdrop", None, "GRASS", baseColorMap=LVP + "art/terrains/t_ti_far_base_b.png",
            normalMap=LVP + "art/terrains/t_ti_far_base_nm.png", roughnessFactor=0.95, metallicFactor=0),
        ("ti_willow_leaves", {"name": "ti_willow_leaves", "mapTo": "ti_willow_leaves", "class": "Material", "persistentId": uid("mat/willow_leaves"),
                              "version": 1.5, "Stages": [{"baseColorMap": T + "t_ti_willow_leaves_b.color.png", "opacityMap": T + "t_ti_willow_leaves_o.data.png",
                                                          "normalMap": T + "t_ti_willow_leaves_nm.normal.png", "roughnessMap": T + "t_ti_willow_leaves_r.data.png"},
                                                         {}, {}, {}],
                              "alphaRef": 90, "alphaTest": True, "doubleSided": True, "invertBackFaceNormals": True, "subSurface": True,
                              "subSurfaceIntensity": 1, "groundType": "GRASS", "annotation": "NATURE", "materialTag0": "beamng",
                              "translucentBlendOp": "None"}),
        pbr("ti_willow_bark", None, "WOOD", baseColorMap=AS + "tree/poplar/t_poplar_bark/t_poplar_bark_b.color.dds",
            normalMap=AS + "tree/poplar/t_poplar_bark/t_poplar_bark_nm.normal.dds", roughnessMap=AS + "tree/poplar/t_poplar_bark/t_poplar_bark_r.data.dds",
            ambientOcclusionMap=AS + "tree/poplar/t_poplar_bark/t_poplar_bark_ao.data.dds"),
        pbr("ti_island_soil", None, "GRASS", baseColorMap=AS + "terrain/grass/t_dirt_dry_grass/t_dirt_dry_grass_b.png",
            baseColorFactor=[0.40, 0.37, 0.25, 1],   # texture in scala di grigi: terra secca bruno-olivastra (Street View 2022)
            normalMap=AS + "terrain/grass/t_dirt_dry_grass/t_dirt_dry_grass_nm.png", roughnessMap=AS + "terrain/grass/t_dirt_dry_grass/t_dirt_dry_grass_r.png",
            ambientOcclusionMap=AS + "terrain/grass/t_dirt_dry_grass/t_dirt_dry_grass_ao.png"),
        pbr("ti_carwash_roof", None, "METAL", baseColorFactor=[0.86, 0.87, 0.88, 1], **dict(paint, roughnessFactor=0.5)),
        pbr("ti_carwash_blue", None, "METAL", baseColorFactor=[0.08, 0.22, 0.55, 1], **dict(paint, roughnessFactor=0.45)),
        pbr("ti_carwash_panel", None, "PLASTIC", baseColorFactor=[0.75, 0.78, 0.8, 1], roughnessFactor=0.4, metallicFactor=0),
        pbr("ti_grille", None, "METAL", baseColorMap=AS + "tileable/metal/metal_paint_peeling/paint_peeling_d.dds",
            normalMap=AS + "tileable/metal/metal_paint_peeling/paint_peeling_n.dds", baseColorFactor=[0.09, 0.075, 0.065, 1],
            roughnessFactor=0.7, metallicFactor=0.25),   # grate verniciate scure, arrugginite
        pbr("ti_bridge_concrete", T + "t_ti_curb", "ASPHALT", **det_concrete),
        pbr("ti_bridge_deck", T + "t_ti_asphalt", "ASPHALT"),
        pbr("ti_notice_panel", None, "PLASTIC", baseColorFactor=[0.80, 0.80, 0.76, 1], roughnessFactor=0.85, metallicFactor=0,
            **dict(det_concrete, detailBaseColorMapStrength=0.6)),   # pannello bianco sbiadito della bacheca
        reeds_mat("ti_reeds", "t_grass_green_long_03", [0.58, 0.74, 0.52, 1]),
        reeds_mat("ti_reeds_dry", "t_grass_dry_long_01", [0.62, 0.63, 0.52, 1]),
    ])
    return mats


# ====================================================================== terminal: mesh + lampioni
_SHP = {}


def SHP(nm):
    """percorso nel gioco della mesh nm: il nome contiene un hash del contenuto. BeamNG tiene una cache compilata (.cdae)
    per percorso e la riusa se le sembra piu' recente del .dae: con lo stesso nome, dopo un aggiornamento della mod
    (o una ricostruzione a gioco aperto) disegnava la versione vecchia mentre la collisione era quella nuova
    (isole 6 m fuori posto, alberi e pali "sulla strada")."""
    if nm not in _SHP:
        import hashlib
        h = hashlib.md5(open(os.path.join(BUILD, "shapes", nm + ".dae"), "rb").read()).hexdigest()[:8]
        _SHP[nm] = f"{nm}_{h}.dae"
    return LVP + "art/shapes/terminal/" + _SHP[nm]


def publish_shapes():
    """copia atomica delle mesh con il nome a hash e rimozione delle versioni precedenti (il gioco tiene la mod montata)."""
    shp = os.path.join(LV, "art", "shapes", "terminal")
    os.makedirs(shp, exist_ok=True)
    keep = set()
    for f in glob.glob(os.path.join(BUILD, "shapes", "*.dae")):
        nm = os.path.splitext(os.path.basename(f))[0]
        dst = os.path.join(shp, os.path.basename(SHP(nm)))
        keep.add(os.path.basename(dst))
        if not os.path.exists(dst):
            tmp = os.path.join(BUILD, "tmp_save", os.path.basename(dst)); os.makedirs(os.path.dirname(tmp), exist_ok=True)
            shutil.copy2(f, tmp); os.replace(tmp, dst)
    for f in glob.glob(os.path.join(shp, "*.dae")):
        if os.path.basename(f) not in keep:
            try:
                os.remove(f)
            except OSError as e:                     # aperta dal gioco: resta, ma nessun oggetto la usa piu'
                print("non rimossa:", os.path.basename(f), e)


def place_terminal(L):
    shp = os.path.join(LV, "art", "shapes", "terminal")
    json.dump(terminal_materials(), open(os.path.join(shp, "main.materials.json"), "w"), indent=1)
    for nm in ("ti_ground", "ti_building", "ti_railing", "ti_props", "ti_canopy", "ti_grilles", "ti_skylight", "ti_powerline", "ti_bacheca"):
        L.add("terminal", {"name": nm.replace("ti_", "terminal_"), "class": "TSStatic", "position": [0, 0, 0], "shapeName": SHP(nm),
                           "collisionType": "Visible Mesh Final", "decalType": "Visible Mesh", "useInstanceRenderData": True})
    meta = json.load(open(os.path.join(BUILD, "export_meta.json")))
    for i, lp in enumerate(meta["lamps"]):
        lp["pos"][2] = round(ground_z(lp["pos"][0], lp["pos"][1]) - 0.02, 3)
        R = lp["rot"]
        rotl = [R[0][0], R[1][0], R[2][0], R[0][1], R[1][1], R[2][1], R[0][2], R[1][2], R[2][2]]
        light = f"ti_lamp_light_{i:02d}"
        L.add("terminal/lampioni", {"name": f"ti_lamp_{i:02d}", "class": "TSStatic", "position": lp["pos"], "rotationMatrix": rotl,
                                    "shapeName": SHP("ti_lamp_pastorale"), "collisionType": "Visible Mesh Final",
                                    "useInstanceRenderData": True, "instanceColor": [0, 0, 0, 1], "child": light})
        # testa del lampione a pastorale (blender_props.py): locale (0, 1.62, 9.1), braccio lungo +Y
        h = np.array(lp["pos"]) + np.array(R) @ np.array([0.0, 1.62, 9.1])
        L.add("terminal/lampioni", {"name": light, "class": "SpotLight", "position": [round(float(h[0]), 3), round(float(h[1]), 3), round(float(h[2]), 3)],
                                    "rotationMatrix": [1, 0, 0, 0, 0, -1, 0, 1, 0],     # asse Y locale verso il basso
                                    "color": [1, 0.72, 0.42, 1], "brightness": 3, "range": 22, "innerAngle": 60, "outerAngle": 125,
                                    "castShadows": i % 3 == 0, "isEnabled": False, "nightLight": True})
    # lampioni decorativi a due globi agli angoli delle pensiline (Street View 2022)
    for i, (mx, my, yaw) in enumerate([(88.9, -20.3, 20), (89.6, 3.9, -20)]):
        for k in range(20):                             # sulla piattaforma dell'edificio, non sull'asfalto accanto
            if ground_z(*geo.model2world(mx, my)) > 0.05:
                break
            mx, my = mx + (100 - mx) * 0.04, my + (-8 - my) * 0.04
        x, y = geo.model2world(mx, my)
        light = f"ti_globe_light_{i}"
        L.add("terminal/lampioni", {"name": f"ti_globe_{i}", "class": "TSStatic", "position": [x, y, round(ground_z(x, y), 3)],
                                    "rotationMatrix": rot_list_from_yaw(math.radians(yaw + geo.MODEL_ROT_DEG)),
                                    "shapeName": SHP("ti_lamp_globe"), "collisionType": "Visible Mesh Final",
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
                               "shapeFile": SHP("ti_reeds"), "windScale": 0.8, "trunkBendScale": 0.03,
                               "branchAmp": 0.08, "detailAmp": 0.35, "detailFreq": 0.9, "mass": 1}
    items["ti_willow"] = {"name": "ti_willow", "internalName": "ti_willow_int", "class": "ForestItemData",
                          "persistentId": uid("fid/willow"), "annotation": "NATURE",
                          "shapeFile": SHP("ti_willow"), "windScale": 0.7, "trunkBendScale": 0.006,
                          "branchAmp": 0.12, "detailAmp": 0.25, "detailFreq": 0.6, "mass": 5000, "radius": 0.4}
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


# coordinate modello del tronco: sul marciapiede nord-ovest, 1.2 m prima della ringhiera (non oltre).
# Street View set 2022 (41.60392 N 14.24645 E): salice a 306 gradi, base al cordolo a ~70 m; chioma ~16 m sull'ortofoto
WILLOW_MODEL = LL.WILLOW


def make_forest(meta):
    inst = {}
    def put(kind, x, y, s_lo=0.85, s_hi=1.2, z_off=-0.05):
        x, y = np.atleast_1d(x), np.atleast_1d(y)
        ok = ~in_building(x, y) & (tsample(TDROAD, x, y) > tsample(TRHW, x, y) + 0.8)
        x, y = x[ok], y[ok]
        if len(x) == 0:
            return
        z = tz(x, y) + z_off
        for xi, yi, zi in zip(np.atleast_1d(x), np.atleast_1d(y), np.atleast_1d(z)):
            a = rng.uniform(0, 2 * math.pi)
            inst.setdefault(kind, []).append({"ctxid": 0, "pos": [round(float(xi), 3), round(float(yi), 3), round(float(zi), 3)],
                                              "rotationMatrix": [round(v, 6) for v in rot_list_from_yaw(a)],
                                              "scale": round(float(rng.uniform(s_lo, s_hi)), 4), "type": kind})
    # 1) aiuole del terminal: lecci da citta' al posto degli alberi originali
    for t in meta["trees"]:
        x, y = t["pos"]; h = t["height"]
        kind = "tree_aspen_small_a" if h > 5 else "holm_oak_city_small"      # Street View 2022: latifoglie giovani, foglie giallo-verdi
        scale = round(min(1.25, max(0.6, h / (7.5 if h > 5 else 4.5))), 3)
        mx, my = geo.world2model(x, y)
        if LL.in_median(mx, my, 1.0) and any(abs(mx - v) < 1.5 for v in LL.MEDIAN_SHRUB_AT):
            kind, scale = "fluffy_bush", 1.3
        elif LL.in_median(mx, my, 1.0) and any(abs(mx - v) < 1.5 for v in LL.MEDIAN_DARK_TREE_AT):
            kind, scale = "holm_oak_city_small", 0.95
        z = round(ground_z(x, y) - 0.05, 3)
        a = rng.uniform(0, 2 * math.pi)
        inst.setdefault(kind, []).append({"ctxid": 0, "pos": [x, y, z], "rotationMatrix": rot_list_from_yaw(a),
                                          "scale": scale, "type": kind})
    for mx, my in LL.MEDIAN_EXTRA_SHRUBS:
        x, y = geo.model2world(mx, my)
        inst.setdefault("generibush", []).append({"ctxid": 0, "pos": [round(x, 3), round(y, 3), round(ground_z(x, y) - 0.05, 3)],
                                                  "rotationMatrix": rot_list_from_yaw(rng.uniform(0, 2 * math.pi)), "scale": 0.7,
                                                  "type": "generibush"})
    # 2) boschi (dal terreno): specie in base alla vicinanza all'acqua e alla distanza
    osm = OSM()
    water = [osm.way_pts(w) for w, t in osm.ways_where(lambda t: "waterway" in t)]
    wpts = np.array([p for w in water for p in w]) if water else np.zeros((0, 2))
    from scipy.spatial import cKDTree
    wtree = cKDTree(wpts) if len(wpts) else None
    lim = 2030
    def se_side(X, Y):
        """oltre la ringhiera sud-est (Street View 2022: canneto alto per una decina di metri, poi gli alberi)."""
        mx, my = geo.world2model(np.asarray(X, float), np.asarray(Y, float))
        return (mx > LL.SW_X - 10) & (mx < LL.NE_X + 10) & (my < np.interp(mx, *zip(*LL.SE_CURB)) - LL.SE_WALK + 0.5)

    def forest_mask(X, Y):
        f = tsample(TFOREST.astype(np.float32), X, Y, 0) > 0.5
        f &= tsample(TDLOT, X, Y) > np.where(se_side(X, Y), 15.0, 7.0)
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
    # prima: un albero ogni ~45 m sparso uniforme (dall'alto sembrava a pois). Ora come nel paesaggio vero:
    # gruppetti di 2-8 alberi e filari/siepi lungo i confini dei campi, con varchi
    X, Y = poisson(meadow_mask, -1700, -1700, 1700, 1700, 150)
    for cx, cy in zip(X, Y):
        n = int(rng.integers(2, 9)); r = rng.uniform(4, 12)
        kinds = [["oak_dry_a", "oak_dry_b", "cork_oak_medium"], ["olive_tree"], ["tree_beech_large_c", "tree_aspen_small_a"],
                 ["oak_dry_c", "generibush", "scraggly_bush"]][int(rng.integers(0, 4))]
        px, py = cx + rng.normal(0, r, n), cy + rng.normal(0, r, n)
        ok = meadow_mask(px, py)
        for x, y in zip(px[ok], py[ok]):
            put(kinds[int(rng.integers(len(kinds)))], x, y)
    n_edge = 0
    for pts, t in osm.polygons_where(lambda t: t.get("landuse") in ("farmland", "meadow", "grass", "orchard", "vineyard", "farmyard")):
        P = np.asarray(pts)
        if np.hypot(*P.mean(0)) > 1700:
            continue
        seg = np.hypot(*np.diff(P, axis=0).T); Ls = np.concatenate([[0], np.cumsum(seg)])
        if Ls[-1] < 30:
            continue
        s_ = np.arange(rng.uniform(0, 7), Ls[-1], 7.0)
        ex, ey = np.interp(s_, Ls, P[:, 0]), np.interp(s_, Ls, P[:, 1])
        # varchi: il filare c'e' solo dove un rumore lento lungo il bordo lo permette
        keep = (np.sin(s_ / 37.0 + P[0, 0] * 0.01) + 0.6 * np.sin(s_ / 13.0 + P[0, 1] * 0.02)) > 0.1
        ex, ey = ex[keep] + rng.normal(0, 1.2, keep.sum()), ey[keep] + rng.normal(0, 1.2, keep.sum())
        ok = (tsample(TDROAD, ex, ey) > tsample(TRHW, ex, ey) + 3) & (tsample(TDLOT, ex, ey) > 12)
        for x, y, uu in zip(ex[ok], ey[ok], rng.random(ok.sum())):
            put(["generibush", "scraggly_bush", "oak_dry_c", "tree_beech_bush_a", "oak_dry_d", "tall_plant_bush", "tree_aspen_small_a"][int(uu * 7) % 7], x, y, 0.75, 1.25)
            n_edge += 1
    print("filari lungo i campi:", n_edge)
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
        se = se_side(X, Y)
        return (d > 2.0) & (d < np.where(se, 15.0, 11 + 4 * n)) & (dr > hw + 1.2) & (mx > -45) & ((n > -0.35) | se)
    X, Y = poisson(reed_mask, -250, -250, 250, 250, 1.6)
    for x, y in zip(X, Y):
        put("ti_reeds_clump", x, y, 0.8, 1.25, z_off=0.0)
    # nei varchi del canneto: siepe mista di arbusti (Street View 2022: il bordo nord-ovest e' soprattutto cespugli)
    def shrub_mask(X, Y):
        d = tsample(TDLOT, X, Y)
        dr = tsample(TDROAD, X, Y); hw = tsample(TRHW, X, Y)
        n = np.sin(X * 0.21) * np.cos(Y * 0.17) + np.sin(X * 0.05 + Y * 0.07)
        return (d > 2.5) & (d < 12) & (dr > hw + 1.5) & (n <= -0.35) & ~se_side(X, Y)
    X, Y = poisson(shrub_mask, -250, -250, 250, 250, 3.2)
    for x, y, uu in zip(X, Y, rng.random(len(X))):
        put(["tall_plant_bush", "generibush", "tree_beech_bush_a", "fluffy_bush", "holm_oak_bush"][int(uu * 5) % 5], x, y, 0.8, 1.3)
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
    # 5b) boschetto nella parte sud-ovest che non e' piazzale (ortofoto: alberi fitti tra il vialetto e il cantiere)
    from matplotlib.path import Path as _MP
    copse = _MP([geo.model2world(x, y) for x, y in [(-42, 38), (-42, -30), (-58, -43), (-86, -33), (-72, 8), (-60, 32)]])
    X, Y = poisson(lambda X, Y: copse.contains_points(np.stack([X, Y], 1)) & (tsample(TDLOT, X, Y) > 4) &
                   (tsample(TDROAD, X, Y) > tsample(TRHW, X, Y) + 2.5), -200, -200, 100, 100, 5.0)
    for x, y, uu in zip(X, Y, rng.random(len(X))):
        put(["oak_dry_a", "tree_beech_large_b", "tree_aspen_large_a", "cork_oak_medium", "generibush", "tree_beech_bush_a"][int(uu * 6) % 6], x, y)
    # 6) il grande salice piangente oltre il marciapiede nord-ovest (Street View 2022): libero lo spazio della chioma
    wx, wy = geo.model2world(*WILLOW_MODEL)
    for kind in list(inst):
        inst[kind] = [o for o in inst[kind] if math.hypot(o["pos"][0] - wx, o["pos"][1] - wy) > 8.5]
    inst["ti_willow"] = [{"ctxid": 0, "pos": [round(wx, 3), round(wy, 3), round(ground_z(wx, wy) - 0.05, 3)],
                          "rotationMatrix": [round(v, 6) for v in rot_list_from_yaw(math.radians(20))], "scale": 1.1, "type": "ti_willow"}]
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
    # crepe del piazzale: l'asfalto rovinato di Italy e' piu' chiaro del nostro, sul piazzale sembravano strisce pallide
    lc = json.loads(json.dumps(out["italy_road_cracks"]))
    lc.update(name="ti_lot_cracks", mapTo="ti_lot_cracks", persistentId=uid("mat/ti_lot_cracks"))
    lc["Stages"][0]["baseColorFactor"] = [0.5, 0.5, 0.49, 0.75]
    out["ti_lot_cracks"] = lc
    # velo d'asfalto della Rava con la tinta scura del piazzale (quello di Italy e' piu' chiaro e si vedeva lo stacco)
    ro = json.loads(json.dumps(out["italy_asphalt_overlay_light"]))
    ro.update(name="ti_rava_overlay", mapTo="ti_rava_overlay", persistentId=uid("mat/ti_rava_overlay"))
    ro["Stages"][0]["baseColorFactor"] = [0.9, 0.9, 0.88, 0.9]
    out["ti_rava_overlay"] = ro
    d = os.path.join(LV, "art", "road"); os.makedirs(d, exist_ok=True)
    json.dump(out, open(os.path.join(d, "main.materials.json"), "w"), indent=1)

    def offset_line(P, off):
        P = np.asarray(P)
        t = np.gradient(P[:, :2], axis=0); t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-9
        n = np.stack([-t[:, 1], t[:, 0]], 1)
        Q = P.copy(); Q[:, :2] += n * off
        return Q

    cnt = 0
    # viadotti (build_bridges.py): mesh percorribile + DecalRoad proiettati sull'impalcato
    bpath = os.path.join(BUILD, "bridges.json")
    decks = json.load(open(bpath)) if os.path.exists(bpath) else []
    if decks:
        L.add("roads", {"name": "viadotti", "class": "TSStatic", "position": [0, 0, 0], "shapeName": SHP("ti_bridges"),
                        "collisionType": "Visible Mesh Final", "decalType": "Visible Mesh", "useInstanceRenderData": True})
    for r in TINFO["roads"] + [dict(d, deck=True, surface="") for d in decks]:
        P = np.array(r["pts"])
        if len(P) < 2:
            continue
        dist = np.hypot(P[:, 0], P[:, 1]).min()
        if dist > 1500:
            continue
        deck = r.get("deck", False)
        P[:, 2] = (P[:, 2] if deck else tz(P[:, 0], P[:, 1])) + 0.02
        hw = r["hw"]
        unpaved = r["type"] == "track" or r["surface"] in ("unpaved", "gravel", "dirt", "ground")
        def road(mat, pts, width, **kw):
            nonlocal cnt
            nodes = [[round(float(a), 3), round(float(b), 3), round(float(c), 3), width] for a, b, c in pts]
            o = {"class": "DecalRoad", "position": nodes[0][:3], "material": mat, "nodes": nodes, "improvedSpline": True,
                 "breakAngle": 5, "decalBias": 0.0015, "distanceFade": [120, 50], "startEndFade": [1, 1], "drivability": -1}
            o.update(kw)
            if deck:
                o["overObjects"] = True
            L.add("roads", o); cnt += 1
        ai = dict(drivability=0.4 if r["type"] in ("track", "service") else 1.0, oneWay=r.get("oneway", False))
        if unpaved:
            road("m_dirt_road_gravels", P, hw * 2, renderPriority=6, textureLength=7, **ai)
            continue
        road("m_road_variation_01", P, hw * 2, renderPriority=25, textureLength=112, **ai)
        near = dist < 900                     # dettagli solo vicino al terminal (tempi di caricamento)
        if near:                                # la Rava continua l'asfalto del piazzale: velo scuro come il piazzale
            road("ti_rava_overlay" if r.get("name") == "Strada Comunale Rava" else "italy_asphalt_overlay_light",
                 P, hw * 2 - 0.4, renderPriority=20, textureLength=112)
        for s in ((-1, 1) if not deck else ()):
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


BLD_POLYS = []          # impronte (4 vertici, coordinate mondo) degli edifici piazzati
_BLD = {}


def bld_mask():
    """raster 1 m (+-1500 m) delle impronte degli edifici, allargate di 1 m."""
    if "m" not in _BLD:
        from PIL import Image, ImageDraw
        n, x0 = 3000, -1500.0
        im = Image.new("L", (n, n), 0); d = ImageDraw.Draw(im)
        for Pq in BLD_POLYS:
            d.polygon([(p[0] - x0, p[1] - x0) for p in Pq], fill=1)
        _BLD["m"] = ndimage.binary_dilation(np.asarray(im) > 0, iterations=1)
    return _BLD["m"]


def in_building(x, y):
    m = bld_mask()
    i = np.clip((np.atleast_1d(x) + 1500).astype(int), 0, 2999); j = np.clip((np.atleast_1d(y) + 1500).astype(int), 0, 2999)
    inside = (np.abs(np.atleast_1d(x)) < 1500) & (np.abs(np.atleast_1d(y)) < 1500)
    return m[j, i] & inside


def buildings(L):
    dims = json.load(open(os.path.join(BUILD, "bld_dims.json")))
    osm = OSM()
    ind_area = []
    for pts, t in osm.polygons_where(lambda t: t.get("landuse") in ("industrial", "construction")):
        ind_area.append(np.asarray(pts))
    from matplotlib.path import Path as MPath
    ind_paths = [MPath(p) for p in ind_area]
    used, placed = set(), 0
    skipped = {"sovrapposti": 0, "su_strada": 0}
    from matplotlib.path import Path as MPath2
    grid = {}                                            # hash spaziale 20 m delle impronte gia' piazzate

    def footprint_pts(cx, cy, yaw, Lseg, W, n=5):
        ca, sa = math.cos(yaw), math.sin(yaw)
        u = (np.linspace(0.1, 0.9, n) - 0.5)
        A, B = np.meshgrid(u * Lseg, u * W)
        return np.stack([cx + ca * A.ravel() - sa * B.ravel(), cy + sa * A.ravel() + ca * B.ravel()], 1)

    def place(shape, cx, cy, yaw, Lseg, W, zs=None, levels=None):
        nonlocal placed
        # niente edifici doppi (OSM ha a volte building + building:part) ne' sulla carreggiata
        pts = footprint_pts(cx, cy, yaw, Lseg, W)
        near = [q for k in {(int(cx // 20) + a, int(cy // 20) + b) for a in (-2, -1, 0, 1, 2) for b in (-2, -1, 0, 1, 2)} for q in grid.get(k, [])]
        if any(q.contains_points(pts).mean() > 0.25 for q in near):
            skipped["sovrapposti"] += 1
            return
        if np.mean(tsample(TDROAD, pts[:, 0], pts[:, 1]) < tsample(TRHW, pts[:, 0], pts[:, 1])) > 0.2:
            skipped["su_strada"] += 1
            return
        ca, sa = math.cos(yaw), math.sin(yaw)
        corners = [(cx + ca * hx - sa * hy, cy + sa * hx + ca * hy) for hx, hy in
                   ((-Lseg / 2, -W / 2), (Lseg / 2, -W / 2), (Lseg / 2, W / 2), (-Lseg / 2, W / 2))]
        BLD_POLYS.append(corners)
        grid.setdefault((int(cx // 20), int(cy // 20)), []).append(MPath2(corners))
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
        zmin = min(float(tz(cx + ca * hx - sa * hy, cy + sa * hx + ca * hy).min()), float(tz(pts[:, 0], pts[:, 1]).min()))
        zmax = float(tz(pts[:, 0], pts[:, 1]).max())
        # in pendio lo alzo finche' la fondazione del modello (sotto z) resta interrata a valle: meno sepolto a monte
        base = -mn[2] * sz
        z = min(zmax, zmin + max(0.0, base - 0.3)) - 0.1
        # stretto tra strade a quote diverse (le strade vincono sulla piazzola): se resta sepolto di oltre 2.5 m lo salto
        if zmax - z > 2.5:
            skipped["sepolti"] = skipped.get("sepolti", 0) + 1
            BLD_POLYS.pop(); grid[(int(cx // 20), int(cy // 20))].pop()
            return
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
        if t.get("amenity") == "car_wash":
            cx_, cy_ = float(ctr[0]), float(ctr[1])
            L.add("dintorni/edifici", {"name": "autolavaggio", "class": "TSStatic", "position": [round(cx_, 3), round(cy_, 3), round(float(tz(cx_, cy_)[0]) + 0.05, 3)],
                                        "rotationMatrix": [round(v, 6) for v in rot_list_from_yaw(yaw)],
                                        "shapeName": SHP("ti_carwash"), "collisionType": "Visible Mesh Final",
                                        "decalType": "Visible Mesh", "useInstanceRenderData": True})
            BLD_POLYS.append([(cx_ + math.cos(yaw) * hx - math.sin(yaw) * hy, cy_ + math.sin(yaw) * hx + math.cos(yaw) * hy)
                              for hx, hy in ((-Lb / 2, -Wb / 2), (Lb / 2, -Wb / 2), (Lb / 2, Wb / 2), (-Lb / 2, Wb / 2))])
            continue
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
    print("edifici:", placed, "modelli:", len(used), "materiali:", len(mats), "scartati:", skipped)


# ====================================================================== dettagli del piazzale: decal e sgommate
DECALS = ["repair_patch_decal", "pothole_decal", "eca_decals_concrete_damage_decal", "italy_ground_parts_decal",
          "nat_decals_fallen_leaves_01_decal", "ind_stuff_02"]


SKID_TEX = "/assets/materials/decalroad/treadmark/skidmark_car_single/skidmark_car_single_d.dds"


def skid_materials():
    out = {}
    for name, alpha in (("ti_skid_dark", 0.9), ("ti_skid_faded", 0.5)):
        out[name] = {"name": name, "mapTo": name, "class": "Material", "persistentId": uid("mat/" + name),
                     "Stages": [{"colorMap": SKID_TEX, "diffuseColor": [1, 1, 1, alpha], "useAnisotropic": True}, {}, {}, {}],
                     "alphaRef": 150, "annotation": "ASPHALT", "castShadows": False, "materialTag0": "RoadAndPath",
                     "materialTag1": "beamng", "translucent": True, "translucentZWrite": True}
    return out


def skids(L, R, asph):
    """sgommate come le lascia un'auto vera: tracce di singoli pneumatici (coppie a 1.55 m, larghe 22-26 cm),
    ciambelle col centro che deriva, archi di drift, un otto, partenze e frenate. Ogni traccia viene tagliata
    dove passa a meno di 0.6 m da cordoli, isole o marciapiedi (maschera dell'asfalto della mesh)."""
    clr = ndimage.distance_transform_edt(asph) * R.res                   # distanza dal bordo dell'asfalto (m)

    def clear_at(P):
        W = np.array([geo.model2world(x, y) for x, y in P])
        i = np.clip(((W[:, 0] - R.x0) / R.res).astype(int), 0, R.w - 1)
        j = np.clip(((W[:, 1] - R.y0) / R.res).astype(int), 0, R.h - 1)
        return clr[j, i], W

    def resample(P, step=0.5):
        P = np.asarray(P, float)
        d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])
        s = np.arange(0, d[-1], step)
        return np.stack([np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])], 1)

    def offset(P, off):
        t = np.gradient(P, axis=0); t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-9
        return P + np.stack([-t[:, 1], t[:, 0]], 1) * off

    n_out = [0]

    def emit(P, mat, w, fade=(1.5, 1.5)):
        c, W = clear_at(P)
        ok = c >= w / 2 + 0.6
        k = 0
        while k < len(P):
            if not ok[k]:
                k += 1
                continue
            e = k
            while e < len(P) and ok[e]:
                e += 1
            if (e - k) * 0.5 >= 3.0:
                seg = W[k:e][::2]
                if len(seg) >= 2:
                    L.add("piazzale/sgommate", {"class": "DecalRoad", "position": [round(float(seg[0][0]), 3), round(float(seg[0][1]), 3), 0.02],
                                                "material": mat, "nodes": [[round(float(x), 3), round(float(y), 3), 0.02, round(float(w), 3)] for x, y in seg],
                                                "overObjects": True, "improvedSpline": True, "renderPriority": 30, "textureLength": 20,
                                                "decalBias": 0.0015, "startEndFade": [float(fade[0]), float(fade[1])], "distanceFade": [120, 50],
                                                "drivability": -1})
                    n_out[0] += 1
            k = e

    def pair(C, mat, track=1.55, fade=(1.5, 1.5), jitter=0.03):
        for side in (-1, 1):
            P = offset(C, side * track / 2) + rng.normal(0, jitter, C.shape)
            emit(P, mat, rng.uniform(0.22, 0.26), fade)

    # centri possibili: punti dell'asfalto con almeno 6.5 m liberi attorno (una ciambella ci sta)
    ys, xs = np.nonzero(clr > 6.5)
    wx, wy = R.x0 + (xs + 0.5) * R.res, R.y0 + (ys + 0.5) * R.res
    cand = np.array([geo.world2model(x, y) for x, y in zip(wx[::7], wy[::7])])
    cand = cand[(cand[:, 0] > -95) & (cand[:, 0] < 88)]                  # non davanti all'edificio
    used = []

    def pick(min_sep=14.0, region=None):
        for _ in range(400):
            p = cand[rng.integers(len(cand))]
            if region is not None and not region(p):
                continue
            if all(np.hypot(*(p - q)) > min_sep for q in used):
                used.append(p)
                return p
        return None

    # ciambelle: 2-4 giri, raggio dell'asse posteriore 3-4.5 m, centro che scivola; anteriori piu' tenui
    for k in range(7):
        c = pick()
        if c is None:
            break
        rc = rng.uniform(3.0, 4.5); loops = rng.uniform(1.6, 3.8); dirn = rng.choice([-1, 1])
        th = np.linspace(0, 2 * math.pi * loops, int(90 * loops))
        drift = np.cumsum(rng.normal(0, 0.02, (len(th), 2)), 0)
        wob = 0.25 * np.sin(th * 0.7 + rng.uniform(0, 6))
        C = np.stack([c[0] + drift[:, 0] + (rc + wob) * np.cos(dirn * th), c[1] + drift[:, 1] + (rc + wob) * np.sin(dirn * th)], 1)
        pair(resample(C), "ti_skid_dark" if k % 3 else "ti_skid_faded", fade=(2.5, 1.0))
        if rng.random() < 0.6:
            rf = math.hypot(rc, 2.7)
            Cf = np.stack([c[0] + drift[:, 0] + (rf + wob) * np.cos(dirn * th + 0.6),
                           c[1] + drift[:, 1] + (rf + wob) * np.sin(dirn * th + 0.6)], 1)
            pair(resample(Cf), "ti_skid_faded", track=1.5, fade=(3, 3))

    # archi di drift: raggio che si stringe e si riapre (entrata/uscita), 70-170 gradi
    for k in range(9):
        c = pick(10.0)
        if c is None:
            break
        r0 = rng.uniform(9, 20); span = math.radians(rng.uniform(70, 170)); a0 = rng.uniform(0, 2 * math.pi)
        dirn = rng.choice([-1, 1]); t = np.linspace(0, 1, 160)
        rr = r0 * (1 + 0.35 * (2 * t - 1) ** 2)
        ang = a0 + dirn * span * t
        C = np.stack([c[0] - r0 * math.cos(a0) + rr * np.cos(ang), c[1] - r0 * math.sin(a0) + rr * np.sin(ang)], 1)
        pair(resample(C), "ti_skid_dark" if k % 2 else "ti_skid_faded", fade=(4, 3))

    # un otto nella parte libera a sud-ovest
    c = pick(16.0, region=lambda p: p[0] < -50)
    if c is not None:
        a = rng.uniform(12, 15); t = np.linspace(0, 2 * math.pi * 1.8, 700); rot = rng.uniform(0, math.pi)
        x = a * np.cos(t) / (1 + np.sin(t) ** 2); y = a * np.sin(t) * np.cos(t) / (1 + np.sin(t) ** 2)
        C = np.stack([c[0] + x * math.cos(rot) - y * math.sin(rot), c[1] + x * math.sin(rot) + y * math.cos(rot)], 1)
        pair(resample(C), "ti_skid_dark", fade=(3, 3))

    # partenze (scure all'inizio, poi svaniscono) e frenate (tenui), lungo l'asse del piazzale
    for k in range(10):
        c = pick(8.0)
        if c is None:
            break
        ang = math.radians(rng.choice([0, 180]) + rng.normal(0, 12))
        Ls = rng.uniform(6, 18); t = np.linspace(0, Ls, int(Ls * 2) + 1)
        wig = 0.12 * np.sin(t * rng.uniform(0.6, 1.2) + rng.uniform(0, 6))
        C = np.stack([c[0] + t * math.cos(ang) - wig * math.sin(ang), c[1] + t * math.sin(ang) + wig * math.cos(ang)], 1)
        if k % 2:
            pair(C, "ti_skid_dark", fade=(0.3, Ls * 0.6))
        else:
            pair(C, "ti_skid_faded", fade=(Ls * 0.3, 0.8))
    print("sgommate:", n_out[0], "tracce")


def lot_details(L, meta):
    # definizioni decal + materiali da Italy
    md = json.loads(va.read("/levels/italy/art/decals/managedDecalData.json"))
    dm = json.loads(va.read("/levels/italy/art/decals/main.materials.json"))
    out_md = {k: md[k] for k in DECALS}
    need = {md[k]["material"] for k in DECALS}
    out_m = {k: v for k, v in dm.items() if v.get("mapTo", k) in need or k in need}
    d = os.path.join(LV, "art", "decals"); os.makedirs(d, exist_ok=True)
    json.dump(out_md, open(os.path.join(d, "managedDecalData.json"), "w"), indent=1)
    out_m.update(skid_materials())
    # i rappezzi di Italy sono cemento chiaro: sul nostro asfalto sembravano macchie bianche -> piu' scuri
    for k, v in out_m.items():
        if k == "m_asphalt_repair_patch_decal":
            v["Stages"][0]["baseColorFactor"] = [0.8, 0.8, 0.79, 1]     # sull'asfalto chiaro (Street View) toppe appena piu' scure
    json.dump(out_m, open(os.path.join(d, "main.materials.json"), "w"), indent=1)
    # maschera dell'asfalto dalla mesh
    from build_terrain import dae_triangles, Raster
    R = Raster(-200, -200, 400, 400, 0.5)
    G = list(dae_triangles(os.path.join(BUILD, "shapes", "ti_ground.dae")))
    asph = R.polys([[tuple(p[:2]) for p in tri] for mat, tri in G if mat == "ti_asphalt"], 1) > 0
    # l'asfalto della mesh continua sotto isole e marciapiedi (rialzati di 10 cm): li tolgo dalla maschera
    other = R.polys([[tuple(p[:2]) for p in tri] for mat, tri in G if mat != "ti_asphalt"], 1) > 0
    other |= R.polys([[geo.model2world(cx + sx * KL / 2, cy + sy * KW / 2) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                      for (cx, cy), KL, KW, _ in LL.KIOSKS], 1) > 0          # casotti sull'asfalto
    asph &= ~ndimage.binary_dilation(other, iterations=1)
    asph_full = asph.copy()
    asph = ndimage.binary_erosion(asph, iterations=6)          # almeno 3 m dai cordoli
    ys, xs = np.nonzero(asph)

    clr_all = ndimage.distance_transform_edt(asph_full) * R.res      # distanza dal primo cordolo/isola/marciapiede

    def rnd_pts(n, need=0.0):
        """n punti sull'asfalto con almeno 'need' m liberi attorno (i decal si proiettano su tutto: niente sbordi)."""
        ok = np.nonzero((clr_all > need).ravel())[0]
        i = ok[rng.integers(0, len(ok), n)]
        yy, xx = np.unravel_index(i, clr_all.shape)
        return R.x0 + (xx + 0.5) * R.res, R.y0 + (yy + 0.5) * R.res

    inst = {}
    def dec(name, x, y, size, rect=0, z=0.0):
        a = rng.uniform(0, 2 * math.pi)
        inst.setdefault(name, []).append([int(rect), round(float(size), 3), 0, round(float(x), 3), round(float(y), 3), z, 0, 0, 1,
                                          round(math.cos(a), 5), round(math.sin(a), 5), 0, int(rng.integers(1, 2 ** 31))])
    for x, y in zip(*rnd_pts(25, 3.2)):
        dec("repair_patch_decal", x, y, rng.uniform(2.2, 5.5), rng.integers(0, 4))
    for x, y in zip(*rnd_pts(14, 1.2)):
        dec("pothole_decal", x, y, rng.uniform(0.7, 1.5), rng.integers(0, 4))
    for x, y in zip(*rnd_pts(6, 3.5)):
        dec("eca_decals_concrete_damage_decal", x, y, rng.uniform(3, 6))
    for x, y in zip(*rnd_pts(10, 1.6)):
        dec("ind_stuff_02", x, y, rng.uniform(1.0, 2.5))                # macchie d'olio sparse
    # macchie d'olio dove si fermano i bus: corsia lungo il lato strada della fascia centrale (fermata con pensilina)
    for mx in np.arange(-14, 72, 4.5):
        if rng.random() < 0.35:
            continue
        x, y = geo.model2world(mx + rng.normal(0, 0.8), LL.median_y(mx) - LL.MED_HALF - 2.4 + rng.normal(0, 0.4))
        i, j = int((x - R.x0) / R.res), int((y - R.y0) / R.res)
        if asph_full[j, i]:
            dec("ind_stuff_02", x, y, rng.uniform(1.2, 2.4))
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
        """crepa come DecalRoad, spezzata dove passerebbe su isole, cordoli o marciapiedi."""
        P = np.asarray(P, float)
        dd = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])
        s_ = np.arange(0, dd[-1], 0.5)
        Q = np.stack([np.interp(s_, dd, P[:, 0]), np.interp(s_, dd, P[:, 1])], 1)
        ii = np.clip(((Q[:, 0] - R.x0) / R.res).astype(int), 0, R.w - 1); jj = np.clip(((Q[:, 1] - R.y0) / R.res).astype(int), 0, R.h - 1)
        ok = clr_all[jj, ii] >= w / 2 + 0.3
        k = 0
        while k < len(Q):
            if not ok[k]:
                k += 1; continue
            e = k
            while e < len(Q) and ok[e]:
                e += 1
            seg = Q[k:e][::6]
            if (e - k) * 0.5 >= 3.0 and len(seg) >= 2:
                L.add("piazzale/crepe", {"class": "DecalRoad", "position": [float(seg[0][0]), float(seg[0][1]), 0.01], "material": "ti_lot_cracks",
                                         "nodes": [[round(float(p[0]), 3), round(float(p[1]), 3), 0.01, w] for p in seg], "overObjects": True,
                                         "improvedSpline": True, "renderPriority": 26, "textureLength": 16, "decalBias": 0.0015,
                                         "startEndFade": [2, 2], "distanceFade": [90, 40], "drivability": -1})
            k = e
    seam = [geo.model2world(mx, 1.5 + 0.6 * math.sin(mx / 9.0)) for mx in np.arange(-36, 112, 2)]
    crack(seam, 1.6)
    for k in range(26):
        x, y = rnd_pts(1, 1.0); x, y = float(x[0]), float(y[0])
        a = rng.uniform(0, math.pi); Lc = rng.uniform(8, 26)
        P = [[x + math.cos(a) * t + rng.normal(0, 0.4), y + math.sin(a) * t + rng.normal(0, 0.4)] for t in np.linspace(0, Lc, 5)]
        crack(P, rng.uniform(0.9, 1.6))
    # sgommate: vedi skids()
    skids(L, R, asph_full)
    # stalli dei bus nell'isola a "E" (Street View 2024): righe gialle sbiadite in diagonale
    n_st = 0
    for xa, xb in LL.E_BAYS:
        for xs in np.arange(xa + 0.6, xb - 1.5, 2.7):
            a, b = geo.model2world(xs, LL.E_BAY_Y[1] + 0.3), geo.model2world(xs + 2.2, LL.E_BAY_Y[0] - 0.3)
            L.add("piazzale/segnaletica", {"class": "DecalRoad", "position": [a[0], a[1], 0.01],
                                           "material": "italy_road_markings_line_thin_yellow",
                                           "nodes": [[a[0], a[1], 0.01, 0.12], [b[0], b[1], 0.01, 0.12]], "overObjects": True,
                                           "renderPriority": 23, "textureLength": 4, "decalBias": 0.0015, "distanceFade": [60, 30],
                                           "startEndFade": [0.4, 0.4], "drivability": -1})
            n_st += 1
    json.dump({"header": {"name": "DecalData File", "comments": "// Instances format: rectIdx, size, renderPriority, position.x, position.y, "
                          "position.z, normal.x, normal.y, normal.z, tangent.x, tangent.y, tangent.z, uid", "version": 2},
               "instances": inst}, open(os.path.join(LV, "main.decals.json"), "w"), indent=1)
    print("stalli della E:", n_st)
    print("decal:", {k: len(v) for k, v in inst.items()})


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
            if in_building(px - 0.6 * n[0], py - 0.6 * n[1])[0] or in_building(px, py)[0]:
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
    # fermata e cestino accanto a ogni pensilina, solo su marciapiede/isola (mai sull'asfalto)
    from build_terrain import dae_triangles
    from scipy.spatial import cKDTree
    pv = cKDTree([geo.world2model(q[0], q[1]) for m, tri in dae_triangles(os.path.join(BUILD, "shapes", "ti_props.dae")) for q in tri])
    seen = []
    for x, y, z in meta["benches"]:
        mx, my = geo.world2model(x, y)
        if any(math.hypot(mx - a, my - b) < 3 for a, b in seen):
            continue
        seen.append((mx, my))
        spots = [(dx, dy) for d in (2.3, 2.8, 3.3) for dx, dy in ((d, 0), (-d, 0), (0, d * 0.5), (0, -d * 0.5))]
        free = [(mx + dx, my + dy) for dx, dy in spots
                if all(ground_z(*geo.model2world(mx + dx + ex, my + dy + ey)) > 0.08 for ex in (-0.4, 0, 0.4) for ey in (-0.4, 0, 0.4))
                and pv.query((mx + dx, my + dy))[0] > 0.6]                   # non dentro la pensilina o la panchina
        if free:
            px, py = geo.model2world(*free[0])
            L.add("terminal/arredo", {"class": "TSStatic", "position": [round(px, 3), round(py, 3), round(ground_z(px, py), 3)],
                                      "shapeName": "/art/shapes/objects/s_sign_busstop.dae",
                                      "rotationMatrix": rot_list_from_yaw(math.radians(geo.MODEL_ROT_DEG)), "annotation": "TRAFFIC_SIGNS"})
        far = [q for q in free[1:] if math.hypot(q[0] - free[0][0], q[1] - free[0][1]) > 3.5]
        if far:
            px, py = geo.model2world(*far[0])
            L.add("terminal/arredo", {"class": "TSStatic", "position": [round(px, 3), round(py, 3), round(ground_z(px, py), 3)],
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
        if not tilt:
            z = ground_z(float(p[0]), float(p[1]))
        L.add("terminal/abbandono", {"class": "TSStatic", "position": [round(float(p[0]), 3), round(float(p[1]), 3), round(z, 3)],
                                     "rotationMatrix": [round(v, 6) for v in rot], "scale": [scale] * 3, "shapeName": B + shape + ".dae",
                                     "collisionType": "Collision Mesh", "useInstanceRenderData": True})
        return shape
    used = [put("italy_clutter_plastic_chair_a", -0.3, 1.1, 20, z=0.35, tilt=True),
            put("italy_clutter_trashbag", 0.9, 0.6, 40), put("italy_clutter_trashbag", 1.4, 0.9, 110),
            put("italy_clutter_trashbag", -1.6, 0.5, 200), put("italy_clutter_concbag_pile", 3.5, 0.9, 15),
            put("italy_clutter_pallet", -3.2, 0.35, 80, z=0.1), put("italy_clutter_metal_drum", 5.0, 1.2, 0)]
    # idranti sui marciapiedi (Street View 2022), mai sull'asfalto
    for (mx, my, yaw) in [(58.0, LL.se_rail_y(58.0) + 0.4, 0), (25.0, LL.nw_curb_y(25.0) + 0.15 + LL.NW_WALK - 0.45, 180),
                          (LL.SW_X - LL.SW_WALK + 0.4, -22.0, 90), (LL.E_POST[0], LL.E_POST[1], 0)]:   # + paletto rosso della "E"
        x, y = geo.model2world(mx, my)
        shp = "italy_clutter_fire_hydrant.DAE"
        L.add("terminal/arredo", {"class": "TSStatic", "position": [round(x, 3), round(y, 3), round(ground_z(x, y), 3)],
                                  "rotationMatrix": rot_list_from_yaw(math.radians(yaw + geo.MODEL_ROT_DEG)), "shapeName": B + shp,
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
                            "fogAtmosphereHeight": 320, "fogColor": [0.64, 0.78, 0.94, 1], "fogDensity": 0.00009,
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
                            "useNightCubemap": True,
                            # cielo notturno: stelle e luna come in Italy (senza starVisibility la notte era nera)
                            "starVisibility": 1, "starLatitude": round(math.radians(geo.LAT0), 5), "meteorRate": 0.1,
                            "moonEnabled": True, "moonAngularSize": 0.67, "moonLightColor": [0.75, 0.8, 1, 1]})
    L.add("Level_objects", {"name": "clouds1", "class": "CloudLayer", "position": [0, 0, 0], "Textures": [{}, {}, {}], "coverage": 0.95,
                            "exposure": 1.35, "height": 8, "texture": "levels/italy/art/skies/SkyNormals_05.dds", "windSpeed": 0.12})
    L.add("Level_objects", {"class": "ForestWindEmitter", "position": [0, 0, 0], "strength": 0.6, "windDirection": [0.7, 0.3, 0]})
    L.add("Level_objects", {"name": "theForest", "class": "Forest", "lodReflectScalar": 0})
    mi = TINFO["main"]
    L.add("terrain", {"name": "theTerrain", "class": "TerrainBlock", "position": mi["position"], "maxHeight": mi["maxHeight"],
                      "squareSize": mi["squareSize"], "baseTexSize": 4096, "materialTextureSet": "ti_TerrainMaterialTextureSet",
                      "terrainFile": LVP + "terrain_main.ter", "minimapImage": LVP + "terminal_isernia_minimap.png"})
    L.add("terrain", {"name": "sfondo_colline", "class": "TSStatic", "position": [0, 0, 0], "collisionType": "None",
                      "shapeName": SHP("ti_backdrop"), "useInstanceRenderData": True})


def free_parking(p):
    """le isole ora sono al posto vero (6 m piu' a sud-est): un'auto che ci finirebbe sopra scivola sull'asfalto libero."""
    mx, my = geo.world2model(p[0], p[1])
    def clear(x, y):
        return all(ground_z(*geo.model2world(x + ex, y + ey)) < 0.03 for ex in np.arange(-8.5, 8.6, 1.0) for ey in (-1.5, 0, 1.5))
    if clear(mx, my):
        return p
    for dy in np.arange(0.5, 12, 0.5):
        for sgn in (-1, 1):
            if clear(mx, my + sgn * dy):
                x, y = geo.model2world(mx, my + sgn * dy)
                print(f"veicolo spostato da ({mx:.1f}, {my:.1f}) a ({mx:.1f}, {my + sgn * dy:.1f})")
                return [x, y, p[2]]
    return p


def spawns_and_vehicles(L):
    old = os.path.join(ORIG, "main", "MissionGroup")
    for grp in ("SimGroup_n",):
        for l in open(os.path.join(old, grp, "items.level.json"), encoding="utf8"):
            d = json.loads(l)
            d["position"] = old_to_world(d["position"])
            d["position"] = free_parking(d["position"])
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
    for name, (mx, my, yaw) in {"spawn_edificio": (80, -40, 0), "spawn_ingresso": (-24, 12, -20)}.items():
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
    bookmark("vista_piazzale", (-32, -36, 4), (60, 5, 0))
    bookmark("aereo", (-120, -150, 90), (40, 0, 0))
    bookmark("pensilina", (54, -25, 1.7), (62.4, -17.6, 1.2))
    bookmark("fermata_centrale", (2, -41, 1.7), (8.1, -33.1, 1.3))
    bookmark("salice", (22, 0, 1.6), (LL.WILLOW[0], LL.WILLOW[1], 5.0))
    bookmark("ingresso", (-60, -44, 2.5), (0, -20, 1))


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
    from build_textures import save_atomic
    save_atomic(b, os.path.join(LV, "terminal_isernia_minimap.png"), optimize=True)


def main():
    L = Level()
    publish_shapes()
    environment(L)
    meta = place_terminal(L)
    write_forest_defs()
    buildings(L)                 # prima della vegetazione: alberi e lampioni evitano le impronte degli edifici
    make_forest(meta)
    groundcover(L)
    roads(L)
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
