# Codex Work Context

This file records the data-building decisions and validation results that matter for future matching work. It is intentionally written as process documentation rather than a code dump.

## Current Canonical Data Files

- `data_dir/hs_complete.db`
  - Canonical cleaned 247 HS recruit file.
  - Main table: `hs_complete`.
  - Current row count after JUCO/duplicate cleanup and 2009 append: 13,740.
  - Contains one row per retained HS recruit after removing confirmed JUCO rows and moving old duplicate HS rows out of the active table.
- `data_dir/bvt_allyears_MAX.db`
  - Canonical BartTorvik all-years player stats file.
  - Main table: `bvt_allyears_MAX`.
  - Current row count: 81,562.
  - `barttorvik_trid` is an alias of BartTorvik `pid` in this file.
- `data_dir/bv_trans_compl_MAX.db`
  - Canonical BartTorvik transfer file.
  - Main table: `bv_trans_compl_MAX`.
  - Current row count: 16,897.
  - Non-null transfer `barttorvik_trid` values were validated to all exist as `pid` values in `bvt_allyears_MAX.db`.

## 247 HS Recruit Pipeline

- The HS recruit scrape starts from the 247 `recruits` API endpoint at `https://ipa.247sports.com/rdb/v1/recruits` with `sportKey=2` for men's basketball and a recruiting class year.
- That API provides player identity, class, rank/rating, position, hometown, and committed/signed/current school fields. It does not expose DOB in the cached recruit JSON checked so far.
- Height, weight, scouting report text, scouting-report evaluator, and skill ratings come from the player's 247 profile HTML/cache, not the recruit-list API payload.
- Some older 247 profile URLs require a `college-XXXXX` suffix. The scraper first tries the API profile URL, then uses search fallback when the base URL does not contain height/weight.
- JUCO rows were removed from the active HS table only when the profile page indicated a definite JUCO page using the specific JUCO details block/class, not merely because the word JUCO appeared somewhere on the page.
- After JUCO removal, repeated HS recruits were treated as multi-school HS cases. The most recent row with the most filled information stayed in `hs_complete`; older duplicate rows were moved to an `old_hs_duplicates` table.
- The active HS table should be treated as one retained row per recruit for ML input. The duplicate/removed tables exist as audit trails.

## BartTorvik All-Years Player Pipeline

- The historical BartTorvik player-stat CSV was renamed using `pstatheaders.xlsx`.
- `year_pulled` was validated to equal `year` before being removed from the final all-years CSV.
- Height and DOB handling were protected during CSV generation because spreadsheet applications can silently convert height-like strings into dates.
- `bvt_allyears_MAX.db` extends the original stat data with BartTorvik identity and source columns such as `barttorvik_trid`, `player_class`, `player_height`, `player_birth_date`, `player_hometown`, player/team/source URLs, and build notes.
- In the all-years MAX file, `barttorvik_trid` and `pid` are the same identifier.

## BartTorvik Transfer Pipeline

- BartTorvik transfer year `n` describes movement before season `n + 1`. Example: transfer cycle 2018 maps into the 2019 season context.
- The plain 2026 transfer request was rejected because it duplicated the current 2026-27 transfer set but with less information and bad orientation behavior. The canonical 2026 transfer rows come from the `trans_current_2026_27` request and are stored as `barttorvik_year = 2026`.
- The final cleaned transfer DB removed the bad plain-2026 rows and retained the current 2026-27 rows as 2026. Validation confirmed the row count dropped by exactly the size of the discarded duplicate request when that cleanup was performed.
- Transfer direction definition:
  - `raw_team_1` means origination / old team.
  - `raw_team_2` means destination / new team.
  - This definition applies to the current canonical transfer MAX DB, including the 2026 current rows.
- Transfer team URL year logic:
  - old team URL uses the transfer cycle year.
  - new team URL uses transfer cycle year + 1.
  - Player-stat URLs use the season context relevant to the player/team row, not a team URL pattern.
- The transfer MAX file still has null `barttorvik_trid` rows. A temporary synthetic-ID experiment for perfect transfer chains was undone because those null transfers first need to be checked against all-years `pid` candidates before inventing new IDs.

## Prompt Log

### 2026-05-31 16:16:44 CDT

Prompt summary:

- Explore whether 247 has DOB or other useful matching fields available through the same general data sources used by the HS scraper.
- If DOB is available, add it to `data_dir/hs_complete.db` without removing or altering existing columns.
- Start this documentation file and keep adding timestamped prompt/result summaries going forward.

Result:

- The cached 247 recruit-list API JSON did not expose DOB fields.
- DOB was found in profile-page JSON-LD as `birthDate` for a subset of cached 247 profile HTML files.
- Added new columns only to `data_dir/hs_complete.db`: `dob_247`, `dob_247_raw`, and `dob_247_source_profile_file`.
- Backed up the DB before editing as `data_dir/hs_complete.backup_before_247_dob_20260531_161644.db`.
- Validation:
  - `hs_complete` row count stayed 13,814 before and after.
  - 1,745 unique cached `year/player_key` DOB records were found.
  - 1,640 rows in `hs_complete` matched those cached DOB records.
  - No conflicting DOB values were found for the same `year/player_key`.
- Updated `scrapers_web/247_scrapers/common_247.py` and `scrapers_web/247_scrapers/scrape_247_hs.py` so future HS scrapes retain `dob_247` from profile JSON-LD.
- Also corrected the moved-path constants in `scrape_247_hs.py` so the script points at `scrapers_web/cache/hs`, `scrapers_web/outputs`, and `scrapers_web/247_scrapers/missing_data`.

### 2026-05-31 21:03:17 CDT

Prompt summary:

- Implement high-confidence matching from `data_dir/hs_complete.db` to `data_dir/bvt_allyears_MAX.db` in `data_dir/data_cleaning/hs_allyears_match.py`.
- Match using HS `full_name`, HS class year mapped to BartTorvik season `year + 1`, and HS `signed_school` against BartTorvik `player_name`, `year`, and `team`.
- Use DOB only as extra identity evidence when available. Do not require DOB for otherwise strong matches.
- Do not match 2026 HS recruits because they have not reached college yet.
- Do not edit any DB files; only write CSV outputs.

Result:

- Implemented a non-mutating matcher that reads the two canonical DB files and writes:
  - `data_dir/data_cleaning/hs_bv_match.csv`
  - `data_dir/data_cleaning/hs_bv_unmatched.csv`
- The matcher uses only the earliest BartTorvik row per `pid`, because the modeling target is performance straight out of high school.
- The hard year rule is `BartTorvik year = HS class year + 1`.
- HS class `2026` rows are retained in the left-join output but marked `ineligible_future_recruit`; none are matched.
- The matcher uses conservative fuzzy scoring with exact hard year constraint, normalized team/name strings, DOB rejection on conflicting DOBs, and a DOB-rescue tier for high-confidence DOB-supported cases.
- Added a one-to-one validation step so the same BartTorvik earliest row cannot be assigned to multiple HS rows; 4 duplicate BV assignments were dropped to `unmatched_duplicate_bv_conflict`.
- Validation from the final run:
  - Output rows: 13,814.
  - Matched rows: 4,974.
  - Unmatched/ineligible rows: 8,840.
  - 2026 matched rows: 0.
  - Hard year violations: 0.
  - Duplicate BartTorvik `pid` assignments: 0.
  - Match tiers: 4,966 `strict_name_team`, 8 `dob_rescue`, 631 `ineligible_future_recruit`, 4 `unmatched_duplicate_bv_conflict`, and 8,205 regular unmatched.

### 2026-05-31 21:06:55 CDT

Prompt summary:

- Shrink `data_dir/data_cleaning/hs_bv_match.csv` so it only contains the small set of human-review columns: 247 name, 247 signed team, 247 year, BartTorvik year, BartTorvik player name, and BartTorvik team.

Result:

- Rewrote `data_dir/data_cleaning/hs_bv_match.csv` in place with only:
  - `hs_year`
  - `hs_full_name`
  - `hs_signed_school`
  - `bv_player_name`
  - `bv_team`
  - `bv_year`
- Row count stayed 13,814.
- Non-null BartTorvik player names stayed 4,974, matching the previous matched-row count.
- `hs_bv_unmatched.csv` was not modified.

### 2026-05-31 21:25:48 CDT

Prompt summary:

- Resolve a 247 matching gap where some recruits do not have `signed_school` or `committed_school` in the API row but their recruiting-profile page shows an `Enrolled` institution.
- Example: Johni Broome has no signed/committed school in the API row but his recruiting profile shows he enrolled at Morehead State.
- Add only new DB columns to `data_dir/hs_complete.db`: the recruiting-profile URL and the enrolled institution.
- Keep recruiting-profile HTML cache separate from the existing main-profile cache.

Result:

- Added a repeatable enrichment script at `data_dir/data_cleaning/enrich_247_enrolled_institution.py`.
- Backed up the DB before editing as `data_dir/backups/hs_complete.backup_before_enrolled_institution_20260531_212548.db`.
- Cached recruiting-profile pages separately under `scrapers_web/cache/hs_recruiting_profiles`.
- Added exactly two new columns to `data_dir/hs_complete.db`:
  - `recruiting_profile_url_247`
  - `enrolled_institution_247`
