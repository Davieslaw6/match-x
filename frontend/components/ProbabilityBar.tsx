type P = { home: number; draw: number; away: number };
export function validP(p: P): boolean {
  const s = p.home + p.draw + p.away;
  return [p.home, p.draw, p.away].every((x) => x >= 0 && x <= 1) && Math.abs(s - 1) < 1e-6;
}
export function ProbabilityBar({ home, draw, away, label }: P & { label: string }) {
  if (!validP({ home, draw, away })) return <p role="alert">Probabilities are missing or invalid.</p>;
  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
  return (
    <div role="img" aria-label={`${label}: home ${pct(home)}, draw ${pct(draw)}, away ${pct(away)}`}>
      <div className="pitch" aria-hidden>
        <span style={{ flexBasis: pct(home), background: "var(--home)" }} />
        <span style={{ flexBasis: pct(draw), background: "var(--draw)" }} />
        <span style={{ flexBasis: pct(away), background: "var(--away)" }} />
      </div>
    </div>
  );
}
