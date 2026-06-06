from __future__ import annotations

from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
import shutil
from urllib.parse import quote, urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import duckdb
import pandas as pd


def find_project_root() -> Path:
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if parent.name == "uiuc_proj":
            return parent
    raise RuntimeError("Could not find uiuc_proj in this script's parent folders.")


PROJECT_ROOT = find_project_root()
WORK_DIR = PROJECT_ROOT / "scrapers_web" / "get_bartovik_data"
DB_DIR = WORK_DIR / "db_files"

SOURCE_DB = DB_DIR / "bv_final_transfers.db"
SOURCE_TABLE = "bv_final_transfers"
OUTPUT_CSV = WORK_DIR / "bv_trans_compl.csv"
OUTPUT_DB = DB_DIR / "bv_trans_compl.db"
OUTPUT_TABLE = "bv_trans_compl"
VALIDATION_TABLE = "bv_trans_compl_validation"

BARTTORVIK_BASE = "https://barttorvik.com"

ORIGINAL_COLS = [
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


def fetch_json(opener, url: str):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
        },
    )
    with opener.open(request, timeout=90) as response:
        return pd.read_json(response)


def historical_stats_url(year: int) -> str:
    params = {
        "year": year,
        "specialSource": 0,
        "conyes": 0,
        "start": f"{year}1101",
        "end": f"{year + 1}0501",
        "top": 364,
        "xvalue": "trans",
        "page": "playerstat",
        "team": "",
    }
    return f"{BARTTORVIK_BASE}/getadvstats.php?{urlencode(params)}"


def current_stats_url() -> str:
    return f"{BARTTORVIK_BASE}/2027_transfer_stats.json"


def team_url(team: object, year: object) -> object:
    if pd.isna(team) or str(team).strip() == "":
        return pd.NA
    return f"{BARTTORVIK_BASE}/team.php?team={quote(str(team), safe='')}&year={int(year)}"


def player_url(player: object, team: object, year_param: object) -> object:
    if pd.isna(player) or pd.isna(team) or str(team).strip() == "":
        return pd.NA
    return (
        f"{BARTTORVIK_BASE}/playerstat.php?"
        f"year={quote(str(year_param), safe='')}&p={quote(str(player), safe='')}&t={quote(str(team), safe='')}"
    )


def normalize_stats_frame(df: pd.DataFrame, label: str, source_url: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=df.index)
    out["source_barttorvik_year"] = label
    if label == "trans_current_2026_27":
        out["barttorvik_year"] = 2026
        out["old_team"] = df[1]
        out["new_team"] = df[34]
        out["player_link_team"] = df[1]
        out["player_link_year"] = "trans"
        out["old_team_conf"] = df[2]
        out["new_team_conf"] = df[66] if 66 in df.columns else pd.NA
    else:
        year = int(label)
        out["barttorvik_year"] = year
        out["old_team"] = df[1]
        out["new_team"] = pd.NA
        out["player_link_team"] = df[1]
        out["player_link_year"] = year
        out["old_team_conf"] = df[2]
        out["new_team_conf"] = pd.NA

    out["player_name"] = df[0]
    out["player_class"] = df[25]
    out["player_height"] = df[26]
    out["barttorvik_trid"] = df[32]
    out["player_hometown"] = df[33]
    out["player_role"] = df[64] if 64 in df.columns else pd.NA
    out["player_birth_date"] = df[66] if label != "trans_current_2026_27" and 66 in df.columns else pd.NA
    out["stats_source_url"] = source_url

    out["player_url"] = [
        player_url(player, team, year)
        for player, team, year in zip(out["player_name"], out["player_link_team"], out["player_link_year"])
    ]
    out["old_team_url"] = [team_url(team, year) for team, year in zip(out["old_team"], out["barttorvik_year"])]
    out["new_team_url"] = [team_url(team, year) for team, year in zip(out["new_team"], out["barttorvik_year"])]

    return out[
        [
            "source_barttorvik_year",
            "barttorvik_year",
            "player_name",
            "old_team",
            "new_team",
            "player_class",
            "player_height",
            "barttorvik_trid",
            "player_hometown",
            "player_birth_date",
            "player_role",
            "old_team_conf",
            "new_team_conf",
            "player_url",
            "old_team_url",
            "new_team_url",
            "stats_source_url",
        ]
    ]


