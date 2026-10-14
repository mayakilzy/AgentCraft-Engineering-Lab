/**
 * ExperimentCard — T20 (G05).
 *
 * Per the architecture contract §1 + A09: each card offers Guided Mode
 * and Challenge Mode, displays the level, prerequisites, expected
 * outputs, and the technologies involved. No direct code execution.
 *
 * Per A12: localized EN/AR; technical symbols (operation_key, validator_key,
 * dataset_key) stay untranslated.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type {
  ExperimentManifest,
  MentorResponse,
  RunCreateResponse,
  RunRecord,
  StepVerdict,
} from '../api/client';
import {
  askMentor,
  createRun,
  exportRun,
  resetRun,
  listRuns,
} from '../api/client';
import { ensureGuestSession } from '../hooks/useGuestSession';

interface ExperimentCardProps {
  manifest: ExperimentManifest;
  locale: 'en' | 'ar';
  selectedForCompare: string[];
  onCompareSelect: (runId: string) => void;
}

export function ExperimentCard({
  manifest,
  locale,
  selectedForCompare,
  onCompareSelect,
}: ExperimentCardProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<'guided' | 'challenge'>('guided');
  const [inputsText, setInputsText] = useState(
    `dataset_id: ${manifest.dataset_key}, fixture_key: ${manifest.dataset_key}`,
  );
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<RunCreateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<RunRecord[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [expandedSteps, setExpandedSteps] = useState(false);
  const [inputsFormat, setInputsFormat] = useState<'text' | 'json'>('text');
  const [inputsError, setInputsError] = useState<string | null>(null);
  const [mentorQuestion, setMentorQuestion] = useState('');
  const [mentorAnswer, setMentorAnswer] = useState<MentorResponse | null>(null);
  const [mentorLoading, setMentorLoading] = useState(false);

  const pick = (text: { en: string; ar: string }) =>
    locale === 'ar' ? text.ar : text.en;

  async function handleRun() {
    setRunning(true);
    setError(null);
    setInputsError(null);
    try {
      // Mission I, ISSUE-004 fix: ensure guest session exists before
      // calling createRun (which requires the ac_guest cookie).
      await ensureGuestSession(locale);
      const inputs = parseInputs(inputsText, inputsFormat);
      if (inputs === null) {
        setInputsError(
          inputsFormat === 'json'
            ? 'Invalid JSON — check syntax'
            : 'Invalid inputs — use key:value pairs',
        );
        setRunning(false);
        return;
      }
      const result = await createRun(manifest.id, { mode, inputs });
      setLastRun(result);
      // Refresh history after a successful run.
      try {
        const h = await listRuns(manifest.id, 20);
        setHistory(h.runs);
        setShowHistory(true);
      } catch {
        // history refresh is best-effort
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }

  async function handleReset() {
    if (!lastRun) return;
    try {
      await resetRun(lastRun.run_id);
      // Refresh history.
      const h = await listRuns(manifest.id, 20);
      setHistory(h.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleExport(format: 'md' | 'json') {
    if (!lastRun) return;
    try {
      const res = await exportRun(lastRun.run_id, format);
      // Trigger a browser download of the report.
      const blob = new Blob(
        [format === 'md' ? String(res.report) : JSON.stringify(res.report, null, 2)],
        { type: format === 'md' ? 'text/markdown' : 'application/json' },
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${manifest.id}-${lastRun.run_id}.${format === 'md' ? 'md' : 'json'}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleAskMentor() {
    if (!lastRun || !mentorQuestion.trim()) return;
    setMentorLoading(true);
    try {
      const res = await askMentor({
        run_id: lastRun.run_id,
        question: mentorQuestion,
        lang: locale,
      });
      setMentorAnswer(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setMentorLoading(false);
    }
  }

  async function loadHistory() {
    try {
      const h = await listRuns(manifest.id, 20);
      setHistory(h.runs);
      setShowHistory(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <article
      className="rounded border border-ink-100 bg-white p-5 shadow-sm"
      aria-labelledby={`exp-${manifest.id}-title`}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3
            id={`exp-${manifest.id}-title`}
            className="text-lg font-semibold text-ink-900"
          >
            {pick(manifest.title)}
          </h3>
          <p className="mt-1 text-xs text-ink-900/70">{manifest.id}</p>
        </div>
        <div className="flex flex-wrap gap-1.5 text-xs">
          <span
            className="rounded bg-ink-50 px-2 py-0.5 text-ink-900/80"
            data-testid="level-badge"
          >
            {t(`experiments.level.${manifest.level}`)}
          </span>
          <span className="rounded bg-ink-50 px-2 py-0.5 text-ink-900/60">
            {manifest.estimated_minutes} {t('experiments.minutes')}
          </span>
          {manifest.technology.map((tech) => (
            <span
              key={tech}
              className="rounded bg-ink-50 px-2 py-0.5 text-ink-900/60"
            >
              {tech}
            </span>
          ))}
        </div>
      </header>

      <p className="mt-3 text-sm text-ink-900/80">{pick(manifest.description)}</p>

      <dl className="mt-3 grid grid-cols-1 gap-2 text-xs text-ink-900/70 sm:grid-cols-2">
        {manifest.prerequisites.length > 0 && (
          <div>
            <dt className="font-medium text-ink-900">
              {t('experiments.prerequisites')}
            </dt>
            <dd className="mt-0.5">{manifest.prerequisites.join(', ')}</dd>
          </div>
        )}
        {manifest.required_services.length > 0 && (
          <div>
            <dt className="font-medium text-ink-900">
              {t('experiments.requiredServices')}
            </dt>
            <dd className="mt-0.5">{manifest.required_services.join(', ')}</dd>
          </div>
        )}
        <div>
          <dt className="font-medium text-ink-900">
            {t('experiments.capabilities')}
          </dt>
          <dd className="mt-0.5">{manifest.capabilities.join(', ') || '—'}</dd>
        </div>
      </dl>

      {/* Steps accordion */}
      <div className="mt-4">
        <button
          type="button"
          className="text-xs font-medium text-ink-900 underline-offset-2 hover:underline"
          onClick={() => setExpandedSteps((v) => !v)}
          aria-expanded={expandedSteps}
          aria-controls={`steps-${manifest.id}`}
        >
          {expandedSteps
            ? t('experiments.hideSteps')
            : `${t('experiments.showAllSteps')} (${manifest.steps.length})`}
        </button>
        {expandedSteps && (
          <ol
            id={`steps-${manifest.id}`}
            className="mt-2 space-y-2 text-xs text-ink-900/80"
          >
            {manifest.steps.map((step, idx) => (
              <li key={step.id} className="border-l-2 border-ink-100 pl-2">
                <div className="font-medium">
                  {idx + 1}. {pick(step.title)}
                </div>
                <div className="mt-0.5 text-ink-900/70">{pick(step.instruction)}</div>
                <div className="mt-0.5 text-[10px] text-ink-900/50">
                  operation: <code>{step.operation_key}</code> · validator:{' '}
                  <code>{step.validator_key}</code>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>

      {/* Run controls */}
      <div className="mt-4 rounded bg-ink-50 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <fieldset className="flex items-center gap-2 text-xs">
            <legend className="sr-only">{t('experiments.mode.guided')}</legend>
            {(['guided', 'challenge'] as const).map((m) => (
              <label
                key={m}
                className="flex cursor-pointer items-center gap-1"
              >
                <input
                  type="radio"
                  name={`mode-${manifest.id}`}
                  value={m}
                  checked={mode === m}
                  onChange={() => setMode(m)}
                  className="h-3 w-3"
                />
                <span>{t(`experiments.mode.${m}`)}</span>
              </label>
            ))}
          </fieldset>
        </div>

        <label className="mt-3 block text-xs text-ink-900/70">
          <span className="font-medium">{t('experiments.inputsLabel')}</span>
          <span className="ml-1 text-ink-900/50">({t('experiments.inputsHint')})</span>
          <div className="mt-1 flex items-center gap-2">
            <button
              type="button"
              onClick={() => setInputsFormat('text')}
              className={`rounded px-2 py-0.5 text-[10px] ${
                inputsFormat === 'text'
                  ? 'bg-ink-900 text-white'
                  : 'bg-ink-50 text-ink-900/70'
              }`}
              aria-pressed={inputsFormat === 'text'}
            >
              Text
            </button>
            <button
              type="button"
              onClick={() => setInputsFormat('json')}
              className={`rounded px-2 py-0.5 text-[10px] ${
                inputsFormat === 'json'
                  ? 'bg-ink-900 text-white'
                  : 'bg-ink-50 text-ink-900/70'
              }`}
              aria-pressed={inputsFormat === 'json'}
            >
              JSON
            </button>
            {inputsError && (
              <span
                role="alert"
                className="text-[10px] text-red-700"
                data-testid={`inputs-error-${manifest.id}`}
              >
                {inputsError}
              </span>
            )}
          </div>
          {inputsFormat === 'json' ? (
            <textarea
              value={inputsText}
              onChange={(e) => setInputsText(e.target.value)}
              className="mt-1 w-full rounded border border-ink-100 bg-white px-2 py-1 font-mono text-xs"
              rows={3}
              placeholder='{"key": "value"}'
              data-testid={`inputs-${manifest.id}`}
              spellCheck={false}
            />
          ) : (
            <input
              type="text"
              value={inputsText}
              onChange={(e) => setInputsText(e.target.value)}
              className="mt-1 w-full rounded border border-ink-100 bg-white px-2 py-1 text-xs"
              data-testid={`inputs-${manifest.id}`}
            />
          )}
        </label>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleRun}
            disabled={running}
            className="rounded bg-ink-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
            data-testid={`run-${manifest.id}`}
          >
            {running ? t('common.loading') : t('experiments.run')}
          </button>
          {lastRun && (
            <>
              <button
                type="button"
                onClick={handleRun}
                className="rounded border border-ink-100 bg-white px-3 py-1 text-xs"
              >
                {t('experiments.rerun')}
              </button>
              <button
                type="button"
                onClick={handleReset}
                className="rounded border border-ink-100 bg-white px-3 py-1 text-xs"
              >
                {t('experiments.reset')}
              </button>
              <button
                type="button"
                onClick={() => handleExport('md')}
                className="rounded border border-ink-100 bg-white px-3 py-1 text-xs"
              >
                {t('experiments.exportMd')}
              </button>
              <button
                type="button"
                onClick={() => handleExport('json')}
                className="rounded border border-ink-100 bg-white px-3 py-1 text-xs"
              >
                {t('experiments.exportJson')}
              </button>
            </>
          )}
          <button
            type="button"
            onClick={loadHistory}
            className="rounded border border-ink-100 bg-white px-3 py-1 text-xs"
          >
            {t('experiments.runHistory')}
          </button>
        </div>
      </div>

      {/* Last run result */}
      {lastRun && (
        <div
          className="mt-3 rounded border border-ink-100 p-3 text-xs"
          data-testid={`run-result-${manifest.id}`}
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{t('experiments.status')}:</span>
            <span data-testid={`verdict-${manifest.id}`}>
              <StatusBadge status={lastRun.status} />
            </span>
            <span className="text-ink-900/70">
              {t('experiments.runId')}: <code>{lastRun.run_id}</code>
            </span>
            {lastRun.trace_id && (
              <span className="text-ink-900/70">
                {t('experiments.traceId')}: <code>{lastRun.trace_id.slice(0, 8)}…</code>
              </span>
            )}
            {lastRun.error_code && (
              <span className="text-ink-900/70">
                {t('experiments.errorCode')}: <code>{lastRun.error_code}</code>
              </span>
            )}
          </div>
          <div className="mt-2 space-y-1">
            {lastRun.step_verdicts.map((v, idx) => (
              <StepVerdictView key={idx} verdict={v} idx={idx + 1} />
            ))}
          </div>
        </div>
      )}

      {/* Mentor (T22) — ask a grounded question about the last run */}
      {lastRun && (
        <div className="mt-3 rounded border border-ink-100 bg-ink-50/50 p-3 text-xs">
          <h4 className="font-medium text-ink-900">Ask Mentor</h4>
          <p className="mt-0.5 text-ink-900/60">
            Ask a question about the run's outcome. The mentor uses only
            the run's evidence — no cross-session data.
          </p>
          <div className="mt-2 flex gap-2">
            <input
              type="text"
              value={mentorQuestion}
              onChange={(e) => setMentorQuestion(e.target.value)}
              placeholder="e.g., why did the run fail?"
              className="flex-1 rounded border border-ink-100 bg-white px-2 py-1 text-xs"
              data-testid={`mentor-question-${manifest.id}`}
              maxLength={2000}
            />
            <button
              type="button"
              onClick={handleAskMentor}
              disabled={mentorLoading || !mentorQuestion.trim()}
              className="rounded bg-ink-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              data-testid={`mentor-ask-${manifest.id}`}
            >
              {mentorLoading ? '…' : 'Ask'}
            </button>
          </div>
          {mentorAnswer && (
            <div
              className="mt-2 rounded bg-white p-2 text-xs"
              data-testid={`mentor-answer-${manifest.id}`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    mentorAnswer.diagnosis_state === 'confirmed'
                      ? 'bg-green-50 text-green-800'
                      : mentorAnswer.diagnosis_state === 'likely'
                        ? 'bg-amber-50 text-amber-800'
                        : 'bg-ink-50 text-ink-900/70'
                  }`}
                >
                  {mentorAnswer.diagnosis_state}
                </span>
                <span className="text-[10px] text-ink-900/50">
                  provider: {mentorAnswer.provider_mode}
                </span>
              </div>
              <p className="mt-1 text-ink-900/80">{mentorAnswer.answer}</p>
              {mentorAnswer.next_checks.length > 0 && (
                <div className="mt-2">
                  <div className="text-[10px] font-medium text-ink-900/70">
                    Next checks:
                  </div>
                  <ul className="mt-0.5 list-disc pl-4 text-ink-900/70">
                    {mentorAnswer.next_checks.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* History */}
      {showHistory && history.length > 0 && (
        <div className="mt-3 text-xs">
          <h4 className="font-medium text-ink-900">
            {t('experiments.runHistory')}
          </h4>
          <ul className="mt-1 space-y-1">
            {history.map((r) => (
              <li
                key={r.run_id}
                className="flex items-center gap-2 border-l-2 border-ink-100 pl-2"
              >
                <input
                  type="checkbox"
                  checked={selectedForCompare.includes(r.run_id)}
                  onChange={() => onCompareSelect(r.run_id)}
                  className="h-3 w-3"
                  aria-label={`Select ${r.run_id} for compare`}
                />
                <StatusBadge status={r.status} />
                <code className="text-[10px] text-ink-900/60">{r.run_id}</code>
                <span className="text-ink-900/50">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {showHistory && history.length === 0 && (
        <p className="mt-3 text-xs text-ink-900/60">{t('experiments.noRuns')}</p>
      )}

      {error && (
        <p
          role="alert"
          className="mt-2 text-xs text-red-700"
          data-testid={`error-${manifest.id}`}
        >
          {error}
        </p>
      )}
    </article>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    PASSED: 'bg-green-50 text-green-800',
    FAILED: 'bg-red-50 text-red-800',
    BLOCKED: 'bg-amber-50 text-amber-800',
    RUNNING: 'bg-blue-50 text-blue-800',
    CREATED: 'bg-ink-50 text-ink-900',
  };
  const cls = colors[status] || 'bg-ink-50 text-ink-900';
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${cls}`}>
      {status}
    </span>
  );
}

function StepVerdictView({ verdict, idx }: { verdict: StepVerdict; idx: number }) {
  return (
    <div className="border-l-2 border-ink-100 pl-2">
      <div className="flex items-center gap-2">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
            verdict.validator_passed
              ? 'bg-green-50 text-green-800'
              : 'bg-red-50 text-red-800'
          }`}
        >
          {verdict.validator_passed ? 'PASS' : 'FAIL'}
        </span>
        <span className="text-ink-900/80">
          {idx}. {verdict.step_id}
        </span>
      </div>
      <div className="mt-0.5 text-ink-900/60">{verdict.validator_message}</div>
    </div>
  );
}

function parseInputs(
  text: string,
  format: 'text' | 'json' = 'text',
): Record<string, unknown> | null {
  const trimmed = text.trim();
  if (!trimmed) return {};

  if (format === 'json') {
    try {
      const parsed = JSON.parse(trimmed);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch {
      return null;
    }
  }

  // Text mode: comma-separated key:value pairs.
  const out: Record<string, unknown> = {};
  for (const pair of trimmed.split(',').map((s) => s.trim())) {
    if (!pair) continue;
    const [k, ...rest] = pair.split(':');
    if (!k || rest.length === 0) continue;
    const v = rest.join(':').trim();
    // Auto-convert to number when it looks like one.
    if (/^-?\d+$/.test(v)) {
      out[k.trim()] = parseInt(v, 10);
    } else if (/^-?\d+\.\d+$/.test(v)) {
      out[k.trim()] = parseFloat(v);
    } else {
      out[k.trim()] = v;
    }
  }
  return out;
}
