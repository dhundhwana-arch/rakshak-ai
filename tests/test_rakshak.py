import io, os, tempfile, unittest, zipfile
from fastapi.testclient import TestClient
os.environ["RAKSHAK_DB_PATH"] = os.path.join(tempfile.gettempdir(), "test_rakshak_v3.db")
if os.path.exists(os.environ["RAKSHAK_DB_PATH"]): os.remove(os.environ["RAKSHAK_DB_PATH"])
from main import app

def make_apk(txt: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z: z.writestr("AndroidManifest.xml", txt.encode())
    return b.getvalue()

class TestRakshakAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.client = TestClient(app)
    def test_health(self):
        r = self.client.get("/api/health"); self.assertEqual(r.status_code, 200); self.assertFalse(r.json()["modules"]["gemini_active"])
    def test_text_benign_and_scam(self):
        r1 = self.client.post("/api/scan/text", data={"message": "Hello mom, I reached home safely and will call you after dinner."})
        self.assertEqual(r1.json()["risk_level"], "SAFE")
        r2 = self.client.post("/api/scan/text", data={"message": "URGENT: Your bank account KYC is blocked! Click http://bit.ly/kyc-now and share OTP."})
        self.assertEqual(r2.json()["risk_level"], "HIGH")
    def test_url_ssrf_and_phishing(self):
        for bad in ["http://127.0.0.1:8000/", "http://localhost/admin", "http://169.254.169.254/latest/meta-data/", "file:///etc/passwd"]:
            self.assertEqual(self.client.post("/api/scan/url", data={"url": bad}).status_code, 400)
        self.assertEqual(self.client.post("/api/scan/url", data={"url": "http://sbi-kyc-verify-now.xyz/login"}).json()["risk_level"], "HIGH")
        self.assertEqual(self.client.post("/api/scan/url", data={"url": "https://api.github.com/repos"}).json()["risk_level"], "SAFE")
    def test_apk_and_image_and_history(self):
        self.assertEqual(self.client.post("/api/scan/apk", files={"file": ("a.txt", b"x", "text/plain")}).status_code, 400)
        self.assertEqual(self.client.post("/api/scan/apk", files={"file": ("clean.apk", make_apk("<manifest/>"), "application/vnd.android.package-archive")}).json()["risk_level"], "SAFE")
        self.assertEqual(self.client.post("/api/scan/apk", files={"file": ("bad.apk", make_apk("READ_SMS BIND_ACCESSIBILITY_SERVICE https://evil.firebaseio.com"), "application/vnd.android.package-archive")}).json()["risk_level"], "HIGH")
        self.assertTrue(self.client.post("/api/scan/image", files={"file": ("s.png", b"\x89PNG", "image/png")}).json()["is_demo"])
        self.assertGreaterEqual(len(self.client.get("/api/history").json()["items"]), 1)

if __name__ == "__main__": unittest.main()
