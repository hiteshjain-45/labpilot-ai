import { Link } from "react-router-dom";
import { api } from "../api";
import SkillPassport from "../components/SkillPassport";
import { Chip, Empty, ErrorNote, LevelChip, Loading, PageHead, Section } from "../components/ui";
import { StackedRows } from "../components/viz";
import { ago, formatDate, pct } from "../lib/format";
import { useAsync, useTitle } from "../lib/hooks";

const STATUS_TONE = { Mastered: "pass", Strong: "pass", Practicing: "warn", Developing: "" };
const BANDS = [
  { key: "mastered", label: "Mastered", color: "#1b7f4b" },
  { key: "attempted", label: "Attempted", color: "#f2b705" },
  { key: "not_started", label: "Not started", color: "#f2f5f3" },
];
const ACHIEVEMENT = { mastered: "Experiment mastered", perfect: "Full marks", skill: "Skill level" };

function StatusCounts({ skills, order }) {
  const counts = order.map((status) => ({ status, n: skills.filter((s) => s.status === status).length }));
  return (
    <div className="chips">
      {counts.map(({ status, n }) => <Chip key={status} tone={STATUS_TONE[status]}>{status}: {n}</Chip>)}
    </div>
  );
}

export default function SkillPassportPage() {
  useTitle("Skill Passport");
  const { data, error, loading, reload } = useAsync(() => api.skillPassport(), []);
  if (loading && !data) return <Loading label="Loading your Skill Passport" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  const { profile, summary, by_difficulty: levels, skills, status_order: order, strengths, improving, needs_improvement: gaps, achievements, mistake_dna: dna } = data;

  return (
    <>
      <PageHead title="Skill Passport">
        A record of what you have demonstrated in the lab. Every number here comes from your own submissions, scores and mistake patterns: nothing is estimated.
      </PageHead>

      <dl className="ledger">
        <div><dt>Student</dt><dd>{profile.full_name}</dd></div>
        {profile.roll_number && <div><dt>Roll number</dt><dd>{profile.roll_number}</dd></div>}
        {profile.cohort && <div><dt>Course and section</dt><dd>{profile.cohort}</dd></div>}
        <div><dt>Experiments completed</dt><dd>{summary.completed} of {summary.experiments_total}</dd></div>
        <div><dt>Experiments mastered</dt><dd>{summary.mastered} of {summary.experiments_total}</dd></div>
        <div><dt>Average best score</dt><dd>{pct(summary.average_percent)}</dd></div>
        <div><dt>Overall progress</dt><dd>{summary.overall_progress}%</dd></div>
      </dl>

      <div className="cols">
        <div>
          <Section title="Coding skills developed" aside={<StatusCounts skills={skills} order={order} />}>
            <ul className="plain">
              {skills.map((s) => (
                <li key={s.skill}>
                  <details className="skill">
                    <summary>
                      <div className="meter-row">
                        <span>{s.skill}</span>
                        <span className="level"><Chip tone={STATUS_TONE[s.status]}>{s.status}</Chip> {Math.round(s.mastery)}%</span>
                      </div>
                    </summary>
                    <div className="skill-body stack">
                      <p className="small muted">{s.description}{s.evidence_count ? ` Demonstrated ${s.evidence_count} time${s.evidence_count === 1 ? "" : "s"}, last ${ago(s.last_evidence_at)}.` : " Not demonstrated yet."}</p>
                      {s.mistakes.length > 0 && (
                        <p className="small">
                          Mistake DNA: {s.mistakes.map((m) => `${m.label} (${m.count}${m.recurring ? ", recurring" : ""})`).join(", ")}.{" "}
                          <Link to="/progress">Review mistakes</Link>
                        </p>
                      )}
                      <p className="small">
                        {s.links.practice
                          ? <><Link to={`/experiments/${s.links.practice.experiment_id}`}>Practice this skill</Link> with {s.links.practice.title}. </>
                          : "Every experiment that trains this skill is already mastered. "}
                        {s.links.related.length > 0 && (
                          <>Related experiments: {s.links.related.map((r, i) => (
                            <span key={r.experiment_id}>{i > 0 && ", "}<Link to={`/experiments/${r.experiment_id}`}>{r.title}</Link></span>
                          ))}.</>
                        )}
                      </p>
                    </div>
                  </details>
                </li>
              ))}
            </ul>
            <p className="small muted">
              Status comes from your scores: <b>Developing</b> until a skill is demonstrated, <b>Practicing</b> while it is being built,
              <b> Strong</b> above 45%, and <b>Mastered</b> above 70% once an experiment that trains it is mastered. A mistake pattern that keeps
              coming back holds a skill at Practicing until it fades.
            </p>
          </Section>

          <Section title="Progress by level" aside="Each bar is every experiment at that level">
            <StackedRows
              legend={BANDS}
              rows={levels.map((l) => ({
                label: l.difficulty[0].toUpperCase() + l.difficulty.slice(1),
                sub: `${l.mastered} mastered, ${l.attempted} attempted, ${l.not_started} not started${l.average_percent != null ? `, average ${l.average_percent}%` : ""}`,
                segments: BANDS.map((b) => ({ ...b, value: l[b.key] })),
              }))}
            />
          </Section>

          <Section title="Full skill record" aside="The same evidence, experiment by experiment">
            <SkillPassport passport={data} />
          </Section>
        </div>

        <div>
          <Section title="Strengths">
            {strengths.length === 0 ? <Empty title="Nothing at Strong yet">Master an experiment to build a skill up.</Empty> : (
              <ul className="plain">
                {strengths.map((s) => (
                  <li key={s.skill}><b>{s.skill}</b> <Chip tone={STATUS_TONE[s.status]}>{s.status}</Chip> {Math.round(s.mastery)}%, from {s.evidence_count} pieces of evidence</li>
                ))}
              </ul>
            )}
            {improving.length > 0 && (
              <p className="small" style={{ marginTop: 10 }}>
                Improving this week: {improving.map((i) => `${i.skill} (+${i.recent_change})`).join(", ")}.
              </p>
            )}
          </Section>

          <Section title="Skills needing improvement">
            {gaps.length === 0 ? <Empty title="No gaps right now" /> : (
              <ul className="plain">
                {gaps.map((g) => (
                  <li key={g.skill}>
                    <b>{g.skill}</b> <Chip tone={STATUS_TONE[g.status]}>{g.status}</Chip> {Math.round(g.mastery)}%
                    {g.mistakes.length > 0 && <div className="small">Because of {g.mistakes.map((m) => `${m.label.toLowerCase()} (${m.count})`).join(" and ")}.</div>}
                    {g.practice && <div className="small"><Link to={`/experiments/${g.practice.experiment_id}`}>Practice this skill</Link> with {g.practice.title}</div>}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Recent achievements">
            {achievements.length === 0 ? <Empty title="None yet">Master an experiment to earn your first one.</Empty> : (
              <ul className="plain">
                {achievements.map((a) => (
                  <li key={a.kind + a.title}>
                    <b>{a.title}</b> <Chip>{ACHIEVEMENT[a.kind]}</Chip>
                    <div className="small muted">{a.detail}, {formatDate(a.at)}</div>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Mistake patterns" aside={<Link to="/progress">Full Mistake DNA</Link>}>
            {dna.total === 0 ? <Empty title="No mistakes recorded yet" /> : (
              <>
                <ul className="plain">
                  {dna.top.map((m) => (
                    <li key={m.category}>
                      <b>{m.label}</b> <Chip tone={m.recurring ? "fail" : ""}>{m.count}x</Chip>
                      {m.skill && <div className="small muted">Affects {m.skill}</div>}
                    </li>
                  ))}
                </ul>
                <p className="small" style={{ marginTop: 10 }}>{dna.improvement.message}</p>
              </>
            )}
          </Section>
        </div>
      </div>
    </>
  );
}
