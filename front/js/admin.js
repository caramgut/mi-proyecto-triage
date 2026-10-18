import {apiGet,apiPost,apiPut,apiPatch,apiDelete} from "./api.js";
import {escapeHtml,formatDate,showToast,modal} from "./ui.js";

export async function renderUsuarios(container){
  container.innerHTML='<div class="card">Cargando usuarios…</div>';
  try{
    const users=await apiGet("/usuarios");
    container._usuarios=users;
    container.innerHTML=`<div class="admin-grid"><div class="admin-toolbar"><div><h2>Gestión de usuarios</h2><p class="muted">Administración, restauración y desbloqueo de cuentas.</p></div><button id="new-user" class="btn btn-primary">Crear usuario</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Documento</th><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Especialidad</th><th>Ficha paciente</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>${users.map(rowUser).join("")}</tbody></table></div></div>`;
    bindUserActions(container);
  }catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}
function rowUser(u){
  const active=u.estado&&!u.is_deleted;
  const ficha=u.rol==="Paciente"?(u.paciente_registrado?'<span class="badge success">Ficha clínica ✓</span>':`<button class="btn btn-secondary" data-create-patient="${u.numero_documento_usuario}" data-name="${escapeHtml(`${u.nombres||""} ${u.apellidos||""}`)}">Crear ficha clínica</button>`):"—";
  return `<tr><td>${u.numero_documento_usuario}</td><td>${escapeHtml(u.username)}</td><td>${escapeHtml(`${u.nombres||""} ${u.apellidos||""}`)}</td><td><span class="badge info">${escapeHtml(u.rol)}</span></td><td>${escapeHtml(u.especialidades||"—")}</td><td>${ficha}</td><td><span class="badge ${active?'success':'danger'}">${active?'Activo':'Inactivo'}</span></td><td><div class="actions"><button class="btn btn-secondary" data-edit="${u.numero_documento_usuario}">Editar</button><button class="btn btn-secondary" data-unlock="${u.numero_documento_usuario}">Desbloquear</button>${u.is_deleted?`<button class="btn btn-success" data-restore="${u.numero_documento_usuario}">Restaurar</button>`:`<button class="btn btn-danger" data-delete="${u.numero_documento_usuario}">Eliminar</button>`}</div></td></tr>`;
}
function bindUserActions(container){
  container.querySelector("#new-user")?.addEventListener("click",newUserModal);
  container.querySelectorAll("[data-unlock]").forEach(b=>b.onclick=async()=>action(()=>apiPatch(`/usuarios/${b.dataset.unlock}/desbloquear`),"Usuario desbloqueado",()=>renderUsuarios(container)));
  container.querySelectorAll("[data-restore]").forEach(b=>b.onclick=async()=>action(()=>apiPatch(`/usuarios/${b.dataset.restore}/restaurar`),"Usuario restaurado",()=>renderUsuarios(container)));
  container.querySelectorAll("[data-edit]").forEach(b=>b.onclick=()=>{const u=(container._usuarios||[]).find(x=>String(x.numero_documento_usuario)===b.dataset.edit);if(u)editUserModal(u,()=>renderUsuarios(container));});
  container.querySelectorAll("[data-delete]").forEach(b=>b.onclick=async()=>{
    const documento=Number(b.dataset.delete);
    try{
      const impacto=await apiGet(`/usuarios/${documento}/impacto-desactivacion`);
      if(impacto?.usuario?.rol==="Medico" && (impacto.encuentros_activos||[]).length){
        return desactivarMedicoConReasignacion(documento,impacto,()=>renderUsuarios(container));
      }
      if(confirm("¿Eliminar lógicamente este usuario? El registro podrá ser restaurado por el Admin."))
        await action(()=>apiDelete(`/usuarios/${documento}`),"Usuario eliminado",()=>renderUsuarios(container));
    }catch(e){showToast(e.message,"error");}
  });
  container.querySelectorAll("[data-create-patient]").forEach(b=>b.onclick=()=>crearFichaPacienteExistente(Number(b.dataset.createPatient),b.dataset.name,()=>renderUsuarios(container)));
}


