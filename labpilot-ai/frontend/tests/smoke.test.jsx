/**
 * Browser-level smoke test: the real React app is rendered in jsdom and talks to a RUNNING backend that has
 * been seeded (`python -m app.seed --reset`, then `uvicorn app.main:app`). Only the CodeMirror editor is
 * swapped for a plain textarea, because CodeMirror needs real browser layout.
 */
import ErrorBoundary from "../src/components/ErrorBoundary";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { setToken } from "../src/api";
import { AuthProvider } from "../src/auth";

vi.mock("../src/components/CodeEditor.jsx", () => ({
  default: ({ value, onChange, readOnly }) => <textarea aria-label="Python code editor" value={value} readOnly={readOnly} onChange={(e) => onChange?.(e.target.value)} />,
}));

const BASE = process.env.SMOKE_API_URL || "http://127.0.0.1:8000";
const tokens = {};
async function login(email, password) {
  const r = await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  if (!r.ok) throw new Error(`Cannot sign in as ${email}: is the backend running and seeded?`);
  return (await r.json()).access_token;
}
function renderAt(path, token) {
  setToken(token || null);
  return render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>);
}
const findText = (text, opts) => screen.findByText(text, { exact: false, ...opts }, { timeout: 15000 });
const heading = (name) => screen.findByRole("heading", { name }, { timeout: 15000 });