- Validation:
  - Row count stayed 13,814.
  - Column count increased from 57 to 59.
  - Recruiting-profile URLs found: 10,766.
  - Enrolled institutions found: 8,064.
  - Rows with missing `signed_school` but non-null `enrolled_institution_247`: 3,135.
  - Johni Broome now has `recruiting_profile_url_247 = https://247sports.com/player/johni-broome-46085384/high-school-237032` and `enrolled_institution_247 = Morehead State`.

### 2026-05-31 22:09:49 CDT

Prompt summary:

- Rematch the HS recruits against BartTorvik using the same name/year/school matching logic, but use `enrolled_institution_247` as the school fallback when `signed_school` is missing.
- Add any newly matched recruits to the concise `data_dir/data_cleaning/hs_bv_match.csv`.
- Keep `hs_bv_match.csv` columns concise and unchanged.

Result:

- Updated `data_dir/data_cleaning/hs_allyears_match.py` so the school used for matching is `signed_school` first, falling back to `enrolled_institution_247` when signed school is blank.
- The matcher now writes the concise six-column `hs_bv_match.csv` directly:
  - `hs_year`
  - `hs_full_name`
  - `hs_signed_school`
  - `bv_player_name`
  - `bv_team`
  - `bv_year`
- Reran the matcher without editing any DB files.
- Validation:
  - `hs_bv_match.csv` row count stayed 13,814.
  - Non-null BartTorvik matches increased from 4,974 to 7,060.
  - Newly added matches: 2,086.
  - `hs_bv_unmatched.csv` decreased to 6,754 rows.
  - 2026 matched rows stayed 0.
  - Johni Broome now matches to `Johni Broome`, `Morehead St.`, BartTorvik year 2021.

### 2026-05-31 22:24:10 CDT

Prompt summary:

- Run a looser manual-review fuzzy pass on the remaining unmatched recruits.
- Do not add these candidates to `hs_bv_match.csv`.
- Only hard constraint: `BartTorvik year = HS year + 1`.
- Candidate threshold: at least 80 for name similarity and at least 80 for school/team similarity.
- Write candidates to `data_dir/data_cleaning/name_team_manualreview.csv`.

Result:

- Added a repeatable manual-review script at `data_dir/data_cleaning/build_name_team_manualreview.py`.
- Wrote `data_dir/data_cleaning/name_team_manualreview.csv`.
- No DB files were edited.

### 2026-06-02 21:45:00 CDT

Prompt summary:

- Create `data_dir/hs_bv_matched.db` containing matched recruits only.
- Each row must include the full source row from `data_dir/hs_complete.db` and the full source row from `data_dir/bvt_allyears_MAX.db`.
- Use `data_dir/data_cleaning/hs_bv_match.csv` only as the match map, since that CSV is intentionally concise and does not contain the full payload.

Result:

- Added repeatable builder script:
  - `data_dir/data_cleaning/build_hs_bv_matched_db.py`
- Created:
  - `data_dir/hs_bv_matched.db`
- Tables in the new DB:
  - `hs_bv_matched`
  - `hs_bv_matched_validation`
- Validation:
  - output rows: 7,900.
  - non-null `hs_full_name`: 7,900.
  - non-null `bv_player_name`: 7,900.
  - distinct `hs_player_key`: 7,900.
  - distinct `bv_pid`: 7,897.
  - column count: 136.
- The three repeated BartTorvik `pid` values came from the current match map, not from row multiplication during DB creation:
  - `51100`: `Ladarius Brewer` / `Ledarrius Brewer` -> `Ledarrius Brewer`.
  - `71118`: `Jalen Thomas` / `Josh Townley-Thomas` -> `Jalen Thomas`.
  - `32107`: `Isaac Thornton` / `Isaac Thorton` -> `Isaac Thornton`.
- Source DB files were read-only and were not edited.
- `hs_bv_match.csv` was not changed by this step; it remains concise with 13,814 rows and 7,060 non-null BartTorvik matches.
- Validation:
  - Candidate rows: 672.
  - Unique HS recruits represented: 660.
  - Minimum `name_score`: 80.0.
  - Minimum `team_score`: 80.0.
  - 2026 candidate rows: 0.
  - Hard year violations: 0.
  - Manual-review school source counts: 549 from `enrolled_institution_247`, 123 from `signed_school_fallback`.

### 2026-06-01 21:20:15 CDT

Prompt summary:

- Consume `match_flag` values added by the user in `name_team_manualreview.csv`.
- Rows with `match_flag = true` should be promoted to confirmed matches and removed from manual review.
- Rebuild matching around a new 247-side `signed_or_enrolled` field: `signed_school` first, falling back to `enrolled_institution_247`.
- Remove the hard year constraint to handle redshirt cases such as Dajuan Harris, while still excluding 2026 recruits.
- Use 90% confidence for name and team fuzzy matching.
- Do not edit any DB files.

Result:

- Added `data_dir/data_cleaning/rebuild_hs_bv_matches_signed_or_enrolled.py`.
- The script reads `hs_complete.db` and `bvt_allyears_MAX.db` read-only and writes only CSV outputs.
- It uses unique normalized BartTorvik team names as a blocking step, then expands back to the original BartTorvik rows for that team so player and team still come from the same source row.
- Final CSV state after the run:
  - `hs_bv_match.csv`: 13,814 rows, 8,370 non-null BartTorvik matches.
  - `hs_bv_unmatched.csv`: 5,444 rows.
  - `name_team_manualreview.csv`: 364 remaining rows, 0 remaining true flags.
  - 2026 matched rows: 0.
  - Dajuan Harris now matches to Kansas, BartTorvik year 2021.
- Important caveat: `name_team_manualreview.csv` initially had 167 true flags, but only 96 resolved into one-to-one source DB matches during this run. The script was then patched so future runs only remove true-flag rows that actually resolve; unresolved true flags would remain in manual review. No DB files were edited.

### 2026-06-01 21:56:29 CDT

Prompt summary:

- Examine the remaining unmatched HS recruits against unused/unmatched BartTorvik all-years player rows.
- Use judgment-heavy matching to identify likely matches and update the manual-review CSV accordingly.
- Do not edit any DB files.

Result:

- Added `data_dir/data_cleaning/assistant_suggest_manual_matches.py`.
- Created a safety copy of the previous manual review file:
  - `data_dir/data_cleaning/name_team_manualreview.backup_before_assistant_suggestions_20260601_215629.csv`
- The script reads `hs_bv_unmatched.csv`, `hs_bv_match.csv`, and `bvt_allyears_MAX.db` read-only.
- It only considers unused BartTorvik earliest-player rows that are not already present in confirmed matches.
- Matching logic uses the available basketball identity evidence:
  - normalized player name similarity,
  - school evidence from signed/enrolled/committed 247 fields,
  - exact DOB agreement when available,
  - plausible HS-to-college year windows, including redshirt-style delays.
- The script rewrote `data_dir/data_cleaning/name_team_manualreview.csv` with likely assistant-suggested matches marked in `match_flag`.
- Current validation:
  - `hs_bv_match.csv`: 13,814 rows, 8,314 non-null BartTorvik matches.
  - `hs_bv_unmatched.csv`: 5,500 rows.
  - `name_team_manualreview.csv`: 2,680 rows.
  - `match_flag = 1.0`: 2,315 assistant-suggested likely matches.
  - `match_flag` blank: 365 rows still left for manual review.
- No DB files were edited.

### 2026-06-01 22:22:00 CDT

Prompt summary:

- Investigate why Malique Ewin shows Florida State as signed/enrolled in the HS-to-BartTorvik matching CSVs even though his original post-HS path was JUCO/Ole Miss.
- Do not edit any CSV or DB files.

Result:

- No CSV or DB files were edited.
- Malique Ewin's `Florida State` value was already present in `hs_complete.db` and its backups before the DOB/enrolled-institution enrichment steps.
- The cached 247 API recruit rows for player key `46083137` in both 2022 and 2024 currently report:
  - `committedInstitution = Florida State`
  - `signedInstitution = Florida State`
  - `currentInstitution = Arkansas`
- The cached main 247 profile timeline shows the actual sequence:
  - Ole Miss enrolled: 2022-06-01.
  - South Florida transfer: 2023-06-05.
  - Florida State commit/sign/enroll: April-August 2024.
  - Arkansas transfer: 2025-04-15.
- The `enrich_247_enrolled_institution.py` fallback allowed `junior-college` and `prep` URLs as "recruiting profile" URLs. For Malique, this selected:
  - `https://247sports.com/player/malique-ewin-46083137/junior-college-313694`
  - That page's top commit/enrolled banner says Florida State, which reinforced the later JUCO/transfer destination rather than the original HS destination.
- Scope check in `hs_complete.db`:
  - 9,766 rows have a `high-school` recruiting profile URL.
  - 920 rows have a `junior-college` recruiting profile URL.
  - 78 rows have a `prep` recruiting profile URL.
  - 3,048 rows have no recruiting profile URL.
  - 998 total rows therefore use non-HS recruiting-profile URLs.
  - 504 of those have disagreement between `signed_school` and `enrolled_institution_247`.
- Current interpretation:
  - This is not random CSV corruption.
  - It is source/logic contamination from 247's current player object plus our fallback accepting non-HS profile pages.
  - The fix should treat `junior-college`/`prep` profile URLs separately, preferably by deriving original HS enrollment from timeline events around the recruit class year or by explicitly using institution-list `(HS)` links when the goal is HS matching.

### 2026-06-01 22:38:22 CDT

Prompt summary:

