r"""herramientas/diag_partida.py -- UN paquete de diagnóstico por PARTIDA, para dárselo a una IA (o leerlo a mano).

★ (21-nov) Para investigar fallas del multijugador entre casas sin buscar archivo por archivo: toma el paquete de
registros del server de prueba (el .tgz que baja la llave `eda-diag`: server.log, relay.log, …) y, si los hay, los
registros de los clientes (NetTrace.log, eda_d3d9.log), corta lo de UNA partida y arma un .zip con:

  RESUMEN.md          quién jugó (#n y cuenta), qué le pasó a cada uno (carga, largada, fin, vuelta a la sala),
                      los caminos P2P, el relay, y las ANOMALÍAS que se detectan solas (ver `anomalias`)
  linea_de_tiempo.txt todo junto y en orden, en UTC: server, relay y cada cliente (su hora local pasada a UTC)
  server.log, relay.log, cliente-<nombre>-*.log   los recortes de esa partida, tal cual (salvo lo que se tapa)

Se tapa (salvo --con-ip): las IP (IP-A, IP-B… siempre la misma letra para la misma IP) y las MAC. Los registros no
traen tickets ni claves; el chat sólo como código (0x1005), nunca su texto.

    py herramientas\diag_partida.py PAQUETE --listar
    py herramientas\diag_partida.py PAQUETE --partida P-20261121-165649-s3 [--cliente jugador2=CARPETA] [--salida X.zip]
    py herramientas\diag_partida.py PAQUETE --desde "2026-11-21 16:50" --hasta "2026-11-21 17:10" [...]
    py herramientas\diag_partida.py control          (las pruebas, sin archivos de verdad)

PAQUETE = el .tgz de `ssh … eda-diag@SERVER HORAS`, o la carpeta donde se abrió. --zona = la hora de las PCs de los
clientes respecto de UTC (Perú: -5, por defecto). Sólo LEE: no cambia ningún archivo de entrada.
"""
import argparse
import io
import json
import os
import re
import sys
import tarfile
import time
import zipfile
from datetime import datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

UTC = timezone.utc
R_DOCKER = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?Z\s")
R_FECHA = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s")
R_HORA = re.compile(r"^(\d\d:\d\d:\d\d)(?:\.(\d{1,3}))?\s")
R_NETTRACE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\s*")
R_MSG = re.compile(r"#(\d+) (←|→) ([0-9a-fA-F]{4}) \((\d+) B\)")
R_PARTIDA = re.compile(r"partida (P-\d{8}-\d{6}-s\d+) empieza: sala (\S+) · (.*)")
R_MIEMBRO = re.compile(r"#(\d+)=(\S+)")
R_CUENTA = re.compile(r"#(\d+) es la cuenta (\S+)")
R_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
R_MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
NOMBRES = {0x104F: "carga (0x104F)", 0x105F: "terminó de cargar (0x105F)", 0x105E: "largada (0x105E)",
           0x1064: "fin de su stage (0x1064)", 0x1073: "PlayEnd (0x1073)", 0x106E: "resultado (0x106E)",
           0x1074: "salir de la stage (0x1074)", 0x1075: "vuelta al lobby (0x1075)", 0x1072: "premios (0x1072)",
           0x1001: "estoy vivo (0x1001)", 0x1005: "chat (0x1005)", 0x1059: "direcciones P2P (0x1059)"}
# lo que el registro de la dll repite todo el tiempo y no dice nada de la red ni de la partida
RUIDO_DLL = ("(escala2d)", "(diag 16:9)", "letras: nº", "(medir", "(gráficos) anisotrópico", "(diag gráficos)")


class Linea:
    __slots__ = ("t", "fuente", "texto")

    def __init__(self, t, fuente, texto):
        self.t, self.fuente, self.texto = t, fuente, texto


# ── leer ─────────────────────────────────────────────────────────────────────────────────────────────────────

def abrir_paquete(ruta):
    """{nombre: texto} del .tgz o la carpeta (sólo lo de texto que interesa)."""
    quiero = ("server.log", "relay.log", "LEEME.txt", "relay.json", "punch.json", "nat.json")

    def nombre(a):                                  # (un recorte a mano: «server_test_0530-0550_UTC.log»)
        return "server.log" if a not in quiero and a.startswith("server") and a.endswith(".log") else a
    r = {"diag": {}}
    if os.path.isdir(ruta):
        for raiz, _, archivos in os.walk(ruta):
            for a in archivos:
                if a.endswith(".jsonl") and os.path.basename(raiz) == "diag":
                    r["diag"][a] = open(os.path.join(raiz, a), encoding="utf-8", errors="replace").read()
                if nombre(a) in quiero and nombre(a) not in r:
                    r[nombre(a)] = open(os.path.join(raiz, a), encoding="utf-8", errors="replace").read()
    else:
        with tarfile.open(ruta) as t:
            for m in t.getmembers():
                a = os.path.basename(m.name)
                if m.isfile() and a.endswith(".jsonl") and "/diag/" in "/" + m.name:
                    r["diag"][a] = t.extractfile(m).read().decode("utf-8", errors="replace")
                    continue
                if m.isfile() and nombre(a) in quiero and nombre(a) not in r:
                    r[nombre(a)] = t.extractfile(m).read().decode("utf-8", errors="replace")
    return r


