// 공개하기 (BUILDER_CONTRACT §2.5, §3 6번). 오른쪽 위.
import type { PublishResult } from '../editor/cardApi';

export interface PublishView {
  busy: boolean;
  result: PublishResult | null;
  siteUrl: string | null;
}

export default function PublishBar({
  view,
  onPublish,
}: {
  view: PublishView;
  onPublish: (force: boolean) => void;
}) {
  const need = view.result?.need ?? null;
  const message = view.result?.message ?? '';
  const loginUrls = view.result?.login_urls ?? [];
  return (
    <div className="bd-publish">
      <button
        type="button"
        className="ed-btn ed-btn--primary"
        disabled={view.busy}
        onClick={() => onPublish(false)}
      >
        {view.busy ? '여는 중…' : '공개하기'}
      </button>
      {view.siteUrl ? (
        <a href={view.siteUrl} target="_blank" rel="noopener noreferrer">
          공개 사이트 보기
        </a>
      ) : null}
      {need === 'login' ? (
        <div role="group" aria-label="로그인하고 공개하기">
          {message ? <p className="bd-msg">{message}</p> : null}
          <a className="ed-btn" href={loginUrls[0] ?? '/auth/kakao/start'}>
            카카오로 계속하기
          </a>
          <a className="ed-btn" href={loginUrls[1] ?? '/auth/google/start'}>
            구글로 계속하기
          </a>
        </div>
      ) : null}
      {need === 'confirm' ? (
        <div>
          <p className="bd-msg">{message}</p>
          <button type="button" className="ed-btn" disabled={view.busy} onClick={() => onPublish(true)}>
            그대로 공개
          </button>
        </div>
      ) : null}
      {need === 'blocked' ? <p className="bd-msg bd-msg--error">{message}</p> : null}
    </div>
  );
}
