/* prueba_teclas.c — ★ (Punto 4) las pruebas de eda_teclas.c, sin Windows ni el juego:
 *     gcc -std=gnu11 -o /tmp/prueba_teclas herramientas/dll_d3d9/prueba_teclas.c && /tmp/prueba_teclas [autoexec.cfg]
 *   Con un autoexec.cfg de verdad como argumento, además prueba con ése (no lo modifica). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <wchar.h>
typedef wchar_t WCHAR;
#define lstrcmpiA strcasecmp
#include "eda_teclas.c"

static int ok, mal;
static void chequear(const char *n, int c) { printf("  %s %s\n", c ? "OK " : "MAL", n); if (c) ok++; else mal++; }
static int fila(const char *a) { for (int i = 0; i < TEC_FILAS; i++) if (!strcmp(TEC[i].accion, a)) return i; return -1; }
static int contar(const char *t, const char *s) { int n = 0; for (const char *p = t; (p = strstr(p, s)); p++) n++; return n; }

static const char *CFG =
    "\"MusicVolume\" \"1.00\"\r\n"
    "\"enabledevice\" \"##mouse\"\r\n"
    "AddAction MoveForward 1\r\n"
    "enabledevice \"##keyboard\"\r\n"
    "rangebind \"##keyboard\" \"##200\" 0.000000 0.000000 \"MoveForward\" \r\n"
    "rangebind \"##keyboard\" \"##59\" 0.000000 0.000000 \"Skill1\" \r\n"
    "rangebind \"##keyboard\" \"##17\" 0.000000 0.000000 \"MoveForward\" \r\n"
    "rangebind \"##keyboard\" \"##2\" 0.000000 0.000000 \"Revival1\" 0.000000 0.000000 \"GameItem1\" \r\n"
    "rangebind \"##keyboard\" \"##99\" 0.000000 0.000000 \"OtraCosa\" \r\n"
    "enabledevice \"##mouse\"\r\n"
    "rangebind \"##mouse\" \"##x-axis\" 0.000000 0.000000 \"Axis1\" \r\n"
    "scale \"##mouse\" \"##x-axis\" 0.008000\r\n"
    "rangebind \"##mouse\" \"##Button 0\" 0.000000 0.000000 \"MouseButtonL\" \r\n";

int main(int argc, char **argv)
{
    static TEC_MAPA viejo, nuevo, vuelta;
    int t[TEC_FILAS][2], q, cods[TEC_BOTONES];
    static char salida[1 << 16];
    char l[200];
    WCHAR w[32];
    tec_leer_cfg(CFG, &viejo);
    tec_de_mapa(&viejo, t);
    chequear("lee: Avanzar = W (17) y ↑ (200), en ese orden", t[fila("MoveForward")][0] == 17 && t[fila("MoveForward")][1] == 200);
    chequear("lee: Ítem 1 = «1» (2), que lleva también Revival1", t[fila("GameItem1")][0] == 2);
    chequear("lee: Atacar = clic izquierdo (botón 0 del mouse)", t[fila("MouseButtonL")][0] == TEC_MOUSE);
    chequear("lee: los ejes del mouse no son botones (no se tocan)", !tec_boton(&viejo, 0, 0) && viejo.n == 6);
    /* cambiar Habilidad 1 de F1 a Q (16) */
    tec_poner(t, fila("Skill1"), 0, 16, &q);
    tec_armar(&viejo, t, &nuevo);
    int n = tec_cambiados(&viejo, &nuevo, cods, TEC_BOTONES);
    chequear("cambia sólo F1 (queda vacío) y Q (Skill1): 2 botones", n == 2);
    tec_comando(&nuevo, 59, l, sizeof(l));
    chequear("en vivo: «Bind ##keyboard ##59» SIN acciones = borrar F1", !strcmp(l, "Bind \"##keyboard\" \"##59\""));
    tec_comando(&nuevo, 16, l, sizeof(l));
    chequear("en vivo: «Bind ##keyboard ##16 Skill1»", !strcmp(l, "Bind \"##keyboard\" \"##16\" \"Skill1\""));
    int largo = tec_nuevo_cfg(CFG, &nuevo, cods, n, salida, sizeof(salida));
    chequear("autoexec nuevo: sin la línea de F1", largo > 0 && !strstr(salida, "\"##59\""));
    chequear("autoexec nuevo: Q con Skill1, debajo de enabledevice del teclado, con \\r\\n",
             strstr(salida, "enabledevice \"##keyboard\"\r\nrangebind \"##keyboard\" \"##16\" 0.000000 0.000000 \"Skill1\" \r\n") != NULL);
    chequear("autoexec nuevo: lo demás igual (opciones, AddAction, ejes, OtraCosa, ítem con Revival)",
             strstr(salida, "\"MusicVolume\" \"1.00\"\r\n") && strstr(salida, "AddAction MoveForward 1") &&
             strstr(salida, "\"Axis1\"") && strstr(salida, "scale \"##mouse\" \"##x-axis\" 0.008000") &&
             strstr(salida, "\"OtraCosa\"") && strstr(salida, "\"Revival1\" 0.000000 0.000000 \"GameItem1\""));
    tec_leer_cfg(salida, &vuelta);
    int t2[TEC_FILAS][2];
    tec_de_mapa(&vuelta, t2);
    chequear("releído: el autoexec nuevo da las mismas teclas", !memcmp(t, t2, sizeof(t)));
    /* repetida: poner W (17) en Saltar → se saca de Avanzar */
    tec_de_mapa(&viejo, t);
    int quitadas = tec_poner(t, fila("Jump"), 0, 17, &q);
    chequear("repetida: W a Saltar la saca de Avanzar (queda ↑) y avisa cuál", quitadas == 1 && q == fila("MoveForward")
             && t[fila("MoveForward")][0] == 0 && t[fila("MoveForward")][1] == 200 && t[fila("Jump")][0] == 17);
    tec_armar(&viejo, t, &nuevo);
    TEC_BOTON *w17 = tec_boton(&nuevo, 17, 0);
    chequear("repetida: en el mapa W tiene sólo Jump", w17 && w17->n == 1 && !strcmp(w17->acc[0], "Jump"));
    /* el ítem: mover Ítem 1 a «5» (6) → Revival1 va con él */
    tec_de_mapa(&viejo, t);
    tec_poner(t, fila("GameItem1"), 0, 6, &q);
    tec_armar(&viejo, t, &nuevo);
    TEC_BOTON *b6 = tec_boton(&nuevo, 6, 0), *b2 = tec_boton(&nuevo, 2, 0);
    chequear("ítem: «5» lleva GameItem1 Y Revival1; «1» queda vacío", b6 && b6->n == 2 && (!b2 || !b2->n));
    /* sin cambios → nada que hacer */
    tec_de_mapa(&viejo, t);
    tec_armar(&viejo, t, &nuevo);
    chequear("sin cambios: ningún botón cambiado (no se escribe ni se manda nada)", tec_cambiados(&viejo, &nuevo, cods, TEC_BOTONES) == 0);
    /* de fábrica */
    tec_de_fabrica(t);
    chequear("de fábrica: Habilidad 1 = F1, Avanzar = W/↑, Ítem 1 = «1»", t[fila("Skill1")][0] == 59 &&
             t[fila("MoveForward")][0] == 17 && t[fila("MoveForward")][1] == 200 && t[fila("GameItem1")][0] == 2);
    int dup = 0;
    for (int a = 0; a < TEC_FILAS; a++) for (int x = 0; x < 2; x++) for (int b = 0; b < TEC_FILAS; b++) for (int y = 0; y < 2; y++)
        if (t[a][x] && t[a][x] == t[b][y] && (a != b || x != y)) dup++;
    chequear("de fábrica: ninguna tecla repetida", dup == 0);
    chequear("reservadas: F9, F10, F11, F12 y Esc", tec_reservada(67) && tec_reservada(68) && tec_reservada(87) && tec_reservada(88) && tec_reservada(1) && !tec_reservada(59));
    chequear("nombres: F1, W, ↑, Clic der., «1», Num 5", tec_nombre(59, w) && !wcscmp(w, L"F1") && tec_nombre(17, w) && !wcscmp(w, L"W")
             && tec_nombre(200, w) && !wcscmp(w, L"↑") && tec_nombre(TEC_MOUSE + 1, w) && !wcscmp(w, L"Clic der.")
             && tec_nombre(2, w) && !wcscmp(w, L"1") && tec_nombre(76, w) && !wcscmp(w, L"Num 5") && !tec_nombre(250, w));
    /* con un autoexec.cfg de verdad */
    if (argc > 1) {
        FILE *f = fopen(argv[1], "rb");
        static char real[1 << 16];
        int lr = f ? (int)fread(real, 1, sizeof(real) - 1, f) : 0;
        if (f) fclose(f);
        real[lr] = 0;
        tec_leer_cfg(real, &viejo);
        tec_de_mapa(&viejo, t);
        printf("  (el de verdad: %d botones; Habilidad 1 = %d/%d, Ítem 1 = %d, Avanzar = %d/%d)\n", viejo.n,
               t[fila("Skill1")][0], t[fila("Skill1")][1], t[fila("GameItem1")][0], t[fila("MoveForward")][0], t[fila("MoveForward")][1]);
        tec_armar(&viejo, t, &nuevo);
        chequear("el de verdad: leerlo y volver a armarlo sin tocar nada = 0 cambios", tec_cambiados(&viejo, &nuevo, cods, TEC_BOTONES) == 0);
        tec_de_fabrica(t);
        tec_armar(&viejo, t, &nuevo);
        n = tec_cambiados(&viejo, &nuevo, cods, TEC_BOTONES);
        largo = tec_nuevo_cfg(real, &nuevo, cods, n, salida, sizeof(salida));
        tec_leer_cfg(salida, &vuelta);
        tec_de_mapa(&vuelta, t2);
        chequear("el de verdad → de fábrica: el archivo nuevo se relee igual a lo pedido", largo > 0 && !memcmp(t, t2, sizeof(t)));
        chequear("el de verdad → de fábrica: los ejes y la escala del mouse siguen", strstr(salida, "\"Axis1\"") && strstr(salida, "\"Axis2\"")
                 && strstr(salida, "\"Axis3\"") && contar(salida, "scale \"##mouse\"") == contar(real, "scale \"##mouse\""));
        chequear("el de verdad → de fábrica: las AddAction siguen todas", contar(salida, "AddAction") == contar(real, "AddAction"));
        printf("  (de fábrica cambia %d botones: %d comandos «Bind» en vivo)\n", n, n);
        int largos = 1;
        for (int k = 0; k < n; k++) { tec_comando(&nuevo, cods[k], l, sizeof(l)); if (strlen(l) >= 96) largos = 0; }
        chequear("el de verdad → de fábrica: cada comando entra en la cola de la consola (< 96)", largos);
    }
    printf("%d bien, %d mal\n", ok, mal);
    return mal != 0;
}