- Trace how `scrapers_web/outputs/actual_db_files/juco_rec.db` was made.
- Move strict JUCO rows out of the HS recruit mix if the existing JUCO DB was built with comparable logic.
- Remove those players from `data_dir/data_cleaning/name_team_manualreview.csv`, including rows where `match_flag` was true.
- Keep prep-profile rows in the HS dataset.

Result:

- Traced `juco_rec.db` to `scrapers_web/cleaning_utils/clean_hs_juco_duplicates.py`.
- The original JUCO DB was built from cached 247 HTML using confirmed JUCO evidence such as:
  - `details.is-juco`,
  - JUCO ranking labels/links,
  - `/junior-college-` profile links inside the relevant profile section,
  - and class-year agreement.
- The newly identified issue was a stricter URL-level marker in `data_dir/hs_complete.db`: rows whose `recruiting_profile_url_247` itself contains `/junior-college-`.
- Backups created:
  - `data_dir/backups/hs_complete.backup_before_strict_juco_move_20260601_223822.db`
  - `scrapers_web/outputs/actual_db_files/backups/juco_rec.backup_before_strict_juco_append_20260601_223822.db`
  - `data_dir/data_cleaning/name_team_manualreview.backup_before_strict_juco_removal_20260601_223822.csv`
- Moved 920 strict `/junior-college-` rows from `data_dir/hs_complete.db` into `scrapers_web/outputs/actual_db_files/juco_rec.db`.
- Added those rows to both `juco_recruits` and `juco_detection_audit` with `juco_evidence = recruiting_profile_url_247_junior_college`.
- Validation:
  - `data_dir/hs_complete.db` went from 13,814 to 12,894 rows.
  - Strict `/junior-college-` rows remaining in HS: 0.
  - Prep rows remaining in HS: 78.
  - `juco_rec.db` went from 1,162 to 2,082 rows.
  - `juco_detection_audit` went from 1,162 to 2,082 rows.
  - Malique Ewin is no longer in `data_dir/hs_complete.db`.
  - Malique Ewin is now in `juco_rec.db`.
  - `name_team_manualreview.csv` went from 2,680 to 2,431 rows.
  - Manual-review rows removed for strict JUCO names: 249.
  - Removed manual-review rows with true flags: 187.

### 2026-06-01 22:47:00 CDT

Prompt summary:

- Report how many BartTorvik transfers remain unmatched/unidentified in `data_dir/bv_trans_compl_MAX.db`.
- Find where those unmatched transfers are stored.
- Do not edit any files.

Result:

- No files were edited.
- Canonical current transfer MAX DB:
  - `data_dir/bv_trans_compl_MAX.db`
  - mirrored copy with the same counts: `scrapers_web/get_bartovik_data/db_files/bv_trans_compl_MAX.db`
- Main table:
  - `bv_trans_compl_MAX`
- The current unmatched/unidentified transfer representation is `barttorvik_trid IS NULL` inside the main table, not a separate current unmatched table.
- Counts:
  - total transfer rows: 16,897.
  - non-null `barttorvik_trid`: 11,683.
  - null `barttorvik_trid`: 5,214.
  - distinct non-null `barttorvik_trid`: 8,941.
- Null `barttorvik_trid` breakdown:
  - 5,089 rows are `stats_merge_status = left_only` and `has_stats_enrichment = False`.
  - 125 rows are `stats_merge_status = both` but still have null `barttorvik_trid`; these are all 2026/current-2027 rows with limited future-season stats identity.
- Old unique-ID experiment DBs under `scrapers_web/get_bartovik_data/db_files/old_db/` contain `manual_review_cases`, but those are obsolete for current canonical work because they came from the abandoned unique-ID run and/or the older transfer orientation/2026 setup.

### 2026-06-02 21:13:45 CDT

Prompt summary:

- Move only true-flagged rows from `data_dir/data_cleaning/name_team_manualreview.csv` into `data_dir/data_cleaning/hs_bv_match.csv`.
- Remove those true rows from manual review.
- Do not touch DB files.

Result:

- Backups created:
  - `data_dir/data_cleaning/name_team_manualreview.backup_before_true_move_20260602_211345.csv`
  - `data_dir/data_cleaning/hs_bv_match.backup_before_true_move_20260602_211345.csv`
- Moved 2,300 true-ish `match_flag` rows from manual review to `hs_bv_match.csv`.
- `name_team_manualreview.csv` went from 2,431 to 131 rows.
- True-ish `match_flag` rows remaining in manual review: 0.
- `hs_bv_match.csv` went from 13,814 to 16,114 rows.
- Rows in `hs_bv_match.csv` with non-null `bv_player_name`/`bv_team`: 10,614.
- No DB files were edited.

### 2026-06-02 21:19:00 CDT

Prompt summary:

- Correct the prior manual-review move.
- Only rows where `match_flag` is the literal word `TRUE` should move to `hs_bv_match.csv`.
- Numeric `1` / `1.0` rows should stay in `name_team_manualreview.csv`.
- Do not edit DB files.

Result:

- First restored the previous mistaken move from backups:
  - `name_team_manualreview.csv` returned to 2,431 rows.
  - `hs_bv_match.csv` returned to 13,814 rows.
- Backups created before the corrected TRUE-only move:
  - `data_dir/data_cleaning/name_team_manualreview.backup_before_TRUE_only_move_20260602_211900.csv`
  - `data_dir/data_cleaning/hs_bv_match.backup_before_TRUE_only_move_20260602_211900.csv`
- Moved only literal `TRUE` rows:
  - TRUE rows moved: 110.
  - `name_team_manualreview.csv` went from 2,431 to 2,321 rows.
  - literal `TRUE` rows remaining in manual review: 0.
  - numeric `1` / `1.0` rows remaining in manual review: 2,190.
  - `hs_bv_match.csv` went from 13,814 to 13,924 rows.
  - rows with non-null `bv_player_name`: 8,424.
- No DB files were edited.

### 2026-06-02 21:26:06 CDT

Prompt summary:

- Correct the HS match CSV shape after the TRUE-only move.
- `hs_bv_match.csv` should not grow beyond the recruit universe.
- Remove JUCO rows from `hs_bv_match.csv` so it reflects the current `data_dir/hs_complete.db` size of 12,894 rows.
- Mark TRUE manual rows as matches by filling existing recruit rows, not appending new rows.
- Do not edit DB files.

Result:

- Backups created before rebuilding:
  - `data_dir/data_cleaning/hs_bv_match.backup_before_rebuild_12894_retry_20260602_212606.csv`
  - `data_dir/data_cleaning/name_team_manualreview.backup_before_rebuild_12894_retry_20260602_212606.csv`
- Rebuilt `hs_bv_match.csv` from the current `data_dir/hs_complete.db` HS universe.
- Final validation:
  - `hs_bv_match.csv` rows: 12,894.
  - `name_team_manualreview.csv` rows: 2,321.
  - literal `TRUE` rows remaining in manual review: 0.
  - numeric `1` / `1.0` rows remaining in manual review: 2,190.
  - literal TRUE manual rows available from the pre-move backup: 110.
  - literal TRUE rows applied as updates to existing HS rows: 110.
  - literal TRUE rows missing a current HS row: 0.
  - rows with non-null `bv_player_name`: 7,900.
  - matched rows missing `bv_year`: 0.
- No DB files were edited.

### 2026-06-02 21:55:49 CDT

Prompt summary:

- Add `hs_height_in` to `data_dir/hs_bv_matched.db`, derived from existing `hs_height`.
- Add `height_in` to `data_dir/hs_complete.db`, derived from existing `height`.
- Store backups in `data_dir/backups`.
- Do not touch any other columns or data rows.
- Continue documenting every prompt in this file using the existing summary structure.

Result:

- The `.db` files were confirmed to be DuckDB databases, not SQLite databases.
- Backups created before editing:
  - `data_dir/backups/hs_bv_matched.backup_before_height_inches_20260602.db`
  - `data_dir/backups/hs_complete.backup_before_height_inches_20260602.db`
- Added and populated:
  - `data_dir/hs_bv_matched.db`, table `hs_bv_matched`, new integer column `hs_height_in`.
  - `data_dir/hs_complete.db`, table `hs_complete`, new integer column `height_in`.
- Height parsing converts feet-inches strings such as `6-10` and `'6-5` into total inches. Non-height placeholders such as `-` remain null in the new columns.
- Validation:
  - `hs_bv_matched` row count stayed 7,900.
  - `hs_bv_matched` column count increased from 136 to 137.
  - `hs_height_in` non-null rows: 7,797.
  - `hs_bv_matched_validation` row count stayed 6 and its data matched the backup exactly.
  - `hs_complete` row count stayed 12,894.
  - `hs_complete` column count increased from 59 to 60.
  - `height_in` non-null rows: 12,743.
  - `scouting_report_evaluator_parse` row count stayed 1,077 and its data matched the backup exactly.
  - Comparing current DBs to their backups while excluding only the newly added columns showed zero differences in all pre-existing columns.

### 2026-06-02 22:11:25 CDT

Prompt summary:

- Review `models_dir/catboost_trials.py`, a basic CatBoost/Optuna model intended to predict college `bv_role` playtype probabilities from high-school recruit numerical and categorical features.
- Identify drastic modeling or implementation mistakes.
- Explain how the 2024/2025 test dataframe should be used and whether Optuna requires a test dataframe.
- Do not directly edit model logic; only insert comments if useful.
- Continue documenting each prompt in this file.

Result:

