/**
 * Mission II — new pages tests.
 *
 * Mocks the API client so every endpoint rejects (simulating backend
 * down) and verifies each of the 7 new pages still renders and falls
 * back to PREVIEW mode (where applicable).
 *
 * 7 tests total: HomePage, WorkbenchPage, ObservabilityPage, MentorPage,
 * EnvironmentPage, NotesPage, SettingsPage.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';
import { clearCachedSession } from '../src/hooks/useGuestSession';

// Default mock: every API client function rejects with a fake ApiError.
const rejectAll = () =>
  Promise.reject({
    code: 'network_error',
    message: 'backend unavailable',
    request_id: 'test',
  });

vi.mock('../src/api/client', () => ({
  createGuestSession: vi.fn(() => rejectAll()),
  getModules: vi.fn(() => rejectAll()),
  getHealthLive: vi.fn(() => rejectAll()),
  getHealthReady: vi.fn(() => rejectAll()),
  listExperiments: vi.fn(() => rejectAll()),
  getExperiment: vi.fn(() => rejectAll()),
  listRuns: vi.fn(() => rejectAll()),
  createRun: vi.fn(() => rejectAll()),
  resetRun: vi.fn(() => rejectAll()),
  exportRun: vi.fn(() => rejectAll()),
  compareRuns: vi.fn(() => rejectAll()),
  askMentor: vi.fn(() => rejectAll()),
  getGraph: vi.fn(() => rejectAll()),
  getMetrics: vi.fn(() => rejectAll()),
  seedGraph: vi.fn(() => rejectAll()),
  shortestPath: vi.fn(() => rejectAll()),
}));

import { HomePage } from '../src/pages/HomePage';
import { WorkbenchPage } from '../src/pages/WorkbenchPage';
import { ObservabilityPage } from '../src/pages/ObservabilityPage';
import { MentorPage } from '../src/pages/MentorPage';
import { EnvironmentPage } from '../src/pages/EnvironmentPage';
import { NotesPage } from '../src/pages/NotesPage';
import { SettingsPage } from '../src/pages/SettingsPage';

function renderPage(node: React.ReactNode) {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{node}</MemoryRouter>
    </I18nextProvider>,
  );
}

describe('New pages (backend down → preview)', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
    document.documentElement.lang = 'en';
    document.documentElement.dir = 'ltr';
    document.documentElement.classList.remove('dark');
    clearCachedSession();
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.clear();
    }
  });

  it('HomePage renders hero and shows PREVIEW pill', async () => {
    renderPage(<HomePage />);
    expect(
      screen.getByText(/Learn graph intelligence and observability by doing/i),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('preview-pill')).toBeInTheDocument();
    });
  });

  it('WorkbenchPage renders title and shows PREVIEW pill', async () => {
    renderPage(<WorkbenchPage />);
    expect(
      await screen.findByRole('heading', { name: 'Experiment Workbench' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('preview-pill')).toBeInTheDocument();
    });
  });

  it('ObservabilityPage renders title and shows PREVIEW pill', async () => {
    renderPage(<ObservabilityPage />);
    expect(
      screen.getByRole('heading', { name: 'Observability' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('preview-pill')).toBeInTheDocument();
    });
  });

  it('MentorPage renders title and shows PREVIEW pill', async () => {
    renderPage(<MentorPage />);
    expect(
      screen.getByRole('heading', { name: 'AI Mentor' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('preview-pill')).toBeInTheDocument();
    });
  });

  it('EnvironmentPage renders title and shows PREVIEW pill', async () => {
    renderPage(<EnvironmentPage />);
    expect(
      screen.getByRole('heading', { name: 'Lab Environment' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId('preview-pill')).toBeInTheDocument();
    });
  });

  it('NotesPage renders title (always local, no preview pill)', () => {
    renderPage(<NotesPage />);
    expect(
      screen.getByRole('heading', { name: 'Lab Notes' }),
    ).toBeInTheDocument();
    // Notes page is always local — no preview pill is rendered.
    expect(screen.queryByTestId('preview-pill')).not.toBeInTheDocument();
  });

  it('SettingsPage renders title (always local, no preview pill)', () => {
    renderPage(<SettingsPage />);
    expect(
      screen.getByRole('heading', { name: 'Preferences' }),
    ).toBeInTheDocument();
    // Settings page is always local — no preview pill is rendered.
    expect(screen.queryByTestId('preview-pill')).not.toBeInTheDocument();
  });
});
