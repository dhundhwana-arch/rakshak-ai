import math
import re
from urllib.parse import urlparse
import requests

class URLScanner:
    def __init__(self):
        self.high_risk_tlds = ['.top', '.xyz', '.buzz', '.club', '.online', '.apk', '.loan', '.win', '.bid']
        self.scam_keywords = ['kyc', 'echallan', 'pan-update', 'electricity-cut', 'digital-arrest', 'sbi-update', 'hdfc-kyc', 'free-recharge', 'lottery', 'job-offer']
        self.legit_brands = {
            'sbi': ['onlinesbi.sbi', 'sbi.co.in'],
            'hdfc': ['hdfcbank.com'],
            'icici': ['icicibank.com'],
            'parivahan': ['parivahan.gov.in'],
            'indiapost': ['indiapost.gov.in'],
            'npci': ['npci.org.in']
        }

    def unshorten_url(self, url: str) -> str:
        """Resolves short URLs like bit.ly, tinyurl to their final destination."""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        try:
            response = requests.head(url, allow_redirects=True, timeout=5)
            return response.url
        except Exception:
            return url

    def calculate_entropy(self, text: str) -> float:
        """Calculates Shannon Entropy to detect DGA or random phishing domains."""
        if not text:
            return 0.0
        entropy = 0.0
        length = len(text)
        # Count character frequencies
        char_counts = {}
        for char in text:
            char_counts[char] = char_counts.get(char, 0) + 1
        
        for count in char_counts.values():
            probability = count / length
            entropy -= probability * math.log2(probability)
        return round(entropy, 2)

    def levenshtein_distance(self, s1: str, s2: str) -> int:
        """Pure Python Levenshtein distance for homograph/typosquatting detection."""
        if len(s1) < len(s2):
            return self.levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def check_homograph(self, domain: str) -> bool:
        """Checks if domain is a typosquatting variant of major Indian services."""
        domain_name = domain.split('.')[0].lower()
        for brand, official_domains in self.legit_brands.items():
            if domain in official_domains:
                return False
            # If domain is suspiciously close to brand name but not exact
            dist = self.levenshtein_distance(domain_name, brand)
            if 0 < dist <= 2:
                return True
        return False

    def scan(self, input_url: str) -> dict:
        final_url = self.unshorten_url(input_url)
        parsed = urlparse(final_url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        full_path = domain + path

        # Checks
        tld_flag = any(domain.endswith(tld) for tld in self.high_risk_tlds)
        keyword_flag = any(kw in full_path for kw in self.scam_keywords)
        entropy_val = self.calculate_entropy(domain)
        high_entropy_flag = entropy_val > 4.0  # Random strings have higher entropy
        homograph_flag = self.check_homograph(domain)

        # Risk scoring logic for URL
        score = 0
        reasons = []

        if tld_flag:
            score += 35
            reasons.append("High-risk TLD detected (.top/.xyz/etc.)")
        if keyword_flag:
            score += 40
            reasons.append("Suspicious scam keyword found in URL path")
        if high_entropy_flag:
            score += 25
            reasons.append(f"High domain entropy ({entropy_val}), looks algorithmically generated")
        if homograph_flag:
            score += 50
            reasons.append("Potential Typosquatting / Homograph attack targeting Indian portals")

        score = min(score, 100)
        risk_level = "SAFE" if score < 30 else ("MEDIUM" if score < 70 else "HIGH")

        return {
            "original_url": input_url,
            "final_resolved_url": final_url,
            "domain": domain,
            "entropy": entropy_val,
            "risk_score": score,
            "risk_level": risk_level,
            "flags": reasons
        }

if __name__ == "__main__":
    scanner = URLScanner()
    test_url = "sbi-kyc-update.top/login"
    print(f"Scanning test URL: {test_url}")
    import json
    print(json.dumps(scanner.scan(test_url), indent=2))
