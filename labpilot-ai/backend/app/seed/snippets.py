"""Student code variants used to build realistic demo history (correct solutions and typical mistakes)."""
from app.seed.catalogue import DEBUGGING, FACTORIAL, LIST_STATS, PRIME, SORT_SEARCH

FACT_LOOP = "for i in range(1, n + 1):\n    result *= i\nprint(result)\n"

SNIPPETS = {
    "factorial": {
        "syntax": "n = int(input())\nresult = 1\nfor i in range(1, n + 1)\n    result *= i\nprint(result)\n",
        "prompt": "n = int(input(\"Enter n: \"))\nresult = 1\n" + FACT_LOOP,
        "off_by_one": "n = int(input())\nresult = 1\nfor i in range(1, n):\n    result *= i\nprint(result)\n",
        "correct": FACTORIAL["reference_solution"],
    },
    "liststats": {
        "index_error": (
            "n = int(input())\nnumbers = list(map(int, input().split()))\ntotal = 0\nlargest = numbers[0]\nsmallest = numbers[0]\n"
            "for i in range(len(numbers) + 1):\n    total += numbers[i]\n    if numbers[i] > largest:\n        largest = numbers[i]\n"
            "    if numbers[i] < smallest:\n        smallest = numbers[i]\nprint(total)\nprint(largest)\nprint(smallest)\nprint(f\"{total / n:.2f}\")\n"
        ),
        "max_zero": (
            "n = int(input())\nnumbers = list(map(int, input().split()))\ntotal = 0\nlargest = 0\nsmallest = numbers[0]\n"
            "for x in numbers:\n    total += x\n    if x > largest:\n        largest = x\n    if x < smallest:\n        smallest = x\n"
            "print(total)\nprint(largest)\nprint(smallest)\nprint(f\"{total / n:.2f}\")\n"
        ),
        "floor_div": (
            "n = int(input())\nnumbers = list(map(int, input().split()))\ntotal = 0\nlargest = numbers[0]\nsmallest = numbers[0]\n"
            "for x in numbers:\n    total += x\n    if x > largest:\n        largest = x\n    if x < smallest:\n        smallest = x\n"
            "print(total)\nprint(largest)\nprint(smallest)\nprint(f\"{total // n:.2f}\")\n"
        ),
        "correct": LIST_STATS["reference_solution"],
    },
    "debug": {
        "starter": DEBUGGING["starter_code"],
        "tie_picks_last": (
            "n = int(input())\nsales = list(map(int, input().split()))\ntotal = 0\nbest_day = 0\n"
            "for i in range(n):\n    total += sales[i]\n    if sales[i] >= sales[best_day]:\n        best_day = i\n"
            "print(total)\nprint(best_day + 1)\nprint(f\"{total / n:.2f}\")\n"
        ),
        "correct": DEBUGGING["reference_solution"],
    },
    "prime": {
        "naive_no_edge": (
            "def is_prime(n):\n    for d in range(2, n):\n        if n % d == 0:\n            return False\n    return True\n\n\n"
            "n = int(input())\nprint(\"Prime\" if is_prime(n) else \"Not prime\")\n"
        ),
        "naive": (
            "def is_prime(n):\n    if n < 2:\n        return False\n    for d in range(2, n):\n        if n % d == 0:\n            return False\n    return True\n\n\n"
            "n = int(input())\nprint(\"Prime\" if is_prime(n) else \"Not prime\")\n"
        ),
        "sqrt_exclusive": (
            "def is_prime(n):\n    if n < 2:\n        return False\n    for d in range(2, int(n ** 0.5)):\n        if n % d == 0:\n            return False\n    return True\n\n\n"
            "n = int(input())\nprint(\"Prime\" if is_prime(n) else \"Not prime\")\n"
        ),
        "correct": PRIME["reference_solution"],
    },
    "sort": {
        "binary_any_match": SORT_SEARCH["reference_solution"].replace(
            "answer = mid\n            high = mid - 1", "return mid"
        ),
        "descending": SORT_SEARCH["reference_solution"].replace("items[j] > current", "items[j] < current"),
        "correct": SORT_SEARCH["reference_solution"],
    },
}
