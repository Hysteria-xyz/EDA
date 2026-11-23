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
import json
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
# (o el que baja herramientas/dll_d3d9/bajar_zig.py a _trabajo/zig/, para quien no tiene el de R2Beat)
_ZIG_AQUI = os.path.join(RAIZ, "_trabajo", "zig", "zig-x86_64-windows-0.16.0", "zig.exe")
if not os.environ.get("ZIG") and not os.path.isfile(ZIG) and os.path.isfile(_ZIG_AQUI):
    ZIG = _ZIG_AQUI
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
; 1 = el ANILLO de vértices: el arreglo del «lag» del lobby y la sala (MEDICIONES §42-43). 0 = apagado
anillo=1

[general]
; 0 = ni siquiera lo de abajo ni el tope: el video y la red del juego como en 2009 (quedan el server,
;     el login del launcher y la caja negra). Para probar si un problema es de la dll
mejoras=1

[pantalla]
; ★ EXPERIMENTAL (Punto 5): la interfaz de 2009 (800×600) escalada y centrada en una pantalla más grande, con el
;   3D del Stage a resolución nativa. 0 = como siempre (800×600). Con 1, «resolucion» dice el tamaño (p. ej.
;   1920x1080); escala2d_stage=0 deja el HUD del Stage como hoy (arriba a la izquierda)
escala2d=0
resolucion=
escala2d_stage=1

[version]
; 1 = al arrancar, unos segundos arriba a la derecha: versión, compilación (commit) y entorno (TEST / PROD /
;     LOCAL, según el server de arriba). No toma el foco ni los clics. 0 = no se muestra (igual queda en
;     eda_d3d9.log y arriba a la izquierda de Options)
aviso=1

#####################################################################
# LA CAJA NEGRA: si el juego se cae, eda_d3d9.log dice DÓNDE
#####################################################################
[cajanegra]
; (sólo mira: no cambia nada del juego) el módulo (el juego, NUESTRA dll o el driver), los registros
; y la cadena de llamadas. Mandar eda_d3d9.log y EDA_limpio.rpt
activo=1

#####################################################################
# LAS LLAMADAS A WINDOWS QUE EL EXE TODAVÍA TIENE SIN RESOLVER (21-nov)
#####################################################################
[apis]
; 1 = al arrancar, la dll pone en EDA_limpio.exe la llamada original de 17 sitios de la CRT que quedaron
;     «sin resolver» al desempacar (IsValidLocale, GetCPInfo, GetStringTypeA…). Sin esto el juego se cae al
;     llegar a uno (medido: 0x7F4626 en una stage). Sólo si el exe es el conocido y en el sitio está la trampa.
reparar=1
; 1 = PRUEBA: en el primer cuadro la dll llama al setlocale del juego con «korean» y lo restituye (el camino
;     de la caída del 21-nov). Dejar en 0 para jugar
probar_locale=0

