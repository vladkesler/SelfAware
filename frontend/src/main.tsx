/**
 * Entry point — router only. "/" is the landing void; "/app" is the console.
 * Transport wiring lives in hooks/useTransport (mounted by Console).
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Landing from './routes/Landing';
import Console from './routes/Console';
import '@fontsource/inter/300.css';
import '@fontsource/inter/400.css';
import '@fontsource/inter/600.css';
import '@fontsource/inter/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
import './styles/tokens.css';
import './styles/base.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<Console />} />
        <Route path="/about" element={<Navigate to="/#about" replace />} />
        <Route path="/team" element={<Navigate to="/#team" replace />} />
        <Route path="/industry" element={<Navigate to="/#industry" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
