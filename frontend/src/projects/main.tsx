import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import ProjectsPage from './ProjectsPage';
import '../styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ProjectsPage />
  </StrictMode>,
);
