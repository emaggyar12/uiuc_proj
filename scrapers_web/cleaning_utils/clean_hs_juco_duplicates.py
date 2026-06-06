from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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

ACTUAL_DB_DIR = (
    PROJECT_ROOT / "scrapers_web" / "outputs" / "actual_db_files"
)
HS_DB_PATH = ACTUAL_DB_DIR / "hs_recruits_247_2010_2026_combined_complete.db"
JUCO_DB_PATH = ACTUAL_DB_DIR / "juco_rec.db"
BACKUP_DIR = ACTUAL_DB_DIR / "backups"
CACHE_DIR = PROJECT_ROOT / "scrapers_web" / "cache" / "hs"

HS_TABLE = "hs_recruits_enriched"
JUCO_TABLE = "juco_recruits"
OLD_DUP_TABLE = "old_hs_duplicates"
JUCO_AUDIT_TABLE = "juco_detection_audit"


@dataclass(frozen=True)
class JucoDetection:
    year: int
    player_key: int
    full_name: str
    is_confirmed_juco: bool
    evidence: str
    class_years: str
    html_path: str


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def read_html(year: int, player_key: int) -> tuple[str, Path]:
    html_path = CACHE_DIR / str(year) / "profiles" / f"{player_key}.html"
    if not html_path.exists():
        return "", html_path
    return html_path.read_text(errors="ignore"), html_path


def prospect_section(html: str) -> str:
    index = html.lower().find("as-a-prospect")
    if index < 0:
        return ""
    return html[index : index + 12000]


def detect_juco_for_row(year: int, player_key: int, full_name: str) -> JucoDetection:
    html, html_path = read_html(year, player_key)
    section = prospect_section(html)
    evidence: list[str] = []
    class_years: set[int] = set()

    details_juco_match = re.search(
        r'<ul\s+class="[^"]*details[^"]*is-juco',
        html,
        flags=re.IGNORECASE,
    )
    if details_juco_match:
        evidence.append("details.is-juco")
        class_match = re.search(
            r'<ul\s+class="[^"]*details[^"]*is-juco[\s\S]*?'
            r"<span>\s*Class\s*</span>\s*<span>\s*(\d{4})\s*</span>",
            html,
            flags=re.IGNORECASE,
        )
        if class_match:
            class_years.add(int(class_match.group(1)))

    if re.search(
        r'<h3[^>]*class="title"[^>]*>\s*247Sports\s*<span>\s*JUCO\s*</span>',
        section,
        flags=re.IGNORECASE,
    ):
        evidence.append("prospect_title_247sports_juco")

    section_lower = section.lower()
    if "institutiongroup=juniorcollege" in section_lower:
        evidence.append("ranking_link_juniorcollege")
    if "/junior-college-" in section_lower:
        evidence.append("junior_college_profile_link")

    commitment_class_match = re.search(
        r'<ul\s+class="commitment"[\s\S]*?'
        r"<span>\s*Class\s*</span>\s*<span>\s*(\d{4})\s*</span>",
        section,
        flags=re.IGNORECASE,
    )
    if commitment_class_match:
        class_years.add(int(commitment_class_match.group(1)))

    is_confirmed = bool(evidence) and year in class_years

    return JucoDetection(
        year=year,
        player_key=player_key,
        full_name=full_name,
        is_confirmed_juco=is_confirmed,
        evidence=";".join(evidence),
        class_years=";".join(str(value) for value in sorted(class_years)),
        html_path=str(html_path),
    )


def filled_count_expr(columns: list[str], table_alias: str = "h") -> str:
    parts = []
    for col in columns:
        col_ref = f"{table_alias}.{quote_ident(col)}"
        parts.append(
            f"CASE WHEN {col_ref} IS NOT NULL "
            f"AND TRIM(CAST({col_ref} AS VARCHAR)) <> '' THEN 1 ELSE 0 END"
        )
    return " + ".join(parts)