function desactivarMedicoConReasignacion(documento,impacto,onDone){
  const activos=impacto.encuentros_activos||[],medicos=impacto.medicos_disponibles||[];
  if(!medicos.length){
    showToast("No hay otro médico activo disponible. Cree o active un médico antes de desactivar este usuario.","error",7000);
    return;
  }
  const rows=activos.map(e=>`<tr><td>#${e.id_encuentro}</td><td>${e.id_paciente}</td><td>${escapeHtml(`${e.paciente_nombres||""} ${e.paciente_apellidos||""}`)}</td><td>${escapeHtml(e.estado||"—")}</td></tr>`).join("");
  const options=medicos.map(m=>`<option value="${m.numero_documento_usuario}">${escapeHtml(`${m.nombres||""} ${m.apellidos||""} · ${m.username}`)}</option>`).join("");
  const m=modal("Reasignar antes de desactivar",`<div class="stack-form"><div class="warning-box"><strong>Este médico tiene ${activos.length} encuentro(s) activo(s).</strong><p>Para no interrumpir la atención, debe transferirlos a otro médico activo antes de desactivar la cuenta.</p></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Encuentro</th><th>Documento</th><th>Paciente</th><th>Estado</th></tr></thead><tbody>${rows}</tbody></table></div><form id="reassign-doctor-form" class="stack-form"><label>Médico de reemplazo<select name="medico_reemplazo" required><option value="">Seleccione…</option>${options}</select></label><button class="btn btn-danger" type="submit">Reasignar y desactivar médico</button></form></div>`);
  m.element.querySelector("#reassign-doctor-form").onsubmit=async e=>{
    e.preventDefault();
    const reemplazo=Number(new FormData(e.target).get("medico_reemplazo"));
    if(!reemplazo)return;
    try{
      const r=await apiDelete(`/usuarios/${documento}?medico_reemplazo=${reemplazo}`);
      showToast(`Médico desactivado. ${r.encuentros_reasignados?.length||0} encuentro(s) reasignado(s).`,"success",6000);
      m.close();
      await onDone?.();
    }catch(err){showToast(err.message,"error");}
  };
}

