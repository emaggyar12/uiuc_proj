"use client";

import { useMemo, useState } from "react";
import { ArrowUpDown, ChevronDown, Search, SlidersHorizontal } from "lucide-react";
import clsx from "clsx";
import type { Player } from "@/data/players";
import { getTopPlaytypes } from "@/lib/data";
import { PlayerDetailPanel } from "@/components/PlayerDetailPanel";
import { StatusBadge } from "@/components/StatusBadge";

type SortKey = "projected_bpr" | "fit_score" | "nil_value_placeholder" | "player_name";

export function PlayerTable({ players, portalDefault = false }: { players: Player[]; portalDefault?: boolean }) {
  const [query, setQuery] = useState("");
  const [position, setPosition] = useState("all");
  const [status, setStatus] = useState("all");
  const [team, setTeam] = useState("all");
  const [classYear, setClassYear] = useState("all");
  const [conference, setConference] = useState("all");
  const [playtype, setPlaytype] = useState("all");
  const [minBpr, setMinBpr] = useState(0);
  const [portalOnly, setPortalOnly] = useState(portalDefault);
  const [sortKey, setSortKey] = useState<SortKey>("projected_bpr");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const options = useMemo(() => {
    const unique = (values: string[]) => Array.from(new Set(values.filter(Boolean))).sort();
    return {
      teams: unique(players.flatMap((player) => [player.current_team, player.committed_team ?? ""])),
      conferences: unique(players.map((player) => player.conference)),
      playtypes: unique(players.map((player) => getTopPlaytypes(player, 1)[0]?.label ?? "")),
    };
  }, [players]);

  const filteredPlayers = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return players
      .filter((player) => {
        const topPlaytype = getTopPlaytypes(player, 1)[0]?.label;
        return (
          (!normalizedQuery ||
            player.player_name.toLowerCase().includes(normalizedQuery) ||
            player.current_team.toLowerCase().includes(normalizedQuery) ||
            player.committed_team?.toLowerCase().includes(normalizedQuery)) &&
          (position === "all" || player.position === position) &&
          (status === "all" || player.portal_status === status) &&
          (team === "all" || player.current_team === team || player.committed_team === team) &&
          (classYear === "all" || player.class_year === classYear) &&
          (conference === "all" || player.conference === conference) &&
          (playtype === "all" || topPlaytype === playtype) &&
          player.projected_bpr >= minBpr &&
          (!portalOnly || player.is_in_portal)
        );
      })
      .sort((a, b) => {
        if (sortKey === "player_name") return a.player_name.localeCompare(b.player_name);
        return b[sortKey] - a[sortKey];
      });
  }, [classYear, conference, minBpr, players, playtype, portalOnly, position, query, sortKey, status, team]);

  return (
    <section className="space-y-4">
      <div className="rounded border border-line bg-white p-4 shadow-soft">
        <div className="grid gap-3 xl:grid-cols-[1.3fr_repeat(7,minmax(112px,1fr))]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="h-10 w-full rounded border border-line bg-panel pl-9 pr-3 text-sm outline-none focus:border-ink"
              placeholder="Search player or team"
            />
          </label>
          <FilterSelect label="Position" value={position} onChange={setPosition} options={["all", "PG", "SG", "SF", "PF", "C"]} />
          <FilterSelect label="Class" value={classYear} onChange={setClassYear} options={["all", "Fr", "So", "Jr", "Sr", "Gr"]} />
          <FilterSelect label="Status" value={status} onChange={setStatus} options={["all", "entered", "committed", "enrolled", "not_in_portal"]} />
          <FilterSelect label="Team" value={team} onChange={setTeam} options={["all", ...options.teams]} />
          <FilterSelect label="Conference" value={conference} onChange={setConference} options={["all", ...options.conferences]} />
          <FilterSelect label="Playtype" value={playtype} onChange={setPlaytype} options={["all", ...options.playtypes]} />
          <label className="grid h-10 grid-cols-[1fr_56px] items-center rounded border border-line bg-panel px-2 text-xs font-semibold text-slate-500">
            BPR
            <input
              type="number"
              min={0}
              max={10}
              step={0.5}
              value={minBpr}
              onChange={(event) => setMinBpr(Number(event.target.value))}
              className="h-7 rounded border border-line bg-white px-2 text-sm text-ink outline-none"
            />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setPortalOnly((value) => !value)}
            className={clsx(
              "inline-flex h-9 items-center gap-2 rounded border px-3 text-sm font-semibold",
              portalOnly ? "border-ink bg-ink text-white" : "border-line bg-panel text-slate-700",
            )}
          >
            <SlidersHorizontal className="h-4 w-4" />
            In Portal
          </button>
          <div className="text-sm text-slate-600">
            {filteredPlayers.length} of {players.length} players
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded border border-line bg-white shadow-soft">
        <div className="hidden grid-cols-[2fr_.8fr_1fr_.8fr_.8fr_.8fr_.8fr_44px] border-b border-line bg-panel px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 md:grid">
          <SortButton label="Player" active={sortKey === "player_name"} onClick={() => setSortKey("player_name")} />
          <div>Pos</div>
          <div>Team</div>
          <div>Status</div>
          <SortButton label="BPR" active={sortKey === "projected_bpr"} onClick={() => setSortKey("projected_bpr")} />
          <SortButton label="Fit" active={sortKey === "fit_score"} onClick={() => setSortKey("fit_score")} />
          <SortButton label="NIL" active={sortKey === "nil_value_placeholder"} onClick={() => setSortKey("nil_value_placeholder")} />
          <div />
        </div>

        {filteredPlayers.map((player) => {
          const topPlaytype = getTopPlaytypes(player, 1)[0];
          const expanded = expandedId === player.player_id;
          return (
            <article key={player.player_id} className="border-b border-line last:border-b-0">
              <button
                type="button"
                onClick={() => setExpandedId(expanded ? null : player.player_id)}
                className="grid w-full gap-3 px-4 py-4 text-left hover:bg-panel md:grid-cols-[2fr_.8fr_1fr_.8fr_.8fr_.8fr_.8fr_44px] md:items-center"
              >
                <div>
                  <div className="font-semibold text-ink">{player.player_name}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {player.height} | {player.weight} | {player.class_year} | {topPlaytype?.label}
                  </div>
                </div>
                <div className="text-sm font-semibold text-slate-700">{player.position}</div>
                <div className="text-sm text-slate-700">
                  {player.committed_team ?? player.current_team}
                  {player.committed_team ? <span className="block text-xs text-slate-500">from {player.current_team}</span> : null}
                </div>
                <div>
                  <StatusBadge status={player.portal_status} />
                </div>
                <TableNumber value={player.projected_bpr.toFixed(1)} label="BPR" />
                <TableNumber value={`${player.fit_score}`} label="Fit" />
                <TableNumber value={`$${Math.round(player.nil_value_placeholder / 1000)}k`} label="NIL" />
                <ChevronDown className={clsx("h-5 w-5 justify-self-end text-slate-500 transition", expanded && "rotate-180")} />
              </button>
              {expanded ? <PlayerDetailPanel player={player} /> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <label className="relative block">
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full appearance-none rounded border border-line bg-panel px-3 pr-8 text-sm outline-none focus:border-ink"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option === "all" ? label : option.replaceAll("_", " ")}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
    </label>
  );
}

function SortButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx("inline-flex items-center gap-1 text-left", active ? "text-ink" : "text-slate-500")}
    >
      {label}
      <ArrowUpDown className="h-3.5 w-3.5" />
    </button>
  );
}

function TableNumber({ value, label }: { value: string; label: string }) {
  return (
    <div className="flex items-center justify-between gap-2 text-sm font-semibold tabular-nums text-ink md:block">
      <span className="text-xs font-medium text-slate-500 md:hidden">{label}</span>
      {value}
    </div>
  );
}
