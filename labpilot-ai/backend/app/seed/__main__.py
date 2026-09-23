import argparse
import logging
import sys

from app.config import get_settings
from app.database import SessionLocal, drop_db, init_db
from app.seed import check_references, demo, seed_all

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description="Seed LabPilot AI with experiments and a demo cohort.")
    parser.add_argument("--reset", action="store_true", help="drop every table first")
    parser.add_argument("--minimal", action="store_true", help="only the teacher account and the experiments")
    parser.add_argument("--check", action="store_true", help="verify reference solutions and exit")
    parser.add_argument("--allow-production", action="store_true", help="create the demo accounts even though APP_ENV=production")
    args = parser.parse_args()

    if get_settings().environment.lower() in ("production", "prod") and not args.allow_production and not args.check:
        print("Refusing to create demo accounts with published passwords while APP_ENV=production.\n"
              "Create real accounts through the application, or pass --allow-production if you are sure.")
        return 2

    if args.check:
        problems = check_references()
        print("All reference solutions pass their test cases." if not problems else "\n".join(problems))
        return 1 if problems else 0

    if args.reset:
        drop_db()
    init_db()
    with SessionLocal() as db:
        result = seed_all(db, minimal=args.minimal)
    if not result["seeded"]:
        print("The database already contains accounts, so nothing was changed. Run with --reset to rebuild it.")
        return 0
    print(f"Seeded {result['experiments']} experiments and {result['students']} demo students.\n")
    print("Demo accounts")
    print(f"  Teacher  {demo.TEACHER['email']}  /  {demo.TEACHER['password']}")
    if not args.minimal:
        for s in demo.STUDENTS:
            print(f"  Student  {s['email']}  /  {s['password']}   ({s['full_name']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
