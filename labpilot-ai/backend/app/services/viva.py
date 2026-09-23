"""AI Viva: rule-based oral practice built from data the lab already holds.

Nothing here calls a language model. Questions come from the experiment's own metadata (concepts, hints,
what-if scenarios, focus categories), from the student's latest submitted code, and from their Mistake DNA.
Answers are judged by matching the concepts the question expects against the words the student wrote, which is
shallow but honest and testable. The interface says so plainly.

Reuses, rather than duplicates: `services/skills.py` for skill evidence, `services/mistakes.py` for the mistake
profile and practice links, and the existing `ai_interactions` table (kind "viva") for the transcript, so the
viva adds no table of its own. A viva never touches a score or a grade.
"""
from __future__ import annotations

import ast
import re
import secrets
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import CATEGORIES, SKILL_FOR_CATEGORY, SKILLS, category_label
from app.core.errors import AppError, NotFound
from app.models import AIInteraction, Experiment, MistakeRecord, Student, Submission
from app.services import mistakes as mistake_service
from app.services import skills as skill_service
from app.utils.timeutil import utcnow

QUESTION_COUNT = 5
MAX_POINTS = 10          # per question
PASS_SCORE = 7           # correct at or above this
PARTIAL_SCORE = 4        # partially correct at or above this
MIN_ANSWER_CHARS = 12    # shorter than this cannot demonstrate anything
SKILL_WEIGHT = 0.4       # a viva is practice, so it moves a skill less than graded work does

NOTE = (
    "Viva feedback is generated from experiment metadata and your submission history. "
    "It is not an LLM judgment."
)

# Words that count as having named an idea. Kept small and explicit so the matching can be read and argued with.
CONCEPT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "loop bounds": ("range", "bound", "start", "stop", "end", "last", "first", "iteration", "off by one", "off-by-one", "inclusive", "exclusive"),
    "loop termination": ("terminate", "stop", "end", "infinite", "forever", "condition", "while", "exit"),
    "accumulator": ("accumulator", "total", "sum", "product", "result", "running", "initial", "initialise", "initialize", "start at", "starts at"),
    "indexing": ("index", "indices", "position", "zero", "0", "len", "length", "out of range", "bounds"),
    "function definition": ("def", "function", "parameter", "argument", "call", "return", "reuse"),
    "return values": ("return", "value", "none", "gives back", "output of the function"),
    "input parsing": ("input", "int(", "split", "strip", "convert", "read", "line", "stdin"),
    "printing output": ("print", "output", "format", "exactly", "extra text", "prompt"),
    "edge cases": ("edge", "special", "zero", "empty", "negative", "smallest", "largest", "single", "boundary", "one element"),
    "complexity": ("complexity", "o(n", "big o", "quadratic", "linear", "faster", "slower", "efficient", "performance", "time", "square root", "sqrt", "half", "skip"),
    "correctness reasoning": ("because", "so that", "therefore", "means", "reason", "expect", "trace", "example"),
    "comparison operators": ("comparison", "operator", "less", "greater", "equal", "<", ">", "<=", ">=", "==", "condition"),
    "data structures": ("list", "array", "element", "item", "collection", "append", "slice"),
    "sorting and searching": ("sort", "sorted", "order", "search", "binary", "compare", "swap", "middle"),
    "debugging method": ("trace", "print", "test", "isolate", "step", "check", "reproduce", "failing", "hand"),
}

# The concepts each mistake category is really about, used for the debugging question and the summary.
CATEGORY_POINTS: dict[str, tuple[str, ...]] = {
    "loop_condition": ("loop bounds", "loop termination", "correctness reasoning"),
    "off_by_one": ("loop bounds", "indexing", "correctness reasoning"),
    "variable_init": ("accumulator", "correctness reasoning"),
    "array_index": ("indexing", "edge cases"),
    "function_logic": ("function definition", "return values"),
    "input_handling": ("input parsing", "printing output"),
    "syntax": ("debugging method", "correctness reasoning"),
    "boundary": ("edge cases", "correctness reasoning"),
    "inefficient": ("complexity", "correctness reasoning"),
    "runtime": ("debugging method", "correctness reasoning"),
    "logic": ("debugging method", "correctness reasoning"),
}

