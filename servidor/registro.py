r"""servidor/registro.py -- qué función atiende cada mensaje del cliente.

Cada módulo de `servidor/` marca sus funciones con `@maneja(0x103F)`. La firma es siempre
`(cmd, cuerpo, conexion, c, p)`: el comando, el cuerpo (sin la cabecera), el número de conexión, la
CUENTA (`cuentas.leer`) y la PARTIDA de esa conexión (`estado.partida`). Devuelve una lista de
`(comando, cuerpo, milisegundos de espera[, conexión destino])`, o None = «no sé» (contestan las
reglas fijas de `herramientas/reglas_broker.py`).
"""
MANEJADORES = {}


def maneja(*comandos):
    def poner(f):
        for c in comandos:
            assert c not in MANEJADORES, "0x%04X ya lo atiende %s" % (c, MANEJADORES[c].__name__)
            MANEJADORES[c] = f
        return f
    return poner
