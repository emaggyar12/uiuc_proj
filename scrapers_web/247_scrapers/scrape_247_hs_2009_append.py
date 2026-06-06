from __future__ import annotations

import concurrent.futures
import json
import re
import shutil
import sys
import time
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import duckdb
import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from common_247 import (
        SPORT_KEY_MBB,
        TFS_BASE_URL,
        PROJECT_ROOT,
        discover_247_profile_url,
        extract_profile_jsonld_person_fields,
        extract_scouting_report,
        fetch_text_cached,
        get_247_headers,
        normalize_profile_url,
        request_json,
    )
except ModuleNotFoundError:
    from .common_247 import (
        SPORT_KEY_MBB,
        TFS_BASE_URL,
        PROJECT_ROOT,
        discover_247_profile_url,
        extract_profile_jsonld_person_fields,
        extract_scouting_report,
        fetch_text_cached,
        get_247_headers,
        normalize_profile_url,
        request_json,
    )


YEAR = 2009
PAGE_SIZE = 250
MAX_WORKERS = 8
REQUEST_SLEEP_SECONDS = 0.15

CACHE_ROOT = PROJECT_ROOT / "scrapers_web" / "cache" / "hs"
RECRUITING_PROFILE_CACHE = PROJECT_ROOT / "scrapers_web" / "cache" / "hs_recruiting_profiles"
OUT_DIR = PROJECT_ROOT / "scrapers_web" / "outputs"
MISSING_DIR = PROJECT_ROOT / "scrapers_web" / "247_scrapers" / "missing_data"

DATA_DIR = PROJECT_ROOT / "data_dir"
HS_DB_PATH = DATA_DIR / "hs_complete.db"
HS_TABLE = "hs_complete"
DATA_BACKUP_DIR = DATA_DIR / "backups"

JUCO_DB_PATH = PROJECT_ROOT / "scrapers_web" / "outputs" / "actual_db_files" / "juco_rec.db"
JUCO_TABLE = "juco_recruits"
JUCO_AUDIT_TABLE = "juco_detection_audit"
JUCO_BACKUP_DIR = JUCO_DB_PATH.parent / "backups"

SKILL_COLS = [
    "skill_athleticism",
    "skill_defender",
    "skill_face_up_high_post_scorer",
    "skill_handle",
    "skill_leadership",
    "skill_low_post_scorer",
    "skill_passing",
    "skill_passing_vision",
    "skill_penetration_ability",
    "skill_physicality_motor",
    "skill_rebounding",
    "skill_shooter",
    "skill_size",
    "skill_versatility",
]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def pull_all_recruits(session: requests.Session) -> list[dict]:
    cache_dir = CACHE_ROOT / str(YEAR)
    all_players: list[dict] = []
    page = 1
    while True:
        data = request_json(
            session=session,
            url=TFS_BASE_URL + "recruits",
            params={
                "sportKey": SPORT_KEY_MBB,
                "year": YEAR,
                "page": page,
                "pageSize": PAGE_SIZE,
            },
            cache_path=cache_dir / "api" / f"recruits_page_{page}.json",
        )
        players = data.get("players", [])
        all_players.extend(players)
        pagination = data.get("pagination", {})
        print(
            f"HS API {YEAR} page {page}: {len(players)} rows "
            f"({len(all_players)}/{pagination.get('count', '?')})",
            flush=True,
        )
        if page >= int(pagination.get("pageCount", page)):
            break
        page += 1
    return all_players


