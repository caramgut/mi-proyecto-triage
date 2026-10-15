// ia.js — Pestaña "Pretriaje IA" de la ficha del paciente (R10, R12).
// El médico pide el análisis, ve la categoría propuesta con su explicación y la
// ACEPTA o la RECHAZA. Solo lo aceptado entra a la historia clínica.
import {apiGet,apiPatch,apiPost} from "./api.js";
import {getCurrentUser} from "./auth.js";
import {escapeHtml,showToast} from "./ui.js";

const CATEGORIA={
  critico:{texto:"Crítico",detalle:"niveles 1-2 · valoración inmediata",clase:"ia-critico"},
  medio:{texto:"Medio",detalle:"nivel 3 · urgente, puede esperar un poco",clase:"ia-medio"},
  no_critico:{texto:"No crítico",detalle:"niveles 4-5 · menos urgente",clase:"ia-no-critico"},
};
const ESTADO={pendiente:"Pendiente de revisión",aprobado:"Aceptado por el clínico",rechazado:"Rechazado por el clínico"};
const MOTIVOS=[["","Sin cambiar"],["cardiovascular","Cardiovascular"],["respiratorio","Respiratorio"],["digestivo","Digestivo"],
  ["neurologico","Neurológico"],["conciencia_paro","Alteración de conciencia / paro"],["fiebre_general","Fiebre / malestar general"],
  ["trauma","Trauma"],["musculoesqueletico","Musculoesquelético"],["genitourinario_gineco","Genitourinario / ginecológico"],
  ["psiquiatrico_sustancias","Psiquiátrico / sustancias"],["piel_alergia","Piel / alergia"],["orl_ojos_dental","Ojos, oídos, boca"],["otros","Otros"]];
const SIGNOS=[["fc","FC","lpm",20,250,1],["fr","FR","rpm",4,80,1],["pas","PAS","mmHg",40,300,1],["pad","PAD","mmHg",20,200,1],
  ["temp_c","Temperatura","°C",30,44,0.1],["spo2","SpO2","%",50,100,1],["dolor_nrs","Dolor","0-10",0,10,1]];

let actual={documento:null,panel:null};

const rol=()=>getCurrentUser()?.rol;
const puedeRevisar=()=>["Medico","Especialista"].includes(rol());
const puedeAnalizar=()=>["Admin","Medico","Especialista"].includes(rol());
const pct=v=>`${Math.round(Number(v)*100)}%`;
const fecha=v=>v?new Date(v).toLocaleString("es-CO",{dateStyle:"medium",timeStyle:"short"}):"—";

export async function renderPanelIA(documento,panel){
  actual={documento:Number(documento),panel};
  panel.innerHTML=`
    <div class="card ia-card">
      <div class="section-head">
        <div><h3>Pretriaje con IA</h3>
          <p class="muted">El modelo propone una categoría; usted la acepta o la rechaza. Solo lo aceptado entra a la historia clínica.</p></div>
        ${puedeAnalizar()?'<button id="ia-analizar" class="btn btn-primary" type="button">Analizar con IA</button>':""}
      </div>
      ${puedeAnalizar()?formularioSignos():""}
    </div>
    <div id="ia-reportes"><div class="card">Cargando reportes…</div></div>`;
  panel.querySelector("#ia-analizar")?.addEventListener("click",()=>analizar(false));
  panel.querySelector("#ia-form")?.addEventListener("submit",e=>{e.preventDefault();analizar(true);});
  await cargarReportes();
}

function formularioSignos(){
  return `<details class="ia-signos"><summary>Registrar signos vitales y analizar</summary>
    <form id="ia-form" class="ia-form">
      ${SIGNOS.map(([k,n,u,min,max,step])=>`<label>${n} <span class="muted">(${u})</span>
        <input name="${k}" type="number" min="${min}" max="${max}" step="${step}"></label>`).join("")}
      <label>Motivo de consulta<select name="motivo_categoria">${MOTIVOS.map(([v,t])=>`<option value="${v}">${t}</option>`).join("")}</select></label>
      <label>Llegada<select name="llegada_ambulancia"><option value="">Sin cambiar</option><option value="true">Ambulancia</option><option value="false">Por sus medios</option></select></label>
      <label>Lesión / trauma<select name="lesion"><option value="">Sin cambiar</option><option value="true">Sí</option><option value="false">No</option></select></label>
      <div class="ia-form-acciones"><button class="btn btn-primary" type="submit">Guardar signos y analizar</button></div>
    </form></details>`;
}

function leerFormulario(){
  const f=actual.panel.querySelector("#ia-form");
  const signos={};
  for(const [k] of SIGNOS){const v=f.elements[k].value;if(v!=="")signos[k]=Number(v);}
  const cuerpo={};
  if(Object.keys(signos).length)cuerpo.signos=signos;
  if(f.elements.motivo_categoria.value)cuerpo.motivo_categoria=f.elements.motivo_categoria.value;
  for(const k of ["llegada_ambulancia","lesion"])if(f.elements[k].value!=="")cuerpo[k]=f.elements[k].value==="true";
  return cuerpo;
}

async function analizar(conFormulario){
  const botones=actual.panel.querySelectorAll("#ia-analizar,#ia-form button");
  botones.forEach(b=>b.disabled=true);
  try{
    const r=await apiPost(`/ia/analizar/${actual.documento}`,conFormulario?leerFormulario():{});
    showToast(`Pretriaje: ${CATEGORIA[r.categoria].texto}${r.alerta?" · alerta crítica creada":""}`,r.alerta?"error":"success");
    actual.panel.querySelector("#ia-form")?.reset();
    await cargarReportes();
  }catch(e){showToast(e.message,"error");}
  finally{botones.forEach(b=>b.disabled=false);}
}

