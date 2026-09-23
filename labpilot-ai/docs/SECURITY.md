# Security notes (Prototype v0.1)

**LabPilot AI is a teaching prototype. It is not production-secure and has not had an independent security review.**
It runs code written by students, so the code sandbox is the most sensitive part. This document says what is
protected, how, what was tested, and where the limits are. Read the limits before exposing it to anyone you do not trust.

## Summary of the final review

| Area | Result |
| --- | --- |
| Student code execution | **A real escape was found and fixed** (see below). The sandbox is now harder to break but is still **not a security boundary**. |
| Authentication | bcrypt passwords, signed JWTs with expiry, login lockout. No server-side token revocation. |
| Authorization | Every route is role-checked on the server; an access-matrix test probes every operation as anonymous, student and teacher. |
| API validation | Pydantic schemas with length and range limits on every body; friendly 422 messages. |
| Database access | SQLAlchemy expression layer only; a code search found no raw or string-built SQL (one static `PRAGMA`). |
| Transport and browser | Basic security headers are sent. **No HTTPS, no CSP, no CSRF layer** in this build. |
| Demo accounts | Published passwords. The seed refuses to run when `APP_ENV=production`. |

## Running student code

Every run starts a **fresh Python process, never the API process**. The API sends the program and its input, and reads back
captured output.

### What was found in the final review

Before the hardening, one line of student code reached the operating system:

```python
W = [c for c in ().__class__.__base__.__subclasses__() if c.__name__ == "_wrap_close"][0]
W.__init__.__globals__["system"]("id")     # ran a shell command; as root, fork() worked too
```

The earlier import guard and the disabled `open()` never saw this, because the program never wrote an `import` statement.
The previous version of this document listed such escapes as "not defended against"; that was accurate, and it is now
reduced but not eliminated. **Any copy of this project from before this hardening should not be used with untrusted users.**

### Layers now in place (subprocess mode, the default and the only tested mode)

| Layer | What it does |
| --- | --- |
| Separate process | A fresh `python -I -S` interpreter per run in a throw-away temp directory, with a minimal environment (no inherited secrets, no site-packages). |
| OS resource limits | CPU seconds, address space (`SANDBOX_MEMORY_MB`), file size, open files, and (non-root only) process count. POSIX only. |
| Wall-clock timeout | The parent kills the whole process group after `SANDBOX_TIMEOUT_SECONDS`. |
| Import allow-list | Only a short list of standard-library modules can be imported by the program. |
| `open()` removed, `sys` replaced | `open` raises; `sys` is a small shim. |
| **Static check** (new) | Before the program runs it is parsed, and it is refused with a readable message if it uses `eval`, `exec`, `compile`, `getattr`, `setattr`, `delattr`, `vars`, `globals`, `locals`, or attributes such as `__subclasses__`, `__globals__`, `__mro__`, `__self__` and frame or traceback internals. A program may still use those words as its own variable names. |
| **Audit hook** (new) | The real barrier. It fires when the *operation* happens, however the program reached it, and refuses: starting or forking processes, deleting or renaming files, any file open except read-only access to the interpreter's own library files, listing directories, opening sockets, `subprocess`, `ctypes`, `pickle`, `sqlite3`, `shutil`, `gc` heap walking, and reading stack frames. It cannot be removed from Python code. |
| Output cap, traceback filtering | Output is truncated; error text omits host paths and harness internals. |
| Concurrency cap, rate limit, size limit | `SANDBOX_MAX_CONCURRENT` (HTTP 503), `EXEC_MAX_PER_MINUTE` per user (HTTP 429), `MAX_CODE_CHARS`. |

**How it was tested.** `backend/tests/test_sandbox_escapes.py` (plus `test_sandbox.py`) covers:

* seven object-graph escapes, each refused with a readable message;
* ten dangerous operations reached through a route that skips both the static check and the import guard, so the audit
  hook alone must stop them (shell command, fork as root, reading `/etc/passwd`, writing a file, directory listing, delete,
  heap walk, socket, subprocess, ctypes);
* the real `sys` module reached through another module;
* a large program (dataclasses, namedtuple, Enum, `strptime`, `random`, `json`, `re`, `decimal`, and more) whose output must equal the
  host interpreter's, so hardening did not break ordinary lab programs.

Along the way this also fixed a pre-existing bug: `datetime.strptime` was blocked by the old import guard.

### Limits you must know about

* **Not a hardened sandbox.** Python-level restrictions are known to be bypassable by a determined and skilled attacker
  (interpreter bugs, unforeseen stdlib behaviour, and so on). The layers above stop honest mistakes, casual abuse and the
  well-known tricks. They are not a substitute for OS-level isolation.
* **Same OS user as the API.** If a bypass were found, student code could read whatever the API user can read, including
  `backend/.env` and the SQLite database. There is no network namespace, seccomp filter or read-only filesystem in this mode.
* **Run the API as an unprivileged user, not root.** The audit hook refuses `fork` even for root, but `RLIMIT_NPROC` is not
  enforced for root. The server logs a warning at start-up when it runs as root.
