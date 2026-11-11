r"""clic_juego -- hacer clic EN la ventana del juego sin tocar el mouse de nadie.

Manda los mensajes de ventana (`WM_MOUSEMOVE`, `WM_LBUTTONDOWN`, `WM_LBUTTONUP`, y para el
teclado `WM_CHAR` / `WM_KEYDOWN`) con `PostMessage` directo a la ventana del juego, en
coordenadas de la ventana. El cursor de el tester no se mueve y la ventana no tiene que estar al frente.
EDA dibuja su interfaz con HGE (las clases `hgeGUIObject` del exe), que lee el mouse de esos mismos
mensajes.

    py herramientas\clic_juego.py clic 640 538            # un clic en (x, y) de la ventana
    py herramientas\clic_juego.py escribir rui             # teclea un texto
    py herramientas\clic_juego.py tecla 13                 # una tecla (código virtual: 13 = Enter)
    py herramientas\clic_juego.py control

Las coordenadas son las del ÁREA DE CLIENTE (800×600), las mismas que las de las fotos de
`foto_juego.py`.

★ El control: una ventana de tkinter en OTRO proceso con un botón que, al apretarse, escribe un
  archivo. El clic mandado así tiene que apretarlo; y el revés: un clic en otra parte de esa
  ventana NO lo tiene que apretar. Sin esto, «el juego no reaccionó» no diría nada.
"""
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from foto_juego import ventanas_de                           # noqa: E402

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202
WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x100, 0x101, 0x102
MK_LBUTTON = 1


def pid_de(nombre="EDA_limpio.exe"):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % nombre, "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for l in out.splitlines():
        partes = [p.strip('"') for p in l.split('","')]
        if len(partes) > 1 and partes[1].isdigit():
            return int(partes[1])
    return None


def ventana(pid):
    v = ventanas_de(pid)
    if not v:
        raise SystemExit("⛔ el proceso %d no tiene ventana visible" % pid)
    return v[0][0]


class PT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def hijo_en(hwnd, x, y):
    """★ La ventana HIJA más profunda bajo (x, y), con las coordenadas pasadas a ella. Un mensaje
    a la ventana de arriba no le llega a la hija que en realidad recibe el mouse (en Tk cada
    widget es una; en EDA está la `D3DProxyWindow`)."""
    u32.ChildWindowFromPointEx.restype = wt.HWND
    u32.ChildWindowFromPointEx.argtypes = [wt.HWND, PT, wt.UINT]
    p = PT(x, y)
    while True:
        c = u32.ChildWindowFromPointEx(hwnd, p, 1 | 4)   # saltear invisibles y transparentes
        if not c or c == hwnd:
            return hwnd, p.x, p.y
        u32.MapWindowPoints(hwnd, c, ctypes.byref(p), 1)
        hwnd = c


def clic(hwnd, x, y, pausa=0.08):
    hwnd, x, y = hijo_en(hwnd, x, y)
    lp = (y << 16) | (x & 0xFFFF)
    u32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    time.sleep(pausa)
    u32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(pausa)
    u32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def clic_derecho(hwnd, x, y, pausa=0.08):
    hwnd, x, y = hijo_en(hwnd, x, y)
    lp = (y << 16) | (x & 0xFFFF)
    u32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    time.sleep(pausa)
    u32.PostMessageW(hwnd, 0x204, 2, lp)                  # WM_RBUTTONDOWN, MK_RBUTTON
    time.sleep(pausa)
    u32.PostMessageW(hwnd, 0x205, 0, lp)                  # WM_RBUTTONUP


