"""Deterministic answer built only from tool data; used as grounded fallback and by the mock LLM."""
CAVEAT = "These are statistical estimates, not advice or guarantees."
def pct(x): return f"{x * 100:.1f}%"

def template_answer(outputs):
    out, predicted = [], False
    for name, r in outputs:
        st = r.get("status")
        if name == "resolve_team" and st == "ambiguous": out.append("Which team do you mean: " + ", ".join(r["candidates"]) + "?")
        elif name == "resolve_team" and st == "none": out.append(f"I couldn't find a team matching '{r['query']}'.")
        elif st == "unsupported": out.append(f"Not available: {r['reason']}.")
        elif name == "run_prediction":
            if st != "ok": out.append(f"No estimate: {r['reason']}.")
            else:
                p = r["probabilities"]; predicted = True
                out.append(f"{r['home']} vs {r['away']} ({r['model']}, data up to {r['data_cutoff']}): home win {pct(p['home'])}, draw {pct(p['draw'])}, "
                           f"away win {pct(p['away'])}. Over 2.5 goals {pct(r['over_2_5'])}; both teams to score {pct(r['btts_yes'])}.")
        elif name == "get_team_form":
            out.append(f"{r['name']} has no finished matches on record." if st != "ok" else
                       f"{r['name']}: {r['points']} points from the last {r['played']} matches. " + "; ".join(f"{m['date']} vs {m['opponent']} {m['gf']}-{m['ga']}" for m in r["matches"]) + ".")
        elif name == "get_head_to_head":
            out.append("No head-to-head matches on record." if st != "ok" else f"{r['a']} vs {r['b']}: {r['played']} matches, {r['a_wins']} wins for {r['a']}, {r['draws']} draws, {r['b_wins']} wins for {r['b']}.")
        elif name == "search_fixtures" and r["fixtures"]:
            out.append("; ".join(f"{f['home']} vs {f['away']} on {f['kickoff_utc'][:10]} ({f['status']})" for f in r["fixtures"][:5]) + ".")
        elif name == "search_fixtures": out.append("No fixtures found for that filter.")
        elif name == "get_odds":
            if st != "ok": out.append(f"No odds: {r['reason']}.")
            else:
                o = r["observations"]; out.append("Odds: " + "; ".join(f"{x['bookmaker']} {x['market']} {x['selection']} {x['odds']} (observed {x['observed_at'][:10]})" for x in o[:6]) + ".")
                if any(x["stale"] for x in o): out.append("Warning: some prices are stale; check the bookmaker before relying on them.")
        elif name == "analyze_ticket":
            out.append(f"Combined odds {r['combined_odds']}." + (" Warnings: " + " ".join(r["warnings"]) if r["warnings"] else ""))
    if predicted: out.append(CAVEAT)
    return " ".join(out) if out else "I don't have data to answer that."
