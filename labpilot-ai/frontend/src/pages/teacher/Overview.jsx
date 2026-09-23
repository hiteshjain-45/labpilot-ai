import { Link } from "react-router-dom";
import { api } from "../../api";
import { Chip, Empty, ErrorNote, LevelChip, Loading, PageHead, Section } from "../../components/ui";
import { ActivityChart, Bars, MistakeBands, StackedRows } from "../../components/viz";
import { pct, plural } from "../../lib/format";
import { useAsync, useTitle } from "../../lib/hooks";

const NONE = "repeating-linear-gradient(45deg, #ffffff, #ffffff 3px, #d3dcd8 3px, #d3dcd8 6px)"; // hatched: no data yet
const LEVELS = [
  { key: "Novice", label: "Novice", color: "#cbd6d2" }, { key: "Developing", label: "Developing", color: "#f2b705" },
  { key: "Proficient", label: "Proficient", color: "#4f8f7c" }, { key: "Advanced", label: "Advanced", color: "#123b33" },
];
const COMPLETION = [
  { key: "mastered", label: "Mastered", color: "#1b7f4b" }, { key: "attempted", label: "Graded, below 80%", color: "#f2b705" },
  { key: "in_progress", label: "Started, not graded", color: "#7fa8d1" }, { key: "not_started", label: "Not started", color: NONE },
];
const DIFFICULTY_TONE = { Hard: "fail", Moderate: "warn", Easy: "pass" };
const PRIORITY_TONE = { high: "fail", medium: "warn", low: "" };

