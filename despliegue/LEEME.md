# El server en Linux (VPS) — Docker, prod y prueba

El **juego** corre sólo en Windows (es de 2009). El **server** es Python puro y corre en cualquier
lado: acá se lo monta en un VPS Linux con Docker, con dos copias:

| entorno | rama | puerto TCP | relay UDP | se actualiza |
|---|---|---|---|---|
| **prod** | `main` | 25900 | 26000–26200 | **solo**, a los 5 min de cada fusión en `main` (1 aprobación): respaldo de las cuentas antes (`/opt/eda/respaldos/`) y vuelta atrás si no contesta |
| **prueba** | `develop` | 35900 | 36000–36200 | **solo**, a los 5 min de cada cambio en `develop` |

Los jugadores entran con `py jugar.py --server IP:25900` (o `:35900` para probar lo nuevo).

---

## ¿Docker o Kubernetes?

**Docker (con `docker compose`), y Kubernetes no.**

Lo que se busca es poder **mudar el server a otro VPS sin sufrir**. Eso lo da Docker solo: la
imagen trae Python, la librería de cifrado y el código, así que el VPS nuevo sólo necesita Docker.
Lo único que hay que llevar son **las cuentas**, que viven en una carpeta afuera del contenedor
(`/opt/eda/estado-*`).

Kubernetes sirve cuando hay **muchas máquinas** y muchos servicios que escalar, reiniciar y
balancear entre ellas. Acá hay **un proceso en un VPS**, y además este server no se puede partir
en varias copias:
- guarda el estado de las salas y partidas en memoria;
- el relay UDP abre un puerto por jugador en esa máquina;
- un balanceador separaría a jugadores de la misma sala.

Kubernetes sumaría un clúster que administrar (etcd, ingress, volúmenes persistentes, y UDP en
cientos de puertos, que es justo lo que peor maneja) sin resolver nada que haga falta hoy.

**Cuándo replantearlo:** si algún día hay varios servers de juego (uno por región, por ejemplo).
Ni así haría falta Kubernetes: alcanza con un VPS por región, cada uno con este mismo
`docker compose`.

---

## Instalar en un VPS nuevo

Ubuntu o Debian, como root. Con 1 núcleo y 1 GB alcanza.

```bash
curl -fsSL https://raw.githubusercontent.com/r2beatlatino/EDA/main/despliegue/instalar.sh | bash
```

Eso deja todo armado:
- instala Docker;
- clona el repo dos veces (`/opt/eda/prod` en `main`, `/opt/eda/prueba` en `develop`);
- escribe `/opt/eda/prod.env` y `/opt/eda/prueba.env` con la IP pública del VPS;
- arranca los dos contenedores (`eda-prod`, `eda-prueba`) y prueba que contesten;
- deja un cron que actualiza el de prueba.

No hay que copiar nada más: las tablas del juego que lee el server (precios, habilidades,
premios) vienen en el repo, en [`datos/`](../datos/LEEME.md), y entran en la imagen.

**Firewall:** si el proveedor del VPS tiene uno (o usás `ufw`), abrí TCP **25900** y **35900** y
UDP **26000–26200** y **36000–36200**.

## El día a día

```bash
docker ps                                       # ¿están andando? (eda-prod, eda-prueba)
docker logs -f eda-prod                         # qué pasa (cada conexión y cada mensaje)
bash /opt/eda/prod/despliegue/actualizar.sh prod     # pasar prod a lo último de main
cat /opt/eda/actualizaciones.log                # qué se actualizó y cuándo
docker exec eda-prod python servidor/juego.py estado  # las cuentas
```

`actualizar.sh` arma la imagen nueva **y antes corre las pruebas del server**. Si fallan, no
reemplaza nada: el contenedor que andaba sigue andando. Un PR roto en `develop` no tira el server
de prueba.

## Los registros del server de prueba, para quien investiga una falla

Quien trabaja en `develop` necesita ver qué hizo el server de prueba en una partida (los mensajes, el
relay, las direcciones del P2P) sin tener la entrada al VPS, donde también está prod. Para eso hay una
llave de SSH que **sólo baja un paquete de registros** del server de prueba:

```sh
sh diagnostico-instalar.sh "ssh-ed25519 AAAA… nombre"   # en el VPS, como root: la llave PÚBLICA de quien va a leer
sh diagnostico-instalar.sh quitar "nombre"              # anularla
```

Y quien tiene la llave privada, desde su PC (en Windows, con `cmd /c "…"`: el `>` de PowerShell rompe el archivo):

