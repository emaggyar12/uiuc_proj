# College Basketball Player Identity Resolution Logic

## Goal

Assign a stable `player_id` to rows in a season-level player statistics dataset when no true player identifier exists.

The input data consists of two datasets:

1. **Transfer data**
   - `year`
   - `player_name`
   - `previous_college`
   - `next_college`

   transfer data path: /Users/anirudhhaharsha/Desktop/sports_analytics_projects/Basketball/College Basketball Project/uiuc_proj/scrapers_web/get_bartovik_data/db_files/bv_final_transfers.db

   transfer output path with unique identifiers for each player (no matter how many times they transferred): /Users/anirudhhaharsha/Desktop/sports_analytics_projects/Basketball/College Basketball Project/uiuc_proj/scrapers_web/get_bartovik_data/db_files/barttorvik_transfers_2018_2026_uniqueid.db

2. **Player-season stats data**
   - `year`
   - `player_name`
   - `institution`
   - player statistics columns

   player data path: /Users/anirudhhaharsha/Desktop/sports_analytics_projects/Basketball/College Basketball Project/uiuc_proj/db_files/bvt_allyears.db

   player data output path: /Users/anirudhhaharsha/Desktop/sports_analytics_projects/Basketball/College Basketball Project/uiuc_proj/db_files/bvt_allyears_uniqueid.db

The same real player can appear in the stats data across multiple years and institutions. The same name can also belong to different real players. Therefore, the logic must be conservative.

The final output should assign a unique `player_id` only when the evidence is strong enough to identify rows as belonging to the same real player. If the algorithm cannot confidently determine that rows belong to the same real player, the `player_id` should be `NULL`.

## Scope Clarification

This document is not asking Codex to merge database files or combine rows.

The task is only to determine whether rows in the stats dataset refer to the same real player and then assign a stable `player_id` where the evidence is strong enough.

No rows should be deleted, combined, aggregated, or collapsed by this logic.

---

## Core Principle

Never decide that two player-season rows are the same real player only because they share the same name.

A shared name is only a candidate key. A player-season row should be connected to another player-season row only if there is deterministic movement evidence from the transfer data or clear same-institution continuity.

When the evidence is incomplete, conflicting, or ambiguous, assign `NULL` and leave the case for manual review.

---

## Required Normalized Fields

Before applying identity logic, create normalized versions of the key fields.

### For both datasets

Create:

```text
name_norm
institution_norm
```

For transfer data, create:

```text
previous_college_norm
next_college_norm
```

Recommended normalization:

1. Lowercase all text.
2. Strip leading/trailing whitespace.
3. Collapse repeated internal whitespace.
4. Remove punctuation that does not change identity meaning.
5. Standardize known school aliases using a manual alias map.

Examples:

```text
"UConn" -> "connecticut"
"Connecticut Huskies" -> "connecticut"
"UNC" -> "north carolina"
"North Carolina Tar Heels" -> "north carolina"
```

Do not rely only on fuzzy matching for institution names. Use a controlled alias map.

---

## Important Assumptions

These rules assume the transfer data represents the player's movement into a future institution.

A transfer row:

```text
transfer_year = Y
player_name = N
previous_college = A
next_college = B
```

means:

```text
A player named N moved from institution A to institution B around year Y.
```

The exact meaning of `transfer_year` may differ depending on the data source. Therefore, the matching logic should not require strictly consecutive years.

Instead, the algorithm should search future player-season rows where the same normalized name appears at the `next_college`.

---

# Identity Resolution Strategy

Use a graph-based approach.

Each player-season row in the stats dataset is a node.

A node is uniquely identified by:

```text
stats_row_id
```

Create conceptual same-player links between nodes only when two rows are believed to represent the same real player.

After all same-player links are created, connected components become candidate real-player groups.

Then assign a `player_id` to a connected component only if the component passes validation rules.

---

# Step 1: Create Candidate Nodes

For each row in the stats dataset, create:

```text
stats_row_id
year
name_norm
institution_norm
```

Each row starts as its own isolated node.

---

# Step 2: Same-Institution Continuity Edges

For each `name_norm`, group all stats rows with that name.

Within each name group, connect rows that have the same `institution_norm` if there is no ambiguity.

