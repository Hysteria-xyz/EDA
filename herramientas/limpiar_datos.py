r"""limpiar_datos -- borrar del exe desempacado el estado que era de UNA corrida.

El problema (medido el 10-nov, `documentacion/MEDICIONES.md`): el exe que armamos sale de un
VOLCADO DE MEMORIA del juego andando, no del archivo. O sea que sus variables globales no tienen
el valor INICIAL, tienen el que tenían a los 25 segundos de juego: punteros al heap de esa corrida,
handles, ids de hilo. Al arrancar de nuevo, el juego mira una de esas variables, la ve distinta de
cero, cree que el objeto ya existe y lo usa — y ahí explota.

Así se cayó `EDA_libre.exe` en `0x0045BF6B`:

    mov eax, [0x931b08]     ; un puntero del heap de la corrida que volcamos
    test eax, eax
    je  crear_el_objeto     ; ← el camino que QUERÍAMOS
    lea esi, [eax + 0x18]
    cmp [esi], 0            ; ⛔ C0000005: esa dirección no existe en este proceso

Cómo se distingue el valor inicial del estado de la corrida, sin suponer nada: **con dos volcados
de dos corridas distintas**. Un valor que viene del archivo sale IGUAL las dos veces; un puntero
del heap, un handle o un id de hilo salen DISTINTOS. Entonces: todo dword del área de datos que
no se repite entre corridas es estado de la corrida, y se pone en CERO para que el juego lo vuelva
a crear (es lo que hace el propio código: `if (!global) global = crear()`).

Qué NO se toca, y por qué (los dos salieron de la medición, no de una suposición):
  - la sección de código: ahí los 41 dwords que difieren son los DESPLAZAMIENTOS de los `call`
    desviados (21 caen exactamente sobre un sitio de la lista y los otros 20 son el dword de al
    lado, porque el desplazamiento cruza el límite). Ésos los arregla `desempacar.py`;
  - la sección del IAT del juego: los dwords que difieren son direcciones DENTRO de una DLL del
    sistema, que cambian de corrida en corrida porque las DLL se cargan en otro lado. Ésos los
    rellena el cargador de Windows con la tabla de imports que armamos.

    py herramientas\limpiar_datos.py                  # usa los dos volcados completos
    py herramientas\limpiar_datos.py <volcado1> <volcado2>

Deja `_trabajo/datos_de_corrida.txt` (una dirección por línea), que lee `desempacar.py construir`.
"""
import os
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import emular_stub as E                                      # noqa: E402

BASE = 0x400000
TRABAJO = os.path.join(RAIZ, "_trabajo")
SALIDA = os.path.join(TRABAJO, "datos_de_corrida.txt")
LISTOS = os.path.join(TRABAJO, "listos_temprano.txt")
CLIENTE = os.path.join(RAIZ, "cliente", "EDA.exe")
# ★ el que tiene que aparecer en la lista: el puntero que hizo explotar al exe en 0x45BF6B.
#   Si un día deja de aparecer, el método dejó de servir y hay que enterarse.
CONTROL = 0x931B08


