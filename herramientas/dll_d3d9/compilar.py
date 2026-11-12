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
INI = """; eda_d3d9.ini — los ajustes del d3d9.dll de EDA (herramientas/dll_d3d9, ver su LEEME.md)
; Cada BLOQUE se prende o se apaga solo. Por defecto: LO MÍNIMO (tope de cuadros + server) y la caja negra.
; (Las líneas que empiezan con «;» son comentarios.)

#####################################################################
# LO MÍNIMO: el server y el tope de cuadros
#####################################################################
[red]
; adónde se conecta el juego: host[:puerto] (puerto por defecto 25900). El cliente busca el server de
; Corea de 2009 (218.145.66.187:25000, que ya no existe) y la dll lo manda acá. Vacío = no se desvía
; (lo hace jugar.py). El launcher lo pasa como 3er argumento, que manda sobre esto.
server=

[video]
; el tope de cuadros por segundo (0 = sin tope). EDA no trae tope: sin él dibuja ~900 cuadros/s y la
; placa va a máxima potencia (MEDICIONES §41). (Esta clave y la de abajo las escribe el launcher.)
tope_fps=120
; 1 = «FPS 120» arriba a la izquierda
mostrar_fps=0

[general]
; 0 = ni siquiera lo de abajo ni el tope: el video y la red del juego como en 2009 (quedan el server,
;     el login del launcher y la caja negra). Para probar si un problema es de la dll
mejoras=1

#####################################################################
# LA CAJA NEGRA: si el juego se cae, eda_d3d9.log dice DÓNDE
#####################################################################
[cajanegra]
; (sólo mira: no cambia nada del juego) el módulo (el juego, NUESTRA dll o el driver), los registros
; y la cadena de llamadas. Mandar eda_d3d9.log y EDA_limpio.rpt
activo=1

#####################################################################
# PARCHES DE RUI (los nuestros)
#####################################################################
[rui]
; 0 = ninguno de este bloque
activo=0
; 1 = el tope es FIJO en todo el juego (nunca hay cuadros de más)
tope_estricto=1
; 1 = si llega un mensaje de red mientras se espera el cuadro, el juego lo atiende enseguida (el ping
;     no depende de los cuadros: 1 ms en la sala a 60 cuadros/s, MEDICIONES §42)
red_inmediata=1
; 1 = el ANILLO de vértices: los dibujos sin frenar la placa. Sirve con DOS juegos en la misma PC (sin
;     él caían a ~14 cuadros/s; MEDICIONES §42–43). Es lo que más toca (cada dibujo)
anillo_vertices=0

#####################################################################
# PARCHES DE HYSTERIA (PR #6)
#####################################################################
[hysteria]
; 0 = ninguno de este bloque
activo=1
; (⛔ medido: NO cambia el color del ping, que sigue rojo; queda apagado. Pendiente: el color de verdad)
ping_verde=0
; 1 = si las letras se ven CORTADAS A LA MITAD: sus texturas empiezan en 32×32 (toca 5 bytes del juego
;     en memoria, sólo si son los originales). En la mayoría de las PCs no hace falta
letras_32=0

#####################################################################
# PARCHES DE MAZINO (PR #1, #5, #9)
#####################################################################
[mazino]
; (todavía ninguno en la dll: su arreglo de la REGIÓN —el juego moría en los Windows en español— ya está
;  ADENTRO de EDA_limpio.exe, MEDICIONES §37; los demás son del server)
activo=0
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
                        "eda_d3d9.c", "d3d9.def", "-lkernel32", "-luser32", "-lwinmm", "-lws2_32", "-liphlpapi"],
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
