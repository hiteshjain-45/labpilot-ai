import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import CodeEditor from "../components/CodeEditor";
import CopilotPanel from "../components/CopilotPanel";
import Observations from "../components/Observations";
import RichText from "../components/RichText";
import WhatIfPanel from "../components/WhatIfPanel";
import { Chip, Empty, ErrorNote, LevelChip, Loading, Notice, Spinner, StatusChip } from "../components/ui";
import { ago, plural, score } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

function Brief({ exp }) {
  return (
    <div className="brief">
      <section><h3>Aim</h3><p>{exp.objective}</p></section>
      <section><h3>Problem</h3><RichText text={exp.problem_statement} /></section>
      <section><h3>Procedure</h3><RichText text={exp.instructions} /></section>
      <section>
        <h3>Sample cases</h3>
        {exp.visible_tests.map((t) => (
          <div className="case" key={t.id}>
            <b className="small">{t.name}</b>
            <div className="io"><span className="label">Input</span><pre className="code-block tight">{t.stdin || "(empty)"}</pre></div>
            <div className="io"><span className="label">Expected output</span><pre className="code-block tight">{t.expected_output}</pre></div>
          </div>
        ))}
        {exp.hidden_test_count > 0 && <p className="small muted" style={{ marginTop: 8 }}>{plural(exp.hidden_test_count, "more case")} stay hidden until you submit, so check the edge cases yourself.</p>}
      </section>
      <section><h3>Skills practised</h3><div className="chips">{exp.skills.map((s) => <Chip key={s}>{s}</Chip>)}</div></section>
    </div>
  );
}

function Report({ report }) {
  const sub = report.submission;
  const graded = report.kind === "submit";
  return (
    <div className="stack" aria-live="polite">
      <div className="result-line">
        {graded
          ? `Result: ${sub.passed_count} of ${sub.total_count} observations match. Score ${score(sub.score, sub.max_score)}.`
          : `Test run: ${sub.passed_count} of ${plural(sub.total_count, "visible case")} match. Runs are not graded.`}
      </div>
      <Observations key={sub.id} results={sub.results} />
      {report.mistakes.length > 0 && (
        <div>
          <h3 style={{ margin: "6px 0" }}>Mistake patterns found</h3>
          <div className="stack">
            {report.mistakes.map((m) => (
              <div key={m.category} className="notice warn"><b>{m.label}.</b> {m.detail}<div className="small">{m.tip}</div></div>
            ))}
          </div>
        </div>
      )}
      {graded && report.skill_changes.length > 0 && (
        <p className="small">Skill passport updated: {report.skill_changes.map((c) => `${c.skill} ${c.delta >= 0 ? "+" : ""}${c.delta} (now ${Math.round(c.after)}%)`).join(", ")}.</p>
      )}
      {graded && report.recommendation && (
        <Notice tone={sub.status === "passed" ? "ok" : "info"}>
          <b>Next suggestion: <Link to={`/experiments/${report.recommendation.experiment_id}`}>{report.recommendation.experiment_title}</Link>.</b> {report.recommendation.reason}
        </Notice>
      )}
      {graded && !report.recommendation && <Notice tone="ok">Every experiment is mastered. Nothing further to recommend.</Notice>}
    </div>
  );
}

