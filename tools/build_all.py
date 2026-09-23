"""Ricostruisce l'intera mod: python tools/build_all.py [--zip]

Ordine: export Blender -> texture -> terreno -> livello -> validazione (-> zip in dist/).
Richiede: Python 3 con numpy, scipy, pillow, opencv-python, matplotlib; Blender 5.x; BeamNG.drive 0.39 installato
(per leggere definizioni e materiali degli asset ufficiali riusati).
"""
import os, sys, subprocess, zipfile, json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
PY = sys.executable


def run(*cmd):
    print(">>", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def package():
    info = json.load(open(os.path.join(ROOT, "mod", "levels", "terminal_isernia", "info.json")))
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", "terminal_isernia.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dp, dn, fn in os.walk(os.path.join(ROOT, "mod")):
            for f in fn:
                p = os.path.join(dp, f)
                arc = os.path.relpath(p, os.path.join(ROOT, "mod")).replace("\\", "/")
                comp = zipfile.ZIP_STORED if f.lower().endswith((".png", ".jpg", ".dds")) else zipfile.ZIP_DEFLATED
                z.write(p, arc, compress_type=comp)
    print("zip:", out, os.path.getsize(out) // (1024 * 1024), "MB")


if __name__ == "__main__":
    run(BLENDER, "-b", "src/blender/terminal.blend", "--python", "tools/blender_export.py", "--", "build/shapes", "build/export_meta.json")
    run(BLENDER, "-b", "--factory-startup", "--python", "tools/blender_props.py", "--", "build/shapes")
    run(PY, "tools/build_textures.py")
    run(PY, "tools/build_terrain.py")
    run(BLENDER, "-b", "--factory-startup", "--python", "tools/build_bridges.py", "--", "build/shapes")
    run(PY, "tools/build_backdrop.py")
    run(PY, "tools/build_level.py")
    run(PY, "tools/validate.py")
    if "--zip" in sys.argv:
        package()