SKILL_POINTS: dict[str, tuple[str, ...]] = {
    "Python Basics": ("input parsing", "printing output"),
    "Loops": ("loop bounds", "loop termination"),
    "Functions": ("function definition", "return values"),
    "Arrays": ("indexing", "data structures"),
    "Sorting & Searching": ("sorting and searching", "complexity"),
    "Debugging": ("debugging method", "correctness reasoning"),
    "Problem Solving": ("edge cases", "correctness reasoning"),
}


# Which concepts a piece of experiment wording is really about, so a question's expected points match its subject.
TEXT_SIGNALS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("loop", "range", "iterat", "while", "repeat"), ("loop bounds", "loop termination")),
    (("index", "list", "array", "element"), ("indexing", "data structures")),
    (("function", "return", "def "), ("function definition", "return values")),
    (("input", "read", "stdin", "parse"), ("input parsing", "printing output")),
    (("sort", "search", "binary", "order"), ("sorting and searching", "complexity")),
    (("efficien", "complexity", "fast", "performance", "large"), ("complexity",)),
    (("edge", "boundary", "zero", "empty", "special"), ("edge cases",)),
    (("accumulat", "total", "sum", "product", "initial"), ("accumulator",)),
    (("condition", "compare", "comparison", "if "), ("comparison operators", "correctness reasoning")),
    (("debug", "fault", "error", "trace"), ("debugging method",)),
)


def points_for_text(text: str, fallback) -> list[str]:
    """Concept points implied by the wording, falling back to the skill's own points."""
    lowered = (text or "").lower()
    found: list[str] = []
    for signals, concepts in TEXT_SIGNALS:
        if any(sig in lowered for sig in signals):
            found += list(concepts)
    return list(dict.fromkeys(found))[:2] or list(dict.fromkeys(fallback))[:2]


def _points(names) -> list[dict]:
    return [{"concept": n, "keywords": list(CONCEPT_KEYWORDS.get(n, (n,)))} for n in dict.fromkeys(names)]


def _latest_submission(db: Session, student_id: int, experiment_id: int) -> Optional[Submission]:
    return db.scalars(
        select(Submission).where(Submission.student_id == student_id, Submission.experiment_id == experiment_id)
        .order_by(Submission.created_at.desc(), Submission.id.desc()).limit(1)
    ).first()


def _code_features(code: str) -> list[str]:
    """What the student's own code actually contains, so the code question can ask about something real."""
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            found.append("a for loop")
        elif isinstance(node, ast.While):
            found.append("a while loop")
        elif isinstance(node, ast.FunctionDef):
            found.append(f"the function `{node.name}`")
        elif isinstance(node, ast.If):
            found.append("an if statement")
        elif isinstance(node, ast.Subscript):
            found.append("a list index")
    return list(dict.fromkeys(found))


def _student_mistakes(db: Session, student_id: int, experiment_id: int) -> list[dict]:
    """The student's recorded mistake categories, this experiment first. Read-only: Mistake DNA is not changed."""
    profile = mistake_service.mistake_profile(db, student_id, with_practice=False)
    here = {
        c for (c,) in db.execute(
            select(MistakeRecord.category)
            .where(MistakeRecord.student_id == student_id, MistakeRecord.experiment_id == experiment_id)
            .distinct()
        ).all()
    }
    ordered = sorted(profile["categories"], key=lambda c: (c["category"] not in here, -c["count"]))
    return ordered


