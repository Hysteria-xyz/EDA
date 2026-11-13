#!/usr/bin/env bash
# despliegue/actualizar.sh — pone un entorno en lo último de SU rama y lo reinicia, sólo si cambió algo.
#
#   bash /opt/eda/prod/despliegue/actualizar.sh prod      # main     → eda-prod   (cron, cada 5 min)
#   bash /opt/eda/prod/despliegue/actualizar.sh prueba    # develop  → eda-prueba (cron, cada 5 min)
#   … --forzar                                            # rearma aunque no haya cambios
#
# ★ Si las pruebas del server fallan, la imagen NO se arma (el Dockerfile corre `juego.py control`) y
#   el contenedor que andaba SIGUE andando: un PR roto en develop no tira el server de prueba.
# ★ (13-nov) Prod se actualiza SOLO al fusionar en main (que pide 2 aprobaciones): antes, el RESPALDO de
#   las cuentas (`/opt/eda/respaldos/`, quedan los últimos 30); después, la prueba de que contesta, y
#   si no contesta, VUELVE al commit anterior y lo rearma.
set -euo pipefail

ENTORNO="${1:?uso: actualizar.sh prod|prueba [--forzar]}"
BASE=/opt/eda
case "$ENTORNO" in
    prod) RAMA=main ;;
    prueba) RAMA=develop ;;
    *) echo "⛔ entorno: prod o prueba"; exit 1 ;;
esac
DIR="$BASE/$ENTORNO"
ENV="$BASE/$ENTORNO.env"
cd "$DIR"
git rev-parse --verify --quiet "origin/$RAMA" >/dev/null || RAMA=main     # (develop todavía no existe)

git fetch --quiet origin "$RAMA"
ANTES="$(git rev-parse --short HEAD)"
AHORA="$(git rev-parse --short "origin/$RAMA")"
CORRIENDO="$(docker ps --filter "name=^eda-$ENTORNO$" --format '{{.Names}}')"
if [ "${2:-}" != "--forzar" ]; then
    [ "$ANTES" = "$AHORA" ] && [ -n "$CORRIENDO" ] && exit 0                     # nada nuevo
    [ "$AHORA" = "$(cat "$BASE/$ENTORNO.fallido" 2>/dev/null)" ] && exit 0      # ya falló: no reintentar
fi

echo "$(date '+%F %T') $ENTORNO ($RAMA): $ANTES → $AHORA"
if [ -d "$BASE/estado-$ENTORNO" ]; then                     # ★ el respaldo de las cuentas, ANTES
    mkdir -p "$BASE/respaldos"
    tar czf "$BASE/respaldos/estado-$ENTORNO-$(date '+%Y%m%d-%H%M%S')-$ANTES.tgz" -C "$BASE" "estado-$ENTORNO"
    ls -1t "$BASE/respaldos/estado-$ENTORNO-"*.tgz | tail -n +31 | xargs -r rm -f
fi
armar() {
    docker compose -p "eda-$ENTORNO" --env-file "$ENV" -f despliegue/docker-compose.yml up -d --build --quiet-pull
}
git reset --hard --quiet "origin/$RAMA"
if ! armar; then
    echo "$(date '+%F %T') ⛔ $ENTORNO: no se pudo armar ($AHORA). Sigue el anterior."
    echo "$AHORA" > "$BASE/$ENTORNO.fallido"
    git reset --hard --quiet "$ANTES"
    exit 1
fi
sleep 3
PUERTO="$(sed -n 's/^EDA_PUERTO=//p' "$ENV")"
if ! docker exec "eda-$ENTORNO" python -m servidor.red prueba "127.0.0.1:${PUERTO:-25900}"; then
    # ★ arrancó pero no contesta: se vuelve al anterior (las cuentas no se tocan: están en estado-*)
    echo "$(date '+%F %T') ⛔ $ENTORNO: $AHORA no contesta. Vuelvo a $ANTES."
    echo "$AHORA" > "$BASE/$ENTORNO.fallido"
    git reset --hard --quiet "$ANTES"
    armar || true
    exit 1
fi
rm -f "$BASE/$ENTORNO.fallido"
