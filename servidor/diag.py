r"""servidor/diag.py -- ★ (21-nov) LOS DIAGNÓSTICOS DE LOS CLIENTES BETA, recibidos en el server de PRUEBA.

POST /eda/diag (el HTTP del server, EDA_PUERTO + 1; afuera, por HTTPS con Caddy). Sólo con EDA_DIAG=1 (prod: 404, como
cualquier ruta que no existe). Lo manda la d3d9.dll del jugador, sola, en segundo plano: el jugador no hace nada.

Autenticación SIN mandar el ticket: el cliente ya tiene el ticket de su sesión (el launcher se lo pasa al exe) y el server
lo tiene en su base del login (`config.PORTERIA`; acá sólo se LEE, el login no cambia). El ticket NO es la clave: de él se
deriva una clave SÓLO para esto, K = HMAC-SHA256(ticket, "eda-diag-v1") (así ninguna firma del diagnóstico sirve para
otra cosa, y el ticket nunca viaja ni se guarda). Cada lote lleva:
    X-EDA-Cuenta  el usuario (el mismo número que va en el login)
    X-EDA-Sesion  32 hex al azar que la dll elige al arrancar (NO es de la PC: cambia cada vez)
    X-EDA-Lote    1, 2, 3…  (siempre mayor: un lote repetido o viejo se rechaza, también después de reiniciar)
    X-EDA-Hora    ms UTC de cuando lo mandó (±10 min)
    X-EDA-Firma   hex de HMAC-SHA256(K, «eda-diag-v1\ncuenta\nhora\nsesion\nlote\nsha256(cuerpo)»)
Afuera va SÓLO por HTTPS (la dll no manda por http salvo a 127.0.0.1, para probar en la misma PC).
El cuerpo: líneas JSON (≤ 64 KB, ≤ 500), cada una un evento chico: {"t": ms UTC, "m": ms desde el arranque, "e": "…", …}.
Los eventos que manda la dll (eda_diag.c): inicio, fin, server_conecta, server_corta, tcp_silencio, escena, carga_fin,
atrapado_carga, congelado, descongelado, fps, foco, caida (una excepción: código, módulo y sitio, como la caja negra).
Se guarda SÓLO lo que tiene forma de evento: claves cortas, valores simples (texto ≤ 200, números, sí/no); se tira
cualquier clave con forma de dato privado (ticket, clave, mac, ip, nombre de la PC…). Nada de texto del chat.

Dónde: <ESTADO>/diag/<AAAA-MM-DD>/<cuenta>-<sesion>.jsonl, cada línea con «r» (cuándo llegó, ms del server) y «dr»
(la diferencia de reloj de esa PC). Se borra lo de más de EDA_DIAG_DIAS (14) y, si pasa de EDA_DIAG_MAX_MB (500), lo más
viejo primero. No hay forma de LEERLOS por la red: los baja la llave eda-diag (diagnostico.sh) y los junta por partida
herramientas/diag_partida.py (con el server.log: qué conexión era cada cuenta y en qué partida estaba).
"""
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import threading
import time

from servidor import config

ACTIVO = os.environ.get("EDA_DIAG") == "1"
DIAS = int(os.environ.get("EDA_DIAG_DIAS") or 14)
MAX_MB = int(os.environ.get("EDA_DIAG_MAX_MB") or 500)
MAX_CUERPO = 64 * 1024
MAX_LINEAS = 500
MAX_LINEA = 1024
VENTANA_MS = 10 * 60 * 1000
POR_MINUTO = 12
R_SESION = re.compile(r"^[0-9a-f]{32}$")
R_CUENTA = re.compile(r"^[0-9A-Za-z_-]{1,40}$")
R_CLAVE = re.compile(r"^[a-z_][a-z0-9_]{0,23}$")
PRIVADAS = {"ticket", "clave", "pass", "password", "pwd", "token", "mac", "ip", "host", "pc", "equipo", "usuario",
            "ruta", "path", "correo", "mail", "chat", "texto", "mensaje", "serial", "nombre"}
