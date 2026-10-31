import { Fragment, Suspense, lazy } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Icon, Loading, Stars, ThemeToggle, type IconName } from "./components/ui";

// Pages load on demand, so the charting library is only downloaded where charts are shown.
const AskPage = lazy(() => import("./pages/AskPage"));
const ChangeDetailPage = lazy(() => import("./pages/ChangeDetailPage"));
const HealthPage = lazy(() => import("./pages/HealthPage"));
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const SincePage = lazy(() => import("./pages/SincePage"));
const TimelinePage = lazy(() => import("./pages/TimelinePage"));
const TrendsPage = lazy(() => import("./pages/TrendsPage"));

export const DISCLAIMER =
  "Not legal advice. Summaries, tags and answers are AI-generated and can be wrong. Always check the official text on EUR-Lex.";

type NavItem = { to: string; label: string; icon: IconName; end?: boolean };

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Monitor",
    items: [
      { to: "/", label: "Overview", icon: "overview", end: true },
      { to: "/changes", label: "Change timeline", icon: "timeline" },
      { to: "/since", label: "Since I last looked", icon: "since" },
    ],
  },
  {
    group: "Analyse",
    items: [
      { to: "/trends", label: "Topic trends", icon: "trends" },
      { to: "/ask", label: "Ask the law", icon: "ask" },
    ],
  },
  {
    group: "System",
    items: [{ to: "/health", label: "Pipeline health", icon: "health" }],
  },
];

export default function App() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand" aria-label="EU Regulation Change Tracker, home">
          <Stars className="brand-mark" />
          <span className="brand-text">
            <strong>EU Reg Tracker</strong>
            <span>Digital regulation changes</span>
          </span>
        </NavLink>
        <nav className="nav" aria-label="Main">
          {NAV.map((g) => (
            <Fragment key={g.group}>
              <div className="nav-group">{g.group}</div>
              {g.items.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} title={n.label}>
                  <Icon name={n.icon} />
                  <span className="nav-label">{n.label}</span>
                </NavLink>
              ))}
            </Fragment>
          ))}
        </nav>
        <div className="sidebar-foot">
          <ThemeToggle />
          <p className="sidebar-note">Source: EUR-Lex consolidated texts via the Publications Office Cellar.</p>
        </div>
      </aside>
      <div className="content">
        {/* Persistent on every page, rendered outside the routed content. */}
        <p className="disclaimer" role="note">
          <Icon name="warning" size={15} />
          <span>
            <strong>Not legal advice.</strong> {DISCLAIMER.replace("Not legal advice. ", "")}
          </span>
        </p>
        <main>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/changes" element={<TimelinePage />} />
              <Route path="/changes/:changeId" element={<ChangeDetailPage />} />
              <Route path="/trends" element={<TrendsPage />} />
              <Route path="/since" element={<SincePage />} />
              <Route path="/ask" element={<AskPage />} />
              <Route path="/health" element={<HealthPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}
