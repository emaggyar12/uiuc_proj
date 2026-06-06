"use client";

import { useMemo, useState } from "react";
import { ChevronDown, Target } from "lucide-react";
import { getRecommendations, getTeams, getTopPlaytypes } from "@/lib/data";
import { StatusBadge } from "@/components/StatusBadge";

export function RecommendationsBoard({ defaultTeam = "UConn" }: { defaultTeam?: string }) {
  const teams = getTeams();
  const [teamName, setTeamName] = useState(defaultTeam);
  const recommendations = useMemo(() => getRecommendations(teamName), [teamName]);
  const selectedTeam = teams.find((team) => team.team_name === teamName) ?? teams[0];

  return (
    <section className="space-y-4">
      <div className="rounded border border-line bg-white p-4 shadow-soft">
        <div className="grid gap-4 md:grid-cols-[280px_1fr] md:items-center">
          <label className="relative block">
            <select
              value={teamName}
              onChange={(event) => setTeamName(event.target.value)}
              className="h-10 w-full appearance-none rounded border border-line bg-panel px-3 pr-8 text-sm outline-none focus:border-ink"
            >
              {teams.map((team) => (
                <option key={team.team_id} value={team.team_name}>
                  {team.team_name}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
          </label>
          <div className="text-sm text-slate-700">
            <span className="font-semibold text-ink">{selectedTeam.style}</span>
            <span className="ml-2 text-slate-500">Needs: {selectedTeam.needs.join(", ")}</span>
          </div>
        </div>
      </div>

      <div className="grid gap-3">
        {recommendations.slice(0, 8).map((player, index) => {
          const topPlaytypes = getTopPlaytypes(player, 3);
          return (
            <article key={player.player_id} className="rounded border border-line bg-white p-4 shadow-soft">
              <div className="grid gap-4 lg:grid-cols-[56px_1.2fr_1fr_1fr] lg:items-center">
                <div className="flex h-12 w-12 items-center justify-center rounded bg-ink text-lg font-semibold text-white">
                  {index + 1}
                </div>
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-semibold text-ink">{player.player_name}</h3>
                    <StatusBadge status={player.portal_status} />
                  </div>
                  <div className="mt-1 text-sm text-slate-600">
                    {player.position} | {player.height} | {player.current_team} | BPR {player.projected_bpr.toFixed(1)}
                  </div>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Role Projection</div>
                  <div className="mt-1 text-sm text-slate-700">
                    {topPlaytypes.map((playtype) => `${playtype.label} ${Math.round(playtype.probability * 100)}%`).join(" / ")}
                  </div>
                </div>
                <div>
                  <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    <Target className="h-4 w-4" />
                    Fit Score
                  </div>
                  <div className="h-2 overflow-hidden rounded bg-slate-200">
                    <div className="h-full rounded bg-emerald-600" style={{ width: `${player.fit_score}%` }} />
                  </div>
                  <div className="mt-2 text-sm font-semibold text-ink">{player.fit_score}/100</div>
                </div>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-700">{player.fit_explanation}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
