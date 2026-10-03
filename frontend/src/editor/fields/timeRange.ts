// 시간 두 개(체크인·체크아웃 등)를 글 한 줄로 쓰고 읽는다. 저장 칸(hours)은 글 그대로라 공개 사이트가 바로 보인다.

export interface TimePair {
  start: string; // 'HH:MM' 또는 ''
  end: string;
}

function pad(h: number, m: number): string {
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/** 글에서 시간을 차례로 찾는다: 15:00, 15시, 15시 30분, 3시반, 오후 3시. */
export function findTimes(text: string): string[] {
  const out: string[] = [];
  const re = /(오전|오후)?\s*(\d{1,2})(?::(\d{2})|\s*시(?:\s*(\d{1,2})\s*분|\s*(반))?)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text || '')) !== null) {
    let h = Number(m[2]);
    const min = m[3] !== undefined ? Number(m[3]) : m[4] !== undefined ? Number(m[4]) : m[5] ? 30 : 0;
    if (m[1] === '오후' && h < 12) h += 12;
    if (m[1] === '오전' && h === 12) h = 0;
    if (h > 24 || min > 59) continue;
    out.push(pad(h % 24, min));
  }
  return out;
}

export function parsePair(text: string): TimePair {
  const t = findTimes(text);
  return { start: t[0] ?? '', end: t[1] ?? '' };
}

/** 'HH:MM' 두 개 → "체크인 15:00 · 체크아웃 11:00". 하나만 있으면 그 하나만. */
export function formatPair(pair: TimePair, startName: string, endName: string): string {
  const parts: string[] = [];
  if (pair.start) parts.push(`${startName} ${pair.start}`);
  if (pair.end) parts.push(`${endName} ${pair.end}`);
  return parts.join(' · ');
}

/** 글이 이 부품이 만든 모양 그대로인가(아니면 사장님이 직접 쓴 글이라 '직접 쓰기'를 펴 둔다). */
export function isComposed(text: string, startName: string, endName: string): boolean {
  const v = (text || '').trim();
  return v === '' || v === formatPair(parsePair(v), startName, endName);
}
