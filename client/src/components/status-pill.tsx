import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const styles: Record<string, string> = {
  READY: "text-emerald-400",
  FAILED: "text-red-400",
  PROCESSING: "text-orange-400",
  QUEUED: "text-sky-400",
  PENDING: "text-neutral-500",
};

export function StatusPill({ status }: { status: DocumentStatus | string }) {
  return (
    <Badge className={cn("font-jetbrains border-transparent bg-transparent px-0 uppercase shadow-none", styles[status] ?? styles.PENDING)}>
      {status}
    </Badge>
  );
}
