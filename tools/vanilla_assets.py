"""Raccoglie dai livelli ufficiali di BeamNG le definizioni necessarie per riusare i loro asset.

BeamNG carica solo i materiali del livello corrente, quindi per usare alberi/oggetti di Italy,
East Coast o West Coast bisogna ricopiare nel nostro livello:
  * le ForestItemData (per gli alberi)
  * i Material usati dalle loro mesh (i percorsi delle texture restano quelli originali:
    nessuna texture viene ridistribuita, il gioco le trova nei suoi pacchetti).
"""
import os, re, json, zipfile, glob

GAME = r"D:\Giochi\Steam\steamapps\common\BeamNG.drive"
LEVELS = os.path.join(GAME, "content", "levels")
_zip_cache, _mat_cache, _item_cache = {}, {}, {}


def _zip_for(path):
    """path virtuale tipo /levels/italy/... o /art/... -> (zipfile, nome interno)."""
    p = path.lstrip("/")
    if p.startswith("levels/"):
        lv = p.split("/")[1]
        zn = [f for f in glob.glob(os.path.join(LEVELS, "*.zip")) if os.path.basename(f).lower() == lv.lower() + ".zip"][0]
    else:
        zn = os.path.join(GAME, "content", "art_shapes.zip") if p.startswith("art/shapes") else None
    if zn not in _zip_cache:
        _zip_cache[zn] = zipfile.ZipFile(zn)
    z = _zip_cache[zn]
    names = {n.lower(): n for n in z.namelist()} if not hasattr(z, "_lower") else z._lower
    z._lower = names
    return z, names.get(p.lower())


def read(path):
    z, n = _zip_for(path)
    if n is None:
        raise FileNotFoundError(path)
    return z.read(n)


def exists(path):
    try:
        return _zip_for(path)[1] is not None
    except Exception:
        return False


def level_materials(level):
    """tutti i Material definiti in un livello (e nei relativi art/)."""
    if level in _mat_cache:
        return _mat_cache[level]
    z, _ = _zip_for(f"/levels/{level}/info.json")
    mats = {}
    for n in z.namelist():
        if n.endswith("materials.json"):
            try:
                d = json.loads(z.read(n))
            except Exception:
                continue
            for k, v in d.items():
                if isinstance(v, dict) and v.get("class") == "Material":
                    mats[v.get("mapTo", k)] = (k, v)
                    mats.setdefault(k, (k, v))
    _mat_cache[level] = mats
    return mats


def forest_items(level):
    if level in _item_cache:
        return _item_cache[level]
    z, _ = _zip_for(f"/levels/{level}/info.json")
    items = {}
    for n in z.namelist():
        if n.endswith("managedItemData.json"):
            items.update(json.loads(z.read(n)))
    _item_cache[level] = items
    return items


def dae_material_names(path):
    s = read(path).decode("utf8", "replace")
    return sorted(set(re.findall(r'<material id="[^"]*" name="([^"]+)"', s)))


def collect(shape_path, level_for_materials, out_mats):
    """aggiunge in out_mats i Material usati da shape_path. Ritorna i nomi non trovati."""
    missing = []
    mats = level_materials(level_for_materials)
    for nm in dae_material_names(shape_path):
        if nm in mats:
            key, v = mats[nm]
            out_mats[key] = v
        else:
            missing.append(nm)
    return missing


def shape_bbox(path, skip=("col", "colmesh", "nulldetail", "bb__")):
    """bounding box (min, max) della mesh visibile applicando le matrici dei nodi Collada."""
    import numpy as np
    import xml.etree.ElementTree as ET
    ns = "{http://www.collada.org/2005/11/COLLADASchema}"
    root = ET.fromstring(read(path))
    geo_pts = {}
    for g in root.iter(ns + "geometry"):
        for s in g.iter(ns + "source"):
            if "position" in s.get("id", "").lower():
                a = s.find(ns + "float_array")
                if a is not None and a.text:
                    geo_pts[g.get("id")] = np.array(list(map(float, a.text.split()))).reshape(-1, 3)
                break
    pts = []

    def walk(node, M):
        m = node.find(ns + "matrix")
        if m is not None:
            M = M @ np.array(list(map(float, m.text.split()))).reshape(4, 4)
        name = (node.get("name") or "").lower()
        if any(k in name for k in skip):
            return
        for ig in node.findall(ns + "instance_geometry"):
            gid = ig.get("url", "").lstrip("#")
            if gid in geo_pts:
                P = geo_pts[gid]
                Ph = np.hstack([P, np.ones((len(P), 1))]) @ M.T
                pts.append(Ph[:, :3])
        for c in node.findall(ns + "node"):
            walk(c, M)

    for vs in root.iter(ns + "visual_scene"):
        for n in vs.findall(ns + "node"):
            walk(n, np.eye(4))
    if not pts:
        return None
    P = np.vstack(pts)
    return P.min(0), P.max(0)


def level_of(path):
    p = path.lstrip("/")
    return p.split("/")[1] if p.startswith("levels/") else None
