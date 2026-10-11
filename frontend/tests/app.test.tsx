import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
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
  });

  it('renders the five navigation items', () => {
    renderApp('/');
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    const links = within(nav).getAllByRole('link');
    // 5 nav links + skip-link (sr-only) + footer-less. Allow extras.
    const labels = links
      .map((l) => l.textContent?.trim() ?? '')
      .filter(Boolean);
    expect(labels).toEqual(
      expect.arrayContaining([
        'Home',
        'Graph Lab',
        'Observability Lab',
        'Experiments',
        'History',
      ]),
    );
  });

  it('renders the home page hero on the default route', () => {
    renderApp('/');
    expect(
      screen.getByText(/Learn graph intelligence and observability by doing/i),
    ).toBeInTheDocument();
  });

  it('renders the Graph Lab page on /graph', () => {
    renderApp('/graph');
    expect(screen.getByRole('heading', { name: 'Graph Lab' })).toBeInTheDocument();
  });

  it('renders a placeholder note on stub pages', () => {
    renderApp('/observability');
    expect(screen.getByRole('note')).toBeInTheDocument();
  });

  it('switches locale to Arabic and flips document dir to rtl', () => {
    renderApp('/');
    const select = screen.getByTestId('locale-select') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'ar' } });
    expect(document.documentElement.lang).toBe('ar');
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByText('مختبر الرسم')).toBeInTheDocument();
  });

  it('renders the skip link and focuses main on click', () => {
    renderApp('/');
    const skip = screen.getByText('Skip to content');
    expect(skip).toHaveClass('sr-only');
  });
});
