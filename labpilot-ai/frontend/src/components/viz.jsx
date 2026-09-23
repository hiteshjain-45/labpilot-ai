import { Link } from "react-router-dom";
import { formatDate } from "../lib/format";

/* ---------- skill meters (Skill Passport) ---------- */
export function Meter({ value, marks = [20, 45, 70], label }) {
  const v = Math.max(0, Math.min(100, value || 0));
  return (
    <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v)} aria-label={label}>
      <i style={{ width: `${v}%` }} />
      {marks.map((m) => <u key={m} style={{ left: `${m}%` }} />)}
    </div>
  );
}

export function SkillMeters({ skills }) {
  return (
    <div className="meters">
      {skills.map((s) => (
        <div className="meter-row" key={s.skill} title={s.description}>
          <span>{s.skill}</span>
          <Meter value={s.mastery} label={`${s.skill} mastery`} />
          <span className="level">{s.evidence_count ? <><b>{s.level}</b> {Math.round(s.mastery)}%</> : "No evidence yet"}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------- Mistake DNA: one gel lane per category ---------- */
const TREND = { rising: "Rising", falling: "Falling", new: "New this fortnight", steady: "Steady", quiet: "Quiet lately" };

export function MistakeBands({ categories, aggregate = false, showAdvice = false }) {
  const max = Math.max(1, ...categories.map((c) => c.count));
  return (
    <div className="bands">
      {categories.map((c) => (
        <div key={c.category}>
          <div className="band">
            <span>{c.label}</span>
            <div className="gel" role="img" aria-label={`${c.label}: ${c.count}`}><i className={c.recurring ? "recurring" : ""} style={{ width: `${Math.max(4, (c.count / max) * 100)}%` }} /></div>
            <small>
              {aggregate ? `${c.count} in ${c.students_affected} ${c.students_affected === 1 ? "student" : "students"}` : `${c.count}x${c.recurring ? ", recurring" : ""}`}
              {!aggregate && c.trend && c.trend !== "quiet" ? `, ${TREND[c.trend].toLowerCase()}` : ""}
            </small>
          </div>
          {showAdvice && (
            <div className="small muted" style={{ margin: "4px 0 4px 0" }}>
              <div><b>Concept:</b> {c.concept}. {c.tip}</div>
              {c.practice?.length > 0 && (
                <div>Practise with: {c.practice.map((p, i) => <span key={p.experiment_id}>{i > 0 && ", "}<Link to={`/experiments/${p.experiment_id}`}>{p.title}</Link></span>)}</div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ---------- charts ---------- */
export function LineChart({ points, threshold = 80 }) {
  const W = 560, H = 220, L = 36, R = 28, T = 12, B = 30;
  const y = (v) => T + (1 - v / 100) * (H - T - B);
  const x = (i) => (points.length === 1 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (points.length - 1));
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.percent).toFixed(1)}`).join(" ");
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Graded scores over time: ${points.map((p) => `${p.percent}%`).join(", ")}`}>
      {[0, 50, 100].map((g) => (
        <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="#cbd6d2" /><text x={L - 6} y={y(g) + 4} textAnchor="end">{g}%</text></g>
      ))}
      <line x1={L} x2={W - R} y1={y(threshold)} y2={y(threshold)} stroke="#1b7f4b" strokeDasharray="5 4" />
      <text x={W - R} y={y(threshold) - 5} textAnchor="end" style={{ fill: "#1b7f4b" }}>Mastery {threshold}%</text>
      <path d={path} fill="none" stroke="#123b33" strokeWidth="2" />
      {points.map((p, i) => (
        <g key={p.submission_id}>
          <circle cx={x(i)} cy={y(p.percent)} r="5" fill={p.percent >= threshold ? "#1b7f4b" : "#f2b705"} stroke="#123b33" strokeWidth="1.5"><title>{`${p.experiment_title}: ${p.percent}%`}</title></circle>
          <text x={x(i)} y={H - 10} textAnchor="middle" style={{ fontSize: 11 }}>{formatDate(p.created_at, false)}</text>
        </g>
      ))}
    </svg>
  );
}

export function ActivityChart({ days }) {
  const W = 560, H = 190, L = 30, T = 8, B = 26;
  const max = Math.max(4, ...days.map((d) => d.runs + d.submissions));
  const bw = (W - L) / days.length;
  const y = (v) => T + (1 - v / max) * (H - T - B);
  return (
    <>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Runs and graded submissions per day">
        {[0, Math.round(max / 2), max].map((g) => <g key={g}><line x1={L} x2={W} y1={y(g)} y2={y(g)} stroke="#cbd6d2" /><text x={L - 5} y={y(g) + 4} textAnchor="end">{g}</text></g>)}
        {days.map((d, i) => {
          const x = L + i * bw + 4, w = bw - 8;
          return (
            <g key={d.date}>
              <rect x={x} y={y(d.submissions)} width={w} height={y(0) - y(d.submissions)} fill="#123b33"><title>{`${d.date}: ${d.submissions} graded`}</title></rect>
              <rect x={x} y={y(d.submissions + d.runs)} width={w} height={y(d.submissions) - y(d.submissions + d.runs)} fill="#9fb1ab"><title>{`${d.date}: ${d.runs} runs`}</title></rect>
              {i % 2 === 0 && <text x={x + w / 2} y={H - 8} textAnchor="middle" style={{ fontSize: 11 }}>{d.date.slice(8)}</text>}
            </g>
          );
        })}
      </svg>
      <div className="legend"><span><i style={{ background: "#123b33" }} />Graded submissions</span><span><i style={{ background: "#9fb1ab" }} />Practice runs</span></div>
    </>
  );
}

export function Bars({ rows }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="bands">
      {rows.map((r) => (
        <div className="band" key={r.label} style={{ gridTemplateColumns: "88px minmax(0, 2fr) 34px" }}>
          <span>{r.label}</span>
          <div className="gel" role="img" aria-label={`${r.label}: ${r.value}`}><i style={{ width: `${r.value ? Math.max(4, (r.value / max) * 100) : 0}%` }} /></div>
          <small>{r.value}</small>
        </div>
      ))}
    </div>
  );
}

/** Rows of stacked horizontal bars. segments: [{ key, label, value, color }]; the legend comes from `legend`. */
export function StackedRows({ rows, legend }) {
  return (
    <div>
      {rows.map((r) => {
        const total = r.segments.reduce((n, s) => n + s.value, 0) || 1;
        const text = r.segments.filter((s) => s.value > 0).map((s) => `${s.value} ${s.label.toLowerCase()}`).join(", ") || "no data";
        return (
          <div className="stack-row" key={r.label}>
            <span>{r.label}</span>
            <div className="stack-bar" role="img" aria-label={`${r.label}: ${text}`}>
              {r.segments.filter((s) => s.value > 0).map((s) => <i key={s.key} title={`${s.value} ${s.label}`} style={{ width: `${(100 * s.value) / total}%`, background: s.color }} />)}
            </div>
            {r.sub && <span className="sub">{r.sub}</span>}
          </div>
        );
      })}
      <div className="legend">{legend.map((l) => <span key={l.key}><i style={{ background: l.color }} />{l.label}</span>)}</div>
    </div>
  );
}
