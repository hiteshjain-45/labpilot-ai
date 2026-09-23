import { Link } from "react-router-dom";
import { Chip, StatusChip } from "./ui";
import { Meter } from "./viz";
import { ago, formatDate, plural } from "../lib/format";

function SkillRow({ s }) {
  const untouched = s.evidence_count === 0;
  return (
    <details className="skill">
      <summary>
        <div className="meter-row">
          <span>{s.skill}</span>
          <Meter value={s.mastery} label={`${s.skill} mastery`} />
          <span className="level">{untouched ? "No evidence yet" : <><b>{s.level}</b> {Math.round(s.mastery)}%</>}</span>
        </div>
      </summary>
      <div className="skill-body stack">
        <p className="small muted">{s.description}{s.last_evidence_at ? ` Last demonstrated ${ago(s.last_evidence_at)} (${formatDate(s.last_evidence_at)}).` : ""}</p>
        {s.contributors.length > 0 ? (
          <div className="table-wrap"><table className="table">
            <caption className="sr-only">Experiments that contributed to {s.skill}</caption>
            <thead><tr><th>Contributed by</th><th className="num">Best score</th><th className="num">Effect</th></tr></thead>
            <tbody>{s.contributors.map((c) => (
              <tr key={`${c.experiment_id}-${c.source}`}>
                <td className="title-cell"><Link to={`/experiments/${c.experiment_id}`}>{c.title}</Link><div className="small muted">{c.source_label}, {plural(c.events, "time")}</div></td>
                <td className="num">{c.best_percent != null ? `${c.best_percent}%` : "n/a"}</td>
                <td className="num">{c.delta >= 0 ? "+" : ""}{c.delta}</td>
              </tr>))}</tbody>
          </table></div>
        ) : <p className="small">No experiment has contributed to this skill yet.</p>}
        {s.trained_by.some((t) => t.status !== "mastered") && (
          <p className="small">
            Trained by: {s.trained_by.map((t, i) => (
              <span key={t.experiment_id}>{i > 0 && ", "}<Link to={`/experiments/${t.experiment_id}`}>{t.title}</Link> <StatusChip status={t.status} /></span>
            ))}
          </p>
        )}
      </div>
    </details>
  );
}

/** Skill Passport: level and progress per skill, the experiments behind each level, recent skills and practice needs. */
export default function SkillPassport({ passport }) {
  return (
    <div className="stack-lg">
      <div className="meters">{passport.skills.map((s) => <SkillRow key={s.skill} s={s} />)}</div>
      <p className="small muted">Select a skill to see which experiments moved it. Tick marks show the Developing, Proficient and Advanced thresholds.</p>

      <div>
        <h3 className="subhead">Recently demonstrated</h3>
        {passport.recent.length === 0 ? <p className="small muted">Nothing in the last 7 days. Submit an experiment to demonstrate a skill.</p> : (
          <ul className="plain">
            {passport.recent.map((r) => (
              <li key={r.skill}><b>{r.skill}</b> <Chip>{r.level}</Chip> {Math.round(r.mastery)}%, net {r.recent_change >= 0 ? "+" : ""}{r.recent_change} points this week, last practised {ago(r.last_evidence_at)}</li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="subhead">Needs more practice</h3>
        {passport.practice.length === 0 ? <p className="small muted">Every skill is at Proficient or above.</p> : (
          <ul className="plain">
            {passport.practice.map((p) => (
              <li key={p.skill}>
                <b>{p.skill}</b> is at {Math.round(p.mastery)}% ({p.level}).{" "}
                {p.suggestion ? <>Try <Link to={`/experiments/${p.suggestion.experiment_id}`}>{p.suggestion.title}</Link>.</> : "No published experiment trains this skill yet."}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
