/**
 * UI primitives — shared building blocks used across all pages.
 *
 * These wrap the design-system CSS classes defined in styles/index.css
 * (.status, .card, .stat-* etc.) and add a few small helpers
 * (verdictTone, formatDuration, formatClock) so the pages don't
 * repeat themselves.
 */
import type { CSSProperties, ReactNode } from 'react';

export type StatusTone =
  | 'green'
  | 'amber'
  | 'blue'
  | 'gray'
  | 'red'
  | 'purple';

interface StatusProps {
  tone: StatusTone;
  children: ReactNode;
  className?: string;
  'data-testid'?: string;
}

/**
 * Status pill — maps to .status + .status-{tone} from the design system.
 * Accepts data-testid via rest props so tests can target a specific verdict.
 */
export function Status({
  tone,
  children,
  className,
  ...rest
}: StatusProps) {
  return (
    <span
      className={`status status-${tone}${className ? ` ${className}` : ''}`}
      {...rest}
    >
      {children}
    </span>
  );
}

interface CardProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  'data-testid'?: string;
}

/**
 * Card — surfaces the .card / .card-hover design-system classes.
 */
export function Card({ children, className, style, ...rest }: CardProps) {
  return (
    <div
      className={`card${className ? ` ${className}` : ''}`}
      style={style}
      {...rest}
    >
      {children}
    </div>
  );
}

interface StatCardProps {
  icon: ReactNode;
  iconTone?: 'brand' | 'green' | 'purple';
  label: string;
  value: ReactNode;
  hint?: string;
  'data-testid'?: string;
}

/**
 * StatCard — one tile in the standard 4-tile stats grid.
 * Uses .stat-icon (with optional .green/.purple modifier) for the badge.
 */
export function StatCard({
  icon,
  iconTone = 'brand',
  label,
  value,
  hint,
  ...rest
}: StatCardProps) {
  const iconCls = `stat-icon${iconTone !== 'brand' ? ` ${iconTone}` : ''}`;
  return (
    <Card className="!p-4" {...rest}>
      <div className="flex items-start gap-3">
        <span className={iconCls} aria-hidden>
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
            {label}
          </div>
          <div className="mt-1 text-[22px] font-extrabold leading-none text-ink-900">
            {value}
          </div>
          {hint && (
            <div className="mt-1.5 text-[11px] text-ink-400">{hint}</div>
          )}
        </div>
      </div>
    </Card>
  );
}

interface CalloutProps {
  title?: string;
  children: ReactNode;
  'data-testid'?: string;
}

/**
 * Callout — informational banner with brand tint.
 */
export function Callout({ title, children, ...rest }: CalloutProps) {
  return (
    <div className="callout" {...rest}>
      {title && (
        <div className="mb-1 text-[12px] font-extrabold text-brand-700">
          {title}
        </div>
      )}
      {typeof children === 'string' ? <p>{children}</p> : children}
    </div>
  );
}

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  body?: string;
  children?: ReactNode;
  'data-testid'?: string;
}

/**
 * EmptyState — placeholder used when a list is empty or backend is down.
 */
export function EmptyState({
  icon,
  title,
  body,
  children,
  ...rest
}: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-card border border-dashed border-ink-200 bg-surface-subtle p-8 text-center"
      {...rest}
    >
      {icon && (
        <div className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-brand-50 text-brand-600">
          {icon}
        </div>
      )}
      <div className="text-[14px] font-bold text-ink-700">{title}</div>
      {body && <p className="mt-1 max-w-sm text-[12px] text-ink-400">{body}</p>}
      {children}
    </div>
  );
}

/**
 * verdictTone — map a run/step verdict string to a Status tone.
 *
 * Accepts either uppercase contract values (PASSED/FAILED/BLOCKED/…)
 * or the diagnosis_state enum (confirmed/likely/insufficient_evidence).
 */
export function verdictTone(verdict: string): StatusTone {
  const v = verdict.toLowerCase();
  if (v === 'passed' || v === 'confirmed' || v === 'ok') return 'green';
  if (v === 'failed' || v === 'error') return 'red';
  if (v === 'blocked') return 'amber';
  if (v === 'running' || v === 'created') return 'blue';
  if (v === 'likely') return 'amber';
  if (v === 'insufficient_evidence') return 'gray';
  if (v === 'degraded') return 'amber';
  if (v === 'ready' || v === 'live') return 'green';
  if (v === 'not_ready' || v === 'notready') return 'red';
  return 'gray';
}

/**
 * formatDuration — render a millisecond duration as a short human string.
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)} s`;
  const min = sec / 60;
  if (min < 60) return `${min.toFixed(1)} min`;
  const hr = min / 60;
  return `${hr.toFixed(1)} h`;
}

/**
 * formatClock — render an ISO timestamp as a locale-aware clock string.
 */
export function formatClock(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleTimeString();
  } catch {
    return '—';
  }
}
