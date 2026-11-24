r"""dos_clientes -- ★ PvP, etapa 0.1: DOS juegos independientes en esta PC contra un server local PROPIO.

    py herramientas\pvp\dos_clientes.py preparar [--dll CARPETA]   # una vez (y cada vez que cambie exe\ o _trabajo\juego)
        --dll: la d3d9.dll + ini de la release «cliente-develop» (gh release download cliente-develop), verificadas
        con su cliente-develop.json. ⚠ exe\d3d9.dll del repo es la del Punto 4 (md5 d7df418b): NO carga traducciones\
    py herramientas\pvp\dos_clientes.py recursos instalar [carpeta …] [--grupos] [--sin-teleport]   # la arena (u otras) en A y B
    py herramientas\pvp\dos_clientes.py recursos quitar                # A y B vuelven a leer sólo Data.dat
    py herramientas\pvp\dos_clientes.py iniciar [--p2p auto|relay|directo] [--hex] [--pvp]
        --hex: cada mensaje en server.log · --pvp: el server árbitro del duelo (EDA_PVP=1, servidor/duelo.py)
        --auto: [mazino] entrada=0 en A y B, para que combate_auto.py / control_partida.py muevan a los personajes
        --batalla: [pvp] batalla=1 en A y B (la pestaña Battle manda /batalla; hace falta preparar --dll-local)
    py herramientas\pvp\dos_clientes.py preparar --dll-local     # la d3d9.dll compilada acá (_trabajo\dll) en A y B
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


def md5(ruta):
    import hashlib
    return hashlib.md5(open(ruta, "rb").read()).hexdigest()


def dll_verificada(carpeta):
    """La d3d9.dll y su ini de `carpeta` (p. ej. la release «cliente-develop»), SÓLO si coinciden con su lista
    cliente-develop.json (md5). Devuelve {"d3d9.dll": ruta, "eda_d3d9.ini": ruta}."""
    lista = os.path.join(carpeta, "cliente-develop.json")
    if not os.path.exists(lista):
        raise SystemExit("⛔ --dll: falta %s (sin la lista no se verifica)" % lista)
    datos = json.load(open(lista, encoding="utf-8"))
    out = {}
    for f in ("d3d9.dll", "eda_d3d9.ini"):
        esperado = next((x["md5"] for x in datos.get("files", []) if x.get("path") == f), None)
        r = os.path.join(carpeta, f)
        if not esperado or not os.path.exists(r) or md5(r) != esperado:
            raise SystemExit("⛔ --dll: %s no coincide con la lista (esperado %s)" % (f, esperado))
        out[f] = r
    print("· dll %s (commit %s, rama %s) verificada: md5 %s" % (datos.get("version"), datos.get("commit"),
                                                            str(datos.get("rama_commit"))[:7], md5(out["d3d9.dll"])))
    return out


def poner_dll_local():
    """La d3d9.dll recién compilada (herramientas/dll_d3d9/compilar.py → _trabajo\\dll) en A y B; el ini queda."""
    src = os.path.join(RAIZ, "_trabajo", "dll", "d3d9.dll")
    if not os.path.exists(src):
        raise SystemExit("⛔ falta %s (compilar.py)" % src)
    for i in INSTANCIAS:
        shutil.copy2(src, os.path.join(BASE, i, "d3d9.dll"))
    print("· d3d9.dll COMPILADA EN ESTA PC en A y B: md5 %s (%s)" % (md5(src), src))


def preparar(dll=None):
    if not os.path.exists(os.path.join(ORIGEN, "Data.dat")):
        raise SystemExit('⛔ falta el juego en _trabajo\\juego. Primero: py jugar.py --preparar "C:\\ruta\\al\\cliente"')
    for f in DEL_REPO:
        if not os.path.exists(os.path.join(EXE_REPO, f)):
            raise SystemExit("⛔ falta exe\\%s en el repo" % f)
    fuentes = {f: os.path.join(EXE_REPO, f) for f in DEL_REPO}
    if dll:
        fuentes.update(dll_verificada(dll))
    os.makedirs(BASE, exist_ok=True)
    for i in INSTANCIAS:
        dst = os.path.join(BASE, i)
        c = espejar(ORIGEN, dst)
        for f, src in fuentes.items():
            shutil.copy2(src, os.path.join(dst, f))
        print("· %s: %s → %d copiados, %d enlazados, %d iguales, %d saltados; d3d9.dll md5 %s (%s)"
              % (i, dst, c["copiados"], c["enlazados"], c["iguales"], c["saltados"],
                 md5(os.path.join(dst, "d3d9.dll")), "verificada de --dll" if dll else "la de exe\\ del repo"))
    print("✅ listo. Ahora: py herramientas\\pvp\\dos_clientes.py iniciar")


ARENA = os.path.join(AQUI, "arena")
SUELTOS = os.path.join("traducciones", "es")      # eda_traduccion.c: <carpeta_exe>\traducciones\<idioma>\<ruta>
CAPA_PVP = "pvp"                                   # eda_traduccion.c (24-nov): <carpeta_exe>\pvp\<ruta>, con [pvp] batalla=1
INSTALADOS = "pvp_recursos.json"


GRUPOS_APAGADO = "PVP_GRUPOS     = false"
GRUPOS_PRENDIDO = "PVP_GRUPOS     = true "
TELEPORT_PRENDIDO = "PVP_TELEPORT   = true "
TELEPORT_APAGADO = "PVP_TELEPORT   = false"


def recursos_instalar(origen=ARENA, base=None, grupos=False, sin_teleport=False):
    """Copia los recursos experimentales (misma ruta relativa que en Data.dat) a cada instancia, donde la dll los
    sirve en lugar de los de Data.dat (idioma «es», el de fábrica). Sólo en EDA_pvp\\A y \\B: nadie más los ve.
    `origen` = una carpeta o una lista de carpetas (p. ej. la arena y la interfaz de Battle)."""
    base = base or BASE
    origenes = [origen] if isinstance(origen, str) else list(origen)
    archivos = []
    de = {}
    capa_de = {}
    for o in origenes:
        # ★ (24-nov) la interfaz de Battle (battle_ui.py) va a la capa pvp\ de la dll ([pvp] batalla=1: la sala con
        #   equipos sólo en salas de duelo); lo demás (la arena) a la carpeta suelta de la traducción
        capa = CAPA_PVP if os.path.basename(os.path.normpath(o)).lower() == "battle_ui" else SUELTOS
        for raiz, _, nombres in os.walk(o):
            for n in nombres:
                if n.lower() in ("leeme.md",) or n.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(raiz, n), o)
                if rel not in de:
                    archivos.append(rel)
                de[rel] = os.path.join(o, rel)
                capa_de[rel] = capa
    if not archivos:
        raise SystemExit("⛔ no hay recursos en %s" % ", ".join(origenes))
    for i in INSTANCIAS:
        inst = os.path.join(base, i)
        if not os.path.isdir(inst):
            raise SystemExit("⛔ falta preparar %s" % inst)
        recursos_quitar(base, solo=i, callado=True)
        puestos = []
        for rel in archivos:
            dst = os.path.join(inst, capa_de[rel], rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(de[rel], dst)
            cambios = ([(GRUPOS_APAGADO, GRUPOS_PRENDIDO)] if grupos else []) + \
                      ([(TELEPORT_PRENDIDO, TELEPORT_APAGADO)] if sin_teleport else [])
            if cambios and rel.lower().endswith(".lua"):
                t = open(dst, encoding="latin-1").read()
                for viejo, nuevo in cambios:
                    if viejo not in t:
                        raise SystemExit("⛔ %s no tiene «%s»" % (rel, viejo))
                    t = t.replace(viejo, nuevo, 1)
                open(dst, "w", encoding="latin-1", newline="").write(t)
            puestos.append(os.path.join(capa_de[rel], rel))
        json.dump(puestos, open(os.path.join(inst, INSTALADOS), "w", encoding="utf-8"), indent=1)
        print("· %s: %d recurso(s) experimental(es)%s%s: %s" % (i, len(puestos), " [PVP_GRUPOS = true]" if grupos else "",
                                                               " [sin teleport]" if sin_teleport else "", ", ".join(puestos)))
    return archivos


def recursos_quitar(base=None, solo=None, callado=False):
    base = base or BASE
    for i in ([solo] if solo else INSTANCIAS):
        inst = os.path.join(base, i)
        lista = os.path.join(inst, INSTALADOS)
        if not os.path.exists(lista):
            continue
        for rel in json.load(open(lista, encoding="utf-8")):
            r = os.path.join(inst, rel)
            if os.path.exists(r):
                os.remove(r)
        os.remove(lista)
        if not callado:
            print("· %s: recursos experimentales quitados (vuelve a leer Data.dat)" % i)


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


def poner_ini(inst, seccion, clave, valor):
    import ctypes
    ctypes.windll.kernel32.WritePrivateProfileStringW(seccion, clave, str(valor), os.path.join(inst, "eda_d3d9.ini"))


def iniciar(p2p, hexa=False, pvp=False, auto=False, batalla=False):
    # ★ (24-nov) --auto: la dll 0.5.4 sólo deja pasar el teclado y el mouse «con EDA al frente» ([mazino] entrada) y
    #   tapa lo que mete control_partida.py (medido: kai quieto aun al frente). Para que las pruebas automáticas
    #   manejen a los personajes se apaga ESO, sólo en estas dos instalaciones; sin --auto vuelve a 1 (lo de fábrica)
    for i in INSTANCIAS:
        if os.path.isdir(os.path.join(BASE, i)):
            poner_ini(os.path.join(BASE, i), "mazino", "entrada", 0 if auto else 1)
            poner_ini(os.path.join(BASE, i), "pvp", "batalla", 1 if batalla else 0)   # (la pestaña Battle, dll compilada)
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
               EDA_P2P=p2p, EDA_GM_CUENTAS="rui,kai", EDA_LOGIN="abierto", EDA_ENTORNO="local",
               EDA_LOG_HEX="1" if hexa else "", EDA_PVP="1" if pvp else "")
    for i in INSTANCIAS:
        if os.path.exists(os.path.join(BASE, i, INSTALADOS)):
            print("· %s con recursos EXPERIMENTALES (%s)" % (i, os.path.join(BASE, i, INSTALADOS)))
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
    # ★ (24-nov) con la dll 0.5.4 el juego se queda en la LISTA DE SERVIDORES (la del Punto 4 entraba sola): se lo
    #   lleva con piloto.py, como multi.py, de a uno y en orden (el 1º que entra es rui)
    for i, pid in zip(INSTANCIAS, pids):
        p = pantallas.esperar(pid, ("lobby", "dialogo"), 8)
        for _ in range(3):
            if p == "lobby":
                break
            if p == "dialogo":
                multi.clic(pid, *pantallas.CANCEL_DIALOGO)
            else:
                multi.piloto(pid, "lobby")
            p = pantallas.esperar(pid, ("lobby", "dialogo"), 20)
        if p != "lobby":
            raise SystemExit("⛔ el juego %s no llegó al lobby (está en «%s»)" % (i, p))
        print("· juego %s en el lobby" % i, flush=True)
    if hasta == "lobby":
        return 0
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
        base = os.path.join(tmp, "base")
        for i in INSTANCIAS:
            os.makedirs(os.path.join(base, i))
        rec = os.path.join(tmp, "rec", "data", "scenario")
        os.makedirs(rec)
        open(os.path.join(rec, "x.lua"), "w").write("-- arena")
        open(os.path.join(tmp, "rec", "LEEME.md"), "w").write("no va")
        recursos_instalar(os.path.join(tmp, "rec"), base)
        puesto = os.path.join(base, "A", SUELTOS, "data", "scenario", "x.lua")
        chequear("recursos: el guion va a <instancia>\\traducciones\\es\\<misma ruta> en A y en B",
                 os.path.exists(puesto) and os.path.exists(puesto.replace(os.sep + "A" + os.sep, os.sep + "B" + os.sep)))
        chequear("★ el revés: el LEEME no se instala", not os.path.exists(os.path.join(base, "A", SUELTOS, "LEEME.md")))
        open(os.path.join(base, "A", SUELTOS, "data", "scenario", "del_jugador.lua"), "w").write("ajeno")
        recursos_quitar(base, callado=True)
        chequear("recursos quitar: se va lo instalado", not os.path.exists(puesto))
        chequear("★ el revés: lo que no instaló esta herramienta queda",
                 os.path.exists(os.path.join(base, "A", SUELTOS, "data", "scenario", "del_jugador.lua")))
        open(os.path.join(rec, "x.lua"), "w").write("PVP_GRUPOS     = false\n")
        otra = os.path.join(tmp, "otra", "menu")
        os.makedirs(otra)
        open(os.path.join(otra, "y.xml"), "w").write("<y/>")
        recursos_instalar([os.path.join(tmp, "rec"), os.path.join(tmp, "otra")], base, grupos=True)
        en_b = os.path.join(base, "B", SUELTOS)
        bui = os.path.join(tmp, "battle_ui", "menu")
        os.makedirs(bui)
        open(os.path.join(bui, "z.xml"), "w").write("<z/>")
        recursos_instalar([os.path.join(tmp, "rec"), os.path.join(tmp, "battle_ui")], base)
        chequear("la carpeta battle_ui va a la capa pvp\\ y la arena a traducciones\\es\\",
                 os.path.exists(os.path.join(base, "B", CAPA_PVP, "menu", "z.xml"))
                 and not os.path.exists(os.path.join(base, "B", SUELTOS, "menu", "z.xml"))
                 and os.path.exists(os.path.join(base, "B", SUELTOS, "data", "scenario", "x.lua")))
        recursos_instalar([os.path.join(tmp, "rec"), os.path.join(tmp, "otra")], base, grupos=True)
        chequear("varias carpetas + --grupos: todo llega a A y a B (el guion con PVP_GRUPOS = true)",
                 all(os.path.exists(os.path.join(base, i, SUELTOS, "menu", "y.xml")) for i in INSTANCIAS)
                 and "PVP_GRUPOS     = true" in open(os.path.join(en_b, "data", "scenario", "x.lua")).read())
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
        if "--dll-local" in a:
            return poner_dll_local()
        return preparar(a[a.index("--dll") + 1] if "--dll" in a and a.index("--dll") + 1 < len(a) else None)
    if cmd == "iniciar":
        p2p = a[a.index("--p2p") + 1] if "--p2p" in a and a.index("--p2p") + 1 < len(a) else "auto"
        if p2p not in ("auto", "relay", "directo"):
            raise SystemExit("⛔ --p2p auto | relay | directo")
        return iniciar(p2p, hexa="--hex" in a, pvp="--pvp" in a, auto="--auto" in a, batalla="--batalla" in a)
    if cmd == "recursos":
        if a[1:2] == ["quitar"]:
            return recursos_quitar()
        resto = [x for x in a[2:] if not x.startswith("--")] if a[1:2] == ["instalar"] else []
        recursos_instalar(resto or ARENA, grupos="--grupos" in a, sin_teleport="--sin-teleport" in a)
        return 0
    if cmd == "llevar":
        hasta = a[1] if len(a) > 1 else "partida"
        if hasta not in ("lobby", "sala", "listo", "partida"):
            raise SystemExit("⛔ llevar lobby | sala | listo | partida")
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
