/**
 * ExperimentCard — gallery card for one experiment.
 *
 * Per the architecture contract §1 + A09: each card offers Guided Mode
 * and Challenge Mode, displays the level, prerequisites, expected
 * outputs, and the technologies involved. No direct code execution.
 *
 * Per A12: localized EN/AR; technical symbols (operation_key, validator_key,
 * dataset_key) stay untranslated.
 *
 * Mission II: restyled with the design-system classes (.exp-card, .card,
 * .status, .segmented, .info-line, .callout, etc.). All existing testids
 * are preserved and two new ones added: verdict-{id} and run-result-{id}.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Play, RotateCcw, Download, Send, ChevronDown, ChevronUp } from 'lucide-react';
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
import { Status, verdictTone } from './ui';

interface ExperimentCardProps {
  manifest: ExperimentManifest;
  locale: 'en' | 'ar';
  selectedForCompare: string[];
  onCompareSelect: (runId: string) => void;
  /** Optional E0N prefix shown in the card header. */
  displayLabel?: string;
}

export function ExperimentCard({
  manifest,
  locale,
  selectedForCompare,
  onCompareSelect,
  displayLabel,
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
            ? t('experiments.invalidJson')
            : t('experiments.invalidText'),
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
      className="exp-card card-hover"
      aria-labelledby={`exp-${manifest.id}-title`}
      data-testid={`exp-card-${manifest.id}`}
    >
      <div className="exp-thumb">
        <span className="text-[10px] font-extrabold uppercase tracking-widest text-white/80">
          {displayLabel ?? manifest.module_id}
        </span>
      </div>

      <div className="exp-body">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h3
              id={`exp-${manifest.id}-title`}
              className="text-[14px] font-extrabold text-ink-900"
            >
              {pick(manifest.title)}
            </h3>
            <small className="muted mt-0.5 block">{manifest.id}</small>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="status status-blue" data-testid="level-badge">
              {t(`experiments.level.${manifest.level}`)}
            </span>
            <span className="status status-gray">
              {manifest.estimated_minutes} {t('common.minutes')}
            </span>
          </div>
        </header>

        <p className="m-0 min-h-[30px] text-[11px] text-ink-500">
          {pick(manifest.description)}
        </p>

        <div className="flex flex-wrap gap-1.5">
          {manifest.technology.map((tech) => (
            <span
              key={tech}
              className="status status-purple"
            >
              {tech}
            </span>
          ))}
        </div>

        <dl className="grid grid-cols-1 gap-1.5 text-[11px] text-ink-600 sm:grid-cols-2">
          {manifest.prerequisites.length > 0 && (
            <div>
              <dt className="font-bold text-ink-900">
                {t('experiments.prerequisites')}
              </dt>
              <dd className="mt-0.5">{manifest.prerequisites.join(', ')}</dd>
            </div>
          )}
          {manifest.required_services.length > 0 && (
            <div>
              <dt className="font-bold text-ink-900">
                {t('experiments.requiredServices')}
              </dt>
              <dd className="mt-0.5">{manifest.required_services.join(', ')}</dd>
            </div>
          )}
          <div>
            <dt className="font-bold text-ink-900">
              {t('experiments.capabilities')}
            </dt>
            <dd className="mt-0.5">{manifest.capabilities.join(', ') || '—'}</dd>
          </div>
        </dl>

        {/* Steps accordion */}
        <div>
          <button
            type="button"
            className="text-link inline-flex items-center gap-1"
            onClick={() => setExpandedSteps((v) => !v)}
            aria-expanded={expandedSteps}
            aria-controls={`steps-${manifest.id}`}
          >
            {expandedSteps ? (
              <ChevronUp size={12} />
            ) : (
              <ChevronDown size={12} />
            )}
            {expandedSteps
              ? t('experiments.hideSteps')
              : `${t('experiments.showAllSteps')} (${manifest.steps.length})`}
          </button>
          {expandedSteps && (
            <ol
              id={`steps-${manifest.id}`}
              className="m-0 mt-2 list-none space-y-1.5 p-0 text-[11px] text-ink-600"
            >
              {manifest.steps.map((step, idx) => (
                <li
                  key={step.id}
                  className="border-s-2 border-ink-200 ps-2"
                >
                  <div className="font-bold text-ink-900">
                    {idx + 1}. {pick(step.title)}
                  </div>
                  <div className="mt-0.5 text-ink-500">{pick(step.instruction)}</div>
                  <div className="mt-0.5 text-[10px] text-ink-400">
                    operation: <code>{step.operation_key}</code> · validator:{' '}
                    <code>{step.validator_key}</code>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      {/* Run controls */}
      <div className="border-t border-ink-100 bg-surface-subtle p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="segmented" role="group" aria-label="Mode">
            {(['guided', 'challenge'] as const).map((m) => (
              <button
                key={m}
                type="button"
                className={mode === m ? 'selected' : ''}
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
                data-testid={`mode-${m}-${manifest.id}`}
              >
                {t(`experiments.mode.${m}`)}
              </button>
            ))}
          </div>
          <div className="segmented" role="group" aria-label="Inputs format">
            {(['text', 'json'] as const).map((f) => (
              <button
                key={f}
                type="button"
                className={inputsFormat === f ? 'selected' : ''}
                aria-pressed={inputsFormat === f}
                onClick={() => setInputsFormat(f)}
                data-testid={`inputs-format-${f}-${manifest.id}`}
              >
                {f === 'text' ? t('experiments.textMode') : t('experiments.jsonMode')}
              </button>
            ))}
          </div>
          {inputsError && (
            <span
              role="alert"
              className="text-[10px] text-danger-600"
              data-testid={`inputs-error-${manifest.id}`}
            >
              {inputsError}
            </span>
          )}
        </div>

        <label className="mt-2 block">
          <span className="muted text-[10px] font-bold uppercase tracking-wide">
            {t('experiments.inputsLabel')}
          </span>
          {inputsFormat === 'json' ? (
            <textarea
              value={inputsText}
              onChange={(e) => setInputsText(e.target.value)}
              className="mt-1 w-full rounded-btn border border-ink-200 bg-white px-2 py-1 font-mono text-[11px]"
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
              className="mt-1 w-full rounded-btn border border-ink-200 bg-white px-2 py-1 text-[11px]"
              data-testid={`inputs-${manifest.id}`}
            />
          )}
        </label>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleRun}
            disabled={running}
            className="btn-primary"
            data-testid={`run-${manifest.id}`}
          >
            <Play size={12} />
            {running ? t('common.loading') : t('experiments.run')}
          </button>
          {lastRun && (
            <>
              <button
                type="button"
                onClick={handleRun}
                className="btn-primary"
                data-testid={`rerun-${manifest.id}`}
              >
                <RotateCcw size={12} />
                {t('experiments.rerun')}
              </button>
              <button
                type="button"
                onClick={handleReset}
                className="btn-secondary"
                data-testid={`reset-${manifest.id}`}
              >
                <RotateCcw size={12} />
                {t('experiments.reset')}
              </button>
              <button
                type="button"
                onClick={() => handleExport('md')}
                className="btn-secondary"
                data-testid={`export-md-${manifest.id}`}
              >
                <Download size={12} />
                {t('experiments.exportMd')}
              </button>
              <button
                type="button"
                onClick={() => handleExport('json')}
                className="btn-secondary"
                data-testid={`export-json-${manifest.id}`}
              >
                <Download size={12} />
                {t('experiments.exportJson')}
              </button>
            </>
          )}
          <button
            type="button"
            onClick={loadHistory}
            className="btn-secondary"
            data-testid={`history-${manifest.id}`}
          >
            {t('experiments.runHistory')}
          </button>
        </div>
      </div>

      {/* Last run result */}
      {lastRun && (
        <div
          className="border-t border-ink-100 p-3"
          data-testid={`run-result-${manifest.id}`}
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-bold text-ink-700">
              {t('experiments.status')}:
            </span>
            <span data-testid={`verdict-${manifest.id}`}>
              <Status tone={verdictTone(lastRun.status)}>{lastRun.status}</Status>
            </span>
            <span className="text-[11px] text-ink-500">
              {t('experiments.runId')}: <code>{lastRun.run_id}</code>
            </span>
            {lastRun.trace_id && (
              <span className="text-[11px] text-ink-500">
                {t('experiments.traceId')}:{' '}
                <code>{lastRun.trace_id.slice(0, 8)}…</code>
              </span>
            )}
            {lastRun.error_code && (
              <span className="text-[11px] text-ink-500">
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
        <div className="border-t border-ink-100 bg-surface-subtle p-3">
          <h4 className="text-[12px] font-bold text-ink-900">
            {t('mentor.title')}
          </h4>
          <p className="muted mt-0.5 text-[11px]">{t('mentor.subtitle')}</p>
          <div className="mt-2 flex gap-2">
            <input
              type="text"
              value={mentorQuestion}
              onChange={(e) => setMentorQuestion(e.target.value)}
              placeholder={t('mentor.placeholder')}
              className="min-w-0 flex-1 rounded-btn border border-ink-200 bg-white px-2 py-1 text-[11px]"
              data-testid={`mentor-question-${manifest.id}`}
              maxLength={2000}
            />
            <button
              type="button"
              onClick={handleAskMentor}
              disabled={mentorLoading || !mentorQuestion.trim()}
              className="btn-primary"
              data-testid={`mentor-ask-${manifest.id}`}
            >
              <Send size={12} />
              {mentorLoading ? '…' : t('mentor.askButton')}
            </button>
          </div>
          {mentorAnswer && (
            <div
              className="mt-2 rounded-btn bg-white p-2 text-[11px]"
              data-testid={`mentor-answer-${manifest.id}`}
            >
              <div className="flex items-center gap-2">
                <Status tone={verdictTone(mentorAnswer.diagnosis_state)}>
                  {t(`mentor.confidence.${mentorAnswer.diagnosis_state}`)}
                </Status>
                <span className="text-[10px] text-ink-400">
                  provider: {mentorAnswer.provider_mode}
                </span>
              </div>
              <p className="mt-1 text-ink-600">{mentorAnswer.answer}</p>
              {mentorAnswer.next_checks.length > 0 && (
                <div className="mt-2">
                  <div className="text-[10px] font-bold text-ink-500">
                    {t('mentor.nextChecks')}
                  </div>
                  <ul className="m-0 list-disc ps-4 text-ink-500">
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
        <div className="border-t border-ink-100 p-3 text-[11px]">
          <h4 className="font-bold text-ink-900">
            {t('experiments.runHistory')}
          </h4>
          <ul className="m-0 mt-1 list-none space-y-1 p-0">
            {history.map((r) => (
              <li
                key={r.run_id}
                className="flex items-center gap-2 border-s-2 border-ink-200 ps-2"
              >
                <input
                  type="checkbox"
                  checked={selectedForCompare.includes(r.run_id)}
                  onChange={() => onCompareSelect(r.run_id)}
                  className="h-3 w-3"
                  aria-label={`Select ${r.run_id} for compare`}
                />
                <Status tone={verdictTone(r.status)}>{r.status}</Status>
                <code className="text-[10px] text-ink-500">{r.run_id}</code>
                <span className="muted">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {showHistory && history.length === 0 && (
        <p className="muted border-t border-ink-100 p-3 text-[11px]">
          {t('experiments.noRuns')}
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="border-t border-ink-100 p-3 text-[11px] text-danger-600"
          data-testid={`error-${manifest.id}`}
        >
          {error}
        </p>
      )}
    </article>
  );
}

function StepVerdictView({ verdict, idx }: { verdict: StepVerdict; idx: number }) {
  return (
    <div className="border-s-2 border-ink-200 ps-2">
      <div className="flex items-center gap-2">
        <Status tone={verdict.validator_passed ? 'green' : 'red'}>
          {verdict.validator_passed ? 'PASS' : 'FAIL'}
        </Status>
        <span className="text-[11px] text-ink-600">
          {idx}. {verdict.step_id}
        </span>
      </div>
      <div className="mt-0.5 text-[11px] text-ink-500">{verdict.validator_message}</div>
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
