"""Pruebas del validador de fichas con una plantilla, fichas y texto extraído mínimos."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

AQUI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AQUI))  # validar_fichas importa inventario_casos
SPEC = importlib.util.spec_from_file_location("validar_fichas", AQUI / "validar_fichas.py")
vf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vf)

PLANTILLA = """# Plantilla

**Tipo de efecto (`tipo_efecto`)**
- `horizontal_no_coordinado`: unilateral.
- `vertical_cierre_insumos`: insumos.

**Tipo de remedio (`tipo_remedio`):** `estructural`, `conductual`, `mixto`.

**Subtipo de remedio (`subtipo_remedio`)**
- `desinversion_negocio`: negocio.
- `acceso`: acceso.
- `no_discriminacion`: trato igual.

**Comprador previo (`comprador_previo`)**
- `upfront_buyer`: antes.
- `no_aplica`: no es venta.

**Trustee (`trustee`):** `monitoreo`, `monitoreo_y_desinversion`, `no`.

**Cláusula de revisión (`clausula_revision`):** `si`, `no`.

## Columnas de `relaciones.csv`

| Columna | Contenido |
|---|---|
| `caso_id` | M.xxxxx |
"""

FICHA = """# M.10001 — A / B

| **Documentos** | `M.10001_DEC_01` (decisión, 6 p.), `M.10001_POST_01` (aprobación) |

## Problemas

### P1 — Mercado de algo

- Cuotas altas (DEC párrs. 2–3 [pp. 1–2], 5 [p. 3]) y cierre (DEC párr. 4 [p. 2] y 6 [p. 3]).

## Remedios

### R1 — Venta del negocio

