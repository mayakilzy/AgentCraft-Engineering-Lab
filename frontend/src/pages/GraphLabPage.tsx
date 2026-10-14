/**
 * Graph Lab page — interactive explorer wired in G02/T07.
 *
 * Layouts: grid / circle / concentric / breadthfirst.
 * Kind filter: app / tool / skill (toggle chips; empty = show all).
 * Selection: detail panel for node or edge.
 * Empty state: a clear prompt to seed a dataset.
 * Error state: surface API errors without crashing.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  GraphViewer,
  type LayoutName,
} from '../components/GraphViewer';
import {
  ApiError,
  type CytoscapeElement,
  type MetricsResponse,
  createGuestSession,
  getGraph,
  getMetrics,
  seedGraph,
  shortestPath,
  type ShortestPathResponse,
} from '../api/client';

const DEFAULT_DATASET = 'lab-default';
const DEFAULT_FIXTURE = 'starter-five-v1';

const LAYOUTS: { id: LayoutName; label: string }[] = [
  { id: 'grid', label: 'Grid' },
  { id: 'circle', label: 'Circle' },
  { id: 'concentric', label: 'Concentric' },
  { id: 'breadthfirst', label: 'Breadthfirst (DAG)' },
];

// Mission I, ISSUE-005 fix: kind chips are derived from the loaded
// graph's distinct kinds, not hardcoded. Empty kinds are not shown.
type Kind = string;  // accept any kind the backend sends

interface NodeDetail {
  id: string;
  label: string;
  kind: string;
}
interface EdgeDetail {
  id: string;
  source: string;
  target: string;
  relation: string;
}

export function GraphLabPage() {
  const { t } = useTranslation();
  const [elements, setElements] = useState<CytoscapeElement[]>([]);
  const [layout, setLayout] = useState<LayoutName>('breadthfirst');
  const [kindFilter, setKindFilter] = useState<Set<Kind>>(new Set());
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<EdgeDetail | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [path, setPath] = useState<ShortestPathResponse | null>(null);
  const [pathInput, setPathInput] = useState({ source: '', target: '' });
  const [datasetInput, setDatasetInput] = useState(DEFAULT_DATASET);
  const [fixtureInput, setFixtureInput] = useState(DEFAULT_FIXTURE);

  // Bootstrap a guest session on first load.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        await createGuestSession('en');
        await refresh(datasetInput);
      } catch (e) {
        if (!cancelled) {
          setError(toMessage(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function refresh(datasetId: string) {
    try {
      const g = await getGraph(datasetId);
      setElements(g.elements);
      setMetrics(await getMetrics(datasetId));
      setError(null);
    } catch (e) {
      setError(toMessage(e));
      setElements([]);
      setMetrics(null);
    }
  }

  function onSeed() {
    setLoading(true);
    (async () => {
      try {
        await seedGraph(datasetInput, fixtureInput);
        await refresh(datasetInput);
      } catch (e) {
        setError(toMessage(e));
      } finally {
        setLoading(false);
      }
    })();
  }

  function onShortestPath() {
    if (!pathInput.source || !pathInput.target) return;
    shortestPath(datasetInput, pathInput.source, pathInput.target)
      .then((r) => setPath(r))
      .catch((e) => {
        setError(toMessage(e));
        setPath(null);
      });
  }

  function toggleKind(k: Kind) {
    setKindFilter((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  }

  // Mission I, ISSUE-005 fix: derive kind chips from loaded elements.
  const availableKinds: string[] = (() => {
    const kinds = new Set<string>();
    for (const el of elements) {
      if (el.group === 'nodes') {
        const kind = (el.data as { kind?: string }).kind;
        if (kind) kinds.add(kind);
      }
    }
    return Array.from(kinds).sort();
  })();

  return (
    <main id="main-content" className="mx-auto max-w-6xl px-4 py-6" tabIndex={-1}>
      <h1 className="text-2xl font-semibold text-ink-900">{t('nav.graphLab')}</h1>

      {error && (
        <div
          className="mt-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
          role="alert"
        >
          {error}
        </div>
      )}

      {/* Dataset controls */}
      <section className="mt-4 rounded border border-ink-100 bg-white p-3 text-sm">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs text-ink-900/70">
            Dataset id
            <input
              type="text"
              value={datasetInput}
              onChange={(e) => setDatasetInput(e.target.value)}
              className="mt-1 rounded border border-ink-100 px-2 py-1 text-sm"
              aria-label="Dataset id"
            />
          </label>
          <label className="flex flex-col text-xs text-ink-900/70">
            Fixture
            <select
              value={fixtureInput}
              onChange={(e) => setFixtureInput(e.target.value)}
              className="mt-1 rounded border border-ink-100 px-2 py-1 text-sm"
              aria-label="Fixture"
            >
              <option value="starter-five-v1">starter-five-v1 (E01)</option>
              <option value="directed-path-v1">directed-path-v1 (E02)</option>
              <option value="mixed-kind-v1">mixed-kind-v1 (E03)</option>
            </select>
          </label>
          <button
            onClick={onSeed}
            disabled={loading}
            className="rounded bg-accent-500 px-3 py-1.5 text-sm text-white hover:bg-accent-600 disabled:opacity-50"
          >
            {loading ? t('common.loading') : 'Load'}
          </button>
          <button
            onClick={() => refresh(datasetInput)}
            className="rounded border border-ink-100 bg-white px-3 py-1.5 text-sm text-ink-900 hover:bg-ink-100"
          >
            Refresh
          </button>
        </div>
      </section>

      {/* Layout + kind filter */}
      <section className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-1">
          <span className="text-ink-900/70">Layout:</span>
          {LAYOUTS.map((l) => (
            <button
              key={l.id}
              onClick={() => setLayout(l.id)}
              className={`rounded px-2 py-1 ${
                layout === l.id
                  ? 'bg-accent-500 text-white'
                  : 'border border-ink-100 bg-white text-ink-900 hover:bg-ink-100'
              }`}
              aria-pressed={layout === l.id}
            >
              {l.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-ink-900/70">Filter by kind:</span>
          {availableKinds.length === 0 ? (
            <span className="text-ink-900/40 text-xs">(no nodes loaded)</span>
          ) : (
            availableKinds.map((k) => {
              const active = kindFilter.has(k);
              // Empty filter means "show all"; clicking a kind toggles to "only".
              return (
                <label
                  key={k}
                  className={`flex items-center gap-1 rounded px-2 py-1 ${
                    active
                      ? 'bg-accent-500 text-white'
                      : 'border border-ink-100 bg-white text-ink-900'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={() => toggleKind(k)}
                    className="sr-only"
                  />
                  {k}
                </label>
              );
            })
          )}
          {kindFilter.size > 0 && (
            <button
              className="text-ink-900/60 underline"
              onClick={() => setKindFilter(new Set())}
            >
              clear
            </button>
          )}
        </div>
      </section>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[1fr_18rem]">
        {/* Viewer */}
        <div>
          {elements.length === 0 ? (
            <div
              className="flex h-96 items-center justify-center rounded border border-dashed border-ink-100 bg-ink-50 text-sm text-ink-900/60"
              role="status"
            >
              Empty dataset — pick a fixture and click Load.
            </div>
          ) : (
            <GraphViewer
              elements={elements}
              layout={layout}
              kindFilter={kindFilter as Set<string>}
              onSelectNode={setSelectedNode}
              onSelectEdge={setSelectedEdge}
            />
          )}
        </div>

        {/* Side panel: metrics + selection + shortest path */}
        <aside className="flex flex-col gap-3">
          {metrics && (
            <div className="rounded border border-ink-100 bg-white p-3 text-xs">
              <h2 className="mb-2 text-sm font-semibold text-ink-900">
                Metrics
              </h2>
              <dl className="grid grid-cols-2 gap-1">
                <dt className="text-ink-900/60">Nodes</dt>
                <dd className="text-right">{metrics.node_count}</dd>
                <dt className="text-ink-900/60">Edges</dt>
                <dd className="text-right">{metrics.edge_count}</dd>
                <dt className="text-ink-900/60">Directed</dt>
                <dd className="text-right">{metrics.is_directed ? 'yes' : 'no'}</dd>
                <dt className="text-ink-900/60">DAG</dt>
                <dd className="text-right">{metrics.is_dag ? 'yes' : 'no'}</dd>
                <dt className="text-ink-900/60">WCC</dt>
                <dd className="text-right">{metrics.weakly_connected_components}</dd>
                <dt className="text-ink-900/60">Density</dt>
                <dd className="text-right">{metrics.density.toFixed(3)}</dd>
              </dl>
            </div>
          )}

          {selectedNode && (
            <div className="rounded border border-accent-500 bg-white p-3 text-xs">
              <h2 className="mb-2 text-sm font-semibold text-ink-900">
                Selected node
              </h2>
              <dl className="grid grid-cols-2 gap-1">
                <dt className="text-ink-900/60">id</dt>
                <dd className="text-right font-mono">{selectedNode.id}</dd>
                <dt className="text-ink-900/60">label</dt>
                <dd className="text-right">{selectedNode.label}</dd>
                <dt className="text-ink-900/60">kind</dt>
                <dd className="text-right">{selectedNode.kind}</dd>
              </dl>
            </div>
          )}

          {selectedEdge && (
            <div className="rounded border border-accent-500 bg-white p-3 text-xs">
              <h2 className="mb-2 text-sm font-semibold text-ink-900">
                Selected edge
              </h2>
              <dl className="grid grid-cols-2 gap-1">
                <dt className="text-ink-900/60">source</dt>
                <dd className="text-right font-mono">{selectedEdge.source}</dd>
                <dt className="text-ink-900/60">target</dt>
                <dd className="text-right font-mono">{selectedEdge.target}</dd>
                <dt className="text-ink-900/60">relation</dt>
                <dd className="text-right">{selectedEdge.relation}</dd>
              </dl>
              <p className="mt-2 text-[10px] text-ink-900/60">
                Arrow direction: {selectedEdge.source} → {selectedEdge.target}.
              </p>
            </div>
          )}

          {/* Shortest path mini-tool (E02 preview; validator gates in G05) */}
          <div className="rounded border border-ink-100 bg-white p-3 text-xs">
            <h2 className="mb-2 text-sm font-semibold text-ink-900">
              Shortest path (directed)
            </h2>
            <div className="flex flex-col gap-2">
              <input
                type="text"
                placeholder="source node_ref"
                value={pathInput.source}
                onChange={(e) =>
                  setPathInput((p) => ({ ...p, source: e.target.value }))
                }
                className="rounded border border-ink-100 px-2 py-1 text-xs"
                aria-label="source node_ref"
              />
              <input
                type="text"
                placeholder="target node_ref"
                value={pathInput.target}
                onChange={(e) =>
                  setPathInput((p) => ({ ...p, target: e.target.value }))
                }
                className="rounded border border-ink-100 px-2 py-1 text-xs"
                aria-label="target node_ref"
              />
              <button
                onClick={onShortestPath}
                className="rounded bg-accent-500 px-2 py-1 text-xs text-white hover:bg-accent-600"
              >
                Find
              </button>
            </div>
            {path && (
              <div className="mt-2 rounded bg-ink-50 p-2 text-[11px]">
                {path.path ? (
                  <>
                    <div className="font-mono break-all">{path.path.join(' → ')}</div>
                    <div className="mt-1 text-ink-900/60">
                      length: {path.length}
                    </div>
                  </>
                ) : (
                  <div className="text-ink-900/60">No directed path.</div>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}

function toMessage(e: unknown): string {
  const err = e as ApiError;
  if (err && typeof err === 'object' && 'message' in err) {
    return `${err.message} (${err.code})`;
  }
  return String(e);
}