function crearFichaPacienteExistente(documento,nombre,onDone){
  const partes=String(nombre||"").trim().split(/\s+/);
  const m=modal("Crear ficha clínica",`<form id="existing-patient-form" class="stack-form"><p class="muted small-text">La cuenta ya existe. Esta acción crea el registro clínico con el mismo documento y lo vincula automáticamente.</p><div class="grid grid-2"><label>Documento<input name="numero_documento_paciente" type="number" value="${documento}" readonly></label><label>Tipo de documento<select name="tipo_documento" required><option value="CC">CC</option><option value="TI">TI</option><option value="CE">CE</option><option value="PA">Pasaporte</option><option value="RC">Registro civil</option></select></label><label>Nombres<input name="nombres" value="${escapeHtml(partes.slice(0,1).join(" "))}" required></label><label>Apellidos<input name="apellidos" value="${escapeHtml(partes.slice(1).join(" "))}" required></label><label>Fecha nacimiento<input name="fecha_nacimiento" type="date"></label><label>Género FHIR<select name="genero_fhir"><option value="">Sin especificar</option><option value="female">Femenino</option><option value="male">Masculino</option><option value="other">Otro</option><option value="unknown">Desconocido</option></select></label><label>Teléfono<input name="telefono"></label><label>Municipio<input name="municipio_residencia"></label><label>Zona<select name="zona_residencia"><option value="">Sin especificar</option><option value="urbana">Urbana</option><option value="rural_dispersa">Rural dispersa</option></select></label><label>Dirección<input name="direccion"></label></div><button class="btn btn-primary" type="submit">Crear y vincular ficha</button></form>`);
  m.element.querySelector("#existing-patient-form").onsubmit=async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target).entries());body.numero_documento_paciente=Number(body.numero_documento_paciente);["fecha_nacimiento","genero_fhir","telefono","direccion","municipio_residencia","zona_residencia"].forEach(k=>{if(!body[k])body[k]=null;});try{await apiPost("/pacientes",body);showToast("Ficha clínica creada y vinculada","success");m.close();await onDone();}catch(err){showToast(err.message,"error");}};
}
async function action(fn,msg,after){try{await fn();showToast(msg,"success");after?.()}catch(e){showToast(e.message,"error")}}
async function editUserModal(u,onDone){
  try{
    const [roles,especialidades]=await Promise.all([apiGet("/roles"),apiGet("/especialidades")]);
    const roleOptions=roles.map(r=>`<option value="${r.id_rol}" data-role="${escapeHtml(r.nombre)}" ${r.id_rol===u.id_rol?"selected":""}>${escapeHtml(r.nombre)}</option>`).join("");
    const espOptions=especialidades.map(e=>`<option value="${e.id_especialidad}" ${e.id_especialidad===u.id_especialidad?"selected":""}>${escapeHtml(e.nombre)}</option>`).join("");
    const v=x=>escapeHtml(x??"");
    const m=modal(`Editar usuario ${u.numero_documento_usuario}`,`<form id="edit-user-form" class="stack-form"><div class="grid grid-2"><label>Usuario<input name="username" minlength="3" maxlength="50" pattern="[A-Za-z0-9._-]+" value="${v(u.username)}" required></label><label>Rol<select id="edit-role" name="id_rol" required>${roleOptions}</select></label><label id="edit-specialty-field" hidden>Especialidad<select name="id_especialidad"><option value="">Seleccione…</option>${espOptions}</select></label><label>Nombres<input name="nombres" maxlength="100" value="${v(u.nombres)}" required></label><label>Apellidos<input name="apellidos" maxlength="100" value="${v(u.apellidos)}" required></label><label>Correo<input name="email" type="email" value="${v(u.email)}"></label><label>Teléfono<input name="telefono" maxlength="30" value="${v(u.telefono)}"></label></div><button class="btn btn-primary" type="submit">Guardar cambios</button></form><p class="muted small-text">El documento no se puede cambiar. Para desactivar una cuenta use Eliminar (si es un médico con encuentros activos, se le pedirá un reemplazo). La contraseña no se modifica aquí.</p>`);
    const roleSelect=m.element.querySelector("#edit-role"),spField=m.element.querySelector("#edit-specialty-field"),spSelect=spField.querySelector("select");
    const sync=()=>{const isEsp=roleSelect.options[roleSelect.selectedIndex]?.dataset.role==="Especialista";spField.hidden=!isEsp;spSelect.required=isEsp&&!u.id_especialidad;};
    roleSelect.addEventListener("change",sync);sync();
    m.element.querySelector("#edit-user-form").onsubmit=async e=>{
      e.preventDefault();const body=Object.fromEntries(new FormData(e.target).entries());
      body.id_rol=Number(body.id_rol);
      if(body.id_especialidad)body.id_especialidad=Number(body.id_especialidad);else delete body.id_especialidad;
      ["email","telefono"].forEach(k=>{if(!body[k])body[k]=null;});
      try{await apiPut(`/usuarios/${u.numero_documento_usuario}`,body);showToast("Usuario actualizado","success");m.close();await onDone();}catch(err){showToast(err.message,"error");}
    };
  }catch(e){showToast(e.message,"error")}
}
async function newUserModal(){
  try{
    const [roles,especialidades]=await Promise.all([apiGet("/roles"),apiGet("/especialidades")]);
    const roleOptions=roles.map(r=>`<option value="${r.id_rol}" data-role="${escapeHtml(r.nombre)}">${escapeHtml(r.nombre)}</option>`).join("");
    const espOptions=especialidades.map(e=>`<option value="${e.id_especialidad}">${escapeHtml(e.nombre)}</option>`).join("");
    const m=modal("Crear usuario",`<form id="new-user-form" class="stack-form"><div class="grid grid-2"><label>Documento<input name="numero_documento_usuario" type="number" required></label><label>Rol<select id="new-role" name="id_rol" required><option value="">Seleccione…</option>${roleOptions}</select></label><label id="specialty-field" hidden>Especialidad<select name="id_especialidad"><option value="">Seleccione…</option>${espOptions}</select></label><label>Usuario<input name="username" minlength="3" maxlength="50" pattern="[A-Za-z0-9._-]+" required></label><label>Contraseña<input name="password" type="password" minlength="8" maxlength="128" required></label><label>Nombres<input name="nombres" required></label><label>Apellidos<input name="apellidos" required></label><label>Correo<input name="email" type="email"></label><label>Teléfono<input name="telefono"></label></div><fieldset id="patient-fields" hidden><legend>Ficha clínica del paciente</legend><p class="muted small-text">Si la ficha clínica no existe, se creará automáticamente y quedará vinculada a esta cuenta.</p><div class="grid grid-2"><label>Tipo de documento<select name="tipo_documento"><option value="">Seleccione…</option><option value="CC">CC</option><option value="TI">TI</option><option value="CE">CE</option><option value="PA">Pasaporte</option><option value="RC">Registro civil</option></select></label><label>Fecha de nacimiento<input name="fecha_nacimiento" type="date"></label><label>Género FHIR<select name="genero_fhir"><option value="">Sin especificar</option><option value="female">Femenino</option><option value="male">Masculino</option><option value="other">Otro</option><option value="unknown">Desconocido</option></select></label><label>Municipio<input name="municipio_residencia"></label><label>Zona<select name="zona_residencia"><option value="">Sin especificar</option><option value="urbana">Urbana</option><option value="rural_dispersa">Rural dispersa</option></select></label><label>Dirección<input name="direccion"></label></div></fieldset><button class="btn btn-primary" type="submit">Crear usuario</button></form><p class="muted small-text">Solo Admin crea cuentas. Una persona puede ser atendida sin cuenta; la cuenta Paciente solo habilita el portal.</p>`);
    const roleSelect=m.element.querySelector("#new-role"),specialtyField=m.element.querySelector("#specialty-field"),specialtySelect=specialtyField.querySelector("select"),patientFields=m.element.querySelector("#patient-fields"),tipoDocumento=patientFields.querySelector('[name="tipo_documento"]');
    const syncRole=()=>{const selected=roleSelect.options[roleSelect.selectedIndex];const role=selected?.dataset.role;const isSpecialist=role==="Especialista",isPatient=role==="Paciente";specialtyField.hidden=!isSpecialist;specialtySelect.required=isSpecialist;if(!isSpecialist)specialtySelect.value="";patientFields.hidden=!isPatient;tipoDocumento.required=isPatient;if(!isPatient){patientFields.querySelectorAll("input,select").forEach(x=>{if(x.name!=="tipo_documento")x.value="";});tipoDocumento.value="";}};
    roleSelect.addEventListener("change",syncRole);syncRole();
    m.element.querySelector("#new-user-form").onsubmit=async e=>{
      e.preventDefault();const fd=new FormData(e.target);const body=Object.fromEntries(fd.entries());
      body.numero_documento_usuario=Number(body.numero_documento_usuario);body.id_rol=Number(body.id_rol);
      if(body.id_especialidad)body.id_especialidad=Number(body.id_especialidad);else body.id_especialidad=null;
      ["email","telefono","tipo_documento","fecha_nacimiento","genero_fhir","direccion","municipio_residencia","zona_residencia"].forEach(k=>{if(!body[k])body[k]=null;});
      try{const r=await apiPost("/usuarios",body);const msg=r?.paciente_creado?"Usuario y ficha clínica creados":r?.paciente_vinculado?"Usuario creado y vinculado a la ficha clínica existente":"Usuario creado";showToast(msg,"success");m.close();document.querySelector('[data-view="usuarios"]')?.click();}catch(err){showToast(err.message,"error")}
    };
  }catch(e){showToast(e.message,"error")}
}

