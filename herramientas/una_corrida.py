r"""una_corrida -- rescatar del log de `cruzar` los sitios que contestó UNO solo de los volcados.

`emular_stub.py cruzar` guarda sólo lo que coincidió en los dos volcados (`apis_cruzadas.json`),
y eso está bien: es la respuesta confirmada. Pero en la corrida del 10-nov quedaron **184 sitios
donde uno de los dos volcados contestó y el otro no pudo** — y eso NO es una contradicción: nadie
dijo lo contrario. Es una respuesta sin confirmar, y vale mucho más que nada (sin ella el exe se
muere en el primer `call` sin resolver que alcanza).

Las que chocan — los dos contestan cosas DISTINTAS — no entran: ésas quedan descartadas.

    py herramientas\una_corrida.py _trabajo\cruzar_694.log

Deja `_trabajo/apis_una_corrida.json`, que `juntar_apis.py` usa en ÚLTIMO lugar y marca como
«una sola corrida» para que se sepa de dónde salió cada una.
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRABAJO = os.path.join(RAIZ, "_trabajo")
SALIDA = os.path.join(TRABAJO, "apis_una_corrida.json")
# «  67/488 00402cb2  KERNEL32.dll!GetACP                      != -»
LINEA = re.compile(r"^\s*\d+/\d+\s+([0-9a-f]{8})\s+(\S+)\s+(==|!=)\s+(\S+)\s*$")


def main():
    logs = sys.argv[1:] or [os.path.join(TRABAJO, "cruzar_694.log")]
    res, choques, iguales, nada = {}, 0, 0, 0
    for ruta in logs:
        if not os.path.exists(ruta):
            sys.exit("[!] no existe %s" % ruta)
        for l in open(ruta, encoding="utf-8", errors="replace"):
            m = LINEA.match(l)
            if not m:
                continue
            sitio, x, _, y = m.group(1), m.group(2), m.group(3), m.group(4)
            if x == "-" and y == "-":        # ⚠ primero éste: si no, «- != -» cuenta como igual
                nada += 1
            elif x == y:
                iguales += 1
            elif x == "-" or y == "-":
                res[sitio] = y if x == "-" else x
            else:
                choques += 1
    print("del log: %d coincidieron (ya están en apis_cruzadas.json)" % iguales)
    print("         %d chocaron entre los dos volcados ⇒ se descartan" % choques)
    print("         %d no los resolvió ninguno de los dos" % nada)
    print("   ★ %d los contestó UNO solo ⇒ entran como «una sola corrida»" % len(res))
    # ★ el control al revés: ninguno de éstos puede estar ya confirmado. Si alguno estuviera,
    #   el que parsea el log se está comiendo líneas de «==» y la lista no vale.
    ya = os.path.join(TRABAJO, "apis_cruzadas.json")
    pisados = []
    if os.path.exists(ya):
        c = json.load(open(ya, encoding="utf-8"))
        pisados = [s for s in res if s in c]
    print("   control al revés: %d de éstos ya estaban confirmados %s"
          % (len(pisados), "✅" if not pisados else "⛔ " + " ".join(pisados[:5])))
    if pisados:
        return 1
    json.dump(dict(sorted(res.items())), open(SALIDA, "w", encoding="utf-8"), indent=1)
    print("\n   -> %s" % SALIDA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
