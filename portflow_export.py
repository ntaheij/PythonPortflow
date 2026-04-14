from portflow_exporter.app import main


if __name__ == "__main__":
    main()

from portflow_exporter.app import main

# ------------------------
# Time range helpers
# ------------------------

def parse_iso_datetime(value):
    """
    Parse common ISO-8601 datetime strings into a timezone-aware datetime.
    Returns None if parsing fails or value is falsy.
    """
    if value is None:
        return None

    # Sometimes APIs return unix timestamps (seconds or ms)
    if isinstance(value, (int, float)):
        try:
            v = float(value)
            # Heuristic: values > 1e12 are probably milliseconds
            if v > 1e12:
                v = v / 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (ValueError, OSError):
            return None

    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s:
        return None

    # Handle common 'Z' suffix for UTC
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None

    if dt.tzinfo is None:
        # Treat naive timestamps as UTC to keep comparisons consistent.
        dt = dt.replace(tzinfo=timezone.utc)

    return dt

def pick_item_timestamp(item):
    """
    Best-effort extraction of a timestamp from an API item.
    Returns a timezone-aware datetime or None.
    """
    if not isinstance(item, dict):
        return None

    # Use top-level "date" as the evaluation timestamp (as provided by API examples).
    # Fallbacks are kept only for compatibility with edge-case payloads.
    for key in ("date", "evaluation_date", "evaluationDate"):
        dt = parse_iso_datetime(item.get(key))
        if dt:
            return dt

    for key in ("created_at", "submitted_at", "updated_at", "createdAt", "submittedAt", "updatedAt"):
        dt = parse_iso_datetime(item.get(key))
        if dt:
            return dt

    evaluation = item.get("evaluation")
    if isinstance(evaluation, dict):
        for key in ("date", "evaluation_date", "evaluationDate", "created_at", "submitted_at", "updated_at", "createdAt", "submittedAt", "updatedAt"):
            dt = parse_iso_datetime(evaluation.get(key))
            if dt:
                return dt

    return None

def in_time_range(ts, start_dt, end_dt):
    if ts is None:
        # If the user selected any range, be strict and exclude items we can't date.
        return (start_dt is None and end_dt is None)
    if start_dt and ts < start_dt:
        return False
    if end_dt and ts > end_dt:
        return False
    return True

def describe_time_range(start_dt, end_dt):
    if start_dt is None and end_dt is None:
        return "All time"
    if start_dt is not None and end_dt is not None:
        return f"{start_dt.isoformat()} -> {end_dt.isoformat()}"
    if start_dt is not None:
        return f"From {start_dt.isoformat()}"
    return f"Until {end_dt.isoformat()}"

def ask_time_range():
    """
    Ask the user to select a time range.
    Returns (start_dt, end_dt) as timezone-aware datetimes in UTC, or (None, None) for all-time.
    """
    while True:
        print("\nSelect time range:")
        print("1) All time")
        print("2) Last N days")
        print("3) Between dates (YYYY-MM-DD to YYYY-MM-DD)")
        print("4) From date until today (YYYY-MM-DD to today)")
        choice = input("Choice: ").strip().lower()

        if choice == "1":
            return None, None

        if choice == "2":
            n_raw = input("Enter N (days): ").strip()
            if not n_raw.isdigit() or int(n_raw) <= 0:
                print("Invalid number of days.")
                continue
            n = int(n_raw)
            end_dt = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=n)
            return start_dt, end_dt

        if choice == "3":
            start_raw = input("Start date (YYYY-MM-DD): ").strip()
            end_raw = input("End date (YYYY-MM-DD): ").strip()
            try:
                start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
            except ValueError:
                print("Invalid date format. Use YYYY-MM-DD.")
                continue

            if end_date < start_date:
                print("End date must be on/after start date.")
                continue

            start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
            return start_dt, end_dt

        if choice == "4":
            start_raw = input("Start date (YYYY-MM-DD): ").strip()
            try:
                start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
            except ValueError:
                print("Invalid date format. Use YYYY-MM-DD.")
                continue

            start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            end_dt = datetime.now(timezone.utc)
            return start_dt, end_dt

        print("Invalid option.")

