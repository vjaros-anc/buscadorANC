/* charts.js — gráficos sin dependencias (SVG / HTML) para las páginas nuevas del sitio.
   Sigue el método del skill dataviz:
     · marcas finas (barras <= 24 px, punta de 4 px redondeada y base recta, líneas de 2 px, puntos de 8 px),
     · 2 px de "aire" entre segmentos apilados y 2 px de anillo en los puntos (sin bordes dibujados),
     · grilla y ejes de 1 px, sólidos y apenas más oscuros que el fondo,
     · leyenda siempre que haya 2 o más series, con el total de cada una (etiquetas visibles),
     · tooltip en hover Y en foco de teclado, y una vista en tabla equivalente de cada gráfico.
   Los textos de los datos entran siempre con textContent (nunca con innerHTML).

   API:  ANCCharts.stackedColumns(host, spec)   columnas apiladas por categoría
         ANCCharts.lines(host, spec)            líneas con puntos (valores null = sin dato)
         ANCCharts.hbars(host, spec)            barras horizontales (categorías nominales)
         ANCCharts.h / .s / .fmt / .pct         utilidades (DOM, SVG, números en formato es-AR)  */
(function (global) {
  'use strict';

  var SVGNS = 'http://www.w3.org/2000/svg';
  var GAP = 2; // aire entre segmentos, en px

  /* ---------- utilidades ---------- */
  function el(ns, tag, attrs, kids) {
    var n = ns ? document.createElementNS(ns, tag) : document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'text') { n.textContent = v; return; }
        n.setAttribute(k, v === true ? '' : v);
      });
    }
    (kids || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      n.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
    });
    return n;
  }
  function h(tag, attrs, kids) { return el(null, tag, attrs, kids); }
  function s(tag, attrs, kids) { return el(SVGNS, tag, attrs, kids); }

  // Formato es-AR determinista (no depende del ICU del navegador): 1.045 · 12,3
  function fmt(n, d) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    var neg = n < 0;
    var parts = Math.abs(n).toFixed(d || 0).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return (neg ? '−' : '') + parts.join(',');
  }
  function pct(n, d) { return fmt(n, d === undefined ? 0 : d) + ' %'; }

  function niceTicks(max, target) {
    target = target || 5;
    if (!(max > 0)) return { max: 1, ticks: [0, 1] };
    var raw = max / target;
    var mag = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
    var norm = raw / mag;
    var step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
    var top = Math.ceil(max / step - 1e-9) * step;
    var ticks = [];
    for (var v = 0; v <= top + step / 1000; v += step) ticks.push(Math.round(v * 100) / 100);
    return { max: top, ticks: ticks };
  }

  // rectángulo con la punta superior redondeada (4 px) y la base recta
  function topRounded(x, y, w, hh, r) {
    r = Math.max(0, Math.min(r, hh, w / 2));
    return 'M' + x + ',' + (y + hh) + 'L' + x + ',' + (y + r) + 'Q' + x + ',' + y + ' ' + (x + r) + ',' + y +
      'L' + (x + w - r) + ',' + y + 'Q' + (x + w) + ',' + y + ' ' + (x + w) + ',' + (y + r) + 'L' + (x + w) + ',' + (y + hh) + 'Z';
  }

  /* ---------- figura base: título, leyenda, escenario, tooltip y vista en tabla ---------- */
  function makeFigure(host, spec) {
    host.textContent = '';
    var b = { spec: spec };
    b.btn = h('button', { type: 'button', class: 'anc-btn-link', 'aria-pressed': 'false' }, ['Ver como tabla']);
    b.legend = h('div', { class: 'anc-legend' });
    b.stage = h('div', { class: 'anc-stage' });
    b.tip = h('div', { class: 'anc-tip', role: 'tooltip', hidden: true });
    b.plot = h('div', { class: 'anc-plot' }, [b.stage, b.tip]);
    b.tablewrap = h('div', { class: 'anc-tablewrap', hidden: true });
    b.fig = h('figure', { class: 'anc-fig' }, [
      h('div', { class: 'anc-fig-h' }, [
        h('div', null, [
          h('h3', { class: 'anc-fig-t' }, [spec.title]),
          spec.subtitle ? h('p', { class: 'anc-fig-s' }, [spec.subtitle]) : null
        ]),
        b.btn
      ]),
      b.legend, b.plot, b.tablewrap,
      spec.note ? h('p', { class: 'anc-fig-n' }, [spec.note]) : null
    ]);
    host.appendChild(b.fig);
    b.btn.addEventListener('click', function () {
      var on = b.btn.getAttribute('aria-pressed') !== 'true';
      b.btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.btn.textContent = on ? 'Ver gráfico' : 'Ver como tabla';
      b.plot.hidden = on;
      b.legend.hidden = on;
      b.tablewrap.hidden = !on;
      hideTip(b);
    });
    return b;
  }

  function setTable(b, caption, headers, rows) {
    b.tablewrap.textContent = '';
    b.tablewrap.appendChild(h('table', { class: 'anc-table' }, [
      h('caption', null, [caption]),
      h('thead', null, [h('tr', null, headers.map(function (t, i) {
        return h('th', { scope: 'col', class: i ? 'num' : null }, [t]);
      }))]),
      h('tbody', null, rows.map(function (r) {
        return h('tr', null, r.map(function (c, i) {
          return i === 0 ? h('th', { scope: 'row' }, [String(c)])
            : h('td', { class: 'num' }, [typeof c === 'number' ? fmt(c) : String(c)]);
        }));
      }))
    ]));
  }

  function tipTitle(t) { return h('div', { class: 'anc-tip-t' }, [t]); }
  function tipRow(color, value, label) {
    return h('div', { class: 'anc-tip-r' }, [
      color ? h('i', { class: 'anc-key', style: 'background:' + color }) : null,
      h('b', null, [value]),
      h('span', null, [label])
    ]);
  }
  function tipNote(t) { return h('div', { class: 'anc-tip-n' }, [t]); }

  function showTip(b, nodes, cx, cy) {
    b.tip.textContent = '';
    nodes.forEach(function (n) { b.tip.appendChild(n); });
    b.tip.hidden = false;
    var pr = b.plot.getBoundingClientRect();
    var tw = b.tip.offsetWidth, th = b.tip.offsetHeight;
    var x = cx - pr.left + 14, y = cy - pr.top - th - 10;
    if (x + tw > pr.width) x = cx - pr.left - tw - 14;
    if (x < 0) x = 4;
    if (y < 0) y = cy - pr.top + 16;
    b.tip.style.left = x + 'px';
    b.tip.style.top = y + 'px';
  }
  function hideTip(b) { b.tip.hidden = true; }
  function anchorOf(node) {
    var r = node.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + Math.min(r.height / 2, 40) };
  }

  // vuelve a dibujar cuando cambia el ANCHO del contenedor (los textos se quedan en 11-12 px reales)
  function onWidth(b, draw) {
    var last = -1;
    function run() {
      var w = Math.floor(b.stage.clientWidth);
      if (w < 120 || w === last) return;
      last = w;
      draw(w);
    }
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(run).observe(b.stage);
    else global.addEventListener('resize', run);
    run();
  }

  function gridAndAxis(svg, m, W, plotH, tk, yOf) {
    tk.ticks.forEach(function (t) {
      var yy = Math.round(yOf(t)) + 0.5;
      svg.appendChild(s('line', { class: t === 0 ? 'anc-base-l' : 'anc-grid-l', x1: m.l, x2: W - m.r, y1: yy, y2: yy }));
      svg.appendChild(s('text', { x: m.l - 7, y: yOf(t) + 4, 'text-anchor': 'end', text: fmt(t) }));
    });
  }

  /* ---------- columnas apiladas ----------
     spec: { title, subtitle, note, categories:['2016',…], catNames:[…] (tooltip), catHeader,
             series:[{ label, color, values:[…] }], unit, height } */
  function stackedColumns(host, spec) {
    var b = makeFigure(host, spec);
    var cats = spec.categories, series = spec.series, n = cats.length;
    var names = spec.catNames || cats;
    var totals = cats.map(function (_, i) {
      return series.reduce(function (a, se) { return a + (se.values[i] || 0); }, 0);
    });
    var seriesTotal = series.map(function (se) {
      return se.values.reduce(function (a, v) { return a + (v || 0); }, 0);
    });

    series.forEach(function (se, k) {
      b.legend.appendChild(h('span', null, [
        h('i', { class: 'anc-sw', style: 'background:' + se.color }), se.label + ' ', h('b', null, [fmt(seriesTotal[k])])
      ]));
    });
    setTable(b, spec.title,
      [spec.catHeader || 'Período'].concat(series.map(function (se) { return se.label; }), ['Total']),
      cats.map(function (_, i) {
        return [names[i]].concat(series.map(function (se) { return se.values[i] || 0; }), [totals[i]]);
      }));

    function draw(W) {
      var H = spec.height || 300, m = { l: 42, r: 6, t: 24, b: 28 };
      var plotW = W - m.l - m.r, plotH = H - m.t - m.b;
      var tk = niceTicks(Math.max.apply(null, totals.concat([1])), 5);
      var yOf = function (v) { return m.t + plotH - (v / tk.max) * plotH; };
      var slot = plotW / n, barW = Math.min(24, Math.max(8, slot * 0.66));
      var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img',
        'aria-label': spec.title + (spec.subtitle ? '. ' + spec.subtitle : '') });
      gridAndAxis(svg, m, W, plotH, tk, yOf);
      var band = s('rect', { class: 'anc-hover-band', y: m.t, height: plotH, visibility: 'hidden' });
      svg.appendChild(band);

      cats.forEach(function (cat, i) {
        var cx = m.l + slot * (i + 0.5), x0 = cx - barW / 2, cum = 0, last = -1;
        series.forEach(function (se, k) { if ((se.values[i] || 0) > 0) last = k; });
        series.forEach(function (se, k) {
          var v = se.values[i] || 0;
          if (v <= 0) return;
          var yt = yOf(cum + v), yb = yOf(cum) - (cum > 0 ? GAP : 0), hh = Math.max(1, yb - yt);
          var common = { style: 'fill:' + se.color };
          svg.appendChild(k === last
            ? s('path', Object.assign({ d: topRounded(x0, yb - hh, barW, hh, 4) }, common))
            : s('rect', Object.assign({ x: x0, y: yb - hh, width: barW, height: hh }, common)));
          cum += v;
        });
        if (slot >= 22 && totals[i] > 0) {
          svg.appendChild(s('text', { class: 'anc-total', x: cx, y: yOf(totals[i]) - 6, 'text-anchor': 'middle', text: fmt(totals[i]) }));
        }
        svg.appendChild(s('text', { x: cx, y: H - 9, 'text-anchor': 'middle',
          text: slot < 38 && /^\d{4}\*?$/.test(cat) ? "'" + cat.slice(2) : cat }));

        var label = names[i] + ': ' + series.map(function (se) { return se.label + ' ' + fmt(se.values[i] || 0); }).join(', ') +
          '. Total ' + fmt(totals[i]);
        var hit = s('rect', { class: 'anc-hit', x: cx - slot / 2, y: m.t, width: slot, height: plotH, tabindex: 0, role: 'img', 'aria-label': label });
        function enter(cx2, cy2) {
          band.setAttribute('x', cx - slot / 2);
          band.setAttribute('width', slot);
          band.setAttribute('visibility', 'visible');
          var rows = [tipTitle(names[i])];
          series.forEach(function (se) { rows.push(tipRow(se.color, fmt(se.values[i] || 0), se.label)); });
          rows.push(tipRow(null, fmt(totals[i]), 'Total' + (spec.unit ? ' · ' + spec.unit : '')));
          showTip(b, rows, cx2, cy2);
        }
        function leave() { band.setAttribute('visibility', 'hidden'); hideTip(b); }
        hit.addEventListener('pointermove', function (e) { enter(e.clientX, e.clientY); });
        hit.addEventListener('pointerleave', leave);
        hit.addEventListener('focus', function () { var a = anchorOf(hit); enter(a.x, a.y); });
        hit.addEventListener('blur', leave);
        svg.appendChild(hit);
      });
      b.stage.textContent = '';
      b.stage.appendChild(svg);
    }
    onWidth(b, draw);
    return b;
  }

  /* ---------- líneas con puntos ----------
     spec: { title, subtitle, note, categories, catHeader,
             series:[{ label, color, values:[número|null], n:[…], suffix }], unit, valueSuffix, height } */
  function lines(host, spec) {
    var b = makeFigure(host, spec);
    var cats = spec.categories, series = spec.series, n = cats.length;
    var suf = spec.valueSuffix || '';

    series.forEach(function (se) {
      b.legend.appendChild(h('span', null, [
        h('i', { class: 'anc-sw line', style: 'background:' + se.color }), se.label,
        se.legendExtra ? h('b', null, [' ' + se.legendExtra]) : null
      ]));
    });
    setTable(b, spec.title,
      [spec.catHeader || 'Período'].concat(series.map(function (se) { return se.label; })),
      cats.map(function (c, i) {
        return [c].concat(series.map(function (se) {
          var nn = se.n ? se.n[i] : null;
          if (se.values[i] === null || se.values[i] === undefined) return nn ? '— (n = ' + nn + ')' : '—';
          return fmt(se.values[i]) + suf + (nn ? ' (n = ' + nn + ')' : '');
        }));
      }));

    function draw(W) {
      var H = spec.height || 280, m = { l: 42, r: 44, t: 14, b: 28 };
      var plotW = W - m.l - m.r, plotH = H - m.t - m.b, slot = plotW / n;
      var vals = [];
      series.forEach(function (se) { se.values.forEach(function (v) { if (v !== null && v !== undefined) vals.push(v); }); });
      var tk = niceTicks(Math.max.apply(null, vals.concat([1])), 5);
      var yOf = function (v) { return m.t + plotH - (v / tk.max) * plotH; };
      var xOf = function (i) { return m.l + slot * (i + 0.5); };
      var svg = s('svg', { viewBox: '0 0 ' + W + ' ' + H, width: W, height: H, role: 'img',
        'aria-label': spec.title + (spec.subtitle ? '. ' + spec.subtitle : '') });
      gridAndAxis(svg, m, W, plotH, tk, yOf);
      cats.forEach(function (c, i) {
        svg.appendChild(s('text', { x: xOf(i), y: H - 9, 'text-anchor': 'middle',
          text: slot < 38 && /^\d{4}\*?$/.test(c) ? "'" + c.slice(2) : c }));
      });
      var cross = s('line', { class: 'anc-cross', y1: m.t, y2: m.t + plotH, visibility: 'hidden' });
      svg.appendChild(cross);

      var endLabels = [];
      series.forEach(function (se) {
        var d = '', prev = false, lastI = -1;
        se.values.forEach(function (v, i) {
          if (v === null || v === undefined) { prev = false; return; }
          d += (prev ? 'L' : 'M') + xOf(i).toFixed(1) + ',' + yOf(v).toFixed(1);
          prev = true; lastI = i;
        });
        if (d) svg.appendChild(s('path', { d: d, fill: 'none', 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', style: 'stroke:' + se.color }));
        se.values.forEach(function (v, i) {
          if (v === null || v === undefined) return;
          svg.appendChild(s('circle', { cx: xOf(i), cy: yOf(v), r: 6, style: 'fill:var(--anc-surface)' }));
          svg.appendChild(s('circle', { cx: xOf(i), cy: yOf(v), r: 4, style: 'fill:' + se.color }));
        });
        if (lastI >= 0) endLabels.push({ x: xOf(lastI) + 10, y: yOf(se.values[lastI]), text: fmt(se.values[lastI]) + suf });
      });
      // etiquetas de punta: solo si no se pisan (si no, quedan el tooltip y la tabla)
      endLabels.sort(function (a, c) { return a.y - c.y; });
      endLabels.forEach(function (lb, i) {
        if (i > 0 && lb.y - endLabels[i - 1].y < 14) return;
        if (lb.x + 8 > W) return;
        svg.appendChild(s('text', { class: 'anc-total', x: lb.x, y: lb.y + 4, text: lb.text }));
      });

      cats.forEach(function (c, i) {
        var label = c + ': ' + series.map(function (se) {
          var v = se.values[i], nn = se.n ? se.n[i] : null;
          return se.label + ' ' + (v === null || v === undefined ? 'sin dato' : fmt(v) + suf) + (nn ? ' (n = ' + nn + ')' : '');
        }).join(', ');
        var hit = s('rect', { class: 'anc-hit', x: xOf(i) - slot / 2, y: m.t, width: slot, height: plotH, tabindex: 0, role: 'img', 'aria-label': label });
        function enter(cx2, cy2) {
          cross.setAttribute('x1', xOf(i)); cross.setAttribute('x2', xOf(i)); cross.setAttribute('visibility', 'visible');
          var rows = [tipTitle(c)];
          series.forEach(function (se) {
            var v = se.values[i], nn = se.n ? se.n[i] : null;
            rows.push(tipRow(se.color, v === null || v === undefined ? '—' : fmt(v) + suf,
              se.label + (nn ? ' · n = ' + fmt(nn) : '') + (v === null || v === undefined ? ' (pocos casos o sin dato)' : '')));
          });
          showTip(b, rows, cx2, cy2);
        }
        function leave() { cross.setAttribute('visibility', 'hidden'); hideTip(b); }
        hit.addEventListener('pointermove', function (e) { enter(e.clientX, e.clientY); });
        hit.addEventListener('pointerleave', leave);
        hit.addEventListener('focus', function () { var a = anchorOf(hit); enter(a.x, a.y); });
        hit.addEventListener('blur', leave);
        svg.appendChild(hit);
      });
      b.stage.textContent = '';
      b.stage.appendChild(svg);
    }
    onWidth(b, draw);
    return b;
  }

  /* ---------- barras horizontales (categorías nominales: una sola serie, un solo color) ----------
     spec: { title, subtitle, note, items:[{ label, value, pct, muted, note }], unit, tableHeaders } */
  function hbars(host, spec) {
    var b = makeFigure(host, spec);
    var items = spec.items;
    var max = Math.max.apply(null, items.map(function (it) { return it.value; }).concat([1]));
    var list = h('div', { class: 'anc-hb', role: 'list' });
    // en la barra: sin decimales, salvo que el porcentaje sea menor a 1 %; en tooltip y tabla: 1 decimal
    function decBar(it) { return it.pctDecimals !== undefined ? it.pctDecimals : (it.pct > 0 && it.pct < 1 ? 1 : 0); }
    function decTip(it) { return it.pctDecimals !== undefined ? it.pctDecimals : 1; }
    items.forEach(function (it) {
      var w = (it.value / max) * 72;
      var vtxt = fmt(it.value) + (it.pct !== undefined && it.pct !== null ? ' · ' + pct(it.pct, decBar(it)) : '');
      var row = h('div', { class: 'anc-hb-row', role: 'listitem', tabindex: 0,
        'aria-label': it.label + ': ' + vtxt + (it.note ? '. ' + it.note : '') }, [
        h('div', { class: 'anc-hb-l' }, [it.label]),
        h('div', { class: 'anc-hb-t' }, [
          h('div', { class: 'anc-hb-bar' + (it.muted ? ' muted' : ''), style: 'width:' + w.toFixed(2) + '%' }),
          h('div', { class: 'anc-hb-v', style: 'left:calc(' + w.toFixed(2) + '% + 6px)' }, [vtxt])
        ])
      ]);
      function enter(cx, cy) {
        var rows = [tipTitle(it.label), tipRow(it.muted ? 'var(--anc-other)' : 'var(--anc-s1)', fmt(it.value), spec.unit || '')];
        if (it.pct !== undefined && it.pct !== null) rows.push(tipRow(null, pct(it.pct, decTip(it)), 'del total'));
        if (it.note) rows.push(tipNote(it.note));
        showTip(b, rows, cx, cy);
      }
      row.addEventListener('pointermove', function (e) { enter(e.clientX, e.clientY); });
      row.addEventListener('pointerleave', function () { hideTip(b); });
      row.addEventListener('focus', function () { var a = anchorOf(row); enter(a.x, a.y); });
      row.addEventListener('blur', function () { hideTip(b); });
      list.appendChild(row);
    });
    b.stage.appendChild(list);
    var hasPct = items.some(function (it) { return it.pct !== undefined && it.pct !== null; });
    setTable(b, spec.title,
      spec.tableHeaders || ['Categoría', spec.unit || 'Cantidad'].concat(hasPct ? ['%'] : []),
      items.map(function (it) {
        return [it.label, it.value].concat(hasPct ? [it.pct === undefined || it.pct === null ? '—' : pct(it.pct, decTip(it))] : []);
      }));
    return b;
  }

  global.ANCCharts = { h: h, s: s, fmt: fmt, pct: pct, stackedColumns: stackedColumns, lines: lines, hbars: hbars };
})(window);
