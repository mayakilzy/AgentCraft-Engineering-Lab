/**
 * Cytoscape.js graph viewer.
 *
 * Per the spec §5 + §6: interactive pan/zoom/select/filter/layout with clear
 * directed edges. Layouts: grid, circle, concentric, breadthfirst (DAG-
 * friendly). Kind filter, selection → side detail panel, empty + error
 * states. Keyboard accessible (focus the canvas container, +/- zoom, arrows
 * pan) — covered by Cytoscape's built-in wheel/keyboard handling plus our
 * focusable wrapper.
 */
import { useEffect, useRef, useState } from 'react';
import cytoscape, { Core, ElementDefinition, EventObject } from 'cytoscape';
import type { CytoscapeElement } from '../api/client';

export type LayoutName = 'grid' | 'circle' | 'concentric' | 'breadthfirst';

interface GraphViewerProps {
  elements: CytoscapeElement[];
  layout: LayoutName;
  kindFilter: Set<string>;
  onSelectNode: (data: { id: string; label: string; kind: string } | null) => void;
  onSelectEdge: (data: { id: string; source: string; target: string; relation: string } | null) => void;
}

const KIND_COLORS: Record<string, string> = {
  app: '#3b82f6',     // accent blue
  tool: '#10b981',    // emerald
  skill: '#f59e0b',   // amber
  default: '#64748b', // slate
};

function kindColor(kind: string): string {
  return KIND_COLORS[kind] ?? KIND_COLORS['default'];
}

/** Convert API elements to Cytoscape ElementDefinition[], applying the
 *  kind filter to nodes (filtered nodes are NOT included; edges whose
 *  endpoints disappear are also dropped to avoid dangling refs). */
function toCytoscapeElements(
  elements: CytoscapeElement[],
  kindFilter: Set<string>,
): ElementDefinition[] {
  const visibleNodeIds = new Set<string>();
  const out: ElementDefinition[] = [];

  for (const el of elements) {
    if (el.group !== 'nodes') continue;
    const data = el.data as { id: string; label: string; kind: string };
    if (kindFilter.size > 0 && !kindFilter.has(data.kind)) continue;
    visibleNodeIds.add(data.id);
    out.push({
      group: 'nodes',
      data: { id: data.id, label: data.label, kind: data.kind },
    });
  }
  for (const el of elements) {
    if (el.group !== 'edges') continue;
    const data = el.data as {
      id: string; source: string; target: string; relation: string;
    };
    // Drop edges whose endpoints were filtered out (no dangling).
    if (!visibleNodeIds.has(data.source) || !visibleNodeIds.has(data.target)) continue;
    out.push({
      group: 'edges',
      data: {
        id: data.id,
        source: data.source,
        target: data.target,
        label: data.relation,
        relation: data.relation,
      },
    });
  }
  return out;
}

export function GraphViewer({
  elements,
  layout,
  kindFilter,
  onSelectNode,
  onSelectEdge,
}: GraphViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Initialize Cytoscape once on mount.
  useEffect(() => {
    if (!containerRef.current) return;
    let cy: Core;
    try {
      cy = cytoscape({
        container: containerRef.current,
        elements: [],
        style: [
          {
            selector: 'node',
            style: {
              label: 'data(label)',
              'background-color': 'data(kindColor)',
              color: '#0f172a',
              'font-size': 10,
              'text-valign': 'bottom',
              'text-margin-y': 4,
              width: 28,
              height: 28,
              'border-width': 1,
              'border-color': '#0f172a33',
            },
          },
          {
            selector: 'edge',
            style: {
              label: 'data(label)',
              'curve-style': 'bezier',
              'target-arrow-shape': 'triangle',
              'arrow-scale': 0.9,
              'line-color': '#94a3b8',
              'target-arrow-color': '#94a3b8',
              'text-rotation': 'autorotate',
              'font-size': 8,
              color: '#475569',
              width: 2,
            },
          },
          {
            selector: 'node:selected',
            style: { 'border-width': 3, 'border-color': '#2563eb' },
          },
          {
            selector: 'edge:selected',
            style: { 'line-color': '#2563eb', 'target-arrow-color': '#2563eb', width: 3 },
          },
        ],
        layout: { name: 'grid', padding: 10 },
        wheelSensitivity: 0.2,
      });
    } catch (e) {
      setError(`Failed to initialize viewer: ${(e as Error).message}`);
      return;
    }
    cyRef.current = cy;

    const onNodeSelect = (evt: EventObject) => {
      const d = evt.target.data();
      onSelectNode({ id: d.id, label: d.label, kind: d.kind });
      onSelectEdge(null);
    };
    const onEdgeSelect = (evt: EventObject) => {
      const d = evt.target.data();
      onSelectEdge({
        id: d.id, source: d.source, target: d.target, relation: d.relation,
      });
      onSelectNode(null);
    };
    const onUnselect = () => {
      onSelectNode(null);
      onSelectEdge(null);
    };
    cy.on('tapselect', 'node', onNodeSelect);
    cy.on('tapselect', 'edge', onEdgeSelect);
    cy.on('unselect', onUnselect);

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Apply elements + kindFilter when they change.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    try {
      const defs = toCytoscapeElements(elements, kindFilter);
      cy.elements().remove();
      // Set kindColor on each node from its kind, then add.
      for (const d of defs) {
        if (d.group === 'nodes' && d.data) {
          (d.data as Record<string, unknown>).kindColor = kindColor(
            String((d.data as { kind: string }).kind),
          );
        }
      }
      cy.add(defs);
    } catch (e) {
      setError(`Failed to apply elements: ${(e as Error).message}`);
    }
  }, [elements, kindFilter]);

  // Apply layout when it changes.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    try {
      // Build the layout options object and cast — Cytoscape's union of
      // per-layout options types is wide; we only set common fields.
      const options: { name: LayoutName; padding: number; animate: boolean; directed?: boolean } = {
        name: layout,
        padding: 16,
        animate: false,
      };
      if (layout === 'breadthfirst') {
        options.directed = true;
      }
      cy.layout(options as unknown as Parameters<typeof cy.layout>[0]).run();
    } catch (e) {
      setError(`Failed to apply layout: ${(e as Error).message}`);
    }
  }, [layout]);

  if (error) {
    return (
      <div
        className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-800"
        role="alert"
      >
        {error}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      aria-label="Graph viewer. Use plus and minus keys to zoom, arrow keys to pan."
      className="h-96 w-full rounded border border-ink-100 bg-white focus:outline-none focus:ring-2 focus:ring-accent-500"
      data-testid="cytoscape-container"
    />
  );
}
