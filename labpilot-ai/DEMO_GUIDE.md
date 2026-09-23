# Demo guide (about 8 to 10 minutes)

Numbers below are for a **freshly seeded** database and were observed in a real browser run. If you rehearse first, reseed before presenting,
because every submission adds data. **Stop the backend before reseeding** (reseeding under a running server breaks its database handle):

```bash
# stop the backend (Ctrl+C), then:      (Windows PowerShell: .venv\Scripts\Activate.ps1 instead of source)
cd backend && source .venv/bin/activate && python -m app.seed --reset
uvicorn app.main:app --port 8000          # and, in another terminal: cd frontend && npm run dev
```

Open http://localhost:5173 in Chrome at 100% zoom on a screen at least 1366 pixels wide. Have this file open on a second screen.

| Role | Email | Password |
| --- | --- | --- |
| Student (use this one) | student@labpilot.demo | Student@123 |
| Teacher | teacher@labpilot.demo | Teacher@123 |

The sign-in page has "Fill in student login" and "Fill in teacher login" buttons.

## What to show first (30 seconds)

Say: "LabPilot AI is a virtual programming lab. Students write and run real code against test cases; teachers see how the class is doing. On top of that,
an intelligence layer watches every run and turns mistakes into guidance. This is Prototype v0.1, so I will also be clear about what it is not."

Show the sign-in page, click **Fill in student login**, then **Sign in**.

## Student demo flow (about 4 minutes)

1. **Dashboard** ("Welcome back, Ananya"). Point at the yellow recommendation card: it names the next experiment (*Prime Number Checker*) and says *why*
   ("Recommended because your recent mistake was loop-condition errors..."). Below: mastered 3 of 5, average best score 90%, the score chart, the Skill Passport and Mistake DNA.
   Say: "None of this is typed in; the seed replays realistic student histories through the same code that grades live work."
