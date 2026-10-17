class RiskMathEngine:
    """Combines individual risk signals into a final score and level."""

    def calculate(self, signals: dict) -> dict:
        # signals: {"name": weight}, weights 0-100
        score = min(100, sum(signals.values()))
        return {"risk_score": score, "risk_level": self.level(score)}

    @staticmethod
    def level(score: int) -> str:
        if score >= 70:
            return "HIGH"
        if score >= 40:
            return "MEDIUM"
        return "LOW"
