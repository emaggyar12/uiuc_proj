from __future__ import annotations

from datetime import datetime, timezone
from http.cookiejar import CookieJar
import csv
import json
from pathlib import Path
import re
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
OUTPUT_DIR = PROJECT_ROOT / "scrapers_web" / "outputs"
DB_DIR = OUTPUT_DIR / "actual_db_files"

OUTPUT_CSV = OUTPUT_DIR / "barttorvik_transfers_2018_2026.csv"
OUTPUT_DB = DB_DIR / "barttorvik_transfers_2018_2026.db"
OUTPUT_TABLE = "barttorvik_transfers"

BASE_URL = "https://barttorvik.com/playerstat.php"
HISTORICAL_YEARS = list(range(2018, 2027))


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
            raise ValueError(
                f"Unexpected transfer row shape for {barttorvik_year}: {row!r}"
            )
        rows.append(
            {
                "barttorvik_year": barttorvik_year,
                "row_number": idx,
                "player_name": row[0],
                "destination_team": row[1],
                "previous_team": row[2],
                "transfer_flag": row[3],
                "page_title": page_title,
                "source_url": source_url,
                "scraped_at_utc": scraped_at_utc,
            }
        )
    return rows


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)

    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    scraped_at_utc = datetime.now(timezone.utc).isoformat()

    pulls: list[tuple[str, str]] = []
    for year in HISTORICAL_YEARS:
        params = {
            "link": "y",
            "minGP": 1,
            "ocvalue": "d1",
            "minmin": 0,
            "erk": 500,
            "year": year,
            "xvalue": "trans",
        }
        pulls.append((str(year), build_url(params)))

    current_params = {
        "link": "y",
        "minGP": 1,
        "ocvalue": "d1",
        "year": "trans",
        "minmin": 0,
        "start": 20241101,
        "end": 20250501,
    }
    current_url = build_url(current_params)

    all_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for barttorvik_year, url in pulls:
        html = fetch_html(opener, url)
        transfer_rows = extract_transfers(html)
        page_title = extract_page_title(html)

        if not transfer_rows:
            raise RuntimeError(
                f"No embedded transfer rows found for {barttorvik_year}: {url}"
            )

        parsed_rows = rows_from_transfer_array(
            transfer_rows=transfer_rows,
            barttorvik_year=barttorvik_year,
            page_title=page_title,
            source_url=url,
            scraped_at_utc=scraped_at_utc,
        )
        all_rows.extend(parsed_rows)
        summary_rows.append(
            {
                "barttorvik_year": barttorvik_year,
                "page_title": page_title,
                "row_count": len(parsed_rows),
                "source_url": url,
                "scraped_at_utc": scraped_at_utc,
                "included_in_main_table": True,
                "matches_2026_table": None,
            }
        )
        print(
            f"{barttorvik_year}: {len(parsed_rows):,} rows"
            + (f" ({page_title})" if page_title else ""),
            flush=True,
        )
        time.sleep(0.3)

    current_html = fetch_html(opener, current_url)
    current_transfer_rows = extract_transfers(current_html)
    current_page_title = extract_page_title(current_html)
    if not current_transfer_rows:
        raise RuntimeError(f"No embedded transfer rows found for current page: {current_url}")

    current_rows = rows_from_transfer_array(
        transfer_rows=current_transfer_rows,
        barttorvik_year="trans_current_2026_27",
        page_title=current_page_title,
        source_url=current_url,
        scraped_at_utc=scraped_at_utc,
    )
    current_keys = {
        (
            row["player_name"],
            row["destination_team"],
            row["previous_team"],
            row["transfer_flag"],
        )
        for row in current_rows
    }
    year_2026_keys = {
        (
            row["player_name"],
            row["destination_team"],
            row["previous_team"],
            row["transfer_flag"],
        )
        for row in all_rows
        if row["barttorvik_year"] == "2026"
    }
    current_matches_2026 = current_keys == year_2026_keys
    summary_rows.append(
        {
            "barttorvik_year": "trans_current_2026_27",
            "page_title": current_page_title,
            "row_count": len(current_rows),
            "source_url": current_url,
            "scraped_at_utc": scraped_at_utc,
            "included_in_main_table": False,
            "matches_2026_table": current_matches_2026,
        }
    )
    print(
        "trans_current_2026_27: "
        f"{len(current_rows):,} rows"
        + (f" ({current_page_title})" if current_page_title else "")
        + f"; matches 2026 table: {current_matches_2026}",
        flush=True,
    )

    fieldnames = [
        "barttorvik_year",
        "row_number",
        "player_name",
        "destination_team",
        "previous_team",
        "transfer_flag",
        "page_title",
        "source_url",
        "scraped_at_utc",
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    if OUTPUT_DB.exists():
        backup = OUTPUT_DB.with_suffix(".backup_before_overwrite.db")
        backup.write_bytes(OUTPUT_DB.read_bytes())
        OUTPUT_DB.unlink()
        print(f"Existing DB backed up to: {backup}", flush=True)

    con = duckdb.connect(str(OUTPUT_DB))
    try:
        con.execute(f"""
            CREATE TABLE {OUTPUT_TABLE} AS
            SELECT *
            FROM read_csv_auto('{OUTPUT_CSV.as_posix()}', header = true)
        """)
        con.execute("""
            CREATE TABLE barttorvik_transfer_pull_summary (
                barttorvik_year VARCHAR,
                page_title VARCHAR,
                row_count BIGINT,
                source_url VARCHAR,
                scraped_at_utc VARCHAR,
                included_in_main_table BOOLEAN,
                matches_2026_table BOOLEAN
            )
        """)
        con.executemany(
            """
            INSERT INTO barttorvik_transfer_pull_summary
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["barttorvik_year"],
                    row["page_title"],
                    row["row_count"],
                    row["source_url"],
                    row["scraped_at_utc"],
                    row["included_in_main_table"],
                    row["matches_2026_table"],
                )
                for row in summary_rows
            ],
        )
    except Exception:
        con.close()
        raise
    finally:
        try:
            con.close()
        except Exception:
            pass

    total_rows = len(all_rows)
    print(f"Total rows: {total_rows:,}", flush=True)
    print(f"CSV: {OUTPUT_CSV}", flush=True)
    print(f"DuckDB: {OUTPUT_DB}", flush=True)
    print(f"Table: {OUTPUT_TABLE}", flush=True)


if __name__ == "__main__":
    main()
