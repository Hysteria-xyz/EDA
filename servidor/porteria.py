r"""servidor/porteria.py -- el LOGIN: el PASE del portero de R2Beat se canjea por un TICKET corto.

Cómo entra un jugador (MEDICIONES §45; el lado de R2Beat lo arma su repo):
  1. El launcher entra al PORTERO de R2Beat (Chile) y le pide un pase para «eda». Sale sólo si la
     cuenta está APROBADA para EDA y no está suspendida. El pase es un JWT firmado con Ed25519:
        header  {"alg": "EdDSA", "typ": "JWT", "kid": …}
        payload {"iss": "r2beat-portero", "aud": "eda", "sub": "<uid>", "iat", "exp" (+300 s), "jti"}
  2. El launcher manda el pase ACÁ (`POST /eda/pase`, lo atiende `servidor/red.py`) y recibe
     {"usuario": uid, "ticket": 20 caracteres, "vence"}. Nuestro server no le pregunta nada a Chile:
     sólo comprueba la firma con la clave PÚBLICA del portero (EDA_PORTERO_CLAVES, un JWKS).
  3. El launcher abre `"EDA_limpio.exe" <usuario> <ticket> [host:puerto]`; nuestra d3d9.dll lo vuelve
     el bloque del launcher que el juego entiende, y el juego los manda en el 0x100F (+0x04 y +0x2E del
     cuerpo, UTF-16, hasta 20 caracteres cada uno). `entrada.py` deja pasar sólo si el ticket es de ese
     usuario y no venció. La cuenta del jugador pasa a ser `r2b_<uid>`.

Lo que se guarda (`config.PORTERIA`, SQLite): los tickets (uno por cuenta, TICKET_HORAS) y el `jti`
de cada pase usado hasta que vence (un pase no se canjea dos veces).

★ El claim «nombre» (opcional, el portero lo manda desde el 12-nov): el APODO del personaje del casillero 1
de R2Beat, nunca el login. Se guarda con el ticket y, al entrar, el personaje que todavía se llama
`r2b_<uid>` pasa a llamarse así (`personajes.bautizar`). Vale lo mismo que al crear un personaje
(`NOMBRE_OK`, recortado a 12); si no entra o ya lo usa otro, se ignora y queda el nombre de antes.

    py servidor\juego.py control        # las pruebas (la firma, cada rechazo y su revés)
"""
import base64
import contextlib
import json
import os
import re
import secrets
import sqlite3
import string
import time
import urllib.request

from servidor import config

ALFABETO = string.ascii_letters + string.digits     # ⚠ sin espacios: el bloque separa A y B con uno
LARGO_TICKET = 20                                    # el campo del juego: 21 UTF-16 con el 0 final
TOLERANCIA = 30                                      # segundos de reloj desparejo entre Chile y acá
NOMBRE_OK = re.compile(r"[A-Za-z0-9_]{2,12}")        # = personajes.NOMBRE_OK (crear personaje, 0x1013)


def nombre_del_pase(datos):
    """El claim «nombre» del pase, recortado a 12 y validado como el de crear personaje; o None."""
    n = datos.get("nombre")
    if not isinstance(n, str):
        return None
    n = n.strip()[:12]
    return n if NOMBRE_OK.fullmatch(n) else None


class Rechazo(Exception):
    """Un pase que no sirve. `codigo` va en la respuesta HTTP (`http`)."""

    def __init__(self, codigo, http=401):
        super().__init__(codigo)
        self.codigo, self.http = codigo, http


def _b64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ── la clave pública del portero (JWKS) ─────────────────────────────────────────────────────────
_CLAVES = {"de": None, "claves": {}, "cuando": 0.0}


def claves(refrescar=False):
    """kid → la clave pública Ed25519 (32 bytes). De un archivo o de una URL https (se recuerda; con
    un kid desconocido se vuelve a pedir, como mucho una vez por minuto)."""
    fuente = config.PORTERO_CLAVES
    if not fuente:
        return {}
    if _CLAVES["de"] == fuente and not refrescar:
        return _CLAVES["claves"]
    if _CLAVES["de"] == fuente and time.time() - _CLAVES["cuando"] < 60:
        return _CLAVES["claves"]                     # no martillar al portero con kids inventados
    if fuente.startswith("https://"):
        with urllib.request.urlopen(fuente, timeout=5) as r:
            jwks = json.loads(r.read(65536))
    elif re.match(r"^[a-z]+://", fuente):
        raise Rechazo("clave", 503)                  # ⛔ una clave por http sin s se puede cambiar en el camino
    else:
        with open(fuente, encoding="utf-8") as f:
            jwks = json.load(f)
    nuevas = {}
    for k in jwks.get("keys", []) if isinstance(jwks, dict) else []:
        if isinstance(k, dict) and k.get("kty") == "OKP" and k.get("crv") == "Ed25519" and k.get("kid"):
            try:
                x = _b64(k.get("x", ""))
            except ValueError:
                continue
            if len(x) == 32:
                nuevas[k["kid"]] = x
    _CLAVES.update(de=fuente, claves=nuevas, cuando=time.time())
    return nuevas


