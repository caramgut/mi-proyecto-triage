import {apiGet} from "./api.js";
import {escapeHtml,formatDate,triageBadge} from "./ui.js";
import {getCurrentUser} from "./auth.js";

const val=v=>escapeHtml(v??"—");

export async function renderUrgencias(container){
  container.innerHTML='<div class="card">Cargando cola de Urgencias…</div>';
  try{
    const rows=await apiGet("/encuentros/urgencias/activos");
    const actual=Number(getCurrentUser()?.numero_documento_usuario||0);
    const rowHtml=e=>{
      const asignado=Number(e.medico_responsable||0);
      const mio=asignado===actual;
      const medico=asignado?`${e.medico_nombres||""} ${e.medico_apellidos||""}`.trim()||e.medico_username||asignado:"Sin asignar";
      const estadoAtencion=asignado?(mio?'<span class="badge success">Asignado a mí</span>':`<span class="badge info">En atención</span><div class="muted small-text">${val(medico)}</div>`):'<span class="badge warning">Sin médico</span>';
      const accion=mio||!asignado?`<button class="btn btn-primary" data-atender="${e.id_paciente}" type="button">Abrir atención</button>`:`<button class="btn btn-secondary" type="button" disabled title="Este encuentro ya tiene médico responsable">Asignado</button>`;
      return `<tr><td>${formatDate(e.fecha_hora_ingreso)}</td><td>${val(`${e.nombres||""} ${e.apellidos||""}`)}</td><td>${val(e.id_paciente)}</td><td>${val(e.motivo_consulta)}</td><td>${e.nivel_triage?triageBadge(e.nivel_triage):'<span class="badge">Pendiente</span>'}</td><td><span class="badge info">${val(e.estado)}</span></td><td>${estadoAtencion}</td><td>${accion}</td></tr>`;
    };
    container.innerHTML=`<section class="page-hero"><div><p class="eyebrow">Flujo asistencial</p><h2>Urgencias activas</h2><p class="muted">La cola muestra todos los encuentros abiertos. Cada caso indica si ya tiene médico responsable; otro médico no puede abrir una atención ajena.</p></div><span class="badge info">${rows.length} activos</span></section><div class="card">${rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Ingreso</th><th>Paciente</th><th>Documento</th><th>Motivo</th><th>Triage</th><th>Estado</th><th>Atención</th><th>Acción</th></tr></thead><tbody>${rows.map(rowHtml).join("")}</tbody></table></div>`:'<div class="empty-state"><strong>No hay pacientes en atención activa.</strong><p>Busque o registre un paciente y cree un encuentro de Urgencias para que aparezca aquí.</p></div>'}</div>`;
    container.querySelectorAll("[data-atender]").forEach(b=>b.onclick=()=>window.dispatchEvent(new CustomEvent("app:open-patient",{detail:{documento:Number(b.dataset.atender)}})));
  }catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}
