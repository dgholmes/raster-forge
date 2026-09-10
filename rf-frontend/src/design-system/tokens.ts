/* ============================================================================
 * tokens.ts — the design system (dark + light).
 *
 * macOS-style dark / light with iOS-blue accent, Outfit + Pretendard type.
 * Every component reads colours from the `C` object returned by useTheme().
 * Do NOT hardcode hex values in components — add a token here instead.
 *
 * Full rules (spacing grid, typography scale, component recipes) live in the
 * `ui-design-system` skill; this file is the runtime source of those tokens.
 * ========================================================================== */

export interface C {
  appBg: string; win: string; side: string; main: string; bar: string;
  b: string; bL: string;
  t1: string; t2: string; t3: string;      // text: primary / secondary / muted
  card: string; cardB: string; cardH: string;
  row: string; activeBg: string;
  inp: string; inpB: string;
  pill: string; pillT: string;
  accent: string; accentBg: string;
  thumbBg: string;
  dark: boolean;
}

export const DARK: C = {
  appBg: '#0f0f11', win: '#1c1c1e', side: '#1f1f21', main: '#181819', bar: '#232325',
  b: '#2c2c2e', bL: '#383838',
  t1: '#e8e8ea', t2: '#aeaeb2', t3: '#636366',
  card: '#28282b', cardB: '#2e2e31', cardH: '#323235',
  row: 'rgba(255,255,255,0.04)', activeBg: 'rgba(255,255,255,0.08)',
  inp: '#2a2a2c', inpB: '#3a3a3c',
  pill: 'rgba(255,255,255,0.06)', pillT: '#aeaeb2',
  accent: '#0a84ff', accentBg: 'rgba(10,132,255,0.10)',
  thumbBg: '#252527',
  dark: true,
};

export const LIGHT: C = {
  appBg: '#d1d1d6', win: '#f5f5f7', side: '#ffffff', main: '#f0f0f3', bar: '#e8e8ed',
  b: '#d1d1d6', bL: '#e5e5ea',
  t1: '#1c1c1e', t2: '#48484a', t3: '#636366',   // t3 stays #636366 in both — passes AA
  card: '#ffffff', cardB: '#e5e5ea', cardH: '#f9f9fb',
  row: 'rgba(0,0,0,0.04)', activeBg: 'rgba(0,0,0,0.07)',
  inp: '#f0f0f3', inpB: '#d1d1d6',
  pill: 'rgba(0,0,0,0.05)', pillT: '#48484a',
  accent: '#0a84ff', accentBg: 'rgba(10,132,255,0.08)',
  thumbBg: '#e8e8ed',
  dark: false,
};

/** Semantic status colours — identical in both themes. Use only for meaning. */
export const STATUS = {
  green: '#30d158', amber: '#ff9f0a', red: '#ff453a',
  greenBg: 'rgba(48,209,88,0.12)', amberBg: 'rgba(255,159,10,0.12)', redBg: 'rgba(255,67,58,0.12)',
};

export const FONT =
  "'Outfit','Pretendard Variable','Pretendard','Noto Sans KR',system-ui,sans-serif";

/** Translucent dark-glass used by panels/toolbars that float over the map.
 *  Reserved for floating overlays (list panels, detail cards, dev/testing
 *  panels) — never for static/docked chrome or ordinary list cards.
 *
 *  GOTCHA: backdrop-filter only blurs pixels actually behind the element in
 *  the DOM. If the "glass" panel is laid out as a flex/grid sibling next to
 *  the map (not stacked on top of it via position:absolute/fixed), there is
 *  nothing behind it to blur and it will just look like a flat tinted box —
 *  this is the single most common way this recipe silently "stops working."
 *  Always position glass panels so real content renders underneath them, and
 *  never nest one glass surface inside another. */
export function mapGlass(dark: boolean): React.CSSProperties {
  return {
    background: dark ? 'rgba(8,11,16,0.55)' : 'rgba(255,255,255,0.62)',
    backdropFilter: 'blur(28px)', WebkitBackdropFilter: 'blur(28px)',
    border: dark ? '1px solid rgba(255,255,255,0.07)' : '1px solid rgba(0,0,0,0.06)',
    boxShadow: dark
      ? '0 8px 32px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06)'
      : '0 6px 24px rgba(0,0,0,0.10)',
  };
}

/** Docked-chrome glass — subtler blur than mapGlass, for permanent shell
 *  pieces that sit beside/over content rather than floating above it in a
 *  small card (Topbar, a Sidebar used with an overlay Topbar). Same recipe
 *  Topbar uses inline; a Sidebar that opts into glass (see its `glass` prop)
 *  reads it from here so both stay in sync.
 *
 *  Only apply this to a Sidebar when it is ALSO positioned as an overlay
 *  (position:absolute/fixed on top of full-bleed map/content) alongside an
 *  overlay Topbar — the same "needs real content behind it" rule as
 *  mapGlass applies. A Sidebar laid out in normal flow next to the map has
 *  nothing to blur and should stay solid (the default, `glass` unset). */
export function chromeGlass(dark: boolean): React.CSSProperties {
  return {
    background: dark ? 'rgba(8,11,16,0.82)' : 'rgba(248,248,250,0.88)',
    backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
    border: dark ? '1px solid rgba(255,255,255,0.09)' : '1px solid rgba(0,0,0,0.08)',
  };
}

/** Translucent input styling for controls that live INSIDE an already-glass
 *  panel — a solid opaque `inp` fill looks like a flat box floating in the
 *  middle of a glass surface. No separate blur needed here; the panel
 *  behind it already provides that. Keep the border subtle (not the bright
 *  0.14+ opacity it's tempting to reach for) — it only needs to read as a
 *  distinct control, not compete visually with the panel's own edge. */
export function glassInput(dark: boolean): React.CSSProperties {
  return {
    background: dark ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.35)',
    border: dark ? '1px solid rgba(255,255,255,0.09)' : '1px solid rgba(0,0,0,0.08)',
  };
}

import type React from 'react';