export async function renderPacientesEliminados(container){
  container.innerHTML='<div class="card">Cargando fichas clínicas eliminadas…</div>';
  try{
    const rows=await apiGet("/pacientes/eliminados");
    container.innerHTML=`<section class="page-hero"><div><p class="eyebrow">Administración clínica</p><h2>Fichas clínicas eliminadas</h2><p class="muted">Soft delete: estos registros no fueron borrados físicamente. Solo el Admin puede restaurarlos.</p></div><span class="badge ${rows.length?'warning':'success'}">${rows.length} pendientes</span></section><div class="card">${rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Documento</th><th>Paciente</th><th>Eliminada</th><th>Eliminada por</th><th>Acción</th></tr></thead><tbody>${rows.map(p=>`<tr><td>${p.numero_documento_paciente}</td><td>${escapeHtml(`${p.nombres||""} ${p.apellidos||""}`)}</td><td>${formatDate(p.deleted_at)}</td><td>${escapeHtml(p.eliminado_por_username||p.deleted_by||"—")}</td><td><button class="btn btn-success" data-restore-patient="${Number(p.numero_documento_paciente)}" type="button">Restaurar ficha</button></td></tr>`).join("")}</tbody></table></div>`:'<div class="empty-state">No hay fichas clínicas eliminadas.</div>'}</div>`;
    container.querySelectorAll("[data-restore-patient]").forEach(btn=>btn.addEventListener("click",async()=>{
      if(!confirm("¿Restaurar esta ficha clínica?"))return;
      btn.disabled=true;
      await action(()=>apiPatch(`/pacientes/${btn.dataset.restorePatient}/restaurar`),"Ficha clínica restaurada",()=>renderPacientesEliminados(container));
    }));
  }catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}

export async function renderSecurity(container){
  container.innerHTML='<div class="card">Cargando eventos de autenticación…</div>';
  try{const logs=await apiGet("/auth/logs?limite=100");container.innerHTML=`<div class="card"><div class="section-head"><div><h2>Seguridad de acceso</h2><p class="muted">Últimos intentos de autenticación y eventos registrados.</p></div></div>${renderLogs(logs)}</div>`;}catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}
export async function renderAuditoria(container){
  container.innerHTML='<div class="card">Cargando auditoría…</div>';
  try{const logs=await apiGet("/auditoria?limite=100");container.innerHTML=`<div class="card"><h2>Auditoría de cambios</h2><p class="muted">Trazabilidad de operaciones sobre registros clínicos y administrativos.</p><div class="table-wrap"><table class="data-table"><thead><tr><th>Fecha</th><th>Tabla</th><th>Registro</th><th>Acción</th><th>Usuario</th><th>Rol</th></tr></thead><tbody>${logs.map(x=>`<tr><td>${formatDate(x.fecha_hora)}</td><td>${escapeHtml(x.tabla_afectada)}</td><td>${escapeHtml(x.registro_id)}</td><td><span class="badge info">${escapeHtml(x.accion)}</span></td><td>${escapeHtml(x.username||x.realizado_por||"—")}</td><td>${escapeHtml(x.rol||"—")}</td></tr>`).join("")}</tbody></table></div></div>`;}catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}
function renderLogs(logs){if(!logs.length)return'<div class="empty-state">No hay eventos registrados.</div>';return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Fecha</th><th>Usuario</th><th>Evento</th><th>Resultado</th><th>Detalle</th></tr></thead><tbody>${logs.map(x=>`<tr><td>${formatDate(x.fecha_hora||x.created_at)}</td><td>${escapeHtml(x.username||x.numero_documento_usuario||"—")}</td><td class="log-event">${escapeHtml(x.evento||x.accion||x.tipo_evento||"—")}</td><td>${escapeHtml(x.resultado ?? x.exitoso ?? "—")}</td><td>${escapeHtml(x.detalle||x.mensaje||"")}</td></tr>`).join("")}</tbody></table></div>`;}