_CANDADO = threading.Lock()
_ULTIMO_LOTE = {}                                   # (cuenta, sesión) → último lote aceptado
_RITMO = {}                                         # cuenta → [ms de los lotes del último minuto]
_PODA = [0.0]


class Rechazo(Exception):
    def __init__(self, http, codigo):
        super().__init__(codigo)
        self.http, self.codigo = http, codigo


def carpeta():
    return os.path.join(config.ESTADO, "diag")


def tickets_de(cuenta, ahora=None):
    """Los tickets VIGENTES de esa cuenta (sólo lectura de la base del login)."""
    if not os.path.exists(config.PORTERIA):
        return []
    db = sqlite3.connect("file:%s?mode=ro" % config.PORTERIA, uri=True, timeout=5)
    try:
        return [r[0] for r in db.execute("SELECT ticket FROM tickets WHERE uid = ? AND vence > ?",
                                         (cuenta, ahora if ahora is not None else time.time()))]
    finally:
        db.close()


DOMINIO = "eda-diag-v1"


def clave(ticket):
    """La clave del diagnóstico, derivada del ticket (nunca el ticket mismo)."""
    return hmac.new(ticket.encode("utf-8"), DOMINIO.encode("ascii"), hashlib.sha256).digest()


def firma(ticket, hora, sesion, lote, cuerpo, cuenta=""):
    msg = "%s\n%s\n%s\n%s\n%s\n%s" % (DOMINIO, cuenta, hora, sesion, lote, hashlib.sha256(cuerpo).hexdigest())
    return hmac.new(clave(ticket), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def _ultimo_lote(cuenta, sesion):
    """el último lote aceptado de esa sesión: en memoria y en disco (un reinicio del server no reabre los viejos)"""
    k = (cuenta, sesion)
    if k not in _ULTIMO_LOTE:
        try:
            _ULTIMO_LOTE[k] = int(open(os.path.join(carpeta(), "lotes", "%s-%s" % k)).read().strip() or 0)
        except (OSError, ValueError):
            _ULTIMO_LOTE[k] = 0
    return _ULTIMO_LOTE[k]


def _anotar_lote(cuenta, sesion, lote):
    _ULTIMO_LOTE[(cuenta, sesion)] = lote
    d = os.path.join(carpeta(), "lotes")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s-%s" % (cuenta, sesion)), "w") as f:
        f.write(str(lote))


def limpiar_evento(ev):
    """Un evento con forma de evento, o None. Sólo claves cortas y valores simples; nada con forma de dato privado."""
    if not isinstance(ev, dict) or not isinstance(ev.get("e"), str) or not isinstance(ev.get("t"), (int, float)):
        return None
    r = {}
    for k, v in list(ev.items())[:24]:
        if not isinstance(k, str) or not R_CLAVE.match(k) or set(k.split("_")) & PRIVADAS:
            continue
        if isinstance(v, bool) or isinstance(v, (int, float)):
            r[k] = v
        elif isinstance(v, str) and len(v) <= 200 and not re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}", v):
            r[k] = v
    return r if "e" in r and "t" in r else None


def recibir(cab, cuerpo, ahora_ms=None, buscar_tickets=tickets_de):
    """cab: las cabeceras (dict, sin importar mayúsculas) · cuerpo: bytes → (http, respuesta)"""
    ahora_ms = int(time.time() * 1000) if ahora_ms is None else ahora_ms
    try:
        return 200, _recibir({k.lower(): v for k, v in cab.items()}, cuerpo, ahora_ms, buscar_tickets)
    except Rechazo as e:
        return e.http, {"error": e.codigo}


