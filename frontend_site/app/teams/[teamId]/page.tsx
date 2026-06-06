import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { PlayerTable } from "@/components/PlayerTable";
import { RecommendationsBoard } from "@/components/RecommendationsBoard";
import { Shell } from "@/components/Shell";
import { getTeam, getTeamPlayers } from "@/lib/data";

export default function TeamPage({ params }: { params: { teamId: string } }) {
  const team = getTeam(params.teamId);
  if (!team) notFound();

  const roster = getTeamPlayers(team.team_name);

  return (
    <Shell>
      <Link href="/" className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-slate-700 hover:text-ink">
        <ArrowLeft className="h-4 w-4" />
        Players
      </Link>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-ink">{team.team_name}</h1>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
          {team.conference} | {team.style} | Needs: {team.needs.join(", ")}
        </p>
      </div>
      <div className="mb-6 grid gap-3 md:grid-cols-3">
        <Metric label="Scholarships Used" value={`${team.scholarships_used}/${team.roster_limit}`} />
        <Metric label="Tracked Roster" value={`${roster.length}`} />
        <Metric label="Portal Commits" value={`${roster.filter((player) => player.committed_team === team.team_name).length}`} />
      </div>
      <div className="space-y-8">
        <section>
          <h2 className="mb-3 text-lg font-semibold text-ink">Roster And Commitments</h2>
          <PlayerTable players={roster} />
        </section>
        <section>
          <h2 className="mb-3 text-lg font-semibold text-ink">Recommended Portal Fits</h2>
          <RecommendationsBoard defaultTeam={team.team_name} />
        </section>
      </div>
    </Shell>
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