def arrastrar(hwnd, x0, y0, x1, y1, pasos=12, pausa=0.04):
    """Arrastra con el botón izquierdo de (x0, y0) a (x1, y1): bajar, mover de a poco, soltar."""
    h, ox, oy = hijo_en(hwnd, x0, y0)
    dx, dy = ox - x0, oy - y0                             # la misma hija para todo el recorrido

    def lp(x, y):
        return ((y + dy) << 16) | ((x + dx) & 0xFFFF)
    u32.PostMessageW(h, WM_MOUSEMOVE, 0, lp(x0, y0))
    time.sleep(pausa)
    u32.PostMessageW(h, WM_LBUTTONDOWN, MK_LBUTTON, lp(x0, y0))
    for i in range(1, pasos + 1):
        time.sleep(pausa)
        u32.PostMessageW(h, WM_MOUSEMOVE, MK_LBUTTON,
                         lp(x0 + (x1 - x0) * i // pasos, y0 + (y1 - y0) * i // pasos))
    time.sleep(pausa * 3)
    u32.PostMessageW(h, WM_LBUTTONUP, 0, lp(x1, y1))


JS_BOTON = r"""
// ★ El GUI (HGE) pregunta por el botón APRETADO con GetKeyState(VK_LBUTTON) en cada cuadro
//   (medido: 20/s con 1 y 2), no por los mensajes: sin esto, un arrastre por mensajes no arrastra.
let apretado = false;
const f = Process.getModuleByName('user32.dll').getExportByName('GetKeyState');
Interceptor.attach(f, {
    onEnter(a) { this.vk = a[0].toInt32(); },
    onLeave(r) { if (apretado && this.vk === 1) r.replace(ptr('0xffff8001')); }
});
rpc.exports = {boton(v) { apretado = v; }};
"""


def arrastrar_de_verdad(pid, x0, y0, x1, y1, pasos=15, pausa=0.05, sostener=0.3):
    """Arrastrar con el botón «apretado» también para `GetKeyState` (Frida). Para el inventario
    y la pantalla de habilidades, donde el juego mira el estado del botón y no sólo el mensaje."""
    import frida
    ses = frida.attach(pid)
    sc = ses.create_script(JS_BOTON)
    sc.load()
    try:
        hwnd = ventana(pid)
        h, ox, oy = hijo_en(hwnd, x0, y0)
        dx, dy = ox - x0, oy - y0

        def lp(x, y):
            return ((y + dy) << 16) | ((x + dx) & 0xFFFF)
        u32.PostMessageW(h, WM_MOUSEMOVE, 0, lp(x0, y0))
        time.sleep(0.2)
        sc.exports_sync.boton(True)
        u32.PostMessageW(h, WM_LBUTTONDOWN, MK_LBUTTON, lp(x0, y0))
        time.sleep(sostener)
        for i in range(1, pasos + 1):
            u32.PostMessageW(h, WM_MOUSEMOVE, MK_LBUTTON,
                             lp(x0 + (x1 - x0) * i // pasos, y0 + (y1 - y0) * i // pasos))
            time.sleep(pausa)
        time.sleep(0.3)
        sc.exports_sync.boton(False)
        u32.PostMessageW(h, WM_LBUTTONUP, 0, lp(x1, y1))
        time.sleep(0.3)
    finally:
        sc.unload()
        ses.detach()


def tecla(hwnd, vk):
    u32.PostMessageW(hwnd, WM_KEYDOWN, vk, 1)
    u32.PostMessageW(hwnd, WM_KEYUP, vk, 0xC0000001)


def edit_oculto(hwnd):
    """★ EDA escribe texto a través de un `Edit` OCULTO, hijo de la ventana LithTech (lo maneja
    el objeto del IME, `0x77A320`). Un WM_CHAR a la ventana de arriba no llega a ningún campo."""
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    hallado = []

    def cb(h, _):
        c = ctypes.create_unicode_buffer(32)
        u32.GetClassNameW(h, c, 32)
        if c.value == "Edit":
            hallado.append(h)
        return True
    u32.EnumChildWindows(hwnd, PROC(cb), 0)
    return hallado[0] if hallado else None


def escribir(hwnd, texto, pausa=0.05, enter=True):
    """★ Escribir en el campo que tenga el foco (antes hay que hacerle clic).
    Medido el 10-nov: el objeto del IME (`0x949530`, procedimiento `0x77A4D0`) subclasea el `Edit`
    oculto; un WM_CHAR ahí entra al `Edit` y a su buffer (`obj+0x1C`). Pero el campo de la
    interfaz recién copia ese texto con el **Enter** (el procedimiento trata el 0x0D aparte, sin
    pasárselo al `Edit`): sin el Enter, «Create» decía «Room Name is missing»."""
    destino = edit_oculto(hwnd) or hwnd
    for ch in texto:
        u32.PostMessageW(destino, WM_CHAR, ord(ch), 1)
        time.sleep(pausa)
    if enter:
        time.sleep(0.6)
        u32.PostMessageW(destino, WM_KEYDOWN, 0x0D, 1)
        u32.PostMessageW(destino, WM_CHAR, 0x0D, 1)
        u32.PostMessageW(destino, WM_KEYUP, 0x0D, 0xC0000001)


def control():
    ok = []

    def chequear(n, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", n, d))
        ok.append(bool(c))
    marca = os.path.join(RAIZ, "_trabajo", "control_clic.txt").replace("\\", "/")
    if os.path.exists(marca):
        os.remove(marca)
    # Ventana nativa Win32 (como la del motor C++ LithTech/HGE) que procesa WM_LBUTTONDOWN directamente
    codigo = (
        "import ctypes, sys, os\n"
        "import ctypes.wintypes as wt\n"
        "u = ctypes.WinDLL('user32')\n"
        "k = ctypes.WinDLL('kernel32')\n"
        "u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]\n"
        "u.DefWindowProcW.restype = wt.LPARAM\n"
        "P = ctypes.WINFUNCTYPE(wt.LPARAM, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)\n"
        "def w(h, m, w, l):\n"
        "    if m == 0x201:\n"
        "        x, y = l & 0xFFFF, (l >> 16) & 0xFFFF\n"
        "        if 100 <= x <= 200 and 80 <= y <= 120:\n"
        "            with open(r'%s', 'a') as f: f.write('clic %%d %%d\\n' %% (x, y))\n"
        "    elif m == 0x10:\n"
        "        u.PostQuitMessage(0)\n"
        "    return u.DefWindowProcW(h, m, w, l)\n"
        "class C(ctypes.Structure):\n"
        "    _fields_ = [('s', wt.UINT), ('p', P), ('ce', ctypes.c_int), ('we', ctypes.c_int), "
        "('hi', wt.HINSTANCE), ('ic', wt.HANDLE), ('cu', wt.HANDLE), ('bg', wt.HANDLE), "
        "('mn', wt.LPCWSTR), ('cn', wt.LPCWSTR)]\n"
        "wc = C()\n"
        "wc.p = P(w)\n"
        "wc.hi = k.GetModuleHandleW(None)\n"
        "wc.cn = 'TestClicWnd'\n"
        "u.RegisterClassW(ctypes.byref(wc))\n"
        "h = u.CreateWindowExW(0, 'TestClicWnd', 'Test', 0x10CF0000, 60, 60, 300, 200, 0, 0, wc.hi, 0)\n"
        "u.ShowWindow(h, 5)\n"
        "m = wt.MSG()\n"
        "while u.GetMessageW(ctypes.byref(m), 0, 0, 0) != 0:\n"
        "    u.TranslateMessage(ctypes.byref(m))\n"
        "    u.DispatchMessageW(ctypes.byref(m))\n"
        % marca
    )
    hijo = subprocess.Popen([sys.executable, "-c", codigo])
    try:
        time.sleep(1.5)
        h = ventana(hijo.pid)
        clic(h, 20, 20)                                      # el revés: fuera del botón
        time.sleep(0.4)
        chequear("un clic FUERA del botón no lo aprieta", not os.path.exists(marca))
        clic(h, 150, 100)                                    # en el medio del botón
        time.sleep(0.4)
        chequear("un clic EN el botón lo aprieta (sin mover el mouse)",
                 os.path.exists(marca) and "clic" in open(marca).read())
    finally:
        hijo.kill()
        if os.path.exists(marca):
            os.remove(marca)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    if not a or a[0] == "control":
        return control()
    pid = pid_de()
    if not pid:
        raise SystemExit("⛔ EDA_limpio.exe no está abierto")
    h = ventana(pid)
    if a[0] == "clic":
        clic(h, int(a[1]), int(a[2]))
    elif a[0] == "escribir":
        escribir(h, a[1])
    elif a[0] == "tecla":
        tecla(h, int(a[1]))
    print("  ok (%s) → pid %d" % (" ".join(a), pid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
