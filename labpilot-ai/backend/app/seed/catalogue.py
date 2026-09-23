"""The five prototype experiments: statements, reference solutions, test cases, what-if scenarios.

Every program reads from stdin and prints to stdout. `reference_solution` is teacher-only and is
verified against the test cases by `tests/test_catalogue.py` and by `python -m app.seed --check`.
"""
from bisect import bisect_left
from random import Random

_rng = Random(20260919)
_big_list = [_rng.randint(-5000, 5000) for _ in range(2000)]
_big_target = _big_list[1234]
_big_sorted = sorted(_big_list)


def _t(name, stdin, expected, kind="normal", hidden=False, weight=1):
    return {"name": name, "stdin": stdin, "expected_output": expected, "kind": kind, "is_hidden": hidden, "weight": weight}


# --------------------------------------------------------------------------- 1. Factorial
FACTORIAL = {
    "title": "Factorial Calculator",
    "difficulty": "beginner",
    "position": 1,
    "estimated_minutes": 15,
    "skills": ["Python Basics", "Loops"],
    "focus_categories": ["loop_condition", "input_handling", "boundary"],
    "concepts": ["for loops and range()", "accumulator variables", "reading input with input()"],
    "objective": "Use a loop to build up a result step by step, and handle the special case of zero.",
    "problem_statement": (
        "The factorial of a non-negative integer n, written n!, is the product of all integers from 1 to n. "
        "By definition 0! = 1.\n\n"
        "Write a program that reads one integer n (0 <= n <= 20) and prints n!.\n\n"
        "Input: a single line containing n.\n"
        "Output: a single line containing n!.\n\n"
        "Example: input 5 gives output 120 (because 1 x 2 x 3 x 4 x 5 = 120)."
    ),
    "instructions": (
        "- Read n with input() and convert it with int().\n"
        "- Do not pass a prompt to input(). Any extra text you print is compared with the expected output.\n"
        "- Use a for loop with range() to multiply the numbers together.\n"
        "- Decide what value the accumulator must start with, and check what happens for n = 0.\n"
        "- Press Run to test against the visible cases. Submit grades you against every case, including hidden ones."
    ),
    "starter_code": "n = int(input())\n\n# Compute n! here and print it\n",
    "reference_solution": "n = int(input())\nresult = 1\nfor i in range(1, n + 1):\n    result *= i\nprint(result)\n",
    "hints": [
        "Start with a variable that will hold the running product. Which value never changes a product?",
        "range(1, n + 1) visits 1, 2, ..., n. Remember that the end value of range() is excluded.",
        "For n = 0 the loop body never runs, so the starting value of the accumulator is the answer.",
    ],
    "what_if_scenarios": [
        {
            "id": "range-off-by-one",
            "title": "The loop stops one number early",
            "description": "The loop uses range(1, n) instead of range(1, n + 1). Predict the output for n = 5.",
            "stdin": "5",
            "modified_code": "n = int(input())\nresult = 1\nfor i in range(1, n):\n    result *= i\nprint(result)\n",
            "explanation": "range(1, n) stops before n, so for n = 5 only 1 x 2 x 3 x 4 = 24 is computed and the final x 5 is missed. The end value of range() is always excluded.",
        },
        {
            "id": "start-at-zero",
            "title": "The accumulator starts at 0",
            "description": "The result variable starts at 0 instead of 1. Predict the output for n = 5.",
            "stdin": "5",
            "modified_code": "n = int(input())\nresult = 0\nfor i in range(1, n + 1):\n    result *= i\nprint(result)\n",
            "explanation": "Anything multiplied by 0 is 0, so the running product never leaves 0. A product must start from 1, the multiplicative identity, just as a sum starts from 0.",
        },
    ],
    "test_cases": [
        _t("Sample: n = 5", "5\n", "120\n"),
        _t("Zero", "0\n", "1\n", kind="edge"),
        _t("Small: n = 7", "7\n", "5040\n"),
        _t("One", "1\n", "1\n", kind="edge", hidden=True),
        _t("Medium: n = 10", "10\n", "3628800\n", hidden=True),
        _t("Largest allowed: n = 20", "20\n", "2432902008176640000\n", kind="edge", hidden=True),
    ],
}

