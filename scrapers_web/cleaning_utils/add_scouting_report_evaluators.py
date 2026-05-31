from __future__ import annotations

from datetime import datetime
from html import unescape
from pathlib import Path
import re
import shutil

import duckdb


def find_project_root() -> Path:
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if parent.name == "uiuc_proj":
            return parent
    raise RuntimeError("Could not find uiuc_proj in this script's parent folders.")


PROJECT_ROOT = find_project_root()
DB_PATH = PROJECT_ROOT / "scrapers_web" / "outputs" / "actual_db_files" / "hs_complete.db"
BACKUP_DIR = PROJECT_ROOT / "scrapers_web" / "outputs" / "actual_db_files" / "backups"
CACHE_DIR = PROJECT_ROOT / "scrapers_web" / "cache" / "hs"

TABLE_NAME = "hs_complete"
NAME_COL = "scouting_report_evaluator_name"
POSITION_COL = "scouting_report_evaluator_position"


def clean_html_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def extract_scouting_section(html: str) -> str | None:
    start = re.search(
        r'<section[^>]+class="[^"]*\bscouting-report\b[^"]*"[^>]*>',
        html,
        flags=re.IGNORECASE,
    )
    if not start:
        return None

    # The pages are minified and this section precedes the timeline admin link.
    # Keep the slice narrow to avoid matching unrelated evaluator-like blocks.
    tail = html[start.start() :]
    end_match = re.search(
        r'<a[^>]+class="[^"]*timeline-comp__admin-link',
        tail,
        flags=re.IGNORECASE,
    )
    if end_match:
        return tail[: end_match.start()]
    return tail[:15000]


def extract_evaluator(html: str) -> tuple[str | None, str | None]:
    section = extract_scouting_section(html)
    if not section:
        return None, None

    evaluator_match = re.search(
        r'<div[^>]+class="[^"]*\bevaluator\b[^"]*"[^>]*>(.*?)</div>',
        section,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not evaluator_match:
        return None, None

    evaluator_html = evaluator_match.group(1)
    name_match = re.search(
        r'<b[^>]+class="[^"]*\btext\b[^"]*"[^>]*>(.*?)</b>',
        evaluator_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    position_match = re.search(
        r'<span[^>]+class="[^"]*\buppercase\b[^"]*"[^>]*>(.*?)</span>',
        evaluator_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return clean_html_text(name_match.group(1) if name_match else None), clean_html_text(
        position_match.group(1) if position_match else None
    )


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{DB_PATH.stem}.backup_before_scouting_evaluators_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    print(f"Backup created: {backup_path}", flush=True)

    con = duckdb.connect(str(DB_PATH))
    try:
        existing_cols = [row[0] for row in con.execute(f"DESCRIBE {TABLE_NAME}").fetchall()]
        if NAME_COL not in existing_cols:
            con.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {NAME_COL} VARCHAR")
        if POSITION_COL not in existing_cols:
            con.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {POSITION_COL} VARCHAR")

        report_rows = con.execute(f"""
            SELECT year, player_key, full_name
            FROM {TABLE_NAME}
            WHERE has_scouting_report = TRUE
              AND scouting_report IS NOT NULL
              AND TRIM(scouting_report) <> ''
            ORDER BY year, player_key, full_name
        """).fetchall()

        extracted_rows: list[tuple[int, int, str, str | None, str | None, str]] = []
        missing_html = 0
        for year, player_key, full_name in report_rows:
            html_path = CACHE_DIR / str(year) / "profiles" / f"{player_key}.html"
            if not html_path.exists():
                missing_html += 1
                extracted_rows.append((year, player_key, full_name, None, None, str(html_path)))
                continue

            html = html_path.read_text(errors="ignore")
            evaluator_name, evaluator_position = extract_evaluator(html)
            extracted_rows.append(
                (
                    year,
                    player_key,
                    full_name,
                    evaluator_name,
                    evaluator_position,
                    str(html_path),
                )
            )

        con.execute("DROP TABLE IF EXISTS scouting_report_evaluator_parse")
        con.execute("""
            CREATE TABLE scouting_report_evaluator_parse (
                year BIGINT,
                player_key BIGINT,
                full_name VARCHAR,
                scouting_report_evaluator_name VARCHAR,
                scouting_report_evaluator_position VARCHAR,
                html_path VARCHAR
            )
        """)
        con.executemany(
            """
            INSERT INTO scouting_report_evaluator_parse
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            extracted_rows,
        )

        con.execute(f"""
            UPDATE {TABLE_NAME} AS h
            SET
                {NAME_COL} = p.scouting_report_evaluator_name,
                {POSITION_COL} = p.scouting_report_evaluator_position
            FROM scouting_report_evaluator_parse AS p
            WHERE h.year = p.year
              AND h.player_key = p.player_key
              AND h.full_name = p.full_name
        """)

        total_reports = len(report_rows)
        parsed_name_count = con.execute("""
            SELECT COUNT(*)
            FROM scouting_report_evaluator_parse
            WHERE scouting_report_evaluator_name IS NOT NULL
        """).fetchone()[0]
        parsed_position_count = con.execute("""
            SELECT COUNT(*)
            FROM scouting_report_evaluator_parse
            WHERE scouting_report_evaluator_position IS NOT NULL
        """).fetchone()[0]
        updated_name_count = con.execute(f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE has_scouting_report = TRUE
              AND {NAME_COL} IS NOT NULL
        """).fetchone()[0]
        updated_position_count = con.execute(f"""
            SELECT COUNT(*)
            FROM {TABLE_NAME}
            WHERE has_scouting_report = TRUE
              AND {POSITION_COL} IS NOT NULL
        """).fetchone()[0]

        print(f"Textual scouting report rows: {total_reports:,}", flush=True)
        print(f"Missing cached HTML files: {missing_html:,}", flush=True)
        print(f"Parsed evaluator names: {parsed_name_count:,}", flush=True)
        print(f"Parsed evaluator positions: {parsed_position_count:,}", flush=True)
        print(f"Updated rows with evaluator names: {updated_name_count:,}", flush=True)
        print(f"Updated rows with evaluator positions: {updated_position_count:,}", flush=True)

    finally:
        con.close()


if __name__ == "__main__":
    main()
