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

SOURCE_DB_PATH = (
    PROJECT_ROOT
    / "scrapers_web"
    / "outputs"
    / "actual_db_files"
    / "hs_recruits_247_2010_2026_combined_complete.db"
)

SOURCE_TABLE_NAME = "hs_recruits_enriched"

SKILL_DB_PATH = (
    PROJECT_ROOT
    / "scrapers_web"
    / "outputs"
    / "actual_db_files"
    / "hs_recruit_skill_ratings.db"
)

SKILL_TABLE_NAME = "hs_recruit_skill_ratings"

OUTPUT_DB_PATH = (
    PROJECT_ROOT
    / "scrapers_web"
    / "outputs"
    / "actual_db_files"
    / "hs_complete.db"
)

OUTPUT_TABLE_NAME = "hs_complete"

OUTPUT_CSV_PATH = (
    PROJECT_ROOT
    / "scrapers_web"
    / "outputs"
    / "hs_complete.csv"
)

SOURCE_PLAYER_KEY_COL = "player_key"
SOURCE_FULL_NAME_COL = "full_name"
SOURCE_YEAR_COL = "year"

SKILL_RECRUIT_KEY_COL = "recruit_key"
SKILL_FULL_NAME_COL = "full_name"
SKILL_YEAR_COL = "year"

SKILL_COLS_TO_ADD = [
    "skill_rating",
    "skill_athleticism",
    "skill_defender",
    "skill_face_up_high_post_scorer",
    "skill_handle",
    "skill_leadership",
    "skill_low_post_scorer",
    "skill_passing",
    "skill_passing_vision",
    "skill_penetration_ability",
    "skill_physicality_motor",
    "skill_rebounding",
    "skill_shooter",
    "skill_size",
    "skill_versatility",
]

CREATE_BACKUP_IF_OUTPUT_EXISTS = True


# -----------------------------
# HELPERS
# -----------------------------
def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def qualified_table(db_alias: str, table_name: str) -> str:
    return f"{quote_ident(db_alias)}.main.{quote_ident(table_name)}"


def get_columns_from_table(
    con: duckdb.DuckDBPyConnection,
    db_alias: str,
    table_name: str
) -> list[str]:
    table_ref = qualified_table(db_alias, table_name)

    result = con.execute(f"""
        SELECT *
        FROM {table_ref}
        LIMIT 0
    """)

    return [col[0] for col in result.description]


