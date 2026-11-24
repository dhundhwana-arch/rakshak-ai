import os, re
from dotenv import load_dotenv
load_dotenv()

class AIAgent:
    HIGH_RISK_PHRASES = [("digital arrest", 45, "Digital Arrest Threat"), ("share otp", 40, "OTP Theft Attempt"), ("upi pin", 40, "UPI PIN Request"), ("account will be blocked", 35, "Account Suspension Fear"), ("account is blocked", 35, "Account Suspension Fear"), ("kyc is blocked", 35, "Fake KYC Threat"), ("kyc suspended", 35, "Fake KYC Threat"), ("update kyc", 30, "Fake KYC Lure"), ("electricity will be disconnected", 40, "Utility Disconnection Scam"), ("won a lottery", 35, "Lottery / Prize Lure"), ("kbc lottery", 40, "KBC Lottery Scam"), ("processing fee", 30, "Advance-Fee Request"), ("customs parcel", 35, "Fake Customs Scam"), ("cbi", 25, "Authority Impersonation"), ("police case", 25, "Legal Threat")]
    KEYWORD_WEIGHTS = {"otp": (20, "OTP Mention"), "kyc": (20, "KYC Trigger"), "urgent": (15, "Urgency"), "immediately": (15, "Urgency"), "disconnect": (20, "Disconnection Threat"), "lottery": (25, "Lottery Lure"), "prize": (20, "Prize Lure"), "arrest": (25, "Legal Fear"), "suspended": (20, "Account Threat"), "blocked": (18, "Account Threat"), "verify": (12, "Verification Lure"), "refund": (12, "Refund Lure"), "apk": (20, "APK Download Lure")}
    URL_REGEX = re.compile(r"https?://\S+|\b(?:bit\.ly|tinyurl\.com|t\.me)/\S+", re.IGNORECASE)

    def __init__(self):
        self.gemini_active = False
        self.client = None

    def analyze_text(self, text: str) -> dict:
        cleaned = (text or "").strip()
        lower = cleaned.lower()
        score, triggers, matched = 0, [], []
        for phrase, w, lbl in self.HIGH_RISK_PHRASES:
            if phrase in lower:
                score += w; matched.append(phrase)
                if lbl not in triggers: triggers.append(lbl)
        for kw, (w, lbl) in self.KEYWORD_WEIGHTS.items():
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                score += w; matched.append(kw)
                if lbl not in triggers: triggers.append(lbl)
        has_url = bool(self.URL_REGEX.search(cleaned))
        if has_url and score > 0:
            score += 20; triggers.append("Suspicious Link With Scam Language")
        score = min(score, 100)
        if score >= 65:
            lv, cat, guj = "HIGH", "Likely Financial / Social Engineering Scam", "Aa message ma scam na spast sanketo malya chhe. Link par click na karo ane OTP/UPI PIN share na karo."
            steps = ["Do not click any link or install any APK", "Never share OTP, UPI PIN, or bank details", "Block sender & report on 1930 or cybercrime.gov.in"]
        elif score >= 30:
            lv, cat, guj = "MEDIUM", "Suspicious / Needs Verification", "Aa message thodo shankaspad lage chhe. Official website ya bank helpline par thi khatri karo."
            steps = ["Verify independently via official app or helpline", "Avoid clicking unverified links"]
        else:
            lv, cat, guj = "SAFE", "No Obvious Scam Indicators Detected", "Aa message ma koi khas scam keyword nathi malya. Chhata pan anjan vyakti sathe OTP share na karvo."
            steps = ["No immediate scam indicators found; stay cautious with unknown senders"]
        return {"scam_category": cat, "risk_score": score, "ai_risk_score": score, "risk_level": lv, "psychological_triggers": triggers, "matched_indicators": sorted(set(matched)), "contains_url": has_url, "explanation_gujarati": guj, "action_steps": steps, "analysis_engine": "heuristic_rules", "gemini_active": False, "confidence": "Medium (Rule-Based Heuristics)", "limitations": "Rule-based keyword & pattern analysis (not live Gemini LLM inference); subtle or novel scams may be missed."}

    def analyze_image(self, file_path: str) -> dict:
        return {"mode": "demo", "is_demo": True, "filename": os.path.basename(file_path or "image"), "scam_category": "Fake Screenshot / Digital Arrest Scam (DEMO SIMULATION)", "risk_score": 90, "ai_risk_score": 90, "risk_level": "HIGH", "explanation_gujarati": "DEMO MODE: Aa hal predefined sample response chhe (real image recognition active nathi).", "action_steps": ["Call 1930 (National Cyber Crime Helpline)", "Report at cybercrime.gov.in", "Do not transfer money or share OTP"], "analysis_engine": "demo_stub", "gemini_active": False, "confidence": "Demo Only (Not Real Image Analysis)", "limitations": "Simulated demo endpoint — uploaded image pixels are NOT analyzed."}
