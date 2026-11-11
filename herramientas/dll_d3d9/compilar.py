r"""compilar -- arma el d3d9.dll PROPIO de EDA (tope de cuadros + contador) desde herramientas/dll_d3d9/.

    py herramientas\dll_d3d9\compilar.py              # → _trabajo\dll\d3d9.dll (+ eda_d3d9.ini) y su md5
    py herramientas\dll_d3d9\compilar.py --poner      # y la copia al lado del juego (_trabajo\juego\)
    py herramientas\dll_d3d9\compilar.py --sacar      # la saca de _trabajo\juego\ (el juego vuelve al d3d9 de Windows)

La receta es la de R2Beat (herramientas/dll_d3d9/compilar.py de ese proyecto): Zig 0.16.0,
`-target x86-windows-gnu -shared -O2 -s`. ⛔ La salida SE LLAMA `d3d9.dll`: el enlazador escribe ese
nombre adentro (la tabla de exportaciones). El compilador no está en este repo (476 MB): se lo
busca en la variable ZIG o en el lugar donde lo dejó el proyecto R2Beat.
"""
import hashlib
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))               # ⚠ herramientas/dll_d3d9 → la raíz
SALIDA = os.path.join(RAIZ, "_trabajo", "dll")
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
ZIG = os.environ.get("ZIG") or os.path.join(os.path.expanduser("~"), "Desktop", "Proyecto qq", "_taller", "_zig",
                                             "zig-x86_64-windows-0.16.0", "zig.exe")
INI = """; eda_d3d9.ini — los ajustes del d3d9.dll de EDA (herramientas/dll_d3d9)
[video]
; el tope de cuadros por segundo (0 = sin tope). EDA no trae tope: sin él dibuja cientos de cuadros
; por segundo, la placa va a máxima potencia y con dos juegos abiertos el ping sube (MEDICIONES §41)
tope_fps=120
; 1 = el tope es FIJO en todo el juego (nunca hay cuadros de más); 0 = la red puede sumar cuadros
tope_estricto=1
; 1 = si llega un mensaje de red mientras se espera el cuadro, el juego lo atiende enseguida
;     (con el tope estricto, ese cuadro adelantado gasta el turno siguiente). MEDICIONES §42
red_inmediata=1
; 1 = los búferes de vértices sin frenar la placa en cada dibujo (DYNAMIC + DISCARD). MEDICIONES §42
buferes_rapidos=1
; 1 = «FPS 120» arriba a la izquierda
mostrar_fps=1
; ⛔ experimental: atender la red llamando al juego desde la espera (CONGELÓ los juegos el 11-nov)
bombeo_red=0
"""


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def compilar():
    if not os.path.isfile(ZIG):
        raise SystemExit("⛔ no encuentro Zig 0.16.0: %s (se puede indicar con la variable ZIG)" % ZIG)
    os.makedirs(SALIDA, exist_ok=True)
    for f in ("eda_d3d9.c", "d3d9.def"):
        shutil.copy(os.path.join(AQUI, f), SALIDA)
    dll = os.path.join(SALIDA, "d3d9.dll")
    if os.path.exists(dll):
        os.remove(dll)
    r = subprocess.run([ZIG, "cc", "-target", "x86-windows-gnu", "-shared", "-O2", "-s", "-o", "d3d9.dll",
                        "eda_d3d9.c", "d3d9.def", "-lkernel32", "-luser32", "-lwinmm", "-lws2_32"],
                       cwd=SALIDA, capture_output=True, text=True)
    if r.returncode or not os.path.isfile(dll):
        raise SystemExit("⛔ no compiló:\n" + (r.stderr or r.stdout)[-3000:])
    open(os.path.join(SALIDA, "eda_d3d9.ini"), "w", encoding="utf-8", newline="\r\n").write(INI)
    print("★ %s\n  %d B · md5 %s" % (dll, os.path.getsize(dll), md5(dll)))
    return dll


def poner():
    dll = os.path.join(SALIDA, "d3d9.dll")
    shutil.copy2(dll, os.path.join(JUEGO, "d3d9.dll"))
    if not os.path.exists(os.path.join(JUEGO, "eda_d3d9.ini")):
        shutil.copy2(os.path.join(SALIDA, "eda_d3d9.ini"), JUEGO)
    print("· puesta en %s" % JUEGO)


def sacar():
    for f in ("d3d9.dll", "eda_d3d9.ini", "eda_d3d9.log"):
        p = os.path.join(JUEGO, f)
        if os.path.exists(p):
            os.remove(p)
    print("· sacada de %s (el juego vuelve al d3d9 de Windows)" % JUEGO)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    if "--sacar" in sys.argv:
        sacar()
    else:
        compilar()
        if "--poner" in sys.argv:
            poner()
