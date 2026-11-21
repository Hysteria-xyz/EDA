#!/bin/sh
# diagnostico-instalar.sh -- una llave de SSH que SÓLO baja el diagnóstico del server de PRUEBA.
#
#   sh diagnostico-instalar.sh "ssh-ed25519 AAAA… nombre"     (la llave PÚBLICA; como root, en el VPS)
#   sh diagnostico-instalar.sh quitar "nombre"                (saca la llave que termina en ese nombre)
#
# Qué deja:
#   · el usuario «eda-diag»: sin contraseña, sin sudo salvo UNA orden (abajo)
#   · /opt/eda/diagnostico-prueba.sh   copia de diagnostico.sh (de root; el usuario no la puede cambiar)
#   · /opt/eda/diagnostico-entrada.sh  lo ÚNICO que corre al entrar con esa llave: lee las horas pedidas
#                                      (sólo dígitos) y llama a la de arriba
#   · /etc/sudoers.d/eda-diag          eda-diag puede correr como root esa copia, y nada más
#   · .ssh/authorized_keys en la casa de ese usuario (de root): la llave con «restrict» (sin terminal,
#                                      sin túneles, sin reenvíos) y la orden forzada
#
# Quien tiene la llave privada hace:   ssh -i LLAVE eda-diag@SERVER 24 > diagnostico.tgz
# y recibe el paquete. Cualquier otra cosa que escriba después del nombre del server se ignora.
# No reinicia nada (ni sshd): con sólo escribir estos archivos ya anda.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
AQUI=$(cd "$(dirname "$0")" && pwd)
U=eda-diag
ARMAR=/opt/eda/diagnostico-prueba.sh
ENTRADA=/opt/eda/diagnostico-entrada.sh

[ "$(id -u)" = 0 ] || { echo "⛔ hay que correrlo como root"; exit 1; }
casa_de() { getent passwd "$U" | cut -d: -f6; }
CASA=$(casa_de || true)
LLAVES=$CASA/.ssh/authorized_keys

if [ "${1:-}" = quitar ]; then
	[ -n "${2:-}" ] || { echo "⛔ falta el nombre de la llave"; exit 1; }
	[ -n "$CASA" ] && [ -f "$LLAVES" ] || { echo "no hay llaves instaladas"; exit 0; }
	antes=$(grep -c . "$LLAVES" || true)
	grep -v -F -- " $2" "$LLAVES" > "$LLAVES.nuevo" || true
	cat "$LLAVES.nuevo" > "$LLAVES"
	rm -f "$LLAVES.nuevo"
	echo "✅ llaves: $antes → $(grep -c . "$LLAVES" || true)"
	exit 0
fi

LLAVE=${1:-}
case "$LLAVE" in
	"ssh-ed25519 AAAA"*|"ssh-rsa AAAA"*|"ecdsa-sha2-"*) ;;
	*) echo "⛔ eso no parece una llave PÚBLICA de SSH (empieza con ssh-ed25519, ssh-rsa o ecdsa-sha2-)"; exit 1 ;;
esac
# una sola línea, y sin comillas ni saltos (va adentro de authorized_keys)
[ "$(printf '%s\n' "$LLAVE" | wc -l)" = 1 ] || { echo "⛔ la llave tiene más de una línea"; exit 1; }
case "$LLAVE" in *'"'*|*"'"*|*'\'*) echo "⛔ la llave trae comillas o barras"; exit 1 ;; esac
[ -f "$AQUI/diagnostico.sh" ] || { echo "⛔ falta diagnostico.sh al lado de este archivo"; exit 1; }

id "$U" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/sh "$U"
CASA=$(casa_de)
[ -n "$CASA" ] && [ "$CASA" != / ] || { echo "⛔ el usuario $U quedó sin carpeta propia"; exit 1; }
LLAVES=$CASA/.ssh/authorized_keys

install -o root -g root -m 0755 "$AQUI/diagnostico.sh" "$ARMAR"
printf '%s\n' '#!/bin/sh' \
	'# lo que corre al entrar con la llave del diagnóstico (ver diagnostico-instalar.sh)' \
	'h=$(printf "%s" "${SSH_ORIGINAL_COMMAND:-}" | tr -cd "0-9" | cut -c1-3)' \
	"exec sudo -n $ARMAR \"\${h:-24}\"" > "$ENTRADA.nuevo"
install -o root -g root -m 0755 "$ENTRADA.nuevo" "$ENTRADA"
rm -f "$ENTRADA.nuevo"

printf '%s\n' "$U ALL=(root) NOPASSWD: $ARMAR" > /etc/sudoers.d/$U.nuevo
visudo -cf /etc/sudoers.d/$U.nuevo >/dev/null || { rm -f /etc/sudoers.d/$U.nuevo; echo "⛔ sudoers no valida"; exit 1; }
install -o root -g root -m 0440 /etc/sudoers.d/$U.nuevo /etc/sudoers.d/$U
rm -f /etc/sudoers.d/$U.nuevo

# la casa y las llaves son de root: el usuario las lee, no las cambia
install -d -o root -g root -m 0755 "$CASA" "$CASA/.ssh"
touch "$LLAVES"
chown root:root "$LLAVES"
chmod 0644 "$LLAVES"
if grep -q -F -- "$(printf '%s' "$LLAVE" | cut -d' ' -f2)" "$LLAVES"; then
	echo "esa llave ya estaba"
else
	printf 'restrict,command="%s" %s\n' "$ENTRADA" "$LLAVE" >> "$LLAVES"
fi
echo "✅ listo: «$U» baja el diagnóstico del server de prueba con $(grep -c . "$LLAVES") llave(s), y nada más"
