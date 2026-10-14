/**
 * MentorPage — AI Mentor chat.
 *
 * Layout:
 *   - Run selector dropdown (from listRuns).
 *   - Chat message bubbles (user/assistant).
 *   - Question input + Ask button.
 *   - Evidence refs + next_checks display.
 *   - diagnosis_state chip (confirmed/likely/insufficient_evidence).
 *
 * Calls listRuns + askMentor. Uses useGuestSession to bootstrap session
 * before asking. Guards scrollIntoView for jsdom (the ref may not have
 * scrollIntoView in the test environment).
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Send, User } from 'lucide-react';
import { AppShell } from '../components/AppShell';
import { Card, Status, EmptyState, verdictTone } from '../components/ui';
import {
  askMentor,
  listRuns,
  type MentorResponse,
  type RunRecord,
} from '../api/client';
import { useGuestSession } from '../hooks/useGuestSession';

interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  response?: MentorResponse;
}

export function MentorPage() {
  const { t, i18n } = useTranslation();
  const locale = i18n.language === 'ar' ? 'ar' : 'en';
  const { session, error: sessionError } = useGuestSession(locale);

  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [preview, setPreview] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // If session creation itself failed, fall back to preview mode so
    // the page still renders something useful.
    if (sessionError) {
      setPreview(true);
    }
    if (!session) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await listRuns(undefined, 50);
        if (!cancelled) {
          setRuns(r.runs);
          setSelectedRunId(r.runs[0]?.run_id ?? '');
        }
      } catch (err) {
        if (!cancelled) {
          setPreview(true);
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, sessionError]);

  // Scroll the latest message into view when messages change. Guard for
  // jsdom where scrollIntoView is not implemented.
  useEffect(() => {
    const el = messagesEndRef.current;
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [messages]);

  async function handleAsk() {
    if (!selectedRunId || !question.trim()) return;
    const userMsg: ChatMessage = { role: 'user', text: question };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setError(null);
    const q = question;
    setQuestion('');
    try {
      const res = await askMentor({
        run_id: selectedRunId,
        question: q,
        lang: locale,
      });
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: res.answer, response: res },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: msg },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell previewMode={preview}>
      <section className="page-heading" aria-labelledby="mentor-title">
        <div>
          <div className="eyebrow">{t('nav.mentor')}</div>
          <h1 id="mentor-title">{t('mentor.title')}</h1>
          <p>{t('mentor.subtitle')}</p>
        </div>
        <Status tone={preview ? 'amber' : 'green'}>
          {preview ? t('common.previewData') : t('mentor.previewOnly')}
        </Status>
      </section>

      <Card className="chat-card" data-testid="mentor-card">
        <header className="mentor-header">
          <span className="bot-avatar" aria-hidden>
            <Bot size={18} />
          </span>
          <div>
            <b className="text-[15px]">{t('mentor.title')}</b>
            <small>{t('mentor.subtitle')}</small>
          </div>
        </header>

        {/* Run selector */}
        <div className="field mt-4 max-w-full" style={{ maxWidth: 'none' }}>
          <label className="muted whitespace-nowrap text-[11px] font-bold uppercase tracking-wide">
            {t('mentor.selectRun')}
          </label>
          <select
            value={selectedRunId}
            onChange={(e) => setSelectedRunId(e.target.value)}
            aria-label={t('mentor.selectRun')}
            data-testid="mentor-run-select"
            className="flex-1"
          >
            {runs.length === 0 && <option value="">—</option>}
            {runs.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.experiment_id} · {r.run_id.slice(0, 8)}… · {r.status}
              </option>
            ))}
          </select>
        </div>

        {/* Chat messages */}
        <div className="chat-messages" data-testid="mentor-messages">
          {messages.length === 0 ? (
            <EmptyState
              icon={<Bot size={20} />}
              title={t('mentor.emptyState')}
            />
          ) : (
            messages.map((m, i) => (
              <div
                key={i}
                className={`bubble ${m.role}`}
                data-testid={`mentor-bubble-${i}`}
              >
                <div className="mb-1.5 flex items-center gap-2 text-[11px] text-ink-400">
                  {m.role === 'assistant' ? <Bot size={12} /> : <User size={12} />}
                  <span>{m.role === 'assistant' ? 'Mentor' : 'You'}</span>
                </div>
                <p className="m-0">{m.text}</p>
                {m.response && (
                  <div className="mt-2">
                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                      <Status tone={verdictTone(m.response.diagnosis_state)}>
                        {t(`mentor.confidence.${m.response.diagnosis_state}`)}
                      </Status>
                      <span className="text-[10px] text-ink-400">
                        provider: {m.response.provider_mode}
                      </span>
                    </div>
                    {m.response.evidence_refs.length > 0 && (
                      <div className="mt-1">
                        <div className="muted text-[10px] font-bold uppercase tracking-wide">
                          {t('mentor.evidenceRefs')}
                        </div>
                        <ul className="m-1 list-disc ps-5 text-[12px] text-ink-600">
                          {m.response.evidence_refs.map((e, j) => (
                            <li key={j}>
                              <code className="text-[11px]">
                                {String((e as Record<string, unknown>).step_id ?? (e as Record<string, unknown>).ref ?? JSON.stringify(e))}
                              </code>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {m.response.next_checks.length > 0 && (
                      <div className="mt-1">
                        <div className="muted text-[10px] font-bold uppercase tracking-wide">
                          {t('mentor.nextChecks')}
                        </div>
                        <ul className="m-1 list-disc ps-5 text-[12px] text-ink-600">
                          {m.response.next_checks.map((c, j) => (
                            <li key={j}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Question input + Ask button */}
        <div className="chat-input">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={t('mentor.placeholder')}
            aria-label={t('mentor.placeholder')}
            data-testid="mentor-question"
            maxLength={2000}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void handleAsk();
              }
            }}
          />
          <button
            type="button"
            className="btn-primary"
            onClick={handleAsk}
            disabled={loading || !question.trim() || !selectedRunId}
            data-testid="mentor-ask"
          >
            <Send size={12} />
            {loading ? '…' : t('mentor.askButton')}
          </button>
        </div>

        {error && (
          <p role="alert" className="mt-3 text-[12px] text-danger-600" data-testid="mentor-error">
            {error}
          </p>
        )}
        {sessionError && (
          <p className="mt-2 text-[11px] text-ink-400">{sessionError}</p>
        )}
      </Card>
    </AppShell>
  );
}