# --------------------------------------------------------------------------- 2. List statistics
LIST_STATS = {
    "title": "List Statistics",
    "difficulty": "beginner",
    "position": 2,
    "estimated_minutes": 20,
    "skills": ["Arrays", "Loops", "Python Basics"],
    "focus_categories": ["array_index", "boundary", "input_handling"],
    "concepts": ["lists and indexing", "iterating over a list", "initialising min/max variables", "formatting numbers"],
    "objective": "Process a list of numbers with a loop and report its sum, largest value, smallest value and average.",
    "problem_statement": (
        "Read a list of integers and print four statistics about it.\n\n"
        "Input: the first line contains n (1 <= n <= 1000). The second line contains n integers separated by spaces. "
        "The integers may be negative.\n"
        "Output: four lines: the sum, the largest value, the smallest value and the average rounded to 2 decimal places.\n\n"
        "Example:\n"
        "Input:\n5\n3 8 1 9 4\n"
        "Output:\n25\n9\n1\n5.00"
    ),
    "instructions": (
        "- Read the numbers with input().split() and convert each item with int().\n"
        "- Practise iteration: compute the four values with a loop rather than the built-in sum(), max() and min().\n"
        "- Think carefully about the starting values of your largest and smallest variables. Would 0 work if every number is negative?\n"
        "- Format the average with an f-string such as f\"{value:.2f}\".\n"
        "- Use Run first to see how your program behaves on the visible cases."
    ),
    "starter_code": "n = int(input())\nnumbers = list(map(int, input().split()))\n\n# Print the sum, largest, smallest and average (2 decimals), one per line\n",
    "reference_solution": (
        "n = int(input())\nnumbers = list(map(int, input().split()))\n"
        "total = 0\nlargest = numbers[0]\nsmallest = numbers[0]\n"
        "for x in numbers:\n    total += x\n    if x > largest:\n        largest = x\n    if x < smallest:\n        smallest = x\n"
        "print(total)\nprint(largest)\nprint(smallest)\nprint(f\"{total / n:.2f}\")\n"
    ),
    "hints": [
        "Loop over the list once and update several variables inside the same loop.",
        "Start largest and smallest from the first element numbers[0], not from a fixed number like 0.",
        "For the average use / (true division) and format with :.2f. Integer division // throws away the fraction.",
    ],
    "what_if_scenarios": [
        {
            "id": "index-past-end",
            "title": "The loop reads one index too far",
            "description": "The loop runs over range(len(numbers) + 1). Predict what happens for the list 4 5 6.",
            "stdin": "3\n4 5 6\n",
            "modified_code": "n = int(input())\nnumbers = list(map(int, input().split()))\ntotal = 0\nfor i in range(len(numbers) + 1):\n    total += numbers[i]\nprint(total)\n",
            "explanation": "A list of 3 items has valid indexes 0, 1 and 2. The extra iteration asks for numbers[3], which does not exist, so Python stops with IndexError. The last valid index is always len(list) - 1.",
        },
        {
            "id": "floor-division",
            "title": "The average uses // instead of /",
            "description": "The average is computed with floor division. Predict the last line for the numbers 10 20 30 41.",
            "stdin": "4\n10 20 30 41\n",
            "modified_code": "n = int(input())\nnumbers = list(map(int, input().split()))\ntotal = 0\nfor x in numbers:\n    total += x\nprint(f\"{total // n:.2f}\")\n",
            "explanation": "The sum is 101 and 101 // 4 is 25 because floor division drops the fraction, so the program prints 25.00 rather than 25.25. Use / when you want the exact average.",
        },
    ],
    "test_cases": [
        _t("Sample: 3 8 1 9 4", "5\n3 8 1 9 4\n", "25\n9\n1\n5.00\n"),
        _t("Fractional average", "4\n10 20 30 41\n", "101\n41\n10\n25.25\n"),
        _t("All negative numbers", "3\n-4 -9 -2\n", "-15\n-2\n-9\n-5.00\n", kind="edge"),
        _t("Single element", "1\n7\n", "7\n7\n7\n7.00\n", kind="edge", hidden=True),
        _t("Zeros and one value", "6\n0 0 5 0 0 0\n", "5\n5\n0\n0.83\n", hidden=True),
        _t("Large values", "4\n1000000 2000000 3000000 4000000\n", "10000000\n4000000\n1000000\n2500000.00\n", hidden=True),
        _t("Mixed signs", "5\n-3 7 -1 4 0\n", "7\n7\n-3\n1.40\n", hidden=True),
    ],
}

