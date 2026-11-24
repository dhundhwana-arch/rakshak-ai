import ipaddress
import math
import socket
from urllib.parse import urljoin, urlparse
import requests

MAX_REDIRECT_HOPS = 5
REQUEST_TIMEOUT_SEC = 5

def _is_public_ip(ip_str: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_unspecified)

def validate_public_url(url: str) -> tuple[bool, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "Only http:// and https:// URLs are supported."
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False, "URL must include a valid hostname."
    if hostname in ("localhost", "localhost.localdomain") or hostname.endswith(".local") or hostname.endswith(".internal"):
        return False, "Blocked internal/local hostname (SSRF protection)."
    try:
        ipaddress.ip_address(hostname)
        if not _is_public_ip(hostname):
            return False, f"Blocked non-public IP address: {hostname} (SSRF protection)."
        return True, None
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        for info in infos:
            if not _is_public_ip(info[4][0]):
                return False, f"Hostname resolves to non-public IP {info[4][0]} (SSRF protection)."
    except socket.gaierror:
        return True, "dns_unresolvable"
    except Exception:
        return True, "dns_check_skipped"
    return True, None

class URLScanner:
    def __init__(self):
        self.high_risk_tlds = (".top", ".xyz", ".buzz", ".club", ".online", ".apk", ".loan", ".win", ".bid", ".tk", ".ml", ".ga", ".cf")
        self.scam_keywords = ["kyc", "echallan", "pan-update", "electricity-cut", "digital-arrest", "sbi-update", "hdfc-kyc", "free-recharge", "lottery", "job-offer", "verify-now", "account-block", "pm-kisan", "rto-challan"]
        self.legit_brands = {"sbi": ["onlinesbi.sbi", "sbi.co.in", "www.sbi.co.in"], "hdfc": ["hdfcbank.com", "www.hdfcbank.com"], "icici": ["icicibank.com", "www.icicibank.com"], "parivahan": ["parivahan.gov.in", "www.parivahan.gov.in"], "indiapost": ["indiapost.gov.in", "www.indiapost.gov.in"], "npci": ["npci.org.in", "www.npci.org.in"], "cybercrime": ["cybercrime.gov.in", "www.cybercrime.gov.in"]}

    def unshorten_url(self, url: str) -> tuple[str, int, str | None]:
        current = url.strip()
        if "://" not in current:
            current = "https://" + current
        ok, note = validate_public_url(current)
        if not ok:
            raise ValueError(note or "Blocked unsafe URL.")
        if note == "dns_unresolvable":
            return current, 0, "Domain could not be resolved via DNS; static heuristics applied."
        hops = 0
        for _ in range(MAX_REDIRECT_HOPS):
            try:
                resp = requests.head(current, allow_redirects=False, timeout=REQUEST_TIMEOUT_SEC, headers={"User-Agent": "RAKSHAK-AI/3.0"})
            except requests.RequestException:
                return current, hops, "Live redirect lookup timed out or unavailable; static heuristics applied."
            if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
                next_url = urljoin(current, resp.headers["Location"])
                ok_n, err_n = validate_public_url(next_url)
                if not ok_n:
                    raise ValueError(f"Redirect target blocked: {err_n}")
                current, hops = next_url, hops + 1
                if err_n == "dns_unresolvable":
                    break
            else:
                break
        return current, hops, None

    def calculate_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        counts = {}
        for ch in text:
            counts[ch] = counts.get(ch, 0) + 1
        return round(-sum((c / len(text)) * math.log2(c / len(text)) for c in counts.values()), 2)

    def levenshtein_distance(self, s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return self.levenshtein_distance(s2, s1)
        if not s2:
            return len(s1)
        prev = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (c1 != c2)))
            prev = curr
        return prev[-1]

    def check_homograph(self, hostname: str) -> tuple[bool, str | None]:
        host = hostname.lower().strip(".")
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        if len(parts) < 2:
            return False, None
        base_label = parts[-3] if (len(parts) >= 3 and parts[-2] in ("co", "gov", "org", "ac", "net") and len(parts[-1]) == 2) else parts[-2]
        for brand, official in self.legit_brands.items():
            if any(host == d or host.endswith("." + d) for d in official):
                return False, None
            if brand in host and len(brand) >= 3 and (f"{brand}-" in host or f"-{brand}" in host):
                return True, brand
            if len(brand) >= 4 and len(base_label) >= 4 and 0 < self.levenshtein_distance(base_label, brand) <= 2:
                return True, brand
        return False, None

    def scan(self, input_url: str) -> dict:
        cleaned = (input_url or "").strip()
        if not cleaned:
            raise ValueError("Please enter a URL to scan.")
        final_url, hops, note = self.unshorten_url(cleaned)
        parsed = urlparse(final_url)
        hostname = (parsed.hostname or "").lower()
        full_target = hostname + (parsed.path + ("?" + parsed.query if parsed.query else "")).lower()
        tld_flag = any(hostname.endswith(t) for t in self.high_risk_tlds)
        matched_kw = [kw for kw in self.scam_keywords if kw in full_target]
        entropy = self.calculate_entropy(hostname)
        homograph, brand = self.check_homograph(hostname)
        score, flags = 0, []
        if tld_flag: score += 35; flags.append("High-risk TLD detected (.top/.xyz/.loan/etc.)")
        if matched_kw: score += 40; flags.append(f"Suspicious scam keywords in URL: {', '.join(matched_kw)}")
        if entropy > 4.0: score += 20; flags.append(f"High domain entropy ({entropy})")
        if homograph: score += 45; flags.append(f"Potential impersonation targeting '{brand}'")
        if parsed.scheme == "http": score += 10; flags.append("Unencrypted HTTP connection")
        if hostname.count(".") >= 3: score += 10; flags.append("Multiple nested subdomains detected")
        if hops >= 2: score += 10; flags.append(f"Multiple URL redirects ({hops} hops)")
        score = min(score, 100)
        return {"original_url": cleaned, "final_resolved_url": final_url, "domain": hostname, "redirect_hops": hops, "entropy": entropy, "risk_score": score, "risk_level": "SAFE" if score < 30 else ("MEDIUM" if score < 70 else "HIGH"), "flags": flags, "analysis_engine": "heuristic_url_scanner", "confidence": "Medium (Heuristic)" if not note else "Low-Medium (Static Only)", "resolution_note": note, "limitations": "Heuristic URL analysis only; does not execute page JavaScript or guarantee safety."}
