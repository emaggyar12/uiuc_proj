from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
import shutil
import unicodedata

import duckdb


def find_project_root() -> Path:
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if parent.name == "uiuc_proj":
            return parent
    raise RuntimeError("Could not find uiuc_proj in this script's parent folders.")


PROJECT_ROOT = find_project_root()

STATS_DB = PROJECT_ROOT / "db_files" / "bvt_allyears.db"
STATS_TABLE = "bvt_allyears"
STATS_OUTPUT_DB = PROJECT_ROOT / "db_files" / "bvt_allyears_uniqueid.db"
STATS_OUTPUT_TABLE = "bvt_allyears_uniqueid"

TRANSFER_DB = (
    PROJECT_ROOT
    / "scrapers_web"
    / "get_bartovik_data"
    / "db_files"
    / "barttorvik_transfers_2018_2026_plus_current.db"
)
TRANSFER_TABLE = "barttorvik_transfers"
TRANSFER_OUTPUT_DB = TRANSFER_DB.with_name("barttorvik_transfers_2018_2026_uniqueid.db")
TRANSFER_OUTPUT_TABLE = "barttorvik_transfers_uniqueid"

BACKUP_DIR = PROJECT_ROOT / "scrapers_web" / "get_bartovik_data" / "db_files" / "backups"
MAX_SAME_SCHOOL_GAP = 6


SCHOOL_ALIASES = {
    "uconn": "connecticut",
    "conn": "connecticut",
    "st johns": "st john's",
    "st john s": "st john's",
    "saint johns": "st john's",
    "saint john s": "st john's",
    "saint marys": "saint mary's",
    "saint mary s": "saint mary's",
    "st marys": "saint mary's",
    "st mary s": "saint mary's",
    "miami fl": "miami fl",
    "miami florida": "miami fl",
    "miami oh": "miami oh",
    "miami ohio": "miami oh",
    "unc": "north carolina",
    "nc state": "n.c. state",
    "n c state": "n.c. state",
    "n c  state": "n.c. state",
    "ole miss": "mississippi",
    "southern california": "usc",
    "ucf knights": "ucf",
    "byu cougars": "byu",
    "iu indy": "iu indy",
    "iupu indianapolis": "iu indy",
    "iupuindy": "iu indy",
    "texas a m": "texas a&m",
    "texas a and m": "texas a&m",
    "texas a m corpus chris": "texas a&m corpus chris",
    "texas a and m corpus chris": "texas a&m corpus chris",
    "cal state bakersfield": "cal st. bakersfield",
    "cal state fullerton": "cal st. fullerton",
    "cal state northridge": "cal st. northridge",
    "cal state la": "cal state los angeles",
    "uc santa barbara": "uc santa barbara",
    "umass": "massachusetts",
    "massachusetts lowell": "umass lowell",
    "louisiana lafayette": "louisiana",
    "ul lafayette": "louisiana",
    "louisiana monroe": "louisiana monroe",
    "ul monroe": "louisiana monroe",
}


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_name(value: object) -> str | None:
    text = normalize_text(value)
    if text is None:
        return None
    suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}
    parts = [part for part in text.split() if part not in suffixes]
    return " ".join(parts) or text


