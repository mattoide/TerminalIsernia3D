"""Scarica le sorgenti pubbliche usate dalla pipeline (non versionate nel repository).

  python tools/fetch_sources.py            # tutto
  python tools/fetch_sources.py osm cc0    # solo alcune

  dem : AWS Terrain Tiles (terrarium), vedi fetch_dem.py
  osm : estratto OpenStreetMap via Overpass  (c) OpenStreetMap contributors, ODbL
  cc0 : materiali PBR CC0 di ambientCG (https://ambientcg.com)
"""
import os, sys, io, json, zipfile, urllib.request, urllib.parse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UA = {"User-Agent": "TerminalIsernia-mod-build/1.0"}

CC0 = {"PavingStones036": "4K-JPG", "PavingStones099": "4K-JPG", "Asphalt031": "4K-JPG", "Asphalt026C": "2K-JPG",
       "PaintedPlaster018": "2K-JPG", "Concrete035": "2K-JPG", "Concrete040": "2K-JPG"}
BBOX = (41.578, 14.212, 41.631, 14.281)
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://z.overpass-api.de/api/interpreter"]


def fetch_cc0():
    out = os.path.join(ROOT, "src", "cc0", "ambientcg")
    os.makedirs(out, exist_ok=True)
    u = "https://ambientcg.com/api/v2/full_json?id=" + ",".join(CC0) + "&include=downloadData"
    d = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60))
    for a in d["foundAssets"]:
        k = a["assetId"]
        if os.path.isdir(os.path.join(out, k)):
            continue
        dls = a["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
        dl = [x for x in dls if x["attribute"] == CC0[k]][0]
        data = urllib.request.urlopen(urllib.request.Request(dl["fullDownloadPath"], headers=UA), timeout=600).read()
        z = zipfile.ZipFile(io.BytesIO(data))
        for n in z.namelist():
            if n.lower().endswith(".jpg"):
                z.extract(n, os.path.join(out, k))
        print("cc0", k)


def fetch_osm():
    s, w, n, e = BBOX
    parts = ["highway", "building", "landuse", "natural", "leisure", "amenity", "waterway", "railway", "barrier"]
    q = "[out:json][timeout:180];(" + "".join(f'way["{p}"]({s},{w},{n},{e});' for p in parts) + \
        "".join(f'relation["{p}"]({s},{w},{n},{e});' for p in ("landuse", "natural")) + \
        f'node["natural"="tree"]({s},{w},{n},{e}););out body;>;out skel qt;'
    out = os.path.join(ROOT, "src", "osm", "isernia_osm.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    for url in OVERPASS:
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers=UA),
                                          timeout=240).read()
            json.loads(data)
            open(out, "wb").write(data)
            print("osm", url, len(data))
            return
        except Exception as ex:
            print("overpass fallito", url, ex)
    raise SystemExit("nessun server Overpass disponibile")


if __name__ == "__main__":
    what = set(sys.argv[1:]) or {"dem", "osm", "cc0"}
    if "dem" in what:
        import fetch_dem
        os.makedirs(fetch_dem.OUT, exist_ok=True)
        fetch_dem.mosaic(15, 2.6)
        fetch_dem.mosaic(12, 16)
    if "osm" in what:
        fetch_osm()
    if "cc0" in what:
        fetch_cc0()
