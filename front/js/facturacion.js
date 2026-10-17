import {apiGet,apiPost,apiPatch} from "./api.js";
import {escapeHtml,formatDate,showToast,modal} from "./ui.js";
import {isRole} from "./auth.js";

const money=v=>new Intl.NumberFormat("es-CO",{style:"currency",currency:"COP",maximumFractionDigits:0}).format(Number(v||0));
const val=v=>escapeHtml(v??"—");

export async function renderFacturacion(container){
  container.innerHTML='<div class="card">Cargando facturación…</div>';
  const refresh=()=>renderFacturacion(container);
  try{
    const rows=await apiGet("/facturas");
    container.innerHTML=`<div class="card"><div class="section-head"><div><h2>Facturación MongoDB</h2><p class="muted">Facturas manuales y facturas automáticas generadas al aprobar reportes de IA.</p></div>${isRole("Contable")||isRole("Admin")?'<button id="new-factura" class="btn btn-primary" type="button">+ Nueva factura</button>':""}</div>${rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Factura</th><th>Paciente</th><th>Servicio</th><th>Reporte IA</th><th>Fecha</th><th>Valor</th><th>Estado</th><th>Origen</th><th></th></tr></thead><tbody>${rows.map(f=>`<tr><td>${val(f.numero_factura||f.id)}</td><td>${val(f.paciente_id)}</td><td>${val(f.servicio)}</td><td>${val(f.reporte_id)}</td><td>${formatDate(f.fecha)}</td><td>${money(f.valor)}</td><td><span class="badge info">${val(f.estado_pago)}</span></td><td>${val(f.origen)}</td><td><div class="actions"><button class="btn btn-secondary" data-ver="${escapeHtml(f.id)}" type="button">Detalle</button><button class="btn btn-secondary" data-estado="${escapeHtml(f.id)}" data-actual="${escapeHtml(f.estado_pago)}" type="button">Cambiar estado</button></div></td></tr>`).join("")}</tbody></table></div>`:'<div class="empty-state">No hay facturas registradas.</div>'}</div>`;
    container.querySelector("#new-factura")?.addEventListener("click",()=>nuevaFacturaModal(refresh));
    container.querySelectorAll("[data-ver]").forEach(b=>b.onclick=()=>detalleModal(b.dataset.ver));
    container.querySelectorAll("[data-estado]").forEach(b=>b.onclick=()=>estadoModal(b.dataset.estado,b.dataset.actual,refresh));
  }catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}

async function detalleModal(id){
  try{
    const f=await apiGet(`/facturas/${id}`);
    modal(`Factura ${f.numero_factura||f.id}`,`<div class="grid grid-2"><div><p><strong>Paciente</strong><br>${val(f.paciente_id)}</p><p><strong>Servicio</strong><br>${val(f.servicio)}</p><p><strong>Descripción</strong><br>${val(f.descripcion)}</p><p><strong>Encuentro</strong><br>${val(f.id_encuentro)}</p></div><div><p><strong>Reporte IA</strong><br>${val(f.reporte_id)}</p><p><strong>Origen</strong><br>${val(f.origen)}</p><p><strong>Estado de pago</strong><br>${val(f.estado_pago)}</p><p><strong>Fecha</strong><br>${formatDate(f.fecha)}</p></div></div><p><strong>Valor: ${money(f.valor)}</strong></p>`);
  }catch(e){showToast(e.message,"error");}
}

function nuevaFacturaModal(refresh){
  const m=modal("Nueva factura",`<form id="f-factura" class="stack-form">
    <div class="grid grid-2"><label>Documento del paciente<input name="paciente_id" type="number" min="1" required></label><label>Servicio<select name="servicio" required><option value="consulta">Consulta</option><option value="remision">Remisión</option><option value="analisis_ia">Análisis IA</option><option value="otro">Otro</option></select></label></div>
    <div class="grid grid-2"><label>Valor (COP)<input name="valor" type="number" min="0" step="1" required></label><label>Estado<select name="estado_pago"><option value="pendiente">Pendiente</option><option value="pagada">Pagada</option><option value="anulada">Anulada</option></select></label></div>
    <div class="grid grid-2"><label>Número de factura (opcional)<input name="numero_factura" maxlength="50"></label><label>ID encuentro (opcional)<input name="id_encuentro" type="number" min="1"></label></div>
    <label>Descripción<input name="descripcion" maxlength="500"></label>
    <button class="btn btn-primary" type="submit">Crear factura</button></form>`);
  const form=m.element.querySelector("#f-factura");
  form.onsubmit=async e=>{
    e.preventDefault();
    const fd=new FormData(form);
    const idEncuentro=fd.get("id_encuentro");
    const body={
      paciente_id:Number(fd.get("paciente_id")),
      servicio:String(fd.get("servicio")),
      valor:Number(fd.get("valor")),
      descripcion:String(fd.get("descripcion")||"").trim()||null,
      estado_pago:String(fd.get("estado_pago")),
      numero_factura:String(fd.get("numero_factura")||"").trim()||null,
      id_encuentro:idEncuentro?Number(idEncuentro):null
    };
    try{await apiPost("/facturas",body);showToast("Factura guardada en MongoDB","success");m.close();await refresh();}
    catch(err){showToast(err.message,"error");}
  };
}


function estadoModal(id,actual,refresh){
  const m=modal("Actualizar estado de pago",`<form id="f-estado" class="stack-form"><p class="muted">Esta acción cambia únicamente el estado contable; no altera el reporte IA, el encuentro ni el origen de la factura.</p><label>Estado<select name="estado_pago"><option value="pendiente">Pendiente</option><option value="pagada">Pagada</option><option value="anulada">Anulada</option></select></label><button class="btn btn-primary" type="submit">Guardar estado</button></form>`);
  const form=m.element.querySelector("#f-estado");form.estado_pago.value=actual||"pendiente";
  form.onsubmit=async e=>{e.preventDefault();try{await apiPatch(`/facturas/${id}/estado`,{estado_pago:form.estado_pago.value});showToast("Estado de factura actualizado","success");m.close();await refresh();}catch(err){showToast(err.message,"error")}};
}
