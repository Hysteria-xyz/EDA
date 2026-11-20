r"""servidor/panel.py -- ★ LA PUERTA INTERNA del panel del Coordinador Eñeños («contrato del panel v1», 20-nov).

El contrato vive en el repo del Coordinador (`documentacion/CONTRATO_PANEL.md`). En corto: el Coordinador decide
QUIÉN puede qué (admin, moderador, cupos); este server sólo EJECUTA lo que sabe hacer hoy y ANOTA quién lo pidió.
Lo atiende el HTTP de `servidor/red.py` (el mismo del login, `EDA_PUERTO + 1`, y si se pide uno aparte sólo para
esto: `EDA_PANEL_ESCUCHAR`), bajo `/interno/panel/…`. Caddy publica sólo `/eda/*`: esto no sale a internet.

    GET  capacidades                          {"juego", "version": 1, "acciones", "monedas", "entorno"}
    GET  salud                                {"en_linea", "jugando", "detalle": [{"nombre", "valor"}]}
    GET  conectados                           {"filas": [{"id", "nick", "enenos_id", "donde", "desde", "ip"}]}
    GET  buscar?q=                            {"filas": [{"id", "nick", "enenos_id", "conectado", "resumen"}]} (tope 50)
    GET  ficha/<id>                           {"id", "nick", "enenos_id", "conectado", "campos", "monedas",
                                               "personajes", "movimientos"}
    POST aviso   {texto, a: todos|uno, id?}   {"ok", "llego_a"}            una línea en el chat (0x1005 tipo 3)
    POST echar   {id, motivo?}                {"ok"} · 404 si no está      corta su conexión (puede volver a entrar)
    POST moneda  {id, moneda, cantidad}       {"ok", "antes", "despues"}   nunca deja negativo

`id` = la CUENTA del juego (`en_<Eñeños ID>` con el pase de Cuenta Eñeños; `rui`… con el login abierto). Las monedas
(oro, cash, monedas para revivir) son de la cuenta, no de cada personaje (`cuentas.CUENTA_CLAVES`). `ficha/<id>.<lugar>`
muestra un personaje que no es el activo (el `id` de `personajes`).

SEGURIDAD
- Toda ruta pide `X-Ficha-Interna` == `R2_CUENTAS_FICHA_INTERNA` (`config.FICHA_INTERNA`, tiempo constante). Sin la
  variable, con otra ficha o sin ella: 404, como si no existiera. Con `X-Forwarded-For` (vino por un proxy: Caddy lo
  pone siempre) también 404: el Coordinador llama directo por la red de adentro. Es la segunda llave.
- Todo POST pide además `X-R2: 1` (si falta: 403) y `X-Coordinador-Quien`; cada cambio se anota con él en el
  registro del server y en `config.PANEL_AUDITORIA` (de ahí salen los `movimientos` de la ficha).
- Nunca sale un ticket, un pase ni una ficha: el server no guarda contraseñas (se entra con el pase).

⚠ LAS MONEDAS DE UN CONECTADO NO SE TOCAN (409). El server lee la cuenta del disco en cada mensaje y la vuelve a
guardar, sin candado entre conexiones: un cambio desde acá en medio de una compra se pisaría. Y aunque quedara, el
cliente no se entera hasta que vuelve a entrar (no hay mensaje suelto que le actualice el oro). Desconectado, el
cambio va con la escritura de siempre (`cuentas.escribir`: archivo temporal + reemplazo de una).

    py servidor\juego.py control         # las pruebas (pruebas_panel: cada regla con su revés)
"""
import hmac
import json
import os
import re
import threading
import time
import urllib.parse

from servidor import config
from servidor.cuentas import EXPS, INICIO, MAX_PERSONAJES, escribir, leer, nivel, nombre_visible, personajes_de, ruta_cuenta
from servidor.estado import ASIGNADAS, PARTIDAS, SALAS, VIVO
from servidor.messenger import aviso as linea_chat, donde_esta, nombres_de_cuentas
from servidor.objetos import stats_de
from servidor.personajes import vista

