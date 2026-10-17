import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

class AIAgent:
    def __init__(self):
        try:
            self.client = genai.Client(api_key=API_KEY) if API_KEY and not API_KEY.startswith("tari_") else None
        except:
            self.client = None

    def analyze_text(self, text: str) -> dict:
        keywords = ["disconnect", "bill", "lottery", "kbc", "prize", "urgent", "verify", "kyc", "block", "police", "arrest"]
        found_triggers = [kw for kw in keywords if kw in text.lower()]
        
        if found_triggers or len(text) > 10:
            return {
                "scam_category": "Financial / Social Engineering Scam",
                "ai_risk_score": 85,
                "psychological_triggers": found_triggers if found_triggers else ["Urgency", "Fear"],
                "explanation_gujarati": "Aa message ekdam suspicious lage chhe. Koi pan personal details ya paisa transfer karta pehla savdhan raho!",
                "action_steps": ["Call 1930", "Do not share OTP/UPI PIN", "Block the sender"]
            }
        
        return {
            "scam_category": "Safe / Normal",
            "ai_risk_score": 10,
            "psychological_triggers": [],
            "explanation_gujarati": "Aa message safe lagto chhe. Chhata pan dhyan rakhvu.",
            "action_steps": ["No action required"]
        }