def flatten_recruits(players: list[dict]) -> pd.DataFrame:
    df = pd.json_normalize(players)
    expected_cols = [
        "key",
        "cbs_Key",
        "firstName",
        "lastName",
        "profileUrl",
        "defaultAssetUrl",
        "primaryPosition",
        "compositeRating",
        "compositeStarRating",
        "compositeNationalRank",
        "compositePositionRank",
        "compositeStateRank",
        "homeTown.city",
        "homeTown.state",
        "committedInstitution.institutionKey",
        "committedInstitution.teamKey",
        "committedInstitution.cbsKey",
        "committedInstitution.name",
        "committedInstitution.abbreviation",
        "committedInstitution.fullName",
        "signedInstitution.institutionKey",
        "signedInstitution.teamKey",
        "signedInstitution.cbsKey",
        "signedInstitution.name",
        "signedInstitution.abbreviation",
        "signedInstitution.fullName",
        "currentInstitution.institutionKey",
        "currentInstitution.teamKey",
        "currentInstitution.cbsKey",
        "currentInstitution.name",
        "currentInstitution.abbreviation",
        "currentInstitution.fullName",
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None
    return df


def clean_skill_name(skill_name: str) -> str:
    skill_name = skill_name.strip().lower()
    skill_name = re.sub(r"[^a-z0-9]+", "_", skill_name).strip("_")
    return f"skill_{skill_name}"


def parse_skill_ratings_from_html(html: str) -> dict[str, object]:
    result: dict[str, object] = {"skill_rating": False}
    soup = BeautifulSoup(html, "html.parser")
    scouting_section = soup.select_one("section.scouting-report#evaluation")
    if scouting_section is None:
        return result
    skills_section = scouting_section.select_one("section.skills")
    if skills_section is None:
        return result
    for item in skills_section.select("li"):
        text_tag = item.select_one("span.text")
        rating_tag = item.select_one("b")
        if text_tag is None or rating_tag is None:
            continue
        skill_name = text_tag.get_text(strip=True)
        rating_text = rating_tag.get_text(strip=True)
        if not skill_name or not rating_text:
            continue
        try:
            rating_value = int(rating_text)
        except ValueError:
            continue
        result[clean_skill_name(skill_name)] = rating_value
        result["skill_rating"] = True
    return result


def clean_html_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def extract_scouting_section(html: str) -> str | None:
    start = re.search(
        r'<section[^>]+class="[^"]*\bscouting-report\b[^"]*"[^>]*>',
        html,
        flags=re.IGNORECASE,
    )
    if not start:
        return None
    tail = html[start.start() :]
    end_match = re.search(
        r'<a[^>]+class="[^"]*timeline-comp__admin-link',
        tail,
        flags=re.IGNORECASE,
    )
    return tail[: end_match.start()] if end_match else tail[:15000]


def extract_evaluator(html: str) -> tuple[str | None, str | None]:
    section = extract_scouting_section(html)
    if not section:
        return None, None
    evaluator_match = re.search(
        r'<div[^>]+class="[^"]*\bevaluator\b[^"]*"[^>]*>(.*?)</div>',
        section,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not evaluator_match:
        return None, None
    evaluator_html = evaluator_match.group(1)
    name_match = re.search(
        r'<b[^>]+class="[^"]*\btext\b[^"]*"[^>]*>(.*?)</b>',
        evaluator_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    position_match = re.search(
        r'<span[^>]+class="[^"]*\buppercase\b[^"]*"[^>]*>(.*?)</span>',
        evaluator_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return clean_html_text(name_match.group(1) if name_match else None), clean_html_text(
        position_match.group(1) if position_match else None
    )


def extract_recruiting_profile_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.select("a.view-profile-link"):
        text = link.get_text(" ", strip=True).lower()
        href = link.get("href")
        if href and "view recruiting profile" in text:
            return urljoin("https://247sports.com", href)
    for pattern in [
        r'href=["\'](?P<href>https?://247sports\.com/player/[^"\']+/(?:high-school|junior-college|prep)-\d+)["\']',
        r'href=["\'](?P<href>/player/[^"\']+/(?:high-school|junior-college|prep)-\d+)["\']',
    ]:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return urljoin("https://247sports.com", match.group("href"))
    return None


def extract_enrolled_institution(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for item in soup.select("li.college-comp__body-list-item"):
        interest = item.select_one(".college-comp__interest-level")
        interest_text = ""
        if interest is not None:
            interest_text = " ".join(
                part
                for part in [
                    interest.get("title", ""),
                    interest.get_text(" ", strip=True),
                    " ".join(interest.get("class", [])),
                ]
                if part
            ).lower()
        if "enrolled" not in interest_text:
            continue
        team = item.select_one(".college-comp__team-name-link")
        if team is not None:
            text = team.get_text(" ", strip=True)
            if text:
                return text
    for banner in soup.select("ul.commit-banner-list"):
        text = banner.get_text(" ", strip=True)
        if "enrolled" not in text.lower():
            continue
        img = banner.select_one("img[alt]")
        if img is not None and img.get("alt"):
            return img["alt"].strip()
        for span in [span.get_text(" ", strip=True) for span in banner.select("span")]:
            low = span.lower()
            if low and "enrolled" not in low and not low.startswith("-"):
                return span
    return None


def fetch_recruiting_profile(
    session: requests.Session, url: str, cache_path: Path
) -> tuple[str | None, int | None]:
    if cache_path.exists():
        return cache_path.read_text(errors="ignore"), 200
    time.sleep(REQUEST_SLEEP_SECONDS)
    response = session.get(url, timeout=30)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if response.status_code == 200:
        cache_path.write_text(response.text)
    return response.text, response.status_code


def parse_height_in(height: object) -> int | None:
    text = str(height or "").strip()
    match = re.match(r"^'?(?P<feet>\d+)-(?P<inches>\d+)$", text)
    if not match:
        return None
    return int(match.group("feet")) * 12 + int(match.group("inches"))


def profile_lookup(row_dict: dict[str, object]) -> dict[str, object]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    player_key = row_dict["key"]
    full_name = f"{row_dict.get('firstName', '')} {row_dict.get('lastName', '')}".strip()
    url = normalize_profile_url(row_dict.get("profileUrl"))
    if not url:
        return {"key": player_key, "profile_lookup_status": None, "profile_lookup_url": None}

    html, status = fetch_text_cached(
        session=session,
        url=url,
        cache_path=CACHE_ROOT / str(YEAR) / "profiles" / f"{player_key}.html",
    )
    jsonld_fields = (
        extract_profile_jsonld_person_fields(html)
        if status == 200
        else {"height": None, "weight": None, "birth_date": None}
    )
    height = jsonld_fields["height"]
    weight = jsonld_fields["weight"]
    birth_date = jsonld_fields["birth_date"]
    scouting_report = extract_scouting_report(html) if status == 200 else None
    evaluator_name, evaluator_position = extract_evaluator(html) if status == 200 else (None, None)
    skill_data = parse_skill_ratings_from_html(html) if status == 200 else {"skill_rating": False}
    resolution_method = "api_profile_url"

    if not (height and weight):
        fallback_url = discover_247_profile_url(
            session=session,
            full_name=full_name,
            year=YEAR,
            player_key=player_key,
            cache_path=CACHE_ROOT / str(YEAR) / "resolved_urls" / f"{player_key}.json",
        )
        if fallback_url and fallback_url != url:
            fallback_html, fallback_status = fetch_text_cached(
                session=session,
                url=fallback_url,
                cache_path=CACHE_ROOT / str(YEAR) / "profiles" / f"{player_key}_fallback.html",
            )
            fallback_fields = (
                extract_profile_jsonld_person_fields(fallback_html)
                if fallback_status == 200
                else {"height": None, "weight": None, "birth_date": None}
            )
            if fallback_fields["height"] and fallback_fields["weight"]:
                url = fallback_url
                status = fallback_status
                html = fallback_html
                height = fallback_fields["height"]
                weight = fallback_fields["weight"]
                birth_date = fallback_fields["birth_date"]
                scouting_report = extract_scouting_report(html) if status == 200 else None
                evaluator_name, evaluator_position = (
                    extract_evaluator(html) if status == 200 else (None, None)
                )
                skill_data = (
                    parse_skill_ratings_from_html(html)
                    if status == 200
                    else {"skill_rating": False}
                )
                resolution_method = "search_fallback_college_profile"

    recruiting_profile_url = extract_recruiting_profile_url(html) if status == 200 else None
    enrolled = None
    recruiting_status = None
    if recruiting_profile_url:
        rec_html, recruiting_status = fetch_recruiting_profile(
            session=session,
            url=recruiting_profile_url,
            cache_path=RECRUITING_PROFILE_CACHE / str(YEAR) / f"{player_key}.html",
        )
        if rec_html and recruiting_status == 200:
            enrolled = extract_enrolled_institution(rec_html)

    return {
        "key": player_key,
        "profile_lookup_url": url,
        "profile_lookup_status": status,
        "height": height,
        "weight": weight,
        "dob_247_raw": birth_date,
        "scouting_report": scouting_report,
        "has_scouting_report": bool(scouting_report),
        "profile_resolution_method": resolution_method,
        "scouting_report_evaluator_name": evaluator_name,
        "scouting_report_evaluator_position": evaluator_position,
        "recruiting_profile_url_247": recruiting_profile_url,
        "enrolled_institution_247": enrolled,
        "recruiting_profile_status": recruiting_status,
        **skill_data,
    }


def add_profile_enrichment(recruits_df: pd.DataFrame) -> pd.DataFrame:
    rows = recruits_df[["key", "profileUrl", "firstName", "lastName"]].to_dict("records")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(profile_lookup, row) for row in rows]
        for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            results.append(future.result())
            if i % 50 == 0 or i == len(futures):
                print(f"HS profile pages {YEAR}: {i}/{len(futures)}", flush=True)
    return recruits_df.merge(pd.DataFrame(results), on="key", how="left")


def normalize_final(enriched: pd.DataFrame, hs_columns: list[str]) -> pd.DataFrame:
    dob_247 = pd.to_datetime(enriched["dob_247_raw"], errors="coerce").dt.strftime("%Y-%m-%d")
    output = pd.DataFrame(
        {
            "year": YEAR,
            "player_key": enriched["key"],
            "first_name": enriched["firstName"],
            "last_name": enriched["lastName"],
            "full_name": (
                enriched["firstName"].fillna("").astype(str)
                + " "
                + enriched["lastName"].fillna("").astype(str)
            ).str.strip(),
            "position": enriched["primaryPosition"],
            "height": enriched["height"],
            "weight": enriched["weight"],
            "stars": enriched["compositeStarRating"],
            "rating": enriched["compositeRating"],
            "national_rank": enriched["compositeNationalRank"],
            "position_rank": enriched["compositePositionRank"],
            "state_rank": enriched["compositeStateRank"],
            "hometown_city": enriched["homeTown.city"],
            "hometown_state": enriched["homeTown.state"],
            "committed_institution_key": enriched["committedInstitution.institutionKey"],
            "committed_team_key": enriched["committedInstitution.teamKey"],
            "committed_school": enriched["committedInstitution.name"],
            "committed_school_abbr": enriched["committedInstitution.abbreviation"],
            "committed_school_full": enriched["committedInstitution.fullName"],
            "signed_institution_key": enriched["signedInstitution.institutionKey"],
            "signed_team_key": enriched["signedInstitution.teamKey"],
            "signed_school": enriched["signedInstitution.name"],
            "signed_school_abbr": enriched["signedInstitution.abbreviation"],
            "signed_school_full": enriched["signedInstitution.fullName"],
            "current_institution_key": enriched["currentInstitution.institutionKey"],
            "current_team_key": enriched["currentInstitution.teamKey"],
            "current_school": enriched["currentInstitution.name"],
            "current_school_abbr": enriched["currentInstitution.abbreviation"],
            "current_school_full": enriched["currentInstitution.fullName"],
            "profile_url_api": enriched["profileUrl"],
            "profile_lookup_url": enriched["profile_lookup_url"],
            "profile_lookup_status": enriched["profile_lookup_status"],
            "profile_resolution_method": enriched["profile_resolution_method"],
            "has_scouting_report": enriched["has_scouting_report"].fillna(False).astype(bool),
            "scouting_report": enriched["scouting_report"],
            "source": "247sports_api_recruits_plus_profile_jsonld_2009_append",
            "skill_rating": enriched["skill_rating"].fillna(False).astype(bool),
            "scouting_report_evaluator_name": enriched["scouting_report_evaluator_name"],
            "scouting_report_evaluator_position": enriched[
                "scouting_report_evaluator_position"
            ],
            "dob_247": dob_247,
            "dob_247_raw": enriched["dob_247_raw"],
            "dob_247_source_profile_file": enriched["key"].map(
                lambda key: str(CACHE_ROOT / str(YEAR) / "profiles" / f"{key}.html")
            ),
            "recruiting_profile_url_247": enriched["recruiting_profile_url_247"],
            "enrolled_institution_247": enriched["enrolled_institution_247"],
            "height_in": enriched["height"].map(parse_height_in),
        }
    )
    for col in SKILL_COLS:
        output[col] = pd.to_numeric(enriched[col], errors="coerce") if col in enriched else None
    for col in hs_columns:
        if col not in output.columns:
            output[col] = None
    return output[hs_columns]


def prospect_section(html: str) -> str:
    index = html.lower().find("as-a-prospect")
    if index < 0:
        return ""
    return html[index : index + 12000]


def detect_juco(row: pd.Series) -> dict[str, object]:
    player_key = int(row["player_key"])
    html_path = CACHE_ROOT / str(YEAR) / "profiles" / f"{player_key}.html"
    html = html_path.read_text(errors="ignore") if html_path.exists() else ""
    section = prospect_section(html)
    evidence: list[str] = []
    class_years: set[int] = set()

    if re.search(r'<ul\s+class="[^"]*details[^"]*is-juco', html, flags=re.IGNORECASE):
        evidence.append("details.is-juco")
        class_match = re.search(
            r'<ul\s+class="[^"]*details[^"]*is-juco[\s\S]*?'
            r"<span>\s*Class\s*</span>\s*<span>\s*(\d{4})\s*</span>",
            html,
            flags=re.IGNORECASE,
        )
        if class_match:
            class_years.add(int(class_match.group(1)))
    if re.search(
        r'<h3[^>]*class="title"[^>]*>\s*247Sports\s*<span>\s*JUCO\s*</span>',
        section,
        flags=re.IGNORECASE,
    ):
        evidence.append("prospect_title_247sports_juco")
    section_lower = section.lower()
    if "institutiongroup=juniorcollege" in section_lower:
        evidence.append("ranking_link_juniorcollege")
    if "/junior-college-" in section_lower:
        evidence.append("junior_college_profile_link")
    rec_url = str(row.get("recruiting_profile_url_247") or "").lower()
    if "/junior-college-" in rec_url:
        evidence.append("recruiting_profile_url_247_junior_college")
        class_years.add(YEAR)
    commitment_class_match = re.search(
        r'<ul\s+class="commitment"[\s\S]*?'
        r"<span>\s*Class\s*</span>\s*<span>\s*(\d{4})\s*</span>",
        section,
        flags=re.IGNORECASE,
    )
    if commitment_class_match:
        class_years.add(int(commitment_class_match.group(1)))

    return {
        "year": YEAR,
        "player_key": player_key,
        "full_name": row["full_name"],
        "is_confirmed_juco": bool(evidence) and YEAR in class_years,
        "evidence": ";".join(evidence),
        "class_years": ";".join(str(value) for value in sorted(class_years)),
        "html_path": str(html_path),
    }


def write_year_outputs(raw: pd.DataFrame, enriched: pd.DataFrame, validation: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db_path = OUT_DIR / f"hs_recruits_247_{YEAR}.db"
    with duckdb.connect(str(db_path)) as con:
        con.register("raw_df", raw)
        con.register("enriched_df", enriched)
        con.register("validation_df", validation)
        con.execute("CREATE OR REPLACE TABLE hs_recruits_raw AS SELECT * FROM raw_df")
        con.execute("CREATE OR REPLACE TABLE hs_recruits_enriched AS SELECT * FROM enriched_df")
        con.execute("CREATE OR REPLACE TABLE validation_summary AS SELECT * FROM validation_df")
    dummy_path = OUT_DIR / f"hs_recruit_dummy_{YEAR}.csv"
    pd.concat([enriched.head(5), enriched.tail(5)], ignore_index=True).to_csv(
        dummy_path, index=False
    )
    missing = enriched.loc[
        enriched["height"].isna() | enriched["weight"].isna(),
        [
            "year",
            "player_key",
            "full_name",
            "position",
            "hometown_city",
            "hometown_state",
            "committed_school",
            "profile_url_api",
            "profile_lookup_url",
            "profile_lookup_status",
            "profile_resolution_method",
            "height",
            "weight",
        ],
    ]
    MISSING_DIR.mkdir(parents=True, exist_ok=True)
    missing.to_csv(MISSING_DIR / f"{YEAR}_missing_hw.csv", index=False)


def append_to_databases(enriched: pd.DataFrame, detections: pd.DataFrame) -> dict[str, int]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    DATA_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    JUCO_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    hs_backup = DATA_BACKUP_DIR / f"hs_complete.backup_before_2009_append_{timestamp}.db"
    juco_backup = JUCO_BACKUP_DIR / f"juco_rec.backup_before_2009_append_{timestamp}.db"
    shutil.copy2(HS_DB_PATH, hs_backup)
    shutil.copy2(JUCO_DB_PATH, juco_backup)
    print(f"HS backup: {hs_backup}", flush=True)
    print(f"JUCO backup: {juco_backup}", flush=True)

    hs_rows = enriched.loc[~detections["is_confirmed_juco"].to_numpy()].copy()
    juco_rows = enriched.loc[detections["is_confirmed_juco"].to_numpy()].copy()

    with duckdb.connect(str(HS_DB_PATH)) as con:
        before_rows = con.execute(f"SELECT COUNT(*) FROM {quote_ident(HS_TABLE)}").fetchone()[0]
        existing_2009 = con.execute(
            f"SELECT COUNT(*) FROM {quote_ident(HS_TABLE)} WHERE year = {YEAR}"
        ).fetchone()[0]
        if existing_2009:
            raise RuntimeError(f"{HS_DB_PATH} already has {existing_2009} rows for {YEAR}.")
        hs_cols = [row[0] for row in con.execute(f"DESCRIBE {quote_ident(HS_TABLE)}").fetchall()]
        if list(hs_rows.columns) != hs_cols:
            raise RuntimeError("Internal column-order mismatch before HS append.")
        con.register("append_hs_df", hs_rows)
        con.execute(f"INSERT INTO {quote_ident(HS_TABLE)} SELECT * FROM append_hs_df")

        parse_rows = hs_rows.loc[
            hs_rows["has_scouting_report"] == True,
            [
                "year",
                "player_key",
                "full_name",
                "scouting_report_evaluator_name",
                "scouting_report_evaluator_position",
                "dob_247_source_profile_file",
            ],
        ].rename(columns={"dob_247_source_profile_file": "html_path"})
        con.register("parse_append_df", parse_rows)
        con.execute(
            """
            INSERT INTO scouting_report_evaluator_parse
            SELECT * FROM parse_append_df
            """
        )
        after_rows = con.execute(f"SELECT COUNT(*) FROM {quote_ident(HS_TABLE)}").fetchone()[0]
        if after_rows != before_rows + len(hs_rows):
            raise RuntimeError("HS append row count validation failed.")

    with duckdb.connect(str(JUCO_DB_PATH)) as con:
        before_rows = con.execute(f"SELECT COUNT(*) FROM {quote_ident(JUCO_TABLE)}").fetchone()[0]
        existing_2009 = con.execute(
            f"SELECT COUNT(*) FROM {quote_ident(JUCO_TABLE)} WHERE year = {YEAR}"
        ).fetchone()[0]
        if existing_2009:
            raise RuntimeError(f"{JUCO_DB_PATH} already has {existing_2009} JUCO rows for {YEAR}.")
        juco_cols = [
            row[0] for row in con.execute(f"DESCRIBE {quote_ident(JUCO_TABLE)}").fetchall()
        ]
        juco_output = juco_rows.copy()
        juco_detection_rows = detections.loc[detections["is_confirmed_juco"]].reset_index(
            drop=True
        )
        juco_output["juco_evidence"] = juco_detection_rows["evidence"]
        juco_output["juco_class_years"] = juco_detection_rows["class_years"]
        juco_output["juco_html_path"] = juco_detection_rows["html_path"]
        for col in juco_cols:
            if col not in juco_output.columns:
                juco_output[col] = None
        juco_output = juco_output[juco_cols]
        con.register("append_juco_df", juco_output)
        con.execute(f"INSERT INTO {quote_ident(JUCO_TABLE)} SELECT * FROM append_juco_df")

        audit_cols = [
            row[0] for row in con.execute(f"DESCRIBE {quote_ident(JUCO_AUDIT_TABLE)}").fetchall()
        ]
        audit_output = juco_detection_rows[audit_cols].copy()
        con.register("append_audit_df", audit_output)
        con.execute(f"INSERT INTO {quote_ident(JUCO_AUDIT_TABLE)} SELECT * FROM append_audit_df")
        after_rows = con.execute(f"SELECT COUNT(*) FROM {quote_ident(JUCO_TABLE)}").fetchone()[0]
        if after_rows != before_rows + len(juco_rows):
            raise RuntimeError("JUCO append row count validation failed.")

    return {
        "hs_appended": len(hs_rows),
        "juco_appended": len(juco_rows),
        "hs_backup": str(hs_backup),
        "juco_backup": str(juco_backup),
    }


def validate_no_existing_rows() -> None:
    with duckdb.connect(str(HS_DB_PATH), read_only=True) as con:
        existing = con.execute(
            f"SELECT COUNT(*) FROM {quote_ident(HS_TABLE)} WHERE year = {YEAR}"
        ).fetchone()[0]
        if existing:
            raise RuntimeError(f"Refusing to append: hs_complete already has {existing} {YEAR} rows.")
    with duckdb.connect(str(JUCO_DB_PATH), read_only=True) as con:
        existing = con.execute(
            f"SELECT COUNT(*) FROM {quote_ident(JUCO_TABLE)} WHERE year = {YEAR}"
        ).fetchone()[0]
        if existing:
            raise RuntimeError(f"Refusing to append: juco_rec already has {existing} {YEAR} rows.")


def main() -> None:
    validate_no_existing_rows()

    with duckdb.connect(str(HS_DB_PATH), read_only=True) as con:
        hs_columns = [row[0] for row in con.execute(f"DESCRIBE {quote_ident(HS_TABLE)}").fetchall()]

    session = requests.Session()
    session.headers.update(get_247_headers())
    players = pull_all_recruits(session)
    raw = flatten_recruits(players)
    enriched_intermediate = add_profile_enrichment(raw)
    enriched = normalize_final(enriched_intermediate, hs_columns)
    detections = pd.DataFrame([detect_juco(row) for _, row in enriched.iterrows()])

    if enriched.duplicated(["year", "player_key"]).sum():
        raise RuntimeError("2009 scrape produced duplicate year/player_key rows.")
    if len(enriched) != len(raw):
        raise RuntimeError("2009 enriched row count does not match raw row count.")

    validation = pd.DataFrame(
        [
            {
                "year": YEAR,
                "raw_rows": len(raw),
                "enriched_rows": len(enriched),
                "duplicate_year_player_keys": int(enriched.duplicated(["year", "player_key"]).sum()),
                "height_non_null": int(enriched["height"].notna().sum()),
                "weight_non_null": int(enriched["weight"].notna().sum()),
                "height_in_non_null": int(enriched["height_in"].notna().sum()),
                "dob_247_non_null": int(enriched["dob_247"].notna().sum()),
                "scouting_report_true": int(enriched["has_scouting_report"].sum()),
                "skill_rating_true": int(enriched["skill_rating"].sum()),
                "recruiting_profile_urls": int(enriched["recruiting_profile_url_247"].notna().sum()),
                "enrolled_institution_non_null": int(enriched["enrolled_institution_247"].notna().sum()),
                "confirmed_juco": int(detections["is_confirmed_juco"].sum()),
                "validation_passed": True,
            }
        ]
    )
    write_year_outputs(raw, enriched, validation)
    append_counts = append_to_databases(enriched, detections)

    print(validation.to_string(index=False), flush=True)
    print(json.dumps(append_counts, indent=2), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
