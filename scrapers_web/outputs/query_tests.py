import os
import duckdb

path = "actual_db_files/hs_complete.db"  # change this
# path = "actual_db_files/hs_recruit_skill_ratings.db"  # change this
# path = "actual_db_files/barttorvik_transfers_2018_2026_plus_current.db"  # change this


print("Current folder:", os.getcwd())
print("File exists:", os.path.exists(path))
print("File size:", os.path.getsize(path) if os.path.exists(path) else "missing")

con = duckdb.connect(path)

tables = con.execute("SHOW TABLES").fetchdf()
print("\nTables:")
print(tables)

if tables.empty:
    print("\nNo tables found in this DuckDB file.")
else:
    table_name = 'hs_complete'
    # table_name = 'hs_recruit_skill_ratings'
    # skill_type = 'skill_footwork'

    df = con.execute(f"""
    SELECT year, full_name
    FROM {table_name}
    WHERE scouting_report IS NOT NULL
        AND scouting_report_evaluator_name IS NULL
    """).fetchdf()
    print(df)

    columns = con.execute(f"""
        DESCRIBE {table_name}
    """).fetchdf()

    print(columns["column_name"].tolist())

    row_count = con.execute(f"""
        SELECT COUNT(*)
        FROM {table_name}
        WHERE scouting_report IS NOT NULL
    """).fetchone()[0]

    print(row_count)

