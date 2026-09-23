"""Local knowledge for the AI Copilot chat: plain-language error explanations, debugging steps, concept notes and
practice problems. Used when no AI provider is configured (and as the safety net when one fails).

Nothing here is a solution to an experiment: concept examples are generic, and practice problems are new
problems, not the lab's own. Text is checked against every experiment's reference solution by the tests.
"""

# ---- errors, in simple words ----------------------------------------------------------------------------
SIMPLE = {
    "syntax": "Python is a very literal reader. It found something it cannot read, so it stopped before running any of your code.",
    "input_handling": "Your program may compute the right thing, but the way it reads the input or prints the answer does not match what the checker expects.",
    "array_index": "Your code asked a list for an item at a position it does not have, like asking for page 5 of a 4-page booklet.",
    "runtime": "The program started, then hit something it could not do (dividing by zero, using a name that does not exist, mixing up types) and crashed.",
    "boundary": "Your program works for everyday inputs but breaks on a special case at the edge, such as the smallest or largest allowed value.",
    "loop_condition": "A loop is repeating one time too many or too few, so the result is off by one step.",
    "inefficient": "The answer is right, but the program takes too long on big inputs. It needs a shorter route to the same answer.",
    "logic": "The program runs without crashing, but somewhere a step does something different from what you intended.",
}

# ---- step-by-step debugging ({case} is filled with the first failing case) ------------------------------------
DEBUG_STEPS = {
    "syntax": [
        "Read the first line of the error message: it names the problem and a line number.",
        "Look at that line and the one above it. Missing colons after if/for/while/def, unclosed brackets or quotes, and inconsistent indentation are the usual causes.",
        "Fix one thing, then press Run again. Do not change several things at once.",
        "If a different error appears, that is progress: Python now understands the earlier lines.",
    ],
    "input_handling": [
        "Open {case} in the results table and compare the Expected and Observed columns character by character.",
        "Check that the program prints only the answer: no prompts, labels or extra words.",
        "Check how each input line is read: int(input()) for one number, input().split() for several values on one line.",
        "Run again and make sure this case matches before you look at the others.",
    ],
    "array_index": [
        "Find the line named in the error message: it is the one asking for a position that does not exist.",
        "For a list of length n the valid positions are 0 to n-1. Work out the length of the list for {case}.",
        "Write down the first and last position your loop uses. Is either one outside 0 to n-1?",
        "Adjust the loop bounds or the index, then run again.",
    ],
    "runtime": [
        "Read the last line of the error message first: it names the error type and often the value involved.",
        "The line above it in the traceback shows which line of your code failed.",
        "Ask what value that line received for {case}: is a name undefined, a value of the wrong type, or a division by zero?",
        "Fix that one line and run again.",
    ],
    "boundary": [
        "Look at {case}: it is an unusual value, not an everyday one.",
        "Ask what the problem statement says about the smallest, largest, zero or empty input.",
        "Follow your code with that input by hand: which branch does it take?",
        "Add handling for that special case, then re-run all the visible tests to be sure the everyday cases still work.",
    ],
    "loop_condition": [
        "Take {case} and write down the value of the loop variable on every pass.",
        "Compare the first and last values with what the problem needs. Remember that range(a, b) stops before b.",
        "Decide whether the loop starts too early, ends too soon, or runs one time too many.",
        "Change one bound at a time and run again.",
    ],
    "inefficient": [
        "The small cases pass, so the idea works. The problem is time.",
        "Estimate how many loop passes the largest input needs. Would that finish in a few seconds?",
        "Look for work you can skip: a point where the loop can stop early, or a smaller range that gives the same answer.",
        "Change the approach, then submit to check the hidden performance case.",
    ],
    "logic": [
        "Take {case} and work out by hand what the correct answer should be.",
        "Trace your code with that input line by line, writing down every variable's value.",
        "Find the first line where a value differs from what you expected. That line, or the one before it, holds the fault.",
        "Fix that one step and run again.",
    ],
}

NOT_RUN_STEPS = [
    "Open the experiment in the editor.",
    "Write a first version, even an incomplete one.",
    "Press Run tests.",
    "Come back here and ask again. The Copilot works from your real results.",
]

