/**
 * WorkbenchPage — experiment workbench.
 *
 * Layout:
 *   - Left sidebar: experiment picker + step list (from manifest).
 *   - Right panel: experiment detail (title, level, prerequisites),
 *     mode toggle (Guided/Challenge), inputs (Text/JSON), Run/Rerun/
 *     Reset/Export buttons, step verdicts, embedded mentor.
 *
 * Calls listExperiments + getExperiment + createRun + resetRun + exportRun
 * + askMentor. Falls back to FALLBACK_MANIFESTS in preview mode.
 * Uses ensureGuestSession before createRun.
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Play, RotateCcw, Download, Send, Bot } from 'lucide-react';
import { AppShell } from '../components/AppShell';
import { Card, Status, Callout, EmptyState, verdictTone } from '../components/ui';
import {
  askMentor,
  createRun,
  exportRun,
  getExperiment,
  listExperiments,
  resetRun,
  type ExperimentManifest,
  type MentorResponse,
  type RunCreateResponse,
  type StepVerdict,
} from '../api/client';
import { FALLBACK_MANIFESTS } from '../data/fallbackExperiments';
import { ensureGuestSession } from '../hooks/useGuestSession';

export function WorkbenchPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language === 'ar' ? 'ar' : 'en';

  const [manifests, setManifests] = useState<ExperimentManifest[]>([]);
  const [preview, setPreview] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string>('');
  const [stepIdx, setStepIdx] = useState(0);
  const [mode, setMode] = useState<'guided' | 'challenge'>('guided');
  const [inputsFormat, setInputsFormat] = useState<'text' | 'json'>('text');
  const [inputsText, setInputsText] = useState('');
  const [inputsError, setInputsError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<RunCreateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mentorQuestion, setMentorQuestion] = useState('');
  const [mentorAnswer, setMentorAnswer] = useState<MentorResponse | null>(null);
  const [mentorLoading, setMentorLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const list = await listExperiments();
        const fetched = await Promise.all(list.ids.map((id) => getExperiment(id)));
        if (!cancelled) {
          setManifests(fetched);
          setSelectedId(fetched[0]?.id ?? '');
        }
      } catch {
        if (!cancelled) {
          setPreview(true);
          setManifests(FALLBACK_MANIFESTS);
          setSelectedId(FALLBACK_MANIFESTS[0]?.id ?? '');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = useMemo(
    () => manifests.find((m) => m.id === selectedId) ?? null,
    [manifests, selectedId],
  );

  // Reset the step cursor whenever the selected experiment changes.
  useEffect(() => {
    setStepIdx(0);
    setLastRun(null);
    setError(null);
    setMentorAnswer(null);
    setMentorQuestion('');
    if (selected) {
      setInputsText(`dataset_id: ${selected.dataset_key}, fixture_key: ${selected.dataset_key}`);
    }
  }, [selectedId, selected]);

  const pick = (text: { en: string; ar: string }) =>
    locale === 'ar' ? text.ar : text.en;

  async function handleRun() {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setInputsError(null);
    try {
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
      const result = await createRun(selected.id, { mode, inputs });
      setLastRun(result);
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
      setLastRun(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleExport(format: 'md' | 'json') {
    if (!lastRun) return;
    try {
      const res = await exportRun(lastRun.run_id, format);
      const blob = new Blob(
        [format === 'md' ? String(res.report) : JSON.stringify(res.report, null, 2)],
        { type: format === 'md' ? 'text/markdown' : 'application/json' },
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${selected?.id ?? 'run'}-${lastRun.run_id}.${format}`;
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

  if (loading) {
    return (
      <AppShell>
        <p className="text-[13px] text-ink-500">{t('common.loading')}</p>
      </AppShell>
    );
  }

  return (
    <AppShell previewMode={preview}>
      <section className="page-heading" aria-labelledby="workbench-title">
        <div>
          <div className="eyebrow">{t('nav.workbench')}</div>
          <h1 id="workbench-title">{t('workbench.title')}</h1>
          <p>{t('workbench.previewOnly')}</p>
        </div>
      </section>

      {!selected ? (
        <EmptyState title={t('experiments.noExperiments')} />
      ) : (
        <div className="workbench">
          {/* Left: picker + step list */}
          <Card className="!p-3">
            <div className="mb-3">
              <label className="muted mb-1.5 block text-[11px] font-bold uppercase tracking-wide">
                {t('workbench.selectExperiment')}
              </label>
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                className="w-full"
                aria-label={t('workbench.selectExperiment')}
              >
                {manifests.map((m, i) => (
                  <option key={m.id} value={m.id}>
                    E{String(i + 1).padStart(2, '0')} · {pick(m.title)}
                  </option>
                ))}
              </select>
            </div>

            <div className="muted mb-2 text-[11px] font-bold uppercase tracking-wide">
              {t('workbench.steps')}
            </div>
            <ol className="m-0 list-none p-0">
              {selected.steps.map((step, idx) => (
                <li key={step.id}>
                  <button
                    type="button"
                    className={`step-btn${idx === stepIdx ? ' current' : ''}`}
                    onClick={() => setStepIdx(idx)}
                    aria-current={idx === stepIdx ? 'step' : undefined}
                  >
                    <span>{idx + 1}</span>
                    <span>{pick(step.title)}</span>
                  </button>
                </li>
              ))}
            </ol>

            <Callout title={mode === 'guided' ? t('experiments.mode.guided') : t('experiments.mode.challenge')}>
              {mode === 'guided'
                ? t('workbench.guidedHint')
                : t('workbench.challengeHint')}
            </Callout>
          </Card>

          {/* Right: detail + inputs + run + verdicts + mentor */}
          <Card>
            <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-[18px] font-extrabold text-ink-900">
                  {pick(selected.title)}
                </h2>
                <p className="mt-1 text-[12px] text-ink-500">
                  {pick(selected.description)}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Status tone={verdictTone(selected.level === 'beginner' ? 'PASSED' : selected.level === 'intermediate' ? 'BLOCKED' : 'FAILED')}>
                  {t(`experiments.level.${selected.level}`)}
                </Status>
                <Status tone="gray">
                  {selected.estimated_minutes} {t('common.minutes')}
                </Status>
              </div>
            </header>

            {/* Current step instruction */}
            <div className="rounded-btn bg-surface-subtle p-4" data-testid="workbench-step">
              <div className="muted mb-1 text-[11px] font-bold uppercase tracking-wide">
                {t('experiments.step')} {stepIdx + 1} / {selected.steps.length}
              </div>
              <div className="text-[14px] font-bold text-ink-900">
                {pick(selected.steps[stepIdx].title)}
              </div>
              <p className="mt-1 text-[12px] text-ink-600">
                {pick(selected.steps[stepIdx].instruction)}
              </p>
              <div className="mt-2 text-[11px] text-ink-400">
                operation:{' '}
                <code className="text-ink-700">
                  {selected.steps[stepIdx].operation_key}
                </code>{' '}
                · validator:{' '}
                <code className="text-ink-700">
                  {selected.steps[stepIdx].validator_key}
                </code>
              </div>
            </div>

            {/* Mode + inputs + actions */}
            <div className="mt-4">
              <div className="toolbar">
                <div className="segmented" role="group" aria-label="Mode">
                  {(['guided', 'challenge'] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      className={mode === m ? 'selected' : ''}
                      aria-pressed={mode === m}
                      onClick={() => setMode(m)}
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
                    >
                      {f === 'text' ? t('experiments.textMode') : t('experiments.jsonMode')}
                    </button>
                  ))}
                </div>
              </div>

              {inputsFormat === 'json' ? (
                <textarea
                  value={inputsText}
                  onChange={(e) => setInputsText(e.target.value)}
                  rows={3}
                  className="font-mono"
                  data-testid="workbench-inputs"
                  spellCheck={false}
                />
              ) : (
                <input
                  type="text"
                  value={inputsText}
                  onChange={(e) => setInputsText(e.target.value)}
                  className="w-full rounded-btn border border-ink-200 bg-white px-3 py-2.5 text-[12px]"
                  data-testid="workbench-inputs"
                />
              )}
              {inputsError && (
                <p role="alert" className="mt-2 text-[11px] text-danger-600">
                  {inputsError}
                </p>
              )}

              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-primary"
                  onClick={handleRun}
                  disabled={running}
                  data-testid="workbench-run"
                >
                  <Play size={12} />
                  {running ? t('common.loading') : t('experiments.run')}
                </button>
                {lastRun && (
                  <>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={handleRun}
                    >
                      <RotateCcw size={12} />
                      {t('experiments.rerun')}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleReset}
                    >
                      <RotateCcw size={12} />
                      {t('experiments.reset')}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleExport('md')}
                    >
                      <Download size={12} />
                      {t('experiments.exportMd')}
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => handleExport('json')}
                    >
                      <Download size={12} />
                      {t('experiments.exportJson')}
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Last run result + step verdicts */}
            {lastRun && (
              <div
                className="mt-4 rounded-btn border border-ink-200 p-4"
                data-testid="run-result-workbench"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <Status tone={verdictTone(lastRun.status)} data-testid="verdict-workbench">
                    {lastRun.status}
                  </Status>
                  <span className="text-[12px] text-ink-500">
                    {t('experiments.runId')}:{' '}
                    <code className="text-[11px]">{lastRun.run_id}</code>
                  </span>
                  {lastRun.trace_id && (
                    <span className="text-[12px] text-ink-500">
                      {t('experiments.traceId')}:{' '}
                      <code className="text-[11px]">
                        {lastRun.trace_id.slice(0, 8)}…
                      </code>
                    </span>
                  )}
                </div>
                <div className="mt-3 space-y-1.5">
                  {lastRun.step_verdicts.map((v, i) => (
                    <StepVerdictRow key={i} verdict={v} idx={i + 1} />
                  ))}
                </div>
              </div>
            )}

            {/* Embedded mentor */}
            {lastRun && (
              <div className="mt-4 rounded-btn border border-ink-200 bg-surface-subtle p-4">
                <div className="mentor-header">
                  <span className="bot-avatar" aria-hidden>
                    <Bot size={18} />
                  </span>
                  <div>
                    <b className="text-[14px]">{t('mentor.title')}</b>
                    <small>{t('mentor.subtitle')}</small>
                  </div>
                </div>
                <div className="chat-input mt-3">
                  <input
                    type="text"
                    value={mentorQuestion}
                    onChange={(e) => setMentorQuestion(e.target.value)}
                    placeholder={t('mentor.placeholder')}
                    data-testid="mentor-question-workbench"
                    maxLength={2000}
                  />
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={handleAskMentor}
                    disabled={mentorLoading || !mentorQuestion.trim()}
                    data-testid="mentor-ask-workbench"
                  >
                    <Send size={12} />
                    {mentorLoading ? '…' : t('mentor.askButton')}
                  </button>
                </div>
                {mentorAnswer && (
                  <div
                    className="bubble assistant mt-3"
                    data-testid="mentor-answer-workbench"
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <Status tone={verdictTone(mentorAnswer.diagnosis_state)}>
                        {t(`mentor.confidence.${mentorAnswer.diagnosis_state}`)}
                      </Status>
                      <span className="text-[10px] text-ink-400">
                        provider: {mentorAnswer.provider_mode}
                      </span>
                    </div>
                    <p className="m-0">{mentorAnswer.answer}</p>
                    {mentorAnswer.next_checks.length > 0 && (
                      <div className="mt-2">
                        <div className="muted text-[10px] font-bold uppercase tracking-wide">
                          {t('mentor.nextChecks')}
                        </div>
                        <ul className="m-1 list-disc ps-5 text-[12px] text-ink-600">
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

            {error && (
              <p
                role="alert"
                className="mt-3 text-[12px] text-danger-600"
                data-testid="error-workbench"
              >
                {error}
              </p>
            )}
          </Card>
        </div>
      )}
    </AppShell>
  );
}

function StepVerdictRow({ verdict, idx }: { verdict: StepVerdict; idx: number }) {
  const passed = verdict.validator_passed;
  return (
    <div className="flex items-start gap-2 border-l-2 border-ink-200 ps-3 text-[12px]">
      <Status tone={passed ? 'green' : 'red'}>
        {passed ? 'PASS' : 'FAIL'}
      </Status>
      <div className="flex-1">
        <div className="font-bold text-ink-900">
          {idx}. {verdict.step_id}
        </div>
        <div className="text-ink-500">{verdict.validator_message}</div>
      </div>
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
  const out: Record<string, unknown> = {};
  for (const pair of trimmed.split(',').map((s) => s.trim())) {
    if (!pair) continue;
    const [k, ...rest] = pair.split(':');
    if (!k || rest.length === 0) continue;
    const v = rest.join(':').trim();
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
