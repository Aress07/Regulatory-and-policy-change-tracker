import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Change, Freshness, Impact } from "../types";

/* ---------- Icons (inline SVG, 24px grid, stroke-based) ---------- */

const ICON_PATHS = {
  overview: "M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z",
  timeline: "M12 8v4l3 2M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0",
  since: "M6 2h12M6 22h12M7 2v4l5 6-5 6v4M17 2v4l-5 6 5 6v4",
  trends: "M3 3v18h18M7 15l4-4 3 3 6-6",
  ask: "M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-6.4A8 8 0 1 1 21 12zM9.5 9.5a2.5 2.5 0 0 1 4.9.8c0 1.7-2.4 2.2-2.4 3.7M12 17h.01",
  health: "M22 12h-4l-3 9L9 3l-3 9H2",
  external: "M14 3h7v7M10 14 21 3M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5",
  back: "M19 12H5M12 19l-7-7 7-7",
  arrow: "M5 12h14M13 5l7 7-7 7",
  sun: "M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  warning: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  diff: "M12 3v18M5 8h4M7 6v4M15 16h4",
  sparkle: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8z",
  quote: "M4 4h16v12H8l-4 4zM8 9h8M8 12h5",
  filter: "M3 5h18M6 12h12M10 19h4",
  file: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5",
  layers: "M12 3 2 8l10 5 10-5zM2 16l10 5 10-5M2 12l10 5 10-5",
  alert: "M12 8v5M12 16h.01M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18",
  check: "M20 6 9 17l-5-5",
} as const;

export type IconName = keyof typeof ICON_PATHS;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

// Five-pointed star centred on the origin (outer radius 5, inner 2).
const STAR = Array.from({ length: 10 }, (_, i) => {
  const r = i % 2 ? 2 : 5;
  const a = (i * Math.PI) / 5;
  return `${(r * Math.sin(a)).toFixed(2)},${(-r * Math.cos(a)).toFixed(2)}`;
}).join(" ");

/** Twelve stars in a circle, a nod to the EU flag. */
export function Stars({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      {Array.from({ length: 12 }, (_, i) => {
        const a = (i / 12) * 2 * Math.PI;
        const x = 50 + 36 * Math.sin(a);
        const y = 50 - 36 * Math.cos(a);
        return <polygon key={i} points={STAR} fill="currentColor" transform={`translate(${x} ${y})`} />;
      })}
    </svg>
  );
}

/* ---------- Badges ---------- */

export function AiBadge() {
  return (
    <span className="badge ai" title="Written by a language model; may be wrong">
      AI-generated
    </span>
  );
}

export function SyntheticBadge() {
  return (
    <span className="badge synthetic" title="Test fixture, not a real legal change">
      Synthetic test data
    </span>
  );
}

export function ImpactBadge({ impact }: { impact: Impact | null }) {
  if (!impact) return <span className="badge">not rated</span>;
  return <span className={`badge ${impact}`}>{impact} impact</span>;
}

export function ChangeTypeBadge({ type }: { type: string }) {
  return (
    <span className={`badge type type-${type}`}>
      <span className="swatch" />
      {type}
    </span>
  );
}

/* ---------- Layout ---------- */

export function PageHeader({
  eyebrow,
  title,
  lede,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  lede?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {lede && <p className="lede">{lede}</p>}
      </div>
      {actions && <div>{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  icon,
  aside,
  className,
  children,
}: {
  title?: ReactNode;
  icon?: IconName;
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`card${className ? ` ${className}` : ""}`}>
      {(title || aside) && (
        <div className="card-head">
          {title && (
            <h2>
              {icon && <Icon name={icon} size={17} />}
              {title}
            </h2>
          )}
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <p className="skeleton" role="status">
      <span className="spinner" aria-hidden="true" />
      {what}…
    </p>
  );
}

export function ErrorMessage({ error }: { error: Error }) {
  return (
    <div className="banner error" role="alert">
      <Icon name="alert" />
      <span>Could not load data: {error.message}</span>
    </div>
  );
}

export function FreshnessBanner({ freshness }: { freshness: Freshness }) {
  if (!freshness.last_successful_ingest) {
    return (
      <div className="banner warn">
        <Icon name="warning" />
        No successful ingestion recorded yet.
      </div>
    );
  }
  const when = freshness.last_successful_ingest.replace("T", " ").slice(0, 16);
  const days = freshness.days_since_ingest ?? 0;
  if (days > 8) {
    return (
      <div className="banner warn">
        <Icon name="warning" />
        <span>
          Last successful ingest: {when} UTC ({days} days ago). Data may be stale.
        </span>
      </div>
    );
  }
  return (
    <p className="status-line">
      <span className="dot" aria-hidden="true" />
      Data fresh · last successful ingest {when} UTC ({days} days ago)
    </p>
  );
}

/** A change as a compact list row, linking to its detail page. */
export function ChangeListItem({ change: c, showInstrument = true }: { change: Change; showInstrument?: boolean }) {
  return (
    <li>
      <Link to={`/changes/${c.change_id}`} className="change-item">
        <div className="change-title">
          {showInstrument && `${c.instrument} · `}
          {sectionLabel(c.section_key)}
          {c.heading && <span className="muted"> · {c.heading}</span>}
        </div>
        <div className="change-meta">
          <ChangeTypeBadge type={c.change_type} />
          <ImpactBadge impact={c.impact} />
          {c.is_synthetic && <SyntheticBadge />}
          <span>{formatDate(c.to_date)}</span>
        </div>
        <p className="change-summary">{c.summary ?? <span className="muted">No AI summary yet.</span>}</p>
      </Link>
    </li>
  );
}

/* ---------- Inputs ---------- */

/** Multi-select as toggle chips (good for a handful of options). */
export function ChipGroup({
  legend,
  options,
  selected,
  onChange,
}: {
  legend: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const toggle = (value: string) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  return (
    <fieldset>
      <legend>{legend}</legend>
      <div className="chips">
        {options.map((o) => (
          <button
            key={o}
            type="button"
            className="chip"
            aria-pressed={selected.includes(o)}
            onClick={() => toggle(o)}
          >
            {o.replace(/_/g, " ")}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

const THEME_KEY = "regtracker.theme";
type Theme = "light" | "dark";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage unavailable */
  }
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const next: Theme = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={`Switch to ${next} theme`}
      onClick={() => {
        setTheme(next);
        try {
          localStorage.setItem(THEME_KEY, next);
        } catch {
          /* storage unavailable */
        }
      }}
    >
      <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
      <span className="label">{next === "dark" ? "Dark" : "Light"} mode</span>
    </button>
  );
}

/** `art_30b` -> "Article 30b", `annex_II` -> "Annex II", `rct_5` -> "Recital 5". */
export function sectionLabel(key: string): string {
  const m = /^(art|annex|rct)_(.+)$/.exec(key);
  if (!m) return key;
  return `${{ art: "Article", annex: "Annex", rct: "Recital" }[m[1] as "art" | "annex" | "rct"]} ${m[2]}`;
}

export function formatDate(iso: string | null): string {
  return iso ? iso.slice(0, 10) : "–";
}
