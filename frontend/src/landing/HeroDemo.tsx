import { useEffect, useRef, useState } from 'react';
import { TEMPLATES } from '../templates';

/**
 * 첫 화면 라이브 데모 무대. "말 한마디가 사이트로 바뀌는 순간"을 약 12초 주기로 반복한다.
 * React state + CSS transition/keyframes만 사용. 장식용이므로 aria-hidden 처리한다.
 */

type Demo = {
  key: string;
  kind: string;
  say: string;
  shop: string;
  line: string;
  chips: [string, string, string];
  rows: Array<[string, string]>;
  hours: string;
  mapLabel: string;
  palette: { primary: string; accent: string; ground: string; ink: string };
};

function tpl(id: string) {
  return TEMPLATES.find((t) => t.id === id) ?? TEMPLATES[0];
}

const REST = tpl('restaurant');
const ACAD = tpl('academy');
const PENS = tpl('pension');

const DEMOS: Demo[] = [
  {
    key: 'bunsik',
    kind: '식당',
    say: '망원동 분식집이에요. 메뉴랑 영업시간, 찾아오는 길 알려 주세요',
    shop: '망원동 분식',
    line: '매콤한 떡볶이와 든든한 김밥',
    chips: ['메뉴', '영업시간', '지도'],
    rows: [
      ['떡볶이', '4,500원'],
      ['김밥', '3,500원'],
      ['순대', '4,000원'],
    ],
    hours: '매일 11:00–21:00',
    mapLabel: '망원역 2번 출구 앞',
    palette: REST.palette,
  },
  {
    key: 'pilates',
    kind: '필라테스',
    say: '성수동 필라테스 스튜디오예요. 시간표랑 가격, 예약 방법 알려 주세요',
    shop: '숨 필라테스',
    line: '소규모 그룹 · 1:1 레슨',
    chips: ['수업', '가격', '예약'],
    rows: [
      ['그룹 레슨', '회당 3만원'],
      ['1:1 레슨', '회당 7만원'],
      ['첫 방문 체험', '1만원'],
    ],
    hours: '평일 07:00–22:00',
    mapLabel: '성수역 3번 출구 앞',
    palette: ACAD.palette,
  },
  {
    key: 'pension',
    kind: '펜션',
    say: '양양 바닷가 펜션이에요. 객실이랑 바비큐장, 주변 여행지 알려 주세요',
    shop: PENS.shop,
    line: '바다 앞 작은 정원과 바비큐',
    chips: [PENS.sections[0] ?? '객실', PENS.sections[1] ?? '바비큐', PENS.sections[2] ?? '주변 안내'],
    rows: [
      ['오션뷰 객실', '15만원~'],
      ['가든 객실', '12만원~'],
      ['바비큐장', '3만원'],
    ],
    hours: '입실 15:00 · 퇴실 11:00',
    mapLabel: '양양 해변 앞',
    palette: PENS.palette,
  },
];

type Phase = 0 | 1 | 2 | 3;