PREFIJO = "/interno/panel"
VERSION = 1
JUEGO = "eda"
# id del contrato · nombre para el panel · la clave en la cuenta · el tope (los mismos que los comandos GM /oro,
#   /cash y /monedas de salas.py: el 0x1012 lleva las monedas de revivir en un u16 y el cliente las muestra hasta 999)
MONEDAS = [
    {"id": "oro", "nombre": "Oro", "campo": "plata", "tope": 2_000_000_000},
    {"id": "cash", "nombre": "Cash", "campo": "cash", "tope": 2_000_000_000},
    {"id": "monedas_revivir", "nombre": "Monedas para revivir", "campo": "monedas", "tope": 999},
]
CLASES = {1: "Guerrero (Warrior)", 2: "Cazador (Hunter)"}
ENENOS_DESDE = 10_000_000          # Cuenta Eñeños numera a las personas desde acá; los uid viejos de R2Beat son menores
TOPE_BUSCAR = 50
TOPE_MOVIMIENTOS = 20
TOPE_AVISO = 200                   # letras (lo mismo que el aviso del panel del Messenger)
TOPE_MOTIVO = 200
TOPE_QUIEN = 80
TOPE_CUERPO = 16 * 1024            # bytes del JSON de un POST
REMITENTE = "[Aviso]"              # el nombre con que sale la línea del chat
NO_EXISTE = (404, {"error": "No existe."})

_candado = threading.Lock()        # un cambio de monedas a la vez: leer → sumar → escribir
_candado_auditoria = threading.Lock()


# ── la puerta ────────────────────────────────────────────────────────────────────────────────────
def es_suya(ruta):
    """¿La ruta (sin la consulta) es de esta puerta?"""
    ruta = ruta.split("?", 1)[0]
    return ruta == PREFIJO or ruta.startswith(PREFIJO + "/")


def ficha_ok(cab):
    """¿Trae la ficha interna? Sin ficha configurada, nunca (la puerta no existe)."""
    esperada = config.FICHA_INTERNA
    if not esperada:
        return False
    traida = cab.get("x-ficha-interna") or ""
    return hmac.compare_digest(traida.encode("utf-8"), esperada.encode("utf-8"))


def acciones_de(red):
    """Lo que esta puerta sabe hacer HOY. Avisar y echar necesitan las conexiones (`red`: el server por la red);
    sin ellas (Windows con `espiar_broker.py`, o una prueba) no se ofrecen."""
    return (["ver"] + (["aviso"] if getattr(red, "enviar", None) else [])
            + (["echar"] if getattr(red, "cortar", None) else []) + ["moneda"])


def atender(metodo, ruta, cabeceras, leer_cuerpo=lambda: b"", red=None):
    """Un pedido a `/interno/panel/…` → (código HTTP, dict). `leer_cuerpo()` devuelve los bytes del cuerpo (o
    ValueError si es demasiado grande); se llama sólo después de comprobar la ficha. `red` = lo que el panel puede
    hacer con las conexiones: `enviar(respuestas)` y `cortar(conexión, espera)` (ver servidor/red.py)."""
    cab = {str(k).lower(): v for k, v in (cabeceras.items() if cabeceras else [])}
    if not ficha_ok(cab) or cab.get("x-forwarded-for"):
        return NO_EXISTE
    camino, _, consulta = ruta.partition("?")
    if not es_suya(camino):
        return NO_EXISTE
    resto = camino[len(PREFIJO):].strip("/")
    if metodo == "GET":
        if resto == "capacidades":
            return 200, capacidades(red)
        if resto == "salud":
            return 200, salud()
        if resto == "conectados":
            return 200, conectados()
        if resto == "buscar":
            return 200, buscar((urllib.parse.parse_qs(consulta).get("q") or [""])[0])
        if resto.startswith("ficha/"):
            return ficha(resto[len("ficha/"):])
        return NO_EXISTE
    hacer = {"aviso": aviso, "echar": echar, "moneda": moneda}.get(resto) if metodo == "POST" else None
    if hacer is None or resto not in acciones_de(red):
        return NO_EXISTE
    if cab.get("x-r2") != "1":
        return 403, {"error": "Falta la cabecera X-R2: 1."}
    quien = re.sub(r"[\x00-\x1f\x7f]", "", str(cab.get("x-coordinador-quien") or "")).strip()[:TOPE_QUIEN]
    if not quien:
        return 400, {"error": "Falta X-Coordinador-Quien: sin eso no se puede anotar quién lo pidió."}
    try:
        crudo = leer_cuerpo()
    except ValueError:
        return 413, {"error": "El pedido es demasiado grande."}
    try:
        datos = json.loads(crudo.decode("utf-8")) if crudo else {}
    except (ValueError, UnicodeError):
        return 400, {"error": "El cuerpo no es un JSON válido."}
    if not isinstance(datos, dict):
        return 400, {"error": "El cuerpo tiene que ser un objeto JSON."}
    return hacer(datos, quien, red)


