// alertas.js — Aviso persistente de alertas críticas (R20).
// Aparece en vivo cuando llega un evento "alerta_*" por el canal SSE y NO se puede cerrar:
// solo desaparece cuando un médico o especialista la reconoce con una nota.
// Al recargar la página vuelve a aparecer, porque se consulta /alertas?estado=activa.
// Paciente y Contable no lo ven (la API además les responde 403).
import {apiGet,apiPatch} from "./api.js";
import {getCurrentUser} from "./auth.js";
import {escapeHtml,showToast,formatDate} from "./ui.js";

const ROLES_CON_ALERTAS=["Admin","Medico","Especialista"];
const rol=()=>getCurrentUser()?.rol;

function contenedor(){
  let caja=document.getElementById("alertas-criticas");
  if(!caja){
    caja=document.createElement("section");
    caja.id="alertas-criticas";
    caja.className="alertas-criticas";
    caja.setAttribute("role","alert");
    caja.setAttribute("aria-live","assertive");
    const ancla=document.getElementById("status-strip");
    ancla?ancla.before(caja):document.querySelector(".app-main")?.prepend(caja);
  }
  return caja;
}

export async function refrescarAlertas(){
  const caja=contenedor();
  if(!ROLES_CON_ALERTAS.includes(rol())){caja.innerHTML="";caja.hidden=true;return;}
  try{
    let alertas=await apiGet("/alertas?estado=activa");
    // Al admin solo le corresponden las que se escalaron por falta de reconocimiento
    if(rol()==="Admin")alertas=alertas.filter(a=>a.escalada_at);
    pintar(caja,alertas);
  }catch(e){
    if(e.status!==401&&e.status!==403)console.warn("No se pudieron cargar las alertas",e);
  }
}

function pintar(caja,alertas){
  caja.hidden=alertas.length===0;
  const puedeReconocer=["Medico","Especialista"].includes(rol());
  caja.innerHTML=alertas.map(a=>`
    <article class="alerta-critica" data-id="${a.id}">
      <div class="alerta-icono" aria-hidden="true">!</div>
      <div class="alerta-cuerpo">
        <strong>ALERTA CRÍTICA · ${escapeHtml(a.paciente_nombres)} ${escapeHtml(a.paciente_apellidos)}</strong>
        <span>Documento ${a.paciente_id} · P(crítico) ${Math.round(Number(a.p_critico)*100)}%${a.escalada_at?' · <b>ESCALADA</b>':""}</span>
        <span class="alerta-motivo">${(a.motivo||[]).map(escapeHtml).join(" · ")}</span>
      </div>
      ${puedeReconocer?`
        <form class="alerta-reconocer">
          <input name="nota" required minlength="3" maxlength="2000" placeholder="Nota de reconocimiento (obligatoria)">
          <button class="btn" type="submit">Reconocer</button>
        </form>`:'<span class="alerta-info">Debe reconocerla un médico</span>'}
    </article>`).join("");
  caja.querySelectorAll(".alerta-reconocer").forEach(f=>f.addEventListener("submit",reconocer));
}

async function reconocer(e){
  e.preventDefault();
  const form=e.currentTarget,id=form.closest(".alerta-critica").dataset.id,nota=form.elements.nota.value.trim();
  form.querySelector("button").disabled=true;
  try{
    await apiPatch(`/alertas/${id}/reconocer`,{nota});
    showToast("Alerta reconocida","success");
    await refrescarAlertas();
    window.dispatchEvent(new CustomEvent("alertas:cambio"));
  }catch(err){
    showToast(err.message,"error");
    form.querySelector("button").disabled=false;
  }
}

// Cada vez que el canal (re)conecta -por ejemplo, después del login- se consulta el estado real
window.addEventListener("tr:conectado",refrescarAlertas);
// Llega una alerta nueva, escalada o reconocida por otro clínico
window.addEventListener("tr:evento",e=>{if((e.detail?.tipo||"").includes("alerta"))refrescarAlertas();});
// Al cerrar sesión se vacía el aviso
window.addEventListener("auth:expired",()=>{const c=document.getElementById("alertas-criticas");if(c){c.innerHTML="";c.hidden=true;}});


export async function renderAlertasEscaladas(container){
  container.innerHTML='<div class="card">Cargando alertas escaladas…</div>';
  try{
    const todas=await apiGet("/alertas?estado=activa");
    const alertas=todas.filter(a=>a.escalada_at);
    container.innerHTML=`<section class="page-hero"><div><p class="eyebrow">Seguridad clínica</p><h2>Alertas críticas escaladas</h2><p class="muted">Una alerta aparece aquí automáticamente cuando permanece activa sin reconocimiento durante el tiempo configurado. El Admin supervisa el escalamiento; el reconocimiento clínico lo realiza un Médico o Especialista.</p></div><span class="badge ${alertas.length?'danger':'success'}">${alertas.length} activas</span></section><div class="card">${alertas.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Paciente</th><th>Documento</th><th>Reporte IA</th><th>Prob. crítico</th><th>Creada</th><th>Escalada</th><th>Estado</th></tr></thead><tbody>${alertas.map(a=>`<tr><td>${escapeHtml(`${a.paciente_nombres||""} ${a.paciente_apellidos||""}`)}</td><td>${a.paciente_id}</td><td>${a.reporte_id}</td><td>${Math.round(Number(a.p_critico||0)*100)}%</td><td>${formatDate(a.created_at)}</td><td>${formatDate(a.escalada_at)}</td><td><span class="badge danger">ESCALADA</span></td></tr>`).join("")}</tbody></table></div>`:'<div class="empty-state"><strong>No hay alertas escaladas activas.</strong><p>Para probar R20, genere un caso crítico y no reconozca la alerta. El sistema revisa automáticamente las alertas y la escalará al Admin cuando venza el tiempo configurado.</p></div>'}</div>`;
  }catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}