def assert_unique_join_keys(
    con: duckdb.DuckDBPyConnection,
    table_ref: str,
    key_exprs: list[str],
    label: str,
) -> None:
    keys_sql = ", ".join(key_exprs)
    duplicate_count = con.execute(f"""
        SELECT COUNT(*)
        FROM (
            SELECT {keys_sql}, COUNT(*) AS row_count
            FROM {table_ref}
            GROUP BY {keys_sql}
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    if duplicate_count:
        examples = con.execute(f"""
            SELECT {keys_sql}, COUNT(*) AS row_count
            FROM {table_ref}
            GROUP BY {keys_sql}
            HAVING COUNT(*) > 1
            ORDER BY row_count DESC
            LIMIT 10
        """).fetchall()

        raise ValueError(
            f"{label} has {duplicate_count:,} duplicate join keys. "
            f"Examples: {examples}"
        )


# -----------------------------
# MAIN
# -----------------------------
def main():
    print(f"Project root: {PROJECT_ROOT}", flush=True)
    print(f"Source DB: {SOURCE_DB_PATH}", flush=True)
    print(f"Skill DB: {SKILL_DB_PATH}", flush=True)
    print(f"Output DB: {OUTPUT_DB_PATH}", flush=True)
    print(f"Output CSV: {OUTPUT_CSV_PATH}", flush=True)

    if not SOURCE_DB_PATH.exists():
        raise FileNotFoundError(f"Source DB not found: {SOURCE_DB_PATH}")

    if not SKILL_DB_PATH.exists():
        raise FileNotFoundError(f"Skill DB not found: {SKILL_DB_PATH}")

    OUTPUT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

    if OUTPUT_DB_PATH.exists() and CREATE_BACKUP_IF_OUTPUT_EXISTS:
        backup_path = OUTPUT_DB_PATH.with_suffix(".backup_before_overwrite.db")
        shutil.copy2(OUTPUT_DB_PATH, backup_path)
        print(f"Backup created: {backup_path}", flush=True)

    if OUTPUT_DB_PATH.exists():
        OUTPUT_DB_PATH.unlink()
        print("Existing output DB deleted so it can be rebuilt.", flush=True)

    con = duckdb.connect(str(OUTPUT_DB_PATH))

    try:
        con.execute(f"""
            ATTACH DATABASE {quote_string(str(SOURCE_DB_PATH))} AS source_db
        """)

        con.execute(f"""
            ATTACH DATABASE {quote_string(str(SKILL_DB_PATH))} AS skill_db
        """)

        source_table_ref = qualified_table("source_db", SOURCE_TABLE_NAME)
        skill_table_ref = qualified_table("skill_db", SKILL_TABLE_NAME)

        source_cols = get_columns_from_table(con, "source_db", SOURCE_TABLE_NAME)
        skill_cols = get_columns_from_table(con, "skill_db", SKILL_TABLE_NAME)

        required_source_cols = [
            SOURCE_YEAR_COL,
            SOURCE_PLAYER_KEY_COL,
            SOURCE_FULL_NAME_COL,
        ]

        required_skill_cols = [
            SKILL_YEAR_COL,
            SKILL_RECRUIT_KEY_COL,
            SKILL_FULL_NAME_COL,
            *SKILL_COLS_TO_ADD,
        ]

        for col in required_source_cols:
            if col not in source_cols:
                raise ValueError(f"Missing column in source table: {col}")

        for col in required_skill_cols:
            if col not in skill_cols:
                raise ValueError(f"Missing column in skill table: {col}")

        skill_select_cols = []

        for col in SKILL_COLS_TO_ADD:
            if col == "skill_rating":
                skill_select_cols.append(
                    f"COALESCE(skill.{quote_ident(col)}, FALSE) AS {quote_ident(col)}"
                )
            else:
                skill_select_cols.append(
                    f"skill.{quote_ident(col)} AS {quote_ident(col)}"
                )

        skill_select_sql = ",\n                ".join(skill_select_cols)

        source_join_keys = [
            f"{quote_ident(SOURCE_YEAR_COL)}",
            f"CAST({quote_ident(SOURCE_PLAYER_KEY_COL)} AS VARCHAR)",
            f"{quote_ident(SOURCE_FULL_NAME_COL)}",
        ]
        skill_join_keys = [
            f"{quote_ident(SKILL_YEAR_COL)}",
            f"CAST({quote_ident(SKILL_RECRUIT_KEY_COL)} AS VARCHAR)",
            f"{quote_ident(SKILL_FULL_NAME_COL)}",
        ]

        assert_unique_join_keys(
            con,
            source_table_ref,
            source_join_keys,
            "Source table",
        )
        assert_unique_join_keys(
            con,
            skill_table_ref,
            skill_join_keys,
            "Skill table",
        )

        print("\nCreating left-joined output table...", flush=True)

        con.execute(f"""
            CREATE TABLE {quote_ident(OUTPUT_TABLE_NAME)} AS
            SELECT
                src.*,
                {skill_select_sql}
            FROM {source_table_ref} AS src
            LEFT JOIN {skill_table_ref} AS skill
                ON src.{quote_ident(SOURCE_YEAR_COL)}
                    = skill.{quote_ident(SKILL_YEAR_COL)}
                AND CAST(src.{quote_ident(SOURCE_PLAYER_KEY_COL)} AS VARCHAR)
                    = CAST(skill.{quote_ident(SKILL_RECRUIT_KEY_COL)} AS VARCHAR)
                AND src.{quote_ident(SOURCE_FULL_NAME_COL)}
                    = skill.{quote_ident(SKILL_FULL_NAME_COL)}
        """)

        print("\nSaving output CSV...", flush=True)

        con.execute(f"""
            COPY {quote_ident(OUTPUT_TABLE_NAME)}
            TO {quote_string(str(OUTPUT_CSV_PATH))}
            WITH (HEADER, DELIMITER ',')
        """)

        total_source_rows = con.execute(f"""
            SELECT COUNT(*)
            FROM {source_table_ref}
        """).fetchone()[0]

        total_output_rows = con.execute(f"""
            SELECT COUNT(*)
            FROM {quote_ident(OUTPUT_TABLE_NAME)}
        """).fetchone()[0]

        true_skill_rows = con.execute(f"""
            SELECT COUNT(*)
            FROM {quote_ident(OUTPUT_TABLE_NAME)}
            WHERE skill_rating = TRUE
        """).fetchone()[0]

        false_skill_rows = con.execute(f"""
            SELECT COUNT(*)
            FROM {quote_ident(OUTPUT_TABLE_NAME)}
            WHERE skill_rating = FALSE
        """).fetchone()[0]

        print("\nDone.", flush=True)
        print(f"Source rows: {total_source_rows:,}", flush=True)
        print(f"Output rows: {total_output_rows:,}", flush=True)
        if total_output_rows != total_source_rows:
            raise ValueError(
                f"Output row count mismatch: source has {total_source_rows:,}, "
                f"output has {total_output_rows:,}"
            )
        print(f"Rows with skill_rating = TRUE: {true_skill_rows:,}", flush=True)
        print(f"Rows with skill_rating = FALSE: {false_skill_rows:,}", flush=True)
        print(f"Saved output DB to: {OUTPUT_DB_PATH}", flush=True)
        print(f"Saved output CSV to: {OUTPUT_CSV_PATH}", flush=True)
        print(f"Output table name: {OUTPUT_TABLE_NAME}", flush=True)

    finally:
        con.close()


if __name__ == "__main__":
    main()
