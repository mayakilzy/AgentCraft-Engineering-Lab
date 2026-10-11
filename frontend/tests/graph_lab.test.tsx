/**
 * T07 — Graph Lab page tests.
 *
 * jsdom doesn't run Cytoscape's canvas; we test the controls (layout,
 * kind filter, selection panel, empty state) and verify the page renders
 * without crashing when the API returns elements.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';

// Stub the GraphViewer so we don't initialize real Cytoscape in jsdom.
vi.mock('../src/components/GraphViewer', () => ({
  GraphViewer: (props: { onSelectNode: Function; onSelectEdge: Function }) => {
    return (
      <div data-testid="cytoscape-container">
        <button
          data-testid="select-node-A"
          onClick={() =>
            props.onSelectNode({ id: 'A', label: 'App A', kind: 'app' })
          }
        >
          select A
        </button>
      </div>
    );
  },
}));

// Stub the API client so we don't need a real backend.
vi.mock('../src/api/client', () => ({
  createGuestSession: vi.fn().mockResolvedValue({
    session_id: 'test',
    expires_at: '2099-01-01T00:00:00Z',
    locale: 'en',
  }),
  getGraph: vi.fn().mockResolvedValue({
    dataset_id: 'lab-default',
    session_id: 'test',
    elements: [
      { group: 'nodes', data: { id: 'A', label: 'App A', kind: 'app' } },
      { group: 'nodes', data: { id: 'B', label: 'Tool B', kind: 'tool' } },
      {
        group: 'edges',
        data: { id: 'e1', source: 'A', target: 'B', relation: 'APP_USES_TOOL' },
      },
    ],
    node_count: 2,
    edge_count: 1,
  }),
  getMetrics: vi.fn().mockResolvedValue({
    dataset_id: 'lab-default',
    node_count: 2,
    edge_count: 1,
    is_directed: true,
    is_dag: true,
    weakly_connected_components: 1,
    strongly_connected_components: 2,
    density: 0.5,
    selfloops: [],
  }),
  seedGraph: vi.fn().mockResolvedValue({
    dataset_id: 'lab-default',
    node_count: 2,
    edge_count: 1,
  }),
  shortestPath: vi.fn().mockResolvedValue({
    dataset_id: 'lab-default',
    source: 'A',
    target: 'B',
    path: ['A', 'B'],
    length: 1,
  }),
}));

import { GraphLabPage } from '../src/pages/GraphLabPage';

function renderPage() {
  return render(
    <I18nextProvider i18n={i18n}>
      <GraphLabPage />
    </I18nextProvider>,
  );
}

describe('Graph Lab page', () => {
  beforeEach(() => {
    i18n.changeLanguage('en');
  });

  it('renders heading and dataset controls', async () => {
    renderPage();
    expect(
      screen.getByRole('heading', { name: 'Graph Lab' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Dataset id')).toHaveValue('lab-default');
    expect(screen.getByLabelText('Fixture')).toHaveValue('starter-five-v1');
  });

  it('renders layout buttons and lets the user switch', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Breadthfirst (DAG)')).toBeInTheDocument();
    });
    const gridBtn = screen.getByText('Grid');
    fireEvent.click(gridBtn);
    expect(gridBtn).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders kind filter chips and toggles selection', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('app')).toBeInTheDocument();
    });
    const appChip = screen.getByText('app');
    fireEvent.click(appChip);
    // Active chip has accent background class
    expect(appChip.className).toContain('bg-accent-500');
    // Clear button appears when a filter is active
    expect(screen.getByText('clear')).toBeInTheDocument();
  });

  it('shows the metrics panel after a successful load', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Metrics')).toBeInTheDocument();
    });
    expect(screen.getByText('Nodes')).toBeInTheDocument();
  });

  it('shows the selected node panel when the viewer reports selection', async () => {
    renderPage();
    const trigger = await screen.findByTestId('select-node-A');
    fireEvent.click(trigger);
    expect(screen.getByText('Selected node')).toBeInTheDocument();
    expect(screen.getByText('App A')).toBeInTheDocument();
  });

  it('renders the shortest-path mini-tool', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Shortest path (directed)')).toBeInTheDocument();
    });
    const src = screen.getByLabelText('source node_ref');
    const tgt = screen.getByLabelText('target node_ref');
    fireEvent.change(src, { target: { value: 'A' } });
    fireEvent.change(tgt, { target: { value: 'B' } });
    fireEvent.click(screen.getByText('Find'));
    await waitFor(() => {
      expect(screen.getByText('length: 1')).toBeInTheDocument();
    });
  });
});
