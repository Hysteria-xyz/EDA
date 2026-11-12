#!/bin/sh
# caddy.sh -- la puerta HTTPS del VPS de EDA, SÓLO para Cloudflare (MEDICIONES §46).
#
#   sh caddy.sh DOMINIO [PUERTO_HTTP]      # p. ej.  sh caddy.sh xn--xxxx.link 25901
#
# Escribe /etc/caddy/Caddyfile y recarga Caddy:
#   · lo que NO viene de una IP de Cloudflare → 403 (la IP del VPS no reparte el cliente: el ancho
#     de banda lo pone la CDN)
#   · /eda/*        → el login (POST /eda/pase) del server de prod, en 127.0.0.1:PUERTO_HTTP (25901)
#   · /files-eda/*  → el cliente para repartir (/opt/eda/files-eda/<release>-<azar>/…), con caché de
#                     un año: la dirección lleva la versión, el contenido de una dirección no cambia
#   · lo demás      → 404
# El certificado: el de ORIGEN de Cloudflare en /etc/caddy/origen/origen.pem + origen.key (la clave
# se generó en el VPS y no sale de ahí). Con él, Cloudflare puede ir en «Full (strict)».
# Los rangos de Cloudflare se bajan de https://www.cloudflare.com/ips-v4 y ips-v6 cada vez que se
# corre esto (correrlo de nuevo si Cloudflare los cambia).
set -eu
DOMINIO="${1:?uso: sh caddy.sh DOMINIO [PUERTO_HTTP]}"
HTTP="${2:-25901}"
ORIGEN=/etc/caddy/origen
[ -s "$ORIGEN/origen.pem" ] && [ -s "$ORIGEN/origen.key" ] || { echo "⛔ falta $ORIGEN/origen.pem o origen.key"; exit 1; }
V4=$(curl -fsS https://www.cloudflare.com/ips-v4)
V6=$(curl -fsS https://www.cloudflare.com/ips-v6)
RANGOS=$(printf '%s\n%s\n' "$V4" "$V6" | grep -E '^[0-9a-f:.]+/[0-9]+$' | tr '\n' ' ')
[ "$(echo "$RANGOS" | wc -w)" -ge 10 ] || { echo "⛔ los rangos de Cloudflare vinieron raros: $RANGOS"; exit 1; }
chown -R root:caddy "$ORIGEN" && chmod 750 "$ORIGEN" && chmod 640 "$ORIGEN/origen.key" "$ORIGEN/origen.pem"
NUEVO=$(mktemp)
cat > "$NUEVO" <<FIN
# generado por despliegue/caddy.sh el $(date -u +%Y-%m-%d) — no editar a mano: volver a correrlo
{
	auto_https disable_redirects
}

$DOMINIO {
	tls $ORIGEN/origen.pem $ORIGEN/origen.key
	route {
		@no_cf not remote_ip $RANGOS
		respond @no_cf "solo por Cloudflare" 403
		reverse_proxy /eda/* 127.0.0.1:$HTTP
		header /files-eda/* Cache-Control "public, max-age=31536000, immutable"
		file_server /files-eda/* {
			root /opt/eda
		}
		respond 404
	}
}
FIN
caddy validate --adapter caddyfile --config "$NUEVO" >/dev/null
[ -f /etc/caddy/Caddyfile ] && cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.antes
install -m 644 "$NUEVO" /etc/caddy/Caddyfile && rm -f "$NUEVO"
systemctl reload caddy
echo "✅ Caddy: $DOMINIO (sólo Cloudflare: $(echo "$RANGOS" | wc -w) rangos) · /eda/* → 127.0.0.1:$HTTP · /files-eda/* → /opt/eda/files-eda"
