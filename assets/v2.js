/* Tablas de la v2 que no pasan por el motor de gráficos. */
(function () {
  function datos(id) {
    var d = window.dash && dash.data(id);
    return d && d.status === 'ok' ? d.data : [];
  }
  function miles(v, dec) {
    return Number(v).toLocaleString('es-AR', { minimumFractionDigits: dec || 0, maximumFractionDigits: dec || 0 });
  }
  function celda(fila, texto, clase) {
    var td = document.createElement('td');
    if (clase) td.className = clase;
    td.textContent = texto;
    fila.appendChild(td);
    return td;
  }
  function perfil() {
    var cuerpo = document.getElementById('perfil-deuda');
    if (!cuerpo) return;
    var filas = datos('deuda_perfil');
    var max = Math.max.apply(null, filas.map(function (f) { return +f.total; }).concat(1));
    cuerpo.replaceChildren();
    filas.forEach(function (f) {
      var tr = document.createElement('tr');
      var th = document.createElement('th');
      th.scope = 'row';
      th.textContent = f.anio;
      tr.appendChild(th);
      celda(tr, miles(f.capital), 'n');
      celda(tr, miles(f.interes), 'n');
      celda(tr, miles(f.total), 'n');
      var barra = celda(tr, '');
      var i = document.createElement('i');
      i.className = 'perfil-barra';
      i.style.width = (f.total / max * 100).toFixed(1) + '%';
      barra.appendChild(i);
      cuerpo.appendChild(tr);
    });
  }
  function resumen() {
    datos('deuda_resumen').forEach(function (f) {
      var el = document.querySelector('[data-resumen="' + f.indicador + '"]');
      if (el) el.textContent = miles(f.valor, 1).concat(el.dataset.u || '');
    });
  }
  function curva() {
    var cuerpo = document.getElementById('curva-pesos');
    if (!cuerpo) return;
    var filas = datos('curva_pesos');
    var max = Math.max.apply(null, filas.map(function (f) { return +f.tea; }).concat(1));
    cuerpo.replaceChildren();
    filas.forEach(function (f) {
      var tr = document.createElement('tr');
      var th = document.createElement('th');
      th.scope = 'row';
      th.textContent = f.ticker;
      tr.appendChild(th);
      celda(tr, f.vencimiento.split('-').reverse().join('/'), 'n');
      celda(tr, miles(f.dias), 'n');
      celda(tr, miles(f.tem, 2) + '%', 'n');
      celda(tr, miles(f.tea, 1) + '%', 'n');
      var barra = celda(tr, '');
      var i = document.createElement('i');
      i.className = 'perfil-barra';
      i.style.width = (f.tea / max * 100).toFixed(1) + '%';
      barra.appendChild(i);
      cuerpo.appendChild(tr);
    });
    var fecha = document.getElementById('curva-fecha');
    if (fecha && filas[0]) fecha.textContent = filas[0].fecha.split('-').reverse().join('/');
  }
  function sostenibilidad() {
    var cuerpo = document.getElementById('tabla-sost');
    if (!cuerpo) return;
    var conteo = { 'Mejoró': 0, 'Empeoró': 0, 'Sin cambios': 0 };
    cuerpo.replaceChildren();
    datos('sostenibilidad').forEach(function (f) {
      var tr = document.createElement('tr');
      var th = document.createElement('th');
      th.scope = 'row';
      th.textContent = f.indicador;
      tr.appendChild(th);
      celda(tr, f.area);
      var dec = String(f.valor).indexOf('.') >= 0 ? String(f.valor).split('.')[1].length : 0;
      celda(tr, miles(f.valor, dec) + ' ' + f.unidad + ' (' + f.periodo + ')', 'n');
      celda(tr, miles(f.previo, dec) + ' ' + f.unidad + ' (' + f.periodo_previo + ')', 'n');
      var c = celda(tr, f.lectura);
      c.className = f.lectura === 'Mejoró' ? 'lec-mejor' : (f.lectura === 'Empeoró' ? 'lec-peor' : '');
      conteo[f.lectura]++;
      cuerpo.appendChild(tr);
    });
    var r = document.getElementById('sost-resumen');
    if (r) r.textContent = conteo['Mejoró'] + ' mejoraron, ' + conteo['Empeoró'] + ' empeoraron y ' + conteo['Sin cambios'] + ' no cambiaron';
  }
  function iniciar() { perfil(); resumen(); curva(); sostenibilidad(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
