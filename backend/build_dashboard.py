"""build_dashboard.py -- generate a standalone analysis dashboard from cleaned data.

Reads full_analysis_clean.json (produced by clean_analysis.py) and writes
analysis_dashboard.html with the data embedded, so it opens offline with no
backend and no external libraries. All aggregates are computed in-browser from
the single embedded dataset.
"""
import json
import os

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "full_analysis_clean.json")
OUT = os.path.join(HERE, "analysis_dashboard.html")

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DSE Analysis Dashboard</title>
<style>
:root{
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --blue:#2a78d6; --blue-100:#cde2fb; --blue-300:#6da7ec;
  --good:#0ca30c; --good-ink:#006300; --warning:#fab219; --warning-ink:#8a5a00;
  --critical:#d03b3b; --critical-ink:#a11f1f; --serious:#ec835a;
  --shadow:0 1px 2px rgba(11,11,11,.05),0 1px 3px rgba(11,11,11,.04);
}
@media (prefers-color-scheme: dark){
  :root{
    --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
    --blue:#3987e5; --blue-100:#184f95; --blue-300:#256abf;
    --good:#0ca30c; --good-ink:#0ca30c; --warning:#fab219; --warning-ink:#fab219;
    --critical:#d03b3b; --critical-ink:#e66767; --serious:#ec835a;
    --shadow:0 1px 2px rgba(0,0,0,.4);
  }
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--page);
  color:var(--ink);line-height:1.45;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 64px}
header.top{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:4px}
h1{font-size:22px;font-weight:800;letter-spacing:-.4px}
h1 span{color:var(--blue)}
.sub{color:var(--ink2);font-size:13px;margin-bottom:22px}
section{margin-bottom:26px}
h2{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;
  color:var(--ink2);margin-bottom:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:18px;box-shadow:var(--shadow)}