def leer_server(texto):
    """Las líneas del server con su hora UTC (las que salen sin hora —los print— toman la de la anterior)."""
    out, ultima = [], None
    for crudo in texto.splitlines():
        s = crudo.rstrip("\r")
        m = R_DOCKER.match(s)
        if m:
            ultima = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
            s = s[m.end():]
        m = R_FECHA.match(s)
        if m:
            ultima = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            s = s[m.end():]
        if ultima is not None and s.strip():
            out.append(Linea(ultima, "server", s.strip()))
    return out


def leer_relay(texto, dia):
    """relay.log: «AAAA-MM-DD HH:MM:SS texto» (desde el 21-nov) o «HH:MM:SS texto» (antes: el día es `dia`)."""
    out = []
    for crudo in texto.splitlines():
        s = crudo.rstrip("\r")
        m = R_FECHA.match(s)
        if m:
            t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        else:
            m = R_HORA.match(s)
            if not m or dia is None:
                continue
            t = datetime.combine(dia, datetime.strptime(m.group(1), "%H:%M:%S").time(), UTC)
        out.append(Linea(t, "relay", s[m.end():].strip()))
    return out


def leer_cliente(nombre, ruta, dia_local, zona):
    """(`dia_local` = None: el día sale de la fecha de cada archivo, lo normal)"""
    """NetTrace.log («[HH:MM:SS]\\t…», hora LOCAL de su PC) y eda_d3d9.log («HH:MM:SS.mmm  …», local) → UTC.
    `ruta` = una carpeta (se toman los dos si están) o un archivo."""
    archivos = []
    if os.path.isdir(ruta):
        for a in ("NetTrace.log", "eda_d3d9.log"):
            if os.path.exists(os.path.join(ruta, a)):
                archivos.append(os.path.join(ruta, a))
    else:
        archivos.append(ruta)
    tz = timezone(timedelta(hours=zona))
    out = {}
    for a in archivos:
        datos = open(a, "rb").read()
        texto = datos.decode("utf-16") if datos[:2] in (b"\xff\xfe", b"\xfe\xff") else datos.decode("utf-8", "replace")
        tipo = "NetTrace" if "nettrace" in os.path.basename(a).lower() else "dll"
        # ★ las líneas no traen el DÍA (y eda_d3d9.log junta varios días): se cuenta hacia ATRÁS desde la fecha del
        #   archivo (su última línea es de ese día) y se resta un día cada vez que la hora «salta» hacia adelante
        dia = datetime.fromtimestamp(os.path.getmtime(a), tz).date() if dia_local is None else dia_local
        crudas = []
        for crudo in texto.splitlines():
            s = crudo.rstrip("\r")
            m = R_NETTRACE.match(s) if tipo == "NetTrace" else R_HORA.match(s)
            if m:
                crudas.append((m, s))
        lineas, despues = [], None
        for m, s in reversed(crudas):
            h = datetime.strptime(m.group(1), "%H:%M:%S").time()
            t = datetime.combine(dia, h, tz)
            if despues is not None and t > despues + timedelta(hours=1):
                dia -= timedelta(days=1)
                t -= timedelta(days=1)
            despues = t
            if tipo == "dll" and m.group(2):
                t += timedelta(milliseconds=int(m.group(2).ljust(3, "0")))
            cuerpo = s[m.end():].strip()
            if tipo == "dll" and any(x in cuerpo for x in RUIDO_DLL):
                continue
            lineas.append(Linea(t.astimezone(UTC), "%s/%s" % (nombre, tipo), cuerpo))
        lineas.reverse()
        out[tipo] = lineas
    return out


def leer_diag(archivos):
    """★ (21-nov) lo que mandaron los clientes beta (servidor/diag.py): «<cuenta>-<sesion>.jsonl» → {cuenta: [Linea]}.
    La hora de cada evento es la del reloj de SU PC: se corrige con «dr» (la diferencia que midió el server al recibir)."""
    r = {}
    for nombre, texto in archivos.items():
        m = re.match(r"^(.+)-([0-9a-f]{32})\.jsonl$", nombre)
        if not m:
            continue
        cuenta, sesion = m.group(1), m.group(2)
        for ln in texto.splitlines():
            try:
                ev = json.loads(ln)
            except ValueError:
                continue
            t = datetime.fromtimestamp((ev.get("t", 0) + ev.get("dr", 0)) / 1000.0, UTC)
            resto = " ".join("%s=%s" % (k, v) for k, v in ev.items() if k not in ("t", "e", "r", "dr", "m"))
            r.setdefault(cuenta, []).append(Linea(t, "%s/diag·%s" % (cuenta, sesion[:6]), ("%s %s" % (ev.get("e"), resto)).strip()))
    for v in r.values():
        v.sort(key=lambda ln: ln.t)
    return r


def de_la_cuenta(diag, cuenta):
    """las líneas de diag de esa cuenta del server («en_10006352» ↔ el usuario «10006352» que manda la dll)"""
    out = []
    for c, ls in diag.items():
        if cuenta and (c == cuenta or cuenta.endswith("_" + c)):
            out += ls
    return out


# ── las partidas ─────────────────────────────────────────────────────────────────────────────────────────────

