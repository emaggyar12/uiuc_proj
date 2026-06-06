import { RecommendationsBoard } from "@/components/RecommendationsBoard";
import { Shell } from "@/components/Shell";

export default function RecommendationsPage() {
  return (
    <Shell>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-ink">Best Available Fits</h1>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
          Rank transfers and high school recruits by projected roster fit, current production, and role probability for the selected team.
        </p>
      </div>
      <RecommendationsBoard />
    </Shell>
  );
}
