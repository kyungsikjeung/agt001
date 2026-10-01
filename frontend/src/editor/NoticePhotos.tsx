// 공지 사진 고르기 (NOTICE_PHOTO_CONTRACT §3-1).
// 사진은 notice 태그로 올려 사이트 첫 화면·공간 사진에 섞이지 않는다. 빼기는 목록에서만(파일은 그대로).
import { useState } from 'react';
import { readMemberId, uploadPhoto } from './cardApi';

export const NOTICE_PHOTO_MAX = 5;

interface NoticePhotosProps {
  roomId: string;
  photos: string[];
  onChange: (photos: string[]) => void;
}

export default function NoticePhotos({ roomId, photos, onChange }: NoticePhotosProps) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  async function add(files: FileList | null) {
    if (!files || files.length === 0 || busy) return;
    const room = NOTICE_PHOTO_MAX - photos.length;
    if (room <= 0) {
      setMsg(`공지 사진은 ${NOTICE_PHOTO_MAX}장까지예요.`);
      return;
    }
    const picked = Array.from(files).slice(0, room);
    setBusy(true);
    setMsg(files.length > room ? `공지 사진은 ${NOTICE_PHOTO_MAX}장까지라 ${room}장만 올려요.` : '');
    const next = [...photos];
    try {
      for (const f of picked) {
        const { url } = await uploadPhoto(roomId, readMemberId(), f, 'notice');
        if (url) next.push(url);
      }
    } catch {
      setMsg('사진을 올리지 못했어요. 잠시 뒤 다시 해 주세요.');
    } finally {
      onChange(next);
      setBusy(false);
    }
  }

  return (
    <div className="ed-notice-photos">
      <ul className="ed-notice-photos__list" aria-label="공지 사진">
        {photos.map((url, i) => (
          <li key={url}>
            <img src={url} alt={`공지 사진 ${i + 1}`} width={72} height={72} />
            <button type="button" className="ed-btn" onClick={() => onChange(photos.filter((u) => u !== url))}>
              빼기
            </button>
          </li>
        ))}
      </ul>
      {photos.length < NOTICE_PHOTO_MAX ? (
        <label className="ed-file">
          {busy ? '올리는 중…' : `사진 추가 (${photos.length}/${NOTICE_PHOTO_MAX})`}
          <input
            type="file"
            accept="image/*"
            multiple
            disabled={busy}
            onChange={(e) => {
              void add(e.target.files);
              e.target.value = '';
            }}
          />
        </label>
      ) : null}
      {msg ? <p role="status">{msg}</p> : null}
    </div>
  );
}