def partidas(server):
    """[{id, desde, miembros {n: cuenta}}] en el orden del registro. Con las líneas «partida … empieza» (desde el
    21-nov) o, en registros viejos, por los 0x104F que salen juntos (en ±2 s) → id «P?-HHMMSS»."""
    r = []
    for ln in server:
        m = R_PARTIDA.search(ln.texto)
        if m:
            r.append({"id": m.group(1), "desde": ln.t, "sala": m.group(2),
                      "miembros": {int(a): b for a, b in R_MIEMBRO.findall(m.group(3))}})
    if r:
        return r
    cuentas, grupo = {}, None
    for ln in server:
        m = R_CUENTA.search(ln.texto)
        if m:
            cuentas[int(m.group(1))] = m.group(2)
        m = R_MSG.search(ln.texto)
        if m and m.group(2) == "→" and int(m.group(3), 16) == 0x104F:
            n = int(m.group(1))
            if grupo and (ln.t - grupo["desde"]).total_seconds() <= 2:
                grupo["miembros"].setdefault(n, cuentas.get(n, "?"))
            else:
                grupo = {"id": "P?-" + ln.t.strftime("%Y%m%d-%H%M%S"), "desde": ln.t, "sala": "?",
                         "miembros": {n: cuentas.get(n, "?")}}
                r.append(grupo)
    return r


def ventana_de(partida, todas, server, antes=90, despues=60):
    """[desde, hasta] de la partida: desde 90 s antes de la carga (la sala y las direcciones P2P) hasta 60 s
    después de que el último salió de la stage (o de que se cerró), o hasta la partida siguiente de los mismos."""
    desde = partida["desde"] - timedelta(seconds=antes)
    siguiente = next((p["desde"] for p in todas if p["desde"] > partida["desde"]
                      and set(p["miembros"]) & set(partida["miembros"])), None)
    fin = None
    for ln in server:
        if ln.t < partida["desde"]:
            continue
        if siguiente and ln.t >= siguiente:
            break
        if ("partida %s:" % partida["id"]) in ln.texto and "ya no queda nadie" in ln.texto:
            fin = ln.t
            break
        m = R_MSG.search(ln.texto)
        if m and int(m.group(1)) in partida["miembros"]:
            fin = ln.t
    hasta = (fin or partida["desde"]) + timedelta(seconds=despues)
    if siguiente and hasta > siguiente:
        hasta = siguiente
    return desde, hasta


# ── qué le pasó a cada uno ───────────────────────────────────────────────────────────────────────────────────

def hechos(server, miembros, desde, hasta, inicio):
    """{n: {'recibio': {cmd: [t…]}, 'mando': {cmd: [t…]}, 'ultimo_mando', 'ultimo_recibio', 'cerrada'}}"""
    h = {n: {"recibio": {}, "mando": {}, "ultimo_mando": None, "ultimo_recibio": None, "cerrada": None}
         for n in miembros}
    for ln in server:
        if not (desde <= ln.t <= hasta + timedelta(minutes=10)):
            continue
        m = R_MSG.search(ln.texto)
        if m and ln.t > hasta:
            continue
        if m:
            n, cmd = int(m.group(1)), int(m.group(3), 16)
            if n not in h:
                continue
            if m.group(2) == "←":
                h[n]["mando"].setdefault(cmd, []).append(ln.t)
                h[n]["ultimo_mando"] = ln.t
            else:
                h[n]["recibio"].setdefault(cmd, []).append(ln.t)
                h[n]["ultimo_recibio"] = ln.t
            continue
        m = re.search(r"#(\d+) cerrada", ln.texto)
        if m and int(m.group(1)) in h and ln.t >= inicio and h[int(m.group(1))]["cerrada"] is None:
            h[int(m.group(1))]["cerrada"] = ln.t
    return h


def primera(lista, desde=None):
    for t in lista or ():
        if desde is None or t >= desde:
            return t
    return None


