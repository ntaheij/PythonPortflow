from __future__ import annotations

import csv
from typing import Iterable, List

from .constants import GOAL_ORDER_LOWER


def sort_goals(goals: Iterable[str]) -> List[str]:
    def sort_key(goal: str):
        goal_lower = goal.lower()
        try:
            return (0, GOAL_ORDER_LOWER.index(goal_lower))
        except ValueError:
            return (1, goal_lower)

    return sorted(set(goals), key=sort_key)


def export_csv_wide(results: list[dict], include_reviewer: bool = False, path: str = "results.csv") -> None:
    if not results:
        print("No data to export.")
        return

    all_goals = sort_goals(r["goal_name"] for r in results)
    students: dict = {}

    for r in results:
        s = r["student_name"]
        g = r["goal_name"]
        students.setdefault(s, {goal: "" for goal in all_goals})

        eval_str = r["evaluation"]
        if include_reviewer:
            eval_str += f" ({r.get('reviewer_name', 'Unknown')})"

        if students[s][g]:
            students[s][g] += f", {eval_str}"
        else:
            students[s][g] = eval_str

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Studentname"] + all_goals)
        for student, goal_data in students.items():
            writer.writerow([student] + [goal_data[g] for g in all_goals])

    print(f"CSV exported to {path}")

