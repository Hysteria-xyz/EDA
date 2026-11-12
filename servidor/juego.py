r"""servidor/juego.py -- la ENTRADA del server de juego: a quién le toca cada mensaje.

Para cada mensaje del cliente, `responder(comando, cuerpo, conexion)` busca la función registrada
(`servidor/registro.py`) y devuelve lo que ella diga:
    · una lista de (comando, cuerpo, milisegundos de espera[, conexión destino]) → eso se contesta;
    · None → «no sé»: contestan las reglas fijas de `herramientas/reglas_broker.py`.
`tick` (cada segundo) y `cerrada` (se cortó una conexión) completan lo que el server necesita.

Quién atiende qué (los formatos de cada mensaje, en `documentacion/PROTOCOLO.md`):
    entrada.py      0x100F quién soy · 0x1011 elegir personaje
    salas.py        el lobby, las salas, el chat, listo / largar
    inventario.py   0x102B / 0x102D (equipar, repartir estadísticas)
    tienda.py       comprar / vender
    habilidades.py  verificar el libro / aprender / borrar
    refineria.py    engarces, piedras, reparar
    partida.py      cargar, morir y revivir, el final, las cartas, el premio
    pruebas.py      ★ `control()`: todo lo de arriba sin el juego, cada prueba con su revés

    py servidor\juego.py control                     # ★ las pruebas (sin el juego)
    py servidor\juego.py estado                      # muestra las cuentas
    py servidor\juego.py preparar <nombre> <1|2> <nivel>   # una cuenta de prueba
"""
import argparse
import json
import os
import re
import sys
import time

if __package__ in (None, ""):                              # `py servidor\juego.py …`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servidor import config                                  # noqa: E402
from servidor.estado import ASIGNADAS, PARTIDAS, SALAS, VIVO, partida   # noqa: E402
from servidor.cuentas import NOMBRES, leer, ruta_cuenta, nivel, EXPS, INICIO, guardar   # noqa: E402
from servidor.salas import avisar_lista, avisar_usuarios     # noqa: E402
from servidor.partida import cuerpo_1072, game_over          # noqa: E402
from servidor.registro import MANEJADORES                    # noqa: E402
# los módulos que REGISTRAN manejadores (importarlos es lo que los anota)
from servidor import entrada, inventario, tienda, habilidades, refineria   # noqa: E402,F401


def responder(cmd, cuerpo, conexion):
    if cmd < 0x1000:                                        # el Broker: no es de una cuenta
        return None
    # (la cuenta y la partida se piden SIEMPRE, aunque nadie atienda el comando: así la conexión
    #   queda con su cuenta desde el primer mensaje, como antes de partir el server en módulos)
    # ★ con login (config.LOGIN == "pase"), hasta que el 0x100F no trae un ticket válido, nada más
    #   se atiende: ni las reglas fijas (por eso [] y no None)
    if config.LOGIN == "pase" and cmd != 0x100F and conexion not in ASIGNADAS:
        return []
    c = leer(conexion)
    p = partida(conexion)
    f = MANEJADORES.get(cmd)
    return f(cmd, cuerpo, conexion, c, p) if f else None


def tick(conexiones):
    """Cada segundo (lo llama el espía): lo que el server tiene que decir por TIEMPO."""
    r = []
    forzar = os.path.join(config.ESTADO, "forzar_lista")   # (para probar a mano)
    if os.path.exists(forzar):
        os.remove(forzar)
        VIVO.LISTA_CAMBIO = True
    if getattr(VIVO, "LISTA_CAMBIO", False):
        VIVO.LISTA_CAMBIO = False
        r += avisar_lista() + avisar_usuarios()
    for n in conexiones:
        p = PARTIDAS.get(n)
        if p and p.get("game_over_en") and time.time() >= p["game_over_en"]:
            r += game_over(leer(n), p, n)
        # ★ vencido el tiempo de las cartas sin elegir (p. ej. con 0 puntos no se puede elegir
        #   ninguna: medido 19:22, el reloj llega a 0 y la pantalla se queda) → AWARD RESULTS
        if p and p.get("cartas_hasta") and time.time() >= p["cartas_hasta"]:
            p["cartas_hasta"] = None
            r.append((0x1072, cuerpo_1072(n, p), 0, n))
    return r


