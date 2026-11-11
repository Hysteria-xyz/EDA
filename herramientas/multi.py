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


def piloto(pid, hasta, desde=None):
    env = dict(os.environ, EDA_PID=str(pid), PYTHONIOENCODING="utf-8")
    if desde:
        env["EDA_DESDE"] = desde
    subprocess.run([sys.executable, PILOTO, hasta], env=env, capture_output=True, timeout=240)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    hasta = sys.argv[2] if len(sys.argv) > 2 else "partida"
    subprocess.run(["taskkill", "/F", "/IM", "EDA_limpio.exe"], capture_output=True)
    # ⚠ abrir enseguida después de matar a los anteriores: los nuevos se cayeron al arrancar en
    #   mss32.dll (el sonido, 17:55: 🟡 el dispositivo todavía tomado). Unos segundos de margen.
    time.sleep(6)
    pids = []
    for i in range(n):
        # ⚠ entre comillas: si no, el juego pisa su MAC del 0x100F (MEDICIONES §39)
        p = subprocess.Popen('"%s"' % os.path.join(JUEGO, "EDA_limpio.exe"), cwd=JUEGO)
        pids.append(p.pid)
        time.sleep(3)
    open(os.path.join(RAIZ, "_trabajo", "multi_pids.txt"), "w").write(" ".join(map(str, pids)))
    print("★ pids %s" % pids, flush=True)
    log = os.path.join(RAIZ, "_trabajo", "broker", "espia.log")

    def entradas():
        return open(log, encoding="utf-8", errors="replace").read().count("comando 1017")
    for pid in pids:
        # ⚠ el piloto a veces se queda en la lista de servidores o en SELECT CHARACTER (tiempos
        #   fijos): se verifica en el espía que ESTE cliente entró al lobby (un 0x1017 más) y si
        #   no, se reintenta desde el principio de su camino
        for intento in range(3):
            antes = entradas()
            piloto(pid, "lobby")
            time.sleep(2)
            if entradas() > antes:
                break
            print("  (pid %d no llegó al lobby: otra vez)" % pid, flush=True)
    fotos(pids, "lobby")
    if hasta == "lobby":
        return 0
    if os.environ.get("EDA_MULTI_PAUSA"):                     # para enganchar algo antes de la sala
        print("  (pausa de %s s)" % os.environ["EDA_MULTI_PAUSA"], flush=True)
        time.sleep(float(os.environ["EDA_MULTI_PAUSA"]))
    anfitrion, invitados = pids[0], pids[1:]
    # el anfitrión crea la sala: Create Stage → doble clic en el marcador → título → Enter
    clic(anfitrion, 495, 356)
    time.sleep(6)
    # ⚠ el doble clic en el marcador a veces no abre CREATE STAGE (medido): se reintenta hasta que
    #   el espía vea el 0x101D (la sala creada)
    log = os.path.join(RAIZ, "_trabajo", "broker", "espia.log")
    antes = open(log, encoding="utf-8", errors="replace").read().count("comando 101d")
    for _ in range(6):
        h = activar(anfitrion)
        for x in (60, 45, 37):                                # pasar por encima del marcador
            C.u32.PostMessageW(h, 0x200, 0, (305 << 16) | x)
            time.sleep(0.15)
        clic(anfitrion, 37, 305, doble=True)
        time.sleep(2.5)
        clic(anfitrion, 310, 342)
        time.sleep(0.8)
        clic(anfitrion, 310, 342)
        time.sleep(1)
        C.escribir(C.ventana(anfitrion), "Sala multi")
        time.sleep(4)
        if open(log, encoding="utf-8", errors="replace").read().count("comando 101d") > antes:
            break
        print("  (la sala no se creó: otra vez)", flush=True)
    # los invitados: la primera fila de la lista + Enter
    for pid in invitados:
        clic(pid, 300, 138)
        time.sleep(1)
        clic(pid, 676, 356)
        time.sleep(4)
    fotos(pids, "sala")
    if hasta == "sala":
        return 0
    for pid in invitados:
        clic(pid, 672, 455)                                   # F9 Ready
        time.sleep(3)
    fotos(pids, "listo")
    if hasta == "listo":
        return 0
    clic(anfitrion, 672, 455)                                 # F9 Start Game
    time.sleep(25)
    fotos(pids, "partida")
    return 0


if __name__ == "__main__":
    sys.exit(main())
