# recruitR-py Debug Handoff

## Original request

I want to use the `sportsdataverse/recruitR-py` package to pull college basketball recruiting and transfer data.

GitHub repo:

https://github.com/sportsdataverse/recruitR-py.git

## Goal

Write/debug Python code that can pull:

1. Recruits for a given year
2. Transfers for a given year
3. Commits for Duke for a given year

Preferably output each result to CSV so I can inspect whether the package is working.

## Intended package

```bash
pip install git+https://github.com/sportsdataverse/recruitR-py.git
```

or from a cloned local repo.

## Test script I was trying to run

```python
import pandas as pd

from recruitR.recruits import tfs_recruits
from recruitR.transfers import tfs_transfers
from recruitR.transfer_portal_player_rankings import tfs_transfer_portal_player_rankings

YEAR = 2025
SPORT_KEY = 2  # men's college basketball

# Recruits for a given year
recruits_result = tfs_recruits(
    sport_key=SPORT_KEY,
    year=YEAR,
    page=1,
    page_size=250
)

recruits_df = pd.DataFrame(recruits_result["players"])
recruits_df.to_csv(f"mbb_recruits_{YEAR}.csv", index=False)

# Transfers for a given year
transfers_result = tfs_transfers(
    sport_key=SPORT_KEY,
    year=YEAR,
    list_type=3,
    page=1,
    page_size=250
)

transfers_df = pd.DataFrame(transfers_result["players"])
transfers_df.to_csv(f"mbb_transfers_{YEAR}.csv", index=False)

# Transfer portal rankings
transfer_rankings_df = tfs_transfer_portal_player_rankings(
    sport_key=SPORT_KEY,
    year=YEAR,
    page_size=500
)

transfer_rankings_df.to_csv(f"mbb_transfer_rankings_{YEAR}.csv", index=False)

# Duke commits for a given year
# If there is no direct Duke commits function, filter recruits for Duke.
duke_commits_df = recruits_df[
    recruits_df.astype(str)
    .apply(lambda row: row.str.contains("Duke", case=False, na=False).any(), axis=1)
]

duke_commits_df.to_csv(f"duke_commits_{YEAR}.csv", index=False)
```

## Errors encountered

### Error 1

```text
ModuleNotFoundError: No module named 'config'
```

Traceback pointed to:

```python
from config import TFS_BASE_URL
```

inside:

```text
recruitR/coaches.py
```

Suggested fix:

```python
from recruitR.config import TFS_BASE_URL
```

or:

```python
from .config import TFS_BASE_URL
```

### Error 2

After patching that, another bad import appeared:

```text
ModuleNotFoundError: No module named 'headers_gen'
```

Traceback pointed to:

```python
from headers_gen import headers_gen
```

inside:

```text
recruitR/coaches.py
```

Suggested fix:

```python
from recruitR.headers_gen import headers_gen
```

or:

```python
from .headers_gen import headers_gen
```

## Likely issue

The package seems to use local imports as if files are being run from inside the `recruitR/` folder, but I am importing it as a package from a normal script. Codex should inspect the repo and convert internal imports to proper package-relative imports.

## What I need Codex to do

1. Fix the import errors cleanly across the package.
2. Find the correct function signatures for:
   - `tfs_recruits`
   - `tfs_transfers`
   - `tfs_transfer_portal_player_rankings`
   - any school/team commits function if one exists
3. Write one minimal working script that outputs:
   - `mbb_recruits_2025.csv`
   - `mbb_transfers_2025.csv`
   - `mbb_transfer_rankings_2025.csv`
   - `duke_commits_2025.csv`
4. If the repo is broken because 247Sports changed its API, explain that clearly and propose the smallest workaround.
