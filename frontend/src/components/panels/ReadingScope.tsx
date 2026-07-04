/**
 * ReadingScope — hand-rolled canvas oscilloscope. A rAF loop redraws only
 * when readings.version[slug] moves, read TRANSIENTLY via store.subscribe /
 * getState() — no React re-render per sample ever flows through here.
 * Phosphor line on a hairline grid; no chart lib.
 */

import { useEffect, useRef } from 'react';
import { useStore } from '../../state/store';

export interface ReadingScopeProps {
  slug: string;
  unit?: string | undefined;
  paused?: boolean | undefined;
}

function cssVar(cs: CSSStyleDeclaration, name: string, fallback: string): string {
  const v = cs.getPropertyValue(name).trim();
  return v || fallback;
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
  const bg = cssVar(cs, '--bg-void', '#0a0b0d');
  const grid = cssVar(cs, '--line', 'rgb(255 255 255 / 0.07)');
  const phosphor = cssVar(cs, '--phosphor', '#3dffa0');
  const glow = cssVar(cs, '--phosphor-glow', 'rgb(61 255 160 / 0.35)');
  const muted = cssVar(cs, '--text-muted', '#7c8591');

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
    ctx.font = '11px ui-monospace, monospace';
    ctx.fillText('no signal', 12, h / 2);
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

  // phosphor trace (alloc-free walk of the ring)
  const n = ring.length;
  ctx.strokeStyle = phosphor;
  ctx.lineWidth = 1.5;
  ctx.shadowColor = glow;
  ctx.shadowBlur = 8;
  ctx.beginPath();
  ring.forEach((pt, i) => {
    const x = (i / (n - 1)) * w;
    const y = h - ((pt.v - min) / (max - min)) * h;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.shadowBlur = 0;

  // last-value readout
  const last = ring.last;
  if (last) {
    ctx.fillStyle = phosphor;
    ctx.font = '11px ui-monospace, monospace';
    ctx.fillText(String(last.v), w - 64, 14);
  }
}

export function ReadingScope({ slug, unit, paused = false }: ReadingScopeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

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
      <div className="scope__label machine">
        {slug}
        {unit ? ` · ${unit}` : ''}
        {paused ? ' · paused' : ''}
      </div>
    </div>
  );
}
