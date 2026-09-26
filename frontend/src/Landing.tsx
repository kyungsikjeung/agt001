import { useEffect, useRef, useState } from 'react';
import { PLACEHOLDERS, TEMPLATES, type Template } from './templates';
import { logout, me, startLogin, type MeUser } from './auth';
import { startRoom, track } from './api';

const MAX_LEN = 2000; // 서버 메시지 상한 (app/services/rooms.py MAX_MESSAGE_LEN)

export default function Landing() {
  const [text, setText] = useState('');
  const [templateId, setTemplateId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loginOpen, setLoginOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [user, setUser] = useState<MeUser | null>(null);
  const [hint, setHint] = useState(0);
  const [canInstall, setCanInstall] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    track('landing_view');
    me().then(setUser).catch(() => setUser(null));
    // 로그인 실패·구글 테스트 사용자 아님: 서버가 /?login_error=<제공자>_<사유>로 되돌린다 (D9).
    const params = new URLSearchParams(location.search);
    const loginError = params.get('login_error');
    if (loginError) {
      setToast(
        loginError.endsWith('_not_ready')
          ? '로그인은 곧 열립니다. 지금은 로그인 없이 바로 시작할 수 있어요.'
          : loginError.startsWith('google')
            ? '구글 로그인은 현재 초대된 분만 가능해요. 카카오로 시작해 주세요.'
            : '로그인에 실패했어요. 다시 시도해 주세요.',
      );
      window.setTimeout(() => setToast(null), 4000);
      params.delete('login_error');
      const rest = params.toString();
      history.replaceState(null, '', location.pathname + (rest ? `?${rest}` : ''));
    }
  }, []);

  // PWA: 브라우저가 설치 가능하다고 알려 주면 "앱 설치" 버튼을 보인다(static/pwa.js).
  useEffect(() => {
    const w = window as Window & { __agtInstall?: unknown };
    const sync = () => setCanInstall(Boolean(w.__agtInstall));
    sync();
    window.addEventListener('agt-install-ready', sync);
    return () => window.removeEventListener('agt-install-ready', sync);
  }, []);

  async function onInstall() {
    const w = window as Window & { __agtInstall?: { prompt: () => Promise<void> } | null };
    const ev = w.__agtInstall;
    if (!ev) return;
    await ev.prompt();
    w.__agtInstall = null;
    setCanInstall(false);
  }

  // 비어 있을 때만 안내 문구를 돌린다. 입력 중에는 바꾸지 않는다.
  useEffect(() => {
    if (text) return;
    const id = window.setInterval(() => setHint((h) => (h + 1) % PLACEHOLDERS.length), 4000);
    return () => window.clearInterval(id);
  }, [text]);

  // 입력 길이에 맞춰 입력창 높이를 늘린다.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 280)}px`;
  }, [text]);

  async function submit(message: string, tid?: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    track(tid ? 'template_click' : 'start_click', tid);
    try {
      await startRoom(trimmed, tid);
    } catch {
      setBusy(false);
      setError('잠시 연결이 불안정해요. 다시 눌러 주세요.');
    }
  }

  function pick(t: Template) {
    setText(t.starter);
    setTemplateId(t.id);
    inputRef.current?.focus();
  }

  function onLogin(provider: 'kakao' | 'google') {
    track('login_click');
    setLoginOpen(false);
    startLogin(provider, location.pathname + location.search);
  }

  async function onLogout() {
    setLoginOpen(false);
    await logout();
    setUser(null);
    setToast('로그아웃했어요.');
    window.setTimeout(() => setToast(null), 2500);
  }

  return (
    <div className="page">
      <header className="topbar">
        <a className="brand" href="/">
          agt001
        </a>
        <div className="login-wrap">
          <nav className="top-links" aria-label="계정">
            {canInstall && (
              <button className="ghost" type="button" onClick={onInstall}>
                앱 설치
              </button>
            )}
            <a className="projects-link" href="/projects">
              내 프로젝트
            </a>
            {user ? (
              <>
                <span className="nickname">{user.nickname}</span>
                <button className="ghost" type="button" onClick={onLogout}>
                  로그아웃
                </button>
              </>
            ) : (
              <button className="ghost" type="button" onClick={() => setLoginOpen((v) => !v)} aria-expanded={loginOpen}>
                로그인
              </button>
            )}
          </nav>
          {loginOpen && !user && (
            <div className="login-menu" role="menu">
              <button className="kakao" type="button" role="menuitem" onClick={() => onLogin('kakao')}>
                카카오로 계속하기
              </button>
              {/* 구글 로그인은 테스트 모드(초대된 계정만)라 숨긴다. 자체 도메인·브랜드 인증 뒤 다시 켠다(서버 경로는 그대로). */}
            </div>
          )}
        </div>
      </header>

      <main>
        <section className="hero">
          <p className="badge">베타 시연 · 무료</p>
          <h1>어떤 사이트를 만들까요?</h1>
          <p className="sub">하는 일을 설명하면 AI가 정리하고, 시안 3안을 보여드려요.</p>

          <form
            className="prompt"
            onSubmit={(e) => {
              e.preventDefault();
              submit(text, templateId);
            }}
          >
            <label htmlFor="prompt-input" className="sr-only">
              만들고 싶은 사이트 설명
            </label>
            <textarea
              id="prompt-input"
              ref={inputRef}
              rows={3}
              maxLength={MAX_LEN}
              value={text}
              placeholder={PLACEHOLDERS[hint]}
              onChange={(e) => {
                setText(e.target.value);
                if (!e.target.value) setTemplateId(undefined);
              }}
              onKeyDown={(e) => {
                // 휴대폰 키보드에서는 줄바꿈이 자연스러우므로, 데스크톱에서만 Enter로 보낸다.
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && window.matchMedia('(pointer: fine)').matches) {
                  e.preventDefault();
                  submit(text, templateId);
                }
              }}
            />
            <div className="prompt-bar">
              <span className="prompt-hint">로그인 없이 바로 시작돼요</span>
              <button className="send" type="submit" disabled={!text.trim() || busy} aria-label="시작하기">
                {busy ? '여는 중…' : '시작하기'}
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">
                  <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </form>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}

          <div className="chips" role="list" aria-label="업종 예시로 채우기">
            {TEMPLATES.map((t) => (
              <button
                key={t.id}
                type="button"
                role="listitem"
                className={`chip${templateId === t.id ? ' on' : ''}`}
                onClick={() => pick(t)}
              >
                {t.name}
              </button>
            ))}
          </div>
        </section>

        <section className="templates" aria-labelledby="tpl-title">
          <div className="section-head">
            <h2 id="tpl-title">템플릿으로 시작하기</h2>
            <p>고르면 그 업종에 맞는 질문부터 시작해요. 가게 이름과 사진은 대화하며 바꿉니다.</p>
          </div>
          <div className="grid">
            {TEMPLATES.map((t) => (
              <button key={t.id} type="button" className="card" onClick={() => submit(t.starter, t.id)} disabled={busy}>
                <MiniSite t={t} />
                <span className="card-meta">
                  <span className="card-name">{t.name}</span>
                  <span className="card-line">{t.tagline}</span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="steps" aria-label="진행 순서">
          <ol>
            <li>
              <b>말하기</b>
              <span>하는 일과 원하는 것을 적거나 말해요</span>
            </li>
            <li>
              <b>확인하기</b>
              <span>AI가 정리한 내용과 시안을 보고 고쳐요</span>
            </li>
            <li>
              <b>공개하기</b>
              <span>확정한 그대로 사이트가 열려요</span>
            </li>
          </ol>
        </section>
      </main>

      <footer className="foot">
        <span>© {new Date().getFullYear()} agt001 · 베타</span>
        <nav className="foot-links" aria-label="약관">
          <a href="/privacy.html">개인정보처리방침</a>
          <a href="/terms.html">이용약관</a>
        </nav>
      </footer>

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}

/** 템플릿의 색과 섹션으로 그린 작은 사이트 모형. 실제 예시 사이트(1-0f)가 생기면 그 화면으로 바꾼다. */
function MiniSite({ t }: { t: Template }) {
  const p = t.palette;
  return (
    <span className="mini" style={{ background: p.ground, color: p.ink }} aria-hidden="true">
      <span className="mini-tag">예시</span>
      <span className="mini-hero" style={{ background: `linear-gradient(135deg, ${p.primary}, ${p.primary}cc 55%, ${p.accent})` }}>
        <span className="mini-shop">{t.shop}</span>
        <span className="mini-cta" style={{ background: p.accent, color: p.ink }}>
          문의하기
        </span>
      </span>
      <span className="mini-sections">
        {t.sections.map((s) => (
          <span key={s} className="mini-sec">
            <span className="mini-thumb" style={{ background: `${p.primary}22` }} />
            <span className="mini-label">{s}</span>
          </span>
        ))}
      </span>
    </span>
  );
}
