import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { Chip, ErrorNote, Field, Loading, Notice, PageHead, Section, Spinner } from "../../components/ui";
import { useAsync, useTitle } from "../../lib/hooks";

const BLANK = {
  title: "", objective: "", problem_statement: "", instructions: "", starter_code: "", reference_solution: "",
  difficulty: "beginner", skills: [], focus_categories: [], concepts: [], hints: [], what_if_scenarios: [],
  max_score: 100, estimated_minutes: 20, is_published: false, position: 0,
};
const BLANK_TEST = { name: "", stdin: "", expected_output: "", kind: "normal", is_hidden: false, weight: 1 };
const BLANK_SCENARIO = { id: "", title: "", description: "", stdin: "", modified_code: "", explanation: "" };
const EDITABLE = Object.keys(BLANK);

function TestForm({ initial, kinds, saveLabel, onSave, onCancel }) {
  const [t, setT] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setT((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  async function save() {
    setBusy(true); setError(null);
    try { await onSave({ ...t, weight: Number(t.weight) || 1 }); if (!initial.id && initial === BLANK_TEST) setT(BLANK_TEST); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return (
    <div className="stack" style={{ padding: 12, background: "var(--wash)", border: "1px solid var(--rule)", borderRadius: 3 }}>
      <div className="grid-3">
        <Field label="Case name" id={`tn-${initial.id || "new"}`}><input id={`tn-${initial.id || "new"}`} type="text" value={t.name} onChange={set("name")} /></Field>
        <Field label="Kind" id={`tk-${initial.id || "new"}`}><select id={`tk-${initial.id || "new"}`} value={t.kind} onChange={set("kind")}>{kinds.map((k) => <option key={k} value={k}>{k === "normal" ? "Normal" : k === "edge" ? "Edge case" : "Performance"}</option>)}</select></Field>
        <Field label="Weight" id={`tw-${initial.id || "new"}`}><input id={`tw-${initial.id || "new"}`} type="number" min="1" max="10" value={t.weight} onChange={set("weight")} /></Field>
      </div>
      <div className="grid-2">
        <Field label="Input (stdin)" id={`ti-${initial.id || "new"}`}><textarea id={`ti-${initial.id || "new"}`} className="code" rows={3} value={t.stdin} onChange={set("stdin")} /></Field>
        <Field label="Expected output" id={`te-${initial.id || "new"}`}><textarea id={`te-${initial.id || "new"}`} className="code" rows={3} value={t.expected_output} onChange={set("expected_output")} /></Field>
      </div>
      <label className="check"><input type="checkbox" checked={t.is_hidden} onChange={set("is_hidden")} /> Hidden from students until they submit</label>
      {error && <Notice tone="error">{error.message}</Notice>}
      <div className="actions">
        <button type="button" className="btn btn-dark btn-sm" onClick={save} disabled={busy || !t.name.trim()}>{busy && <Spinner />}{saveLabel}</button>
        {onCancel && <button type="button" className="btn btn-sm" onClick={onCancel}>Cancel</button>}
      </div>
    </div>
  );
}

function TestCases({ expId, tests, setTests, kinds }) {
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState(null);
  const keyOf = (t) => t.id ?? t._key;

  async function add(body) {
    const created = expId ? await api.teacher.addTest(expId, body) : { ...body, _key: crypto.randomUUID() };
    setTests((prev) => [...prev, created]);
    setAdding(false);
  }
  async function update(t, body) {
    const saved = t.id ? await api.teacher.updateTest(expId, t.id, body) : { ...t, ...body };
    setTests((prev) => prev.map((x) => (keyOf(x) === keyOf(t) ? saved : x)));
    setEditing(null);
  }
  async function remove(t) {
    if (!window.confirm(`Delete the test case "${t.name}"?`)) return;
    setError(null);
    try {
      if (t.id) await api.teacher.deleteTest(expId, t.id);
      setTests((prev) => prev.filter((x) => keyOf(x) !== keyOf(t)));
    } catch (e) { setError(e); }
  }

  return (
    <div className="stack">
      {error && <ErrorNote error={error} />}
      {tests.length === 0 && <p className="muted">No test cases yet. Students need at least one visible or hidden case to run code.</p>}
      {tests.map((t, i) => (
        <div key={keyOf(t)}>
          {editing === keyOf(t) ? (
            <TestForm initial={t} kinds={kinds} saveLabel="Save case" onSave={(b) => update(t, b)} onCancel={() => setEditing(null)} />
          ) : (
            <div className="between" style={{ borderBottom: "1px solid var(--rule)", paddingBottom: 8 }}>
              <div>
                <b>{i + 1}. {t.name}</b>{" "}
                <span className="chips" style={{ display: "inline-flex" }}><Chip>{t.kind}</Chip><Chip tone={t.is_hidden ? "warn" : "pass"}>{t.is_hidden ? "Hidden" : "Visible"}</Chip>{t.weight > 1 && <Chip>Weight {t.weight}</Chip>}</span>
                <div className="small muted nowrap" style={{ overflow: "hidden", textOverflow: "ellipsis", maxWidth: "60ch" }}>Input: {(t.stdin || "(empty)").replace(/\n/g, " / ").slice(0, 80)}</div>
              </div>
              <div className="actions"><button type="button" className="btn btn-sm" onClick={() => setEditing(keyOf(t))}>Edit</button><button type="button" className="btn btn-sm btn-danger" onClick={() => remove(t)}>Delete</button></div>
            </div>
          )}
        </div>
      ))}
      {adding ? <TestForm initial={BLANK_TEST} kinds={kinds} saveLabel="Add case" onSave={add} onCancel={() => setAdding(false)} /> : <div><button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>Add a test case</button></div>}
    </div>
  );
}

function Editor({ saved }) {
  const navigate = useNavigate();
  const taxonomy = useAsync(() => api.taxonomy(), []);
  const [form, setForm] = useState(saved ? Object.fromEntries(EDITABLE.map((k) => [k, saved[k]])) : BLANK);
  const [tests, setTests] = useState(saved ? saved.test_cases : []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [check, setCheck] = useState(null);
  const [checking, setChecking] = useState(false);
  const id = saved?.id;
  useTitle(saved ? `Edit ${saved.title}` : "New experiment");

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const lines = (k) => ({ value: form[k].join("\n"), onChange: (e) => setForm((f) => ({ ...f, [k]: e.target.value.split("\n") })) });
  const toggle = (k, v) => setForm((f) => ({ ...f, [k]: f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v] }));
  const setScenario = (i, k) => (e) => setForm((f) => ({ ...f, what_if_scenarios: f.what_if_scenarios.map((s, j) => (j === i ? { ...s, [k]: e.target.value } : s)) }));

  async function save(e) {
    e.preventDefault();
    setBusy(true); setError(null); setMessage(null);
    const body = { ...form, max_score: Number(form.max_score), estimated_minutes: Number(form.estimated_minutes), position: Number(form.position) };
    try {
      if (id) {
        await api.teacher.updateExperiment(id, body);
        setMessage("Saved.");
      } else {
        const created = await api.teacher.createExperiment({ ...body, test_cases: tests.map(({ name, stdin, expected_output, kind, is_hidden, weight }) => ({ name, stdin, expected_output, kind, is_hidden, weight })) });
        navigate(`/teacher/experiments/${created.id}`, { replace: true });
      }
    } catch (err) { setError(err); } finally { setBusy(false); }
  }

  async function validate() {
    setChecking(true); setCheck(null); setError(null);
    try { setCheck(await api.teacher.validate(id)); } catch (err) { setError(err); } finally { setChecking(false); }
  }

  async function remove() {
    if (!window.confirm("Delete this experiment? Every student's attempts and results for it are deleted too. This cannot be undone.")) return;
    try { await api.teacher.deleteExperiment(id); navigate("/teacher/experiments", { replace: true }); } catch (err) { setError(err); }
  }

  const tx = taxonomy.data;
  return (
    <>
      <PageHead title={saved ? "Edit experiment" : "New experiment"} actions={<Link className="btn" to="/teacher/experiments">All experiments</Link>}>
        {saved ? "Changes apply to students straight away. Test cases save as you edit them." : "Fill in the details, add test cases, then save. Save as a draft to keep it hidden from students."}
      </PageHead>
      <form onSubmit={save} style={{ maxWidth: 900 }}>
        <Section title="Details">
          <Field label="Title" id="title"><input id="title" type="text" value={form.title} onChange={set("title")} required /></Field>
          <div className="grid-3">
            <Field label="Level" id="difficulty"><select id="difficulty" value={form.difficulty} onChange={set("difficulty")}>{(tx?.difficulties || ["beginner", "intermediate", "advanced"]).map((d) => <option key={d} value={d}>{d[0].toUpperCase() + d.slice(1)}</option>)}</select></Field>
            <Field label="Estimated minutes" id="minutes"><input id="minutes" type="number" min="1" value={form.estimated_minutes} onChange={set("estimated_minutes")} /></Field>
            <Field label="Maximum score" id="max"><input id="max" type="number" min="1" value={form.max_score} onChange={set("max_score")} /></Field>
          </div>
          <div className="grid-3">
            <Field label="Order in the list" id="position" hint="Lower numbers come first."><input id="position" type="number" min="0" value={form.position} onChange={set("position")} /></Field>
            <div className="field"><span className="label">Visibility</span><label className="check"><input type="checkbox" checked={form.is_published} onChange={set("is_published")} /> Published to students</label></div>
          </div>
        </Section>

        <Section title="Statement">
          <Field label="Aim" id="objective" hint="One or two sentences on what the student will practise."><textarea id="objective" rows={2} value={form.objective} onChange={set("objective")} /></Field>
          <Field label="Problem" id="problem" hint="Describe the input and output format and give an example. Separate paragraphs with a blank line."><textarea id="problem" rows={8} value={form.problem_statement} onChange={set("problem_statement")} /></Field>
          <Field label="Procedure" id="instructions" hint="Start a line with a dash to make a bullet. Use backticks for code."><textarea id="instructions" rows={6} value={form.instructions} onChange={set("instructions")} /></Field>
        </Section>

        <Section title="Code">
          <Field label="Starter code" id="starter" hint="What the student sees first. Programs read stdin and print to stdout."><textarea id="starter" className="code" rows={7} value={form.starter_code} onChange={set("starter_code")} spellCheck={false} /></Field>
          <Field label="Reference solution" id="reference" hint="Never shown to students and never sent to the AI, but the checker below runs it against your test cases."><textarea id="reference" className="code" rows={10} value={form.reference_solution} onChange={set("reference_solution")} spellCheck={false} /></Field>
          {id && (
            <div className="stack">
              <div><button type="button" className="btn btn-sm" onClick={validate} disabled={checking}>{checking && <Spinner />}Check reference solution against test cases</button></div>
              {check && (
                <div className="stack">
                  <Notice tone={check.all_passed ? "ok" : "error"}>{check.all_passed ? "The reference solution passes every test case." : `The reference solution passes ${check.results.filter((r) => r.passed).length} of ${check.results.length} cases (${check.score_percent}%). Fix the solution or the expected outputs below.`}</Notice>
                  {check.results.filter((r) => !r.passed).map((r) => (
                    <div key={r.name} className="small"><b>{r.name}</b> ({r.status})<pre className="code-block tight">Expected: {r.expected_output}{"\n"}Actual: {r.actual_output || "(nothing)"}{r.stderr ? `\n${r.stderr}` : ""}</pre></div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Section>

        <Section title="Skills and mistake patterns">
          <div className="field"><span className="label">Skills this experiment trains</span>
            <div className="grid-2">{(tx?.skills || []).map((s) => <label className="check" key={s}><input type="checkbox" checked={form.skills.includes(s)} onChange={() => toggle("skills", s)} />{s}</label>)}</div></div>
          <div className="field"><span className="label">Mistake patterns it practises</span><span className="hint">Used to suggest this experiment to students who repeat these mistakes.</span>
            <div className="grid-2">{(tx?.categories || []).map((c) => <label className="check" key={c.key}><input type="checkbox" checked={form.focus_categories.includes(c.key)} onChange={() => toggle("focus_categories", c.key)} />{c.label}</label>)}</div></div>
          <Field label="Concepts to review" id="concepts" hint="One per line. Shown to students as the Copilot's concept suggestions."><textarea id="concepts" rows={3} {...lines("concepts")} /></Field>
          <Field label="Hint ladder for the Copilot" id="hints" hint="Up to five hints, one per line, from gentle to specific. The Copilot uses these as background and does not quote them."><textarea id="hints" rows={4} {...lines("hints")} /></Field>
        </Section>

        <Section title="What-if scenarios" aside="Up to five">
          <div className="stack-lg">
            {form.what_if_scenarios.map((s, i) => (
              <div key={i} className="panel"><div className="panel-body">
                <div className="grid-2">
                  <Field label="Scenario id" id={`s-id-${i}`} hint="Lowercase letters, digits and dashes."><input id={`s-id-${i}`} type="text" value={s.id} onChange={setScenario(i, "id")} /></Field>
                  <Field label="Title" id={`s-t-${i}`}><input id={`s-t-${i}`} type="text" value={s.title} onChange={setScenario(i, "title")} /></Field>
                </div>
                <Field label="What changes" id={`s-d-${i}`}><textarea id={`s-d-${i}`} rows={2} value={s.description} onChange={setScenario(i, "description")} /></Field>
                <Field label="Modified program" id={`s-c-${i}`}><textarea id={`s-c-${i}`} className="code" rows={6} value={s.modified_code} onChange={setScenario(i, "modified_code")} spellCheck={false} /></Field>
                <div className="grid-2">
                  <Field label="Default input" id={`s-i-${i}`}><textarea id={`s-i-${i}`} className="code" rows={2} value={s.stdin} onChange={setScenario(i, "stdin")} /></Field>
                  <Field label="Explanation shown afterwards" id={`s-e-${i}`}><textarea id={`s-e-${i}`} rows={2} value={s.explanation} onChange={setScenario(i, "explanation")} /></Field>
                </div>
                <button type="button" className="btn btn-sm btn-danger" onClick={() => setForm((f) => ({ ...f, what_if_scenarios: f.what_if_scenarios.filter((_, j) => j !== i) }))}>Remove scenario</button>
              </div></div>
            ))}
            {form.what_if_scenarios.length < 5 && <div><button type="button" className="btn btn-sm" onClick={() => setForm((f) => ({ ...f, what_if_scenarios: [...f.what_if_scenarios, { ...BLANK_SCENARIO }] }))}>Add a scenario</button></div>}
          </div>
        </Section>

        {error && <div style={{ marginBottom: 14 }}><ErrorNote error={error} /></div>}
        {message && <div style={{ marginBottom: 14 }}><Notice tone="ok">{message}</Notice></div>}
        <div className="actions">
          <button className="btn btn-primary" type="submit" disabled={busy}>{busy && <Spinner />}{saved ? "Save changes" : "Create experiment"}</button>
          {id && <button className="btn btn-danger" type="button" onClick={remove}>Delete experiment</button>}
        </div>
      </form>

      <div style={{ maxWidth: 900, marginTop: 34 }}>
        <Section title="Test cases" aside={tests.length ? `${tests.length} total, ${tests.filter((t) => t.is_hidden).length} hidden` : null}>
          <TestCases expId={id} tests={tests} setTests={setTests} kinds={tx?.test_kinds || ["normal", "edge", "performance"]} />
        </Section>
      </div>
    </>
  );
}

export default function ExperimentEditor() {
  const { id } = useParams();
  const { data, error, loading, reload } = useAsync(() => (id ? api.teacher.experiment(id) : Promise.resolve(null)), [id]);
  if (loading && !data && id) return <Loading />;
  if (error) return <div className="stack"><ErrorNote error={error} retry={reload} /><Link to="/teacher/experiments">Back to experiments</Link></div>;
  return <Editor key={id || "new"} saved={data} />;
}
