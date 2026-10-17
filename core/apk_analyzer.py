import hashlib
import re
import zipfile
import os

class APKAnalyzer:
    def __init__(self):
        self.dangerous_permissions = [
            'READ_SMS', 'RECEIVE_SMS', 'SEND_SMS',
            'BIND_ACCESSIBILITY_SERVICE',
            'SYSTEM_ALERT_WINDOW',
            'REQUEST_INSTALL_PACKAGES',
            'READ_CALL_LOG', 'PROCESS_OUTGOING_CALLS',
            'READ_CONTACTS', 'CAMERA'
        ]
        self.tg_token_regex = re.compile(r'bot[0-9]{8,10}:[a-zA-Z0-9_-]{35}')
        self.firebase_regex = re.compile(r'https?://[a-zA-Z0-9_-]+\.firebaseio\.com')
        self.ip_tunnel_regex = re.compile(r'(?:https?://)?(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::[0-9]+)?|[a-zA-Z0-9-]+\.(?:ngrok-free\.app|trycloudflare\.com)')

    def calculate_sha256(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def analyze(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            return {"error": "APK file not found"}

        sha256 = self.calculate_sha256(file_path)
        found_permissions = []
        c2_indicators = {
            "telegram_bots": [],
            "firebase_urls": [],
            "tunnels_or_ips": []
        }

        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                namelist = zf.namelist()
                all_bytes = b""
                for filename in namelist:
                    if filename == 'AndroidManifest.xml' or filename.endswith('.dex'):
                        try:
                            all_bytes += zf.read(filename)
                        except Exception:
                            pass

                if not all_bytes:
                    with open(file_path, 'rb') as f:
                        all_bytes = f.read()

                text_content = all_bytes.decode('latin-1', errors='ignore')

                # Scan Permissions
                for perm in self.dangerous_permissions:
                    if perm in text_content:
                        found_permissions.append(perm)

                # C2 Hunter
                tg_matches = self.tg_token_regex.findall(text_content)
                if tg_matches:
                    c2_indicators["telegram_bots"].extend(list(set(tg_matches)))

                fb_matches = self.firebase_regex.findall(text_content)
                if fb_matches:
                    c2_indicators["firebase_urls"].extend(list(set(fb_matches)))

                ip_matches = self.ip_tunnel_regex.findall(text_content)
                if ip_matches:
                    filtered_ips = [ip for ip in ip_matches if not ip.startswith(('127.', '0.', '10.', '192.168.', '8.8.', '1.1.'))]
                    c2_indicators["tunnels_or_ips"].extend(list(set(filtered_ips)))

        except Exception as e:
            return {"error": f"Failed to parse APK: {str(e)}"}

        # Risk Score Calculation
        score = 0
        flags = []

        if len(found_permissions) > 0:
            score += min(len(found_permissions) * 10, 40)
            flags.append(f"Dangerous permissions found: {', '.join(found_permissions)}")

        if 'BIND_ACCESSIBILITY_SERVICE' in found_permissions:
            score += 35
            flags.append("Accessibility Service abuse risk (Common in banking trojans)")

        if c2_indicators["telegram_bots"]:
            score += 40
            flags.append("Hardcoded Telegram Bot token found (Attacker C2 channel)")

        if c2_indicators["firebase_urls"] or c2_indicators["tunnels_or_ips"]:
            score += 30
            flags.append("Suspicious hardcoded backend infrastructure")

        score = min(score, 100)
        risk_level = "SAFE" if score < 30 else ("MEDIUM" if score < 70 else "HIGH")

        return {
            "file_path": file_path,
            "sha256": sha256,
            "risk_score": score,
            "risk_level": risk_level,
            "permissions": found_permissions,
            "c2_indicators": c2_indicators,
            "flags": flags
        }

if __name__ == "__main__":
    import json
    analyzer = APKAnalyzer()
    print("APK Analyzer module loaded successfully.")
