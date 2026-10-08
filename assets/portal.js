/* Herramientas de lectura. No escribe ni modifica las fuentes de datos. */
(() => {
  "use strict";
  const section = document.body.dataset.section;
  if (!section || section === "herramientas") return;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const number = value => new Intl.NumberFormat("es-AR", {maximumFractionDigits: 1}).format(value);
  const date = value => value ? value.split("-").reverse().join("/") : "Sin fecha";
  const norm = value => String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const daysBetween = (end, start) => Math.round((Date.parse(end + "T00:00:00Z") - Date.parse(start + "T00:00:00Z")) / 86400000);
  const median = values => {
    if (!values.length) return null;
    const ordered = [...values].sort((a,b) => a-b), middle = Math.floor(ordered.length/2);
    return ordered.length % 2 ? ordered[middle] : (ordered[middle-1]+ordered[middle])/2;
  };
  const counts = values => {
    const result = new Map();
    values.forEach(value => result.set(value, (result.get(value)||0)+1));
    return [...result].sort((a,b) => b[1]-a[1] || String(a[0]).localeCompare(String(b[0]), "es"));
  };
  function stat(id, value, detail) {
    $(id).textContent = value;
    if (detail !== undefined) $(id+"-detail").textContent = detail;
  }
  function options(id, values) {
    [...new Set(values.filter(v => v !== null && v !== ""))].sort((a,b) => String(a).localeCompare(String(b), "es", {numeric:true})).forEach(value => {
      const option = document.createElement("option"); option.value = value; option.textContent = value; $(id).append(option);
    });
  }
  function bars(id, entries) {
    const maximum = Math.max(1, ...entries.map(entry => entry[1]));
    $(id).innerHTML = entries.length ? '<div class="anc-bars">'+entries.map(([label, value]) =>
      `<div class="anc-bar-row"><span class="anc-bar-label">${esc(label)}</span><div class="anc-bar-track" aria-hidden="true"><div class="anc-bar-fill" style="width:${100*value/maximum}%"></div></div><span class="anc-bar-value">${number(value)}</span></div>`).join("")+"</div>" : '<p class="anc-empty">Sin registros para estos filtros.</p>';
  }
  function table(id, headers, rows, caption) {
    $(id).innerHTML = rows.length ? `<div class="anc-table-wrap"><table class="anc-table"><caption>${esc(caption)}</caption><thead><tr>${headers.map(h => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map((cell,i) => `<td${i===r.length-1?' class="anc-number"':''}>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : '<p class="anc-empty">Sin registros para estos filtros.</p>';
  }
  function csv(filename, rows) {
    const content = "\ufeff"+rows.map(row => row.map(value => {
      let text = String(value ?? "");
      if (/^[\s]*[=+@-]/.test(text)) text = "'"+text;
      return '"'+text.replace(/"/g, '""')+'"';
    }).join(";")).join("\r\n");
    const url = URL.createObjectURL(new Blob([content], {type:"text/csv;charset=utf-8"}));
    const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function badge(state) {
    const extra = state === "Notificada" ? " anc-badge-ok" : state === "A verificar" ? " anc-badge-warn" : "";
    return `<span class="anc-badge${extra}">${esc(state)}</span>`;
  }
  function bind(render, exportRows, filename) {
    $("filters").addEventListener("submit", event => event.preventDefault());
    $("filters").addEventListener("input", render);
    $("filters").addEventListener("reset", () => setTimeout(render, 0));
    if ($("export")) $("export").addEventListener("click", () => csv(filename, exportRows()));
    render();
  }
  async function dataset(path, demo=false) {
    const response = await fetch(path);
    if (!response.ok) throw new Error("No se pudo cargar la fuente de datos.");
    const value = await response.json();
    if (value.schema_version !== 1) throw new Error("La fuente de datos tiene un formato no compatible.");
    if (demo && value.demo !== true) throw new Error("Esta página de prueba requiere datos de demostración.");
    return value;
  }
  async function dashboard() {
    const data = await dataset("../data/conc.json");
    options("year", data.registros.map(r=>r.anio)); options("type", data.registros.map(r=>r.tipo));
    let selected = [];
    const render = () => {
      selected = data.registros.filter(r => (!$("year").value || String(r.anio) === $("year").value) && (!$("type").value || r.tipo === $("type").value));
      const times = selected.map(r=>r.dias).filter(d=>Number.isFinite(d));
      const n = selected.length, withDecision = selected.filter(r=>r.decision).length;
      const midpoint = median(times);
      stat("total", number(n), `${number(data.registros.length)} registros en el corpus completo`);
      stat("median", midpoint===null?"—":number(midpoint), `${number(times.length)} registros con ambas fechas · días corridos`);
      stat("coverage", n?number(100*times.length/n)+" %":"—", `${number(times.length)} de ${number(n)} registros`);
      stat("decisions", n?number(100*withDecision/n)+" %":"—", `${number(n-withDecision)} registros sin decisión informada`);
      bars("years", counts(selected.map(r=>r.anio || "Sin fecha")).sort((a,b)=>String(a[0]).localeCompare(String(b[0]),"es",{numeric:true})));
      bars("types", counts(selected.map(r=>r.tipo)));
      bars("sectors", counts(selected.flatMap(r=>r.sectores)));
      bars("relations", counts(selected.flatMap(r=>r.relaciones.length?r.relaciones:["Sin relación informada"])));
      table("decision-table", ["Decisión (texto original)", "Registros"], counts(selected.map(r=>r.decision || "Sin decisión informada")).map(([label,value])=>[esc(label),number(value)]), `${number(n)} registros seleccionados`);
      $("source-note").textContent = `Última firma en el corpus: ${date(data.actualizado_al)}. Fuente: ${data.fuente}. Los tiempos incluyen solo pares de fechas válidos; no descuentan suspensiones ni representan plazos legales. Sectores y relaciones admiten múltiples etiquetas.`;
    };
    bind(render, () => [["Fecha firma","Tipo","Decisión original","Sectores","Días ingreso a firma"],...selected.map(r=>[r.fecha,r.tipo,r.decision,r.sectores.join(" | "),r.dias])], "resoluciones-seleccion.csv");
  }
  async function news() {
    const data = await dataset("../data/monitor.sample.json", true);
    options("state", data.operaciones.map(r=>r.estado)); options("sector", data.operaciones.map(r=>r.sector));
    let selected=[];
    const render = () => {
      const terms=norm($("q").value).trim().split(/\s+/).filter(Boolean);
      selected=data.operaciones.filter(r=>(!$("state").value || r.estado===$("state").value) && (!$("sector").value || r.sector===$("sector").value) && terms.every(term=>norm([r.id,r.comprador,r.objeto,r.operacion,r.sector].join(" ")).includes(term))).sort((a,b)=>b.fecha.localeCompare(a.fecha));
      stat("total",number(selected.length)); stat("pending",number(selected.filter(r=>r.estado==="A verificar").length));
      stat("notified",number(selected.filter(r=>r.estado==="Notificada").length)); stat("markets",number(new Set(selected.map(r=>r.sector)).size));
      table("operations", ["Fecha","Operación y empresas","Mercado","Verificación"], selected.map(r=>[esc(date(r.fecha)),`<strong>${esc(r.operacion)}</strong><br>${esc(r.comprador)} → ${esc(r.objeto)}<br><span class="anc-stat-detail">${esc(r.fuente)}</span>`,esc(r.sector),badge(r.estado)]),`${selected.length} operaciones de demostración`);
    };
    bind(render,()=>[["ID demo","Fecha","Operación ficticia","Comprador ficticio","Objeto ficticio","Mercado","Estado de ejemplo"],...selected.map(r=>[r.id,r.fecha,r.operacion,r.comprador,r.objeto,r.sector,r.estado])],"monitor-DEMO.csv");
  }
  async function tracking() {
    const data = await dataset("../data/seguimiento.sample.json", true);
    options("analyst",data.expedientes.map(r=>r.analista)); options("state",data.expedientes.map(r=>r.estado)); options("type",data.expedientes.map(r=>r.tipo));
    const rows=data.expedientes.map(r=>({...r,edad:daysBetween(data.corte,r.ingreso),proxima:daysBetween(r.revision,data.corte)}));
    let selected=[];
    const render=()=>{
      selected=rows.filter(r=>(!$("analyst").value||r.analista===$("analyst").value)&&(!$("state").value||r.estado===$("state").value)&&(!$("type").value||r.tipo===$("type").value)).sort((a,b)=>a.revision.localeCompare(b.revision));
      const age=median(selected.map(r=>r.edad));
      stat("total",number(selected.length)); stat("age",age===null?"—":number(age));
      stat("reviews",number(selected.filter(r=>r.proxima>=0&&r.proxima<=15).length)); stat("old",number(selected.filter(r=>r.edad>180).length));
      bars("analysts",counts(selected.map(r=>r.analista))); bars("states",counts(selected.map(r=>r.estado)));
      table("cases",["Expediente ficticio","Analista","Procedimiento","Estado","Ingreso","Próxima revisión","Antigüedad (días)"],selected.map(r=>[esc(r.id),esc(r.analista),esc(r.tipo),badge(r.estado),esc(date(r.ingreso)),esc(date(r.revision)),number(r.edad)]),`${selected.length} expedientes de demostración`);
      $("source-note").textContent=`Corte de la demo: ${date(data.corte)}. La futura fuente será Res_firmadas.xlsm en el área interna. Esta demo no contiene expedientes reales.`;
    };
    bind(render,()=>[["Expediente ficticio","Analista ficticio","Procedimiento","Estado","Ingreso ficticio","Revisión ficticia","Antigüedad días","Corte demo"],...selected.map(r=>[r.id,r.analista,r.tipo,r.estado,r.ingreso,r.revision,r.edad,data.corte])],"seguimiento-DEMO.csv");
  }
  const start = {conc:dashboard,noticias:news,seguimiento:tracking}[section];
  if (start) start().catch(error=>{
    const message=document.createElement("p"); message.className="anc-error"; message.textContent=error.message+" Recargá la página para volver a intentar.";
    $("error").replaceChildren(message);
    $("filters").querySelectorAll("input,select,button").forEach(control=>control.disabled=true);
  });
})();
