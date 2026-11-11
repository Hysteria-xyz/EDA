r"""sacar_xml -- rearmar un XML de Data.dat a partir de lo que volcó `volcar_inflados.py`.

El juego descomprime cada archivo de `Data.dat` en bloques de 7680 B, uno detrás del otro (se
ven seguidos en `_trabajo/inflados/indice.tsv`). Esto busca el bloque donde empieza la raíz pedida
y concatena los siguientes hasta su cierre, y lo deja en `_trabajo/datos/<nombre>.xml`.

    py herramientas\sacar_xml.py SHOP Product          # Data\Product.xml (la tienda)
    py herramientas\sacar_xml.py ITEMTYPELIST ItemTypeList
    py herramientas\sacar_xml.py control

⚠ Sólo encuentra lo que el juego descomprimió en la ÚLTIMA corrida del volcador (el índice se
  reescribe en cada corrida, desde el bloque 1). `Product.xml` se carga al arrancar.

★ El control: la raíz conocida (SHOP) sale con su cierre y 66 productos (`<PRODUCTS NUM="66">`
  lo dice el mismo archivo), y una raíz que no existe NO sale.
"""
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFLADOS = os.path.join(RAIZ, "_trabajo", "inflados")
DATOS = os.path.join(RAIZ, "_trabajo", "datos")


def bloques():
    """Los archivos de bloque de la última corrida, en orden."""
    lineas = open(os.path.join(INFLADOS, "indice.tsv"), encoding="utf-8").read().splitlines()
    ult = max(i for i, l in enumerate(lineas) if l.startswith("#"))
    for l in lineas[ult + 1:]:
        p = l.split("\t")
        if len(p) >= 6 and p[5]:
            yield os.path.join(INFLADOS, p[5])


def sacar(raiz):
    abre, cierra = b"<" + raiz.encode(), b"</" + raiz.encode() + b">"
    junto = None
    for ruta in bloques():
        try:
            b = open(ruta, "rb").read()
        except OSError:
            continue
        if junto is None:
            i = b.find(abre)
            if i < 0 or b[i + len(abre):i + len(abre) + 1] not in (b" ", b">", b"\r", b"\n"):
                continue
            x = b.rfind(b"<?xml", 0, i)
            junto = b[x if x >= 0 else i:]
        else:
            junto += b
        j = junto.find(cierra)
        if j >= 0:
            return junto[:j + len(cierra)]
    return None


def control():
    ok = []
    x = sacar("SHOP")
    n = len(re.findall(rb"<Product ", x or b""))
    dice = re.search(rb'<PRODUCTS NUM="(\d+)"', x or b"")
    ok.append(bool(x and x.endswith(b"</SHOP>") and dice and n == int(dice.group(1))))
    print("  %s SHOP: %s productos, el archivo dice %s" % ("✅" if ok[-1] else "⛔", n,
                                                         dice and dice.group(1).decode()))
    ok.append(sacar("NO_EXISTE_ESTA_RAIZ") is None)
    print("  %s ★ el revés: una raíz que no existe no sale" % ("✅" if ok[-1] else "⛔"))
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    if a and a[0] == "control":
        return control()
    if len(a) < 2:
        print(__doc__)
        return 2
    x = sacar(a[0])
    if x is None:
        print("⛔ no está <%s> en la última corrida del volcador" % a[0])
        return 1
    os.makedirs(DATOS, exist_ok=True)
    ruta = os.path.join(DATOS, a[1] + ".xml")
    open(ruta, "wb").write(x)
    print("★ %s (%d B)" % (ruta, len(x)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