def parse_time_range_from_args(args):
    """
    Convert argparse args into (start_dt, end_dt) in UTC.
    Returns (None, None) for all-time.
    """
    if not getattr(args, "time_range", None) or args.time_range == "prompt":
        return None, None

    if args.time_range == "all":
        return None, None

    if args.time_range == "last":
        if args.days is None or args.days <= 0:
            raise ValueError("--days must be a positive integer when using --time-range last")
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=args.days)
        return start_dt, end_dt

    if args.time_range == "between":
        if not args.start_date or not args.end_date:
            raise ValueError("--start-date and --end-date are required when using --time-range between")
        try:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError("Dates must be in YYYY-MM-DD format") from e

        if end_date < start_date:
            raise ValueError("--end-date must be on/after --start-date")

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
        return start_dt, end_dt

    if args.time_range == "since":
        if not args.start_date:
            raise ValueError("--start-date is required when using --time-range since")
        try:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError("--start-date must be in YYYY-MM-DD format") from e

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.now(timezone.utc)
        return start_dt, end_dt

    raise ValueError(f"Unknown --time-range value: {args.time_range}")

# ------------------------
# Student fetching (paginated)
# ------------------------

def get_shared_collections(token):
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "user-agent": "Mozilla/5.0"
    }

    print("Fetching shared collections...")

    all_items = []
    page = 1

    while True:
        response = request_with_retries(
            f"{BASE_URL}/shares/shared-with-me",
            headers,
            params={
                "order_by": "created_at",
                "order_direction": "desc",
                "page": page,
                "per_page": PER_PAGE
            }
        )

        if response in (None, "TOKEN_EXPIRED", "NOT_FOUND"):
            return response

        data = response.json()
        if not data:
            break

        all_items.extend(data)

        if len(data) < PER_PAGE:
            break

        page += 1

    print(f"Found {len(all_items)} shared collections.")


    return all_items

def extract_students(shared_items):
    students = {}
    for item in shared_items:
        inviter = item.get("inviter")
        if not inviter or inviter.get("current_role") != "student":
            continue

        name = inviter["name"]
        portfolio_id = item["portfolio_id"]

        students.setdefault(name, {
            "student_id": inviter["id"],
            "portfolio_ids": set()
        })

        students[name]["portfolio_ids"].add(portfolio_id)

    return students

def get_students_from_section(token, section_id):
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "user-agent": "Mozilla/5.0"
    }

    print("Fetching students from section...")

    students = {}
    page = 1

    while True:
        response = request_with_retries(
            f"{BASE_URL}/dashboard",
            headers,
            params={
                "section_id": section_id,
                "page": page,
                "per_page": PER_PAGE
            }
        )

        if response in (None, "TOKEN_EXPIRED", "NOT_FOUND"):
            return response

        data = response.json()
        page_students = data.get("students", [])

        if not page_students:
            break

        for student in page_students:
            name = student["name"]
            portfolio_id = student.get("portfolio_id")
            share_type = student.get("share_type")

            students.setdefault(name, {
                "student_id": student["id"],
                "portfolio_ids": set(),
                "has_access": share_type is not None and share_type != "none"
            })

            if portfolio_id:
                students[name]["portfolio_ids"].add(portfolio_id)

        if len(page_students) < PER_PAGE:
            break

        page += 1

    print(f"Found {len(students)} students.")

    return students

# ------------------------
# Portfolio & feedback
# ------------------------

def get_goals(token, portfolio_id):
    headers = {"accept": "*/*", "authorization": f"Bearer {token}"}
    response = request_with_retries(
        f"{BASE_URL}/portfolios/{portfolio_id}/goals",
        headers,
        params={"page": 1, "per_page": PER_PAGE}
    )
    if response in (None, "TOKEN_EXPIRED", "NOT_FOUND"):
        return response
    return response.json()

def get_feedback(token, portfolio_id, goal_id):
    headers = {"accept": "*/*", "authorization": f"Bearer {token}"}
    feedback_items = []
    page = 1

    while True:
        response = request_with_retries(
            f"{BASE_URL}/portfolios/{portfolio_id}/goals/{goal_id}/feedback-items",
            headers,
            params={"page": page, "per_page": PER_PAGE}
        )

        if response == "NOT_FOUND":
            return []

        if response in (None, "TOKEN_EXPIRED"):
            return "TOKEN_EXPIRED"

        data = response.json()
        if not data:
            break

        feedback_items.extend(data)

        if len(data) < PER_PAGE:
            break

        page += 1

    return feedback_items

