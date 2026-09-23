"""Anteprima dall'alto di uno o piu' .dae (solo per controllo, colori per materiale)."""
import re, sys, hashlib
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}

def tris(path):
    root = ET.parse(path).getroot()
    for g in root.iter("{%s}geometry" % NS["c"]):
        pos = None
        for s in g.iter("{%s}source" % NS["c"]):
            if s.get("id").endswith("-pos"):
                pos = list(map(float, s.find("c:float_array", NS).text.split()))
        for t in g.iter("{%s}triangles" % NS["c"]):
            mat = t.get("material").replace("-material", "")
            ninp = len(t.findall("c:input", NS)); offs = max(int(i.get("offset")) for i in t.findall("c:input", NS)) + 1
            idx = list(map(int, t.find("c:p", NS).text.split()))[::offs]
            for k in range(0, len(idx), 3):
                yield mat, [(pos[3*i], pos[3*i+1], pos[3*i+2]) for i in idx[k:k+3]]

def color(m):
    h = hashlib.md5(m.encode()).digest(); return (60 + h[0] % 196, 60 + h[1] % 196, 60 + h[2] % 196)

if __name__ == "__main__":
    out, files = sys.argv[1], sys.argv[2:]
    allt = [t for f in files for t in tris(f)]
    xs = [p[0] for _, tr in allt for p in tr]; ys = [p[1] for _, tr in allt for p in tr]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys); S = 1600 / max(x1 - x0, y1 - y0)
    im = Image.new("RGB", (int((x1 - x0) * S) + 1, int((y1 - y0) * S) + 1 + 20 * 12), (15, 15, 15)); d = ImageDraw.Draw(im)
    allt.sort(key=lambda t: sum(p[2] for p in t[1]))
    mats = []
    for m, tr in allt:
        if m not in mats: mats.append(m)
        d.polygon([((p[0] - x0) * S, (y1 - p[1]) * S) for p in tr], fill=color(m))
    for i, m in enumerate(mats):
        d.text((5, int((y1 - y0) * S) + 5 + i * 12), m, fill=color(m))
    im.save(out); print(len(allt), "tris", mats, "bbox", round(x0,1), round(x1,1), round(y0,1), round(y1,1))
