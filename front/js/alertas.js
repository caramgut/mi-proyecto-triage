// alertas.js — Aviso persistente de alertas críticas (R20).
// Aparece en vivo cuando llega un evento "alerta_*" por el canal SSE y NO se puede cerrar:
// solo desaparece cuando un médico o especialista la reconoce con una nota.
// Al recargar la página vuelve a aparecer, porque se consulta /alertas?estado=activa.
// Paciente y Contable no lo ven (la API además les responde 403).
import {apiGet,apiPatch} from "./api.js";
import {getCurrentUser} from "./auth.js";
import {escapeHtml,showToast} from "./ui.js";

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