- Reviewed `models_dir/catboost_trials.py` and inspected `data_dir/hs_bv_matched.db`.
- Added review-only comments to `models_dir/catboost_trials.py`; no executable model logic was changed.
- Key finding: the script currently splits on `df["year"]`, but `hs_bv_matched` has `hs_year` and `bv_year`, not `year`, so the script should fail before training until that is corrected.
- Data inspection:
  - `hs_bv_matched` rows: 7,900.
  - Target column `bv_role` exists.
  - `bv_role` has 8 non-null classes plus 5 null rows.
  - `hs_height_in` non-null rows: 7,797.
  - `hs_stars`, `hs_rating`, `hs_national_rank`, and `hs_position_rank` are each non-null for 5,396 rows.
  - Found 8 rows where `bv_year < hs_year` and 28 rows where `bv_year > hs_year + 3`, suggesting some match-timing outliers should be filtered or reviewed before modeling.
- Guidance recorded in code comments and discussed:
  - Filter out null `bv_role` rows before training.
  - Split by `hs_year` for recruit forecasting, not by a nonexistent `year` column.
  - Optuna does not require a test dataframe; it should tune on train/validation only.
  - Keep 2024/2025 as untouched holdout data and evaluate the final selected model once, with caution that 2025/2026 labels may be current/incomplete.
  - The current script prints best parameters but does not yet refit/save a final model or evaluate the test dataframe.

### 2026-06-02 22:16:04 CDT

Prompt summary:

- Implement the final review comment in the CatBoost/Optuna playtype model.
- Specifically, after Optuna tuning, refit a final model, evaluate the held-out test dataframe once, and save the model plus class-probability column order.
- The user had renamed/fixed the model file, and requested that the code not be run.

Result:

- Found the current model script at `models_dir/catboost_baseline_trials.py`; `models_dir/catboost_trials.py` no longer existed.
- Did not run or compile the training script, per user request.
- Updated `models_dir/catboost_baseline_trials.py` to:
  - create `test_df` from `hs_year` 2024-2025.
  - use `hs_year` 2022-2023 as validation.
  - keep `hs_year` 2010-2021 as training.
  - refit a final CatBoost model on train + validation rows using `study.best_params`.
  - evaluate final model log loss once on `test_df` when non-empty.
  - save the final model to `models_dir/artifacts/catboost_baseline_playtype_model.cbm`.
  - save metadata to `models_dir/artifacts/catboost_baseline_playtype_metadata.json`, including target column, feature columns, categorical features, class order for probability outputs, best validation log loss, test log loss, best parameters, final parameters, split year ranges, and split row counts.
- Added safe JSON casting for class labels and log-loss values.

### 2026-06-02 22:29:59 CDT

Prompt summary:

- Interpret the completed CatBoost/Optuna run results:
  - best validation log loss: 1.3579014922404222.
  - test log loss: 1.3266202224846795.
  - saved model and metadata artifact paths.
- Explain what the scores mean for high-school recruit to college playtype probability prediction.

Result:

- Read `models_dir/artifacts/catboost_baseline_playtype_metadata.json`.
- Confirmed model setup:
  - target: `bv_role`.
  - features: `hs_year`, `hs_position`, `hs_height_in`, `hs_weight`, `hs_stars`, `hs_rating`, `hs_national_rank`, `hs_position_rank`.
  - class order: `C`, `Combo G`, `PF/C`, `Pure PG`, `Scoring PG`, `Stretch 4`, `Wing F`, `Wing G`.
  - train rows: 5,713 from HS years 2010-2021.
  - validation rows: 1,195 from HS years 2022-2023.
  - test rows: 987 from HS years 2024-2025.
- Interpretation:
  - Both validation and test log loss are far better than an uninformed uniform 8-class log loss of about 2.079.
  - Test log loss being slightly better than validation log loss suggests no obvious validation overfit in this run.
  - The best model is a conservative low-learning-rate, shallow-tree model: 2,256 iterations, learning rate about 0.0114, depth 4.
- Additional saved-model diagnostics on the 2024-2025 test split:
  - test accuracy: 47.0%.
  - top-2 accuracy: 72.0%.
  - average max predicted probability: 48.4%.
  - strongest recall: `C` at 86.5% and `Wing G` at 77.6%.
  - weakest recall: `Pure PG` at 0.0%, `Stretch 4` at 3.5%, and `PF/C` at 11.6%.
  - common confusions included `Scoring PG -> Combo G`, `Combo G -> Wing G`, `PF/C -> C`, and `Stretch 4` split across `Wing G`, `Wing F`, and `C`.
- Recommendation:
  - Treat the current model as a useful baseline probability model, not a final classifier.
  - Next improvements should focus on class imbalance, playtype granularity, calibration, confusion analysis, and stronger recruit/team-context features.

### 2026-06-02 22:36:40 CDT

Prompt summary:

- Explain whether CatBoost automatically ignores non-meaningful features and whether rerunning without `hs_year` is worth trying.
- Use the saved baseline CatBoost model to run inference from `models_dir/catboost_baseline_inference.py`.
- Write top-3 predicted college playtype roles for each player in the inference dataframe to `models_dir/outputs/baseline`.

Result:

- Explained that CatBoost can learn to mostly ignore weak features, but features are not literally thrown out automatically; noisy, leaky, or time-shift features can still affect splits and probability calibration.
- Recommended trying a no-year rerun as a valid ablation because `hs_year` may capture era/data-coverage effects rather than player talent.
- Replaced the inference stub at `models_dir/catboost_baseline_inference.py` with a complete reproducible inference script.
- The script now:
  - reads `data_dir/hs_complete.db` in read-only mode.
  - aliases HS columns to the exact feature names expected by the trained model.
  - loads `models_dir/artifacts/catboost_baseline_playtype_model.cbm`.
  - validates saved metadata class order against the model class order.
  - writes top-3 predicted roles/probabilities plus all class probabilities.
- Created inference output:
  - `models_dir/outputs/baseline/catboost_baseline_top3_predictions.csv`.
- Validation:
  - rows scored: 12,894.
  - output shape: 12,894 rows by 27 columns.
  - probability row sums ranged from approximately 1.0 to 1.0.
  - top predicted role counts:
    - `Wing G`: 4,413.
    - `C`: 2,858.
    - `Combo G`: 2,356.
    - `Wing F`: 1,211.
    - `Scoring PG`: 1,079.
    - `PF/C`: 877.
    - `Stretch 4`: 87.
    - `Pure PG`: 13.

### 2026-06-03 20:18:53 CDT

Prompt summary:

- Scrape and append the missing 2009 247 HS recruit class only.
- Do not scrape or modify 2010+ HS rows.
- Cache 2009 main profile HTML under `scrapers_web/cache/hs` and recruiting-profile HTML separately under `scrapers_web/cache/hs_recruiting_profiles`.
- Deposit confirmed 2009 JUCO rows into `scrapers_web/outputs/actual_db_files/juco_rec.db`.
- Append only non-JUCO 2009 HS recruits to `data_dir/hs_complete.db`.
- Store `hs_complete.db` backups in `data_dir/backups`.
- Try to capture scouting reports and skill ratings using the same style as previous 247 scrapers.
- Document the work in this file.

Result:

- Added a dedicated 2009-only append script:
  - `scrapers_web/247_scrapers/scrape_247_hs_2009_append.py`
- The script reuses the existing 247 API/profile parsing helpers and intentionally refuses to run if 2009 rows already exist in either live destination DB.
- Ran the script with network access after the first sandboxed attempt failed before any DB backup or append due to blocked DNS/network access while generating 247 request headers.
- 247 API scrape:
  - pages cached: 5.
  - raw 2009 recruit rows: 1,011.
  - duplicate `year/player_key` rows: 0.
- Main profile cache:
  - `scrapers_web/cache/hs/2009/profiles`: 1,011 cached HTML files.
  - `scrapers_web/cache/hs/2009/api`: 5 cached JSON files.
  - `scrapers_web/cache/hs/2009/resolved_urls`: not created because fallback search was not needed.
- Recruiting profile cache:
  - `scrapers_web/cache/hs_recruiting_profiles/2009`: 1,003 cached HTML files.
- 2009-only output files created:
  - `scrapers_web/outputs/hs_recruits_247_2009.db`
  - `scrapers_web/outputs/hs_recruit_dummy_2009.csv`
  - `scrapers_web/247_scrapers/missing_data/2009_missing_hw.csv`
- Backups created before live DB appends:
  - `data_dir/backups/hs_complete.backup_before_2009_append_20260603_201716.db`
  - `scrapers_web/outputs/actual_db_files/backups/juco_rec.backup_before_2009_append_20260603_201716.db`
- Appended rows:
  - 846 non-JUCO 2009 HS recruits appended to `data_dir/hs_complete.db`.
  - 165 confirmed 2009 JUCO rows appended to `scrapers_web/outputs/actual_db_files/juco_rec.db`.
  - 165 corresponding 2009 rows appended to `juco_detection_audit`.
- `data_dir/hs_complete.db` validation:
  - row count went from 12,894 to 13,740.
  - 2009 HS rows now in `hs_complete`: 846.
  - non-2009 row count stayed 12,894.
  - comparing current non-2009 rows to the pre-append backup showed zero differences in both directions.
  - duplicate `year/player_key` groups after append: 0.
  - 2009 HS height non-null rows: 846.
  - 2009 HS `height_in` non-null rows: 836.
  - 2009 HS DOB non-null rows: 70.
  - 2009 HS recruiting-profile URLs: 839.
  - 2009 HS enrolled institutions: 826.
