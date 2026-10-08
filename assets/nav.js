/* nav.js — barra de navegación común del sitio: la llevan el buscador (index.html), las páginas nuevas
   y la 404. En el buscador son 3 líneas de la plantilla de generar_pagina.py; nada más cambia ahí.
   Uso: <div id="anc-nav"></div> y <script src="…/assets/nav.js" defer></script>.
   Las rutas se calculan a partir de la ubicación de este mismo script, así funciona en la raíz del
   sitio, en un preview de Cloudflare o abriendo los archivos desde disco. */
(function () {
  'use strict';

  var script = document.currentScript;
  var src = (script && script.src) || '';
  var root = src.replace(/assets\/nav\.js(?:\?.*)?$/, '');
  if (!root) root = '/';

  // Grupos propuestos: Concentraciones (buscador, OPIs) · Estadísticas · Mercados · Área interna.
  var ITEMS = [
    { k: 'buscador',     t: 'Buscador',      h: '' },
    { k: 'opis',         t: 'OPIs',          h: 'opis/' },
    { k: 'estadisticas', t: 'Estadísticas',  h: 'conc/' },
    { k: 'mercados',     t: 'Mercados',      soon: true },
    { k: 'interno',      t: 'Área interna 🔒', h: 'demo-interno/noticias/', tag: 'demo' },
    { k: 'mapa',         t: 'Mapa',          h: 'herramientas/' }
  ];

  function current() {
    var here = location.href.split('#')[0].split('?')[0];
    var best = '';
    var rel = here.indexOf(root) === 0 ? here.slice(root.length) : '';
    if (rel === '' || rel === 'index.html') best = 'buscador';
    else if (rel.indexOf('opis/') === 0) best = 'opis';
    else if (rel.indexOf('conc/') === 0) best = 'estadisticas';
    else if (rel.indexOf('demo-interno/') === 0 || rel.indexOf('interno/') === 0) best = 'interno';
    else if (rel.indexOf('herramientas/') === 0) best = 'mapa';
    else if (rel.indexOf('mercados/') === 0) best = 'mercados';
    return best;
  }

  function build() {
    var host = document.getElementById('anc-nav');
    if (!host) {
      host = document.createElement('div');
      host.id = 'anc-nav';
      document.body.insertBefore(host, document.body.firstChild);
    }
    host.textContent = '';
    var cur = current();

    var nav = document.createElement('nav');
    nav.className = 'anc-nav';
    nav.setAttribute('aria-label', 'Herramientas ANC');
    var inner = document.createElement('div');
    inner.className = 'anc-nav-in';

    var brand = document.createElement('a');
    brand.className = 'anc-brand';
    brand.href = root + 'herramientas/';
    brand.textContent = 'Herramientas ANC';
    inner.appendChild(brand);

    ITEMS.forEach(function (it) {
      var node;
      if (it.soon) {
        node = document.createElement('span');
        node.className = 'anc-nl anc-soon';
        node.title = 'Próximamente';
        node.textContent = it.t;
        var soon = document.createElement('span');
        soon.className = 'anc-tag';
        soon.textContent = 'pronto';
        node.appendChild(soon);
      } else {
        node = document.createElement('a');
        node.className = 'anc-nl';
        node.href = root + it.h;
        node.textContent = it.t;
        if (it.k === cur) node.setAttribute('aria-current', 'page');
        if (it.tag) {
          var tg = document.createElement('span');
          tg.className = 'anc-tag';
          tg.textContent = it.tag;
          node.appendChild(tg);
        }
      }
      inner.appendChild(node);
    });

    nav.appendChild(inner);
    host.appendChild(nav);
    compact(inner);
  }

  // En pantallas angostas la barra es una sola fila que se desliza: se desplaza lo justo para que la
  // seccion activa se vea entera y, mientras haya mas para ver, el borde derecho se difumina
  // (clase anc-more, ver anc.css).
  function compact(inner) {
    function more() {
      inner.classList.toggle('anc-more', inner.scrollWidth - inner.clientWidth - inner.scrollLeft > 4);
    }
    var act = inner.querySelector('[aria-current="page"]');
    if (act && inner.scrollWidth > inner.clientWidth) {
      var r = act.getBoundingClientRect(), b = inner.getBoundingClientRect();
      if (r.right > b.right - 36) inner.scrollLeft += r.right - b.right + 36;
    }
    inner.addEventListener('scroll', more, { passive: true });
    window.addEventListener('resize', more);
    more();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
})();
