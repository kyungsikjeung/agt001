// 전화번호 칸 자동 하이픈 (10/4). 치는 동안 010-1234-5678처럼 나눠 보여 준다.
// 저장 형식은 서버가 같은 규칙으로 한 번 더 맞춘다(app/services/phone_format.py).
// 숫자·공백·하이픈·괄호·점·+ 말고 다른 글자가 있으면("카톡으로 문의") 손대지 않는다.

const NUMBERISH = /^[\d\s\-().+]*$/;

function cut(d: string, sizes: number[]): string {
  const out: string[] = [];
  let i = 0;
  for (const n of sizes) {
    if (i >= d.length) break;
    out.push(d.slice(i, i + n));
    i += n;
  }
  if (i < d.length) out[out.length - 1] += d.slice(i);
  return out.join('-');
}

/** 치는 중인 값을 하이픈 표기로. 번호가 아니면 그대로 돌려준다. */
export function formatPhone(value: string): string {
  if (!NUMBERISH.test(value)) return value;
  let d = value.replace(/\D/g, '');
  if (value.trim().startsWith('+82') && d.startsWith('82')) d = '0' + d.slice(2);
  if (d === '') return value.trim() === '' ? '' : value;
  if (d.startsWith('02')) {
    d = d.slice(0, 10);
    // 02-123-4567(9자리) / 02-1234-5678(10자리)
    return cut(d, d.length === 10 ? [2, 4, 4] : [2, 3, 4]);
  }
  if (/^1[568]/.test(d)) return cut(d.slice(0, 8), [4, 4]); // 대표번호 1588-1234
  if (d.startsWith('050') && d.length > 11) return cut(d.slice(0, 12), [4, 4, 4]); // 안심번호
  d = d.slice(0, 11);
  // 010-1234-5678(휴대폰은 늘 3-4-4) / 031-123-4567(10자리)
  return cut(d, d.length === 11 || d.startsWith('010') ? [3, 4, 4] : [3, 3, 4]);
}

/** onChange용: 끝의 하이픈을 지우면(백스페이스) 그 앞 숫자까지 지운다. 안 그러면 하이픈이 바로 다시 붙어 지워지지 않는다. */
export function nextPhone(prev: string, next: string): string {
  if (next.length < prev.length && prev.startsWith(next) && prev.slice(next.length) === '-') {
    return formatPhone(next.slice(0, -1));
  }
  return formatPhone(next);
}

/** 다 친 값이 전화번호 모양인지(안내 문구용). 빈 값·글은 true(막지 않는다). */
export function phoneLooksOk(value: string): boolean {
  const v = value.trim();
  if (v === '' || !NUMBERISH.test(v)) return true;
  const d = v.replace(/\D/g, '');
  if (/^1[568]\d{6}$/.test(d)) return true;
  if (/^02\d{7,8}$/.test(d)) return true;
  if (/^050\d{9}$/.test(d)) return true;
  if (/^82\d{9,10}$/.test(d)) return true;
  return /^0[1-9]\d{8,9}$/.test(d);
}