def anomalias(h, inicio, clientes, partida_id):
    """Las reglas. Cada una dice QUÉ se vio y QUÉ falta, con la hora: no adivina la causa."""
    a = []
    fines = {n: primera(x["mando"].get(0x1064), inicio) for n, x in h.items()}
    salidas = {n: primera(x["mando"].get(0x1074), inicio) for n, x in h.items()}
    vueltas = {n: primera(x["recibio"].get(0x1075), inicio) for n, x in h.items()}
    for n, x in h.items():
        carga = primera(x["recibio"].get(0x104F), inicio - timedelta(seconds=5))
        largada = primera(x["recibio"].get(0x105E), carga)
        if carga and not largada:
            a.append("⛔ #%s recibió la carga (0x104F, %s) y NUNCA la largada (0x105E): se quedó cargando."
                     % (n, hh(carga)))
        if carga and largada:
            molestos = [(c, t) for c, ts in x["recibio"].items() if 0x1003 <= c <= 0x100B
                        for t in ts if carga <= t < largada]
            if molestos:
                a.append("⚠ #%s recibió %s DURANTE la carga (entre 0x104F y 0x105E): eso termina el hilo de carga del "
                         "juego (0x5345C0)." % (n, ", ".join("0x%04X a las %s" % (c, hh(t)) for c, t in molestos)))
        if largada and not (primera(x["recibio"].get(0x1073), largada) or salidas[n] or vueltas[n] or x["cerrada"]):
            a.append("⛔ #%s tuvo la largada (%s) y después NO recibió el fin (PlayEnd 0x1073), no salió (0x1074) ni "
                     "volvió al lobby (0x1075), ni se desconectó: se quedó en la stage." % (n, hh(largada)))
        if largada and x["cerrada"] and not (fines[n] or salidas[n]):
            a.append("⛔ #%s se DESCONECTÓ (%s) en la stage, sin fin ni salida." % (n, hh(x["cerrada"])))
        if fines[n] and not primera(x["recibio"].get(0x1073), fines[n]):
            a.append("⛔ #%s mandó su fin (0x1064, %s) y NO recibió el PlayEnd (0x1073)." % (n, hh(fines[n])))
    # ★ con varios, el fin lo manda SÓLO el máster (exe `0x636EA0`, bandera +0x168): los demás terminan cuando el
    #   server les manda su PlayEnd. Si el máster terminó y a otro que seguía en la stage no le llegó → quedó adentro
    playend = {n: primera(x["recibio"].get(0x1073), inicio) for n, x in h.items()}
    for n, t in sorted(((n, t) for n, t in fines.items() if t), key=lambda kv: kv[1]):
        for o in h:
            if o == n or salidas[o] or (h[o]["cerrada"] and h[o]["cerrada"] <= t):
                continue
            if not primera(h[o]["recibio"].get(0x105E), inicio):
                continue
            pe = playend[o]
            if not pe or (pe - t).total_seconds() > 5:
                ult = h[o]["ultimo_mando"]
                a.append("⛔ #%s mandó el fin de la stage (0x1064, %s) y a #%s, que seguía en la stage, NO le llegó su "
                         "PlayEnd (0x1073)%s. Con varios jugadores sólo el máster manda el 0x1064 (exe 0x636EA0): el "
                         "server tiene que cerrarles la stage a los demás. Lo último que mandó #%s: %s." % (
                             n, hh(t), o, " hasta las %s" % hh(pe) if pe else "", o, hh(ult) if ult else "nada"))
        break
    for n, x in h.items():
        largada = primera(x["recibio"].get(0x105E), inicio)
        if not largada:
            continue
        fin_n = fines[n] or salidas[n] or x["cerrada"] or x["ultimo_recibio"]
        vivos = [t for t in x["mando"].get(0x1001, ()) if t >= largada]
        todos = sorted(t for ts in x["mando"].values() for t in ts if t >= largada)
        hueco = max(((b - a_).total_seconds(), a_) for a_, b in zip(todos, todos[1:])) if len(todos) > 1 else (0, None)
        if hueco[0] >= 45:
            a.append("⚠ #%s estuvo %d s sin mandarle NADA al server en la stage (desde %s; el «estoy vivo» es cada "
                     "20 s)." % (n, hueco[0], hh(hueco[1])))
        if fin_n and not vivos and (fin_n - largada).total_seconds() > 60:
            a.append("⚠ #%s no mandó ningún «estoy vivo» (0x1001) en la stage." % n)
    for nombre, tipos in clientes.items():
        nt = tipos.get("NetTrace", [])
        textos = [(ln.t, ln.texto) for ln in nt]
        doend = next((t for t, s in textos if "Thread DoEnd" in s), None)
        start = next((t for t, s in textos if "Play_Start Succeed" in s), None)
        if doend and (not start or doend < start):
            a.append("⛔ cliente %s: el hilo de carga terminó (Thread DoEnd!! %s) %s." % (
                nombre, hh(doend), "ANTES de la largada" if start else "y la largada (Play_Start) no se procesó"))
        if start and not any("PlayEnd" in s for _, s in textos):
            a.append("⚠ cliente %s: entró a la stage (%s) y su NetTrace no tiene PlayEnd." % (nombre, hh(start)))
        congelados = [ln for ln in tipos.get("dll", []) if "CONGELADO" in ln.texto]
        for ln in congelados[:5]:
            a.append("⚠ cliente %s: %s (%s)" % (nombre, ln.texto, hh(ln.t)))
    return a


def hh(t):
    return t.strftime("%H:%M:%S") if t else "—"


# ── tapar ────────────────────────────────────────────────────────────────────────────────────────────────────

class Tapa:
    def __init__(self, activa):
        self.activa, self.letras = activa, {}

    def __call__(self, s):
        if not self.activa:
            return s
        s = R_MAC.sub("MAC-tapada", s)

        def ip(m):
            v = m.group(0)
            if v.startswith(("127.", "0.")) or v == "255.255.255.255":
                return v
            if v not in self.letras:
                k = len(self.letras)
                self.letras[v] = "IP-" + (chr(65 + k) if k < 26 else "Z%d" % k)
            return self.letras[v]
        return R_IP.sub(ip, s)


# ── armar ────────────────────────────────────────────────────────────────────────────────────────────────────

