import pandas as pd

from recruitR.recruits import tfs_recruits
from recruitR.transfers import tfs_transfers
from recruitR.transfer_portal_player_rankings import tfs_transfer_portal_player_rankings


YEAR = 2025
SPORT_KEY = 2  # 2 = men's college basketball


# -----------------------------
# 1. Recruits for a given year
# -----------------------------
recruits_result = tfs_recruits(
    sport_key=SPORT_KEY,
    year=YEAR,
    page=1,
    page_size=250
)

recruits_df = pd.DataFrame(recruits_result["players"])
recruits_df.to_csv(f"mbb_recruits_{YEAR}.csv", index=False)


# -----------------------------
# 2. Transfers for a given year
# -----------------------------
# list_type:
# 1 = Latest
# 2 = Position
# 3 = Overall
transfers_result = tfs_transfers(
    sport_key=SPORT_KEY,
    year=YEAR,
    list_type=3,
    page=1,
    page_size=250
)

transfers_df = pd.DataFrame(transfers_result["players"])
transfers_df.to_csv(f"mbb_transfers_{YEAR}.csv", index=False)


# -----------------------------
# 3. Transfer portal rankings
# -----------------------------
transfer_rankings_df = tfs_transfer_portal_player_rankings(
    sport_key=SPORT_KEY,
    year=YEAR,
    page_size=500
)

transfer_rankings_df.to_csv(f"mbb_transfer_rankings_{YEAR}.csv", index=False)


# -----------------------------
# 4. Duke commits for a given year
# -----------------------------
# recruitR-py does not appear to have a direct "school commits" function.
# So this filters the recruit table for rows containing "Duke".
duke_commits_df = recruits_df[
    recruits_df.astype(str)
    .apply(lambda row: row.str.contains("Duke", case=False, na=False).any(), axis=1)
]

duke_commits_df.to_csv(f"duke_commits_{YEAR}.csv", index=False)