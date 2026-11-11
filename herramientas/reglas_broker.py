r"""reglas_broker -- escribe `_trabajo/broker/reglas.json`: lo que el oyente de `espiar_broker.py`
contesta a cada comando del cliente. Es el guion del «server» mientras no haya server.

    py herramientas\reglas_broker.py            # el guion entero hasta la lista de servidores
    py herramientas\reglas_broker.py vacio      # el mismo, pero sin anuncio ni servidores

Lo medido de cada mensaje está en `paquete_broker.py` y en MEDICIONES (corridas 15 y 16).
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paquete_broker as P                                   # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                            # noqa: BLE001
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGLAS = os.path.join(RAIZ, "_trabajo", "broker", "reglas.json")
BROKER_IP, BROKER_PUERTO = "218.145.66.187", 25000


def ip_host(ip):
    """IP como u32 en orden de host, que es como viaja (el cliente le hace ntohl)."""
    return struct.pack("<I", struct.unpack(">I", bytes(int(x) for x in ip.split(".")))[0])


def guion(vacio=False):
    # 0x0607: dónde está el «UDP label» para medir el NAT (lo mandamos al Broker mismo, así
    #         WinDivert anota el UDP). 0x0609: el resultado del NAT: tipo 1 = «public».
    nat_init = ip_host(BROKER_IP) + struct.pack("<H", BROKER_PUERTO)
    nat_tipo = struct.pack("<B3x", 1) + ip_host("127.0.0.1") + struct.pack("<H", 57654)
    if vacio:
        anuncio, servidores = b"\0" * 449, P.cuerpo_servidores([])
    else:
        anuncio = P.cuerpo_anuncio("EDA vuelve", "Servidor de prueba de EDA - Espada del Alma. "
                                   "Este anuncio lo manda nuestro server.")
        # ★ ENTER (`0x549300`) desconecta del Broker y conecta a la IP:puerto del registro. Se
        #   apunta al MISMO 218.145.66.187:25000: así WinDivert también agarra esa conexión y el
        #   oyente anota lo primero que el cliente le dice al server de juego.
        servidores = P.cuerpo_servidores([
            # estado (+0x31) = el SERVICIO de ese server: el cliente lo pone en la cabecera y
            # descarta lo que llegue con otro (`0x744910`). 12 = el del Broker (`00 0c`).
            P.registro_servidor("EDA Local", ip=BROKER_IP, puerto=BROKER_PUERTO, idx=1,
                                estado=12, usuarios=7, maximo=500),
        ])
    # ★ el server de JUEGO (después de ENTER): el cliente manda 0x100F (IP local, MAC, y el md5
    #   del exe en texto) y espera 0x1010 (`0x5496C0`, lee 12 bytes):
    #     u16 resultado (1 = OK; 0x66 / 0x899 / 0x89A = errores) · u32 🟡 (va a +0x2B8, ¿sesión?)
    #     · u32 🟡 · u16 🟡   → con OK manda 0x1001 y cambia de pantalla (`0x4E7350(2)`)
    entrada = struct.pack("<HIIH", 1, 1, 1, 0)
    # ★ SELECT CHARACTER: el cliente manda 0x1011 (u32 1) y espera 0x1012 (`0x544820`):
    #     u16 resultado (1 = OK; 0x65 = error 0x70) · 26 bytes 🟡 de la cuenta (+2..+0x1B)
    #     · u16 N1 (+0x1C) · u16 N2 (+0x1E) · u8 N3 (+0x20)
    #     y después N1×21, N2×36 y N3×186 bytes (🟡 los 186 = un PERSONAJE: 5 lugares)
    #   ★ lo de la cuenta lo copia `0x53EBC0` (cuerpo+2 → estructura+0x2B4), y `0x4FA4E0` habilita
    #     sólo los primeros N lugares, con N = el byte +0x2CB de la estructura = **cuerpo[0x19]**.
    #     Con 0 los lugares no se pueden clickear y «Create» dice «no hay personaje» (El tester).
    #     ✅ cuerpo[0x0F] u32 = CASH y cuerpo[0x13] u32 = GOLD (vistos en pantalla: mandando 1234
    #     y 5678 salió «5678 Gold · 1234 Cash»).
    cuenta = bytearray(struct.pack("<H", 1) + bytes(26) + struct.pack("<HHB", 0, 0, 0))
    struct.pack_into("<I", cuenta, 0x0F, 1234)
    struct.pack_into("<I", cuenta, 0x13, 5678)
    cuenta[0x19] = 5                                     # lugares de personaje habilitados
    # ★ cuerpo[0x17] u16 = las MONEDAS DE REVIVIR (estructura +0x2C9: el «● X0» del HUD, al lado
    #   del nombre). Con 0, al morir no hay menú y el personaje queda tirado (El tester, 10-nov). Lo
    #   leen `0x5008A2` («¿usar moneda?» → manda 0x106A) y el HUD `0x50F5E0` («X%u», texto 6016)
    struct.pack_into("<H", cuenta, 0x17, int(os.environ.get("EDA_MONEDAS", "3")))
    # y «rui» ya creado (N3 = 1 + sus 186 bytes): las reglas no tienen memoria, así que sin esto
    # cada vez que se abre el juego la cuenta vuelve vacía
    cuenta[0x20] = 1
    # 🟡 EDA_EXTRA (para medir): "off:hexa,off:hexa" → esos bytes en el personaje de la cuenta
    extra = {int(k, 16): bytes.fromhex(v) for k, v in
             (x.split(":") for x in os.environ.get("EDA_EXTRA", "").split(",") if x)}
    cuenta = bytes(cuenta) + P.registro_personaje("rui", lugar=0, clase=1, extra=extra)
    assert len(cuenta) == 33 + 186
    # ★ el «estoy vivo»: con el 0x1010 OK el cliente arma un 0x1001 (1 byte, 0x80) y lo manda
    #   CADA 20 s (`0x549770` → `0x744230(0x4E20)`). Sin respuesta, al rato da la conexión por
    #   caída: arma él mismo un 0x1003 (`0x4E55FD`) y sale «conexión inestable» (lo vio el tester).
    #   🟡 Se contesta con el mismo 0x1001 (eco): lo que el server real mandaba no se sabe.
    # ★ CREATE CHARACTER: el cliente manda 0x1013 = u32 🟡 lugar · u16 🟡 clase · nombre UTF-16;
    #   espera 0x1014 (`0x544A40`): u16 resultado (1 = OK; 0x8FD.. = errores) + 1 personaje de
    #   186 bytes. ⚠ el nombre va FIJO acá («rui», el que escribió el tester): las reglas son estáticas.
    #   ⚠ la CLASE va en +0x04 del personaje (desde 1): con 0 el juego muere al dibujar el
    #   modelo (ver `registro_personaje`). ⛔ Probado y descartado: que hiciera falta agregar
    #   campos detrás del personaje (con ellos murió igual, en el mismo lugar).
    creado = struct.pack("<H", 1) + P.registro_personaje("rui", lugar=0, clase=1)
    # ★ ENTER LOBBY: el cliente manda 0x1017 (u32 🟡 + u8 🟡) y espera 0x1018 (`0x544690`):
    #     cabecera de 16: u16 resultado (1 = OK; 0x899 = error 0x0B) · 4 🟡 · u8 (+6) 🟡 el
    #     personaje elegido (→ +0x21C) · u32 N1 (+7) · u16 N2 (+0xB) · 3 🟡 (+0xD)
    #     y después N1×10 y N2×13 bytes. Con OK termina en `0x4E7350(3)`: la pantalla 3.
    #   ⚠ CORREGIDO el 10-nov (mal contado un `push ebx`): la cabecera es u16 resultado · u8
    #     personaje (+2 → +0x21C) · u32 N1 (+3) · u16 N2 (+7) · 7 B (+9 → `0x6103E0`, +0x220)
    lobby = struct.pack("<HBIH7x", 1, 0, 0, 0)
    assert len(lobby) == 16
    # 🟡 EDA_N1 (para medir): "id,id,..." → N1 registros de 10 bytes con ese id de misión
    #   (la clave del mapa es un u32; no se sabe en qué offset, va en +0 y en +4) y 1, 1
    n1 = [int(x) for x in os.environ.get("EDA_N1", "").split(",") if x]
    if n1:
        lobby = struct.pack("<HBIH7x", 1, 0, len(n1), 0) + b"".join(
            struct.pack("<IIBB", 0, m, 1, 1) for m in n1)
    # ★ CREATE STAGE → «Create»: el cliente manda 0x101D (93 B) = u32 🟡 + la SALA serializada
    #   (el objeto entero, con su vtable 0x89A358 adelante): +4 u16 número (0xFFFF = sin número),
    #   +6 título UTF-16, +0x28 u32 escenario (1011), +0x2C..+0x30 bytes 🟡, +0x31 clave UTF-16.
    #   Espera 0x101E (`0x543500`, lee 94 B): u16 resultado (1 = OK; 0x3E9 / 0xA2A / 0xA91 =
    #   errores 7 / 0x135 / 0x137) · u8 (+2) 🟡 · u8 (+3) · u8 (+4) — si +3 == +4 arranca además
    #   lo de UDP (🟡 ser el anfitrión) — · y 89 bytes = la sala desde su +4. Con OK: pantalla 5.
    #   ⚠ los 89 bytes son la sala DESDE SU +0 (con el lugar de la vtable, que se ignora), como el
    #   personaje: la primera versión los ponía desde +4, el escenario quedó corrido 4 bytes y el
    #   cliente murió buscándolo (`0x5367D4`: `0x4EE7D0` devolvió NULL). Medido el 10-nov.
    sala = bytearray(0x59)
    struct.pack_into("<H", sala, 0x04, 1)                 # número de sala
    sala[0x06:0x28] = P.wtexto("EDA vuelve", 34)          # título (de +6 a +0x28)
    struct.pack_into("<I", sala, 0x28, 1011)              # escenario
    sala[0x2F] = 3      # ★ MÁXIMO de jugadores (medido: con 7 la sala dice «7 Players» y dibuja 7
    #                     lugares; con 0 decía «0 Players» y no había ninguno). El jugador local
    #                     se agrega solo, como anfitrión («1LV rui 0 ms» con la casita).
    # 🟡 EDA_SALA (para medir): "off:hexa,..." → esos bytes en la sala (offset del objeto)
    for k, v in (x.split(":") for x in os.environ.get("EDA_SALA", "").split(",") if x):
        b = bytes.fromhex(v)
        sala[int(k, 16):int(k, 16) + len(b)] = b
    sala_ok = struct.pack("<HBBB", 1, 0, 0, 0) + bytes(sala)
    assert len(sala_ok) == 94
    # ★ F9 START GAME: el cliente manda 0x104E (u8 🟡) y espera 0x104F (`0x54F170`, 8 bytes):
    #     u16 🟡 · u32 → +0x53 del personaje (partidas) · u8 🟡 (→ escenarios +0x34) · u8 N
    #     y N × 68: [u8 índice del jugador en la sala][9 × 7 bytes: 🟡 su equipo para la partida]
    #     (`0x61C230` busca el miembro con ese índice). Con eso pasa a la pantalla 8: la PARTIDA.
    arranque = struct.pack("<HIBB", 1, 1, 0, 1) + bytes([0]) + bytes(67)
    assert len(arranque) == 8 + 68
    # ★ LA LARGADA: al terminar de cargar el cliente manda 0x105F (u32 = ms que tardó en cargar)
    #   y se queda en el `while (!this[0xE0]) Sleep(1)` de OnEnterWorld (`0x500643`). Lo
    #   destraba el callback de la escena de carga (`0x510D50`), que durante la carga recibe los
    #   mensajes TCP (el hilo de carga bombea la red: `0x534770`) y sólo actúa con un comando
    #   INTERNO 1: [u8 modo][u32 → this+0xEC] (🟡 el tiempo de la stage); con modo 1 pasa la
    #   pantalla al estado 3. ★ Ese comando 1 NO viaja por la red: lo arma el manejador de
    #   **0x105E «OnPktS2C_Ntf_Play_Start»** (`0x5333D0`, registrado en el mapa de la escena de
    #   carga) con lo que le llega: cuerpo [u16 resultado][u32 valor]; resultado 1 → [1][valor].
    largada = struct.pack("<HI", 1, 600)
    # ★ REVIVIR: al morir el cliente manda 0x1065 (u8 jugador · u32 quién lo mató); con monedas
    #   pregunta «Do you want to use current coin to respawn?» (texto 6010) y con «sí» manda
    #   0x106A (`0x546550(1, 0xFF)`; «no» = (0, 0xFF)). Contesta 0x106B (`0x547680`, 6 B):
    #   u16 1 · u8 modo · u16 monedas que QUEDAN · u8 — modo 1 = revive (estado 4), 0 = se rinde
    #   (estado 0xA), 2 = revivió OTRO jugador (lee además su id).
    revivir = struct.pack("<HBHB", 1, 1, 2, 0)
    #   ★ Pero la pregunta NO sale sola al morir (medido: muerto con 3 monedas, nada): la abre el
    #   server con **0x1068** (`0x546920`: u32 → +0xEC, y llama `0x5037D0`, el cuadro 0x1770
    #   que revisa las monedas). El u32 es 🟡 el tiempo para contestar en ms: con 10 la cuenta
    #   salió ya en 0 y Confirm no respondía; con 15000 Confirm mandó el 0x106A. (Un 0x1066 con
    #   estado 1 o 2 no abre nada.)
    pregunta = struct.pack("<I", 15000)
    # ★ EL FIN: `OnEnd()` del guion → `scenario:SendEvent()` → 0x1064 (u8 jugador). El server
    #   contesta 0x1073 PlayEnd (`0x548AF0`; formato en PROTOCOLO.md §5.13): cabecera de 28 B
    #   (monedas, plata, EXP, nivel, la MISIÓN TERMINADA [u32 · u32 escenario · u8 · u8], y los
    #   contadores de ítems en 0) + u8 M = 0 jugadores. 🟡 los valores de premio son de prueba.
    fin = (struct.pack("<HHIIHB", 1, 2, 5678 + 100, 150, 0, 1) + struct.pack("<IIBB", 0, 1011, 1, 1)
           + bytes([0, 0, 0]) + bytes([0]))
    assert len(fin) == 29
    # ★ DESPUÉS DEL PlayEnd (medido el 10-nov, pantalla por pantalla):
    #   0x106E (`0x546960`, 19 B) → «MISSION COMPLETION RESULT»: u32 🟡 · u16 monstruos muertos ·
    #     u16 golpes recibidos · u16 revividas · u32 tiempo en MS · u32 puntos · u8 rango (1 = D)
    #   0x106F (`0x546A00`, 16 B) → «REWARD CHOICE»: u32 tiempo para elegir (ms) · u32 precio de
    #     las cartas I (4 doradas) · II (6 plateadas) · III (8 de bronce)
    #   clic en una carta → el cliente manda 0x1070 (u8 nivel · u8 carta; `0x5007D0` → `0x546A80`)
    #   0x1071 (`0x546B70`, 11 B): u8 1 · u32 la carta (+1) · u8 jugador (+6) · u32 puntos que
    #     QUEDAN (+7) — medido: «Earned Point» 1500 → 1167
    #   0x1072 (`0x546CA0`): u32 · u8 N · N × 2 → «AWARD RESULTS» (Gold / Exp por jugador + Confirm,
    #     el control 4056 = 0xFD8 que habilitó el 0x1073)
    resultado = struct.pack("<IHHHIIB", 0, 56, 12, 0, 185000, 1500, 1)
    cartas = struct.pack("<IIII", 60000, 333, 222, 111)
    carta = bytes([1, 0, 0, 0, 0, 0, 0]) + struct.pack("<I", 1500 - 333)
    premios = struct.pack("<IB", 0, 0)
    # ★ SALIR de la stage (ESC → «quit the stage?» → Confirm, el control 7000 → `0x546E70`):
    #   el cliente manda 0x1074 (u8 jugador). 0x1075 (`0x546F40`, 16 B): u16 1 · u16 monedas ·
    #   u32 (+0x57 del personaje) · u8 nivel · u32 EXP · u16 (+0x6C) · u8 N × 10 B → pantalla 3,
    #   el LOBBY. (Mandado estando en AWARD RESULTS, el juego se cayó en `0x752B7E`.)
    salida = struct.pack("<HHIBIHB", 1, 3, 1, 1, 150, 0, 0)
    return {
        "1064": ["1073:" + fin.hex(), "106e:" + resultado.hex(), "106f:" + cartas.hex()],
        "1070": ["1071:" + carta.hex(), "1072:" + premios.hex()],
        "1074": ["1075:" + salida.hex()],
        "1065": ["1068:" + pregunta.hex()],
        "106a": ["106b:" + revivir.hex()],
        "105f": ["105e:" + largada.hex()],
        "104e": ["104f:" + arranque.hex()],
        "101d": ["101e:" + sala_ok.hex()],
        "1017": ["1018:" + lobby.hex()],
        "1013": ["1014:" + creado.hex()],
        "1001": ["1001:80"],
        "1011": ["1012:" + cuenta.hex()],
        "0604": ["0607:" + nat_init.hex(), "0609:" + nat_tipo.hex()],
        "0708": ["0709:" + anuncio.hex()],
        "070a": ["070b:" + servidores.hex()],
        "100f": ["1010:" + entrada.hex()],
    }


def main():
    g = guion(vacio=sys.argv[1:2] == ["vacio"])
    os.makedirs(os.path.dirname(REGLAS), exist_ok=True)
    json.dump(g, open(REGLAS, "w", encoding="utf-8"), indent=1)
    for k, v in g.items():
        print("  cuando llega %s  →  %s" % (k, ", ".join(
            "%s (%d bytes)" % (r.split(":")[0], len(r.split(":")[1]) // 2) for r in v)))
    print("  -> %s" % REGLAS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
