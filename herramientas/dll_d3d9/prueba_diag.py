r"""prueba_diag.py -- ★ (21-nov) el diagnóstico automático de la dll contra el server que lo recibe.

    python herramientas/dll_d3d9/prueba_diag.py        (desde la raíz del repo; necesita gcc y lo del server)

1. compila y corre prueba_diag.c (SHA-256, HMAC, la cola con varios hilos, el lote, la dirección);
2. la dll y servidor/diag.py derivan la MISMA clave y la MISMA firma (200 casos al azar: tickets, cuentas, cuerpos);
3. de punta a punta: los eventos que arma la dll, firmados por la dll, los acepta servidor/diag.recibir y guarda
   TODAS sus claves (si el server tirara alguna por «privada», el diagnóstico perdería datos sin avisar); el mismo lote
   otra vez → 409; con otro ticket → 401;
4. privacidad, mirando el código de eda_diag.c: no llama a nada que lea la MAC, la IP, el nombre de la PC o del usuario
   de Windows, y el ticket no se copia a ningún lado (sólo se deriva K).
"""
import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, RAIZ)


def compilar():
    exe = os.path.join(tempfile.gettempdir(), "prueba_diag")
    r = subprocess.run(["gcc", "-std=gnu11", "-O2", "-Wall", "-pthread", "-o", exe, os.path.join(AQUI, "prueba_diag.c")],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("⛔ prueba_diag.c no compila:\n" + r.stderr)
    return exe


def firmar_c(exe, ticket, cuenta, hora, sesion, lote, cuerpo):
    r = subprocess.run([exe, "firma", ticket, cuenta, str(hora), sesion, str(lote)], input=cuerpo, capture_output=True,
                       check=True)
    return r.stdout.decode().split()


def main():
    fallas = []
    exe = compilar()
    r = subprocess.run([exe], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode:
        fallas.append("prueba_diag.c")

    os.environ["EDA_ESTADO"] = tempfile.mkdtemp()
    from servidor import config, diag
    config.ESTADO = os.environ["EDA_ESTADO"]

    # 2. la misma clave y la misma firma
    azar = random.Random(21)
    iguales = 0
    for i in range(200):
        ticket = "".join(azar.choice(string.ascii_letters + string.digits + "-_") for _ in range(azar.randint(1, 20)))
        cuenta = "".join(azar.choice(string.digits) for _ in range(azar.randint(1, 12)))
        sesion = "%032x" % azar.getrandbits(128)
        hora, lote = azar.randint(1, 2 ** 45), azar.randint(1, 10 ** 6)
        cuerpo = bytes(azar.getrandbits(8) for _ in range(azar.choice((0, 1, 55, 56, 63, 64, 65, 1000, 60000))))
        k, f = firmar_c(exe, ticket, cuenta, hora, sesion, lote, cuerpo)
        if k == diag.clave(ticket).hex() and f == diag.firma(ticket, hora, sesion, lote, cuerpo, cuenta):
            iguales += 1
        else:
            fallas.append("firma distinta: ticket %r cuenta %r cuerpo %d B" % (ticket, cuenta, len(cuerpo)))
            break
    print("%s la dll y el server firman igual (%d de 200 casos al azar)" % ("✅" if iguales == 200 else "⛔", iguales))

    # 3. de punta a punta
    lineas = subprocess.run([exe, "eventos"], capture_output=True, text=True, check=True).stdout.splitlines()
    ahora = int(time.time() * 1000)
    eventos = []
    for i, ln in enumerate(lineas):
        ev = json.loads(ln)
        ev["t"] = ahora - 1000 + i
        eventos.append(ev)
    cuerpo = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in eventos).encode()
    ticket, cuenta, sesion = "TkPrueba123", "10006352", "%032x" % random.getrandbits(128)
    _, f = firmar_c(exe, ticket, cuenta, ahora, sesion, 1, cuerpo)
    cab = {"X-EDA-Cuenta": cuenta, "X-EDA-Sesion": sesion, "X-EDA-Lote": "1", "X-EDA-Hora": str(ahora), "X-EDA-Firma": f}
    http, resp = diag.recibir(cab, cuerpo, ahora, buscar_tickets=lambda c: [ticket] if c == cuenta else [])
    ok = http == 200 and resp.get("guardados") == len(eventos)
    print("%s el server acepta el lote de la dll: %s %s" % ("✅" if ok else "⛔", http, resp))
    if not ok:
        fallas.append("lote rechazado")
    perdidas = [(e["e"], k) for e in eventos for k in e if k not in (diag.limpiar_evento(e) or {})]
    print("%s el server guarda todas las claves de los eventos de la dll%s" % ("✅" if not perdidas else "⛔",
                                                                             "" if not perdidas else ": tira %s" % perdidas))
    if perdidas:
        fallas.append("claves tiradas")
    http2, _ = diag.recibir(cab, cuerpo, ahora, buscar_tickets=lambda c: [ticket])
    print("%s el mismo lote otra vez → %s (repetido)" % ("✅" if http2 == 409 else "⛔", http2))
    if http2 != 409:
        fallas.append("repetido aceptado")
    _, f3 = firmar_c(exe, "OtroTicket", cuenta, ahora, sesion, 2, cuerpo)
    cab3 = dict(cab, **{"X-EDA-Lote": "2", "X-EDA-Firma": f3})
    http3, _ = diag.recibir(cab3, cuerpo, ahora, buscar_tickets=lambda c: [ticket])
    print("%s firmado con otro ticket → %s" % ("✅" if http3 == 401 else "⛔", http3))
    if http3 != 401:
        fallas.append("otro ticket aceptado")
    shutil.rmtree(os.environ["EDA_ESTADO"], ignore_errors=True)

    # 4. privacidad (en el código)
    fuente = open(os.path.join(AQUI, "eda_diag.c"), encoding="utf-8").read()
    codigo = re.sub(r"/\*.*?\*/", "", fuente, flags=re.S)
    prohibidas = ["GetAdaptersInfo", "mac_texto", "gethostname", "gethostbyname", "GetComputerName", "GetUserName",
                  "getsockname", "g_server", "inet_ntoa", "GetVolumeInformation", "GetCommandLine", "g_linea"]
    usadas = [p for p in prohibidas if p in codigo]
    copia_ticket = re.findall(r"(?:memcpy|lstrcpy\w*|strcpy|strncpy)\s*\([^;]*ticket", codigo)
    ok = not usadas and not copia_ticket
    print("%s privacidad: eda_diag.c no lee MAC / IP / nombres%s" % (
        "✅" if ok else "⛔", "" if ok else ": usa %s %s" % (usadas, copia_ticket)))
    if not ok:
        fallas.append("privacidad")

    print("%s prueba_diag: %s" % ("⛔" if fallas else "✅", ", ".join(fallas) if fallas else "todo bien"))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
