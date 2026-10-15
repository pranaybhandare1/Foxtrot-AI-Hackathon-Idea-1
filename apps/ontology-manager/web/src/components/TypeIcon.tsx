/** Object-type glyphs for the Ontology Manager: a coloured rounded square with a line icon, Foundry-style. */

import type { ReactNode } from "react";

const PATHS: Record<string, ReactNode> = {
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>,
  droplet: <path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z" />,
  drop_check: <><path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z" /><path d="m9.5 14 2 2 3.5-4" /></>,
  sensor: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></>,
  syringe: <><path d="m18 2 4 4M17 7l-9.5 9.5L4 20M20 4l-3 3M14 4l6 6" /><path d="m8 13 3 3" /></>,
  calculator: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M8 7h8M8 12h2M14 12h2M8 16h2M14 16h2" /></>,
  utensils: <><path d="M7 3v8a2 2 0 0 0 2 2v8M11 3v8M7 7h4" /><path d="M17 3c-2 0-3 2-3 5s1 4 3 4v9" /></>,
  wave: <path d="M2 12c2.5 0 2.5-6 5-6s2.5 12 5 12 2.5-12 5-12 2.5 6 5 6" />,
  bell: <><path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4z" /><path d="M10 20a2 2 0 0 0 4 0" /></>,
  pause: <><circle cx="12" cy="12" r="9" /><path d="M10 9v6M14 9v6" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  ring: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="5" /><path d="M12 4v2" /></>,
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" />,
  activity: <path d="M3 12h4l3-8 4 16 3-8h4" />,
  grid: <><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M3 15h18M9 3v18M15 3v18" /></>,
  heart: <path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.5-7 10-7 10Z" />,
  flask: <><path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3" /><path d="M7 15h10" /></>,
  note: <><path d="M5 3h10l4 4v14H5z" /><path d="M15 3v4h4M8 12h8M8 16h5" /></>,
  link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></>,
  bolt: <path d="M13 2 4 14h7l-1 8 9-12h-7z" />,
  cube: <><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9z" /><path d="m4 7.5 8 4.5 8-4.5M12 12v9" /></>,
};

export function TypeIcon({ icon, color, size = 28 }: { icon: string; color: string; size?: number }) {
  return (
    <span className="type-icon" style={{ width: size, height: size, background: `${color}22`, color, borderColor: `${color}55` }}>
      <svg width={size * 0.6} height={size * 0.6} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
        strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        {PATHS[icon] ?? PATHS.cube}
      </svg>
    </span>
  );
}