def main() -> None:
    if not HS_DB_PATH.exists():
        raise FileNotFoundError(f"HS DB not found: {HS_DB_PATH}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"{HS_DB_PATH.stem}.backup_before_juco_dedupe_{timestamp}.db"
    shutil.copy2(HS_DB_PATH, backup_path)

    print(f"Backup created: {backup_path}", flush=True)

    con = duckdb.connect(str(HS_DB_PATH))
    try:
        columns = [row[0] for row in con.execute(f"DESCRIBE {quote_ident(HS_TABLE)}").fetchall()]
        row_keys = con.execute(f"""
            SELECT year, player_key, full_name
            FROM {quote_ident(HS_TABLE)}
            ORDER BY year, player_key, full_name
        """).fetchall()

        detections = [
            detect_juco_for_row(int(year), int(player_key), full_name)
            for year, player_key, full_name in row_keys
        ]

        con.execute("DROP TABLE IF EXISTS juco_detection_input")
        con.execute("""
            CREATE TEMP TABLE juco_detection_input (
                year BIGINT,
                player_key BIGINT,
                full_name VARCHAR,
                is_confirmed_juco BOOLEAN,
                evidence VARCHAR,
                class_years VARCHAR,
                html_path VARCHAR
            )
        """)
        con.executemany(
            """
            INSERT INTO juco_detection_input
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.year,
                    item.player_key,
                    item.full_name,
                    item.is_confirmed_juco,
                    item.evidence,
                    item.class_years,
                    item.html_path,
                )
                for item in detections
            ],
        )

        con.execute(f"CREATE OR REPLACE TABLE {quote_ident(JUCO_AUDIT_TABLE)} AS SELECT * FROM juco_detection_input")

        confirmed_juco_count = con.execute("""
            SELECT COUNT(*)
            FROM juco_detection_input
            WHERE is_confirmed_juco
        """).fetchone()[0]

        original_count = con.execute(f"SELECT COUNT(*) FROM {quote_ident(HS_TABLE)}").fetchone()[0]

        if JUCO_DB_PATH.exists():
            juco_backup_path = BACKUP_DIR / f"{JUCO_DB_PATH.stem}.backup_before_overwrite_{timestamp}.db"
            shutil.copy2(JUCO_DB_PATH, juco_backup_path)
            JUCO_DB_PATH.unlink()
            print(f"Existing JUCO DB backed up: {juco_backup_path}", flush=True)

        con.execute(f"ATTACH DATABASE {quote_string(str(JUCO_DB_PATH))} AS juco_db")
        con.execute(f"""
            CREATE TABLE juco_db.main.{quote_ident(JUCO_TABLE)} AS
            SELECT h.*, d.evidence AS juco_evidence, d.class_years AS juco_class_years, d.html_path AS juco_html_path
            FROM {quote_ident(HS_TABLE)} AS h
            JOIN juco_detection_input AS d
              ON h.year = d.year
             AND h.player_key = d.player_key
             AND h.full_name = d.full_name
            WHERE d.is_confirmed_juco
        """)
        con.execute(f"""
            CREATE TABLE juco_db.main.{quote_ident(JUCO_AUDIT_TABLE)} AS
            SELECT *
            FROM juco_detection_input
            WHERE is_confirmed_juco
        """)

        con.execute(f"""
            DELETE FROM {quote_ident(HS_TABLE)} AS h
            USING juco_detection_input AS d
            WHERE h.year = d.year
              AND h.player_key = d.player_key
              AND h.full_name = d.full_name
              AND d.is_confirmed_juco
        """)

        filled_expr = filled_count_expr(columns)

        con.execute("DROP TABLE IF EXISTS dedupe_ranked")
        con.execute(f"""
            CREATE TEMP TABLE dedupe_ranked AS
            WITH scored AS (
                SELECT
                    h.*,
                    {filled_expr} AS non_null_field_count,
                    MAX(year) OVER (PARTITION BY player_key, full_name) AS latest_year,
                    MAX({filled_expr}) OVER (PARTITION BY player_key, full_name) AS max_non_null_field_count,
                    COUNT(*) OVER (PARTITION BY player_key, full_name) AS duplicate_group_size
                FROM {quote_ident(HS_TABLE)} AS h
            )
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY player_key, full_name
                    ORDER BY
                        CASE
                            WHEN year = latest_year
                             AND non_null_field_count = max_non_null_field_count
                            THEN 0 ELSE 1
                        END,
                        non_null_field_count DESC,
                        year DESC
                ) AS keep_rank
            FROM scored
        """)

        problem_count = con.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT player_key, full_name
                FROM dedupe_ranked
                WHERE duplicate_group_size > 1
                GROUP BY player_key, full_name
                HAVING MAX(CASE WHEN year = latest_year AND non_null_field_count = max_non_null_field_count THEN 1 ELSE 0 END) = 0
            )
        """).fetchone()[0]
        if problem_count:
            raise RuntimeError(
                f"Found {problem_count:,} duplicate groups where the most-filled row "
                "does not match the latest year. No duplicate cleanup was applied."
            )

        con.execute(f"DROP TABLE IF EXISTS {quote_ident(OLD_DUP_TABLE)}")
        con.execute(f"""
            CREATE TABLE {quote_ident(OLD_DUP_TABLE)} AS
            SELECT *
            EXCLUDE (non_null_field_count, latest_year, max_non_null_field_count, duplicate_group_size, keep_rank)
            FROM dedupe_ranked
            WHERE duplicate_group_size > 1
              AND keep_rank > 1
        """)

        old_duplicate_count = con.execute(f"SELECT COUNT(*) FROM {quote_ident(OLD_DUP_TABLE)}").fetchone()[0]

        con.execute(f"""
            CREATE OR REPLACE TABLE {quote_ident(HS_TABLE)} AS
            SELECT *
            EXCLUDE (non_null_field_count, latest_year, max_non_null_field_count, duplicate_group_size, keep_rank)
            FROM dedupe_ranked
            WHERE keep_rank = 1
        """)

        final_count = con.execute(f"SELECT COUNT(*) FROM {quote_ident(HS_TABLE)}").fetchone()[0]
        duplicate_groups_remaining = con.execute(f"""
            SELECT COUNT(*)
            FROM (
                SELECT player_key, full_name
                FROM {quote_ident(HS_TABLE)}
                GROUP BY 1, 2
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        juco_db_count = con.execute(f"""
            SELECT COUNT(*)
            FROM juco_db.main.{quote_ident(JUCO_TABLE)}
        """).fetchone()[0]

        expected_final = original_count - confirmed_juco_count - old_duplicate_count
        if final_count != expected_final:
            raise RuntimeError(
                f"Final row count mismatch: expected {expected_final:,}, got {final_count:,}"
            )
        if duplicate_groups_remaining:
            raise RuntimeError(
                f"Expected zero duplicate recruit groups, found {duplicate_groups_remaining:,}"
            )
        if juco_db_count != confirmed_juco_count:
            raise RuntimeError(
                f"JUCO DB row count mismatch: expected {confirmed_juco_count:,}, got {juco_db_count:,}"
            )

        print(f"Original HS rows: {original_count:,}", flush=True)
        print(f"Confirmed JUCO rows moved: {confirmed_juco_count:,}", flush=True)
        print(f"Old HS duplicate rows moved to {OLD_DUP_TABLE}: {old_duplicate_count:,}", flush=True)
        print(f"Final HS rows: {final_count:,}", flush=True)
        print(f"Remaining duplicate player_key/full_name groups: {duplicate_groups_remaining:,}", flush=True)
        print(f"JUCO DB: {JUCO_DB_PATH}", flush=True)
        print(f"JUCO table: {JUCO_TABLE}", flush=True)
        print(f"Backup: {backup_path}", flush=True)

    finally:
        con.close()


if __name__ == "__main__":
    main()