#####################################################################
# EL DIAGNÓSTICO AUTOMÁTICO (21-nov) — SÓLO en el server de PRUEBA
#####################################################################
[diag]
; la dirección del server de prueba que recibe los eventos (https://…/eda/diag; http sólo a 127.0.0.1).
; Vacío = apagado. Aunque esté puesta, la dll NO manda nada si el entorno no es TEST o si el juego no se lanzó
; con usuario y ticket (el launcher). Manda eventos chicos (escena, congelado, fps, foco, caída), sin MAC, IP,
; nombre de la PC ni chat. EDA_DIAG_URL manda sobre esto.
url=

#####################################################################
# TRADUCCIÓN EN MEMORIA (23-nov) — español embebido por defecto
#####################################################################
[traduccion]
; idioma de la interfaz (es = español embebido en la dll; si existe traducciones\\<idioma>\\ junto al juego,
; esos archivos sueltos tienen prioridad para probar cambios sin recompilar). en / off = el juego original
; en inglés (sin enganchar nada). Respeta [general] mejoras=0. EDA_IDIOMA manda sobre esto.
idioma=es
; 1 = con idioma=es, también traduce en memoria 3 etiquetas cortas del exe (LV%3d → Nv%3d, %dGold → %d Oro)
cadenas_exe=1
; 1 = diagnóstico de glifos FreeType (anota en eda_d3d9.log medidas y mapa de ñ, Ñ, ó, n, ü; 0 para jugar)
diag_glifos=0

#####################################################################
# P2P: que los juegos se encuentren (sin pasar por el server)
#####################################################################
[p2p]
; 0 = ninguno de este bloque (la partida igual anda, por el relay del server)
activo=1
; 1 = la identidad del juego (su MAC) llega al server: el ticket del launcher la pisaba
mac=1
; 1 = la IP de la casa que se le da al otro es la de la red de verdad (cable o WiFi, la que se usa),
;     no la de una red virtual (VMware, VirtualBox, Hyper-V)
ip_privada=1
; 1 = el juego atiende la red apenas llega un paquete, sin esperar al próximo cuadro (el ping de la sala
;     baja de decenas de ms a ~1 ms + la red; MEDICIONES §42). Sólo corta la espera del tope de cuadros
red_inmediata=1

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
; ★ (14-nov) lo que antes hacía Frida (herramientas/eda_original.py), ahora en la dll: llega a todos con el
;   launcher. Prendido por defecto; cada uno se apaga solo (0). MEDICIONES §57
activo=1
; 1 = los botones Clan / Messenger / Options de arriba (el cliente de 2009 no los une a nada): en el lobby y en
;     Shop / Inventory / Refinery / Skill mandan /clan, /messenger, /opciones al server
botones=1
; 1 = Ctrl+clic en la bolsa marca VARIAS casillas (con la selección del propio juego); «Sell» vende todas
seleccion_multiple=1
; 1 = EDA no se pausa al cambiar de ventana, y no centra ni encierra el mouse si no está al frente
foco=1
; 1 = el botón Options abre la ventana de opciones de la dll (anda igual en local y en multijugador)
opciones=1
; 1 = F11 y el botón Messenger abren el Messenger de la dll (amigos y mensajes; local y multijugador, sin Python).
;     0 = como antes: mandan /messenger al server (el panel de Python, sólo con el server en la misma PC)
messenger=1
"""


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


GENERADOS = {"eda_version.h", "eda_traduccion_datos.h"}


def traduccion_archivos(raiz=RAIZ):
    """Lista ordenada [(idioma, ruta_solfs_norm, ruta_disco)] de traduccion/<idioma>/** para embeber en la DLL."""
    import re
    base = os.path.join(raiz, "traduccion")
    if not os.path.isdir(base):
        return []
    salida = []
    for idi in sorted(os.listdir(base)):
        if idi == "herramientas" or idi.startswith((".", "_")):
            continue
        if not re.fullmatch(r"[a-z0-9_-]{2,15}", idi):
            continue
        carp_idi = os.path.join(base, idi)
        if not os.path.isdir(carp_idi):
            continue
        for rdir, dirs, files in os.walk(carp_idi):
            dirs.sort()
            for fn in sorted(files):
                p = os.path.join(rdir, fn)
                rel = os.path.relpath(p, carp_idi).replace("/", "\\").lower()
                salida.append((idi, rel, p))
    return sorted(salida, key=lambda x: (x[0], x[1]))


def generar_traduccion_header(ruta_h, raiz=RAIZ):
    """Genera `eda_traduccion_datos.h` con cada archivo de traduccion/<idioma>/** como arreglo de bytes."""
    entradas = traduccion_archivos(raiz)
    lineas = [
        "/* eda_traduccion_datos.h -- GENERADO por compilar.py desde traduccion/<idioma>/ (no editar ni commitear) */",
        "#ifndef EDA_TRADUCCION_DATOS_H",
        "#define EDA_TRADUCCION_DATOS_H",
        "",
        "typedef struct {",
        "    const char *idioma;",
        "    const char *ruta;",
        "    const unsigned char *datos;",
        "    unsigned long tam;",
        "} TR_EMBEBIDO;",
        "",
    ]
    total_bytes = 0
    idiomas = sorted({idi for idi, _, _ in entradas})
    for idx, (idi, rel, p) in enumerate(entradas):
        raw = open(p, "rb").read()
        total_bytes += len(raw)
        lineas.append("/* %s/%s (%d B) */" % (idi, rel.replace("\\", "/"), len(raw)))
        lineas.append("static const unsigned char TR_EMB_D%d[%d] = {" % (idx, max(1, len(raw))))
        if raw:
            for off in range(0, len(raw), 16):
                chunk = raw[off:off + 16]
                lineas.append("    " + ",".join("0x%02X" % b for b in chunk) + ",")
        else:
            lineas.append("    0x00")
        lineas.append("};")
        lineas.append("")
    lineas.append("static const TR_EMBEBIDO TR_EMBEBIDOS[] = {")
    if entradas:
        for idx, (idi, rel, p) in enumerate(entradas):
            sz = os.path.getsize(p)
            rel_c = rel.replace("\\", "\\\\").replace('"', '\\"')
            lineas.append('    {"%s", "%s", TR_EMB_D%d, %du},' % (idi, rel_c, idx, sz))
    else:
        lineas.append("    {0, 0, 0, 0u}")
    lineas.append("};")
    lineas.append("#define TR_NEMBEBIDOS %d" % len(entradas))
    lineas.append("")
    lineas.append("#endif /* EDA_TRADUCCION_DATOS_H */")
    os.makedirs(os.path.dirname(os.path.abspath(ruta_h)), exist_ok=True)
    open(ruta_h, "w", encoding="utf-8", newline="\n").write("\n".join(lineas) + "\n")
    return len(entradas), total_bytes, idiomas


