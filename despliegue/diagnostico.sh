#!/bin/sh
# diagnostico.sh -- el paquete de registros del server de PRUEBA, para quien investiga una falla.
#
#   sh diagnostico.sh [horas] > diagnostico.tgz        (horas: 1 … 168; sin nada, 24)
#
# Saca por la salida un .tgz con:
#   LEEME.txt    cuándo se armó, qué código corre, desde cuándo, y la configuración (SÓLO las variables de
#                la lista de abajo: ninguna clave)
#   server.log   lo que escribió el server de prueba en esas horas
#   relay.log    el relay UDP (sus líneas no llevan fecha; van las últimas 20000)
#   punch.json · nat.json · relay.json   como están AHORA (el server los pisa en cada cambio)
#
# SÓLO LEE, y SÓLO lo del server de prueba: no toca prod, ni las cuentas, ni la base del login, ni reinicia
# nada. Lo instala diagnostico-instalar.sh, que le da a una llave de SSH permiso para correr esto y nada más.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
C=eda-prueba
E=/opt/eda/estado-prueba
R=/opt/eda/prueba
VARIABLES='EDA_P2P|EDA_P2P_ENTRE_CASAS|EDA_RELAY_IP|EDA_RELAY_BASE|EDA_ESPERA_CARGA|EDA_LOGIN|EDA_ENTORNO|EDA_PUERTO|EDA_MAX_CONEXIONES'

# las horas: sólo dígitos, de 1 a 168. Cualquier otra cosa → 24 (lo que llega acá lo escribe quien pide)
h=$(printf '%s' "${1:-}" | tr -cd '0-9' | cut -c1-3 | sed 's/^0*//')
[ -n "$h" ] || h=24
[ "$h" -le 168 ] || h=168

T=$(mktemp -d /tmp/eda-diagnostico.XXXXXX)
trap 'rm -rf "$T"' EXIT
D="$T/eda-prueba-diagnostico"
mkdir "$D"

{
	echo "EDA · server de PRUEBA · diagnostico"
	echo "armado:      $(date -u '+%Y-%m-%d %H:%M:%S') UTC, con las ultimas $h horas del server"
	echo "codigo:      $(git -C "$R" log -1 --format='%h · %cI · %s' 2>&1 || true)"
	echo "contenedor:  $(docker inspect "$C" --format 'arrancado {{.State.StartedAt}} · {{.State.Status}}' 2>&1 || true)"
	echo
	echo "TODAS las horas son UTC. Las lineas de relay.log no llevan fecha."
	echo "punch.json, nat.json y relay.json son los de AHORA: el server los pisa en cada cambio."
	echo
	echo "configuracion (la que no aparece no esta puesta: vale el valor por defecto del codigo)"
	docker inspect "$C" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
		| grep -E "^($VARIABLES)=" | sed 's/^/  /' || true
	echo
	echo "los archivos del estado (ultimo cambio)"
	for f in relay.log punch.json nat.json relay.json; do
		if [ -f "$E/$f" ]; then
			echo "  $f  $(date -u -r "$E/$f" '+%Y-%m-%d %H:%M:%S')  $(wc -c < "$E/$f") B"
		else
			echo "  $f  (no esta)"
		fi
	done
} > "$D/LEEME.txt"

docker logs "$C" --since "${h}h" > "$D/server.log" 2>&1 || true
tail -n 20000 "$E/relay.log" > "$D/relay.log" 2>/dev/null || true
for f in punch.json nat.json relay.json; do
	cp "$E/$f" "$D/$f" 2>/dev/null || true
done
tar -C "$T" -czf - eda-prueba-diagnostico
