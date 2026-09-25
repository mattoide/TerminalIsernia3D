"""Genera i terreni del livello dai dati reali.

  terreno principale : 2048 x 2048 vertici, passo 2 m (4 km), quote AWS Terrain Tiles z15 + dettaglio frattale
  terreno di sfondo  : 1024 x 1024 vertici, passo 32 m (33 km), quote z12, abbassato sotto il principale
Il piazzale (mesh) resta a Z=0: il terreno ci passa sotto e si raccorda ai bordi.
Strade, boschi, campi e zone industriali arrivano da OpenStreetMap (ODbL).

Uscite (mod/levels/terminal_isernia):
  terrain_main.ter/.terrain.json, art/terrains/*.png (anche la mappa colore dello sfondo), art/terrains/main.materials.json
  build/terrain_masks.npz (maschere per vegetazione e oggetti)
"""
import os, sys, json, math, struct, re, io, zipfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo import model2world
from osm import OSM
from build_textures import fbm, save_atomic

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LEVEL = os.path.join(ROOT, "mod", "levels", "terminal_isernia")
TEX = os.path.join(LEVEL, "art", "terrains")
BUILD = os.path.join(ROOT, "build")
ASSETS_TERRAIN_ZIP = r"D:\Giochi\Steam\steamapps\common\BeamNG.drive\content\assets\materials\terrain.zip"

H0 = 460.2            # quota s.l.m. del piazzale (Z = 0)
N, SQ = 2048, 2.0     # terreno principale
X0 = Y0 = -2048.0
NF, SQF = 1024, 32.0  # sfondo
XF0 = YF0 = -NF * SQF / 2

# ------------------------------------------------------------------ materiali terreno
A = "/assets/materials/terrain/"
TMATS = [  # nome, dettaglio, macro, groundmodel, colore medio base (calcolato), dimensione dettaglio (m)
    ("ti_t_grass",      A + "grass/t_grass_01/t_grass_01",                A + "grass/t_macro_grass/t_macro_grass",      "GRASS",       2.0),
    ("ti_t_grass_dry",  A + "grass/t_dirt_dry_grass/t_dirt_dry_grass",    A + "soil/macro_clumply/t_macro_clumpy",      "GRASS",       2.0),
    ("ti_t_forest",     A + "forest/t_forest_ground/t_forest_ground",     A + "forest/t_macro_forest/t_macro_forest",   "DIRT",        2.5),
    ("ti_t_dirt",       A + "soil/dirt_loose_dusty/t_dirt_loose_dusty",   A + "soil/macro_holes/t_macro_holes",         "DIRT_DUSTY",  2.0),
    ("ti_t_gravel",     A + "soil/t_gravels/t_gravels",                   A + "soil/macro_clumply/t_macro_clumpy",      "GRAVEL",      2.0),
    ("ti_t_asphalt",    A + "asphalt/t_asphalt_02/t_asphalt_02",          A + "asphalt/macro_asphalt/t_macro_asphalt",  "ASPHALT",     3.0),
    ("ti_t_rock",       A + "rock/t_dirt_rocky/t_dirt_rocky",             A + "rock/macro_rocky/t_macro_rocky",         "ROCK",        3.0),
    ("ti_t_farmland",   A + "soil/dirt_crumbly/t_dirt_crumbly",           A + "soil/macro_clumply/t_macro_clumpy",      "DIRT",        2.5),
    ("ti_t_weeds",      A + "grass/t_dirt_vegetation/t_dirt_vegetation",  A + "grass/t_macro_grass/t_macro_grass",      "GRASS",       2.0),
]
GRASS, GRASS_DRY, FOREST, DIRT, GRAVEL, ASPHALT, ROCK, FARM, WEEDS = range(len(TMATS))


def avg_colors():
    """colore base (sRGB) per strato. Le texture di dettaglio di BeamNG sono quasi neutre: il colore
    vero sta nella mappa base (calibrato sulla mappa base di Italy, un po' piu' verde: Molise in autunno)."""
    pal = {GRASS: (0.33, 0.37, 0.19), GRASS_DRY: (0.45, 0.42, 0.28), FOREST: (0.24, 0.25, 0.15), DIRT: (0.46, 0.41, 0.34),
           GRAVEL: (0.50, 0.48, 0.44), ASPHALT: (0.31, 0.31, 0.31), ROCK: (0.53, 0.50, 0.44), FARM: (0.42, 0.35, 0.26),
           WEEDS: (0.38, 0.38, 0.22)}
    return np.array([pal[i] for i in range(len(TMATS))], np.float32)


# ------------------------------------------------------------------ DEM
def dem_sampler(z):
    d = np.load(os.path.join(ROOT, "src", "dem", f"dem_z{z}.npz"))
    H, px, py, m = d["h"], float(d["px"]), float(d["py"]), float(d["m_per_px"])
    def sample(x, y, order=3):
        return ndimage.map_coordinates(H, [py - y / m, px + x / m], order=order, mode="nearest")
    return sample


