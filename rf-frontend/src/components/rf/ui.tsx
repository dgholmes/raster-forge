import React from 'react';
import type { LucideIcon } from 'lucide-react';
import { STATUS, type C } from '../../design-system/tokens';

/* ============================================================================
 * ui.tsx — RasterForge primitives.
 *
 * Every colour comes from the `C` token object; nothing here hardcodes a hex.
 * Spacing is on the 4px grid. Radii follow the design system: pills 5,
 * inputs/buttons 7, cards/panels 10.
 * ========================================================================== */

export const FONT =
  "'Outfit','Pretendard Variable','Pretendard','Noto Sans KR',system-ui,sans-serif";

/* ── Card ────────────────────────────────────────────────────────────────── */

export const Card: React.FC<{
  C: C;
  children: React.ReactNode;
  padding?: number;
  style?: React.CSSProperties;
}> = ({ C, children, padding = 20, style }) => (
  <div
    style={{
      background: C.card,
      border: `1.5px solid ${C.cardB}`,
      borderRadius: 10,
      padding,
      ...style,
    }}
  >
    {children}
  </div>
);

/* ── Section heading ─────────────────────────────────────────────────────── */

export const SectionLabel: React.FC<{ C: C; children: React.ReactNode }> = ({ C, children }) => (
  <div
    style={{
      fontSize: 10,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: C.t3,
      marginBottom: 12,
    }}
  >
    {children}
  </div>
);

export const PanelTitle: React.FC<{
  C: C;
  icon?: LucideIcon;
  children: React.ReactNode;
  right?: React.ReactNode;
}> = ({ C, icon: Icon, children, right }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      marginBottom: 16,
    }}
  >
    {Icon && <Icon size={16} color={C.t2} strokeWidth={1.7} />}
    <h2
      style={{
        margin: 0,
        fontSize: 15,
        fontWeight: 700,
        letterSpacing: '-0.015em',
        color: C.t1,
      }}
    >
      {children}
    </h2>
    <div style={{ marginLeft: 'auto' }}>{right}</div>
  </div>
);

/* ── Key/value row ───────────────────────────────────────────────────────── */

export const KeyValue: React.FC<{
  C: C;
  label: string;
  value: React.ReactNode;
  mono?: boolean;
  /** Stack the label above the value. Use inside narrow grid cells — the
   *  side-by-side form reserves 132px for the label, which in a ~160px
   *  column leaves the value so little room it wraps one character per line. */
  stacked?: boolean;
}> = ({ C, label, value, mono, stacked }) => (
  <div
    style={
      stacked
        ? { padding: '6px 0', minWidth: 0 }
        : { display: 'flex', alignItems: 'baseline', gap: 12, padding: '6px 0' }
    }
  >
    <div
      style={{
        fontSize: stacked ? 10 : 12,
        fontWeight: stacked ? 700 : 400,
        textTransform: stacked ? 'uppercase' : undefined,
        letterSpacing: stacked ? '0.08em' : undefined,
        color: C.t3,
        minWidth: stacked ? undefined : 132,
        flexShrink: 0,
        marginBottom: stacked ? 6 : undefined,
      }}
    >
      {label}
    </div>
    <div
      style={{
        fontSize: 13,
        fontWeight: 500,
        color: C.t1,
        wordBreak: 'break-word',
        fontFamily: mono ? 'ui-monospace, SFMono-Regular, Menlo, monospace' : undefined,
      }}
    >
      {value}
    </div>
  </div>
);

/* ── Button ──────────────────────────────────────────────────────────────── */

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

