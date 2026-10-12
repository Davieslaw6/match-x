"""Pure ticket operations over selection dicts. Odds are strings with 3 decimals; combined odds use exact Decimal."""
from decimal import Decimal
from . import core as tk

def o3(d) -> str: return f"{Decimal(str(d)):.3f}"
def to_core(sels, probs=None):
    probs = probs or {}
    return [tk.Sel(str(s["id"] if s["id"] is not None else f"n{i}"), s["fixture_label"], s["market"], s["outcome"], Decimal(s["odds"]), probs.get(i)) for i, s in enumerate(sels)]

def apply(sels: list[dict], op: dict) -> list[dict]:
    out = [dict(s) for s in sels]; kind = op["op"]
    if kind == "add": return out + [{**op["selection"], "id": None, "odds": o3(op["selection"]["odds"])}]
    if kind in ("remove", "edit"):
        idx = next((i for i, s in enumerate(out) if s["id"] == op.get("selection_id")), None)
        if idx is None: raise KeyError("selection not found")
        if kind == "remove": del out[idx]
        else:
            for k, v in (op.get("fields") or {}).items():
                if v is not None: out[idx][k] = o3(v) if k == "odds" else v
        return out
    if kind == "sort":
        key = (lambda s: Decimal(s["odds"])) if op.get("by", "odds") == "odds" else (lambda s: s["fixture_label"])
        return sorted(out, key=key, reverse=bool(op.get("descending")))
    raise ValueError("unsupported operation")
