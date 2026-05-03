import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md border px-3 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "border-white bg-white text-black shadow-[0_0_28px_rgba(255,255,255,0.12)] hover:bg-neutral-200",
        secondary: "border-white/10 bg-white/[0.04] text-white hover:bg-white/10",
        ghost: "border-transparent bg-transparent text-neutral-400 hover:bg-white/10 hover:text-white",
        danger: "border-white/10 bg-black text-white hover:border-red-500 hover:text-red-400",
      },
      size: {
        default: "h-9 px-3",
        sm: "h-8 px-2 text-xs",
        icon: "h-9 w-9 px-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}
