import re
import pandas as pd

def normalizar_carpeta(valor):
    """
    Convierte valores como:
      'CONC 1884', 'CONC. 1953 (PROSUM)', 'CONC.1939 (PROSUM)',
      'OPI 388', 'INC. I. CONC. 1663'
    al formato: 'PREFIJO-numero'
    """
    if pd.isna(valor):
        return valor

    texto = str(valor).strip()

    # Busca el último prefijo alfabético seguido (con o sin espacios/puntos) de un número
    match = re.search(r'([A-Za-z]+)\s*\.?\s*(\d+)(?!.*\d)', texto)
    if not match:
        return texto  # no se pudo parsear, se deja como estaba

    prefijo = match.group(1).upper()
    numero = match.group(2)

    return f"{prefijo}-{numero}"


if __name__ == "__main__":
    # Ejemplo de uso si ya tenés un DataFrame `df` cargado en memoria:
    # df["Carpeta"] = df["Carpeta"].apply(normalizar_carpeta)
    pass