def normalize_school(value: object) -> str | None:
    text = normalize_text(value)
    if text is None:
        return None
    text = re.sub(r"\b(university|college|school|the)\b", " ", text)
    text = re.sub(r"\b(raiders|wildcats|tigers|bulldogs|eagles|hawks|spartans|cougars|bears|panthers|cardinals|knights|aggies|rams|lions|warriors|colonials|falcons|mustangs|minutemen|explorers|musketeers|gaels|saints|dons|dolphins|pilots|terriers|broncos|bison|bears|dukes|mountaineers|rebels|huskies|boilermakers|tar heels|blue devils|cyclones|cowboys|volunteers|commodores|gators|seminoles|hurricanes|yellow jackets|badgers|wolverines|buckeyes|hoosiers|illini|terrapins|scarlet knights)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = SCHOOL_ALIASES.get(text, text)
    text = text.replace(" and ", " & ")
    return text or None


@dataclass
class StatsNode:
    stats_row_id: int
    year: int | None
    player_name: str | None
    institution: str | None
    name_norm: str | None
    institution_norm: str | None
    ambiguous_duplicate: bool = False


@dataclass
class TransferRow:
    transfer_row_id: int
    year: int | None
    player_name: str | None
    previous_team: str | None
    destination_team: str | None
    name_norm: str | None
    previous_norm: str | None
    destination_norm: str | None
    destination_min_year: int | None
    movement_orientation: str


class UnionFind:
    def __init__(self, values: list[int]):
        self.parent = {value: value for value in values}
        self.rank = {value: 0 for value in values}

    def find(self, value: int) -> int:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            self.parent[root_left] = root_right
        elif self.rank[root_left] > self.rank[root_right]:
            self.parent[root_right] = root_left
        else:
            self.parent[root_right] = root_left
            self.rank[root_left] += 1


def backup_input_db(path: Path, timestamp: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_DIR / f"{path.stem}.input_backup_before_uniqueid_{timestamp}.db"
    shutil.copy2(path, backup)
    return backup


def backup_existing_output(path: Path, timestamp: str) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_name(f"{path.stem}.backup_before_overwrite_{timestamp}.db")
    shutil.copy2(path, backup)
    path.unlink()
    return backup


def load_stats() -> tuple[list[str], list[StatsNode]]:
    con = duckdb.connect(str(STATS_DB), read_only=True)
    try:
        columns = [row[0] for row in con.execute(f"DESCRIBE {quote_ident(STATS_TABLE)}").fetchall()]
        rows = con.execute(f"""
            SELECT
                ROW_NUMBER() OVER () AS stats_row_id,
                year,
                player_name,
                team
            FROM {quote_ident(STATS_TABLE)}
        """).fetchall()
    finally:
        con.close()

    nodes = [
        StatsNode(
            stats_row_id=int(row[0]),
            year=int(row[1]) if row[1] is not None else None,
            player_name=row[2],
            institution=row[3],
            name_norm=normalize_name(row[2]),
            institution_norm=normalize_school(row[3]),
        )
        for row in rows
    ]
    return columns, nodes


def load_transfers() -> list[TransferRow]:
    con = duckdb.connect(str(TRANSFER_DB), read_only=True)
    try:
        rows = con.execute(f"""
            SELECT
                ROW_NUMBER() OVER () AS transfer_row_id,
                barttorvik_year,
                player_name,
                previous_team,
                destination_team
            FROM {quote_ident(TRANSFER_TABLE)}
        """).fetchall()
    finally:
        con.close()

    transfers = []
    for row in rows:
        raw_year = row[1]
        if raw_year == "trans_current_2026_27":
            year = 2026
        elif raw_year is not None:
            year = int(raw_year)
        else:
            year = None

        if year is not None and year < 2026:
            # Historical transfer pages list the player's current/source team
            # in destination_team and the next school in previous_team.
            true_previous_team = row[4]
            true_destination_team = row[3]
            destination_min_year = year + 1
            movement_orientation = "historical_outgoing_next_season"
        else:
            # 2026/current pages are incoming-transfer views.
            true_previous_team = row[3]
            true_destination_team = row[4]
            destination_min_year = year
            movement_orientation = "current_incoming"

        transfers.append(
            TransferRow(
                transfer_row_id=int(row[0]),
                year=year,
                player_name=row[2],
                previous_team=row[3],
                destination_team=row[4],
                name_norm=normalize_name(row[2]),
                previous_norm=normalize_school(true_previous_team),
                destination_norm=normalize_school(true_destination_team),
                destination_min_year=destination_min_year,
                movement_orientation=movement_orientation,
            )
        )
    return transfers


def add_review(
    reviews: list[dict[str, object]],
    reason: str,
    name_norm: str | None,
    candidate_stats_row_ids: list[int] | None = None,
    candidate_years: list[int] | None = None,
    candidate_institutions: list[str | None] | None = None,
    candidate_transfer_rows: list[int] | None = None,
    notes: str | None = None,
) -> None:
    reviews.append(
        {
            "review_case_id": len(reviews) + 1,
            "reason": reason,
            "name_norm": name_norm,
            "candidate_stats_row_ids": ",".join(map(str, candidate_stats_row_ids or [])),
            "candidate_years": ",".join(map(str, candidate_years or [])),
            "candidate_institutions": ",".join(x or "" for x in (candidate_institutions or [])),
            "candidate_transfer_rows": ",".join(map(str, candidate_transfer_rows or [])),
            "notes": notes,
        }
    )


def closest_unique(candidates: list[StatsNode], transfer_year: int, direction: str) -> tuple[StatsNode | None, str | None, list[StatsNode]]:
    if not candidates:
        return None, "no_candidates", []
    if direction == "source":
        best_year = max(node.year for node in candidates if node.year is not None)
    else:
        best_year = min(node.year for node in candidates if node.year is not None)
    tied = [node for node in candidates if node.year == best_year]
    if len(tied) != 1:
        return None, "multiple_candidates", tied
    return tied[0], None, tied


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats_backup = backup_input_db(STATS_DB, timestamp)
    transfer_backup = backup_input_db(TRANSFER_DB, timestamp)
    stats_output_backup = backup_existing_output(STATS_OUTPUT_DB, timestamp)
    transfer_output_backup = backup_existing_output(TRANSFER_OUTPUT_DB, timestamp)

    stats_columns, stats_nodes = load_stats()
    transfers = load_transfers()
    nodes_by_id = {node.stats_row_id: node for node in stats_nodes}
    reviews: list[dict[str, object]] = []
    links: list[dict[str, object]] = []
    transfer_link_rows: list[dict[str, object]] = []
    supported_transitions: defaultdict[int, set[tuple[str | None, str | None]]] = defaultdict(set)

    duplicate_groups: defaultdict[tuple[str | None, str | None, int | None], list[StatsNode]] = defaultdict(list)
    for node in stats_nodes:
        duplicate_groups[(node.name_norm, node.institution_norm, node.year)].append(node)

    for (name_norm, institution_norm, year), grouped_nodes in duplicate_groups.items():
        if len(grouped_nodes) > 1:
            for node in grouped_nodes:
                node.ambiguous_duplicate = True
            add_review(
                reviews,
                "duplicate_same_name_school_year",
                name_norm,
                [node.stats_row_id for node in grouped_nodes],
                [year] if year is not None else [],
                [institution_norm],
                notes="Same normalized name, school, and year appears more than once.",
            )

    uf = UnionFind([node.stats_row_id for node in stats_nodes])

    by_name_school: defaultdict[tuple[str | None, str | None], list[StatsNode]] = defaultdict(list)
    for node in stats_nodes:
        if node.name_norm and node.institution_norm and not node.ambiguous_duplicate:
            by_name_school[(node.name_norm, node.institution_norm)].append(node)

    for (name_norm, institution_norm), grouped_nodes in by_name_school.items():
        grouped_nodes = sorted(grouped_nodes, key=lambda node: (node.year is None, node.year or -1, node.stats_row_id))
        for left, right in zip(grouped_nodes, grouped_nodes[1:]):
            if left.year is None or right.year is None:
                continue
            gap = right.year - left.year
            if gap <= MAX_SAME_SCHOOL_GAP:
                uf.union(left.stats_row_id, right.stats_row_id)
                links.append(
                    {
                        "left_stats_row_id": left.stats_row_id,
                        "right_stats_row_id": right.stats_row_id,
                        "link_type": "same_school_continuity",
                        "transfer_row_id": None,
                        "notes": f"gap={gap}",
                    }
                )
            else:
                add_review(
                    reviews,
                    "same_name_gap_too_large",
                    name_norm,
                    [left.stats_row_id, right.stats_row_id],
                    [left.year, right.year],
                    [institution_norm],
                    notes=f"Same-school gap {gap} exceeds {MAX_SAME_SCHOOL_GAP}.",
                )

    stats_index: defaultdict[tuple[str | None, str | None], list[StatsNode]] = defaultdict(list)
    for node in stats_nodes:
        if node.name_norm and node.institution_norm and not node.ambiguous_duplicate:
            stats_index[(node.name_norm, node.institution_norm)].append(node)

    conflict_keys = set()
    transfers_by_conflict_key: defaultdict[tuple[str | None, int | None, str | None], set[str | None]] = defaultdict(set)
    for transfer in transfers:
        transfers_by_conflict_key[(transfer.name_norm, transfer.year, transfer.previous_norm)].add(transfer.destination_norm)
    for key, destinations in transfers_by_conflict_key.items():
        real_destinations = {destination for destination in destinations if destination}
        if len(real_destinations) > 1:
            conflict_keys.add(key)

    for transfer in transfers:
        if transfer.year is None or not transfer.name_norm:
            add_review(
                reviews,
                "unmatched_transfer_row",
                transfer.name_norm,
                candidate_transfer_rows=[transfer.transfer_row_id],
                notes="Missing transfer year or normalized player name.",
            )
            continue

        if (transfer.name_norm, transfer.year, transfer.previous_norm) in conflict_keys:
            add_review(
                reviews,
                "conflicting_transfer_paths",
                transfer.name_norm,
                candidate_transfer_rows=[transfer.transfer_row_id],
                notes="Same name/year/previous school has multiple destination schools.",
            )
            continue

        source = None
        destination = None
        source_reason = None
        destination_reason = None

        if transfer.previous_norm:
            source_candidates = [
                node
                for node in stats_index.get((transfer.name_norm, transfer.previous_norm), [])
                if node.year is not None and node.year <= transfer.year
            ]
            source, source_reason, source_tied = closest_unique(source_candidates, transfer.year, "source")
            if source_reason == "multiple_candidates":
                add_review(
                    reviews,
                    "multiple_source_candidates",
                    transfer.name_norm,
                    [node.stats_row_id for node in source_tied],
                    [node.year for node in source_tied if node.year is not None],
                    [transfer.previous_norm],
                    [transfer.transfer_row_id],
                    "Multiple closest previous-school stats rows tied for transfer.",
                )

        if transfer.destination_norm:
            destination_year_floor = transfer.destination_min_year or transfer.year
            destination_candidates = [
                node
                for node in stats_index.get((transfer.name_norm, transfer.destination_norm), [])
                if node.year is not None and node.year >= destination_year_floor
            ]
            destination, destination_reason, destination_tied = closest_unique(destination_candidates, transfer.year, "destination")
            if destination_reason == "multiple_candidates":
                add_review(
                    reviews,
                    "multiple_destination_candidates",
                    transfer.name_norm,
                    [node.stats_row_id for node in destination_tied],
                    [node.year for node in destination_tied if node.year is not None],
                    [transfer.destination_norm],
                    [transfer.transfer_row_id],
                    "Multiple closest destination-school stats rows tied for transfer.",
                )

        if source and destination:
            uf.union(source.stats_row_id, destination.stats_row_id)
            links.append(
                {
                    "left_stats_row_id": source.stats_row_id,
                    "right_stats_row_id": destination.stats_row_id,
                    "link_type": "transfer_movement",
                    "transfer_row_id": transfer.transfer_row_id,
                    "notes": f"{transfer.previous_norm}->{transfer.destination_norm}",
                }
            )
            supported_transitions[source.stats_row_id].add((source.institution_norm, destination.institution_norm))
            transfer_link_rows.append(
                {
                    "transfer_row_id": transfer.transfer_row_id,
                    "source_stats_row_id": source.stats_row_id,
                    "destination_stats_row_id": destination.stats_row_id,
                    "match_status": "source_and_destination_matched",
                    "notes": None,
                }
            )
        elif source and transfer.year == 2026:
            transfer_link_rows.append(
                {
                    "transfer_row_id": transfer.transfer_row_id,
                    "source_stats_row_id": source.stats_row_id,
                    "destination_stats_row_id": None,
                    "match_status": "source_only_2026_current_cycle",
                    "notes": "Assigned transfer row to previous-school stats component; future destination season may not exist.",
                }
            )
        else:
            add_review(
                reviews,
                "unmatched_transfer_row",
                transfer.name_norm,
                [node.stats_row_id for node in [source, destination] if node],
                [node.year for node in [source, destination] if node and node.year is not None],
                [transfer.previous_norm, transfer.destination_norm],
                [transfer.transfer_row_id],
                f"source={source_reason or bool(source)}, destination={destination_reason or bool(destination)}",
            )

    components: defaultdict[int, list[StatsNode]] = defaultdict(list)
    for node in stats_nodes:
        components[uf.find(node.stats_row_id)].append(node)

    transition_support_by_component: defaultdict[int, set[tuple[str | None, str | None]]] = defaultdict(set)
    for stats_row_id, transitions in supported_transitions.items():
        transition_support_by_component[uf.find(stats_row_id)].update(transitions)

    component_rows = []
    player_id_by_stats_row_id: dict[int, str | None] = {}
    next_player_number = 1

    for component_root, grouped_nodes in sorted(components.items()):
        grouped_nodes = sorted(grouped_nodes, key=lambda node: (node.year is None, node.year or -1, node.stats_row_id))
        invalid_reasons = []

        years = [node.year for node in grouped_nodes if node.year is not None]
        if len(years) != len(set(years)):
            invalid_reasons.append("component_has_multiple_rows_same_year")

        if any(node.ambiguous_duplicate for node in grouped_nodes):
            invalid_reasons.append("contains_duplicate_same_name_school_year")

        support = transition_support_by_component.get(component_root, set())
        for left, right in zip(grouped_nodes, grouped_nodes[1:]):
            if left.institution_norm != right.institution_norm:
                if (left.institution_norm, right.institution_norm) not in support:
                    invalid_reasons.append("institution_change_without_transfer")
                    break
            elif left.year is not None and right.year is not None:
                gap = right.year - left.year
                if gap > MAX_SAME_SCHOOL_GAP:
                    invalid_reasons.append("same_name_gap_too_large")
                    break

        is_valid = not invalid_reasons
        assigned_player_id = None
        if is_valid:
            assigned_player_id = f"p_{next_player_number:06d}"
            next_player_number += 1

        for node in grouped_nodes:
            player_id_by_stats_row_id[node.stats_row_id] = assigned_player_id

        component_rows.append(
            {
                "component_root": component_root,
                "player_id": assigned_player_id,
                "is_valid": is_valid,
                "invalid_reasons": ",".join(sorted(set(invalid_reasons))),
                "stats_row_ids": ",".join(str(node.stats_row_id) for node in grouped_nodes),
                "years": ",".join(str(node.year) for node in grouped_nodes if node.year is not None),
                "names": ",".join(sorted({node.player_name or "" for node in grouped_nodes})),
                "institutions": ",".join(sorted({node.institution or "" for node in grouped_nodes})),
                "component_size": len(grouped_nodes),
            }
        )

        if invalid_reasons:
            add_review(
                reviews,
                ",".join(sorted(set(invalid_reasons))),
                grouped_nodes[0].name_norm,
                [node.stats_row_id for node in grouped_nodes],
                [node.year for node in grouped_nodes if node.year is not None],
                [node.institution_norm for node in grouped_nodes],
                notes="Component failed validation.",
            )

    transfer_id_by_row_id: dict[int, str | None] = {}
    for transfer_link in transfer_link_rows:
        stats_row_id = transfer_link["source_stats_row_id"] or transfer_link["destination_stats_row_id"]
        transfer_id_by_row_id[transfer_link["transfer_row_id"]] = player_id_by_stats_row_id.get(stats_row_id)

    create_outputs(
        stats_columns=stats_columns,
        stats_nodes=stats_nodes,
        transfers=transfers,
        player_id_by_stats_row_id=player_id_by_stats_row_id,
        transfer_id_by_row_id=transfer_id_by_row_id,
        links=links,
        component_rows=component_rows,
        reviews=reviews,
        transfer_link_rows=transfer_link_rows,
    )

    assigned_stats = sum(1 for value in player_id_by_stats_row_id.values() if value)
    assigned_transfers = sum(1 for value in transfer_id_by_row_id.values() if value)
    print(f"Stats input backup: {stats_backup}", flush=True)
    print(f"Transfer input backup: {transfer_backup}", flush=True)
    if stats_output_backup:
        print(f"Previous stats output backed up: {stats_output_backup}", flush=True)
    if transfer_output_backup:
        print(f"Previous transfer output backed up: {transfer_output_backup}", flush=True)
    print(f"Stats rows: {len(stats_nodes):,}", flush=True)
    print(f"Stats rows with player_id: {assigned_stats:,}", flush=True)
    print(f"Stats rows with NULL player_id: {len(stats_nodes) - assigned_stats:,}", flush=True)
    print(f"Transfer rows: {len(transfers):,}", flush=True)
    print(f"Transfer rows linked to player_id: {assigned_transfers:,}", flush=True)
    print(f"Manual review cases: {len(reviews):,}", flush=True)
    print(f"Stats output DB: {STATS_OUTPUT_DB}", flush=True)
    print(f"Transfer output DB: {TRANSFER_OUTPUT_DB}", flush=True)


def create_outputs(
    stats_columns: list[str],
    stats_nodes: list[StatsNode],
    transfers: list[TransferRow],
    player_id_by_stats_row_id: dict[int, str | None],
    transfer_id_by_row_id: dict[int, str | None],
    links: list[dict[str, object]],
    component_rows: list[dict[str, object]],
    reviews: list[dict[str, object]],
    transfer_link_rows: list[dict[str, object]],
) -> None:
    STATS_OUTPUT_DB.parent.mkdir(parents=True, exist_ok=True)
    TRANSFER_OUTPUT_DB.parent.mkdir(parents=True, exist_ok=True)

    stats_con = duckdb.connect(str(STATS_OUTPUT_DB))
    try:
        stats_con.execute(f"ATTACH '{STATS_DB}' AS source_db")
        stats_con.execute("""
            CREATE TABLE stats_identity_map (
                stats_row_id BIGINT,
                player_id VARCHAR,
                name_norm VARCHAR,
                institution_norm VARCHAR,
                identity_is_ambiguous BOOLEAN
            )
        """)
        stats_con.executemany(
            "INSERT INTO stats_identity_map VALUES (?, ?, ?, ?, ?)",
            [
                (
                    node.stats_row_id,
                    player_id_by_stats_row_id.get(node.stats_row_id),
                    node.name_norm,
                    node.institution_norm,
                    node.ambiguous_duplicate or player_id_by_stats_row_id.get(node.stats_row_id) is None,
                )
                for node in stats_nodes
            ],
        )
        stats_con.execute(f"""
            CREATE TABLE {quote_ident(STATS_OUTPUT_TABLE)} AS
            WITH source_rows AS (
                SELECT ROW_NUMBER() OVER () AS stats_row_id, *
                FROM source_db.main.{quote_ident(STATS_TABLE)}
            )
            SELECT
                s.*,
                m.player_id,
                m.name_norm,
                m.institution_norm,
                m.identity_is_ambiguous
            FROM source_rows AS s
            LEFT JOIN stats_identity_map AS m USING (stats_row_id)
        """)
        write_audit_tables(stats_con, links, component_rows, reviews, transfer_link_rows)
    finally:
        stats_con.close()

    transfer_con = duckdb.connect(str(TRANSFER_OUTPUT_DB))
    try:
        transfer_con.execute(f"ATTACH '{TRANSFER_DB}' AS source_db")
        transfer_con.execute("""
            CREATE TABLE transfer_identity_map (
                transfer_row_id BIGINT,
                player_id VARCHAR,
                name_norm VARCHAR,
                previous_college_norm VARCHAR,
                next_college_norm VARCHAR,
                movement_orientation VARCHAR,
                identity_is_ambiguous BOOLEAN
            )
        """)
        transfer_con.executemany(
            "INSERT INTO transfer_identity_map VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    transfer.transfer_row_id,
                    transfer_id_by_row_id.get(transfer.transfer_row_id),
                    transfer.name_norm,
                    transfer.previous_norm,
                    transfer.destination_norm,
                    transfer.movement_orientation,
                    transfer_id_by_row_id.get(transfer.transfer_row_id) is None,
                )
                for transfer in transfers
            ],
        )
        transfer_con.execute(f"""
            CREATE TABLE {quote_ident(TRANSFER_OUTPUT_TABLE)} AS
            WITH source_rows AS (
                SELECT ROW_NUMBER() OVER () AS transfer_row_id, *
                FROM source_db.main.{quote_ident(TRANSFER_TABLE)}
            )
            SELECT
                s.*,
                m.player_id,
                m.name_norm,
                m.previous_college_norm,
                m.next_college_norm,
                m.movement_orientation,
                m.identity_is_ambiguous
            FROM source_rows AS s
            LEFT JOIN transfer_identity_map AS m USING (transfer_row_id)
        """)
        write_audit_tables(transfer_con, links, component_rows, reviews, transfer_link_rows)
    finally:
        transfer_con.close()


