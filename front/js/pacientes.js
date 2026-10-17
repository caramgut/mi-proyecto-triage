import {apiGet,apiPut,apiPost} from "./api.js";
import {isRole,getCurrentUser} from "./auth.js";
import {escapeHtml,formatDateOnly,initialsFromName,showToast,modal} from "./ui.js";
import {renderHistoria} from "./historia.js";
import {renderPacs} from "./pacs.js";
import {renderEncuentroActual} from "./encuentro_actual.js";
import {abrirRemisionModal,renderResumenRemisionesMedico} from "./remisiones.js";
import {renderPanelIA} from "./ia.js";

let currentPatient=null;
export async function renderPacienteWorkspace(container,{self=false,documento=null}={}){
  const tpl=document.getElementById("tpl-paciente-shell");container.innerHTML="";container.appendChild(tpl.content.cloneNode(true));
  const form=container.querySelector("#patient-search-form"),input=container.querySelector("#patient-document");
  if(self){form.hidden=true;const u=getCurrentUser();await loadPatient(u.numero_documento_usuario,container.querySelector("#patient-result"),true);return;}
  if(documento){form.hidden=true;await loadPatient(documento,container.querySelector("#patient-result"));return;}
  form.addEventListener("submit",async e=>{e.preventDefault();await loadPatient(Number(input.value),container.querySelector("#patient-result"));});
}
async function loadPatient(documento,target,self=false){
  target.innerHTML='<div class="card">Buscando paciente…</div>';
  try{currentPatient=await apiGet(`/pacientes/${documento}`);target.innerHTML=patientShell(currentPatient,self);bindTabs(documento,target);if(!self&&isRole("Medico"))await renderResumenRemisionesMedico(documento,target.querySelector("#patient-referrals"));if(!self)target.querySelector('[data-tab="actual"]')?.click();}
  catch(e){
    if(!self&&isRole("Medico")&&String(e.message||"").toLowerCase().includes("paciente no encontrado")){
      target.innerHTML=`<div class="card"><div class="empty-state"><strong>Paciente no registrado</strong><p>La persona puede ser atendida aunque no tenga cuenta del portal. Registre primero su ficha clínica y luego inicie la atención de Urgencias.</p><button id="register-patient" class="btn btn-primary" type="button">+ Registrar paciente</button></div></div>`;
      target.querySelector("#register-patient")?.addEventListener("click",()=>registrarPacienteModal(documento,()=>loadPatient(documento,target)));
    }else target.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;
  }
}