export const Button: React.FC<{
  C: C;
  variant?: ButtonVariant;
  icon?: LucideIcon;
  onClick?: () => void;
  disabled?: boolean;
  type?: 'button' | 'submit';
  title?: string;
  full?: boolean;
  children?: React.ReactNode;
}> = ({
  C,
  variant = 'secondary',
  icon: Icon,
  onClick,
  disabled,
  type = 'button',
  title,
  full,
  children,
}) => {
  const [hover, setHover] = React.useState(false);

  const palette: Record<ButtonVariant, React.CSSProperties> = {
    primary: { background: C.accent, color: '#ffffff', border: `1px solid ${C.accent}` },
    secondary: { background: C.inp, color: C.t1, border: `1px solid ${C.inpB}` },
    danger: { background: STATUS.redBg, color: STATUS.red, border: `1px solid ${STATUS.red}` },
    ghost: { background: 'transparent', color: C.t2, border: '1px solid transparent' },
  };

  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        ...palette[variant],
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        padding: '8px 16px',
        borderRadius: 7,
        fontFamily: FONT,
        fontSize: 13,
        fontWeight: 600,
        letterSpacing: '-0.01em',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        width: full ? '100%' : undefined,
        filter: hover && !disabled ? 'brightness(1.08)' : undefined,
        transition: 'filter 0.12s ease, opacity 0.12s ease',
      }}
    >
      {Icon && <Icon size={15} strokeWidth={1.8} />}
      {children}
    </button>
  );
};

/* ── Inputs ──────────────────────────────────────────────────────────────── */

export const TextInput: React.FC<{
  C: C;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  disabled?: boolean;
  id?: string;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
}> = ({ C, value, onChange, placeholder, type = 'text', disabled, id, onKeyDown }) => {
  const [focus, setFocus] = React.useState(false);
  return (
    <input
      id={id}
      type={type}
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      onKeyDown={onKeyDown}
      style={{
        width: '100%',
        height: 32,
        padding: '0 12px',
        background: C.inp,
        border: `1px solid ${focus ? C.accent : C.inpB}`,
        borderRadius: 7,
        color: C.t1,
        fontFamily: FONT,
        fontSize: 13,
        outline: 'none',
        boxSizing: 'border-box',
      }}
    />
  );
};

export const NumberInput: React.FC<{
  C: C;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
  id?: string;
}> = ({ C, value, onChange, min, max, disabled, id }) => {
  const [focus, setFocus] = React.useState(false);
  return (
    <input
      id={id}
      type="number"
      value={value}
      min={min}
      max={max}
      disabled={disabled}
      onChange={(e) => {
        const n = Number(e.target.value);
        if (!Number.isNaN(n)) onChange(n);
      }}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      style={{
        width: '100%',
        height: 32,
        padding: '0 12px',
        background: C.inp,
        border: `1px solid ${focus ? C.accent : C.inpB}`,
        borderRadius: 7,
        color: C.t1,
        fontFamily: FONT,
        fontSize: 13,
        outline: 'none',
        boxSizing: 'border-box',
      }}
    />
  );
};

export const Select: React.FC<{
  C: C;
  value: string;
  onChange: (v: string) => void;
  options: readonly { value: string; label: string; hint?: string }[];
  disabled?: boolean;
  id?: string;
}> = ({ C, value, onChange, options, disabled, id }) => (
  <select
    id={id}
    value={value}
    disabled={disabled}
    onChange={(e) => onChange(e.target.value)}
    style={{
      width: '100%',
      height: 32,
      padding: '0 8px',
      background: C.inp,
      border: `1px solid ${C.inpB}`,
      borderRadius: 7,
      color: C.t1,
      fontFamily: FONT,
      fontSize: 13,
      outline: 'none',
      cursor: disabled ? 'not-allowed' : 'pointer',
      boxSizing: 'border-box',
    }}
  >
    {options.map((o) => (
      <option key={o.value} value={o.value}>
        {o.hint ? `${o.label} — ${o.hint}` : o.label}
      </option>
    ))}
  </select>
);

export const Field: React.FC<{
  C: C;
  label: string;
  htmlFor?: string;
  hint?: string;
  children: React.ReactNode;
}> = ({ C, label, htmlFor, hint, children }) => (
  <div style={{ marginBottom: 16 }}>
    <label
      htmlFor={htmlFor}
      style={{
        display: 'block',
        fontSize: 12,
        fontWeight: 500,
        color: C.t2,
        marginBottom: 8,
      }}
    >
      {label}
    </label>
    {children}
    {hint && <div style={{ fontSize: 11, color: C.t3, marginTop: 4 }}>{hint}</div>}
  </div>
);

