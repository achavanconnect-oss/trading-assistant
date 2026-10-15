"""Deterministic check that every price-like number in a reply came from a tool result."""
import re

# decimals (1.0852), thousands-separated numbers (2,650.50) and integers of 3+ digits; skips percentages
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{3,})(?!\d)(?!\s*%)")


def numbers_in(obj) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= numbers_in(v)
    return out


def unverified_numbers(reply: str, tool_results: list[dict], user_text: str = "", rel_tol: float = 1e-4) -> list[str]:
    """Price-like numbers in the reply found in no tool result and not given by the user (within tolerance)."""
    known: set[float] = set()
    for r in tool_results:
        known |= numbers_in(r)
    for m in NUM.finditer(user_text):
        known.add(float(m.group(1).replace(",", "")))
    bad = []
    for m in NUM.finditer(reply):
        raw = m.group(1)
        v = float(raw.replace(",", ""))
        if not any(abs(v - k) <= rel_tol * max(abs(k), 1.0) for k in known):
            bad.append(raw)
    return bad