export default function Overview() {
  useTitle("Class overview");
  const { data, error, loading, reload } = useAsync(() => api.teacher.overview(), []);
  if (loading && !data) return <Loading label="Loading class overview" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  const { counts, experiments, activity, common_mistakes, score_distribution, skill_distribution, needs_practice, completion, viva } = data;
  return (
    <>
      <PageHead title="Class overview">Performance across the whole class. Mistake patterns and skill levels are shown as totals; the support list uses scores and attempts only.</PageHead>
      <dl className="ledger">
        <div><dt>Students</dt><dd>{counts.active_students} of {counts.students} active</dd></div>
        <div><dt>Published experiments</dt><dd>{counts.published_experiments}</dd></div>
        <div><dt>Graded submissions</dt><dd>{counts.graded_submissions}</dd></div>
        <div><dt>Average best score</dt><dd>{pct(data.average_percent)}</dd></div>
        <div><dt>Average first attempt</dt><dd>{pct(data.first_attempt_percent)}</dd></div>
        <div><dt>AI Viva practice</dt><dd>{viva.sessions === 0 ? "None yet" : `${viva.sessions} by ${viva.students} student${viva.students === 1 ? "" : "s"}${viva.average_percent != null ? `, ${viva.average_percent}% average` : ""}`}</dd></div>
        <div><dt>Experiments mastered</dt><dd>{completion.mastered} of {completion.possible}{completion.rate != null ? ` (${completion.rate}%)` : ""}</dd></div>
      </dl>

      <Section title="Students who may need extra practice" aside="Scores and attempts only">
        {needs_practice.length === 0 ? <Empty title="Nobody currently meets the criteria" /> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Student</th><th>Priority</th><th>Why</th><th className="num">Average best</th><th className="num">Graded</th></tr></thead>
            <tbody>{needs_practice.map((f) => (
              <tr key={f.student_id}>
                <td className="title-cell"><Link to={`/teacher/students/${f.student_id}`}>{f.full_name}</Link></td>
                <td><Chip tone={PRIORITY_TONE[f.priority]}>{f.priority[0].toUpperCase() + f.priority.slice(1)}</Chip></td>
                <td><ul className="reasons">{f.reasons.map((r) => <li key={r}>{r}</li>)}</ul></td>
                <td className="num">{pct(f.average_percent)}</td><td className="num">{f.graded_submissions}</td>
              </tr>))}</tbody>
          </table></div>
        )}
        <p className="small muted" style={{ marginTop: 8 }}>
          Flagged when a student has 3 or more graded attempts on one experiment, an average best score under 60%, nothing submitted after 3 days, or no submissions for 7 days with work left.
          Mistake profiles and Copilot conversations stay private to each student.
        </p>
      </Section>

      <Section title="Experiments" aside="Difficulty is judged from the class's first graded try">
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Experiment</th><th className="num">Students</th><th className="num">Best score</th><th className="num">First attempt</th><th>Observed difficulty</th><th>Most common mistake</th><th>Viva practice</th><th className="num">Hints</th></tr></thead>
          <tbody>
            {experiments.map((e) => (
              <tr key={e.id}>
                <td className="title-cell"><Link to={`/teacher/experiments/${e.id}`}>{e.title}</Link><div className="chips" style={{ marginTop: 3 }}><LevelChip level={e.difficulty} />{!e.is_published && <Chip tone="warn">Draft</Chip>}</div></td>
                <td className="num">{e.students_attempted}</td>
                <td className="num">{pct(e.average_percent)}</td>
                <td className="num">{pct(e.first_attempt_percent)}</td>
                <td><Chip tone={DIFFICULTY_TONE[e.difficulty_label] || ""}>{e.difficulty_label}</Chip></td>
                <td>{e.top_mistake ? <>{e.top_mistake.label}<div className="small muted">{plural(e.top_mistake.count, "attempt")}, {plural(e.top_mistake.students_affected, "student")}</div></> : <span className="muted">None recorded</span>}</td>
                <td>{e.viva.sessions === 0 ? <span className="muted">None yet</span> : (<>{e.viva.average_percent}% average<div className="small muted">{e.viva.sessions} viva{e.viva.sessions === 1 ? "" : "s"}, {e.viva.students} student{e.viva.students === 1 ? "" : "s"}</div></>)}</td>
                <td className="num">{e.avg_hints_used}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </Section>

      <div className="cols">
        <div>
          <Section title="Completion by experiment" aside={`Each bar is all ${counts.students} students`}>
            <StackedRows
              legend={COMPLETION}
              rows={experiments.map((e) => ({
                label: e.title, sub: `${e.completion.mastered} mastered, ${e.completion.attempted} graded below 80%, ${e.completion.in_progress} started, ${e.completion.not_started} not started`,
                segments: COMPLETION.map((c) => ({ ...c, value: e.completion[c.key] })),
              }))}
            />
          </Section>
          <Section title="Activity" aside="Last 14 days"><ActivityChart days={activity} /></Section>
        </div>
        <div>
          <Section title="Common mistakes" aside="Class totals">
            {common_mistakes.length ? <MistakeBands categories={common_mistakes} aggregate /> : <Empty title="No mistakes recorded yet" />}
            <p className="small muted" style={{ marginTop: 10 }}>Each pattern is counted once per attempt. Individual students' mistake profiles are not shown to teachers.</p>
          </Section>
          <Section title="Skill distribution" aside={`Each bar is all ${counts.students} students`}>
            <StackedRows
              legend={[...LEVELS, { key: "none", label: "No evidence yet", color: NONE }]}
              rows={skill_distribution.map((s) => ({
                label: s.skill,
                sub: s.students_with_evidence
                  ? `Average ${Math.round(s.average_mastery)}% across ${plural(s.students_with_evidence, "student")}${s.not_started ? `, ${s.not_started} without evidence` : ""}`
                  : "No student has demonstrated this yet",
                segments: [...LEVELS.map((l) => ({ ...l, value: s.levels[l.key] })), { key: "none", label: "No evidence yet", color: NONE, value: s.not_started }],
              }))}
            />
          </Section>
          <Section title="Where students stand" aside="Average best score per student">
            <Bars rows={score_distribution.map((b) => ({ label: b.range, value: b.students }))} />
          </Section>
        </div>
      </div>
    </>
  );
}