def secciones():
    d = open(CLIENTE, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    t = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    out = []
    for i in range(n):
        nom, vsz, va = struct.unpack_from("<8sII", d, t + i * 40)
        out.append((nom.rstrip(b"\0").decode(errors="replace") or "(sin nombre)",
                    BASE + va, (vsz + 0xFFF) & ~0xFFF))
    return out


def sitios_desviados():
    r = os.path.join(TRABAJO, "sitios_desviados.txt")
    if not os.path.exists(r):
        sys.exit("[!] falta %s — corré antes: py herramientas\\emular_stub.py sitios" % r)
    return {int(l, 16) for l in open(r) if l.strip()}


def comparar(a, b, sitios, contar=False):
    """Las direcciones del área de DATOS cuyo dword no se repite entre las dos corridas.
    Con `contar` también imprime la tabla por sección."""
    desplazamientos = {s + 1 + k for s in sitios for k in range(4)}
    limpiar, quietas = [], []
    if contar:
        print("%-13s %-8s %8s %8s   %s" % ("sección", "va", "dwords", "difieren",
                                           "qué se hace"))
    for nom, va, tam in secciones():
        da, db = a.leer(va, tam), b.leer(va, tam)
        if not da or not db or len(da) != len(db):
            if contar:
                print("%-13s %08x  ⚠ no está entera en los dos volcados" % (nom, va))
            continue
        nd = len(da) // 4
        x = struct.unpack("<%dI" % nd, da[:nd * 4])
        y = struct.unpack("<%dI" % nd, db[:nd * 4])
        dif = [va + i * 4 for i in range(nd) if x[i] != y[i]]
        # ¿es la sección del código? se reconoce por tener sitios desviados adentro
        if any(va <= s < va + tam for s in sitios):
            if contar:
                sobre = sum(1 for d in dif if d in desplazamientos)
                print("%-13s %08x %8d %8d   código: %d/%d sobre un `call` desviado → "
                      "los arregla desempacar" % (nom, va, nd, len(dif), sobre, len(dif)))
            continue
        if contar:
            print("%-13s %08x %8d %8d   ← datos: se ponen en CERO"
                  % (nom, va, nd, len(dif)))
        if not dif:
            quietas.append((nom, nd))
        limpiar += dif
    limpiar.sort()
    return limpiar, quietas


def main():
    v1 = sys.argv[1] if len(sys.argv) > 2 else os.path.join(TRABAJO, "volcado", "eda_2_total")
    v2 = sys.argv[2] if len(sys.argv) > 2 else os.path.join(TRABAJO, "volcado", "eda_3")
    print("volcado 1: %s\nvolcado 2: %s\n" % (v1, v2))
    a, b = E.Memoria(v1), E.Memoria(v2)
    sitios = sitios_desviados()
    limpiar, quietas = comparar(a, b, sitios, contar=True)

    print("\n★ dwords que se van a poner en cero: %d" % len(limpiar))
    bien = CONTROL in limpiar
    print("   control: %08x (el puntero que explotaba en 0x45BF6B) %s"
          % (CONTROL, "está en la lista ✅" if bien else "NO está ⛔"))
    # ★ el control al revés — el caso que TIENE que dar vacío: un volcado contra
    #   SÍ MISMO. Si de ahí saliera una sola dirección, el que mide está roto
    #   (el lector, el recorrido de las secciones o el alineado) y la lista no vale nada.
    vacio, _ = comparar(a, a, sitios)
    print("   control al revés: el mismo volcado contra sí mismo da %d direcciones %s"
          % (len(vacio), "✅" if not vacio else "⛔"))
    # y las secciones donde las dos corridas coinciden ENTERAS son datos del archivo: el
    # método no marca ni una. Eso dice que no marca por el solo hecho de ser "datos".
    print("   secciones idénticas las dos veces: %d (%d dwords, 0 marcados)"
          % (len(quietas), sum(n for _, n in quietas)))
    if not bien or vacio:
        print("\n⛔ el control no pasa: no se escribe nada.")
        return 1
    open(SALIDA, "w").write("".join("%08x\n" % d for d in limpiar))
    print("\n   -> %s" % SALIDA)

    # ★ Y de paso, LA SEÑAL de que ASProtect ya terminó de escribir los datos, que es lo que
    #   necesita `volcar_todo.py --temprano` para saber cuándo volcar.
    #   Un dword que sale IGUAL y NO CERO en las dos corridas tardías es un dato del archivo: ése
    #   es su valor final. Si en el proceso vivo ya tiene ese valor, esa parte ya está escrita.
    #   ⚠ Hizo falta porque el primer disparador —«los 694 `call` ya están desviados»— resultó
    #     DEMASIADO TEMPRANO: a los 0,06 s las secciones 0x88A000 y 0x90C000 tenían todavía 63.965
    #     y 12.296 dwords en cero que después valen algo fijo (`.data`, en cambio, ya estaba
    #     entera). O sea que desviar los `call` NO es lo último que hace ASProtect.
    muestra = []
    for nom, va, tam in secciones():
        if any(va <= x < va + tam for x in sitios):
            continue
        da, db = a.leer(va, tam), b.leer(va, tam)
        if not da or not db or len(da) != len(db):
            continue
        nd = len(da) // 4
        x = struct.unpack("<%dI" % nd, da[:nd * 4])
        y = struct.unpack("<%dI" % nd, db[:nd * 4])
        # ⚠ y NO sirven de testigo las direcciones de DLL (los casilleros del IAT): coinciden en
        #   los dos volcados porque Windows carga las DLL en el mismo lugar mientras no se
        #   reinicie, pero en otra corrida pueden cambiar y entonces el testigo nunca se cumple.
        fijos = [i for i in range(nd)
                 if x[i] == y[i] and x[i] != 0 and not 0x50000000 <= x[i] < 0x80000000]
        if not fijos:
            continue
        # ⚠ la muestra tiene que ser GRANDE y repartida: con 24 por sección el volcado temprano
        #   salía con 245 dwords de 0x90C000 todavía en cero. Con ~400 por sección el sondeo
        #   sigue costando pocos milisegundos y cubre mucho mejor.
        paso = max(len(fijos) // 400, 1)
        muestra += [(va + i * 4, x[i]) for i in fijos[::paso][:400]]
    open(LISTOS, "w").write("".join("%08x %08x\n" % w for w in muestra))
    print("   -> %s (%d dwords testigo de «esto ya está escrito»)" % (LISTOS, len(muestra)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
