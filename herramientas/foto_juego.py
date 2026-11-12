r"""foto_juego -- abrir el juego, esperar, y sacarle una FOTO a su ventana (sin tocar nada más).

Para cuando la pregunta es «¿qué muestra la pantalla?» y el tester no está mirando. Usa
`PrintWindow(hwnd, hdc, PW_RENDERFULLCONTENT=2)`, que en Windows 8.1+ captura también lo que
dibuja Direct3D, y no hace falta traer la ventana al frente ni capturar el escritorio.

    py herramientas\foto_juego.py                       # EDA_limpio.exe, fotos a los 6, 12 y 20 s
    py herramientas\foto_juego.py --en 5,15,30 --exe EDA_limpio.exe
    py herramientas\foto_juego.py --pid 1234 --en 0     # uno que ya está abierto

Deja `_trabajo/fotos/<hora>_<segundos>s.png`.

★ El control (`control`): una ventana propia pintada de un color conocido tiene que salir de
  ESE color en la foto, y una ventana de OTRO proceso no tiene que salir (el revés: que la
  herramienta fotografíe la ventana pedida y no cualquier cosa).
⚠ Si la foto sale toda negra, el juego no había dibujado todavía (o el driver no deja
  copiar el contenido de D3D): probar más tarde o mirar con los ojos.
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
FOTOS = os.path.join(RAIZ, "_trabajo", "fotos")

u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32", use_last_error=True)
u32.SetProcessDPIAware()


def ventanas_de(pid):
    """[(hwnd, título, clase, ancho, alto)] visibles de ese proceso, la más grande primero."""
    out = []
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def una(h, _):
        p = wt.DWORD(0)
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            t = ctypes.create_unicode_buffer(256)
            c = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(h, t, 256)
            u32.GetClassNameW(h, c, 256)
            r = wt.RECT()
            u32.GetClientRect(h, ctypes.byref(r))
            out.append((h, t.value, c.value, r.right - r.left, r.bottom - r.top))
        return True
    u32.EnumWindows(PROC(una), 0)
    return sorted(out, key=lambda v: -(v[3] * v[4]))


def foto(hwnd, ancho, alto):
    """La imagen (PIL) del contenido de la ventana."""
    from PIL import Image
    hdc = u32.GetDC(hwnd)
    mem = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, ancho, alto)
    g32.SelectObject(mem, bmp)
    u32.PrintWindow(hwnd, mem, 3)            # PW_CLIENTONLY | PW_RENDERFULLCONTENT

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("x", ctypes.c_long), ("y", ctypes.c_long),
                    ("c1", wt.DWORD), ("c2", wt.DWORD)]
    bi = BIH()
    bi.biSize = ctypes.sizeof(bi)
    bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = ancho, -alto, 1, 32
    buf = ctypes.create_string_buffer(ancho * alto * 4)
    g32.GetDIBits(mem, bmp, 0, alto, buf, ctypes.byref(bi), 0)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mem)
    u32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGB", (ancho, alto), buf.raw, "raw", "BGRX", 0, 1)


def control():
    """★ Una ventana de tkinter de un color conocido, en OTRO proceso: la foto tiene que ser de
    ese color. Y el revés: con el pid de este proceso (que no tiene ventanas) no sale nada."""
    ok = []

    def chequear(n, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok.append(bool(c))
    codigo = ("import tkinter as t; r=t.Tk(); r.geometry('320x200+40+40'); "
              "r.configure(bg='#12c34a'); r.title('EDA_CONTROL_FOTO'); r.after(9000, r.destroy); "
              "r.mainloop()")
    hijo = subprocess.Popen([sys.executable, "-c", codigo])
    try:
        time.sleep(2.5)
        v = ventanas_de(hijo.pid)
        chequear("encuentra la ventana del otro proceso", v, str([x[1] for x in v]))
        if v:
            img = foto(v[0][0], v[0][3], v[0][4])
            px = img.getpixel((v[0][3] // 2, v[0][4] // 2))
            chequear("la foto es del color pintado (#12c34a)",
                     all(abs(a - b) <= 6 for a, b in zip(px, (0x12, 0xC3, 0x4A))), str(px))
        chequear("con un pid sin ventanas no saca nada (el revés)", not ventanas_de(os.getpid()))
    finally:
        hijo.kill()
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    if sys.argv[1:2] == ["control"]:
        return control()
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default="EDA_limpio.exe")
    ap.add_argument("--en", default="6,12,20", help="segundos en que sacar cada foto")
    ap.add_argument("--pid", type=int)
    a = ap.parse_args()
    os.makedirs(FOTOS, exist_ok=True)
    momentos = [float(x) for x in a.en.split(",")]
    p = None
    if a.pid:
        pid = a.pid
    else:
        subprocess.run(["taskkill", "/F", "/IM", a.exe], capture_output=True)
        time.sleep(0.4)
        p = subprocess.Popen('"%s"' % os.path.join(JUEGO, a.exe), cwd=JUEGO)   # entre comillas (§39)
        pid = p.pid
    t0, hora = time.time(), time.strftime("%H%M%S")
    try:
        for m in momentos:
            while time.time() - t0 < m:
                time.sleep(0.1)
            if p is not None and p.poll() is not None:
                print("  %5.1fs  ⛔ el juego ya salió (código %d)" % (time.time() - t0, p.returncode))
                break
            v = ventanas_de(pid)
            if not v:
                print("  %5.1fs  (sin ventana visible)" % (time.time() - t0))
                continue
            h, titulo, clase, w, hh = v[0]
            ruta = os.path.join(FOTOS, "%s_%02ds.png" % (hora, int(m)))
            foto(h, w, hh).save(ruta)
            print("  %5.1fs  %r [%s] %dx%d  -> %s" % (time.time() - t0, titulo, clase, w, hh, ruta))
    finally:
        if p is not None and p.poll() is None:
            p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
