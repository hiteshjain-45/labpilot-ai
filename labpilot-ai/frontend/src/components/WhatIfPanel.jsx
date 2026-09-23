import { useEffect, useState } from "react";
import { api } from "../api";
import { useAsync } from "../lib/hooks";
import WhatIfExplore from "./WhatIfExplore";
import { Chip, Empty, ErrorNote, Loading, Notice, Spinner } from "./ui";

const MODES = [["predict", "Predict and check"], ["explore", "Explore a change"]];

export default function WhatIfPanel({ expId, onSkill, code }) {
  const [mode, setMode] = useState("predict");
  const { data, error, loading, reload } = useAsync(() => api.whatIf(expId), [expId]);
  const [selected, setSelected] = useState(null);
  const [prediction, setPrediction] = useState("");
  const [stdin, setStdin] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [runError, setRunError] = useState(null);

  const scenarios = data?.scenarios || [];
  const scenario = scenarios.find((s) => s.id === selected) || scenarios[0];

  useEffect(() => {
    if (scenario) { setStdin(scenario.default_input || ""); setPrediction(""); setResult(null); setRunError(null); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario?.id]);

  async function run() {
    setBusy(true); setRunError(null);
    try {
      const r = await api.runWhatIf(expId, { scenario_id: scenario.id, prediction, stdin });
      setResult(r);
      if (r.skill_change) onSkill?.(r.skill_change);
      reload();
    } catch (e) { setRunError(e); } finally { setBusy(false); }
  }

  const modeSwitch = (
    <div className="tabs tabs-sm" role="tablist" aria-label="What-if mode">
      {MODES.map(([id, label]) => (
        <button key={id} role="tab" aria-selected={mode === id} className={mode === id ? "active" : ""} onClick={() => setMode(id)}>{label}</button>
      ))}
    </div>
  );
  if (mode === "explore") return <div className="stack">{modeSwitch}<WhatIfExplore expId={expId} code={code} /></div>;
  if (loading && !data) return <><div className="stack">{modeSwitch}</div><Loading /></>;
  if (error) return <ErrorNote error={error} retry={reload} />;
  if (!scenarios.length) return <Empty title="No what-if scenarios">Your teacher has not added scenarios to this experiment yet.</Empty>;

  return (
    <div className="stack">
      {modeSwitch}
      <p className="small muted">Change one detail of the program, predict what it prints, then run it to see if you were right.</p>
      <div className="stack" role="radiogroup" aria-label="Scenario">
        {scenarios.map((s) => (
          <label className="scenario" key={s.id}>
            <span className="check"><input type="radio" name="scenario" checked={scenario.id === s.id} onChange={() => setSelected(s.id)} /><span><b>{s.title}</b><span className="small muted">{s.description}</span></span></span>
          </label>
        ))}
      </div>
      <div className="io"><span className="label">The modified program</span><pre className="code-block">{scenario.modified_code}</pre></div>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor="wi-stdin">Input given to the program</label>
        <textarea id="wi-stdin" className="code" rows={2} value={stdin} onChange={(e) => setStdin(e.target.value)} />
      </div>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor="wi-pred">Your prediction</label>
        <textarea id="wi-pred" className="code" rows={2} value={prediction} onChange={(e) => setPrediction(e.target.value)} placeholder="What will it print? If you expect a crash, say so." />
      </div>
      <div><button className="btn btn-dark" onClick={run} disabled={busy || !prediction.trim()}>{busy && <Spinner />}Run the experiment</button></div>
      <p className="small muted">Skill credit is given for a correct prediction the first time you try a scenario with a given input, so predict before you look.</p>
      {runError && <Notice tone="error">{runError.message}</Notice>}
      {result && (
        <div className="stack" aria-live="polite">
          <Chip tone={result.matched ? "pass" : "warn"}>{result.matched ? "Your prediction was right" : "Different from your prediction"}</Chip>
          <div className="io"><span className="label">What the program printed</span><pre className="code-block">{result.actual_output || "(nothing)"}</pre></div>
          <p>{result.explanation}</p>
          {result.skill_change && <p className="small muted">Problem Solving is now {Math.round(result.skill_change.after)}% (+{result.skill_change.delta}).</p>}
        </div>
      )}
      {data.history.length > 0 && (
        <div>
          <h3 className="subhead">Your earlier predictions ({data.history.length})</h3>
          <ul className="plain">
            {data.history.map((h) => (
              <li key={h.id}>
                <details>
                  <summary>
                    {h.scenario_title} <Chip tone={h.matched ? "pass" : "warn"}>{h.matched ? "Right" : "Missed"}</Chip>
                    {h.credited && <> <Chip tone="info">Skill credit</Chip></>}
                  </summary>
                  <div className="stack" style={{ marginTop: 8 }}>
                    <div className="io"><span className="label">Input</span><pre className="code-block tight">{h.stdin || "(empty)"}</pre></div>
                    <div className="io"><span className="label">You predicted</span><pre className="code-block tight">{h.prediction}</pre></div>
                    <div className="io"><span className="label">The program printed</span><pre className="code-block tight">{h.actual_output || "(nothing)"}</pre></div>
                    <p className="small">{h.explanation}</p>
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