def fuentes():
    """lo que se copia a la carpeta de compilación"""
    return sorted(x for x in os.listdir(AQUI) if x.startswith("eda_") and x.endswith((".c", ".h"))
                  and x not in GENERADOS) + ["d3d9.def"]            # (los GENERADOS los arman version.py y compilar.py)


def control_fuentes():
    """(CI) copia como compilar() y verifica que no falte ningún #include: lo que rompió la 1ª compilación de 0.5.1"""
    import tempfile
    d = tempfile.mkdtemp()
    for f in fuentes():
        shutil.copy(os.path.join(AQUI, f), d)
    n_emb, b_emb, idis = generar_traduccion_header(os.path.join(d, "eda_traduccion_datos.h"))
    faltan = incluidos_que_faltan(os.path.join(d, "eda_d3d9.c"), d)
    shutil.rmtree(d, ignore_errors=True)
    print("fuentes: %d copiados · embebidos: %d (%d B, %s) · %s" % (
        len(fuentes()), n_emb, b_emb, ",".join(idis) or "ninguno",
        "faltan: " + ", ".join(faltan) if faltan else "ninguno falta"))
    return not faltan


def incluidos_que_faltan(fuente, carpeta, vistos=None):
    """los #include "x.c" / "x.h" (recursivos) que no están en la carpeta de compilación"""
    import re
    vistos = set() if vistos is None else vistos
    faltan = []
    for m in re.finditer(r'^\s*#include\s+"([^"]+\.[ch])"', open(fuente, encoding="utf-8", errors="replace").read(), re.M):
        f = m.group(1)
        if f in vistos or f == "eda_version.h":                      # (la genera version.py después)
            continue
        vistos.add(f)
        p = os.path.join(carpeta, f)
        if not os.path.isfile(p):
            faltan.append(f)
        else:
            faltan += incluidos_que_faltan(p, carpeta, vistos)
    return faltan


