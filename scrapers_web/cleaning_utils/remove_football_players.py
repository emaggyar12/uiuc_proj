from pathlib import Path
import shutil
import duckdb


# -----------------------------
# PATH SETUP
# -----------------------------
def find_project_root() -> Path:
    """
    Finds the uiuc_proj folder by walking upward from this script.
    This lets you run the script from basically anywhere.
    """
    current_path = Path(__file__).resolve()

    for parent in current_path.parents:
        if parent.name == "uiuc_proj":
            return parent

    raise RuntimeError("Could not find uiuc_proj in this script's parent folders.")


# -----------------------------
# CONFIG
# -----------------------------
PROJECT_ROOT = find_project_root()

DB_PATH = PROJECT_ROOT / "scrapers_web" / "outputs" / "actual_db_files" / "hs_recruit_skill_ratings.db"
TABLE_NAME = "hs_recruit_skill_ratings"

OUTPUT_CSV = PROJECT_ROOT / "scrapers_web" / "outputs" / "hs_recruit_skill_ratings_cleaned.csv"

NON_BASKETBALL_SKILL_COLS = [
    'skill_accuracy',
    'skill_agility',
    'skill_arm_strength',
    'skill_ball_skills',
    'skill_body_quickness',
    'skill_catch_radius',
    'skill_change_of_direction',
    'skill_delivery',
    'skill_elusiveness',
    'skill_explosiveness',
    'skill_feet',
    'skill_footwork',
    'skill_frame',
    'skill_hands',
    'skill_instincts',
    'skill_intangibles',
    'skill_lateral_movement',
    'skill_mismatch_ability',
    'skill_pass_blocking',
    'skill_play_in_space',
    'skill_pocket_presence',
    'skill_point_of_attack',
    'skill_punch',
    'skill_pursuit',
    'skill_reactive_quickness',
    'skill_release',
    'skill_route_running',
    'skill_run_blocking',
    'skill_scorer_finisher',
    'skill_speed',
    'skill_tackling',
    'skill_yards_after_catch'
]

CREATE_BACKUP = True


# -----------------------------
# HELPERS
# -----------------------------
def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def get_table_columns(con: duckdb.DuckDBPyConnection, table_name: str) -> list[str]:
    rows = con.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = ?
        ORDER BY ordinal_position
    """, [table_name]).fetchall()

    return [row[0] for row in rows]


# -----------------------------
# MAIN
# -----------------------------
def main():
    print(f"Project root: {PROJECT_ROOT}", flush=True)
    print(f"Database path: {DB_PATH}", flush=True)
    print(f"Database exists: {DB_PATH.exists()}", flush=True)
    print(f"Output CSV path: {OUTPUT_CSV}", flush=True)

    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database file not found: {DB_PATH}")

    if CREATE_BACKUP:
        backup_path = DB_PATH.with_suffix(".backup_before_non_basketball_clean.db")
        shutil.copy2(DB_PATH, backup_path)
        print(f"Backup created: {backup_path}", flush=True)

    con = duckdb.connect(str(DB_PATH))

    all_cols = get_table_columns(con, TABLE_NAME)

    if not all_cols:
        con.close()
        raise ValueError(f"No columns found for table: {TABLE_NAME}")

    print(f"Total columns in table: {len(all_cols)}", flush=True)

    existing_non_basketball_cols = [
        col for col in NON_BASKETBALL_SKILL_COLS
        if col in all_cols
    ]

    missing_non_basketball_cols = [
        col for col in NON_BASKETBALL_SKILL_COLS
        if col not in all_cols
    ]

    print("\nExisting non-basketball columns found:", flush=True)
    print(existing_non_basketball_cols, flush=True)

    if missing_non_basketball_cols:
        print("\nColumns from your list that were NOT found:", flush=True)
        print(missing_non_basketball_cols, flush=True)

    if existing_non_basketball_cols:
        bad_row_condition = " OR ".join([
            f"{quote_ident(col)} IS NOT NULL"
            for col in existing_non_basketball_cols
        ])

        bad_row_count = con.execute(f"""
            SELECT COUNT(*)
            FROM {quote_ident(TABLE_NAME)}
            WHERE {bad_row_condition}
        """).fetchone()[0]

        print(f"\nRows with non-basketball skill ratings: {bad_row_count:,}", flush=True)

        basketball_skill_cols_to_null = [
            col for col in all_cols
            if col.startswith("skill_")
            and col != "skill_rating"
            and col not in existing_non_basketball_cols
        ]

        print("\nBasketball skill columns that will be nulled for those rows:", flush=True)
        print(basketball_skill_cols_to_null, flush=True)

        set_clauses = [
            f"{quote_ident('skill_rating')} = FALSE"
        ]

        for col in basketball_skill_cols_to_null:
            set_clauses.append(f"{quote_ident(col)} = NULL")

        set_sql = ",\n            ".join(set_clauses)

        print("\nCleaning affected rows...", flush=True)

        con.execute(f"""
            UPDATE {quote_ident(TABLE_NAME)}
            SET
                {set_sql}
            WHERE {bad_row_condition}
        """)

        print("\nDropping non-basketball columns...", flush=True)

        for col in existing_non_basketball_cols:
            current_cols = get_table_columns(con, TABLE_NAME)

            if col not in current_cols:
                print(f"Already dropped, skipping: {col}", flush=True)
                continue

            print(f"Dropping column: {col}", flush=True)

            con.execute(f"""
                ALTER TABLE {quote_ident(TABLE_NAME)}
                DROP COLUMN {quote_ident(col)}
            """)

    else:
        bad_row_count = 0
        print("\nNo listed non-basketball columns exist. Skipping cleaning/drop step.", flush=True)

    remaining_cols = get_table_columns(con, TABLE_NAME)

    remaining_skill_cols = [
        col for col in remaining_cols
        if col.startswith("skill_")
    ]

    print("\nSaving final cleaned CSV...", flush=True)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    final_df = con.execute(f"""
        SELECT *
        FROM {quote_ident(TABLE_NAME)}
    """).fetchdf()

    final_df.to_csv(OUTPUT_CSV, index=False)

    print("\nDone.", flush=True)
    print(f"Rows cleaned: {bad_row_count:,}", flush=True)
    print(f"CSV saved to: {OUTPUT_CSV}", flush=True)

    print("\nRemaining skill columns:", flush=True)
    print(remaining_skill_cols, flush=True)

    con.close()


if __name__ == "__main__":
    main()