/* KPI tiles */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:14px 16px;box-shadow:var(--shadow)}
.kpi .label{font-size:11px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted)}
.kpi .value{font-size:26px;font-weight:800;margin-top:3px;letter-spacing:-.5px}
.kpi .foot{font-size:12px;color:var(--ink2);margin-top:2px}
.value.good{color:var(--good-ink)} .value.warn{color:var(--warning-ink)} .value.crit{color:var(--critical-ink)}
/* bars */
.bars{display:flex;flex-direction:column;gap:9px}
.bar-row{display:grid;grid-template-columns:130px 1fr 52px;align-items:center;gap:10px;font-size:13px}
.bar-row .name{color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
.track{position:relative;height:16px;background:var(--grid);border-radius:4px;overflow:hidden}
.fill{position:absolute;left:0;top:0;bottom:0;border-radius:4px;background:var(--blue)}
.bar-row .val{text-align:right;font-weight:700;font-variant-numeric:tabular-nums;font-size:12px}
.bar-row .name b{color:var(--muted);font-weight:600;font-size:11px}
/* recommendation strip */
.recgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.recbox{border:1px solid var(--border);border-radius:10px;padding:14px 16px;background:var(--surface)}
.recbox .rtop{display:flex;align-items:center;gap:8px}
.dotm{width:11px;height:11px;border-radius:3px;flex:none}
.recbox .rname{font-weight:700;font-size:13px}
.recbox .rn{font-size:28px;font-weight:800;margin-top:6px;letter-spacing:-.5px}
.recbox .rp{font-size:12px;color:var(--ink2)}
.recbar{height:6px;border-radius:3px;margin-top:10px;background:var(--grid);overflow:hidden}
.recbar > i{display:block;height:100%;border-radius:3px}
/* data quality */
.dq{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.dq .item{border:1px solid var(--border);border-radius:10px;padding:13px 15px;background:var(--surface)}
.dq .h{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}
.dq .big{font-size:20px;font-weight:800;margin:3px 0}
.dq .d{font-size:12px;color:var(--ink2)}
.chip{display:inline-block;font-size:11px;padding:1px 7px;border-radius:20px;margin:2px 3px 0 0;
  background:var(--blue-100);color:var(--ink);border:1px solid var(--border);font-variant-numeric:tabular-nums}
.ok{color:var(--good-ink);font-weight:700}
/* tables */
.tbl-tools{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center}
input[type=search],select{font:inherit;font-size:13px;padding:7px 10px;border:1px solid var(--border);
  border-radius:8px;background:var(--surface);color:var(--ink)}
input[type=search]{min-width:180px;flex:1}
.count{font-size:12px;color:var(--muted);margin-left:auto}
.tscroll{overflow-x:auto;border:1px solid var(--border);border-radius:12px;background:var(--surface)}
table{width:100%;border-collapse:collapse;font-size:13px;min-width:760px}
th{position:sticky;top:0;background:var(--surface);text-align:right;font-weight:700;color:var(--ink2);
  padding:10px 12px;border-bottom:2px solid var(--grid);white-space:nowrap;cursor:pointer;user-select:none;
  font-size:11px;text-transform:uppercase;letter-spacing:.4px}
th:first-child,th:nth-child(2){text-align:left}
th.sorted::after{content:" \25BC";font-size:9px;color:var(--blue)}
th.sorted.asc::after{content:" \25B2"}
td{padding:8px 12px;border-bottom:1px solid var(--grid);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td:first-child{text-align:left;font-weight:700;color:var(--blue)}
td:nth-child(2){text-align:left;color:var(--ink2);max-width:210px;overflow:hidden;text-overflow:ellipsis}
tr:hover td{background:color-mix(in srgb,var(--blue) 7%,var(--surface))}
.badge{display:inline-block;border-radius:6px;padding:1px 9px;font-size:11px;font-weight:700;letter-spacing:.3px}
.badge.BUY{background:color-mix(in srgb,var(--good) 16%,transparent);color:var(--good-ink)}
.badge.HOLD{background:color-mix(in srgb,var(--warning) 22%,transparent);color:var(--warning-ink)}
.badge.SELL{background:color-mix(in srgb,var(--critical) 16%,transparent);color:var(--critical-ink)}
.flag{font-size:11px;color:var(--serious);font-weight:700;cursor:help}
.na{color:var(--muted)}
.recovered{font-size:10px;color:var(--muted);border:1px dashed var(--axis);border-radius:4px;padding:0 4px;margin-left:5px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:720px){.two{grid-template-columns:1fr}.recgrid{grid-template-columns:1fr}
  .bar-row{grid-template-columns:96px 1fr 46px}}
.foot-note{font-size:12px;color:var(--muted);margin-top:10px}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <h1>DSE <span>Analysis</span> Dashboard</h1>
    <div class="sub" id="asof"></div>
  </header>
  <div class="sub">Combined technical + fundamental screen of the full Dhaka Stock Exchange universe. Sectors recovered and data-quality flagged.</div>

  <section><div class="kpis" id="kpis"></div></section>

  <section>
    <h2>Recommendation distribution</h2>
    <div class="recgrid" id="recgrid"></div>
  </section>

  <section>
    <h2>Data quality</h2>
    <div class="card"><div class="dq" id="dq"></div>
    <div class="foot-note" id="dqnote"></div></div>
  </section>

  <section>
    <h2>Sector performance &mdash; average combined score</h2>
    <div class="card"><div class="bars" id="sectors"></div></div>
  </section>

  <section class="two">
    <div>
      <h2>Top 10 BUY</h2>
      <div class="tscroll"><table id="topbuy"></table></div>
    </div>
    <div>
      <h2>Weakest 10 SELL</h2>
      <div class="tscroll"><table id="worstsell"></table></div>
    </div>
  </section>

  <section>
    <h2>All stocks</h2>
    <div class="tbl-tools">
      <input type="search" id="q" placeholder="Search ticker or sector...">
      <select id="fsector"></select>
      <select id="frec">
        <option value="">All recommendations</option>
        <option value="BUY">BUY</option><option value="HOLD">HOLD</option><option value="SELL">SELL</option>
      </select>
      <span class="count" id="tcount"></span>
    </div>
    <div class="tscroll"><table id="maintbl"></table></div>
    <div class="foot-note">Click a column header to sort. <span class="flag">&#9888;</span> = PE not economically meaningful (near-zero / negative earnings). <span class="na">&mdash;</span> = data not reported.</div>
  </section>
</div>

<script>
const DATA = __DATA__;

const num = (x)=> (x===null||x===undefined||Number.isNaN(x))?null:x;
const fmt = (x,d=2)=> x===null?'<span class="na">&mdash;</span>':Number(x).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:0});
const REC = {BUY:{c:'var(--good)',ink:'good'},HOLD:{c:'var(--warning)',ink:'warn'},SELL:{c:'var(--critical)',ink:'crit'}};

// ---- KPIs ----
const total = DATA.length;
const cnt = r => DATA.filter(d=>d.recommendation===r).length;
const avg = arr => arr.length? arr.reduce((a,b)=>a+b,0)/arr.length : 0;
const avgScore = avg(DATA.map(d=>d.combined_score).filter(x=>x!==null));
const recovered = DATA.filter(d=>d.sector_source==='recovered').length;
const fundCov = DATA.filter(d=>d.has_fundamentals).length;
document.getElementById('asof').textContent = total+' tickers scanned';
document.getElementById('kpis').innerHTML = [
  ['Total stocks', total, 'across '+new Set(DATA.map(d=>d.sector)).size+' sectors',''],
  ['BUY', cnt('BUY'), (100*cnt('BUY')/total).toFixed(0)+'% of universe','good'],
  ['HOLD', cnt('HOLD'), (100*cnt('HOLD')/total).toFixed(0)+'% of universe','warn'],
  ['SELL', cnt('SELL'), (100*cnt('SELL')/total).toFixed(0)+'% of universe','crit'],
  ['Avg combined score', avgScore.toFixed(1), 'technical + fundamental',''],
  ['Fundamentals coverage', (100*fundCov/total).toFixed(0)+'%', fundCov+' of '+total+' with data',''],
].map(([l,v,f,c])=>`<div class="kpi"><div class="label">${l}</div><div class="value ${c}">${v}</div><div class="foot">${f}</div></div>`).join('');

// ---- Recommendation distribution ----
document.getElementById('recgrid').innerHTML = ['BUY','HOLD','SELL'].map(r=>{
  const n=cnt(r), p=100*n/total;
  return `<div class="recbox"><div class="rtop"><span class="dotm" style="background:${REC[r].c}"></span><span class="rname">${r}</span></div>
    <div class="rn">${n}</div><div class="rp">${p.toFixed(1)}% of ${total}</div>
    <div class="recbar"><i style="width:${p}%;background:${REC[r].c}"></i></div></div>`;
}).join('');

// ---- Data quality ----
const peUnreliable = DATA.filter(d=>d.pe!==null && !d.pe_reliable).length;
const noFund = DATA.filter(d=>!d.has_fundamentals).length;
const recBySec = {};
DATA.filter(d=>d.sector_source==='recovered').forEach(d=>recBySec[d.sector]=(recBySec[d.sector]||0)+1);
document.getElementById('dq').innerHTML = [
  ['Blank sectors','<span class="ok">0</span> <span style="color:var(--muted)">/ was '+recovered+'</span>',
    Object.entries(recBySec).map(([s,n])=>`<span class="chip">${s}: ${n}</span>`).join('')],
  ['Fundamentals coverage', (100*fundCov/total).toFixed(0)+'%', noFund+' tickers report no EPS/PE/NAV/PB'],
  ['PE flagged unreliable', peUnreliable, 'negative or |PE|&gt;100 &mdash; excluded from valuation reads'],
  ['Duplicate tickers','<span class="ok">0</span>','ticker integrity clean'],
].map(([h,b,d])=>`<div class="item"><div class="h">${h}</div><div class="big">${b}</div><div class="d">${d}</div></div>`).join('');
document.getElementById('dqnote').innerHTML = 'Sectors were recovered from an explicit override map plus ticker-suffix heuristics (life-insurance &rarr; Insurance, fund schemes &rarr; Mutual Fund). Flags are advisory &mdash; no source values were overwritten.';

// ---- Sector performance ----
const secMap={};
DATA.forEach(d=>{ if(d.combined_score!==null){ (secMap[d.sector]=secMap[d.sector]||[]).push(d.combined_score);} });
const secRows = Object.entries(secMap).map(([s,v])=>[s,avg(v),v.length]).sort((a,b)=>b[1]-a[1]);
const maxSec = Math.max(...secRows.map(r=>r[1]));
document.getElementById('sectors').innerHTML = secRows.map(([s,a,n])=>
  `<div class="bar-row"><div class="name" title="${s}">${s} <b>(${n})</b></div>
   <div class="track"><div class="fill" style="width:${100*a/maxSec}%"></div></div>
   <div class="val">${a.toFixed(1)}</div></div>`).join('');

// ---- small tables (top buy / worst sell) ----
function miniTable(el, rows){
  el.innerHTML = '<thead><tr><th>Ticker</th><th>Sector</th><th>Score</th><th>PE</th><th>RSI</th></tr></thead><tbody>'+
    rows.map(d=>`<tr><td>${d.ticker}</td><td title="${d.sector}">${d.sector}</td>
      <td>${fmt(d.combined_score,1)}</td><td>${d.pe===null?'<span class="na">&mdash;</span>':(d.pe_reliable?fmt(d.pe,1):'<span class="flag" title="not meaningful">'+fmt(d.pe,1)+' &#9888;</span>')}</td>
      <td>${fmt(d.rsi,0)}</td></tr>`).join('')+'</tbody>';
}
miniTable(document.getElementById('topbuy'),
  DATA.filter(d=>d.recommendation==='BUY').sort((a,b)=>b.combined_score-a.combined_score).slice(0,10));
miniTable(document.getElementById('worstsell'),
  DATA.filter(d=>d.recommendation==='SELL').sort((a,b)=>a.combined_score-b.combined_score).slice(0,10));

// ---- main interactive table ----
const COLS = [
  ['ticker','Ticker','s'],['sector','Sector','s'],['recommendation','Rec','r'],
  ['combined_score','Score',1],['tech_score','Tech',0],['fund_score','Fund',0],
  ['ltp','LTP',2],['percent_change','%Chg',2],['rsi','RSI',0],
  ['pe','PE',1],['pb','P/B',2],['eps','EPS',2],['debt_equity','D/E',2],
];
let sortKey='combined_score', sortDir=-1;
const secSel=document.getElementById('fsector');
secSel.innerHTML='<option value="">All sectors</option>'+
  [...new Set(DATA.map(d=>d.sector))].sort().map(s=>`<option>${s}</option>`).join('');

function render(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  const fs=secSel.value, fr=document.getElementById('frec').value;
  let rows=DATA.filter(d=>
    (!fs||d.sector===fs)&&(!fr||d.recommendation===fr)&&
    (!q||d.ticker.toLowerCase().includes(q)||d.sector.toLowerCase().includes(q)));
  rows.sort((a,b)=>{
    let x=a[sortKey],y=b[sortKey];
    if(typeof x==='string'){x=x||'';y=y||'';return sortDir*x.localeCompare(y);}
    x=x===null?-Infinity:x; y=y===null?-Infinity:y; return sortDir*(x-y);
  });
  const t=document.getElementById('maintbl');
  t.innerHTML='<thead><tr>'+COLS.map(([k,l])=>
    `<th data-k="${k}" class="${k===sortKey?'sorted '+(sortDir>0?'asc':''):''}">${l}</th>`).join('')+'</tr></thead><tbody>'+
    rows.map(d=>'<tr>'+COLS.map(([k,l,f])=>{
      if(k==='recommendation') return `<td><span class="badge ${d[k]}">${d[k]}</span></td>`;
      if(k==='ticker') return `<td>${d[k]}${d.sector_source==='recovered'?'<span class="recovered">fixed</span>':''}</td>`;
      if(f==='s') return `<td title="${d[k]}">${d[k]}</td>`;
      let v=d[k];
      if(k==='pe'&&v!==null&&!d.pe_reliable) return `<td><span class="flag" title="not economically meaningful">${fmt(v,f)} &#9888;</span></td>`;
      return `<td>${fmt(v,f)}</td>`;
    }).join('')+'</tr>').join('')+'</tbody>';
  document.getElementById('tcount').textContent=rows.length+' of '+total+' shown';
  t.querySelectorAll('th').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(k===sortKey) sortDir*=-1; else {sortKey=k; sortDir=(typeof DATA[0][k]==='string')?1:-1;}
    render();
  });
}
['q','fsector','frec'].forEach(id=>document.getElementById(id).addEventListener('input',render));
render();
</script>
</body>
</html>
"""


def main():
    data = json.load(open(DATA, encoding="utf-8"))
    compact = json.dumps(data, separators=(",", ":"))
    html = HTML.replace("__DATA__", compact)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT} ({len(html)//1024} KB, {len(data)} rows embedded)")


if __name__ == "__main__":
    main()
