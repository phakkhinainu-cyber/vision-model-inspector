import { useState } from "react";

// กราฟแท่งแบบ SVG (ไม่ใช้ไลบรารีภายนอก): แท่งบางไม่เกิน 24px ปลายมน 4px ฐานตรง, ช่องว่าง 2px ระหว่างแท่ง,
// เส้นกริดบาง, legend เมื่อมี ≥2 ชุดข้อมูล, tooltip เมื่อชี้ และสลับดูเป็นตารางได้
export interface Series { key: string; label: string; color: string }

function niceMax(v: number): number {
  if (v <= 4) return 4;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function colPath(x: number, y: number, w: number, h: number, r = 4): string {
  if (h <= 0) return "";
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

export function GroupedColumns({ data, series, labelKey, title, tickEvery = 1, height = 240 }: {
  data: Record<string, number | string>[]; series: Series[]; labelKey: string; title: string; tickEvery?: number; height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const W = 960, H = height, padL = 36, padB = 26, padT = 10;
  const max = niceMax(Math.max(1, ...data.flatMap((d) => series.map((s) => Number(d[s.key]) || 0))));
  const plotW = W - padL - 8, plotH = H - padB - padT;
  const band = plotW / Math.max(1, data.length);
  const gap = 2;
  const barW = Math.max(2, Math.min(24, (band * 0.72 - gap * (series.length - 1)) / series.length));
  const groupW = barW * series.length + gap * (series.length - 1);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(max * t));
  const y = (v: number) => padT + plotH - (v / max) * plotH;
  return (
    <figure className="chart">
      <figcaption className="chart-head">
        <span className="chart-title">{title}</span>
        <span className="legend">{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</span>
        <button className="btn btn-ghost btn-sm" onClick={() => setTable(!table)}>{table ? "ดูเป็นกราฟ" : "ดูเป็นตาราง"}</button>
      </figcaption>
      {table ? (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>{labelKey === "hour" ? "ชั่วโมง" : "วันที่"}</th>{series.map((s) => <th key={s.key}>{s.label}</th>)}</tr></thead>
          <tbody>{data.map((d, i) => <tr key={i}><td>{String(d.label)}</td>{series.map((s) => <td key={s.key}>{Number(d[s.key]) || 0}</td>)}</tr>)}</tbody>
        </table></div>
      ) : (
        <div className="chart-wrap" onMouseLeave={() => setHover(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={padL} x2={W - 8} y1={y(t)} y2={y(t)} className="grid" />
                <text x={padL - 6} y={y(t) + 4} textAnchor="end" className="tick">{t >= 1000 ? `${t / 1000}K` : t}</text>
              </g>
            ))}
            {data.map((d, i) => {
              const gx = padL + i * band + (band - groupW) / 2;
              return (
                <g key={i}>
                  {hover === i && <rect x={padL + i * band} y={padT} width={band} height={plotH} className="hover-band" />}
                  {series.map((s, j) => {
                    const v = Number(d[s.key]) || 0;
                    return <path key={s.key} d={colPath(gx + j * (barW + gap), y(v), barW, padT + plotH - y(v))} fill={s.color} />;
                  })}
                  {i % tickEvery === 0 && <text x={padL + i * band + band / 2} y={H - 8} textAnchor="middle" className="tick">{String(d.short ?? d.label)}</text>}
                  <rect x={padL + i * band} y={padT} width={band} height={plotH + padB} fill="transparent"
                    onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} tabIndex={-1} />
                </g>
              );
            })}
            <line x1={padL} x2={W - 8} y1={padT + plotH} y2={padT + plotH} className="axis" />
          </svg>
          {hover !== null && data[hover] && (
            <div className="tooltip" style={{ left: `${((padL + hover * band + band / 2) / W) * 100}%` }}>
              <b>{String(data[hover].label)}</b>
              {series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label} {Number(data[hover][s.key]) || 0}</span>)}
            </div>
          )}
        </div>
      )}
    </figure>
  );
}

export function HBars({ items, color, title }: { items: { label: string; value: number }[]; color: string; title: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <figure className="chart">
      <figcaption className="chart-head"><span className="chart-title">{title}</span></figcaption>
      {items.length === 0 ? <p className="muted small">ไม่มีข้อมูล</p> : (
        <ul className="hbars">
          {items.map((i) => (
            <li key={i.label} title={`${i.label}: ${i.value}`}>
              <span className="hb-label">{i.label}</span>
              <span className="hb-track"><span className="hb-bar" style={{ width: `${(i.value / max) * 100}%`, background: color }} /></span>
              <span className="hb-val">{i.value.toLocaleString("th-TH")}</span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