function HistoryPanel({ expId, refreshKey, onLoad }) {
  const { data, error, loading, reload } = useAsync(() => api.history(expId), [expId, refreshKey]);
  const [busyId, setBusyId] = useState(null);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  if (!data.length) return <Empty title="Nothing yet">Runs and submissions for this experiment will be listed here.</Empty>;
  return (
    <table className="table">
      <thead><tr><th>When</th><th>Type</th><th>Outcome</th><th>Teacher review</th><th><span className="sr-only">Load</span></th></tr></thead>
      <tbody>
        {data.map((s) => (
          <tr key={s.id}>
            <td className="nowrap">{ago(s.created_at)}</td>
            <td>{s.kind === "submit" ? "Graded" : "Run"}</td>
            <td><Chip tone={s.status === "passed" ? "pass" : s.status === "partial" ? "warn" : "fail"}>{s.passed_count}/{s.total_count}</Chip>{s.kind === "submit" && <span className="small muted"> {score(s.score, s.max_score)}</span>}</td>
            <td>
              {s.review ? (
                <>
                  <Chip tone={s.review.status === "approved" ? "pass" : "warn"}>{s.review.label}</Chip>
                  {s.review.remark && <div className="small">{s.review.remark}</div>}
                  <div className="small muted">{s.review.teacher_name}, {ago(s.review.reviewed_at)}</div>
                </>
              ) : <span className="small muted">{s.kind === "submit" ? "Not reviewed yet" : "n/a"}</span>}
            </td>
            <td><button className="btn-link" disabled={busyId === s.id} onClick={async () => { setBusyId(s.id); try { onLoad((await api.submission(s.id)).code); } finally { setBusyId(null); } }}>Load code</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function WorkspaceInner({ exp, aiReal }) {
  const { user } = useAuth();
  const draftKey = `labpilot.draft.${user.id}.${exp.id}`;
  const initial = useMemo(() => localStorage.getItem(draftKey) ?? exp.last_code ?? exp.starter_code, [draftKey, exp]);
  const [code, setCode] = useState(initial);
  const [report, setReport] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(exp.current_attempt);
  const [tab, setTab] = useState("copilot");
  const [historyKey, setHistoryKey] = useState(0);
  const codeRef = useRef(code);
  const reportRef = useRef(null);
  codeRef.current = code;

  useEffect(() => {
    const t = setTimeout(() => localStorage.setItem(draftKey, code), 400);
    return () => clearTimeout(t);
  }, [code, draftKey]);

  const execute = useCallback(async (kind) => {
    setBusy(kind); setError(null);
    try {
      const r = kind === "run" ? await api.run(exp.id, codeRef.current) : await api.submit(exp.id, codeRef.current);
      setReport({ ...r, kind });
      setAttempt(r.attempt);
      setHistoryKey((k) => k + 1);
      setTimeout(() => reportRef.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" }), 50);
    } catch (e) { setError(e); } finally { setBusy(null); }
  }, [exp.id]);

  const consoleText = () => {
    const failing = report?.submission.results.find((r) => !r.is_hidden && r.stderr);
    return failing ? failing.stderr.slice(-1500) : null;
  };

  return (
    <>
      <div className="page-head">
        <div>
          <p className="small"><Link to="/experiments">All experiments</Link></p>
          <h1>{exp.title}</h1>
          <div className="chips" style={{ marginTop: 8 }}>
            <LevelChip level={exp.difficulty} /><StatusChip status={exp.progress.status} />
            <Chip>About {exp.estimated_minutes} min</Chip>
            {exp.progress.best_percent != null && <Chip>Best score {exp.progress.best_percent}%</Chip>}
          </div>
        </div>
      </div>
      <div className="workspace">
        <aside aria-label="Experiment brief"><Brief exp={exp} /></aside>
        <div>
          <div className="toolbar">
            <span className="small muted">
              {attempt.status === "submitted" ? `Attempt ${attempt.attempt_number} submitted. Your next run starts attempt ${attempt.attempt_number + 1}.` : `Attempt ${attempt.attempt_number}, ${plural(attempt.run_count, "run")}`}
            </span>
            <div className="actions">
              <button className="btn btn-sm" onClick={() => { if (window.confirm("Replace your code with the starter code?")) setCode(exp.starter_code); }}>Reset to starter</button>
              <button className="btn" onClick={() => execute("run")} disabled={!!busy}>{busy === "run" && <Spinner />}Run tests</button>
              <button className="btn btn-primary" onClick={() => execute("submit")} disabled={!!busy}>{busy === "submit" && <Spinner />}Submit for grading</button>
            </div>
          </div>
          <div onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !busy) { e.preventDefault(); execute("run"); } }}>
            <CodeEditor value={code} onChange={setCode} />
          </div>
          <p className="small muted" style={{ margin: "6px 0 18px" }}>Ctrl+Enter runs the tests. To leave the editor with the keyboard, press Esc and then Tab. Your code is saved in this browser as you type.</p>
          {error && <div style={{ marginBottom: 14 }}><ErrorNote error={error} /></div>}
          <div ref={reportRef}>
            {report ? <Report report={report} /> : <Empty title="No results yet">Run the tests to see how your program behaves on the sample cases.</Empty>}
          </div>
        </div>
        <aside className="side">
          <div className="panel">
            <div className="tabs" role="tablist">
              {[["copilot", "Copilot"], ["whatif", "What if"], ["history", "History"]].map(([key, label]) => (
                <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{label}</button>
              ))}
            </div>
            <div className="panel-body" role="tabpanel">
              {tab === "copilot" && <CopilotPanel expId={exp.id} getCode={() => codeRef.current} getConsole={consoleText} hintsUsed={attempt.hints_used} aiReal={aiReal}
                onHint={() => setAttempt((a) => ({ ...a, hints_used: a.hints_used + 1 }))} />}
              {tab === "whatif" && <WhatIfPanel expId={exp.id} code={code} />}
              {tab === "history" && <HistoryPanel expId={exp.id} refreshKey={historyKey} onLoad={setCode} />}
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}

export default function Workspace() {
  const { id } = useParams();
  const { status } = useOutletContext();
  const { data, error, loading, reload } = useAsync(() => api.experiment(id), [id]);
  useTitle(data?.title);
  if (loading && !data) return <Loading label="Opening experiment" />;
  if (error) return <div className="stack"><ErrorNote error={error} retry={reload} /><Link to="/experiments">Back to experiments</Link></div>;
  return <WorkspaceInner key={data.id} exp={data} aiReal={!!status?.ai?.is_real} />;
}