def armar(paquete, partida_id=None, desde=None, hasta=None, clientes=(), zona=-5, con_ip=False, salida=None):
    """→ (ruta del .zip, el RESUMEN en texto)"""
    arch = abrir_paquete(paquete) if paquete else {}
    server = leer_server(arch.get("server.log", ""))
    todas = partidas(server)
    if partida_id:
        p = next((x for x in todas if x["id"] == partida_id), None)
        if not p:
            raise SystemExit("⛔ no está la partida %s. Las que hay: %s" % (partida_id, ", ".join(x["id"] for x in todas)
                                                                        or "ninguna"))
        desde_, hasta_ = ventana_de(p, todas, server)
        elegidas = [p]
    else:
        desde_, hasta_ = desde, hasta
        elegidas = [x for x in todas if desde_ <= x["desde"] <= hasta_]
    dia = (desde_ or datetime.now(UTC)).date()
    relay = leer_relay(arch.get("relay.log", ""), dia)
    cli = {n: leer_cliente(n, r, None, zona) for n, r in clientes}
    tapa = Tapa(not con_ip)

    def en(ln):
        return desde_ <= ln.t <= hasta_
    miembros = {}
    for x in elegidas:
        miembros.update(x["miembros"])
    nums = set(miembros)

    def del_server(ln):
        m = re.findall(r"#(\d+)", ln.texto)
        return not m or any(int(k) in nums for k in m) or not nums

    diag = leer_diag(arch.get("diag", {}))
    dg = {n: [ln for ln in de_la_cuenta(diag, c) if en(ln)] for n, c in miembros.items()}
    sv = [ln for ln in server if en(ln) and del_server(ln)]
    rl = [ln for ln in relay if en(ln)]
    cl = {n: {t: [ln for ln in ls if en(ln)] for t, ls in tipos.items()} for n, tipos in cli.items()}
    inicio = elegidas[0]["desde"] if elegidas else desde_
    h = hechos(server, nums, desde_, hasta_, inicio)
    an = anomalias(h, inicio, cl, elegidas[0]["id"] if elegidas else None) if nums else []
    for n, ls in dg.items():
        for ln in ls:
            ev = ln.texto.split(" ", 1)[0]
            if ev in ("caida", "congelado", "atrapado_carga", "server_corta", "tcp_silencio"):
                an.append("%s #%s (%s), su cliente: %s (%s)" % ("⛔" if ev in ("caida", "atrapado_carga") else "⚠", n,
                                                               miembros.get(n, "?"), ln.texto, hh(ln.t)))
    nombre = elegidas[0]["id"] if len(elegidas) == 1 else "intervalo-%s" % desde_.strftime("%Y%m%d-%H%M%S")

    res = ["# Diagnóstico de %s" % nombre, "",
           "Ventana: %s → %s UTC (Perú = UTC−5). Armado: %s UTC por herramientas/diag_partida.py." % (
               desde_.strftime("%Y-%m-%d %H:%M:%S"), hasta_.strftime("%H:%M:%S"),
               datetime.now(UTC).strftime("%Y-%m-%d %H:%M")), ""]
    for x in elegidas:
        res.append("- Partida **%s** (sala %s), carga a las %s: %s" % (x["id"], x["sala"], hh(x["desde"]), ", ".join(
            "#%s = %s" % (n, c) for n, c in sorted(x["miembros"].items()))))
    if not elegidas:
        res.append("- Ninguna partida empezó en esta ventana.")
    res += ["", "## Anomalías detectadas", ""] + (["- " + tapa(x) for x in an] or ["- Ninguna regla saltó."])
    res += ["", "## Qué le pasó a cada jugador (según el server)", "",
            "| # | cuenta | carga 0x104F | largada 0x105E | fin 0x1064 | PlayEnd 0x1073 | salida 0x1074 | lobby 0x1075 "
            "| último que mandó | desconexión |", "|---|---|---|---|---|---|---|---|---|---|"]
    for n in sorted(h):
        x = h[n]
        res.append("| #%s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            n, miembros.get(n, "?"), hh(primera(x["recibio"].get(0x104F))), hh(primera(x["recibio"].get(0x105E))),
            hh(primera(x["mando"].get(0x1064))), hh(primera(x["recibio"].get(0x1073))),
            hh(primera(x["mando"].get(0x1074))), hh(primera(x["recibio"].get(0x1075))),
            hh(x["ultimo_mando"]), hh(x["cerrada"])))
    caminos = [tapa(ln.texto) for ln in sv if ln.texto.startswith("sala: a #")]
    res += ["", "## Caminos P2P que dio el server", ""] + (["- " + c for c in caminos] or ["- (no hay líneas «sala: a #…»)"])
    resumen_relay = [tapa(ln.texto) for ln in rl if "reenviados" in ln.texto or "olvida" in ln.texto
                     or "descartado" in ln.texto][:40]
    res += ["", "## Relay", ""] + (["- %s" % x for x in resumen_relay] or ["- Nada del relay en la ventana "
                                                                         "(con P2P directo es lo normal)."])
    res += ["", "## Diagnóstico automático de los clientes", ""] + (
        ["- #%s (%s): %d eventos" % (n, miembros.get(n, "?"), len(ls)) for n, ls in sorted(dg.items()) if ls]
        or ["- Ninguno en la ventana (clientes sin la dll con diagnóstico, o EDA_DIAG apagado)."])
    res += ["", "## Clientes", ""]
    if cl:
        for n, tipos in cl.items():
            res.append("- **%s**: %s" % (n, ", ".join("%s (%d líneas)" % (t, len(ls)) for t, ls in tipos.items())))
    else:
        res.append("- Sin registros de clientes. Para sumarlos: `--cliente NOMBRE=carpeta del juego` (NetTrace.log y "
                   "eda_d3d9.log, juntados apenas termina la partida: NetTrace.log se pisa en cada sesión).")
    res += ["", "## Cómo leer el resto", "",
            "- `linea_de_tiempo.txt`: todo junto en UTC. `server` = lo que entra (←) y sale (→) por cada conexión #n; "
            "`relay` = el relay UDP; `<nombre>/NetTrace` y `<nombre>/dll` = cada cliente (hora de su PC pasada a UTC: "
            "la diferencia de reloj entre PCs puede ser de unos segundos).",
            "- Las IP están tapadas (IP-A, IP-B…: la misma letra = la misma IP)." if not con_ip else "- Con las IP.",
            ""]
    resumen = "\n".join(res)

    todo = sorted(sv + rl + [ln for tipos in cl.values() for ls in tipos.values() for ln in ls]
                  + [ln for ls in dg.values() for ln in ls], key=lambda ln: ln.t)
    linea = "\n".join("%s  %-18s %s" % (ln.t.strftime("%Y-%m-%d %H:%M:%S"), ln.fuente, tapa(ln.texto)) for ln in todo)
    salida = salida or "%s.zip" % nombre
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("RESUMEN.md", resumen)
        z.writestr("linea_de_tiempo.txt", linea + "\n")
        z.writestr("server.log", "\n".join("%s %s" % (ln.t.strftime("%Y-%m-%d %H:%M:%S"), tapa(ln.texto)) for ln in sv) + "\n")
        z.writestr("relay.log", "\n".join("%s %s" % (ln.t.strftime("%Y-%m-%d %H:%M:%S"), tapa(ln.texto)) for ln in rl) + "\n")
        for n, tipos in cl.items():
            for t, ls in tipos.items():
                z.writestr("cliente-%s-%s.log" % (n, t), "\n".join("%s %s" % (ln.t.strftime("%Y-%m-%d %H:%M:%S"),
                                                                              tapa(ln.texto)) for ln in ls) + "\n")
        for n, ls in dg.items():
            if ls:
                z.writestr("diag-%s.log" % n, "\n".join("%s %s %s" % (ln.t.strftime("%Y-%m-%d %H:%M:%S"), ln.fuente,
                                                                       tapa(ln.texto)) for ln in ls) + "\n")
        if "LEEME.txt" in arch:
            z.writestr("LEEME-del-server.txt", tapa(arch["LEEME.txt"]))
    return salida, resumen


