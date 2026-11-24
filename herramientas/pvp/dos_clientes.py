r"""dos_clientes -- ★ PvP, etapa 0.1: DOS juegos independientes en esta PC contra un server local PROPIO.

    py herramientas\pvp\dos_clientes.py preparar               # una vez (y cada vez que cambie exe\ o _trabajo\juego)
    py herramientas\pvp\dos_clientes.py iniciar [--p2p auto|relay|directo]
    py herramientas\pvp\dos_clientes.py llevar [sala|listo|partida]   # los dos, del lobby a la stage 1011 (A anfitrión)
    py herramientas\pvp\dos_clientes.py estado
    py herramientas\pvp\dos_clientes.py cerrar                  # cierra todo y junta los registros de la sesión
    py herramientas\pvp\dos_clientes.py control                 # las pruebas (cada una con su revés), sin el juego

Por qué así (documentacion/PVP_MEDICIONES.md §1):
  · cada juego en SU carpeta (`<base>\A`, `<base>\B`): dos juegos en `_trabajo\juego` escriben el mismo
    eda_d3d9.log, NetTrace.log y autoexec.cfg. Los archivos grandes (Data.dat, mapas…) son enlaces duros a
    `_trabajo\juego` (no ocupan lugar; si el disco no deja, se copian). `_trabajo\juego` no se toca;
  · <base> = EDA_PVP_DIR o %USERPROFILE%\EDA_pvp: FUERA de OneDrive (no sube 300 MB por sesión);
  · el exe, la d3d9.dll y su ini son los del repo (exe\): se prueba el mismo cliente que reciben todos, sin Frida;
  · un server `servidor.red` propio en 127.0.0.1:27900 (no choca con `jugar.py`, que usa 25900), con su relay
    UDP local (28000…) y sus cuentas aparte (<base>\estado: `rui` y `kai`, GM las dos para /fin y /oro). Las
    cuentas las da el server por orden de llegada: la PRIMERA ventana que pasa la lista de servers es `rui`;
  · `--p2p relay` hace pasar TODO el UDP de la partida por el relay local: así se puede observar (etapa 0.3).
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
ORIGEN = os.path.join(RAIZ, "_trabajo", "juego")
EXE_REPO = os.path.join(RAIZ, "exe")
# ⚠ no %LOCALAPPDATA%: un programa empaquetado (MSIX) que lance esto lo ve redirigido a otra carpeta
BASE = os.environ.get("EDA_PVP_DIR") or os.path.join(os.path.expanduser("~"), "EDA_pvp")
INSTANCIAS = ("A", "B")
EXE = "EDA_limpio.exe"
PUERTO = 27900
RELAY_BASE = 28000
GRANDE = 1 << 20
# lo que el juego ESCRIBE (cada instancia el suyo) y lo que no hace falta para jugar
NO_ESPEJAR = (".log", ".dmp", ".rpt")
NO_HACE_FALTA = ("eis_", "unins")
DEL_REPO = ("EDA_limpio.exe", "d3d9.dll", "eda_d3d9.ini")
REGISTROS_CLIENTE = ("eda_d3d9.log", "eda_d3d9.anterior.log", "NetTrace.log", "EDA_limpio.rpt", "EDA_limpio.dmp")


def sesion_ruta(base=None):
    return os.path.join(base or BASE, "sesion.json")


def espejar(origen, destino):
    """Copia el árbol del juego: lo chico se copia, lo grande se enlaza (enlace duro; si no se puede, se copia).
    Devuelve {"copiados", "enlazados", "iguales", "saltados"}."""
    cuenta = {"copiados": 0, "enlazados": 0, "iguales": 0, "saltados": 0}
    for raiz, dirs, archivos in os.walk(origen):
        rel = os.path.relpath(raiz, origen)
        os.makedirs(os.path.join(destino, rel), exist_ok=True)
        for a in archivos:
            bajo = a.lower()
            if bajo.endswith(NO_ESPEJAR) or bajo.startswith(NO_HACE_FALTA) or (rel == "." and a in DEL_REPO):
                cuenta["saltados"] += 1
                continue
            src, dst = os.path.join(raiz, a), os.path.join(destino, rel, a)
            st = os.stat(src)
            if os.path.exists(dst):
                try:
                    if os.path.samefile(src, dst):
                        cuenta["iguales"] += 1
                        continue
                except OSError:
                    pass
                d = os.stat(dst)
                if d.st_size == st.st_size and int(d.st_mtime) == int(st.st_mtime):
                    cuenta["iguales"] += 1
                    continue
                os.remove(dst)
            if st.st_size >= GRANDE:
                try:
                    os.link(src, dst)
                    cuenta["enlazados"] += 1
                    continue
                except OSError:
                    pass
            shutil.copy2(src, dst)
            cuenta["copiados"] += 1
    return cuenta


def preparar():
    if not os.path.exists(os.path.join(ORIGEN, "Data.dat")):
        raise SystemExit('⛔ falta el juego en _trabajo\\juego. Primero: py jugar.py --preparar "C:\\ruta\\al\\cliente"')
    for f in DEL_REPO:
        if not os.path.exists(os.path.join(EXE_REPO, f)):
            raise SystemExit("⛔ falta exe\\%s en el repo" % f)
    os.makedirs(BASE, exist_ok=True)
    for i in INSTANCIAS:
        dst = os.path.join(BASE, i)
        c = espejar(ORIGEN, dst)
        for f in DEL_REPO:
            shutil.copy2(os.path.join(EXE_REPO, f), os.path.join(dst, f))
        print("· %s: %s → %d copiados, %d enlazados, %d iguales, %d saltados; exe, d3d9.dll e ini del repo"
              % (i, dst, c["copiados"], c["enlazados"], c["iguales"], c["saltados"]))
    print("✅ listo. Ahora: py herramientas\\pvp\\dos_clientes.py iniciar")


def puerto_libre(puerto, host="127.0.0.1"):
    s = socket.socket()
    try:
        s.bind((host, puerto))
        return True
    except OSError:
        return False
    finally:
        s.close()


def vivo(pid):
    if not pid:
        return False
    out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return '"%d"' % pid in out


def leer_sesion(base=None):
    try:
        return json.load(open(sesion_ruta(base), encoding="utf-8"))
    except (OSError, ValueError):
        return None


def acomodar(pid, x, y, espera=40):
    """Pone la ventana del juego en (x, y) para que las dos se vean juntas. Sólo la mueve."""
    import ctypes
    sys.path.insert(0, os.path.dirname(AQUI))
    from foto_juego import ventanas_de
    fin = time.time() + espera
    while time.time() < fin:
        v = ventanas_de(pid)
        if v:
            ctypes.windll.user32.SetWindowPos(v[0][0], 0, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)
            return True
        time.sleep(0.5)
    return False


def iniciar(p2p):
    s = leer_sesion()
    if s and (vivo(s.get("server")) or any(vivo(p) for p in s.get("clientes", {}).values())):
        raise SystemExit("⛔ ya hay una sesión andando (%s). Primero: dos_clientes.py cerrar" % s["carpeta"])
    for i in INSTANCIAS:
        if not os.path.exists(os.path.join(BASE, i, EXE)):
            raise SystemExit("⛔ falta preparar. Primero: py herramientas\\pvp\\dos_clientes.py preparar")
    for p in (PUERTO, PUERTO + 1):
        if not puerto_libre(p):
            raise SystemExit("⛔ el puerto %d está ocupado (¿otra sesión o un server colgado?)" % p)
    carpeta = os.path.join(BASE, "registros", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(carpeta)
    for i in INSTANCIAS:                       # lo que quedó de una sesión que no se cerró bien
        for f in REGISTROS_CLIENTE:
            r = os.path.join(BASE, i, f)
            if os.path.exists(r):
                shutil.move(r, os.path.join(carpeta, "previo_%s_%s" % (i, f)))
    env = dict(os.environ, PYTHONIOENCODING="utf-8", EDA_ESTADO=os.path.join(BASE, "estado"),
               EDA_PUERTO=str(PUERTO), EDA_RELAY_IP="127.0.0.1", EDA_RELAY_BASE=str(RELAY_BASE),
               EDA_P2P=p2p, EDA_GM_CUENTAS="rui,kai", EDA_LOGIN="abierto", EDA_ENTORNO="local")
    log = open(os.path.join(carpeta, "server.log"), "w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "servidor.red"], cwd=RAIZ, env=env, stdout=log,
                              stderr=subprocess.STDOUT)
    for _ in range(60):
        if not puerto_libre(PUERTO):
            break
        if server.poll() is not None:
            raise SystemExit("⛔ el server no arrancó: mirá %s" % os.path.join(carpeta, "server.log"))
        time.sleep(0.25)
    print("· server 127.0.0.1:%d (pid %d, P2P «%s», relay UDP %d…) → %s"
          % (PUERTO, server.pid, p2p, RELAY_BASE, os.path.join(carpeta, "server.log")))
    clientes = {}
    for n, i in enumerate(INSTANCIAS):
        d = os.path.join(BASE, i)
        # ★ la ruta ENTRE COMILLAS: sin ellas el exe toma su propia ruta como bloque del launcher y pisa la MAC
        #   (PROTOCOLO §5.1, «La línea de comandos del launcher»)
        p = subprocess.Popen('"%s"' % os.path.join(d, EXE), cwd=d,
                             env=dict(os.environ, EDA_SERVER="127.0.0.1:%d" % PUERTO))
        clientes[i] = p.pid
        ok = acomodar(p.pid, 0 if n == 0 else 820, 0)
        print("· juego %s: pid %d %s" % (i, p.pid, "" if ok else "(⚠ todavía sin ventana: acomodala a mano)"))
        time.sleep(2)
    json.dump({"inicio": time.strftime("%Y-%m-%d %H:%M:%S"), "carpeta": carpeta, "server": server.pid,
               "clientes": clientes, "puerto": PUERTO, "p2p": p2p}, open(sesion_ruta(), "w", encoding="utf-8"),
              indent=1)
    print("""
