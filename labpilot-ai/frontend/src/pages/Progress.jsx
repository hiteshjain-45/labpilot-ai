import { Link } from "react-router-dom";
import { api } from "../api";
import MistakeDNA from "../components/MistakeDNA";
import SkillPassport from "../components/SkillPassport";
import { Empty, ErrorNote, LevelChip, Loading, PageHead, Section } from "../components/ui";
import { ago } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

const DECISIONS = {
  new: "You have no graded work yet, so the plan starts at beginner level.",
  advance: "Your recent scores are strong and the current level is complete, so the plan moves up a level.",
  consolidate: "Your recent scores are strong, but experiments at this level remain, so the plan finishes them first.",
  hold: "Your recent scores are middling, so the plan stays at the same level.",
  ease: "Your recent scores are low, so the plan steps back a level to rebuild the basics.",
};

export default function Progress() {
  useTitle("My progress");
  const skills = useAsync(() => api.skills(), []);
  const mistakes = useAsync(() => api.mistakes(), []);
  const reco = useAsync(() => api.recommendation(), []);
  const history = useAsync(() => api.recommendationHistory(), []);
  const rec = reco.data?.recommendation;
  const s = rec?.signals;
  const cases = s?.failed_cases;

  return (
    <>
      <PageHead title="My progress">Your skill passport, recurring mistake patterns and why each experiment was recommended.</PageHead>
      <div className="cols">
        <div>
          <Section title="Skill passport" aside={skills.data ? `Overall ${Math.round(skills.data.overall)}%` : null}>
            {skills.loading && !skills.data ? <Loading /> : skills.error ? <ErrorNote error={skills.error} retry={skills.reload} /> : (
              <>
                <SkillPassport passport={skills.data} />
                <p className="small muted" style={{ marginTop: 12 }}>
                  Mastery moves towards your score on each graded experiment that trains the skill, and rises faster than it falls, so one bad day never erases progress.
                  {skills.data.strongest && <> Strongest so far: <b>{skills.data.strongest}</b>. Needs most work: <b>{skills.data.weakest}</b>.</>}
                </p>
              </>
            )}
          </Section>
          <Section title="Mistake DNA" aside={mistakes.data ? `${mistakes.data.total} recorded patterns` : null}>
            {mistakes.loading && !mistakes.data ? <Loading /> : mistakes.error ? <ErrorNote error={mistakes.error} retry={mistakes.reload} /> : <MistakeDNA data={mistakes.data} full />}
          </Section>
        </div>
        <div>
          <Section title="Why this experiment next">
            {reco.loading && !reco.data ? <Loading /> : reco.error ? <ErrorNote error={reco.error} retry={reco.reload} /> : !rec ? <Empty title="Everything is mastered">There is nothing left to recommend.</Empty> : (
              <div className="stack">
                <div><b><Link to={`/experiments/${rec.experiment_id}`}>{rec.experiment_title}</Link></b> <LevelChip level={rec.difficulty} /></div>
                <p>{rec.reason}</p>
                <details>
                  <summary>How was this chosen?</summary>
                  <div className="stack small" style={{ marginTop: 8 }}>
                    <p>{DECISIONS[s.decision]}</p>
                    <p>Recent average: {s.recent_average == null ? "no graded work" : `${Math.round(s.recent_average * 100)}% over ${s.recent_submissions} submissions`}. Target level: {s.target_difficulty}.</p>
                    {s.top_mistakes?.length > 0 && <p>Most frequent recent mistakes: {s.top_mistakes.map(([c, n]) => `${c.replace("_", " ")} (${n})`).join(", ")}.</p>}
                    {cases && <p>Failed test cases in those submissions: {cases.normal} ordinary, {cases.edge} edge, {cases.performance} performance ({cases.hidden} hidden).</p>}
                    <p className="muted">The rules are fixed and visible: difficulty fit, overlap with your mistake patterns and failed edge or performance cases, gaps in the skills an experiment trains, and a bonus for finishing what you started.</p>
                  </div>
                </details>
              </div>
            )}
          </Section>
          <Section title="Recommendation history">
            {history.loading && !history.data ? <Loading /> : history.error ? <ErrorNote error={history.error} retry={history.reload} /> : history.data.length === 0 ? <Empty title="None yet" /> : (
              <ul className="plain">
                {history.data.map((h) => (
                  <li key={h.id}>
                    <details>
                      <summary><b>{h.experiment_title}</b>, {h.followed ? "started" : "not started yet"}, {ago(h.created_at)}</summary>
                      <p className="small" style={{ marginTop: 6 }}>{h.reason}</p>
                    </details>
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