def resolve_level(evaluation):
    level_id = evaluation.get("level")
    if not level_id:
        return None

    for lvl in evaluation.get("level_set", []):
        if lvl["id"] == level_id:
            return lvl["label"]

    return None

def collect_results(token, student_name, student_data, include_reviewer=False, start_dt=None, end_dt=None):
    results = []

    for portfolio_id in student_data["portfolio_ids"]:
        goals = get_goals(token, portfolio_id)
        
        if goals == "TOKEN_EXPIRED":
            return "TOKEN_EXPIRED"
        
        if goals in (None, "NOT_FOUND"):
            print(f"  Warning: Cannot access evaluations for {student_name} (no permission or not found)")
            continue
        
        if not goals:
            continue

        for goal in goals:
            goal_id = goal["id"]
            goal_name = goal["name"]

            feedback_items = get_feedback(token, portfolio_id, goal_id)
            if feedback_items == "TOKEN_EXPIRED":
                return "TOKEN_EXPIRED"

            for item in feedback_items:
                if item.get("type") != "criterion_evaluation":
                    continue
                if item.get("role") == "self":
                    continue


                ts = pick_item_timestamp(item)
                if not in_time_range(ts, start_dt, end_dt):
                    continue

                evaluation = item.get("evaluation")
                if not evaluation:
                    continue

                level = resolve_level(evaluation)
                if level is None:
                    continue

                result = {
                    "student_name": student_name,
                    "goal_name": goal_name,
                    "evaluation": level
                }

                if include_reviewer:
                    reviewer = evaluation.get("reviewer", {})
                    result["reviewer_name"] = reviewer.get("name", "Unknown")

                results.append(result)

    return results

# ------------------------
# CSV Export (; separator)
# ------------------------

def sort_goals(goals):
    """Sort goals according to GOAL_ORDER (case-insensitive), with unspecified goals at the end."""
    def sort_key(goal):
        goal_lower = goal.lower()
        try:
            return (0, GOAL_ORDER_LOWER.index(goal_lower))
        except ValueError:
            return (1, goal_lower)
    return sorted(goals, key=sort_key)

def export_csv_wide(results, include_reviewer=False):
    if not results:
        print("No data to export.")
        return

    all_goals = sort_goals(set(r["goal_name"] for r in results))
    students = {}

    for r in results:
        s = r["student_name"]
        g = r["goal_name"]

        students.setdefault(s, {goal: "" for goal in all_goals})

        eval_str = r["evaluation"]
        if include_reviewer:
            eval_str += f" ({r['reviewer_name']})"

        if students[s][g]:
            students[s][g] += f", {eval_str}"
        else:
            students[s][g] = eval_str

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Studentname"] + all_goals)

        for student, goal_data in students.items():
            writer.writerow([student] + [goal_data[g] for g in all_goals])

    print("CSV exported to results.csv")

# ------------------------
# Main program
# ------------------------