def load_source_df() -> pd.DataFrame:
    if not SOURCE_DB.exists():
        raise FileNotFoundError(SOURCE_DB)
    con = duckdb.connect(str(SOURCE_DB), read_only=True)
    try:
        return con.execute(f"SELECT * FROM {SOURCE_TABLE}").fetchdf()
    finally:
        con.close()


def load_all_stats() -> pd.DataFrame:
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    frames = []
    for year in range(2018, 2026):
        url = historical_stats_url(year)
        raw_df = fetch_json(opener, url)
        frames.append(normalize_stats_frame(raw_df, str(year), url))
        print(f"Fetched {year} stats rows: {len(raw_df):,}", flush=True)

    url = current_stats_url()
    raw_df = fetch_json(opener, url)
    frames.append(normalize_stats_frame(raw_df, "trans_current_2026_27", url))
    print(f"Fetched 2026-27 current stats rows: {len(raw_df):,}", flush=True)
    return pd.concat(frames, ignore_index=True)


def build_complete_df(source_df: pd.DataFrame, stats_df: pd.DataFrame) -> pd.DataFrame:
    source_df = source_df.copy()
    stats_df = stats_df.copy()

    merge_cols = ["source_barttorvik_year", "barttorvik_year", "player_name", "old_team"]
    current_mask = stats_df["source_barttorvik_year"].eq("trans_current_2026_27")
    historical_stats = stats_df.loc[~current_mask].copy()
    current_stats = stats_df.loc[current_mask].copy()

    historical_stats = historical_stats.drop_duplicates(merge_cols, keep="first")

    def pair_key(left: object, right: object) -> str:
        values = sorted(str(value) for value in [left, right] if pd.notna(value) and str(value).strip() != "")
        return "||".join(values)

    current_stats["team_pair_key"] = [
        pair_key(old_team, new_team)
        for old_team, new_team in zip(current_stats["old_team"], current_stats["new_team"])
    ]
    current_stats = current_stats.drop_duplicates(
        ["source_barttorvik_year", "barttorvik_year", "player_name", "team_pair_key"],
        keep="first",
    )

    historical_source = source_df[source_df["source_barttorvik_year"] != "trans_current_2026_27"].copy()
    current_source = source_df[source_df["source_barttorvik_year"] == "trans_current_2026_27"].copy()
    current_source["team_pair_key"] = [
        pair_key(old_team, new_team)
        for old_team, new_team in zip(current_source["old_team"], current_source["new_team"])
    ]

    historical = historical_source.merge(
        historical_stats.drop(columns=["new_team"]),
        on=merge_cols,
        how="left",
        validate="many_to_one",
        indicator="stats_merge_status",
    )
    current = current_source.merge(
        current_stats.drop(columns=["old_team", "new_team"]),
        on=["source_barttorvik_year", "barttorvik_year", "player_name", "team_pair_key"],
        how="left",
        validate="many_to_one",
        indicator="stats_merge_status",
    ).drop(columns=["team_pair_key"])

    complete = pd.concat([historical, current], ignore_index=True)
    complete = complete.sort_values(["barttorvik_year", "row_number"], kind="stable").reset_index(drop=True)

    complete["has_stats_enrichment"] = complete["stats_merge_status"].eq("both")

    # Construct movement URLs for every row, even when no stats row was available.
    complete["old_team_url"] = [
        team_url(team, year) for team, year in zip(complete["old_team"], complete["barttorvik_year"])
    ]
    complete["new_team_url"] = [
        team_url(team, year) for team, year in zip(complete["new_team"], complete["transfer_cycle_season"])
    ]
    player_link_teams = complete["new_team"].where(complete["new_team"].notna(), complete["old_team"])
    complete["player_url"] = [
        player_url(player, team, year)
        for player, team, year in zip(
            complete["player_name"],
            player_link_teams,
            complete["transfer_cycle_season"],
        )
    ]

    added_cols = [
        "has_stats_enrichment",
        "player_class",
        "player_height",
        "barttorvik_trid",
        "player_hometown",
        "player_birth_date",
        "player_role",
        "old_team_conf",
        "new_team_conf",
        "player_url",
        "old_team_url",
        "new_team_url",
        "stats_source_url",
        "stats_merge_status",
    ]
    return complete[ORIGINAL_COLS + added_cols]


