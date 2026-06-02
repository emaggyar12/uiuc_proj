# Codex Work Context

This file records the data-building decisions and validation results that matter for future matching work. It is intentionally written as process documentation rather than a code dump.

## Current Canonical Data Files

- `data_dir/hs_complete.db`
  - Canonical cleaned 247 HS recruit file.
  - Main table: `hs_complete`.
  - Current row count after JUCO/duplicate cleanup: 13,814.
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