def build_arg_parser():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--time-range",
        choices=["prompt", "all", "last", "between", "since"],
        default="prompt",
        help="Filter evaluations by time range. 'prompt' asks interactively.",
    )
    parser.add_argument("--days", type=int, default=None, help="Used with --time-range last")
    parser.add_argument("--start-date", type=str, default=None, help="Used with --time-range between (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=None, help="Used with --time-range between (YYYY-MM-DD)")
    return parser

def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        start_dt, end_dt = parse_time_range_from_args(args)
    except ValueError as e:
        print(f"Invalid time range arguments: {e}")
        return 2

    try:
        token = get_bearer_token()

        while True:
            # ---- Student fetch menu ----
            while True:
                print("\nChoose student fetching method:")
                print("1) All students with shared collection")
                print("2) Students from section (fetched from API)")
                print("3) Students from custom section ID")
                print("q) Quit")

                fetch_choice = input("Choice: ").strip().lower()

                if fetch_choice == "q":
                    print("Exiting gracefully. Goodbye!")
                    return 0

                if fetch_choice == "1":
                    shared = get_shared_collections(token)
                    if shared == "TOKEN_EXPIRED":
                        print("Token expired, please enter a new one.")
                        token = get_bearer_token()
                        continue
                    if shared is None:
                        print("Failed to fetch shared collections. Please try again.")
                        continue
                    students = extract_students(shared)
                    break

                if fetch_choice == "2":
                    section_id = select_section(token)
                    if section_id == "TOKEN_EXPIRED":
                        print("Token expired, please enter a new one.")
                        token = get_bearer_token()
                        continue
                    if section_id is None:
                        continue
                    students = get_students_from_section(token, section_id)
                    if students == "TOKEN_EXPIRED":
                        print("Token expired, please enter a new one.")
                        token = get_bearer_token()
                        continue
                    if students is None:
                        print("Failed to fetch students. Please try again.")
                        continue
                    break

                if fetch_choice == "3":
                    section_id = input("Enter section_id: ").strip()
                    students = get_students_from_section(token, section_id)
                    if students == "TOKEN_EXPIRED":
                        print("Token expired, please enter a new one.")
                        token = get_bearer_token()
                        continue
                    if students is None:
                        print("Failed to fetch students. Please try again.")
                        continue
                    break

                print("Invalid option.")

            if not students:
                print("No students found.")
                continue

            if args.time_range == "prompt":
                start_dt, end_dt = ask_time_range()
            print(f"\nActive time filter: {describe_time_range(start_dt, end_dt)}")

            print(f"\nFound {len(students)} students:")
            for name in sorted(students.keys()):
                if "has_access" in students[name] and not students[name]["has_access"]:
                    print(f"- {name} (Geen Toegang)")
                else:
                    print(f"- {name}")

            # ---- Output menu ----
            print("\nChoose output:")
            print("1) Single student")
            print("2) All students (CSV)")
            print("m) Main menu")

            choice = input("Choice: ").strip().lower()

            if choice == "m":
                continue

            if choice == "1":
                name = input("Enter student name exactly as shown: ").strip()
                if name not in students:
                    print("Student not found.")
                    continue

                print("\nInclude reviewer names?")
                print("1) Yes")
                print("2) No")
                reviewer_choice = input("Choice: ").strip()
                include_reviewer = reviewer_choice == "1"

                results = collect_results(token, name, students[name], include_reviewer, start_dt, end_dt)
                if results == "TOKEN_EXPIRED":
                    print("Token expired, please enter a new one.")
                    token = get_bearer_token()
                    continue

                if not results:
                    print(f"\nNo evaluations found for {name}")
                    continue

                print(f"\n{name}")
                goals = {}
                for r in results:
                    goal = r["goal_name"]
                    if include_reviewer:
                        eval_str = f"{r['evaluation']} ({r['reviewer_name']})"
                    else:
                        eval_str = r["evaluation"]
                    goals.setdefault(goal, []).append(eval_str)

                sorted_goals = sort_goals(goals.keys())
                for goal in sorted_goals:
                    print(f"{goal}: {', '.join(goals[goal])}")

            elif choice == "2":
                print("\nInclude reviewer names?")
                print("1) Yes")
                print("2) No")
                reviewer_choice = input("Choice: ").strip()
                include_reviewer = reviewer_choice == "1"

                all_results = []
                total = len(students)
                processed = 0

                for name, data in students.items():
                    processed += 1
                    print(f"Processing {name}... ({processed}/{total})")
                    res = collect_results(token, name, data, include_reviewer, start_dt, end_dt)
                    if res == "TOKEN_EXPIRED":
                        print("Token expired, please enter a new one.")
                        token = get_bearer_token()
                        break
                    if res:
                        all_results.extend(res)
                else:
                    if all_results:
                        export_csv_wide(all_results, include_reviewer)
                    else:
                        print("\nNo evaluation data found for any student.")

            else:
                print("Invalid option.")

    except KeyboardInterrupt:
        print("\nInterrupted. Exiting gracefully. Goodbye!")
        return 0

    return 0

if __name__ == "__main__":
    main()