def flat_normal(size, strength, seed):
    h = fbm(size, octaves=5, base_cells=size // 16, seed=seed)
    gy, gx = np.gradient(h)
    n = np.dstack([-gx * strength * 8, -gy * strength * 8, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------ rasterizzazione
class Raster:
    """griglia allineata al terreno principale (o a un sottorettangolo) con risoluzione res m/px."""
    def __init__(self, x0, y0, w_m, h_m, res):
        self.x0, self.y0, self.res = x0, y0, res
        self.w, self.h = int(round(w_m / res)), int(round(h_m / res))

    def px(self, p):  # riga 0 = sud (come il .ter)
        return ((p[0] - self.x0) / self.res, (p[1] - self.y0) / self.res)

    def polys(self, polys, value=1, width=0, mode="L", base=0):
        im = Image.new(mode, (self.w, self.h), base)
        d = ImageDraw.Draw(im)
        for pts in polys:
            q = [self.px(p) for p in pts]
            if width:
                d.line(q, fill=value, width=max(1, int(round(width / self.res))), joint="curve")
            elif len(q) >= 3:
                d.polygon(q, fill=value)
        return np.asarray(im)


def dae_triangles(path):
    import xml.etree.ElementTree as ET
    ns = "{http://www.collada.org/2005/11/COLLADASchema}"
    root = ET.parse(path).getroot()
    for g in root.iter(ns + "geometry"):
        pos = None
        for s in g.iter(ns + "source"):
            if s.get("id").endswith("-pos"):
                pos = np.array(list(map(float, s.find(ns + "float_array").text.split()))).reshape(-1, 3)
        for t in g.iter(ns + "triangles"):
            mat = t.get("material").replace("-material", "")
            idx = np.array(list(map(int, t.find(ns + "p").text.split())))
            for k in range(0, len(idx), 3):
                yield mat, pos[idx[k:k + 3]]


# ------------------------------------------------------------------ .ter
def write_ter(path, heights_m, layers, names, max_h):
    """heights_m relativi alla position.z del TerrainBlock, riga 0 = sud."""
    n = heights_m.shape[0]
    h = np.clip(np.round(heights_m / max_h * 65535), 0, 65535).astype("<u2")
    tmp = os.path.join(BUILD, "tmp_save", os.path.basename(path))       # scrittura atomica (il gioco tiene la mod montata)
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "wb") as f:
        f.write(struct.pack("<BI", 9, n))
        f.write(h.tobytes())
        f.write(layers.astype(np.uint8).tobytes())
        f.write(struct.pack("<I", len(names)))
        for nm in names:
            b = nm.encode()
            f.write(struct.pack("<B", len(b)) + b)
    os.replace(tmp, path)


def write_heightmap_png(ter_path):
    """PNG 16 bit (riga 0 = nord) usato dall'editor terreno di BeamNG."""
    d = open(ter_path, "rb").read()
    n = struct.unpack("<I", d[1:5])[0]
    h = np.frombuffer(d[5:5 + n * n * 2], dtype="<u2").reshape(n, n)[::-1]
    save_atomic(Image.fromarray(h.astype(np.uint16)), ter_path.replace(".ter", ".terrainheightmap.png"))


def write_terrain_json(path, level_rel_ter, n, names):
    json.dump({
        "binaryFormat": "version(char), size(unsigned int), heightMap(heightMapSize * heightMapItemSize), layerMap(layerMapSize * layerMapItemSize), layerTextureMap(layerMapSize * layerMapItemSize), materialNames",
        "datafile": level_rel_ter,
        "heightMapItemSize": 2, "heightMapSize": n * n,
        "heightmapImage": level_rel_ter.replace(".ter", ".terrainheightmap.png"),
        "layerMapItemSize": 1, "layerMapSize": n * n,
        "materials": names, "size": n, "version": 9}, open(path, "w"), indent=2)


def save_img(arr, name, mode):
    save_atomic(Image.fromarray(np.clip(arr * 255 + 0.5, 0, 255).astype(np.uint8), mode), os.path.join(TEX, name), optimize=True)


# ================================================================== main
def rava_to_lot(P):
    """la Strada Comunale Rava entra nel piazzale dall'angolo sud-ovest, tra la fine del marciapiede sud-ovest (y -34) e il
    cordolo sud-est (y -51): da x modello -110 la porto dolcemente sul centro della strada che prosegue a ovest (y -47.5, ciglio sud-est sul cordolo)."""
    from geo import world2model, model2world
    Q = []
    for x, y in P:
        mx, my = world2model(x, y)
        k = smoothstep(-110, -37, mx)
        Q.append(model2world(mx, my + (-47.5 - my) * k))
    return np.array(Q)


LONG_BRIDGE = 70.0          # oltre questa lunghezza il ponte e' un viadotto vero (mesh di build_bridges.py)


CARWASH_YARD = []       # (j0, j1, i0, i1, maschera) del piazzale dell'autolavaggio, per lo strato asfalto
SPORT_COVER = []        # (j0, j1, i0, i1, maschera) dove campo e pista li fa build_stadium.py: strato asfalto (niente erba 3D)


def sport_pads(osm, XX, YY, Z):
    """campi da calcio OSM in piano: lo stadio fino al suo muro di cinta, il campo d'allenamento fino al suo recinto;
    raccordo di 10 m. Registra in SPORT_COVER l'area coperta dalle mesh di build_stadium.py."""
    from matplotlib.path import Path as MP
    rings = [(t, np.array(osm.way_pts(w))) for w, t in osm.ways_where(lambda t: t.get("barrier") in ("wall", "fence")
                                                                       or t.get("leisure") == "sports_centre")]
    out = Z.copy(); n = 0
    for w, t in osm.ways_where(lambda t: t.get("leisure") == "pitch" and t.get("sport") == "soccer"):
        P = np.array(osm.way_pts(w)); c = P.mean(0)
        if np.hypot(*c) > 1200 or len(P) < 4:
            continue
        enc = [(tt, r) for tt, r in rings if len(r) > 3 and MP(r).contains_point(c) and np.ptp(r[:, 0]) < 320]
        walls = [r for tt, r in enc if tt.get("barrier") == "wall"]
        centres = [r for tt, r in enc if tt.get("leisure") == "sports_centre"]
        fences = [r for tt, r in enc if tt.get("barrier") == "fence"]
        pad = max(walls, key=len) if walls else (centres[0] if centres else P)
        cover = (min(fences, key=lambda r: np.ptp(r[:, 0])) if (walls and fences) else P)
        lo, hi = pad.min(0) - 14, pad.max(0) + 14
        i0 = max(0, int((lo[0] - X0) / SQ)); i1 = min(Z.shape[1], int((hi[0] - X0) / SQ) + 1)
        j0 = max(0, int((lo[1] - Y0) / SQ)); j1 = min(Z.shape[0], int((hi[1] - Y0) / SQ) + 1)
        pts = np.stack([XX[j0:j1, i0:i1].ravel(), YY[j0:j1, i0:i1].ravel()], 1)
        ins = MP(pad).contains_points(pts).reshape(j1 - j0, i1 - i0)
        if not ins.any():
            continue
        d = ndimage.distance_transform_edt(~ins) * SQ
        zp = float(np.median(Z[j0:j1, i0:i1][ins]))
        wgt = 1 - smoothstep(0, 10, d)
        sub = out[j0:j1, i0:i1]; sub[:] = sub * (1 - wgt) + zp * wgt
        cov = ndimage.binary_dilation(MP(cover).contains_points(pts).reshape(j1 - j0, i1 - i0), iterations=2)
        SPORT_COVER.append((j0, j1, i0, i1, cov))
        n += 1
    print("campi sportivi in piano:", n)
    return out


def building_pads(osm, XX, YY, Z, D_out, margin=1.0, blend=7.0):
    """spiana il terreno sotto ogni edificio OSM (rettangolo orientato + margine) alla quota mediana,
    raccordando in 'blend' metri: come i terrazzamenti veri di Isernia."""
    from osm import obb
    N = Z.shape[0]
    PZ = np.zeros_like(Z); PW = np.zeros_like(Z); PM = np.zeros_like(Z)
    n = 0
    for pts, t in osm.polygons_where(lambda t: "building" in t):
        P = np.asarray(pts); c0 = P.mean(0)
        if np.hypot(*c0) > 1450:
            continue
        o = obb(pts)
        if o is None:
            continue
        a, L, W, ctr = o
        if L * W < 12:
            continue
        m_, b_ = (margin, blend)
        cw = t.get("amenity") == "car_wash"
        if cw:                                            # piazzale asfaltato: a nord la seconda tettoia e il locale tecnico
            m_, b_ = 9.0, 6.0
        r = math.hypot(L, W) / 2 + m_ + b_ + (14.0 if cw else 0.0)
        i0 = max(0, int((ctr[0] - r - X0) / SQ)); i1 = min(N, int((ctr[0] + r - X0) / SQ) + 2)
        j0 = max(0, int((ctr[1] - r - Y0) / SQ)); j1 = min(N, int((ctr[1] + r - Y0) / SQ) + 2)
        if i1 <= i0 or j1 <= j0:
            continue
        xs, ys = XX[j0:j1, i0:i1] - ctr[0], YY[j0:j1, i0:i1] - ctr[1]
        u = xs * math.cos(a) + ys * math.sin(a); v = -xs * math.sin(a) + ys * math.cos(a)
        if cw:                                            # satellite 2026: 20 m a nord, 6 a sud, 10 alle testate
            d = np.hypot(np.maximum(np.abs(u) - L / 2 - 10.0, 0), np.maximum(np.abs(v - 7.0) - (W / 2 + 13.0), 0))
        else:
            d = np.hypot(np.maximum(np.abs(u) - L / 2 - m_, 0), np.maximum(np.abs(v) - W / 2 - m_, 0))
        inside = d <= 0
        foot = np.hypot(np.maximum(np.abs(u) - L / 2, 0), np.maximum(np.abs(v) - W / 2, 0)) <= 0
        if not inside.any() or not foot.any() or D_out[j0:j1, i0:i1][foot].min() < 25:   # il terminal e' la nostra mesh
            continue
        zp = float(np.median(Z[j0:j1, i0:i1][inside]))
        w = 1 - smoothstep(0, b_, d)
        if t.get("amenity") == "car_wash":
            CARWASH_YARD.append((j0, j1, i0, i1, d <= 0, w, zp))
        PZ[j0:j1, i0:i1] += w * zp; PW[j0:j1, i0:i1] += w
        PM[j0:j1, i0:i1] = np.maximum(PM[j0:j1, i0:i1], w)
        n += 1
    pad = np.where(PW > 0, PZ / np.maximum(PW, 1e-6), Z)
    print("piazzole edifici:", n)
    return Z * (1 - PM) + pad * PM


def main():
    os.makedirs(TEX, exist_ok=True)
    rng = np.random.default_rng(42)
    dem15, dem12 = dem_sampler(15), dem_sampler(12)
    osm = OSM()

    xs = X0 + np.arange(N) * SQ
    ys = Y0 + np.arange(N) * SQ
    XX, YY = np.meshgrid(xs, ys)                       # [riga=y (sud->nord), col=x]
    Z = dem15(XX.ravel(), YY.ravel()).reshape(N, N) - H0
    print("DEM ok", Z.min(), Z.max())

    # dettaglio frattale (il DEM pubblico e' ~25-30 m effettivi)
    n1 = fbm(N, octaves=6, base_cells=16, seed=1) - 0.5    # 256 m .. 8 m
    n2 = fbm(N, octaves=3, base_cells=256, seed=2) - 0.5   # 16 m .. 4 m
    slope0 = np.hypot(*np.gradient(Z, SQ))
    detail = n1 * (1.6 + 4 * np.clip(slope0, 0, 0.6)) + n2 * 0.35

    # --- piazzale: superficie della mesh rasterizzata a 0.5 m
    fr = Raster(-200, -200, 400, 400, 0.5)
    surf = np.full((fr.h, fr.w), np.nan, np.float32)
    polys_asph, polys_side = [], []
    for mat, tri in dae_triangles(os.path.join(BUILD, "shapes", "ti_ground.dae")):
        if tri[:, 2].max() > 0.5:
            continue
        (polys_asph if mat == "ti_asphalt" else polys_side).append([tuple(p[:2]) for p in tri])
    m_as = fr.polys(polys_asph, 255) > 0
    m_sd = fr.polys(polys_side, 255) > 0
    surf[m_as] = 0.0
    surf[m_sd] = 0.1
    foot = m_as | m_sd
    foot = ndimage.binary_closing(foot, iterations=2)
    # distanza (m) dal perimetro, positiva fuori; e quota del bordo piu' vicino
    d_out, idx = ndimage.distance_transform_edt(~foot, return_indices=True)
    d_in = ndimage.distance_transform_edt(foot)
    surf_f = np.where(np.isnan(surf), 0.0, surf)
    edge_z = surf_f[idx[0], idx[1]]
    d_out *= fr.res; d_in *= fr.res
    # campiono sul terreno
    def samp(a, order=1):
        cx = (XX - fr.x0) / fr.res; cy = (YY - fr.y0) / fr.res
        out = ndimage.map_coordinates(a.astype(np.float32), [cy.ravel(), cx.ravel()], order=order, mode="nearest").reshape(N, N)
        inside = (cx >= 0) & (cy >= 0) & (cx < fr.w) & (cy < fr.h)
        return out, inside
    D_out, ins = samp(d_out); D_out[~ins] = 1e4
    D_in, _ = samp(d_in); D_in[~ins] = 0
    E_z, _ = samp(edge_z, 0)
    FOOT = (D_out < 0.25) & ins

    # --- lato sud-est (oltre il parapetto): scarpata verso il bosco
    # direzione "fuori" SE = -Y del modello ruotato
    t = math.radians(44.5)
    se_dir = np.array([math.sin(t), -math.cos(t)])
    cx_w, cy_w = model2world(12, 0)
    side_se = ((XX - cx_w) * se_dir[0] + (YY - cy_w) * se_dir[1]) > 44
    ditch = -1.8 * smoothstep(3, 10, D_out) * (1 - smoothstep(22, 50, D_out)) * side_se

    # --- strade OSM spianate
    HW = {"trunk": 5.5, "trunk_link": 4, "primary": 5, "primary_link": 3.5, "secondary": 4.5, "tertiary": 4,
          "unclassified": 3, "residential": 3, "living_street": 2.5, "service": 2.2, "track": 1.6,
          "construction": 3.5, "busway": 3}
    road_center = np.zeros((N, N), bool); road_hw = np.zeros((N, N), np.float32); road_z = np.zeros((N, N), np.float32)
    roads_out = []
    # 1) profili: quota DEM lisciata lungo la strada. Gallerie escluse; i ponti corti (tombini, fossi, torrenti)
    #    diventano strada normale sul terreno spianato, i viadotti lunghi li fa build_bridges.py
    ways = []
    for w, tg in osm.ways_where(lambda t: t.get("highway") in HW):
        if tg.get("tunnel") and tg.get("tunnel") != "no":
            continue
        pts = np.array(osm.way_pts(w))
        if len(pts) < 2:
            continue
        seg = np.hypot(*np.diff(pts, axis=0).T); L = np.concatenate([[0], np.cumsum(seg)])
        if L[-1] < 2:
            continue
        if tg.get("bridge") and tg.get("bridge") != "no" and L[-1] > LONG_BRIDGE:
            continue
        s = np.arange(0, L[-1], 1.0)
        P = np.stack([np.interp(s, L, pts[:, 0]), np.interp(s, L, pts[:, 1])], 1)
        hw_way = HW[tg["highway"]]
        if tg.get("name") == "Strada Comunale Rava":
            P = rava_to_lot(P); hw_way = 3.5
        if tg.get("service") == "driveway" and np.hypot(P[:, 0], P[:, 1]).min() < 150:
            hw_way = 3.0                                  # stradina asfaltata che sale all'autolavaggio
        keep = (np.abs(P[:, 0]) < 2040) & (np.abs(P[:, 1]) < 2040)
        if keep.sum() < 2:
            continue
        zprof = dem15(P[:, 0], P[:, 1])
        zprof = ndimage.gaussian_filter1d(zprof - H0, 25, mode="nearest")
        # vicino al piazzale la strada si porta a quota 0: conta la distanza dal bordo del piazzale (prima dal centro,
        # 120-260 m, che teneva a quota 0 anche la stradina dell'autolavaggio: arrivava 1.2 m sotto il suo piazzale)
        dl = ndimage.map_coordinates(D_out.astype(np.float32), [(P[:, 1] - Y0) / SQ, (P[:, 0] - X0) / SQ], order=1, mode="nearest")
        zprof = zprof * smoothstep(8, 70, dl)
        nid = [n for n in w["nodes"] if n in osm.en]
        idx = np.clip(np.round(L).astype(int), 0, len(s) - 1)
        # la strada che dalla testata nord-est del piazzale va verso lo stadio: dal vero e' in piano (il DEM ha una gobba
        # di 1.7 m, forse la vegetazione): profilo lineare tra i due capi e campi ai lati spianati (FLAT_ROADS)
        from geo import world2model
        m0 = world2model(*P[0]); flat = (not tg.get("name")) and math.hypot(m0[0] - 115, m0[1] + 40) < 15
        ways.append(dict(w=w, tg=tg, P=P, s=s, z=zprof, keep=keep, nodes=list(zip(nid, idx)), hw=hw_way, flat=flat))
    # 2) incroci: tutte le strade che si toccano nello stesso nodo OSM ci arrivano alla stessa quota
    #    (prima ogni via era lisciata per conto suo: gradini e rampe del 40-50% agli innesti)
    from collections import defaultdict
    use = defaultdict(int)
    for W_ in ways:
        for n, _ in W_["nodes"]:
            use[n] += 1
    junc = {n for n, c in use.items() if c > 1}
    for it in range(4):
        acc = defaultdict(list)
        for W_ in ways:
            for n, i in W_["nodes"]:
                if n in junc:
                    acc[n].append(W_["z"][i])
        target = {n: float(np.mean(v)) for n, v in acc.items()}
        for W_ in ways:
            J = [(W_["s"][i], target[n] - W_["z"][i]) for n, i in W_["nodes"] if n in junc]
            if not J:
                continue
            num = np.zeros_like(W_["z"]); den = np.zeros_like(W_["z"])
            for sj, cj in J:
                h = np.clip(1 - np.abs(W_["s"] - sj) / 80.0, 0, 1)
                num += cj * h; den += h
            W_["z"] = W_["z"] + num / np.maximum(den, 1.0)
    for W_ in ways:                                       # strade in piano: retta tra le quote dei due capi
        if W_["flat"]:
            s_ = W_["s"]; W_["z"] = W_["z"][0] + (W_["z"][-1] - W_["z"][0]) * s_ / max(s_[-1], 1e-6)
    flat_center = np.zeros((N, N), bool)
    for W_ in ways:
        if W_["flat"]:
            ci = np.clip(((W_["P"][:, 0] - X0) / SQ).round().astype(int), 0, N - 1)
            cj = np.clip(((W_["P"][:, 1] - Y0) / SQ).round().astype(int), 0, N - 1)
            flat_center[cj, ci] = True
    # 3) raster delle carreggiate; in uscita solo i tratti dentro il terreno principale
    for W_ in ways:
        tg, P, zprof, keep = W_["tg"], W_["P"], W_["z"], W_["keep"]
        k = 0
        while k < len(P):
            if not keep[k]:
                k += 1
                continue
            e = k
            while e < len(P) and keep[e]:
                e += 1
            if e - k >= 4:
                Pk, zk = P[k:e], zprof[k:e]
                sel = list(range(0, len(Pk), 4))
                if sel[-1] != len(Pk) - 1:
                    sel.append(len(Pk) - 1)
                roads_out.append({"type": tg["highway"], "name": tg.get("name", ""), "hw": W_["hw"],
                                  "oneway": tg.get("oneway") == "yes", "surface": tg.get("surface", ""),
                                  "bridge": bool(tg.get("bridge") and tg.get("bridge") != "no"),
                                  "pts": [[float(Pk[i][0]), float(Pk[i][1]), float(zk[i])] for i in sel]})
            k = e
        Pin, zin = P[keep], zprof[keep]
        ci = np.clip(((Pin[:, 0] - X0) / SQ).round().astype(int), 0, N - 1)
        cj = np.clip(((Pin[:, 1] - Y0) / SQ).round().astype(int), 0, N - 1)
        road_center[cj, ci] = True
        road_hw[cj, ci] = np.maximum(road_hw[cj, ci], W_["hw"])
        road_z[cj, ci] = zin
    dr, ridx = ndimage.distance_transform_edt(~road_center, return_indices=True)
    dr *= SQ
    RHW = road_hw[ridx[0], ridx[1]]; RZ = road_z[ridx[0], ridx[1]]
    road_blend = 1 - smoothstep(RHW + 0.6, RHW + 6.0, dr)
    if flat_center.any():                                 # campi piatti ai lati della strada in piano (raccordo 15-55 m)
        dfl, fidx = ndimage.distance_transform_edt(~flat_center, return_indices=True)
        dfl *= SQ
        wfl = 1 - smoothstep(15, 55, dfl)
        Z = Z * (1 - wfl) + road_z[fidx[0], fidx[1]] * wfl
        detail = detail * (1 - wfl)
    print("strade", len(roads_out))

    # --- composizione quote
    Znat = Z + detail * smoothstep(6, 60, D_out) * (1 - road_blend) + ditch
    # piazzole piane sotto gli edifici OSM (prima gli edifici in pendio restavano sepolti fino a 13 m a monte)
    Znat = building_pads(osm, XX, YY, Znat, D_out)
    Znat = sport_pads(osm, XX, YY, Znat)
    Znat = Znat * (1 - road_blend) + RZ * road_blend
    # il piazzale dell'autolavaggio vince sulla stradina che gli passa accanto (la strada vi sale con una rampa)
    for j0, j1, i0, i1, msk, w, zp in CARWASH_YARD:
        sub = Znat[j0:j1, i0:i1]; sub[:] = sub * (1 - w) + zp * w
    # raccordo al piazzale: entro 3 m dal bordo quota del bordo, poi naturale in 25 m
    k = smoothstep(2.5, 25, D_out)
    Zf = E_z - 0.02 + (Znat - (E_z - 0.02)) * k
    near_edge = (D_out < 3.0)
    Zf = np.where(near_edge, np.minimum(Zf, E_z + 0.02), Zf)
    # subito fuori dal bordo (una cella da 2 m): il terreno interpolato non deve affiorare sull'asfalto accanto ai cordoli;
    # dietro a cordoli e marciapiedi scende di 14 cm (li chiudono le facce posteriori), agli imbocchi delle strade di 2
    ring = (D_out < 2.5) & ~FOOT
    Zf = np.where(ring, np.minimum(Zf, E_z - np.where(E_z > 0.05, 0.14, 0.02)), Zf)
    # sotto la mesh: sotto la superficie
    Zf = np.where(FOOT, np.minimum(E_z, 0.0) - 0.06 - 0.25 * smoothstep(2, 8, D_in), Zf)

    # --- layer materiali
    lay = np.full((N, N), GRASS, np.uint8)
    main_r = Raster(X0, Y0, N * SQ, N * SQ, SQ)
    def area(fn):
        return main_r.polys([p for p, t in osm.polygons_where(fn)], 1) > 0
    nz = fbm(N, octaves=5, base_cells=32, seed=5)
    lay[nz > 0.62] = GRASS_DRY
    lay[area(lambda t: t.get("landuse") in ("farmland",))] = FARM
    lay[area(lambda t: t.get("landuse") in ("grass", "meadow", "village_green") or t.get("natural") in ("grassland",) or t.get("leisure") in ("park", "garden"))] = GRASS
    lay[area(lambda t: t.get("landuse") in ("industrial", "construction", "brownfield", "railway"))] = GRAVEL
    lay[area(lambda t: t.get("landuse") in ("residential", "retail", "commercial"))] = WEEDS
    forest = area(lambda t: t.get("natural") in ("wood", "scrub") or t.get("landuse") in ("forest",))
    # bosco ripariale lungo i corsi d'acqua (non sempre mappato)
    water = main_r.polys([osm.way_pts(w) for w, t in osm.ways_where(lambda t: "waterway" in t)], 1, width=2) > 0
    dw = ndimage.distance_transform_edt(~water) * SQ
    forest |= (dw < 18 + 14 * nz)
    # boschi attorno al piazzale visti in ortofoto (fascia NE-E-SE e scarpata SE)
    forest |= side_se & (D_out > 6) & (D_out < 160 + 60 * nz)
    # i boschi OSM qui sono disegnati larghi: dal satellite lungo le strade c'e' quasi sempre una fascia di prato
    # (l'utente: "alberi anche dove nella realta' c'e' solo prato"); lungo la strada verso lo stadio prato per 45 m
    forest &= ~((dr < RHW + 8.0) & (np.hypot(XX, YY) < 1500))
    if flat_center.any():
        forest &= ~(dfl < 45.0)
    lay[forest] = FOREST
    lay[area(lambda t: t.get("amenity") == "parking" or t.get("leisure") == "pitch" and t.get("surface") in ("asphalt",))] = ASPHALT
    lay[area(lambda t: "building" in t)] = GRAVEL
    slope = np.degrees(np.arctan(np.hypot(*np.gradient(Zf, SQ))))
    lay[(slope > 32) & (lay != ASPHALT)] = ROCK
    # un metro in piu' della carreggiata: i materiali del terreno si fondono su una cella (2 m) e la terra dei bordi
    # arrivava fin quasi al centro delle strade senza velo d'asfalto sopra (la Rava sembrava verde)
    road_core = dr < RHW + 1.0
    lay[road_core] = ASPHALT
    lay[(dr >= RHW + 1.0) & (dr < RHW + 2.5 + nz)] = DIRT
    lay[(D_out < 1.8) & ~FOOT & ~road_core] = DIRT   # terra battuta attorno ai cordoli, ma non sopra le strade che li costeggiano
    lay[FOOT] = ASPHALT
    # sentieri e piste sterrate
    unpaved = main_r.polys([osm.way_pts(w) for w, t in osm.ways_where(lambda t: t.get("highway") == "track" or t.get("surface") in ("unpaved", "gravel", "dirt", "ground"))], 1, width=3.2) > 0
    lay[unpaved] = DIRT

    # --- quota di base e scrittura
    zmin = float(Zf.min()) - 1.0
    maxh = float(Zf.max() - zmin) + 1.0
    names = [m[0] for m in TMATS]
    # piazzale dell'autolavaggio asfaltato (ortofoto)
    ia = [n for n, *_ in TMATS].index("ti_t_asphalt")
    for j0, j1, i0, i1, msk, w, zp in CARWASH_YARD:
        sub = lay[j0:j1, i0:i1]; sub[msk] = ia
    for j0, j1, i0, i1, msk in SPORT_COVER:                  # sotto campo e pista (mesh): niente erba 3D che spunta
        sub = lay[j0:j1, i0:i1]; sub[msk] = ia
    write_ter(os.path.join(LEVEL, "terrain_main.ter"), Zf - zmin, lay, names, maxh)
    write_terrain_json(os.path.join(LEVEL, "terrain_main.terrain.json"), "/levels/terminal_isernia/terrain_main.ter", N, names)
    write_heightmap_png(os.path.join(LEVEL, "terrain_main.ter"))
    print("terreno principale: zmin", zmin, "maxh", maxh)

    # --- mappe base 4096 (1 m/px) condivise da tutti i materiali
    cols = avg_colors()
    up = lambda a, order=0: ndimage.zoom(a, 2, order=order)
    L4 = up(lay)
    base = cols[L4]
    fine = fbm(4096, octaves=6, base_cells=64, seed=9)[..., None]
    base = base * (0.82 + 0.36 * fine)
    # campi: tinta diversa per appezzamento (arato / stoppie / erba medica)
    tints = {FARM: [(0.46, 0.36, 0.26), (0.62, 0.55, 0.36), (0.40, 0.46, 0.25)]}
    field_noise = ndimage.zoom(fbm(N, octaves=2, base_cells=24, seed=13), 2, order=0)
    fm = L4 == FARM
    choice = (field_noise * 3).astype(int).clip(0, 2)
    tc = np.array(tints[FARM], np.float32)[choice]
    base[fm] = base[fm] * 0.4 + tc[fm] * 0.6
    base = base[::-1]                                     # immagine: riga 0 = nord
    save_img(base, "t_ti_terrain_base_b.png", "RGB")
    Z4 = ndimage.zoom(Zf, 2, order=1)
    # la normal "base" NON contiene le pendenze (le da' gia' la geometria): solo micro-rilievo
    save_img(flat_normal(4096, 0.35, seed=31), "t_ti_terrain_base_nm.png", "RGB")
    rough = np.select([L4 == ASPHALT, L4 == ROCK, L4 == GRAVEL], [0.82, 0.9, 0.93], 0.97).astype(np.float32)
    save_img(rough[::-1], "t_ti_terrain_base_r.png", "L")
    lap = ndimage.gaussian_filter(Z4, 4) - Z4
    save_img(np.clip(1 - lap * 0.8, 0.6, 1)[::-1], "t_ti_terrain_base_ao.png", "L")
    save_img(((Z4 - Z4.min()) / np.ptp(Z4))[::-1], "t_ti_terrain_base_h.png", "L")

    # --- sfondo (33 km): quote z12, centro abbassato sotto il terreno principale
    xf = XF0 + np.arange(NF) * SQF
    XF, YF = np.meshgrid(xf, xf)
    ZF = dem12(XF.ravel(), YF.ravel()).reshape(NF, NF) - H0
    cheb = np.maximum(np.abs(XF), np.abs(YF))
    # (niente abbassamento: lo sfondo ora e' una mesh, vedi build_backdrop.py)
    zfmin = float(ZF.min()) - 1; zfmax = float(ZF.max() - zfmin) + 1
    slopef = np.degrees(np.arctan(np.hypot(*np.gradient(ZF, SQF))))
    # un solo materiale: con piu' strati BeamNG disegna i blocchi da 32 m con i colori dei singoli strati
    layf = np.zeros((NF, NF), np.uint8)
    namesf = ["ti_t_far_hills", "ti_t_far_pasture", "ti_t_far_rock"]
    for f in ("terrain_far.ter", "terrain_far.terrain.json", "terrain_far.terrainheightmap.png"):
        if os.path.exists(os.path.join(LEVEL, f)):
            os.remove(os.path.join(LEVEL, f))
    # colore sfondo 2048: boschi scuri, campi in valle, pascoli e roccia in quota
    Zf2 = ndimage.zoom(ZF, 2, order=1); s2 = ndimage.zoom(slopef, 2, order=1)
    nf = fbm(2048, octaves=6, base_cells=16, seed=21)
    valley = smoothstep(80, 0, Zf2 - 0) * (s2 < 8)
    colf = np.zeros((2048, 2048, 3), np.float32)
    forest_c = np.array([0.20, 0.27, 0.14]); field_c = np.array([0.43, 0.43, 0.28]); past_c = np.array([0.36, 0.39, 0.24]); rock_c = np.array([0.47, 0.46, 0.43])
    wf = np.clip(nf * 1.4 - 0.05 + s2 / 22, 0, 1)
    colf[:] = forest_c * wf[..., None] + field_c * (1 - wf[..., None])
    hi = smoothstep(1100 - H0, 1500 - H0, Zf2)[..., None]
    colf = colf * (1 - hi) + past_c * hi
    rk = smoothstep(34, 48, s2)[..., None] * 0.7
    colf = colf * (1 - rk) + rock_c * rk
    colf *= (0.85 + 0.3 * fbm(2048, octaves=4, base_cells=64, seed=22))[..., None] * 0.78   # piu' scuro: la foschia schiarisce gia' molto
    save_img(colf[::-1], "t_ti_far_base_b.png", "RGB")
    save_img(flat_normal(2048, 0.25, seed=32), "t_ti_far_base_nm.png", "RGB")
    save_img(np.full((2048, 2048), 0.95, np.float32), "t_ti_far_base_r.png", "L")
    save_img(np.full((2048, 2048), 1.0, np.float32), "t_ti_far_base_ao.png", "L")
    save_img(((Zf2 - Zf2.min()) / np.ptp(Zf2))[::-1], "t_ti_far_base_h.png", "L")

    # --- materiali terreno (json)
    write_materials(zmin, maxh)
    json.dump({"main": {"position": [X0, Y0, zmin], "maxHeight": maxh, "squareSize": SQ, "size": N},
               "far": {"position": [XF0, YF0, zfmin], "maxHeight": zfmax, "squareSize": SQF, "size": NF},
               "roads": roads_out}, open(os.path.join(BUILD, "terrain_info.json"), "w"))
    # boschi dell'orizzonte (stessa logica della mappa colore, alla risoluzione del terreno di sfondo)
    nfs = fbm(NF, octaves=6, base_cells=8, seed=21)
    far_forest = ((np.clip(nfs * 1.4 - 0.2 + slopef / 30, 0, 1) > 0.5) & (slopef < 38) & (ZF < 1350 - H0))
    np.savez_compressed(os.path.join(BUILD, "terrain_masks.npz"), z=Zf.astype(np.float32), lay=lay, forest=forest,
                        zf=ZF.astype(np.float32), far_forest=far_forest, xf0=XF0, sqf=SQF,
                        d_lot=np.minimum(D_out, 1e4).astype(np.float32), d_road=dr.astype(np.float32),
                        road_hw=RHW.astype(np.float32), x0=X0, y0=Y0, sq=SQ)
    print("TERRAIN_OK")


def write_materials(zmin, maxh):
    B = "/levels/terminal_isernia/art/terrains/t_ti_terrain_base"
    mats = {}
    for name, det, mac, gm, dsize in TMATS:
        mats[name] = {
            "internalName": name, "class": "TerrainMaterial", "persistentId": _uuid(name),
            "annotation": gm, "groundmodelName": gm,
            "baseColorBaseTex": B + "_b.png", "baseColorBaseTexSize": 4096,
            "normalBaseTex": B + "_nm.png", "normalBaseTexSize": 4096,
            "roughnessBaseTex": B + "_r.png", "roughnessBaseTexSize": 4096,
            "aoBaseTex": B + "_ao.png", "aoBaseTexSize": 4096,
            "heightBaseTex": B + "_h.png", "heightBaseTexSize": 4096,
            "baseColorDetailTex": det + "_b.png", "normalDetailTex": det + "_nm.png",
            "roughnessDetailTex": det + "_r.png", "aoDetailTex": det + "_ao.png", "heightDetailTex": det + "_h.png",
            "baseColorMacroTex": mac + "_b.png", "normalMacroTex": mac + "_nm.png",
            "roughnessMacroTex": mac + "_r.png", "aoMacroTex": mac + "_ao.png", "heightMacroTex": mac + "_h.png",
            "detailSize": dsize, "diffuseSize": 4096,
            "detailDistances": [0, 0, 20, 45], "macroDistances": [0, 60, 150, 1500],
            "baseColorDetailStrength": [0.45, 0.45], "normalDetailStrength": [1, 0.3],
            "roughnessDetailStrength": [0.5, 0.5],
            "baseColorMacroStrength": [0.25, 0.2], "normalMacroStrength": [0.5, 0.5], "roughnessMacroStrength": [0.2, 0.3],
            "macroSize": 60, "baseColorMacroTexSize": 60, "normalMacroTexSize": 60, "roughnessMacroTexSize": 60,
            "aoMacroTexSize": 60, "heightMacroTexSize": 60,
            "detailStrength": 0.6, "macroStrength": 0.2, "detailDistance": 60, "macroDistance": 1500,
        }
    mats["ti_TerrainMaterialTextureSet"] = {"name": "ti_TerrainMaterialTextureSet", "class": "TerrainMaterialTextureSet",
                                            "persistentId": _uuid("tset"), "baseTexSize": [4096, 4096],
                                            "detailTexSize": [1024, 1024], "macroTexSize": [1024, 1024]}
    json.dump(mats, open(os.path.join(TEX, "main.materials.json"), "w"), indent=1)


def _uuid(s):
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "terminal_isernia/" + s))


if __name__ == "__main__":
    main()
