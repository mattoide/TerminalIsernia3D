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
import os, sys
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


def save(arr, name, mode="RGB"):
    arr = np.clip(arr, 0, 1)
    im = Image.fromarray((arr * 255 + 0.5).astype(np.uint8)).convert(mode) if mode != 'RGB' else Image.fromarray((arr * 255 + 0.5).astype(np.uint8))
    im.save(os.path.join(OUT, name), optimize=True)


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
    patches = np.clip((n - 0.58) * 6, 0, 1)
    n2 = fbm(res, octaves=5, base_cells=12, seed=11)
    stains = np.clip((n2 - 0.7) * 5, 0, 1) * 0.5
    return np.clip(patches + stains, 0, 1)


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
    ppm_u, ppm_v = W / wall_w, (v1 - v0) * H / wall_h                  # pixel per metro
    # grana: passa-alto della foto CC0, piastrellata a ~1.2 m
    pl = Image.open(os.path.join(CC0, "PaintedPlaster018", "PaintedPlaster018_2K-JPG_Color.jpg")).convert("L")
    tw, th = max(8, int(grain_tile * ppm_u)), max(8, int(grain_tile * ppm_v))
    pl = np.asarray(pl.resize((tw, th), Image.LANCZOS)).astype(np.float32) / 255
    pl = np.tile(pl, (H // th + 1, W // tw + 1))[:H, :W]
    hp = pl - np.asarray(Image.fromarray((pl * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6))).astype(np.float32) / 255
    out = col * (1 + hp[..., None] * 0.9)
    # quota in metri sulla facciata (0 = piede del muro), per righe
    y = np.arange(H, dtype=np.float32)
    zm = (((1 - v0) * H - y) / ppm_v)[:, None]
    S = max(W, H)
    n1 = fbm(S, octaves=6, base_cells=24, seed=3)[:H, :W]
    n2 = fbm(S, octaves=4, base_cells=64, seed=4)[:H, :W]
    # scrostature: macchie organiche, piu' frequenti in alto (sotto il cornicione) e alla base
    bias = np.clip(1 - (wall_h - zm) / 1.3, 0, 1) * 0.2 + np.clip(1 - zm / 0.8, 0, 1) * 0.14
    peel = np.clip((n1 * 0.7 + n2 * 0.3 + bias - 0.72) * 14, 0, 1)[..., None]
    under = np.array([0.56, 0.54, 0.49], np.float32) * (0.78 + 0.38 * n2[..., None])
    edge = np.clip(peel * (1 - peel) * 4, 0, 1)                       # bordo scuro del distacco
    out = out * (1 - peel) + under * peel
    out *= 1 - edge * 0.25
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
    st = (st * (0.7 + 0.3 * n2))[..., None] * 0.45
    out = out * (1 - st) + dirt * st
    Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(dst_png)
    return dst_png


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    only = set(sys.argv[1:])
    run = lambda k: not only or k in only

    if run("asphalt"):
        cc0_set("Asphalt031", 2048, "4K", "t_ti_asphalt", dict(brightness=0.92, saturation=0.6), rough_mul=0.9, rough_add=0.08)
        cc0_set("Asphalt026C", 2048, "2K", "t_ti_asphalt_cracked", dict(brightness=1.9, saturation=0.5, contrast=0.8), rough_add=0.02)
        save(asphalt_breakup_mask(), "t_ti_asphalt_breakup_o.data.png", "L")
    if run("pavers"):
        cc0_set("PavingStones036", 2048, "4K", "t_ti_pavers_moss", dict(brightness=0.95, saturation=0.8), color_fn=pavers_moss_color)
        cc0_set("PavingStones099", 2048, "4K", "t_ti_pavers", dict(brightness=0.95, saturation=0.9))
    if run("concrete"):
        cc0_set("Concrete040", 1024, "2K", "t_ti_curb", dict(brightness=1.05, saturation=0.35))
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
