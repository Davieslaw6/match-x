import re
BANNED = re.compile(r"\b(safe|sure|guaranteed)\b", re.I)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}"); NUM = re.compile(r"\d+(?:\.\d+)?")

def _leaves(x, nums, strs):
    if isinstance(x, dict): [_leaves(v, nums, strs) for v in x.values()]
    elif isinstance(x, list): [_leaves(v, nums, strs) for v in x]
    elif isinstance(x, bool) or x is None: pass
    elif isinstance(x, (int, float)): nums.append(float(x))
    elif isinstance(x, str):
        strs.append(x); body = DATE.sub(" ", x)
        nums += [float(n) for n in NUM.findall(body)]

def ungrounded(text: str, outputs) -> list[str]:
    nums, strs = [], []; [_leaves(r, nums, strs) for _, r in outputs]
    bad = [f"banned word '{m.group(0)}'" for m in BANNED.finditer(text)]
    for d in DATE.findall(text):
        if not any(d in s for s in strs): bad.append(d)
    for tok in NUM.findall(DATE.sub(" ", text)):
        dec = len(tok.split(".")[1]) if "." in tok else 0; tol = 0.5 * 10 ** -dec + 1e-9; v = float(tok)
        if v in (0.0, 1.0): continue
        if not any(abs(v - n) <= tol or abs(v - n * 100) <= tol for n in nums): bad.append(tok)
    return bad
