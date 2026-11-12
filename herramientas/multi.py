r"""multi -- DOS (o más) clientes a la vez, solos, hasta la misma partida: la prueba del multijugador.

    py herramientas\multi.py [jugadores=2] [hasta=partida]     # hasta: lobby | sala | listo | partida

Abre N `EDA_limpio.exe` (el segundo abre normal: el mutex de instancia única no lo frena), lleva
cada uno al lobby con `piloto.py` (EDA_PID), el primero crea la sala, los demás entran (fila +
Enter → 0x101F), aprietan F9 Ready, y el anfitrión F9 Start. Con `servidor/juego.py` cada conexión
tiene su cuenta (rui, kai, mio…). Deja los pids en `_trabajo/multi_pids.txt` y una foto de cada
ventana por paso en `_trabajo/fotos/multi_<paso>.png` (todas juntas).

⚠ Cada clic va con la ventana «activada» por mensaje (WM_ACTIVATEAPP / WM_ACTIVATE): con varias
  ventanas abiertas, sin eso los clics en la sala y en el selector no hacen nada (medido).
"""
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clic_juego as C                                       # noqa: E402
import foto_juego as F                                       # noqa: E402
import pantallas as P                                        # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
PILOTO = os.path.join(RAIZ, "herramientas", "piloto.py")


def activar(pid):
    h = C.ventana(pid)
    C.u32.PostMessageW(h, 0x1C, 1, 0)
    C.u32.PostMessageW(h, 0x06, 1, 0)
    time.sleep(0.4)
    return h


def clic(pid, x, y, doble=False):
    h = activar(pid)
    C.clic(h, x, y, pausa=0.03 if doble else 0.12)
    if doble:
        time.sleep(0.12)
        C.clic(h, x, y, pausa=0.03)


def fotos(pids, paso):
    from PIL import Image
    ims = []
    for pid in pids:
        v = F.ventanas_de(pid)
        if v:
            ims.append(F.foto(v[0][0], v[0][3], v[0][4]).resize((400, 300)))
    if ims:
        m = Image.new("RGB", (400 * len(ims), 300))
        for i, im in enumerate(ims):
            m.paste(im, (400 * i, 0))
        ruta = os.path.join(RAIZ, "_trabajo", "fotos", "multi_%s.png" % paso)
        m.save(ruta)
        print("  %-10s %s" % (paso, ruta), flush=True)


