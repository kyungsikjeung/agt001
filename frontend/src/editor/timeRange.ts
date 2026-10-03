// 시간 칸 빠르게 고르기 (10/4): 체크인·아웃 / 영업·수업 시간을 버튼으로 고르고, 글 한 줄로 저장한다.
// 카드 hours 칸은 글 하나라(공개 사이트에 그대로 보임) 고른 값을 사람이 읽는 문장으로 만든다.
// 이미 있는 글(채팅으로 들어온 "15시 / 11시", "매일 10시~21시, 월요일 휴무")도 읽어 버튼을 맞춘다.

export type TimeMode = 'stay' | 'open';

export const DAY_SETS = ['매일', '평일', '주말'] as const;
export const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'] as const;

export interface StayTimes {
  checkin: string;
  checkout: string;
}

export interface OpenTimes {
  days: string;
  open: string;
  close: string;
  closed: string[];
}

/** 라벨로 고르기 모양을 정한다. 체크인이 있으면 숙박, 시간 칸이면 여는·닫는 시간. 아니면 글 칸 그대로. */
export function timeModeOf(label: string): TimeMode | null {
  if (label.includes('체크인')) return 'stay';
  if (/(영업|수업|운영|이용)\s*시간/.test(label)) return 'open';
  return null;
}

function pad(h: number, m: number): string {
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/** 글에서 시각을 차례로 뽑는다: 15:00, 15시, 15시 30분, 오후 3시, 3시반. */
export function readTimes(text: string): string[] {
  const out: string[] = [];
  // "10~21시"처럼 앞 숫자에 '시'가 빠진 범위를 먼저 "10시~21시"로
  const t = text.replace(/(\d{1,2})\s*([~\-–])\s*(?=\d{1,2}\s*시)/g, '$1시$2');
  const re = /(오전|오후)?\s*(\d{1,2})\s*(?::\s*(\d{2})|시\s*(?:(\d{1,2})\s*분|(반))?)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(t)) !== null) {
    let h = Number(m[2]);
    const min = m[3] ? Number(m[3]) : m[4] ? Number(m[4]) : m[5] ? 30 : 0;
    if (m[1] === '오후' && h < 12) h += 12;
    if (m[1] === '오전' && h === 12) h = 0;
    if (h > 24 || min > 59) continue;
    out.push(pad(h === 24 ? 0 : h, min));
  }
  return out;
}

export function readStay(text: string): StayTimes {
  const [checkin = '', checkout = ''] = readTimes(text);
  return { checkin, checkout };
}

export function writeStay(t: StayTimes): string {
  const parts = [];
  if (t.checkin) parts.push(`체크인 ${t.checkin}`);
  if (t.checkout) parts.push(`체크아웃 ${t.checkout}`);
  return parts.join(' · ');
}

export function readOpen(text: string): OpenTimes {
  const [open = '', close = ''] = readTimes(text);
  const days = DAY_SETS.find((d) => text.includes(d)) ?? '';
  const off = /([월화수목금토일](?:\s*[·,/\s]\s*[월화수목금토일])*)\s*(?:요일)?\s*(?:정기\s*)?휴무/.exec(text);
  const closed = off ? WEEKDAYS.filter((d) => off[1].includes(d)) : [];
  return { days, open, close, closed };
}

export function writeOpen(t: OpenTimes): string {
  const range = t.open || t.close ? `${t.open || '?'}~${t.close || '?'}` : '';
  const head = [t.days, range].filter(Boolean).join(' ');
  const off = t.closed.length > 0 ? `${t.closed.join('·')}요일 휴무` : '';
  return [head, off].filter(Boolean).join(', ');
}

/** 30분 간격 시각 목록 (고르기 칸). */
export function halfHours(): string[] {
  const out: string[] = [];
  for (let h = 0; h < 24; h += 1) for (const m of [0, 30]) out.push(pad(h, m));
  return out;
}

/** 자주 쓰는 시각 (버튼). */
export const QUICK = {
  checkin: ['14:00', '15:00', '16:00'],
  checkout: ['10:00', '11:00', '12:00'],
  open: ['09:00', '10:00', '11:00'],
  close: ['18:00', '20:00', '21:00', '22:00'],
} as const;
