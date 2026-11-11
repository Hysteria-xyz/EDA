#!/usr/bin/env bash
# despliegue/instalar.sh — deja un VPS Linux (Ubuntu / Debian) con los DOS servers de EDA andando:
#   prod   = la rama main     (puerto 25900, relay UDP 26000-26200)
#   prueba = la rama develop  (puerto 35900, relay UDP 36000-36200)
# y la copia de prueba actualizándose sola cada 5 minutos desde GitHub.
#
#   curl -fsSL https://raw.githubusercontent.com/r2beatlatino/EDA/main/despliegue/instalar.sh | sudo bash
#   (o, con el repo ya bajado:  sudo bash despliegue/instalar.sh)
#
# Variables opcionales: EDA_REPO (otro fork), EDA_RELAY_IP (la IP pública, si el VPS está detrás de NAT).
# Se puede correr de nuevo sin romper nada: lo que ya existe no se pisa.
set -euo pipefail

REPO="${EDA_REPO:-https://github.com/r2beatlatino/EDA.git}"
BASE=/opt/eda
[ "$(id -u)" = 0 ] || { echo "⛔ correlo como root (sudo)"; exit 1; }

echo "· 1/5 Docker y git"
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-v2 git >/dev/null
    systemctl enable --now docker
fi
command -v git >/dev/null || apt-get install -y -qq git >/dev/null

echo "· 2/5 carpetas en $BASE"
mkdir -p "$BASE/datos" "$BASE/estado-prod" "$BASE/estado-prueba"

echo "· 3/5 las dos copias del repositorio"
for par in prod:main prueba:develop; do
    entorno="${par%%:*}"; rama="${par##*:}"
    if [ ! -d "$BASE/$entorno/.git" ]; then
        git clone --quiet "$REPO" "$BASE/$entorno"
    fi
    git -C "$BASE/$entorno" fetch --quiet origin
    if git -C "$BASE/$entorno" rev-parse --verify --quiet "origin/$rama" >/dev/null; then
        git -C "$BASE/$entorno" checkout --quiet -B "$rama" "origin/$rama"
    else
        echo "  ⚠ no existe la rama $rama: $entorno usa main"
        git -C "$BASE/$entorno" checkout --quiet -B main origin/main
    fi
done

echo "· 4/5 la configuración (prod.env / prueba.env)"
IP="${EDA_RELAY_IP:-$(ip -4 route get 1.1.1.1 | awk '{for (i=1;i<NF;i++) if ($i=="src") print $(i+1)}')}"
for par in prod:25900:26000 prueba:35900:36000; do
    IFS=: read -r entorno puerto relay <<<"$par"
    env="$BASE/$entorno.env"
    [ -f "$env" ] && { echo "  ($env ya estaba: no se toca)"; continue; }
    sed -e "s/^EDA_ENTORNO=.*/EDA_ENTORNO=$entorno/" \
        -e "s/^EDA_PUERTO=.*/EDA_PUERTO=$puerto/" \
        -e "s/^EDA_RELAY_IP=.*/EDA_RELAY_IP=$IP/" \
        -e "s/^EDA_RELAY_BASE=.*/EDA_RELAY_BASE=$relay/" \
        -e "s#^EDA_ESTADO_DIR=.*#EDA_ESTADO_DIR=$BASE/estado-$entorno#" \
        "$BASE/prod/despliegue/ejemplo.env" > "$env"
    echo "  $env: puerto $puerto, relay $IP:$relay"
done

echo "· 5/5 arrancar y actualizar sola la de prueba"
bash "$BASE/prod/despliegue/actualizar.sh" prod --forzar
bash "$BASE/prod/despliegue/actualizar.sh" prueba --forzar
cat > /etc/cron.d/eda <<CRON
# EDA: la copia de PRUEBA sigue a la rama develop (la de prod se actualiza a mano: actualizar.sh prod)
*/5 * * * * root bash $BASE/prod/despliegue/actualizar.sh prueba >> $BASE/actualizaciones.log 2>&1
CRON

cat <<FIN

✅ Listo.
   prod:   py jugar.py --server $IP:25900
   prueba: py jugar.py --server $IP:35900

⚠ Falta (una vez):
   1. Los XML del juego en $BASE/datos (Product.xml, Skill.xml, StageReward.xml, ItemTypeList.xml).
      Salen de TU cliente: en Windows, 'py jugar.py' los guarda en _trabajo\\datos. Copialos con
      scp _trabajo/datos/*.xml root@$IP:$BASE/datos/   y después: bash $BASE/prod/despliegue/actualizar.sh prod --forzar
   2. Si el VPS tiene firewall (el del proveedor o ufw), abrir: TCP 25900 y 35900, UDP 26000-26200 y 36000-36200.
FIN
