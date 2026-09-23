import { useState } from "react";
import { api } from "../api";
import { Link } from "react-router-dom";
import { useAsync } from "../lib/hooks";
import { Chip, Empty, ErrorNote, Loading, Notice, Spinner } from "./ui";

const VERDICT = {
  quadratic: ["Grows steeply", "fail"], steep: ["Grows very steeply", "fail"], timed_out: ["Stops finishing in time", "fail"],
  linear: ["Grows in step with the input", "warn"], sub_linear: ["Grows slowly", "pass"],
  too_fast: ["Too fast to measure", ""], unknown: ["Not enough data", ""], needs_bigger_input: ["Needs a bigger input to judge", ""],
};
const OUTCOME = { same: ["Same answer", "pass"], different: ["Different answer", "warn"], crash: ["Stops with an error", "fail"] };

function Timings({ performance: p }) {
  const widest = Math.max(...p.points.map((x) => x.runtime_ms), 1);
  const [label, tone] = VERDICT[p.verdict] || VERDICT.unknown;
  return (
    <div>
      <h4 className="subhead">Performance impact <Chip tone={tone}>{label}</Chip></h4>
      <div>
        {p.points.map((x) => (
          <div className="stack-row" key={x.size}>
            <span>{x.size} values</span>
            <div className="stack-bar" role="img" aria-label={`${x.size} values took ${x.timed_out ? "too long to finish" : `${x.runtime_ms} milliseconds`}`}>
              <i style={{ width: `${(100 * x.runtime_ms) / widest}%`, background: x.timed_out ? "#a4303f" : "#123b33" }} />
            </div>
            <span className="sub">{x.timed_out ? "did not finish in time" : `${x.runtime_ms} ms in total, about ${x.work_ms} ms of actual work`}</span>
          </div>
        ))}
      </div>
      <p className="small">{p.summary}</p>
      <p className="small muted">Each run starts a fresh Python process, which costs about {p.startup_ms} ms before your code begins. Timings on a shared machine vary a little between runs.</p>
    </div>
  );
}

/** Explore a hypothetical change: what changes, what it prints, why, and what it costs. Nothing is stored. */
export default function WhatIfExplore({ expId, code }) {
  const { data, error, loading, reload } = useAsync(() => api.whatIfConditions(expId), [expId]);
  const [chosen, setChosen] = useState(null);
  const [option, setOption] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState(null);

  const conditions = data?.conditions || [];
  const condition = conditions.find((c) => c.id === chosen) || null;
  const selected = condition?.options.find((o) => o.id === option) || condition?.options[0] || null;

  function reset() {
    setChosen(null); setOption(null); setResult(null); setRunError(null);
  }

  async function run() {
    setBusy(true); setRunError(null);
    try {
      setResult(await api.exploreWhatIf(expId, { condition_id: condition.id, option: selected.id, code }));
    } catch (e) { setRunError(e); } finally { setBusy(false); }
  }

  if (loading && !data) return <Loading label="Loading what-if questions" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  if (!conditions.length) return <Empty title="No what-if questions for this experiment yet">These questions need a sample input made of numbers. The predict-and-check tab still works.</Empty>;

  const [outcomeLabel, outcomeTone] = result ? OUTCOME[result.outcome] : [];
  return (
    <div className="stack">
      <p className="small muted">
        Ask what would happen if something changed. Your program runs both ways and the answers are compared. This never affects your score, and nothing is stored.
      </p>

      <div className="stack" role="radiogroup" aria-label="What-if question">
        {conditions.map((c) => (
          <label className="scenario" key={c.id}>
            <span className="check">
              <input type="radio" name="whatif-condition" checked={condition?.id === c.id}
                onChange={() => { setChosen(c.id); setOption(c.options[0]?.id ?? null); setResult(null); setRunError(null); }} />
              <span><b>{c.question}</b><span className="small muted">{c.explains}</span></span>
            </span>
          </label>
        ))}
      </div>

      {condition && (
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor="wi-option">{condition.label}</label>
          <select id="wi-option" value={selected?.id ?? ""} onChange={(e) => { setOption(e.target.value); setResult(null); }}>
            {condition.options.map((o) => <option key={o.id} value={o.id}>{o.label} ({o.detail})</option>)}
          </select>
        </div>
      )}

      <div className="chips">
        <button className="btn btn-dark" onClick={run} disabled={busy || !condition}>{busy && <Spinner />}See what happens</button>
        <button className="btn" onClick={reset} disabled={busy || (!condition && !result)}>Reset scenario</button>
      </div>
      <p className="small muted">
        Starting point: {data.base_input.name ? `the sample case "${data.base_input.name}"` : "the sample input"}, run with {data.code_source}.
      </p>

      {runError && <Notice tone="error">{runError.message}</Notice>}

      {result && (
        <div className="stack" aria-live="polite">
          <div>
            <h3 className="subhead">What changes <Chip tone={outcomeTone}>{outcomeLabel}</Chip></h3>
            <p>{result.what_changes}</p>
          </div>

          <div>
            <h4 className="subhead">What it prints</h4>
            <div className="detail-grid">
              <div className="io"><span className="label">As it is now</span><pre className="code-block tight">{result.baseline.output || "(nothing)"}</pre></div>
              {result.runs.map((r) => (
                <div className="io" key={r.label}>
                  <span className="label">With {r.label}</span>
                  <pre className="code-block tight">{r.timed_out ? "(did not finish in time)" : r.crashed ? `${r.error_type || "Error"}` : r.output || "(nothing)"}</pre>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h4 className="subhead">Why it changes</h4>
            <p>{result.why}</p>
          </div>

          <div>
            <h4 className="subhead">
              Risk <Chip tone={result.risk === "High" ? "fail" : result.risk === "Medium" ? "warn" : "pass"}>{result.risk}</Chip>
              {result.can_introduce_bug && <> <Chip tone="warn">can introduce a bug</Chip></>}
            </h4>
            <p className="small">{result.risk_reason}</p>
            {result.concept && <p className="small"><b>Affected concept:</b> {result.concept}.</p>}
            {result.mistake && (
              <p className="small">
                <b>Mistake DNA:</b> {result.mistake.label}
                {result.mistake.your_count > 0
                  ? ` — you have made this ${result.mistake.your_count} time${result.mistake.your_count === 1 ? "" : "s"}${result.mistake.recurring ? ", and it keeps coming back" : ""}.`
                  : " — not recorded against you yet."}
                {result.mistake.practice?.length > 0 && (
                  <> <Link to={`/experiments/${result.mistake.practice[0].experiment_id}`}>Practice this concept</Link> with {result.mistake.practice[0].title}.</>
                )}
              </p>
            )}
            {result.skill && (
              <p className="small">
                <b>Skill:</b> {result.skill.skill} ({result.skill.level}, {Math.round(result.skill.mastery)}%)
                {result.skill.needs_practice && " — this one needs practice."} <Link to="/passport">Skill Passport</Link>
              </p>
            )}
          </div>

          {result.performance && <Timings performance={result.performance} />}

          {result.changed_code && (
            <details>
              <summary>The changed line of code</summary>
              <pre className="code-block" style={{ marginTop: 8 }}>{result.changed_code}</pre>
            </details>
          )}
          {!result.changed_code && result.runs[result.runs.length - 1]?.stdin && (
            <details>
              <summary>The changed input</summary>
              <pre className="code-block tight" style={{ marginTop: 8 }}>{result.runs[result.runs.length - 1].stdin}</pre>
            </details>
          )}
          <p className="small muted">Your own program and your score are untouched: this ran a copy.</p>
        </div>
      )}
    </div>
  );
}