- `juco_rec.db` validation:
  - row count went from 2,082 to 2,247.
  - 2009 JUCO rows now in `juco_recruits`: 165.
  - 2009 JUCO audit rows: 165.
  - comparing current non-2009 JUCO rows to the pre-append backup showed zero differences in both directions.
  - 2009 JUCO evidence counts:
    - 162 rows: `prospect_title_247sports_juco;ranking_link_juniorcollege;junior_college_profile_link;recruiting_profile_url_247_junior_college`.
    - 2 rows: `details.is-juco;recruiting_profile_url_247_junior_college`.
    - 1 row: `details.is-juco`.
- Scouting report and skill-rating outcome:
  - The 2009 cached profile pages contain `scouting-report` sections, but the content is the older `H.S. Athletic Background` block rather than the richer evaluation narrative used by the existing 2010-2026 extraction logic.
  - No 2009 pages contained the existing skill-rating list markup such as `section.skills`.
  - Therefore 2009 rows were appended with `has_scouting_report = False`, `scouting_report = NULL`, and `skill_rating = False`; no new `_appended` skill columns were needed.

### 2026-06-03 20:37:50 CDT

Prompt summary:

- Rerun HS-to-BartTorvik matching after the 2009 HS append.
- Only consider BartTorvik players not previously matched in `data_dir/hs_bv_matched.db`.
- For BartTorvik duplicate player-id rows, only use each player id's oldest row because the target is performance right out of high school.
- Match primarily by HS full name and signed-or-enrolled institution, using DOB as fallback/supporting evidence.
- Put potential matches in `data_dir/data_cleaning/name_team_manualreview.csv`.
- Put still-unmatched recruits in `data_dir/data_cleaning/hs_bv_unmatched.csv`.
- Append complete high-confidence rows to `data_dir/hs_bv_matched.db`; do not touch existing matched rows.

Result:

- Added repeatable second-round matcher:
  - `data_dir/data_cleaning/second_round_unused_bv_matching.py`
- The matcher reads:
  - `data_dir/hs_complete.db`
  - `data_dir/hs_bv_matched.db`
  - `data_dir/bvt_allyears_MAX.db`
- BartTorvik candidate restriction:
  - Built earliest BartTorvik row per non-null `pid`.
  - Excluded every `bv_pid` already present in `hs_bv_matched`.
  - Available unused earliest BartTorvik rows considered: 24,106.
- HS candidate universe:
  - Current HS rows: 13,740.
  - Existing matched rows before this pass: 7,900.
  - Current unmatched HS universe before this pass: 5,840.
  - 2026 recruits were retained in unmatched output but excluded from active matching.
- Backups created before writes:
  - `data_dir/backups/hs_bv_matched.backup_before_second_round_append_20260603_203551.db`
  - `data_dir/data_cleaning/name_team_manualreview.backup_before_second_round_20260603_203551.csv`
  - `data_dir/data_cleaning/hs_bv_unmatched.backup_before_second_round_20260603_203551.csv`
- Matching results:
  - Resolved one-to-one candidates: 858.
  - High-confidence auto matches appended to `hs_bv_matched`: 686.
  - Manual-review candidates added: 172.
  - Manual-review rows now: 2,493.
  - Keyed/manual rows from this second round: 172.
  - Still-unmatched rows now: 5,154.
  - Still-unmatched 2009 HS rows: 176.
  - 2026 ineligible future recruits in unmatched output: 631.
- `data_dir/hs_bv_matched.db` validation:
  - row count increased from 7,900 to 8,586.
  - exactly 686 rows were appended.
  - pre-existing 7,900 rows compared against the backup showed zero changed or removed rows.
  - overlap between newly appended `bv_pid` values and pre-existing matched `bv_pid` values: 0.
  - duplicate `hs_year/hs_player_key` groups in matched table: 0.
  - 2009 rows now in matched table: 670.
  - `hs_bv_matched_validation` was intentionally left unchanged because the user requested append-only behavior for the match DB.
- CSV output validation:
  - `name_team_manualreview.csv`: 2,493 rows by 18 columns.
  - `hs_bv_unmatched.csv`: 5,154 rows by 147 columns, preserving the previous full unmatched output shape.
- Correction during this run:
  - The first manual-review merge collapsed old unkeyed manual-review rows because older rows did not have `hs_year/hs_player_key/bv_pid/bv_year`.
  - Restored the old manual-review CSV from backup and re-appended the 172 new keyed candidate rows.
  - Patched the script so future manual-review deduplication only deduplicates rows where all key columns are present.

### 2026-06-03 20:41:08 CDT

Prompt summary:

- Clarify how the 686 second-round high-confidence matches were defined before treating them as final.
- Investigate why 16 appended matches were not 2009 recruits.

Result:

- Confirmed that the second-round script did not restrict auto-appends to 2009 recruits.
- The script considered all currently unmatched HS recruits, excluding 2026, against unused earliest BartTorvik player ids.
- High confidence was a heuristic score, not a calibrated probability:
  - `confidence = 0.58 * name_score + 0.37 * team_score + DOB/year bonuses`.
  - `+7` for exact DOB match.
  - `+3` for `bv_year - hs_year` of 0 or 1.
  - `+1` for year gap of 2 or 3.
  - Auto append required `confidence >= 95` and an auto tier such as very strong name/team or DOB-supported matching.
- The 16 non-2009 appended rows were pulled because they were unmatched HS rows from prior passes and had unused BartTorvik pids with strong name/team evidence and plausible year gaps.
- Important interpretation:
  - The 16 non-2009 rows should be treated cautiously because the fact that prior passes did not match them is negative evidence.
  - A stricter follow-up policy would be to keep automatic appends limited to 2009, and send non-2009 second-round candidates to manual review unless they have exact DOB support and unambiguous name/team evidence.

### 2026-06-03 21:06:57 CDT

Prompt summary:

- Review the two non-baseline model implementations in `models_dir`:
  - scouting-report transformer model.
  - structured + scouting-report + skill-rating model.
- Create `artifacts`, `outputs`, and `scripts` directories for model folders that do not already have them.
- If no significant issues are found, run both models one after another and run 2026 inference into the proper output directories.
- If significant issues are found, report them immediately and do not run model training/inference.

Result:

- Created directories:
  - `models_dir/scouting_report_xfmr/artifacts`
  - `models_dir/scouting_report_xfmr/outputs`
  - `models_dir/scouting_report_xfmr/scripts`
  - `models_dir/skill_rating_xfmr/artifacts`
  - `models_dir/skill_rating_xfmr/outputs`
  - `models_dir/skill_rating_xfmr/scripts`
- Did not run model training or inference because significant code issues were found.
- Main blocker:
  - Both non-baseline scripts query `data_dir/hs_bv_matched.db`, whose columns are prefixed, e.g. `hs_scouting_report` and `hs_skill_athleticism`.
  - The scripts currently reference unprefixed names such as `scouting_report`, `skill_athleticism`, `skill_defender`, etc., so they would fail before training.
- Additional issues:
  - Neither non-baseline folder currently has a 2026 inference script.
  - If scripts are moved into the new `scripts` directories, their artifact path logic must change from `Path(__file__).resolve().parent / "artifacts"` to the model-folder artifact directory.
  - The 2026 inference source would be `data_dir/hs_complete.db`, where columns are unprefixed (`scouting_report`, `skill_athleticism`, etc.), while the training source `hs_bv_matched.db` is prefixed (`hs_scouting_report`, `hs_skill_athleticism`, etc.), so training and inference need explicit column aliasing to the same feature names.
  - Current 2026 HS rows have 135 non-empty scouting reports but 0 rows with `skill_rating = TRUE`; the combined skill/scouting model can still run, but the skill component will add no 2026-specific signal unless 2026 skill ratings are populated later.

### 2026-06-03 21:19:49 CDT

Prompt summary:

- Update the scouting-report model and skill+scouting model feature names so they match `data_dir/hs_bv_matched.db`.
- Include flags for scouting report availability, evaluator availability, and skill-rating availability.
- Add the scouting evaluator itself as a feature to the scouting-report model and include evaluator features in the combined skill+scouting model.
- Create 2026 inference scripts using the same style of identity/input columns as the baseline inference script.
- Explain that prior suggestions after item 4 were cut off.

Result:

- Replaced/corrected training scripts:
  - `models_dir/scouting_report_xfmr/scripts/catboost_scouting_rep.py`
  - `models_dir/skill_rating_xfmr/scripts/catboost_skill_scouting.py`
- Added inference scripts:
  - `models_dir/scouting_report_xfmr/scripts/catboost_scouting_inference.py`
  - `models_dir/skill_rating_xfmr/scripts/catboost_skill_scouting_inference.py`
- Training scripts now query `hs_bv_matched.db` with explicit aliases from prefixed source columns to normalized feature names:
  - `hs_scouting_report AS scouting_report`
  - `hs_scouting_report_evaluator_name AS scouting_report_evaluator_name`
  - `hs_skill_athleticism AS skill_athleticism`, etc.
- Added feature flags:
  - `has_scouting_report_text`
  - `has_scouting_report_evaluator`
  - `has_skill_ratings_available` for the skill+scouting model.
