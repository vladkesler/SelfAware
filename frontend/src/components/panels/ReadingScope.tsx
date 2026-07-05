/**
 * ReadingScope — hand-rolled canvas oscilloscope. A rAF loop redraws only
 * when readings.version[slug] moves, read TRANSIENTLY via store.subscribe /
 * getState() — no React re-render per sample flows through the canvas.
 * Phosphor trace on a hairline grid; stretches the host judged implausible
 * draw in the reserved alert. The hero readout is an HTML overlay (crisp,
 * projector-size) that re-renders at signal rate — cheap for one number.
 */

import { useEffect, useRef } from 'react';
import { useStore } from '../../state/store';

export interface ReadingScopeProps {
  slug: string;
  unit?: string | undefined;
  paused?: boolean | undefined;
  /** Show the big HTML last-value readout (center-stage mode). */
  hero?: boolean | undefined;
}

function cssVar(cs: CSSStyleDeclaration, name: string, fallback: string): string {
  const v = cs.getPropertyValue(name).trim();
  return v || fallback;
}

function formatValue(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return Math.abs(v) >= 100 ? String(Math.round(v)) : v.toFixed(1);
}

function draw(canvas: HTMLCanvasElement, slug: string): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 320;
  const h = canvas.clientHeight || 140;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const cs = getComputedStyle(canvas);
  const bg = cssVar(cs, '--bg-void', '#0f1216');
  const grid = cssVar(cs, '--line', 'rgb(210 230 255 / 0.09)');
  const signal = cssVar(cs, '--live', '#ff8a3d');
  const glow = cssVar(cs, '--live-glow', 'rgb(255 138 61 / 0.4)');
  const alert = cssVar(cs, '--alert', '#ff5d4d');
  const muted = cssVar(cs, '--text-dim', '#96a2b0');

  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);

  // grid
  ctx.strokeStyle = grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = 0.5; x < w; x += 32) {
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
  }
  for (let y = 0.5; y < h; y += 24) {
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
  }
  ctx.stroke();

  const ring = useStore.getState().readings.bySlug[slug];
  if (!ring || ring.length < 2) {
    ctx.fillStyle = muted;
    ctx.font = '13px ui-monospace, monospace';
    ctx.fillText('no signal yet', 12, h / 2);
    return;
  }

  // autoscale with headroom
  let min = Infinity;
  let max = -Infinity;
  ring.forEach((pt) => {
    if (pt.v < min) min = pt.v;
    if (pt.v > max) max = pt.v;
  });
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.15;
  min -= pad;
  max += pad;

  const n = ring.length;
  const px = (i: number) => (i / (n - 1)) * w;
  const py = (v: number) => h - ((v - min) / (max - min)) * h;

  // signal trace (alloc-free walk of the ring)
  ctx.strokeStyle = signal;
  ctx.lineWidth = 1.5;
  ctx.shadowColor = glow;
  ctx.shadowBlur = 12;
  ctx.beginPath();
  ring.forEach((pt, i) => {
    if (i === 0) ctx.moveTo(px(i), py(pt.v));
    else ctx.lineTo(px(i), py(pt.v));
  });
  ctx.stroke();
  ctx.shadowBlur = 0;

  // implausible stretches re-draw in the reserved alert, over the signal
  ctx.strokeStyle = alert;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  let prevBad = false;
  let prevX = 0;
  let prevY = 0;
  ring.forEach((pt, i) => {
    const x = px(i);
    const y = py(pt.v);
    if (i > 0 && (!pt.plausible || prevBad)) {
      ctx.moveTo(prevX, prevY);
      ctx.lineTo(x, y);
    }
    prevBad = !pt.plausible;
    prevX = x;
    prevY = y;
  });
  ctx.stroke();
}

export function ReadingScope({ slug, unit, paused = false, hero = false }: ReadingScopeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Hero readout: re-render this small component at signal rate (~1 Hz).
  const version = useStore((s) => (hero ? (s.readings.version[slug] ?? 0) : 0));
  void version;
  const last = hero ? useStore.getState().readings.bySlug[slug]?.last : undefined;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let raf = 0;
    let lastDrawn = -1;
    let dirty = true; // draw once on mount

    // Transient subscribe: mark dirty, let the rAF loop pace the redraws.
    const unsubscribe = useStore.subscribe((state) => {
      if ((state.readings.version[slug] ?? 0) !== lastDrawn) dirty = true;
    });

    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (paused || !dirty) return;
      dirty = false;
      lastDrawn = useStore.getState().readings.version[slug] ?? 0;
      draw(canvas, slug);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      unsubscribe();
    };
  }, [slug, paused]);

  return (
    <div className="scope">
      <canvas ref={canvasRef} className="scope__canvas" />
      {hero && last ? (
        <div className="scope__hero">
          <span className="scope__hero-value">{formatValue(last.v)}</span>
          {unit ? <span className="scope__hero-unit">{unit}</span> : null}
        </div>
      ) : null}
      <div className="scope__label">
        {slug}
        {unit ? ` · ${unit}` : ''}
        {paused ? ' · paused' : ''}
      </div>
    </div>
  );
}
