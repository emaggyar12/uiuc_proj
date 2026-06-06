import { PlayerTable } from "@/components/PlayerTable";
import { Shell } from "@/components/Shell";
import { getPlayers } from "@/lib/data";

export default function HomePage() {
  const players = getPlayers();
  const portalCount = players.filter((player) => player.is_in_portal).length;

  return (
    <Shell>
      <PageHeader
        title="Player Leaderboard"
        description="Search, filter, sort, and expand players across the roster and transfer portal pool."
      />
      <div className="mb-4 grid gap-3 md:grid-cols-4">
        <Metric label="Tracked Players" value={`${players.length}`} />
        <Metric label="In Portal" value={`${portalCount}`} />
        <Metric label="Average BPR" value={(players.reduce((sum, player) => sum + player.projected_bpr, 0) / players.length).toFixed(1)} />
        <Metric label="Top Fit" value={`${Math.max(...players.map((player) => player.fit_score))}`} />
      </div>
      <PlayerTable players={players} />
    </Shell>
  );
}

function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-5">
      <h1 className="text-2xl font-semibold text-ink">{title}</h1>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{description}</p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-line bg-white p-4 shadow-soft">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-ink">{value}</div>
    </div>
  );
}