- Added `scouting_report_evaluator_name` as a categorical feature in both transformer-based models.
- Fixed artifact paths so scripts under `scripts/` write to the model folder's sibling `artifacts/` directory.
- Inference scripts read 2026 rows from `data_dir/hs_complete.db`, where HS columns are unprefixed, and build the same normalized feature columns expected by training.
- Syntax checks passed for all four scripts.
- Data availability check:
  - labeled rows in `hs_bv_matched.db` with non-null `bv_role`: 8,577.
  - labeled rows with non-empty scouting reports: 818.
  - labeled rows with evaluator names: 812.
  - labeled rows with skill ratings: 86.
  - 2026 inference rows in `hs_complete.db`: 631.
  - 2026 rows with non-empty scouting reports: 135.
  - 2026 rows with evaluator names: 134.
  - 2026 rows with skill ratings: 0.
- Did not run model training or inference because `sentence_transformers` is not installed locally:
  - import check failed with `ModuleNotFoundError: No module named 'sentence_transformers'`.

### 2026-06-03 22:42:50 CDT

Prompt summary:

- Downgrade `transformers` and run the scouting-report CatBoost model after the prior Torch/Transformers incompatibility.
- Keep the scouting evaluator logic present but commented out as a model feature because evaluator overlap may not hold for 2026.
- Train the scouting-report model, run 2026 inference, and report normal held-out test metrics.

Result:

- Downgraded `transformers` to `4.57.6`; `torch` remained at `2.2.2`.
- Added/kept environment guards in transformer model scripts to avoid TensorFlow/Keras import conflicts:
  - `USE_TF=0`
  - `TRANSFORMERS_NO_TF=1`
- Confirmed `SentenceTransformer` imports successfully after the downgrade.
- In `models_dir/scouting_report_xfmr/scripts/catboost_scouting_rep.py`, left evaluator parsing/metadata in place but commented evaluator feature usage out:
  - `EVALUATOR_COL` is commented out of `CAT_FEATURES`.
  - `EVALUATOR_COL` and `EVALUATOR_FLAG_COL` are commented out of `feature_cols`.
- Training completed for `models_dir/scouting_report_xfmr/scripts/catboost_scouting_rep.py`.
- Best validation log loss: `1.3570080461531382`.
- Best params:
  - `iterations`: `1187`
  - `learning_rate`: `0.03174556449427722`
  - `depth`: `4`
  - `l2_leaf_reg`: `2.4202281174435583`
  - `bagging_temperature`: `0.4734355286065646`
- Held-out 2024-2025 test metrics:
  - rows: `988`
  - log loss: `1.322872`
  - top-1 accuracy: `0.469636`
  - top-3 accuracy: `0.857287`
  - balanced accuracy: `0.360986`
  - average top-1 probability: `0.481419`
  - median top-1 probability: `0.435931`
- Saved artifacts:
  - `models_dir/scouting_report_xfmr/artifacts/catboost_playtype_with_scouting_embeddings.cbm`
  - `models_dir/scouting_report_xfmr/artifacts/catboost_playtype_with_scouting_embeddings_metadata.json`
  - `models_dir/scouting_report_xfmr/artifacts/scouting_embeddings_sentence-transformers__all-MiniLM-L6-v2.parquet`
- Ran 2026 inference successfully.
- Saved 631 scored 2026 rows to:
  - `models_dir/scouting_report_xfmr/outputs/catboost_scouting_2026_top3_predictions.csv`
- Notes:
  - The first training run needed network approval to download/cache `sentence-transformers/all-MiniLM-L6-v2`.
  - The first inference attempt stalled under sandboxed DNS because `sentence-transformers` performed Hugging Face metadata checks even after caching; it was terminated and rerun with network approval.
  - Non-fatal warnings seen: mixed Intel/LLVM OpenMP warning, Arrow CPU `sysctlbyname` permission warnings, and pandas fragmentation warnings during inference embedding-column insertion.

### 2026-06-04 19:16:27 CDT

Prompt summary:

- Clean `data_dir/data_cleaning/name_team_manualreview.csv` so manual review does not include players or BartTorvik rows already present in `data_dir/hs_bv_matched.db`.
- Do not edit any DB files.
- Validate that already-matched examples such as Anthony Davis, GG Jackson, and Zakai Zeigler are removed from manual review.

Result:

- Edited only `data_dir/data_cleaning/name_team_manualreview.csv`.
- Did not edit `data_dir/hs_bv_matched.db` or any other database.
- Removed manual-review rows when either side was already matched using strict validation checks:
  - exact `hs_player_key` / `hs_year` presence in the matched DB when keys were available.
  - exact `bv_pid` presence in the matched DB when keys were available.
  - normalized exact HS name plus normalized enrolled/signed institution match against matched DB identities.
  - normalized exact HS name plus exact DOB match when DOB was available.
  - normalized exact BV name plus normalized BV team match against matched DB identities.
  - normalized exact BV name plus exact BV DOB match when DOB was available.
- `name_team_manualreview.csv` row count changed from `2,493` to `1,456`.
- Preserved the original 18 CSV columns.
- Post-clean validation results:
  - `remaining_already_matched_violations`: `0`.
  - Anthony Davis remaining manual-review rows: `0`.
  - GG Jackson remaining manual-review rows: `0`.
  - Zakai Zeigler remaining manual-review rows: `0`.
  - `hs_bv_matched.db` remained at `8,586` rows.

### 2026-06-04 19:32:05 CDT

Prompt summary:

- Reformat/rebuild `data_dir/data_cleaning/name_team_manualreview.csv` so it is useful for reviewing unmatched recruits.
- The manual review CSV does not need to retain every old sparse row, but every remaining row must be actionable: when the user later says to move a recruit, the row should identify exact source rows from both `hs_complete.db` and `bvt_allyears_MAX.db` so all HS and BartTorvik columns can be expanded into `hs_bv_matched.db`.
- Do not edit DB files.

Result:

- Rebuilt `data_dir/data_cleaning/name_team_manualreview.csv` from the current unmatched HS pool and unused earliest BartTorvik pid pool using the second-round matching candidate logic.
- Replaced the mixed sparse/full manual-review file with keyed candidate rows only.
- Row count is now `172`.
- Preserved the existing 18-column CSV schema.
- All remaining rows now have:
  - `hs_year`
  - `hs_player_key`
  - `hs_signed_or_enrolled`
  - `bv_year`
  - `bv_pid`
  - `name_score`
  - `team_score`
  - `confidence`
  - `year_gap`
  - `match_tier`
- `match_flag` is blank for the rebuilt candidates; the user can mark rows for later movement.
- Validation results:
  - each manual row maps to exactly one source row in `hs_complete.db` by `(hs_year, hs_player_key)`: `0` failures.
  - each manual row maps to exactly one earliest BartTorvik pid source row in `bvt_allyears_MAX.db` by `(bv_year, bv_pid)`: `0` failures.
  - already-matched HS key violations against `hs_bv_matched.db`: `0`.
  - already-used BV pid violations against `hs_bv_matched.db`: `0`.
  - duplicate manual key rows by `(hs_year, hs_player_key, bv_year, bv_pid)`: `0`.
  - `hs_bv_matched.db` remained at `8,586` rows.

### 2026-06-04 19:44:03 CDT

Prompt summary:

- Correct the manual-review rebuild after the user clarified that the CSV should contain broad possible matches, not only one-to-one resolved candidates.
- Use the entire currently unmatched HS pool that can reasonably be matched to college data, explicitly including the newly scraped 2009 recruits.
- Match against only unmatched BartTorvik players, using each BartTorvik pid's oldest season row.
- Keep the CSV concise for human review, but retain source keys so a selected row can later be expanded into the full HS and full BartTorvik records for `hs_bv_matched.db`.

Result:

- Rebuilt `data_dir/data_cleaning/name_team_manualreview.csv` again as a broad manual-review candidate pool.
- Backed up the prior 172-row keyed file to:
  - `data_dir/data_cleaning/name_team_manualreview.backup_before_broad_rebuild_20260604_194109.csv`
- The previous 172-row result was too narrow because it used one-to-one candidate resolution; that was inappropriate for manual review.
- New candidate logic:
  - HS side: currently unmatched HS recruits from `hs_complete.db`, excluding 2026 because no completed college season should be expected yet.
  - Included 2009 HS recruits.
  - BV side: unused BartTorvik pids only, using the oldest season row per pid.
  - Primary evidence: fuzzy full-name match plus fuzzy signed/enrolled institution vs BV team match.
  - Allowed multiple possible BV candidates per HS recruit, up to 10 per recruit.
  - Candidate year gaps considered: `0` through `4`.
  - DOB is displayed and affects match tier/confidence, but DOB conflicts are not automatically discarded because some source DOBs appear defaulted or imperfect.
- Rebuilt CSV result:
  - candidate rows: `368`
  - unique HS recruits with candidates: `347`
  - eligible unmatched HS pool searched: `1,452`
  - 2009 candidate rows: `57`
- Validation results:
  - every row has non-null `(hs_year, hs_player_key, bv_year, bv_pid)`: `368`.
  - each row maps to exactly one source row in `hs_complete.db`: `0` failures.
  - each row maps to exactly one oldest-pid source row in `bvt_allyears_MAX.db`: `0` failures.
  - already-matched HS key violations: `0`.
  - already-used BV pid violations: `0`.
  - duplicate exact candidate rows: `0`.
  - `hs_bv_matched.db` remained at `8,586` rows.

### 2026-06-04 19:54:54 CDT

Prompt summary:

