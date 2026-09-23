"""Controlli statici sulla mod: json validi, riferimenti a file esistenti (nella mod o nei pacchetti del gioco)."""
import os, re, json, glob, zipfile, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MOD = os.path.join(ROOT, "mod")
GAME = r"D:\Giochi\Steam\steamapps\common\BeamNG.drive"

index = set()
for z in glob.glob(os.path.join(GAME, "content", "**", "*.zip"), recursive=True) + [os.path.join(GAME, "gameengine.zip")]:
    try:
        for n in zipfile.ZipFile(z).namelist():
            index.add(n.lower())
    except Exception:
        pass
for dp, dn, fn in os.walk(MOD):
    for f in fn:
        index.add(os.path.relpath(os.path.join(dp, f), MOD).replace("\\", "/").lower())


def resolves(p):
    p = p.lstrip("/").lower()
    cands = [p, p + ".link"]
    stem, ext = os.path.splitext(p)
    if ext in (".png", ".dds", ".jpg"):
        cands += [stem + e for e in (".dds", ".png", ".jpg", ".dds.link", ".png.link")]
    return any(c in index for c in cands)


bad_json, missing = [], {}
for f in glob.glob(os.path.join(MOD, "**", "*.json"), recursive=True):
    txt = open(f, encoding="utf8").read()
    try:
        if f.endswith(("items.level.json", ".forest4.json")):
            objs = [json.loads(l) for l in txt.splitlines() if l.strip()]
        else:
            objs = [json.loads(txt)]
    except Exception as e:
        bad_json.append((f, str(e))); continue
    for s in re.findall(r'"(/?(?:levels|assets|art)/[^"]+\.(?:png|dds|jpg|dae|ter|cdae))"', txt, re.I):
        if not resolves(s):
            missing.setdefault(s, set()).add(os.path.relpath(f, MOD))
print("json non validi:", bad_json)
print("riferimenti mancanti:", len(missing))
for k, v in sorted(missing.items())[:60]:
    print("  ", k, "<-", sorted(v)[:2])
sys.exit(1 if bad_json or missing else 0)
