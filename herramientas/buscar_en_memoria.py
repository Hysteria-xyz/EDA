r"""buscar_en_memoria -- buscar bytes en la memoria del juego ANDANDO, y decir dónde están.

Para cuando un dato existe en la corrida pero NO está en ningún archivo (así se buscó la IP del
Broker, `218.145.66.187`, que no aparece ni en el exe ni en `Data.dat` ni en el registro). Si la
cadena está en memoria, esto dice en qué región y qué hay alrededor — y de ahí sale si la armó el
programa, si la descomprimió de `Data.dat` o si la trajo de la red.

    py herramientas\buscar_en_memoria.py "218.145.66.187"
    py herramientas\buscar_en_memoria.py --exe EDA_limpio.exe --esperar 4 "25000"
    py herramientas\buscar_en_memoria.py --hex "da914 2bb"
    py herramientas\buscar_en_memoria.py control

Sólo lee (`ReadProcessMemory`). No escribe ni suspende nada.
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
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def regiones(h, tope=0x7FFFFFFEFFFF):
    """[(base, tamaño, protección)] de lo que está mapeado y se puede leer.

    ⚠ El techo va hasta los 47 bits a propósito. Con `0x80000000` (que alcanza de sobra para el
      juego, que es de 32 bits) el CONTROL de esta herramienta fallaba: se corre sobre este mismo
      Python, que es de 64, y su montón vive más arriba. Un control que no pasa deja sin valor
      cualquier «no está».
    """
    out, va = [], 0
    m = MBI()
    while va < tope:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(va), ctypes.byref(m), ctypes.sizeof(m)):
            break
        base = m.BaseAddress or 0
        tam = m.RegionSize or 0x1000
        # MEM_COMMIT y no PAGE_NOACCESS/GUARD
        if m.State == 0x1000 and not (m.Protect & 0x101) and m.Protect:
            out.append((base, tam, m.Protect))
        va = base + tam
        if tam == 0:
            break
    return out


def modulos(h):
    """[(base, fin, nombre)] para poder decir en qué DLL cayó cada hallazgo."""
    n = wt.DWORD(0)
    bases = (ctypes.c_void_p * 1024)()
    out = []
    if not psapi.EnumProcessModulesEx(h, bases, ctypes.sizeof(bases), ctypes.byref(n), 1):
        return out

    class INFO(ctypes.Structure):
        _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD),
                    ("EntryPoint", ctypes.c_void_p)]
    for i in range(n.value // ctypes.sizeof(ctypes.c_void_p)):
        b = bases[i] or 0
        inf = INFO()
        psapi.GetModuleInformation(h, ctypes.c_void_p(b), ctypes.byref(inf), ctypes.sizeof(inf))
        nom = ctypes.create_unicode_buffer(512)
        psapi.GetModuleFileNameExW(h, ctypes.c_void_p(b), nom, 512)
        out.append((b, b + (inf.SizeOfImage or 0), os.path.basename(nom.value)))
    return out


def donde(mods, va):
    for b, f, n in mods:
        if b <= va < f:
            return "%s + 0x%x" % (n, va - b)
    return "memoria suelta"


def buscar(pid, aguja, alrededor=48):
    h = k32.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        raise SystemExit("⛔ no pude abrir el proceso %d" % pid)
    mods = modulos(h)
    hallados = []
    leidos = 0
    for base, tam, prot in regiones(h):
        trozo = min(tam, 1 << 24)
        off = 0
        while off < tam:
            n = min(trozo, tam - off)
            b = ctypes.create_string_buffer(n)
            got = ctypes.c_size_t(0)
            if k32.ReadProcessMemory(h, ctypes.c_void_p(base + off), b, n, ctypes.byref(got)) \
                    and got.value:
                d = b.raw[:got.value]
                leidos += got.value
                i = d.find(aguja)
                while i != -1:
                    va = base + off + i
                    a = max(0, i - alrededor)
                    ctx = d[a:i + len(aguja) + alrededor]
                    hallados.append((va, donde(mods, va), prot, ctx, i - a))
                    i = d.find(aguja, i + 1)
                    if len(hallados) > 60:
                        break
            off += n
            if len(hallados) > 60:
                break
        if len(hallados) > 60:
            break
    k32.CloseHandle(h)
    return hallados, leidos


def pinta_ctx(ctx):
    return "".join(chr(c) if 32 <= c < 127 else "." for c in ctx)


def control():
    """★ El control y su revés: una cadena que SABEMOS que está en este proceso tiene que
    aparecer, y una que no puede estar NO tiene que aparecer. Sin esto, «no está en memoria» no
    quiere decir nada."""
    # ⚠ El control NO puede correr sobre este mismo proceso: la aguja que se busca VIVE acá, así
    #   que el caso que debe fallar encuentra siempre la propia aguja y el control no distingue
    #   nada. Por eso se lanza un proceso aparte que se guarda una marca conocida.
    marca = "EDA_CONTROL_" + os.urandom(6).hex()
    hijo = subprocess.Popen(
        [sys.executable, "-c", "m='%s'*8\nimport time\ntime.sleep(25)\nprint(len(m))" % marca])
    time.sleep(2.5)
    try:
        h, leidos = buscar(hijo.pid, marca.encode())
        print("  %s encuentra en OTRO proceso una marca que sabemos que tiene (%d veces, %.0f MB)"
              % ("✅" if h else "⛔", len(h), leidos / 1048576.0))
        f, _ = buscar(hijo.pid, ("EDA_AUSENTE_" + os.urandom(8).hex()).encode())
        print("  %s NO encuentra en ese proceso una marca que no tiene"
              % ("✅" if not f else "⛔"))
    finally:
        hijo.kill()
    ok = bool(h) and not f
    print("\n%s" % ("→ TODO BIEN" if ok else "→ ⛔ ALGO FALLA"))
    return 0 if ok else 1


def main():
    if sys.argv[1:2] == ["control"]:
        return control()
    ap = argparse.ArgumentParser()
    ap.add_argument("aguja")
    ap.add_argument("--exe", default="EDA_limpio.exe")
    ap.add_argument("--esperar", type=float, default=4.0, help="segundos antes de buscar")
    ap.add_argument("--hex", action="store_true")
    ap.add_argument("--pid", type=int)
    a = ap.parse_args()
    aguja = bytes.fromhex(a.aguja.replace(" ", "")) if a.hex else a.aguja.encode("latin1")

    p = None
    if a.pid:
        pid = a.pid
    else:
        exe = a.exe if os.path.isabs(a.exe) else os.path.join(JUEGO, a.exe)
        subprocess.run(["taskkill", "/F", "/IM", os.path.basename(exe)], capture_output=True)
        time.sleep(0.4)
        p = subprocess.Popen([exe], cwd=JUEGO)
        pid = p.pid
        print("★ %s pid %d — espero %.1f s" % (a.exe, pid, a.esperar))
        time.sleep(a.esperar)
    try:
        hall, leidos = buscar(pid, aguja)
        print("  busqué %s en %.1f MB" % (aguja, leidos / 1048576.0))
        for va, mod, prot, ctx, pos in hall:
            print("  %08x  [%s]  prot=%x" % (va, mod, prot))
            print("        |%s|" % pinta_ctx(ctx))
        if not hall:
            print("  (no está)")
    finally:
        if p is not None and p.poll() is None:
            p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