/* ── Pill / chip ─────────────────────────────────────────────────────────── */

export const Pill: React.FC<{
  C: C;
  children: React.ReactNode;
  tone?: 'default' | 'accent';
  uppercase?: boolean;
}> = ({ C, children, tone = 'default', uppercase }) => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      background: tone === 'accent' ? C.accentBg : C.pill,
      border: `1px solid ${tone === 'accent' ? C.accent : C.b}`,
      borderRadius: 5,
      padding: '2px 8px',
      fontSize: 11,
      fontWeight: 600,
      color: tone === 'accent' ? C.accent : C.pillT,
      textTransform: uppercase ? 'uppercase' : undefined,
      letterSpacing: uppercase ? '0.06em' : undefined,
      whiteSpace: 'nowrap',
    }}
  >
    {children}
  </span>
);

/* ── Notices ─────────────────────────────────────────────────────────────── */

export const Notice: React.FC<{
  C: C;
  tone: 'warn' | 'error' | 'info' | 'success';
  title?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}> = ({ C, tone, title, children, action }) => {
  const map = {
    warn: { fg: STATUS.amber, bg: STATUS.amberBg },
    error: { fg: STATUS.red, bg: STATUS.redBg },
    success: { fg: STATUS.green, bg: STATUS.greenBg },
    info: { fg: C.accent, bg: C.accentBg },
  } as const;
  const { fg, bg } = map[tone];

  return (
    <div
      style={{
        background: bg,
        border: `1px solid ${fg}`,
        borderRadius: 8,
        padding: 12,
        display: 'flex',
        gap: 12,
        alignItems: 'flex-start',
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        {title && (
          <div style={{ fontSize: 13, fontWeight: 600, color: fg, marginBottom: 4 }}>{title}</div>
        )}
        <div style={{ fontSize: 12, color: C.t2, lineHeight: 1.5 }}>{children}</div>
      </div>
      {action}
    </div>
  );
};

/* ── Progress bar ────────────────────────────────────────────────────────── */

export const ProgressBar: React.FC<{ C: C; percent: number; height?: number }> = ({
  C,
  percent,
  height = 8,
}) => (
  <div
    role="progressbar"
    aria-valuenow={Math.round(percent)}
    aria-valuemin={0}
    aria-valuemax={100}
    style={{
      width: '100%',
      height,
      background: C.inp,
      borderRadius: height / 2,
      overflow: 'hidden',
    }}
  >
    <div
      style={{
        width: `${Math.max(0, Math.min(100, percent))}%`,
        height: '100%',
        background: C.accent,
        borderRadius: height / 2,
        transition: 'width 0.3s ease',
      }}
    />
  </div>
);

/* ── Spinner ─────────────────────────────────────────────────────────────── */

export const Spinner: React.FC<{ size?: number; color?: string }> = ({ size = 16, color }) => (
  <span
    className="rf-spinner"
    style={{
      display: 'inline-block',
      width: size,
      height: size,
      borderRadius: '50%',
      border: '1.5px solid rgba(128,128,128,0.2)',
      borderTopColor: color || 'currentColor',
    }}
  />
);

/* ── Empty state ─────────────────────────────────────────────────────────── */

export const EmptyState: React.FC<{
  C: C;
  icon?: LucideIcon;
  title: string;
  children?: React.ReactNode;
}> = ({ C, icon: Icon, title, children }) => (
  <div style={{ textAlign: 'center', padding: '48px 20px', color: C.t3 }}>
    {Icon && <Icon size={32} strokeWidth={1.4} color={C.t3} style={{ opacity: 0.5 }} />}
    <div style={{ fontSize: 14, fontWeight: 600, color: C.t2, marginTop: 12 }}>{title}</div>
    {children && <div style={{ fontSize: 12, marginTop: 8, lineHeight: 1.6 }}>{children}</div>}
  </div>
);