beforeAll(async () => {
  tokens.student = await login("student@labpilot.demo", "Student@123");
  tokens.teacher = await login("teacher@labpilot.demo", "Teacher@123");
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => { localStorage.clear(); });

describe("authentication", () => {
  it("signs in through the form and lands on the student dashboard", async () => {
    renderAt("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "student@labpilot.demo");
    await userEvent.type(screen.getByLabelText("Password"), "Student@123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await heading("Welcome back, Ananya")).toBeTruthy();
    expect(await heading("Prime Number Checker")).toBeTruthy(); // the recommendation
  });

  it("shows a readable error for wrong credentials", async () => {
    renderAt("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "student@labpilot.demo");
    await userEvent.type(screen.getByLabelText("Password"), "not-the-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent.toLowerCase()).toContain("incorrect");
  });

  it("sends signed-out visitors to the sign-in page and keeps students out of teacher pages", async () => {
    renderAt("/dashboard");
    expect(await heading("Sign in")).toBeTruthy();
  });

  it("redirects a student who opens a teacher URL", async () => {
    renderAt("/teacher/students", tokens.student);
    expect(await heading(/Welcome back/)).toBeTruthy();
  });
});

describe("student pages", () => {
  it("dashboard shows the learning layers", async () => {
    renderAt("/dashboard", tokens.student);
    await heading("Welcome back, Ananya");
    for (const text of ["Skill passport", "Mistake DNA", "Graded scores", "Recent attempts"]) expect(await heading(text)).toBeTruthy();
    expect(screen.getAllByText("Mastered").length).toBeGreaterThan(0);
    expect(document.querySelector("svg[role='img']")).toBeTruthy(); // score chart rendered
  });

  it("lists every experiment", async () => {
    renderAt("/experiments", tokens.student);
    for (const title of ["Factorial Calculator", "List Statistics", "Prime Number Checker", "Sorting and Binary Search"]) expect(await findText(title)).toBeTruthy();
  });

  it("progress page explains the recommendation", async () => {
    renderAt("/progress", tokens.student);
    expect(await heading("Skill passport")).toBeTruthy();
    expect(await heading("Why this experiment next")).toBeTruthy();
    await userEvent.click(await screen.findByText("How was this chosen?"));
    expect(await findText("Recent average")).toBeTruthy();
  });

  it("workspace: run, hint, what-if and graded submission all work end to end", async () => {
    renderAt("/experiments/1", tokens.student);
    expect(await heading("Factorial Calculator")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Aim" })).toBeTruthy();
    const editor = screen.getByLabelText("Python code editor");
    expect(editor.value).toContain("input");

    fireEvent.change(editor, { target: { value: "n = int(input())\nresult = 1\nfor i in range(2, n + 1):\n    result *= i\nprint(result)\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Run tests" }));
    expect(await findText("Test run: 3 of 3 visible cases match")).toBeTruthy();

    // Copilot: broken code gets a rule-based hint
    fireEvent.change(editor, { target: { value: "n = int(input('n? '))\nprint(n)\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Run tests" }));
    await findText("Test run: 0 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Get a hint" }));
    expect(await findText("What is going wrong")).toBeTruthy();
    expect((await screen.findAllByText("Hint 1 of 3", { exact: false })).length).toBeGreaterThan(0); // the collapsed list of earlier hints may repeat it

    // What-if
    await userEvent.click(screen.getByRole("tab", { name: "What if" }));
    await userEvent.type(await screen.findByLabelText("Your prediction"), "24");
    await userEvent.click(screen.getByRole("button", { name: "Run the experiment" }));
    expect(await findText("Your prediction was right")).toBeTruthy();

    // Graded submission
    fireEvent.change(editor, { target: { value: "n = int(input())\nresult = 1\nfor i in range(2, n + 1):\n    result *= i\nprint(result)\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Submit for grading" }));
    expect(await findText("Result: 6 of 6 observations match. Score 100 / 100")).toBeTruthy();
    await userEvent.click(screen.getByRole("tab", { name: "History" }));
    expect((await screen.findAllByText("Load code")).length).toBeGreaterThan(0);
  });

  it("hides hidden test data from the student's observation table", async () => {
    renderAt("/experiments/1", tokens.student);
    await heading("Factorial Calculator");
    fireEvent.change(screen.getByLabelText("Python code editor"), { target: { value: "print(0)\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Submit for grading" }));
    await findText("Result:");
    expect(screen.getAllByText("Hidden").length).toBeGreaterThan(0);
  });
});

describe("teacher pages", () => {
  it("overview shows class statistics and aggregate-only mistakes", async () => {
    renderAt("/teacher", tokens.teacher);
    expect(await heading("Class overview")).toBeTruthy();
    expect(await heading("Common mistakes")).toBeTruthy();
    expect(await findText("support list uses scores and attempts only")).toBeTruthy();
    // Mistake data is aggregate: no student's name may appear inside the class-wide mistakes section
    const roster = await apiGet("/api/teacher/students", tokens.teacher);
    const mistakesSection = (await heading("Common mistakes")).closest("section").textContent;
    for (const student of roster) expect(mistakesSection).not.toContain(student.full_name);
  });

  it("roster links to a student's detail page", async () => {
    renderAt("/teacher/students", tokens.teacher);
    await userEvent.click(await screen.findByRole("link", { name: "Priya Nair" }));
    expect(await heading("Priya Nair")).toBeTruthy();
    expect(await heading("Skill passport")).toBeTruthy();
    expect(await heading("Graded submissions")).toBeTruthy();
  });

  it("submission review reveals hidden cases to the teacher", async () => {
    renderAt("/teacher/submissions", tokens.teacher);
    const links = await screen.findAllByRole("link", { name: "Review" });
    await userEvent.click(links[0]);
    expect(await heading("Submitted code")).toBeTruthy();
    expect((await screen.findAllByText("Hidden from students")).length).toBeGreaterThan(0);
  });

  it("creates, checks, and deletes an experiment through the editor", async () => {
    renderAt("/teacher/experiments/new", tokens.teacher);
    await userEvent.type(await screen.findByLabelText("Title"), "Double a Number");
    await userEvent.type(screen.getByLabelText("Aim"), "Practise reading input.");
    await userEvent.type(screen.getByLabelText("Problem"), "Read an integer and print twice its value.");
    fireEvent.change(screen.getByLabelText("Reference solution"), { target: { value: "print(int(input()) * 2)\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Add a test case" }));
    await userEvent.type(screen.getByLabelText("Case name"), "basic");
    fireEvent.change(screen.getByLabelText("Input (stdin)"), { target: { value: "21\n" } });
    fireEvent.change(screen.getByLabelText("Expected output"), { target: { value: "42\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Add case" }));
    await userEvent.click(screen.getByRole("button", { name: "Create experiment" }));

    expect(await heading("Edit experiment")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /Check reference solution/ }));
    expect(await findText("passes every test case")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Delete experiment" }));
    expect(await heading("Experiments")).toBeTruthy();
    await waitFor(() => expect(screen.queryByText("Double a Number")).toBeNull());
  });
});

/* ------------------------------------------------------------------------------------------------
 * The pages must show what the API returns, not literals, and must render cleanly.
 * ---------------------------------------------------------------------------------------------- */
async function apiPost(path, body, token) {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

async function apiGet(path, token) {
  const r = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}
const textOf = (selector) => (document.querySelector(selector)?.textContent || "").replace(/\s+/g, "");
const settle = () => waitFor(() => expect(document.querySelector(".spinner")).toBeNull(), { timeout: 15000 });

describe("pages display the backend's numbers", () => {
  it("student dashboard ledger, skills and recommendation equal the API response", async () => {
    const d = await apiGet("/api/students/me/dashboard", tokens.student);
    renderAt("/dashboard", tokens.student);
    await heading(/Welcome back/);
    await settle();
    const ledger = textOf("dl.ledger");
    expect(ledger).toContain(`Mastered${d.stats.experiments_mastered}of${d.stats.experiments_total}`);
    expect(ledger).toContain(`Gradedsubmissions${d.stats.submissions}`);
    expect(ledger).toContain(`Testruns${d.stats.runs}`);
    expect(ledger).toContain(`Averagebestscore${Math.round(d.stats.average_percent)}%`);
    expect(await heading(d.recommendation.experiment_title)).toBeTruthy();
    const meters = textOf(".meters");
    for (const s of d.passport.skills.filter((x) => x.evidence_count > 0)) expect(meters).toContain(`${s.level}${Math.round(s.mastery)}%`.replace(/\s+/g, ""));
    expect(document.querySelectorAll(".chart circle").length).toBe(d.score_history.length);
  });

  it("teacher overview ledger and experiment table equal the API response", async () => {
    const o = await apiGet("/api/teacher/overview", tokens.teacher);
    renderAt("/teacher", tokens.teacher);
    await heading("Class overview");
    await settle();
    const ledger = textOf("dl.ledger");
    expect(ledger).toContain(`Students${o.counts.active_students}of${o.counts.students}active`);
    expect(ledger).toContain(`Gradedsubmissions${o.counts.graded_submissions}`);
    expect(ledger).toContain(`Averagebestscore${o.average_percent}%`);
    const rows = [...document.querySelectorAll("table.table tbody tr")].map((r) => r.textContent.replace(/\s+/g, ""));
    for (const e of o.experiments) expect(rows.some((r) => r.includes(e.title.replace(/\s+/g, "")) && r.includes(`${e.students_attempted}`))).toBe(true);
    for (const m of o.common_mistakes) expect(textOf(".bands")).toContain(m.label.replace(/\s+/g, ""));
  });

  it("a graded submission made in the UI changes the dashboard totals", async () => {
    const before = (await apiGet("/api/students/me/dashboard", tokens.student)).stats;
    renderAt("/experiments/2", tokens.student);
    await heading(/List Statistics/);
    fireEvent.change(screen.getByLabelText("Python code editor"), { target: { value: "print(0)\n" } });
    await userEvent.click(screen.getByRole("button", { name: "Submit for grading" }));
    await findText("Result:");
    const after = (await apiGet("/api/students/me/dashboard", tokens.student)).stats;
    expect(after.submissions).toBe(before.submissions + 1);
    document.body.innerHTML = "";
    renderAt("/dashboard", tokens.student);
    await heading(/Welcome back/);
    await settle();
    expect(textOf("dl.ledger")).toContain(`Gradedsubmissions${after.submissions}`);
  });
});

describe("every page renders cleanly with live data", () => {
  it("shows no undefined, NaN, null or [object Object] and raises no React errors", async () => {
    const errors = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args) => errors.push(args.map(String).join(" ")));
    const subs = await apiGet("/api/teacher/submissions?limit=1", tokens.teacher);
    const roster = await apiGet("/api/teacher/students", tokens.teacher);
    const pages = [
      ["student", "/dashboard"], ["student", "/experiments"], ["student", "/experiments/1"], ["student", "/experiments/4"], ["student", "/progress"],
      ["teacher", "/teacher"], ["teacher", "/teacher/students"], ["teacher", `/teacher/students/${roster[0].id}`], ["teacher", "/teacher/experiments"],
      ["teacher", "/teacher/experiments/1"], ["teacher", "/teacher/experiments/new"], ["teacher", "/teacher/submissions"], ["teacher", `/teacher/submissions/${subs.items[0].id}`],
    ];
    for (const [who, path] of pages) {
      const view = renderAt(path, tokens[who]);
      await waitFor(() => expect(document.querySelector("h1")).toBeTruthy(), { timeout: 15000 });
      await settle();
      await new Promise((r) => setTimeout(r, 150));
      const text = document.body.textContent;
      expect(text, `${path} renders a placeholder value`).not.toMatch(/\bundefined\b|\bNaN\b|\bnull\b|\[object Object\]/);
      view.unmount();
    }
    spy.mockRestore();
    const real = errors.filter((e) => /unique "key"|Invalid|Unknown prop|Cannot update|Maximum update|uncontrolled|controlled|Objects are not valid/i.test(e));
    expect(real).toEqual([]);
  });
});


/* ------------------------------------------------------------------------------------------------
 * LabPilot AI intelligence layer as the user sees it.
 * ---------------------------------------------------------------------------------------------- */
async function registerFresh(tag) {
  const email = `${tag}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@ui.test`;
  const r = await fetch(`${BASE}/api/auth/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: "Password1!", full_name: "UI Learner" }) });
  return (await r.json()).access_token;
}
const OFF_BY_ONE = "n = int(input())\nresult = 1\nfor i in range(1, n):\n    result *= i\nprint(result)\n";

describe("intelligence layer in the UI", () => {
  it("dashboard shows recurring patterns, recent mistakes, the trend and practice suggestions from the API", async () => {
    const d = await apiGet("/api/students/me/dashboard", tokens.student);
    renderAt("/dashboard", tokens.student);
    await heading(/Welcome back/);
    await settle();
    for (const name of ["Most frequent patterns", "Improvement", "Recent mistakes", "Practice suggestions"]) expect(await heading(name)).toBeTruthy();
    const body = document.body.textContent;
    expect(body).toContain(d.mistakes.improvement.message);
    expect(body).toContain(d.mistakes.recent[0].label);
    expect(body).toContain(d.mistakes.recent[0].experiment_title);
    const recurring = d.mistakes.categories.find((c) => c.recurring && c.practice.length);
    expect(recurring).toBeTruthy();
    expect(body).toContain(recurring.tip);
    expect(body).toContain(recurring.practice[0].title);
  });

  it("each skill row lists the experiments that contributed to it; recent and practice lists come from the API", async () => {
    const p = await apiGet("/api/skills/me", tokens.student);
    renderAt("/progress", tokens.student);
    await heading("Skill passport");
    await settle();
    const rows = [...document.querySelectorAll("details.skill")];
    expect(rows.length).toBe(p.skills.length);
    const contributing = p.skills.filter((s) => s.contributors.length);
    expect(contributing.length).toBeGreaterThan(0);
    for (const s of contributing) {
      const row = rows.find((r) => r.querySelector("summary").textContent.startsWith(s.skill));
      for (const c of s.contributors) expect(row.textContent).toContain(c.title);
    }
    await heading("Recently demonstrated");
    await heading("Needs more practice");
    for (const r of p.recent) expect(document.body.textContent).toContain(r.skill);
    for (const r of p.practice) expect(document.body.textContent).toContain(r.skill);
  });

  it("teacher overview shows skill distribution, completion and the support list, using scores and attempts only", async () => {
    const o = await apiGet("/api/teacher/overview", tokens.teacher);
    renderAt("/teacher", tokens.teacher);
    await heading("Class overview");
    await settle();
    for (const name of ["Completion by experiment", "Skill distribution"]) expect(await heading(name)).toBeTruthy();
    const support = await heading("Students who may need extra practice");
    const body = document.body.textContent;
    for (const s of o.skill_distribution) expect(body).toContain(s.skill);
    expect(o.needs_practice.length).toBeGreaterThan(0);
    for (const f of o.needs_practice) { expect(body).toContain(f.full_name); for (const r of f.reasons) expect(body).toContain(r); }
    for (const e of o.experiments) expect(body).toContain(e.difficulty_label);
    for (const m of o.common_mistakes) expect(support.closest("section").textContent).not.toContain(m.label);
    expect(screen.getAllByRole("img", { name: /^Loops:/ }).length).toBe(1);
  });

  it("What-If shows the prediction, the real output and the explanation, and credits only the first try", async () => {
    const token = await registerFresh("whatif");
    renderAt("/experiments/1", token);
    await heading("Factorial Calculator");
    await userEvent.click(screen.getByRole("tab", { name: "What if" }));
    await userEvent.type(await screen.findByLabelText("Your prediction"), "24");
    await userEvent.click(screen.getByRole("button", { name: "Run the experiment" }));
    expect((await screen.findAllByText("Your prediction was right")).length).toBeGreaterThan(0);
    await heading(/Your earlier predictions \(1\)/);
    await userEvent.click(screen.getByRole("button", { name: "Run the experiment" })); // the same input again
    expect((await screen.findAllByText(/already tried this input/)).length).toBeGreaterThan(0);
    await heading(/Your earlier predictions \(2\)/);
    expect(screen.getAllByText("Skill credit").length).toBe(1);
    expect(document.body.textContent).toContain("You predicted");
    expect(document.body.textContent).toContain("The program printed");
  });

  it("the complete learning loop works through the interface", async () => {
    const token = await registerFresh("loop");
    renderAt("/experiments/1", token);                                                    // 1 open the experiment
    await heading("Factorial Calculator");
    fireEvent.change(screen.getByLabelText("Python code editor"), { target: { value: OFF_BY_ONE } });
    await userEvent.click(screen.getByRole("button", { name: "Run tests" }));              // 2 attempt it
    await findText("Test run:");
    await userEvent.click(screen.getByRole("button", { name: "Submit for grading" }));     // 3 submit
    expect(await findText("Result: 2 of 6 observations match")).toBeTruthy();              // 4 test results
    expect(await findText("Mistake patterns found")).toBeTruthy();                         // 6 mistake recorded
    await userEvent.click(screen.getByRole("button", { name: "Get a hint" }));             // 5 Copilot guidance
    expect(await findText("What is going wrong")).toBeTruthy();
    expect(screen.getAllByText("Loop-condition errors", { exact: false }).length).toBeGreaterThan(1); // the notice and the Copilot chip
    await userEvent.click(screen.getByRole("tab", { name: "What if" }));                   // 10 What-If
    await userEvent.type(await screen.findByLabelText("Your prediction"), "24");
    await userEvent.click(screen.getByRole("button", { name: "Run the experiment" }));
    expect((await screen.findAllByText("Your prediction was right")).length).toBeGreaterThan(0);

    cleanup();                                                                             // 7-9 the dashboard reflects it all
    renderAt("/dashboard", token);
    await heading("Welcome back, UI");
    await settle();
    const body = document.body.textContent;
    expect(body).toContain("Recommended because your recent mistake was loop-condition errors");
    expect(body).toContain("Recent mistakes");
    const loops = [...document.querySelectorAll("details.skill")].find((r) => r.querySelector("summary").textContent.startsWith("Loops"));
    expect(loops.querySelector("summary").textContent).not.toContain("No evidence yet");
    expect(loops.textContent).toContain("Factorial Calculator");
    const ps = [...document.querySelectorAll("details.skill")].find((r) => r.querySelector("summary").textContent.startsWith("Problem Solving"));
    expect(ps.textContent).toContain("Correct What-If prediction");

    cleanup();
    renderAt("/progress", token);
    await heading("Recommendation history");
    await settle();
    expect(document.body.textContent).toContain("started");
  });
});

describe("resilience", () => {
  it("an unexpected render error shows a recovery message instead of a blank page", () => {
    const Boom = () => { throw new Error("boom"); };
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBoundary><Boom /></ErrorBoundary>);
    expect(screen.getByRole("alert").textContent).toContain("Something went wrong");
    expect(screen.getByRole("button", { name: "Reload the page" })).toBeTruthy();
    spy.mockRestore();
  });
});


describe("AI Copilot chat page", () => {
  it("is reachable from the main navigation and shows the real experiment context", async () => {
    renderAt("/dashboard", tokens.student);
    await heading(/Welcome back/);
    await userEvent.click(screen.getByRole("link", { name: "AI Copilot" }));
    await heading("AI Copilot");
    await settle();
    const ctx = await apiGet("/api/copilot/context", tokens.student);
    const side = (await heading("What the Copilot can see")).closest("section");
    expect(side.textContent).toContain(ctx.context.experiment.title);
    expect(side.textContent).toContain(`${ctx.context.attempt.hints_used} of ${ctx.context.attempt.max_hints}`);
    if (ctx.context.score.best_percent != null) expect(side.textContent).toContain(`${ctx.context.score.best_percent}%`);
    for (const a of ["Explain my error", "Give me a hint", "Explain the concept", "Give me a similar problem"]) {
      expect(screen.getByRole("button", { name: a })).toBeTruthy();
    }
  });

  it("answers a quick action, stores the exchange and offers the Try Again workflow", async () => {
    const token = await registerFresh("copilot");
    renderAt("/experiments/1", token);                       // make a failing run so there is an error to explain
    await heading("Factorial Calculator");
    fireEvent.change(screen.getByLabelText("Python code editor"), { target: { value: OFF_BY_ONE } });
    await userEvent.click(screen.getByRole("button", { name: "Run tests" }));
    await findText("Test run:");

    cleanup();
    renderAt("/copilot?experiment=1", token);
    await heading("AI Copilot");
    await settle();
    await userEvent.click(screen.getByRole("button", { name: "Explain my error" }));
    const log = await screen.findByRole("log");
    await waitFor(() => expect(log.textContent).toMatch(/Loop-condition|loop/i));
    expect(log.textContent).toContain("Explain my error");                 // the student's side of the exchange
    expect(log.textContent).not.toContain("range(1, n + 1)");              // no solution handed over
    expect(await screen.findByRole("button", { name: "Try again in the editor" })).toBeTruthy();
    const followUps = [...log.querySelectorAll("button")].map((b) => b.textContent);
    expect(new Set(followUps).size).toBe(followUps.length);       // no duplicated follow-up buttons
    expect(screen.getByRole("button", { name: "I tried again: check my attempt" })).toBeTruthy();

    const stored = await apiGet("/api/copilot/messages?experiment_id=1", token);
    expect(stored.length).toBe(1);
    expect(stored[0].user.action).toBe("explain_error");

    await userEvent.click(screen.getByRole("button", { name: "I tried again: check my attempt" }));
    await waitFor(() => expect(log.textContent).toMatch(/no new run|check my attempt/i));

    cleanup();                                                             // the conversation is reloaded from the server
    renderAt("/copilot?experiment=1", token);
    await heading("AI Copilot");
    await settle();
    await waitFor(() => expect(screen.getByRole("log").textContent).toContain("Explain my error"));
  });

  it("answers a typed question with a hint rather than the solution", async () => {
    const token = await registerFresh("copilot-q");
    renderAt("/copilot?experiment=1", token);
    await heading("AI Copilot");
    await settle();
    await userEvent.type(screen.getByLabelText("Ask a question about this experiment"), "just give me the full solution");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    const log = await screen.findByRole("log");
    await waitFor(() => expect(log.textContent).toMatch(/hint/i));
    expect(log.textContent).not.toContain("result *= i");
  });

  it("the teacher navigation is unchanged and the page is student-only", async () => {
    renderAt("/teacher", tokens.teacher);
    await heading("Class overview");
    expect(screen.queryByRole("link", { name: "AI Copilot" })).toBeNull();
    cleanup();
    renderAt("/copilot", tokens.teacher);
    await heading("Class overview");                                        // redirected to the teacher home
  });
});


describe("What-If exploration", () => {
  const openWhatIf = async (token, path = "/experiments/2") => {
    renderAt(path, token);
    await heading(/Statistics|Factorial|Prime/);
    await userEvent.click(screen.getByRole("tab", { name: "What if" }));
    await userEvent.click(await screen.findByRole("tab", { name: "Explore a change" }));
    return screen.findByRole("button", { name: "See what happens" });
  };

  it("offers only the questions that fit the experiment, and keeps predict-and-check available", async () => {
    await openWhatIf(tokens.student);
    const offered = await apiGet("/api/experiments/2/whatif/explore", tokens.student);
    expect(offered.conditions.length).toBeGreaterThan(0);
    for (const c of offered.conditions) expect(await findText(c.question)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reset scenario" })).toBeTruthy();

    await userEvent.click(screen.getByRole("tab", { name: "Predict and check" }));   // the original flow is untouched
    expect(await screen.findByLabelText("Your prediction")).toBeTruthy();
  });

  it("shows what changes, what it prints, why, and the performance impact", async () => {
    const token = await registerFresh("whatif-explore");
    await openWhatIf(token);
    await userEvent.click(await screen.findByRole("radio", { name: /increase the input size/i }));
    await userEvent.click(screen.getByRole("button", { name: "See what happens" }));

    expect(await heading(/What changes/, {}, { timeout: 30000 })).toBeTruthy();
    for (const section of ["What it prints", "Why it changes", "Performance impact"]) {
      expect(await heading(new RegExp(section, "i"))).toBeTruthy();
    }
    const live = document.querySelector("[aria-live=polite]");
    expect(live.textContent).toMatch(/As it is now/);
    expect(live.textContent).toMatch(/times bigger/);
    expect(live.querySelectorAll(".stack-row").length).toBeGreaterThan(1);   // the original size plus each bigger one
  });

  it("Reset scenario clears the question and its result", async () => {
    const token = await registerFresh("whatif-reset");
    await openWhatIf(token);
    const first = await screen.findAllByRole("radio");
    await userEvent.click(first[0]);
    await userEvent.click(screen.getByRole("button", { name: "See what happens" }));
    await heading(/What changes/, {}, { timeout: 30000 });
    await userEvent.click(screen.getByRole("button", { name: "Reset scenario" }));
    await waitFor(() => expect(screen.queryByText(/What changes/)).toBeNull());
    expect(screen.getAllByRole("radio").every((r) => !r.checked)).toBe(true);
  });

  it("exploring does not change the student's score or dashboard", async () => {
    const token = await registerFresh("whatif-noscore");
    const before = await apiGet("/api/students/me/dashboard", token);
    await openWhatIf(token);
    await userEvent.click((await screen.findAllByRole("radio"))[0]);
    await userEvent.click(screen.getByRole("button", { name: "See what happens" }));
    await heading(/What changes/, {}, { timeout: 30000 });
    const after = await apiGet("/api/students/me/dashboard", token);
    expect(after.stats).toEqual(before.stats);
    expect(after.mistakes.total).toBe(before.mistakes.total);
  });
});


describe("Skill Passport page", () => {
  it("is reachable from the navigation and shows profile, totals and statuses from the API", async () => {
    renderAt("/dashboard", tokens.student);
    await heading(/Welcome back/);
    await userEvent.click(screen.getByRole("link", { name: "Skill Passport" }));
    await heading("Skill Passport");
    await settle();
    const p = await apiGet("/api/skills/me/passport", tokens.student);
    const body = document.body.textContent;
    expect(body).toContain(p.profile.full_name);
    if (p.profile.cohort) expect(body).toContain(p.profile.cohort);
    expect(body).toContain(`${p.summary.mastered} of ${p.summary.experiments_total}`);
    expect(body).toContain(`${p.summary.overall_progress}%`);
    for (const s of p.skills) expect(body).toContain(s.skill);
    for (const section of ["Coding skills developed", "Progress by level", "Strengths", "Skills needing improvement", "Recent achievements", "Mistake patterns"]) {
      expect(await heading(section)).toBeTruthy();
    }
    const statuses = new Set(p.skills.map((s) => s.status));
    for (const s of statuses) expect(body).toContain(s);
  });

  it("links a repeated mistake to the skill it affects and offers practice", async () => {
    const token = await registerFresh("passport");
    for (let i = 0; i < 2; i++) {
      renderAt("/experiments/1", token);
      await heading("Factorial Calculator");
      fireEvent.change(screen.getByLabelText("Python code editor"), { target: { value: OFF_BY_ONE } });
      await userEvent.click(screen.getByRole("button", { name: "Submit for grading" }));
      await findText("Result:");
      cleanup();
    }
    renderAt("/passport", token);
    await heading("Skill Passport");
    await settle();
    const gaps = (await heading("Skills needing improvement")).closest("section");
    expect(gaps.textContent).toContain("Loops");
    expect(gaps.textContent).toMatch(/loop-condition errors/i);
    expect(gaps.querySelector("a[href*='/experiments/']")).toBeTruthy();   // "Practice this skill"
    const dna = (await heading("Mistake patterns")).closest("section");
    expect(dna.textContent).toContain("Loop-condition errors");
    expect(dna.textContent).toContain("Affects Loops");
  });

  it("leaves the dashboard, progress page and teacher navigation alone", async () => {
    renderAt("/dashboard", tokens.student);
    await heading(/Welcome back/);
    await settle();
    for (const section of ["Skill passport", "Mistake DNA", "Experiments"]) expect(await heading(section)).toBeTruthy();
    cleanup();
    renderAt("/progress", tokens.student);
    expect(await heading("Mistake DNA")).toBeTruthy();
    cleanup();
    renderAt("/teacher", tokens.teacher);
    await heading("Class overview");
    expect(screen.queryByRole("link", { name: "Skill Passport" })).toBeNull();
  });
});


describe("teacher sees AI Viva practice", () => {
  it("shows viva practice per experiment and class-wide, matching the API, with no student named", async () => {
    const token = await registerFresh("viva-teacher");
    const started = await apiPost("/api/viva/start", { experiment_id: 1 }, token);
    let reply = { next_question: started.question };
    while (reply.next_question) {
      reply = await apiPost("/api/viva/answer", { session_id: started.session_id, answer: "The loop range must include the last value, otherwise it stops one iteration early." }, token);
    }
    const mine = await apiGet(`/api/viva/summary?session_id=${started.session_id}`, token);

    const overview = await apiGet("/api/teacher/overview", tokens.teacher);
    const factorial = overview.experiments.find((e) => e.id === 1);
    expect(factorial.viva.sessions).toBeGreaterThanOrEqual(1);

    renderAt("/teacher", tokens.teacher);
    await heading("Class overview");
    await settle();
    const body = document.body.textContent;
    expect(body).toContain("AI Viva practice");
    expect(body).toContain(`${factorial.viva.average_percent}% average`);
    expect(body).toContain(`${factorial.viva.sessions} viva`);
    const roster = await apiGet("/api/teacher/students", tokens.teacher);
    const table = (await heading("Experiments")).closest("section");
    for (const s of roster) expect(table.textContent).not.toContain(s.full_name);
    expect(table.textContent).not.toContain(mine.answers[0].answer);
  });
});


describe("teacher review of a submission", () => {
  it("a teacher leaves a remark and the student sees it on that submission", async () => {
    const token = await registerFresh("review");
    renderAt("/experiments/1", token);
    await heading("Factorial Calculator");
    fireEvent.change(screen.getByLabelText("Python code editor"), { target: { value: OFF_BY_ONE } });
    await userEvent.click(screen.getByRole("button", { name: "Submit for grading" }));
    await findText("Result:");
    const history = await apiGet("/api/experiments/1/submissions", token);
    const graded = history.find((h) => h.kind === "submit");
    expect(graded.review).toBeNull();
    cleanup();

    renderAt(`/teacher/submissions/${graded.id}`, tokens.teacher);
    await heading("Your review");
    await userEvent.selectOptions(screen.getByLabelText("Outcome"), "needs_rework");
    await userEvent.type(screen.getByLabelText("Remark for the student"), "Check the loop bound, then resubmit.");
    await userEvent.click(screen.getByRole("button", { name: "Save review" }));
    await waitFor(() => expect(screen.getByText("Saved")).toBeTruthy());

    const reviewed = await apiGet(`/api/submissions/${graded.id}`, token);
    expect(reviewed.review.status).toBe("needs_rework");
    expect(reviewed.score).toBe(graded.score);            // the score is untouched
    cleanup();

    renderAt("/experiments/1", token);
    await heading("Factorial Calculator");
    await userEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(await findText("Needs rework")).toBeTruthy();
    expect(await findText("Check the loop bound, then resubmit.")).toBeTruthy();
  });
});
