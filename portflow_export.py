import requests
import csv
import time
import sys

BASE_URL = "https://portfolio.drieam.app/api/v1"
PER_PAGE = 200

# ------------------------
# Helper functions
# ------------------------

def get_bearer_token():
    return input("Enter Bearer token: ").strip()

def request_with_retries(url, headers, params=None, max_attempts=3):
    attempt = 0
    while attempt < max_attempts:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 401:
                return "TOKEN_EXPIRED"

            if response.status_code == 404:
                return "NOT_FOUND"

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            attempt += 1
            print(f"Request failed ({attempt}/{max_attempts}): {e}")

            if attempt < max_attempts:
                print("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print("3 failed attempts. Waiting 60 seconds...")
                time.sleep(60)
                return None

# ------------------------
# Student fetching (paginated)
# ------------------------

def get_shared_collections(token):
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "user-agent": "Mozilla/5.0"
    }

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

        if response in (None, "TOKEN_EXPIRED"):
            return response

        data = response.json()
        if not data:
            break

        all_items.extend(data)

        if len(data) < PER_PAGE:
            break

        page += 1

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

        if response in (None, "TOKEN_EXPIRED"):
            return response

        data = response.json()
        page_students = data.get("students", [])

        if not page_students:
            break

        for student in page_students:
            name = student["name"]
            portfolio_id = student["portfolio_id"]

            students.setdefault(name, {
                "student_id": student["id"],
                "portfolio_ids": set()
            })

            students[name]["portfolio_ids"].add(portfolio_id)

        if len(page_students) < PER_PAGE:
            break

        page += 1

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
    if response in (None, "TOKEN_EXPIRED"):
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

        if response is None:
            break

        if response == "TOKEN_EXPIRED":
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

def collect_results(token, student_name, student_data):
    results = []

    for portfolio_id in student_data["portfolio_ids"]:
        goals = get_goals(token, portfolio_id)
        if goals == "TOKEN_EXPIRED":
            return "TOKEN_EXPIRED"

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

                evaluation = item.get("evaluation")
                if not evaluation:
                    continue

                level = resolve_level(evaluation)
                if level is None:
                    continue

                results.append({
                    "student_name": student_name,
                    "goal_name": goal_name,
                    "evaluation": level
                })

    return results

# ------------------------
# CSV Export (; separator)
# ------------------------

def export_csv_wide(results):
    if not results:
        print("No data to export.")
        return

    all_goals = sorted(set(r["goal_name"] for r in results))
    students = {}

    for r in results:
        s = r["student_name"]
        g = r["goal_name"]

        students.setdefault(s, {goal: "" for goal in all_goals})

        if students[s][g]:
            students[s][g] += f", {r['evaluation']}"
        else:
            students[s][g] = r["evaluation"]

    with open("results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Studentname"] + all_goals)

        for student, goal_data in students.items():
            writer.writerow([student] + [goal_data[g] for g in all_goals])

    print("CSV exported to results.csv")

# ------------------------
# Main program
# ------------------------

try:
    token = get_bearer_token()

    while True:
        # ---- Student fetch menu ----
        while True:
            print("\nChoose student fetching method:")
            print("1) All students with shared collection")
            print("2) Students from section (coachingsdashboard)")
            print("q) Quit")

            fetch_choice = input("Choice: ").strip().lower()

            if fetch_choice == "q":
                print("Exiting gracefully. Goodbye!")
                sys.exit(0)

            if fetch_choice == "1":
                shared = get_shared_collections(token)
                if shared == "TOKEN_EXPIRED":
                    print("Token expired, please enter a new one.")
                    token = get_bearer_token()
                    continue
                students = extract_students(shared)
                break

            if fetch_choice == "2":
                section_id = input("Enter section_id: ").strip()
                students = get_students_from_section(token, section_id)
                if students == "TOKEN_EXPIRED":
                    print("Token expired, please enter a new one.")
                    token = get_bearer_token()
                    continue
                break

            print("Invalid option.")

        if not students:
            print("No students found.")
            continue

        print("\nStudents:")
        for name in students:
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

            results = collect_results(token, name, students[name])
            if results == "TOKEN_EXPIRED":
                print("Token expired, please enter a new one.")
                token = get_bearer_token()
                continue

            print(f"\n{name}")
            goals = {}
            for r in results:
                goals.setdefault(r["goal_name"], []).append(r["evaluation"])

            for goal, evals in goals.items():
                print(f"{goal}: {', '.join(evals)}")

        elif choice == "2":
            all_results = []
            for name, data in students.items():
                print(f"Processing {name}...")
                res = collect_results(token, name, data)
                if res == "TOKEN_EXPIRED":
                    print("Token expired, please enter a new one.")
                    token = get_bearer_token()
                    break
                all_results.extend(res)
            else:
                export_csv_wide(all_results)

        else:
            print("Invalid option.")

except KeyboardInterrupt:
    print("\nInterrupted. Exiting gracefully. Goodbye!")
    sys.exit(0)
