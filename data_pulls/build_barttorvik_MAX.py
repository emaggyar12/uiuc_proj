from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from urllib.parse import quote

import duckdb
import pandas as pd


def find_project_root() -> Path:
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if parent.name == "uiuc_proj":
            return parent
    raise RuntimeError("Could not find uiuc_proj in this script's parent folders.")


PROJECT_ROOT = find_project_root()
BARTTORVIK_BASE = "https://barttorvik.com"

SOURCE_PLAYER_DB = PROJECT_ROOT / "db_files" / "bvt_allyears.db"
SOURCE_PLAYER_TABLE = "bvt_allyears"
OUTPUT_PLAYER_DB = PROJECT_ROOT / "db_files" / "bvt_allyears_MAX.db"
OUTPUT_PLAYER_TABLE = "bvt_allyears_MAX"
OUTPUT_PLAYER_VALIDATION_TABLE = "bvt_allyears_MAX_validation"

SOURCE_TRANSFER_DB = (
    PROJECT_ROOT
    / "scrapers_web"
    / "get_bartovik_data"
    / "db_files"
    / "bv_trans_compl.db"
)
SOURCE_TRANSFER_TABLE = "bv_trans_compl"
OUTPUT_TRANSFER_DB = SOURCE_TRANSFER_DB.with_name("bv_trans_compl_MAX.db")
OUTPUT_TRANSFER_TABLE = "bv_trans_compl_MAX"
OUTPUT_TRANSFER_VALIDATION_TABLE = "bv_trans_compl_MAX_validation"


def team_url(team: object, year: object) -> object:
    if pd.isna(team) or pd.isna(year) or str(team).strip() == "":
        return pd.NA
    return f"{BARTTORVIK_BASE}/team.php?team={quote(str(team), safe='')}&year={int(year)}"


def player_url(player: object, team: object, year: object) -> object:
    if pd.isna(player) or pd.isna(team) or pd.isna(year) or str(team).strip() == "":
        return pd.NA
    return (
        f"{BARTTORVIK_BASE}/playerstat.php?"
        f"year={int(year)}&p={quote(str(player), safe='')}&t={quote(str(team), safe='')}"
    )


