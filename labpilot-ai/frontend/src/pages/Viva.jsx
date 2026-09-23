import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Chip, Empty, ErrorNote, LevelChip, Loading, Notice, PageHead, Section, Spinner } from "../components/ui";
import { useAsync, useTitle } from "../lib/hooks";
import { formatDate } from "../lib/format";

const VERDICT = { correct: "pass", "partially correct": "warn", incorrect: "fail" };
const TYPE = {
  concept: "Concept", code_explanation: "Code explanation", debugging: "Debugging",
  what_if: "What would happen if", improvement: "Improvement",
};

function Question({ q, onSubmit, busy }) {
  const [answer, setAnswer] = useState("");
  return (
    <div className="stack">
      <div>
        <Chip>{TYPE[q.type] || q.type}</Chip> <Chip>{q.difficulty}</Chip>
        {q.skill && <> <Chip>{q.skill}</Chip></>}
        <span className="small muted"> Question {q.index} of {q.total}</span>
      </div>
      <p><b>{q.question}</b></p>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor="viva-answer">Your answer</label>
        <textarea id="viva-answer" rows={6} maxLength={4000} value={answer} disabled={busy}
          onChange={(e) => setAnswer(e.target.value)} placeholder="Answer in your own words, as you would out loud." />
      </div>
      <div className="chips">
        <button className="btn btn-primary" disabled={busy || !answer.trim()} onClick={() => onSubmit(answer)}>{busy && <Spinner />}Submit answer</button>
      </div>
    </div>
  );
}

function Feedback({ result, onContinue, next, recommendation, busy }) {
  return (
    <div className="stack" aria-live="polite">
      <div>
        <h3 className="subhead">Feedback <Chip tone={VERDICT[result.verdict]}>{result.verdict}</Chip> <Chip>{result.score} / {result.out_of}</Chip></h3>
        <p>{result.feedback}</p>
      </div>
      {result.matched_concepts.length > 0 && <p className="small"><b>Concepts you named:</b> {result.matched_concepts.join(", ")}.</p>}
      {result.missing_concepts.length > 0 && <p className="small"><b>Still missing:</b> {result.missing_concepts.join(", ")}.</p>}
      <p className="small muted">{recommendation}</p>
      <div className="chips">
        <button className="btn btn-dark" onClick={onContinue} disabled={busy}>{busy && <Spinner />}{next ? "Next question" : "See viva summary"}</button>
      </div>
    </div>
  );
}

function Summary({ summary, onRestart }) {
  const s = summary;
  return (
    <div className="stack-lg">
      <div>
        <h3 className="subhead">Viva summary <Chip tone={s.percent >= 70 ? "pass" : s.percent >= 40 ? "warn" : "fail"}>{s.percent}%</Chip></h3>
        <p>{s.experiment.title}: {s.total_score} out of {s.out_of} across {s.questions_answered} questions.</p>
      </div>
      <div>
        <h4 className="subhead">Concepts demonstrated</h4>
        {s.concepts_demonstrated.length ? <p>{s.concepts_demonstrated.join(", ")}.</p> : <p className="small muted">None were named clearly this time.</p>}
        <h4 className="subhead">Concepts needing practice</h4>
        {s.concepts_needing_practice.length ? <p>{s.concepts_needing_practice.join(", ")}.</p> : <p className="small muted">Nothing outstanding.</p>}
      </div>
      {s.mistake_dna.length > 0 && (
        <div>
          <h4 className="subhead">Connected to your Mistake DNA</h4>
          <ul className="plain">
            {s.mistake_dna.map((m) => (
              <li key={m.category}>
                <b>{m.label}</b> {m.recurring && <Chip tone="fail">recurring</Chip>} recorded {m.recorded_count} time{m.recorded_count === 1 ? "" : "s"}
                {m.skill && <div className="small muted">Affects {m.skill}</div>}
              </li>
            ))}
          </ul>
          <p className="small"><Link to="/progress">Review your Mistake DNA</Link></p>
        </div>
      )}
      {s.recommendation && (
        <Notice>
          {s.recommendation.reason}{" "}
          <Link to={`/experiments/${s.recommendation.experiment_id}`}>Open {s.recommendation.title}</Link>
        </Notice>
      )}
      {s.skill_changes.length > 0 && (
        <p className="small">
          Skill Passport updated as practice evidence: {s.skill_changes.map((c) => `${c.skill} ${c.delta >= 0 ? "+" : ""}${c.delta}`).join(", ")}.{" "}
          <Link to="/passport">Open your Skill Passport</Link>. Your experiment scores and grades are unchanged.
        </p>
      )}
      <details>
        <summary>Your answers</summary>
        <ul className="plain" style={{ marginTop: 10 }}>
          {s.answers.map((a) => (
            <li key={a.index}>
              <b>{a.index}. {a.question}</b>
              <div className="small muted">You said: {a.answer || "(nothing)"}</div>
              <div className="small">{a.score} / {a.out_of}, {a.verdict}. {a.feedback}</div>
            </li>
          ))}
        </ul>
      </details>
      <div className="chips"><button className="btn" onClick={onRestart}>Practise another viva</button></div>
    </div>
  );
}