## Rule 2.1: Same name + same institution continuity

For a given `name_norm` and `institution_norm`, collect all rows:

```text
same_name_same_school_rows = stats rows where:
    name_norm = N
    institution_norm = S
```

If there is only one row for a given `(name_norm, institution_norm, year)`, then rows for that same `(name_norm, institution_norm)` across years can be connected.

This allows:

```text
John Smith, Duke, 2018
John Smith, Duke, 2019
John Smith, Duke, 2021
```

to be identified as the same real player even if 2020 is missing.

A missing year does not break continuity.

## Rule 2.2: Do not identify duplicated same-school-year rows automatically

If there are multiple rows with the same:

```text
name_norm
institution_norm
year
```

then mark those rows as ambiguous.

Do not create same-player links involving those duplicate rows.

Reason: the same-name/same-school/same-year duplicate may be a data duplication issue or two different people. It must be manually inspected.

---

# Step 3: Transfer Movement Edges

Use transfer rows to connect a previous-institution player-season node to a future next-institution player-season node.

For each transfer row:

```text
transfer_year = Y
name_norm = N
previous_college_norm = A
next_college_norm = B
```

find candidate source rows in the stats data:

```text
source_candidates:
    name_norm = N
    institution_norm = A
    year <= Y
```

find candidate destination rows in the stats data:

```text
destination_candidates:
    name_norm = N
    institution_norm = B
    year >= Y
```

Do not require `destination_year = Y + 1`.

A player may sit out, redshirt, transfer mid-cycle, miss a year, or the stats dataset may be incomplete.

---

## Rule 3.1: Use the closest valid previous source row

From `source_candidates`, choose the row with the largest year less than or equal to `transfer_year`.

```text
source = candidate with max(year) where year <= transfer_year
```

If there are multiple source rows tied for the same closest year, the transfer is ambiguous. Create no same-player link.

---

## Rule 3.2: Use the closest valid future destination row

From `destination_candidates`, choose the row with the smallest year greater than or equal to `transfer_year`.

```text
destination = candidate with min(year) where year >= transfer_year
```

If there are multiple destination rows tied for the same closest year, the transfer is ambiguous. Create no same-player link.

---

## Rule 3.3: Identify source and destination as the same real player only if both sides are unique

Create a same-player link only when:

```text
exactly one source row is selected
and
exactly one destination row is selected
```

Then identify these two rows as the same real player:

```text
source.stats_row_id <-> destination.stats_row_id
```

---

## Rule 3.4: Allow non-consecutive transfer matching

This should be valid:

```text
Stats:
2018, John Smith, School A
2021, John Smith, School B

Transfer:
2019, John Smith, School A, School B
```

The 2018 School A row and 2021 School B row can be connected because:

```text
School A is the previous institution
School B is the next institution
John Smith appears at School B in a future year
```

The gap does not invalidate the connection.

---

## Rule 3.5: Do not assign same-player identity if transfer evidence points to multiple possible players

If a transfer row maps to more than one possible source or destination row after applying the closest-year rule, do not create a same-player link.

Set involved unresolved rows aside for manual review.

---

# Step 4: Chained Transfer Logic

After transfer-supported same-player links are created, use connected components to chain identity across multiple seasons.

Example:

```text
Stats:
2018, John Smith, School A
2020, John Smith, School B
2022, John Smith, School C

Transfers:
2019, John Smith, School A, School B
2021, John Smith, School B, School C
```

Edges:

```text
2018 School A <-> 2020 School B
2020 School B <-> 2022 School C
```

Connected component:

```text
{2018 School A, 2020 School B, 2022 School C}
```

These rows receive the same `player_id`.

This should be handled naturally by graph connected components or union-find.

# Side Note:

The transfer data contains the current 2026-27 year and he 2027 season has not happened yet. To assign the unique identifier to players in the 2026-27 cycle, try to use the previous institution (ignoring the futuer one bcause that season has not happend) and the name as tools to identify (you still need strict validation though)


---

# Step 5: Prevent Bad Merges with Validation Rules

After creating same-player components, validate each component before assigning a `player_id`.

A component should receive a `player_id` only if all validation checks pass.

If any check fails, assign `NULL` to all rows in that component and flag the component for manual review.

