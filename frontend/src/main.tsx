/**
 * Entry point — router only. "/" is the landing void; "/app" is the console.
 * Transport wiring lives in hooks/useTransport (mounted by Console).
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Landing from './routes/Landing';
import Console from './routes/Console';
import './styles/tokens.css';
import './styles/base.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/app" element={<Console />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
