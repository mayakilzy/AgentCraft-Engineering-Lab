import { Route, Routes } from 'react-router-dom';
import {
  EnvironmentPage,
  ExperimentsPage,
  GraphLabPage,
  HistoryPage,
  HomePage,
  MentorPage,
  NotesPage,
  ObservabilityPage,
  SettingsPage,
  WorkbenchPage,
} from './pages';
import './i18n';
import './styles/index.css';

/**
 * App — 10-route table. Each page wraps itself in <AppShell>, so the App
 * component is just the route table (no NavBar/Footer at this level).
 * The Router itself is provided by main.tsx (BrowserRouter) or tests
 * (MemoryRouter) so we never nest routers.
 */
export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/experiments" element={<ExperimentsPage />} />
      <Route path="/workbench" element={<WorkbenchPage />} />
      <Route path="/graph" element={<GraphLabPage />} />
      <Route path="/observability" element={<ObservabilityPage />} />
      <Route path="/mentor" element={<MentorPage />} />
      <Route path="/history" element={<HistoryPage />} />
      <Route path="/environment" element={<EnvironmentPage />} />
      <Route path="/notes" element={<NotesPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<HomePage />} />
    </Routes>
  );
}
