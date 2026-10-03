// 선생님·담당자 고치기 칸 (BUILDER_FIX_1003_CONTRACT S2).
// 한 사람은 접힌 줄(이름 · 과목)로 보이고, 눌러 펼치면 칸을 고친다.
// 아래 '저장'을 한 번 눌러 전체를 보내고, 사진은 저장된 이름에만 올린다.
// 이름을 바꿔 저장하면 원래 이름(prev_name)을 같이 보내 서버가 사진을 새 이름으로 옮긴다.
import { useEffect, useRef, useState } from 'react';
import { fetchCard, readMemberId, saveCard, uploadPhoto, type RoomCard, type StaffMember } from './cardApi';

/** 한 줄 편집용. 전문 분야는 쉼표로 적었다가 저장할 때 목록으로 푼다. */
interface StaffRow {
  /** 서버에 저장돼 있던 이름(새 줄은 ""). 이름 바꾸기 때 사진을 옮기는 데 쓴다 */
  prev: string;
  name: string;
  role: string;
  subject: string;
  tagline: string;
  bio: string;
  specialties: string;
}

const MAX_STAFF = 12;

function emptyRow(): StaffRow {
  return { prev: '', name: '', role: '', subject: '', tagline: '', bio: '', specialties: '' };
}

/** 카드의 선생님 목록 → 편집용 줄. 비어 있으면 빈 줄 하나로 시작한다. */
function toRows(staff: StaffMember[] | undefined): StaffRow[] {
  if (!staff || staff.length === 0) return [emptyRow()];
  return staff.map((m) => ({
    prev: m.name ?? '',
    name: m.name ?? '',
    role: m.role ?? '',
    subject: m.subject ?? '',
    tagline: m.tagline ?? '',
    bio: m.bio ?? '',
    specialties: (m.specialties ?? []).join(', '),
  }));
}

/** 사진 주소를 뺀 선생님 내용. 사진만 바뀌었을 때(사진 올리기) 고치던 줄을 되돌리지 않게 비교에 쓴다. */
function staffKey(staff: StaffMember[] | undefined): string {
  return JSON.stringify((staff ?? []).map(({ photo: _photo, ...rest }) => rest));
}

/** 접힌 줄에 보일 이름 · 과목. */
function rowTitle(row: StaffRow): string {
  const name = row.name.trim() || '새 선생님';
  const subject = row.subject.trim();
  return subject ? `${name} · ${subject}` : name;
}

