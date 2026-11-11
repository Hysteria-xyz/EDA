r"""contar_piezas -- ¿cuánto del juego ya tenemos? Dos números MEDIDOS sobre el exe, no escritos a mano.

  1. MENSAJES: cuántos mensajes del server sabe recibir el cliente de 2009, y cuántos ya manda el
     nuestro. Los del cliente salen de SU código: cada pantalla registra sus manejadores con
         mov edi, <manejador> · … · push <comando> · push ebx · push edi · push esi · add ecx, 4 · call
     (el lobby, `0x5441FC`), más la escena de carga, que usa `mov [esp+X], <comando>` (`0x534547`:
     0x105E y 0x1058). Los nuestros: los comandos que aparecen en `servidor/*.py` y en el guion de
     `herramientas/reglas_broker.py`.
  2. LLAMADAS A WINDOWS: de las 694 que ASProtect desvió, cuántas quedan SIN resolver en el exe
     desempacado = cuántos `call` siguen yendo a la trampa (0xD0000000 + sitio − 0x400000, ver
     `desempacar.py`).

    py herramientas\contar_piezas.py                 # sobre exe\EDA_limpio.exe (o _trabajo\juego)
    py herramientas\contar_piezas.py --readme        # y actualiza la tabla de README.md
    py herramientas\contar_piezas.py control         # el conteo, con su revés

Sólo LEE el exe.
"""
import glob
import os
import re
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
DESVIADAS = 694                  # los `call` que ASProtect desvió (MEDICIONES, corrida 13)
TRAMPA = 0xD0000000
BASE = 0x400000
RANGOS = ((0x0600, 0x0800), (0x1000, 0x1100), (0x3000, 0x3100))
# ★ la escena de carga los registra de otra forma (`mov [esp+X], cmd`, 0x534547 / 0x534569)
DE_LA_CARGA = {0x105E, 0x1058}
REGISTRO = re.compile(rb"\x68(..)\x00\x00\x53\x57\x56\x83\xc1\x04\xe8", re.S)
REGISTRO_SUELTO = re.compile(rb"\x68(..)\x00\x00(.{3,6})\x83\xc1\x04\xe8", re.S)


def exe_a_usar():
    for r in [os.path.join(RAIZ, "exe", "EDA_limpio.exe"), os.path.join(RAIZ, "_trabajo", "juego", "EDA_limpio.exe")]:
        if os.path.exists(r):
            return r
    raise SystemExit("⛔ no está exe\\EDA_limpio.exe")


