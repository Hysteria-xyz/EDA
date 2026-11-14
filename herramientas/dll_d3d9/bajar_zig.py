r"""bajar_zig -- baja el compilador de la dll (Zig 0.16.0, el de la receta de R2Beat) a _trabajo\zig\, UNA vez.

    py herramientas\dll_d3d9\bajar_zig.py          # → _trabajo\zig\zig-x86_64-windows-0.16.0\zig.exe
    py herramientas\dll_d3d9\compilar.py           # y ya compila (lo busca ahí si no hay ZIG)

Es el zip oficial de ziglang.org (~90 MB; descomprimido ~476 MB, por eso no va en el repo). Se verifica
que adentro esté zig.exe antes de dejarlo. Si ya está, no baja nada.
"""
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

VERSION = "0.16.0"
NOMBRE = "zig-x86_64-windows-%s" % VERSION
URL = "https://ziglang.org/download/%s/%s.zip" % (VERSION, NOMBRE)
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESTINO = os.path.join(RAIZ, "_trabajo", "zig")


def bajar():
    zig = os.path.join(DESTINO, NOMBRE, "zig.exe")
    if os.path.isfile(zig):
        print("· ya está: %s" % zig)
        return zig
    os.makedirs(DESTINO, exist_ok=True)
    tmp = os.path.join(tempfile.gettempdir(), NOMBRE + ".zip")
    print("· bajando %s …" % URL)
    with urllib.request.urlopen(URL, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    with zipfile.ZipFile(tmp) as z:
        if not any(n.endswith("/zig.exe") for n in z.namelist()):
            raise SystemExit("⛔ el zip no trae zig.exe: %s" % URL)
        z.extractall(DESTINO)
    os.remove(tmp)
    if not os.path.isfile(zig):
        raise SystemExit("⛔ no quedó %s" % zig)
    print("★ %s" % zig)
    return zig


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    bajar()
