import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";

const badgeVariants = cva(
  "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium font-mono tracking-wide transition-colors",
  {
    variants: {
      variant: {
        default: "bg-stone-100 text-stone-600",
        emerald: "bg-emerald-50 text-emerald-700",
        outline: "border border-stone-200 text-stone-500",
        destructive: "bg-red-50 text-red-700",
        warning: "bg-amber-50 text-amber-700",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