def write_audit_tables(
    con: duckdb.DuckDBPyConnection,
    links: list[dict[str, object]],
    component_rows: list[dict[str, object]],
    reviews: list[dict[str, object]],
    transfer_link_rows: list[dict[str, object]],
) -> None:
    con.execute("""
        CREATE TABLE same_player_links (
            left_stats_row_id BIGINT,
            right_stats_row_id BIGINT,
            link_type VARCHAR,
            transfer_row_id BIGINT,
            notes VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO same_player_links VALUES (?, ?, ?, ?, ?)",
        [
            (
                row["left_stats_row_id"],
                row["right_stats_row_id"],
                row["link_type"],
                row["transfer_row_id"],
                row["notes"],
            )
            for row in links
        ],
    )

    con.execute("""
        CREATE TABLE identity_components (
            component_root BIGINT,
            player_id VARCHAR,
            is_valid BOOLEAN,
            invalid_reasons VARCHAR,
            stats_row_ids VARCHAR,
            years VARCHAR,
            names VARCHAR,
            institutions VARCHAR,
            component_size BIGINT
        )
    """)
    con.executemany(
        "INSERT INTO identity_components VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                row["component_root"],
                row["player_id"],
                row["is_valid"],
                row["invalid_reasons"],
                row["stats_row_ids"],
                row["years"],
                row["names"],
                row["institutions"],
                row["component_size"],
            )
            for row in component_rows
        ],
    )

    con.execute("""
        CREATE TABLE manual_review_cases (
            review_case_id BIGINT,
            reason VARCHAR,
            name_norm VARCHAR,
            candidate_stats_row_ids VARCHAR,
            candidate_years VARCHAR,
            candidate_institutions VARCHAR,
            candidate_transfer_rows VARCHAR,
            notes VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO manual_review_cases VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                row["review_case_id"],
                row["reason"],
                row["name_norm"],
                row["candidate_stats_row_ids"],
                row["candidate_years"],
                row["candidate_institutions"],
                row["candidate_transfer_rows"],
                row["notes"],
            )
            for row in reviews
        ],
    )

    con.execute("""
        CREATE TABLE transfer_identity_links (
            transfer_row_id BIGINT,
            source_stats_row_id BIGINT,
            destination_stats_row_id BIGINT,
            match_status VARCHAR,
            notes VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO transfer_identity_links VALUES (?, ?, ?, ?, ?)",
        [
            (
                row["transfer_row_id"],
                row["source_stats_row_id"],
                row["destination_stats_row_id"],
                row["match_status"],
                row["notes"],
            )
            for row in transfer_link_rows
        ],
    )


if __name__ == "__main__":
    main()