# ---- concept notes: first match on the concept text wins ----------------------------------------------------
# example_kind: "code" is shown as code, "text" as a plain worked example.
CONCEPT_NOTES = [
    {"pattern": r"range|for loop", "title": "for loops and range()", "idea": "A for loop repeats a block once for each value in a sequence. range(a, b) produces a, a+1, ... up to b-1: it stops just before b.", "example_kind": "code", "example": "for i in range(2, 5):\n    print(i)      # prints 2, 3, 4", "watch_out": "The end value is never included, and range(5) starts at 0, not 1."},
    {"pattern": r"accumulator|running total", "title": "accumulator variables", "idea": "An accumulator is a variable that starts with a neutral value and is updated inside a loop to build up a result, like a running total on a till receipt.", "example_kind": "code", "example": "total = 0\nfor price in [4, 6, 5]:\n    total = total + price   # 4, then 10, then 15", "watch_out": "The starting value must not change the answer: 0 is neutral for adding, 1 for multiplying."},
    {"pattern": r"input\(\)|reading input|reading and converting", "title": "reading input with input()", "idea": "input() reads one line typed by the user as text. Convert it with int() or float() when you need a number, and use split() to break a line into several values.", "example_kind": "code", "example": "n = int(input())\nparts = input().split()   # 'a b c' -> ['a', 'b', 'c']", "watch_out": "Do not print prompts such as 'Enter n:'. The checker compares your output exactly."},
    {"pattern": r"list|index|indices", "title": "lists and indexing", "idea": "A list keeps items in order. Positions start at 0, so a list of length n has valid positions 0 to n-1. Negative positions count from the end: -1 is the last item.", "example_kind": "code", "example": "items = [4, 8, 15]\nprint(items[0], items[-1])   # 4 15", "watch_out": "items[len(items)] is one past the end and raises IndexError."},
    {"pattern": r"iterat", "title": "iterating over a list", "idea": "for x in items visits every item in order, so you do not need to manage positions yourself. Use range(len(items)) only when you need the position too.", "example_kind": "code", "example": "for word in ['a', 'bb', 'ccc']:\n    print(len(word))", "watch_out": "Do not add or remove items from a list while looping over it."},
    {"pattern": r"min/max|minimum|maximum|largest|smallest", "title": "tracking a minimum or maximum", "idea": "To find the largest value, keep a 'best so far' variable. Start it with a value that cannot be wrong (such as the first item), and replace it whenever you meet a better one.", "example_kind": "text", "example": "Tracing [3, 9, 4]: best starts at 3. It sees 9, which is bigger, so best becomes 9. It sees 4, which is not bigger, so best stays 9.", "watch_out": "Starting from 0 fails when every value is negative."},
    {"pattern": r"format", "title": "formatting numbers", "idea": "An f-string lets you control how a value is printed. After the colon, .2f means 'fixed-point with 2 decimals'. This changes only what is shown, not the stored value.", "example_kind": "code", "example": "x = 2.71828\nprint(f\"{x:.2f}\")   # 2.72", "watch_out": "Check the expected output for the exact number of decimals."},
    {"pattern": r"error output|traceback|reading error|tracebacks", "title": "reading error output", "idea": "A traceback lists the lines Python was running when it failed. The last line names the error type and message, and the line of code just above it shows where it happened.", "example_kind": "text", "example": "'IndexError: list index out of range' on line 6 means line 6 asked a list for a position it does not have.", "watch_out": "Fix the first error first. Later errors are often side effects of it."},
    {"pattern": r"trac(e|ing)", "title": "tracing by hand", "idea": "Tracing means playing the computer: make a table with one column per variable and one row per pass of the loop, and update the values exactly as the code would.", "example_kind": "text", "example": "For 'total = 0; for x in [2, 5]: total += x' the rows are: x=2 total=2; x=5 total=7.", "watch_out": "Trace what the code does, not what you meant it to do."},
    {"pattern": r"0-based|1-based|numbering|off-by-one", "title": "0-based versus 1-based numbering", "idea": "People count from 1, Python counts positions from 0. The first item is items[0], and range(n) gives 0 to n-1.", "example_kind": "text", "example": "In the list ['a', 'b', 'c'], 'a' is at position 0 and 'c' is at position 2, although the list has 3 items.", "watch_out": "Off-by-one mistakes usually come from mixing the two ways of counting."},
    {"pattern": r"modulo|divisib|remainder", "title": "divisibility and the modulo operator", "idea": "a % b is the remainder left after dividing a by b. If the remainder is 0, b divides a exactly.", "example_kind": "code", "example": "print(12 % 4, 13 % 4)   # 0 1", "watch_out": "a % 0 raises ZeroDivisionError."},
    {"pattern": r"edge case|special case|boundary", "title": "edge cases", "idea": "Edge cases are the smallest, largest or most unusual valid inputs (0, 1, empty, negative). Rules often behave differently there than for ordinary values, so test them on purpose.", "example_kind": "text", "example": "A rule such as 'a number is special if it has exactly two divisors' needs an explicit decision for 0 and 1.", "watch_out": "Ask what the definition says about the smallest input before you write code."},
    {"pattern": r"square root|sqrt", "title": "stopping at the square root", "idea": "If a number has a divisor larger than its square root, it also has a matching divisor smaller than its square root. So when searching for divisors you only need to look up to the square root.", "example_kind": "text", "example": "For 36 the pairs are 2 x 18, 3 x 12, 4 x 9 and 6 x 6. Every pair has a member of 6 or less.", "watch_out": "Be careful whether the last value you test is included in your loop."},
    {"pattern": r"function|def ", "title": "writing a function", "idea": "def gives a group of steps a name and lets it take inputs (parameters). return sends a value back to the caller, so the answer can be used or printed elsewhere.", "example_kind": "code", "example": "def double(x):\n    return x * 2\nprint(double(4))   # 8", "watch_out": "A function that only prints returns None."},
    {"pattern": r"binary search", "title": "binary search", "idea": "On a sorted list, look at the middle item. If the target is smaller, keep only the lower half; if larger, keep only the upper half. Repeat until you find it or nothing is left.", "example_kind": "text", "example": "Searching for 7 in [1, 3, 5, 7, 9]: the middle is 5, which is too small, so keep [7, 9]; the middle of that is 7, found.", "watch_out": "The list must already be sorted, and both ends of the search range must be updated every pass."},
    {"pattern": r"first occurrence", "title": "first occurrence in a sorted list", "idea": "With repeated values, finding one match is not enough. After a match, keep looking in the lower half for an earlier one.", "example_kind": "text", "example": "In [2, 4, 4, 4, 9] the value 4 sits at positions 1, 2 and 3; the first occurrence is position 1.", "watch_out": "Remember the match you found while you keep searching."},
    {"pattern": r"swap", "title": "swapping list items", "idea": "Python can swap two items in one step, without a temporary variable, by assigning both at once.", "example_kind": "code", "example": "a[0], a[2] = a[2], a[0]", "watch_out": "Both positions must be valid indices."},
    {"pattern": r"sorting|comparison", "title": "comparison sorting", "idea": "Comparison sorts put items in order by repeatedly comparing two items and moving them. Bubble, selection and insertion sort differ in which items they compare and how they move them.", "example_kind": "text", "example": "Bubble sort passes over the list, swapping neighbours that are in the wrong order, until a pass makes no swaps.", "watch_out": "After each pass, think about which part of the list is now certainly in place."},
    {"pattern": r"complexity|slow|efficien", "title": "algorithmic complexity", "idea": "Complexity asks how much work a program needs as the input grows. A loop up to n does about n steps; a loop up to the square root of n does far fewer.", "example_kind": "text", "example": "For n = 1,000,000,000 a loop up to n needs a billion passes (too slow), but a loop up to the square root needs about 31,623.", "watch_out": "Estimate the passes for the largest allowed input before you submit."},
    {"pattern": r"syntax|indentation", "title": "Python syntax and indentation", "idea": "Python uses indentation to show which lines belong to an if, for, while or def, and a colon to start such a block. Every opening bracket and quote needs a closing one.", "example_kind": "code", "example": "if x > 0:\n    print('positive')   # indented lines belong to the if", "watch_out": "Mixing tabs and spaces in one file causes confusing errors."},
]

