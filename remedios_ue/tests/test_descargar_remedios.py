"""Pruebas sin sitios públicos: servidor local o transporte en memoria si no hay sockets."""
import contextlib
import csv
import hashlib
import http.server
import importlib.util
import io
import json
import sys
import tempfile
import threading
import unittest
from unittest import mock
from email.message import Message
from types import SimpleNamespace
import urllib.error
import urllib.parse
from collections import Counter
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'descargar_remedios.py'
spec = importlib.util.spec_from_file_location('descargar_remedios', SCRIPT)
dl = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dl
spec.loader.exec_module(dl)


def pdf(text=b'Fixture local'):
    stream = b'BT /F1 12 Tf 10 10 Td (' + text + b') Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    out = bytearray(b'%PDF-1.4\n'); offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out)); out.extend(f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(out)
    out.extend(b'xref\n0 5\n0000000000 65535 f \n')
    for off in offsets: out.extend(f'{off:010d} 00000 n \n'.encode())
    out.extend(b'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n')
    return bytes(out)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def do_GET(self):
        name = self.path.split('?', 1)[0]
        self.server.calls[name] += 1
        if name == '/redirect.pdf':
            self.send_response(302); self.send_header('Location', '/pagina'); self.end_headers(); return
        if name == '/forbidden.pdf':
            self.send_response(403); self.end_headers(); return
        if name == '/missing.pdf':
            self.send_response(404); self.end_headers(); return
        if name == '/retry.pdf' and self.server.calls[name] == 1:
            self.send_response(503); self.send_header('Retry-After', '0'); self.end_headers(); return
        data = self.server.body
        mime = 'application/pdf'
        if name == '/wrong.pdf' or name == '/pagina':
            data, mime = b'<!doctype html><html><body>Pagina de referencia</body></html>', 'text/html'
        elif name == '/bot.pdf':
            data, mime = b'<html><body>JavaScript is disabled. Verify that you are not a robot</body></html>', 'text/html'
        elif name == '/noeof.pdf':
            data = data.split(b'%%EOF')[0]
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data) + (25 if name == '/truncated.pdf' else 0)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()
        self.close_connection = True


class MemoryResponse(io.BytesIO):
    def __init__(self, data, url, mime, length):
        super().__init__(data)
        self.url = url
        self.headers = Message()
        self.headers['Content-Type'] = mime
        self.headers['Content-Length'] = str(length)

    def getcode(self): return 200
    def geturl(self): return self.url


class MemoryOpener:
    """Mismos escenarios de respuesta; solo se sustituye la frontera de transporte."""
    def __init__(self, server): self.server = server

    def open(self, request, timeout=None):
        url = request.full_url
        name = urllib.parse.urlsplit(url).path
        self.server.calls[name] += 1
        if name == '/redirect.pdf':
            self.server.calls['/pagina'] += 1
            url = url.rsplit('/',1)[0]+'/pagina'
            name = '/pagina'
        if name == '/forbidden.pdf':
            raise urllib.error.HTTPError(url,403,'Forbidden',Message(),io.BytesIO())
        if name == '/missing.pdf':
            raise urllib.error.HTTPError(url,404,'Not Found',Message(),io.BytesIO())
        if name == '/retry.pdf' and self.server.calls[name] == 1:
            headers=Message(); headers['Retry-After']='0'
            raise urllib.error.HTTPError(url,503,'Unavailable',headers,io.BytesIO())
        data,mime=self.server.body,'application/pdf'
        if name in ['/wrong.pdf','/pagina']:
            data,mime=b'<!doctype html><html><body>Pagina de referencia</body></html>','text/html'
        elif name == '/bot.pdf':
            data,mime=b'<html><body>JavaScript is disabled. Verify that you are not a robot</body></html>','text/html'
        elif name == '/noeof.pdf': data=data.split(b'%%EOF')[0]
        return MemoryResponse(data,url,mime,len(data)+(25 if name=='/truncated.pdf' else 0))