- Validate the usable unmatched HS pool using the user's equation:
  - matched HS rows + usable unmatched pool = `hs_complete` non-2026 rows.
- Rebuild `name_team_manualreview.csv` using institution matching when possible, then strict name-only fallback only when no institution signal is available.
- Keep 2009 recruits included.

Result:

- Pool validation:
  - `hs_complete` rows: `13,740`.
  - 2026 HS rows excluded from matching: `631`.
  - non-2026 HS rows: `13,109`.
  - `hs_bv_matched.db` rows / unique matched HS keys: `8,586`.
  - unmatched non-2026 HS pool: `4,523`.
  - validation equation passed: `8,586 + 4,523 = 13,109`.
- Root cause of the prior low `1,452` usable-pool number:
  - `1,452` only counted unmatched non-2026 recruits with signed/enrolled school fields.
  - It incorrectly excluded unmatched recruits that lacked signed/enrolled fields but had committed-school institution evidence or no institution evidence.
- Rebuilt `data_dir/data_cleaning/name_team_manualreview.csv` again with corrected candidate logic.
- Backed up prior broad file to:
  - `data_dir/data_cleaning/name_team_manualreview.backup_before_institution_plus_name_fallback_20260604_195000.csv`
- Candidate logic:
  - HS pool: all `4,523` unmatched non-2026 HS recruits.
  - institution-backed pass: used signed/enrolled institution first, then committed-school fields as fallback institution evidence.
  - name-only fallback: used only for HS rows with no signed/enrolled/committed institution signal.
  - did not use `current_school` as institution evidence because it can contain high schools, NBA teams, or other non-college values.
  - BV pool: unused BartTorvik pids only, using oldest season row per pid.
  - 2009 recruits included.
- Final manual-review CSV:
  - candidate rows: `2,337`.
  - unique HS recruits with candidates: `2,228`.
  - 2009 candidate rows: `68`.
  - all rows have non-null source keys `(hs_year, hs_player_key, bv_year, bv_pid)`.
- Validation results:
  - HS source lookup failures by `(hs_year, hs_player_key)`: `0`.
  - BV oldest-pid source lookup failures by `(bv_year, bv_pid)`: `0`.
  - already-matched HS violations: `0`.
  - already-used BV pid violations: `0`.
  - duplicate exact candidate rows: `0`.
  - `hs_bv_matched.db` remained at `8,586` rows.

### 2026-06-04 19:57:09 CDT

Prompt summary:

- Add a `dupe_flag` column to `data_dir/data_cleaning/name_team_manualreview.csv`.
- Mark duplicate HS recruit candidate groups so the user can see which recruits have multiple possible BV matches.
- Leave `match_flag` available and blank for user review decisions.

Result:

- Added `dupe_flag` to `name_team_manualreview.csv`.
- `dupe_flag = True` for every row where the same `(hs_year, hs_player_key)` appears more than once in the manual-review CSV.
- Row count remained `2,337`.
- `dupe_flag` true rows: `203`.
- Unique HS recruits with duplicate candidate rows: `94`.
- `match_flag` remained present and blank for all rows.

### 2026-06-04 20:28:11 CDT

Prompt summary:

- Investigate the confusing Anyeuri Castillo manual-review row without editing CSV files.
- Specifically explain why the row shows Kent State on one side but Appalachian State in `hs_signed_or_enrolled`.

Result:

- Did not edit CSV or DB files.
- `hs_complete.db` contains one HS row for `player_key = 46059298`.
- That row has:
  - `signed_school = Appalachian State`
  - `committed_school = Appalachian State`
  - `current_school = Kent State`
  - `enrolled_institution_247 = Kent State`
- Cached 247 profile/timeline confirms both facts:
  - signed/committed Appalachian State on `2018-11-15`.
  - enrolled Kent State on `2019-10-15`.
- BartTorvik has Anyeuri Castillo at Kent State in 2020 with pid `70250`.
- Interpretation:
  - This is not a simple scrape corruption; 247 itself records a signed/committed school and a later enrolled/current school.
  - For matching actual college appearance, Kent State is the stronger institution signal.
  - The manual-review row is confusing because `hs_signed_or_enrolled` currently prioritizes `signed_school` over `enrolled_institution_247`, so it displays Appalachian State even when enrolled/current is Kent State.

### 2026-06-04 20:33:23 CDT

Prompt summary:

- Investigate six name-only manual-review candidates without editing data files.
- Look only in BartTorvik data to determine whether an earlier BV year exists for the same player/name/pid.

Result:

- Did not edit CSV or DB files.
- Checked listed BV pids and exact normalized BV player names in `data_dir/bvt_allyears_MAX.db`.
- Findings:
  - Mark McLaughlin, pid `17294`: earliest BV row is Seattle `2011`; no earlier exact-name or same-pid BV row.
  - Shane Phillips, pid `21259`: earliest BV row is South Carolina `2012`; no earlier exact-name or same-pid BV row.
  - Tyler Summitt, pid `16661`: earliest BV row is Tennessee `2011`; no earlier exact-name or same-pid BV row.
  - C.J. Reese, pid `31567`: earliest BV row is Southeast Missouri St. `2014`; no earlier exact-name or same-pid BV row.
  - Cameron Neysmith, pid `38201`: earliest BV row is Kennesaw St. `2015`; no earlier exact-name or same-pid BV row.
  - Deontae Hawkins, pid `36639`: earliest BV row is Illinois St. `2015`; no earlier exact-name or same-pid BV row.
- Interpretation:
  - For these six cases, the delayed BV year is real in the current BV data rather than caused by selecting a later row for an existing pid.
  - Some of the BV rows list non-freshman classes in the first available BV season, e.g. Shane Phillips as `Jr` in 2012, which suggests prior non-D1/JUCO/redshirt/late-entry context may exist outside the current BV table.

### 2026-06-04 20:46:43 CDT

Prompt summary:

- Move only manual-review rows with `match_flag = True` from `data_dir/data_cleaning/name_team_manualreview.csv` into `data_dir/hs_bv_matched.db`.
- Expand each selected manual-review row back to the complete HS row plus complete BartTorvik row using the stored source keys.
- Remove successfully moved rows from the manual-review CSV.
- Keep ambiguous rows in the manual-review CSV.
- Put CSV backups under `data_dir/data_cleaning/backups`.

Result:

- Created backups before editing:
  - `data_dir/data_cleaning/backups/name_team_manualreview.backup_before_true_append_20260604_204500.csv`
  - `data_dir/backups/hs_bv_matched.backup_before_manual_true_append_20260604_204500.db`
- Found `2,109` true-like manual-review rows.
- Appended `2,071` complete expanded rows into `data_dir/hs_bv_matched.db`.
- Removed those `2,071` moved rows from `name_team_manualreview.csv`.
- Left `38` true-flagged rows in the manual-review CSV because they represented `19` duplicate BartTorvik `(year, pid)` conflicts where two HS recruit rows pointed to the same BV player.
- Final counts:
  - `hs_bv_matched.db`: `8,586` rows before, `10,657` rows after.
  - `name_team_manualreview.csv`: `2,337` rows before, `266` rows after.
  - loose root-level CSV backups in `data_dir/data_cleaning`: `0`.

Validation:

- Each appended HS row resolved one-to-one from `data_dir/hs_complete.db` by `(hs_year, hs_player_key)`.
- Each appended BV row resolved one-to-one from `data_dir/bvt_allyears_MAX.db` by `(bv_year, bv_pid)`.
- Manual display fields were checked against source rows before append.
- No appended row reused an already-matched HS recruit key.
- No appended row reused an already-matched BV pid.
- No duplicate HS recruit keys or duplicate BV pids were appended in this batch.

### 2026-06-04 20:54:43 CDT

Prompt summary:

- Put the remaining manual-review rows that map to duplicate BartTorvik pids into a single CSV.
- Keep rows from the same duplicate BV pid group right next to each other so the user can choose one.

Result:

- Created `data_dir/data_cleaning/duplicate_bv_pid_manualreview.csv`.
- Included only the remaining true-flagged manual-review rows where the same `(bv_year, bv_pid)` appears more than once.
- Wrote `38` rows across `19` duplicate BV pid groups.
- Sorted by `bv_year`, `bv_pid`, BV player name, HS year, and HS player key so each duplicate group is contiguous.
- Left `data_dir/data_cleaning/name_team_manualreview.csv` unchanged.

Validation:

- Confirmed the output CSV has `38` rows.
- Confirmed it has `19` groups.
- Confirmed every group has more than one row.
- Confirmed all rows for each duplicate BV key are adjacent.

### 2026-06-04 21:01:00 CDT

Prompt summary:

- Resolve the duplicate-BV-pid manual-review groups because the user determined the groups were matches.
- For each duplicate BV pid group, prefer the candidate where `bv_year = hs_year + 1`.
- If a duplicate group still has multiple candidates after that filter, select the expanded HS+BV row with the most non-null/non-empty source values.
- Insert the selected complete expanded rows into `data_dir/hs_bv_matched.db`.

Result:

- Created backups before editing:
  - `data_dir/backups/hs_bv_matched.backup_before_duplicate_pid_resolution_20260604_210039.db`
  - `data_dir/data_cleaning/backups/name_team_manualreview.backup_before_duplicate_pid_resolution_20260604_210039.csv`
  - `data_dir/data_cleaning/backups/duplicate_bv_pid_manualreview.backup_before_resolution_20260604_210039.csv`
