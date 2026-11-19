/* prueba_version.c — ★ las pruebas de eda_version.c (entorno, líneas del aviso, marca), sin Windows ni el juego.
 *   Las compila y corre prueba_version.py con gcc, con un eda_version.h de mentira en -I (limpio y sucio):
 *     gcc -std=gnu11 -I<carpeta con eda_version.h> -o /tmp/pv herramientas/dll_d3d9/prueba_version.c && /tmp/pv */
#include <stdio.h>
#include <string.h>
#include "eda_version.c"

static int ok, mal;
static void chequear(const char *n, int c) { printf("  %s %s\n", c ? "OK " : "MAL", n); if (c) ok++; else mal++; }

int main(void)
{
    int p;
    printf("prueba_version: EDA %s · commit %s · sucio %d · build %s\n", EDA_VERSION, EDA_COMMIT, EDA_SUCIO, EDA_BUILD);
    /* el entorno sale del SERVER, no de la rama */
    chequear("vacío → SIN SERVER", ver_entorno("", &p) == ENT_SIN && ver_entorno(NULL, NULL) == ENT_SIN);
    chequear("127.0.0.1:25900 → LOCAL (aunque sea el puerto de prod)", ver_entorno("127.0.0.1:25900", &p) == ENT_LOCAL && p == 25900);
    chequear("127.0.0.1:35900 → LOCAL", ver_entorno("127.0.0.1:35900", NULL) == ENT_LOCAL);
    chequear("localhost → LOCAL", ver_entorno("LocalHost:35900", NULL) == ENT_LOCAL);
    chequear("192.168.1.20 → LOCAL", ver_entorno("192.168.1.20:25900", NULL) == ENT_LOCAL);
    chequear("10.0.0.5 → LOCAL", ver_entorno("10.0.0.5", NULL) == ENT_LOCAL);
    /* (las 172.16–31.x: revisar_publico.py no deja escribir IPs de redes de casa fuera de 10.x y 192.168.0/1.x) */
    chequear("203.0.113.7:35900 → TEST", ver_entorno("203.0.113.7:35900", &p) == ENT_TEST && p == 35900);
    chequear("203.0.113.7:25900 → PROD", ver_entorno("203.0.113.7:25900", NULL) == ENT_PROD);
    chequear("203.0.113.7 (sin puerto = 25900) → PROD", ver_entorno("203.0.113.7", &p) == ENT_PROD && p == 25900);
    chequear("un dominio :35900 → TEST", ver_entorno("eda.example.org:35900", NULL) == ENT_TEST);
    chequear("un dominio :25900 → PROD", ver_entorno("eda.example.org:25900", NULL) == ENT_PROD);
    chequear("otro puerto → OTRO", ver_entorno("eda.example.org:4000", NULL) == ENT_OTRO);
    chequear("puerto roto → OTRO", ver_entorno("eda.example.org:9x9", NULL) == ENT_OTRO
             && ver_entorno("eda.example.org:", NULL) == ENT_OTRO && ver_entorno("eda.example.org:999999", NULL) == ENT_OTRO);
    chequear("1.2.3.256 no es una IP (→ por el puerto)", ver_entorno("1.2.3.256:25900", NULL) == ENT_PROD);

    /* las líneas del aviso */
    char lin[VER_LINEAS][VER_LARGO], esperado[160];
    int e = ver_lineas("203.0.113.7:35900", NULL, lin);
    chequear("aviso: título", !strcmp(lin[0], "EDA — Cliente iniciado"));
    snprintf(esperado, sizeof(esperado), "Versión: %s-test", EDA_VERSION);
    chequear("aviso: versión con el entorno del server", e == ENT_TEST && !strcmp(lin[1], esperado));
    if (EDA_SUCIO) snprintf(esperado, sizeof(esperado), "Compilación: %s-dirty · %s (LOCAL, no publicada)", EDA_COMMIT, EDA_BUILD);
    else snprintf(esperado, sizeof(esperado), "Compilación: %s · %s", EDA_COMMIT, EDA_BUILD);
    chequear("aviso: compilación (y LOCAL si está sucia)", !strcmp(lin[2], esperado));
    chequear("aviso: entorno y puerto", !strcmp(lin[3], "Entorno: TEST (puerto 35900)"));
    chequear("aviso: estado por defecto", !strcmp(lin[4], "Estado: DLL cargada correctamente"));
    ver_lineas("203.0.113.7:25900", "⚠ no se pudo desviar la conexión al server", lin);
    snprintf(esperado, sizeof(esperado), "Versión: %s-prod", EDA_VERSION);
    chequear("aviso: PROD + un estado de error", !strcmp(lin[1], esperado) && strstr(lin[4], "no se pudo desviar"));
    ver_lineas("", NULL, lin);
    chequear("aviso: sin server", strstr(lin[1], "-sin-server") && !strcmp(lin[3], "Entorno: SIN SERVER (el juego no se desvía)"));
    char corta[128];
    ver_corta("127.0.0.1:25900", corta, sizeof(corta));
    snprintf(esperado, sizeof(esperado), "EDA %s-local · %s%s · %s", EDA_VERSION, EDA_COMMIT, EDA_SUCIO ? "-dirty" : "", EDA_BUILD);
    chequear("línea corta (Options / registro)", !strcmp(corta, esperado));

    /* la marca que lee identificar.py */
    snprintf(esperado, sizeof(esperado), "EDA-ID|v=%s|c=%s|s=%d|f=%s|b=%s|", EDA_VERSION, EDA_COMMIT, EDA_SUCIO, EDA_FECHA, EDA_BUILD);
    chequear("marca EDA-ID con los datos de la compilación", !strcmp(g_eda_id, esperado));

    printf("prueba_version: %d bien · %d mal\n", ok, mal);
    return mal ? 1 : 0;
}
