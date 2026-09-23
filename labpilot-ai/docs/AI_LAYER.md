# The LabPilot AI intelligence layer

This document describes how the five intelligence features work, where they live in the code, what data they use and how the
application behaves when no AI key is configured. Everything runs on the existing FastAPI backend and database; there is no
separate service.

## The learning loop

```
open experiment -> attempt (Run) -> Submit -> test results
       ^                                          |
       |            +-----------------------------+---------------------------+
       |            v                                                         v
  next experiment <- Adaptive Engine <- Skill Passport <- Mistake DNA <- AI Practical Copilot
       |
       +-> What-If experiment (predict, run, compare, explain)
```

Every arrow is real data in SQLite/PostgreSQL. Nothing on any screen is a literal. `backend/scripts/verify_integration.py`
(section 12) walks this loop on a live server and checks each step against raw SQL.

## 1. AI Practical Copilot (`app/ai/`)

**Input (built in `copilot.build_context`, from the database and the request):**

| Context | Source |
| --- | --- |
| Experiment title, objective, problem statement, concepts, difficulty, teacher's hint ladder | `experiments` |
| The student's current code, and whether it changed since the last run | request, latest `submissions` row |
| Test-case results of the latest run or submission: up to four failing cases with status and error type; visible cases also with input, expected and actual output and the error text | `execution_results` |
| Runtime and syntax errors | stderr of failing cases, plus the console output the editor sends |
| Previous relevant mistakes: most frequent categories, the recent mistakes (labels and experiment titles) and how often this category appeared in **earlier attempts** | `mistake_records` |
| Requested hint level and an optional free-text question | attempt state, request |

**Never sent:** hidden-case inputs and expected outputs, the reference solution, and any hidden-case value echoed by an error
message (for example a `ValueError` quoting the input is redacted). This is covered by tests.

**Output:** `error_category`, `explanation`, `hint`, `concept_to_review`, `next_step`, plus the hint level, which provider answered
and whether the answer was a fallback. Each request is stored in `ai_interactions` linked to the submission.

**Hint-first teaching.** There are three levels per attempt: 1 is a gentle nudge towards the area of the problem, 2 pinpoints what is
wrong and why, 3 gives step-by-step guidance without full code. The level rises with each request and the ladder restarts after each
graded submission. The system prompt forbids writing the solution, and fenced code blocks longer than three lines are stripped from replies. A reply that
reproduces the reference solution is discarded and replaced by rule-based guidance; this also protects one- and two-line solutions.

### Development fallback: rule-based guidance (no API key needed)

If no key is configured (`AI_PROVIDER=auto`, or `mock`), the application uses `MockProvider`, which builds the answer from
`app/ai/rules.py`. It is **not** canned text unrelated to the student: it uses the same context as the AI path.

* It picks the error category from the real test results and explains it in plain language, quoting the failing line from the error
  where there is one and the expected and actual output of the first visible failure.
* It uses the three-level hint ladder for that category, the experiment's concepts and the teacher's hint for the next step.
* It adds a sentence when the same category appeared in earlier attempts.

What it cannot do: read free-text questions or write bespoke prose. The interface says so plainly: a yellow notice in the Copilot
panel, a note in the left rail, and a "Rule-based mode" chip on each answer. If a real provider fails, times out or returns something
unusable, the same rules answer instead and the answer is marked as a fallback.

