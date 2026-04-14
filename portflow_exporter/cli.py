from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import api
from .time_range import TimeRange, range_between_dates, range_last_days, range_since_date


def _try_questionary():
    try:
        # Dynamic import so the minimal PyInstaller build does not bundle TUI deps.
        return importlib.import_module("questionary")
    except Exception:
        return None


@dataclass(frozen=True)
class CliChoice:
    label: str
    value: str


def _default_token_cache_path() -> Path:
    # Use a per-user roaming directory on Windows when available.
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "PortflowExport" / "token.txt"
    return Path.home() / ".portflowexport" / "token.txt"


def _read_token_file(path: Path) -> Optional[str]:
    try:
        if not path.exists():
            return None
        token = path.read_text(encoding="utf-8").strip()
        return token or None
    except Exception:
        return None


def _write_token_file(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token.strip() + "\n", encoding="utf-8")


def prompt_token(
    *,
    provided_token: Optional[str] = None,
    allow_env: bool = True,
    env_var: str = "PORTFLOW_BEARER_TOKEN",
    token_file: Optional[str] = None,
    allow_cache_file: bool = True,
    save: bool = False,
) -> str:
    # 1) explicit CLI-provided token wins
    if provided_token:
        token = provided_token.strip()
        if save:
            _write_token_file(Path(token_file) if token_file else _default_token_cache_path(), token)
        return token

    # 2) environment variable
    if allow_env:
        env_token = os.environ.get(env_var)
        if env_token and env_token.strip():
            token = env_token.strip()
            if save:
                _write_token_file(Path(token_file) if token_file else _default_token_cache_path(), token)
            return token

    # 3) cached token file
    if allow_cache_file:
        cache_path = Path(token_file) if token_file else _default_token_cache_path()
        cached = _read_token_file(cache_path)
        if cached:
            return cached

    # 4) prompt user
    q = _try_questionary()
    if q:
        raw = (
            q.text(
                "Enter Bearer token (or paste 'Copy as cURL' / an Authorization header):",
            ).ask()
            or ""
        )
    else:
        raw = input("Enter Bearer token (or paste cURL / Authorization header): ").strip()

    token = _extract_bearer_from_text(raw) or raw.strip()

    if save and token:
        _write_token_file(Path(token_file) if token_file else _default_token_cache_path(), token)
    return token


def _extract_bearer_from_text(text: str) -> Optional[str]:
    """
    Extract a bearer token from:
    - Authorization header lines
    - "Copy as cURL" commands (any shell), where headers contain authorization
    """
    if not text:
        return None

    # Fast path: if user pasted just the header or token line
    m = re.search(r"authorization\s*:\s*bearer\s+([A-Za-z0-9\-\._~\+\/]+=*)", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Sometimes headers are quoted/escaped; allow any non-quote whitespace up to end-quote/line
    m = re.search(r"authorization\s*:\s*bearer\s+([^\s\"\'\^]+)", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Some users paste: "Bearer xxx"
    m = re.search(r"\bbearer\s+([A-Za-z0-9\-\._~\+\/]+=*)\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return None




def _select(question: str, choices: List[CliChoice]) -> str:
    q = _try_questionary()
    if q:
        return q.select(question, choices=[c.label for c in choices]).ask()

    print(f"\n{question}")
    for idx, c in enumerate(choices, 1):
        print(f"{idx}) {c.label}")
    while True:
        raw = input("Choice: ").strip()
        if raw.isdigit():
            i = int(raw) - 1
            if 0 <= i < len(choices):
                return choices[i].label
        print("Invalid option.")


def _confirm(question: str, default: bool = False) -> bool:
    q = _try_questionary()
    if q:
        return bool(q.confirm(question, default=default).ask())
    raw = input(f"{question} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "1", "true")


def categorize_sections(sections: List[dict]) -> Dict[str, List[dict]]:
    categories: Dict[str, List[dict]] = {"Coaches": [], "Gildes": [], "Misc": []}
    for section in sections:
        name = section["name"]
        if name.startswith("Coach "):
            categories["Coaches"].append(section)
        elif name.startswith("Gilde "):
            categories["Gildes"].append(section)
        else:
            categories["Misc"].append(section)
    for category in categories.values():
        category.sort(key=lambda x: x["name"])
    return categories


def select_section_id(token: str) -> Optional[str]:
    sections = api.get_all_sections(token, use_cache=True)
    if sections == api.TokenExpired:
        return api.TokenExpired  # type: ignore[return-value]
    if not sections:
        print("No sections available.")
        return None

    categories = categorize_sections(sections)  # type: ignore[arg-type]
    available = [(name, items) for name, items in categories.items() if items]
    if not available:
        print("No sections available.")
        return None

    cat_label = _select(
        "Select category",
        [CliChoice(f"{name} ({len(items)} sections)", name) for name, items in available] + [CliChoice("Back", "__back")],
    )
    if cat_label == "Back":
        return None

    cat_name = next((c.value for c in [CliChoice(f"{name} ({len(items)} sections)", name) for name, items in available] if c.label == cat_label), None)
    if not cat_name:
        # fallback mapping by prefix
        cat_name = cat_label.split(" (", 1)[0]

    section_list = categories.get(cat_name, [])
    sec_label = _select(
        f"Select section from {cat_name}",
        [CliChoice(s["name"], str(s["id"])) for s in section_list] + [CliChoice("Back", "__back")],
    )
    if sec_label == "Back":
        return None

    # map label->id
    for s in section_list:
        if s["name"] == sec_label:
            return str(s["id"])
    return None


def prompt_time_range_interactive() -> TimeRange:
    mode = _select(
        "Select time range",
        [
            CliChoice("All time", "all"),
            CliChoice("Last N days", "last"),
            CliChoice("Between dates (YYYY-MM-DD to YYYY-MM-DD)", "between"),
            CliChoice("From date until today (YYYY-MM-DD to today)", "since"),
        ],
    )

    if mode.startswith("All time"):
        return TimeRange()

    if mode.startswith("Last"):
        while True:
            raw = input("Enter N (days): ").strip()
            if raw.isdigit() and int(raw) > 0:
                return range_last_days(int(raw))
            print("Invalid number of days.")

    if mode.startswith("Between"):
        while True:
            s = input("Start date (YYYY-MM-DD): ").strip()
            e = input("End date (YYYY-MM-DD): ").strip()
            try:
                return range_between_dates(s, e)
            except Exception as ex:
                print(f"Invalid date range: {ex}")

    while True:
        s = input("Start date (YYYY-MM-DD): ").strip()
        try:
            return range_since_date(s)
        except Exception as ex:
            print(f"Invalid date: {ex}")


def choose_student_fetch_method() -> str:
    return _select(
        "Choose student fetching method",
        [
            CliChoice("All students with shared collection", "shared"),
            CliChoice("Students from section (select from API)", "section_select"),
            CliChoice("Students from custom section ID", "section_custom"),
            CliChoice("Quit", "quit"),
        ],
    )


def choose_output_mode() -> str:
    return _select(
        "Choose output",
        [
            CliChoice("Single student", "single"),
            CliChoice("All students (CSV)", "csv"),
            CliChoice("Main menu", "main"),
        ],
    )


def prompt_student_name(students: Dict[str, dict]) -> Optional[str]:
    names = sorted(students.keys())
    q = _try_questionary()
    if q:
        picked = q.autocomplete("Student:", choices=names, ignore_case=True).ask()
        return picked if picked in students else None

    raw = input("Enter student name exactly as shown: ").strip()
    return raw if raw in students else None


def prompt_include_reviewer() -> bool:
    return _confirm("Include reviewer names?", default=False)

