# -*- coding: utf-8 -*-
"""
Lee todos los PDF de una carpeta, extrae el nombre que figura en cada archivo
(p. ej. "(conc 2047) EMPRESA S.A. S/ ..."), vuelca esos datos a un Excel y
renombra cada PDF a la forma corta  CONC-2047.pdf  usando el número que
aparece en el nombre original.

Ejemplo:
    "(conc 2047) CENCOSUD S.A. Y OTRO S_ NOTIFICACION.pdf"  ->  "CONC-2047.pdf"
    "(OPI 365) WHIRLPOOL ARGENTINA S.R.L. ...pdf"           ->  "OPI-365.pdf"

Requisitos:
    pip install openpyxl

Uso:
    1. Ajustá la sección CONFIGURACIÓN.
    2. Ejecutá:  python renombrar_y_listar.py
"""

import os
import re
from pathlib import Path

from openpyxl import Workbook

# ==========================================================================
# CONFIGURACIÓN  --  editá estos valores
# ==========================================================================

# Carpeta con los PDF a procesar.
CARPETA = str(Path(__file__).parent / "nuevas")

# Nombre del Excel que se genera (se guarda dentro de CARPETA).
EXCEL_SALIDA = "listado_archivos2017_concentraciones.xlsx"

# ¿Renombrar realmente los archivos? Poné False para solo generar el Excel
# y ver qué haría, sin tocar los PDF (modo prueba).
RENOMBRAR = True

# ==========================================================================

# Patrón unificado y flexible:
# - Prefijo opcional: ( o [
# - Palabras clave: CONC, CONCENTRACION, OPI, PLATIN
# - Separadores opcionales: ., -, _, espacios, N°, N
# - Captura de 1 a 5 dígitos
PATRON_CODIGO_GENERAL = re.compile(
    r"[(\[]?\b(CONC|CONCENTRACION|OPI|PLATIN)\b\.?\s*(?:N[°º]?)?\s*[-_\s]?\s*(\d{1,5})\b",
    re.IGNORECASE,
)


def extraer_codigo(nombre_sin_ext):
    """Devuelve (prefijo, numero) a partir del nombre, o (None, None)."""
    m = PATRON_CODIGO_GENERAL.search(nombre_sin_ext)
    if m:
        prefijo = m.group(1).upper()
        numero = m.group(2)

        # Estandariza variaciones de texto largo
        if prefijo == "CONCENTRACION":
            prefijo = "CONC"

        return prefijo, numero

    return None, None


def main():
    if not os.path.isdir(CARPETA):
        print(f"ERROR: no existe la carpeta '{CARPETA}'.")
        return

    # Lista de PDF en la carpeta (ordenada).
    archivos = sorted(
        f for f in os.listdir(CARPETA)
        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(CARPETA, f))
    )

    if not archivos:
        print(f"No se encontraron PDF en '{CARPETA}'.")
        return

    wb = Workbook()
    ws = wb.active
    ws.title = "Archivos"
    ws.append(["Codigo", "Nombre original", "Archivo original", "Archivo nuevo"])

    usados = set()          # nombres nuevos ya asignados (evita choques)
    renombrados = 0
    sin_codigo = 0

    for original in archivos:
        base, ext = os.path.splitext(original)
        prefijo, numero = extraer_codigo(base)

        if prefijo and numero:
            codigo = f"{prefijo}-{numero}"
            nuevo = codigo + ext

            # Evita sobrescribir si dos archivos comparten el mismo código.
            candidato = nuevo
            contador = 2
            while candidato.lower() in usados or (
                candidato != original
                and os.path.exists(os.path.join(CARPETA, candidato))
            ):
                candidato = f"{codigo}_{contador}{ext}"
                contador += 1
            nuevo = candidato
            usados.add(nuevo.lower())
        else:
            # Sin código reconocible: se lista pero no se renombra.
            codigo = ""
            nuevo = original
            sin_codigo += 1
            print(f"  SIN CODIGO (no se renombra): {original}")

        ws.append([codigo, base, original, nuevo])

        # Renombrado físico del archivo.
        if RENOMBRAR and codigo and nuevo != original:
            origen = os.path.join(CARPETA, original)
            destino = os.path.join(CARPETA, nuevo)
            try:
                os.rename(origen, destino)
                print(f"  {original}  ->  {nuevo}")
                renombrados += 1
            except OSError as e:
                print(f"  ERROR al renombrar '{original}': {e}")

    # Ajusta el ancho de las columnas para que se lea cómodo.
    anchos = {"A": 14, "B": 90, "C": 90, "D": 18}
    for col, ancho in anchos.items():
        ws.column_dimensions[col].width = ancho

    ruta_excel = os.path.join(CARPETA, EXCEL_SALIDA)
    wb.save(ruta_excel)

    print()
    print(f"Total de PDF procesados : {len(archivos)}")
    print(f"Renombrados             : {renombrados}"
          f"{'  (modo prueba: no se tocaron archivos)' if not RENOMBRAR else ''}")
    print(f"Sin codigo reconocible  : {sin_codigo}")
    print(f"Excel generado          : {ruta_excel}")


if __name__ == "__main__":
    main()