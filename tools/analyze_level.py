"""Controlli di qualita' sul livello generato (sovrapposizioni e oggetti mal posati).

python tools/analyze_level.py  -> stampa un riepilogo e salva build/analisi.json con gli esempi peggiori
"""
import os, sys, json, glob, math
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
from matplotlib.path import Path as MPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LV = os.path.join(ROOT, "mod", "levels", "terminal_isernia")
BUILD = os.path.join(ROOT, "build")
M = np.load(os.path.join(BUILD, "terrain_masks.npz"))
TZ, TDLOT, TDROAD, TRHW = M["z"], M["d_lot"], M["d_road"], M["road_hw"]
X0, SQ = float(M["x0"]), float(M["sq"])
dims = json.load(open(os.path.join(BUILD, "bld_dims.json")))


def ts(a, x, y, order=1):
    return ndimage.map_coordinates(a, [(np.atleast_1d(y) - X0) / SQ, (np.atleast_1d(x) - X0) / SQ], order=order, mode="nearest")


def objs(group):
    out = []
    for f in glob.glob(os.path.join(LV, "main", "MissionGroup", *group.split("/"), "items.level.json")):
        out += [json.loads(l) for l in open(f, encoding="utf8") if l.strip()]
    return [o for o in out if o.get("class") != "SimGroup"]


def footprint(o):
    shp = o["shapeName"].split("/")[-1].rsplit(".", 1)[0]
    if shp not in dims:
        return None
    mn, mx = np.array(dims[shp]["min"]), np.array(dims[shp]["max"])
    r = o["rotationMatrix"]; ax = np.array(r[0:2]); ay = np.array(r[3:5]); sx, sy, sz = o.get("scale", [1, 1, 1])
    p = np.array(o["position"][:2])
    return np.array([p + ax * x * sx + ay * y * sy for x, y in [(mn[0], mn[1]), (mx[0], mn[1]), (mx[0], mx[1]), (mn[0], mx[1])]]), mn, mx, (sx, sy, sz)


rep = {}
# --- edifici
blds = objs("dintorni/edifici")
polys, on_road, slope_bad, sunk = [], [], [], []
for o in blds:
    fp = footprint(o)
    if fp is None:
        continue
    P, mn, mx, (sx, sy, sz) = fp
    polys.append((P, o))
    # campiono dentro l'impronta
    u = np.linspace(0.1, 0.9, 5)
    pts = np.array([P[0] + (P[1] - P[0]) * a + (P[3] - P[0]) * b for a in u for b in u])
    dr = ts(TDROAD, pts[:, 0], pts[:, 1]); hw = ts(TRHW, pts[:, 0], pts[:, 1])
    if np.mean(dr < hw) > 0.15:
        on_road.append((float(np.mean(dr < hw)), o["position"], o["shapeName"].split("/")[-1]))
    z = ts(TZ, pts[:, 0], pts[:, 1])
    drop = float(z.max() - o["position"][2])
    base_depth = -mn[2] * sz                       # quanto scende la "fondazione" del modello
    if drop > base_depth + 0.5:
        slope_bad.append((round(drop, 1), round(base_depth, 1), o["position"], o["shapeName"].split("/")[-1]))
rep["edifici"] = {"totale": len(blds), "su_strada_>15%": len(on_road), "terreno_sopra_fondazione": len(slope_bad)}
# sovrapposizioni tra edifici
cent = np.array([P.mean(0) for P, o in polys]); tree = cKDTree(cent)
over = 0; over_list = []
paths = [MPath(P) for P, o in polys]
for i, (P, o) in enumerate(polys):
    for j in tree.query_ball_point(cent[i], 40):
        if j <= i:
            continue
        Pj = polys[j][0]
        u = np.linspace(0.05, 0.95, 8)
        gi = np.array([P[0] + (P[1] - P[0]) * a + (P[3] - P[0]) * b for a in u for b in u])
        gj = np.array([Pj[0] + (Pj[1] - Pj[0]) * a + (Pj[3] - Pj[0]) * b for a in u for b in u])
        f = max(paths[j].contains_points(gi).mean(), paths[i].contains_points(gj).mean())
        if f > 0.2:
            over += 1; over_list.append((round(float(f), 2), [round(float(v)) for v in cent[i]]))
rep["edifici"]["coppie_sovrapposte_>20%"] = over

# --- alberi dentro edifici o su strada
ftot, in_bld, on_rd = 0, 0, 0
bld_tree = cKDTree(cent)
for f in glob.glob(os.path.join(LV, "forest", "*.forest4.json")):
    arr = np.array([json.loads(l)["pos"][:2] for l in open(f) if l.strip()])
    ftot += len(arr)
    near = (np.abs(arr).max(1) < 2030) & (np.hypot(*arr.T) < 1500)   # terreno principale (oltre ci sono gli alberi dello sfondo)
    a = arr[near]
    if len(a) == 0:
        continue
    dr = ts(TDROAD, a[:, 0], a[:, 1]); hw = ts(TRHW, a[:, 0], a[:, 1])
    on_rd += int((dr < hw).sum())
    idx = bld_tree.query_ball_point(a, 35)
    for k, js in enumerate(idx):
        if any(paths[j].contains_point(a[k]) for j in js):
            in_bld += 1
rep["vegetazione"] = {"totale": ftot, "dentro_edifici": in_bld, "su_carreggiata": on_rd}

# --- lampioni stradali dentro edifici
lamps = [o for o in objs("dintorni/illuminazione") if o["class"] == "TSStatic"]
lb = 0
for o in lamps:
    p = np.array(o["position"][:2])
    if any(paths[j].contains_point(p) for j in bld_tree.query_ball_point(p, 35)):
        lb += 1
rep["lampioni_stradali"] = {"totale": len(lamps), "dentro_edifici": lb}

# --- strade: tratti con pendenza trasversale forte (terreno spianato male)
roads = json.load(open(os.path.join(BUILD, "terrain_info.json")))["roads"]
steep = 0; seg = 0
for r in roads:
    P = np.array(r["pts"])
    if len(P) < 2 or np.hypot(P[:, 0], P[:, 1]).min() > 1500:
        continue
    z = ts(TZ, P[:, 0], P[:, 1])
    d = np.hypot(*np.diff(P[:, :2], axis=0).T); dz = np.abs(np.diff(z))
    g = dz / np.maximum(d, 0.1)
    seg += len(g); steep += int((g > 0.18).sum())
rep["strade"] = {"segmenti": seg, "pendenza_>18%": steep}

json.dump({"rep": rep, "edifici_su_strada": sorted(on_road, reverse=True)[:15], "edifici_in_pendenza": sorted(slope_bad, reverse=True)[:15], "sovrapposti": sorted(over_list, reverse=True)[:15]},
          open(os.path.join(BUILD, "analisi.json"), "w"), indent=1)
print(json.dumps(rep, indent=1, ensure_ascii=False))