- Venta (COMP cl. 1 [p. 5]; DEC párr. 7 [p. 4]). Comprador aprobado (`M.10001_POST_01` [p. 1]).
- En el texto se citan con "COMP cl." y la página.
"""

PAGINAS_DEC = [
    "(1) Las partes.\n(2) La operación de 2022.\n",
    "(3) Cuotas [40-50]%.\n En (2021) hubo cambios.\n(4) Cierre.\n",
    "(5) Más cuotas.\nTable 1 — Cuotas\n(6) Conclusión.\n",
    "(7) Compromisos ofrecidos.\n",
    "ANNEX\nCOMMITMENTS\n1. Definitions\n2. Divestment\n",
    "3. Trustee\n",
]


def fila(**kw) -> dict:
    base = {
        "caso_id": "M.10001", "problema_id": "P1", "mercado": "Algo", "ambito_geografico": "EEE",
        "tipo_efecto": "horizontal_no_coordinado", "mecanismo": "Cuotas altas", "remedio_id": "R1",
        "tipo_remedio": "estructural", "subtipo_remedio": "desinversion_negocio", "obligacion": "Vender",
        "duracion": "10 años", "comprador_previo": "upfront_buyer", "trustee": "monitoreo_y_desinversion",
        "clausula_revision": "si", "cita_problema": "DEC párrs. 2–3 [pp. 1–2]",
        "cita_remedio": "COMP cl. 2 [p. 5]", "cita_suficiencia": "DEC párr. 7 [p. 4]", "notas": "",
    }
    base.update(kw)
    return base


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.plantilla = self.dir / "PLANTILLA.md"
        self.plantilla.write_text(PLANTILLA, encoding="utf-8")
        self.vocab = vf.leer_vocabularios(self.plantilla)

    def texto_extraido(self, ocr: set[int] = frozenset()) -> Path:
        carpeta = self.dir / "texto_extraido"
        (carpeta / "documentos").mkdir(parents=True, exist_ok=True)
        docs = {"M.10001_DEC_01": PAGINAS_DEC, "M.10001_POST_01": ["Woodward aprobado."]}
        with (carpeta / "documentos.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, ["documento_id", "paginas_compromisos", "json"])
            w.writeheader()
            for doc_id, paginas in docs.items():
                ruta = f"documentos/{doc_id}.json"
                datos = {"paginas": [{"pagina_pdf": i, "texto": t,
                                      "origen_texto": "ocr" if doc_id.endswith("DEC_01") and i in ocr else "pdf"}
                                     for i, t in enumerate(paginas, 1)]}
                (carpeta / ruta).write_text(json.dumps(datos), encoding="utf-8")
                w.writerow({"documento_id": doc_id, "json": ruta})
            w.writerow({"documento_id": "M.10001_COMP_01", "paginas_compromisos": "5–6",
                        "json": "documentos/M.10001_DEC_01.json"})
        return carpeta


class VocabularioYFormato(Base):
    def test_lee_listas_con_viñetas_y_en_linea(self):
        self.assertEqual(self.vocab["tipo_efecto"], {"horizontal_no_coordinado", "vertical_cierre_insumos"})
        self.assertEqual(self.vocab["tipo_remedio"], {"estructural", "conductual", "mixto"})
        self.assertEqual(self.vocab["trustee"], {"monitoreo", "monitoreo_y_desinversion", "no"})
        self.assertEqual(self.vocab["clausula_revision"], {"si", "no"})
        self.assertNotIn("caso_id", self.vocab)

    def test_vocabulario_real_de_la_plantilla(self):
        vocab = vf.leer_vocabularios()
        self.assertTrue({"tipo_efecto", "tipo_remedio", "subtipo_remedio", "comprador_previo",
                         "trustee", "clausula_revision"} <= set(vocab))
        self.assertIn("cesion_espectro_slots", vocab["subtipo_remedio"])

    def test_expandir_rangos_y_listas(self):
        self.assertEqual(vf.expandir("166–168, 177"), ["166", "167", "168", "177"])
        self.assertEqual(vf.expandir("2.1-2.3"), ["2.1", "2.3"])
        self.assertEqual(vf.expandir("45"), ["45"])

    def test_parsea_citas_compuestas(self):
        citas, errores = vf.parsear_citas(
            "DEC párrs. 166–167 [pp. 45–47], 177 [p. 48] y 192 [p. 50]; COMP cl. 4 [p. 84]; "
            "DEC párrs. 317, 327 [pp. 78, 80] (`M.10001_POST_01` [p. 1]) M.10001_COMP_M01 cl. 3 [p. 5]")
        self.assertEqual(errores, [])
        resumen = [(c["fuente"], c["numeros"], c["paginas"]) for c in citas]
        self.assertEqual(resumen, [
            ("DEC", ["166", "167"], [45, 46, 47]), ("DEC", ["177"], [48]), ("DEC", ["192"], [50]),
            ("COMP", ["4"], [84]), ("DEC", ["317", "327"], [78, 80]),
            ("M.10001_POST_01", [], [1]), ("M.10001_COMP_M01", ["3"], [5]),
        ])

    def test_detecta_citas_mal_formadas(self):
        _, errores = vf.parsear_citas("según DEC párr. 192 sin página y DEC párr. 5 [p. 3–4]")
        self.assertEqual(len(errores), 2)
        self.assertIn("sin número o sin página", errores[0])
        self.assertIn("va 'pp.'", errores[1])

    def test_ignora_menciones_entre_comillas_y_documentos_sin_pagina(self):
        citas, errores = vf.parsear_citas('se citan con "COMP cl." y `M.10001_DEC_01` (decisión, 6 p.)')
        self.assertEqual((citas, errores), ([], []))


class Filas(Base):
    def chequear(self, filas, fichas=None, columnas=vf.COLUMNAS):
        return vf.chequear_filas(filas, columnas, self.vocab, {"M.10001"}, fichas or {"M.10001": FICHA})

    def test_filas_validas(self):
        self.assertEqual(self.chequear([fila()]), [])

    def test_dos_valores_separados_por_punto_y_coma(self):
        self.assertEqual(self.chequear([fila(subtipo_remedio="acceso;no_discriminacion")]), [])

    def test_valor_fuera_de_vocabulario_y_campo_vacio(self):
        errores = self.chequear([fila(tipo_efecto="horizontal", obligacion=" ")])
        self.assertTrue(any("'tipo_efecto' = 'horizontal'" in e for e in errores))
        self.assertTrue(any("'obligacion' vacío" in e for e in errores))

    def test_repetidas_caso_desconocido_e_ids(self):
        errores = self.chequear([fila(), fila(), fila(caso_id="M.99999", problema_id="X")],
                                fichas={"M.10001": FICHA})
        self.assertTrue(any("fila repetida" in e for e in errores))
        self.assertTrue(any("no está en casos.csv" in e for e in errores))
        self.assertTrue(any("deben ser P1, R1" in e for e in errores))
        self.assertTrue(any("M.99999: tiene filas" in e for e in errores))

    def test_ids_de_la_ficha_y_del_csv_coinciden(self):
        errores = self.chequear([fila(remedio_id="R2")])
        self.assertIn("M.10001: R2 está en relaciones.csv pero no como encabezado '### R2' en la ficha", errores)
        self.assertIn("M.10001: '### R1' de la ficha no aparece en relaciones.csv", errores)

    def test_ficha_sin_filas_y_columnas_distintas(self):
        self.assertEqual(self.chequear([], fichas={"M.10001": FICHA}), ["M.10001.md: no tiene filas en relaciones.csv"])
        self.assertEqual(len(self.chequear([fila()], columnas=vf.COLUMNAS[:-1])), 1)


class Verificacion(Base):
    def verificar(self, texto_cita: str, ocr=frozenset()):
        texto = vf.Texto(self.texto_extraido(ocr))
        citas, errores = vf.parsear_citas(texto_cita)
        self.assertEqual(errores, [])
        salida = ([], [])
        for c in citas:
            e, a = vf.verificar_cita(c, "M.10001", texto)
            salida[0].extend(e)
            salida[1].extend(a)
        return salida

    def test_ubica_parrafos_sin_confundir_anios(self):
        texto = vf.Texto(self.texto_extraido())
        rangos = texto.parrafos("M.10001")
        self.assertEqual(rangos["2"], (1, 2))  # empieza en p. 1 y puede seguir en la p. 2
        self.assertEqual(rangos["4"], (2, 3))
        self.assertEqual(rangos["7"], (4, 4))
        self.assertNotIn("2021", rangos)
        self.assertNotIn("1", {n for n, (p, _) in rangos.items() if p >= 5})  # el anexo no cuenta

    def test_citas_correctas(self):
        self.assertEqual(self.verificar(
            "DEC párrs. 2–3 [pp. 1–2], 5 [p. 3]; COMP cl. 2 [p. 5]; COMP cl. 3 [p. 6]; M.10001_POST_01 [p. 1]"),
            ([], []))

    def test_parrafo_en_otra_pagina(self):
        errores, _ = self.verificar("DEC párr. 7 [p. 2]")
        self.assertEqual(errores, ["'DEC párr. 7 [p. 2]': el párrafo (7) está en p. 4"])

    def test_compromisos_fuera_del_anexo_y_clausula_no_encontrada(self):
        errores, avisos = self.verificar("COMP cl. 2 [p. 3]; COMP cl. 9 [p. 5]")
        self.assertEqual(errores, ["'COMP cl. 2 [p. 3]': fuera del anexo de compromisos (pp. 5–6)"])
        self.assertIn("'COMP cl. 9 [p. 5]': no encuentro la cláusula 9 en esas páginas", avisos)

    def test_documento_inexistente_o_pagina_de_mas(self):
        errores, _ = self.verificar("M.10001_POST_01 [p. 3]; M.10001_CP_01 [p. 1]")
        self.assertEqual(len(errores), 2)
        self.assertIn("tiene 1 páginas", errores[0])
        self.assertIn("no está en texto_extraido", errores[1])

    def test_tablas(self):
        self.assertEqual(self.verificar("DEC tabla 1 [p. 3]"), ([], []))
        _, avisos = self.verificar("DEC tablas 1–2 [p. 3]")
        self.assertEqual(avisos, ["'DEC tablas 1–2 [p. 3]': no encuentro la tabla 2 en esas páginas"])

    def test_parrafo_no_ubicado_y_pagina_ocr_son_avisos(self):
        errores, avisos = self.verificar("DEC párr. 50 [p. 3]; DEC párr. 3 [p. 2]", ocr={2})
        self.assertEqual(errores, [])
        self.assertTrue(any("no ubico el párrafo (50)" in a for a in avisos))
        self.assertTrue(any("la p. 2 se leyó por OCR" in a for a in avisos))


class Main(Base):
    def correr(self, filas, ficha=FICHA, texto=True):
        fichas = self.dir / "fichas"
        fichas.mkdir(exist_ok=True)
        (fichas / "M.10001.md").write_text(ficha, encoding="utf-8")
        relaciones = fichas / "relaciones.csv"
        with relaciones.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, vf.COLUMNAS)
            w.writeheader()
            w.writerows(filas)
        argv = ["validar_fichas.py"] + (["--texto", str(self.texto_extraido())] if texto else [])
        salida = io.StringIO()
        with mock.patch.object(vf, "FICHAS", fichas), mock.patch.object(vf, "RELACIONES_CSV", relaciones), \
                mock.patch.object(vf, "PLANTILLA", self.plantilla), \
                mock.patch.object(vf.inv, "leer_csv", return_value={"M.10001": {}}), \
                mock.patch.object(sys, "argv", argv), redirect_stdout(salida):
            codigo = vf.main()
        return codigo, salida.getvalue()

    def test_ok_con_texto(self):
        codigo, salida = self.correr([fila()])
        self.assertEqual(codigo, 0, salida)
        self.assertIn("Chequeos: OK", salida)
        self.assertIn("citas verificadas", salida)

    def test_error_en_la_ficha(self):
        codigo, salida = self.correr([fila()], ficha=FICHA.replace("DEC párr. 7 [p. 4]", "DEC párr. 7 [p. 1]"))
        self.assertEqual(codigo, 1)
        self.assertIn("el párrafo (7) está en p. 4", salida)

    def test_sin_texto_solo_formato(self):
        codigo, salida = self.correr([fila()], texto=False)
        self.assertEqual(codigo, 0, salida)
        self.assertIn("solo formato", salida)


if __name__ == "__main__":
    unittest.main()