- Resolved `19` duplicate BV pid groups.
- Inserted `19` complete expanded HS+BV rows into `data_dir/hs_bv_matched.db`.
- Reduced `data_dir/data_cleaning/duplicate_bv_pid_manualreview.csv` from `38` rows to the `19` selected winner rows and added selection metadata columns.
- Removed the `38` resolved true-flagged duplicate-conflict rows from `data_dir/data_cleaning/name_team_manualreview.csv`.
- Final counts:
  - `hs_bv_matched.db`: `10,657` rows before, `10,676` rows after.
  - `name_team_manualreview.csv`: `266` rows before, `228` rows after.
  - `duplicate_bv_pid_manualreview.csv`: `38` rows before, `19` rows after.

Validation:

- Confirmed all `19` selected BV pids appear exactly once in `hs_bv_matched.db`.
- Confirmed `name_team_manualreview.csv` has `0` remaining true-flagged rows.
- Confirmed `duplicate_bv_pid_manualreview.csv` now has `19` unique BV keys and no repeated BV key.
- Selection breakdown:
  - `17` groups selected by the `bv_year = hs_year + 1` rule.
  - `2` groups selected by the non-null/non-empty information count tiebreak because no candidate had `bv_year = hs_year + 1`.

### 2026-06-04 21:05:43 CDT

Prompt summary:

- Inspect `data_dir/data_cleaning/duplicate_bv_pid_manualreview.csv` for user-added last-column flags.
- Reinsert rows marked as "leave separate" back into `data_dir/data_cleaning/name_team_manualreview.csv`.

Result:

- Did not edit CSV or DB data files.
- Inspected the duplicate-pid CSV and found `19` rows.
- The physical last column is `selection_next_year_candidates`, which contains the prior metadata values `0`, `1`, or `2`.
- The prior blank note column `Unnamed: 19` is blank for all `19` rows.
- No saved value resembling "leave separate" was found in the CSV, so no rows were reinserted into `name_team_manualreview.csv`.

### 2026-06-04 21:09:29 CDT

Prompt summary:

- Use `data_dir/data_cleaning/potential_repeated_bv.csv` instead of `duplicate_bv_pid_manualreview.csv`.
- For rows marked `leave_both_separate`, reinsert the affected manual-review rows into `data_dir/data_cleaning/name_team_manualreview.csv`.

Result:

- Inspected `potential_repeated_bv.csv`.
- Found `14` BV-vs-BV pairs marked `leave_both_separate`.
- Found `1` BV-vs-BV pair marked `older_pid_kept_if_same_player`.
- Compared the current manual-review CSV against the pre-append backup for all BV pids involved in the `leave_both_separate` pairs.
- Current `name_team_manualreview.csv` already contained `32` of the `33` relevant prior manual-review rows.
- Reinserted the one missing row:
  - HS `2016`, `player_key = 46045420`, `Keaton Van Soelen`
  - BV `2018`, `pid = 51158`, `Keaton Van Soelen`, Air Force
- Cleared `match_flag` on the reinserted row to avoid making it look like a ready-to-append duplicate.
- Added note `reinserted_leave_both_separate_from_potential_repeated_bv` in `Unnamed: 19`.
- `name_team_manualreview.csv` row count increased from `228` to `229`.
- Left DB files unchanged.

Backup:

- `data_dir/data_cleaning/backups/name_team_manualreview.backup_before_reinsert_leave_separate_bv_20260604_210910.csv`

Validation:

- Confirmed the current manual-review CSV now has all `33` prior manual-review rows involving the `leave_both_separate` BV pids.
- Confirmed `0` missing rows versus `name_team_manualreview.backup_before_true_append_20260604_204500.csv` for those BV pids.

### 2026-06-04 21:11:12 CDT

Prompt summary:

- Enforce the year constraint in `data_dir/hs_bv_matched.db`.
- For every matched row where `bv_year != hs_year + 1`, remove it from `hs_bv_matched`.
- Insert those removed rows into a new table named `year_constraint_failure` in the same DuckDB file.
- List the highest-rated recruits that failed the year constraint.

Result:

- Created backup:
  - `data_dir/backups/hs_bv_matched.backup_before_year_constraint_move_20260604_211101.db`
- Created table `year_constraint_failure` with the same schema as `hs_bv_matched`.
- Moved `1,677` rows from `hs_bv_matched` into `year_constraint_failure`.
- `hs_bv_matched` row count changed from `10,676` to `8,999`.
- `year_constraint_failure` row count is `1,677`.

Validation:

- Confirmed `hs_bv_matched` has `0` remaining rows where `hs_year IS NULL`, `bv_year IS NULL`, or `bv_year != hs_year + 1`.
- Failure year-gap distribution:
  - `-11`: `1`
  - `-5`: `1`
  - `-3`: `1`
  - `-2`: `1`
  - `-1`: `4`
  - `0`: `74`
  - `2`: `1,343`
  - `3`: `186`
  - `4`: `63`
  - `5`: `3`

### 2026-06-04 23:27:47 CDT

Prompt summary:

- Rerun the `baseline_model` and `scouting_report_xfmr` playtype models using the updated `data_dir/hs_bv_matched.db`.
- Run inference on the 2026 class for both models.
- Add better logging artifacts: Optuna trial metrics, per-iteration metrics, split metrics, model params, confusion matrices, and practical ML summaries.
- Back up existing saved model artifacts before overwriting current artifact filenames.

Code changes:

- Updated `models_dir/baseline_model/scripts/catboost_baseline_trials.py`.
  - Fixed project/model path handling.
  - Added `optuna_trials.csv`, `optuna_iteration_metrics.csv`, `final_iteration_metrics.csv`, `metrics_by_split.csv`, `metrics_summary.json`.
  - Added train/valid/test confusion matrices and classification reports.
  - Added top-1 and top-3 accuracy alongside log loss.
- Updated `models_dir/baseline_model/scripts/catboost_baseline_inference.py`.
  - Fixed project/model path handling after folder move.
- Updated `models_dir/scouting_report_xfmr/scripts/catboost_scouting_rep.py`.
  - Added the same metrics/logging artifact outputs as baseline.
  - Kept scouting evaluator value commented out as a feature, but kept evaluator availability flag.
  - Added local-only SentenceTransformer loading using the cached local snapshot.
  - Rebuilt scouting embeddings for the updated filtered matched data.
- Updated `models_dir/scouting_report_xfmr/scripts/catboost_scouting_inference.py`.
  - Added local-only SentenceTransformer loading using metadata `embedding_model_path`.
  - Reworked embedding-column assembly to avoid pandas fragmentation warnings.

Backups:

- Baseline previous artifacts:
  - `models_dir/baseline_model/artifacts/backups/previous_artifacts_20260604_212507/catboost_baseline_playtype_model.cbm`
  - `models_dir/baseline_model/artifacts/backups/previous_artifacts_20260604_212507/catboost_baseline_playtype_metadata.json`
  - `models_dir/baseline_model/artifacts/backups/previous_artifacts_20260604_212507/model_params.txt`
- Scouting previous artifacts:
  - `models_dir/scouting_report_xfmr/artifacts/backups/previous_artifacts_20260604_212507/catboost_playtype_with_scouting_embeddings.cbm`
  - `models_dir/scouting_report_xfmr/artifacts/backups/previous_artifacts_20260604_212507/catboost_playtype_with_scouting_embeddings_metadata.json`
  - `models_dir/scouting_report_xfmr/artifacts/backups/previous_artifacts_20260604_212507/model_params.txt`

Training results:

- Baseline model:
  - labeled rows: `8,990`
  - train rows: `6,822`
  - valid rows: `1,117`
  - test rows: `1,051`
  - best validation log loss: `1.350719246824245`
  - test log loss: `1.3604667574646236`
  - test top-1 accuracy: `0.4548049476688868`
  - test top-3 accuracy: `0.8667935299714558`
  - best params: `iterations=1603`, `learning_rate=0.1208477527445918`, `depth=4`, `l2_leaf_reg=2.1474533743252815`, `bagging_temperature=0.8256178443374325`
- Scouting report embedding model:
  - labeled rows: `8,990`
  - train rows: `6,822`
  - valid rows: `1,117`
  - test rows: `1,051`
  - best validation log loss: `1.3355686527466277`
  - test log loss: `1.3468232248353262`
  - test top-1 accuracy: `0.46907706945765937`
  - test top-3 accuracy: `0.879162702188392`
  - best params: `iterations=1801`, `learning_rate=0.02817040664839508`, `depth=5`, `l2_leaf_reg=1.137628112577669`, `bagging_temperature=0.9836916216232724`

Inference outputs:

- Baseline 2026 predictions:
  - `models_dir/baseline_model/outputs/baseline/catboost_baseline_top3_predictions.csv`
  - rows scored: `631`
- Scouting 2026 predictions:
  - `models_dir/scouting_report_xfmr/outputs/catboost_scouting_2026_top3_predictions.csv`
  - rows scored: `631`

Notes:

- The first scouting training attempt failed because the old embedding cache did not cover the updated dataset and SentenceTransformer tried to check Hugging Face while network access was unavailable.
- Fixed by using the local cached snapshot path and rebuilding the embedding cache locally.
- DuckDB/Arrow emitted sandbox-related `sysctlbyname` warnings; these did not block training or inference.
- SentenceTransformer emitted an OpenMP duplicate-runtime warning; training and inference completed successfully despite it.
