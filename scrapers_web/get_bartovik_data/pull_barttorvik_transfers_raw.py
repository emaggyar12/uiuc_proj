from __future__ import annotations

from datetime import datetime, timezone
from http.cookiejar import CookieJar
import argparse
import csv
import json
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import duckdb


def find_project_root() -> Path:
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if parent.name == "uiuc_proj":
            return parent
    raise RuntimeError("Could not find uiuc_proj in this script's parent folders.")


PROJECT_ROOT = find_project_root()
BASE_URL = "https://barttorvik.com/playerstat.php"

OUTPUT_ROOT = PROJECT_ROOT / "scrapers_web" / "get_bartovik_data"
RAW_REVIEW_DIR = OUTPUT_ROOT / "raw_review"
RAW_YEAR_DIR = RAW_REVIEW_DIR / "year_csvs"
DB_DIR = OUTPUT_ROOT / "db_files"

COMBINED_CSV = OUTPUT_ROOT / "barttorvik_transfers_2018_current_raw.csv"
COMBINED_DB = DB_DIR / "barttorvik_transfers_2018_current_raw.db"
OUTPUT_TABLE = "barttorvik_transfers_raw"
SUMMARY_TABLE = "barttorvik_transfer_raw_pull_summary"

HISTORICAL_YEARS = list(range(2018, 2027))

RECOGNIZABLE_NAMES_BY_YEAR = {
    "2018": ["Teddy Allen", "Corey Allen", "Akoy Agau"],
    "2019": ["Mac McClung", "Justin Pierce", "Quincy McKnight"],
    "2020": ["Seth Towns", "Carlik Jones", "Alan Griffin"],
    "2021": ["Adam Miller", "Marcus Carr", "Walker Kessler", "Devin Askew"],
    "2022": ["Kendric Davis", "Baylor Scheierman", "Terrence Shannon Jr."],
    "2023": ["Hunter Dickinson", "Max Abmas", "Caleb Love"],
    "2024": ["Johnell Davis", "Clifford Omoruyi", "Kadary Richmond"],
    "2025": ["Denzel Aberdeen", "Achor Achor", "Devin Askew", "Yaxel Lendeborg"],
    "2026": ["Denzel Aberdeen", "Tucker Anderson", "Robert Vaihola"],
    "trans_current_2026_27": ["Denzel Aberdeen", "Tucker Anderson", "Robert Vaihola"],
}


def build_url(params: dict[str, str | int]) -> str:
    return f"{BASE_URL}?{urlencode(params)}"


