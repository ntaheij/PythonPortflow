from __future__ import annotations

from typing import Dict, List, Union

from . import api
from .time_range import TimeRange, in_time_range, pick_evaluation_timestamp


def extract_students(shared_items: List[dict]) -> Dict[str, dict]:
    students: Dict[str, dict] = {}
    for item in shared_items:
        inviter = item.get("inviter")
        if not inviter or inviter.get("current_role") != "student":
            continue

        name = inviter["name"]
        portfolio_id = item["portfolio_id"]

        students.setdefault(name, {"student_id": inviter["id"], "portfolio_ids": set()})
        students[name]["portfolio_ids"].add(portfolio_id)

    return students


def resolve_level(evaluation: dict):
    level_id = evaluation.get("level")
    if not level_id:
        return None

    for lvl in evaluation.get("level_set", []):
        if lvl["id"] == level_id:
            return lvl["label"]

    return None


def collect_results(
    token: str,
    student_name: str,
    student_data: dict,
    include_reviewer: bool = False,
    time_range: TimeRange = TimeRange(),
) -> Union[List[dict], str]:
    results: List[dict] = []

    for portfolio_id in student_data["portfolio_ids"]:
        goals = api.get_goals(token, portfolio_id)

        if goals == api.TokenExpired:
            return api.TokenExpired

        if goals in (None, api.NotFound):
            print(f"  Warning: Cannot access evaluations for {student_name} (no permission or not found)")
            continue

        if not goals:
            continue

        for goal in goals:
            goal_id = goal["id"]
            goal_name = goal["name"]

            feedback_items = api.get_feedback(token, portfolio_id, goal_id)
            if feedback_items == api.TokenExpired:
                return api.TokenExpired

            for item in feedback_items:
                if item.get("type") != "criterion_evaluation":
                    continue
                if item.get("role") == "self":
                    continue

                ts = pick_evaluation_timestamp(item)
                if not in_time_range(ts, time_range):
                    continue

                evaluation = item.get("evaluation")
                if not evaluation:
                    continue

                level = resolve_level(evaluation)
                if level is None:
                    continue

                result = {"student_name": student_name, "goal_name": goal_name, "evaluation": level}
                if include_reviewer:
                    reviewer = evaluation.get("reviewer", {})
                    result["reviewer_name"] = reviewer.get("name", "Unknown")

                results.append(result)

    return results