def fecha(s):
    s = s.strip().replace("T", " ")
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, f).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise SystemExit("⛔ fecha «%s»: va «AAAA-MM-DD HH:MM[:SS]» en UTC" % s)


# ── pruebas ──────────────────────────────────────────────────────────────────────────────────────────────────

def control():
    """Con registros INVENTADOS (rangos de documentación del RFC 5737): las dos fallas medidas en el server de
    prueba —la carga cortada por un 0x1005 (21-nov 05:35) y uno que termina la stage mientras el otro se queda
    (21-nov 16:58)— y el revés: una partida sana no levanta ninguna anomalía."""
    import tempfile
    ok = []

    def chequear(t, c, d=""):
        print("  %s %s %s" % ("✅" if c else "⛔", t, d))
        ok.append(bool(c))
    d = tempfile.mkdtemp(prefix="diag_partida_")
    server = """2026-11-21 16:55:30 #1 conectó 198.51.100.26:18111
2026-11-21 16:55:30 #1 ← 100f (237 B)
#1 es la cuenta en_1
2026-11-21 16:55:40 #2 conectó 203.0.113.77:40500
2026-11-21 16:55:40 #2 ← 100f (237 B)
#2 es la cuenta en_2
2026-11-21 16:56:10 #2 ← 101f (26 B)
sala: a #1 le doy #2 por directo (pública)
sala: a #2 le doy #1 por directo (pública)
2026-11-21 16:56:48 #1 ← 104e (0 B)
partida P-20261121-165648-s3 empieza: sala 3 · #1=en_1 · #2=en_2
2026-11-21 16:56:48 #1 → 104f (140 B)
2026-11-21 16:56:48 #2 → 104f (140 B)
2026-11-21 16:56:52 #1 ← 105f (4 B)
2026-11-21 16:56:52 #2 ← 105f (4 B)
2026-11-21 16:56:53 #1 → 105e (4 B)
2026-11-21 16:56:53 #2 → 105e (4 B)
2026-11-21 16:57:10 #2 ← 1001 (5 B)
2026-11-21 16:57:30 #1 ← 1001 (5 B)
2026-11-21 16:58:33 #1 ← 1064 (1 B)
2026-11-21 16:58:33 #1 → 1073 (60 B)
partida P-20261121-165648-s3: #1 terminó su stage · siguen en la stage: #2
2026-11-21 16:58:34 #1 → 106e (19 B)
2026-11-21 16:59:10 #2 ← 1001 (5 B)
2026-11-21 17:01:10 #2 ← 1001 (5 B)
2026-11-21 17:04:00 #2 cerrada
"""
    relay = "2026-11-21 16:57:30 reenviados en 30 s: 1→2: 40, 2→1: 0\n"
    os.makedirs(os.path.join(d, "eda-prueba-diagnostico"))
    open(os.path.join(d, "eda-prueba-diagnostico", "server.log"), "w").write(server)
    open(os.path.join(d, "eda-prueba-diagnostico", "relay.log"), "w").write(relay)
    os.makedirs(os.path.join(d, "eda-prueba-diagnostico", "diag"))
    t_caida = int(datetime(2026, 11, 21, 16, 57, 30, tzinfo=UTC).timestamp() * 1000)
    with open(os.path.join(d, "eda-prueba-diagnostico", "diag", "2-" + "ab" * 16 + ".jsonl"), "w") as f:
        f.write(json.dumps({"t": t_caida - 3000, "e": "escena", "a": "stage", "r": t_caida, "dr": 3000}) + "\n")
        f.write(json.dumps({"t": t_caida - 3000, "e": "caida", "codigo": "C0000005", "sitio": "0x7F4626", "dr": 3000}) + "\n")
    with open(os.path.join(d, "eda-prueba-diagnostico", "diag", "12-" + "cd" * 16 + ".jsonl"), "w") as f:
        f.write(json.dumps({"t": t_caida, "e": "caida", "sitio": "0x1", "dr": 0}) + "\n")
    tgz = os.path.join(d, "paquete.tgz")
    with tarfile.open(tgz, "w:gz") as t:
        t.add(os.path.join(d, "eda-prueba-diagnostico"), arcname="eda-prueba-diagnostico")
    cli = os.path.join(d, "jugador2")
    os.makedirs(cli)
    open(os.path.join(cli, "NetTrace.log"), "w").write(
        "[11:55:31]\t00:00:5E:00:53:01\n[11:56:49]\tThread Do Start\n[11:56:53]\tOnPktS2C_Ntf_Play_Start Succeed\n"
        "[11:56:53]\tThread DoEnd!!\n")
    open(os.path.join(cli, "eda_d3d9.log"), "w").write(
        "11:57:40.100    (diag) ⚠ CONGELADO 4000 ms sin cuadros (escena 0x00899C20)\n11:57:41.000    (escala2d) ruido\n")
    hora_pc = datetime(2026, 11, 21, 12, 10, tzinfo=timezone(timedelta(hours=-5))).timestamp()
    for a in ("NetTrace.log", "eda_d3d9.log"):
        os.utime(os.path.join(cli, a), (hora_pc, hora_pc))
    todas = partidas(leer_server(server))
    chequear("encuentra la partida por su línea «partida … empieza», con sus dos jugadores",
             [x["id"] for x in todas] == ["P-20261121-165648-s3"] and todas[0]["miembros"] == {1: "en_1", 2: "en_2"})
    z, res = armar(tgz, partida_id="P-20261121-165648-s3", clientes=[("jugador2", cli)], salida=os.path.join(d, "p.zip"))
    chequear("lo de la última prueba: #1 termina y #2 se queda → la anomalía lo dice, con la hora",
             "#1 mandó el fin de la stage (0x1064, 16:58:33) y a #2, que seguía en la stage, NO le llegó su PlayEnd" in res)
    chequear("…y que #2 siguió vivo (mandó «estoy vivo») hasta desconectarse", "se DESCONECTÓ (17:04:00)" in res)
    chequear("el cliente: su hora de Perú pasa a UTC (11:56:53 → 16:56:53) y entra en la línea de tiempo",
             "16:56:53  jugador2/NetTrace" in zipfile.ZipFile(z).read("linea_de_tiempo.txt").decode())
    chequear("el congelamiento que vio la dll aparece en las anomalías", "CONGELADO 4000 ms" in res)
    chequear("★ diagnóstico automático: la caída que mandó el cliente de #2 entra a las anomalías, con la hora del server",
             "#2 (en_2), su cliente: caida codigo=C0000005 sitio=0x7F4626 (16:57:30)" in res, res.split("## Anomalías")[1][:600])
    chequear("★ el revés: lo de la cuenta 12 no se confunde con la 2", "sitio=0x1" not in res)
    todo = "".join(zipfile.ZipFile(z).read(n).decode() for n in zipfile.ZipFile(z).namelist())
    chequear("★ tapadas: ninguna IP ni MAC de los registros queda en el .zip",
             "198.51.100.26" not in todo and "203.0.113.77" not in todo and "00:00:5E:00:53:01" not in todo and "IP-A" in todo)
    chequear("★ el ruido de la dll (escala2d) no entra", "ruido" not in todo)
    chequear("un solo .zip con RESUMEN, línea de tiempo y los recortes",
             set(zipfile.ZipFile(z).namelist()) >= {"RESUMEN.md", "linea_de_tiempo.txt", "server.log", "relay.log",
                                                    "cliente-jugador2-NetTrace.log", "cliente-jugador2-dll.log", "diag-2.log"})
    # la carga cortada (21-nov 05:35): registro viejo, sin la línea «partida», con un 0x1005 durante la carga
    viejo = """2026-11-21 05:35:48 #1 → 104f (140 B)
2026-11-21 05:35:48 #2 → 104f (140 B)
2026-11-21 05:35:51 #1 ← 105f (4 B)
2026-11-21 05:35:52 #1 → 1005 (261 B)
2026-11-21 05:35:53 #2 ← 105f (4 B)
2026-11-21 05:35:53 #2 → 105e (4 B)
2026-11-21 05:35:53 #1 → 105e (4 B)
2026-11-21 05:36:30 #2 ← 1074 (1 B)
2026-11-21 05:36:30 #2 → 1075 (16 B)
"""
    open(os.path.join(d, "eda-prueba-diagnostico", "server.log"), "w").write(viejo)
    ps = partidas(leer_server(viejo))
    chequear("registro viejo (sin «partida … empieza»): la partida sale de los 0x104F juntos",
             [x["id"] for x in ps] == ["P?-20261121-053548"] and set(ps[0]["miembros"]) == {1, 2})
    _, res = armar(os.path.join(d, "eda-prueba-diagnostico"), partida_id="P?-20261121-053548",
                   salida=os.path.join(d, "v.zip"))
    chequear("el 0x1005 DURANTE la carga se detecta (lo del 21-nov 05:35)", "#1 recibió 0x1005 a las 05:35:52" in res)
    # el revés: una partida sana
    sana = """2026-11-21 18:00:00 #1 → 104f (140 B)
2026-11-21 18:00:00 #2 → 104f (140 B)
2026-11-21 18:00:04 #1 → 105e (4 B)
2026-11-21 18:00:04 #2 → 105e (4 B)
2026-11-21 18:00:20 #1 ← 1001 (5 B)
2026-11-21 18:00:21 #2 ← 1001 (5 B)
2026-11-21 18:00:40 #1 ← 1001 (5 B)
2026-11-21 18:00:41 #2 ← 1001 (5 B)
2026-11-21 18:01:00 #1 ← 1064 (1 B)
2026-11-21 18:01:00 #1 → 1073 (60 B)
2026-11-21 18:01:00 #2 → 1073 (60 B)
"""
    open(os.path.join(d, "eda-prueba-diagnostico", "server.log"), "w").write(sana)
    _, res = armar(os.path.join(d, "eda-prueba-diagnostico"), desde=fecha("2026-11-21 17:59"),
                   hasta=fecha("2026-11-21 18:05"), salida=os.path.join(d, "s.zip"))
    chequear("★ el revés: una partida sana (el máster termina y los dos reciben su PlayEnd) → ninguna anomalía",
             "Ninguna regla saltó." in res, res.split("## Anomalías detectadas")[1][:300] if "Ninguna" not in res else "")
    chequear("por intervalo horario: toma la partida que empezó adentro", "P?-20261121-180000" in res)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


