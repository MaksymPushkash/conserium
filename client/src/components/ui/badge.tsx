import * as React from "react";

import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center rounded-md border border-white/10 bg-white/[0.04] px-2 text-xs font-medium text-neutral-400",
        className,
      )}
      {...props}
    />
  );
}
