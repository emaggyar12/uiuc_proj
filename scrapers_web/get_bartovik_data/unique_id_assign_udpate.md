# Updated Unique ID Assignment Plan

## Current Inputs

### Transfer Data

Use the cleaned raw transfer database:

```text
/Users/anirudhhaharsha/Desktop/sports_analytics_projects/Basketball/College Basketball Project/uiuc_proj/scrapers_web/get_bartovik_data/db_files/bv_final_transfers.db
```

Primary table:

```text
bv_final_transfers
```

Important columns:

```text
barttorvik_year
transfer_cycle_season
player_name
old_team
new_team
raw_team_1
raw_team_2
team_orientation
source_barttorvik_year
```

Interpretation:

```text
barttorvik_year = N means transfer movement before season N + 1
transfer_cycle_season = N + 1
```

The final transfer DB intentionally removes the duplicate pure `2026` page and keeps `trans_current_2026_27` rows relabeled as `barttorvik_year = 2026`.

### Player Stats Data

Use:

```text
/Users/anirudhhaharsha/Desktop/sports_analytics_projects/Basketball/College Basketball Project/uiuc_proj/db_files/bvt_allyears.db
```

Primary table:

```text
bvt_allyears
```

Important columns:

```text
year
player_name
team
```

## Core Principle

Do not identify two rows as the same player only because they share a name.

Same-name rows can be linked only through:

```text
1. same-school continuity
2. transfer movement evidence
3. manual/verified external evidence
```

If evidence is incomplete, conflicting, or ambiguous, leave `player_id` as `NULL` and flag the case for review.

## Normalized Fields

Before matching, create:

```text
name_norm
institution_norm
old_team_norm
new_team_norm
```

Normalization should:

```text
1. lowercase
2. strip leading/trailing whitespace
3. collapse repeated internal whitespace
4. remove punctuation that does not alter identity
5. standardize known school aliases through a controlled alias map
```

Examples:

```text
UConn -> connecticut
Connecticut Huskies -> connecticut
UNC -> north carolina
N.C. State -> n.c. state
Detroit -> detroit mercy, only if verified in this data context
```

Do not rely on fuzzy matching alone for school names.

## Transfer-Year Meaning

For a transfer row:

```text
barttorvik_year = N
transfer_cycle_season = N + 1
player_name = P
old_team = A
new_team = B
```

Interpret as:

```text
P moved from A to B before season N + 1
```

Expected stats linkage:

```text
source stats row:
  player_name = P
  team = A
  year <= N

destination stats row:
  player_name = P
  team = B
  year >= N + 1
```

Do not require strict consecutive years. Players may sit out, redshirt, miss seasons, or be absent from the stats table.

## Graph-Based Identity Resolution

Each stats row is a node:

```text
stats_row_id
year
name_norm
institution_norm
```

Create same-player edges only when evidence is strong. Connected components become candidate player identities.

## Same-School Continuity

For rows with the same:

```text
name_norm
institution_norm
```

Link rows across seasons if:

```text
1. there is no duplicate row for the same name_norm + institution_norm + year
2. the year gap is not too large
```

Suggested max same-school gap:

```text
6 years
```

Rows with the same name, same school, and same year should be treated as ambiguous and not automatically linked.

## Transfer Movement Links

For each transfer row:

```text
transfer_year = N
transfer_cycle_season = N + 1
name_norm = P
old_team_norm = A
new_team_norm = B
```

Find source candidates:

```text
stats.name_norm = P
stats.institution_norm = A
stats.year <= N
```

Choose the closest source row:

```text
max(stats.year) <= N
```

Find destination candidates:

```text
stats.name_norm = P
stats.institution_norm = B
stats.year >= N + 1
```

Choose the closest destination row:

```text
min(stats.year) >= N + 1
```

Create a same-player link only if:

```text
1. exactly one closest source row exists
2. exactly one closest destination row exists
3. no conflicting transfer path exists for the same name and time window
```

## Current 2026 Cycle

For `barttorvik_year = 2026`, the movement is before the 2027 season.

Because `bvt_allyears.db` currently only goes through 2026, many 2026 transfer destinations may not have a stats row yet.

Possible conservative behavior:

```text
1. If source row exists but destination row does not yet exist, attach the transfer row to the source player's component only.
2. Do not create a new future stats identity until 2027 stats exist.
3. Mark as source_only_current_cycle for review.
```

## Component Validation

Before assigning a `player_id`, validate each connected component.

Reject or mark as NULL if:

```text
1. component has more than one stats row in the same year
2. component changes schools without transfer evidence
3. same-school gap exceeds the allowed threshold
4. transfer rows imply conflicting movements
5. component includes ambiguous duplicate same-name/same-school/same-year rows
```

## Output Tables

Recommended output DBs:

```text
bvt_allyears_uniqueid.db
bv_final_transfers_uniqueid.db
```

Recommended tables:

```text
bvt_allyears_uniqueid
bv_final_transfers_uniqueid
same_player_links
identity_components
manual_review_cases
transfer_identity_links
```

Recommended `player_id` format:

```text
p_000001
p_000002
p_000003
```

Do not use names inside IDs.

## Manual Review Cases

Track unresolved cases in a manual review table with:

```text
review_case_id
reason
name_norm
candidate_stats_row_ids
candidate_years
candidate_institutions
candidate_transfer_rows
notes
```

Useful reasons:

```text
duplicate_same_name_school_year
multiple_source_candidates
multiple_destination_candidates
conflicting_transfer_paths
component_has_multiple_rows_same_year
institution_change_without_transfer
same_name_gap_too_large
unmatched_transfer_row
source_only_current_cycle
school_alias_missing
```

## Suggestions For More Robust Transfer Tracking

1. Build a controlled school alias table before assigning IDs.

   The biggest preventable mismatch risk is school naming. Examples like `Detroit` vs `Detroit Mercy`, `Houston Baptist` vs `Houston Christian`, `St. Francis NY` vs `Saint Francis Brooklyn`, and punctuation variants should be handled in a reviewed alias table.

2. Add a transfer-link confidence category.

   Suggested categories:

   ```text
   exact_name_exact_school_path
   exact_name_alias_school_path
   source_only_current_cycle
   unmatched_non_d1_or_juco
   ambiguous_same_name
   ```

3. Preserve both raw and interpreted transfer columns.

   Keep:

   ```text
   raw_team_1
   raw_team_2
   old_team
   new_team
   team_orientation
   ```

   This makes future debugging much easier.

4. Use player attributes as secondary validation, not primary matching.

   If available, compare:

   ```text
   height
   jersey number
   class year
   position
   hometown
   date of birth
   ```

   These should not override transfer evidence but can flag suspicious merges.

5. Add temporal sanity checks.

   A valid player identity should generally have plausible college career duration. Components spanning unusually many years should be flagged.

6. Store transfer rows that involve non-D1, JUCO, prep, D2, D3, or NAIA separately.

   These rows can still be useful, but they often cannot be fully matched against a D1-only stats table.

7. Consider using BartTorvik player URLs or hidden player keys if available.

   If player detail pages or embedded links expose a stable player key, that should become the preferred ID source over graph inference.

8. Compare against external transfer data.

   If another source has explicit previous/new school fields and player IDs, use it as validation for high-impact ambiguous cases.
