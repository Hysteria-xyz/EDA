# El server en Linux (VPS) — Docker, prod y prueba

El **juego** corre sólo en Windows (es de 2009). El **server** es Python puro y corre en cualquier
lado: acá se lo monta en un VPS Linux con Docker, con dos copias:

| entorno | rama | puerto TCP | relay UDP | se actualiza |
|---|---|---|---|---|
| **prod** | `main` | 25900 | 26000–26200 | a mano: `actualizar.sh prod` |
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

**Después, una sola vez — los XML del juego.** El server lee `Product.xml` (precios),
`Skill.xml`, `StageReward.xml` y `ItemTypeList.xml`. Son de Softnyx y **no están en el repo**.
Salen de tu cliente: `py jugar.py` los guarda la primera vez en `_trabajo\datos\`. Copialos desde
tu PC:

```bash
scp _trabajo/datos/*.xml root@IP_DEL_VPS:/opt/eda/datos/
```

Y en el VPS:

```bash
bash /opt/eda/prod/despliegue/actualizar.sh prod --forzar
```

Sin los XML el server anda igual, pero la tienda sale vacía y las stages no dan ítems.

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

## Mudarse a otro VPS

1. En el VPS **nuevo**: el `curl … instalar.sh | bash` de arriba.
2. Copiar las cuentas y los XML del viejo al nuevo:

   ```bash
   rsync -a root@VPS_VIEJO:/opt/eda/{datos,estado-prod,estado-prueba} /opt/eda/
   ```

3. En el nuevo, rearmar los dos entornos:

   ```bash
   bash /opt/eda/prod/despliegue/actualizar.sh prod --forzar && bash /opt/eda/prod/despliegue/actualizar.sh prueba --forzar
   ```

4. Avisar la IP nueva (`--server IP_NUEVA:25900`) y apagar el viejo: `docker compose -p eda-prod down`.

Son tres carpetas: nada más guarda estado.

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

- **Cuentas de verdad.** No hay login. Cada conexión toma la primera cuenta libre de `rui`, `kai`,
  `mio` y `ren` (`servidor/cuentas.py`). En un server público, un jugador no tiene SU personaje.
  El cliente no manda usuario ni contraseña (eso lo hacía el launcher de Softnyx), así que hay que
  inventar cómo identificar a cada jugador.
- **El relay entre PCs de verdad** se probó con dos clientes en una misma PC hablando con el VPS.
  Falta probarlo entre dos casas distintas.