def cerrada(conexion):
    """El espía avisa que la conexión se cerró: olvidar su partida, su sala y soltar su cuenta.
    (Sin forma de devolver mensajes acá: la lista nueva sale con el próximo `tick`.)"""
    PARTIDAS.pop(conexion, None)
    ASIGNADAS.pop(conexion, None)
    viejas = [k for k, v in SALAS.items() if v["anfitrion"] == conexion]
    for k in viejas:
        del SALAS[k]
    VIVO.LISTA_CAMBIO = True                               # salas y usuarios: uno menos


from servidor.objetos import inventario, libre_en_bolsa, serial_nuevo
from servidor.datos import NADA, tabla_habilidades

def ajustar_pruebas(argv):
    parser = argparse.ArgumentParser(description="Ajusta una cuenta local de pruebas con el juego cerrado.")
    parser.add_argument("nombre", choices=NOMBRES)
    parser.add_argument("--nivel", type=int)
    parser.add_argument("--oro", type=int)
    parser.add_argument("--cash", type=int)
    parser.add_argument("--nick")
    args = parser.parse_args(argv)
    cambios = {}
    if args.nick is not None:
        if not re.fullmatch(r"[A-Za-z0-9_]{1,12}", args.nick):
            parser.error("el nick admite 1 a 12 letras ASCII, números o guiones bajos")
        cambios["nick"] = args.nick
    if args.nivel is not None:
        if not 1 <= args.nivel <= len(EXPS):
            parser.error("el nivel debe estar entre 1 y %d" % len(EXPS))
        cambios["exp"] = EXPS[args.nivel - 1]
    for campo, valor in (("plata", args.oro), ("cash", args.cash)):
        if valor is not None:
            if not 0 <= valor <= 0xFFFFFFFF:
                parser.error("el oro y el cash deben estar entre 0 y 4294967295")
            cambios[campo] = valor
    if not cambios:
        parser.error("indica --nivel, --oro, --cash o --nick")
    ruta = ruta_cuenta(args.nombre)
    if args.nombre == "rui" and not os.path.exists(ruta) and os.path.exists(config.CUENTA):
        ruta = config.CUENTA
    try:
        with open(ruta, encoding="utf-8") as archivo:
            cuenta = json.load(archivo)
    except FileNotFoundError:
        parser.error("la cuenta aún no existe; entra al juego una vez para crearla")
    except (OSError, ValueError) as exc:
        parser.error("no se pudo leer la cuenta: %s" % exc)
    cuenta.update(cambios, nombre=args.nombre)
    guardar(cuenta)
    print("%s: nivel %d, oro %d, cash %d" % (
        args.nombre, nivel(cuenta.get("exp", INICIO["exp"])),
        cuenta.get("plata", INICIO["plata"]), cuenta.get("cash", INICIO["cash"])))