async function cargarReportes(){
  const caja=actual.panel?.querySelector("#ia-reportes");
  if(!caja)return;
  try{
    const reportes=await apiGet(`/ia/pacientes/${actual.documento}/reportes`);
    caja.innerHTML=reportes.length?reportes.map(tarjeta).join(""):
      '<div class="card muted">Este paciente aún no tiene análisis de IA.</div>';
    caja.querySelectorAll("[data-revisar]").forEach(b=>b.addEventListener("click",()=>revisar(b)));
    caja.querySelectorAll("[data-payload]").forEach(b=>b.addEventListener("click",()=>verPayload(b)));
  }catch(e){caja.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}

function tarjeta(r){
  const res=r.resultado||{},cat=CATEGORIA[r.categoria],P=res.probabilidades||{};
  const factores=(lista,signo)=>(lista||[]).map(f=>`<li><span class="ia-flecha">${signo}</span>${escapeHtml(f.texto)}</li>`).join("")||'<li class="muted">—</li>';
  return `<article class="card ia-reporte ${cat.clase}" data-id="${r.id}">
    <header class="ia-reporte-head">
      <div><span class="ia-badge ${cat.clase}">${cat.texto}</span>
        <span class="muted">${cat.detalle}</span></div>
      <div class="ia-estado ia-estado-${r.estado}">${ESTADO[r.estado]}</div>
    </header>
    ${r.id_alerta?`<p class="ia-alerta-nota">⚠ Generó una alerta crítica (${r.estado_alerta==="activa"?"activa":"reconocida"})</p>`:""}
    <div class="ia-probs">${["critico","medio","no_critico"].map(k=>`
      <div class="ia-prob"><span>${CATEGORIA[k].texto}</span>
        <div class="ia-barra"><div class="${CATEGORIA[k].clase}" style="width:${pct(P[k]||0)}"></div></div>
        <strong>${pct(P[k]||0)}</strong></div>`).join("")}
    </div>
    <div class="ia-columnas">
      <div><h4>Lo que sube la urgencia</h4><ul class="ia-factores">${factores(res.factores_suben,"▲")}</ul></div>
      <div><h4>Lo que la baja</h4><ul class="ia-factores">${factores(res.factores_bajan,"▼")}</ul></div>
    </div>
    ${(res.signos_alarma||[]).length?`<p><strong>Signos de alarma:</strong> ${res.signos_alarma.map(escapeHtml).join(" · ")}</p>`:""}
    ${(res.avisos||[]).length?`<p class="muted">ℹ ${res.avisos.map(escapeHtml).join(" · ")}</p>`:""}
    <p class="muted small-text">Perfil del paciente: ${escapeHtml(res.grupo||"—")} · Modelo ${escapeHtml(r.modelo_version)} · ${fecha(r.created_at)}</p>
    ${r.estado==="pendiente"&&puedeRevisar()?`
      <div class="ia-revision">
        <textarea rows="2" maxlength="2000" placeholder="Observaciones del clínico (opcional)"></textarea>
        <div class="actions">
          <button class="btn btn-primary" type="button" data-revisar="aprobar" data-id="${r.id}">Aceptar categoría</button>
          <button class="btn btn-secondary" type="button" data-revisar="rechazar" data-id="${r.id}">Rechazar</button>
        </div></div>`:""}
    ${r.estado!=="pendiente"?`<p class="small-text">Revisado ${fecha(r.revisado_at)}${r.observaciones_clinico?` · “${escapeHtml(r.observaciones_clinico)}”`:""}</p>`:""}
    <button class="btn btn-ghost small-text" type="button" data-payload="${r.id}">Ver datos enviados al modelo (R12)</button>
    <pre class="ia-payload" hidden></pre>
  </article>`;
}

async function revisar(boton){
  const tarjetaEl=boton.closest(".ia-reporte"),nota=tarjetaEl.querySelector("textarea").value.trim();
  tarjetaEl.querySelectorAll("[data-revisar]").forEach(b=>b.disabled=true);
  try{
    await apiPatch(`/ia/reportes/${boton.dataset.id}/${boton.dataset.revisar}`,{observaciones:nota||null});
    showToast(boton.dataset.revisar==="aprobar"?"Categoría aceptada: ya está en la historia clínica":"Reporte rechazado (queda como evidencia)","success");
    window.dispatchEvent(new CustomEvent("ia:revisado"));
    await cargarReportes();
  }catch(e){showToast(e.message,"error");tarjetaEl.querySelectorAll("[data-revisar]").forEach(b=>b.disabled=false);}
}

async function verPayload(boton){
  const pre=boton.nextElementSibling;
  if(!pre.hidden){pre.hidden=true;return;}
  try{
    const r=await apiGet(`/ia/reportes/${boton.dataset.payload}/payload`);
    pre.textContent=JSON.stringify(r.payload,null,2);
    pre.hidden=false;
  }catch(e){showToast(e.message,"error");}
}

// Si llega un evento en vivo de este paciente (otro clínico lo analizó o aprobó), se refresca la lista
window.addEventListener("tr:evento",e=>{
  const ev=e.detail||{};
  if(actual.panel?.isConnected&&Number(ev.paciente_id)===actual.documento&&/reporte_ia|alerta/.test(ev.tipo||""))cargarReportes();
});
window.addEventListener("alertas:cambio",()=>{if(actual.panel?.isConnected)cargarReportes();});
