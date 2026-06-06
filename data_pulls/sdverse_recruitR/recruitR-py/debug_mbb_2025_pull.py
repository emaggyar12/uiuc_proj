import pandas as pd

from recruitR.headers_gen import headers_gen
from recruitR.recruits import tfs_recruits
from recruitR.transfer_portal_player_rankings import (
    tfs_transfer_portal_player_rankings,
)
from recruitR.transfers import tfs_transfers


YEAR = 2025
SPORT_KEY = 2


def write_csv(df, path):
    df.to_csv(path, index=False)
    print(f"{path}: {len(df)} rows, {len(df.columns)} columns")


def main():
    headers = headers_gen()

    recruits_result = tfs_recruits(
        sport_key=SPORT_KEY,
        year=YEAR,
        page=1,
        page_size=250,
        headers=headers,
    )
    recruits_df = pd.DataFrame(recruits_result["players"])
    write_csv(recruits_df, f"mbb_recruits_{YEAR}.csv")

    transfers_result = tfs_transfers(
        sport_key=SPORT_KEY,
        year=YEAR,
        list_type=3,
        page=1,
        page_size=250,
        headers=headers,
    )
    transfers_df = pd.DataFrame(transfers_result["players"])
    write_csv(transfers_df, f"mbb_transfers_{YEAR}.csv")

    transfer_rankings_df = tfs_transfer_portal_player_rankings(
        sport_key=SPORT_KEY,
        year=YEAR,
        page_size=500,
        headers=headers,
    )
    write_csv(transfer_rankings_df, f"mbb_transfer_rankings_{YEAR}.csv")

    duke_commit_cols = [
        "committedInstitution.name",
        "committedInstitution.fullName",
        "committedInstitution.abbreviation",
    ]
    duke_commits_df = recruits_df[
        recruits_df[duke_commit_cols].astype(str).apply(
            lambda row: (
                row["committedInstitution.name"].casefold() == "duke"
                or row["committedInstitution.fullName"].casefold()
                == "duke blue devils"
                or row["committedInstitution.abbreviation"].casefold() == "duke"
            ),
            axis=1,
        )
    ]
    write_csv(duke_commits_df, f"duke_commits_{YEAR}.csv")


if __name__ == "__main__":
    main()
