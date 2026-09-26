// voice.ts 테스트 (fetch 가짜). 채팅방 static/voice.js와 같은 계약·문구인지 본다.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MSG, errorFor, hasNumber, transcribe } from './voice';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

function mockFetch(status: number, body: unknown = {}) {
  return vi.fn(async () => ({ ok: status >= 200 && status < 300, status, json: async () => body }) as Response);
}

describe('voice', () => {
  it('전화번호·가격·한글 숫자를 번호로 본다', () => {
    expect(hasNumber('아메리카노 4500원')).toBe(true);
    expect(hasNumber('공일공 일이삼사')).toBe(true);
    expect(hasNumber('전화번호는 나중에')).toBe(true);
    expect(hasNumber('동네 카페예요')).toBe(false);
  });

  it('서버 상태 코드마다 채팅방과 같은 안내를 준다', () => {
    expect(errorFor(413)).toBe(MSG.tooBig);
    expect(errorFor(429)).toBe(MSG.tooMany);
    expect(errorFor(503)).toBe(MSG.unavailable);
  });

  it('/api/stt에 audio 파일과 X-Member-Id를 보내고 글자를 돌려준다', async () => {
    localStorage.setItem('agt001_member_id', 'm1');
    const f = mockFetch(200, { text: '  꽃집 사이트요 ' });
    vi.stubGlobal('fetch', f);
    expect(await transcribe(new Blob(['x'], { type: 'audio/webm' }))).toBe('꽃집 사이트요');
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/stt');
    expect((init.headers as Record<string, string>)['X-Member-Id']).toBe('m1');
    expect((init.body as FormData).get('audio')).toBeInstanceOf(File);
  });

  it('방에 들어간 적 없으면 방문자 ID로 보낸다 (서버가 빈 값은 거절)', async () => {
    const f = mockFetch(200, { text: '네' });
    vi.stubGlobal('fetch', f);
    await transcribe(new Blob(['x'], { type: 'audio/mp4' }));
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)['X-Member-Id']).toMatch(/^v-/);
  });

  it('빈 글자·서버 오류는 안내 문구로 실패한다', async () => {
    vi.stubGlobal('fetch', mockFetch(200, { text: ' ' }));
    await expect(transcribe(new Blob(['x']))).rejects.toThrow(MSG.emptyText);
    vi.stubGlobal('fetch', mockFetch(503));
    await expect(transcribe(new Blob(['x']))).rejects.toThrow(MSG.unavailable);
  });
});