**Turning on real AI:** set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`, optionally with `OPENAI_BASE_URL` for a local model) in
`backend/.env` and restart. The provider layer speaks the Anthropic and OpenAI-compatible wire formats over HTTP; both are exercised
by the live verifier against a local stand-in server.

### The AI Copilot chat page (`app/ai/chat.py`, `api/routes/copilot_chat.py`, `frontend/src/pages/CopilotChat.jsx`)

The workspace panel helps with the code on screen. The **AI Copilot** page in the navigation is a conversation about one chosen experiment, using the same
context builder, the same guardrails and the same rule-based fallback.

* **Endpoints:** `GET /api/copilot/context` (experiments to choose from, plus the score, latest run, hints used and recent mistakes for the chosen one),
  `GET /api/copilot/messages?experiment_id=`, `POST /api/copilot/messages` (a quick action, a typed question, or both). All are student-only and share the
  per-student request budget, because a message can call a paid API.
* **Quick actions:** explain my error, give me a hint, explain the concept, give me a similar problem, and "I tried again: check my attempt".
* **Try Again workflow:** any answer that is not "all tests pass" offers a button back to the editor and a follow-up that compares the new run with the run
  the advice was based on, so the student hears whether the change helped.
* **Without an AI key** every quick action still works from the rules; a typed question is matched to the closest action by keyword, and the page says so.
  A request for the full solution is refused with a hint instead.
* **Stored** in `ai_interactions` with `kind="chat"`, so a conversation survives a reload and stays per experiment. No new tables were added.
* **Connecting a real LLM:** nothing in the page changes. Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`; `chat.handle_message` then asks the provider with
  `CHAT_SYSTEM_PROMPT`, and falls back to the rules on any error, timeout or guardrail block.

## 2. Mistake DNA (`services/mistakes.py`)

* **Analysis:** every run and every submission is analysed, deterministically: the failed cases (status, error type,
  error text, which kinds of case failed) plus static analysis of the code with Python's `ast`. **No AI model reads the
  code**; the Copilot only puts the result into words. Eleven categories: syntax errors, input handling, array / index
  errors, runtime errors, boundary cases, loop-condition errors, **off-by-one errors**, **variable initialisation**,
  **function logic**, inefficient solutions and logic errors. The last three are detected by named static checks:
  reading `seq[i + 1]` inside `for i in range(len(seq))`, a `<= len(...)` or `range(len(...) + 1)` bound, an accumulator
  whose starting value cancels its own updates (`total = 1` then `+=`), an accumulator reset inside its own loop, a
  `NameError`/`UnboundLocalError`, a function that is never called, a path with no `return`, and a `TypeError` naming
  `NoneType`. Each check is reported with the specific evidence, and a correct program trips none of them.
* **Practice for a newer category:** teachers tag experiments with focus categories, so `RELATED_FOCUS` maps the newer
  categories onto the practice they need (off-by-one to loop conditions and boundaries, the other two to logic) until an
  experiment is tagged with the new name directly. The recommender uses the same mapping, so a reason can cite them.
* **Storage:** one row per category per run or submission in `mistake_records`, linked to the submission.
* **Frequency and recurrence:** a category is counted once per **attempt**, so re-running the same bug does not inflate it. A
  pattern is *recurring* when it appears in two or more attempts.
* **Trend:** per category, the last 14 days are compared with the 14 days before: quiet, new, rising, falling or steady.
* **Improvement:** overall mistakes per attempt in the last 14 days against the previous 14 days: improving, steady or worsening,
  and "not enough data" until each period has at least two attempts.
* **Dashboard:** most frequent patterns, the improvement message, recent mistakes and practice suggestions. Suggestions link to
  unmastered experiments that practise each recurring category (`focus_categories`, set by the teacher).

## 3. Adaptive Experiment Engine (`services/recommendation.py`)

Rules only (no AI), so it is explainable and testable. Inputs: the last five graded scores, failed cases by kind (ordinary, edge,
performance, hidden), Mistake DNA counts, mastered experiments and skill mastery.

1. **Level:** average of recent scores 80% or more moves up once the current level is fully mastered (or finishes it first); 50-79%
   holds the level; below 50% steps back one level; no history starts at beginner.
2. **Choice among unmastered experiments:** +3 for fitting the target level (-1.5 per level away), +4 x the share of the student's
   recent mistakes in categories the experiment practises, +2 x the average gap in the skills it trains, +0.75 to finish something
   already started (best 30-79%), +1 each for missed edge cases or a failed performance case when the experiment practises them.