def compilar():
    if not os.path.isfile(ZIG):
        raise SystemExit("⛔ no encuentro Zig 0.16.0: %s (se puede indicar con la variable ZIG)" % ZIG)
    os.makedirs(SALIDA, exist_ok=True)
    # ★ (21-nov) TODOS los eda_*.c y eda_*.h (antes una lista fija: un módulo nuevo, eda_apis.c, quedaba afuera)
    for f in fuentes():
        shutil.copy(os.path.join(AQUI, f), SALIDA)
    n_emb, b_emb, idis = generar_traduccion_header(os.path.join(SALIDA, "eda_traduccion_datos.h"))
    faltan = incluidos_que_faltan(os.path.join(SALIDA, "eda_d3d9.c"), SALIDA)
    if faltan:
        raise SystemExit("⛔ eda_d3d9.c incluye archivos que no están: %s" % ", ".join(faltan))
    # ★ (19-nov) la identidad (versión, commit, sucio, fecha, build): la calcula version.py, nadie la escribe a mano
    sys.path.insert(0, AQUI)
    import version
    ident = version.escribir_header(os.path.join(SALIDA, "eda_version.h"))
    dll = os.path.join(SALIDA, "d3d9.dll")
    if os.path.exists(dll):
        os.remove(dll)
    r = subprocess.run([ZIG, "cc", "-target", "x86-windows-gnu", "-shared", "-O2", "-s", "-o", "d3d9.dll",
                        "eda_d3d9.c", "d3d9.def", "-lkernel32", "-luser32", "-lwinmm", "-lws2_32", "-liphlpapi", "-lgdi32"],
                       cwd=SALIDA, capture_output=True, text=True)
    if r.returncode or not os.path.isfile(dll):
        raise SystemExit("⛔ no compiló:\n" + (r.stderr or r.stdout)[-3000:])
    open(os.path.join(SALIDA, "eda_d3d9.ini"), "w", encoding="utf-8", newline="\r\n").write(INI)
    # ★ (19-nov) el manifiesto de ESTA compilación: la identidad + el hash del archivo final (que no puede ir adentro)
    datos = open(dll, "rb").read()
    manif = dict(ident, archivo="d3d9.dll", tam=len(datos), md5=hashlib.md5(datos).hexdigest(),
                 sha256=hashlib.sha256(datos).hexdigest())
    open(dll + ".json", "w", encoding="utf-8", newline="\n").write(json.dumps(manif, ensure_ascii=False, indent=2) + "\n")
    print("★ %s\n  %d B · md5 %s · traducción embebida: %d archivo(s) (%d B, %s)" % (
        dll, len(datos), manif["md5"], n_emb, b_emb, ",".join(idis) or "ninguno"))
    print("  EDA %s · commit %s%s · build %s · %s%s" % (ident["version"], ident["commit"],
          "-dirty (LOCAL: cambios sin commitear)" if ident["sucio"] else "", ident["build"], ident["fecha"],
          "" if ident["en_github"] is None else " · en GitHub: %s" % ("sí" if ident["en_github"] else "NO (sólo local)")))
    for c in ident["cambios"][:12]:
        print("    cambio: %s" % c)
    print("  manifiesto: %s" % (dll + ".json"))
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
    if "--generar-traduccion" in sys.argv:
        i = sys.argv.index("--generar-traduccion")
        ruta = sys.argv[i + 1] if i + 1 < len(sys.argv) else os.path.join(AQUI, "eda_traduccion_datos.h")
        n_emb, b_emb, idis = generar_traduccion_header(ruta)
        print("%s → %d archivo(s) embebido(s) (%d B, idiomas: %s)" % (
            ruta, n_emb, b_emb, ", ".join(idis) or "ninguno"))
    elif "--sacar" in sys.argv:
        sacar()
    else:
        compilar()
        if "--poner" in sys.argv:
            poner()
