"""Scarica le tile di elevazione pubbliche AWS Terrain Tiles (formato terrarium) attorno al terminal
e le cuce in un array numpy (metri s.l.m.)."""
import math, os, io, sys, urllib.request
import numpy as np
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

LAT0, LON0 = 41.6043, 14.2463          # centro piazzale ex terminal (Le Piane, Isernia)
OUT = os.path.join(os.path.dirname(__file__), "..", "src", "dem")

def tile_xy(lat, lon, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n

def fetch(z, x, y):
    fn = os.path.join(OUT, f"t_{z}_{x}_{y}.png")
    if not os.path.exists(fn):
        u = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
        data = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "TerminalIsernia-mod"}), timeout=60).read()
        open(fn, "wb").write(data)
    a = np.asarray(Image.open(fn).convert("RGB"), dtype=np.float64)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768

def mosaic(z, half_km):
    m_per_px = 156543.03392 * math.cos(math.radians(LAT0)) / 2 ** z
    cx, cy = tile_xy(LAT0, LON0, z)
    r = half_km * 1000 / (m_per_px * 256)
    x0, x1 = int(math.floor(cx - r)), int(math.floor(cx + r))
    y0, y1 = int(math.floor(cy - r)), int(math.floor(cy + r))
    jobs = [(z, x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    with ThreadPoolExecutor(8) as ex:
        tiles = list(ex.map(lambda j: fetch(*j), jobs))
    W, H = (x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256
    arr = np.zeros((H, W))
    for (zz, x, y), t in zip(jobs, tiles):
        arr[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = t
    # posizione (in pixel del mosaico) del centro del terminal
    px, py = (cx - x0) * 256, (cy - y0) * 256
    np.savez_compressed(os.path.join(OUT, f"dem_z{z}.npz"), h=arr, px=px, py=py, m_per_px=m_per_px)
    print(f"z{z}: {len(jobs)} tile, {W}x{H}px, {m_per_px:.2f} m/px, centro px=({px:.1f},{py:.1f}), "
          f"quota min/max {arr.min():.0f}/{arr.max():.0f} m, quota centro {arr[int(py), int(px)]:.1f} m")

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    mosaic(15, 2.6)   # dettaglio vicino (~3.6 m/px) per il terreno principale 4 km
    mosaic(12, 16)    # orizzonte (~29 m/px) per lo sfondo montuoso ~30 km