def menu_items():
    import xml.etree.ElementTree as ET

    ruta = os.path.join(config.DATOS, "ItemTypeList.xml")
    try:
        catalogo = ET.parse(ruta).getroot()
    except (OSError, ET.ParseError) as exc:
        print("No se pudo abrir el catálogo de EDA: %s" % exc)
        return
    grupos = {"1": ("EQUIP_ITEM", "Equipo"), "2": ("POTION", "Pociones"),
              "3": ("SOULSTONE", "Piedras de alma"), "4": ("SKILLBOOK", "Libros de habilidad"),
              "5": ("ETC", "Pergaminos y otros")}
    print(" | ".join("%s. %s" % (i, nombre) for i, (_, nombre) in grupos.items()))
    grupo = grupos.get(input("Categoría (Enter para volver): ").strip())
    if grupo is None:
        return
    items = [x for x in catalogo.findall(grupo[0] + "/ITEMTYPE") if int(x.attrib["ID"]) != NADA]
    habilidades = tabla_habilidades() if grupo[0] == "SKILLBOOK" else {}
    equipo = {0: ("⚔", "Arma principal"), 1: ("⚔", "Arma secundaria"),
              3: ("◉", "Máscara"), 4: ("▣", "Peto"), 5: ("▣", "Pantalones"),
              6: ("▣", "Guantes"), 7: ("▣", "Cinturón"), 8: ("▣", "Botas")}
    categorias = {"POTION": ("🧪", "Poción"), "SOULSTONE": ("💎", "Piedra de alma"),
                  "SKILLBOOK": ("📕", "Libro de habilidad"), "ETC": ("◇", "Objeto")}
    nombres = {1: "Basic Long Sword", 32001: "Libro de Dash", 40051: "Skill Check Scroll"}
    atributos = {"N_ATCK": "Ataque cuerpo a cuerpo", "N_DEF": "Defensa cuerpo a cuerpo",
                 "F_ATCK": "Ataque a distancia", "F_DEF": "Defensa a distancia",
                 "INC_HP": "Vida", "INC_MP": "Maná"}
    for i, item in enumerate(items, 1):
        a = item.attrib
        tipo = int(a["ID"])
        icono, familia = (equipo.get(tipo // 1000, ("▣", "Equipo")) if grupo[0] == "EQUIP_ITEM"
                          else categorias[grupo[0]])
        if tipo == 40051:
            icono = "📜"
        nombre = nombres.get(tipo, familia)
        detalle = item.find("DETAIL")
        desc = "grado %s, nivel %s, clase %s" % (
            a["GRADE"], a["LEVEL_RESTRICT"], {"1": "Warrior", "2": "Hunter", "65535": "todas"}.get(
                a["USECLASS"], a["USECLASS"]))
        if tipo == 40051:
            desc = "Identifica un libro de habilidad antes de aprenderlo."
        elif tipo in habilidades:
            activa, ident, _, oro, nivel_min = habilidades[tipo]
            desc = "habilidad %d (%s), nivel %d, %d oro para aprender" % (
                ident, "activa" if activa == 1 else "pasiva", nivel_min, oro)
        elif detalle is not None:
            stats = [f"{nombre_stat} {detalle.get(k)}" for k, nombre_stat in atributos.items()
                     if detalle.get(k) not in (None, "0")]
            if stats:
                desc += " | " + ", ".join(stats)
        if grupo[0] == "POTION":
            desc += " | consumible para la barra 1–6"
        elif grupo[0] == "SOULSTONE":
            desc += " | se inserta en un engarce del equipo"
        print("%3d. %s %s [ID %d] — %s" % (i, icono, nombre, tipo, desc))
    try:
        opcion = int(input("Número de la lista (0 para volver): "))
        if opcion == 0:
            return
        if not 1 <= opcion <= len(items):
            raise ValueError
        item = items[opcion - 1]
        tipo = int(item.attrib["ID"])
        limite = min(255, max(1, int(item.attrib["MAXOVERLAPCNT"])))
        cantidad = int(input("Cantidad por casilla (1–%d, Enter = 1): " % limite) or "1")
        if not 1 <= cantidad <= limite:
            raise ValueError
    except ValueError:
        print("Selección o cantidad fuera de rango.")
        return
    if not os.path.exists(ruta_cuenta("rui")) and not os.path.exists(config.CUENTA):
        print("Entra al juego con rui una vez para crear la cuenta.")
        return
    cuenta = leer()
    inv = inventario(cuenta)
    try:
        casilla = libre_en_bolsa(inv)
    except StopIteration:
        print("La bolsa está llena.")
        return
    inv.append([tipo, cantidad, casilla, serial_nuevo(inv), int(grupo[0] != "SKILLBOOK")])
    cuenta["items"] = inv
    guardar(cuenta)
    print("Agregado a la bolsa de rui: ID %d × %d." % (tipo, cantidad))


def menu_equipar_pocion():
    if not os.path.exists(ruta_cuenta("rui")) and not os.path.exists(config.CUENTA):
        print("Entra al juego una vez para crear tu cuenta.")
        return
    cuenta = leer()
    inv = inventario(cuenta)
    tipos = {26001: "HP I", 26002: "HP II", 26003: "HP III",
             26101: "MP I", 26102: "MP II", 26103: "MP III"}
    bolsa = [it for it in inv if it[0] in tipos and it[2] >= 18 and it[1] > 0]
    for tecla in range(1, 7):
        it = next((it for it in inv if it[2] == tecla + 11), None)
        nombre = tipos.get(it[0], "Otro objeto") if it else "Libre"
        print("Tecla %d: %s%s" % (tecla, nombre, (" × %d" % it[1]) if it else ""))
    if not bolsa:
        print("No tienes pociones en la bolsa.")
        return
    for i, it in enumerate(bolsa, 1):
        print("%d. Poción %s × %d" % (i, tipos[it[0]], it[1]))
    try:
        seleccion = int(input("Poción de la lista (0 para volver): "))
        if seleccion == 0:
            return
        if not 1 <= seleccion <= len(bolsa):
            raise ValueError
        tecla = int(input("Tecla 1–6 (0 para volver): "))
        if tecla == 0:
            return
        if not 1 <= tecla <= 6:
            raise ValueError
    except ValueError:
        print("Selección fuera de rango.")
        return
    it = bolsa[seleccion - 1]
    destino = tecla + 11
    anterior = next((x for x in inv if x[2] == destino), None)
    if anterior is not None:
        anterior[2] = it[2]
    it[2] = destino
    cuenta["items"] = inv
    guardar(cuenta)
    print("Poción %s asignada a la tecla %d." % (tipos[it[0]], tecla))


def menu_ajustes():
    print("Cierra EDA antes de cambiar tu cuenta local.")
    opciones = {"1": "nivel", "2": "oro", "3": "cash", "4": "nick"}
    while True:
        print("\nCuenta rui | 1. Nivel | 2. Oro | 3. Cash | 4. Nick | 5. Agregar items | 6. Equipar pociones | 0. Salir")
        opcion = input("Opción: ").strip()
        if opcion == "0":
            return
        if opcion == "5":
            menu_items()
            continue
        if opcion == "6":
            menu_equipar_pocion()
            continue
        campo = opciones.get(opcion)
        if campo is None:
            print("Selecciona una opción del menú.")
            continue
        valor = input("Nuevo %s (Enter para cancelar): " % campo).strip()
        if valor:
            try:
                ajustar_pruebas(["rui", "--" + campo + "=" + valor])
            except SystemExit:
                pass


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                         # noqa: BLE001
        pass
    from servidor import pruebas
    if sys.argv[1:2] == ["preparar"]:
        # py servidor\juego.py preparar <nombre> <1 Warrior | 2 Hunter> <nivel>
        cc = pruebas.preparar(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
        print("%s: clase %d, nivel %d, %d ítems, %d habilidades (atajos %s)" % (
            cc["nombre"], cc["clase"], nivel(cc["exp"]), len(cc["items"]), len(cc["habilidades"]),
            [h[2] for h in cc["habilidades"] if h[4]]))
    elif sys.argv[1:2] == ["menu-ajustes"]:
        menu_ajustes()
    elif sys.argv[1:2] == ["ajustar"]:
        ajustar_pruebas(sys.argv[2:])
    elif sys.argv[1:2] == ["estado"]:
        for nombre in NOMBRES:
            if os.path.exists(ruta_cuenta(nombre)) or nombre == "rui":
                print(json.dumps(dict(leer(None) if nombre == "rui" else
                                      json.load(open(ruta_cuenta(nombre), encoding="utf-8"))),
                                 indent=1, ensure_ascii=False))
    else:
        sys.exit(pruebas.control())