function registrarPacienteModal(documento,onDone){
  const m=modal("Registrar paciente",`<form id="new-patient-form" class="stack-form"><p class="muted small-text">Este registro crea la ficha clínica. No crea una cuenta de acceso; la atención no depende de tener portal.</p><div class="grid grid-2"><label>Documento<input name="numero_documento_paciente" type="number" value="${Number(documento)}" readonly required></label><label>Tipo de documento<select name="tipo_documento" required><option value="CC">CC</option><option value="TI">TI</option><option value="CE">CE</option><option value="PA">Pasaporte</option><option value="RC">Registro civil</option></select></label><label>Nombres<input name="nombres" required></label><label>Apellidos<input name="apellidos" required></label><label>Fecha de nacimiento<input name="fecha_nacimiento" type="date"></label><label>Género FHIR<select name="genero_fhir"><option value="">Sin especificar</option><option value="female">Femenino</option><option value="male">Masculino</option><option value="other">Otro</option><option value="unknown">Desconocido</option></select></label><label>Teléfono<input name="telefono"></label><label>Municipio<input name="municipio_residencia"></label><label>Zona<select name="zona_residencia"><option value="">Sin especificar</option><option value="urbana">Urbana</option><option value="rural_dispersa">Rural dispersa</option></select></label><label>Dirección<input name="direccion"></label></div><button class="btn btn-primary" type="submit">Registrar y abrir ficha</button></form>`);
  m.element.querySelector("#new-patient-form").onsubmit=async e=>{
    e.preventDefault();const fd=new FormData(e.target);const body=Object.fromEntries(fd.entries());body.numero_documento_paciente=Number(body.numero_documento_paciente);["fecha_nacimiento","genero_fhir","telefono","direccion","municipio_residencia","zona_residencia"].forEach(k=>{if(!body[k])body[k]=null;});
    try{await apiPost("/pacientes",body);showToast("Ficha clínica creada. Ya puede iniciar la atención.","success");m.close();await onDone();}catch(err){showToast(err.message,"error");}
  };
}
function patientShell(p,self){
  return `<section class="patient-header"><div class="patient-title"><div class="patient-avatar">${initialsFromName(p.nombres,p.apellidos)}</div><div><h2>${escapeHtml(p.nombres)} ${escapeHtml(p.apellidos)}</h2><p class="muted">${escapeHtml(p.tipo_documento||"Documento")} ${p.numero_documento_paciente}</p></div></div><div class="actions">${isRole("Medico")?'<button id="refer-patient" class="btn btn-primary" type="button">+ Nueva remisión</button><button id="sync-patient-fhir" class="btn btn-secondary" type="button">Sincronizar Patient FHIR</button>':''}</div></section>${isRole("Medico")?`<section id="patient-referrals" data-documento="${Number(p.numero_documento_paciente)}"></section>`:''}<nav class="patient-tabs">${self?"":'<button class="patient-tab active" data-tab="actual">Encuentro actual</button>'}<button class="patient-tab ${self?"active":""}" data-tab="datos">Datos personales</button><button class="patient-tab" data-tab="historia">Historia clínica</button><button class="patient-tab" data-tab="imagenes">Imágenes PACS</button>${!self&&(isRole("Admin")||isRole("Medico")||isRole("Especialista"))?'<button class="patient-tab" data-tab="ia">Apoyo al triage con IA</button>':""}</nav><section id="patient-panel" class="patient-panel">${self?renderDatos(p):""}</section>`;
}
function renderDatos(p){const fields=[["Fecha de nacimiento",formatDateOnly(p.fecha_nacimiento)],["Género FHIR",p.genero_fhir],["Teléfono",p.telefono],["Dirección",p.direccion],["Municipio",p.municipio_residencia],["Zona",p.zona_residencia]];return `<div class="card"><div class="section-head"><h3>Información del paciente</h3></div><div class="detail-list">${fields.map(([k,v])=>`<div class="detail-item"><span>${escapeHtml(k)}</span><strong>${escapeHtml(v||"—")}</strong></div>`).join("")}</div></div>`;}
function bindTabs(doc,target){
  const panel=target.querySelector("#patient-panel");target.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",async()=>{target.querySelectorAll("[data-tab]").forEach(x=>x.classList.toggle("active",x===b));if(b.dataset.tab==="actual")await renderEncuentroActual(doc,panel);if(b.dataset.tab==="datos")panel.innerHTML=renderDatos(currentPatient);if(b.dataset.tab==="historia")await renderHistoria(doc,panel);if(b.dataset.tab==="imagenes")await renderPacs(doc,panel);if(b.dataset.tab==="ia")await renderPanelIA(doc,panel);}));
  target.querySelector("#sync-patient-fhir")?.addEventListener("click",async()=>{try{await apiPut(`/fhir/pacientes/${doc}`,{});showToast("Paciente sincronizado con HAPI FHIR","success");}catch(e){showToast(e.message,"error");}});
  target.querySelector("#refer-patient")?.addEventListener("click",async()=>{try{const h=await apiGet(`/pacientes/${doc}/historia-clinica`);const enc=(h.encuentros||[]).find(e=>e.estado!=="finalizado");await abrirRemisionModal(currentPatient,enc?.id_encuentro||null,()=>renderResumenRemisionesMedico(doc,target.querySelector("#patient-referrals")));}catch(e){showToast(e.message,"error")}});
}
