import json, os, uuid
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from core.ai_agent import AIAgent
from core.apk_analyzer import APKAnalyzer
from core.database import RakshakDatabase
from core.url_scanner import URLScanner

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR, UPLOAD_DIR = BASE_DIR / "web", BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_APK_BYTES, CHUNK = 25 * 1024 * 1024, 64 * 1024

app = FastAPI(title="RAKSHAK AI — Public Cyber Safety Platform", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
url_scanner, apk_analyzer, ai_agent = URLScanner(), APKAnalyzer(), AIAgent()
db = RakshakDatabase(os.getenv("RAKSHAK_DB_PATH", str(BASE_DIR / "rakshak_cache.db")))
if WEB_DIR.exists(): app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

@app.get("/")
def serve_home():
    idx = WEB_DIR / "index.html"
    return FileResponse(str(idx), media_type="text/html") if idx.exists() else {"status": "Rakshak AI Backend is Live!", "version": "3.0.0"}

@app.get("/manifest.json")
def serve_manifest(): return FileResponse(str(WEB_DIR / "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js")
def serve_sw(): return FileResponse(str(WEB_DIR / "sw.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

@app.get("/api/health")
@app.get("/healthz")
def health():
    return {"status": "Rakshak AI Backend is Live!", "version": "3.0.0", "creator": "Divyesh Bambhaniya", "modules": {"url_scanner": True, "apk_analyzer": True, "text_analyzer": True, "database": True, "gemini_active": ai_agent.gemini_active, "image_scanner_mode": "demo"}}

@app.get("/api/history")
def get_history(limit: int = 12): return {"items": db.get_recent_scans(limit=max(1, min(limit, 50)))}

@app.delete("/api/history")
def clear_history(): db.clear_history(); return {"status": "cleared"}

@app.post("/api/scan/url")
def scan_url(url: str = Form(...)):
    cleaned = url.strip()
    if not cleaned: raise HTTPException(status_code=400, detail="Please enter a URL to scan.")
    cached = db.get_cached_url(cleaned)
    if cached:
        data = json.loads(cached[2])
        db.log_scan("url", cleaned, data.get("risk_score", 0), data.get("risk_level", "SAFE"), "cache")
        return {"source": "cache", **data}
    try: result = url_scanner.scan(cleaned)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))
    except Exception: raise HTTPException(status_code=500, detail="URL analysis failed unexpectedly.")
    db.cache_url(cleaned, result["risk_score"], result["risk_level"], json.dumps(result))
    db.log_scan("url", cleaned, result["risk_score"], result["risk_level"], "fresh_scan")
    return {"source": "fresh_scan", **result}

@app.post("/api/scan/text")
def scan_text(message: str = Form(...)):
    cleaned = message.strip()
    if not cleaned: raise HTTPException(status_code=400, detail="Please enter a message.")
    if len(cleaned) > 5000: raise HTTPException(status_code=400, detail="Message exceeds 5000 characters.")
    result = ai_agent.analyze_text(cleaned)
    db.log_scan("text", cleaned[:80], result["risk_score"], result["risk_level"], "fresh_scan")
    return result

@app.post("/api/scan/image")
async def scan_image(file: UploadFile = File(...)):
    _ = await file.read(1024)
    result = ai_agent.analyze_image(file.filename or "image")
    db.log_scan("image", result["filename"], result["risk_score"], "DEMO", "demo")
    return result

@app.post("/api/scan/apk")
async def scan_apk(file: UploadFile = File(...)):
    safe_name = os.path.basename(file.filename or "")
    if not safe_name.lower().endswith(".apk"): raise HTTPException(status_code=400, detail="Please upload a valid .apk file.")
    tmp_path, total = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}", 0
    try:
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk: break
                total += len(chunk)
                if total > MAX_APK_BYTES: raise HTTPException(status_code=413, detail="APK exceeds 25 MB limit.")
                out.write(chunk)
        if total == 0: raise HTTPException(status_code=400, detail="Uploaded APK is empty.")
        result = apk_analyzer.analyze(str(tmp_path), original_filename=safe_name)
        if "error" in result: raise HTTPException(status_code=400, detail=result["error"])
        cached = db.get_cached_apk(result["sha256"])
        if cached:
            cd = json.loads(cached[2]); db.log_scan("apk", safe_name, cd["risk_score"], cd["risk_level"], "cache")
            return {"source": "cache", **cd}
        db.cache_apk(result["sha256"], result["risk_score"], result["risk_level"], json.dumps(result))
        db.log_scan("apk", safe_name, result["risk_score"], result["risk_level"], "fresh_scan")
        return {"source": "fresh_scan", **result}
    finally:
        try:
            if tmp_path.exists(): tmp_path.unlink()
        except OSError: pass
