r"""robados -- qué se ROBÓ ASProtect en cada llamada desviada, y qué hacían esos bytes.

El descubrimiento del 10-nov. Hasta ahora creíamos que todo sitio desviado era una llamada a una
API de Windows: ASProtect reemplazaba el `call dword ptr [casillero]` (6 bytes) por un `call` al
suyo (5 + 1 de relleno) y volvía **a +6**. Pero hay sitios donde los 6 bytes que SIGUEN al sitio
son basura imposible de ejecutar (`salc`, `popal`, `pop es`). Ahí pasa otra cosa:

    ASProtect se robó TAMBIÉN las instrucciones de después, las ejecuta en su VM, y vuelve a +12.

Medido emulando y anotando a qué dirección del juego vuelve cada sitio:

    0x40395F → vuelve a sitio+6    ⇒ una llamada normal, nada robado
    0x7CF0BF → vuelve a sitio+12   ⇒ ★ además se llevó 6 bytes de código real

Por eso esos sitios no resuelven a ninguna API —puede que no haya ninguna API— y por eso el exe
reconstruido se moría en `0x7CF0C6`: estaba ejecutando la basura que quedó en el agujero.

★ Cómo se averigua QUÉ decían esos bytes sin tener el archivo original: se emula el stub con los
registros puestos en **valores marcados** (`eax = 0xAAAA0000`, `ebx = 0xBBBB0000`, …). Cuando la
ejecución vuelve al juego se miran los registros y las escrituras a memoria y se traducen de vuelta
a nombres de registro:

    escribió 4 bytes en [ebx+0x2b7c] con el valor de eax
    ⇒ lo robado era `mov dword ptr [ebx + 0x2B7C], eax`

No es una suposición: es lo que la VM hace de verdad cuando se la deja correr.

    py herramientas\robados.py control            # el control y su revés: un normal y un robado
    py herramientas\robados.py <VA> [<VA> ...]
    py herramientas\robados.py todos              # los 694 → _trabajo/robados.json

⚠ Tarda: cada sitio es una emulación entera (hasta `EDA_SEGUNDOS`, 25 s por omisión).
"""
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import emular_stub as E                                      # noqa: E402

SALIDA = os.path.join(RAIZ, "_trabajo", "robados.json")


#  ⚠ el tope de APIs importa: con 4 la emulación se corta ANTES de volver al juego y todos los
#    sitios dan «no volvió». Con 8 ya vuelven. Se deja 12 de margen.
TOPE = 12


def mirar(mem, sitio, callado=False, anotar=False):
    r = E.secuencia_de(mem, sitio, tope=TOPE, marcas=True)
    if (r.get("vuelve_al_juego") or 6) > 6 and anotar:
        # ★ 2ª pasada, sólo para los robados: ahora sí se anotan las escrituras (es caro).
        r2 = E.secuencia_de(mem, sitio, tope=TOPE, marcas=True, anotar=True)
        if r2.get("vuelve_al_juego") == r.get("vuelve_al_juego"):
            r = r2
    v = r.get("vuelve_al_juego")
    if v is None:
        if not callado:
            print("%08x  no volvió al juego · %s" % (sitio, r["detalle"]))
        return {"vuelve_a": None, "detalle": r["detalle"]}
    robados = v - 6
    out = {"vuelve_a": v, "robados": robados, "detalle": r["detalle"],
           "regs": r.get("regs") or {}, "escrituras": r.get("escrituras") or [],
           # ★ los bytes de argumento de la API DE VERDAD (`validar_apis.py`): las API son
           #   stdcall, así que la diferencia de ESP al volver los dice, medidos.
           "bytes_de_argumento": r.get("bytes_de_argumento"),
           "ultimo_en_dll": r.get("ultimo_en_dll")}
    if callado:
        return out
    if robados <= 0:
        print("%08x  vuelve a sitio+%d = una llamada normal" % (sitio, v))
        return out
    print("%08x  vuelve a sitio+%d  ⇒ ★ SE ROBÓ %d bytes de código" % (sitio, v, robados))
    cambiados = {k: x for k, x in out["regs"].items() if x != k}
    print("     registros que cambiaron: %s" % (cambiados or "ninguno"))
    print("     escrituras: %s" % (" · ".join("[%s] (%d bytes) = %s" % w
                                              for w in out["escrituras"][:8]) or "ninguna"))
    return out


def main():
    mem = E.Memoria()
    arg = sys.argv[1:] or ["control"]
    if arg[0] == "control":
        # ★ el control y su revés de una vez: un sitio que sabemos NORMAL tiene que dar +6, y uno
        #   que sabemos ROBADO tiene que dar más. Si los dos dieran lo mismo, esto no mide nada.
        n = mirar(mem, 0x40395F).get("vuelve_a")
        r = mirar(mem, 0x7CF0BF, anotar=True).get("vuelve_a")
        bien = n == 6 and r is not None and r > 6
        print("\n%s   normal=+%s · robado=+%s" % ("✅ bien" if bien else "⛔ NO distingue", n, r))
        return 0 if bien else 1
    if arg[0] in ("todos", "faltantes", "resueltos"):
        sitios = sorted(mem.sitios())
        if arg[0] == "resueltos":
            # los que YA tienen respuesta: acá la medición sirve para CONTROLARLA (cuántos
            # argumentos lleva de verdad) y para ver a cuáles les robó código.
            f = os.path.join(RAIZ, "_trabajo", "apis_finales.json")
            ya = {int(k, 16) for k in json.load(open(f, encoding="utf-8"))}
            sitios = [x for x in sitios if x in ya]
            print("sólo los que ya tienen respuesta: %d" % len(sitios))
        if arg[0] == "faltantes":
            # sólo los que siguen sin resolver: son los que importan para que el exe siga
            f = os.path.join(RAIZ, "_trabajo", "apis_finales.json")
            ya = {int(k, 16) for k in json.load(open(f, encoding="utf-8"))} if os.path.exists(f) else set()
            sitios = [x for x in sitios if x not in ya]
            print("sólo los que faltan: %d" % len(sitios))
        salida = SALIDA.replace(".json", "_%s.json" % arg[0])
        res = {}
        for i, s in enumerate(sitios, 1):
            print("  %3d/%d " % (i, len(sitios)), end="", flush=True)
            res["%08x" % s] = mirar(mem, s, anotar=True)
            if i % 20 == 0:
                json.dump(res, open(salida, "w", encoding="utf-8"), indent=1)
        json.dump(res, open(salida, "w", encoding="utf-8"), indent=1)
        rob = [k for k, v in res.items() if (v.get("robados") or 0) > 0]
        print("\n★ sitios a los que ASProtect les robó código: %d de %d" % (len(rob), len(sitios)))
        print("   -> %s" % salida)
        return 0
    for a in arg:
        mirar(mem, int(a, 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
