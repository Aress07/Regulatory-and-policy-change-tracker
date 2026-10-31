import { Suspense, lazy } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Loading } from "./components/ui";

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

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/changes", label: "Change timeline" },
  { to: "/trends", label: "Topic trends" },
  { to: "/since", label: "Since I last looked" },
  { to: "/ask", label: "Ask" },
  { to: "/health", label: "Pipeline health" },
];

export default function App() {
  return (
    <>
      <header className="header">
        <div className="header-inner">
          <NavLink to="/" className="brand">
            EU Regulation Change Tracker
          </NavLink>
          <nav className="nav" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}>
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
        {/* Persistent on every page, rendered outside the routed content. */}
        <p className="disclaimer" role="note">
          <strong>Not legal advice.</strong> {DISCLAIMER.replace("Not legal advice. ", "")}
        </p>
      </header>
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
    </>
  );
}