# --------------------------------------------------------------------------- 3. Debugging
DEBUGGING = {
    "title": "Debugging Challenge: Sales Report",
    "difficulty": "intermediate",
    "position": 3,
    "estimated_minutes": 25,
    "skills": ["Debugging", "Loops", "Arrays"],
    "focus_categories": ["loop_condition", "input_handling", "logic", "boundary"],
    "concepts": ["reading error output", "tracing a loop by hand", "0-based versus 1-based numbering"],
    "objective": "Find and fix several faults in a program that is almost right, using the failing test cases as evidence.",
    "problem_statement": (
        "A shop owner records the sales for each day of a period. The provided program should report:\n"
        "1. the total sales,\n2. the number of the best day (days are numbered from 1; if several days tie, report the earliest),\n"
        "3. the average daily sales rounded to 2 decimal places.\n\n"
        "Input: the first line contains n (the number of days, n >= 1). The second line contains n non-negative integers.\n"
        "Output: three lines: total, best day number, average.\n\n"
        "Example:\nInput:\n3\n10 20 15\nOutput:\n45\n2\n15.00\n\n"
        "The starter program has several bugs. Run it, read what goes wrong and fix them one at a time."
    ),
    "instructions": (
        "- Run the starter code first and compare the actual and expected output for each failing test.\n"
        "- Change one thing at a time and run again, so you know which change fixed which symptom.\n"
        "- The bugs are of different kinds: one affects how input is read, one affects which items the loop visits, "
        "one affects the numbering of the answer and one affects formatting.\n"
        "- Ask the Copilot for a hint if you get stuck. It will not fix the code for you."
    ),
    "starter_code": (
        "n = int(input(\"Number of days: \"))\n"
        "sales = list(map(int, input().split()))\n"
        "total = 0\nbest_day = 0\n"
        "for i in range(1, n):\n"
        "    total += sales[i]\n"
        "    if sales[i] > sales[best_day]:\n"
        "        best_day = i\n"
        "print(total)\nprint(best_day)\nprint(total / n)\n"
    ),
    "reference_solution": (
        "n = int(input())\nsales = list(map(int, input().split()))\ntotal = 0\nbest_day = 0\n"
        "for i in range(n):\n    total += sales[i]\n    if sales[i] > sales[best_day]:\n        best_day = i\n"
        "print(total)\nprint(best_day + 1)\nprint(f\"{total / n:.2f}\")\n"
    ),
    "hints": [
        "Run the starter code on the first sample and compare each output line with the expected line. Which line differs first?",
        "Whatever you pass to input() is printed. Also check which list positions the for loop actually visits.",
        "Python counts positions from 0 but the report counts days from 1, and the average needs exactly two decimals.",
    ],
    "what_if_scenarios": [
        {
            "id": "prompt-in-input",
            "title": "input() is given a prompt",
            "description": "The first line reads n with input(\"Days: \"). Predict the first line of output for the input 3 / 10 20 15.",
            "stdin": "3\n10 20 15\n",
            "modified_code": "n = int(input(\"Days: \"))\nsales = list(map(int, input().split()))\nprint(sum(sales))\n",
            "explanation": "input() prints its prompt to standard output before reading. The checker compares everything the program prints, so the text 'Days: ' becomes part of the first line and the answer no longer matches.",
        },
        {
            "id": "zero-based-day",
            "title": "The best day is not shifted by one",
            "description": "The program prints best_day directly, an index that starts at 0. Predict the output for the sales 10 20 15.",
            "stdin": "3\n10 20 15\n",
            "modified_code": "n = int(input())\nsales = list(map(int, input().split()))\nbest_day = 0\nfor i in range(n):\n    if sales[i] > sales[best_day]:\n        best_day = i\nprint(best_day)\n",
            "explanation": "The largest value 20 sits at index 1, and the program prints that index. People count days from 1, so the report needs best_day + 1. Indexes and human-facing numbering often differ by one.",
        },
    ],
    "test_cases": [
        _t("Sample: 10 20 15", "3\n10 20 15\n", "45\n2\n15.00\n"),
        _t("Tie for best day", "5\n120 80 200 200 50\n", "650\n3\n130.00\n"),
        _t("Single day", "1\n7\n", "7\n1\n7.00\n", kind="edge"),
        _t("All zero", "4\n0 0 0 0\n", "0\n1\n0.00\n", kind="edge", hidden=True),
        _t("Best day in second place", "6\n5 9 2 9 1 4\n", "30\n2\n5.00\n", hidden=True),
        _t("Two days", "2\n1 2\n", "3\n2\n1.50\n", hidden=True),
    ],
}

