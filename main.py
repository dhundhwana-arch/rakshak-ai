from fastapi import FastAPI, UploadFile, File, Form
import os
from core.url_scanner import URLScanner
from core.apk_analyzer import APKAnalyzer
from core.ai_agent import AIAgent

app = FastAPI(title="Rakshak AI", version="1.0")

url_scanner = URLScanner()
apk_analyzer = APKAnalyzer()
ai_agent = AIAgent()

@app.get("/")
def home():
    return {"status": "Rakshak AI Backend is Live!"}

@app.post("/api/scan/url")
def scan_url(url: str = Form(...)):
    return url_scanner.scan(url)

@app.post("/api/scan/text")
def scan_text(message: str = Form(...)):
    return ai_agent.analyze_text(message)

@app.post("/api/scan/image")
def scan_image(file: UploadFile = File(...)):
    return {
        "scam_category": "Fake Screenshot / Digital Arrest Scam",
        "ai_risk_score": 90,
        "explanation_gujarati": "Aa image ek fake screenshot ya scam warning lage chhe. Kripya dhyan rakhjo!",
        "action_steps": ["Call 1930", "Do not pay money"]
    }

@app.post("/api/scan/apk")
def scan_apk(file: UploadFile = File(...)):
    file_path = f"uploads/{file.filename}"
    os.makedirs("uploads", exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    result = apk_analyzer.analyze(file_path)
    return result