def clean_excel_safe_text(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    text = str(value)
    if text.startswith('="') and text.endswith('"'):
        return text[2:-1]
    return text


def read_table(db_path: Path, table_name: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(f"SELECT * FROM {table_name}").fetchdf()
    finally:
        con.close()


def write_table(db_path: Path, table_name: str, df: pd.DataFrame, validation_table: str, validation_rows) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = db_path.with_name(f"{db_path.stem}.backup_before_overwrite_{timestamp}.db")
        shutil.copy2(db_path, backup)
        print(f"Existing output DB backed up to: {backup}")
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    try:
        con.register("max_df", df)
        con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM max_df")
        con.execute(f"CREATE TABLE {validation_table} (metric VARCHAR, value VARCHAR)")
        con.executemany(
            f"INSERT INTO {validation_table} VALUES (?, ?)",
            [(metric, str(value)) for metric, value in validation_rows],
        )
    finally:
        con.close()


def build_player_max() -> tuple[pd.DataFrame, list[tuple[str, object]]]:
    source_df = read_table(SOURCE_PLAYER_DB, SOURCE_PLAYER_TABLE)
    max_df = source_df.copy()
    original_cols = list(source_df.columns)

    max_df["barttorvik_trid"] = max_df["pid"]
    max_df["player_class"] = max_df["yr"]
    max_df["player_height"] = max_df["ht"].map(clean_excel_safe_text)
    max_df["player_birth_date"] = max_df["dob"].map(clean_excel_safe_text)
    max_df["player_hometown"] = max_df["type"]
    max_df["barttorvik_player_url"] = [
        player_url(player, team, year)
        for player, team, year in zip(max_df["player_name"], max_df["team"], max_df["year"])
    ]
    max_df["barttorvik_team_url"] = [
        team_url(team, year) for team, year in zip(max_df["team"], max_df["year"])
    ]
    max_df["barttorvik_source_url"] = [
        f"{BARTTORVIK_BASE}/getadvstats.php?year={int(year)}&csv=1" for year in max_df["year"]
    ]
    max_df["max_build_note"] = (
        "Original bvt_allyears columns preserved; extra columns are BartTorvik URL/identity aliases."
    )

    if not source_df.reset_index(drop=True).equals(max_df[original_cols].reset_index(drop=True)):
        raise RuntimeError("Original bvt_allyears columns changed while building MAX table.")

    validation_rows = [
        ("source_rows", len(source_df)),
        ("max_rows", len(max_df)),
        ("source_columns_preserved", True),
        ("source_column_count", len(original_cols)),
        ("max_column_count", len(max_df.columns)),
        ("rows_with_barttorvik_trid", int(max_df["barttorvik_trid"].notna().sum())),
        ("rows_with_player_height", int(max_df["player_height"].notna().sum())),
        ("rows_with_player_birth_date", int(max_df["player_birth_date"].notna().sum())),
        ("rows_with_player_url", int(max_df["barttorvik_player_url"].notna().sum())),
        ("rows_with_team_url", int(max_df["barttorvik_team_url"].notna().sum())),
        ("built_at_utc", datetime.now(timezone.utc).isoformat()),
    ]
    return max_df, validation_rows


def build_transfer_max() -> tuple[pd.DataFrame, list[tuple[str, object]]]:
    source_df = read_table(SOURCE_TRANSFER_DB, SOURCE_TRANSFER_TABLE)
    max_df = source_df.copy()
    original_cols = list(source_df.columns)

    player_link_teams = max_df["new_team"].where(max_df["new_team"].notna(), max_df["old_team"])
    max_df["player_url"] = [
        player_url(player, team, year)
        for player, team, year in zip(
            max_df["player_name"],
            player_link_teams,
            max_df["transfer_cycle_season"],
        )
    ]
    max_df["old_team_url"] = [
        team_url(team, year) for team, year in zip(max_df["old_team"], max_df["barttorvik_year"])
    ]
    max_df["new_team_url"] = [
        team_url(team, year) for team, year in zip(max_df["new_team"], max_df["transfer_cycle_season"])
    ]
    max_df["barttorvik_player_url"] = max_df["player_url"]
    max_df["barttorvik_old_team_url"] = max_df["old_team_url"]
    max_df["barttorvik_new_team_url"] = max_df["new_team_url"]
    max_df["max_build_note"] = (
        "Original bv_trans_compl columns preserved; pure 2026 rows already removed and 2026-27 current rows retained as 2026."
    )

    mutable_url_cols = {"player_url", "old_team_url", "new_team_url"}
    preserved_cols = [col for col in original_cols if col not in mutable_url_cols]
    if not source_df[preserved_cols].reset_index(drop=True).equals(
        max_df[preserved_cols].reset_index(drop=True)
    ):
        raise RuntimeError("Non-URL bv_trans_compl columns changed while building MAX table.")

    pure_2026_rows = int(max_df["source_barttorvik_year"].eq("2026").sum())
    current_rows = int(max_df["source_barttorvik_year"].eq("trans_current_2026_27").sum())
    if pure_2026_rows != 0:
        raise RuntimeError(f"Pure 2026 rows are present in transfer MAX: {pure_2026_rows}")
    if current_rows != 3821:
        raise RuntimeError(f"Expected 3,821 current 2026-27 rows retained as 2026, found {current_rows}")

    validation_rows = [
        ("source_rows", len(source_df)),
        ("max_rows", len(max_df)),
        ("source_non_url_columns_preserved", True),
        ("source_column_count", len(original_cols)),
        ("max_column_count", len(max_df.columns)),
        ("pure_2026_rows_remaining", pure_2026_rows),
        ("trans_current_2026_27_rows_kept_as_2026", current_rows),
        ("rows_with_stats_enrichment", int(max_df["has_stats_enrichment"].sum())),
        ("rows_with_player_height", int(max_df["player_height"].notna().sum())),
        ("rows_with_player_class", int(max_df["player_class"].notna().sum())),
        ("rows_with_barttorvik_trid", int(max_df["barttorvik_trid"].notna().sum())),
        ("rows_with_player_url", int(max_df["barttorvik_player_url"].notna().sum())),
        ("rows_with_old_team_url", int(max_df["barttorvik_old_team_url"].notna().sum())),
        ("rows_with_new_team_url", int(max_df["barttorvik_new_team_url"].notna().sum())),
        ("built_at_utc", datetime.now(timezone.utc).isoformat()),
    ]
    return max_df, validation_rows


def main() -> None:
    player_max, player_validation = build_player_max()
    write_table(OUTPUT_PLAYER_DB, OUTPUT_PLAYER_TABLE, player_max, OUTPUT_PLAYER_VALIDATION_TABLE, player_validation)

    transfer_max, transfer_validation = build_transfer_max()
    write_table(
        OUTPUT_TRANSFER_DB,
        OUTPUT_TRANSFER_TABLE,
        transfer_max,
        OUTPUT_TRANSFER_VALIDATION_TABLE,
        transfer_validation,
    )

    print(f"Player MAX DB: {OUTPUT_PLAYER_DB}")
    print(f"Player MAX table: {OUTPUT_PLAYER_TABLE}")
    for metric, value in player_validation:
        print(f"player {metric}: {value}")

    print(f"Transfer MAX DB: {OUTPUT_TRANSFER_DB}")
    print(f"Transfer MAX table: {OUTPUT_TRANSFER_TABLE}")
    for metric, value in transfer_validation:
        print(f"transfer {metric}: {value}")


if __name__ == "__main__":
    main()