✅ los dos juegos abiertos (A a la izquierda, B a la derecha).
   1. En A: «EDA» de la lista → ENTER → el personaje (tiene que decir rui) → Enter Lobby.
   2. Recién entonces en B: lo mismo (tiene que decir kai).
   3. Seguí el procedimiento de documentacion\\PVP_MEDICIONES.md §2.
   Al terminar: py herramientas\\pvp\\dos_clientes.py cerrar""")


def llevar(hasta):
    """Los dos juegos, ya en el lobby (la dll entra sola con EDA_SERVER), hasta la sala o la partida, con
    `herramientas/multi.py` (que espera cada pantalla). A = anfitrión. La stage es la primera del selector
    (1011, Easy: la «stage controlada» de PVP_MEDICIONES.md §1)."""
    s = leer_sesion()
    if not s:
        raise SystemExit("⛔ no hay sesión. Primero: dos_clientes.py iniciar")
    sys.path.insert(0, os.path.dirname(AQUI))
    import multi
    import pantallas
    pids = [s["clientes"][i] for i in INSTANCIAS]
    for i, pid in zip(INSTANCIAS, pids):
        p = pantallas.esperar(pid, "lobby", 60)
        if p != "lobby":
            raise SystemExit("⛔ el juego %s no está en el lobby (está en «%s»)" % (i, p))
    multi.desde_el_lobby(pids, hasta, titulo="Duelo de prueba")
    for i, pid in zip(INSTANCIAS, pids):
        print("· juego %s: «%s»" % (i, pantallas.cual(pid)))
    return 0


def estado():
    s = leer_sesion()
    if not s:
        print("· no hay sesión")
        return 0
    print("· sesión %s (P2P «%s»), registros en %s" % (s["inicio"], s.get("p2p"), s["carpeta"]))
    print("  server pid %d: %s" % (s["server"], "andando" if vivo(s["server"]) else "cerrado"))
    for i, pid in s["clientes"].items():
        print("  juego %s pid %d: %s" % (i, pid, "abierto" if vivo(pid) else "cerrado"))
    return 0


def cerrar():
    s = leer_sesion()
    if not s:
        print("· no hay sesión")
        return 0
    for i, pid in s["clientes"].items():
        if vivo(pid):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
            print("· juego %s (pid %d) cerrado" % (i, pid))
    if vivo(s["server"]):
        subprocess.run(["taskkill", "/PID", str(s["server"]), "/T", "/F"], capture_output=True)
        print("· server (pid %d) cerrado" % s["server"])
    time.sleep(1)
    for i in s["clientes"]:
        for f in REGISTROS_CLIENTE:
            r = os.path.join(BASE, i, f)
            if os.path.exists(r):
                try:
                    shutil.move(r, os.path.join(s["carpeta"], "%s_%s" % (i, f)))
                except OSError as e:
                    print("  ⚠ %s: %s" % (r, e))
    os.remove(sesion_ruta())
    print("✅ registros de la sesión en %s" % s["carpeta"])
    return 0


def control():
    ok = []

    def chequear(nombre, cond):
        ok.append(bool(cond))
        print("  %s %s" % ("✅" if cond else "⛔", nombre))

    tmp = tempfile.mkdtemp()
    try:
        o, d = os.path.join(tmp, "o"), os.path.join(tmp, "d")
        os.makedirs(os.path.join(o, "sub"))
        open(os.path.join(o, "chico.txt"), "w").write("x")
        open(os.path.join(o, "sub", "grande.bin"), "wb").write(b"\0" * (GRANDE + 1))
        open(os.path.join(o, "NetTrace.log"), "w").write("de otra sesión")
        open(os.path.join(o, "EDA_limpio.exe"), "w").write("el viejo")
        open(os.path.join(o, "eis_090814_ver1.exe"), "w").write("instalador")
        c = espejar(o, d)
        chequear("lo chico se copia", os.path.exists(os.path.join(d, "chico.txt")) and c["copiados"] >= 1)
        g = os.path.join(d, "sub", "grande.bin")
        chequear("lo grande queda (enlazado o, si no se puede, copiado)",
                 os.path.exists(g) and os.path.getsize(g) == GRANDE + 1)
        chequear("★ el revés: los registros NO se espejan (cada instancia escribe el suyo)",
                 not os.path.exists(os.path.join(d, "NetTrace.log")))
        chequear("★ el revés: el exe de _trabajo\\juego NO se espeja (va el del repo) ni el instalador",
                 not os.path.exists(os.path.join(d, "EDA_limpio.exe"))
                 and not os.path.exists(os.path.join(d, "eis_090814_ver1.exe")))
        c2 = espejar(o, d)
        chequear("otra vez: nada nuevo (todo «igual»)", c2["copiados"] == 0 and c2["enlazados"] == 0)
        open(os.path.join(o, "chico.txt"), "w").write("cambió")
        os.utime(os.path.join(o, "chico.txt"), (time.time() + 5, time.time() + 5))
        espejar(o, d)
        chequear("si cambia el original, se actualiza", open(os.path.join(d, "chico.txt")).read() == "cambió")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    ocupado = s.getsockname()[1]
    chequear("un puerto en uso no está libre", not puerto_libre(ocupado))
    s.close()
    chequear("★ el revés: cerrado, vuelve a estar libre", puerto_libre(ocupado))
    chequear("este proceso está vivo", vivo(os.getpid()))
    chequear("★ el revés: un pid que no existe no está vivo", not vivo(0x7FFFFFF0))
    chequear("los puertos de la sesión no son los de jugar.py (25900) ni los del relay de siempre (26000)",
             PUERTO != 25900 and RELAY_BASE != 26000 and abs(RELAY_BASE - PUERTO) > 2)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    if cmd == "preparar":
        return preparar()
    if cmd == "iniciar":
        p2p = a[a.index("--p2p") + 1] if "--p2p" in a and a.index("--p2p") + 1 < len(a) else "auto"
        if p2p not in ("auto", "relay", "directo"):
            raise SystemExit("⛔ --p2p auto | relay | directo")
        return iniciar(p2p)
    if cmd == "llevar":
        hasta = a[1] if len(a) > 1 else "partida"
        if hasta not in ("sala", "listo", "partida"):
            raise SystemExit("⛔ llevar sala | listo | partida")
        return llevar(hasta)
    if cmd == "estado":
        return estado()
    if cmd == "cerrar":
        return cerrar()
    if cmd == "control":
        return control()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
