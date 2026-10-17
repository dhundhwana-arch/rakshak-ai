import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import shutil
import json

from core.url_scanner import URLScanner
from core.apk_analyzer import APKAnalyzer
from core.ai_agent import AIAgent
from core.risk_math import RiskMathEngine
from core.database import RakshakDatabase

app = FastAPI(title="Rakshak AI API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

url_scanner = URLScanner()
apk_analyzer = APKAnalyzer()
ai_agent = AIAgent()
risk_engine = RiskMathEngine()
db = RakshakDatabase()

os.makedirs("uploads", exist_ok=True)

@app.get("/")
def home():
    return {"status": "Rakshak AI Backend is running smoothly!"}

@app.post("/api/scan/url")
def scan_url(url: str = Form(...)):
    cached = db.get_cached_url(url)
    if cached:
        return {
            "source": "cache",
            "url": url,
            "risk_score": cached[0],
            "risk_level": cached[1],
            "details": json.loads(cached[2])
        }

    result = url_scanner.scan(url)
    db.cache_url(url, result["risk_score"], result["risk_level"], json.dumps(result))
    return {"source": "fresh_scan", **result}

@app.post("/api/scan/text")
def scan_text(message: str = Form(...)):
    result = ai_agent.analyze_text(message)
    return result

@app.post("/api/scan/apk")
async def scan_apk(file: UploadFile = File(...)):
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = apk_analyzer.analyze(file_path)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    sha256 = result["sha256"]
    cached = db.get_cached_apk(sha256)
    if cached:
        if os.path.exists(file_path):
            os.remove(file_path)
        return {
            "source": "cache",
            "sha256": sha256,
            "risk_score": cached[0],
            "risk_level": cached[1],
            "details": json.loads(cached[2])
        }

    db.cache_apk(sha256, result["risk_score"], result["risk_level"], json.dumps(result))
    return {"source": "fresh_scan", **result}

@app.post("/api/scan/image")
async def scan_image(file: UploadFile = File(...)):
    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = ai_agent.analyze_image(file_path)
    if os.path.exists(file_path):
        os.remove(file_path)
    return result
