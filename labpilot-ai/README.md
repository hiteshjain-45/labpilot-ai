# LabPilot AI: Intelligent Virtual Lab Management System

**Prototype v0.1.** A working prototype of a virtual programming lab: students write Python in the browser, run it against real test
cases in an isolated process and get graded; teachers author experiments and see how the class is doing. On top of that core sits the
**LabPilot AI** layer: an AI Practical Copilot, Mistake DNA, an Adaptive Experiment Engine, a Practical Skill Passport and What-If experiments.

> **This is a teaching prototype, not a production platform.** It is not production-secure: read [Security](#security) and
> [`docs/SECURITY.md`](docs/SECURITY.md) before letting anyone you do not trust use it. For a walkthrough to present, see [`DEMO_GUIDE.md`](DEMO_GUIDE.md).

## Contents

[Architecture](#architecture-overview) · [Tech stack](#tech-stack) · [Features](#main-features) · [Setup](#setup-from-zero-to-demo) · [Environment variables](#environment-variables) ·
[Demo credentials](#demo-credentials) · [Database](#database-overview) · [Layout](#project-layout) · [Security](#security) · [Testing](#tests-and-what-has-been-verified) ·
[Limitations](#known-limitations) · [Future improvements](#future-improvements) · [Troubleshooting](#troubleshooting)

## Architecture overview

```
  Browser: React single-page app
      │  JSON over HTTP, JWT bearer token
      ▼
  FastAPI application (uvicorn)
   ├─ api/routes   auth · experiments · submissions · copilot · what-if · learning · students · teacher · system
   ├─ services     grading · mistakes · skills · recommendation · what-if · analytics   (all learning logic, no AI needed)
   ├─ ai           providers: Anthropic | OpenAI-compatible | built-in rule-based fallback; prompts; guardrails
   ├─ sandbox ───► one short-lived, separate Python process per run (harness.py), never the API process
   └─ SQLAlchemy ► SQLite by default, PostgreSQL-ready
```

* The **learning layer is deterministic** (rules and arithmetic on stored results), so it works offline and is unit-tested. AI is used only for wording
  hints and explanations, is optional, and every AI reply passes guardrails and falls back to rules on any failure.
* In development the Vite server proxies `/api` to the backend. After `npm run build` the API can also serve the built app, so a demo needs one process.

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, React Router 7, Vite 8, CodeMirror 6 (editor), hand-written SVG charts, plain CSS with design tokens |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2, PyJWT, bcrypt |
| Database | SQLite (default, zero setup); PostgreSQL through `DATABASE_URL` (not exercised here) |
| Code execution | Subprocess sandbox (tested); Docker sandbox (experimental, never run) |
| AI | Anthropic and OpenAI-compatible HTTP providers; built-in rule-based fallback |
| Tests | pytest, a live end-to-end verifier script, Vitest + Testing Library (jsdom) |

## Main features

**Virtual lab core**

* Roles: students and teachers, JWT sign-in, students can self-register, teachers are created by the seed or by a teacher.
* Experiments with aim, problem, procedure, sample cases, starter code, hint ladder, skills and difficulty. Five are included.
* **AI Copilot** chat page in the main navigation: pick an experiment, use the quick actions or type a question, and see exactly what context the Copilot has (score, latest run, recent mistakes).
* Code editor with syntax highlighting; **Run** (visible cases only, not graded) and **Submit** (visible and hidden cases, graded); Ctrl+Enter runs.
* Observation table with per-case verdicts and expected/actual diffs; hidden cases show only a verdict to students.
* Attempt and submission history, dashboards for students and teachers, a submission review page (hidden cases visible to teachers).
* Teacher experiment management: create, edit, publish, delete, add test cases and What-If scenarios, and "Check reference solution".

**LabPilot AI features** (details in [`docs/AI_LAYER.md`](docs/AI_LAYER.md))

| Feature | What it does |
| --- | --- |
| AI Practical Copilot | Hint-first help in three levels from the real test results, errors, code and mistake history. Never writes the solution. With no API key a documented rule-based fallback answers, and the interface says so. Available beside the editor, and as a full **AI Copilot** chat page in the navigation with quick actions (explain my error, give me a hint, explain the concept, give me a similar problem), step-by-step debugging and a Try Again workflow. Conversations are stored per experiment. |
| Mistake DNA | Classifies every failure into eleven categories (syntax, input handling, array/index, runtime, boundary, loop-condition, off-by-one, variable initialisation, function logic, inefficient, logic) from test outcomes and `ast` static analysis, with no AI involved. Counts them once per attempt, finds recurring patterns, shows the trend and improvement, recent mistakes and targeted practice; recommendations cite the pattern by name. |
| Adaptive Experiment Engine | Recommends the next experiment from recent scores, failed cases, mistakes, completion and skills, with a stored, written reason. |
| Practical Skill Passport | Seven skills whose levels move with real results; each skill shows the experiments that contributed. |
| What-If experiments | Two modes in one tab. **Predict and check:** predict the output of a modified program, run it, compare, explain; skill credit for the first try only. **Explore a change:** ask what if the input were bigger, the loop ran more times, a condition were flipped or values repeated, and see what changes, what it prints, why, and the measured performance impact, with a Reset scenario button. Exploring stores nothing and never moves a score. |
| Teacher intelligence | Completion, observed difficulty, most common mistakes, skill distribution and a support list, using scores and attempts only. |

## Setup: from zero to demo

**Requirements:** Python 3.12 and Node 22 (what this was developed and tested with; Python 3.11 works but is less tested), on Linux, macOS or Windows. No API key and no Docker are needed.
**Windows:** supported on a best-effort basis. It was developed and fully tested on Linux; the Windows-specific code paths (the sandbox starting the real interpreter, killing a run's whole process tree, tolerant temp-file cleanup) are covered by unit tests but were not run on a real Windows machine by the author. The sandbox's memory and CPU limits are POSIX-only, so on Windows only the time limit and the audit hook apply. If anything misbehaves, WSL gives the tested Linux behaviour.

**1. Get the project.** Unzip `labpilot-ai.zip` (or clone the repository) and open the folder in VS Code.

```bash
unzip labpilot-ai.zip && cd labpilot-ai
```

**2. Configure the environment (optional).** Every variable has a working default. To change any, copy the example files:

```bash
cp backend/.env.example backend/.env        # backend settings, see the table below
cp frontend/.env.example frontend/.env      # only needed to change the proxy target or hide the demo buttons
```

**3. Install the backend and initialise the database.** Tables are created automatically; the seed also fills them with demo data.

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate      # Windows PowerShell: python -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt                     # requirements.txt alone is enough to run, dev adds pytest
python -m app.seed --reset                              # about 20 s: 5 experiments, 1 teacher, 5 students with history
```

The seed does not insert made-up rows. It replays each student's story (runs, submissions, hints, What-If predictions with back-dated timestamps) through the
real services, so every score, mistake pattern, skill level and recommendation was computed by the actual code. Two clean seeds produce identical content.
`--minimal` creates only the teacher and experiments; without `--reset` an existing database is left untouched.

**4. Start the backend** (run it as a normal user, not root):

```bash
uvicorn app.main:app --reload --port 8000               # API docs at http://localhost:8000/docs
```

**5. Install and start the frontend** in a second terminal:

```bash
cd frontend
npm install
npm run dev                                             # http://localhost:5173, proxies /api to port 8000
```

*Single-process alternative:* `cd frontend && npm install && npm run build`, then start only the backend and open http://localhost:8000.

**6. Log in** with a [demo account](#demo-credentials) (the sign-in page has "Fill in" buttons), then follow [`DEMO_GUIDE.md`](DEMO_GUIDE.md).

**Main demonstration flow** (about 8 minutes): student logs in → dashboard shows a recommendation with its reason → open the recommended experiment → run the starter code →
read the observation table → ask the Copilot for hints → fix the code → submit → see the score and how the Skill Passport moved → Mistake DNA and the recommendation update →
try a What-If → sign in as the teacher and see the class analytics, the submission and the experiment editor.

## Environment variables

Backend, in `backend/.env` (values already in the real environment win over the file). Everything is optional.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` makes the server refuse to start with a weak `SECRET_KEY` and makes the seed refuse to create demo accounts |
| `DATABASE_URL` | `sqlite:///…/backend/labpilot.db` | Any SQLAlchemy URL. PostgreSQL: `postgresql+psycopg://…` after installing a driver |
| `SECRET_KEY` | insecure development value | JWT signing key. **Set a long random value for any shared use** (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `ACCESS_TOKEN_MINUTES` | `480` | Session length |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Only needed when a browser calls the API directly |
| `AI_PROVIDER` | `auto` | `auto`, `mock`, `anthropic` or `openai`; `auto` uses whichever key is set, else the rule-based fallback |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ANTHROPIC_BASE_URL` | empty, `claude-haiku-4-5-20251001`, Anthropic URL | Enables Claude-written hints |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` | empty, `gpt-4o-mini`, OpenAI URL | Any OpenAI-compatible endpoint, including a local Ollama |
| `AI_TIMEOUT_SECONDS` | `20` | Provider timeout before falling back to rules |
| `SANDBOX_MODE` | `subprocess` | `subprocess` (tested) or `docker` (experimental, never run) |
| `SANDBOX_TIMEOUT_SECONDS`, `SANDBOX_MEMORY_MB` | `3`, `256` | Per-run limits |
| `SANDBOX_MAX_OUTPUT_CHARS`, `SANDBOX_MAX_CONCURRENT` | `64000`, `4` | Output cap and parallel runs |
| `MAX_CODE_CHARS` | `20000` | Longest accepted program |
| `LOGIN_MAX_FAILURES`, `LOGIN_WINDOW_SECONDS` | `5`, `300` | Login lockout |
| `EXEC_MAX_PER_MINUTE` | `60` | Runs and AI requests per user per minute |

Frontend, in `frontend/.env` (read at build or dev-server start): `VITE_BACKEND_URL` (dev proxy target, default `http://127.0.0.1:8000`),
`VITE_API_URL` (only if the API is on another origin), `VITE_SHOW_DEMO=false` (hide the "Fill in" login buttons). The example files contain no keys or real secrets.

## Demo credentials

Created by `python -m app.seed`. **Published passwords: for local demos only.** The seed refuses to run when `APP_ENV=production`.

| Role | Email | Password | What the data shows |
| --- | --- | --- | --- |
| Teacher | teacher@labpilot.demo | Teacher@123 | Dr. Meera Kapoor, sees the whole class |
| Student | student@labpilot.demo | Student@123 | Ananya Verma: three experiments mastered, one in progress, the richest history (use this one) |
| Student | rohan@labpilot.demo | Student@123 | Strong; has attempted the advanced experiment |
| Student | priya@labpilot.demo | Student@123 | Struggled early; needed several attempts (appears on the teacher's support list) |
| Student | karan@labpilot.demo | Student@123 | Mixed; needed a retry on debugging |
| Student | sneha@labpilot.demo | Student@123 | Just getting started |

## Database overview

Fifteen tables, created by `Base.metadata.create_all` on start-up (there are no migrations yet). SQLite foreign keys are enforced, so deleting an experiment removes its attempts, results and mistakes.

| Table | Holds |
| --- | --- |
| `roles`, `users`, `students`, `teachers` | Accounts (bcrypt hashes), roles, roll number and cohort, department |
| `experiments`, `experiment_test_cases` | Experiment content, hints, skills, What-If scenarios; test cases with kind (normal, edge, performance), hidden flag and weight |
| `attempts`, `submissions`, `execution_results` | A working session on one experiment; each run or graded submit with its code and score; the per-case result of each |
| `ai_interactions`, `what_if_predictions` | Every Copilot and What-If explanation request (audit); each What-If prediction with the real output |
| `mistake_records` | Mistake DNA raw data: one row per detected category per run or submission |
| `skill_records`, `skill_evidence` | Current mastery per skill; an audit trail of every change, with the experiment and source behind it |
| `experiment_recommendations` | Every recommendation with its written reason, the signals used and whether it was followed |

Reset everything with `python -m app.seed --reset`. An older database from before this version gains the new `skill_evidence` table automatically, but has no evidence for past activity, so reseed.

## Project layout

```
backend/
  app/
    api/routes/     HTTP endpoints            core/       auth dependencies, limits, constants
    services/       grading, mistakes, skills, recommendation, what-if, analytics
    ai/             providers, prompts, guardrails, rule-based fallback
    sandbox/        harness.py (runs in the child process), subprocess and Docker runners
    models/ schemas/ seed/ (experiment catalogue, student code variants, demo cohort)
  tests/            191 pytest tests        scripts/verify_integration.py   live end-to-end verifier
frontend/
  src/pages/        student pages and teacher/ pages      src/components/   editor, observation table, panels, charts
  tests/            23 frontend tests (jsdom, against a live API)
docs/               AI_LAYER.md (intelligence layer)  ·  SECURITY.md (threat model and limits)
DEMO_GUIDE.md       presentation script         verify_all.sh   one-command test run
```

## Security

Summary only; the full picture is in [`docs/SECURITY.md`](docs/SECURITY.md).

* **Student code runs in a separate process** with resource limits, a wall-clock timeout, an import allow-list, no `open()`, a static check for reflection tricks and an audit hook that refuses
  process creation, file access and sockets. A final security review found that an earlier version could be escaped with one line of code; that was fixed and is covered by regression tests.
* **The sandbox is still not a security boundary.** Student code runs as the same OS user as the API. Do not expose this to untrusted users without container or VM isolation, and never run it as root.
* Passwords are bcrypt-hashed, sessions are signed JWTs, every route is role-checked on the server, hidden test data is never sent to students or to AI providers.
* **Not implemented:** HTTPS, CSRF protection, a Content-Security-Policy, server-side token revocation, audit logging, password reset, dependency scanning.
* Demo accounts have published passwords. With a real AI key configured, students' code is sent to that provider.

## Tests and what has been verified

```bash
./verify_all.sh            # everything below, about five minutes; uses scratch databases, never your demo data (needs bash: Linux, macOS, WSL or Git Bash)
./verify_all.sh backend    # pytest + live verifier only
./verify_all.sh frontend   # build + frontend tests + dev-proxy check only
```

| Layer | What it covers | Result at last run |
| --- | --- | --- |
| `pytest` | Auth and roles, an access matrix over every API operation, sandbox attacks and escape regressions, experiment CRUD, grading, hidden-case concealment, Mistake DNA, skill evidence, recommendations, Copilot context and guardrails, What-If, teacher analytics and their privacy rules, clean-database demo seeding, security headers | 191 passed |
| `backend/scripts/verify_integration.py` | Starts the real API on a scratch database and drives it over HTTP, cross-checking every dashboard number, mistake, skill and recommendation against raw SQL, including the complete learning loop | 145 of 145 checks |
| Frontend tests | The real React app in jsdom against a live seeded API, including the complete learning loop through the interface | 23 passed |
| Build and dev proxy | Production build; the dev server forwards `/api` to the backend | passed |

In a separate manual pass (headless Chrome, scripts **not included** in the repository because they need a Chromium build that is not a project dependency) the following was also checked and passed:
28 page views at desktop and phone widths with no console errors, failed requests or horizontal overflow; a 34-step student-and-teacher flow through the real UI (CodeMirror typing,
Ctrl+Enter, Copilot, submit, What-If, dashboards, teacher editing and review, route guards); and the interface's behaviour when the backend goes away and returns.

**Not verified:** a real AI vendor (only local stand-in servers speaking the Anthropic and OpenAI formats were used), the Docker sandbox, PostgreSQL, Windows and macOS, real touch devices,
screen readers, and any independent security testing.

## Known limitations

* Not production-secure (see above): same-user sandbox, `localStorage` token, no HTTPS/CSRF/CSP, in-memory rate limits (per process, keyed by client IP).
* Python programs only, reading stdin and printing to stdout: no files, network or third-party packages. Students cannot use `eval`, `exec`, `getattr` and similar reflection functions.
* No schema migrations: tables are created on start-up. No email verification or password reset. One class, no courses, sections or deadlines.
* Mistake classification, difficulty labels and the recommender are heuristics on small classes; treat them as guidance, not verdicts.
* Skill mastery is a moving average that rises faster than it falls. What-If credit is only for the first try at a scenario and input.
* Without an API key the Copilot uses built-in rules: it cannot answer free-text questions.
* The frontend has no offline mode and no formal accessibility audit (labels, focus rings and keyboard use were built in but not audited).

## Future improvements

1. Run student code in Docker or a micro-VM on a separate worker host, keeping the current layers as a second line of defence.
2. Alembic migrations, PostgreSQL in CI, Redis for rate limits.
3. Cookie sessions with CSRF protection, HTTPS, email verification, password reset and an audit log.
4. Courses and cohorts (several teachers, sections, deadlines), grade export.
5. More languages, and multi-function or file-based tests.
6. Tune Mistake DNA and the recommender on real class data, with a labelled evaluation set.
7. An accessibility audit and a browser end-to-end suite in the repository (for example Playwright).

## Troubleshooting

* **"Cannot reach the server" on sign-in:** the API is not running on port 8000, or `VITE_BACKEND_URL` points elsewhere.
* **`ModuleNotFoundError` starting the API:** run it from the `backend` folder with the virtual environment active.
* **Windows: `WinError 32` (file in use) while seeding or running code:** you have a build from before the fix. Use this version, end any leftover `python.exe` processes in Task Manager, and run `python -m app.seed --reset` again.
* **Log shows "running as root":** start the API as a normal user; the sandbox cannot limit process creation for root.
* **"The code runner is busy":** more than `SANDBOX_MAX_CONCURRENT` runs are in flight; retry.
* **Runs time out on a slow machine:** raise `SANDBOX_TIMEOUT_SECONDS`.
* **Start over with clean demo data:** stop the API, then `python -m app.seed --reset`.
* **Blank page in single-process mode:** run `npm run build` in `frontend` first.
* **A student program is refused with "SandboxRestriction":** it used a restricted name such as `eval`, `getattr` or `__subclasses__`; see `docs/SECURITY.md`.
