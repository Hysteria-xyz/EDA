r"""servidor/datos.py -- las TABLAS del juego: escenarios, precios de la tienda, habilidades,
premios de cada stage y tipos de ítem.

Las que salen de los XML de `Data.dat` (`<EDA_DATOS>/*.xml`) devuelven {} si falta el archivo:
el server anda igual, pero esa parte (la tienda, por ejemplo) queda vacía.
"""
import re

from servidor import config


# ★ De los XML de cada escenario (`Data\Scenario\<dificultad>\Chapter1_N_X.xml`, volcados):
#   <INFO RANK_POINT KILL_POINT TOTALEXP MONSTER_CNT>. Y <RANKRATE S="0.8" A="0.6" B="0.4" C="0.2"
#   D="0.1"/> (el mismo en todos los vistos).
ESCENARIOS = {1011: (29, 120, 128, 56), 1012: (38, 168, 179, 78), 1013: (48, 240, 256, 78),
              1021: (42, 173, 184, 92)}


RANKRATE = (0.8, 0.6, 0.4, 0.2, 0.1)                       # S A B C D


# ★ De un VIDEO de la beta (capturas de el tester, 10-nov): REWARD CHOICE con las cartas a 350 / 150 /
#   50, y un resultado de la 1-1 con los 56 monstruos muertos = 257 puntos, rango S. 🟡 La fórmula
#   de los puntos no se sabe: acá, proporcional a TOTALEXP, calibrada para que 1011 completa = 257.
PRECIOS = (350, 150, 50)


def puntos_de(totalexp, frac):
    return int(round(totalexp * frac * 257 / 128.0))


def productos():
    """★ La TIENDA: `Data\\Product.xml` (sacado con `herramientas/sacar_xml.py SHOP Product`).
    {ID de producto: (oro, cash, [(tipo de ítem, cantidad)])}. Sin el archivo, la tienda no
    vende (vacío)."""
    try:
        x = open(config.PRODUCTOS_XML, "rb").read()
    except OSError:
        return {}
    r = {}
    for a, cuerpo in re.findall(rb"<Product ([^>]*)>(.*?)</Product>", x, re.S):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', a))
        r[int(v[b"ID"])] = (int(v[b"SellGold"]), int(v[b"SellCash"]),
                            [(int(t), int(n)) for t, n in
                             re.findall(rb'RefID="(\d+)" Count="(\d+)"', cuerpo)])
    return r


def precios_venta():
    """{tipo de ítem: oro que da la tienda} — `<BUYS><BuyItem RefID BuyGold/>` de Product.xml."""
    try:
        x = open(config.PRODUCTOS_XML, "rb").read()
    except OSError:
        return {}
    return {int(t): int(g) for t, g in re.findall(rb'<BuyItem RefID="(\d+)" BuyGold="(\d+)"', x)}


def tabla_habilidades():
    """★ `Data\\Skill.xml` (`sacar_xml.py SKILLXML Skill`): {tipo del ítem-libro (REFID): (1 activa
    / 2 pasiva, ID, CLASS (65535 = todas), COST_GOLD, ACQUIRE_LEVEL)}."""
    try:
        x = open(config.HABILIDADES_XML, "rb").read()
    except OSError:
        return {}
    r = {}
    for clase_xml, a in re.findall(rb"<(ACTIVE|PASSIVE)_SKILL ([^>]*)>", x):
        v = dict(re.findall(rb'(\w+)="([^"]*)"', a))
        r[int(v[b"REFID"])] = (1 if clase_xml == b"ACTIVE" else 2, int(v[b"ID"]),
                               int(v[b"CLASS"]), int(v[b"COST_GOLD"]), int(v[b"ACQUIRE_LEVEL"]))
    return r


NADA = 40071                                                 # el ítem «None» (NameAndExplainString)


def tabla_premios():
    """★ `Data\\StageReward.xml` (`sacar_xml.py STAGE_REWARDS StageReward`): {escenario:
    (GiveCount, [(Type, Data, Count)])}. Type 2 = ítem (Data = tipo); Type 0 = 🟡 oro (Data)."""
    try:
        x = open(config.PREMIOS_XML, "rb").read()
    except OSError:
        return {}
    return {int(i): (int(g), [tuple(map(int, t)) for t in re.findall(
                rb'Type="(\d+)" Data="(\d+)" Count="(\d+)"', cuerpo)])
            for i, g, cuerpo in re.findall(
                rb'<REWARD Present_Index="(\d+)" GiveCount="(\d+)">(.*?)</REWARD>', x, re.S)}


def tipos_item():
    """{tipo: (MAXSOLID, REPAIRGOLD)} de `ItemTypeList.xml` (`sacar_xml.py ITEMTYPELIST ItemTypeList`)."""
    try:
        x = open(config.TIPOS_XML, "rb").read()
    except OSError:
        return {}
    return {int(i): (int(m), int(g)) for i, m, g in re.findall(
        rb'<ITEMTYPE ID="(\d+)"[^>]*?MAXSOLID="(\d+)" REPAIRGOLD="(\d+)"', x)}
