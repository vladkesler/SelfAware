/**
 * Entry point. PR4 replaces this with the router (Landing at /, Console at
 * /app) — this placeholder only proves the toolchain and shows the contract
 * is wired.
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { PROTOCOL_VERSION } from './types/events';

function Placeholder() {
  return (
    <main style={{ fontFamily: 'ui-monospace, monospace', padding: '4rem', background: '#0a0b0d', color: '#3dffa0', minHeight: '100vh' }}>
      <h1 style={{ fontSize: '1rem', fontWeight: 400 }}>
        &gt; selfaware — protocol v{PROTOCOL_VERSION} — theater arrives in PR4_
      </h1>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Placeholder />
  </StrictMode>,
);