# ── las cuentas ──────────────────────────────────────────────────────────────────────────────────
def _conectadas():
    """cuenta → conexión, de los que ya entraron (sin las internas `_…`, p. ej. `_sin_login`)."""
    return {nombre: n for n, nombre in list(ASIGNADAS.items()) if nombre and not nombre.startswith("_")}


def _crudo(nombre):
    """La cuenta tal como está en su archivo, o None (no existe, o el .json no es una cuenta)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", nombre or "") or nombre.startswith("_"):
        return None
    try:
        with open(ruta_cuenta(nombre), encoding="utf-8") as f:
            crudo = json.load(f)
    except (OSError, ValueError):
        return None
    return crudo if isinstance(crudo, dict) and ("pjs" in crudo or "nombre" in crudo) else None


def _cuenta(nombre):
    """La cuenta (lo de la cuenta + `pjs` + `activo`): del archivo o, si es una conectada que todavía no guardó
    nada (una cuenta nueva del login abierto), como la ve el server ahora."""
    crudo = _crudo(nombre)
    n = _conectadas().get(nombre)
    if crudo is None and n is not None:
        c = leer(n)
        crudo = {k: c[k] for k in ("nombre", "plata", "cash", "monedas") if k in c}
        crudo.update(pjs=c.get("pjs") or [], activo=c.get("activo", 0))
    return crudo


def enenos_id(nombre):
    """El Eñeños ID de una cuenta, si se sabe: con el login por pase la cuenta es `<prefijo><número del pase>`, y
    ese número es el Eñeños ID cuando el pase es de Cuenta Eñeños (desde 10.000.000; los uid de R2Beat del portero
    viejo son menores y NO son una persona de Cuenta Eñeños). Si no: None."""
    p = config.PREFIJO_CUENTA
    resto = nombre[len(p):] if config.LOGIN == "pase" and nombre.startswith(p) else ""
    return int(resto) if re.fullmatch(r"[0-9]{1,20}", resto) and int(resto) >= ENENOS_DESDE else None


def _nick(nombre, crudo):
    pjs, activo = personajes_de(crudo)
    return (pjs[activo].get("nick") if pjs else None) or nombre


def _valor(crudo, campo):
    """Una moneda de la cuenta, con el mismo valor por omisión que `cuentas.leer`."""
    return int(crudo.get(campo, INICIO[campo]))


def _resumen(crudo, pj):
    if pj is None:
        return "Sin personajes"
    v = vista(crudo, pj)
    k = len(personajes_de(crudo)[0])
    return "Nivel %d · %s · %d %s" % (nivel(v["exp"]), CLASES.get(v.get("clase"), "clase %s" % v.get("clase")),
                                      k, "personaje" if k == 1 else "personajes")


def _cuando(t):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def _duracion(s):
    s = int(max(0, s))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return ("%d d %d h" % (d, h)) if d else ("%d h %d min" % (h, m)) if h else "%d min" % m


# ── ver ──────────────────────────────────────────────────────────────────────────────────────────
def capacidades(red=None):
    return {"juego": JUEGO, "version": VERSION, "acciones": acciones_de(red),
            "monedas": [{"id": m["id"], "nombre": m["nombre"]} for m in MONEDAS], "entorno": config.ENTORNO}


def salud():
    con = _conectadas()
    en_stage = sum(1 for n in con.values()
                   if (PARTIDAS.get(n) or {}).get("inicio") and not (PARTIDAS.get(n) or {}).get("resultado_guardado"))
    detalle = [
        {"nombre": "Servidor", "valor": config.NOMBRE_SERVER},
        {"nombre": "Entorno", "valor": config.ENTORNO},
        {"nombre": "Conectados", "valor": "%d de %d" % (len(con), config.MAX_JUGADORES)},
        {"nombre": "Jugando una stage", "valor": en_stage},
        {"nombre": "Salas abiertas", "valor": len(SALAS)},
        {"nombre": "Cuentas guardadas", "valor": len(nombres_de_cuentas())},
        {"nombre": "Encendido hace", "valor": _duracion(time.time() - getattr(VIVO, "ARRANQUE", time.time()))},
        {"nombre": "Inicio de sesión", "valor": "con el pase de la cuenta" if config.LOGIN == "pase" else "abierto (sin pase)"},
        {"nombre": "Versión del contrato del panel", "valor": VERSION},
    ]
    return {"en_linea": True, "jugando": len(con), "detalle": detalle}


def conectados():
    filas = []
    for nombre, n in sorted(_conectadas().items(), key=lambda x: x[1]):
        p = PARTIDAS.get(n) or {}
        fila = {"id": nombre, "nick": nombre_visible(leer(n)), "enenos_id": enenos_id(nombre),
                "donde": donde_esta(n), "desde": int(p["desde"]) if p.get("desde") else None}
        if p.get("ip_tcp"):
            fila["ip"] = p["ip_tcp"]
        filas.append(fila)
    return {"filas": filas}


def buscar(q):
    """Por la cuenta exacta (`en_10000042`), por el Eñeños ID (número) o por una parte del apodo de cualquiera de
    sus personajes. Primero las exactas; tope 50."""
    q = str(q or "").strip()[:40]
    if not q:
        return {"filas": []}
    ql = q.lower()
    eid = int(q) if re.fullmatch(r"[0-9]{1,20}", q) else None
    con = _conectadas()
    hallados = []
    for nombre in nombres_de_cuentas():
        crudo = _cuenta(nombre)
        if crudo is None:
            continue
        exacta = nombre.lower() == ql or (eid is not None and enenos_id(nombre) == eid)
        pjs, activo = personajes_de(crudo)
        if not exacta and not any(ql in (p.get("nick") or "").lower() for p in pjs):
            continue
        hallados.append((0 if exacta else 1, nombre, {
            "id": nombre, "nick": _nick(nombre, crudo), "enenos_id": enenos_id(nombre), "conectado": nombre in con,
            "resumen": _resumen(crudo, pjs[activo] if pjs else None)}))
    hallados.sort(key=lambda x: (x[0], x[1]))
    return {"filas": [x[2] for x in hallados[:TOPE_BUSCAR]]}


def ficha(ident):
    """La cuenta (o `<cuenta>.<lugar>`: ese personaje) con sus datos en palabras, sus monedas y sus movimientos."""
    m = re.fullmatch(r"([A-Za-z0-9_-]{1,40})(?:\.([0-9]))?", ident or "")
    crudo = _cuenta(m.group(1)) if m else None
    if crudo is None:
        return 404, {"error": "No existe esa cuenta en EDA."}
    nombre = m.group(1)
    pjs, activo = personajes_de(crudo)
    if m.group(2) is not None:
        i = next((k for k, p in enumerate(pjs) if p.get("lugar", k) == int(m.group(2))), None)
        if i is None:
            return 404, {"error": "Esa cuenta no tiene un personaje en ese lugar."}
    else:
        i = activo if pjs else None
    n = _conectadas().get(nombre)
    campos = [{"nombre": "Cuenta", "valor": nombre},
              {"nombre": "Conectado", "valor": ("Sí, " + donde_esta(n)) if n is not None else "No"}]
    if n is not None and (PARTIDAS.get(n) or {}).get("desde"):
        campos.append({"nombre": "Conectado desde", "valor": _cuando(PARTIDAS[n]["desde"])})
    if i is None:
        campos.append({"nombre": "Personajes", "valor": "Ninguno (los crea el jugador en el juego)"})
    else:
        v = vista(crudo, pjs[i])
        st = stats_de(v)
        campos += [
            {"nombre": "Personaje", "valor": (v.get("nick") or nombre) + (" (el que usa)" if i == activo else "")},
            {"nombre": "Clase", "valor": CLASES.get(v.get("clase"), "clase %s" % v.get("clase"))},
            {"nombre": "Nivel", "valor": nivel(v["exp"])},
            {"nombre": "Experiencia", "valor": v["exp"]},
            {"nombre": "Experiencia para el próximo nivel",
             "valor": EXPS[nivel(v["exp"])] if nivel(v["exp"]) < len(EXPS) else "nivel máximo"},
            {"nombre": "Fuerza · Constitución · Destreza · Inteligencia · Sabiduría",
             "valor": " · ".join(str(x) for x in st[:5])},
            {"nombre": "Puntos de estadística sin repartir", "valor": st[5]},
            {"nombre": "Partidas jugadas", "valor": v.get("partidas", 0)},
            {"nombre": "Abandonos", "valor": v.get("abandonos", 0)},
            {"nombre": "Stages terminadas", "valor": len(v.get("terminadas") or [])},
            {"nombre": "Objetos (equipo, bolsa y atajos)", "valor": len(v.get("items") or [])},
            {"nombre": "Habilidades aprendidas", "valor": len(v.get("habilidades") or [])},
            {"nombre": "Amigos", "valor": len(v.get("amigos") or [])},
        ]
    campos.append({"nombre": "Personajes en la cuenta", "valor": "%d de %d" % (len(pjs), MAX_PERSONAJES)})
    try:
        campos.append({"nombre": "Último guardado de la cuenta", "valor": _cuando(os.path.getmtime(ruta_cuenta(nombre)))})
    except OSError:
        pass
    return 200, {
        "id": nombre if m.group(2) is None else ident, "nick": (pjs[i].get("nick") if i is not None else None) or nombre,
        "enenos_id": enenos_id(nombre), "conectado": n is not None, "campos": campos,
        "monedas": {x["id"]: _valor(crudo, x["campo"]) for x in MONEDAS},
        "personajes": [{"id": "%s.%s" % (nombre, p.get("lugar", k)), "nick": p.get("nick") or nombre}
                       for k, p in enumerate(pjs)],
        "movimientos": movimientos(nombre)}


# ── la auditoría ─────────────────────────────────────────────────────────────────────────────────
def auditar(quien, accion, ident, que):
    """Cada cambio pedido por el panel: al registro del server y a `config.PANEL_AUDITORIA` (una línea JSON)."""
    print("panel: %s · %s · %s · %s" % (quien, accion, ident or "-", que), flush=True)
    linea = json.dumps({"cuando": int(time.time()), "quien": quien, "accion": accion, "id": ident, "que": que},
                       ensure_ascii=False)
    with _candado_auditoria:
        os.makedirs(os.path.dirname(config.PANEL_AUDITORIA), exist_ok=True)
        with open(config.PANEL_AUDITORIA, "a", encoding="utf-8") as f:
            f.write(linea + "\n")


def movimientos(nombre, tope=TOPE_MOVIMIENTOS):
    """Los últimos cambios del panel sobre esa cuenta (de los últimos 512 KB de la auditoría), el más nuevo primero."""
    try:
        with open(config.PANEL_AUDITORIA, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 512 * 1024))
            lineas = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    r = []
    for linea in reversed(lineas):
        try:
            x = json.loads(linea)
        except ValueError:
            continue
        if isinstance(x, dict) and x.get("id") == nombre:
            r.append({"cuando": _cuando(x.get("cuando", 0)), "que": x.get("que", ""), "quien": x.get("quien", "")})
            if len(r) >= tope:
                break
    return r


# ── hacer ────────────────────────────────────────────────────────────────────────────────────────
def _texto(v, tope):
    """Un texto para el chat del cliente: sin saltos ni caracteres de control. None si no es texto o pasa el tope."""
    if not isinstance(v, str):
        return None
    t = re.sub(r"\s+", " ", re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", v)).strip()
    return t if len(t) <= tope else None


def _entero(v):
    """Un entero de JSON (no bool) o un texto de dígitos (con signo). → int o None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and re.fullmatch(r"-?[0-9]{1,12}", v.strip()):
        return int(v.strip())
    return None


