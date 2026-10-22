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


class ManifestPreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=SCRIPT.with_name('preparar_manifiesto.py')
        spec=importlib.util.spec_from_file_location('prepare',path); cls.mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.mod)

    def source(self,url,kind='prior_notification'):
        return {'Documento ID':'D0001','Caso':'M.10341','Título':'Aviso','Tipo original':kind,'URL del documento':url}

    def test_oj_table_of_contents_is_never_treated_as_individual_pdf(self):
        r=self.mod.classify(self.source('https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ%3AC%3A2022%3A327%3ATOC'))
        self.assertEqual(r['formato'],'indice_do'); self.assertEqual(r['url'],''); self.assertTrue(r['url_referencia'])

    def test_individual_pdf_url_is_preserved(self):
        url='https://ec.europa.eu/competition/mergers/cases1/202235/M_10341_8468325_1420_3.pdf'
        r=self.mod.classify(self.source(url,'clearance_decision'))
        self.assertEqual(r['url'],url); self.assertEqual(r['formato'],'pdf'); self.assertEqual(r['grupo'],'nucleo')

    def test_html_metadata_is_not_promoted_to_full_decision(self):
        r=self.mod.classify(self.source('https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026M12161','full_decision_record'))
        self.assertEqual(r['grupo'],'referencia'); self.assertEqual(r['formato'],'html')


if __name__=='__main__': unittest.main(verbosity=2)