---

## Validation Rule 5.1: One row maximum per player-year

A valid component cannot contain more than one stats row for the same year.

Invalid:

```text
2020, John Smith, Duke
2020, John Smith, Kentucky
```

Reason: one real player cannot have two season-level stat rows in the same season unless the dataset explicitly supports split-season rows. If split-season rows are possible, this rule must be adjusted.

Default behavior:

```text
If a component has more than one row in the same year, player_id = NULL.
```

---

## Validation Rule 5.2: Transfer path must explain institution changes

For every institution change inside a connected component, there must be a transfer row supporting that movement.

Same institution across different years does not need transfer evidence.

Institution changes do need transfer evidence.

Valid:

```text
2018, John Smith, School A
2020, John Smith, School B
```

only if transfer data contains:

```text
John Smith, School A -> School B
```

Invalid:

```text
2018, John Smith, School A
2020, John Smith, School B
```

if no transfer row connects School A to School B.

---

## Validation Rule 5.3: Do not identify distant same-name rows as the same player without evidence

If the only thing linking two rows is the same `name_norm`, do not identify as the same player them.

Example:

```text
2018, John Smith, School A
2026, John Smith, School A
```

This should not automatically receive the same `player_id` unless same-institution continuity rules justify it.

Recommended conservative rule:

Same-institution continuity is allowed across missing years, but only within a single uninterrupted institution component.

However, if the year gap is extremely large, apply a maximum same-school gap threshold.

Suggested default:

```text
max_same_school_gap = 6 years
```

So this is allowed:

```text
2018, John Smith, School A
2021, John Smith, School A
```

but this is not automatically allowed:

```text
2018, John Smith, School A
2026, John Smith, School A
```

because the gap is 8 years.

Rows beyond the threshold should get `NULL` unless transfer data or other reliable evidence links them.

---

## Validation Rule 5.4: Do not assign identity across conflicting transfer paths

If the transfer data implies conflicting movements for the same name and same time window, do not resolve automatically.

Example:

```text
2019, John Smith, School A -> School B
2019, John Smith, School A -> School C
```

If both School B and School C appear in future stats rows for John Smith, this is ambiguous.

Do not choose one identity path automatically.

Assign `NULL` to the affected unresolved rows and flag for manual review.

---

# Step 6: Assign Player IDs

After graph construction and validation:

For each connected component:

1. If the component has more than one row and passes validation:
   - assign one generated `player_id` to all rows in the component.
2. If the component has exactly one row:
   - assign a unique `player_id` only if the row is not ambiguous.
   - otherwise assign `NULL`.
3. If the component fails validation:
   - assign `NULL`.

Recommended `player_id` format:

```text
p_<zero_padded_integer>
```

Example:

```text
p_000001
p_000002
p_000003
```

Do not use player names inside the ID. Names can change, contain punctuation differences, or collide.

---

# Step 7: Manual Review Table

Create a separate review table for unresolved cases.

Recommended columns:

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

Possible `reason` values:

```text
duplicate_same_name_school_year
multiple_source_candidates
multiple_destination_candidates
conflicting_transfer_paths
component_has_multiple_rows_same_year
institution_change_without_transfer
same_name_gap_too_large
unmatched_transfer_row
```

---

# Concrete Decision Rules Summary

## Automatically identify rows as the same real player when:

### Case A: Same player, same school

Identify stats rows as the same real player if:

```text
same name_norm
same institution_norm
different years
no duplicate row for the same name_norm + institution_norm + year
year gap <= max_same_school_gap
```

Default:

```text
max_same_school_gap = 6
```

---

### Case B: Transfer-supported movement

Connect stats rows if a transfer row exists where:

```text
transfer.name_norm = stats.name_norm
transfer.previous_college_norm = source.institution_norm
transfer.next_college_norm = destination.institution_norm
source.year <= transfer.year
destination.year >= transfer.year
source is the closest previous source row
destination is the closest future destination row
source is unique
destination is unique
```

---

## Never automatically identify rows as the same player when:

