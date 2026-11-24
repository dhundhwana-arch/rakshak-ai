import hashlib, os, re, zipfile
MAX_ZIP_ENTRIES = 5000
MAX_ENTRY_UNCOMPRESSED_BYTES = 15 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024

class APKAnalyzer:
    def __init__(self):
        self.dangerous_permissions = ["READ_SMS", "RECEIVE_SMS", "SEND_SMS", "BIND_ACCESSIBILITY_SERVICE", "SYSTEM_ALERT_WINDOW", "REQUEST_INSTALL_PACKAGES", "READ_CALL_LOG", "PROCESS_OUTGOING_CALLS", "READ_CONTACTS", "CAMERA"]
        self.tg_token_regex = re.compile(r"bot[0-9]{8,10}:[a-zA-Z0-9_-]{35}")
        self.firebase_regex = re.compile(r"https?://[a-zA-Z0-9_-]+\.firebaseio\.com")
        self.ip_tunnel_regex = re.compile(r"(?:https?://)?(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?::[0-9]+)?|[a-zA-Z0-9-]+\.(?:ngrok-free\.app|trycloudflare\.com)")

    def calculate_sha256(self, file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for blk in iter(lambda: f.read(65536), b""):
                h.update(blk)
        return h.hexdigest()

    def analyze(self, file_path: str, original_filename: str | None = None) -> dict:
        if not os.path.exists(file_path): return {"error": "APK file not found"}
        if not zipfile.is_zipfile(file_path): return {"error": "Invalid APK archive (not a valid ZIP container)."}
        sha256 = self.calculate_sha256(file_path)
        display_name = os.path.basename(original_filename or file_path)
        found_perms, c2 = [], {"telegram_bots": [], "firebase_urls": [], "tunnels_or_ips": []}
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                infos = zf.infolist()
                if len(infos) > MAX_ZIP_ENTRIES: return {"error": f"APK exceeds safe entry limit ({MAX_ZIP_ENTRIES})."}
                inspected, chunks = 0, []
                for info in infos:
                    if info.filename == "AndroidManifest.xml" or info.filename.endswith(".dex"):
                        if info.file_size > MAX_ENTRY_UNCOMPRESSED_BYTES or inspected + info.file_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
                            return {"error": "ZIP safety limit exceeded (decompressed size too large)."}
                        with zf.open(info, "r") as m:
                            data = m.read(MAX_ENTRY_UNCOMPRESSED_BYTES + 1)
                            if len(data) > MAX_ENTRY_UNCOMPRESSED_BYTES: return {"error": "ZIP safety limit exceeded."}
                            chunks.append(data); inspected += len(data)
                txt = b"".join(chunks).decode("latin-1", errors="ignore")
                found_perms = [p for p in self.dangerous_permissions if p in txt]
                c2["telegram_bots"] = sorted(set(self.tg_token_regex.findall(txt)))
                c2["firebase_urls"] = sorted(set(self.firebase_regex.findall(txt)))
                c2["tunnels_or_ips"] = sorted(set(ip for ip in self.ip_tunnel_regex.findall(txt) if not ip.startswith(("127.", "0.", "10.", "192.168.", "8.8.", "1.1."))))
        except zipfile.BadZipFile: return {"error": "Corrupted APK ZIP structure."}
        except Exception as exc: return {"error": f"Failed to inspect APK safely: {exc}"}
        score, flags = 0, []
        if found_perms: score += min(len(found_perms) * 10, 40); flags.append(f"Sensitive permissions: {', '.join(found_perms)}")
        if "BIND_ACCESSIBILITY_SERVICE" in found_perms: score += 35; flags.append("Accessibility Service indicator (banking trojan risk)")
        if c2["telegram_bots"]: score += 40; flags.append("Hardcoded Telegram Bot token detected")
        if c2["firebase_urls"] or c2["tunnels_or_ips"]: score += 30; flags.append("Suspicious hardcoded external infrastructure")
        score = min(score, 100)
        return {"filename": display_name, "sha256": sha256, "risk_score": score, "risk_level": "SAFE" if score < 30 else ("MEDIUM" if score < 70 else "HIGH"), "permissions": found_perms, "c2_indicators": c2, "flags": flags, "analysis_engine": "static_apk_inspector", "confidence": "Medium (Static Archive Inspection)", "limitations": "Static inspection only; runtime behavior cannot be detected without dynamic sandboxing."}
