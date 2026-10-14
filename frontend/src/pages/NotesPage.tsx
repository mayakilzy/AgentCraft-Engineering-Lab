/**
 * NotesPage — local scratchpad.
 *
 * Layout:
 *   - localStorage-backed scratchpad (STORAGE_KEY = 'ac-lab-notes-v1').
 *   - Editor (textarea) + notes list.
 *   - Create / edit / delete / clear-all.
 *   - "Saved locally" indicator.
 *
 * No previewMode — this page is always local. Uses AppShell (no preview flag).
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Save, Trash2, Plus, FileText, Check } from 'lucide-react';
import { AppShell } from '../components/AppShell';
import { Card, Status, EmptyState } from '../components/ui';

const STORAGE_KEY = 'ac-lab-notes-v1';

interface Note {
  id: string;
  title: string;
  body: string;
  updatedAt: string;
}

function loadNotes(): Note[] {
  if (typeof localStorage === 'undefined') return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed as Note[];
  } catch {
    return [];
  }
}

function saveNotes(notes: Note[]) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(notes));
  } catch {
    /* quota / disabled storage — silent */
  }
}

function newId(): string {
  return `note-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function NotesPage() {
  const { t } = useTranslation();
  const [notes, setNotes] = useState<Note[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [saved, setSaved] = useState(false);

  // Load on mount.
  useEffect(() => {
    const loaded = loadNotes();
    setNotes(loaded);
    if (loaded.length > 0) {
      setActiveId(loaded[0].id);
      setTitle(loaded[0].title);
      setBody(loaded[0].body);
    }
  }, []);

  // Persist whenever notes change.
  useEffect(() => {
    saveNotes(notes);
  }, [notes]);

  function startNew() {
    setActiveId(null);
    setTitle('');
    setBody('');
  }

  function selectNote(id: string) {
    const n = notes.find((x) => x.id === id);
    if (!n) return;
    setActiveId(id);
    setTitle(n.title);
    setBody(n.body);
  }

  function save() {
    const trimmedTitle = title.trim() || t('notes.title');
    const trimmedBody = body;
    const now = new Date().toISOString();
    if (activeId) {
      setNotes((prev) =>
        prev.map((n) =>
          n.id === activeId
            ? { ...n, title: trimmedTitle, body: trimmedBody, updatedAt: now }
            : n,
        ),
      );
    } else {
      const id = newId();
      const note: Note = { id, title: trimmedTitle, body: trimmedBody, updatedAt: now };
      setNotes((prev) => [note, ...prev]);
      setActiveId(id);
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  function removeNote(id: string) {
    setNotes((prev) => prev.filter((n) => n.id !== id));
    if (activeId === id) {
      setActiveId(null);
      setTitle('');
      setBody('');
    }
  }

  function clearAll() {
    setNotes([]);
    setActiveId(null);
    setTitle('');
    setBody('');
  }

  return (
    <AppShell>
      <section className="page-heading" aria-labelledby="notes-title">
        <div>
          <div className="eyebrow">{t('nav.notes')}</div>
          <h1 id="notes-title">{t('notes.title')}</h1>
          <p>{t('notes.subtitle')}</p>
        </div>
        {saved && (
          <Status tone="green" data-testid="notes-saved-indicator">
            <Check size={10} className="me-1 inline" aria-hidden />
            {t('notes.savedLocally')}
          </Status>
        )}
      </section>

      <div className="grid gap-[18px] lg:grid-cols-[1fr_320px]">
        {/* Editor */}
        <Card>
          <header className="mb-3 flex items-center justify-between">
            <h2 className="text-[16px] font-bold text-ink-900">
              {activeId ? t('notes.saveButton') : t('notes.placeholder')}
            </h2>
            <button
              type="button"
              className="btn-secondary"
              onClick={startNew}
              data-testid="notes-new"
            >
              <Plus size={12} />
              {t('notes.saveButton')}
            </button>
          </header>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t('notes.title')}
            aria-label={t('notes.title')}
            className="mb-3 w-full rounded-btn border border-ink-200 bg-white px-3 py-2.5 text-[14px] font-bold"
            data-testid="notes-title-input"
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={t('notes.placeholder')}
            aria-label={t('notes.placeholder')}
            rows={12}
            data-testid="notes-body-input"
          />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn-primary"
              onClick={save}
              data-testid="notes-save"
            >
              <Save size={12} />
              {t('notes.saveButton')}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={clearAll}
              disabled={notes.length === 0}
              data-testid="notes-clear"
            >
              <Trash2 size={12} />
              {t('notes.clearButton')}
            </button>
          </div>
        </Card>

        {/* Notes list */}
        <Card>
          <header className="mb-3 flex items-center justify-between">
            <h2 className="text-[16px] font-bold text-ink-900">
              {t('history.runHistory')}
            </h2>
            <small className="muted">{notes.length}</small>
          </header>
          {notes.length === 0 ? (
            <EmptyState
              icon={<FileText size={20} />}
              title={t('notes.placeholder')}
            />
          ) : (
            <ul className="m-0 max-h-96 list-none overflow-y-auto p-0">
              {notes.map((n) => (
                <li
                  key={n.id}
                  className={`flex items-start gap-2 border-b border-ink-100 py-3 text-[12px] ${
                    activeId === n.id ? 'bg-brand-50/40' : ''
                  }`}
                >
                  <button
                    type="button"
                    className="flex-1 text-start"
                    onClick={() => selectNote(n.id)}
                    data-testid={`notes-item-${n.id}`}
                  >
                    <div className="font-bold text-ink-900">{n.title}</div>
                    <small className="muted mt-0.5 block">
                      {new Date(n.updatedAt).toLocaleString()}
                    </small>
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${n.title}`}
                    className="icon-btn"
                    onClick={() => removeNote(n.id)}
                    data-testid={`notes-delete-${n.id}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
