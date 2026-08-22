import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function icon({ size = 20, className, ...rest }: IconProps) {
  return { width: size, height: size, className, viewBox: "0 0 24 24", fill: "none", ...rest };
}

export function IconGrid(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}

export function IconServer(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="4" width="18" height="6" rx="1.5" />
      <rect x="3" y="14" width="18" height="6" rx="1.5" />
      <circle cx="7" cy="7" r="1" fill="currentColor" stroke="none" />
      <circle cx="7" cy="17" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function IconNetwork(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" />
    </svg>
  );
}

export function IconBuilds(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <path d="M4 20h16M6 16V8l6-4 6 4v8" />
      <path d="M10 20v-6h4v6" />
    </svg>
  );
}

export function IconPlay(p: IconProps) {
  return (
    <svg {...icon(p)} fill="currentColor">
      <path d="M8 5.5v13l11-6.5L8 5.5z" />
    </svg>
  );
}

export function IconStop(p: IconProps) {
  return (
    <svg {...icon(p)} fill="currentColor">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

export function IconRestart(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <path d="M20 12a8 8 0 1 1-2.3-5.6" />
      <path d="M20 4v5h-5" />
    </svg>
  );
}

export function IconTerminal(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="m7 9 3 3-3 3M12 15h5" />
    </svg>
  );
}

export function IconPlus(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function IconFiles(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
      <path d="M14 3v5h5" />
    </svg>
  );
}

export function IconUsers(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <circle cx="9" cy="8" r="3" />
      <path d="M3 19c0-3 2.5-5 6-5s6 2 6 5" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M21 19c0-2.2-1.5-3.8-4-4.2" />
    </svg>
  );
}

export function IconCpu(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
      <path d="M9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4" />
    </svg>
  );
}

export function IconHeart(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <path d="M12 20s-7-4.4-7-9.2A3.8 3.8 0 0 1 12 7.5a3.8 3.8 0 0 1 7 3.3C19 15.6 12 20 12 20z" />
    </svg>
  );
}

export function IconCopy(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M4 16V6a2 2 0 0 1 2-2h10" />
    </svg>
  );
}

export function IconSystem(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
      <path d="M9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4" />
    </svg>
  );
}

export function IconCloud(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <path d="M7 18h10a4 4 0 0 0 .5-8 5.5 5.5 0 0 0-10.5-1.5A3.5 3.5 0 0 0 7 18z" />
    </svg>
  );
}

export function IconProfiles(p: IconProps) {
  return (
    <svg {...icon(p)} stroke="currentColor" strokeWidth="1.8">
      <path d="M8 4h8l1 2h3v14H4V6h3l1-2z" />
      <path d="M9 12h6M9 15h4" />
    </svg>
  );
}
