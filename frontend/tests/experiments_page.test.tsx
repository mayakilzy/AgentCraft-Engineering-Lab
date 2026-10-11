/**
 * G05 — Experiments page frontend tests.
 *
 * Verifies the Experiments page loads, displays the experiment cards
 * (mocked API), and supports the compare workflow.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';
import { ExperimentsPage } from '../src/pages/ExperimentsPage';

// Mock the API client so the page can render without a backend.
vi.mock('../src/api/client', () => ({
  listExperiments: vi.fn().mockResolvedValue({
    count: 1,
    ids: ['graph-first-network'],
  }),
  getExperiment: vi.fn().mockResolvedValue({
    id: 'graph-first-network',
    version: '1.0.0',
    module_id: 'graph',
    level: 'beginner',
    estimated_minutes: 20,
    title: { en: 'Build Your First Graph', ar: 'أنشئ أول شبكة علاقات' },
    description: { en: 'Model five tools as nodes.', ar: 'مثّل خمس أدوات كعقد.' },
    technology: ['NetworkX'],
    prerequisites: [],
    dataset_key: 'starter-five-v1',
    required_services: ['postgres'],
    capabilities: ['graph-visualization'],
    public_demo_enabled: true,
    steps: [
      {
        id: 'seed',
        title: { en: 'Load dataset', ar: 'تحميل البيانات' },
        instruction: { en: 'Load the sample.', ar: 'حمّل العينة.' },
        operation_key: 'seed_graph',
        input_schema_ref: 'seed_graph_v1',
        validator_key: 'seed_five_nodes_v1',
        expected: { node_count: 5 },
      },
    ],
  }),
  createRun: vi.fn().mockResolvedValue({
    run_id: '11111111-1111-1111-1111-111111111111',
    status: 'PASSED',
    trace_id: 'abcdef0123456789abcdef0123456789',
    error_code: null,
    step_verdicts: [
      {
        step_id: 'seed',
        operation_key: 'seed_graph',
        operation_status: 'ok',
        operation_error_code: null,
        validator_key: 'seed_five_nodes_v1',
        validator_passed: true,
        validator_message: 'seed matches expected counts',
        expected: { node_count: 5 },
        actual: { node_count: 5 },
      },
    ],
  }),
  listRuns: vi.fn().mockResolvedValue({ count: 0, runs: [] }),
  exportRun: vi.fn().mockResolvedValue({ format: 'md', report: '# mock' }),
  resetRun: vi.fn().mockResolvedValue({
    run_id: '11111111-1111-1111-1111-111111111111',
    experiment_id: 'graph-first-network',
    dataset_id: 'starter-five-v1',
    deleted_nodes: 5,
    deleted_edges: 4,
    reset_event_id: '22222222-2222-2222-2222-222222222222',
  }),
  compareRuns: vi.fn().mockResolvedValue({
    run_a_id: '11111111-1111-1111-1111-111111111111',
    run_b_id: '33333333-3333-3333-3333-333333333333',
    same_experiment: true,
    same_final_status: true,
    same_step_count: true,
    step_diffs: [
      {
        step_index: 0,
        step_id: 'seed',
        a_passed: true,
        b_passed: true,
        same_verdict: true,
      },
    ],
    note: 'neutral relative comparison',
  }),
}));

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={['/experiments']}>
        <ExperimentsPage />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

describe('ExperimentsPage', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
    document.documentElement.lang = 'en';
    document.documentElement.dir = 'ltr';
  });

  it('renders the page title and description', async () => {
    renderPage();
    expect(
      screen.getByRole('heading', { name: 'Experiments' }),
    ).toBeInTheDocument();
    // Description from i18n.
    expect(
      screen.getByText(/Ten canonical experiments/i),
    ).toBeInTheDocument();
  });

  it('loads the experiment manifest and renders the card', async () => {
    renderPage();
    // Wait for the manifest to load and the card title to appear.
    await waitFor(() => {
      expect(
        screen.getByText('Build Your First Graph'),
      ).toBeInTheDocument();
    });
    // The level badge should be visible.
    expect(screen.getByTestId('level-badge')).toHaveTextContent('Beginner');
  });

  it('switches to Arabic and shows the translated title', async () => {
    i18n.changeLanguage('ar');
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText('أنشئ أول شبكة علاقات'),
      ).toBeInTheDocument();
    });
  });

  it('renders the compare panel', async () => {
    renderPage();
    await waitFor(() => {
      // The compare panel's button has the testid "compare-button".
      expect(screen.getByTestId('compare-button')).toBeInTheDocument();
    });
    // The compare button starts disabled (no runs selected).
    const compareBtn = screen.getByTestId('compare-button') as HTMLButtonElement;
    expect(compareBtn.disabled).toBe(true);
  });

  it('renders the run button on each card', async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByTestId('run-graph-first-network'),
      ).toBeInTheDocument();
    });
  });
});