export default function StaffEditor({
  roomId,
  card,
  onSaved,
}: {
  roomId: string;
  card: RoomCard;
  onSaved: (card: RoomCard) => void;
}) {
  const [rows, setRows] = useState<StaffRow[]>(() => toRows(card.staff));
  const [open, setOpen] = useState<boolean[]>(() => toRows(card.staff).map(() => true));
  const [saving, setSaving] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const fileRefs = useRef<Array<HTMLInputElement | null>>([]);

  // 서버의 선생님 내용이 바뀌었을 때만 줄을 다시 채운다. 사진만 바뀐 카드(사진 올리기 뒤)는
  // 다른 줄에서 고치던 글을 지우지 않는다. 저장 결과 문구('저장했어요.')도 여기서 지우지 않는다.
  const contentKey = staffKey(card.staff);
  useEffect(() => {
    const next = toRows(card.staff);
    setRows(next);
    setOpen(next.map(() => true));
  }, [contentKey]);

  // 서버에 저장된 이름들. 여기에 없는 이름에는 사진을 올릴 수 없다.
  const savedNames = new Set((card.staff ?? []).map((m) => m.name.trim()).filter((n) => n !== ''));
  // 저장된 이름 → 지금 사진 주소 (줄 안 미리보기)
  const photoOf = new Map((card.staff ?? []).map((m) => [m.name.trim(), m.photo ?? ''] as const));

  function setCell(i: number, key: keyof StaffRow, value: string) {
    setRows((prev) => prev.map((r, j) => (j !== i ? r : { ...r, [key]: value })));
  }

  function toggle(i: number) {
    setOpen((prev) => prev.map((v, j) => (j !== i ? v : !v)));
  }

  function addRow() {
    setRows((prev) => (prev.length >= MAX_STAFF ? prev : [...prev, emptyRow()]));
    setOpen((prev) => (prev.length >= MAX_STAFF ? prev : [...prev, true]));
  }

  function removeRow(i: number) {
    setRows((prev) => prev.filter((_, j) => j !== i));
    setOpen((prev) => prev.filter((_, j) => j !== i));
  }

  async function save() {
    setSaving(true);
    setError('');
    setInfo('');
    try {
      const staff: StaffMember[] = rows.map((r) => ({
        name: r.name.trim(),
        role: r.role.trim(),
        subject: r.subject.trim(),
        tagline: r.tagline.trim(),
        bio: r.bio.trim(),
        specialties: r.specialties
          .split(',')
          .map((s) => s.trim())
          .filter((s) => s !== '')
          .slice(0, 4),
        ...(r.prev && r.prev !== r.name.trim() ? { prev_name: r.prev } : {}),
      }));
      const updated = await saveCard(roomId, readMemberId(), {}, undefined, { staff });
      onSaved(updated);
      setInfo('저장했어요.');
    } catch (e) {
      setError(
        e instanceof Error && e.message && !e.message.startsWith('저장하지 못했습니다')
          ? e.message
          : '저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.',
      );
    } finally {
      setSaving(false);
    }
  }

  async function onPhoto(file: File | undefined, name: string) {
    if (!file) return;
    setPhotoBusy(true);
    setError('');
    try {
      await uploadPhoto(roomId, readMemberId(), file, `staff:${name}`);
      const updated = await fetchCard(roomId, readMemberId());
      onSaved(updated);
      setInfo('사진을 올렸어요.');
    } catch {
      setError('사진을 올리지 못했어요.');
    } finally {
      setPhotoBusy(false);
    }
  }

  return (
    <div className="ed-staff">
      <p className="ed-site-hint">선생님을 눌러 펼치고 고친 뒤, 아래 저장 한 번으로 끝내세요.</p>
      {rows.map((row, i) => {
        const name = row.name.trim();
        const canPhoto = name !== '' && savedNames.has(name);
        const photo = canPhoto ? photoOf.get(name) ?? '' : '';
        return (
          <div key={i} className="ed-staff__row">
            <button type="button" className="ed-btn ed-staff__head" aria-expanded={open[i] ?? true} onClick={() => toggle(i)}>
              {rowTitle(row)}
            </button>
            {open[i] ?? true ? (
              <div className="ed-staff__body">
                <label className="ed-staff__cell">
                  <span>이름</span>
                  <input
                    className="ed-input"
                    type="text"
                    value={row.name}
                    maxLength={20}
                    disabled={saving}
                    onChange={(e) => setCell(i, 'name', e.target.value)}
                  />
                </label>
                <label className="ed-staff__cell">
                  <span>역할</span>
                  <input
                    className="ed-input"
                    type="text"
                    value={row.role}
                    placeholder="선생님"
                    maxLength={12}
                    disabled={saving}
                    onChange={(e) => setCell(i, 'role', e.target.value)}
                  />
                </label>
                <label className="ed-staff__cell">
                  <span>과목·분야</span>
                  <input
                    className="ed-input"
                    type="text"
                    value={row.subject}
                    placeholder="예: 영어"
                    maxLength={12}
                    disabled={saving}
                    onChange={(e) => setCell(i, 'subject', e.target.value)}
                  />
                </label>
                <label className="ed-staff__cell ed-staff__cell--wide">
                  <span>한 줄 소개</span>
                  <input
                    className="ed-input"
                    type="text"
                    value={row.tagline}
                    placeholder="예: 수능 영어, 해석은 제대로"
                    maxLength={40}
                    disabled={saving}
                    onChange={(e) => setCell(i, 'tagline', e.target.value)}
                  />
                </label>
                <label className="ed-staff__cell ed-staff__cell--wide">
                  <span>소개</span>
                  <textarea
                    className="ed-input"
                    value={row.bio}
                    rows={3}
                    maxLength={200}
                    disabled={saving}
                    onChange={(e) => setCell(i, 'bio', e.target.value)}
                  />
                </label>
                <label className="ed-staff__cell ed-staff__cell--wide">
                  <span>전문 분야</span>
                  <input
                    className="ed-input"
                    type="text"
                    value={row.specialties}
                    placeholder="쉼표로 구분, 최대 4개"
                    disabled={saving}
                    onChange={(e) => setCell(i, 'specialties', e.target.value)}
                  />
                </label>
                <div className="ed-staff__photo">
                  {photo ? (
                    <img className="ed-staff__thumb" src={photo} alt={`${name} 사진`} width={56} height={70} />
                  ) : null}
                  <button
                    type="button"
                    className="ed-btn"
                    disabled={!canPhoto || photoBusy}
                    onClick={() => fileRefs.current[i]?.click()}
                  >
                    {photo ? '사진 바꾸기' : '사진 올리기'}
                  </button>
                  <input
                    ref={(el) => {
                      fileRefs.current[i] = el;
                    }}
                    type="file"
                    accept="image/*"
                    tabIndex={-1}
                    aria-hidden="true"
                    className="ed-staff__file"
                    onChange={(e) => {
                      void onPhoto(e.target.files?.[0], name);
                      e.target.value = '';
                    }}
                  />
                  {canPhoto ? null : <p className="ed-site-hint">이름을 저장한 뒤 사진을 올릴 수 있어요.</p>}
                </div>
                <button
                  type="button"
                  className="ed-btn ed-staff__remove"
                  disabled={saving}
                  onClick={() => removeRow(i)}
                  aria-label={`${i + 1}번째 선생님 빼기`}
                >
                  빼기
                </button>
              </div>
            ) : null}
          </div>
        );
      })}
      {rows.length < MAX_STAFF ? (
        <button type="button" className="ed-btn" disabled={saving} onClick={addRow}>
          + 선생님 더하기
        </button>
      ) : null}
      <div className="ed-site-save">
        <button type="button" className="ed-btn ed-btn--primary ed-btn--block" disabled={saving} onClick={() => void save()}>
          {saving ? '저장 중…' : '저장'}
        </button>
      </div>
      {error ? (
        <p className="ed-error" role="alert">
          {error}
        </p>
      ) : null}
      {info ? <p role="status">{info}</p> : null}
    </div>
  );
}
