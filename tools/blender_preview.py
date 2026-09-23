"""Anteprima di controllo in Blender dei .dae esportati, con i materiali PBR della mod (approssimati).

blender -b --factory-startup --python tools/blender_preview.py -- <cartella_output_png>
Serve solo come QA (scale UV, allineamenti, texture giuste sulle facce giuste) prima di provare in gioco.
"""
import bpy, os, sys, math
import xml.etree.ElementTree as ET
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHAPES = os.path.join(ROOT, "build", "shapes")
TEX = os.path.join(ROOT, "mod", "levels", "terminal_isernia", "art", "textures")
OUT = sys.argv[sys.argv.index("--") + 1]
NS = "{http://www.collada.org/2005/11/COLLADASchema}"

TEXSET = {"ti_asphalt": "t_ti_asphalt", "ti_pavers_moss": "t_ti_pavers_moss", "ti_pavers": "t_ti_pavers", "ti_curb": "t_ti_curb",
          "ti_bld_facade_arches": "t_ti_bld_arches", "ti_bld_plaster": "t_ti_plaster_yellow", "ti_bld_wall_left": "t_ti_bld_left",
          "ti_bld_wall_front": "t_ti_bld_front", "ti_bld_graffiti": "t_ti_bld_graffiti", "ti_bld_roof": "t_ti_roof"}
FLAT = {"ti_planter_soil": (0.18, 0.13, 0.09, 0.95, 0), "ti_railing": (0.6, 0.6, 0.62, 0.45, 1), "ti_lamp_pole": (0.55, 0.56, 0.58, 0.4, 1),
        "ti_lamp_head": (0.9, 0.9, 0.85, 0.2, 0), "ti_bench": (0.05, 0.16, 0.11, 0.5, 0), "ti_shelter": (0.04, 0.18, 0.13, 0.5, 0),
        "ti_bld_frame": (0.62, 0.62, 0.60, 0.8, 0), "ti_canopy_steel": (0.06, 0.20, 0.12, 0.5, 0.3),
        "ti_canopy_panel": (0.8, 0.82, 0.78, 0.3, 0), "ti_lamp_black": (0.02, 0.02, 0.02, 0.4, 0.5), "ti_lamp_globe": (0.95, 0.95, 0.9, 0.2, 0)}


def make_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    if name in TEXSET:
        t = os.path.join(TEX, TEXSET[name])
        def img(suffix, noncolor):
            n = nt.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(t + suffix)
            if noncolor: n.image.colorspace_settings.name = "Non-Color"
            return n
        nt.links.new(img("_b.color.png", False).outputs[0], b.inputs["Base Color"])
        nt.links.new(img("_r.data.png", True).outputs[0], b.inputs["Roughness"])
        nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(img("_nm.normal.png", True).outputs[0], nm.inputs["Color"])
        nt.links.new(nm.outputs[0], b.inputs["Normal"])
    else:
        r, g, bb, rough, metal = FLAT.get(name, (0.5, 0.5, 0.5, 0.8, 0))
        b.inputs["Base Color"].default_value = (r, g, bb, 1); b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
    return m


def load_dae(path, loc=(0, 0, 0), rot=None):
    root = ET.parse(path).getroot()
    mats = {}
    for g in root.iter(NS + "geometry"):
        src = {}
        for s in g.iter(NS + "source"):
            a = list(map(float, s.find(NS + "float_array").text.split()))
            src[s.get("id").split("-")[-1]] = a
        verts, faces, uv0, fmat = [], [], [], []
        me = bpy.data.meshes.new(g.get("name"))
        matlist = []
        for t in g.iter(NS + "triangles"):
            mn = t.get("material").replace("-material", "")
            if mn not in mats:
                mats[mn] = make_mat(mn)
            if mn not in matlist:
                matlist.append(mn)
            idx = list(map(int, t.find(NS + "p").text.split()))
            for k in range(0, len(idx), 3):
                tri = idx[k:k + 3]
                base = len(verts)
                for i in tri:
                    verts.append(tuple(src["pos"][3 * i:3 * i + 3])); uv0.append(tuple(src["uv0"][2 * i:2 * i + 2]))
                faces.append((base, base + 1, base + 2)); fmat.append(matlist.index(mn))
        me.from_pydata(verts, [], faces)
        for mn in matlist:
            me.materials.append(mats[mn])
        uvl = me.uv_layers.new(name="UV0")
        for poly in me.polygons:
            poly.material_index = fmat[poly.index]
            for li in poly.loop_indices:
                uvl.data[li].uv = uv0[me.loops[li].vertex_index]
        me.update()
        ob = bpy.data.objects.new(g.get("name"), me)
        ob.location = loc
        if rot is not None:
            ob.matrix_world = rot
        bpy.context.scene.collection.objects.link(ob)
        bpy.ops.object.select_all(action="DESELECT")
    return mats


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 1600, 900
for f in ("ti_ground", "ti_building", "ti_railing", "ti_props", "ti_canopy"):
    load_dae(os.path.join(SHAPES, f + ".dae"))
# lampioni (istanze)
import json
meta = json.load(open(os.path.join(ROOT, "build", "export_meta.json")))
from mathutils import Matrix
for lp in meta["lamps"]:
    R = Matrix(lp["rot"]).to_4x4(); R.translation = Vector(lp["pos"])
    load_dae(os.path.join(SHAPES, "ti_lamp.dae"), rot=R)
# sole pomeridiano d'ottobre (az ~235 deg, el ~25 deg) + cielo
sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 4.5; sun.angle = math.radians(0.6)
so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so)
az, el = math.radians(235), math.radians(25)
d = Vector((math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)))
so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.65, 0.85, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
cam = bpy.data.cameras.new("cam"); co = bpy.data.objects.new("cam", cam); sc.collection.objects.link(co); sc.camera = co
views = {"pensilina_se": ((78, -40, 1.8), (98, -16, 3.5), 24), "pensilina_ne": ((116, -30, 1.8), (98, -8, 4.0), 24), "facciata": ((99, -34, 1.7), (99, -8, 2.2), 28), "piazzale": ((-40, -35, 4), (60, 5, 0), 24),
         "pensilina": ((55, -24, 1.7), (62.6, -13.8, 1.2), 24), "asfalto_vicino": ((20, -20, 1.4), (26, -14, 0), 35),
         "aereo": ((-60, -110, 60), (40, 0, 0), 30)}
for name, (c, t, lens) in views.items():
    cw = Vector((*geo.model2world(c[0], c[1]), c[2])); tw = Vector((*geo.model2world(t[0], t[1]), t[2]))
    co.location = cw; co.rotation_euler = (tw - cw).to_track_quat("-Z", "Y").to_euler(); cam.lens = lens
    sc.render.filepath = os.path.join(OUT, f"prev_{name}.png")
    bpy.ops.render.render(write_still=True)
print("PREVIEW_OK")
