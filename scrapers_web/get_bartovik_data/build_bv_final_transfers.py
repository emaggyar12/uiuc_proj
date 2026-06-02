from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

import duckdb
import pandas as pd


def find_project_root() -> Path:
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if parent.name == "uiuc_proj":
            return parent
    raise RuntimeError("Could not find uiuc_proj in this script's parent folders.")


PROJECT_ROOT = find_project_root()
RAW_YEAR_DIR = PROJECT_ROOT / "scrapers_web" / "get_bartovik_data" / "raw_review" / "year_csvs"
OUTPUT_DIR = PROJECT_ROOT / "scrapers_web" / "get_bartovik_data"
DB_DIR = OUTPUT_DIR / "db_files"
OUTPUT_CSV = OUTPUT_DIR / "bv_final_transfers.csv"
OUTPUT_DB = DB_DIR / "bv_final_transfers.db"
OUTPUT_TABLE = "bv_final_transfers"
SUMMARY_TABLE = "bv_final_transfers_build_summary"


def read_year_csv(label: str) -> pd.DataFrame:
    path = RAW_YEAR_DIR / f"barttorvik_transfers_{label}_raw.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype="string")


def validate_2026_duplicate() -> tuple[int, int, bool]:
    pure_2026 = read_year_csv("2026").fillna("")
    current = read_year_csv("trans_current_2026_27").fillna("")
    core_cols = ["row_number", "player_name", "raw_team_1", "raw_team_2", "raw_flag"]
    is_match = pure_2026[core_cols].equals(current[core_cols])
    return len(pure_2026), len(current), is_match


def build_final_rows() -> pd.DataFrame:
    frames = []
    for year in range(2018, 2026):
        df = read_year_csv(str(year)).copy()
        df["source_barttorvik_year"] = str(year)
        df["barttorvik_year"] = year
        df["old_team"] = df["raw_team_1"]
        df["new_team"] = df["raw_team_2"]
        df["team_orientation"] = "raw_team_1_old_raw_team_2_new"
        frames.append(df)

    current = read_year_csv("trans_current_2026_27").copy()
    current["source_barttorvik_year"] = "trans_current_2026_27"
    current["barttorvik_year"] = 2026
    current["old_team"] = current["raw_team_1"]
    current["new_team"] = current["raw_team_2"]
    current["team_orientation"] = "raw_team_1_old_raw_team_2_new"
    frames.append(current)

    final_df = pd.concat(frames, ignore_index=True)
    final_df["transfer_cycle_season"] = final_df["barttorvik_year"].astype("int64") + 1

    ordered_cols = [
        "barttorvik_year",
        "transfer_cycle_season",
        "source_barttorvik_year",
        "row_number",
        "player_name",
        "old_team",
        "new_team",
        "raw_team_1",
        "raw_team_2",
        "raw_flag",
        "team_orientation",
        "page_title",
        "source_url",
        "scraped_at_utc",
    ]
    return final_df[ordered_cols]


def main() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)

    pure_2026_rows, current_rows, duplicate_match = validate_2026_duplicate()
    if not duplicate_match:
        raise RuntimeError("Pure 2026 rows do not match trans_current_2026_27 rows on core raw columns.")

    old_raw_total = sum(len(read_year_csv(label)) for label in [*map(str, range(2018, 2027)), "trans_current_2026_27"])
    final_df = build_final_rows()
    expected_final_rows = old_raw_total - pure_2026_rows
    if len(final_df) != expected_final_rows:
        raise RuntimeError(f"Expected {expected_final_rows:,} final rows, got {len(final_df):,}.")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_csv(OUTPUT_CSV, index=False)

    if OUTPUT_DB.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = OUTPUT_DB.with_name(f"{OUTPUT_DB.stem}.backup_before_overwrite_{timestamp}.db")
        shutil.copy2(OUTPUT_DB, backup)
        OUTPUT_DB.unlink()
        print(f"Existing output DB backed up to: {backup}", flush=True)

    con = duckdb.connect(str(OUTPUT_DB))
    try:
        con.execute(
            f"""
            CREATE TABLE {OUTPUT_TABLE} AS
            SELECT *
            FROM read_csv_auto('{OUTPUT_CSV.as_posix()}', header = true)
            """
        )
        con.execute(
            f"""
            CREATE TABLE {SUMMARY_TABLE} AS
            SELECT *
            FROM (
                VALUES
                    ('old_raw_total_including_duplicate_2026', {old_raw_total}),
                    ('pure_2026_rows_removed', {pure_2026_rows}),
                    ('trans_current_2026_27_rows_used_as_2026', {current_rows}),
                    ('final_rows', {len(final_df)}),
                    ('row_count_drop', {old_raw_total - len(final_df)}),
                    ('pure_2026_matches_current_core_raw_cols', {str(duplicate_match).lower()})
            ) AS t(metric, value)
            """
        )
    finally:
        con.close()

    print(f"Pure 2026 rows: {pure_2026_rows:,}", flush=True)
    print(f"trans_current_2026_27 rows: {current_rows:,}", flush=True)
    print(f"Core raw columns match: {duplicate_match}", flush=True)
    print(f"Old raw total including duplicate 2026/current: {old_raw_total:,}", flush=True)
    print(f"Final rows: {len(final_df):,}", flush=True)
    print(f"Row count drop: {old_raw_total - len(final_df):,}", flush=True)
    print(f"Output CSV: {OUTPUT_CSV}", flush=True)
    print(f"Output DB: {OUTPUT_DB}", flush=True)
    print(f"Output table: {OUTPUT_TABLE}", flush=True)


if __name__ == "__main__":
    main()
