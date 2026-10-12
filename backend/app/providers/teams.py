import re, unicodedata
from rapidfuzz import fuzz, process

_SUF = re.compile(r"\b(fc|afc|cf|sc)\b")

def normalise(name: str) -> str:
    n = unicodedata.normalize("NFKD", name)
    n = "".join(c for c in n if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+", " ", _SUF.sub("", re.sub(r"[^\w\s]", " ", n))).strip()

def resolve(query: str, aliases: dict[str, str], teams: list[str], threshold: int = 90):
    """Returns ('match', team) | ('ambiguous', candidates) | ('none', [])."""
    q = normalise(query)
    if q in aliases: return ("match", aliases[q])
    names = {normalise(t): t for t in teams}
    if q in names: return ("match", names[q])
    hits = process.extract(q, list(names), scorer=fuzz.WRatio, limit=3)
    good = [(names[n], s) for n, s, _ in hits if s >= 70]
    if len(good) == 1 and good[0][1] >= threshold: return ("match", good[0][0])
    if good and good[0][1] >= threshold and (len(good) == 1 or good[0][1] - good[1][1] >= 5):
        return ("match", good[0][0])
    return ("ambiguous", [g[0] for g in good]) if good else ("none", [])
