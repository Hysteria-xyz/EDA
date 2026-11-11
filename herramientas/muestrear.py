r"""muestrear -- de a tirones de microsegundos, ver POR DÓNDE va un proceso. Sólo lectura.

Para qué (10-nov): el exe reconstruido se muere en `0x7E88A5` porque la global del locale del CRT
(`0x94AE64`) sigue en cero. Y está medido que en el juego de verdad **también arranca en cero** y
alguien la escribe en los primeros milisegundos. O sea que al exe le falta recorrer un camino, no
le falta un dato. Para saber QUÉ camino hay que ver por dónde pasa cada uno.

Cómo, sin depurador y sin escribir nada en el proceso: se lo suspende, se lo deja correr un tirón
corto, se lo vuelve a suspender y se le lee el **EIP** y los retornos que tenga en la pila
(`Wow64GetThreadContext` + `ReadProcessMemory`: las dos son de lectura). Eso da una muestra. Con
muchas muestras seguidas sale el recorrido.

⚠ Es un muestreo, no una traza: entre dos tirones el proceso ejecuta millones de instrucciones y
  no se ven. Sirve para comparar DOS recorridos y encontrar dónde se separan, no para afirmar que
  una función no se ejecutó.
⚠ Y ASProtect no se entera: nunca nos registramos como depurador, así que su anti-debug no aplica.

    py herramientas\muestrear.py original            # EDA.exe, desde que ASProtect termina
    py herramientas\muestrear.py libre               # EDA_libre.exe, desde el arranque
    py herramientas\muestrear.py libre --mirar 0x94AE64 --tirones 400 --rodaja 0.0005
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
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
import volcar_todo as V                                      # noqa: E402

k32 = V.k32
nt = ctypes.WinDLL("ntdll")
CODIGO = (0x401000, 0x90C000)
LIBRE = os.path.join(RAIZ, "_trabajo", "juego", "EDA_libre.exe")


class CTX(ctypes.Structure):
    """WOW64_CONTEXT: el contexto de 32 bits visto desde un Python de 64."""
    _fields_ = [("ContextFlags", wt.DWORD)] + \
               [(n, wt.DWORD) for n in ("Dr0", "Dr1", "Dr2", "Dr3", "Dr6", "Dr7")] + \
               [("FloatSave", ctypes.c_byte * 112)] + \
               [(n, wt.DWORD) for n in ("SegGs", "SegFs", "SegEs", "SegDs", "Edi", "Esi",
                                        "Ebx", "Edx", "Ecx", "Eax", "Ebp", "Eip", "SegCs",
                                        "EFlags", "Esp", "SegSs")] + \
               [("Extended", ctypes.c_byte * 512)]


def hilos_de(pid):
    """Los tid del proceso, por Toolhelp (sólo consulta)."""
    class TE(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                    ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long),
                    ("tpDeltaPri", ctypes.c_long), ("dwFlags", wt.DWORD)]
    h = k32.CreateToolhelp32Snapshot(0x00000004, 0)          # TH32CS_SNAPTHREAD
    if h == -1:
        return []
    te = TE()
    te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(h, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(h, ctypes.byref(te))
    k32.CloseHandle(h)
    return out


def muestra(hproc, tid):
    """(eip, [retornos del código del juego que haya en la pila])."""
    hh = k32.OpenThread(0x1FFFFF, False, tid)
    if not hh:
        return None, []
    c = CTX()
    c.ContextFlags = 0x10001 | 0x10002
    if not k32.Wow64GetThreadContext(hh, ctypes.byref(c)):
        k32.CloseHandle(hh)
        return None, []
    buf = ctypes.create_string_buffer(0x100)
    got = ctypes.c_size_t(0)
    k32.ReadProcessMemory(hproc, ctypes.c_void_p(c.Esp), buf, 0x100, ctypes.byref(got))
    rets = []
    for i in range(0, max(got.value - 4, 0), 4):
        v = int.from_bytes(buf.raw[i:i + 4], "little")
        if CODIGO[0] <= v < CODIGO[1]:
            rets.append(v)
    k32.CloseHandle(hh)
    return c.Eip, rets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cual", choices=["original", "libre"])
    ap.add_argument("--rodaja", type=float, default=0.0005, help="segundos de cada tirón")
    ap.add_argument("--tirones", type=int, default=600)
    ap.add_argument("--mirar", default="", help="direcciones a leer en cada tirón, por coma")
    ap.add_argument("--hasta", help="parar cuando ESA dirección deje de ser cero")
    a = ap.parse_args()
    mirar = [int(x, 0) for x in a.mirar.split(",") if x.strip()]
    hasta = int(a.hasta, 0) if a.hasta else None
    exe = V.JUEGO if a.cual == "original" else LIBRE
    if not os.path.exists(exe):
        sys.exit("[!] falta %s" % exe)
    # ⚠ el exe nuestro se crea SUSPENDIDO: si se lo deja arrancar aunque sean 5 ms, el CRT ya
    #   corrió entero y las primeras muestras llegan tarde (medido: en el tirón 0 el índice de TLS
    #   ya estaba asignado). Al original no se le puede hacer esto: hay que dejar que ASProtect
    #   termine, así que ahí se usa `esperar_temprano`.
    proc = subprocess.Popen([exe], cwd=os.path.dirname(exe),
                            creationflags=0 if a.cual == "original" else 0x00000004)
    try:
        if a.cual == "original":
            if not V.esperar_temprano(proc.pid):
                return 1
        else:
            nt.NtSuspendProcess(wt.HANDLE(k32.OpenProcess(0x0800, False, proc.pid)))
            # el hilo principal está suspendido dos veces (CREATE_SUSPENDED + el nuestro): se
            # saca una, así que el primer NtResumeProcess lo pone a correr.
            for tid in hilos_de(proc.pid):
                hh = k32.OpenThread(0x1FFFFF, False, tid)
                if hh:
                    k32.ResumeThread(hh)
                    k32.CloseHandle(hh)
        h = k32.OpenProcess(0x0410, False, proc.pid)
        hs = k32.OpenProcess(0x0800, False, proc.pid)
        visto, anterior = [], None
        for i in range(a.tirones):
            tid = (hilos_de(proc.pid) or [0])[0]
            eip, rets = muestra(h, tid)
            vals = [V.leer(h, x, 4) for x in mirar]
            vals = [int.from_bytes(v, "little") if v else None for v in vals]
            if eip and CODIGO[0] <= eip < CODIGO[1]:
                visto.append(eip)
            linea = "  %4d  eip=%08x %s %s" % (
                i, eip or 0,
                " ".join("%08x=%08x" % (x, v or 0) for x, v in zip(mirar, vals)),
                " ".join("%08x" % r for r in rets[:5]))
            if (eip, vals) != anterior:
                print(linea, flush=True)
                anterior = (eip, vals)
            if hasta:
                b = V.leer(h, hasta, 4)
                if b and int.from_bytes(b, "little"):
                    print("\n★ %08x dejó de ser cero en el tirón %d · eip=%08x · pila: %s"
                          % (hasta, i, eip or 0, " ".join("%08x" % r for r in rets[:8])))
                    break
            nt.NtResumeProcess(wt.HANDLE(hs))
            time.sleep(a.rodaja)
            nt.NtSuspendProcess(wt.HANDLE(hs))
        print("\n  muestras dentro del código del juego: %d · distintas: %d"
              % (len(visto), len(set(visto))))
    finally:
        proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