export async function renderPapeleraClinica(container){
  container.innerHTML='<div class="card">Cargando registros clínicos eliminados…</div>';
  try{
    const rows=await apiGet("/admin/papelera-clinica");
    const labels={antecedente:"Antecedente",observacion:"Observación",diagnostico:"Diagnóstico",nota:"Nota clínica",examen:"Examen",prescripcion:"Prescripción"};
    const restorePath={
      antecedente:id=>`/antecedentes/${id}/restaurar`,
      observacion:id=>`/observaciones/${id}/restaurar`,
      diagnostico:id=>`/diagnosticos/${id}/restaurar`,
      nota:id=>`/notas-clinicas/${id}/restaurar`,
      examen:id=>`/examenes/${id}/restaurar`,
      prescripcion:id=>`/prescripciones/${id}/restaurar`,
    };
    container.innerHTML=`<section class="page-hero"><div><p class="eyebrow">Administración clínica</p><h2>Papelera clínica</h2><p class="muted">Registros eliminados lógicamente por profesionales. El Admin puede restaurarlos sin perder trazabilidad.</p></div><span class="badge ${rows.length?'warning':'success'}">${rows.length} eliminados</span></section><div class="card">${rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Tipo</th><th>Paciente</th><th>Encuentro</th><th>Resumen</th><th>Eliminado</th><th>Por</th><th>Acción</th></tr></thead><tbody>${rows.map(r=>`<tr><td><span class="badge info">${labels[r.tipo]||escapeHtml(r.tipo)}</span></td><td>${escapeHtml(r.paciente||String(r.id_paciente||"—"))}<br><span class="muted small-text">${r.id_paciente||""}</span></td><td>${r.id_encuentro?`#${r.id_encuentro}`:"—"}</td><td>${escapeHtml(r.resumen||"—")}</td><td>${formatDate(r.deleted_at)}</td><td>${escapeHtml(r.eliminado_por||String(r.deleted_by||"—"))}</td><td><button class="btn btn-success" data-restore-clinical="${r.tipo}" data-id="${r.id_registro}" type="button">Restaurar</button></td></tr>`).join("")}</tbody></table></div>`:'<div class="empty-state">No hay registros clínicos eliminados.</div>'}</div>`;
    container.querySelectorAll("[data-restore-clinical]").forEach(btn=>btn.onclick=async()=>{
      const fn=restorePath[btn.dataset.restoreClinical];
      if(!fn)return;
      if(!confirm("¿Restaurar este registro clínico?"))return;
      await action(()=>apiPatch(fn(btn.dataset.id)),"Registro restaurado",()=>renderPapeleraClinica(container));
    });
  }catch(e){container.innerHTML=`<div class="error-box">${escapeHtml(e.message)}</div>`;}
}
