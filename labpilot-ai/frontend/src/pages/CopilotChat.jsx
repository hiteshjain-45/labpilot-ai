import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Chip, Empty, ErrorNote, LevelChip, Loading, Notice, PageHead, Section, Spinner, StatusChip } from "../components/ui";
import { useAsync, useTitle } from "../lib/hooks";

const FALLBACK_LABELS = { check_attempt: "I tried again: check my attempt", explain_error: "Explain my error", hint: "Give me a hint", explain_concept: "Explain the concept", similar_problem: "Give me a similar problem" };

/** One exchange: what the student asked and what the Copilot answered. */
function Exchange({ item, onQuickAction, onTryAgain, busy, labelFor }) {
  const a = item.assistant || {};
  const suggestions = [...new Set(a.suggestions || [])];
  return (
    <div className="chat-turn">
      <div className="bubble bubble-student">
        <span className="who">You</span>
        <p>{item.user?.text}</p>
      </div>
      <div className="bubble bubble-copilot">
        <span className="who">Copilot{a.is_ai === false ? " (rule-based)" : ""}</span>
        {a.title && <h3>{a.title}</h3>}
        {a.text && <p>{a.text}</p>}
        {a.sections?.map((s) => (
          <div key={s.title} className="chat-section">
            <h4>{s.title}</h4>
            {s.kind === "code" ? <pre className="code-block tight">{s.body}</pre> : <p>{s.body}</p>}
          </div>
        ))}
        {a.steps?.length > 0 && (
          <>
            <h4>Step by step</h4>
            <ol className="chat-steps">{a.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
          </>
        )}
        {a.outcome?.before && a.outcome?.after && (
          <p className="small"><b>Progress:</b> {a.outcome.before.passed} of {a.outcome.before.total} cases passed before, {a.outcome.after.passed} of {a.outcome.after.total} now.</p>
        )}
        {a.is_fallback && <Notice tone="warn">The AI provider could not be reached, so this answer comes from the built-in rules.</Notice>}
        {a.note && <Notice>{a.note}</Notice>}
        <div className="chips chat-actions">
          {a.try_again && (
            <button className="btn btn-sm btn-dark" onClick={() => onTryAgain(a.try_again.experiment_id)}>{a.try_again.label}</button>
          )}
          {a.try_again && (
            <button className="btn btn-sm" disabled={busy} onClick={() => onQuickAction("check_attempt")}>{labelFor("check_attempt")}</button>
          )}
          {suggestions.map((s) => (
            <button key={s} className="btn btn-sm" disabled={busy} onClick={() => onQuickAction(s)}>{labelFor(s)}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ContextCard({ context }) {
  const { experiment, score, latest_run: run, attempt, category, recent_mistakes: mistakes } = context;
  return (
    <div className="stack">
      <div>
        <b>{experiment.title}</b> <LevelChip level={experiment.difficulty} /> <StatusChip status={score.status} />
        <p className="small muted" style={{ marginTop: 4 }}>{experiment.objective}</p>
      </div>
      <dl className="ledger compact">
        <div><dt>Best score</dt><dd>{score.best_percent == null ? "None yet" : `${score.best_percent}%`}</dd></div>
        <div><dt>Attempts</dt><dd>{score.attempts}</dd></div>
        <div><dt>Hints this attempt</dt><dd>{attempt.hints_used} of {attempt.max_hints}</dd></div>
      </dl>
      <p className="small">
        {run ? `Latest ${run.kind === "submit" ? "graded submission" : "test run"}: ${run.passed} of ${run.total} cases match.` : "You have not run this experiment yet."}
        {category && <> Most recent problem area: <b>{category.label}</b>.</>}
      </p>
      {mistakes.length > 0 && (
        <div>
          <h3 className="subhead">Recent mistakes the Copilot can see</h3>
          <ul className="plain small">{mistakes.slice(0, 3).map((m, i) => <li key={i}>{m.label} in {m.experiment}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

export default function CopilotChat() {
  useTitle("AI Copilot");
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const wanted = params.get("experiment");
  const [expId, setExpId] = useState(wanted ? Number(wanted) : null);
  const [messages, setMessages] = useState(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [sendError, setSendError] = useState(null);
  const endRef = useRef(null);

  const ctx = useAsync(() => api.copilotContext(expId ?? undefined), [expId]);
  // Button text comes from the server's own action list, so the two stay in step.
  const labelFor = useCallback(
    (action) => (ctx.data?.quick_actions || []).find((a) => a.id === action)?.label || FALLBACK_LABELS[action] || action,
    [ctx.data],
  );
  const activeId = ctx.data?.experiment_id ?? null;

  useEffect(() => {
    if (activeId == null) return;
    let alive = true;
    setMessages(null);
    api.copilotMessages(activeId).then((r) => alive && setMessages(r)).catch(() => alive && setMessages([]));
    return () => { alive = false; };
  }, [activeId]);

  // scrollIntoView is missing in some environments (jsdom, older embedded browsers), so never assume it exists.
  useEffect(() => { endRef.current?.scrollIntoView?.({ block: "nearest" }); }, [messages, busy]);

  const send = useCallback(async (body) => {
    if (activeId == null) return;
    setBusy(true);
    setSendError(null);
    try {
      const exchange = await api.copilotSend({ experiment_id: activeId, ...body });
      setMessages((prev) => [...(prev || []), exchange]);
      setQuestion("");
      ctx.reload();      // hints used and the latest run may have changed
    } catch (e) {
      setSendError(e);
    } finally {
      setBusy(false);
    }
  }, [activeId, ctx]);

  const chooseExperiment = (id) => {
    setExpId(id);
    setParams(id ? { experiment: String(id) } : {}, { replace: true });
  };

  if (ctx.loading && !ctx.data) return <Loading label="Opening the Copilot" />;
  if (ctx.error) return <ErrorNote error={ctx.error} retry={ctx.reload} />;
  const { experiments, context, quick_actions: quickActions, provider } = ctx.data;
  if (!context) return <Empty title="No experiments yet">Ask your teacher to publish an experiment, then the Copilot can help with it.</Empty>;

  return (
    <>
      <PageHead title="AI Copilot">
        Ask about the experiment you are working on. The Copilot gives hints, explains errors in plain language and walks you through debugging. It never writes the solution for you.
      </PageHead>
      <div className="cols">
        <div>
          <Section
            title="Chat"
            aside={
              <label className="inline-field">
                <span>Experiment</span>
                <select value={activeId ?? ""} onChange={(e) => chooseExperiment(Number(e.target.value))} aria-label="Experiment to discuss">
                  {experiments.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
                </select>
              </label>
            }
          >
            {!provider.is_real && (
              <Notice tone="warn">
                <b>Development fallback.</b> No AI key is configured, so answers come from built-in rules applied to your real experiment, score, test results and recent mistakes. Quick actions work fully; free-text questions are matched to the closest quick action.
              </Notice>
            )}

            <div className="chat-log" role="log" aria-live="polite" aria-label="Conversation with the AI Copilot">
              {messages === null ? <Loading label="Loading your conversation" /> : messages.length === 0 ? (
                <Empty title="No messages yet">Pick a quick action below, or type a question about this experiment.</Empty>
              ) : (
                messages.map((m) => <Exchange key={m.id} item={m} busy={busy} labelFor={labelFor} onQuickAction={(action) => send({ action })} onTryAgain={(id) => navigate(`/experiments/${id}`)} />)
              )}
              {busy && <div className="bubble bubble-copilot"><Spinner /> Thinking</div>}
              <div ref={endRef} />
            </div>

            <div className="stack">
              <div>
                <h3 className="subhead">Quick actions</h3>
                <div className="chips">
                  {quickActions.map((a) => (
                    <button key={a.id} className="btn btn-sm" disabled={busy} onClick={() => send({ action: a.id })}>{a.label}</button>
                  ))}
                </div>
              </div>
              {sendError && <ErrorNote error={sendError} />}
              <form
                className="chat-compose"
                onSubmit={(e) => { e.preventDefault(); if (question.trim()) send({ message: question.trim() }); }}
              >
                <label className="sr-only" htmlFor="chat-input">Ask a question about this experiment</label>
                <input
                  id="chat-input" value={question} maxLength={500} disabled={busy}
                  onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about this experiment, for example: why does my loop stop early?"
                />
                <button className="btn btn-primary" type="submit" disabled={busy || !question.trim()}>{busy && <Spinner />}Send</button>
              </form>
            </div>
          </Section>
        </div>
        <div>
          <Section title="What the Copilot can see" aside={<Chip tone={provider.is_real ? "pass" : ""}>{provider.label}</Chip>}>
            <ContextCard context={context} />
            <p className="small muted" style={{ marginTop: 12 }}>
              Hidden test cases and the reference solution are never shared, with the Copilot or with an AI provider.
            </p>
          </Section>
        </div>
      </div>
    </>
  );
}
