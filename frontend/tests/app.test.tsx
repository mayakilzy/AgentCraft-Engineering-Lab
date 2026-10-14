import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';
import { App } from '../src/App';

function renderApp(initialPath = '/') {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe('App shell', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
    document.documentElement.lang = 'en';
    document.documentElement.dir = 'ltr';
    document.documentElement.classList.remove('dark');
  });

  it('renders the main navigation with all 10 items', () => {
    renderApp('/');
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(nav).toBeInTheDocument();
    const links = within(nav).getAllByRole('link');
    const labels = links
      .map((l) => l.textContent?.trim() ?? '')
      .filter(Boolean);
    // All 10 page nav labels are present.
    expect(labels).toEqual(
      expect.arrayContaining([
        'Home',
        'Experiments',
        'Experiment Workbench',
        'Graph Explorer',
        'Observability',
        'AI Mentor',
        'Results & Timeline',
        'Lab Environment',
        'Notes',
        'Settings',
      ]),
    );
  });

  it('renders the home page hero on the default route', async () => {
    renderApp('/');
    expect(
      screen.getByText(/Learn graph intelligence and observability by doing/i),
    ).toBeInTheDocument();
  });

  it('renders the Graph Explorer page on /graph', async () => {
    renderApp('/graph');
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Graph Explorer' }),
      ).toBeInTheDocument();
    });
  });

  it('renders the Observability page on /observability', async () => {
    renderApp('/observability');
    // Observability page renders its own heading (not a placeholder note).
    expect(
      screen.getByRole('heading', { name: 'Observability' }),
    ).toBeInTheDocument();
  });

  it('switches locale via the toggle-language button and flips dir to rtl', () => {
    renderApp('/');
    const toggle = screen.getByRole('button', { name: 'Toggle language' });
    fireEvent.click(toggle);
    expect(document.documentElement.lang).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
    // Sidebar brand renders the Arabic app title.
    expect(screen.getByText('مختبر AgentCraft للهندسة')).toBeInTheDocument();
  });

  it('renders the skip link visible-only on focus', () => {
    renderApp('/');
    const skip = screen.getByText('Skip to content');
    expect(skip).toHaveClass('sr-only');
  });
});
