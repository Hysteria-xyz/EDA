# servidor/ — el server de juego de EDA, por módulos

Cada archivo es **una parte del juego**. Un mensaje del cliente llega a `juego.responder()`, que se
lo pasa a la función registrada para ese comando con `@maneja(0x....)` (`registro.py`).

| archivo | qué tiene | mensajes que atiende |
|---|---|---|
| `juego.py` | ★ la entrada: `responder`, `tick` (cada segundo), `cerrada` | — |
| `red.py` | ★ el server por la red (Linux / Docker / Windows) | todos (los pasa a `juego.py`) |
| `config.py` | dónde se guarda cada cosa y los puertos (variables `EDA_*`) | — |
| `estado.py` | lo que se recuerda mientras anda: partidas, salas, quién es quién | — |
| `registro.py` | `@maneja`: qué función atiende cada comando | — |
| `cuentas.py` | leer y guardar la cuenta, la EXP y el nivel | — |
| `datos.py` | las tablas del juego (escenarios, `Product.xml`, `Skill.xml`…) | — |
| `objetos.py` | los BYTES de lo que tiene un jugador: ítems, fichas, equipo, personaje | — |
| `relay.py` | el modo relay (jugadores en PCs distintas) | — |
| `entrada.py` | entrar al server de juego | `100F` quién soy · `1011` elegir personaje |
| `salas.py` | lobby y salas | `1017` lobby · `101D` crear · `101F` entrar · `1047` listo · `104E` largar · `100D` chat · `1023` `1027` `104C` pantallas |
| `inventario.py` | equipar, la barra de pociones, repartir estadísticas | `102B` `102D` |
| `tienda.py` | comprar y vender | `103F` `1041` |
| `habilidades.py` | verificar el libro, aprender, borrar | `103B` `103D` `1043` |
| `refineria.py` | engarces, piedras, refinar, reparar | `1037` `1033` `1035` `1039` |
| `partida.py` | la stage: cargar, morir, revivir, el final, cartas, premio | `105F` `1061` `1063` `1065` `106A` `1064` `1070` `1074` `1001` |
| `pruebas.py` | ★ las pruebas (`py servidor\juego.py control`) | — |

Lo que el server todavía no contesta lo cuenta `py herramientas\contar_piezas.py` (ver el README).

## Las tres reglas del código

1. **Una función por mensaje**, con `@maneja`. Firma: `(cmd, cuerpo, conexion, c, p)`, donde `c`
   es la cuenta y `p` la partida de esa conexión. Devuelve una lista de
   `(comando, cuerpo, ms de espera[, conexión destino])`, o `None` si no sabe.
2. **La configuración se lee como `config.X`** (nunca `from servidor.config import X`): las pruebas
   la cambian en caliente.
3. **El estado vivo va en `estado.py`.** El server recarga `servidor/` cuando cambia un archivo,
   sin reiniciarse, y lo de `estado.py` sobrevive a la recarga.

## Probar

```bat
py servidor\juego.py control         :: las pruebas, sin el juego
py -m servidor.red                   :: el server por la red (puerto 25900)
py -m servidor.red prueba 127.0.0.1:25900   :: ¿contesta?
```

Sin los XML del juego (`_trabajo\datos\`), las pruebas que los necesitan se saltan; con
`EDA_EXIGIR_DATOS=1` cuentan como falla.