def _recibir(cab, cuerpo, ahora_ms, buscar_tickets):
    cuenta, sesion = cab.get("x-eda-cuenta", ""), cab.get("x-eda-sesion", "")
    if not R_CUENTA.match(cuenta) or not R_SESION.match(sesion):
        raise Rechazo(400, "cabeceras")
    try:
        lote, hora = int(cab.get("x-eda-lote", "")), int(cab.get("x-eda-hora", ""))
    except ValueError:
        raise Rechazo(400, "cabeceras")
    if len(cuerpo) > MAX_CUERPO:
        raise Rechazo(413, "grande")
    if abs(ahora_ms - hora) > VENTANA_MS:
        raise Rechazo(401, "hora")
    dada = cab.get("x-eda-firma", "")
    if not re.match(r"^[0-9a-f]{64}$", dada) or not any(
            hmac.compare_digest(firma(t, hora, sesion, lote, cuerpo, cuenta), dada) for t in buscar_tickets(cuenta)):
        raise Rechazo(401, "firma")
    with _CANDADO:
        if lote <= _ultimo_lote(cuenta, sesion):
            raise Rechazo(409, "lote")
        ritmo = [x for x in _RITMO.get(cuenta, []) if ahora_ms - x < 60000]
        if len(ritmo) >= POR_MINUTO:
            raise Rechazo(429, "ritmo")
        _RITMO[cuenta] = ritmo + [ahora_ms]
        lineas = cuerpo.decode("utf-8", "replace").splitlines()
        if len(lineas) > MAX_LINEAS:
            raise Rechazo(413, "lineas")
        buenos = []
        for ln in lineas:
            if not ln.strip() or len(ln) > MAX_LINEA:
                continue
            try:
                ev = limpiar_evento(json.loads(ln))
            except ValueError:
                ev = None
            if ev:
                ev["r"], ev["dr"] = ahora_ms, ahora_ms - hora
                buenos.append(ev)
        _anotar_lote(cuenta, sesion, lote)
        dia = time.strftime("%Y-%m-%d", time.gmtime(ahora_ms / 1000))
        d = os.path.join(carpeta(), dia)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "%s-%s.jsonl" % (cuenta, sesion)), "a", encoding="utf-8") as f:
            for ev in buenos:
                f.write(json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n")
        if time.time() - _PODA[0] > 600:
            _PODA[0] = time.time()
            podar(ahora_ms)
    return {"ok": True, "lote": lote, "guardados": len(buenos)}


def podar(ahora_ms=None, dias=None, max_mb=None):
    """Borra los días de más de `dias`, y si todo pasa de `max_mb`, los días más viejos primero (nunca el de hoy)."""
    ahora_ms = int(time.time() * 1000) if ahora_ms is None else ahora_ms
    dias = DIAS if dias is None else dias
    max_mb = MAX_MB if max_mb is None else max_mb
    base = carpeta()
    if not os.path.isdir(base):
        return []
    hoy = time.strftime("%Y-%m-%d", time.gmtime(ahora_ms / 1000))
    limite = time.strftime("%Y-%m-%d", time.gmtime(ahora_ms / 1000 - dias * 86400))
    borrados = []
    lotes = os.path.join(base, "lotes")
    if os.path.isdir(lotes):                        # (las marcas de lote de sesiones de más de 1 día ya no hacen falta)
        for a in os.listdir(lotes):
            if os.path.getmtime(os.path.join(lotes, a)) < ahora_ms / 1000 - 86400:
                os.remove(os.path.join(lotes, a))
    fechas = sorted(x for x in os.listdir(base) if re.match(r"^\d{4}-\d{2}-\d{2}$", x))
    for x in fechas:
        if x < limite:
            shutil.rmtree(os.path.join(base, x), ignore_errors=True)
            borrados.append(x)
    fechas = [x for x in fechas if x not in borrados]

    def tam(x):
        return sum(os.path.getsize(os.path.join(base, x, a)) for a in os.listdir(os.path.join(base, x)))
    total = sum(tam(x) for x in fechas)
    for x in fechas:
        if total <= max_mb * 1024 * 1024 or x == hoy:
            break
        total -= tam(x)
        shutil.rmtree(os.path.join(base, x), ignore_errors=True)
        borrados.append(x)
    return borrados