# ---------------------------------------------------------------------------------------------- questions
def build_questions(db: Session, student: Student, experiment: Experiment) -> list[dict]:
    """Five questions, in a fixed order of types, derived from this experiment and this student."""
    concepts = list(experiment.concepts or [])
    skills = [s for s in (experiment.skills or []) if s in SKILLS]
    submission = _latest_submission(db, student.id, experiment.id)
    features = _code_features(submission.code if submission else experiment.starter_code)
    mistakes = _student_mistakes(db, student.id, experiment.id)
    scenarios = list(experiment.what_if_scenarios or [])
    focus = list(experiment.focus_categories or [])

    skill_names = [p for s in skills for p in SKILL_POINTS.get(s, ())]
    first_concept = concepts[0] if concepts else (skills[0] if skills else "this experiment")

    # 1. concept
    q1 = {
        "type": "concept",
        "question": f"In your own words, explain {first_concept} and why {experiment.title} needs it.",
        "skill": skills[0] if skills else None,
        "concept": first_concept,
        "difficulty": "easy",
        "points": _points(points_for_text(f"{first_concept} {experiment.objective}", skill_names or ["correctness reasoning"])),
        "related_category": None,
    }

    # 2. code explanation, about something that is genuinely in the student's own submission
    subject = features[0] if features else "your solution"
    q2 = {
        "type": "code_explanation",
        "question": (
            f"Walk through {subject} in the code you submitted for {experiment.title}: what does it do, step by step?"
            if submission else
            f"Describe how you would structure a solution to {experiment.title}, step by step."
        ),
        "skill": skills[0] if skills else None,
        "concept": "reading your own code",
        "difficulty": "medium",
        "points": _points(["correctness reasoning", *points_for_text(f"{subject} {' '.join(features)}", skill_names or ["debugging method"])]),
        "related_category": None,
        "about_submission_id": submission.id if submission else None,
    }

    # 3. debugging, taken from the student's real Mistake DNA where there is one
    if mistakes:
        category = mistakes[0]["category"]
        meta = CATEGORIES.get(category, {})
        q3 = {
            "type": "debugging",
            "question": (
                f"Your submissions have shown {mistakes[0]['label'].lower()} "
                f"({mistakes[0]['count']} time{'s' if mistakes[0]['count'] != 1 else ''}). "
                "What causes that kind of mistake, and how do you find and fix it?"
            ),
            "skill": SKILL_FOR_CATEGORY.get(category),
            "concept": meta.get("concept", "debugging"),
            "difficulty": "medium",
            "points": _points(CATEGORY_POINTS.get(category, ("debugging method",))),
            "related_category": category,
        }
    else:
        category = focus[0] if focus else "logic"
        q3 = {
            "type": "debugging",
            "question": (
                f"{experiment.title} often goes wrong with {category_label(category).lower()}. "
                "How would you find that kind of fault in a program, and what would you check first?"
            ),
            "skill": SKILL_FOR_CATEGORY.get(category),
            "concept": CATEGORIES.get(category, {}).get("concept", "debugging"),
            "difficulty": "medium",
            "points": _points(CATEGORY_POINTS.get(category, ("debugging method",))),
            "related_category": category,
        }

    # 4. what-would-happen-if, from the teacher's own what-if scenarios where they exist
    if scenarios:
        s = scenarios[0]
        q4 = {
            "type": "what_if",
            "question": f"What would happen if {s.get('title', 'one condition changed').lower()}? Explain what the program would print, and why.",
            "skill": skills[0] if skills else None,
            "concept": s.get("title", "changing a condition"),
            "difficulty": "medium",
            "points": _points(["correctness reasoning", *points_for_text(f"{s.get('title', '')} {s.get('explanation', '')}", ["edge cases"])]),
            "related_category": None,
            "scenario_id": s.get("id"),
        }
    else:
        q4 = {
            "type": "what_if",
            "question": f"What would happen if {experiment.title} were given an empty or zero input? Explain what your program would do, and why.",
            "skill": skills[0] if skills else None,
            "concept": "edge cases",
            "difficulty": "medium",
            "points": _points(["edge cases", "correctness reasoning"]),
            "related_category": "boundary",
        }

    # 5. improvement
    q5 = {
        "type": "improvement",
        "question": (
            f"How could your solution to {experiment.title} be made faster or more reliable for very large inputs? "
            "Name one change and say what it would save."
        ),
        "skill": "Problem Solving" if "Problem Solving" in SKILLS else (skills[0] if skills else None),
        "concept": "efficiency and robustness",
        "difficulty": "hard",
        "points": _points(["complexity", "edge cases"]),
        "related_category": "inefficient" if "inefficient" in focus else None,
    }

    questions = [q1, q2, q3, q4, q5][:QUESTION_COUNT]
    for i, q in enumerate(questions, start=1):
        q["index"] = i
        q["total"] = len(questions)
        q["expected_points"] = [p["concept"] for p in q["points"]]
    return questions


