import { Link } from "react-router-dom";
import { Chip, Empty } from "./ui";
import { MistakeBands } from "./viz";
import { ago } from "../lib/format";

const DIRECTION = {
  improving: ["Improving", "pass"], steady: ["Steady", ""], worsening: ["Getting worse", "fail"], not_enough_data: ["Trend needs more data", ""],
};

/** Mistake DNA for the signed-in student: recurring categories, trend, recent mistakes and targeted practice. */
export default function MistakeDNA({ data, full = false }) {
  if (!data.categories.length) {
    return <Empty title="No mistakes recorded">Patterns are detected from failing tests once you run or submit code.</Empty>;
  }
  const { improvement } = data;
  const [label, tone] = DIRECTION[improvement.direction] || DIRECTION.not_enough_data;
  const recurring = data.categories.filter((c) => c.recurring);
  const practise = recurring.filter((c) => c.practice.length > 0).slice(0, 3);
  return (
    <div className="stack-lg">
      <div>
        <h3 className="subhead">{recurring.length ? "Most frequent patterns" : "Patterns so far"}</h3>
        <MistakeBands categories={data.categories} showAdvice={full} />
        <p className="small muted" style={{ marginTop: 8 }}>
          A pattern is counted once per attempt, so re-running the same bug does not inflate it. Red lanes appeared in two or more attempts.
        </p>
      </div>

      <div>
        <h3 className="subhead">Improvement</h3>
        <p><Chip tone={tone}>{label}</Chip> {improvement.message}</p>
        {improvement.improved_categories.length > 0 && <p className="small">Fading: {improvement.improved_categories.join(", ")}.</p>}
        {improvement.worsening_categories.length > 0 && <p className="small">Growing: {improvement.worsening_categories.join(", ")}.</p>}
      </div>

      {data.recent?.length > 0 && (
        <div>
          <h3 className="subhead">Recent mistakes</h3>
          <ul className="plain">
            {data.recent.slice(0, full ? 8 : 4).map((m) => (
              <li key={m.id}>
                <b>{m.label}</b> in <Link to={`/experiments/${m.experiment_id}`}>{m.experiment_title}</Link>, {ago(m.created_at)}
                <div className="small muted">{m.detail}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!full && (
        <div>
          <h3 className="subhead">Practice suggestions</h3>
          {practise.length === 0 ? (
            <p className="small muted">No pattern has recurred yet, so nothing specific to practise.</p>
          ) : (
            <ul className="plain">
              {practise.map((c) => (
                <li key={c.category}>
                  Because <b>{c.label.toLowerCase()}</b> keeps coming back ({c.count} attempts): {c.tip}
                  <div className="small">Practise with {c.practice.map((p, i) => <span key={p.experiment_id}>{i > 0 && ", "}<Link to={`/experiments/${p.experiment_id}`}>{p.title}</Link></span>)}.</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
