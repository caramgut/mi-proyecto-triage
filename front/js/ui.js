export function escapeHtml(v){return String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));}
export function formatDate(v){if(!v)return"—";const d=new Date(v);if(Number.isNaN(d.getTime()))return escapeHtml(v);return new Intl.DateTimeFormat("es-CO",{dateStyle:"medium",timeStyle:"short",timeZone:"America/Bogota"}).format(d)}
export function formatDateOnly(v){if(!v)return"—";const d=new Date(`${String(v).slice(0,10)}T12:00:00`);return Number.isNaN(d.getTime())?escapeHtml(v):new Intl.DateTimeFormat("es-CO",{dateStyle:"medium"}).format(d)}
export function showToast(message,type="info",ms=3500){const c=document.getElementById("toast-container");if(!c)return;const t=document.createElement("div");t.className=`toast ${type}`;t.textContent=message;c.appendChild(t);setTimeout(()=>t.remove(),ms)}
export function initialsFromName(nombres="",apellidos=""){return `${nombres.trim()[0]||""}${apellidos.trim()[0]||""}`.toUpperCase()||"P"}
export function triageBadge(n){return n?`<span class="badge triage-${n}">Triage ${n}</span>`:'<span class="badge">Sin triage</span>'}
export function modal(title,content){const b=document.createElement("div");b.className="modal-backdrop";b.innerHTML=`<div class="modal"><div class="modal-head"><h2>${escapeHtml(title)}</h2><button class="btn btn-ghost" data-close type="button">✕</button></div><div>${content}</div></div>`;document.body.appendChild(b);const close=()=>b.remove();b.querySelector("[data-close]").onclick=close;b.addEventListener("click",e=>{if(e.target===b)close()});return {element:b,close};}


export function enhanceTables(container){
  if(!container)return;
  const filterable=new Set(["Rol","Estado","Origen","Servicio","Acción","Tabla","Especialidad","Triage","Resultado","Evento"]);
  container.querySelectorAll("table.data-table").forEach((table,idx)=>{
    if(table.dataset.enhanced==="1")return;
    table.dataset.enhanced="1";
    const headers=[...table.querySelectorAll("thead th")].map(th=>th.textContent.trim());
    const wrap=table.closest(".table-wrap");
    if(!wrap)return;
    const bar=document.createElement("div");
    bar.className="table-filters";
    bar.innerHTML=`<label class="table-search"><span>Buscar</span><input type="search" placeholder="Buscar en la tabla…" aria-label="Buscar en tabla"></label>`;
    const search=bar.querySelector("input");
    const selects=[];
    headers.forEach((h,i)=>{
      if(!filterable.has(h))return;
      const values=[...new Set([...table.querySelectorAll("tbody tr")].map(tr=>tr.children[i]?.textContent.trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"es"));
      if(values.length<2||values.length>30)return;
      const label=document.createElement("label");
      label.className="table-select-filter";
      label.innerHTML=`<span>${escapeHtml(h)}</span><select aria-label="Filtrar por ${escapeHtml(h)}"><option value="">Todos</option>${values.map(v=>`<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("")}</select>`;
      bar.appendChild(label);
      selects.push([i,label.querySelector("select")]);
    });
    const count=document.createElement("span");
    count.className="table-filter-count muted small-text";
    bar.appendChild(count);
    wrap.parentNode.insertBefore(bar,wrap);
    const apply=()=>{
      const q=search.value.trim().toLowerCase();let visible=0;
      table.querySelectorAll("tbody tr").forEach(tr=>{
        const text=tr.textContent.toLowerCase();
        const okText=!q||text.includes(q);
        const okSelect=selects.every(([i,sel])=>!sel.value||tr.children[i]?.textContent.trim()===sel.value);
        const ok=okText&&okSelect;tr.hidden=!ok;if(ok)visible++;
      });
      count.textContent=`${visible} resultado${visible===1?"":"s"}`;
    };
    search.addEventListener("input",apply);
    selects.forEach(([,sel])=>sel.addEventListener("change",apply));
    apply();
  });
}
