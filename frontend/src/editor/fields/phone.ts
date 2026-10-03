// 전화번호 모양 (서버 app/services/validate.py check_phone·format_phone과 같은 규칙).
// 입력 칸에서는 쓰는 동안 하이픈을 넣어 보이고, 저장은 서버가 같은 규칙으로 한 가지 모양(010-1234-5678)으로 맞춘다.

const MOBILE = ['010', '011', '016', '017', '018', '019'];
const AREA = ['02', '031', '032', '033', '041', '042', '043', '044', '051', '052', '053', '054', '055', '061', '062', '063', '064'];
const REP = /^1[568]\d{6}$/;
const INTERNET = /^050\d/;
const RRN_HYPHEN = /(?<!\d)\d{6}\s*-\s*[1-4]\d{6}(?!\d)/;
const RRN_PLAIN = /(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[1-4]\d{6}(?!\d)/;

export const PHONE_LEN_MSG = '전화번호 자리수가 맞지 않아요';
export const RRN_MSG = '주민등록번호는 받지 않아요';

export function phoneDigits(value: string): string {
  return (value || '').replace(/\D/g, '');
}

/** 한 자리 수 읽기("공일공")가 있으면 서버가 숫자로 바꾼다 — 칸에서는 손대지 않는다. */
export function hasSpokenDigits(value: string): boolean {
  return /[공영빵일이삼사오육륙칠팔구]{3,}/.test(value || '');
}

/** 자리 수가 다 차지 않아도 쓰는 동안 하이픈을 넣는다. 넘치는 숫자는 버린다. */
export function formatPhoneTyping(value: string): string {
  const d = phoneDigits(value);
  if (/^1[568]/.test(d)) return d.length <= 4 ? d : `${d.slice(0, 4)}-${d.slice(4, 8)}`;
  if (d.startsWith('02')) {
    if (d.length <= 2) return d;
    if (d.length <= 5) return `02-${d.slice(2)}`;
    if (d.length <= 9) return `02-${d.slice(2, 5)}-${d.slice(5)}`;
    return `02-${d.slice(2, 6)}-${d.slice(6, 10)}`;
  }
  const head = INTERNET.test(d) ? 4 : 3;
  const max = head + 8;
  const t = d.slice(0, max);
  if (t.length <= head) return t;
  if (t.length <= head + 3) return `${t.slice(0, head)}-${t.slice(head)}`;
  if (t.length <= head + 7) return `${t.slice(0, head)}-${t.slice(head, head + 3)}-${t.slice(head + 3)}`;
  return `${t.slice(0, head)}-${t.slice(head, head + 4)}-${t.slice(head + 4)}`;
}

/** 정상이면 null, 아니면 짧은 이유 (서버 check_phone과 같음). */
export function checkPhone(value: string): string | null {
  const text = value || '';
  if (RRN_HYPHEN.test(text) || RRN_PLAIN.test(text)) return RRN_MSG;
  const d = phoneDigits(text);
  if (!d) return PHONE_LEN_MSG;
  if (REP.test(d)) return null;
  if (d.startsWith('070')) return d.length >= 10 && d.length <= 11 ? null : PHONE_LEN_MSG;
  if (INTERNET.test(d)) return d.length >= 11 && d.length <= 12 ? null : PHONE_LEN_MSG;
  if (MOBILE.some((h) => d.startsWith(h))) return d.length >= 10 && d.length <= 11 ? null : PHONE_LEN_MSG;
  if (AREA.some((h) => d.startsWith(h))) return d.length >= 9 && d.length <= 11 ? null : PHONE_LEN_MSG;
  return PHONE_LEN_MSG;
}

/** 쓰기 전 칸의 커서 앞 숫자 개수 → 새 글에서 같은 숫자 뒤의 위치 (하이픈이 끼어도 커서가 튀지 않게). */
export function caretAfterDigits(formatted: string, digitsBefore: number): number {
  if (digitsBefore <= 0) return 0;
  let seen = 0;
  for (let i = 0; i < formatted.length; i += 1) {
    if (/\d/.test(formatted[i])) {
      seen += 1;
      if (seen === digitsBefore) return i + 1;
    }
  }
  return formatted.length;
}