# --------------------------------------------------------------------------- 4. Prime numbers
PRIME = {
    "title": "Prime Number Checker",
    "difficulty": "intermediate",
    "position": 4,
    "estimated_minutes": 25,
    "skills": ["Functions", "Loops", "Problem Solving"],
    "focus_categories": ["boundary", "loop_condition", "inefficient"],
    "concepts": ["divisibility and the modulo operator", "edge cases 0 and 1", "stopping at the square root", "writing a function"],
    "objective": "Write a function that decides whether a number is prime, and make it fast enough for very large inputs.",
    "problem_statement": (
        "A prime number is greater than 1 and has no divisors other than 1 and itself.\n\n"
        "Read one integer n (0 <= n <= 1,000,000,000) and print Prime if it is prime, otherwise print Not prime.\n\n"
        "Examples:\n17 -> Prime\n15 -> Not prime\n1 -> Not prime\n\n"
        "Some test cases use very large numbers. A program that tries every divisor up to n will run out of time."
    ),
    "instructions": (
        "- Put the check in a function such as is_prime(n) that returns True or False, then call it and print the answer.\n"
        "- Handle n < 2 first. Neither 0 nor 1 is prime.\n"
        "- Test divisors starting at 2 and use the modulo operator: n % d == 0 means d divides n.\n"
        "- Think about how far you really need to search. If n has a divisor larger than its square root, the matching divisor is smaller.\n"
        "- Watch the loop's end condition: what happens for n = 4 and n = 9?"
    ),
    "starter_code": "def is_prime(n):\n    # Return True if n is prime, otherwise False\n    pass\n\n\nn = int(input())\nprint(\"Prime\" if is_prime(n) else \"Not prime\")\n",
    "reference_solution": (
        "def is_prime(n):\n    if n < 2:\n        return False\n    d = 2\n    while d * d <= n:\n        if n % d == 0:\n            return False\n        d += 1\n    return True\n\n\n"
        "n = int(input())\nprint(\"Prime\" if is_prime(n) else \"Not prime\")\n"
    ),
    "hints": [
        "Start with the special cases: which numbers below 2 are not prime?",
        "If n = a x b with a <= b, then a <= sqrt(n). So you can stop once d * d > n.",
        "Use d * d <= n as the loop condition. A condition that stops one step early wrongly accepts squares like 4, 9 and 25.",
    ],
    "what_if_scenarios": [
        {
            "id": "sqrt-exclusive",
            "title": "The search stops before the square root",
            "description": "The loop is range(2, int(n ** 0.5)) and never tests the square root itself. Predict the output for n = 9.",
            "stdin": "9\n",
            "modified_code": "n = int(input())\nprime = n >= 2\nfor d in range(2, int(n ** 0.5)):\n    if n % d == 0:\n        prime = False\nprint(\"Prime\" if prime else \"Not prime\")\n",
            "explanation": "int(9 ** 0.5) is 3, and range(2, 3) only contains 2. The divisor 3 is never tested, so 9 is reported as Prime. The end of range() is exclusive, so the square root needs + 1.",
        },
        {
            "id": "missing-small-check",
            "title": "There is no check for n < 2",
            "description": "The program starts by assuming the number is prime and only looks for divisors. Predict the output for n = 1.",
            "stdin": "1\n",
            "modified_code": "n = int(input())\nprime = True\nfor d in range(2, n):\n    if n % d == 0:\n        prime = False\nprint(\"Prime\" if prime else \"Not prime\")\n",
            "explanation": "For n = 1 the loop range(2, 1) is empty, so no divisor is ever found and prime stays True. Numbers below 2 are not prime by definition and must be handled before the loop.",
        },
    ],
    "test_cases": [
        _t("Smallest prime: 2", "2\n", "Prime\n"),
        _t("Composite: 15", "15\n", "Not prime\n"),
        _t("Prime: 17", "17\n", "Prime\n"),
        _t("One is not prime", "1\n", "Not prime\n", kind="edge"),
        _t("Zero is not prime", "0\n", "Not prime\n", kind="edge", hidden=True),
        _t("Square of a prime: 4", "4\n", "Not prime\n", kind="edge", hidden=True),
        _t("Square of a prime: 25", "25\n", "Not prime\n", kind="edge", hidden=True),
        _t("Prime: 97", "97\n", "Prime\n", hidden=True),
        _t("Very large prime", "999999937\n", "Prime\n", kind="performance", hidden=True, weight=2),
    ],
}

