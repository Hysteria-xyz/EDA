# Contribuir

Gracias por querer ayudar a revivir EDA. Lo más útil es **medir** algo que el server todavía no
hace: falta un mensaje, un valor es inventado (🟡), una pantalla se queda esperando. Si no
programás, también sirve un issue con una foto y lo que dice la consola.

## Las ramas y los servers

```
  tu rama  ──PR──▶  develop  ──(cuando anduvo bien)──▶  main
                       │                                   │
                       ▼                                   ▼
               server de PRUEBA                      server de PROD
               (puerto 35900, se                     (puerto 25900, se
                actualiza solo)                       actualiza a mano)
```

- **`main`** es lo estable, y es lo que corre el server de **prod**. Nadie empuja directo a `main`.
- **`develop`** es lo próximo, y es lo que corre el server de **prueba**, que se actualiza solo
  a los 5 minutos de cada cambio. Ahí se prueba jugando: `py jugar.py --server IP:35900`.
- **Tu trabajo** va en una rama tuya (`tienda-cash`, `fix-sala-llena`…), con un **PR a `develop`**.
- Cada tanto, cuando `develop` anduvo bien en prueba, un mantenedor abre el PR `develop → main` y
  actualiza prod.

## Paso a paso (con un fork)

1. **Fork** del repo en GitHub (botón *Fork*) y clonalo.
2. Una rama desde `develop`:

   ```bash
   git checkout develop
   git checkout -b mi-cambio
   ```

3. Cambiá lo que haga falta, y **corré las pruebas**:

   ```bash
   py servidor\juego.py control
   ```

   Tiene que terminar en «→ TODO BIEN». Si agregás algo, agregá su prueba, **con su caso al revés**
   (ver abajo).
4. Probalo **jugando**, si podés: `py jugar.py` (server local) o contra el server de prueba.
5. `git push` a tu fork y abrí el **PR contra `develop`** (no contra `main`).
6. GitHub corre las pruebas solo. Con todo en verde y una revisión, se fusiona. A los 5 minutos
   está en el server de prueba.

## Dónde va cada cosa

El server está partido por pantallas del juego: [servidor/LEEME.md](servidor/LEEME.md). Para
atender un mensaje nuevo:

```python
# servidor/tienda.py (por ejemplo)
from servidor.registro import maneja

@maneja(0x1029)                       # el comando que manda el cliente
def comprar_con_cash(cmd, cuerpo, conexion, c, p):
    """Qué es, y DÓNDE se midió (la dirección del manejador en el exe, la corrida de MEDICIONES)."""
    if len(cuerpo) < 8:
        return None                   # None = «no sé» (contestan las reglas fijas)
    ...
    guardar(c)                        # c = la cuenta (se guarda en disco)
    return [(0x102A, respuesta, 0)]   # (comando, cuerpo, milisegundos de espera[, otra conexión])
```

Los formatos de cada mensaje están en [documentacion/PROTOCOLO.md](documentacion/PROTOCOLO.md).

## Las reglas del proyecto

Son las que hicieron que esto funcione. Están explicadas en [LEEME.md](LEEME.md#reglas-con-las-que-se-trabajó).

- **Medir antes que deducir.** Si un campo es una suposición, se marca 🟡 en el código.
- **Toda prueba lleva su control al revés**: el caso que TIENE que fallar (sin oro no compra, una
  clave falsa no abre). Una prueba que nunca puede fallar no prueba nada.
- **Lo esperado sale del generador** (los XML del juego, las tablas), no se copia a mano.
- ⛔ **Nada del cliente de Softnyx entra al repo**: ni `Data.dat`, ni los XML, ni capturas de
  pantalla del juego. El único binario es `exe/EDA_limpio.exe` (ver [AVISO-LEGAL.md](AVISO-LEGAL.md)).
- ⛔ **Nada de datos personales**: ni tu IP, ni tu MAC, ni rutas con tu usuario de Windows en el
  código o en los documentos.

## Para los mantenedores

- `main` y `develop` protegidas en GitHub (*Settings → Branches*): sólo por PR, con las pruebas en verde.
- `develop` como rama por defecto, así los PR apuntan ahí solos.
- Pasar a prod: PR `develop → main`, fusionar, y en el VPS
  `bash /opt/eda/prod/despliegue/actualizar.sh prod` (ver [despliegue/LEEME.md](despliegue/LEEME.md)).
