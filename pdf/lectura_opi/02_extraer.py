#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
02_extraer.py — Etapa 3: extracción semántica con LLM.

Lee opi_segmentado.jsonl (salida del paso 01) y produce opi_extraido.jsonl con
la pregunta de las partes, la respuesta de la CNDC y la CAUSA de la decisión.

Requiere:
    pip install anthropic
    set ANTHROPIC_API_KEY=...        (Windows CMD)
    $env:ANTHROPIC_API_KEY="..."     (PowerShell)

Uso:
    python 02_extraer.py                       # todas
    python 02_extraer.py --limite 15           # muestra de calibración
    python 02_extraer.py --solo 350,312,373    # OPI puntuales
    python 02_extraer.py --hilos 6             # paralelismo

Es reanudable: si opi_extraido.jsonl ya tiene una OPI, la saltea
(usar --rehacer para forzar).
"""
import json, os, sys, re, time, argparse, threading
from concurrent.futures import ThreadPoolExecutor

MODELO = "claude-sonnet-5"
MAX_CHARS_SECCION = 30000   # recorte de guarda para dictámenes muy largos
MAX_TOKENS = 8000           # techo alto: un JSON cortado es un JSON inválido
REINTENTOS = 3              # los fallos de parseo suelen no repetirse

SYSTEM = """Sos un analista de la Comisión Nacional de Defensa de la Competencia (Argentina).
Extraés información estructurada de dictámenes de Opinión Consultiva (OPI).

Reglas:
1. Solo usás lo que está en el texto. Si un campo no surge del texto, poné null.
   Nunca inferís desde tu conocimiento general del derecho de competencia.
2. `causa.ratio_decidendi` es el POR QUÉ, no el QUÉ. "No está sujeta a
   notificación" es el RESULTADO, no la causa. La causa es, por ejemplo, "la
   participación adquirida es minoritaria y pasiva, sin derechos de veto sobre
   la estrategia competitiva de la empresa objeto".
3. La causa casi siempre está en los últimos párrafos de la sección ANÁLISIS,
   inmediatamente antes de la CONCLUSIÓN. Buscá ahí primero.
4. Citás en `trazabilidad.parrafos` los números de párrafo de los que sacaste la causa.
5. Si el dictamen resuelve varias cuestiones, la causa principal es la de la
   cuestión que decide el sentido dispositivo; las demás van en medidas_accesorias.
6. Si hay voto en disidencia o dictamen complementario, extraés el de la MAYORÍA
   y ponés `trazabilidad.requiere_revision_humana` en true.
7. Los campos enumerados (`tipo`, `sentido`, `criterio`) salen EXCLUSIVAMENTE de
   las listas del esquema. Si ninguno encaja, usá "otro" y explicá en
   `hecho_determinante`.
