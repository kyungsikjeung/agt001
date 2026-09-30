import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import BuilderPage from './BuilderPage';
import { readRoomId } from '../editor/cardApi';
import '../styles.css';
import '../editor/editor.css';
import './builder.css';

const roomId = readRoomId();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {roomId ? (
      <BuilderPage roomId={roomId} />
    ) : (
      <div className="bd-page ed-page">
        <main className="bd-main">
          <h1>주소가 맞지 않아요</h1>
          <p>랜딩의 템플릿에서 다시 시작해 주세요.</p>
        </main>
      </div>
    )}
  </StrictMode>,
);