# ---------------------------------------------------------------------------------------------- answers
def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9<>=+ ]+", " ", (text or "").lower())


def evaluate_answer(question: dict, answer: str) -> dict:
    """Keyword and concept matching against the points the question expects. Deliberately simple, and stated as such."""
    text = _normalise(answer)
    words = set(text.split())
    matched, missing = [], []
    for point in question["points"]:
        # Longer keywords match as substrings so ordinary word endings count ("stops", "iterations",
        # "initialised"); very short ones ("0", "<=") must match a whole word to avoid false hits.
        hit = any(
            (kw in text) if len(kw) >= 4 else (kw in words)
            for kw in (k.lower() for k in point["keywords"])
        )
        (matched if hit else missing).append(point["concept"])

    total = len(question["points"]) or 1
    if len((answer or "").strip()) < MIN_ANSWER_CHARS:
        matched, missing = [], [p["concept"] for p in question["points"]]
        score = 0
    else:
        score = round(MAX_POINTS * len(matched) / total)
        if matched and len(text.split()) >= 25:
            score = min(MAX_POINTS, score + 1)  # a developed answer that names the ideas
    verdict = "correct" if score >= PASS_SCORE else "partially correct" if score >= PARTIAL_SCORE else "incorrect"

    if score == 0 and not (answer or "").strip():
        feedback = "No answer was given, so nothing could be credited."
    elif not missing:
        feedback = f"You named every idea this question was looking for: {', '.join(matched)}."
    elif matched:
        feedback = f"Good on {', '.join(matched)}. Still missing: {', '.join(missing)}. Say what each one does and why it matters here."
    else:
        feedback = f"This answer does not mention {', '.join(missing)}. Try again with those ideas in your own words."

    return {
        "score": score, "out_of": MAX_POINTS, "verdict": verdict,
        "matched_concepts": matched, "missing_concepts": missing,
        "feedback": feedback, "related_category": question.get("related_category"),
    }


# ---------------------------------------------------------------------------------------------- sessions
def _rows(db: Session, student_id: int, session_id: str) -> list[AIInteraction]:
    """Every answered question of one session, in order. The transcript lives in `ai_interactions`."""
    rows = db.scalars(
        select(AIInteraction)
        .where(AIInteraction.student_id == student_id, AIInteraction.kind == "viva")
        .order_by(AIInteraction.id)
    ).all()
    return [r for r in rows if (r.request_context or {}).get("session_id") == session_id]


def _session_or_404(db: Session, student: Student, session_id: str) -> tuple[Experiment, list[AIInteraction]]:
    rows = _rows(db, student.id, session_id)
    if not rows:
        raise NotFound("Viva session not found")
    experiment = db.get(Experiment, rows[0].experiment_id)
    if experiment is None:
        raise NotFound("Experiment not found")
    return experiment, rows


