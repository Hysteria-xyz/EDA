# El server de EDA en un contenedor (Linux). Sólo el server: el juego sigue corriendo en Windows,
# en la PC de cada jugador (`py jugar.py --server IP:PUERTO`).
#
#   docker compose -f despliegue/docker-compose.yml up -d --build     (ver despliegue/LEEME.md)
FROM python:3.13-slim

WORKDIR /eda
RUN pip install --no-cache-dir "pycryptodome==3.24.1"

# lo que el server usa de herramientas/ (el paquete cifrado, las reglas del Broker y el relay UDP)
COPY herramientas/paquete_broker.py herramientas/reglas_broker.py herramientas/relay_udp.py herramientas/
COPY servidor/ servidor/
# las tablas del juego (Product.xml, Skill.xml…: ver datos/LEEME.md)
COPY datos/*.xml datos/

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    EDA_ESTADO=/eda/estado \
    EDA_DATOS=/eda/datos

# ¿anda? = las pruebas del server (sin el juego), TODAS: con los XML adentro ninguna se salta.
# Si fallan, la imagen no se arma.
RUN EDA_EXIGIR_DATOS=1 python servidor/juego.py control > /tmp/control.txt || (cat /tmp/control.txt; exit 1)

# ¿contesta? = un 0x0604 de verdad (el primer mensaje del cliente) y su respuesta
HEALTHCHECK --interval=5m --timeout=10s --start-period=20s \
    CMD python -c "import os,socket; socket.create_connection(('127.0.0.1', int(os.environ.get('EDA_PUERTO') or 25900)), 5).close()"

CMD ["python", "-m", "servidor.red"]
