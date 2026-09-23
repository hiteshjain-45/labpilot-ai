"""Domain taxonomies: difficulty levels, practical skills and mistake categories.

Adding a skill or mistake category is a one-line change here; the rest of the system reads
these dictionaries.
"""

DIFFICULTIES = ["beginner", "intermediate", "advanced"]
DIFFICULTY_WEIGHT = {"beginner": 0.8, "intermediate": 1.0, "advanced": 1.25}

TEST_KINDS = ["normal", "edge", "performance"]

SKILLS: dict[str, str] = {
    "Python Basics": "Variables, input/output, arithmetic and control flow.",
    "Loops": "for/while loops, ranges and loop conditions.",
    "Functions": "Defining and reusing functions with parameters and return values.",
    "Arrays": "Lists, indexing, slicing and iteration over collections.",
    "Sorting & Searching": "Ordering data and locating values efficiently.",
    "Debugging": "Reading errors, isolating faults and fixing code that is almost right.",
    "Problem Solving": "Breaking a problem into steps and choosing a workable algorithm.",
}

SKILL_LEVELS = [(70, "Advanced"), (45, "Proficient"), (20, "Developing"), (0, "Novice")]


def skill_level_label(mastery: float) -> str:
    for threshold, label in SKILL_LEVELS:
        if mastery >= threshold:
            return label
    return "Novice"


# Ordered by how specific/actionable the diagnosis is (used to pick a primary category).
CATEGORY_PRIORITY = [
    "syntax",
    "input_handling",
    "array_index",
    "runtime",
    "boundary",
    "variable_init",
    "off_by_one",
    "loop_condition",
    "function_logic",
    "inefficient",
    "logic",
]

CATEGORIES: dict[str, dict[str, str]] = {
    "syntax": {
        "label": "Syntax errors",
        "concept": "Python syntax and indentation",
        "tip": "Read the line number in the error, then check colons, brackets, quotes and indentation on that line and the one above it.",
    },
    "logic": {
        "label": "Logic errors",
        "concept": "Tracing a program by hand",
        "tip": "Pick one failing input and trace the variables line by line on paper; compare each value with what you expect.",
    },
    "input_handling": {
        "label": "Input handling",
        "concept": "Reading and converting input",
        "tip": "Print nothing except the answer, and check how each input line is split and converted with int()/split().",
    },
    "array_index": {
        "label": "Array / index errors",
        "concept": "List indexing and valid index ranges",
        "tip": "For a list of length n the valid indices are 0..n-1. Check the first and last index your loop touches.",
    },
    "loop_condition": {
        "label": "Loop-condition errors",
        "concept": "range() bounds and loop termination",
        "tip": "Write down the first and last values the loop variable takes; range(a, b) stops before b.",
    },
    "boundary": {
        "label": "Boundary cases",
        "concept": "Edge cases and special values",
        "tip": "Before submitting, test the smallest, largest, zero, negative and single-element inputs.",
    },
    "inefficient": {
        "label": "Inefficient solutions",
        "concept": "Algorithmic complexity",
        "tip": "Estimate how many loop iterations the largest input needs, and look for a way to stop earlier or skip work.",
    },
    "off_by_one": {
        "label": "Off-by-one errors",
        "concept": "Counting from zero, and inclusive versus exclusive bounds",
        "tip": "Write down the first and last value your loop or index actually reaches, then compare them with the first and last you meant to reach.",
    },
    "variable_init": {
        "label": "Variable initialisation",
        "concept": "Starting values for counters and accumulators",
        "tip": "A running sum starts at 0 and a running product at 1. Check that the starting value is set once, before the loop, not inside it.",
    },
    "function_logic": {
        "label": "Function logic",
        "concept": "Calling functions and returning values",
        "tip": "Check that the function is actually called, and that every path through it returns a value: a path with no return gives back None.",
    },
    "runtime": {
        "label": "Runtime errors",
        "concept": "Reading Python tracebacks",
        "tip": "Read the last line of the traceback first: it names the error type and the value involved.",
    },
}


# Which skill(s) a mistake category is evidence about. The first entry is the main one. Used by the Skill Passport to
# turn repeated mistakes into "this skill needs improvement".
CATEGORY_SKILLS: dict[str, tuple[str, ...]] = {
    "syntax": ("Python Basics",),
    "input_handling": ("Python Basics",),
    "variable_init": ("Python Basics",),
    "loop_condition": ("Loops",),
    "off_by_one": ("Loops", "Arrays"),
    "array_index": ("Arrays",),
    "function_logic": ("Functions",),
    "runtime": ("Debugging",),
    "boundary": ("Problem Solving", "Algorithmic Thinking"),
    "inefficient": ("Problem Solving", "Algorithmic Thinking"),
    "logic": ("Problem Solving",),
}


# A new category practises the same skills as these existing focus tags, so an experiment tagged with either is
# useful practice for it. Teachers can also tag the new names directly.
RELATED_FOCUS: dict[str, tuple[str, ...]] = {
    "off_by_one": ("loop_condition", "boundary"),
    "variable_init": ("logic",),
    "function_logic": ("logic",),
}


SKILL_FOR_CATEGORY: dict[str, str] = {
    "syntax": "Python Basics", "input_handling": "Python Basics", "variable_init": "Python Basics",
    "loop_condition": "Loops", "off_by_one": "Loops",
    "array_index": "Arrays", "function_logic": "Functions",
    "runtime": "Debugging", "boundary": "Problem Solving", "inefficient": "Problem Solving", "logic": "Problem Solving",
}


def practice_tags(category: str) -> tuple[str, ...]:
    """Every focus tag that counts as practice for this mistake category."""
    return (category,) + RELATED_FOCUS.get(category, ())


def category_label(category: str) -> str:
    return CATEGORIES.get(category, {}).get("label", category.replace("_", " ").title())
