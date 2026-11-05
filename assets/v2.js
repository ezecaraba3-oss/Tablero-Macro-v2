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
  function iniciar() { perfil(); resumen(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