```sh
ssh -i LLAVE eda-diag@SERVER 24 > diagnostico.tgz       # 24 = horas hacia atrás (1 a 168)
```

Trae el registro del server (`server.log`), `relay.log`, `punch.json`, `nat.json`, `relay.json` y un
`LEEME.txt` con el commit que corre y la configuración del P2P (sólo una lista fija de variables: ninguna
clave). La llave entra como el usuario `eda-diag` con `restrict` y una orden forzada: no da terminal, ni
túneles, ni otro comando, y lo que arma el paquete ([`diagnostico.sh`](diagnostico.sh)) sólo lee, y sólo
lo del server de prueba. ⚠ Los registros traen las IP de quienes probaron: no van a un PR ni a un issue.

## Mudarse a otro VPS

1. En el VPS **nuevo**: el `curl … instalar.sh | bash` de arriba.
2. Copiar las cuentas del viejo al nuevo:

   ```bash
   rsync -a root@VPS_VIEJO:/opt/eda/{estado-prod,estado-prueba} /opt/eda/
   ```

3. En el nuevo, rearmar los dos entornos:

   ```bash
   bash /opt/eda/prod/despliegue/actualizar.sh prod --forzar && bash /opt/eda/prod/despliegue/actualizar.sh prueba --forzar
   ```

4. Avisar la IP nueva (`--server IP_NUEVA:25900`) y apagar el viejo: `docker compose -p eda-prod down`.

Son dos carpetas: nada más guarda estado. (Con las cuentas en SQLite, ver abajo, va a ser **un
archivo** por entorno.)

## Sin Docker

Con Python 3.10+ y `pip install pycryptodome`:

```bash
EDA_RELAY_IP=<IP pública> python -m servidor.red
```

Las variables (puertos, carpetas) están explicadas al principio de `servidor/red.py` y de
`servidor/config.py`.

Para probar que contesta, desde cualquier PC con el repo:

```bash
python -m servidor.red prueba IP:25900
```

Le manda el primer mensaje del juego y espera la respuesta; con una clave falsa, tiene que quedarse
callado.

## Lo que todavía no está

### Las cuentas y el login

**El login ya está del lado de este server** (MEDICIONES §45, `servidor/porteria.py`); se prende con
`EDA_LOGIN=pase`. Sin eso (`abierto`, el de siempre) cada conexión toma la primera cuenta libre de
`rui`, `kai`, `mio` y `ren`: sirve para probar.

Cómo entra un jugador con login:

1. El **launcher de R2Beat** entra al **portero** de R2Beat, que le da un **pase** firmado (Ed25519)
   sólo si su cuenta está aprobada para EDA.
2. El launcher manda el pase a este server (`POST /eda/pase`, en `EDA_PUERTO + 1`) y recibe un
   **ticket**. Este server sólo comprueba la firma con la clave PÚBLICA del portero
   (`EDA_PORTERO_CLAVES`, un JWKS): no le pregunta nada a nadie.
3. El launcher abre `"EDA_limpio.exe" <usuario> <ticket> <IP:PUERTO>`; nuestra `d3d9.dll` se lo pasa
   al juego como en 2009 lo hacía el `NyxLauncher`, y el juego lo manda en el `0x100F`. La conexión
   recibe **su** cuenta (`r2b_<uid>`).

Lo que falta: **HTTPS** para el `/eda/pase` (un dominio y Caddy u otro proxy delante; hoy escucha en
127.0.0.1, porque el ticket es un secreto), el portero de verdad, y el launcher. Y más adelante,
**SQLite** en vez de un JSON por cuenta (un `eda.db` por entorno, detrás de `servidor/cuentas.py`).

### El relay entre dos casas

**El relay entre PCs de verdad** no se probó todavía: sólo con los dos clientes y el relay en la
  misma PC (MEDICIONES §30–31). Lo que sí está medido es que el server en Docker se arma, pasa las
  pruebas y contesta en Linux (las pruebas de GitHub), y que el juego llega a la partida por
  `servidor/red.py` con el relay prendido (MEDICIONES §38).

## La web: el login y el cliente para repartir (Caddy + Cloudflare)

El launcher canjea el pase en `https://<dominio>/eda/pase` y baja el cliente de
`https://<dominio>/files-eda/<release>-<azar>/`, **siempre por Cloudflare** (la IP del VPS no reparte
nada: el ancho de banda lo pone la CDN). En el VPS (MEDICIONES §46):

```sh
sh cortafuegos.sh                       # ufw: SSH, el juego y el relay abiertos; 80/443 sólo Cloudflare
sh caddy.sh <dominio en punycode> 25901 [<host del panel>]  # Caddy: sólo Cloudflare · /eda/* → el login · /files-eda/* · (/admin → el panel del portero)
```

