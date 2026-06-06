import json
import re
import time
from html import unescape
from pathlib import Path

import pandas as pd
import requests


YEAR = 2025
INPUT_CSV = Path(f"mbb_recruits_{YEAR}.csv")
OUTPUT_CSV = Path(f"mbb_recruits_{YEAR}_with_measurables.csv")
BASE_URL = "https://247sports.com"


def normalize_profile_url(profile_url):
    path = str(profile_url).strip()
    if not path.startswith("/"):
        path = "/" + path

    match = re.search(r"-(\d+)$", path.rstrip("/"))
    if not match:
        return BASE_URL + path

    key = match.group(1)
    slug = path.rstrip("/").split("/")[-1]
    slug = re.sub(rf"-{key}$", "", slug)
    slug = slug.replace(".", "")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower()
    return f"{BASE_URL}/player/{slug}-{key}/"


def value_from_quantitative_field(value):
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        return value.get("value")
    return value


def extract_measurables(html):
    scripts = re.findall(
        r'<script[^>]+type=["\\\']application/ld\\+json["\\\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for script in scripts:
        raw = unescape(script).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            height = value_from_quantitative_field(obj.get("height"))
            weight = value_from_quantitative_field(obj.get("weight"))
            if height or weight:
                return height, weight

    return None, None


def fetch_measurables(session, profile_url):
    url = normalize_profile_url(profile_url)
    response = session.get(url, timeout=30)
    if response.status_code != 200:
        return {
            "profile_lookup_url": url,
            "profile_lookup_status": response.status_code,
            "profile_height": None,
            "profile_weight": None,
        }

    height, weight = extract_measurables(response.text)
    return {
        "profile_lookup_url": url,
        "profile_lookup_status": response.status_code,
        "profile_height": height,
        "profile_weight": weight,
    }


def main():
    recruits = pd.read_csv(INPUT_CSV)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )

    results = []
    for i, row in recruits.iterrows():
        measurables = fetch_measurables(session, row["profileUrl"])
        measurables["key"] = row["key"]
        results.append(measurables)
        if (i + 1) % 25 == 0:
            print(f"Fetched {i + 1}/{len(recruits)} profiles")
        time.sleep(0.1)

    measurables_df = pd.DataFrame(results)
    enriched = recruits.merge(measurables_df, on="key", how="left")
    enriched.to_csv(OUTPUT_CSV, index=False)

    matched = enriched["profile_height"].notna() | enriched["profile_weight"].notna()
    print(f"{OUTPUT_CSV}: {len(enriched)} rows")
    print(f"matched measurable rows: {matched.sum()}/{len(enriched)}")
    print(
        enriched[
            [
                "key",
                "firstName",
                "lastName",
                "primaryPosition",
                "profile_height",
                "profile_weight",
                "profile_lookup_status",
            ]
        ]
        .head(20)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
