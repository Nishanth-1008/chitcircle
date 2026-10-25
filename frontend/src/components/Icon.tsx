import type { SVGProps } from 'react';

const PATHS = {
  home: 'M3 11.5 12 4l9 7.5M5.5 10v9.5h13V10M10 19.5v-5h4v5',
  circles: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM2.5 20c.6-3.3 3.2-5 6.5-5s5.9 1.7 6.5 5M16.5 4.4a3.5 3.5 0 0 1 0 6.7M18 15.2c1.8.6 3 2 3.5 4.8',
  activity: 'M7 4 3.5 7.5 7 11M3.5 7.5H15M17 13l3.5 3.5L17 20M20.5 16.5H9',
  profile: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20.5c.8-3.6 3.7-5.5 7.5-5.5s6.7 1.9 7.5 5.5',
  chevronRight: 'm9 5 7 7-7 7',
  chevronLeft: 'm15 5-7 7 7 7',
  chevronDown: 'm5 9 7 7 7-7',
  plus: 'M12 5v14M5 12h14',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5l3 2',
  check: 'm5 12.5 4.5 4.5L19 7.5',
  checkCircle: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-4-9 3 3 5-6',
  alert: 'M12 3.5 2.8 19.5h18.4L12 3.5ZM12 10v4.5M12 17.2v.1',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 11v5M12 7.8v.1',
  lock: 'M6.5 11V8a5.5 5.5 0 0 1 11 0v3M5 11h14v9.5H5V11Z',
  refresh: 'M20 12a8 8 0 1 1-2.6-5.9M20 4v5h-5',
  gavel: 'm14 5 5 5M10.5 8.5l5 5M4 20l7-7M8.5 3.5l5 5-4 4-5-5 4-4ZM12 20h8',
  calendar: 'M4 7h16v13H4V7ZM4 11h16M8 4v4M16 4v4',
  arrowDown: 'M12 5v14M6 13l6 6 6-6',
  arrowUp: 'M12 19V5M6 11l6-6 6 6',
  wallet: 'M4 7.5h15.5V19H4V7.5ZM4 7.5 16 4v3.5M15.5 13.5h4',
  trophy: 'M8 4h8v5a4 4 0 0 1-8 0V4ZM8 6H4.5a3 3 0 0 0 3.5 4M16 6h3.5A3 3 0 0 1 16 10M12 13v4M8.5 20h7M10 17h4',
  file: 'M7 3.5h7l4 4V20.5H7V3.5ZM14 3.5v4h4M10 12h5M10 16h5',
  scale: 'M12 4v16M6 20h12M4 8h16M7 8l-3 6a3.2 3.2 0 0 0 6 0L7 8ZM17 8l-3 6a3.2 3.2 0 0 0 6 0l-3-6Z',
  help: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM9.5 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-.9.8-.9 1.4M12 16.5v.1',
  moon: 'M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z',
  signOut: 'M10 4H5v16h5M15 8l4 4-4 4M19 12H9',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM20 20l-4-4',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM2.5 20c.6-3.3 3.2-5 6.5-5s5.9 1.7 6.5 5',
  receipt: 'M6 3.5h12V21l-3-2-3 2-3-2-3 2V3.5ZM9 8.5h6M9 12.5h6',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1',
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, ...rest }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true" focusable="false" {...rest}>
      <path d={PATHS[name]} />
    </svg>
  );
}