`caddy.sh` necesita el certificado de ORIGEN de Cloudflare en `/etc/caddy/origen/origen.pem` y su clave
`origen.key` (se genera en el VPS con `openssl req -new -newkey ec …` y sólo el CSR sale para que
Cloudflare lo firme). El cliente se arma con `py herramientas\armar_cliente.py` (y su `eda.json` con
`… manifiesto`), se sube a `/opt/eda/files-eda/<release>-<azar>/` y se verifica con `md5sum -c` **antes**
de pedir ningún archivo por Cloudflare (si no, la CDN puede guardar un 404). Un nombre de release ya
servido no se reutiliza nunca.

## El panel del Coordinador (la puerta interna)

El Coordinador Eñeños administra EDA con el **contrato del panel v1** (está en el repo del Coordinador,
`documentacion/CONTRATO_PANEL.md`; acá lo atiende `servidor/panel.py`). El Coordinador decide quién puede qué; este
server sólo hace lo que sabe hacer hoy y anota quién lo pidió:

| ruta (`/interno/panel/…`) | qué hace |
|---|---|
| `GET capacidades` · `salud` · `conectados` · `buscar?q=` · `ficha/<cuenta>` | mirar: quién está, dónde, su personaje, sus monedas y lo que el panel le cambió |
| `POST aviso` | una línea en el chat de todos o de uno (`[Aviso]`) |
| `POST echar` | le corta la conexión (con el motivo en el chat, si se da). ⚠ No es un baneo: puede volver a entrar; el bloqueo es del Coordinador (el pase) |
| `POST moneda` | suma o resta **oro**, **cash** o **monedas para revivir** (de la cuenta). Nunca deja negativo. ⚠ Sólo con el jugador **desconectado** (si no, 409: el juego no se lo mostraría y una compra a la vez lo pisaría) |

- **La ficha:** todo pedido trae `X-Ficha-Interna` = `R2_CUENTAS_FICHA_INTERNA` (la misma del `.env` de Eñeños).
  Sin la variable, la puerta no existe (todo 404). Cada POST pide `X-R2: 1` y `X-Coordinador-Quien`.
- **La auditoría:** cada cambio va al registro del server (`docker logs`, líneas `panel: …`) y a
  `<estado>/panel_auditoria.jsonl` (de ahí salen los «movimientos» de la ficha).
- **No sale a internet:** Caddy publica sólo `/eda/*`; y un pedido que llega con `X-Forwarded-For` (por un proxy)
  da 404 aunque traiga la ficha.

**Cómo lo alcanza el Coordinador** (su contenedor `cuentas` vive en la red de Docker de la pila Eñeños):

- **El EDA de la pila Eñeños** (el servicio `eda` de su `docker-compose.yml`): el HTTP del login ya escucha en
  `0.0.0.0` dentro de esa red, sin publicarse. Se lo alcanza por el nombre: `http://eda:<EDA_PUERTO + 1>/interno/panel`.
  Al servicio hay que pasarle `R2_CUENTAS_FICHA_INTERNA` (y, si se quiere, `EDA_ENTORNO`).
- **`eda-prod` / `eda-prueba`** (este `docker-compose.yml`, con la red del VPS): su HTTP del login escucha en
  `127.0.0.1`, que desde otro contenedor no se alcanza. Para eso está `EDA_PANEL_ESCUCHAR`: un HTTP aparte, **sólo con
  el panel**, en la IP de la máquina en la red `bridge` de Docker, que los contenedores sí alcanzan:

  ```bash
  docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}'     # la IP de la máquina en esa red
  # en /opt/eda/prod.env:   R2_CUENTAS_FICHA_INTERNA=<la de Eñeños>   EDA_PANEL_ESCUCHAR=<esa IP>:25902
  # en /opt/eda/prueba.env: R2_CUENTAS_FICHA_INTERNA=<la de Eñeños>   EDA_PANEL_ESCUCHAR=<esa IP>:35902
  ufw allow proto tcp from <las redes de Docker: el bloque 172.16/12> to <esa IP> port 25902,35902 comment "panel del Coordinador"
  ```

  (`ufw` cierra lo que entra, también lo que viene de un contenedor a la máquina.) En el Coordinador:
  `R2_PANEL_GESTION=eda=contrato1:http://<esa IP>:25902/interno/panel` (o `host.docker.internal` con
  `extra_hosts: ["host.docker.internal:host-gateway"]` en `cuentas`). Esa IP no es pública: desde internet no llega.