def mensaje_aviso(texto, conexion):
    """El aviso = una línea del chat (0x1005 tipo 3, medido con el Messenger: se ve en verde con su remitente)."""
    return linea_chat(texto, conexion, nombre=REMITENTE)


def aviso(datos, quien, red):
    texto = _texto(datos.get("texto"), TOPE_AVISO)
    if texto is None and isinstance(datos.get("texto"), str):
        return 400, {"error": "El aviso es demasiado largo (máximo %d letras)." % TOPE_AVISO}
    if not texto:
        return 400, {"error": "Escriba el texto del aviso."}
    con = _conectadas()
    a = datos.get("a")
    if a == "todos":
        ident, destinos = None, sorted(con.values())
    elif a == "uno":
        ident = str(datos.get("id") or "")
        if ident not in con:
            return 404, {"error": "Ese jugador no está conectado."}
        destinos = [con[ident]]
    else:
        return 400, {"error": "Indique a quién va el aviso: «a» tiene que ser \"todos\" o \"uno\"."}
    red.enviar([mensaje_aviso(texto, n) for n in destinos])
    auditar(quien, "aviso", ident, "aviso a %s (%d): %s" % ("todos" if a == "todos" else ident, len(destinos), texto))
    return 200, {"ok": True, "llego_a": len(destinos)}


