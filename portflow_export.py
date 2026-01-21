import requests
import csv
import time
import sys

BASE_URL = "https://portfolio.drieam.app/api/v1"
PER_PAGE = 200

# Session cache
sections_cache = None

# Desired goal order
GOAL_ORDER = [
    "Overzicht creëren",
    "Kritisch Oordelen",
    "Juiste Kennis Ontwikkelen",
    "Kwalitatief Product Maken",
    "Plannen",
    "Boodschap delen",
    "Samenwerken",
    "Flexibel opstellen",
    "Pro-actief handelen",
    "Reflecteren"
]

# ------------------------
# Helper functions
# ------------------------

def get_bearer_token():
    return input("Enter Bearer token: ").strip()

def get_all_sections(token, use_cache=True):
    """Fetch all sections from the API with pagination."""
    global sections_cache
    
    if use_cache and sections_cache is not None:
        print("Using cached sections...")
        return sections_cache
    
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "user-agent": "Mozilla/5.0"
    }
    
    all_sections = []
    page = 1
    
    print("Fetching sections...")
    
    while True:
        response = request_with_retries(
            f"{BASE_URL}/lms/sections",
            headers,
            params={"page": page}
        )
        
        if response in (None, "TOKEN_EXPIRED", "NOT_FOUND"):
            return response
        
        data = response.json()
        
        if not data:
            break
        
        all_sections.extend(data)
        
        # If we got less than a full page, we're done
        if len(data) < 10:  # API default per page appears to be 10
            break
        
        page += 1
    
    print(f"Found {len(all_sections)} sections.")
    sections_cache = all_sections
    return all_sections

def categorize_sections(sections):
    """Organize sections into categories (Coaches, Gildes, Misc)."""
    categories = {
        "Coaches": [],
        "Gildes": [],
        "Misc": []
    }
    
    for section in sections:
        name = section["name"]
        if name.startswith("Coach "):
            categories["Coaches"].append(section)
        elif name.startswith("Gilde "):
            categories["Gildes"].append(section)
        else:
            categories["Misc"].append(section)
    
    # Sort each category by name
    for category in categories.values():
        category.sort(key=lambda x: x["name"])
    
    return categories

def select_section(token):
    """Display section categories and let user select a specific section."""
    sections = get_all_sections(token, use_cache=True)
    
    if sections == "TOKEN_EXPIRED":
        return "TOKEN_EXPIRED"
    
    if not sections:
        print("No sections available.")
        return None
    
    categories = categorize_sections(sections)
    
    print("\nSelect category:")
    category_names = [name for name, items in categories.items() if items]
    for idx, category in enumerate(category_names, 1):
        print(f"{idx}) {category} ({len(categories[category])} sections)")
    print("b) Back")
    
    while True:
        cat_choice = input("Choice: ").strip().lower()
        
        if cat_choice == "b":
            return None
        
        if cat_choice.isdigit():
            cat_idx = int(cat_choice) - 1
            if 0 <= cat_idx < len(category_names):
                category = category_names[cat_idx]
                break
        
        print("Invalid option.")
    
    section_list = categories[category]
    print(f"\nSelect section from {category}:")
    for idx, section in enumerate(section_list, 1):
        print(f"{idx}) {section['name']}")
    print("b) Back")
    
    while True:
        sec_choice = input("Choice: ").strip().lower()
        
        if sec_choice == "b":
            return None
        
        if sec_choice.isdigit():
            sec_idx = int(sec_choice) - 1
            if 0 <= sec_idx < len(section_list):
                return section_list[sec_idx]["id"]
        
        print("Invalid option.")

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

def collect_results(token, student_name, student_data, include_reviewer=False):
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
    """Sort goals according to GOAL_ORDER, with unspecified goals at the end."""
    def sort_key(goal):
        try:
            return (0, GOAL_ORDER.index(goal))
        except ValueError:
            return (1, goal)
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
                sys.exit(0)

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

            results = collect_results(token, name, students[name], include_reviewer)
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
                res = collect_results(token, name, data, include_reviewer)
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
    sys.exit(0)
