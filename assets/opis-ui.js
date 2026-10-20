/* Presentación de las OPIs. Los datos y los filtros conservan sus valores originales. */
(function () {
  'use strict';
  var decisions = {
    sujeta_a_notificacion: 'Sujeta a notificación',
    no_sujeta_a_notificacion: 'No sujeta a notificación',
    sujeta_con_salvedades: 'Sujeta con salvedades',
    abstracta_o_desistida: 'Abstracta o desistida',
    archivo: 'Archivo',
    otro: 'Otro'
  };
  function label(value) {
    var text = String(value || '');
    return decisions[text] || text.replace(/_/g, ' ').replace(/^./, function (c) { return c.toUpperCase(); });
  }
  function excerpt(value) {
    var text = String(value || '').replace(/\s+/g, ' ').trim();
    if (text.length <= 280) return text;
    var cut = text.lastIndexOf(' ', 280);
    return text.slice(0, cut > 200 ? cut : 280) + '…';
  }
  function card(d, terms, u) {
    var split = u.split, esc = u.esc;
    var decision = split(d.respuesta_sentido).map(function (x) {
      return '<span class="tag s" data-decision="' + encodeURIComponent(x) + '">' + esc(label(x)) + '</span>';
    }).join('');
    var tags = split(d.pregunta_tipo).map(function (x) {
      return '<span class="tag">' + esc(label(x)) + '</span>';
    }).concat(split(d.ley).map(function (x) {
      return '<span class="tag">Ley ' + esc(x) + '</span>';
    })).join('');
    var pdf = /^OPI-\d+\.pdf$/.test(d.archivo || '')
      ? '<a class="opi-pdf" href="../pdf/' + encodeURIComponent(d.archivo) + '" target="_blank" rel="noopener noreferrer">Ver dictamen original ↗<span class="anc-sr"> (abre en otra pestaña)</span></a>' : '';
    var preview = d.respuesta_texto
      ? '<div class="opi-answer-preview"><span class="opi-eyebrow">Respuesta · extracto</span><p>' + u.hl(excerpt(d.respuesta_texto), terms) + '</p></div>' : '';
    return '<article class="card opi-card">' +
      '<div class="opi-card-top"><h2 class="num">OPI ' + esc(d.OPI) + '</h2><div class="opi-decisions">' + decision + '</div>' + pdf + '</div>' +
      '<p class="preg">' + u.hl(d.pregunta_texto, terms) + '</p>' + preview +
      '<div class="tags opi-tags">' + tags + '</div>' +
      '<details class="opi-details"><summary>Ver respuesta y fundamentos</summary><div class="body">' +
      u.field('Respuesta de la CNDC', d.respuesta_texto, terms) +
      u.field('Fundamento de la decisión', d.CAUSA_ratio_decidendi, terms) +
      u.field('Hecho determinante', d.hecho_determinante, terms) +
      u.field('Criterio', label(d.causa_criterio).replace(/\|/g, ' · '), terms) +
      u.field('Argumento del consultante', d.argumento_consultante, terms) +
      u.field('Medidas accesorias', label(d.medidas_accesorias).replace(/\|/g, ' · '), terms) +
      u.field('Fundamento normativo', d.fundamento_normativo.replace(/\|/g, ' · '), terms) +
      u.listField('Precedentes citados', split(d.precedentes), terms) +
      u.listField('Normas invocadas', d.normas_lista, terms) +
      u.field('Expediente', d.expediente, terms) +
      u.field('Párrafos fuente', d.parrafos.replace(/\|/g, ', '), terms) +
      u.field('Archivo', d.archivo, terms) +
      u.field('Confianza de la extracción automática', label(d.confianza), terms) +
      '</div></details></article>';
  }
  window.OPIUI = { label: label, excerpt: excerpt, card: card };
})();