8. Devolvés ÚNICAMENTE un objeto JSON válido conforme al esquema. Sin markdown,
   sin ```json, sin texto antes ni después.
9. IMPORTANTE para que el JSON sea válido: dentro de los valores NUNCA uses
   comillas dobles rectas ("). Si citás texto del dictamen, usá comillas
   tipográficas (« » o “ ”). Tampoco metas saltos de línea dentro de un valor.
10. EMPRESAS: distinguí bien los roles. `compradoras` = quien adquiere el
   control o la participación; `objeto` = la empresa o los activos adquiridos;
   `vendedoras` = quien se desprende. Si una firma aparece con varios roles,
   repetila en cada uno. Usá la razón social completa como figura en el
   dictamen (con S.A., LLC, LIMITED, etc.), sin abreviar ni normalizar.
   Si el dictamen no identifica un rol, dejá la lista vacía.
11. Sé conciso: `texto` y `ratio_decidendi` no deben superar las 80 palabras
   cada uno. No transcribas la conclusión entera, resumila."""

PLANTILLA = """<esquema>
{esquema}
</esquema>

<documento opi="{opi}" ley="{ley}">
### CONSULTA / HECHOS
{hechos}

### PARTES
{partes}

### ANÁLISIS
{analisis}

### CONCLUSIÓN
{conclusion}
</documento>

Extraé el JSON conforme al esquema."""

_lock = threading.Lock()


def recortar(txt, n=MAX_CHARS_SECCION):
    """Conserva inicio y final: la causa vive al final del análisis."""
    txt = (txt or "").strip()
    if len(txt) <= n:
        return txt or "(sin datos)"
    return txt[: n // 2] + "\n\n[... recorte ...]\n\n" + txt[-n // 2 :]


def limpiar_json(s):
    s = s.strip()
    s = re.sub(r'^```(?:json)?\s*|\s*```$', '', s)
    i, j = s.find('{'), s.rfind('}')
    return s[i : j + 1] if i >= 0 and j > i else s


def reparar(s):
    """Arregla los dos defectos típicos: saltos de línea crudos dentro de un
    valor y comillas dobles sin escapar en medio del texto citado."""
    s = re.sub(r'(?<!\\)\n(?=[^"{}\[\]]*")', ' ', s)   # saltos dentro de strings

    out, dentro, i = [], False, 0
    while i < len(s):
        c = s[i]
        if c == '"' and (i == 0 or s[i - 1] != '\\'):
            if not dentro:
                dentro = True
            else:
                # Cierra solo si lo que sigue es puntuación estructural JSON.
                resto = s[i + 1:].lstrip()
                if resto[:1] in (',', '}', ']', ':', ''):
                    dentro = False
                else:
                    out.append('\\"')   # comilla interna: la escapamos
                    i += 1
                    continue
        out.append(c)
        i += 1
    return ''.join(out)


def parsear(txt):
    txt = limpiar_json(txt)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return json.loads(reparar(txt))


def extraer(cli, reg, esquema):
    ultimo = None
    for intento in range(REINTENTOS):
        try:
            return _extraer_una(cli, reg, esquema)
        except Exception as e:
            ultimo = e
            time.sleep(1.5 * (intento + 1))
    raise ultimo


def _extraer_una(cli, reg, esquema):
    sec = reg['secciones']
    # Si falta 'hechos', el análisis suele traer los antecedentes igual.
    msg = cli.messages.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": PLANTILLA.format(
            esquema=esquema,
            opi=reg.get('opi'),
            ley=", ".join(reg.get('ley') or []) or "s/d",
            hechos=recortar(sec.get('hechos')),
            partes=recortar(sec.get('partes'), 8000),
            analisis=recortar(sec.get('analisis')),
            conclusion=recortar(sec.get('conclusion'), 12000),
        )}],
    )
    # La respuesta puede traer bloques de razonamiento antes del texto.
    txt = "".join(b.text for b in msg.content if getattr(b, 'type', None) == 'text')
    if not txt:
        raise ValueError("respuesta sin bloque de texto")
    try:
        out = parsear(txt)
    except Exception:
        # Guarda la respuesta cruda para poder diagnosticarla sin volver a pagar.
        os.makedirs('errores', exist_ok=True)
        with open(os.path.join('errores', reg['archivo'] + '.txt'), 'w',
                  encoding='utf-8') as fh:
            fh.write(txt)
        raise
    out['_archivo'] = reg['archivo']
    out['_opi'] = reg.get('opi')
    out['_expediente'] = (reg.get('expedientes') or [None])[0]
    out['_ley'] = reg.get('ley')
    out['_referencias'] = reg.get('referencias')
    out['_firmantes'] = reg.get('firmantes')
    out['_piezas'] = reg.get('piezas')
    out['_tokens'] = (msg.usage.input_tokens, msg.usage.output_tokens)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--entrada', default='opi_segmentado.jsonl')
    ap.add_argument('--salida', default='opi_extraido.jsonl')
    ap.add_argument('--esquema', default='esquema_opi.json')
    ap.add_argument('--limite', type=int)
    ap.add_argument('--solo', help='lista de números de OPI separados por coma')
    ap.add_argument('--hilos', type=int, default=4)
    ap.add_argument('--rehacer', action='store_true')
    a = ap.parse_args()

    try:
        import anthropic
    except ImportError:
        sys.exit("Falta la librería: pip install anthropic")
    if not os.environ.get('ANTHROPIC_API_KEY'):
        sys.exit("Falta la variable de entorno ANTHROPIC_API_KEY")

    esquema = open(a.esquema, encoding='utf-8').read()
    regs = [json.loads(l) for l in open(a.entrada, encoding='utf-8')]

    if a.solo:
        pedidos = {s.strip() for s in a.solo.split(',')}
        regs = [r for r in regs if str(r.get('opi')) in pedidos]

    hechos = set()
    if os.path.exists(a.salida) and not a.rehacer:
        for l in open(a.salida, encoding='utf-8'):
            try:
                hechos.add(json.loads(l)['_archivo'])
            except Exception:
                pass
        regs = [r for r in regs if r['archivo'] not in hechos]
        if hechos:
            print(f"Reanudando: {len(hechos)} ya extraídas, faltan {len(regs)}.")

    if a.limite:
        regs = regs[: a.limite]
    if not regs:
        print("Nada para procesar.")
        return

    cli = anthropic.Anthropic()
    fh = open(a.salida, 'a' if hechos and not a.rehacer else 'w', encoding='utf-8')
    ok = err = 0
    tin = tout = 0

    def tarea(reg):
        nonlocal ok, err, tin, tout
        try:
            r = extraer(cli, reg, esquema)
        except Exception as e:
            with _lock:
                err += 1
                print(f"  ERROR {reg['archivo']}: {type(e).__name__}: {e}", file=sys.stderr)
            return
        with _lock:
            ok += 1
            tin += r['_tokens'][0]; tout += r['_tokens'][1]
            fh.write(json.dumps(r, ensure_ascii=False) + '\n'); fh.flush()
            print(f"  [{ok+err}/{len(regs)}] OPI {r['_opi']:>4} "
                  f"{(r.get('respuesta_cndc') or {}).get('sentido')}")

    print(f"Extrayendo {len(regs)} OPI con {MODELO} ({a.hilos} hilos)...")
    with ThreadPoolExecutor(max_workers=a.hilos) as ex:
        list(ex.map(tarea, regs))
    fh.close()

    costo = tin / 1e6 * 3 + tout / 1e6 * 15
    print(f"\nListo: {ok} ok, {err} errores -> {a.salida}")
    print(f"Tokens: {tin:,} in / {tout:,} out  (~US$ {costo:.2f})")


if __name__ == '__main__':
    main()
