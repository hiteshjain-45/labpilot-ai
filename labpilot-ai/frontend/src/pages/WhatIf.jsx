import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import WhatIfExplore from "../components/WhatIfExplore";
import { Chip, Empty, ErrorNote, LevelChip, Loading, Notice, PageHead, Section } from "../components/ui";
import { useAsync, useTitle } from "../lib/hooks";

const RISK = { High: "fail", Medium: "warn", Low: "pass" };

/** A dedicated page for the What-If engine. The simulation itself is the existing WhatIfExplore panel,
 *  so the workspace tab and this page always behave identically. */
export default function WhatIf() {
  useTitle("What-If");
  const experiments = useAsync(() => api.experiments(), []);
  const [expId, setExpId] = useState(null);
  useEffect(() => {
    if (expId == null && experiments.data?.length) setExpId(experiments.data[0].id);
  }, [experiments.data, expId]);

  const conditions = useAsync(() => (expId ? api.whatIfConditions(expId) : Promise.resolve(null)), [expId]);

  if (experiments.loading && !experiments.data) return <Loading label="Loading experiments" />;
  if (experiments.error) return <ErrorNote error={experiments.error} retry={experiments.reload} />;
  const list = experiments.data || [];
  const chosen = list.find((e) => e.id === expId);

  return (
    <>
      <PageHead title="What-If">
        Change one part of a program and see what it would do. Each simulation runs your own code both ways and compares the results, so the prediction is measured, not guessed.
      </PageHead>
      <Notice tone="warn">
        What-If results are produced by running your code and comparing outputs, with fixed rules for the explanations. No language model is involved, and nothing here changes your scores.
      </Notice>

      <div className="cols">
        <div>
          <Section
            title="Simulation"
            aside={
              <label className="inline-field">
                <span>Experiment</span>
                <select value={expId ?? ""} onChange={(e) => setExpId(Number(e.target.value))} aria-label="Experiment to simulate">
                  {list.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
                </select>
              </label>
            }
          >
            {list.length === 0 ? <Empty title="No experiments published yet" /> : expId && <WhatIfExplore expId={expId} />}
          </Section>
        </div>

        <div>
          <Section title="Concepts you can change here" aside={chosen && <LevelChip level={chosen.difficulty} />}>
            {conditions.loading && !conditions.data ? <Loading /> : conditions.error ? <ErrorNote error={conditions.error} retry={conditions.reload} /> : (
              (conditions.data?.conditions || []).length === 0 ? (
                <Empty title="No changes fit this experiment yet">These simulations need a sample input made of numbers, and code to change.</Empty>
              ) : (
                <ul className="plain">
                  {conditions.data.conditions.map((c) => (
                    <li key={c.id}>
                      <b>{c.concept || c.label}</b> <Chip tone={RISK[c.risk]}>{c.risk} risk</Chip>
                      <div className="small muted">{c.question}</div>
                      <div className="small">
                        {c.category_label && <>Mistake DNA: {c.category_label}. </>}
                        {c.skill && <>Skill: {c.skill}.</>}
                      </div>
                    </li>
                  ))}
                </ul>
              )
            )}
            <p className="small muted" style={{ marginTop: 10 }}>
              Risk is how often this kind of change turns into a real bug. After a simulation it is re-judged from what actually happened.
            </p>
          </Section>

          <Section title="Where this connects">
            <p className="small">
              Every simulation names the <Link to="/progress">Mistake DNA</Link> category it belongs to, with how many times you have made it,
              and the <Link to="/passport">Skill Passport</Link> skill it exercises. Where a category has practice available, the result links to it.
            </p>
            <p className="small muted">
              The same simulation is available inside an experiment, under the <b>What if</b> tab, alongside predict-and-check.
            </p>
          </Section>
        </div>
      </div>
    </>
  );
}
