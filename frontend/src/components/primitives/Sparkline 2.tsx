/**
 * Sparkline — a 72×20 whisper of the scope. Same transient-subscribe rAF
 * pattern as ReadingScope (no React re-render per sample); 1px ion-blue
 * polyline, alert where the host judged a value implausible. No grid, no
 * glow — the rail hints, the theater shows.
 */

import { useEffect, useRef } from 'react';
import { useStore } from '../../state/store';

export interface SparklineProps {
  slug: string;
  width?: number;
  height?: number;
}

function draw(canvas: HTMLCanvasElement, slug: string, w: number, h: number): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr;
    canvas.height = h * dpr;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const ring = useStore.getState().readings.bySlug[slug];
  if (!ring || ring.length < 2) return;

  const cs = getComputedStyle(canvas);
  const hum = cs.getPropertyValue('--ion-dim').trim() || '#3a72a8';
  const alert = cs.getPropertyValue('--alert').trim() || '#ff5d4d';

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

  const n = ring.length;
  ctx.lineWidth = 1;
  ctx.strokeStyle = hum;
  ctx.beginPath();
  let anyBad = false;
  ring.forEach((pt, i) => {
    const x = (i / (n - 1)) * (w - 2) + 1;
    const y = h - 2 - ((pt.v - min) / (max - min)) * (h - 4);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
    if (!pt.plausible) anyBad = true;
  });
  ctx.stroke();

  if (anyBad) {
    ctx.strokeStyle = alert;
    ctx.beginPath();
    let px = 0;
    let py = 0;
    let prevBad = false;
    ring.forEach((pt, i) => {
      const x = (i / (n - 1)) * (w - 2) + 1;
      const y = h - 2 - ((pt.v - min) / (max - min)) * (h - 4);
      if (i > 0 && (!pt.plausible || prevBad)) {
        ctx.moveTo(px, py);
        ctx.lineTo(x, y);
      }
      prevBad = !pt.plausible;
      px = x;
      py = y;
    });
    ctx.stroke();
  }
}

export function Sparkline({ slug, width = 72, height = 20 }: SparklineProps) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let raf = 0;
    let lastDrawn = -1;
    let dirty = true;
    const unsubscribe = useStore.subscribe((state) => {
      if ((state.readings.version[slug] ?? 0) !== lastDrawn) dirty = true;
    });
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (!dirty) return;
      dirty = false;
      lastDrawn = useStore.getState().readings.version[slug] ?? 0;
      draw(canvas, slug, width, height);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      unsubscribe();
    };
  }, [slug, width, height]);

  return (
    <canvas
      ref={ref}
      className="card__spark"
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}
