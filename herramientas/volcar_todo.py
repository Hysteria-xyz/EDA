r"""volcar_todo -- volcar TODA la memoria del juego vivo (no sólo la imagen del exe).

Para qué: `volcar_exe.py` saca la imagen desempacada de `EDA.exe`, que alcanza para LEER el código.
Pero la VM de ASProtect no vive ahí: vive en memoria que pide al arrancar, y para emularla
(`emular_stub.py`) hacen falta también las DLL y esas regiones sueltas. Eso es esto: ~91 MB.

    py herramientas\volcar_todo.py --abrir            # abre el juego, espera, vuelca y lo cierra
    py herramientas\volcar_todo.py                    # con el juego ya abierto
    py herramientas\volcar_todo.py --salida _trabajo\volcado\eda_3

Deja en la carpeta de salida:
    todo.bin     todas las regiones comprometidas, una detrás de la otra
    indice.txt   una línea por región: base  tamaño  offset-en-todo.bin  tipo   (todo en hex)

⚠ Sólo LEE la memoria (ReadProcessMemory): GameGuard bloquea escribir, no leer (medido en R2Beat).
⚠ El juego NO se abre desde `cliente/`: se usa la copia de `_trabajo/juego/` (regla de LEEME.md,
  porque al abrirse crea GameGuard/ y al cerrarse deja EDA.dmp/EDA.rpt).

★ Y para qué sirve tener DOS volcados de DOS corridas: ASProtect pone su VM en una dirección
  distinta cada vez. Si `emular_stub.py` contesta lo mismo para un sitio en los dos volcados, esa
  respuesta no depende de la corrida ⇒ es la buena. Es el control independiente del método.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
JUEGO = os.path.join(RAIZ, "_trabajo", "juego", "EDA.exe")

MEM_COMMIT = 0x1000
# -------- el volcado TEMPRANO (10-nov) --------
# ★ Por qué hace falta: el exe reconstruido saca sus DATOS del volcado, y un volcado a los 25 s
#   trae los valores que las globales tenían A LOS 25 SEGUNDOS — punteros al heap de esa corrida,
#   no los valores iniciales. Así murió en 0x45BF6B (un puntero al heap) y en 0x7E88A5 (la global
#   del locale del CRT, que `limpiar_datos.py` ponía en cero porque es estado de la corrida: pero
#   su valor inicial NO es cero, es una dirección de la imagen, y eso no se recupera comparando
#   volcados).
#   ⇒ Hay que volcar ANTES de que corra el código del juego: cuando ASProtect ya descomprimió las
#   secciones (el código del arranque ya está en su lugar) pero el juego todavía no arrancó.
#   Se reconoce por dos cosas a la vez, sin tocar nada, sólo leyendo:
ARRANQUE = 0x7E3A11                      # el OEP (`__tmainCRTStartup`), MEDICIONES corrida 4
BYTES_ARRANQUE = bytes.fromhex("6a6068e0ab8b00e89b1b0000")   # iguales en los dos volcados
#   y estas globales, que el juego escribe al arrancar, todavía en cero:
TESTIGOS = (0x931B08, 0x94AE64)
# ★★ Y el testigo MÁS SENSIBLE de todos (10-nov): `__tlsindex` del CRT. En el archivo vale
#    0xFFFFFFFF y lo primero que hace el CRT es pedir un índice de TLS y guardarlo ahí. Si ya no
#    vale -1, el CRT arrancó y lo que se lea ya no son valores iniciales.
#    ⚠ Hizo falta porque `limpiar_datos.py` NO lo marcaba: en los dos volcados tardíos valía 7 las
#      dos veces, así que parecía un dato del archivo. Era el agujero del método de los dos
#      volcados: un valor de corrida que sale IGUAL en las dos corridas no se distingue. Comparar
#      el temprano contra el tardío sí lo distingue.
TESTIGOS_DEL_ARCHIVO = ((0x92BE30, 0xFFFFFFFF),)
SIN_ACCESO = 0x01          # PAGE_NOACCESS
GUARDA = 0x100             # PAGE_GUARD


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("__a", wt.DWORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD), ("__b", wt.DWORD)]


def pid_de(nombre):
    salida = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + nombre, "/FO", "CSV", "/NH"],
                            capture_output=True, text=True).stdout
    for l in salida.splitlines():
        p = [c.strip('" ') for c in l.split('","')]
        if len(p) > 1 and p[0].lower() == nombre.lower():
            return int(p[1])
    return None


def leer(h, dir_, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t(0)
    if k32.ReadProcessMemory(h, ctypes.c_void_p(dir_), buf, n, ctypes.byref(got)) and got.value == n:
        return buf.raw
    return None


def sitios_desviados():
    r = os.path.join(RAIZ, "_trabajo", "sitios_desviados.txt")
    return sorted(int(l, 16) for l in open(r)) if os.path.exists(r) else []


def listos_temprano():
    """[(dirección, valor final)] de dwords que son dato del archivo: los escribe `limpiar_datos.py`
    (son los que salen iguales y no cero en dos volcados tardíos)."""
    r = os.path.join(RAIZ, "_trabajo", "listos_temprano.txt")
    if not os.path.exists(r):
        return []
    return [(int(a, 16), int(b, 16)) for a, b in (l.split() for l in r and open(r) if l.strip())]


def esperar_temprano(pid, tope=120):
    """Espera LEYENDO (nunca escribiendo) hasta el momento en que ASProtect ya terminó y el juego
    todavía no arrancó, y ahí suspende el proceso.

    ★ Cómo se sabe que ASProtect terminó, sin suponer, por DOS cosas:

    1. **los desvíos**: los 694 `call` ya tienen su `E8` apuntando afuera de la imagen.
       (Medido: a los 0,1 s de una corrida había 612 hechos y 82 sin tocar, así que esperar un
       rato fijo no sirve.)
    2. ⛔ **y los datos escritos** — esto hizo falta porque (1) solo era DEMASIADO TEMPRANO: a los
       0,06 s las secciones `0x88A000` y `0x90C000` tenían todavía 63.965 y 12.296 dwords en cero
       que después valen algo fijo. Con ese volcado el exe se moría en `0x7E88A5`, porque la
       global del locale del CRT (`0x94AE64`) salía en cero. O sea que desviar los `call` NO es lo
       último que hace ASProtect. Se espera a que los dwords testigo de `limpiar_datos.py` —los
       que son dato del archivo— ya tengan su valor final.

    ★ Y que el juego NO arrancó: los testigos `TESTIGOS` siguen en cero.
    """
    h = k32.OpenProcess(0x0410, False, pid)
    if not h:
        return False
    sitios = sitios_desviados()
    if not sitios:
        print("[temprano] ⛔ falta _trabajo/sitios_desviados.txt")
        k32.CloseHandle(h)
        return False
    muestra = sitios[::max(len(sitios) // 48, 1)]

    def desviados(cuales):
        n = 0
        for x in cuales:
            d = leer(h, x, 5)
            if not d or d[0] != 0xE8:
                return n, False
            t = (x + 5 + int.from_bytes(d[1:5], "little", signed=True)) & 0xFFFFFFFF
            if 0x400000 <= t < 0xA00000:          # todavía apunta adentro de la imagen
                return n, False
            n += 1
        return n, True

    testigos_datos = listos_temprano()
    if not testigos_datos:
        print("[temprano] ⚠ falta _trabajo/listos_temprano.txt (py herramientas\\limpiar_datos.py):"
              " se vuelca con el disparador viejo, que es demasiado temprano")

    def datos_escritos():
        n = 0
        for dir_, val in testigos_datos:
            d = leer(h, dir_, 4)
            if d is None or int.from_bytes(d, "little") != val:
                return n, False
            n += 1
        return n, True

    t0, mejor, mejor_d = time.time(), 0, 0
    while time.time() - t0 < tope:
        n, listo = desviados(muestra)
        mejor = max(mejor, n)
        if not listo:
            continue
        n, listo = desviados(sitios)            # ahora sí, los 694
        mejor = max(mejor, n)
        if not listo:
            continue
        vals = [leer(h, t, 4) for t in TESTIGOS]
        if any(v is None for v in vals):
            continue
        if any(v != bytes(4) for v in vals):
            k32.CloseHandle(h)
            print("[temprano] ⛔ llegó tarde: el juego ya escribió sus globales (%s)"
                  % [v[::-1].hex() for v in vals])
            return False
        hs = k32.OpenProcess(0x0800, False, pid)          # SUSPEND_RESUME
        r = ctypes.WinDLL("ntdll").NtSuspendProcess(wt.HANDLE(hs)) if hs else -1
        if hs:
            k32.CloseHandle(hs)
        k32.CloseHandle(h)
        n, _ = datos_escritos()
        print("[temprano] ★ agarrado a los %.2f s: los %d desvíos hechos y los testigos todavía "
              "en cero · datos del archivo ya escritos: %d de %d (suspender: %s)"
              % (time.time() - t0, len(sitios), n, len(testigos_datos),
                 "ok" if r == 0 else "falló"))
        return r == 0
    k32.CloseHandle(h)
    print("[temprano] ⛔ en %d s ASProtect no terminó (desvíos: %d de %d · datos escritos: "
          "%d de %d)" % (tope, mejor, len(sitios), mejor_d, len(testigos_datos)))
    return False


def valores_iniciales(pid, rodaja=0.002, vueltas=400):
    """★★ Los valores INICIALES de las globales que son estado de la corrida, agarrados con el
    proceso suspendido y avanzado de a poquito.

    Por qué no alcanza con volcar una sola vez (medido el 10-nov): el instante «los 694 `call` ya
    están desviados» es DEMASIADO TEMPRANO —ASProtect todavía no escribió unos 12.000 dwords de las
    secciones de datos— y el instante «ya escribió todo» es DEMASIADO TARDE, porque el juego ya
    arrancó y pisó sus globales. Las dos cosas se solapan.

    ⇒ Entonces: se suspende antes de que el juego arranque y se lo deja correr de a **2 ms**,
    leyendo después de cada tirón. Mientras los testigos sigan en cero, el juego no arrancó y lo
    que se leyó vale: se guarda. Cuando un testigo deja de ser cero, se para y queda **la última
    lectura buena**. Sólo se lee; lo único que se escribe es el suspender/reanudar del proceso.

    Devuelve (lo leído, cuántos datos del archivo ya estaban escritos, cuántos faltaban).
    """
    h = k32.OpenProcess(0x0410, False, pid)
    hs = k32.OpenProcess(0x0800, False, pid)
    nt = ctypes.WinDLL("ntdll")
    testigos_datos = listos_temprano()
    paginas = [p for _, va, tam in secciones_de_datos() for p in range(va, va + tam, 0x1000)]
    ultimo, listos_max, v = {}, 0, 0
    for v in range(vueltas):
        if not limpio(h):
            break                      # el CRT ya arrancó: la vuelta anterior es la buena
        foto = {}
        for p in paginas:
            b = leer(h, p, 0x1000)
            if b is not None:
                foto[p] = b
        ultimo = foto
        n = sum(1 for d, x in testigos_datos
                if (lambda b: b is not None and int.from_bytes(b, "little") == x)(leer(h, d, 4)))
        listos_max = max(listos_max, n)
        if n == len(testigos_datos):
            break                      # ASProtect terminó y el juego no arrancó: el momento ideal
        nt.NtResumeProcess(wt.HANDLE(hs))
        time.sleep(rodaja)
        nt.NtSuspendProcess(wt.HANDLE(hs))
    k32.CloseHandle(h)
    k32.CloseHandle(hs)
    print("[iniciales] %d tirones de %.0f ms · datos del archivo escritos: %d de %d · "
          "páginas leídas: %d" % (v + 1, rodaja * 1000, listos_max, len(testigos_datos),
                                  len(ultimo)))
    return ultimo, listos_max, len(testigos_datos) - listos_max


def limpio(h):
    """¿Lo que hay en memoria son todavía los valores INICIALES? Dos preguntas:
    los testigos que el juego escribe siguen en cero, y los que vienen del archivo
    (`__tlsindex` = -1) todavía tienen su valor."""
    for t in TESTIGOS:
        b = leer(h, t, 4)
        if b is None or b != bytes(4):
            return False
    for t, esperado in TESTIGOS_DEL_ARCHIVO:
        b = leer(h, t, 4)
        # ⚠ vale el valor del archivo, y también CERO: al principio ASProtect todavía no escribió
        #   esa parte. Lo que no vale es cualquier otra cosa: eso ya lo puso el CRT.
        if b is None or int.from_bytes(b, "little") not in (0, esperado):
            return False
    return True


def secciones_de_datos():
    """[(nombre, va, tamaño)] de las secciones del EDA.exe original que NO tienen código."""
    d = open(os.path.join(RAIZ, "cliente", "EDA.exe"), "rb").read()
    pe = int.from_bytes(d[0x3C:0x40], "little")
    n = int.from_bytes(d[pe + 6:pe + 8], "little")
    t = pe + 24 + int.from_bytes(d[pe + 20:pe + 22], "little")
    sitios = set(sitios_desviados())
    out = []
    for i in range(n):
        nom = d[t + i * 40:t + i * 40 + 8].rstrip(b"\0").decode(errors="replace")
        vsz = int.from_bytes(d[t + i * 40 + 8:t + i * 40 + 12], "little")
        va = 0x400000 + int.from_bytes(d[t + i * 40 + 12:t + i * 40 + 16], "little")
        tam = (vsz + 0xFFF) & ~0xFFF
        if any(va <= s < va + tam for s in sitios):
            continue
        out.append((nom or "(sin nombre)", va, tam))
    return out


def volcar(pid, salida):
    h = k32.OpenProcess(0x0410, False, pid)        # VM_READ | QUERY_INFORMATION
    if not h:
        sys.exit("[!] no pude abrir el proceso %d (error %d)" % (pid, ctypes.get_last_error()))
    os.makedirs(salida, exist_ok=True)
    mbi = MBI()
    dir_ = 0
    n = leidos = 0
    with open(os.path.join(salida, "todo.bin"), "wb") as bin_, \
         open(os.path.join(salida, "indice.txt"), "w") as idx:
        while dir_ < 0x7FFF0000:
            if not k32.VirtualQueryEx(h, ctypes.c_void_p(dir_), ctypes.byref(mbi),
                                      ctypes.sizeof(mbi)):
                dir_ += 0x1000
                continue
            base, tam = mbi.BaseAddress or 0, mbi.RegionSize
            if mbi.State == MEM_COMMIT and not (mbi.Protect & (SIN_ACCESO | GUARDA)):
                buf = ctypes.create_string_buffer(tam)
                got = ctypes.c_size_t(0)
                if k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, tam,
                                         ctypes.byref(got)) and got.value:
                    idx.write("%x %x %x %d\n" % (base, got.value, leidos, mbi.Type))
                    bin_.write(buf.raw[:got.value])
                    leidos += got.value
                    n += 1
            dir_ = base + tam if tam else dir_ + 0x1000
    k32.CloseHandle(h)
    print("[volcado] %d regiones · %.1f MB → %s" % (n, leidos / 1048576.0, salida))
    return n, leidos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int)
    ap.add_argument("--salida", default=os.path.join(RAIZ, "_trabajo", "volcado", "eda_3"))
    ap.add_argument("--abrir", action="store_true", help="abrir el juego, volcar y cerrarlo")
    ap.add_argument("--espera", type=int, default=25,
                    help="segundos a esperar para que ASProtect termine de desempacar")
    ap.add_argument("--temprano", action="store_true",
                    help="★ volcar ANTES de que corra el juego: para los DATOS iniciales")
    ap.add_argument("--valores-iniciales", action="store_true", dest="iniciales",
                    help="★★ en vez de volcar todo: leer los valores INICIALES de las globales, "
                         "avanzando el proceso de a 2 ms (ver valores_iniciales)")
    a = ap.parse_args()
    if a.iniciales:
        a.temprano = True
    proc = None
    pid = a.pid or pid_de("EDA.exe")
    if a.abrir and not pid:
        if not os.path.exists(JUEGO):
            sys.exit("[!] falta la copia del juego en %s" % JUEGO)
        proc = subprocess.Popen([JUEGO], cwd=os.path.dirname(JUEGO))
        pid = proc.pid
        if a.temprano:
            print("[volcado] juego abierto (pid %d); esperando el momento TEMPRANO" % pid)
            if not esperar_temprano(pid):
                proc.kill()
                return 1
        else:
            print("[volcado] juego abierto (pid %d); esperando %d s a que se desempaque"
                  % (pid, a.espera))
            time.sleep(a.espera)
    if not pid:
        sys.exit("[!] el juego no está abierto (y no se pidió --abrir)")
    if a.iniciales:
        vals, listos, faltan = valores_iniciales(pid)
        if proc:
            proc.kill()
            print("[volcado] juego cerrado")
        carpeta = os.path.join(RAIZ, "_trabajo", "datos_iniciales")
        os.makedirs(carpeta, exist_ok=True)
        with open(os.path.join(carpeta, "paginas.bin"), "wb") as f, \
             open(os.path.join(carpeta, "indice.txt"), "w") as idx:
            off = 0
            for p in sorted(vals):
                f.write(vals[p])
                idx.write("%x %x %x\n" % (p, len(vals[p]), off))
                off += len(vals[p])
        # ★ los controles: (a) los testigos que el juego escribe tienen que estar en CERO y
        #   `__tlsindex` todavía en -1 —si no, esto no son valores iniciales—, y (b) los datos
        #   del archivo tienen que estar ya escritos.
        def v32(a):
            for p, d in vals.items():
                if p <= a < p + len(d):
                    return int.from_bytes(d[a - p:a - p + 4], "little")
            return None
        malos = [t for t in TESTIGOS if v32(t)]
        malos += ["%08x" % t for t, e in TESTIGOS_DEL_ARCHIVO if v32(t) != e]
        print("  %s los testigos dicen que son valores iniciales %s"
              % ("✅" if not malos else "⛔", malos))
        print("  %s datos del archivo ya escritos: %d (faltaban %d)"
              % ("✅" if faltan == 0 else "⚠", listos, faltan))
        print("  -> %s (%d páginas)" % (carpeta, len(vals)))
        return 0 if not malos else 1
    n, leidos = volcar(pid, a.salida)
    if proc:
        proc.kill()
        print("[volcado] juego cerrado")
    # ★ el control: un volcado útil tiene que traer la imagen del exe Y las regiones de ASProtect
    print("  %s regiones" % ("✅" if n > 300 else "⛔ pocas:"), n)
    print("  %s tamaño" % ("✅" if leidos > 50 * 1048576 else "⛔ chico:"),
          "%.1f MB" % (leidos / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