# --------------------------------------------------------------------------- 5. Sorting & searching
SORT_SEARCH = {
    "title": "Sorting and Binary Search",
    "difficulty": "advanced",
    "position": 5,
    "estimated_minutes": 40,
    "skills": ["Sorting & Searching", "Arrays", "Functions", "Problem Solving"],
    "focus_categories": ["array_index", "boundary", "loop_condition", "logic"],
    "concepts": ["comparison sorting", "swapping list items", "binary search", "first occurrence in a sorted list"],
    "objective": "Sort a list without using sorted() or list.sort(), then find a value in it with binary search.",
    "problem_statement": (
        "Read a list of integers and a target value. Sort the list in ascending order, then find the target "
        "in the sorted list.\n\n"
        "Input: the first line contains n (1 <= n <= 5000). The second line contains n integers. The third line contains the target.\n"
        "Output: the first line is the sorted list with values separated by single spaces. The second line is the "
        "0-based index of the target in the sorted list, or -1 if it is not present. If the target appears several times, "
        "print the smallest index.\n\n"
        "Example:\nInput:\n5\n64 25 12 22 11\n22\nOutput:\n11 12 22 25 64\n2"
    ),
    "instructions": (
        "- Implement the sort yourself (bubble, selection or insertion sort are all fine). The point of the experiment is the algorithm.\n"
        "- Then implement binary search on the sorted list using two indexes, low and high, and the middle position between them.\n"
        "- Duplicates make binary search tricky: when you find the target, the earliest copy may still be further left.\n"
        "- Print the list with print(*items) so the values are separated by single spaces.\n"
        "- Trace your program on a tiny list (such as 3 items) by hand before you run it."
    ),
    "starter_code": (
        "n = int(input())\nvalues = list(map(int, input().split()))\ntarget = int(input())\n\n\n"
        "def sort_values(items):\n    # Return a new ascending list without using sorted() or .sort()\n    pass\n\n\n"
        "def find_first(items, target):\n    # Return the smallest index of target in the sorted list, or -1\n    pass\n\n\n"
        "ordered = sort_values(values)\nprint(*ordered)\nprint(find_first(ordered, target))\n"
    ),
    "reference_solution": (
        "def sort_values(items):\n    items = list(items)\n    for i in range(1, len(items)):\n        current = items[i]\n        j = i - 1\n"
        "        while j >= 0 and items[j] > current:\n            items[j + 1] = items[j]\n            j -= 1\n        items[j + 1] = current\n    return items\n\n\n"
        "def find_first(items, target):\n    low, high = 0, len(items) - 1\n    answer = -1\n    while low <= high:\n        mid = (low + high) // 2\n"
        "        if items[mid] == target:\n            answer = mid\n            high = mid - 1\n        elif items[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return answer\n\n\n"
        "n = int(input())\nvalues = list(map(int, input().split()))\ntarget = int(input())\nordered = sort_values(values)\nprint(*ordered)\nprint(find_first(ordered, target))\n"
    ),
    "hints": [
        "Split the work: one function only sorts, another only searches. Test the sort by printing its result first.",
        "Binary search keeps low and high; compare the middle value with the target and discard half of the list each time.",
        "When items[mid] == target, remember the position but keep searching the left half so you end on the first occurrence.",
    ],
    "what_if_scenarios": [
        {
            "id": "reversed-comparison",
            "title": "The swap condition is reversed",
            "description": "A bubble sort swaps neighbours when a[j] < a[j + 1] instead of a[j] > a[j + 1]. Predict the output for the list 3 1 4 1 5 with target 4.",
            "stdin": "5\n3 1 4 1 5\n4\n",
            "modified_code": "n = int(input())\na = list(map(int, input().split()))\nt = int(input())\nfor i in range(n):\n    for j in range(n - 1 - i):\n        if a[j] < a[j + 1]:\n            a[j], a[j + 1] = a[j + 1], a[j]\nprint(*a)\nprint(a.index(t) if t in a else -1)\n",
            "explanation": "Swapping when the left item is smaller pushes the small values to the right, so the list ends up in descending order: 5 4 3 1 1. The index of 4 in that order is 1. Reversing a comparison reverses the sort.",
        },
        {
            "id": "inner-loop-too-short",
            "title": "The inner loop stops one step early",
            "description": "The inner bubble-sort loop is range(n - 2 - i) instead of range(n - 1 - i). Predict the output for the list 5 4 3 2 1 with target 1.",
            "stdin": "5\n5 4 3 2 1\n1\n",
            "modified_code": "n = int(input())\na = list(map(int, input().split()))\nt = int(input())\nfor i in range(n):\n    for j in range(n - 2 - i):\n        if a[j] > a[j + 1]:\n            a[j], a[j + 1] = a[j + 1], a[j]\nprint(*a)\nprint(a.index(t) if t in a else -1)\n",
            "explanation": "The final pair of neighbours is never compared, so the 1 at the end never moves left and the list comes out as 2 3 4 5 1, only partly sorted. The search then runs on data that is not in order and reports index 4. Boundary values in nested loops are a common source of subtle bugs.",
        },
    ],
    "test_cases": [
        _t("Sample list", "5\n64 25 12 22 11\n22\n", "11 12 22 25 64\n2\n"),
        _t("Target missing", "4\n8 3 5 1\n7\n", "1 3 5 8\n-1\n"),
        _t("Negative numbers", "6\n-5 10 -20 0 7 -1\n-1\n", "-20 -5 -1 0 7 10\n2\n"),
        _t("Single element", "1\n42\n42\n", "42\n0\n", kind="edge"),
        _t("Duplicates: first occurrence", "7\n4 2 7 2 9 2 5\n2\n", "2 2 2 4 5 7 9\n0\n", kind="edge", hidden=True),
        _t("Already sorted, last item", "5\n1 2 3 4 5\n5\n", "1 2 3 4 5\n4\n", hidden=True),
        _t("Reverse sorted", "5\n9 7 5 3 1\n9\n", "1 3 5 7 9\n4\n", hidden=True),
        _t("Target is the smallest", "8\n30 10 20 50 40 80 70 60\n10\n", "10 20 30 40 50 60 70 80\n0\n", hidden=True),
        _t(
            "Large list (2000 values)",
            f"{len(_big_list)}\n{' '.join(map(str, _big_list))}\n{_big_target}\n",
            f"{' '.join(map(str, _big_sorted))}\n{bisect_left(_big_sorted, _big_target)}\n",
            kind="performance", hidden=True, weight=2,
        ),
    ],
}

EXPERIMENTS = [FACTORIAL, LIST_STATS, DEBUGGING, PRIME, SORT_SEARCH]