def validate_complete(source_df: pd.DataFrame, complete_df: pd.DataFrame) -> list[tuple[str, object]]:
    if len(source_df) != len(complete_df):
        raise RuntimeError(f"Row count changed: source={len(source_df):,}, complete={len(complete_df):,}")

    source_ordered = source_df.sort_values(["barttorvik_year", "row_number"], kind="stable").reset_index(drop=True)
    complete_original = complete_df[ORIGINAL_COLS].reset_index(drop=True)
    source_original = source_ordered[ORIGINAL_COLS].reset_index(drop=True)

    if not complete_original.equals(source_original):
        mismatch_cols = [
            col for col in ORIGINAL_COLS if not complete_original[col].equals(source_original[col])
        ]
        raise RuntimeError(f"Original columns changed during enrichment: {mismatch_cols}")

    pure_2026_count = complete_df["source_barttorvik_year"].eq("2026").sum()
    if pure_2026_count:
        raise RuntimeError(f"Unexpected pure 2026 rows survived: {pure_2026_count:,}")

    current_count = complete_df["source_barttorvik_year"].eq("trans_current_2026_27").sum()
    if current_count != 3821:
        raise RuntimeError(f"Expected 3,821 current 2026-27 rows, got {current_count:,}")

    enriched = int(complete_df["has_stats_enrichment"].sum())
    return [
        ("source_rows", len(source_df)),
        ("complete_rows", len(complete_df)),
        ("original_columns_identical", True),
        ("pure_2026_rows_remaining", int(pure_2026_count)),
        ("trans_current_2026_27_rows_kept_as_2026", int(current_count)),
        ("rows_with_stats_enrichment", enriched),
        ("rows_with_player_height", int(complete_df["player_height"].notna().sum())),
        ("rows_with_player_class", int(complete_df["player_class"].notna().sum())),
        ("rows_with_player_url", int(complete_df["player_url"].notna().sum())),
        ("rows_with_old_team_url", int(complete_df["old_team_url"].notna().sum())),
        ("rows_with_new_team_url", int(complete_df["new_team_url"].notna().sum())),
        ("built_at_utc", datetime.now(timezone.utc).isoformat()),
    ]


def write_outputs(complete_df: pd.DataFrame, validation_rows: list[tuple[str, object]]) -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    complete_df.to_csv(OUTPUT_CSV, index=False)

    if OUTPUT_DB.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = OUTPUT_DB.with_name(f"{OUTPUT_DB.stem}.backup_before_overwrite_{timestamp}.db")
        shutil.copy2(OUTPUT_DB, backup)
        OUTPUT_DB.unlink()
        print(f"Existing output DB backed up to: {backup}", flush=True)

    con = duckdb.connect(str(OUTPUT_DB))
    try:
        con.register("complete_df", complete_df)
        con.execute(f"CREATE TABLE {OUTPUT_TABLE} AS SELECT * FROM complete_df")
        con.execute(f"CREATE TABLE {VALIDATION_TABLE} (metric VARCHAR, value VARCHAR)")
        con.executemany(
            f"INSERT INTO {VALIDATION_TABLE} VALUES (?, ?)",
            [(metric, str(value)) for metric, value in validation_rows],
        )
    finally:
        con.close()


def main() -> None:
    source_df = load_source_df()
    stats_df = load_all_stats()
    complete_df = build_complete_df(source_df, stats_df)
    validation_rows = validate_complete(source_df, complete_df)
    write_outputs(complete_df, validation_rows)

    print(f"Output CSV: {OUTPUT_CSV}", flush=True)
    print(f"Output DB: {OUTPUT_DB}", flush=True)
    print(f"Output table: {OUTPUT_TABLE}", flush=True)
    for metric, value in validation_rows:
        print(f"{metric}: {value}", flush=True)

    examples = complete_df[
        complete_df["player_name"].isin(["Colby Garland", "Denzel Aberdeen", "Cane Broome", "Hunter Dickinson"])
    ][
        [
            "barttorvik_year",
            "player_name",
            "old_team",
            "new_team",
            "player_class",
            "player_height",
            "barttorvik_trid",
            "has_stats_enrichment",
        ]
    ]
    if not examples.empty:
        print("\nExamples:", flush=True)
        print(examples.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