def contar(cmd):
    """★ Cuántas veces vio el SERVER el comando `cmd` ("1017", "101d"…). Lee el registro que haya:
      · EDA_MULTI_SSH="usuario@host contenedor" → `docker logs` de ese contenedor (un VPS; la llave,
        si hace falta, en EDA_MULTI_LLAVE);
      · EDA_MULTI_LOG=<archivo> → el registro de `servidor/red.py` (local);
      · si no, el del espía de Windows (`_trabajo/broker/espia.log`).
    ⚠ Antes leía SÓLO el del espía: contra red.py o un VPS nunca veía avanzar nada y repetía clics
    que desarmaban la sala (medido 11-nov)."""
    if os.environ.get("EDA_MULTI_SSH"):
        destino, contenedor = os.environ["EDA_MULTI_SSH"].split()
        llave = ["-i", os.environ["EDA_MULTI_LLAVE"]] if os.environ.get("EDA_MULTI_LLAVE") else []
        t = subprocess.run(["ssh", "-o", "BatchMode=yes"] + llave + [destino, "docker logs %s 2>&1" % contenedor],
                           capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    else:
        ruta = os.environ.get("EDA_MULTI_LOG") or os.path.join(RAIZ, "_trabajo", "broker", "espia.log")
        try:
            t = open(ruta, encoding="utf-8", errors="replace").read()
        except OSError:
            t = ""
    return t.count("comando %s" % cmd) + t.count("← %s " % cmd)


def piloto(pid, hasta, desde=None):
    env = dict(os.environ, EDA_PID=str(pid), PYTHONIOENCODING="utf-8")
    if desde:
        env["EDA_DESDE"] = desde
    subprocess.run([sys.executable, PILOTO, hasta], env=env, capture_output=True, timeout=240)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    hasta = sys.argv[2] if len(sys.argv) > 2 else "partida"
    pids = []
    if os.environ.get("EDA_MULTI_PIDS"):
        # ★ juegos YA abiertos (p. ej. el EDA.exe de 2009 con `jugar.py --original`): sólo se manejan
        pids = [int(x) for x in os.environ["EDA_MULTI_PIDS"].split()]
        n = 0
    else:
        subprocess.run(["taskkill", "/F", "/IM", "EDA_limpio.exe"], capture_output=True)
        # ⚠ abrir enseguida después de matar a los anteriores: los nuevos se cayeron al arrancar en
        #   mss32.dll (el sonido, 17:55: 🟡 el dispositivo todavía tomado). Unos segundos de margen.
        time.sleep(6)
    for i in range(n):
        # ⚠ entre comillas: si no, el juego pisa su MAC del 0x100F (MEDICIONES §39)
        p = subprocess.Popen('"%s"' % os.path.join(JUEGO, "EDA_limpio.exe"), cwd=JUEGO)
        pids.append(p.pid)
        time.sleep(3)
    open(os.path.join(RAIZ, "_trabajo", "multi_pids.txt"), "w").write(" ".join(map(str, pids)))
    print("★ pids %s" % pids, flush=True)
    for pid in pids:
        # ★ se MIRA la pantalla (herramientas/pantallas.py) en vez de contar mensajes con un plazo
        #   fijo: a 60 cuadros/s el 0x1017 llegaba después de los 2 s, multi creía que no había
        #   entrado y repetía el piloto ENTERO sobre un juego que ya estaba en el lobby; ahí
        #   «Enter Lobby» cae sobre «Search User» y quedaba un diálogo abierto (11-nov)
        for intento in range(3):
            piloto(pid, "lobby")
            p = P.esperar(pid, ("lobby", "dialogo"), 20)
            if p == "dialogo":
                clic(pid, *P.CANCEL_DIALOGO)
                p = P.esperar(pid, "lobby", 5)
            if p == "lobby":
                break
            print("  (pid %d no llegó al lobby: está en «%s», otra vez)" % (pid, p), flush=True)
    fotos(pids, "lobby")
    if hasta == "lobby":
        return 0
    if os.environ.get("EDA_MULTI_PAUSA"):                     # para enganchar algo antes de la sala
        print("  (pausa de %s s)" % os.environ["EDA_MULTI_PAUSA"], flush=True)
        time.sleep(float(os.environ["EDA_MULTI_PAUSA"]))
    anfitrion, invitados = pids[0], pids[1:]
    # ★ el anfitrión crea la sala, pantalla por pantalla: lobby → Create Stage → SELECTOR → doble
    #   clic en el marcador → CREATE STAGE → título + Enter → SALA. Cada paso espera su pantalla (y
    #   se reintenta si no llega), en vez de un tiempo fijo
    for intento in range(4):
        if P.cual(anfitrion) == "dialogo":
            clic(anfitrion, *P.CANCEL_DIALOGO)
            P.esperar(anfitrion, "lobby", 5)
        if P.cual(anfitrion) == "lobby":
            clic(anfitrion, 495, 356)                         # Create Stage
        if P.esperar(anfitrion, ("selector", "crear"), 10) == "selector":
            h = activar(anfitrion)
            for x in (60, 45, 37):                            # pasar por encima del marcador
                C.u32.PostMessageW(h, 0x200, 0, (305 << 16) | x)
                time.sleep(0.15)
            clic(anfitrion, 37, 305, doble=True)
        if P.esperar(anfitrion, "crear", 6) == "crear":
            clic(anfitrion, 310, 342)                         # el campo Room Title (dos veces: el
            time.sleep(0.8)                                   #   primero no toma el foco)
            clic(anfitrion, 310, 342)
            time.sleep(0.8)
            C.escribir(C.ventana(anfitrion), "Sala multi")    # + Enter = crear la sala
        if P.esperar(anfitrion, "sala", 10) == "sala":
            break
        print("  (la sala no se creó: el anfitrión está en «%s», otra vez)" % P.cual(anfitrion), flush=True)
    # los invitados: la primera fila de la lista + Enter, hasta que estén en la SALA
    for pid in invitados:
        for intento in range(4):
            if P.cual(pid) == "dialogo":
                clic(pid, *P.CANCEL_DIALOGO)
                P.esperar(pid, "lobby", 5)
            clic(pid, 300, 138)
            time.sleep(1)
            clic(pid, 676, 356)
            if P.esperar(pid, "sala", 8) == "sala":
                break
            print("  (pid %d no entró a la sala: está en «%s», otra vez)" % (pid, P.cual(pid)), flush=True)
    fotos(pids, "sala")
    if hasta == "sala":
        return 0
    for pid in invitados:
        clic(pid, 672, 455)                                   # F9 Ready
        time.sleep(2)
    fotos(pids, "listo")
    if hasta == "listo":
        return 0
    clic(anfitrion, 672, 455)                                 # F9 Start Game
    for pid in pids:
        print("  pid %d → %s" % (pid, P.esperar(pid, "partida", 45)), flush=True)
    time.sleep(3)
    fotos(pids, "partida")
    return 0


if __name__ == "__main__":
    sys.exit(main())
