import { useEffect, useRef } from "react";
import { projectLocal } from "./geo";
import type { DesignElement } from "./api";

const COL_GOOD = [54, 226, 196];
const COL_WARN = [240, 169, 60];
const COL_CRIT = [239, 83, 80];
const FOOTPATH_COLOR = "#b8a888";
const CYCLE_TRACK_COLOR = "#5f93c9";

function lerp(a: number[], b: number[], t: number): string {
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * t)},${Math.round(a[1] + (b[1] - a[1]) * t)},${Math.round(a[2] + (b[2] - a[2]) * t)})`;
}
function congColor(vc: number): string {
  const t = Math.max(0, Math.min(1, vc));
  return t < 0.5 ? lerp(COL_GOOD, COL_WARN, t / 0.5) : lerp(COL_WARN, COL_CRIT, (t - 0.5) / 0.5);
}
function drawTree(ctx: CanvasRenderingContext2D, x: number, y: number, s: number) {
  ctx.fillStyle = "#5a3a26";
  ctx.fillRect(x - s * 0.06, y - s * 0.1, s * 0.12, s * 0.22);
  ctx.fillStyle = "#2e8f6e";
  ctx.beginPath(); ctx.arc(x, y - s * 0.28, s * 0.26, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#36a87f";
  ctx.beginPath(); ctx.arc(x - s * 0.12, y - s * 0.36, s * 0.17, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(x + s * 0.13, y - s * 0.34, s * 0.15, 0, Math.PI * 2); ctx.fill();
}

type Props = {
  geometry: { type: "LineString"; coordinates: [number, number][] } | null;
  /** This scenario's actual cross-section — drives whether footpath/cycle-track bands and tree
   * icons are drawn, so the map never shows a tree that isn't really there (or hides a footpath
   * that is). */
  elements: DesignElement[];
  /** 0-1+ volume/capacity; null draws a neutral road with no flow (no demand data). */
  vcRatio: number | null;
  label: string;
};

/** A top-down, to-scale flow map of the segment's real alignment. The lane core is coloured by
 * congestion with dots flowing along it; footpath and cycle-track, when this scenario actually
 * has them, are drawn as their own bands either side so "today, no footpath" and "this option,
 * with one" read differently. Plain 2D canvas — no WebGL, so no context-budget concerns the way
 * RoadScene3D has. */
export default function RoadFlowMap({ geometry, elements, vcRatio, label }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const hasFootpath = elements.some((e) => e.kind === "footpath");
  const hasCycleTrack = elements.some((e) => e.kind === "cycle_track");
  const hasTrees = elements.some((e) => e.kind === "tree_strip");

  useEffect(() => {
    const el = container.current;
    if (!el) return;
    if (!geometry || geometry.coordinates.length < 2) return;

    const canvas = document.createElement("canvas");
    el.replaceChildren(canvas);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = el.getBoundingClientRect();
    const w = rect.width || 320, h = rect.height || 180;
    canvas.width = Math.max(1, Math.round(w * dpr));
    canvas.height = Math.max(1, Math.round(h * dpr));
    canvas.style.width = "100%"; canvas.style.height = "100%";
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const local = projectLocal(geometry.coordinates);
    const minX = Math.min(...local.map((p) => p.x)), maxX = Math.max(...local.map((p) => p.x));
    const minY = Math.min(...local.map((p) => p.y)), maxY = Math.max(...local.map((p) => p.y));
    const margin = 26;
    const scale = Math.min((w - margin * 2) / Math.max(maxX - minX, 1), (h - margin * 2) / Math.max(maxY - minY, 1));
    const toScreen = (p: { x: number; y: number }) => ({
      x: margin + (p.x - minX) * scale + (w - margin * 2 - (maxX - minX) * scale) / 2,
      y: margin + (p.y - minY) * scale + (h - margin * 2 - (maxY - minY) * scale) / 2,
    });
    const samples = local.map(toScreen);

    function normalAt(i: number) {
      const a = samples[Math.max(0, i - 1)], b = samples[Math.min(samples.length - 1, i + 1)];
      const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
      return { x: -dy / len, y: dx / len };
    }
    function strokeOffset(offset: number, color: string, width: number) {
      if (!ctx) return;
      ctx.strokeStyle = color; ctx.lineWidth = width;
      ctx.beginPath();
      samples.forEach((p, i) => {
        const n = normalAt(i);
        const x = p.x + n.x * offset, y = p.y + n.y * offset;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();
    }

    const vc = vcRatio ?? 0;
    const treeOffset = hasFootpath ? 16 : 10;
    const footpathOffset = 9, cycleTrackOffset = hasFootpath ? 5.5 : 4;
    const dotsFwd = [0, 0.25, 0.5, 0.75];
    const dotsBack = [0.1, 0.45, 0.8];
    let disposed = false, frame = 0;

    function draw() {
      if (disposed || !ctx) return;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#f8fafc"; ctx.fillRect(0, 0, w, h);
      ctx.lineCap = "round"; ctx.lineJoin = "round";

      if (hasTrees) {
        const step = Math.max(1, Math.round(samples.length / 7));
        for (let i = 0; i < samples.length; i += step) {
          const n = normalAt(i);
          drawTree(ctx, samples[i].x + n.x * treeOffset, samples[i].y + n.y * treeOffset, 15);
          drawTree(ctx, samples[i].x - n.x * treeOffset, samples[i].y - n.y * treeOffset, 15);
        }
      }

      // Casing for the core (lane) band only — footpath/cycle-track bands are drawn as their own
      // thin coloured lines, not part of this dark casing, so they read as separate elements.
      ctx.beginPath();
      samples.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.strokeStyle = "#334155"; ctx.lineWidth = 9; ctx.stroke();
      ctx.strokeStyle = vcRatio == null ? "#94a3b8" : congColor(vc);
      ctx.lineWidth = 5; ctx.stroke();
      ctx.strokeStyle = "rgba(255,255,255,.7)"; ctx.lineWidth = 1; ctx.setLineDash([4, 6]);
      ctx.beginPath();
      samples.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
      ctx.stroke(); ctx.setLineDash([]);

      if (hasCycleTrack) {
        strokeOffset(cycleTrackOffset, CYCLE_TRACK_COLOR, 3);
        strokeOffset(-cycleTrackOffset, CYCLE_TRACK_COLOR, 3);
      }
      if (hasFootpath) {
        strokeOffset(footpathOffset, FOOTPATH_COLOR, 4);
        strokeOffset(-footpathOffset, FOOTPATH_COLOR, 4);
      }

      if (vcRatio != null) {
        const speed = 0.0046 - vc * 0.0032; // more congested -> slower
        const n = samples.length - 1;
        dotsFwd.forEach((t, i) => {
          const idx = Math.max(0, Math.min(n, Math.floor(t * n)));
          const p = samples[idx], nrm = normalAt(idx);
          ctx.fillStyle = "#0f172a";
          ctx.beginPath(); ctx.arc(p.x + nrm.x * 4, p.y + nrm.y * 4, 2.6, 0, Math.PI * 2); ctx.fill();
          dotsFwd[i] = (t + speed) % 1;
        });
        dotsBack.forEach((t, i) => {
          const idx = Math.max(0, Math.min(n, Math.floor((1 - t) * n)));
          const p = samples[idx], nrm = normalAt(idx);
          ctx.fillStyle = "#64748b";
          ctx.beginPath(); ctx.arc(p.x - nrm.x * 4, p.y - nrm.y * 4, 2.3, 0, Math.PI * 2); ctx.fill();
          dotsBack[i] = (t + speed * 0.9) % 1;
        });
      }

      frame = requestAnimationFrame(draw);
    }
    draw();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      el.replaceChildren();
    };
  }, [geometry, vcRatio, hasFootpath, hasCycleTrack, hasTrees]);

  if (!geometry || geometry.coordinates.length < 2) {
    return (
      <div data-testid="road-flow-map-unavailable"
        className="flex h-40 items-center justify-center rounded border border-slate-200 bg-slate-50 text-xs text-slate-500">
        No road geometry to map.
      </div>
    );
  }

  return (
    <div>
      <div ref={container} data-testid="road-flow-map" className="h-40 w-full overflow-hidden rounded border border-slate-200" />
      <p className="mt-1 text-center text-xs text-slate-500">{label}</p>
      <ul className="mt-1 flex flex-wrap justify-center gap-x-3 gap-y-0.5 text-[10px] text-slate-400" aria-label="Legend">
        <li className="flex items-center gap-1"><span className="inline-block h-1.5 w-2.5 rounded-sm" style={{ background: "#64748b" }} />Lane</li>
        {hasCycleTrack && <li className="flex items-center gap-1"><span className="inline-block h-1.5 w-2.5 rounded-sm" style={{ background: CYCLE_TRACK_COLOR }} />Cycle track</li>}
        {hasFootpath && <li className="flex items-center gap-1"><span className="inline-block h-1.5 w-2.5 rounded-sm" style={{ background: FOOTPATH_COLOR }} />Footpath</li>}
        {hasTrees && <li className="flex items-center gap-1"><span className="inline-block h-1.5 w-2.5 rounded-sm" style={{ background: "#2e8f6e" }} />Trees</li>}
      </ul>
    </div>
  );
}
