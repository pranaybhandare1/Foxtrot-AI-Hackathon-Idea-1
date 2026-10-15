/** Minimal line-icon set (24px grid, currentColor). */

import type { SVGProps } from "react";

const Svg = (props: SVGProps<SVGSVGElement>) => (
  <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden {...props} />
);

export const Icons = {
  overview: () => (<Svg><rect x="3" y="3" width="7" height="9" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" /><rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="16" width="7" height="5" rx="2" /></Svg>),
  agp: () => (<Svg><path d="M3 17c3 0 4-8 7-8s4 6 7 6 3-4 4-4" /><path d="M3 20c3 0 4-5 7-5s4 3 7 3 3-2 4-2" opacity=".45" /><path d="M3 13c3 0 4-9 7-9s4 7 7 7 3-5 4-5" opacity=".45" /></Svg>),
  history: () => (<Svg><rect x="3" y="3" width="18" height="18" rx="3" /><path d="M3 8h18M3 13h18M3 18h18" opacity=".45" /><circle cx="9" cy="10.5" r="1.2" fill="currentColor" /><circle cx="15" cy="15.5" r="1.2" fill="currentColor" /></Svg>),
  report: () => (<Svg><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5M10 13h6M10 17h6M10 9h2" /></Svg>),
  print: () => (<Svg><path d="M7 8V3h10v5M7 17H4v-7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7h-3" /><rect x="7" y="14" width="10" height="7" rx="1" /></Svg>),
  daily: () => (<Svg><rect x="3" y="4" width="18" height="17" rx="3" /><path d="M3 9h18M8 2v4M16 2v4" /><path d="M7 15l3-2 3 3 4-4" /></Svg>),
  weekly: () => (<Svg><path d="M4 20V10M8 20V6M12 20v-8M16 20V4M20 20v-6" /></Svg>),
  meals: () => (<Svg><path d="M4 11h16a8 8 0 0 1-16 0Z" /><path d="M9 7c0-1.5 1-1.5 1-3M13 7c0-1.5 1-1.5 1-3" /></Svg>),
  lows: () => (<Svg><path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z" /><path d="M9.5 14.5 12 17l2.5-2.5" /></Svg>),
  insulin: () => (<Svg><path d="m18 2 4 4M17 7l-9.5 9.5L4 20M20 4l-3 3M14 4l6 6M11.5 6.5l6 6" /><path d="m8 13 3 3" /></Svg>),
  devices: () => (<Svg><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 4v2M12 18v2M4 12h2M18 12h2" /></Svg>),
  explorer: () => (<Svg><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="7" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M8.3 7.2 15.6 7M7.2 8.2l3.7 7.6M16.9 9.2l-3.8 6.7" /></Svg>),
  insights: () => (<Svg><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.4 1 1.1 1 1.8V16h5v-.3c0-.7.4-1.4 1-1.8A6 6 0 0 0 12 3Z" /></Svg>),
  quality: () => (<Svg><path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6l-8-3Z" /><path d="m8.5 12 2.5 2.5 4.5-5" /></Svg>),
  sun: () => (<Svg><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Svg>),
  moon: () => (<Svg><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" /></Svg>),
  collapse: () => (<Svg><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /></Svg>),
  left: () => (<Svg><path d="m15 18-6-6 6-6" /></Svg>),
  right: () => (<Svg><path d="m9 18 6-6-6-6" /></Svg>),
  close: () => (<Svg><path d="M18 6 6 18M6 6l12 12" /></Svg>),
  search: () => (<Svg><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></Svg>),
  arrowUp: () => (<Svg width={12} height={12}><path d="M12 19V5M5 12l7-7 7 7" /></Svg>),
  arrowDown: () => (<Svg width={12} height={12}><path d="M12 5v14M19 12l-7 7-7-7" /></Svg>),
  external: () => (<Svg width={14} height={14}><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></Svg>),
};