def fetch_html(opener, url: str) -> str:
    post_data = urlencode({"js_test_submitted": "1"}).encode()
    request = Request(
        url,
        data=post_data,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with opener.open(request, timeout=45) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_transfers(html: str) -> list[list[object]]:
    match = re.search(r"var\s+transfers\s*=\s*(\[.*?\]);", html, flags=re.DOTALL)
    if not match:
        return []
    return json.loads(match.group(1))


def extract_page_title(html: str) -> str | None:
    match = re.search(r"<h3[^>]*>(.*?)</h3>", html, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    title = re.sub(r"<.*?>", "", match.group(1))
    return re.sub(r"\s+", " ", title).strip()


def pull_definitions() -> list[tuple[str, str]]:
    pulls: list[tuple[str, str]] = []
    for year in HISTORICAL_YEARS:
        pulls.append(
            (
                str(year),
                build_url(
                    {
                        "link": "y",
                        "minGP": 1,
                        "ocvalue": "d1",
                        "minmin": 0,
                        "erk": 500,
                        "year": year,
                        "xvalue": "trans",
                    }
                ),
            )
        )

    pulls.append(
        (
            "trans_current_2026_27",
            build_url(
                {
                    "link": "y",
                    "minGP": 1,
                    "ocvalue": "d1",
                    "year": "trans",
                    "minmin": 0,
                    "start": 20241101,
                    "end": 20250501,
                }
            ),
        )
    )
    return pulls


def rows_from_transfer_array(
    transfer_rows: list[list[object]],
    barttorvik_year: str,
    page_title: str | None,
    source_url: str,
    scraped_at_utc: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, row in enumerate(transfer_rows, start=1):
        if len(row) < 4:
            raise ValueError(f"Unexpected transfer row shape for {barttorvik_year}: {row!r}")
        rows.append(
            {
                "barttorvik_year": barttorvik_year,
                "row_number": idx,
                "player_name": row[0],
                "raw_team_1": row[1],
                "raw_team_2": row[2],
                "raw_flag": row[3],
                "page_title": page_title,
                "source_url": source_url,
                "scraped_at_utc": scraped_at_utc,
            }
        )
    return rows


def choose_review_row(barttorvik_year: str, rows: list[dict[str, object]]) -> dict[str, object]:
    names = RECOGNIZABLE_NAMES_BY_YEAR.get(barttorvik_year, [])
    for name in names:
        for row in rows:
            if row["player_name"] == name:
                return row
    return rows[0]


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def compile_db(all_rows: list[dict[str, object]], summary_rows: list[dict[str, object]]) -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "barttorvik_year",
        "row_number",
        "player_name",
        "raw_team_1",
        "raw_team_2",
        "raw_flag",
        "page_title",
        "source_url",
        "scraped_at_utc",
    ]
    write_csv(COMBINED_CSV, all_rows, fieldnames)

    if COMBINED_DB.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = COMBINED_DB.with_name(f"{COMBINED_DB.stem}.backup_before_overwrite_{timestamp}.db")
        shutil.copy2(COMBINED_DB, backup)
        COMBINED_DB.unlink()
        print(f"Existing combined DB backed up to: {backup}", flush=True)

    con = duckdb.connect(str(COMBINED_DB))
    try:
        con.execute(
            f"""
            CREATE TABLE {OUTPUT_TABLE} AS
            SELECT *
            FROM read_csv_auto('{COMBINED_CSV.as_posix()}', header = true)
            """
        )
        con.execute(
            f"""
            CREATE TABLE {SUMMARY_TABLE} (
                barttorvik_year VARCHAR,
                page_title VARCHAR,
                row_count BIGINT,
                source_url VARCHAR,
                scraped_at_utc VARCHAR
            )
            """
        )
        con.executemany(
            f"INSERT INTO {SUMMARY_TABLE} VALUES (?, ?, ?, ?, ?)",
            [
                (
                    row["barttorvik_year"],
                    row["page_title"],
                    row["row_count"],
                    row["source_url"],
                    row["scraped_at_utc"],
                )
                for row in summary_rows
            ],
        )
    finally:
        con.close()

    print(f"Combined raw CSV: {COMBINED_CSV}", flush=True)
    print(f"Combined raw DB: {COMBINED_DB}", flush=True)
    print(f"Combined raw table: {OUTPUT_TABLE}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Create the one combined raw CSV and DuckDB after review is approved.",
    )
    args = parser.parse_args()

    RAW_YEAR_DIR.mkdir(parents=True, exist_ok=True)

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    scraped_at_utc = datetime.now(timezone.utc).isoformat()

    fieldnames = [
        "barttorvik_year",
        "row_number",
        "player_name",
        "raw_team_1",
        "raw_team_2",
        "raw_flag",
        "page_title",
        "source_url",
        "scraped_at_utc",
    ]

    all_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []

    for barttorvik_year, url in pull_definitions():
        html = fetch_html(opener, url)
        transfer_rows = extract_transfers(html)
        page_title = extract_page_title(html)
        if not transfer_rows:
            raise RuntimeError(f"No embedded transfer rows found for {barttorvik_year}: {url}")

        rows = rows_from_transfer_array(transfer_rows, barttorvik_year, page_title, url, scraped_at_utc)
        all_rows.extend(rows)
        summary_rows.append(
            {
                "barttorvik_year": barttorvik_year,
                "page_title": page_title,
                "row_count": len(rows),
                "source_url": url,
                "scraped_at_utc": scraped_at_utc,
            }
        )
        year_csv = RAW_YEAR_DIR / f"barttorvik_transfers_{barttorvik_year}_raw.csv"
        write_csv(year_csv, rows, fieldnames)

        review_row = choose_review_row(barttorvik_year, rows)
        review_rows.append(review_row)
        print(
            f"{barttorvik_year}: {len(rows):,} rows | {page_title}",
            flush=True,
        )
        print(
            "  sample raw row: "
            f"player={review_row['player_name']!r}, "
            f"raw_team_1={review_row['raw_team_1']!r}, "
            f"raw_team_2={review_row['raw_team_2']!r}, "
            f"raw_flag={review_row['raw_flag']!r}",
            flush=True,
        )
        time.sleep(0.3)

    review_csv = RAW_REVIEW_DIR / "barttorvik_transfer_review_samples.csv"
    write_csv(review_csv, review_rows, fieldnames)
    summary_csv = RAW_REVIEW_DIR / "barttorvik_transfer_raw_pull_summary.csv"
    write_csv(
        summary_csv,
        summary_rows,
        ["barttorvik_year", "page_title", "row_count", "source_url", "scraped_at_utc"],
    )

    print(f"Review samples CSV: {review_csv}", flush=True)
    print(f"Per-year raw CSV directory: {RAW_YEAR_DIR}", flush=True)

    if args.compile:
        compile_db(all_rows, summary_rows)
    else:
        print("Compile skipped. Re-run with --compile after column review is approved.", flush=True)


if __name__ == "__main__":
    main()
