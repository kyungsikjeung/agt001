// 사장님용 "사이트 직접 편집" 목업 화면 (서버 연결 없음, ?room 없이 열 때).
// D27: 내용(글자·연락처·영업시간·가격)만 직접 고침. 구조·분위기는 "AI에게 부탁하기"(자리 링크).
// D23: 자리 표시는 눈에 띄게 + 상단 배너. D24: 공유방 사실 변경은 "방장 확인 필요" 문구만.
import { useMemo, useState } from 'react';
import { MOCK_SPECS } from './mockSpec';
import {
  applySetContent,
  canRedo,
  canUndo,
  initialEditorState,
  isPublishable,
  listPlaceholders,
  redo,
  undo,
  type EditorState,
} from './specReducer';
import SectionPreview, { type EditTarget } from './SectionPreview';

type Mode = 'preview' | 'edit';

interface PendingConfirm {
  target: EditTarget;
  value: string;
}

const LONG_FIELDS = new Set(['subtitle', 'body', 'desc']);

export default function MockEditor() {
  const [mockId, setMockId] = useState(MOCK_SPECS[0].id);
  const [editor, setEditor] = useState<EditorState>(() => initialEditorState(MOCK_SPECS[0].spec));
  const [mode, setMode] = useState<Mode>('preview');
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [draft, setDraft] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<PendingConfirm | null>(null);

  const placeholders = useMemo(() => listPlaceholders(editor.spec), [editor.spec]);
  const publish = useMemo(() => isPublishable(editor.spec), [editor.spec]);

  function switchMock(id: string) {
    const found = MOCK_SPECS.find((m) => m.id === id);
    if (!found) return;
    setMockId(id);
    setEditor(initialEditorState(found.spec));
    setEditing(null);
    setConfirm(null);
    setFormError(null);
  }

  function openEdit(t: EditTarget) {
    setEditing(t);
    setDraft(t.value);
    setFormError(null);
  }

  function buildValue(target: EditTarget, raw: string): unknown {
    if (target.itemIndex !== undefined) {
      const section = editor.spec.sections.find((s) => s.id === target.sectionId);
      const items = (Array.isArray(section?.content['items']) ? [...(section?.content['items'] as unknown[])] : []) as Array<
        Record<string, unknown>
      >;
      const prev = (items[target.itemIndex] ?? {}) as Record<string, unknown>;
      items[target.itemIndex] = { ...prev, [target.itemField ?? 'price']: raw };
      return items;
    }
    return raw;
  }

  function saveEdit(force = false) {
    if (!editing) return;
    const value = buildValue(editing, draft);
    const res = applySetContent(editor, editing.sectionId, editing.key, value, { force });
    if (res.needsConfirm) {
      setConfirm({ target: editing, value: draft });
      return;
    }
    if (!res.ok) {
      setFormError(res.error ?? '입력값을 확인해 주세요.');
      return;
    }
    setEditor(res.state);
    setEditing(null);
    setConfirm(null);
    setFormError(null);
  }

  function saveConfirm() {
    if (!confirm) return;
    const value = buildValue(confirm.target, confirm.value);
    const res = applySetContent(editor, confirm.target.sectionId, confirm.target.key, value, { force: true });
    if (!res.ok) {
      setFormError(res.error ?? '입력값을 확인해 주세요.');
      setConfirm(null);
      return;
    }
    setEditor(res.state);
    setConfirm(null);
    setEditing(null);
    setFormError(null);
  }

  function goToFirstSlot() {
    const first = placeholders[0];
    if (!first) return;
    const id =
      first.itemIndex === undefined
        ? `slot-${first.sectionId}-${first.key}`
        : `slot-${first.sectionId}-${first.key}-${first.itemIndex}`;
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    document.getElementById(id)?.focus({ preventScroll: true });
  }

  const multiline = editing ? (editing.multiline ?? LONG_FIELDS.has(editing.key)) : false;

  return (
    <div className="ed-page">
      <header className="ed-top">
        <div className="ed-top-row">
          <h1 className="ed-shop">{editor.spec.shopName}</h1>
          <span className="ed-saved" aria-live="polite">
            저장됨 v{editor.spec.version}
          </span>
        </div>
        <div className="ed-toolbar" role="group" aria-label="편집 도구">
          <button
            type="button"
            className="ed-btn"
            aria-pressed={mode === 'preview'}
            onClick={() => setMode('preview')}
          >
            미리보기
          </button>
          <button type="button" className="ed-btn" aria-pressed={mode === 'edit'} onClick={() => setMode('edit')}>
            편집
          </button>
          <button
            type="button"
            className="ed-btn"
            disabled={!canUndo(editor)}
            onClick={() => setEditor((s) => undo(s))}
            aria-label="되돌리기"
          >
            되돌리기
          </button>
          <button
            type="button"
            className="ed-btn"
            disabled={!canRedo(editor)}
            onClick={() => setEditor((s) => redo(s))}
            aria-label="다시 하기"
          >
            다시 하기
          </button>
        </div>
        <div className="ed-mock-switch" role="group" aria-label="예시 가게 바꾸기">
          <span>예시:</span>
          {MOCK_SPECS.map((m) => (
            <button key={m.id} type="button" aria-pressed={mockId === m.id} onClick={() => switchMock(m.id)}>
              {m.label}
            </button>
          ))}
        </div>
        {publish.publishable ? (
          <p className="ed-banner-ok">다 채웠어요. 이제 공개할 수 있어요. (목업)</p>
        ) : (
          <button type="button" className="ed-banner" onClick={goToFirstSlot}>
            공개 전에 채울 곳 {placeholders.length}개 — 누르면 그 칸으로 이동해요
          </button>
        )}
      </header>

      <main className="ed-main">
        <span className="ed-example-tag">예시 화면 · 목업 데이터</span>
        <SectionPreview spec={editor.spec} mode={mode} placeholders={placeholders} onEdit={openEdit} />

        <div className="ed-ai-box">
          <p>섹션 추가·순서·색 같은 구조·분위기 변경은 여기서 직접 못 바꿔요.</p>
          <a href="#">AI에게 부탁하기 — 채팅방으로 이동 (자리)</a>
        </div>
        <p className="ed-history">
          기록 {editor.history.length}개 · 되돌리기 {canUndo(editor) ? '가능' : '없음'}
        </p>
      </main>

      {editing ? (
        <div className="ed-scrim" onClick={() => setEditing(null)}>
          <div
            className="ed-sheet"
            role="dialog"
            aria-modal="true"
            aria-label={`${editing.label} 고치기`}
            onClick={(e) => e.stopPropagation()}
          >
            <h2>
              {editing.label} 고치기
            </h2>
            <label htmlFor="ed-edit-input">{editing.label}</label>
            {multiline ? (
              <textarea
                id="ed-edit-input"
                value={draft}
                autoFocus
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setEditing(null);
                }}
              />
            ) : (
              <input
                id="ed-edit-input"
                type="text"
                value={draft}
                autoFocus
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setEditing(null);
                }}
              />
            )}
            {formError ? (
              <p className="ed-error" role="alert">
                {formError}
              </p>
            ) : null}
            <div className="ed-sheet-row">
              <button type="button" className="ed-btn" onClick={() => setEditing(null)}>
                닫기
              </button>
              <button type="button" className="ed-btn ed-btn--primary" onClick={() => saveEdit(false)}>
                저장
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {confirm ? (
        <div className="ed-scrim" onClick={() => setConfirm(null)}>
          <div
            className="ed-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="잠긴 값 확인"
            onClick={(e) => e.stopPropagation()}
          >
            <h2>직접 정하신 값이에요. 바꿀까요?</h2>
            <p>
              ‘{confirm.target.label}’은(는) 잠긴 값이에요. 공유방의 사실 변경은 방장 확인이 필요해요. (목업)
            </p>
            <div className="ed-sheet-row">
              <button type="button" className="ed-btn" autoFocus onClick={() => setConfirm(null)}>
                그대로 두기
              </button>
              <button type="button" className="ed-btn ed-btn--primary" onClick={saveConfirm}>
                바꾸기
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
