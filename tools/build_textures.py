"""Prepara le texture della mod nel formato del texture-cooker di BeamNG.

Convenzioni BeamNG (0.39):
  *_b.color.png   base color sRGB
  *_nm.normal.png normal map OpenGL (Y+), verificato sulle texture di terreno vanilla
  *_r.data.png    roughness (lineare, grigio)
  *_ao.data.png   ambient occlusion
  *_o.data.png    opacita' / maschere
Il gioco converte da solo i png in dds (BC7/BC5) nella cartella temp dell'utente.

Sorgenti: texture CC0 di ambientCG (src/cc0/ambientcg, scaricate da fetch_sources.py) e le foto
dell'edificio della mod originale (_orig/extracted/...).
"""
import os, sys, math
import numpy as np
from PIL import Image, ImageFilter

Image.MAX_IMAGE_PIXELS = None
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CC0 = os.path.join(ROOT, "src", "cc0", "ambientcg")
ORIG_TEX = os.path.join(ROOT, "_orig", "extracted", "levels", "terminal_isernia", "terminal", "texture")
OUT = os.path.join(ROOT, "mod", "levels", "terminal_isernia", "art", "textures")


def load(path, mode="RGB", size=None):
    im = Image.open(path).convert(mode)
    if size and im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    return np.asarray(im).astype(np.float32) / 255.0


def save_atomic(im, path, **kw):
    """scrive in un file temporaneo e poi rinomina: il gioco (che tiene la mod montata e ricuoce le texture
    cambiate) non deve mai leggere un PNG scritto a meta' (crash del TextureCooker, 23/09/2026)."""
    d = os.path.join(ROOT, "build", "tmp_save"); os.makedirs(d, exist_ok=True)     # fuori dalla mod, stesso disco
    tmp = os.path.join(d, os.path.basename(path))
    im.save(tmp, **kw)
    os.replace(tmp, path)


def save(arr, name, mode="RGB"):
    arr = np.clip(arr, 0, 1)
    im = Image.fromarray((arr * 255 + 0.5).astype(np.uint8)).convert(mode) if mode != 'RGB' else Image.fromarray((arr * 255 + 0.5).astype(np.uint8))
    save_atomic(im, os.path.join(OUT, name), optimize=True)


def srgb2lin(c): return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
def lin2srgb(c): return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0), 1 / 2.4) - 0.055)


