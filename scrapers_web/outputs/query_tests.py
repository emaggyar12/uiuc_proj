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

    columns = con.execute(f"""
        DESCRIBE {table_name}
    """).fetchdf()

    print(columns["column_name"].tolist())

    row_count = con.execute(f"""
        SELECT COUNT(*)
        FROM {table_name}
    """).fetchone()[0]

    df = con.execute(f"""
    SELECT year, full_Name, committed_school, signed_school
    FROM {table_name}
    WHERE full_name LIKE '%Dajuan Harris%'
    """).fetchdf()
    print(df)

    # df.to_csv('penis_balls.csv', index = False)

    print(row_count)

