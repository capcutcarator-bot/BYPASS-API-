"""
Bypass API — main.py

Notun shortener support korte, bypassers/ folder e ekta notun .py file
felle e hoye jay (DOMAIN + async bypass() function shoho). Ei file
touch korার dorkar nai. Files upload/delete/list Telegram admin bot
(admin_bot.py) theke /admin/* endpoint diye remote-e kora jay.
"""

import importlib.util
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Header, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from config import API_KEY

BYPASSERS_DIR = os.path.join(os.path.dirname(__file__), "bypassers")

# domain-substring -> module object
_registry: dict[str, object] = {}


def load_bypassers():
    """bypassers/ folder er shob .py file scan kore reload kore."""
    global _registry
    new_registry = {}

    for fname in os.listdir(BYPASSERS_DIR):
        if not fname.endswith(".py") or fname == "__init__.py":
            continue

        mod_name = f"bypassers.{fname[:-3]}"
        path = os.path.join(BYPASSERS_DIR, fname)

        spec = importlib.util.spec_from_file_location(mod_name, path)
        module = importlib.util.module_from_spec(spec)
        try:
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"[!] Failed to load {fname}: {e}")
            continue

        domain = getattr(module, "DOMAIN", None)

        # Function naming flexible: bypass(), bypass_earnlinks(), bypass_vplink() etc.
        # sob e cholbe -- shudhu naam "bypass" diye shuru hote hobe.
        bypass_fn = getattr(module, "bypass", None)
        if not callable(bypass_fn):
            for attr_name in dir(module):
                if attr_name.startswith("bypass") and callable(getattr(module, attr_name)):
                    bypass_fn = getattr(module, attr_name)
                    break

        # DOMAIN na dile filename theke guess kora hoy (e.g. earnlink.py -> "earnlink")
        if not domain:
            domain = fname[:-3].replace("_bypass", "").replace("bypass_", "")

        if not callable(bypass_fn):
            print(f"[!] Skipped {fname}: no bypass*() function found")
            continue

        # Registry shob shomoy module.bypass() diye call kore, tai jekono
        # naam er function hok, oita e module.bypass e map kore rakhi.
        module.bypass = bypass_fn

        domains = domain if isinstance(domain, list) else [domain]
        for d in domains:
            new_registry[d] = module

    _registry = new_registry
    print(f"[+] Loaded bypassers: {list(_registry.keys())}")


def check_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_bypassers()
    yield


app = FastAPI(title="Link Bypass API", lifespan=lifespan)


@app.get("/")
def health():
    return {"status": "ok", "supported": list(_registry.keys())}


@app.get("/bypass")
async def bypass(url: str = Query(...)):
    matched_module = None
    for d, module in _registry.items():
        if d in url:
            matched_module = module
            break

    if not matched_module:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Unsupported shortener"},
        )

    try:
        result = await matched_module.bypass(url)
        return {"status": "success", "result": result}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ---------------- Admin endpoints (protected by X-API-Key) ----------------

@app.get("/admin/list")
def admin_list(x_api_key: str = Header(None)):
    check_key(x_api_key)
    return {"files": os.listdir(BYPASSERS_DIR)}


@app.post("/admin/upload")
async def admin_upload(file: UploadFile = File(...), x_api_key: str = Header(None)):
    check_key(x_api_key)
    if not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files allowed")

    dest = os.path.join(BYPASSERS_DIR, file.filename)
    with open(dest, "wb") as f:
        f.write(await file.read())

    load_bypassers()
    return {"status": "success", "message": f"{file.filename} uploaded & loaded", "supported": list(_registry.keys())}


@app.delete("/admin/delete")
def admin_delete(filename: str = Query(...), x_api_key: str = Header(None)):
    check_key(x_api_key)
    path = os.path.join(BYPASSERS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    os.remove(path)
    load_bypassers()
    return {"status": "success", "message": f"{filename} deleted", "supported": list(_registry.keys())}


@app.post("/admin/reload")
def admin_reload(x_api_key: str = Header(None)):
    check_key(x_api_key)
    load_bypassers()
    return {"status": "success", "supported": list(_registry.keys())}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
        
