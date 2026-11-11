r"""probar_libre -- correr el `EDA_libre.exe` reconstruido y decir HASTA DÓNDE llega.

Sin ASProtect ya no hay anti-debug, así que se puede correr bajo un depurador mínimo y anotar
dónde muere. Lo que importa de la salida: la dirección de la excepción.
  - si cae en un `call <stub>` que quedó sin resolver ⇒ falta esa API (y se dice cuál sitio es)
  - si cae en otro lado ⇒ el problema es otro y hay que mirarlo

    py herramientas\probar_libre.py                       # usa _trabajo/juego/EDA_libre.exe
    py herramientas\probar_libre.py --exe <ruta> --segundos 30

⚠ Se corre desde `_trabajo/juego/` (la copia), nunca desde `cliente/` — regla de LEEME.md.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import shutil
import struct
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

CONSTRUIDO = os.path.join(RAIZ, "_trabajo", "volcado", "eda_1", "EDA_libre.exe")
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
EXCEPCION, CREA_HILO, SALIDA_PROC, CARGA_DLL = 1, 2, 5, 6


def hilo_de(tid, hilos):
    """⚠ El handle del hilo que tiró la excepción. Hacía falta porque sólo se guardaba el
    del hilo principal, y los crashes que importan pasan en OTROS hilos: sin esto no se
    podía leer su pila ni saltear su trampa, y las trampas de esos hilos no se veían."""
    h = hilos.get(tid)
    if h:
        return h
    h = k32.OpenThread(0x1FFFFF, False, tid)        # THREAD_ALL_ACCESS
    if h:
        hilos[tid] = h
    return h
SEGUIR, NO_MANEJADA = 0x00010002, 0x80010001


class SI(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("r1", wt.LPWSTR), ("d", wt.LPWSTR), ("t", wt.LPWSTR),
                ("x", wt.DWORD), ("y", wt.DWORD), ("xs", wt.DWORD), ("ys", wt.DWORD),
                ("xc", wt.DWORD), ("yc", wt.DWORD), ("fill", wt.DWORD), ("flags", wt.DWORD),
                ("sw", wt.WORD), ("cb2", wt.WORD), ("r2", ctypes.c_void_p),
                ("hIn", wt.HANDLE), ("hOut", wt.HANDLE), ("hErr", wt.HANDLE)]


class PI(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                ("dwPid", wt.DWORD), ("dwTid", wt.DWORD)]


class EXR(ctypes.Structure):
    _fields_ = [("code", wt.DWORD), ("flags", wt.DWORD), ("rec", ctypes.c_void_p),
                ("addr", ctypes.c_void_p), ("n", wt.DWORD), ("info", ctypes.c_void_p * 15)]


class DBG(ctypes.Structure):
    class U(ctypes.Union):
        _fields_ = [("crudo", ctypes.c_byte * 176)]
    _fields_ = [("code", wt.DWORD), ("pid", wt.DWORD), ("tid", wt.DWORD),
                ("pad", wt.DWORD), ("u", U)]


class CTX(ctypes.Structure):
    """WOW64_CONTEXT: el contexto de 32 bits visto desde un Python de 64."""
    _fields_ = [("ContextFlags", wt.DWORD)] + \
               [(n, wt.DWORD) for n in ("Dr0", "Dr1", "Dr2", "Dr3", "Dr6", "Dr7")] + \
               [("FloatSave", ctypes.c_byte * 112)] + \
               [(n, wt.DWORD) for n in ("SegGs", "SegFs", "SegEs", "SegDs", "Edi", "Esi",
                                        "Ebx", "Edx", "Ecx", "Eax", "Ebp", "Eip", "SegCs",
                                        "EFlags", "Esp", "SegSs")] + \
               [("Extended", ctypes.c_byte * 512)]


def quien_llamo(h, hhilo, codigo=(0x401000, 0x90C000)):
    """★ La pila en el momento de la excepción: las direcciones que caen en el código del juego
    son retornos, y el `call` está justo antes. Sin esto sólo se sabe DÓNDE se murió, no por qué."""
    c = CTX()
    c.ContextFlags = 0x10001 | 0x10002
    if not k32.Wow64GetThreadContext(hhilo, ctypes.byref(c)):
        return None, [], {}
    buf = ctypes.create_string_buffer(0x200)
    got = ctypes.c_size_t(0)
    k32.ReadProcessMemory(h, ctypes.c_void_p(c.Esp), buf, 0x200, ctypes.byref(got))
    datos = buf.raw[:got.value]
    retornos = []
    for i in range(0, len(datos) - 4, 4):
        v = struct.unpack_from("<I", datos, i)[0]
        if codigo[0] <= v < codigo[1]:
            retornos.append(v)
    # ★ y los registros: sin esto, cada vez que el exe se muere leyendo [eax] hay que adivinar
    #   de dónde salió ese eax. Con el valor delante se ve enseguida si es cero, basura o un
    #   puntero que viene de otra parte.
    regs = {n: getattr(c, n) for n in ("Eax", "Ebx", "Ecx", "Edx", "Esi", "Edi", "Ebp", "Esp")}
    return c.Eip, retornos, regs


BASE_TRAMPA_ = 0xD0000000


def argumentos_en_la_trampa(h, hhilo, cuantos=8):
    """★ Los ARGUMENTOS DE VERDAD de la llamada que no supimos resolver.

    Cuando el exe cae en una trampa, el `call` ya se hizo: en el tope de la pila está la
    dirección de vuelta y arriba de ella **los argumentos tal como el juego los empujó**, con
    valores reales de una corrida real. Eso contesta cosas que ningún desensamblado contesta:
    si el primer argumento es un puntero, se lee el texto que apunta y se ve de qué se trata
    (una ruta, un nombre de archivo, un número).

    Devuelve [(valor, texto o None)].
    """
    c = CTX()
    c.ContextFlags = 0x10001 | 0x10002
    if not k32.Wow64GetThreadContext(hhilo, ctypes.byref(c)):
        return []
    buf = ctypes.create_string_buffer(4 * (cuantos + 1))
    g = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(c.Esp), buf, 4 * (cuantos + 1),
                                 ctypes.byref(g)):
        return []
    out = []
    for i in range(1, min(cuantos + 1, g.value // 4)):        # el 0 es la dirección de vuelta
        v = struct.unpack_from("<I", buf.raw, i * 4)[0]
        out.append((v, texto_en(h, v)))
    return out


def modulo_de(h, va):
    """★ En qué DLL cayó una dirección, y a cuántos bytes de su base.

    Hacía falta porque cuando el crash deja de caer en una trampa y cae DENTRO de una DLL del
    sistema, la dirección sola no dice nada: las DLL se cargan en una base distinta en cada
    corrida, así que no sirve compararla con el volcado. Se pregunta al proceso vivo."""
    n = wt.DWORD(0)
    bases = (ctypes.c_void_p * 1024)()
    # ⚠ desde un Python de 64 bits, `EnumProcessModules` a secas devuelve UNA sola entrada de un
    #   proceso de 32: hay que pedir `...Ex` con LIST_MODULES_32BIT (1). Sin esto el crash salía
    #   siempre como «EDA.exe + 0x76...», que es imposible.
    if not psapi.EnumProcessModulesEx(h, bases, ctypes.sizeof(bases), ctypes.byref(n), 1):
        return None
    mejor = None
    for i in range(n.value // ctypes.sizeof(ctypes.c_void_p)):
        b = bases[i] or 0
        if b <= va and (mejor is None or b > mejor[0]):
            nom = ctypes.create_unicode_buffer(512)
            psapi.GetModuleFileNameExW(h, ctypes.c_void_p(b), nom, 512)
            mejor = (b, os.path.basename(nom.value) or "?")
    return None if not mejor else "%s + 0x%x" % (mejor[1], va - mejor[0])


def texto_en(h, va, n=160):
    """El texto ASCII (o UTF-16) que hay en esa dirección, o None si no hay nada legible."""
    if va < 0x10000:
        return None
    b = ctypes.create_string_buffer(n)
    g = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(va), b, n, ctypes.byref(g)) or g.value < 2:
        return None
    d = b.raw[:g.value]
    a = d.split(b"\0")[0]
    if len(a) >= 2 and all(32 <= x < 127 for x in a):
        return a.decode("latin1")
    # ⚠ el control al revés de esto: si no se prueba UTF-16, una cadena ancha pasa por «no hay
    #   texto» y se pierde justo el dato que importa (así se encontró `CryptVerifySignature`).
    if len(d) >= 4 and d[1] == 0 and 32 <= d[0] < 127:
        try:
            w = d.decode("utf-16-le", "ignore").split("\0")[0]
        except Exception:                                    # noqa: BLE001
            return None
        if len(w) >= 2 and all(32 <= ord(x) < 127 for x in w):
            return w + "  (UTF-16)"
    return None


def saltear_trampa(h, hhilo):
    """★ Sigue adelante después de caer en una trampa, para que UNA corrida muestre TODOS los
    sitios sin resolver que el juego alcanza y no sólo el primero.

    Qué hace: pone EIP en la dirección de vuelta (que está en el tope de la pila), saca ese
    valor, y deja EAX en 0 como si la API hubiera fallado.
    ⚠ Y por qué lo que venga DESPUÉS ya no es confiable: las API de Windows son `stdcall`, o sea
      que limpian ellas los argumentos de la pila. Sin saber cuántos eran, la pila queda corrida.
      Sirve para ver la LISTA de sitios que hacen falta, no para creerle al crash siguiente."""
    c = CTX()
    c.ContextFlags = 0x10001 | 0x10002
    if not k32.Wow64GetThreadContext(hhilo, ctypes.byref(c)):
        return None
    b = ctypes.create_string_buffer(4)
    g = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(c.Esp), b, 4, ctypes.byref(g)):
        return None
    c.Eip = struct.unpack("<I", b.raw)[0]
    c.Esp += 4
    c.Eax = 0
    return c.Eip if k32.Wow64SetThreadContext(hhilo, ctypes.byref(c)) else None


def correr(exe, segundos, mirar=(), seguir_trampas=False):
    si = SI()
    si.cb = ctypes.sizeof(si)
    pi = PI()
    if not k32.CreateProcessW(exe, None, None, None, False, 2, None,
                              os.path.dirname(exe), ctypes.byref(si), ctypes.byref(pi)):
        sys.exit("[!] no pude lanzar %s (error %d)" % (exe, ctypes.get_last_error()))
    ev = DBG()
    t0 = time.time()
    dlls, excepciones, salio = 0, [], None
    hilos = {pi.dwTid: pi.hThread}
    pila = []
    trampas_vistas = []
    while time.time() - t0 < segundos:
        if not k32.WaitForDebugEvent(ctypes.byref(ev), 50):
            continue
        seguir = SEGUIR
        if ev.code == CARGA_DLL:
            dlls += 1
        elif ev.code == SALIDA_PROC:
            salio = struct.unpack_from("<I", bytes(ev.u.crudo), 0)[0]
            break
        elif ev.code == EXCEPCION:
            e = ctypes.cast(ctypes.byref(ev.u), ctypes.POINTER(EXR)).contents
            if e.code not in (0x80000003, 0x4000001F, 0x40010006):
                hh = hilo_de(ev.tid, hilos)
                if not excepciones and hh:
                    pila = quien_llamo(pi.hProcess, hh)
                    dd = (e.addr or 0) & 0xFFFFFFFF
                    if not BASE_TRAMPA_ <= dd < BASE_TRAMPA_ + 0x600000:
                        m = modulo_de(pi.hProcess, dd)
                        if m:
                            print("  ★ la excepción cayó en %s" % m)
                        # ★ el registro de la excepción dice MÁS que la dirección del código: para
                        #   un C0000005 trae si fue lectura o escritura y QUÉ dirección se tocó.
                        #   Sin esto hay que adivinar cuál de los argumentos estaba mal.
                        if e.code == 0xC0000005 and e.n >= 2:
                            tipo = {0: "leyendo", 1: "escribiendo", 8: "ejecutando"}.get(
                                int(e.info[0] or 0), "?")
                            print("     %s la dirección %08x"
                                  % (tipo, int(e.info[1] or 0) & 0xFFFFFFFF))
                        print("  ★ la pila en ese momento:")
                        for i, (v, t) in enumerate(
                                argumentos_en_la_trampa(pi.hProcess, hh, 56)):
                            print("     [esp+%02x] = %08x%s"
                                  % (4 + i * 4, v, "   «%s»" % t if t else ""))
                    if BASE_TRAMPA_ <= dd < BASE_TRAMPA_ + 0x600000:
                        print("  ★ los argumentos de verdad en la trampa %08x:"
                              % (dd - BASE_TRAMPA_ + 0x400000))
                        for i, (v, t) in enumerate(
                                argumentos_en_la_trampa(pi.hProcess, hh), 1):
                            print("     arg%d = %08x%s" % (i, v, "   «%s»" % t if t else ""))
                    # ★ ¿Windows rellenó la tabla de imports? Se compara un casillero NUEVO
                    #   (el de la llamada que ASProtect había desviado) con uno VIEJO.
                    for va in mirar:
                        b = ctypes.create_string_buffer(4)
                        g = ctypes.c_size_t(0)
                        ok = k32.ReadProcessMemory(pi.hProcess, ctypes.c_void_p(va), b, 4,
                                                   ctypes.byref(g))
                        print("  casillero %08x = %s" % (
                            va, ("%08x" % struct.unpack("<I", b.raw)[0]) if ok else "ilegible"))
                dir_ = (e.addr or 0) & 0xFFFFFFFF
                excepciones.append((e.code, dir_))
                seguir = NO_MANEJADA
                # ★ si cayó en una trampa y se pidió seguir, se saltea la llamada y se anota
                if (seguir_trampas and e.code == 0xC0000005
                        and BASE_TRAMPA_ <= dir_ < BASE_TRAMPA_ + 0x600000
                        and hh):
                    sitio = dir_ - BASE_TRAMPA_ + 0x400000
                    if sitio not in trampas_vistas:
                        trampas_vistas.append(sitio)
                    if saltear_trampa(pi.hProcess, hh) is not None:
                        seguir = SEGUIR
        k32.ContinueDebugEvent(ev.pid, ev.tid, seguir)
    k32.TerminateProcess(pi.hProcess, 1)
    return dlls, excepciones, salio, pila, trampas_vistas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe")
    ap.add_argument("--segundos", type=int, default=25)
    ap.add_argument("--seguir", action="store_true",
                    help="★ saltear las trampas para ver TODOS los sitios sin resolver que el "
                         "juego alcanza (lo de despues ya no es confiable: ver saltear_trampa)")
    ap.add_argument("--mirar", help="casilleros a leer en la 1ª excepción, separados por coma")
    a = ap.parse_args()
    exe = a.exe
    if not exe:
        # ⚠ el exe reconstruido importa mss32.dll y las de Miles: tiene que correr AL LADO de los
        #   archivos del juego, o Windows no lo carga. Se copia a la carpeta de pruebas.
        if not os.path.exists(CONSTRUIDO):
            sys.exit("[!] falta %s — correr `desempacar.py construir`" % CONSTRUIDO)
        exe = os.path.join(JUEGO, "EDA_libre.exe")
        shutil.copy2(CONSTRUIDO, exe)
        print("[probar] copiado a %s" % exe)
    dlls, exc, salio, pila, trampas = correr(
        exe, a.segundos, [int(x, 0) for x in (a.mirar or '').split(',') if x],
        seguir_trampas=a.seguir)
    print("[probar] DLL cargadas: %d · excepciones: %d · salida: %s"
          % (dlls, len(exc), "sigue vivo" if salio is None else "código %d" % salio))
    if not exc:
        print("  ✅ no se murió en %d s" % a.segundos)
        return 0
    if pila:
        eip, retornos, regs = pila
        print("  en el momento de la 1ª excepción: eip=%08x" % (eip or 0))
        print("  registros: %s" % "  ".join("%s=%08x" % (k.lower(), v) for k, v in regs.items()))
        print("  retornos en la pila (quién llamó):",
              " ".join("%08x" % r for r in list(dict.fromkeys(retornos))[:8]) if retornos else "ninguno")
    from desempacar import Volcado
    v = Volcado()
    desv = set(v.sitios_desviados())
    resueltos = v.desviados()
    from desempacar import BASE_TRAMPA
    for code, dir_ in exc[:6]:
        # ★ la trampa: si el crash cae en BASE_TRAMPA+algo, fue un sitio desviado SIN resolver,
        #   y la propia dirección dice cuál (ver `desempacar.py`, BASE_TRAMPA).
        if BASE_TRAMPA <= dir_ < BASE_TRAMPA + 0x600000:
            print("  ⛔ el juego llegó a un sitio SIN RESOLVER: %08x"
                  % (dir_ - BASE_TRAMPA + 0x400000))
        else:
            print("  ⛔ excepción %08X en %08x" % (code, dir_))
    # ★ ¿la primera excepción es por un sitio que quedó sin resolver? Se mira quién la llamó
    #   buscando el `call` más cercano: si el sitio está en la lista de desviados y NO está
    #   resuelto, ésa es la causa y hay nombre y apellido.
    sin = sorted(s for s in desv if s not in resueltos)
    print("  sitios desviados todavía SIN resolver: %d de %d" % (len(sin), len(desv)))
    if sin:
        print("  los primeros:", " ".join("%08x" % s for s in sin[:12]))
    if trampas:
        print("\n★ sitios SIN RESOLVER que el juego alcanzó de verdad: %d" % len(trampas))
        print("  " + " ".join("%08x" % s for s in trampas))
    return 1


if __name__ == "__main__":
    sys.exit(main())
