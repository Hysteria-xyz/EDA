r"""validar_apis -- cazar las respuestas EQUIVOCADAS midiendo cuántos argumentos lleva la API.

★ El juez (10-nov). Las API de Windows son `stdcall`: las limpia la propia API con su `ret N`.
Entonces, si se emula el stub de un sitio y se lo deja correr **hasta que el control vuelve al
código del juego**, la diferencia de ESP dice **cuántos bytes de argumento tenía la API de
verdad**. Eso es una medición, no una cuenta de los `push` del juego — que no sirve de juez porque
los argumentos se entrelazan entre llamadas (ver `contar_argumentos.py` y MEDICIONES corrida 7).

Después se compara con el `ret N` de la API que dijimos, leído del código de la DLL en el volcado.
Si no coinciden, **la respuesta está mal y hay que sacarla**: una API equivocada limpia la pila de
menos o de más, el `ret` se lleva como dirección de vuelta un argumento que sobró, y el exe se
muere en un lugar que no tiene nada que ver (así nos pasó en `0x7D75AD`, que daba
`CryptReleaseContext` de 2 argumentos donde iba `CryptAcquireContextA` de 5).

    py herramientas\validar_apis.py control
    py herramientas\validar_apis.py            # valida todo lo de _trabajo/apis_finales.json
    py herramientas\validar_apis.py <VA> ...

Deja `_trabajo/apis_mal.json` con los sitios cuya respuesta NO pasa, y `juntar_apis.py` los tira.
⚠ Lo que esto NO puede: cuando la emulación no llega a volver al juego (la API es `MessageBoxA` y
  se queda esperando una ventana, por ejemplo) no hay medición y el sitio queda «sin juzgar».
  Eso no lo condena: sólo quiere decir que este juez no opina.
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
from contar_argumentos import saca                           # noqa: E402

TRABAJO = os.path.join(RAIZ, "_trabajo")
SALIDA = os.path.join(TRABAJO, "apis_mal.json")
TOPE = 12                      # el tope de APIs: con menos la emulación no llega a volver


MEDIDO = {}        # lo que ya midió `robados.py` (para no volver a emular 467 sitios)


def cargar_medido(ruta=None):
    """★ Lee lo que `robados.py resueltos` ya dejó medido en su JSON. Emular los 467 sitios otra
    vez son horas; el dato (bytes de argumento) es el mismo."""
    ruta = ruta or os.path.join(TRABAJO, "robados_resueltos.json")
    if not os.path.exists(ruta):
        return 0
    for k, v in json.load(open(ruta, encoding="utf-8")).items():
        if v.get("bytes_de_argumento") is not None:
            MEDIDO[int(k, 16)] = (v["bytes_de_argumento"], v.get("vuelve_a"))
    return len(MEDIDO)


def medir(mem, sitio):
    """(bytes de argumento medidos, a dónde volvió) o (None, None) si no llegó a volver."""
    if sitio in MEDIDO:
        return MEDIDO[sitio]
    r = E.secuencia_de(mem, sitio, tope=TOPE, marcas=True)
    return r.get("bytes_de_argumento"), r.get("vuelve_al_juego")


# ⚠ EL LÍMITE DEL JUEZ (medido el 11-nov): en 78 de los 234 sitios medidos la diferencia de ESP
#   sale absurda (504, 524, 1068 bytes de argumento). O sea que en esos la VM no deja la pila donde
#   la encontró y la resta no significa nada. No se sabe por qué todavía. Lo honesto es que ahí el
#   juez NO opine: una medición imposible no condena a nadie.
#   ★ El corte sale de CALIBRAR, no de elegirlo a dedo: mirando los 290 sitios medidos, donde la
#   medición COINCIDE con el `ret N` los valores van de 0 a 40 y nunca más; donde NO coincide,
#   arriba de 40 no hay ni un acierto (68, 80, 116, 144, 524, 1980…). Y 40 bytes son 10
#   argumentos, que es lo más que lleva una API que el juego pueda estar llamando
#   (`CreateProcessA` lleva 10). Arriba de ahí la medición no sirve y el juez no opina.
#   ⚠ Esto importó: con el corte en 64 el juez reprobaba `GetFileType` en `0x7EC044` por una
#     medición de 56, cuando el juego empuja UN argumento (`push edi` con el handle que acaba de
#     devolver `GetStdHandle`) y `GetFileType` es exactamente eso. Una acusación falsa saca del
#     exe una respuesta buena.
TOPE_ARG = 40


def juzgar(mem, sitio, api):
    """'ok' | 'mal' | 'sin juzgar', y el detalle."""
    medido, vuelve = medir(mem, sitio)
    if medido is None:
        return "sin juzgar", "la emulación no llegó a volver al juego"
    if medido < 0 or medido > TOPE_ARG or medido % 4:
        return "sin juzgar", "la pila midió %d bytes: imposible, la VM no la dejó donde estaba" % medido
    n = saca(mem, api)
    if n is None:
        return "sin juzgar", "no se pudo leer el `ret N` de %s" % api
    if n * 4 == medido:
        return "ok", "%d argumentos, y vuelve a +%d" % (n, vuelve)
    return "mal", "medido %d bytes de argumento, pero %s saca %d" % (medido, api, n * 4)


def main():
    mem = E.Memoria()
    fin = os.path.join(TRABAJO, "apis_finales.json")
    res = {int(k, 16): v for k, v in json.load(open(fin, encoding="utf-8")).items()} \
        if os.path.exists(fin) else {}
    arg = sys.argv[1:]
    if arg and arg[0] == "control":
        # ★ el control y su revés: una respuesta que SABEMOS buena tiene que dar «ok», y una que
        #   SABEMOS mala tiene que dar «mal». Si las dos dieran igual, este juez no juzga nada.
        bien = juzgar(mem, 0x40395F, "KERNEL32.dll!GetThreadLocale")
        mala = juzgar(mem, 0x40395F, "KERNEL32.dll!lstrlenA")      # 1 argumento donde van 0
        print("  la buena  (GetThreadLocale en 0x40395F): %s · %s" % bien)
        print("  la mala   (lstrlenA en 0x40395F):        %s · %s" % mala)
        ok = bien[0] == "ok" and mala[0] == "mal"
        print("\n%s" % ("✅ el juez distingue" if ok else "⛔ NO distingue: no sirve"))
        return 0 if ok else 1
    n = cargar_medido()
    if n:
        print("  ★ %d sitios ya medidos por `robados.py resueltos`: no se vuelven a emular" % n)
    if arg and arg[0] == "medidos":
        # ★ sólo los que `robados.py` ya midió: no emula nada, contesta al instante. Sirve para ir
        #   viendo el resultado mientras la corrida larga sigue.
        sitios = [s for s in sorted(res) if s in MEDIDO]
        print("  sólo los ya medidos: %d" % len(sitios))
    elif arg:
        sitios = [int(x, 0) for x in arg]
    else:
        sitios = sorted(res)
    # ⚠ ACUMULA: los reprobados de corridas anteriores ya no están en `apis_finales.json`
    #   (los saca `juntar_apis.py`), así que si se pisara el archivo volverían a entrar.
    mal = json.load(open(SALIDA, encoding="utf-8")) if os.path.exists(SALIDA) else {}
    bueno = nada = 0
    for i, s in enumerate(sitios, 1):
        api = res.get(s)
        if not api:
            continue
        v, d = juzgar(mem, s, api)
        print("  %3d/%d %08x %-45s %-11s %s" % (i, len(sitios), s, api, v, d), flush=True)
        if v == "mal":
            mal["%08x" % s] = {"api": api, "por_que": d}
        elif v == "ok":
            bueno += 1
        else:
            nada += 1
        if i % 20 == 0:
            json.dump(mal, open(SALIDA, "w", encoding="utf-8"), indent=1)
    json.dump(mal, open(SALIDA, "w", encoding="utf-8"), indent=1)
    print("\n★ %d bien · %d MAL · %d sin juzgar" % (bueno, len(mal), nada))
    print("   -> %s" % SALIDA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
