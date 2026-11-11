r"""ventanas -- abrir un exe del juego y anotar QUÉ VENTANAS va abriendo, segundo a segundo.

Es el instrumento de medición de «¿hasta dónde llegó?». Sólo lee: enumera las ventanas de
nivel superior que pertenecen al proceso (clase, título, tamaño, si se ve) y escribe una línea
cada vez que la lista CAMBIA. Al final mata el proceso.

    py herramientas\ventanas.py                              # _trabajo/juego/EDA_libre.exe
    py herramientas\ventanas.py --exe EDA_emular.exe --segundos 60
    py herramientas\ventanas.py --exe EDA.exe --segundos 40   # el original, para comparar

⚠ Se corre desde `_trabajo/juego/` (la copia), nunca desde `cliente/` — regla de LEEME.md.
⚠ Mata el proceso al terminar, y también los que haya quedado colgados de corridas anteriores
  (`--no-limpiar` para no hacerlo).
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

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def ventanas_de(pid):
    """[(clase, titulo, ancho, alto, se_ve)] de las ventanas de nivel superior del proceso."""
    out = []

    def una(h, _):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value != pid:
            return True
        cls = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, cls, 256)
        tit = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(h, tit, 512)
        r = wt.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        out.append((cls.value, tit.value, r.right - r.left, r.bottom - r.top,
                    bool(u32.IsWindowVisible(h))))
        return True

    u32.EnumWindows(PROC(una), 0)
    return sorted(out)


def pinta(v):
    return " | ".join("%s «%s» %dx%d%s" % (c, t, a, b, "" if ve else " oculta")
                      for c, t, a, b, ve in v) or "(ninguna)"


class ENTRADA(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]


def procesos():
    """{pid: (nombre, pid del padre)} de toda la máquina. Sólo lee."""
    h = k32.CreateToolhelp32Snapshot(2, 0)             # TH32CS_SNAPPROCESS
    if h == -1:
        return {}
    e = ENTRADA()
    e.dwSize = ctypes.sizeof(e)
    out = {}
    if k32.Process32First(h, ctypes.byref(e)):
        while True:
            out[e.th32ProcessID] = (e.szExeFile.decode("latin1", "replace"),
                                    e.th32ParentProcessID)
            if not k32.Process32Next(h, ctypes.byref(e)):
                break
    k32.CloseHandle(h)
    return out


def linea_de_comando(pid):
    """La línea de comando de un proceso (por si es un navegador: ahí va la URL)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter 'ProcessId=%d').CommandLine" % pid],
            capture_output=True, timeout=20)
        return r.stdout.decode("latin1", "replace").strip()
    except Exception:                                        # noqa: BLE001
        return ""


def matar_viejos(nombre):
    subprocess.run(["taskkill", "/F", "/IM", nombre], capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="EDA_libre.exe")
    ap.add_argument("--segundos", type=int, default=45)
    ap.add_argument("--no-limpiar", action="store_true")
    a = ap.parse_args()

    exe = a.exe if os.path.isabs(a.exe) else os.path.join(JUEGO, a.exe)
    if not os.path.exists(exe):
        raise SystemExit("⛔ no está %s" % exe)
    nombre = os.path.basename(exe)
    if not a.no_limpiar:
        matar_viejos(nombre)
        time.sleep(0.5)

    print("★ %s  (%d s)" % (nombre, a.segundos))
    # ★ la foto de los procesos ANTES de lanzar: lo que aparezca después es cosa del juego.
    #   Hacía falta para contestar quién abre la web de GameGuard: el exe o un proceso aparte.
    ya_estaban = set(procesos())
    p = subprocess.Popen([exe], cwd=JUEGO)
    ya_estaban.add(p.pid)
    t0 = time.time()
    antes, vivo, avisados = None, True, set()
    try:
        while time.time() - t0 < a.segundos:
            v = ventanas_de(p.pid) if p.poll() is None else None
            if v is not None and v != antes:
                print("  %5.1fs  %s" % (time.time() - t0, pinta(v)), flush=True)
                antes = v
            for pid, (nom, padre) in procesos().items():
                if pid in ya_estaban or pid in avisados:
                    continue
                avisados.add(pid)
                print("  %5.1fs  ★ PROCESO NUEVO: %s (pid %d, padre %d)%s"
                      % (time.time() - t0, nom, pid, padre,
                         "\n              " + linea_de_comando(pid)), flush=True)
            if p.poll() is not None:
                print("  %5.1fs  ⛔ el proceso SALIÓ solo, código %d"
                      % (time.time() - t0, p.returncode))
                vivo = False
                break
            time.sleep(0.4)
    finally:
        if vivo:
            print("  %5.1fs  → sigue vivo; lo cierro" % (time.time() - t0))
            p.kill()
            p.wait(timeout=10)
        if not a.no_limpiar:
            matar_viejos(nombre)
    return 0


if __name__ == "__main__":
    sys.exit(main())