class Downloads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memory = False
        try:
            cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        except PermissionError:
            cls.memory = True
            cls.server = SimpleNamespace(calls=Counter(),body=pdf())
            cls.base = 'https://fixture.invalid'
            print('Pruebas HTTP: transporte en memoria; este entorno no permite sockets locales.', file=sys.stderr)
            return
        cls.server.daemon_threads = True
        cls.server.calls = Counter()
        cls.server.body = pdf()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        if not cls.memory:
            cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = self.root / 'manifiesto.csv'
        self.out = self.root / 'salida'
        self.server.calls.clear(); self.server.body = pdf()
        if self.memory:
            patcher=mock.patch.object(dl.urllib.request,'build_opener',side_effect=lambda:MemoryOpener(self.server))
            patcher.start(); self.addCleanup(patcher.stop)

    def manifest_rows(self, paths, *, formats=None, cases=None):
        rows = []
        for i, path in enumerate(paths):
            rows.append({'documento_id':f'D{i+1:04d}', 'caso':cases[i] if cases else 'M.10341',
                         'titulo':f'Documento {i+1}', 'grupo':'nucleo',
                         'formato':formats[i] if formats else 'pdf',
                         'url':self.base+path if path else '', 'url_referencia':''})
        self.write_manifest(rows)
        return rows

    def write_manifest(self, rows):
        with self.manifest.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    def run_cli(self, *extra):
        args=['--manifiesto',str(self.manifest),'--todos','--destino',str(self.out),
              '--pausa','0','--reintento-base','0','--max-espera','0','--timeout','2',
              '--timeout-total','5','--intentos','2',*extra]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return dl.main(args)

    def report(self):
        with (self.out/'reporte.csv').open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

    def test_duplicate_url_is_requested_once_and_both_documents_are_mapped(self):
        self.manifest_rows(['/valid.pdf','/valid.pdf'],cases=['M.10341','M.10262'])
        self.assertEqual(self.run_cli(),0)
        rows=self.report(); self.assertEqual(self.server.calls['/valid.pdf'],1)
        self.assertEqual(rows[0]['archivo'],rows[1]['archivo'])
        self.assertEqual(rows[0]['sha256'],hashlib.sha256(self.server.body).hexdigest())
        self.assertIn('compartidos',rows[0]['archivo'])

    def test_resume_verifies_cache_without_another_request(self):
        self.manifest_rows(['/valid.pdf']); self.assertEqual(self.run_cli(),0)
        self.assertEqual(self.run_cli(),0)
        self.assertEqual(self.server.calls['/valid.pdf'],1)
        self.assertEqual(self.report()[0]['estado'],'ya_descargado')
        self.assertEqual(self.report()[0]['intentos'],'0')

    def test_corrupt_cached_file_is_redownloaded_and_old_copy_preserved(self):
        self.manifest_rows(['/valid.pdf']); self.run_cli()
        file=self.out/self.report()[0]['archivo']; file.write_bytes(b'archivo alterado')
        self.assertEqual(self.run_cli(),0)
        self.assertEqual(self.server.calls['/valid.pdf'],2)
        self.assertEqual(file.read_bytes(),self.server.body)
        self.assertTrue(list((self.out/'_corruptos').iterdir()))

    def test_same_content_under_different_urls_has_one_physical_file(self):
        self.manifest_rows(['/valid.pdf','/alias.pdf']); self.assertEqual(self.run_cli(),0)
        self.assertEqual(len(list((self.out/'archivos').rglob('*.pdf'))),1)
        self.assertEqual(self.report()[1]['estado'],'contenido_reutilizado')
        self.assertEqual(self.report()[0]['archivo'],self.report()[1]['archivo'])

    def test_forced_new_version_preserves_previous_pdf(self):
        self.manifest_rows(['/valid.pdf']); self.run_cli()
        first=self.out/self.report()[0]['archivo']
        self.server.body=pdf(b'Version posterior')
        self.assertEqual(self.run_cli('--forzar'),0)
        self.assertTrue(first.is_file())
        self.assertEqual(len(list((self.out/'archivos').rglob('*.pdf'))),2)
        self.assertNotEqual(str(first),str(self.out/self.report()[0]['archivo']))

    def test_html_response_is_not_saved_as_pdf(self):
        self.manifest_rows(['/wrong.pdf']); self.assertEqual(self.run_cli(),2)
        row=self.report()[0]; self.assertEqual(row['estado'],'html_en_lugar_pdf')
        self.assertEqual(row['http_status'],'200'); self.assertEqual(row['archivo'],'')
        self.assertFalse(list(self.out.rglob('*.pdf')))

    def test_antibot_page_is_detected(self):
        self.manifest_rows(['/bot.pdf']); self.assertEqual(self.run_cli(),2)
        self.assertEqual(self.report()[0]['estado'],'bloqueado')
        self.assertEqual(self.server.calls['/bot.pdf'],1)

    def test_redirect_to_page_keeps_final_url_and_does_not_claim_pdf(self):
        self.manifest_rows(['/redirect.pdf']); self.assertEqual(self.run_cli(),2)
        self.assertEqual(self.report()[0]['url_final'],self.base+'/pagina')
        self.assertEqual(self.report()[0]['estado'],'html_en_lugar_pdf')

    def test_transient_503_is_retried(self):
        self.manifest_rows(['/retry.pdf']); self.assertEqual(self.run_cli(),0)
        self.assertEqual(self.server.calls['/retry.pdf'],2)
        self.assertEqual(self.report()[0]['intentos'],'2')

    def test_403_is_not_retried(self):
        self.manifest_rows(['/forbidden.pdf']); self.assertEqual(self.run_cli(),2)
        self.assertEqual(self.server.calls['/forbidden.pdf'],1)
        self.assertEqual(self.report()[0]['http_status'],'403')

    def test_truncated_transfer_is_not_accepted(self):
        self.manifest_rows(['/truncated.pdf']); self.assertEqual(self.run_cli(),2)
        self.assertEqual(self.server.calls['/truncated.pdf'],2)
        self.assertIn(self.report()[0]['estado'],{'transferencia_incompleta','error_red'})
        self.assertFalse(list(self.out.rglob('*.pdf')))

    def test_missing_eof_is_retried_and_rejected(self):
        self.manifest_rows(['/noeof.pdf']); self.assertEqual(self.run_cli(),2)
        self.assertEqual(self.report()[0]['estado'],'pdf_incompleto')
        self.assertEqual(self.server.calls['/noeof.pdf'],2)

    def test_oversized_response_is_rejected(self):
        self.manifest_rows(['/valid.pdf']); self.assertEqual(self.run_cli('--max-mb','0.0001'),2)
        self.assertEqual(self.report()[0]['estado'],'excede_tamano')
        self.assertEqual(self.server.calls['/valid.pdf'],1)

    def test_dry_run_makes_no_request_or_output_directory(self):
        self.manifest_rows(['/valid.pdf']); self.assertEqual(self.run_cli('--plan'),0)
        self.assertFalse(self.server.calls); self.assertFalse(self.out.exists())

    def test_missing_url_and_html_are_explicit_skips(self):
        self.manifest_rows(['','/pagina'],formats=['sin_url','html'])
        self.assertEqual(self.run_cli(),0)
        self.assertEqual([r['estado'] for r in self.report()],['sin_url','html_no_solicitado'])
        self.assertFalse(self.server.calls)

    def test_optional_html_is_saved_with_html_extension(self):
        self.manifest_rows(['/pagina'],formats=['html'])
        self.assertEqual(self.run_cli('--incluir-html'),0)
        self.assertEqual(self.report()[0]['formato_real'],'html')
        self.assertTrue(self.report()[0]['archivo'].endswith('.html'))

    def test_state_cannot_reuse_file_outside_output_directory(self):
        self.manifest_rows(['/valid.pdf']); self.out.mkdir()
        outside=self.root/'externo.pdf'; outside.write_bytes(self.server.body)
        entry={'archivo':'../externo.pdf','sha256':hashlib.sha256(self.server.body).hexdigest(),
               'bytes':len(self.server.body),'formato_real':'pdf'}
        (self.out/'estado.json').write_text(json.dumps({'version':1,'urls':{dl.url_key(self.base+'/valid.pdf'):entry}}))
        self.assertEqual(self.run_cli(),0); self.assertEqual(self.server.calls['/valid.pdf'],1)
        self.assertEqual(outside.read_bytes(),self.server.body)
        self.assertNotIn('..',self.report()[0]['archivo'])

    def test_duplicate_document_id_is_rejected_before_network(self):
        rows=self.manifest_rows(['/valid.pdf','/alias.pdf']); rows[1]['documento_id']=rows[0]['documento_id']; self.write_manifest(rows)
        self.assertEqual(self.run_cli(),1); self.assertFalse(self.out.exists()); self.assertFalse(self.server.calls)

    def test_existing_lock_prevents_simultaneous_write(self):
        self.manifest_rows(['/valid.pdf']); self.out.mkdir(); lock=self.out/'.descarga.lock'; lock.write_text('otro proceso')
        self.assertEqual(self.run_cli(),1); self.assertTrue(lock.exists()); self.assertFalse(self.server.calls)

    def test_limit_counts_urls_and_preserves_unprocessed_references(self):
        self.manifest_rows(['/valid.pdf','/alias.pdf']); self.assertEqual(self.run_cli('--limite','1'),0)
        self.assertEqual(sum(self.server.calls.values()),1)
        self.assertEqual(self.report()[1]['estado'],'fuera_limite')


    # --- documentos.csv como entrada (inventario de la etapa 2) ---

    def write_inventory(self, rows):
        base = {'doc_id':'', 'caso_id':'M.10341', 'universo':'principal', 'tipo_doc':'DEC', 'titulo':'Documento',
                'idioma':'EN', 'url':'', 'ref':'', 'estado':'localizado_verificado', 'tipo_contenido':'application/pdf',
                'sha256':'', 'paginas_compromisos':''}
        full = [{**base, **r} for r in rows]
        self.manifest = self.root / 'documentos.csv'
        self.write_manifest(full)
        return full

    def test_inventory_shared_pdf_is_named_after_decision_and_checked_against_hash(self):
        sha = hashlib.sha256(self.server.body).hexdigest()
        self.write_inventory([
            {'doc_id':'M.10341_COMP_01', 'tipo_doc':'COMP', 'url':self.base+'/valid.pdf', 'paginas_compromisos':'40–55'},
            {'doc_id':'M.10341_DEC_01', 'url':self.base+'/valid.pdf', 'sha256':sha},
        ])
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(self.server.calls['/valid.pdf'], 1)
        rows = {r['documento_id']: r for r in self.report()}
        self.assertTrue(rows['M.10341_DEC_01']['archivo'].startswith('archivos/M_10341/M.10341_DEC_01_'))
        self.assertEqual(rows['M.10341_COMP_01']['archivo'], rows['M.10341_DEC_01']['archivo'])
        self.assertEqual(rows['M.10341_DEC_01']['coincide_inventario'], 'si')
        self.assertEqual(rows['M.10341_COMP_01']['coincide_inventario'], '')
        self.assertEqual(rows['M.10341_COMP_01']['paginas_compromisos'], '40–55')

    def test_press_release_without_print_pdf_is_not_an_error(self):
        rows = [{'documento_id':'D0001', 'caso':'M.10341', 'titulo':'Comunicado', 'grupo':'comunicados',
                 'formato':'pdf', 'url':self.base+'/missing.pdf', 'url_referencia':'', 'impresion':'si'},
                {'documento_id':'D0002', 'caso':'M.10341', 'titulo':'Otro PDF', 'grupo':'nucleo',
                 'formato':'pdf', 'url':self.base+'/missing.pdf?otro=1', 'url_referencia':'', 'impresion':''}]
        self.write_manifest(rows)
        self.assertEqual(self.run_cli(), 2)  # el 404 de un PDF comun sigue siendo un error
        estados = {r['documento_id']: r['estado'] for r in self.report()}
        self.assertEqual(estados, {'D0001':'sin_version_pdf', 'D0002':'error_http'})
        self.write_manifest(rows[:1])
        self.assertEqual(self.run_cli(), 0)

    def test_inventory_hash_mismatch_is_flagged_but_file_is_kept(self):
        self.write_inventory([{'doc_id':'M.10341_DEC_01', 'url':self.base+'/valid.pdf', 'sha256':'0'*64}])
        self.assertEqual(self.run_cli(), 0)
        row = self.report()[0]
        self.assertEqual(row['estado'], 'descargado'); self.assertEqual(row['coincide_inventario'], 'no')
        self.assertIn('distinto del inventario', row['detalle'])
        self.assertTrue((self.out/row['archivo']).is_file())
        summary = json.loads((self.out/'resumen.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['distintos_del_inventario'], ['M.10341_DEC_01'])


class InventoryConversion(unittest.TestCase):
    """Conversión de documentos.csv y armado del plan, sin red."""

    def plan(self, rows, *extra):
        args = dl.parser().parse_args(['--todos', *extra])
        selected, jobs, statuses = dl.make_plan(dl.filas_desde_inventario(rows), args)
        return selected, jobs, {k: v[0] for k, v in statuses.items()}, {k: v[1] for k, v in statuses.items()}

    def row(self, **kw):
        base = {'doc_id':'M.10341_DEC_01', 'caso_id':'M.10341', 'universo':'principal', 'tipo_doc':'DEC',
                'titulo':'Decisión', 'idioma':'EN', 'url':'https://ec.europa.eu/competition/mergers/cases1/202235/M_10341_8468325_1420_3.pdf',
                'ref':'', 'estado':'localizado_verificado', 'tipo_contenido':'application/pdf', 'sha256':'', 'paginas_compromisos':''}
        return {**base, **kw}

    def test_oj_table_of_contents_is_never_treated_as_individual_pdf(self):
        url = 'https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ%3AC%3A2022%3A327%3ATOC'
        self.assertEqual(dl.formato_de(url), 'indice_do')
        fila = dl.filas_desde_inventario([self.row(tipo_doc='RES_DO', url=url, estado='localizado_no_verificado')])[0]
        self.assertEqual(fila['formato'], 'indice_do'); self.assertEqual(fila['url'], ''); self.assertEqual(fila['url_referencia'], url)

    def test_formats_and_groups(self):
        self.assertEqual(dl.formato_de('https://ec.europa.eu/competition/mergers/cases1/202235/M_10341_8468325_1420_3.pdf'), 'pdf')
        self.assertEqual(dl.formato_de('https://competition-policy.ec.europa.eu/document/download/x_en?filename=brief_2025-2.pdf'), 'pdf')
        self.assertEqual(dl.formato_de('https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026M12161'), 'html')
        self.assertEqual(dl.formato_de('https://example.eu/doc', 'application/pdf'), 'pdf')
        grupos = {t: dl.filas_desde_inventario([self.row(tipo_doc=t)])[0]['grupo'] for t in dl.GRUPO_POR_TIPO}
        self.assertEqual(grupos['DEC'], 'nucleo'); self.assertEqual(grupos['COMP'], 'nucleo')
        self.assertEqual(grupos['MB'], 'analisis'); self.assertEqual(grupos['SENT'], 'referencia')
        self.assertIn('analisis', dl.GRUPOS); self.assertNotIn('referencia', dl.GRUPOS)

    def test_press_release_is_downloaded_as_print_pdf(self):
        self.assertEqual(dl.url_impresion('IP/24/761'),
                         'https://ec.europa.eu/commission/presscorner/api/files/document/print/en/ip_24_761/IP_24_761_EN.pdf')
        self.assertEqual(dl.url_impresion('sin referencia'), '')
        detalle = 'https://ec.europa.eu/commission/presscorner/detail/en/ip_24_761'
        fila = dl.filas_desde_inventario([self.row(tipo_doc='CP', url=detalle, ref='IP/24/761', tipo_contenido='text/html')])[0]
        self.assertEqual(fila['formato'], 'pdf'); self.assertTrue(fila['url'].endswith('/IP_24_761_EN.pdf'))
        self.assertEqual(fila['url_referencia'], detalle)

    def test_unpublished_document_is_skipped_with_inventory_state(self):
        _, jobs, estados, detalles = self.plan([self.row(url='', estado='no_publicado_aun')])
        self.assertEqual(estados['M.10341_DEC_01'], 'sin_url'); self.assertIn('no_publicado_aun', detalles['M.10341_DEC_01'])
        self.assertFalse(jobs)

    def test_blocked_sites_are_skipped_unless_requested(self):
        url = 'https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022M10721'
        rows = [self.row(doc_id='M.10341_RES_DO_M01', tipo_doc='RES_DO', url=url, estado='localizado_no_verificado')]
        _, jobs, estados, _ = self.plan(rows)
        self.assertEqual(estados['M.10341_RES_DO_M01'], 'sitio_bloqueado'); self.assertFalse(jobs)
        _, jobs, estados, _ = self.plan(rows, '--intentar-bloqueados')
        self.assertEqual(estados['M.10341_RES_DO_M01'], 'pendiente'); self.assertEqual(len(jobs), 1)

    def test_review_annex_only_with_flag(self):
        rows = [self.row(), self.row(doc_id='M.3280_DEC_01', caso_id='M.3280', universo='revisiones',
                                     url='https://ec.europa.eu/competition/mergers/cases/decisions/m3280_en.pdf')]
        selected, _, _, _ = self.plan(rows)
        self.assertEqual({r['caso'] for r in selected}, {'M.10341'})
        selected, _, _, _ = self.plan(rows, '--incluir-revisiones')
        self.assertEqual({r['caso'] for r in selected}, {'M.10341', 'M.3280'})

    def test_shared_pdf_main_row_is_the_decision(self):
        url = self.row()['url']
        _, jobs, _, _ = self.plan([self.row(doc_id='M.10341_COMP_01', tipo_doc='COMP', url=url), self.row()])
        self.assertEqual(len(jobs), 1); self.assertEqual(jobs[0]['principal']['documento_id'], 'M.10341_DEC_01')


if __name__=='__main__': unittest.main(verbosity=2)
