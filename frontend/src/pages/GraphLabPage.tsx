/**
 * Graph Lab page — interactive explorer wired in G02/T07.
 *
 * Layouts: grid / circle / concentric / breadthfirst.
 * Kind filter: app / tool / skill (toggle chips; empty = show all).
 * Selection: detail panel for node or edge.
 * Empty state: a clear prompt to seed a dataset.
 * Error state: surface API errors without crashing.
 *
 * Mission II: wrapped in AppShell and restyled with the design-system
 * classes (.card, .segmented, .info-line, .field, .graph-stage, etc.).
 * Cytoscape integration and the kind-filter fix are preserved.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  GraphViewer,
  type LayoutName,
} from '../components/GraphViewer';
import { AppShell } from '../components/AppShell';
import { Card, Status, EmptyState, Callout } from '../components/ui';
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
  { id: 'breadthfirst', label: 'Breadthfirst' },
];

// Mission I, ISSUE-005 fix: kind chips are derived from the loaded
// graph's distinct kinds, not hardcoded. Empty kinds are not shown.
type Kind = string;

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
    <AppShell>
      <section className="page-heading" aria-labelledby="graph-title">
        <div>
          <div className="eyebrow">{t('nav.graphLab')}</div>
          <h1 id="graph-title">{t('graph.title')}</h1>
          <p>{t('graph.topology')}</p>
        </div>
      </section>

      {error && (
        <div
          className="mb-4 rounded-btn border border-danger-100 bg-danger-50 p-3 text-[12px] text-danger-600"
          role="alert"
        >
          {error}
        </div>
      )}

      {/* Dataset controls */}
      <Card className="mb-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-[11px] font-bold uppercase tracking-wide text-ink-500">
            {t('graph.dataset')}
            <input
              type="text"
              value={datasetInput}
              onChange={(e) => setDatasetInput(e.target.value)}
              className="mt-1 min-w-[200px] rounded-btn border border-ink-200 bg-white px-3 py-2 text-[12px]"
              aria-label={t('graph.dataset')}
              data-testid="dataset-input"
            />
          </label>
          <label className="flex flex-col text-[11px] font-bold uppercase tracking-wide text-ink-500">
            Fixture
            <select
              value={fixtureInput}
              onChange={(e) => setFixtureInput(e.target.value)}
              className="mt-1"
              aria-label="Fixture"
            >
              <option value="starter-five-v1">starter-five-v1 (E01)</option>
              <option value="directed-path-v1">directed-path-v1 (E02)</option>
              <option value="mixed-kind-v1">mixed-kind-v1 (E03)</option>
            </select>
          </label>
          <button
            type="button"
            onClick={onSeed}
            disabled={loading}
            className="btn-primary"
            data-testid="seed-button"
          >
            {loading ? t('common.loading') : t('graph.seedGraph')}
          </button>
          <button
            type="button"
            onClick={() => refresh(datasetInput)}
            className="btn-secondary"
          >
            {t('common.refresh')}
          </button>
        </div>
      </Card>

      {/* Layout segmented control + kind filter chips */}
      <Card className="mb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="segmented" role="group" aria-label={t('graph.layout')}>
            <span className="muted px-2 text-[11px] font-bold uppercase tracking-wide">
              {t('graph.layout')}:
            </span>
            {LAYOUTS.map((l) => (
              <button
                key={l.id}
                type="button"
                className={layout === l.id ? 'selected' : ''}
                aria-pressed={layout === l.id}
                onClick={() => setLayout(l.id)}
                data-testid={`layout-${l.id}`}
              >
                {l.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <span className="muted text-[11px] font-bold uppercase tracking-wide">
              {t('graph.kindFilter')}:
            </span>
            {availableKinds.length === 0 ? (
              <span className="muted text-[11px]">
                ({t('common.notChecked')})
              </span>
            ) : (
              availableKinds.map((k) => {
                const active = kindFilter.has(k);
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() => toggleKind(k)}
                    aria-pressed={active}
                    data-testid={`kind-chip-${k}`}
                    className={`rounded-btn border px-2 py-1 text-[11px] font-bold ${
                      active
                        ? 'border-brand-500 bg-brand-500 text-white'
                        : 'border-ink-200 bg-white text-ink-600'
                    }`}
                  >
                    {k}
                  </button>
                );
              })
            )}
            {kindFilter.size > 0 && (
              <button
                type="button"
                className="text-link"
                onClick={() => setKindFilter(new Set())}
                data-testid="kind-clear"
              >
                {t('history.clearSelection')}
              </button>
            )}
          </div>
        </div>
      </Card>

      <div className="workbench" style={{ gridTemplateColumns: 'minmax(0,1fr) 280px' }}>
        {/* Viewer stage */}
        <div>
          {elements.length === 0 ? (
            <EmptyState
              title={t('graph.selectNode')}
              body={t('graph.staticIllustrationNote')}
            />
          ) : (
            <div className="graph-stage" data-testid="graph-stage">
              <GraphViewer
                elements={elements}
                layout={layout}
                kindFilter={kindFilter as Set<string>}
                onSelectNode={setSelectedNode}
                onSelectEdge={setSelectedEdge}
              />
            </div>
          )}
        </div>

        {/* Side panel: metrics + selection + shortest path */}
        <aside className="flex flex-col gap-3">
          {metrics && (
            <Card>
              <h2 className="mb-2 text-[14px] font-bold text-ink-900">
                {t('graph.metrics')}
              </h2>
              <div className="info-line">
                <span>{t('graph.nodeCount')}</span>
                <b>{metrics.node_count}</b>
              </div>
              <div className="info-line">
                <span>{t('graph.edgeCount')}</span>
                <b>{metrics.edge_count}</b>
              </div>
              <div className="info-line">
                <span>{t('graph.directed')}</span>
                <b>{metrics.is_directed ? 'yes' : 'no'}</b>
              </div>
              <div className="info-line">
                <span>{t('graph.isDag')}</span>
                <b>{metrics.is_dag ? 'yes' : 'no'}</b>
              </div>
              <div className="info-line">
                <span>{t('graph.weaklyConnected')}</span>
                <b>{metrics.weakly_connected_components}</b>
              </div>
              <div className="info-line">
                <span>{t('graph.density')}</span>
                <b>{metrics.density.toFixed(3)}</b>
              </div>
            </Card>
          )}

          {selectedNode && (
            <Card>
              <h2 className="mb-2 text-[14px] font-bold text-ink-900">
                {t('graph.nodeInspector')}
              </h2>
              <div className="info-line">
                <span>id</span>
                <code className="text-[11px]">{selectedNode.id}</code>
              </div>
              <div className="info-line">
                <span>label</span>
                <b>{selectedNode.label}</b>
              </div>
              <div className="info-line">
                <span>kind</span>
                <Status tone="blue">{selectedNode.kind}</Status>
              </div>
            </Card>
          )}

          {selectedEdge && (
            <Card>
              <h2 className="mb-2 text-[14px] font-bold text-ink-900">
                Selected edge
              </h2>
              <div className="info-line">
                <span>source</span>
                <code className="text-[11px]">{selectedEdge.source}</code>
              </div>
              <div className="info-line">
                <span>target</span>
                <code className="text-[11px]">{selectedEdge.target}</code>
              </div>
              <div className="info-line">
                <span>relation</span>
                <b>{selectedEdge.relation}</b>
              </div>
              <Callout>
                Arrow direction: {selectedEdge.source} → {selectedEdge.target}.
              </Callout>
            </Card>
          )}

          {/* Shortest path mini-tool */}
          <Card>
            <h2 className="mb-2 text-[14px] font-bold text-ink-900">
              {t('graph.shortestPath')}
            </h2>
            <div className="flex flex-col gap-2">
              <input
                type="text"
                placeholder={t('graph.sourceLabel')}
                value={pathInput.source}
                onChange={(e) =>
                  setPathInput((p) => ({ ...p, source: e.target.value }))
                }
                className="rounded-btn border border-ink-200 bg-white px-3 py-2 text-[12px]"
                aria-label={t('graph.sourceLabel')}
                data-testid="path-source"
              />
              <input
                type="text"
                placeholder={t('graph.targetLabel')}
                value={pathInput.target}
                onChange={(e) =>
                  setPathInput((p) => ({ ...p, target: e.target.value }))
                }
                className="rounded-btn border border-ink-200 bg-white px-3 py-2 text-[12px]"
                aria-label={t('graph.targetLabel')}
                data-testid="path-target"
              />
              <button
                type="button"
                onClick={onShortestPath}
                className="btn-primary"
                data-testid="path-compute"
              >
                {t('graph.computePath')}
              </button>
            </div>
            {path && (
              <div
                className="mt-3 rounded-btn bg-surface-subtle p-3 text-[11px]"
                data-testid="path-result"
              >
                {path.path ? (
                  <>
                    <div className="font-mono break-all text-[11px] text-ink-700">
                      {path.path.join(' → ')}
                    </div>
                    <div className="muted mt-1">
                      {t('graph.pathLength')}: {path.length}
                    </div>
                  </>
                ) : (
                  <div className="muted">{t('graph.noPath')}</div>
                )}
              </div>
            )}
          </Card>
        </aside>
      </div>
    </AppShell>
  );
}

function toMessage(e: unknown): string {
  const err = e as ApiError;
  if (err && typeof err === 'object' && 'message' in err) {
    return `${err.message} (${err.code})`;
  }
  return String(e);
}
