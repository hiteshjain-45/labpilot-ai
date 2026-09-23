"""Demo cohort: accounts and realistic study histories.

Histories are not inserted as fake rows. Every step is replayed through the real services
(sandbox execution, grading, Mistake DNA, skill updates, recommendations, Copilot, What-If) with
backdated timestamps, so the dashboards show exactly what the system would have computed.
"""

TEACHER = {
    "email": "teacher@labpilot.demo", "password": "Teacher@123",
    "full_name": "Dr. Meera Kapoor", "department": "Computer Science and Engineering",
}

STUDENTS = [
    {"key": "ananya", "email": "student@labpilot.demo", "password": "Student@123", "full_name": "Ananya Verma", "roll_number": "24CS017", "cohort": "CSE 2nd Year, Section A"},
    {"key": "rohan", "email": "rohan@labpilot.demo", "password": "Student@123", "full_name": "Rohan Mehta", "roll_number": "24CS031", "cohort": "CSE 2nd Year, Section A"},
    {"key": "priya", "email": "priya@labpilot.demo", "password": "Student@123", "full_name": "Priya Nair", "roll_number": "24CS044", "cohort": "CSE 2nd Year, Section A"},
    {"key": "karan", "email": "karan@labpilot.demo", "password": "Student@123", "full_name": "Karan Singh", "roll_number": "24CS052", "cohort": "CSE 2nd Year, Section A"},
    {"key": "sneha", "email": "sneha@labpilot.demo", "password": "Student@123", "full_name": "Sneha Iyer", "roll_number": "24CS063", "cohort": "CSE 2nd Year, Section A"},
]

# (kind, experiment, variant | scenario, days ago, "HH:MM", prediction for what-if steps)
# kinds: run | submit | hint | whatif. Experiments: factorial, liststats, debug, prime, sort.
JOURNEYS = {
    "ananya": [
        ("run", "factorial", "syntax", 20, "10:05", None),
        ("run", "factorial", "prompt", 20, "10:12", None),
        ("hint", "factorial", "prompt", 20, "10:15", None),
        ("run", "factorial", "off_by_one", 20, "10:26", None),
        ("submit", "factorial", "off_by_one", 20, "10:31", None),
        ("run", "factorial", "correct", 19, "16:20", None),
        ("submit", "factorial", "correct", 19, "16:22", None),
        ("run", "liststats", "index_error", 14, "11:00", None),
        ("hint", "liststats", "index_error", 14, "11:08", None),
        ("submit", "liststats", "floor_div", 14, "11:40", None),
        ("submit", "liststats", "correct", 13, "17:10", None),
        ("run", "debug", "starter", 9, "18:00", None),
        ("run", "debug", "starter", 9, "18:10", None),
        ("hint", "debug", "starter", 9, "18:12", None),
        ("submit", "debug", "tie_picks_last", 9, "18:40", None),
        ("whatif", "debug", "prompt-in-input", 8, "18:50", "Days: 45"),
        ("submit", "debug", "correct", 8, "19:00", None),
        ("run", "prime", "naive_no_edge", 5, "15:00", None),
        ("hint", "prime", "naive_no_edge", 5, "15:10", None),
        ("submit", "prime", "naive_no_edge", 5, "15:40", None),
        ("whatif", "factorial", "range-off-by-one", 4, "09:30", "120"),
        ("whatif", "factorial", "range-off-by-one", 4, "09:32", "24"),
    ],
    "rohan": [
        ("submit", "factorial", "correct", 12, "09:10", None),
        ("submit", "liststats", "correct", 11, "09:40", None),
        ("run", "debug", "tie_picks_last", 10, "10:00", None),
        ("submit", "debug", "tie_picks_last", 10, "10:05", None),
        ("submit", "debug", "correct", 10, "10:30", None),
        ("submit", "prime", "sqrt_exclusive", 7, "14:00", None),
        ("submit", "prime", "correct", 6, "14:20", None),
        ("submit", "sort", "binary_any_match", 3, "16:00", None),
    ],
    "priya": [
        ("run", "factorial", "syntax", 13, "20:00", None),
        ("submit", "factorial", "syntax", 13, "20:05", None),
        ("submit", "factorial", "off_by_one", 12, "20:30", None),
        ("submit", "factorial", "correct", 11, "21:00", None),
        ("run", "liststats", "index_error", 8, "19:00", None),
        ("run", "liststats", "index_error", 8, "19:10", None),
        ("hint", "liststats", "index_error", 8, "19:12", None),
        ("submit", "liststats", "index_error", 8, "19:30", None),
        ("submit", "liststats", "floor_div", 7, "19:00", None),
        ("submit", "liststats", "max_zero", 3, "18:30", None),
    ],
    "karan": [
        ("submit", "factorial", "correct", 10, "12:00", None),
        ("submit", "liststats", "max_zero", 9, "12:30", None),
        ("submit", "prime", "naive", 6, "13:00", None),
        ("run", "debug", "starter", 5, "13:30", None),
        ("submit", "debug", "starter", 5, "13:40", None),
        ("submit", "debug", "correct", 2, "13:00", None),
    ],
    "sneha": [
        ("submit", "factorial", "prompt", 6, "17:00", None),
        ("submit", "factorial", "correct", 5, "17:20", None),
        ("submit", "liststats", "correct", 2, "17:00", None),
    ],
}