* **Some information can still be read.** The program may read the interpreter's own `.py`/`.so` files, check whether a file exists,
  and use string formatting to print the representation of objects. None of this executes code, but it is not perfect secrecy.
* **Resource limits are POSIX-only.** On Windows the memory and CPU limits are not applied (the timeout, the process-tree kill and the audit hook are). Windows support was fixed after a user report and has not been run on a real Windows machine by the author; use WSL or a Linux container for anything that matters.
* **Denial of service is limited, not prevented.** A run can use up to `SANDBOX_MEMORY_MB` for up to `SANDBOX_TIMEOUT_SECONDS`, times
  `SANDBOX_MAX_CONCURRENT`. Rate limits and lockouts are in memory per process and use the client IP, which is the proxy's address behind a reverse proxy.
* **Behaviour change for students.** The restricted names above cannot be used in student programs, including `eval(input())`.
* **Docker mode (`SANDBOX_MODE=docker`) is experimental and has never been run.** It copies the same harness, but the build
  environment had no Docker daemon. Treat it as a starting point.

### Recommended for real use

Run student code in a container or micro-VM (Docker with `--network none`, `--read-only`, a non-root user, dropped capabilities and a
seccomp profile, or gVisor / Firecracker) on a separate worker host from the API and database, with per-run CPU and memory quotas. Keep
the layers above as a second line of defence. Move rate limits to Redis.

## Hidden test cases

Hidden cases exist so students cannot hard-code answers. They are protected in three places:

1. **API responses.** Student-facing serialisers replace `stdin`, expected output, observed output and error text of hidden cases with `null`
   and return only the verdict. Teachers see everything.
2. **AI Copilot.** The context sent to any AI provider contains the names, kinds, statuses and error types of hidden failures, never their data,
   and never the reference solution. The request is also stored in an audit table with the same restrictions.
3. **Tests.** `test_hidden_test_data_is_concealed_from_students` and `test_hidden_test_data_is_never_sent_to_the_ai` were checked by mutation:
   removing the protection makes them fail.

## AI provider safety

* Student code and questions are treated as untrusted data: they are fenced inside tags and the system prompt tells the model to ignore instructions found there.
* Replies must parse as the expected JSON shape; fenced code blocks longer than three lines are stripped; a reply that reproduces the reference solution is
  discarded and replaced by rule-based guidance. The leak check also covers reference solutions shorter than three lines.
* Hidden-case values echoed by an error message (a `ValueError` quoting the input, say) are redacted before the diagnosis reaches the AI, and mistake details are never sent, only category labels and experiment titles.
* Any provider error, timeout or invalid reply falls back to rule-based guidance, and the interface says so.
* **Privacy:** when a real provider is configured, the student's code and test results are sent to that third party. Tell students, and check your
  institution's data policy first. With no API key nothing leaves the server.
* Every request is logged in `ai_interactions` (level, provider, category) for review.

## Accounts and sessions

* Passwords: bcrypt with a per-password salt, after a SHA-256 pre-hash so long passwords are not truncated at 72 bytes. Minimum length 8.
* Sessions: signed JWT (HS256) with an expiry (`ACCESS_TOKEN_MINUTES`, default 480). The key comes from `SECRET_KEY`; the server warns while the development
  default is in use and **refuses to start with `APP_ENV=production` unless it is a random string of 32 or more characters**. There is no server-side
  revocation: signing out only deletes the token in the browser.
* The browser keeps the token in `localStorage`, which any script on the page can read. A production build should use an `HttpOnly` cookie with CSRF protection over HTTPS.
* Login failures are limited per IP and email (`LOGIN_MAX_FAILURES` in `LOGIN_WINDOW_SECONDS`), and the message is identical for unknown emails and wrong passwords.
* Roles are enforced on the server for every route, and authentication runs before any lookup, so an unknown id gives an anonymous or wrong-role caller 401 or 403, never
  a 404 that reveals what exists. Self-registration always creates a student; teachers are created by the seed script or by an existing teacher.
* A student can only read their own attempts, submissions, hints and mistakes; other students' ids return 404.
* Teachers see class-wide mistake totals without names, and cannot read individual students' mistake profiles or Copilot conversations. Individual code and results are visible to teachers by design.

## Browser and network

* Responses carry `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: same-origin`; `/api/` responses are `Cache-Control: no-store`.
* CORS allows only the origins in `CORS_ORIGINS`. The Vite dev proxy makes CORS unnecessary in development.
* **Not implemented:** HTTPS/HSTS (terminate TLS in front of the app), a Content-Security-Policy, CSRF protection (not needed for bearer tokens, needed if you move to cookies).

## Demo data

The seed creates accounts with published passwords (`Teacher@123`, `Student@123`). `python -m app.seed` therefore **refuses to run when
`APP_ENV=production`** unless `--allow-production` is passed. Never deploy the demo accounts. Do not put real personal data in a prototype database.

## Known gaps

No email verification or password reset, no audit log for teacher actions, no HTTPS termination, no CSP, no CSRF layer, no token revocation, no automated dependency
scanning, no database migrations, no backups, and no independent penetration test.
