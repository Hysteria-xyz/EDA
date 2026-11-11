r"""espiar_apis -- descubrir, MIDIENDO, qué API de Windows emula cada llamada que ASProtect desvió.

⛔ ESTADO AL 08-nov-2026: NO LO LOGRA TODAVÍA. Queda acá porque lo que MIDIÓ sirve y no hay que
   volver a pagarlo (ver `documentacion/MEDICIONES.md`, corrida 5):
     ✅ el anti-debug de ASProtect se pasa borrando las marcas del PEB (BeingDebugged,
        NtGlobalFlag, flags del heap). Sin eso el juego se mata solo, siempre en el mismo lugar.
     ⛔ un breakpoint por HARDWARE en el arranque del juego también lo mata: mira los registros Dr.
     ⛔ un `int3` en el arranque del juego lo pisa ASProtect al desempacar.
     ⛔ un `int3` en el despachador queda escrito (comprobado al releerlo) pero NO SE DISPARA NUNCA,
        y el juego termina saliendo: o verifica ese código, o la trampa llega tarde.
     ⚠ y llega tarde porque **ASProtect descifra el código por partes, según se va ejecutando**:
        cuando los `call` testigo aparecen desempacados ya hay 48 DLL cargadas, o sea que el
        arranque del juego ya pasó.
   ⇒ Lo que sigue NO es insistir por acá: es entrar DENTRO del proceso con la DLL proxy `d3d9`
     (que Windows carga antes que nada) y mirar desde ahí, sin depurador de por medio.

Por qué: ASProtect reemplazó 329 `call dword ptr [IAT]` del juego por llamadas a stubs propios.
Los que copian el comienzo de la API se resuelven leyendo (`desempacar.py api_de_stub`), pero los
**259 que van a un despachador común** son una máquina virtual: no hay tabla que leer
(se buscaron las direcciones de retorno en 91 MB de memoria del juego: no están).
⇒ No se deduce: se mide. Se corre el juego bajo un depurador propio y se mira dónde termina cada una.

    py herramientas\espiar_apis.py              # corre el juego y anota lo que vea
    py herramientas\espiar_apis.py --segundos 90
    py herramientas\espiar_apis.py --control    # ★ comprueba que el método ve bien

Deja `_trabajo/apis_emuladas.json`: {dirección del call: "dll!función"}.

Cómo funciona
  1. lanza el juego bajo depuración y **le limpia al PEB las marcas de "me están depurando"**
     (BeingDebugged, NtGlobalFlag, flags del heap). Sin esto ASProtect se tira a matar: medido el
     08-nov, moría siempre en la misma dirección.
  2. espera a que ASProtect cree el despachador y le pone un `int3` encima.
  3. en cada parada: la dirección de retorno dice QUIÉN llamó; después va paso a paso hasta que la
     ejecución entra en una DLL **con esa misma dirección de retorno en la pila** — ésa es la API
     de verdad, no una que la VM use para su propio trabajo.
  4. lo que ya conoce no lo vuelve a seguir, así que el juego avanza a velocidad razonable.

⚠ Sólo puede ver las llamadas que el juego EJECUTE. Las que están en código al que no llega
  (por ejemplo, después de que GameGuard corta) quedan sin resolver.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")

JUEGO = os.path.join(RAIZ, "_trabajo", "juego", "EDA.exe")
SALIDA = os.path.join(RAIZ, "_trabajo", "apis_emuladas.json")
# (la dirección del despachador se descubre en cada corrida: ver poner_trampas)
EXE = (0x401000, 0x90C000)
TOPE_PASOS = 300000

EXCEPCION, SALIDA_PROC, CARGA_DLL, ARRANQUE = 1, 5, 6, 3
BP, PASO = 0x80000003, 0x80000004
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
    """WOW64_CONTEXT: el contexto de 32 bits, visto desde un Python de 64."""
    _fields_ = [("ContextFlags", wt.DWORD), ("Dr0", wt.DWORD), ("Dr1", wt.DWORD),
                ("Dr2", wt.DWORD), ("Dr3", wt.DWORD), ("Dr6", wt.DWORD), ("Dr7", wt.DWORD),
                ("FloatSave", ctypes.c_byte * 112), ("SegGs", wt.DWORD), ("SegFs", wt.DWORD),
                ("SegEs", wt.DWORD), ("SegDs", wt.DWORD), ("Edi", wt.DWORD), ("Esi", wt.DWORD),
                ("Ebx", wt.DWORD), ("Edx", wt.DWORD), ("Ecx", wt.DWORD), ("Eax", wt.DWORD),
                ("Ebp", wt.DWORD), ("Eip", wt.DWORD), ("SegCs", wt.DWORD), ("EFlags", wt.DWORD),
                ("Esp", wt.DWORD), ("SegSs", wt.DWORD), ("Extended", ctypes.c_byte * 512)]


CTX_CONTROL_ENTEROS = 0x10001 | 0x10002 | 0x10010   # control + enteros + registros de depuración


class Proceso:
    def __init__(self, exe):
        si = SI()
        si.cb = ctypes.sizeof(si)
        self.pi = PI()
        if not k32.CreateProcessW(exe, None, None, None, False, 0x00000002, None,
                                  os.path.dirname(exe), ctypes.byref(si), ctypes.byref(self.pi)):
            raise SystemExit("[!] no pude lanzar %s (error %d)" % (exe, ctypes.get_last_error()))
        self.h = self.pi.hProcess
        self.hilos = {self.pi.dwTid: self.pi.hThread}

    def leer(self, a, n):
        buf = ctypes.create_string_buffer(n)
        r = ctypes.c_size_t(0)
        return buf.raw[:r.value] if k32.ReadProcessMemory(
            self.h, ctypes.c_void_p(a), buf, n, ctypes.byref(r)) else None

    def u32(self, a):
        b = self.leer(a, 4)
        return int.from_bytes(b, "little") if b and len(b) == 4 else None

    def escribir(self, a, b):
        old = wt.DWORD()
        k32.VirtualProtectEx(self.h, ctypes.c_void_p(a), len(b), 0x40, ctypes.byref(old))
        r = ctypes.c_size_t(0)
        ok = k32.WriteProcessMemory(self.h, ctypes.c_void_p(a), b, len(b), ctypes.byref(r))
        k32.VirtualProtectEx(self.h, ctypes.c_void_p(a), len(b), old, ctypes.byref(old))
        return bool(ok)

    def ctx(self, tid):
        c = CTX()
        c.ContextFlags = CTX_CONTROL_ENTEROS
        h = self.hilos.get(tid)
        return c if h and k32.Wow64GetThreadContext(h, ctypes.byref(c)) else None

    def set_ctx(self, tid, c):
        return bool(k32.Wow64SetThreadContext(self.hilos[tid], ctypes.byref(c)))

    def freno_por_hardware(self, tid, dir_):
        """Un breakpoint de EJECUCIÓN por hardware (registro Dr0). No toca la memoria, así que
        ASProtect no lo pisa al desempacar ni lo ve con un checksum — que es lo que pasó al
        intentarlo con un int3 en el arranque del juego."""
        c = self.ctx(tid)
        if not c:
            return False
        c.Dr0 = dir_
        c.Dr7 = (c.Dr7 & ~0xF) | 0x1        # habilitar Dr0, al ejecutar, 1 byte
        return self.set_ctx(tid, c)

    def soltar_frenos(self, tid):
        c = self.ctx(tid)
        if c:
            c.Dr0 = 0
            c.Dr7 = 0
            self.set_ctx(tid, c)

    def sin_marcas_de_debug(self):
        """⚠ sin esto ASProtect se mata solo: es la única razón por la que esto funciona."""
        p = ctypes.c_ulonglong(0)
        ntdll.NtQueryInformationProcess(self.h, 26, ctypes.byref(p), 8, None)
        if not p.value:
            return False
        self.escribir(p.value + 2, b"\x00")                       # BeingDebugged
        self.escribir(p.value + 0x68, b"\x00" * 4)                # NtGlobalFlag
        hp = self.u32(p.value + 0x18)                             # ProcessHeap
        if hp:
            self.escribir(hp + 0x40, b"\x02\x00\x00\x00")         # Flags
            self.escribir(hp + 0x44, b"\x00" * 4)                 # ForceFlags
        return True


def export_cercano(res, va, tope=160):
    """(dll, función) del export que empieza hasta `tope` bytes antes: el stub devuelve el control
    unos pocos bytes DESPUÉS del comienzo de la API."""
    import bisect
    m = res.modulo(va)
    if not m:
        return None
    t = res._tabla(m)
    rs = sorted(t)
    i = bisect.bisect_right(rs, va - m["base"]) - 1
    if i < 0:
        return None
    return (m["nombre"], t[rs[i]]) if (va - m["base"]) - rs[i] <= tope else None


ARRANQUE_JUEGO = 0x7E3A11        # el OEP, medido en MEDICIONES.md
# Testigos: `call <despachador>` del código del juego; dicen dónde cayó el despachador en ESTA
# corrida (la dirección cambia cada vez). ⚠ ASProtect descifra el código POR PARTES, a medida que
# se ejecuta: con un testigo de una función tardía (la del cartel de GameGuard) la trampa llegaba
# siempre tarde, con el arranque ya hecho. Los dos primeros son del arranque del CRT.
TESTIGOS = (0x7E39BD, 0x7E3B16, 0x402CB2)


def espiar(segundos=120, juego=JUEGO, verbose=True):
    from desempacar import Resolvedor
    import volcar_exe
    v = None
    p = Proceso(juego)
    conocidas, sin_resolver, orden = {}, set(), []
    byte_orig = None
    puesto = False
    limpiado = False
    ev = DBG()
    t0 = time.time()
    trazando = None            # (tid, callsite, pasos) mientras seguimos una llamada nueva
    reponer = None             # (tid,) cuando sólo hay que volver a poner el int3

    def log(s):
        if verbose:
            print(s, flush=True)

    despachador = None
    byte_oep = None

    def poner_trampas():
        """Ya desempacado: averiguar dónde cayó el despachador en ESTA corrida y atraparlo.
        ⚠ ASProtect lo pone en memoria que pide al arranque, así que la dirección CAMBIA cada vez
        (medido: 0x4760000 una corrida, 0x47A0000 la siguiente). Se lee del `call` testigo."""
        nonlocal despachador, byte_orig, puesto, v
        destino = None
        for t in TESTIGOS:
            b = p.leer(t, 5)
            if not b or b[0] != 0xE8:
                continue
            d = (t + 5 + int.from_bytes(b[1:5], "little", signed=True)) & 0xFFFFFFFF
            # tiene que ser memoria de ASProtect, con código adentro (y no bytes aún cifrados)
            if 0x1000000 < d < 0x10000000 and (p.leer(d, 4) or bytes(4)) != bytes(4):
                destino = d
                break
        if destino is None:
            return False
        despachador = destino
        byte_orig = p.leer(despachador, 1)
        if not byte_orig or not p.escribir(despachador, b"\xcc"):
            return False
        # y las DLL de ESTA corrida, no las del volcado viejo: las bases cambian
        v = Resolvedor(volcar_exe.modulos(p.h))
        puesto = True
        log("[espia] despachador de esta corrida: %08x — trampa puesta (%d DLL)"
            % (despachador, len(v.mods)))
        return True

    while time.time() - t0 < segundos:
        if not k32.WaitForDebugEvent(ctypes.byref(ev), 1):
            continue
        if not puesto:
            # ⚠ ASProtect lanza muchas excepciones mientras desempaca: cada una es una pausa
            #   donde podemos mirar. Esperar sólo a los ratos sin eventos llegaba TARDE, con el
            #   arranque del juego ya hecho (medido el 08-nov).
            poner_trampas()
        seguir = SEGUIR
        if ev.code == ARRANQUE and not limpiado:
            limpiado = p.sin_marcas_de_debug()
            log("[espia] marcas de depuración borradas del PEB: %s" % limpiado)
        elif ev.code == SALIDA_PROC:
            log("[espia] el juego salió")
            break
        elif ev.code == EXCEPCION:
            e = ctypes.cast(ctypes.byref(ev.u), ctypes.POINTER(EXR)).contents
            dir_ = (e.addr or 0) & 0xFFFFFFFF
            if e.code == BP and puesto and dir_ == despachador:
                c = p.ctx(ev.tid)
                if c:
                    c.Eip = despachador
                    llamador = (p.u32(c.Esp) or 0) - 5     # el `call` mide 5 bytes
                    p.escribir(despachador, byte_orig)     # dejarlo pasar
                    c.EFlags |= 0x100                      # paso a paso
                    p.set_ctx(ev.tid, c)
                    if llamador in conocidas or llamador in sin_resolver:
                        reponer = ev.tid
                    else:
                        trazando = [ev.tid, llamador, 0, p.u32(c.Esp) or 0]
            elif e.code == PASO and (reponer is not None or trazando):
                c = p.ctx(ev.tid)
                if reponer is not None:
                    p.escribir(despachador, b"\xcc")
                    reponer = None
                    if c:
                        c.EFlags &= ~0x100
                        p.set_ctx(ev.tid, c)
                elif c:
                    trazando[2] += 1
                    fin = None
                    if EXE[0] <= c.Eip < EXE[1]:           # volvió al juego sin pasar por DLL
                        fin = "???"
                    elif v.modulo(c.Eip) and p.u32(c.Esp) == trazando[3]:
                        n = export_cercano(v, c.Eip)
                        if n:
                            fin = "%s!%s" % (n[0], n[1])
                    if fin is None and trazando[2] > TOPE_PASOS:
                        fin = "???"
                    if fin:
                        if fin == "???":
                            sin_resolver.add(trazando[1])
                        else:
                            conocidas[trazando[1]] = fin
                            orden.append(trazando[1])
                            log("[espia] %08x -> %-38s (%d pasos, van %d)"
                                % (trazando[1], fin, trazando[2], len(conocidas)))
                        c.EFlags &= ~0x100
                        p.set_ctx(ev.tid, c)
                        p.escribir(despachador, b"\xcc")
                        trazando = None
            elif e.code == BP:
                log("[espia] (int3 en %08x, que no es el despachador %s)"
                    % (dir_, "%08x" % despachador if despachador else "-"))
            elif e.code not in (PASO, 0x4000001F, 0x40010006):
                seguir = NO_MANEJADA
        elif ev.code == 2:                                   # hilo nuevo
            h = ctypes.cast(ctypes.byref(ev.u), ctypes.POINTER(ctypes.c_void_p))[1]
            if h:
                p.hilos[ev.tid] = h
        k32.ContinueDebugEvent(ev.pid, ev.tid, seguir)
    k32.TerminateProcess(p.h, 1)
    return conocidas, sin_resolver


def control():
    """★ ¿el método ve bien? Dos casos de respuesta conocida, medidos el 08-nov:
       - `0x402CB2` tiene que dar MessageBox (es el cartel de GameGuard, se ve en pantalla);
       - `0x7E39BD` tiene que dar GetModuleHandle (el CRT pidiendo su propio módulo, y el stub
         individual `0x03AD0004` ya dio `GetModuleHandleA` leyendo, sin correr nada).
    Y el control al revés: ninguna dirección fuera del código del juego puede aparecer."""
    con, sin = espiar(segundos=150, verbose=True)
    ok = True

    def chequear(n, c, d=""):
        nonlocal ok
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok = ok and c
    print("\ncontrol:")
    chequear("descubrió llamadas", len(con) > 0, "(%d resueltas, %d sin resolver)" % (len(con), len(sin)))
    m = con.get(0x402CB2, "")
    chequear("0x402CB2 es el cartel (MessageBox)", "MessageBox" in m, m or "no se ejecutó")
    g = con.get(0x7E39BD, "")
    chequear("0x7E39BD pide su módulo (GetModuleHandle)", "GetModuleHandle" in g, g or "no se ejecutó")
    chequear("NO inventa llamadores fuera del código del juego",
             all(EXE[0] <= a < EXE[1] for a in con))
    print("  →", "TODO BIEN" if ok else "ALGO FALLA")
    return con, sin, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segundos", type=int, default=120)
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()
    if a.control:
        con, sin, ok = control()
    else:
        con, sin = espiar(a.segundos)
        ok = True
    json.dump({"%08x" % k: v for k, v in sorted(con.items())},
              open(SALIDA, "w", encoding="utf-8"), indent=1)
    print("\n%d llamadas resueltas, %d sin resolver → %s" % (len(con), len(sin), SALIDA))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
