import { useEffect, useRef, useState } from 'react';
import Mascot from '../Mascot';
import { claim, me, startLogin, type MeUser } from '../auth';
import { useScrolled } from '../useScrolled';

export interface Project {
  room_id: string;
  title: string;
  industry: string | null;
  state: string | null;
  state_label: string;
  created_at: string | null;
  updated_at: string | null;
  last_message: string | null;
  members: number;
  deploy_url: string | null;
  design_url: string | null;
  /** 지운 시각. 지운 프로젝트는 비활성으로 남고 purge_at에 영구 삭제된다. */
  deleted_at?: string | null;
  purge_at?: string | null;
  is_owner?: boolean;
}

const ROOMS_KEY = 'agt001_rooms';
const MEMBER_KEY = 'agt001_member_id';
// 지운 뒤 되살릴 수 있는 기간 (서버 project_delete.GRACE_DAYS와 같아야 한다).
const GRACE_DAYS = 30;

function safeRead(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function readRoomIds(): string[] {
  try {
    const raw = localStorage.getItem(ROOMS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((r): r is string => typeof r === 'string' && r.length > 0).slice(0, 50);
  } catch {
    return [];
  }
}

/** "3시간 전" 같은 상대 시간. 파싱 실패나 미래 시각이면 날짜 그대로. */
export function relativeTime(iso: string | null): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const diff = Date.now() - t;
  if (diff < 0) return '';
  const min = Math.floor(diff / 60000);
  if (min < 1) return '방금 전';
  if (min < 60) return `${min}분 전`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}시간 전`;
  const day = Math.floor(hour / 24);
  if (day < 30) return `${day}일 전`;
  return new Date(t).toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });
}

// 로그인했으면 이 기기에 방이 없어도 부른다: 서버가 계정에 옮긴 방(다른 기기 포함)을 함께 돌려준다.
async function fetchSummary(roomIds: string[], memberId: string | null, loggedIn: boolean): Promise<Project[]> {
  if (!loggedIn && (roomIds.length === 0 || !memberId)) return [];
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (memberId) headers['X-Member-Id'] = memberId;
  const res = await fetch('/api/projects/summary', {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: JSON.stringify({ room_ids: roomIds }),
  });
  if (!res.ok) throw new Error(`목록을 불러오지 못했습니다 (${res.status})`);
  const data = (await res.json()) as { projects?: Project[] };
  return Array.isArray(data.projects) ? data.projects : [];
}

/** "10월 12일" 같은 날짜. 못 읽으면 빈 글. */
export function dayText(iso: string | null | undefined): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  return new Date(t).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });
}

async function postProject(roomId: string, action: 'delete' | 'restore', memberId: string | null): Promise<Project['deleted_at']> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (memberId) headers['X-Member-Id'] = memberId;
  const res = await fetch(`/api/projects/${encodeURIComponent(roomId)}/${action}`, {
    method: 'POST',
    credentials: 'same-origin',
    headers,
  });
  if (!res.ok) throw new Error(String(res.status));
  const data = (await res.json()) as { deleted_at?: string | null };
  return data.deleted_at ?? null;
}

export default function ProjectsPage() {
  const scrolled = useScrolled();
  const [user, setUser] = useState<MeUser | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const claimedRef = useRef(false);
  // 지우기: 한 번 더 묻고(진짜 지울까요?) 지운다. 30일 안에는 되살릴 수 있다.
  const [askDelete, setAskDelete] = useState<string | null>(null);
  const [busyRoom, setBusyRoom] = useState<string | null>(null);

  async function changeDeleted(roomId: string, action: 'delete' | 'restore') {
    setBusyRoom(roomId);
    setError(null);
    try {
      const deletedAt = await postProject(roomId, action, safeRead(MEMBER_KEY));
      setProjects((list) =>
        (list ?? []).map((p) =>
          p.room_id === roomId
            ? { ...p, deleted_at: deletedAt, purge_at: deletedAt ? new Date(Date.parse(deletedAt) + GRACE_DAYS * 86400000).toISOString() : null }
            : p,
        ),
      );
      setAskDelete(null);
    } catch {
      setError(action === 'delete' ? '지우지 못했어요. 잠시 뒤 다시 눌러 주세요.' : '되살리지 못했어요. 잠시 뒤 다시 눌러 주세요.');
    } finally {
      setBusyRoom(null);
    }
  }

  useEffect(() => {
    let alive = true;
    (async () => {
      const roomIds = readRoomIds();
      const memberId = safeRead(MEMBER_KEY);
      const u = await me();
      if (!alive) return;
      setUser(u);
      if (u && !claimedRef.current) {
        claimedRef.current = true;
        await claim(roomIds, memberId);
      }
      if (!alive) return;
      try {
        setProjects(await fetchSummary(roomIds, memberId, Boolean(u)));
      } catch {
        if (!alive) return;
        setError('목록을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.');
        setProjects([]);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const next = '/projects';

  return (
    <div className="page">
      <header className={scrolled ? 'topbar topbar--solid' : 'topbar'}>
        <a className="brand" href="/">
          <img className="brand-mark" src="/icons/kkachi.svg" alt="" width={30} height={30} />
          한마디
        </a>
        <nav className="top-links">
          <a className="projects-link on" href="/projects" aria-current="page">
            내 프로젝트
          </a>
          {user && <span className="nickname">{user.nickname}</span>}
        </nav>
      </header>

      <main className="projects">
        <h1>내 프로젝트</h1>

        {!user && (
          <section className="login-guide" aria-label="로그인 안내">
            <p>이 기기에서 만든 것만 보여요. 로그인하면 다른 기기에서도 볼 수 있어요.</p>
            <div className="login-guide-btns">
              <button className="kakao" type="button" onClick={() => startLogin('kakao', next)}>
                카카오로 계속하기
              </button>
              {/* 구글 로그인은 테스트 모드라 숨긴다(Landing.tsx와 같은 이유) */}
            </div>
          </section>
        )}

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {projects === null ? (
          <Mascot mood="wait" role="status" className="loading">
            <p>불러오는 중…</p>
          </Mascot>
        ) : projects.length === 0 ? (
          <section className="empty" aria-label="빈 목록">
            <img className="mascot__img" src="/icons/kkachi.svg" alt="" width={72} height={72} />
            <p>아직 만든 사이트가 없어요</p>
            <a className="send" href="/">
              새로 만들기
            </a>
          </section>
        ) : (
          <ul className="proj-list">
            {projects.map((p) => (
              <li key={p.room_id} className={`proj-card${p.deleted_at ? ' proj-card--deleted' : ''}`}>
                <div className="proj-head">
                  <b className="proj-title">{p.title}</b>
                  <span className="proj-badge">{p.state_label}</span>
                </div>
                <div className="proj-meta">
                  {p.industry && <span>{p.industry}</span>}
                  {p.updated_at && <time dateTime={p.updated_at}>{relativeTime(p.updated_at)}</time>}
                  <span>참여자 {p.members}명</span>
                </div>
                {p.last_message && <p className="proj-last">{p.last_message}</p>}
                {p.deleted_at ? (
                  <div className="proj-actions">
                    <p className="proj-deleted" role="status">
                      지웠어요. 사이트는 이미 닫혔고 {dayText(p.purge_at)}에 모든 기록이 영구 삭제돼요.
                    </p>
                    <button
                      type="button"
                      className="send"
                      disabled={busyRoom === p.room_id}
                      onClick={() => void changeDeleted(p.room_id, 'restore')}
                    >
                      {busyRoom === p.room_id ? '되살리는 중…' : '되살리기'}
                    </button>
                  </div>
                ) : askDelete === p.room_id ? (
                  <div className="proj-actions proj-confirm" role="group" aria-label="지우기 확인">
                    <p className="proj-deleted">
                      <b>정말 지울까요?</b> 공개 사이트가 바로 닫혀요(주문·결제·예약·채팅도 함께 멈춰요). 내시던
                      요금제가 있으면 바로 해지돼요. {GRACE_DAYS}일 뒤에 사이트·채팅·사진·예약·주문 기록까지 모두
                      영구 삭제돼요. {GRACE_DAYS}일 안에는 되살릴 수 있어요(요금제는 다시 신청해야 해요).
                    </p>
                    <button type="button" className="ghost" disabled={busyRoom === p.room_id} onClick={() => setAskDelete(null)}>
                      그만두기
                    </button>
                    <button
                      type="button"
                      className="proj-danger"
                      disabled={busyRoom === p.room_id}
                      onClick={() => void changeDeleted(p.room_id, 'delete')}
                    >
                      {busyRoom === p.room_id ? '지우는 중…' : '네, 지울래요'}
                    </button>
                  </div>
                ) : (
                  <div className="proj-actions">
                    <a className="send" href={`/room.html?room=${encodeURIComponent(p.room_id)}`}>
                      이어서 하기
                    </a>
                    {/* 공개한 뒤에도 고칠 수 있다(고치면 공개 사이트에 바로 반영). 전엔 길이 채팅방 안내 글뿐이었다. */}
                    <a className="ghost" href={`/editor?room=${encodeURIComponent(p.room_id)}`}>
                      고치기
                    </a>
                    {p.deploy_url && (
                      <a className="ghost" href={p.deploy_url} target="_blank" rel="noopener noreferrer">
                        사이트 보기
                      </a>
                    )}
                    {p.design_url && (
                      <a className="ghost" href={p.design_url} target="_blank" rel="noopener noreferrer">
                        시안 보기
                      </a>
                    )}
                    {p.is_owner !== false && (
                      <button type="button" className="ghost proj-del" onClick={() => setAskDelete(p.room_id)}>
                        지우기
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </main>

      <footer className="foot">
        <span>© {new Date().getFullYear()} 한마디 · 베타</span>
      </footer>
    </div>
  );
}
