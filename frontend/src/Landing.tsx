import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { PLACEHOLDERS, TEMPLATES, type Template } from './templates';
import { logout, me, startLogin, type MeUser } from './auth';
import { startRoom, track } from './api';
import { MEMBER_KEY, startBuilder } from './editor/cardApi';
import { MSG, voiceSupported, useVoiceInput } from './voice';
import { PHOTOS, photoBg } from './landing/photos';
import HeroDemo from './landing/HeroDemo';
import './landing.css';

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
  const promptRef = useRef<HTMLDivElement>(null);
  const [canVoice] = useState(voiceSupported);
  // 말한 내용은 입력창 끝에 이어 붙이기만 한다. 보내기는 사장님이 고친 뒤 직접 누른다.
  const voice = useVoiceInput((said) => {
    setText((cur) => (cur.trim() ? `${cur.trim()} ${said}` : said).slice(0, MAX_LEN));
    inputRef.current?.focus();
  });

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

  // 스크롤로 보이는 블록은 차례로 떠오른다.
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      document.querySelectorAll('.lp-reveal').forEach((el) => el.classList.add('is-in'));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('is-in');
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12 },
    );
    document.querySelectorAll('.lp-reveal').forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

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

  // 템플릿은 빌더로 시작한다(BUILDER_CONTRACT §4). 실패하면 예시 문장을 채운다.
  async function startFromTemplate(t: Template) {
    if (busy) return;
    setBusy(true);
    setError(null);
    track('template_click', t.id);
    try {
      const r = await startBuilder(t.id);
      try {
        localStorage.setItem(MEMBER_KEY, r.member_id);
      } catch {
        // 저장소를 못 써도 이동은 한다.
      }
      location.href = r.builder_url;
    } catch {
      setText(t.starter);
      setTemplateId(t.id);
      setBusy(false);
      inputRef.current?.focus();
    }
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

  function goToPrompt() {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    promptRef.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' });
    window.setTimeout(() => inputRef.current?.focus({ preventScroll: true }), reduced ? 0 : 500);
  }

  return (
    <div className="page">
      <header className="topbar">
        <a className="brand" href="/">
          한마디
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
              <p className="login-note">구글 로그인은 준비 중이에요. 카카오로 시작해 주세요.</p>
            </div>
          )}
        </div>
      </header>

      <main>
        <section className="hero lp-hero lp-bg lp-bg-hero">
          <div className="lp-hero-grid">
            <div className="lp-hero-copy">
              <p className="badge">베타 시연 · 무료</p>
              <h1 className="lp-title">
                말 한마디면
                <br />
                가게 사이트가{' '}
                <span className="lp-underline">
                  됩니다
                  <svg viewBox="0 0 200 24" preserveAspectRatio="none" aria-hidden="true">
                    <path d="M4 16 C 60 8, 140 8, 196 14" />
                  </svg>
                </span>
              </h1>
              <p className="sub lp-sub">하는 일을 말로 설명하세요. AI가 정리하고, 시안 3안을 보여 드리고, 고른 안을 바로 공개해요.</p>

              <div ref={promptRef}>
                <form
                  className="prompt lp-prompt"
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
                  {voice.numCheck && <p className="voice-note">{MSG.checkNumbers}</p>}
                  <div className="prompt-bar">
                    <span className="prompt-hint">로그인 없이 바로 시작돼요</span>
                    <span className="prompt-actions">
                      {canVoice && (
                        <button
                          type="button"
                          className={`mic${voice.state === 'recording' ? ' on' : ''}`}
                          onClick={voice.toggle}
                          disabled={voice.state === 'uploading' || busy}
                          aria-label={voice.state === 'recording' ? '녹음 멈추기' : '말로 입력'}
                        >
                          {voice.state === 'recording' ? (
                            <>
                              <svg aria-hidden="true" width="14" height="14" viewBox="0 0 14 14"><rect x="2" y="2" width="10" height="10" rx="2" fill="currentColor" /></svg>
                              <span className="mic-time">{voice.seconds}초</span>
                            </>
                          ) : (
                            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="9" y="2" width="6" height="12" rx="3" />
                              <path d="M5 10a7 7 0 0 0 14 0" />
                              <line x1="12" y1="17" x2="12" y2="22" />
                              <line x1="8" y1="22" x2="16" y2="22" />
                            </svg>
                          )}
                        </button>
                      )}
                      <button className="send" type="submit" disabled={!text.trim() || busy} aria-label="시작하기">
                        {busy ? '여는 중…' : '시작하기'}
                        <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16">
                          <path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </button>
                    </span>
                  </div>
                </form>
              </div>
              <p className="voice-status" role="status" aria-live="polite">
                {voice.status ?? (canVoice ? '' : MSG.keyboardMic)}
              </p>
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}

              <div className="chips lp-chips" role="list" aria-label="업종 예시로 채우기">
                {TEMPLATES.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    role="listitem"
                    className={`chip${templateId === t.id ? ' on' : ''}`}
                    onClick={() => void startFromTemplate(t)}
                  >
                    {t.name}
                  </button>
                ))}
              </div>
            </div>
            <div className="lp-hero-demo">
              <HeroDemo />
            </div>
          </div>
        </section>

        <section className="lp-section lp-bg lp-bg-how" aria-labelledby="how-title">
          <p className="lp-kicker">어떻게 되나요</p>
          <h2 className="lp-h2" id="how-title">말하고, 고르고, 열면 끝</h2>
          <p className="lp-lead">어려운 설정은 없어요. 세 단계면 가게 사이트가 열립니다.</p>
          <ol className="lp-how">
            <li className="lp-reveal" style={{ '--d': '0s' } as CSSProperties}>
              <span className="lp-num" aria-hidden="true">01</span>
              <b>말하기</b>
              <p>글·음성·사진으로 편하게. 하는 일과 원하는 것만 말하세요.</p>
              <div className="lp-art lp-art-talk" aria-hidden="true">
                <p className="lp-art-bubble">동네 카페예요. 소금빵이 제일 잘 나가요</p>
                <div className="lp-art-voice">
                  <span className="lp-art-mic">
                    <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z" /></svg>
                  </span>
                  <span className="lp-art-wave">{Array.from({ length: 14 }, (_, i) => <i key={i} style={{ '--i': i } as CSSProperties} />)}</span>
                  <span className="lp-art-photo" style={{ backgroundImage: `url(${PHOTOS.cafe})` }} />
                </div>
              </div>
            </li>
            <li className="lp-reveal" style={{ '--d': '0.1s' } as CSSProperties}>
              <span className="lp-num" aria-hidden="true">02</span>
              <b>확인하기</b>
              <p>요약 카드에서 사장님이 확인. 여럿이면 한 방에서 같이 정해요.</p>
              <div className="lp-art lp-art-check" aria-hidden="true">
                <div className="lp-art-card">
                  <small>이렇게 이해했어요</small>
                  {[['가게 이름', '모퉁이 커피'], ['대표 메뉴', '소금빵 3,500원'], ['영업시간', '매일 9시–8시']].map(([k, v], i) => (
                    <p key={k} style={{ '--i': i } as CSSProperties}><span>{k}</span><b>{v}</b><i>✓</i></p>
                  ))}
                </div>
              </div>
            </li>
            <li className="lp-reveal" style={{ '--d': '0.2s' } as CSSProperties}>
              <span className="lp-num" aria-hidden="true">03</span>
              <b>공개하기</b>
              <p>고른 시안 그대로 공개. 문의·예약 버튼으로 손님이 바로 와요.</p>
              <div className="lp-art lp-art-open" aria-hidden="true">
                <div className="lp-art-phone">
                  <div className="lp-art-hero" style={{ background: photoBg(PHOTOS.cafe) }}><b>모퉁이 커피</b></div>
                  <span className="lp-art-cta">문의하기</span>
                </div>
                <p className="lp-art-toast"><i />새 문의가 왔어요</p>
              </div>
            </li>
          </ol>
        </section>

        <section className="templates lp-bg lp-bg-tpl" aria-labelledby="tpl-title">
          <div className="section-head">
            <h2 id="tpl-title">템플릿으로 시작하기</h2>
            <p>고르면 바로 시안이 나와요. 기능은 눌러서 붙이고, 이름·사진은 그 자리에서 바꿔요.</p>
          </div>
          <div className="grid lp-tgrid">
            {TEMPLATES.map((t, i) => (
              <button
                key={t.id}
                type="button"
                className="card lp-tcard lp-reveal"
                style={{ '--d': `${Math.min(i, 5) * 0.07}s` } as CSSProperties}
                onClick={() => void startFromTemplate(t)}
                disabled={busy}
              >
                <MiniSite t={t} />
                <span className="card-meta">
                  <span className="card-name">{t.name}</span>
                  <span className="card-line">{t.tagline}</span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="lp-section lp-bg lp-bg-trust" aria-label="안심하고 시작하세요">
          <p className="lp-kicker">안심하고 시작하세요</p>
          <h2 className="lp-h2">없는 말은 만들지 않아요</h2>
          <ul className="lp-trust">
            <li className="lp-reveal" style={{ '--d': '0s' } as CSSProperties}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-3.6 8-10V5l-8-3-8 3v7c0 6.4 8 10 8 10z" /></svg>
              말하지 않은 전화·가격은 넣지 않아요
            </li>
            <li className="lp-reveal" style={{ '--d': '0.07s' } as CSSProperties}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
              공개 전에 사장님이 한 번 더 확인해요
            </li>
            <li className="lp-reveal" style={{ '--d': '0.14s' } as CSSProperties}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></svg>
              여럿이 한 방에서 같이 정해요
            </li>
            <li className="lp-reveal" style={{ '--d': '0.21s' } as CSSProperties}>
              <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z" /><circle cx="7" cy="7" r="1.5" fill="currentColor" /></svg>
              베타 기간 무료
            </li>
          </ul>
        </section>

        <section className="lp-cta lp-reveal" aria-labelledby="cta-title">
          <h2 id="cta-title">지금 한마디 해 보세요</h2>
          <p>로그인 없이 바로 시작돼요. 1분이면 시안 이야기가 시작됩니다.</p>
          <button className="lp-cta-btn" type="button" onClick={goToPrompt}>
            한마디 적어 보기
          </button>
        </section>

      </main>

      <footer className="foot">
        <span>© {new Date().getFullYear()} 한마디 · 베타</span>
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
  const photo = PHOTOS[t.id];
  return (
    <span className="mini" style={{ background: p.ground, color: p.ink }} aria-hidden="true">
      <span className="mini-tag">{photo ? '예시 이미지' : '예시'}</span>
      <span
        className="mini-hero"
        style={{ background: photo ? photoBg(photo) : `linear-gradient(135deg, ${p.primary}, ${p.primary}cc 55%, ${p.accent})` }}
      >
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
