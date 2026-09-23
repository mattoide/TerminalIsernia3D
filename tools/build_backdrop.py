"""Sfondo lontano (colline e montagne fino a ~16 km) come mesh .dae invece di un secondo TerrainBlock.

Un secondo terreno da 33 km veniva disegnato a blocchi con colori sbagliati; una mesh e' piu' prevedibile
ed e' la soluzione usata anche dalle mappe ufficiali (backdrop). Quote = stesso campo ZF di build_terrain.py
(salvato in build/terrain_masks.npz), quindi combacia con gli alberi lontani gia' posizionati.

  zona vicina  : passo 64 m fino a 6.5 km, con un buco al centro (sotto c'e' il terreno principale)
  zona lontana : passo 192 m fino a 16 km
"""
import os, json
import numpy as np
from scipy import ndimage

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(BUILD, "shapes", "ti_backdrop.dae")

M = np.load(os.path.join(BUILD, "terrain_masks.npz"))
ZF, XF0, SQF = M["zf"].astype(np.float64), float(M["xf0"]), float(M["sqf"])
EXT = -XF0                                          # meta' lato del campo ZF (16384 m)


def zf(x, y):
    return ndimage.map_coordinates(ZF, [(y - XF0) / SQF, (x - XF0) / SQF], order=3, mode="nearest")


def grid(lo, hi, step, hole=None, lower_inside=None, lower_ring=None):
    xs = np.arange(-hi, hi + 1e-6, step)
    X, Y = np.meshgrid(xs, xs)
    Z = zf(X.ravel(), Y.ravel()).reshape(X.shape)
    cheb = np.maximum(np.abs(X), np.abs(Y))
    if lower_inside:
        Z = np.where(cheb < lower_inside, Z - 25.0, Z)
    if lower_ring:                                 # fascia sovrapposta alla zona vicina: sotto di qualche metro
        Z = np.where(cheb < lower_ring[0] - 1, Z - lower_ring[1], Z)
    n = len(xs)
    quads = []
    for j in range(n - 1):
        for i in range(n - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (xs[j] + xs[j + 1]) / 2
            c = max(abs(cx), abs(cy))
            if c - step / 2 < lo - 1e-6 or (hole and c + step / 2 <= hole):
                continue
            quads.append((j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i))
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    gy, gx = np.gradient(Z, step)
    N = np.stack([-gx.ravel(), -gy.ravel(), np.ones(Z.size)], 1)
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    UV = np.stack([(P[:, 0] + EXT) / (2 * EXT), (P[:, 1] + EXT) / (2 * EXT)], 1)
    UV1 = P[:, :2] / 64.0                          # dettaglio ripetuto ogni 64 m
    tris = [t for q in quads for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))]
    return P, N, UV, UV1, np.array(tris, np.int64)


def fmt(a):
    return " ".join("%.4f" % v for v in np.asarray(a).ravel())


def write(meshes):
    geoms, nodes = [], []
    for gi, (name, (P, N, UV, UV1, T)) in enumerate(meshes):
        # compatto: solo i vertici usati
        used = np.unique(T); remap = -np.ones(len(P), np.int64); remap[used] = np.arange(len(used))
        P, N, UV, UV1, T = P[used], N[used], UV[used], UV1[used], remap[T]
        g = f"g{gi}"
        src = lambda nm, arr, st, prm: (f'<source id="{g}-{nm}"><float_array id="{g}-{nm}-a" count="{arr.size}">{fmt(arr)}</float_array>'
                                        f'<technique_common><accessor source="#{g}-{nm}-a" count="{len(arr)}" stride="{st}">'
                                        + "".join(f'<param name="{p}" type="float"/>' for p in prm) + '</accessor></technique_common></source>')
        geoms.append(f'<geometry id="{g}" name="{name}"><mesh>' + src("pos", P, 3, "XYZ") + src("nrm", N, 3, "XYZ") +
                     src("uv0", UV, 2, "ST") + src("uv1", UV1, 2, "ST") +
                     f'<vertices id="{g}-v"><input semantic="POSITION" source="#{g}-pos"/></vertices>'
                     f'<triangles material="ti_backdrop-material" count="{len(T)}">'
                     f'<input semantic="VERTEX" source="#{g}-v" offset="0"/><input semantic="NORMAL" source="#{g}-nrm" offset="0"/>'
                     f'<input semantic="TEXCOORD" source="#{g}-uv0" offset="0" set="0"/><input semantic="TEXCOORD" source="#{g}-uv1" offset="0" set="1"/>'
                     f'<p>{" ".join(map(str, T.ravel()))}</p></triangles></mesh></geometry>')
        nodes.append(f'<node id="{name}_a2" name="{name}_a2" type="NODE"><matrix sid="transform">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</matrix>'
                     f'<instance_geometry url="#{g}" name="{name}_a2"><bind_material><technique_common>'
                     f'<instance_material symbol="ti_backdrop-material" target="#ti_backdrop-material"/></technique_common></bind_material>'
                     f'</instance_geometry></node>')
    ident = '<matrix sid="transform">1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</matrix>'
    doc = ('<?xml version="1.0" encoding="utf-8"?>\n<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">'
           '<asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>'
           '<library_effects><effect id="ti_backdrop-effect"><profile_COMMON><technique sid="common"><lambert><diffuse>'
           '<color sid="diffuse">0.3 0.4 0.2 1</color></diffuse></lambert></technique></profile_COMMON></effect></library_effects>'
           '<library_materials><material id="ti_backdrop-material" name="ti_backdrop"><instance_effect url="#ti_backdrop-effect"/></material></library_materials>'
           f'<library_geometries>{"".join(geoms)}</library_geometries>'
           '<library_visual_scenes><visual_scene id="Scene" name="Scene">'
           f'<node id="base00" name="base00" type="NODE">{ident}<node id="start01" name="start01" type="NODE">{ident}{"".join(nodes)}</node>'
           f'<node id="detail2" name="detail2" type="NODE">{ident}</node></node></visual_scene></library_visual_scenes>'
           '<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>')
    open(OUT, "w", encoding="utf8").write(doc)


if __name__ == "__main__":
    near = grid(0, 6528, 64, hole=1984, lower_inside=2040)
    far = grid(6336, EXT - 192, 192, lower_ring=(6528, 4.0))
    write([("backdrop_near", near), ("backdrop_far", far)])
    print("BACKDROP_OK", len(near[4]) + len(far[4]), "triangoli", os.path.getsize(OUT) // 1024, "KB")