def echar(datos, quien, red):
    ident = str(datos.get("id") or "")
    n = _conectadas().get(ident)
    if n is None:
        return 404, {"error": "Ese jugador no está conectado."}
    motivo = _texto(datos.get("motivo"), TOPE_MOTIVO) if datos.get("motivo") is not None else ""
    if motivo is None:
        return 400, {"error": "El motivo tiene que ser un texto de hasta %d letras." % TOPE_MOTIVO}
    if motivo:
        red.enviar([mensaje_aviso("Se lo desconectó del servidor. Motivo: %s" % motivo, n)])
    red.cortar(n, 1.5 if motivo else 0)          # (con motivo, que alcance a verlo antes del corte)
    auditar(quien, "echar", ident, "desconectado" + (": %s" % motivo if motivo else ""))
    return 200, {"ok": True}


def moneda(datos, quien, red):
    ident = str(datos.get("id") or "")
    mon = next((m for m in MONEDAS if m["id"] == datos.get("moneda")), None)
    if mon is None:
        return 400, {"error": "Esa moneda no existe en EDA. Las que hay: %s." % ", ".join(m["id"] for m in MONEDAS)}
    cantidad = _entero(datos.get("cantidad"))
    if not cantidad:
        return 400, {"error": "La cantidad tiene que ser un número entero distinto de cero."}
    with _candado:
        if ident in _conectadas():
            return 409, {"error": "El jugador está conectado: el juego no le mostraría el cambio y podría pisarlo. "
                                  "Desconéctelo («echar») o espere a que salga, y vuelva a intentarlo."}
        crudo = _crudo(ident)
        if crudo is None:
            return 404, {"error": "No existe esa cuenta en EDA."}
        antes = _valor(crudo, mon["campo"])
        despues = antes + cantidad
        if despues < 0:
            return 409, {"error": "No alcanza: la cuenta tiene %d de %s y no se le pueden quitar %d."
                                  % (antes, mon["nombre"], -cantidad)}
        if despues > mon["tope"]:
            return 409, {"error": "Pasaría el máximo de %s (%d): hoy tiene %d." % (mon["nombre"], mon["tope"], antes)}
        crudo[mon["campo"]] = despues
        escribir(ident, crudo)
    auditar(quien, "moneda", ident, "%+d %s (%d → %d)" % (cantidad, mon["nombre"], antes, despues))
    return 200, {"ok": True, "antes": antes, "despues": despues}