def context(db: Session, student: Student) -> dict:
    """What the viva page opens with: which experiments can be examined, and recent vivas."""
    from app.services import views

    experiments = db.scalars(
        select(Experiment).where(Experiment.is_published.is_(True)).order_by(Experiment.position, Experiment.id)
    ).all()
    progress = views.experiment_progress(db, student.id)
    choices = [
        {
            "id": e.id, "title": e.title, "difficulty": e.difficulty, "skills": e.skills or [],
            "best_percent": (progress.get(e.id) or {}).get("best_percent"),
            "submitted": bool((progress.get(e.id) or {}).get("submissions")),
        }
        for e in experiments
    ]
    choices.sort(key=lambda c: (not c["submitted"], c["id"]))
    return {"experiments": choices, "question_count": QUESTION_COUNT, "history": history(db, student), "note": NOTE}


def start(db: Session, student: Student, experiment: Experiment, now=None) -> dict:
    now = now or utcnow()
    questions = build_questions(db, student, experiment)
    # A random suffix: two vivas started in the same second must not share an id.
    session_id = f"v{student.id}-{experiment.id}-{int(now.timestamp()):x}{secrets.token_hex(4)}"
    return {
        "session_id": session_id,
        "experiment": {"id": experiment.id, "title": experiment.title, "difficulty": experiment.difficulty},
        "total_questions": len(questions),
        "question": public(questions[0]),
        "note": NOTE,
    }


def public(question: dict) -> dict:
    """What the student sees: never the keyword list used for matching."""
    return {k: v for k, v in question.items() if k != "points"}


def answer(db: Session, student: Student, session_id: str, text: str, now=None) -> dict:
    now = now or utcnow()
    rows = _rows(db, student.id, session_id)
    if rows:
        experiment = db.get(Experiment, rows[0].experiment_id)
    else:
        # First answer of a session: the id must be one this student was issued (v<student>-<experiment>-<time>).
        match = re.fullmatch(r"v(\d+)-(\d+)-([0-9a-f]{6,})", session_id or "")
        if not match or int(match.group(1)) != student.id:
            raise NotFound("Viva session not found")
        experiment = db.get(Experiment, int(match.group(2)))
    if experiment is None or not experiment.is_published:
        raise NotFound("Experiment not found")

    questions = build_questions(db, student, experiment)
    index = len(rows)
    if index >= len(questions):
        raise AppError(409, "This viva is already finished. Open the summary or start a new one.")
    question = questions[index]
    result = evaluate_answer(question, text)

    db.add(AIInteraction(
        student_id=student.id, experiment_id=experiment.id,
        submission_id=question.get("about_submission_id"),
        kind="viva", hint_level=question["index"],
        request_context={"session_id": session_id, "index": question["index"], "type": question["type"],
                         "question": question["question"], "concept": question["concept"],
                         "expected_points": question["expected_points"], "answer": (text or "")[:4000]},
        response=result, provider="rules", created_at=now,
    ))
    db.flush()

    finished = index + 1 >= len(questions)
    nxt = None if finished else public(questions[index + 1])
    return {
        "session_id": session_id,
        "evaluation": result,
        "answered": index + 1,
        "total_questions": len(questions),
        "finished": finished,
        "next_question": nxt,
        "next_recommendation": (
            f"Next: a {nxt['type'].replace('_', ' ')} question on {nxt['concept']}." if nxt
            else "That was the last question. Open your viva summary."
        ),
        "note": NOTE,
    }