3. **Reason and storage:** a plain-language reason (for example "Recommended because you recently struggled with boundary cases
   (2x); this experiment practises it.") and the raw signals are stored in `experiment_recommendations`. `followed` turns true when
   the student runs or submits that experiment. The history is shown on the progress page.

## 4. Practical Skill Passport (`services/skills.py`)

Seven skills: Python Basics, Loops, Functions, Arrays, Sorting & Searching, Debugging, Problem Solving.

* **Update rule:** each graded submission moves the mastery of every skill the experiment trains towards its score, faster upwards
  (0.30) than downwards (0.10), scaled by difficulty (beginner 0.8, intermediate 1.0, advanced 1.25). Improving on an earlier failing
  best also credits Debugging. A correct What-If prediction (first try only) credits Problem Solving.
* **Evidence log:** every change is a row in `skill_evidence` (skill, experiment, source, before, after, change). The passport is
  read from it, so it can say which experiments contributed, what was demonstrated in the last 7 days and what needs practice.
* **Levels:** Novice under 20, Developing 20-44, Proficient 45-69, Advanced 70 or more. "Needs more practice" means below 45.

## 5. What-If experiment (`services/whatif.py`)

The student picks a scenario (a teacher-authored change to the program), may change the input, predicts the output and submits.
The server runs the modified program in the sandbox, compares the real output with the prediction line by line (if the modified program crashes, the
prediction must mention an error), explains the difference (the AI when configured, otherwise the first differing line plus the
teacher's explanation for the scenario) and stores the attempt in `what_if_predictions`. Skill credit is given only for a correct prediction the first time a
given scenario and input is tried, so seeing the answer and repeating it earns nothing.

### Exploring a change (`services/whatif_explore.py`, `frontend/src/components/WhatIfExplore.jsx`)

The **Explore a change** mode in the same tab answers hypothetical questions without asking for a prediction. It runs the student's own
program twice (as it is, and with one thing changed), compares the two, and explains the difference from local rules. Nothing is stored
and no score moves, so exploring is free and repeatable.

Each question is one entry in `CONDITIONS`, which says when it applies, what choices it offers and how to build the variant, so adding a
question later means adding a condition rather than touching the route or the page. The four shipped are: bigger input, more loop turns,
a flipped comparison (`<` becomes `<=`, and so on), and duplicate values. A question is only offered when it fits the experiment's sample
input and the student's current code, and the starting point is always a **visible** test case.

**Performance impact.** For the input-size question the program is run at several sizes and timed. Starting Python costs roughly 30-60 ms
and varies, so a run counts as measurable only when it rises clearly above that floor; below it the answer is "too fast to measure".
When only the largest size is measurable the result is a lower bound, which can prove growth is steep but never that it is gentle, so
in that case the tool says a bigger input is needed rather than guessing a shape. A run that stops finishing in time is reported as its
own result, which is what an inefficient approach looks like.

Class-wide, from the same tables: common mistake categories (per attempt) and the most common one per experiment, observed
difficulty (from the class's first graded try: under 50% hard, under 75% moderate, otherwise easy, needing two students), completion
per experiment (mastered, graded below 80%, started, not started), skill distribution by level and a support list.

**Privacy:** mistake data is shown only as totals. The support list uses scores and attempts only: 3 or more graded attempts on one
experiment, an average best score under 60%, nothing submitted after 3 days, or no submissions for 7 days with work left. It never
shows a student's mistake categories or Copilot conversations.

## Limits

Mistake classification is heuristic (syntax tree and test outcomes): it is right for the common cases in the catalogue and can be
wrong for unusual code. The recommender and the difficulty labels are simple rules on small classes, so treat them as guidance.
No real AI vendor was called while building; the provider code is verified against local stand-in servers.
