import clsx from "clsx";
import { formatStatus } from "@/lib/data";
import type { PortalStatus } from "@/data/players";

const statusStyles: Record<PortalStatus, string> = {
  not_in_portal: "border-slate-300 bg-slate-100 text-slate-700",
  entered: "border-amber-300 bg-amber-100 text-amber-800",
  committed: "border-blue-300 bg-blue-100 text-blue-800",
  enrolled: "border-emerald-300 bg-emerald-100 text-emerald-800",
};

export function StatusBadge({ status }: { status: PortalStatus }) {
  return (
    <span
      className={clsx(
        "inline-flex h-7 items-center whitespace-nowrap rounded border px-2 text-xs font-semibold",
        statusStyles[status],
      )}
    >
      {formatStatus(status)}
    </span>
  );
}