def imagen(ruta):
    """El exe como se ve en memoria (secciones en su dirección), sin pefile."""
    d = open(ruta, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n_sec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    base, = struct.unpack_from("<I", d, pe + 24 + 28)
    tam, = struct.unpack_from("<I", d, pe + 24 + 56)
    img = bytearray(tam)
    img[:0x1000] = d[:0x1000]
    secs = []
    for i in range(n_sec):
        o = pe + 24 + opt + 40 * i
        va, = struct.unpack_from("<I", d, o + 12)
        crudo, ptr = struct.unpack_from("<II", d, o + 16)
        vsize, = struct.unpack_from("<I", d, o + 8)
        img[va:va + min(crudo, vsize or crudo)] = d[ptr:ptr + min(crudo, vsize or crudo)]
        secs.append((va, vsize))
    return bytes(img), base, secs


def mensajes_del_cliente(img):
    cmds = set(DE_LA_CARGA)
    for patron in (REGISTRO, REGISTRO_SUELTO):
        for m in patron.finditer(img):
            c = struct.unpack("<H", m.group(1))[0]
            if any(a <= c < b for a, b in RANGOS):
                cmds.add(c)
    return cmds


def mensajes_del_server():
    """Los comandos que el server MANDA: los primeros de cada tupla de respuesta en servidor/ y los
    del guion de reglas_broker (los de entrada se filtran después, al cruzar con el cliente)."""
    out = set()
    for f in glob.glob(os.path.join(RAIZ, "servidor", "*.py")):
        t = open(f, encoding="utf-8").read()
        out |= {int(x, 16) for x in re.findall(r"\(\s*0x([0-9A-Fa-f]{4})\s*,", t)}
    import reglas_broker as R
    for respuestas in R.guion().values():
        out |= {int(r.split(":")[0], 16) for r in respuestas}
    return out


def sin_resolver(img, base, secs):
    va, vsize = secs[0]                                       # la sección de código
    n = 0
    for a in range(va, va + vsize - 5):
        if img[a] == 0xE8:
            destino = (base + a + 5 + struct.unpack_from("<i", img, a + 1)[0]) & 0xFFFFFFFF
            if destino == TRAMPA + (base + a - BASE):
                n += 1
    return n


def contar(ruta=None):
    ruta = ruta or exe_a_usar()
    img, base, secs = imagen(ruta)
    cliente = mensajes_del_cliente(img)
    nuestros = mensajes_del_server() & cliente
    faltan = sorted(cliente - nuestros)
    trampas = sin_resolver(img, base, secs)
    import hashlib
    return {"exe": os.path.relpath(ruta, RAIZ), "md5": hashlib.md5(open(ruta, "rb").read()).hexdigest(),
            "cliente": len(cliente), "hechos": len(nuestros),
            "faltan": faltan, "trampas": trampas, "resueltas": DESVIADAS - trampas}


def tabla(r):
    def barra(a, b):
        llenos = round(20 * a / b)
        return "`%s%s` %d %%" % ("█" * llenos, "░" * (20 - llenos), round(100 * a / b))
    return "\n".join([
        "| pieza | tenemos | avance |",
        "|---|---|---|",
        "| mensajes del server que el cliente sabe recibir | **%d / %d** | %s |"
        % (r["hechos"], r["cliente"], barra(r["hechos"], r["cliente"])),
        "| llamadas a Windows que ASProtect desvió, ya resueltas | **%d / %d** | %s |"
        % (r["resueltas"], DESVIADAS, barra(r["resueltas"], DESVIADAS)),
        "",
        "Faltan estos mensajes: %s. Las llamadas que faltan no se tocan jugando (si el juego llega a"
        " una, la consola dice cuál)." % ", ".join("`%04X`" % c for c in r["faltan"]),
        "",
        "<sub>Medido con `py herramientas\\contar_piezas.py` sobre `%s` (md5 `%s`).</sub>"
        % (os.path.basename(r["exe"]), r["md5"]),
    ])


INICIO, FIN = "<!-- piezas: desde acá lo escribe herramientas/contar_piezas.py -->", "<!-- piezas: hasta acá -->"


def al_readme(r, ruta=os.path.join(RAIZ, "publico", "README.md")):
    t = open(ruta, encoding="utf-8").read()
    assert INICIO in t and FIN in t, "README sin las marcas de la tabla de piezas"
    a, b = t.index(INICIO) + len(INICIO), t.index(FIN)
    open(ruta, "w", encoding="utf-8", newline="\n").write(t[:a] + "\n" + tabla(r) + "\n" + t[b:])
    print("✅ tabla actualizada en %s" % os.path.relpath(ruta, RAIZ))


def control():
    ok = []

    def chequear(n, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok.append(bool(c))
    r = contar()
    img, base, secs = imagen(exe_a_usar())
    cli = mensajes_del_cliente(img)
    chequear("el cliente registra los mensajes CONOCIDOS (0x1012 personaje, 0x1018 lobby, 0x105E largada)",
             {0x1012, 0x1018, 0x105E} <= cli)
    chequear("★ el revés: NO registra los que manda él (0x100F «quién soy», 0x1011)",
             not ({0x100F, 0x1011} & cli))
    chequear("los que el server manda incluyen los medidos en el juego (0x1012, 0x105E, 0x1072)",
             {0x1012, 0x105E, 0x1072} <= mensajes_del_server())
    chequear("sin resolver > 0 y < 694 (%d)" % r["trampas"], 0 < r["trampas"] < DESVIADAS)
    chequear("★ el revés: el EDA.exe de 2009 (empaquetado) no tiene NINGÚN call a la trampa",
             not os.path.exists(os.path.join(RAIZ, "_trabajo", "juego", "EDA.exe"))
             or sin_resolver(*imagen(os.path.join(RAIZ, "_trabajo", "juego", "EDA.exe"))) == 0)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["control"]:
        sys.exit(control())
    res = contar()
    print(tabla(res))
    if "--readme" in a:
        al_readme(res)
