"""Mini client per il server MCP integrato in BeamNG.drive (http://127.0.0.1:29292/mcp).

  python tools/bng.py call <tool> '{"arg": 1}'
  python tools/bng.py lua "return be:getObjectCount()"
  python tools/bng.py shot <file.jpg> [scale]       # screenshot scaricato in locale
  python tools/bng.py cam <bookmark>                # camera libera su un CameraBookmark del livello
Usato per i test automatici della mappa (caricamento, log, inquadrature, screenshot).
"""
import json, sys, time, base64, urllib.request

URL = "http://127.0.0.1:29292/mcp"
_id = 0


def call(name, args=None, timeout=60):
    global _id
    _id += 1
    body = json.dumps({"jsonrpc": "2.0", "id": _id, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}).encode()
    r = urllib.request.urlopen(urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"}), timeout=timeout)
    res = json.loads(r.read().decode("utf8", "replace"))
    if "error" in res:
        raise RuntimeError(res["error"])
    c = res["result"]["content"][0]
    if res["result"].get("isError"):
        raise RuntimeError(c.get("text"))
    return c


def text(name, args=None, **kw):
    return call(name, args, **kw).get("text", "")


def lua(code):
    return text("run_lua", {"code": code})


def shot(path, scale=0.6, tries=40):
    call("screenshot_image", {"scale": scale})
    for _ in range(tries):
        time.sleep(0.5)
        c = call("screenshot_image", {"scale": scale})
        if c.get("type") == "image":
            open(path, "wb").write(base64.b64decode(c["data"]))
            return path
    raise RuntimeError("screenshot non arrivato")


def cam_bookmark(name, fov=60):
    """camera libera alla posa di un CameraBookmark (rotationMatrix = assi X,Y,Z; la camera guarda lungo +Y)."""
    js = lua(f"local o=scenetree.findObject('{name}'); if not o then return 'nil' end; "
             "local p=o:getPosition(); local q=quat(o:getRotation()); return jsonEncode({p={p.x,p.y,p.z},q={q.x,q.y,q.z,q.w}})")
    d = json.loads(js)
    return text("set_free_camera", {"pos": dict(zip("xyz", d["p"])), "rot": dict(zip("xyzw", d["q"])), "fov": fov})


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "call":
        print(json.dumps(call(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}))[:4000])
    elif cmd == "lua":
        print(lua(sys.argv[2]))
    elif cmd == "shot":
        print(shot(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.6))
    elif cmd == "cam":
        print(cam_bookmark(sys.argv[2]))