export default function Viva() {
  useTitle("AI Viva");
  const ctx = useAsync(() => api.vivaContext(), []);
  const [expId, setExpId] = useState("");
  const [session, setSession] = useState(null);       // { session_id, question, total_questions }
  const [result, setResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const reset = () => { setSession(null); setResult(null); setSummary(null); setError(null); };

  async function run(fn) {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e); } finally { setBusy(false); }
  }

  const start = () => run(async () => {
    const chosen = Number(expId || ctx.data.experiments[0].id);
    const started = await api.vivaStart({ experiment_id: chosen });
    setResult(null); setSummary(null); setSession(started);
  });

  const submitAnswer = (answer) => run(async () => {
    const r = await api.vivaAnswer({ session_id: session.session_id, answer });
    setResult(r);
  });

  const cont = () => run(async () => {
    if (result.next_question) {
      setSession({ ...session, question: result.next_question });
      setResult(null);
    } else {
      setSummary(await api.vivaSummary(session.session_id));
      setResult(null);
    }
  });

  if (ctx.loading && !ctx.data) return <Loading label="Loading the viva" />;
  if (ctx.error) return <ErrorNote error={ctx.error} retry={ctx.reload} />;
  const { experiments, question_count: count, history, note } = ctx.data;

  return (
    <>
      <PageHead title="AI Viva">
        Practise answering questions about an experiment out loud, in writing. {count} questions: a concept, your own code, a mistake you have made, a what-if, and an improvement.
      </PageHead>
      <Notice tone="warn">{note}</Notice>
      <div className="cols">
        <div>
          <Section title={summary ? "Result" : session ? "Viva in progress" : "Start a viva"}>
            {error && <ErrorNote error={error} />}
            {!session && !summary && (
              experiments.length === 0 ? <Empty title="No experiments published yet" /> : (
                <div className="stack">
                  <div className="field" style={{ marginBottom: 0 }}>
                    <label htmlFor="viva-exp">Select an experiment</label>
                    <select id="viva-exp" value={expId} onChange={(e) => setExpId(e.target.value)}>
                      {experiments.map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.title}{e.submitted ? ` (best ${e.best_percent}%)` : " (not submitted yet)"}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="small muted">Questions are drawn from the experiment's own material, your latest submission and your recorded mistakes.</p>
                  <div><button className="btn btn-primary" onClick={start} disabled={busy}>{busy && <Spinner />}Start Viva</button></div>
                </div>
              )
            )}
            {session && !summary && !result && <Question q={session.question} onSubmit={submitAnswer} busy={busy} />}
            {session && !summary && result && (
              <Feedback result={result.evaluation} next={result.next_question} recommendation={result.next_recommendation} onContinue={cont} busy={busy} />
            )}
            {summary && <Summary summary={summary} onRestart={reset} />}
          </Section>
        </div>
        <div>
          <Section title="How answers are judged">
            <p className="small">
              Each question lists the ideas a full answer should mention. Your text is matched against those ideas, and the score is the share you named,
              out of 10. It is shallow on purpose: it rewards naming and explaining the right concepts, and it cannot judge style or a clever answer worded unusually.
            </p>
            <p className="small muted">Nothing here changes your experiment scores or grades. A finished viva adds practice evidence to your Skill Passport.</p>
          </Section>
          <Section title="Recent vivas">
            {history.length === 0 ? <Empty title="None yet" /> : (
              <ul className="plain">
                {history.map((h) => (
                  <li key={h.session_id}>
                    <b>{h.title}</b> <Chip>{h.percent}%</Chip>
                    <div className="small muted">{h.answered} questions, {formatDate(h.at)}</div>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      </div>
    </>
  );
}
