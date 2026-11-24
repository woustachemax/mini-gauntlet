import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

// shadcn's Button, trimmed to the two variants this app uses. Hover changes colour only:
// no filled backgrounds and no shadows.
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-40 shrink-0 outline-none focus-visible:ring-ring focus-visible:ring-2",
  {
    variants: {
      variant: {
        outline: "border border-input text-foreground hover:border-muted-foreground",
        ghost: "text-muted-foreground hover:text-foreground",
      },
      size: {
        sm: "h-7 px-2 text-xs",
      },
    },
    defaultVariants: {
      variant: "outline",
      size: "sm",
    },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
