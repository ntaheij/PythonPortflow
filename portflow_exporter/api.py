from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Union

import requests

from .constants import BASE_URL, PER_PAGE


TokenExpired = "TOKEN_EXPIRED"
NotFound = "NOT_FOUND"


def request_with_retries(
    url: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    max_attempts: int = 3,
) -> Union[requests.Response, str, None]:
    attempt = 0
    while attempt < max_attempts:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 401:
                return TokenExpired

            if response.status_code == 404:
                return NotFound

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


def get_all_sections(token: str, use_cache: bool = True, _cache: dict = {}) -> Union[List[dict], str, None]:
    if use_cache and "sections" in _cache:
        print("Using cached sections...")
        return _cache["sections"]

    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "user-agent": "Mozilla/5.0",
    }

    all_sections: List[dict] = []
    page = 1

    print("Fetching sections...")
    while True:
        response = request_with_retries(f"{BASE_URL}/lms/sections", headers, params={"page": page})
        if response in (None, TokenExpired, NotFound):
            return response

        data = response.json()
        if not data:
            break

        all_sections.extend(data)

        if len(data) < 10:
            break
        page += 1

    print(f"Found {len(all_sections)} sections.")
    _cache["sections"] = all_sections
    return all_sections


def get_shared_collections(token: str) -> Union[List[dict], str, None]:
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "user-agent": "Mozilla/5.0",
    }

    print("Fetching shared collections...")
    all_items: List[dict] = []
    page = 1
    seen_ids: set = set()

    while True:
        response = request_with_retries(
            f"{BASE_URL}/shares/shared-with-me",
            headers,
            params={
                "order_by": "created_at",
                "order_direction": "desc",
                "page": page,
                "per_page": PER_PAGE,
            },
        )
        if response in (None, TokenExpired, NotFound):
            return response

        data = response.json()
        if not data:
            break

        # Avoid premature termination if the API ignores per_page, and avoid infinite loops
        new_count = 0
        for item in data:
            item_id = item.get("id") if isinstance(item, dict) else None
            if item_id is None or item_id not in seen_ids:
                all_items.append(item)
                new_count += 1
                if item_id is not None:
                    seen_ids.add(item_id)

        if new_count == 0:
            break
        page += 1

    print(f"Found {len(all_items)} shared collections.")
    return all_items


def get_students_from_section(token: str, section_id: str) -> Union[dict, str, None]:
    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {token}",
        "user-agent": "Mozilla/5.0",
    }

    print("Fetching students from section...")
    students: dict = {}
    page = 1

    while True:
        response = request_with_retries(
            f"{BASE_URL}/dashboard",
            headers,
            params={"section_id": section_id, "page": page, "per_page": PER_PAGE},
        )
        if response in (None, TokenExpired, NotFound):
            return response

        data = response.json()
        page_students = data.get("students", [])
        if not page_students:
            break

        for student in page_students:
            name = student["name"]
            portfolio_id = student.get("portfolio_id")
            share_type = student.get("share_type")

            students.setdefault(
                name,
                {
                    "student_id": student["id"],
                    "portfolio_ids": set(),
                    "has_access": share_type is not None and share_type != "none",
                },
            )
            if portfolio_id:
                students[name]["portfolio_ids"].add(portfolio_id)

        page += 1

    print(f"Found {len(students)} students.")
    return students


def get_goals(token: str, portfolio_id: str) -> Union[List[dict], str, None]:
    headers = {"accept": "*/*", "authorization": f"Bearer {token}"}
    response = request_with_retries(
        f"{BASE_URL}/portfolios/{portfolio_id}/goals",
        headers,
        params={"page": 1, "per_page": PER_PAGE},
    )
    if response in (None, TokenExpired, NotFound):
        return response
    return response.json()


def get_feedback(token: str, portfolio_id: str, goal_id: str) -> Union[List[dict], str]:
    headers = {"accept": "*/*", "authorization": f"Bearer {token}"}
    feedback_items: List[dict] = []
    page = 1
    seen_ids: set = set()

    while True:
        response = request_with_retries(
            f"{BASE_URL}/portfolios/{portfolio_id}/goals/{goal_id}/feedback-items",
            headers,
            params={"page": page, "per_page": PER_PAGE},
        )

        if response == NotFound:
            return []

        if response in (None, TokenExpired):
            return TokenExpired

        data = response.json()
        if not data:
            break

        new_count = 0
        for item in data:
            item_id = item.get("id") if isinstance(item, dict) else None
            if item_id is None or item_id not in seen_ids:
                feedback_items.append(item)
                new_count += 1
                if item_id is not None:
                    seen_ids.add(item_id)

        if new_count == 0:
            break
        page += 1

    return feedback_items

