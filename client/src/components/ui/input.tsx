import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-md border border-white/10 bg-white/[0.03] px-3 text-sm text-white outline-none transition-colors placeholder:text-neutral-600 focus:border-white/40",
        className,
      )}
      {...props}
    />
  );
}
