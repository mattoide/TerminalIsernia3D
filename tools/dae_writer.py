"""Scrittura Collada minimale per BeamNG (Blender 5.x non ha piu' l'esportatore .dae).
Da usare dentro Blender (richiede mathutils)."""
from mathutils import Matrix, Vector


class MeshData:
    """triangoli per materiale, con posizioni/normali/uv0/uv1 per-vertice (gia' spezzati per angolo)."""
    def __init__(self, name):
        self.name = name
        self.by_mat = {}          # mat -> list of (pos, nrm, uv0, uv1) * 3

    def add_tri(self, mat, corners):
        self.by_mat.setdefault(mat, []).append(corners)

    def tri_count(self):
        return sum(len(v) for v in self.by_mat.values())


# ---------------------------------------------------------------- scrittura Collada
def fmt(vals):
    return " ".join("%.5g" % v for v in vals)


def write_dae(path, meshes, to_world):
    """meshes: lista di MeshData (spazio modello). to_world: Matrix applicata alle posizioni."""
    R3 = to_world.to_3x3()
    geoms, nodes, mats = [], [], set()
    for mi, md in enumerate(meshes):
        if md.tri_count() == 0:
            continue
        gid = f"g{mi}"
        P, N, U0, U1, prims = [], [], [], [], []
        idx = 0
        weld = {}                                   # vertici identici condivisi tra triangoli
        for mat, tris in sorted(md.by_mat.items()):
            mats.add(mat)
            ind = []
            for tri in tris:
                for (p, n, uv0, uv1) in tri:
                    wp = to_world @ p
                    wn = (R3 @ n).normalized()
                    key = (round(wp.x, 4), round(wp.y, 4), round(wp.z, 4), round(wn.x, 3), round(wn.y, 3), round(wn.z, 3),
                           round(uv0[0], 4), round(uv0[1], 4), round(uv1[0], 5), round(uv1[1], 5))
                    vi = weld.get(key)
                    if vi is None:
                        vi = weld[key] = idx; idx += 1
                        P += (wp.x, wp.y, wp.z); N += (wn.x, wn.y, wn.z)
                        U0 += (uv0[0], uv0[1]); U1 += (uv1[0], uv1[1])
                    ind.append(vi)
            prims.append((mat, len(tris), ind))
        cnt = idx
        src = lambda nm, arr, stride, params: (
            f'<source id="{gid}-{nm}"><float_array id="{gid}-{nm}-a" count="{len(arr)}">{fmt(arr)}</float_array>'
            f'<technique_common><accessor source="#{gid}-{nm}-a" count="{len(arr)//stride}" stride="{stride}">'
            + "".join(f'<param name="{p}" type="float"/>' for p in params) + '</accessor></technique_common></source>')
        g = [f'<geometry id="{gid}" name="{md.name}"><mesh>',
             src("pos", P, 3, "XYZ"), src("nrm", N, 3, "XYZ"), src("uv0", U0, 2, "ST"), src("uv1", U1, 2, "ST"),
             f'<vertices id="{gid}-v"><input semantic="POSITION" source="#{gid}-pos"/></vertices>']
        for mat, ntri, ind in prims:
            g.append(f'<triangles material="{mat}-material" count="{ntri}">'
                     f'<input semantic="VERTEX" source="#{gid}-v" offset="0"/>'
                     f'<input semantic="NORMAL" source="#{gid}-nrm" offset="0"/>'
                     f'<input semantic="TEXCOORD" source="#{gid}-uv0" offset="0" set="0"/>'
                     f'<input semantic="TEXCOORD" source="#{gid}-uv1" offset="0" set="1"/>'
                     f'<p>{" ".join(map(str, ind))}</p></triangles>')
        g.append('</mesh></geometry>')
        geoms.append("".join(g))
        binds = "".join(f'<instance_material symbol="{m}-material" target="#{m}-material"/>' for m, _, _ in prims)
        nodes.append(f'<node id="{md.name}_a2" name="{md.name}_a2" type="NODE">'
                     f'<matrix sid="transform">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</matrix>'
                     f'<instance_geometry url="#{gid}" name="{md.name}_a2"><bind_material><technique_common>{binds}'
                     f'</technique_common></bind_material></instance_geometry></node>')
    ident = '<matrix sid="transform">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</matrix>'
    effects = "".join(f'<effect id="{m}-effect"><profile_COMMON><technique sid="common"><lambert><diffuse>'
                      f'<color sid="diffuse">0.8 0.8 0.8 1</color></diffuse></lambert></technique></profile_COMMON></effect>'
                      for m in sorted(mats))
    materials = "".join(f'<material id="{m}-material" name="{m}"><instance_effect url="#{m}-effect"/></material>'
                        for m in sorted(mats))
    doc = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">'
           '<asset><contributor><authoring_tool>TerminalIsernia blender_export.py</authoring_tool></contributor>'
           '<unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>'
           f'<library_effects>{effects}</library_effects><library_materials>{materials}</library_materials>'
           f'<library_geometries>{"".join(geoms)}</library_geometries>'
           '<library_visual_scenes><visual_scene id="Scene" name="Scene">'
           f'<node id="base00" name="base00" type="NODE">{ident}'
           f'<node id="start01" name="start01" type="NODE">{ident}{"".join(nodes)}</node>'
           f'<node id="detail2" name="detail2" type="NODE">{ident}</node>'
           '</node></visual_scene></library_visual_scenes>'
           '<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>')
    open(path, "w", encoding="utf8").write(doc)
    return sum(m.tri_count() for m in meshes), sorted(mats)


