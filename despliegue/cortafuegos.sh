#!/bin/sh
# cortafuegos.sh -- ufw en el VPS de EDA (MEDICIONES §46).
#
#   sh cortafuegos.sh
#
#   · 22/tcp (SSH)                         abierto   ⚠ se abre ANTES de prender ufw (si no, te deja afuera)
#   · 25900, 35900/tcp (el juego)          abiertos  (prod y prueba: el juego va DIRECTO, no por Cloudflare)
#   · 26000-26300, 36000-36300/udp         abiertos  (el relay UDP de prod y de prueba)
#   · 80, 443/tcp                          SÓLO desde Cloudflare (https://www.cloudflare.com/ips-v4 y v6)
#   · lo demás que entre                   cerrado
# El login (25901 / 35901) escucha en 127.0.0.1: no hace falta abrirlo, Caddy lo alcanza por adentro.
set -eu
V4=$(curl -fsS https://www.cloudflare.com/ips-v4)
V6=$(curl -fsS https://www.cloudflare.com/ips-v6)
[ "$(printf '%s\n%s\n' "$V4" "$V6" | grep -cE '/[0-9]+$')" -ge 10 ] || { echo "⛔ los rangos de Cloudflare vinieron raros"; exit 1; }
ufw allow 22/tcp comment ssh >/dev/null
ufw allow 25900/tcp comment "eda prod" >/dev/null
ufw allow 35900/tcp comment "eda prueba" >/dev/null
ufw allow 26000:26300/udp comment "relay prod" >/dev/null
ufw allow 36000:36300/udp comment "relay prueba" >/dev/null
for r in $V4 $V6; do
	ufw allow proto tcp from "$r" to any port 80,443 comment cloudflare >/dev/null
done
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw --force enable >/dev/null
echo "✅ ufw prendido: SSH, juego (25900/35900), relay UDP, y 80/443 sólo desde Cloudflare"
ufw status | head -12