def summary(db: Session, student: Student, session_id: str, now=None) -> dict:
    """The end-of-viva summary. Records skill evidence once, and links weak concepts to Mistake DNA (read-only)."""
    now = now or utcnow()
    experiment, rows = _session_or_404(db, student, session_id)
    answers = [
        {**(r.request_context or {}), **{"result": r.response or {}}}
        for r in rows
    ]
    total = sum(a["result"].get("score", 0) for a in answers)
    out_of = len(answers) * MAX_POINTS
    ratio = total / out_of if out_of else 0.0

    demonstrated, needs_practice = [], []
    for a in answers:
        demonstrated += a["result"].get("matched_concepts", [])
        needs_practice += a["result"].get("missing_concepts", [])
    demonstrated = list(dict.fromkeys(demonstrated))
    needs_practice = [c for c in dict.fromkeys(needs_practice) if c not in demonstrated]

    # Mistake DNA: the categories behind the questions that went badly, with the counts already on record.
    profile = {c["category"]: c for c in mistake_service.mistake_profile(db, student.id, with_practice=False)["categories"]}
    linked = []
    for a in answers:
        category = a["result"].get("related_category")
        if not category or a["result"].get("score", 0) >= PASS_SCORE:
            continue
        recorded = profile.get(category)
        linked.append({
            "category": category, "label": category_label(category),
            "recorded_count": recorded["count"] if recorded else 0,
            "recurring": bool(recorded and recorded["recurring"]),
            "skill": SKILL_FOR_CATEGORY.get(category),
            "practice": mistake_service.practice_for(db, student.id, category, limit=1),
        })

    # Practice link: from a weak category if there is one, otherwise the experiment just examined.
    recommendation = None
    for item in linked:
        if item["practice"]:
            p = item["practice"][0]
            recommendation = {
                "experiment_id": p["experiment_id"], "title": p["title"],
                "reason": f"Your answers suggest you need more practice with {item['label'].lower()}. Try {p['title']}.",
            }
            break
    if recommendation is None and needs_practice:
        recommendation = {
            "experiment_id": experiment.id, "title": experiment.title,
            "reason": f"Revisit {experiment.title} and look again at {', '.join(needs_practice[:2])}.",
        }

    already = db.scalar(
        select(func.count()).select_from(AIInteraction)
        .where(AIInteraction.student_id == student.id, AIInteraction.kind == "viva_summary")
        .where(AIInteraction.request_context["session_id"].as_string() == session_id)
    )
    skill_changes = []
    if not already and answers:
        # Practice evidence, at a lower weight than graded work. Scores and grades are never touched.
        for skill in dict.fromkeys(s for s in (experiment.skills or []) if s in SKILLS):
            change = skill_service.record_skill_evidence(
                db, student.id, skill, ratio, SKILL_WEIGHT, now, experiment_id=experiment.id, source="viva",
            )
            if change:
                skill_changes.append(change)
        db.add(AIInteraction(
            student_id=student.id, experiment_id=experiment.id, kind="viva_summary", hint_level=0,
            request_context={"session_id": session_id, "answered": len(answers)},
            response={"total": total, "out_of": out_of, "percent": round(100 * ratio)},
            provider="rules", created_at=now,
        ))
        db.flush()

    return {
        "session_id": session_id,
        "experiment": {"id": experiment.id, "title": experiment.title},
        "total_score": total, "out_of": out_of, "percent": round(100 * ratio),
        "questions_answered": len(answers),
        "answers": [
            {"index": a.get("index"), "type": a.get("type"), "question": a.get("question"),
             "answer": a.get("answer"), **a["result"]}
            for a in answers
        ],
        "concepts_demonstrated": demonstrated,
        "concepts_needing_practice": needs_practice,
        "mistake_dna": linked,
        "recommendation": recommendation,
        "skill_changes": skill_changes,
        "note": NOTE,
    }


def history(db: Session, student: Student, limit: int = 5) -> list[dict]:
    rows = db.scalars(
        select(AIInteraction).where(AIInteraction.student_id == student.id, AIInteraction.kind == "viva_summary")
        .order_by(AIInteraction.id.desc()).limit(limit)
    ).all()
    out = []
    for r in rows:
        experiment = db.get(Experiment, r.experiment_id)
        out.append({
            "session_id": (r.request_context or {}).get("session_id"),
            "experiment_id": r.experiment_id, "title": experiment.title if experiment else "(removed)",
            "answered": (r.request_context or {}).get("answered"),
            "percent": (r.response or {}).get("percent"), "at": r.created_at,
        })
    return out
