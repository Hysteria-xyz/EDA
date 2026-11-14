r"""EDA-Atajos -- las teclas de EDA que el cliente de 2009 no tiene, mientras EDA está AL FRENTE:

    F9          listo / empezar (ya es del juego: acá no se toca)
    F10         Options               (EDA-Opciones.py)
    F11         Messenger (abre/cierra)   (EDA-Messenger.py)
    F12         Clan: reservado (avisa)

Un gancho de teclado de Windows (WH_KEYBOARD_LL): ve la tecla aunque el juego lea DirectInput, y
sólo actúa si la ventana del frente es de un proceso EDA*.exe (así F10 en otro programa sigue
siendo F10). Esas teclas NO le llegan al juego. Se cierra solo cuando no queda ningún EDA abierto.

Lo abre el server local al entrar al lobby (y EDA-Jugar.bat). Una sola copia (atajos.pid).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
SERVIDOR = RAIZ / "repo" / "_trabajo" / "servidor"
PID = SERVIDOR / "atajos.pid"
LOG = SERVIDOR / "atajos.log"
ESTADO = SERVIDOR / "messenger_estado.json"
PEDIDOS = SERVIDOR / "messenger_pedidos.jsonl"
sys.path.insert(0, str(RAIZ))


def anotar(texto):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + texto + "\n")
    except OSError:
        pass


def cuenta_activa():
    """La cuenta conectada (la primera; con un solo EDA abierto es la tuya)."""
    try:
        cuentas = json.loads(ESTADO.read_text(encoding="utf-8")).get("cuentas", {})
    except (OSError, ValueError):
        return "rui"
    return next((n for n, d in cuentas.items() if d.get("conectado")), "rui")


def abrir(script, *args):
    py = Path(sys.executable).with_name("pythonw.exe")
    try:
        subprocess.Popen([str(py if py.exists() else sys.executable), str(RAIZ / script)] + list(args),
                         cwd=str(RAIZ), close_fds=True)
    except OSError as error:
        anotar("no se pudo abrir %s: %s" % (script, error))


def alternar(script, pid, *args):
    """Si la ventana está abierta, la cierra; si no, la abre."""
    import eda_ui
    if eda_ui.vivo(str(pid)):
        eda_ui.matar_si_python(int(pid.read_text().strip()))
    else:
        abrir(script, *args)


def avisar(texto):
    """Una línea en el chat del juego (la manda el server: pedido «aviso»)."""
    try:
        with open(PEDIDOS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"de": cuenta_activa(), "accion": "aviso", "texto": texto},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def tecla_inventario():
    """★ 14-nov: SIN atajo (el usuario quiere la venta múltiple DENTRO del Inventory del juego).
    """
    return None


def _tecla_inventario_vieja():
    """El atajo del inventario de EDA-teclas.json: (ctrl, código DirectInput)."""
    try:
        cod = json.loads((RAIZ / "EDA-teclas.json").read_text(encoding="utf-8"))["EDA_Inventario"][0]
    except (OSError, ValueError, KeyError, IndexError):
        cod = "C23"
    if not cod or cod[0] not in "CK":
        return None
    return cod[0] == "C", int(cod[1:])


ACCIONES = {
    68: lambda: alternar("EDA-Opciones.py", SERVIDOR / "opciones_panel.pid"),          # F10
    87: lambda: alternar("EDA-Messenger.py", SERVIDOR / "messenger_panel.pid", "--cuenta", cuenta_activa()),
    88: lambda: avisar("Clan: reservado (F12). Todavía no existe en esta versión."),     # F12
}


# ★ LOS MARCOS de la venta múltiple: el lanzador (eda_original.py, INVENTARIO_JS) deja en
#   marcas.json el rectángulo de cada ítem marcado con Ctrl+clic (relativo a la grilla de la bolsa);
#   acá se dibujan en rojo sobre el juego, en una ventana transparente que no recibe clics.
MARCAS = SERVIDOR / "marcas.json"
GRILLA = (412, 170)          # dónde empieza la grilla de la bolsa en la pantalla 800×600 del juego
# (la bolsa entera, 6 × 5 casillas, en coordenadas de 800×600: donde aparece la ficha del ítem)
BOLSA = (GRILLA[0] - 4, GRILLA[1] - 4, GRILLA[0] + 280, GRILLA[1] + 236)


class Marcos:
    def __init__(self):
        import tkinter as tk
        import ctypes
        self.raiz = tk.Tk()
        self.raiz.withdraw()
        self.v = tk.Toplevel(self.raiz)
        self.v.overrideredirect(True)
        self.v.configure(bg="#ff00ff")
        self.v.attributes("-transparentcolor", "#ff00ff")
        self.cv = tk.Canvas(self.v, bg="#ff00ff", highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.v.update_idletasks()
        u32 = ctypes.windll.user32
        hwnd = u32.GetParent(self.v.winfo_id()) or self.v.winfo_id()
        u32.SetWindowLongW(hwnd, -20, u32.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20 | 0x08000000)
        self.v.withdraw()
        self.visible, self.mtime, self.celdas, self.ultimo = False, 0, [], None
        self.hwnd, self.dueno = hwnd, 0

    def paso(self):
        import ctypes
        from ctypes import wintypes
        import eda_ui
        try:
            m = MARCAS.stat().st_mtime
            if m != self.mtime:
                self.mtime = m
                self.celdas = json.loads(MARCAS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.celdas = []
        u32 = ctypes.windll.user32
        hwnd = eda_ui.ventana_por_proceso() if self.celdas else 0
        # ★ 14-nov: ya NO es «siempre encima». La capa pasa a ser PROPIEDAD de la ventana del
        #   juego (GWL_HWNDPARENT): Windows la deja justo encima del juego y DEBAJO de cualquier
        #   otra ventana (Messenger, Options, el navegador…). Por eso tampoco hace falta ocultarla
        #   cuando el juego no está al frente (eso la hacía parpadear y «desaparecer»).
        if hwnd and hwnd != self.dueno:
            fijar = getattr(u32, "SetWindowLongPtrW", u32.SetWindowLongW)
            fijar.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            fijar(ctypes.c_void_p(self.hwnd), -8, ctypes.c_void_p(hwnd))
            self.dueno = hwnd
        if not hwnd or u32.IsIconic(ctypes.c_void_p(hwnd)):
            if self.visible:
                self.v.withdraw()
                self.visible = False
            self.raiz.update()
            return
        r = wintypes.RECT()
        u32.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        p = wintypes.POINT(0, 0)
        u32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(p))
        w, h = r.right, r.bottom
        # ★ 14-nov: el juego dibuja su FICHA del ítem (el cartel negro) al pasar el mouse por la
        #   bolsa, y esta capa quedaba encima del cartel. Mientras el mouse esté sobre la bolsa
        #   (sin Ctrl: con Ctrl apretado se está marcando y se quieren ver los marcos) se ocultan.
        c = wintypes.POINT()
        u32.GetCursorPos(ctypes.byref(c))
        mx, my = (c.x - p.x) * 800.0 / max(w, 1), (c.y - p.y) * 600.0 / max(h, 1)
        ctrl = u32.GetAsyncKeyState(0x11) & 0x8000
        if not ctrl and BOLSA[0] <= mx <= BOLSA[2] and BOLSA[1] <= my <= BOLSA[3]:
            if self.visible:
                self.v.withdraw()
                self.visible = False
            self.raiz.update()
            return
        estado = (p.x, p.y, w, h, json.dumps(self.celdas))
        if estado != self.ultimo:
            self.ultimo = estado
            sx, sy = w / 800.0, h / 600.0
            self.v.geometry("%dx%d+%d+%d" % (w, h, p.x, p.y))
            self.cv.delete("all")
            for x0, y0, x1, y1 in self.celdas:
                a, b = (GRILLA[0] + x0) * sx, (GRILLA[1] + y0) * sy
                c, d = (GRILLA[0] + x1) * sx, (GRILLA[1] + y1) * sy
                # ★ como la selección ORIGINAL del juego: marco celeste con brillo (un halo
                #   oscuro afuera, el trazo claro adentro)
                self.cv.create_rectangle(a + 1, b + 1, c - 1, d - 1, outline="#1b8fa0", width=3)
                self.cv.create_rectangle(a + 2, b + 2, c - 2, d - 2, outline="#5fe8f5", width=1)
                self.cv.create_rectangle(a + 3, b + 3, c - 3, d - 3, outline="#2bb9c9", width=1)
        if not self.visible:
            self.v.deiconify()
            self.visible = True
        self.raiz.update()


def frente_nuestro(hwnd):
    """★ 14-nov: el juego O una de nuestras ventanas (Buddy, Options…: pythonw). Antes sólo el
    juego: abierto el Buddy, F11 ya no lo cerraba (el frente era el Buddy)."""
    import eda_ui
    if eda_ui.es_del_juego(hwnd):
        return True
    try:
        import ctypes
        from ctypes import wintypes
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        return pid.value != 0 and "pythonw" in (eda_ui._imagen(pid.value) or "").lower()
    except Exception:                                         # noqa: BLE001
        return False


def main():
    import ctypes
    from ctypes import wintypes
    import eda_ui

    eda_ui.una_instancia(str(PID))
    eda_ui.con_dpi()
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32

    class KBD(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

    HOOK = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    u32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    u32.CallNextHookEx.restype = ctypes.c_ssize_t
    u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOK, ctypes.c_void_p, wintypes.DWORD]
    u32.SetWindowsHookExW.restype = ctypes.c_void_p
    k32.GetModuleHandleW.restype = ctypes.c_void_p              # ★ (64 bits: sin esto, error 126)
    u32.GetForegroundWindow.restype = ctypes.c_void_p
    u32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    pendientes = []
    inv = {"tecla": tecla_inventario(), "cuando": 0}

    def gancho(n, wparam, lparam):
        if n == 0 and wparam in (0x100, 0x104, 0x101, 0x105):          # KEYDOWN/SYSKEYDOWN/UP/SYSUP
            k = ctypes.cast(lparam, ctypes.POINTER(KBD)).contents
            dik = (k.scanCode & 0x7F) | (0x80 if k.flags & 1 else 0)
            if time.time() - inv["cuando"] > 5:
                inv["tecla"], inv["cuando"] = tecla_inventario(), time.time()
            ctrl = bool(u32.GetAsyncKeyState(0x11) & 0x8000)
            es_inv = inv["tecla"] is not None and dik == inv["tecla"][1] and ctrl == inv["tecla"][0]
            if (dik in ACCIONES or es_inv) and frente_nuestro(u32.GetForegroundWindow()):
                if wparam in (0x100, 0x104):
                    pendientes.append("inv" if es_inv else dik)
                return 1                                                  # no le llega al juego
        return u32.CallNextHookEx(None, n, wparam, lparam)

    funcion = HOOK(gancho)
    h = u32.SetWindowsHookExW(13, funcion, k32.GetModuleHandleW(None), 0)
    if not h:
        anotar("no se pudo poner el gancho (error %d)" % k32.GetLastError())
        return 1
    anotar("atajos listos (F10 Options · F11 Messenger · F12 Clan · inventario %s)" % (inv["tecla"],))
    try:
        marcos = Marcos()
    except Exception as error:                                   # noqa: BLE001
        anotar("sin marcos: %r" % error)
        marcos = None
    msg = wintypes.MSG()
    ultimo_juego = revisado = revisado_m = time.time()
    while True:
        # mensajes sin bloquear (el gancho corre dentro de PeekMessage)
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        while pendientes:
            que = pendientes.pop(0)
            try:
                if que == "inv":
                    alternar("EDA-Inventario.py", SERVIDOR / "inventario_panel.pid", "--cuenta", cuenta_activa())
                else:
                    ACCIONES[que]()
                anotar("tecla %s" % que)
            except Exception as error:                                # noqa: BLE001
                anotar("error con %s: %r" % (que, error))
        if time.time() - revisado > 2:
            revisado = time.time()
            if eda_ui.ventana_por_proceso():
                ultimo_juego = revisado
            elif revisado - ultimo_juego > 20:                            # sin EDA abierto: se va
                anotar("no hay EDA abierto: fin")
                break
        if marcos is not None and time.time() - revisado_m > 0.08:
            revisado_m = time.time()
            try:
                marcos.paso()
            except Exception as error:                           # noqa: BLE001
                anotar("marcos: %r" % error)
                marcos = None
        time.sleep(0.02)
    u32.UnhookWindowsHookEx(ctypes.c_void_p(h))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                         # noqa: BLE001
        import traceback
        anotar(traceback.format_exc())
        raise
