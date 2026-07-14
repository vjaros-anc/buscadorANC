"""
Renombra PDFs tipo CONC/DIC/RESO/OPI a formato normalizado: "CONC-numero.pdf"

Ejemplos:
  1794                 -> CONC-1794.pdf
  1829conc             -> CONC-1829.pdf
  CONC1748resoydic      -> CONC-1748.pdf
  dic860_merged         -> CONC-860.pdf
  reso1798              -> CONC-1798.pdf
  opi344                -> CONC-344.pdf

USO: un solo comando.
  python renombrar_conc.py

Te muestra la lista de cambios propuestos y al final te pregunta
si querés aplicarlos (s/n). No renombra nada hasta que contestes "s".
"""

import re
import os

# --- CONFIGURACION: cambiar esta ruta si hace falta ---
CARPETA = r"C:\Users\Admin\Documents\ANC\descargas_cndc\2024"

PATRON_PREFIJO = re.compile(r'(conc|dic|reso|opi)\D*?(\d{2,5})', re.IGNORECASE)
PATRON_SOLO_NUM = re.compile(r'(\d{2,5})')


def proponer_nombre(nombre_original):
    nombre, ext = os.path.splitext(nombre_original)
    m = PATRON_PREFIJO.search(nombre)
    if m:
        numero = m.group(2)
        return f"CONC-{numero}{ext}"
    m2 = PATRON_SOLO_NUM.search(nombre)
    if m2:
        return f"CONC-{m2.group(1)}{ext}"
    return None


def main():
    if not os.path.isdir(CARPETA):
        print(f"No encuentro la carpeta: {CARPETA}")
        print("Editá la variable CARPETA al principio del archivo.")
        return

    archivos = [f for f in os.listdir(CARPETA) if f.lower().endswith('.pdf')]
    cambios = []
    usados = set()
    sin_match = []

    for f in archivos:
        nuevo = proponer_nombre(f)
        if nuevo is None:
            sin_match.append(f)
            continue
        base = nuevo
        i = 2
        while nuevo.lower() in usados:
            n, ext = os.path.splitext(base)
            nuevo = f"{n}_{i}{ext}"
            i += 1
        usados.add(nuevo.lower())
        cambios.append((f, nuevo))

    if not cambios:
        print("No encontré archivos para renombrar.")
        return

    print(f"Encontré {len(cambios)} archivos para renombrar:\n")
    for original, nuevo in cambios:
        print(f"  {original}  ->  {nuevo}")

    if sin_match:
        print(f"\nSin coincidencia ({len(sin_match)}), estos NO se van a tocar:")
        for f in sin_match:
            print(f"  {f}")

    print()
    respuesta = input("¿Aplicar estos cambios ahora? Escribí 's' para confirmar, cualquier otra tecla para cancelar: ")
    if respuesta.strip().lower() == 's':
        for original, nuevo in cambios:
            os.rename(os.path.join(CARPETA, original), os.path.join(CARPETA, nuevo))
        print("Listo, se renombraron los archivos.")
    else:
        print("Cancelado. No se tocó ningún archivo.")


if __name__ == "__main__":
    main()