1. The only evidence is the same name.
2. A player name appears in the same institution and same year multiple times.
3. A transfer row has multiple equally valid source rows.
4. A transfer row has multiple equally valid destination rows.
5. A component contains more than one row in the same year.
6. A component contains an institution change that is not supported by transfer data.
7. The same-name same-school gap exceeds `max_same_school_gap`.
8. Transfer rows conflict with each other.

---

# Recommended Implementation Outline

## Input tables

```text
stats_df
transfers_df
```

## Output tables

```text
stats_with_player_ids
manual_review_cases
same_player_links
identity_components
```

---

## Algorithm

```text
1. Normalize names and institution names in both datasets.

2. Create one graph node per stats row.

3. Detect duplicate stats rows with same:
   name_norm + institution_norm + year.
   Mark these rows as ambiguous.

4. Add same-institution same-player links:
   For each name_norm + institution_norm:
       Sort rows by year.
       Connect rows across years if:
           neither row is ambiguous
           year gap <= max_same_school_gap

5. Add transfer-supported same-player links:
   For each transfer row:
       Find source candidates:
           same name_norm
           institution_norm == previous_college_norm
           stats.year <= transfer.year

       Select source rows with max(stats.year).

       Find destination candidates:
           same name_norm
           institution_norm == next_college_norm
           stats.year >= transfer.year

       Select destination rows with min(stats.year).

       If exactly one source and exactly one destination:
           Add same-player link source <-> destination.
       Else:
           create manual review case.

6. Build connected components using graph traversal or union-find.

7. Validate each connected component:
       a. no more than one stats row per year
       b. all institution changes are supported by transfer evidence
       c. no conflicting transfer paths
       d. no same-school gap above threshold without external evidence

8. Assign player_id:
       If component passes validation:
           assign generated player_id
       Else:
           assign NULL and create manual review case

9. Export:
       stats_with_player_ids
       manual_review_cases
       same_player_links
       identity_components
```

---

# Example 1: Clear Transfer Match

## Stats

```text
stats_row_id | year | name        | institution
1            | 2018 | Ray Kasongo | Oregon
2            | 2020 | Ray Kasongo | Tennessee
```

## Transfer

```text
year | name        | previous_college | next_college
2019 | Ray Kasongo | Oregon           | Tennessee
```

## Result

```text
stats_row_id 1 and 2 receive the same player_id.
```

Reason:

```text
The player appears at the previous school before/at the transfer year
and appears at the next school after/at the transfer year.
```

---

# Example 2: Year Gap Is Allowed

## Stats

```text
2018 | John Smith | School A
2022 | John Smith | School B
```

## Transfer

```text
2019 | John Smith | School A -> School B
```

## Result

```text
Same player_id.
```

Reason:

```text
The destination year does not need to be consecutive.
```

---

# Example 3: Same Name, No Evidence

## Stats

```text
2018 | John Smith | School A
2026 | John Smith | School B
```

## Transfer

```text
No matching transfer row.
```

## Result

```text
player_id = NULL for the unresolved rows.
```

Reason:

```text
Same name alone is not enough evidence.
```

---

# Example 4: Same School, Reasonable Gap

## Stats

```text
2018 | John Smith | Duke
2019 | John Smith | Duke
2021 | John Smith | Duke
```

## Result

```text
Same player_id.
```

Reason:

```text
Same name, same institution, no duplicate same-school-year rows, and gap is within threshold.
```

---

# Example 5: Same School, Gap Too Large

## Stats

```text
2018 | John Smith | Duke
2026 | John Smith | Duke
```

## Result

```text
player_id = NULL unless other reliable evidence exists.
```

Reason:

```text
The same-name same-school gap exceeds max_same_school_gap.
```

---

# Example 6: Ambiguous Destination

## Stats

```text
2018 | John Smith | School A
2020 | John Smith | School B
2020 | John Smith | School B
```

## Transfer

```text
2019 | John Smith | School A -> School B
```

## Result

```text
No automatic player_id assignment for the ambiguous rows.
```

Reason:

```text
There are multiple destination rows in the closest valid destination year.
```

---

# Final Conservative Rule

When in doubt, do not assign a player ID.

The goal is not to maximize the number of automatic matches. The goal is to avoid incorrectly identifying two different players as the same person.

False negatives are acceptable because unresolved rows can be manually reviewed.

False positives are dangerous because they corrupt the player history and downstream modeling.
