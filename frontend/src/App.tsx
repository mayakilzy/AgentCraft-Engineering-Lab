import { Route, Routes } from 'react-router-dom';
import { NavBar } from './components/NavBar';
import { Footer } from './components/Footer';
import {
  ExperimentsPage,
  GraphLabPage,
  HistoryPage,
  HomePage,
  ObservabilityLabPage,
} from './pages';
import './i18n';
import './styles/index.css';

/**
 * AppShell: the route table + chrome (nav, footer, skip link). The Router
 * itself is provided by main.tsx (BrowserRouter) or tests (MemoryRouter)
 * so we never nest routers.
 */
export function App() {
  return (
    <div className="flex min-h-full flex-col">
      {/* Skip link for keyboard users (spec §5: keyboard accessible). */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to content
      </a>
      <NavBar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/graph" element={<GraphLabPage />} />
        <Route path="/observability" element={<ObservabilityLabPage />} />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="*" element={<HomePage />} />
      </Routes>
      <Footer />
    </div>
  );
}
