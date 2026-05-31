import os
import duckdb

# path = "actual_db_files/hs_recruits_247_2010_2026_combined_complete.db"  # change this
# path = "actual_db_files/hs_recruit_skill_ratings.db"  # change this
path = "db_files/barttorvik_transfers_2018_2026_uniqueid.db"  # change this


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
    table_name = 'barttorvik_transfers_uniqueid'
    # table_name = 'hs_recruit_skill_ratings'

    # df = con.execute(f"""
    # SELECT year, full_name, skill_rating, {skill_type}
    # FROM {table_name}
    # WHERE {skill_type} IS NOT NULL
    # """).fetchdf()
    # print(df)

    columns = con.execute(f"""
        DESCRIBE {table_name}
    """).fetchdf()

    print(columns["column_name"].tolist())

    row_count = con.execute(f"""
        SELECT COUNT(*)
        FROM {table_name}
    """).fetchone()[0]

    print(row_count)

#     df = con.execute(f"""
#     SELECT player_name, barttorvik_year
#     FROM {table_name}
#     WHERE player_name  LIKE '%Mazara%'
#     """).fetchdf()
#     print(df)

