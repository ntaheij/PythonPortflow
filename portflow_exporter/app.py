from __future__ import annotations

import argparse
from typing import Optional

from . import api, cli, logic
from .exporters import export_csv_wide
from .time_range import TimeRange, range_between_dates, range_last_days, range_since_date


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--time-range",
        choices=["prompt", "all", "last", "between", "since"],
        default="prompt",
        help="Filter evaluations by time range. 'prompt' asks interactively.",
    )
    parser.add_argument("--days", type=int, default=None, help="Used with --time-range last")
    parser.add_argument("--start-date", type=str, default=None, help="Used with --time-range between/since (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="Used with --time-range between (YYYY-MM-DD)")
    return parser


def _time_range_from_args(args: argparse.Namespace) -> TimeRange:
    if args.time_range == "prompt":
        return TimeRange()
    if args.time_range == "all":
        return TimeRange()
    if args.time_range == "last":
        if not args.days or args.days <= 0:
            raise ValueError("--days must be > 0 for --time-range last")
        return range_last_days(args.days)
    if args.time_range == "between":
        if not args.start_date or not args.end_date:
            raise ValueError("--start-date and --end-date are required for --time-range between")
        return range_between_dates(args.start_date, args.end_date)
    if args.time_range == "since":
        if not args.start_date:
            raise ValueError("--start-date is required for --time-range since")
        return range_since_date(args.start_date)
    raise ValueError(f"Unknown time range: {args.time_range}")


def run(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        time_range = _time_range_from_args(args)
    except ValueError as e:
        print(f"Invalid time range arguments: {e}")
        return 2

    token = cli.prompt_token()

    while True:
        method_label = cli.choose_student_fetch_method()
        if method_label == "Quit":
            return 0

        method = "shared"
        if method_label.startswith("All students"):
            method = "shared"
        elif method_label.startswith("Students from section (select"):
            method = "section_select"
        elif method_label.startswith("Students from custom"):
            method = "section_custom"

        students = None

        if method == "shared":
            shared = api.get_shared_collections(token)
            if shared == api.TokenExpired:
                print("Token expired, please enter a new one.")
                token = cli.prompt_token()
                continue
            if shared is None:
                print("Failed to fetch shared collections. Please try again.")
                continue
            students = logic.extract_students(shared)  # type: ignore[arg-type]

        elif method == "section_select":
            section_id = cli.select_section_id(token)
            if section_id == api.TokenExpired:
                print("Token expired, please enter a new one.")
                token = cli.prompt_token()
                continue
            if section_id is None:
                continue
            students = api.get_students_from_section(token, section_id)
            if students == api.TokenExpired:
                print("Token expired, please enter a new one.")
                token = cli.prompt_token()
                continue
            if students is None:
                print("Failed to fetch students. Please try again.")
                continue

        else:
            section_id = input("Enter section_id: ").strip()
            students = api.get_students_from_section(token, section_id)
            if students == api.TokenExpired:
                print("Token expired, please enter a new one.")
                token = cli.prompt_token()
                continue
            if students is None:
                print("Failed to fetch students. Please try again.")
                continue

        if not students:
            print("No students found.")
            continue

        # time range prompt only if requested
        if args.time_range == "prompt":
            time_range = cli.prompt_time_range_interactive()

        print(f"\nActive time filter: {time_range.describe()}")

        print(f"\nFound {len(students)} students:")
        for name in sorted(students.keys()):
            if "has_access" in students[name] and not students[name]["has_access"]:
                print(f"- {name} (Geen Toegang)")
            else:
                print(f"- {name}")

        out_label = cli.choose_output_mode()
        if out_label == "Main menu":
            continue

        include_reviewer = cli.prompt_include_reviewer()

        if out_label == "Single student":
            name = cli.prompt_student_name(students)
            if not name:
                print("Student not found.")
                continue

            results = logic.collect_results(token, name, students[name], include_reviewer, time_range)
            if results == api.TokenExpired:
                print("Token expired, please enter a new one.")
                token = cli.prompt_token()
                continue

            if not results:
                print(f"\nNo evaluations found for {name}")
                continue

            print(f"\n{name}")
            goals: dict = {}
            for r in results:
                goal = r["goal_name"]
                if include_reviewer:
                    eval_str = f"{r['evaluation']} ({r['reviewer_name']})"
                else:
                    eval_str = r["evaluation"]
                goals.setdefault(goal, []).append(eval_str)

            from .exporters import sort_goals

            for goal in sort_goals(goals.keys()):
                print(f"{goal}: {', '.join(goals[goal])}")

        else:
            all_results = []
            total = len(students)
            processed = 0
            for name, data in students.items():
                processed += 1
                print(f"Processing {name}... ({processed}/{total})")
                res = logic.collect_results(token, name, data, include_reviewer, time_range)
                if res == api.TokenExpired:
                    print("Token expired, please enter a new one.")
                    token = cli.prompt_token()
                    break
                if res:
                    all_results.extend(res)
            else:
                if all_results:
                    export_csv_wide(all_results, include_reviewer)
                else:
                    print("\nNo evaluation data found for any student.")


def main() -> None:
    raise SystemExit(run())

