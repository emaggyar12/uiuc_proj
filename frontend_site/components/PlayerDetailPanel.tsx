import type React from "react";
import { Activity, BadgeDollarSign, ClipboardList, Target } from "lucide-react";
import type { Player } from "@/data/players";
import { formatCurrency, getTopPlaytypes } from "@/lib/data";

export function PlayerDetailPanel({ player }: { player: Player }) {
  const playtypes = getTopPlaytypes(player, 4);

  return (
    <div className="grid gap-4 border-t border-line bg-white px-4 py-4 text-sm md:grid-cols-[1.2fr_1fr_1fr]">
      <section className="space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <ClipboardList className="h-4 w-4" />
          Profile
        </div>
        <p className="leading-6 text-slate-700">{player.scouting_summary}</p>
        <p className="leading-6 text-slate-700">{player.fit_explanation}</p>
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <Target className="h-4 w-4" />
          Playtype Probabilities
        </div>
        <div className="space-y-2">
          {playtypes.map((playtype) => (
            <div key={playtype.label} className="grid grid-cols-[92px_1fr_44px] items-center gap-2">
              <span className="truncate text-xs font-medium text-slate-700">{playtype.label}</span>
              <div className="h-2 overflow-hidden rounded bg-slate-200">
                <div
                  className="h-full rounded bg-emerald-600"
                  style={{ width: `${Math.round(playtype.probability * 100)}%` }}
                />
              </div>
              <span className="text-right text-xs tabular-nums text-slate-600">
                {Math.round(playtype.probability * 100)}%
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-2">
        <Metric icon={<Activity className="h-4 w-4" />} label="BPR" value={player.projected_bpr.toFixed(1)} />
        <Metric label="MIN" value={player.projected_minutes.toFixed(0)} />
        <Metric label="PTS" value={player.projected_points.toFixed(1)} />
        <Metric label="REB" value={player.projected_rebounds.toFixed(1)} />
        <Metric label="AST" value={player.projected_assists.toFixed(1)} />
        <Metric icon={<BadgeDollarSign className="h-4 w-4" />} label="NIL" value={formatCurrency(player.nil_value_placeholder)} />
      </section>
    </div>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="min-h-16 rounded border border-line bg-panel p-3">
      <div className="flex items-center gap-1 text-xs font-semibold text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 truncate text-lg font-semibold text-ink">{value}</div>
    </div>
  );
}
