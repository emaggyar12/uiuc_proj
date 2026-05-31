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

SKILL_DB_PATH = (
    PROJECT_ROOT
    / "scrapers_web"
    / "outputs"
    / "actual_db_files"
    / "hs_recruit_skill_ratings.db"
)

SKILL_TABLE_NAME = "hs_recruit_skill_ratings"

SOURCE_DB_PATH = (
    PROJECT_ROOT
    / "scrapers_web"
    / "outputs"
    / "actual_db_files"
    / "hs_recruits_247_2010_2026_combined_complete.db"
)

SOURCE_TABLE_NAME = "hs_recruits_enriched"

# Skill ratings table has recruit_key
SKILL_RECRUIT_KEY_COL = "recruit_key"

# Source table has player_key
SOURCE_PLAYER_KEY_COL = "player_key"

SOURCE_FULL_NAME_COL = "full_name"

CREATE_BACKUP = True


# -----------------------------
# HELPERS
# -----------------------------
def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def qualified_table(db_alias: str, table_name: str) -> str:
    if db_alias == "main":
        return f"main.{quote_ident(table_name)}"

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


def print_tables(con: duckdb.DuckDBPyConnection, db_alias: str) -> None:
    if db_alias == "main":
        tables = con.execute("SHOW TABLES").fetchdf()
    else:
        tables = con.execute(f"SHOW TABLES FROM {quote_ident(db_alias)}").fetchdf()

    print(f"\nTables in {db_alias}:", flush=True)
    print(tables, flush=True)


# -----------------------------
# MAIN
# -----------------------------
def main():
    print(f"Project root: {PROJECT_ROOT}", flush=True)
    print(f"Skill ratings DB: {SKILL_DB_PATH}", flush=True)
    print(f"Source DB: {SOURCE_DB_PATH}", flush=True)

    if not SKILL_DB_PATH.exists():
        raise FileNotFoundError(f"Skill ratings database not found: {SKILL_DB_PATH}")

    if not SOURCE_DB_PATH.exists():
        raise FileNotFoundError(f"Source database not found: {SOURCE_DB_PATH}")

    if CREATE_BACKUP:
        backup_path = SKILL_DB_PATH.with_suffix(".backup_before_add_full_name.db")
        shutil.copy2(SKILL_DB_PATH, backup_path)
        print(f"Backup created: {backup_path}", flush=True)

    con = duckdb.connect(str(SKILL_DB_PATH))

    try:
        con.execute(f"""
            ATTACH DATABASE {quote_string(str(SOURCE_DB_PATH))} AS source_db
        """)

        skill_table_ref = qualified_table("main", SKILL_TABLE_NAME)
        source_table_ref = qualified_table("source_db", SOURCE_TABLE_NAME)

        print_tables(con, "main")
        print_tables(con, "source_db")

        skill_cols = get_columns_from_table(
            con=con,
            db_alias="main",
            table_name=SKILL_TABLE_NAME
        )

        source_cols = get_columns_from_table(
            con=con,
            db_alias="source_db",
            table_name=SOURCE_TABLE_NAME
        )

        print(f"\nSkill table columns: {skill_cols}", flush=True)
        print(f"\nSource table columns: {source_cols}", flush=True)

        if SKILL_RECRUIT_KEY_COL not in skill_cols:
            raise ValueError(f"Missing column in skill table: {SKILL_RECRUIT_KEY_COL}")

        if SOURCE_PLAYER_KEY_COL not in source_cols:
            raise ValueError(f"Missing column in source table: {SOURCE_PLAYER_KEY_COL}")

        if SOURCE_FULL_NAME_COL not in source_cols:
            raise ValueError(f"Missing column in source table: {SOURCE_FULL_NAME_COL}")

        if "full_name" not in skill_cols:
            print("\nAdding full_name column to skill ratings table...", flush=True)
            con.execute(f"""
                ALTER TABLE {skill_table_ref}
                ADD COLUMN full_name VARCHAR
            """)
        else:
            print("\nfull_name column already exists. Updating it...", flush=True)

        before_count = con.execute(f"""
            SELECT COUNT(*)
            FROM {skill_table_ref}
            WHERE full_name IS NOT NULL
        """).fetchone()[0]

        print(f"Rows with full_name before update: {before_count:,}", flush=True)

        print("\nUpdating full_name by skill.recruit_key -> source.player_key...", flush=True)

        con.execute("BEGIN TRANSACTION")

        con.execute(f"""
            UPDATE {skill_table_ref} AS skill
            SET full_name = src.full_name
            FROM (
                SELECT
                    CAST({quote_ident(SOURCE_PLAYER_KEY_COL)} AS VARCHAR) AS player_key_str,
                    MAX({quote_ident(SOURCE_FULL_NAME_COL)}) AS full_name
                FROM {source_table_ref}
                WHERE {quote_ident(SOURCE_PLAYER_KEY_COL)} IS NOT NULL
                GROUP BY CAST({quote_ident(SOURCE_PLAYER_KEY_COL)} AS VARCHAR)
            ) AS src
            WHERE regexp_replace(
                CAST(skill.{quote_ident(SKILL_RECRUIT_KEY_COL)} AS VARCHAR),
                '_fallback$',
                ''
            ) = src.player_key_str
        """)

        con.execute("COMMIT")

        after_count = con.execute(f"""
            SELECT COUNT(*)
            FROM {skill_table_ref}
            WHERE full_name IS NOT NULL
        """).fetchone()[0]

        total_rows = con.execute(f"""
            SELECT COUNT(*)
            FROM {skill_table_ref}
        """).fetchone()[0]

        unmatched_count = con.execute(f"""
            SELECT COUNT(*)
            FROM {skill_table_ref}
            WHERE full_name IS NULL
        """).fetchone()[0]

        print("\nDone.", flush=True)
        print(f"Total rows: {total_rows:,}", flush=True)
        print(f"Rows with full_name before update: {before_count:,}", flush=True)
        print(f"Rows with full_name after update: {after_count:,}", flush=True)
        print(f"Rows still missing full_name: {unmatched_count:,}", flush=True)

        print("\nExample matched rows:", flush=True)
        matched_examples = con.execute(f"""
            SELECT
                {quote_ident(SKILL_RECRUIT_KEY_COL)} AS recruit_key,
                full_name
            FROM {skill_table_ref}
            WHERE full_name IS NOT NULL
            LIMIT 10
        """).fetchdf()
        print(matched_examples, flush=True)

        print("\nExample rows still missing full_name:", flush=True)
        missing_examples = con.execute(f"""
            SELECT {quote_ident(SKILL_RECRUIT_KEY_COL)} AS recruit_key
            FROM {skill_table_ref}
            WHERE full_name IS NULL
            LIMIT 20
        """).fetchdf()
        print(missing_examples, flush=True)

    except Exception as e:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass

        raise e

    finally:
        con.close()


if __name__ == "__main__":
    main()