# ---- practice problems (new problems, grouped by skill) ---------------------------------------------------------
SIMILAR_PROBLEMS = {
    "Python Basics": [
        {"id": "pb-temperature", "title": "Temperature converter", "statement": "Read a temperature in degrees Celsius and print it in Fahrenheit with one decimal place.", "example": "Input: 100  ->  Output: 212.0", "start_with": "Write the conversion between the two scales in words first, then work out how to print exactly one decimal."},
        {"id": "pb-even-odd", "title": "Even or odd", "statement": "Read one integer and print Even or Odd.", "example": "Input: 7  ->  Output: Odd", "start_with": "What remainder does an even number leave when you divide it by 2?"},
    ],
    "Loops": [
        {"id": "lp-sum", "title": "Sum of the first n numbers", "statement": "Read n and print 1 + 2 + ... + n.", "example": "Input: 4  ->  Output: 10", "start_with": "Decide what the running total starts as, and which values the loop must visit."},
        {"id": "lp-vowels", "title": "Count the vowels", "statement": "Read one word and print how many vowels (a, e, i, o, u) it contains.", "example": "Input: education  ->  Output: 5", "start_with": "Go through the word one letter at a time and decide, for each letter, whether to count it."},
    ],
    "Functions": [
        {"id": "fn-leap", "title": "Leap year checker", "statement": "Write a function is_leap(year) and print Leap or Not leap for the year that is read. A year is a leap year if it is divisible by 4, except years divisible by 100 that are not divisible by 400.", "example": "Input: 2000  ->  Leap    Input: 1900  ->  Not leap", "start_with": "List the three divisibility rules in order of priority before writing any code."},
        {"id": "fn-palindrome", "title": "Palindrome check", "statement": "Write a function that says whether a word reads the same backwards. Print Yes or No.", "example": "Input: level  ->  Yes", "start_with": "Which two letters would you compare first, and where do the comparisons stop?"},
    ],
    "Arrays": [
        {"id": "ar-above-average", "title": "Above the average", "statement": "Read numbers on one line and print how many are strictly greater than their average.", "example": "Input: 1 2 3 4 10  ->  Output: 1", "start_with": "You need two passes over the numbers: one to find the average, one to count."},
        {"id": "ar-reverse", "title": "Reverse the list", "statement": "Read numbers on one line and print them in reverse order, separated by spaces, without using reverse() or slicing.", "example": "Input: 1 2 3  ->  Output: 3 2 1", "start_with": "Which positions does a loop need to visit, and in which order?"},
    ],
    "Sorting & Searching": [
        {"id": "ss-linear", "title": "Where is it?", "statement": "Read a list of numbers on one line, then a target on the next line. Print the position of the first occurrence of the target, or -1 if it is not there.", "example": "Input: 4 8 8 2 / 8  ->  Output: 1", "start_with": "Decide what your program should do the moment it finds a match."},
        {"id": "ss-sorted", "title": "Is it sorted?", "statement": "Read numbers on one line and print Yes if they are in non-decreasing order, otherwise No.", "example": "Input: 1 2 2 5  ->  Yes", "start_with": "Which pairs of neighbours would prove the list is NOT sorted?"},
    ],
    "Debugging": [
        {"id": "db-average", "title": "Fix the average", "statement": "This program should read n, then n numbers, and print their average. It gives the wrong answer. Find the fault and fix it.", "example": "n = int(input())\ntotal = 0\nfor i in range(1, n):\n    total += int(input())\nprint(total / n)", "start_with": "Trace it with n = 3 and count how many numbers it really reads."},
        {"id": "db-countdown", "title": "The countdown that never ends", "statement": "This program should print n, n-1, ... 1 and stop, but it runs forever. Find out why.", "example": "n = int(input())\nwhile n > 0:\n    print(n)\nn -= 1", "start_with": "Which lines are inside the loop? Look at the indentation."},
    ],
    "Problem Solving": [
        {"id": "ps-fizz", "title": "Fizz and Buzz", "statement": "For each number from 1 to n print the number, but print Fizz for multiples of 3, Buzz for multiples of 5, and FizzBuzz for multiples of both.", "example": "Input: 5  ->  1, 2, Fizz, 4, Buzz (one per line)", "start_with": "Which case must be checked first so that 15 does not print only Fizz?"},
        {"id": "ps-digits", "title": "Digit sum", "statement": "Read a non-negative integer and print the sum of its digits.", "example": "Input: 4096  ->  Output: 19", "start_with": "How can you peel off the last digit of a number, and what is left afterwards?"},
    ],
}

# The category of a recent mistake points to the skill worth practising.
CATEGORY_SKILL = {
    "loop_condition": "Loops", "array_index": "Arrays", "syntax": "Python Basics", "input_handling": "Python Basics",
    "runtime": "Debugging", "boundary": "Problem Solving", "inefficient": "Problem Solving", "logic": "Problem Solving",
}
