r"""jugar.py -- EDA (Espada del Alma, Softnyx 2009) contra nuestro server, en tu PC. Sólo Windows.

    py jugar.py --preparar "C:\ruta\al\cliente"     # UNA vez: copia el juego a _trabajo\juego
    py jugar.py                                      # el server + el juego (EDA.exe original)
    py jugar.py --limpio                             # lo mismo con exe\EDA_limpio.exe (si el
                                                     #   original da «Game guard error»)

Qué hace (ver EMPEZAR.md):
  · `--preparar` copia tu cliente de 2009 a `_trabajo\juego\` (el original no se toca), verifica
    que el EDA.exe sea el de 2009 y pone el juego en ventana.
  · después levanta el server (`herramientas\espiar_broker.py sin_admin`, en 127.0.0.1:25900) y
    abre el EDA.exe ORIGINAL con `herramientas\eda_original.py`, que en memoria pasa GameGuard,
    lo conecta al server y guarda los datos que el server necesita.
  · al cerrar el juego, apaga el server.

Nada pide administrador. Las cuentas quedan en `_trabajo\servidor\cuentas\`.
"""
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.abspath(__file__))
HERR = os.path.join(RAIZ, "herramientas")
JUEGO = os.path.join(RAIZ, "_trabajo", "juego")
REGLAS = os.path.join(RAIZ, "_trabajo", "broker", "reglas.json")
PARAR = os.path.join(RAIZ, "_trabajo", "broker", "parar")
MD5_2009 = "f0b12e6cddf3efdd0676b6491efe46be"               # EDA.exe compilado el 2009-08-14
sys.path.insert(0, HERR)


def md5(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def preparar(origen):
    exe = os.path.join(origen, "EDA.exe")
    if not os.path.exists(exe):
        raise SystemExit("⛔ en «%s» no hay EDA.exe. Tiene que ser la carpeta del juego." % origen)
    m = md5(exe)
    if m != MD5_2009:
        print("⚠ ese EDA.exe no es el de 2009 que conocemos (md5 %s, esperado %s): los parches de"
              " memoria pueden no calzar." % (m, MD5_2009))
    if os.path.abspath(origen) == os.path.abspath(JUEGO):
        raise SystemExit("⛔ el origen ya es _trabajo\\juego")
    print("copiando %s → %s …" % (origen, JUEGO))
    shutil.copytree(origen, JUEGO, dirs_exist_ok=True)
    limpio = os.path.join(RAIZ, "exe", "EDA_limpio.exe")
    if os.path.exists(limpio):
        shutil.copy2(limpio, os.path.join(JUEGO, "EDA_limpio.exe"))
        print("  + EDA_limpio.exe (para «py jugar.py --limpio»)")
    cfg = os.path.join(JUEGO, "autoexec.cfg")
    if os.path.exists(cfg):
        t = open(cfg, encoding="latin-1").read()
        if '"windowed"' in t:
            import re
            t = re.sub(r'"windowed"\s+"\d"', '"windowed" "1"', t)
        else:
            t = '"windowed" "1"\n' + t
        open(cfg, "w", encoding="latin-1").write(t)
        print("  modo ventana: «\"windowed\" \"1\"» en autoexec.cfg")
    print("✅ listo. Ahora: py jugar.py")


def server_andando():
    try:
        socket.create_connection(("127.0.0.1", 25900), timeout=0.5).close()
        return True
    except OSError:
        return False


def main():
    a = sys.argv[1:]
    if a[:1] == ["--preparar"]:
        if len(a) < 2:
            raise SystemExit('uso: py jugar.py --preparar "C:\\ruta\\al\\cliente"')
        return preparar(a[1])
    nombre = "EDA_limpio.exe" if "--limpio" in a else "EDA.exe"
    if not os.path.exists(os.path.join(JUEGO, "EDA.exe")):
        raise SystemExit('⛔ falta el juego. Primero: py jugar.py --preparar "C:\\ruta\\al\\cliente"')
    if not os.path.exists(os.path.join(JUEGO, nombre)):
        lim = os.path.join(RAIZ, "exe", "EDA_limpio.exe")
        if nombre == "EDA_limpio.exe" and os.path.exists(lim):
            shutil.copy2(lim, os.path.join(JUEGO, nombre))
        else:
            raise SystemExit("⛔ no está %s" % os.path.join(JUEGO, nombre))
    if not os.path.exists(REGLAS):                     # las respuestas del Broker (anuncio, lista)
        subprocess.run([sys.executable, os.path.join(HERR, "reglas_broker.py")], check=True)
    propio = None
    if server_andando():
        print("· el server ya estaba andando (127.0.0.1:25900)")
    else:
        log = open(os.path.join(RAIZ, "_trabajo", "server.txt"), "a", encoding="utf-8")
        propio = subprocess.Popen([sys.executable, os.path.join(HERR, "espiar_broker.py"), "sin_admin"],
                                  stdout=log, stderr=log, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        for _ in range(40):
            if server_andando():
                break
            time.sleep(0.25)
        print("· server andando (127.0.0.1:25900) — su registro: _trabajo\\broker\\espia.log")
    import eda_original
    try:
        eda_original.lanzar(esperar=True, nombre=nombre)
        print("· el juego se cerró")
    except KeyboardInterrupt:
        pass
    finally:
        if propio:
            open(PARAR, "w").close()
            try:
                propio.wait(timeout=5)
            except subprocess.TimeoutExpired:
                propio.kill()
            print("· server apagado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
