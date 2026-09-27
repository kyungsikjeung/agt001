import { useEffect, useRef, useState } from 'react';
import { claim, me, startLogin, type MeUser } from '../auth';

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
}

const ROOMS_KEY = 'agt001_rooms';
const MEMBER_KEY = 'agt001_member_id';

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

export default function ProjectsPage() {
  const [user, setUser] = useState<MeUser | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const claimedRef = useRef(false);

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
      <header className="topbar">
        <a className="brand" href="/">
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
          <p className="loading" role="status">
            불러오는 중…
          </p>
        ) : projects.length === 0 ? (
          <section className="empty" aria-label="빈 목록">
            <p>아직 만든 사이트가 없어요</p>
            <a className="send" href="/">
              새로 만들기
            </a>
          </section>
        ) : (
          <ul className="proj-list">
            {projects.map((p) => (
              <li key={p.room_id} className="proj-card">
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
                <div className="proj-actions">
                  <a className="send" href={`/room.html?room=${encodeURIComponent(p.room_id)}`}>
                    이어서 하기
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
                </div>
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
