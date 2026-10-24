/* csv.js — descarga de CSV desde el navegador (sin servidor), para las páginas nuevas del sitio.
   Separador ";" y UTF-8 con BOM: se abre bien en Excel con configuración regional es-AR.
   Los textos que empiezan con = + - @ (o tabulación / retorno) se prefijan con ' para que Excel no los
   ejecute como fórmula: vienen de la prensa o de planillas y no son de confianza.

   API:  ANCCsv.cell(valor)                  una celda ya escapada
         ANCCsv.build(cabecera, filas)       texto CSV completo (BOM + CRLF); filas = [[…], …]
         ANCCsv.download(nombre, texto)      baja el archivo  */
(function (global) {
  'use strict';

  function cell(v) {
    var s = v === null || v === undefined ? '' : String(v);
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return /[";\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function build(header, rows) {
    var lines = [header.map(cell).join(';')];
    rows.forEach(function (r) { lines.push(r.map(cell).join(';')); });
    return '﻿' + lines.join('\r\n') + '\r\n';
  }

  function download(filename, text) {
    var url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  global.ANCCsv = { cell: cell, build: build, download: download };
})(window);