2. Click **Open experiment**. Show the aim, problem, procedure and sample cases on the left, the editor in the middle, the Copilot on the right. Note "5 more cases stay hidden until you submit".
3. **Run the starter code.** Press **Ctrl+Enter** (or **Run tests**). Result: *Test run: 3 of 4 visible cases match.* The failing case **One is not prime** opens by itself: input `1`, expected output `Not prime`,
   your output `Prime` (the table's Expected and Observed columns show the same). On a freshly seeded database the editor opens with this starter code; if it holds anything else, paste it:

   ```python
   def is_prime(n):
       for d in range(2, n):
           if n % d == 0:
               return False
       return True

   n = int(input())
   print("Prime" if is_prime(n) else "Not prime")
   ```
4. **Ask the Copilot** (see the AI flow below), then **fix the code**. Select all in the editor and paste:

   ```python
   def is_prime(n):
       if n < 2:
           return False
       d = 2
       while d * d <= n:
           if n % d == 0:
               return False
           d += 1
       return True

   n = int(input())
   print("Prime" if is_prime(n) else "Not prime")
   ```
5. **Run tests**: all 4 visible cases match. Click **Submit for grading**: *Result: 9 of 9 observations match. Score 100 / 100.* The hidden cases (including a very large prime) now show as matches.
   Point at the line *Skill passport updated: Functions +24.6 (now 43%), Loops ..., Problem Solving ..., Debugging ...* and the green box *Next suggestion: Sorting and Binary Search* with its reason.

## AI and Mistake DNA demo flow (about 3 minutes)

**Copilot (hint-first).** On the failing run, click **Get a hint** (Copilot tab). Read the card: category chip (*Boundary cases*), *What is going wrong* (it quotes the real
input `1` that printed `Prime`), *Hint*, *Concept to review*, *Next step*. Click **Get a hint** again: **Hint 2 of 3**, more specific. Say: "It moves up one level per request, never gives the
solution, and starts over after each graded submission." Point at the yellow **Development fallback** notice: with no API key the same real results feed built-in rules; set `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY` and the wording becomes AI-written (with guardrails that block leaking the solution).

**Mistake DNA.** Go back to **Dashboard** (before or after submitting):

* *Most frequent patterns*: red bars are patterns that recurred in two or more **attempts** (a bug re-run five times counts once).
* *Improvement*: "You are making fewer mistakes per attempt: 1.0 in the last 14 days, down from 1.7".
* *Recent mistakes*: the newest is now on **Prime Number Checker** (from your failing run); the number in the corner rose from 9 to 10 recorded patterns.
* *Practice suggestions*: for each recurring pattern, a tip and links to experiments that practise it.

**Skill Passport and recommendation.** Skill Passport: Functions rose from 18% to 43%. Click **Functions** to expand it: it lists *Prime Number Checker* as the contributor with its best score.
The recommendation card now points to **Sorting and Binary Search**. Open **My progress** for the full history: every recommendation is stored with its reason.

**What-If.** Back in *Prime Number Checker*, open the **What if** tab. Scenario *The search stops before the square root*, input `9`: type the natural guess `Not prime` and run.
The interface says *Different from your prediction*, shows what the program really printed (`Prime`) and explains why. Then choose scenario *There is no check for n < 2* (its input is already `1`),
predict `Prime`, run: *Your prediction was right*, with skill credit. Say: "Credit is only for the first try at a given scenario and input, so seeing the answer and repeating it earns nothing."

## Teacher demo flow (about 3 minutes)

Click **Sign out**, then **Fill in teacher login** and sign in.

1. **Class overview.** Graded submissions 29 and *Experiments mastered 17 of 25* (they include the run you just did). **Students who may need extra practice**: Priya Nair (low priority: needed 3 or more graded attempts on two
   experiments). Say: "This list uses scores and attempts only. Teachers never see an individual student's mistake profile or Copilot chat." Show *Completion by experiment*, the *Observed difficulty* labels
   (Factorial and Debugging are Hard for the first try), *Common mistakes* as class totals with no names, and *Skill distribution*.
2. **Experiments** (menu). All five are listed. Open *Prime Number Checker*: aim, problem, starter code, hint ladder, test cases (some hidden), What-If scenarios. Click **Check reference solution**:
   *The reference solution passes every test case.* Optionally change *Estimated minutes* and save.
3. **Submissions** (menu). The newest row is Ananya's graded Prime submission. Open it: her code, and the observation table **with the hidden cases visible**, which students never see.
   **Students** lists the roster; open *Ananya Verma* for per-experiment progress and her Skill Passport.

## Presentation sequence

| Time | Do | Say |
| --- | --- | --- |
| 0:00 | Sign-in page, student login | What it is; Prototype v0.1 |
| 0:30 | Dashboard | Recommendation with a reason; real replayed history |
| 1:30 | Open Prime; Ctrl+Enter | 3 of 4 cases match; hidden cases exist |
| 2:30 | Copilot, two hints | Hint-first; fallback notice; never the solution |
| 4:00 | Fix, run, submit | 9 of 9; skills moved; next suggestion |
| 5:00 | Dashboard: Mistake DNA, Skill Passport | Per-attempt counting; trend; contributors |
| 6:30 | What-If | Predict, compare, explain; first-try credit |
| 7:30 | Teacher: overview, support list | Aggregates; privacy rule |
| 9:00 | Experiments editor, submission review | Management; hidden cases visible to teachers |
| 9:45 | Close with the limits below | Honest boundaries |

**Five-minute version:** dashboard, run, one hint, fix and submit, the dashboard again, then the teacher overview only.

## Say this about the limits

* It is a **prototype**. The sandbox runs student code in a separate, restricted process, and a security review found and fixed an escape, but it is **not** a security boundary. A real deployment needs containers or micro-VMs.
* Without an AI key the Copilot is rule-based (still using the real results). AI wording was tested against local stand-in servers, not a live vendor.
* Mistake classification and recommendations are heuristics tuned on five experiments and a five-student class.
* One class, Python only, SQLite, no HTTPS or password reset yet. See `README.md` and `docs/SECURITY.md`.

## If something goes wrong

| Symptom | Fix |
| --- | --- |
| "Cannot reach the server" | The backend is not running on port 8000. Start it; press **Try again** on the page. |
| Numbers differ from this guide | Data was changed by a rehearsal. Stop the backend, `python -m app.seed --reset`, restart. |
| "The code runner is busy" | Wait a few seconds and press Run again. |
| Sign-in locked after five wrong passwords | Wait five minutes or restart the backend. |
| Hints read differently from the script | An AI key is set in `backend/.env`; that is expected (AI-written). Clear it for the rule-based text. |
| A run is refused with "SandboxRestriction" | The code used a restricted name such as `eval` or `getattr`; not needed in this demo. |
