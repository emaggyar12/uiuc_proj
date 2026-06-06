import { PortalSimulator } from "@/components/PortalSimulator";
import { Shell } from "@/components/Shell";

export default function SimulatorPage() {
  return (
    <Shell>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold text-ink">Transfer Portal Simulator</h1>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
          Build a roster scenario by removing current players and adding portal targets while tracking scholarships and projected team quality.
        </p>
      </div>
      <PortalSimulator />
    </Shell>
  );
}