# ── la base (tickets y pases usados) ────────────────────────────────────────────────────────────
@contextlib.contextmanager
def _base():
    os.makedirs(os.path.dirname(config.PORTERIA), exist_ok=True)
    db = sqlite3.connect(config.PORTERIA, timeout=5)
    try:
        db.execute("CREATE TABLE IF NOT EXISTS tickets (ticket TEXT PRIMARY KEY, uid TEXT, vence REAL)")
        db.execute("CREATE TABLE IF NOT EXISTS jtis (jti TEXT PRIMARY KEY, vence REAL)")
        if "nombre" not in [f[1] for f in db.execute("PRAGMA table_info(tickets)")]:
            db.execute("ALTER TABLE tickets ADD COLUMN nombre TEXT")   # (la base de antes del 13-nov)
        yield db
        db.commit()
    finally:
        db.close()


# ── el pase ─────────────────────────────────────────────────────────────────────────────────────
def verificar_pase(pase, ahora=None):
    """(el uid de R2Beat del pase (texto con dígitos), su nombre o None), o `Rechazo`. Gasta el pase."""
    from Crypto.Signature import eddsa
    ahora = time.time() if ahora is None else ahora
    if not isinstance(pase, str) or len(pase) > 4096 or pase.count(".") != 2:
        raise Rechazo("formato", 400)
    h, d, f = pase.split(".")
    try:
        cab, datos, firma = json.loads(_b64(h)), json.loads(_b64(d)), _b64(f)
        firmado = (h + "." + d).encode("ascii")
    except (ValueError, UnicodeError):
        raise Rechazo("formato", 400)
    if not isinstance(cab, dict) or not isinstance(datos, dict):
        raise Rechazo("formato", 400)
    if cab.get("alg") != "EdDSA":                    # ⛔ ni «none» ni otro algoritmo
        raise Rechazo("algoritmo")
    kid = cab.get("kid")
    try:
        cl = claves()
        if kid not in cl:
            cl = claves(refrescar=True)
    except (OSError, ValueError):                    # el JWKS no se pudo leer (red, archivo, JSON)
        raise Rechazo("clave", 503)
    if kid not in cl:
        raise Rechazo("clave")
    try:
        eddsa.new(eddsa.import_public_key(cl[kid]), "rfc8032").verify(firmado, firma)
    except (ValueError, TypeError):
        raise Rechazo("firma")
    if datos.get("iss") != config.PORTERO_EMISOR:
        raise Rechazo("emisor")
    aud = datos.get("aud")
    if aud != config.PORTERO_AUDIENCIA and not (isinstance(aud, list) and config.PORTERO_AUDIENCIA in aud):
        raise Rechazo("audiencia")
    exp, iat = datos.get("exp"), datos.get("iat")
    if not isinstance(exp, (int, float)) or exp + TOLERANCIA < ahora:
        raise Rechazo("vencido")
    if isinstance(iat, (int, float)) and iat - TOLERANCIA > ahora:
        raise Rechazo("futuro")
    sub, jti = datos.get("sub"), datos.get("jti")
    if not (isinstance(sub, str) and re.fullmatch(r"[0-9]{1,20}", sub)):
        raise Rechazo("cuenta")
    if not (isinstance(jti, str) and 0 < len(jti) <= 128):
        raise Rechazo("jti")
    with _base() as db:
        db.execute("DELETE FROM jtis WHERE vence < ?", (ahora,))
        try:
            db.execute("INSERT INTO jtis VALUES (?, ?)", (jti, exp + TOLERANCIA))
        except sqlite3.IntegrityError:
            raise Rechazo("repetido", 409)
    return sub, nombre_del_pase(datos)


# ── el ticket ───────────────────────────────────────────────────────────────────────────────────
def dar_ticket(uid, ahora=None, nombre=None):
    """Un ticket nuevo para esa cuenta (el anterior deja de valer). → (ticket, vence)"""
    ahora = time.time() if ahora is None else ahora
    t = "".join(secrets.choice(ALFABETO) for _ in range(LARGO_TICKET))
    vence = ahora + config.TICKET_HORAS * 3600
    with _base() as db:
        db.execute("DELETE FROM tickets WHERE vence < ? OR uid = ?", (ahora, uid))
        db.execute("INSERT INTO tickets (ticket, uid, vence, nombre) VALUES (?, ?, ?, ?)", (t, uid, vence, nombre))
    return t, vence


def nombre_de(uid, ticket):
    """El nombre que trajo el pase de ese ticket (None si no trajo, o si el ticket no es de esa cuenta)."""
    with _base() as db:
        r = db.execute("SELECT uid, nombre FROM tickets WHERE ticket = ?", (ticket,)).fetchone()
    return r[1] if r and secrets.compare_digest(r[0], uid) else None


def ticket_valido(uid, ticket, ahora=None):
    """¿Ese ticket es de esa cuenta y no venció? (Vale varias veces: el juego se reconecta.)"""
    ahora = time.time() if ahora is None else ahora
    if not (isinstance(uid, str) and isinstance(ticket, str) and ticket):
        return False
    with _base() as db:
        r = db.execute("SELECT uid, vence FROM tickets WHERE ticket = ?", (ticket,)).fetchone()
    return bool(r) and secrets.compare_digest(r[0], uid) and r[1] >= ahora


def canjear(pase, ahora=None):
    """POST /eda/pase: el pase → {"usuario", "ticket", "vence"} (o `Rechazo`)."""
    uid, nombre = verificar_pase(pase, ahora)
    ticket, vence = dar_ticket(uid, ahora, nombre)
    return {"usuario": uid, "ticket": ticket, "vence": int(vence)}
