import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ErrorNote, LevelChip, Loading, Notice, PageHead, Section, StatusChip, Empty, Chip } from "../components/ui";
import MistakeDNA from "../components/MistakeDNA";
import SkillPassport from "../components/SkillPassport";
import { LineChart } from "../components/viz";
import { ago, pct, plural, score } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

export function NextUp({ rec, experiments }) {
  const navigate = useNavigate();
  if (!rec) return <Notice tone="ok">You have mastered every experiment. Ask your teacher for more, or revisit one to improve your score.</Notice>;
  const exp = experiments?.find((e) => e.id === rec.experiment_id);
  return (
    <div className="next-up">
      <div className="meta"><LevelChip level={rec.difficulty} />{exp && <Chip>About {exp.estimated_minutes} min</Chip>}{exp && exp.progress.best_percent != null && <Chip>Best so far {exp.progress.best_percent}%</Chip>}</div>
      <h2>{rec.experiment_title}</h2>
      <p className="why">{rec.reason}</p>
      <div className="actions"><button className="btn btn-primary" onClick={() => navigate(`/experiments/${rec.experiment_id}`)}>Open experiment</button></div>
    </div>
  );
}

export default function Dashboard() {
  useTitle("Dashboard");
  const { data, error, loading, reload } = useAsync(() => api.dashboard(), []);
  if (loading && !data) return <Loading label="Loading your dashboard" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  const { student, stats, experiments, recommendation, score_history, recent_attempts, passport, mistakes } = data;

  return (
    <>
      <PageHead title={`Welcome back, ${student.full_name.split(" ")[0]}`}>{student.cohort || "Your practical file at a glance."}</PageHead>
      <h2 className="sr-only">Recommended next</h2>
      <NextUp rec={recommendation} experiments={experiments} />
      <dl className="ledger">
        <div><dt>Mastered</dt><dd>{stats.experiments_mastered} of {stats.experiments_total}</dd></div>
        <div><dt>Average best score</dt><dd>{pct(stats.average_percent)}</dd></div>
        <div><dt>Graded submissions</dt><dd>{stats.submissions}</dd></div>
        <div><dt>Test runs</dt><dd>{stats.runs}</dd></div>
      </dl>
      <div className="cols">
        <div>
          <Section title="Experiments" aside={<Link to="/experiments">Details</Link>}>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Experiment</th><th>Level</th><th className="num">Best score</th><th>Status</th></tr></thead>
                <tbody>
                  {experiments.map((e) => (
                    <tr key={e.id}>
                      <td className="title-cell"><Link to={`/experiments/${e.id}`}>{e.title}</Link></td>
                      <td><LevelChip level={e.difficulty} /></td>
                      <td className="num">{e.progress.best_percent != null ? `${e.progress.best_percent}%` : "None yet"}</td>
                      <td><StatusChip status={e.progress.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
          <Section title="Graded scores" aside="Last 12 graded submissions">
            {score_history.length ? <LineChart points={score_history} /> : <Empty title="No graded submissions yet">Submit an experiment for grading and your scores will be charted here.</Empty>}
          </Section>
          <Section title="Recent attempts">
            {recent_attempts.length ? (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Experiment</th><th>Attempt</th><th>Outcome</th><th className="num">Hints</th><th>Started</th></tr></thead>
                <tbody>
                  {recent_attempts.map((a) => (
                    <tr key={a.id}>
                      <td className="title-cell"><Link to={`/experiments/${a.experiment_id}`}>{a.experiment_title}</Link></td>
                      <td>{a.attempt_number}</td>
                      <td>{a.status === "submitted" ? `Graded ${score(a.score, a.max_score)}` : `In progress, ${plural(a.run_count, "run")}`}</td>
                      <td className="num">{a.hints_used}</td>
                      <td className="nowrap">{ago(a.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
            ) : <Empty title="No attempts yet">Open an experiment and run your first test.</Empty>}
          </Section>
        </div>
        <div>
          <Section title="Skill passport" aside={<Link to="/progress">Full passport</Link>}>
            <SkillPassport passport={passport} />
          </Section>
          <Section title="Mistake DNA" aside={mistakes.total ? `${plural(mistakes.total, "recorded pattern")}` : null}>
            <MistakeDNA data={mistakes} />
          </Section>
        </div>
      </div>
    </>
  );
}
