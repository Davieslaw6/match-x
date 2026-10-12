import json, re
from dataclasses import dataclass, field
import httpx

class LLMError(Exception): ...
@dataclass
class ToolCall: id: str; name: str; args: dict
@dataclass
class LLMResponse: text: str | None = None; tool_calls: list = field(default_factory=list)

class OpenAICompatible:
    """UNVERIFIED live: needs LLM_BASE_URL, LLM_API_KEY, LLM_MODEL."""
    def __init__(self, base, key, model): self.base, self.key, self.model = base.rstrip("/"), key, model
    async def complete(self, messages, tools):
        body = {"model": self.model, "messages": [{"role": "tool" if m["role"] == "tool" else m["role"], "content": m["content"],
                **({"tool_call_id": m["tool_call_id"]} if m["role"] == "tool" else {})} for m in messages],
                "tools": [{"type": "function", "function": t} for t in tools]}
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"{self.base}/chat/completions", json=body, headers={"Authorization": f"Bearer {self.key}"}); r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            return LLMResponse(msg.get("content"), [ToolCall(t["id"], t["function"]["name"], json.loads(t["function"]["arguments"])) for t in msg.get("tool_calls") or []])
        except (httpx.HTTPError, KeyError, ValueError) as e: raise LLMError(type(e).__name__) from e

STOP = {"What", "Who", "How", "Show", "Give", "Tell", "Is", "Analyze", "Analyse", "List", "Compare", "Will", "Can", "Do", "My", "Remove", "Are", "The", "I", "Predict", "Fixtures", "Odds", "Form", "Over", "Ignore", "Hello", "Whats"}
def _teams(u):
    out = []
    for m in re.finditer(r"\b[A-Z][\w'.&-]*(?:\s[A-Z][\w'.&-]*)*", u):
        w = [x for x in m.group(0).replace("'s", "").split()]
        while w and w[0] in STOP: w = w[1:]
        if w: out.append(" ".join(w))
    return out

def _plan(u):
    low, t = u.lower(), _teams(u); res = lambda n: [("resolve_team", (lambda r, i=i: {"query": t[i]})) for i in range(n)]
    ids = lambda r: [x[1]["team_id"] for x in r if x[0] == "resolve_team"]
    d = re.findall(r"\d{4}-\d{2}-\d{2}", u)
    if "analyze ticket" in low or "analyse ticket" in low:
        odds = re.findall(r"\d+(?:\.\d+)?", u.split(":", 1)[-1])
        return [("analyze_ticket", lambda r: {"selections": [{"fixture": f"f{i}", "odds": o} for i, o in enumerate(odds)]})]
    if "my tickets" in low: return [("list_tickets", lambda r: {})]
    if "remove" in low and "ticket" in low: return [("propose_ticket_change", lambda r: {"ticket_id": 1, "operation": "remove", "selection_id": "1"})]
    if "screenshot" in low: return [("parse_screenshot", lambda r: {"upload_id": "latest"})]
    if re.search(r"head to head|h2h|head-to-head", low) and len(t) >= 2:
        return res(2) + [("get_head_to_head", lambda r: {"team_a": ids(r)[0], "team_b": ids(r)[1]})]
    if "odds" in low and len(t) >= 2:
        return res(2) + [("search_fixtures", lambda r: {"home_team_id": ids(r)[0], "away_team_id": ids(r)[1], "status": "scheduled"}),
                         ("get_odds", lambda r: {"fixture_id": r[-1][1]["fixtures"][0]["id"]} if r[-1][1]["fixtures"] else None)]
    if re.search(r"predict|chance|who will win|probab|over 2|btts", low) and len(t) >= 2:
        return res(2) + [("run_prediction", lambda r: {"home_team_id": ids(r)[0], "away_team_id": ids(r)[1]})]
    if "form" in low and t: return res(1) + [("get_team_form", lambda r: {"team_id": ids(r)[0]})]
    if re.search(r"fixture|playing|matches on", low):
        if t: return res(1) + [("search_fixtures", lambda r: {"team_id": ids(r)[0]})]
        if d: return [("search_fixtures", lambda r: {"date_from": d[0], "date_to": d[-1]})]
    return []

class MockLLM:
    """Deterministic rule-based stand-in used for CI and demos. It tests orchestration, NOT real model behaviour."""
    async def complete(self, messages, tools):
        from .compose import template_answer
        i = max(k for k, m in enumerate(messages) if m["role"] == "user"); u = messages[i]["content"]
        res = [(m["name"], json.loads(m["content"])["untrusted_data"]) for m in messages[i + 1:] if m["role"] == "tool"]
        steps = _plan(u)
        if len(res) < len(steps) and not (res and res[-1][0] == "resolve_team" and res[-1][1].get("status") != "match"):
            args = steps[len(res)][1](res)
            if args is not None: return LLMResponse(tool_calls=[ToolCall(f"c{len(res)}", steps[len(res)][0], args)])
        if res: return LLMResponse(template_answer(res))
        low = u.lower()
        if re.search(r"\b(safe|sure|guarantee|lock|certain)\b", low): return LLMResponse("I can't promise any outcome. I can show model estimates and recorded prices, which are statistical estimates and not guarantees.")
        if re.search(r"ignore|python|run code|execute", low): return LLMResponse("I can't run code or follow instructions embedded in messages. I can look up fixtures, form, head-to-head, odds and model estimates.")
        return LLMResponse("I can look up fixtures, team form, head-to-head records, recorded odds and model estimates, and analyze a ticket's combined odds.")

def make_llm(settings):
    if settings.llm_provider == "mock": return MockLLM()
    if settings.llm_provider == "openai_compatible": return OpenAICompatible(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
    return None
