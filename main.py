import os
import uuid
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from core.url_scanner import URLScanner
    _url_import_err = None
except Exception as exc:
    URLScanner, _url_import_err = None, str(exc)

try:
    from core.apk_analyzer import APKAnalyzer
    _apk_import_err = None
except Exception as exc:
    APKAnalyzer, _apk_import_err = None, str(exc)

try:
    from core.ai_agent import AIAgent
    _ai_import_err = None
except Exception as exc:
    AIAgent, _ai_import_err = None, str(exc)

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_APK_BYTES = 25 * 1024 * 1024

app = FastAPI(title="RAKSHAK AI", description="Digital Threat Intelligence & Cyber Safety Platform", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

def _safe_init(cls, err):
    if cls is None:
        return None, err
    try:
        return cls(), None
    except Exception as exc:
        return None, str(exc)

url_scanner, url_init_err = _safe_init(URLScanner, _url_import_err)
apk_analyzer, apk_init_err = _safe_init(APKAnalyzer, _apk_import_err)
ai_agent, ai_init_err = _safe_init(AIAgent, _ai_import_err)

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

@app.get("/")
def serve_home():
    index_file = WEB_DIR / "index.html"
    return FileResponse(str(index_file), media_type="text/html") if index_file.exists() else {"status": "Rakshak AI Backend is Live!"}

@app.get("/manifest.json")
def serve_manifest():
    return FileResponse(str(WEB_DIR / "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js")
def serve_sw():
    return FileResponse(str(WEB_DIR / "sw.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

@app.get("/api/health")
@app.get("/healthz")
def health():
    return {"status": "Rakshak AI Backend is Live!", "version": "2.0.0", "modules": {"url_scanner": url_scanner is not None, "apk_analyzer": apk_analyzer is not None, "ai_agent": ai_agent is not None}}

@app.post("/api/scan/url")
def scan_url(url: str = Form(...)):
    cleaned = url.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Please enter a URL to scan.")
    if url_scanner is None:
        return JSONResponse(status_code=503, content={"error": f"URL scanner unavailable: {url_init_err}"})
    try:
        return url_scanner.scan(cleaned)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"URL scan failed: {exc}")

@app.post("/api/scan/text")
def scan_text(message: str = Form(...)):
    cleaned = message.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Please enter a message to analyze.")
    if ai_agent is None:
        return JSONResponse(status_code=503, content={"error": f"Text analysis unavailable: {ai_init_err}"})
    try:
        return ai_agent.analyze_text(cleaned)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Text analysis failed: {exc}")

@app.post("/api/scan/image")
async def scan_image(file: UploadFile = File(...)):
    _ = await file.read(1024)
    return {
        "mode": "demo",
        "filename": os.path.basename(file.filename or "image"),
        "scam_category": "Fake Screenshot / Digital Arrest Scam (Demo Response)",
        "ai_risk_score": 90,
        "explanation_gujarati": "Aa image analysis hal demo mode ma chhe. Fake screenshot ke digital arrest scam jeva sandehaspad message par vishwas na karo.",
        "action_steps": ["Call 1930 (National Cyber Crime Helpline)", "Report at cybercrime.gov.in", "Do not transfer money or share OTP"],
    }

@app.post("/api/scan/apk")
async def scan_apk(file: UploadFile = File(...)):
    if apk_analyzer is None:
        return JSONResponse(status_code=503, content={"error": f"APK analyzer unavailable: {apk_init_err}"})
    safe_name = os.path.basename(file.filename or "sample.apk")
    if not safe_name.lower().endswith(".apk"):
        raise HTTPException(status_code=400, detail="Please upload a valid .apk file.")
    content = await file.read()
    if len(content) > MAX_APK_BYTES:
        raise HTTPException(status_code=413, detail="APK file exceeds 25 MB limit.")
    tmp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    try:
        tmp_path.write_bytes(content)
        return apk_analyzer.analyze(str(tmp_path))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"APK inspection failed: {exc}")
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
