import type { ReactNode } from "react";
import { Link } from "react-router-dom";

type Props = {
  children: ReactNode;
  className?: string;
  variant?: "primary" | "danger" | "ghost" | "default";
  size?: "md" | "xl";
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  href?: string;
  target?: string;
  rel?: string;
};

const variants: Record<NonNullable<Props["variant"]>, string> = {
  primary: "grad-forge text-black font-semibold border-transparent hover:brightness-110",
  danger: "bg-transparent text-danger border-danger/40 hover:bg-danger/10",
  ghost: "bg-transparent text-text-dim border-border hover:border-border-soft hover:text-text",
  default: "bg-card-2 text-text border-border hover:border-border-soft",
};

/** Map /panel/... full paths onto the React Router basename (/panel). */
function panelTo(href: string): string | null {
  if (/^https?:\/\//i.test(href)) return null;
  if (href.startsWith("/panel/") || href === "/panel") {
    const rest = href.slice("/panel".length) || "/";
    return rest.startsWith("/") ? rest : `/${rest}`;
  }
  if (href.startsWith("/")) return href;
  return null;
}

export function Button({
  children,
  className = "",
  variant = "default",
  size = "md",
  disabled,
  onClick,
  type = "button",
  href,
  target,
  rel,
}: Props) {
  const cls = [
    "inline-flex items-center justify-center gap-2 rounded-md border text-[13px] transition-colors duration-150",
    size === "xl" ? "px-4 py-2.5 min-w-[7rem]" : "px-3 py-1.5",
    variants[variant],
    disabled ? "opacity-45 pointer-events-none" : "",
    className,
  ].join(" ");

  if (href) {
    const to = panelTo(href);
    if (to) {
      return (
        <Link className={cls} to={to} onClick={onClick}>
          {children}
        </Link>
      );
    }
    const external = /^https?:\/\//i.test(href);
    return (
      <a
        className={cls}
        href={href}
        target={target ?? (external ? "_blank" : undefined)}
        rel={rel ?? (external ? "noopener noreferrer" : undefined)}
      >
        {children}
      </a>
    );
  }
  return (
    <button type={type} className={cls} disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}