export default function HeroDemo() {
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState<Phase>(0);
  const [typed, setTyped] = useState(0);
  const [visible, setVisible] = useState(true);
  const [reduced] = useState(
    () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  const wrapRef = useRef<HTMLDivElement>(null);
  const demo = DEMOS[idx];

  // 화면 밖으로 스크롤되면 일시정지
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(
      (entries) => {
        const e = entries[0];
        if (e) setVisible(e.isIntersecting);
      },
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // 주기 진행. reduced-motion이면 ③④ 완성 상태를 정지 화면으로 보여 준다.
  useEffect(() => {
    if (reduced) {
      setPhase(3);
      setTyped(demo.say.length);
      return;
    }
    if (!visible) return;
    if (phase === 0) {
      if (typed < demo.say.length) {
        const id = window.setTimeout(() => setTyped((t) => Math.min(t + 1, demo.say.length)), 55);
        return () => window.clearTimeout(id);
      }
      const id = window.setTimeout(() => setPhase(1), 600);
      return () => window.clearTimeout(id);
    }
    const DUR: Record<Phase, number> = { 0: 0, 1: 2600, 2: 3000, 3: 3400 };
    const id = window.setTimeout(() => {
      if (phase < 3) {
        setPhase((p) => (Math.min(p + 1, 3) as Phase));
      } else {
        setIdx((i) => (i + 1) % DEMOS.length);
        setPhase(0);
        setTyped(0);
      }
    }, DUR[phase]);
    return () => window.clearTimeout(id);
  }, [phase, typed, idx, visible, reduced, demo.say.length]);

  const staticMode = reduced;
  const showChat = staticMode ? false : phase < 2;
  const fullSay = staticMode ? demo.say : demo.say.slice(0, typed);
  const p = demo.palette;

  return (
    <div ref={wrapRef} className="lp-stage" aria-hidden="true">
      <div className="lp-stage-glow" />
      <div className="lp-stage-dots" />
      <div className={`lp-drafts${phase === 3 || staticMode ? ' is-fan' : ''}`}>
        {DEMOS.map((d, i) => (
          <span
            key={d.key}
            className={`lp-draft lp-draft-${i}`}
            style={{ background: d.palette.ground, borderColor: d.palette.primary }}
          >
            <span className="lp-draft-bar" style={{ background: d.palette.primary }} />
            <span className="lp-draft-name" style={{ color: d.palette.ink }}>{d.shop}</span>
            {i === idx && (phase === 3 || staticMode) && <span className="lp-draft-pick">이걸로 할게요 ✓</span>}
          </span>
        ))}
      </div>
      <div className="lp-phone">
        <span className="lp-phone-notch" />
        <span className="lp-example">예시</span>
        <div className="lp-screen">
          <div className="lp-screen-head">
            <span className="lp-screen-kind">{demo.kind}</span>
            <span className="lp-screen-dots"><i /><i /><i /></span>
          </div>
          {showChat ? (
            <div className="lp-chat" key={`chat-${idx}`}>
              <div className="lp-bubble-me">
                <p>{fullSay}<span className="lp-caret" /></p>
                {phase === 0 && (
                  <span className="lp-wave">
                    {[0, 1, 2, 3, 4].map((i) => <i key={i} style={{ animationDelay: `${i * 0.13}s` }} />)}
                  </span>
                )}
              </div>
              {phase >= 1 && (
                <div className="lp-bubble-ai lp-enter">
                  <p>이렇게 이해했어요</p>
                  <span className="lp-checks">
                    {demo.chips.map((c, i) => (
                      <span key={c} className="lp-check" style={{ animationDelay: `${0.15 + i * 0.4}s` }}>
                        <b>✓</b> {c}
                      </span>
                    ))}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div className="lp-site" key={`site-${idx}`} style={{ background: p.ground }}>
              <div className="lp-site-hero" style={{ background: `linear-gradient(135deg, ${p.primary}, ${p.primary}cc 60%, ${p.accent})` }}>
                <b style={{ color: '#fff' }}>{demo.shop}</b>
                <span style={{ color: '#ffffffdd' }}>{demo.line}</span>
              </div>
              <ul className="lp-site-rows">
                {demo.rows.map(([name, price], i) => (
                  <li key={name} className="lp-enter" style={{ animationDelay: `${0.1 + i * 0.22}s`, color: p.ink }}>
                    <span>{name}</span><span>{price}</span>
                  </li>
                ))}
              </ul>
              <div className="lp-site-sub lp-enter" style={{ animationDelay: '0.8s', color: p.ink }}>
                <span>◷ {demo.hours}</span>
              </div>
              <div className="lp-site-map lp-enter" style={{ animationDelay: '1s', color: p.ink }}>
                <span>◎ {demo.mapLabel}</span>
              </div>
              <span className="lp-site-cta lp-pop" style={{ background: p.accent, color: p.ink, animationDelay: '1.25s' }}>
                문의하기
              </span>
            </div>
          )}
        </div>
        {(phase === 3 || staticMode) && (
          <span className="lp-published lp-enter"><b>●</b> 공개됨</span>
        )}
      </div>
      <p className="lp-stage-cap">예시 · {demo.kind} — 말하면 이렇게 바뀝니다</p>
    </div>
  );
}
