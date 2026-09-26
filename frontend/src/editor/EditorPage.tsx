// 직접 편집 화면 갈림길. ?room=<id>이 있으면 실제 카드(CardEditor), 없으면 목업(MockEditor).
// 불러오기 실패도 CardEditor 안에서 목업으로 돌아간다.
import { useMemo } from 'react';
import CardEditor from './CardEditor';
import MockEditor from './MockEditor';
import { readRoomId } from './cardApi';

interface EditorPageProps {
  roomId?: string | null;
}

export default function EditorPage({ roomId }: EditorPageProps) {
  const resolved = useMemo(() => roomId ?? readRoomId(), [roomId]);
  if (!resolved) return <MockEditor />;
  return <CardEditor roomId={resolved} />;
}
