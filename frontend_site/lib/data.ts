import { players, type Player, type PortalStatus } from "@/data/players";
import { teams, type Team } from "@/data/teams";

export type PlayerFilters = {
  query?: string;
  team?: string;
  position?: string;
  classYear?: string;
  portalStatus?: string;
  conference?: string;
  playtype?: string;
  minBpr?: number;
  portalOnly?: boolean;
  availableOnly?: boolean;
};

export function getPlayers(filters: PlayerFilters = {}) {
  return players.filter((player) => {
    const query = filters.query?.trim().toLowerCase();
    const topPlaytype = getTopPlaytypes(player, 1)[0]?.label;
    return (
      (!query ||
        player.player_name.toLowerCase().includes(query) ||
        player.current_team.toLowerCase().includes(query) ||
        player.previous_team?.toLowerCase().includes(query)) &&
      (!filters.team || player.current_team === filters.team || player.committed_team === filters.team) &&
      (!filters.position || player.position === filters.position) &&
      (!filters.classYear || player.class_year === filters.classYear) &&
      (!filters.portalStatus || player.portal_status === filters.portalStatus) &&
      (!filters.conference || player.conference === filters.conference) &&
      (!filters.playtype || topPlaytype === filters.playtype) &&
      (!filters.minBpr || player.projected_bpr >= filters.minBpr) &&
      (!filters.portalOnly || player.is_in_portal) &&
      (!filters.availableOnly || player.portal_status === "entered")
    );
  });
}

export function getPortalPlayers() {
  return players.filter((player) => player.is_in_portal);
}

export function getTeams() {
  return teams;
}

export function getTeam(teamId: string): Team | undefined {
  return teams.find((team) => team.team_id === teamId);
}

export function getTeamPlayers(teamName: string) {
  return players.filter(
    (player) =>
      player.current_team === teamName ||
      player.committed_team === teamName ||
      player.new_team === teamName,
  );
}

export function getRecommendations(teamName: string) {
  return getPortalPlayers()
    .map((player) => ({
      ...player,
      fit_score: Math.min(99, player.fit_score + teamAdjustment(teamName, player.position)),
    }))
    .sort((a, b) => b.fit_score - a.fit_score || b.projected_bpr - a.projected_bpr);
}

export function getTopPlaytypes(player: Player, count = 3) {
  return Object.entries(player.playtype_probabilities)
    .sort((a, b) => b[1] - a[1])
    .slice(0, count)
    .map(([label, probability]) => ({ label, probability }));
}

export function formatStatus(status: PortalStatus) {
  return status
    .split("_")
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function teamAdjustment(teamName: string, position: Player["position"]) {
  if (teamName === "Indiana" && ["PG", "PF", "C"].includes(position)) return 6;
  if (teamName === "UCLA" && ["SG", "SF", "C"].includes(position)) return 5;
  if (teamName === "UConn" && ["PG", "PF"].includes(position)) return 4;
  if (teamName === "Providence" && ["SF", "C"].includes(position)) return 6;
  return 0;
}