def main():
    if sys.argv[1:2] == ["control"]:
        return control()
    a = argparse.ArgumentParser(description="Un paquete de diagnóstico por partida (ver el comienzo del archivo).")
    a.add_argument("paquete", help="el .tgz del server de prueba (llave eda-diag) o su carpeta")
    a.add_argument("--listar", action="store_true", help="las partidas que hay en el paquete")
    a.add_argument("--partida", help="el ID (P-AAAAMMDD-HHMMSS-sN, o P?-… en registros viejos)")
    a.add_argument("--desde", help="UTC «AAAA-MM-DD HH:MM[:SS]»")
    a.add_argument("--hasta", help="UTC «AAAA-MM-DD HH:MM[:SS]»")
    a.add_argument("--cliente", action="append", default=[], help="NOMBRE=carpeta del juego (o un .log); repetible")
    a.add_argument("--zona", type=float, default=-5, help="horas de las PCs de los clientes respecto de UTC (Perú: -5)")
    a.add_argument("--hora-local", action="store_true", help="--desde y --hasta en la hora de --zona (Perú), no en UTC")
    a.add_argument("--con-ip", action="store_true", help="no tapar las IP ni las MAC")
    a.add_argument("--salida", help="el .zip (por defecto: <ID>.zip)")
    o = a.parse_args()
    if o.listar:
        server = leer_server(abrir_paquete(o.paquete).get("server.log", ""))
        for x in partidas(server):
            print("%s  %s UTC  sala %s  %s" % (x["id"], x["desde"].strftime("%Y-%m-%d %H:%M:%S"), x["sala"],
                                               ", ".join("#%s=%s" % kv for kv in sorted(x["miembros"].items()))))
        return 0
    if not o.partida and not (o.desde and o.hasta):
        a.error("va --partida ID, o --desde y --hasta")
    clientes = []
    for c in o.cliente:
        if "=" not in c:
            a.error("--cliente va NOMBRE=carpeta")
        n, r = c.split("=", 1)
        clientes.append((re.sub(r"[^\w.-]", "_", n), r))
    corr = timedelta(hours=-o.zona) if o.hora_local else timedelta(0)
    z, res = armar(o.paquete, o.partida, fecha(o.desde) + corr if o.desde else None,
                   fecha(o.hasta) + corr if o.hasta else None, clientes, o.zona, o.con_ip, o.salida)
    print(res)
    print("→ %s" % os.path.abspath(z))
    return 0


if __name__ == "__main__":
    sys.exit(main())
