import { Link, useParams } from "react-router-dom";
import { api } from "../../api";
import { Chip, Empty, ErrorNote, LevelChip, Loading, PageHead, Section, StatusChip } from "../../components/ui";
import { SkillMeters } from "../../components/viz";
import { ago, pct, score } from "../../lib/format";
import { useAsync, useTitle } from "../../lib/hooks";

export default function StudentDetail() {
  const { id } = useParams();
  const { data, error, loading, reload } = useAsync(() => api.teacher.student(id), [id]);
  useTitle(data?.student.full_name);
  if (loading && !data) return <Loading />;
  if (error) return <div className="stack"><ErrorNote error={error} retry={reload} /><Link to="/teacher/students">Back to students</Link></div>;
  const { student, experiments, submissions, skills } = data;
  return (
    <>
      <PageHead title={student.full_name} actions={<Link className="btn" to="/teacher/students">All students</Link>}>{[student.roll_number, student.cohort, student.email].filter(Boolean).join(", ")}</PageHead>
      <div className="cols">
        <div>
          <Section title="Experiment progress">
            <div className="table-wrap"><table className="table">
              <thead><tr><th>Experiment</th><th>Level</th><th className="num">Attempts</th><th className="num">Best score</th><th>Status</th></tr></thead>
              <tbody>{experiments.map((e) => <tr key={e.id}><td className="title-cell">{e.title}</td><td><LevelChip level={e.difficulty} /></td><td className="num">{e.attempts}</td><td className="num">{pct(e.best_percent)}</td><td><StatusChip status={e.status} /></td></tr>)}</tbody>
            </table></div>
          </Section>
          <Section title="Graded submissions">
            {submissions.length === 0 ? <Empty title="Nothing graded yet" /> : (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Experiment</th><th>Cases</th><th className="num">Score</th><th>When</th><th><span className="sr-only">Open</span></th></tr></thead>
                <tbody>{submissions.map((s) => (
                  <tr key={s.id}>
                    <td className="title-cell">{s.experiment_title}</td>
                    <td><Chip tone={s.status === "passed" ? "pass" : s.status === "partial" ? "warn" : "fail"}>{s.passed_count}/{s.total_count}</Chip></td>
                    <td className="num">{score(s.score, s.max_score)}</td><td className="nowrap">{ago(s.created_at)}</td>
                    <td><Link to={`/teacher/submissions/${s.id}`}>Review code</Link></td>
                  </tr>))}</tbody>
              </table></div>
            )}
          </Section>
        </div>
        <div>
          <Section title="Skill passport" aside={`Overall ${Math.round(data.skills_overall)}%`}><SkillMeters skills={skills} /></Section>
          <p className="small muted">Mistake patterns and AI conversations are private to the student. Teachers see class-wide totals only.</p>
        </div>
      </div>
    </>
  );
}
