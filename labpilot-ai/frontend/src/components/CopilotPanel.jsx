import { useEffect, useState } from "react";
import { api } from "../api";
import { Chip, Notice, Spinner } from "./ui";

function HintCard({ h, compact = false }) {
  return (
    <div className="hint-card">
      <div className="chips">
        <Chip tone="info">{h.category_label}</Chip>
        <Chip>Hint {h.hint_level} of 3</Chip>
        {!compact && <Chip tone={h.is_ai ? "pass" : ""}>{h.provider_label}</Chip>}
      </div>
      {h.is_fallback && (
        <Notice tone="warn">
          {h.fallback_reason === "solution_leak_blocked"
            ? "The AI reply was blocked because it gave away too much of the solution. This guidance comes from built-in rules instead."
            : "The AI provider could not be reached, so this guidance comes from built-in rules."}
        </Notice>
      )}
      {h.note && !compact && <Notice>{h.note}</Notice>}
      <div><h4>What is going wrong</h4><p>{h.explanation}</p></div>
      <div><h4>Hint</h4><p>{h.hint}</p></div>
      {h.concept_to_review && <div><h4>Concept to review</h4><p>{h.concept_to_review}</p></div>}
      {h.next_step && <div><h4>Next step</h4><p>{h.next_step}</p></div>}
    </div>
  );
}

export default function CopilotPanel({ expId, getCode, getConsole, hintsUsed, onHint, aiReal }) {
  const [items, setItems] = useState(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    // Merge rather than replace: a hint requested before the history arrives must not be lost or duplicated.
    const merge = (loaded) => (prev) => {
      const known = new Set((prev || []).map((h) => h.interaction_id));
      return [...(prev || []), ...loaded.filter((h) => !known.has(h.interaction_id))].sort((a, b) => b.interaction_id - a.interaction_id);
    };
    api.hintHistory(expId).then((r) => alive && setItems(merge(r))).catch(() => alive && setItems((prev) => prev || []));
    return () => { alive = false; };
  }, [expId]);

  async function ask() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.hint(expId, { code: getCode(), question: question.trim() || null, console_output: getConsole() });
      setItems((prev) => [result, ...(prev || [])]);
      onHint?.(result);
      setQuestion("");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  // Only a hint requested in the current attempt is shown as current guidance; older ones stay under "Earlier hints".
  const all = items || [];
  const showCurrent = hintsUsed > 0 && all.length > 0;
  const latest = showCurrent ? all[0] : null;
  const older = showCurrent ? all.slice(1) : all;
  return (
    <div className="stack">
      <p className="small muted">
        The Copilot reads your latest test results and code, then nudges you towards the fix. It never writes the solution for you. Each request moves up one hint level, and the levels start again after each graded submission.
      </p>
      {!aiReal && (
        <Notice tone="warn">
          <b>Development fallback.</b> No AI key is configured, so hints come from built-in rules applied to your real test results, errors and mistake history. Set an API key on the server to get AI-written hints.
        </Notice>
      )}
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor="copilot-q">Ask a question</label>
        <textarea id="copilot-q" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={500} rows={3} disabled={!aiReal}
          placeholder={aiReal ? "For example: why does my loop stop early?" : "Questions are read once an AI provider is configured."} />
      </div>
      <div className="between">
        <button className="btn btn-dark" onClick={ask} disabled={busy}>{busy ? <Spinner /> : null}Get a hint</button>
        <span className="small muted">Hints this attempt: {hintsUsed}</span>
      </div>
      {error && <Notice tone="error">{error.message}</Notice>}
      {items === null && <p className="small muted">Loading earlier hints</p>}
      {items !== null && !latest && <p className="small muted">No hint requested in this attempt yet.</p>}
      {latest && <HintCard h={latest} />}
      {older.length > 0 && (
        <details>
          <summary>Earlier hints ({older.length})</summary>
          <div className="stack-lg" style={{ marginTop: 12 }}>{older.map((h) => <HintCard key={h.interaction_id} h={h} compact />)}</div>
        </details>
      )}
    </div>
  );
}