def grade(rgb, brightness=1.0, saturation=1.0, tint=(1, 1, 1), contrast=1.0):
    lin = srgb2lin(rgb) * brightness * np.array(tint, np.float32)
    lum = (lin * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    lin = lum + (lin - lum) * saturation
    if contrast != 1.0:
        m = lum.mean()
        lin = m + (lin - m) * contrast
    return lin2srgb(np.clip(lin, 0, 1))


def height_to_ao(h, radius_px=12, strength=1.2):
    """AO approssimata: quanto il punto sta sotto la media locale dell'altezza."""
    im = Image.fromarray((h * 255).astype(np.uint8))
    blur = np.asarray(im.filter(ImageFilter.GaussianBlur(radius_px))).astype(np.float32) / 255
    return np.clip(1 - (blur - h) * strength * 2, 0.35, 1)


def height_to_normal(h, strength=2.0):
    gy, gx = np.gradient(h)
    n = np.dstack([-gx * strength * h.shape[1] / 256, gy * strength * h.shape[0] / 256, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5          # verde = +dH/dv -> convenzione OpenGL come le texture vanilla


def cc0_set(asset, res, src_res, out_name, color_kw=None, rough_mul=1.0, rough_add=0.0, color_fn=None):
    base = os.path.join(CC0, asset, f"{asset}_{src_res}-JPG_")
    col = load(base + "Color.jpg", "RGB", res)
    if color_fn:
        col = color_fn(col, base, res)
    if color_kw:
        col = grade(col, **color_kw)
    save(col, f"{out_name}_b.color.png")
    save(load(base + "NormalGL.jpg", "RGB", res), f"{out_name}_nm.normal.png")
    r = load(base + "Roughness.jpg", "L", res) * rough_mul + rough_add
    save(r, f"{out_name}_r.data.png", "L")
    if os.path.exists(base + "AmbientOcclusion.jpg"):
        ao = load(base + "AmbientOcclusion.jpg", "L", res)
    else:
        ao = height_to_ao(load(base + "Displacement.jpg", "L", res))
    save(ao, f"{out_name}_ao.data.png", "L")
    print("ok", out_name)


def fbm(size, octaves=6, base_cells=4, seed=0, persistence=0.55):
    """rumore frattale tileable (somma di griglie di valori interpolate)."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((size, size), np.float32); amp = 1.0; tot = 0.0
    for o in range(octaves):
        cells = base_cells * 2 ** o
        g = rng.random((cells, cells)).astype(np.float32)
        g = np.pad(g, ((0, 1), (0, 1)), mode="wrap")
        im = Image.fromarray(g).resize((size + size // cells, size + size // cells), Image.BICUBIC)
        a = np.asarray(im)[:size, :size]
        acc += a * amp; tot += amp; amp *= persistence
    acc /= tot
    return (acc - acc.min()) / (np.ptp(acc) + 1e-6)


def pavers_moss_color(col, base, res):
    """le fughe della foto CC0 sono verde brillante: le rendo muschio secco/terra come nella foto reale."""
    hsv = np.asarray(Image.fromarray((col * 255).astype(np.uint8)).convert("HSV")).astype(np.float32) / 255
    green = np.clip((hsv[..., 1] - 0.25) * 3, 0, 1) * np.clip(1 - np.abs(hsv[..., 0] - 0.22) * 6, 0, 1)
    dry = grade(col, brightness=0.55, saturation=0.35, tint=(1.08, 1.0, 0.82))
    m = green[..., None]
    return col * (1 - m) + dry * m


def asphalt_breakup_mask(res=2048):
    """maschera macro (UV1 sul piazzale, 230 m): zone rappezzate/crepate e macchie."""
    n = fbm(res, octaves=7, base_cells=3, seed=7)
    patches = np.clip((n - 0.52) * 7, 0, 1)
    n2 = fbm(res, octaves=5, base_cells=12, seed=11)
    stains = np.clip((n2 - 0.7) * 5, 0, 1) * 0.5
    return np.clip(patches + stains, 0, 1)


def flatten_normal(name, k):
    """attenua una normal map (k=0 piatta, 1 invariata)."""
    n = load(os.path.join(OUT, name)) * 2 - 1
    n[..., :2] *= k
    n /= np.linalg.norm(n, axis=2, keepdims=True) + 1e-6
    save(n * 0.5 + 0.5, name)


def remap_rough(name, lo, hi):
    """roughness riportata nell'intervallo [lo, hi] mantenendo la variazione della foto."""
    r = load(os.path.join(OUT, name), "L")
    a, b = np.percentile(r, 2), np.percentile(r, 98)
    save(lo + np.clip((r - a) / (b - a + 1e-6), 0, 1) * (hi - lo), name, "L")


def asphalt_macro_detail(res=2048):
    """variazione macro del piazzale (detailMap su UV1: quadrato di 230 m, riga 0 = y modello +115).
    0.5 = neutro. Toni larghi scoloriti dal sole, corsie consumate dalle ruote dei bus, macchie d'olio
    agli stalli, bordi piu' sporchi vicino ai cordoli (terra e foglie portate dall'acqua)."""
    X0, Y0, SZ = -100.0, -115.0, 230.0
    px = SZ / res
    mx = X0 + (np.arange(res) + 0.5) * px
    my = Y0 + SZ - (np.arange(res) + 0.5) * px
    MX, MY = np.meshgrid(mx, my)
    tone = (fbm(res, octaves=5, base_cells=3, seed=21) - 0.5) * 0.16          # +-8% su decine di metri
    tone += (fbm(res, octaves=6, base_cells=16, seed=22) - 0.5) * 0.07        # chiazze di qualche metro
    out = 0.5 + tone
    # corsie dei bus: due coppie di tracce (scartamento 2.0 m) lungo le corsie di marcia, leggermente lucidate
    wob = lambda seed, amp: np.interp(mx, np.linspace(X0, X0 + SZ, 40), np.random.default_rng(seed).normal(0, amp, 40))
    for yc, seed in ((18.0, 31), (-33.5, 32), (-11.0, 33)):
        yl = yc + wob(seed, 0.5)[None, :]
        d = np.abs(MY - yl)
        track = np.exp(-((d - 1.0) / 0.45) ** 2)                                 # le due ruote
        drip = np.exp(-(d / 0.5) ** 2)                                           # olio al centro della corsia
        along = np.clip((MX + 95) / 10, 0, 1) * np.clip((112 - MX) / 10, 0, 1)
        out += (-0.04 * track + -0.03 * drip) * along
    # sporco lungo i bordi: si stima con la distanza dal perimetro dell'asfalto (niente geometria qui:
    # uso il rettangolo del piazzale, i cordoli interni li sporcano i decal)
    edge = np.minimum.reduce([np.abs(MY - 47.5), np.abs(MY + 47.5), np.abs(MX + 95), np.abs(MX - 119)])
    out -= 0.06 * np.exp(-edge / 1.8) * (0.6 + 0.8 * fbm(res, octaves=4, base_cells=24, seed=23))
    return np.clip(out, 0, 1)


def photo_set(src, out_name, res=None, normal_strength=1.2, rough_base=0.88):
    """texture fotografiche dell'edificio: base color + mappe derivate dalla luminanza."""
    im = Image.open(src).convert("RGB")
    if res:
        im = im.resize((res, res), Image.LANCZOS)
    col = np.asarray(im).astype(np.float32) / 255
    save(col, f"{out_name}_b.color.png")
    if im.size[0] > 2048:                      # mappe derivate a 2K: il dettaglio lo da' gia' il colore
        im = im.resize((2048, 2048), Image.LANCZOS)
        col = np.asarray(im).astype(np.float32) / 255
    lum = (col * np.array([0.299, 0.587, 0.114], np.float32)).sum(-1)
    blur = np.asarray(Image.fromarray((lum * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32) / 255
    detail = np.clip(0.5 + (lum - blur) * 1.5, 0, 1)
    save(height_to_normal(detail, normal_strength), f"{out_name}_nm.normal.png")
    hsv = np.asarray(im.convert("HSV")).astype(np.float32) / 255
    rough = rough_base - hsv[..., 1] * 0.18 - (detail - 0.5) * 0.2      # vernice spray un po' piu' liscia
    save(np.clip(rough, 0.45, 1.0), f"{out_name}_r.data.png", "L")
    save(height_to_ao(detail, 8, 0.8), f"{out_name}_ao.data.png", "L")
    print("ok", out_name)


def enhance_arches(src, dst_png, wall_w=22.0, wall_h=4.6, v0=0.34, v1=0.66, grain_tile=1.2):
    """facciata con archi (texture dipinta della v0.3): grana d'intonaco fotografica, scrostature,
    umidita' di risalita e colature. La facciata usa la fascia v0..v1 della texture (wall_w x wall_h metri)."""
    base = Image.open(src).convert("RGB")
    W, H = base.size
    col = np.asarray(base).astype(np.float32) / 255
    # le macchie dipinte della v0.3 stanno tra il giallo dell'intonaco e il marrone degli sguinci:
    # le riporto al giallo pieno (restano sguinci e vani neri)
    Y = np.array([0.90, 0.74, 0.35], np.float32); R = np.array([0.65, 0.35, 0.16], np.float32)
    t = ((col - Y) @ (R - Y)) / float((R - Y) @ (R - Y))
    smudge = ((t < 0.72) & (col.max(-1) > 0.25))[..., None]
    col = np.where(smudge, Y, col)
    ppm_u, ppm_v = W / wall_w, (v1 - v0) * H / wall_h                  # pixel per metro
    # grana: passa-alto della foto CC0, piastrellata a ~1.2 m
    pl = Image.open(os.path.join(CC0, "PaintedPlaster018", "PaintedPlaster018_2K-JPG_Color.jpg")).convert("L")
    tw, th = max(8, int(grain_tile * ppm_u)), max(8, int(grain_tile * ppm_v))
    pl = np.asarray(pl.resize((tw, th), Image.LANCZOS)).astype(np.float32) / 255
    pl = np.tile(pl, (H // th + 1, W // tw + 1))[:H, :W]
    hp = pl - np.asarray(Image.fromarray((pl * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32) / 255
    out = col * (1 + hp[..., None] * 0.9)
    out *= (0.95 + 0.1 * fbm(max(W, H), octaves=5, base_cells=6, seed=9)[:H, :W])[..., None]   # intonaco scolorito a chiazze
    # quota in metri sulla facciata (0 = piede del muro), per righe
    y = np.arange(H, dtype=np.float32)
    zm = (((1 - v0) * H - y) / ppm_v)[:, None]
    S = max(W, H)
    n1 = fbm(S, octaves=6, base_cells=24, seed=3)[:H, :W]
    n2 = fbm(S, octaves=4, base_cells=64, seed=4)[:H, :W]
    # scrostature: macchie organiche, piu' frequenti in alto (sotto il cornicione) e alla base
    bias = np.clip(1 - (wall_h - zm) / 1.3, 0, 1) * 0.2 + np.clip(1 - zm / 0.8, 0, 1) * 0.14
    peel = np.clip((n1 * 0.7 + n2 * 0.3 + bias - 0.80) * 14, 0, 1)[..., None]
    under = np.array([0.66, 0.62, 0.53], np.float32) * (0.85 + 0.25 * n2[..., None])
    edge = np.clip(peel * (1 - peel) * 4, 0, 1)                       # bordo scuro del distacco
    out = out * (1 - peel) + under * peel
    out *= 1 - edge * 0.15
    # umidita' di risalita alla base
    dirt = np.array([0.30, 0.29, 0.22], np.float32)
    grime = (np.clip(1 - zm / (0.5 + 0.6 * n1), 0, 1) * 0.5)[..., None]
    out = out * (1 - grime) + dirt * grime
    # colature dal cornicione: larghe 5-20 cm, lunghe 0.5-2.5 m
    rng = np.random.default_rng(5)
    cols = max(8, int(wall_w / 0.12))
    sv = rng.random(cols).astype(np.float32)
    streak = np.asarray(Image.fromarray((sv[None, :] * 255).astype(np.uint8)).resize((W, 1), Image.BICUBIC)).astype(np.float32)[0] / 255
    length = np.asarray(Image.fromarray((rng.random(cols)[None, :] * 255).astype(np.uint8)).resize((W, 1), Image.BICUBIC)).astype(np.float32)[0] / 255
    st = np.clip((streak - 0.72) * 5, 0, 1)[None, :] * np.clip(1 - (wall_h - zm) / (0.5 + 2.0 * length[None, :]), 0, 1)
    st = (st * (0.7 + 0.3 * n2))[..., None] * 0.3
    out = out * (1 - st) + dirt * st
    Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(dst_png)
    return dst_png


def willow_strands(W=2048, H=2048, ncol=8, seed=17):
    """atlante di 8 "tende" di salice piangente (rametti pendenti con foglie lanceolate), disegnato in 2x e ridotto.
    Ogni colonna copre ~0.9 m x 6.5 m di tenda: la cima e' in alto (v=1)."""
    from PIL import ImageDraw
    rng = np.random.default_rng(seed)
    S = 2
    col_im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(col_im)
    cw = W * S // ncol
    # verde pieno e piu' scuro (Street View set 2022), qualche foglia giallina e il rovescio argentato
    greens = np.array([[70, 100, 34], [84, 114, 40], [100, 128, 46], [58, 84, 30], [112, 134, 54], [64, 92, 38]], np.float32)
    silver = np.array([128, 142, 104], np.float32)
    for c in range(ncol):
        x0 = c * cw + cw / 2
        ntw = rng.integers(7, 11)                                 # piu' rametti per tenda
        for k in range(ntw):
            xo = x0 + rng.uniform(-0.38, 0.38) * cw
            amp = rng.uniform(4, 14) * S; ph = rng.uniform(0, 6); fr = rng.uniform(1.5, 3.5) / (H * S)
            y_end = H * S * rng.uniform(0.55, 1.0)                # non tutti arrivano in fondo
            ys = np.arange(0, y_end, 3 * S)
            xs = xo + amp * np.sin(ys * fr * 2 * np.pi + ph) + (ys / (H * S)) * rng.uniform(-18, 18) * S
            w0 = rng.uniform(2.2, 3.2) * S
            for i in range(len(ys) - 1):                          # rametto: marrone-verde, sempre piu' sottile
                w = max(1, int(w0 * (1 - 0.7 * ys[i] / (H * S))))
                d.line([(xs[i], ys[i]), (xs[i + 1], ys[i + 1])], fill=(86, 78, 44, 255), width=w)
            # foglie: ogni 9-15 px, alternate, pendenti di 12-40 gradi rispetto al rametto
            y = rng.uniform(4, 12) * S; side = 1
            while y < y_end - 10 * S:
                i = min(int(y / (3 * S)), len(xs) - 1)
                px, py = xs[i], ys[i]
                Lf = rng.uniform(26, 44) * S * (1 - 0.25 * y / (H * S)); Wf = Lf * rng.uniform(0.14, 0.2)
                ang = math.radians(90 + side * rng.uniform(12, 40))   # 90 = verso il basso
                ca, sa = math.cos(ang), math.sin(ang)
                pts = []
                for t in np.linspace(0, 1, 9):                    # lanceolata: larga a 1/3, punta sottile
                    wdt = Wf * (math.sin(math.pi * t) ** 0.8) * (1.2 - 0.4 * t)
                    pts.append((t * Lf, wdt / 2))
                pts = pts + [(x, -y2) for x, y2 in reversed(pts)]
                poly = [(px + x * ca - yy * sa, py + x * sa + yy * ca) for x, yy in pts]
                g = greens[rng.integers(len(greens))] * rng.uniform(0.85, 1.1)
                if rng.random() < 0.18:
                    g = silver * rng.uniform(0.9, 1.05)           # rovescio argentato delle foglie
                d.polygon(poly, fill=tuple(int(v) for v in np.clip(g, 0, 255)) + (255,))
                side = -side
                y += rng.uniform(9, 15) * S
    im = col_im.resize((W, H), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32) / 255
    rgb, alpha = a[..., :3], a[..., 3]
    # bordi: premoltiplico verso il colore medio per evitare aloni scuri col mip-mapping
    mean = (rgb * alpha[..., None]).sum((0, 1)) / (alpha.sum() + 1e-6)
    rgb = np.where(alpha[..., None] > 0.02, rgb / np.maximum(alpha[..., None], 1e-3), mean)
    rgb = np.clip(rgb, 0, 1)
    save(rgb, "t_ti_willow_leaves_b.color.png")
    save(alpha, "t_ti_willow_leaves_o.data.png", "L")
    h = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))).astype(np.float32) / 255
    save(height_to_normal(h, 0.8), "t_ti_willow_leaves_nm.normal.png")
    lum = rgb.mean(-1)
    save(np.clip(0.72 - (lum - lum.mean()) * 0.6, 0.45, 0.9), "t_ti_willow_leaves_r.data.png", "L")
    print("ok willow")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[1:])
    run = lambda k: not only or k in only

    if run("asphalt"):
        # asfalto vecchio e asciutto: albedo lineare ~0.12, roughness 0.8-0.95 (prima era 0.55: sembrava bagnato)
        cc0_set("Asphalt031", 2048, "4K", "t_ti_asphalt", dict(brightness=0.62, saturation=0.45, tint=(1.03, 1.0, 0.96)))
        remap_rough("t_ti_asphalt_r.data.png", 0.80, 0.95)
        flatten_normal("t_ti_asphalt_nm.normal.png", 0.55)
        cc0_set("Asphalt026C", 2048, "2K", "t_ti_asphalt_cracked", dict(brightness=1.9, saturation=0.45, contrast=0.85, tint=(1.02, 1.0, 0.97)))
        remap_rough("t_ti_asphalt_cracked_r.data.png", 0.78, 0.95)
        flatten_normal("t_ti_asphalt_cracked_nm.normal.png", 0.7)
        save(asphalt_breakup_mask(), "t_ti_asphalt_breakup_o.data.png", "L")
        # RGB anche se e' grigia: un PNG a un canale diventa una texture solo-rosso e il detailMap tinge di rosso
        m = asphalt_macro_detail()
        save(np.dstack([m, m, m]), "t_ti_asphalt_macro_detail_b.data.png", "RGB")
    if run("willow"):
        willow_strands()
    if run("pavers"):
        # marciapiedi: autobloccanti rettangolari grigio-rossastri sbiaditi (Street View 2022, lato sud-est)
        cc0_set("PavingStones036", 2048, "4K", "t_ti_pavers_moss", dict(brightness=0.95, saturation=1.0, tint=(1.15, 0.86, 0.74)),
                color_fn=pavers_moss_color)
        cc0_set("PavingStones099", 2048, "4K", "t_ti_pavers", dict(brightness=0.62, saturation=0.9, tint=(1.04, 1.0, 0.94)))
    if run("concrete"):
        cc0_set("Concrete026", 1024, "2K", "t_ti_curb", dict(brightness=1.0, saturation=0.6))
        cc0_set("Plaster007", 1024, "2K", "t_ti_pillar", dict(brightness=0.82, saturation=0.3))
        cc0_set("Concrete035", 1024, "2K", "t_ti_roof", dict(brightness=0.9, saturation=0.6))
    if run("stone"):
        cc0_set("PaintedPlaster018", 2048, "2K", "t_ti_plaster_yellow", dict(brightness=0.95, saturation=0.75))
    if run("building"):
        E = os.path.join(ORIG_TEX, "edificio")
        photo_set(os.path.join(ROOT, "build", "bld_front_4k.png") if os.path.exists(os.path.join(ROOT, "build", "bld_front_4k.png"))
                  else os.path.join(E, "Mura Edificio Dietro.png"), "t_ti_bld_front")
        photo_set(os.path.join(E, "Mura Edificio Sinistra.png"), "t_ti_bld_left")
        os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
        photo_set(enhance_arches(os.path.join(E, "MuraEdificio.png"), os.path.join(ROOT, "build", "bld_arches_enh.png")),
                  "t_ti_bld_arches", normal_strength=1.0)
        photo_set(os.path.join(E, "wildtextures-grunge-graffiti-street-wall.jpg"), "t_ti_bld_graffiti", res=2048)
