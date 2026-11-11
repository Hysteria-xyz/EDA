# -*- coding: utf-8 -*-
"""¿Alguien tocó el cliente original? Compara `cliente/` contra el md5 de cada archivo anotado en
`documentacion/INVENTARIO_CLIENTE_2009.md`.

    python herramientas/inventario.py            -> compara; sale 1 si algo cambió, falta o sobra
    python herramientas/inventario.py --control  -> ★ el control al revés: altera UN md5 en memoria y
                                                    exige que la comparación lo detecte (si no, la
                                                    herramienta no controla nada)
"""
import hashlib
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # herramientas/ -> dirname doble
CLIENTE = os.path.join(RAIZ, "cliente")
DOC = os.path.join(RAIZ, "documentacion", "INVENTARIO_CLIENTE_2009.md")
# Lo que el launcher/patcher escribe al correr: no es parte de la foto
IGNORAR = ("apply/", "fetch/")


def anotado():
    filas = re.findall(r"^([0-9a-f]{32})\s+(\d+)\s+(.+?)\s*$", open(DOC, encoding="utf-8").read(), re.M)
    return {r: (m, int(n)) for m, n, r in filas}


def actual():
    out = {}
    for base, _dirs, archivos in os.walk(CLIENTE):
        for a in archivos:
            p = os.path.join(base, a)
            rel = os.path.relpath(p, CLIENTE).replace("\\", "/")
            if rel.startswith(IGNORAR):
                continue
            h = hashlib.md5()
            with open(p, "rb") as f:
                for blk in iter(lambda: f.read(1 << 20), b""):
                    h.update(blk)
            out[rel] = (h.hexdigest(), os.path.getsize(p))
    return out


def comparar(esperado, hoy):
    problemas = []
    for r, v in sorted(esperado.items()):
        if r not in hoy:
            problemas.append(f"FALTA     {r}")
        elif hoy[r] != v:
            problemas.append(f"CAMBIÓ    {r}  ({v[0]} -> {hoy[r][0]})")
    for r in sorted(set(hoy) - set(esperado)):
        problemas.append(f"SOBRA     {r}")
    return problemas


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    esp, hoy = anotado(), actual()
    if not esp:
        sys.exit("⛔ el inventario no tiene filas: la expresión no leyó el documento")
    if "--control" in sys.argv:
        r = sorted(esp)[0]
        esp[r] = ("0" * 32, esp[r][1])
        ok = any(r in p for p in comparar(esp, hoy))
        print(("✅ el control detecta el cambio en " if ok else "⛔ el control NO detectó el cambio en ") + r)
        sys.exit(0 if ok else 1)
    prob = comparar(esp, hoy)
    for p in prob:
        print(p)
    print(f"{'⛔' if prob else '✅'} {len(esp)} anotados · {len(hoy)} en cliente/ · {len(prob)} diferencias")
    sys.exit(1 if prob else 0)
