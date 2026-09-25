import type { DesignElement, ElementKind } from "./api";

export const KIND_STYLE: Record<ElementKind, { fill: string; text: string; label: string }> = {
  footpath: { fill: "#d6ccb8", text: "#3f3a2e", label: "Footpath" },
  tree_strip: { fill: "#86c084", text: "#1d3d1c", label: "Trees" },
  cycle_track: { fill: "#79aee0", text: "#12324f", label: "Cycle track" },
  bus_bay: { fill: "#e6a95c", text: "#4a2c06", label: "Bus bay" },
  lane: { fill: "#8e959d", text: "#ffffff", label: "Lane" },
  median: { fill: "#b9dca6", text: "#264015", label: "Median" },
};

const W = 1000; // drawing width in SVG units; 1 unit = row_cm / 1000, so widths are strictly to scale
const H = 150;
const TOP = 34;
const BAR_H = 64;

type Props = { elements: DesignElement[]; rowCm: number; title?: string };

/** Road cut side to side, drawn to scale: every rectangle's width is exactly its share of the right-of-way. */
export default function CrossSection({ elements, rowCm, title }: Props) {
  let x = 0;
  const boxes = elements.map((e, i) => {
    const w = (e.width_cm / rowCm) * W;
    const box = { e, i, x, w };
    x += w;
    return box;
  });
  const kinds = [...new Set(elements.map((e) => e.kind))];
  const summary = elements.map((e) => `${e.label} ${e.width_m} m`).join(", ");

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title ?? "Road"} cross-section, ${rowCm / 100} m: ${summary}`}
        className="w-full" preserveAspectRatio="xMidYMid meet">
        {boxes.map(({ e, i, x: bx, w }) => (
          <g key={i}>
            <rect data-testid="element" data-kind={e.kind} data-width-cm={e.width_cm} x={bx} y={TOP} width={w} height={BAR_H}
              fill={KIND_STYLE[e.kind].fill} stroke="#ffffff" strokeWidth={1.5} />
            {w >= 44 && (
              <text x={bx + w / 2} y={TOP + BAR_H / 2 + 6} textAnchor="middle" fontSize={w >= 90 ? 20 : 15}
                fill={KIND_STYLE[e.kind].text} fontWeight={600}>
                {w >= 90 ? e.label : e.label.slice(0, 4)}
              </text>
            )}
            {w >= 26 && (
              <text x={bx + w / 2} y={TOP + BAR_H + 22} textAnchor="middle" fontSize={17} fill="#475569">
                {e.width_m}
              </text>
            )}
          </g>
        ))}
        {/* property lines and the overall dimension */}
        <line x1={0} y1={TOP - 12} x2={0} y2={TOP + BAR_H + 6} stroke="#334155" strokeWidth={2} />
        <line x1={W} y1={TOP - 12} x2={W} y2={TOP + BAR_H + 6} stroke="#334155" strokeWidth={2} />
        <line x1={0} y1={TOP - 8} x2={W} y2={TOP - 8} stroke="#334155" strokeWidth={1} />
        <text x={W / 2} y={TOP - 14} textAnchor="middle" fontSize={19} fill="#334155" fontWeight={600}>
          {rowCm / 100} m right-of-way
        </text>
        <text x={0} y={H - 6} fontSize={15} fill="#64748b">widths in metres</text>
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600" aria-label="Legend">
        {kinds.map((k) => (
          <li key={k} className="flex items-center gap-1">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: KIND_STYLE[k].fill }} />
            {KIND_STYLE[k].label}
          </li>
        ))}
      </ul>
    </div>
  );
}
