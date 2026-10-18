import {apiGet,apiPost,apiBlob} from "./api.js";
import {escapeHtml,formatDate,triageBadge,modal,showToast} from "./ui.js";
import {isRole} from "./auth.js";
import {renderHistoriaToolbar,bindHistoriaToolbar,encounterActionsHtml,deleteButtonHtml,bindEncounterActions} from "./encuentro.js";

const val=(v)=>escapeHtml(v??"—");
function list(items,renderer){return items?.length?`<div class="compact-list">${items.map(renderer).join("")}</div>`:'<div class="history-empty">Sin registros.</div>'}
function row(inner,tipo,id){return `<div class="compact-row"><span>${inner}</span>${deleteButtonHtml(tipo,id)}</div>`}

export async function renderHistoria(documento,container){
  container.innerHTML='<div class="card">Cargando historia clínica…</div>';
  const refresh=()=>renderHistoria(documento,container);
  try{
    const h=await apiGet(`/pacientes/${documento}/historia-clinica`); const encounters=h.encuentros||[];
    const obs=encounters.reduce((a,e)=>a+(e.observaciones?.length||0),0), dx=encounters.reduce((a,e)=>a+(e.diagnosticos?.length||0),0), exams=encounters.reduce((a,e)=>a+(e.examenes?.length||0),0);
    const reportes=h.reportes_ia||[];
    container.innerHTML=`<div class="history-summary"><div class="metric"><strong>${encounters.length}</strong><span>Encuentros</span></div><div class="metric"><strong>${obs}</strong><span>Observaciones</span></div><div class="metric"><strong>${dx}</strong><span>Diagnósticos</span></div><div class="metric"><strong>${exams}</strong><span>Exámenes</span></div></div><div class="card"><div class="section-head"><h3>Antecedentes</h3><div class="actions">${isRole("Medico","Especialista")?`<button id="nuevo-antecedente" class="btn btn-secondary" type="button">+ Antecedente</button>`:""}<button id="descargar-historia-pdf" class="btn btn-secondary" type="button">Descargar PDF</button></div></div>${list(h.antecedentes,a=>row(`<strong>${val(a.tipo_antecedente||a.tipo||"Antecedente")}</strong> · ${val(a.descripcion||a.detalle||"")} <span class="muted">${formatDate(a.fecha_registro)}</span>`,"antecedente",a.id_antecedente))}</div><div class="card"><div class="section-head"><h3>Reportes IA aprobados</h3><span class="badge success">${reportes.length}</span></div>${list(reportes,r=>`<div class="compact-row"><span><strong>Reporte #${val(r.id)}</strong> · ${val(r.categoria)} · P(crítico) ${val(r.p_critico)}${r.observaciones_clinico?`<br><span class="muted">${val(r.observaciones_clinico)}</span>`:""}</span></div>`)}</div><div class="section-head"><h3>Encuentros clínicos</h3>${renderHistoriaToolbar(documento,refresh)}</div><div class="history-timeline">${encounters.length?encounters.map(renderEncounter).join(""):'<div class="empty-state">No hay encuentros clínicos registrados.</div>'}</div>`;
    container.querySelector("#nuevo-antecedente")?.addEventListener("click",()=>nuevoAntecedente(documento,refresh));
    container.querySelector("#descargar-historia-pdf")?.addEventListener("click",async()=>{
      try{
        const blob=await apiBlob(`/pacientes/${documento}/historia-clinica/pdf`);
        const url=URL.createObjectURL(blob);
        const a=document.createElement("a");
        a.href=url;a.download=`historia_${documento}.pdf`;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
      }catch(err){container.insertAdjacentHTML("afterbegin",`<div class="error-box">${escapeHtml(err.message)}</div>`);}
    });
    bindHistoriaToolbar(container,documento,refresh);
    bindEncounterActions(container,refresh);
  }catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}
function renderEncounter(e){
  return `<article class="encounter-card"><header class="encounter-head"><div><strong>Encuentro #${e.id_encuentro}</strong><div class="muted small-text">${formatDate(e.fecha_hora_ingreso)} · ${val(e.servicio||e.tipo_encuentro)}</div></div><div class="actions">${triageBadge(e.nivel_triage)}<span class="badge ${e.estado==='finalizado'?'success':'info'}">${val(e.estado)}</span></div></header><div class="encounter-body">${encounterActionsHtml(e)}<div class="clinical-block"><h4>Motivo de consulta</h4><div>${val(e.motivo_consulta)}</div>${e.triage?.observaciones_triage?`<div class="muted small-text">Triage: ${val(e.triage.observaciones_triage)}</div>`:""}</div><div class="grid grid-2"><div class="clinical-block"><h4>Observaciones</h4>${list(e.observaciones,o=>row(`<strong>${val(o.tipo_observacion||o.codigo_loinc||"Observación")}</strong>: ${val(o.valor_numerico??o.valor_texto)} ${val(o.unidad||"")}`,"observacion",o.id_observacion))}</div><div class="clinical-block"><h4>Diagnósticos</h4>${list(e.diagnosticos,d=>row(`<strong>${val(d.codigo_cie10||"")}</strong> ${val(d.descripcion)} <span class="muted small-text">${val(d.tipo)}</span>`,"diagnostico",d.id_diagnostico))}</div><div class="clinical-block"><h4>Exámenes</h4>${list(e.examenes,x=>row(`<strong>${val(x.nombre)}</strong> · ${val(x.categoria)} · ${val(x.estado)}`,"examen",x.id_examen))}</div><div class="clinical-block"><h4>Prescripciones</h4>${list(e.prescripciones,p=>row(`<strong>${val(p.medicamento||p.codigo_cum)}</strong> ${val(p.dosis||"")} ${val(p.frecuencia||"")}`,"prescripcion",p.id_prescripcion))}</div><div class="clinical-block"><h4>Notas clínicas</h4>${list(e.notas_clinicas,n=>row(val(n.contenido),"nota",n.id_nota))}</div></div></div></article>`;
}

function nuevoAntecedente(documento,refresh){
  const m=modal("Nuevo antecedente",`<form id="form-antecedente" class="stack-form"><label>Tipo<select name="tipo" required><option value="">Seleccione…</option><option value="personal">Personal</option><option value="familiar">Familiar</option><option value="alergia">Alergia</option><option value="quirurgico">Quirúrgico</option><option value="farmacologico">Farmacológico</option><option value="otro">Otro</option></select></label><label>Código (opcional)<input name="codigo" maxlength="50"></label><label>Descripción<textarea name="descripcion" required maxlength="2000"></textarea></label><button class="btn btn-primary" type="submit">Guardar antecedente</button></form>`);
  m.element.querySelector("#form-antecedente").onsubmit=async e=>{
    e.preventDefault();
    const body=Object.fromEntries(new FormData(e.target).entries());
    body.id_paciente=Number(documento);
    if(!body.codigo)body.codigo=null;
    try{await apiPost("/antecedentes",body);showToast("Antecedente registrado","success");m.close();await refresh();}
    catch(err){showToast(err.message,"error");}
  };
}
