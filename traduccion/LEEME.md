# Traducción de EDA

Esta carpeta guarda la **fuente de verdad** de las traducciones del cliente de EDA (textos XML de `Data.dat`) y las herramientas para mantenerlas sin tocar `EDA_limpio.exe`, `Data.dat` ni `LTMsg.dll`.

## Estructura

```text
traduccion/
├── es/                          # Español (fuente de verdad: 5 XML de texto)
│   ├── data/scenario/string/international/chapter1_string.xml
│   └── string/international/
│       ├── err_string.xml
│       ├── mapnameandexplainstring.xml
│       ├── nameandexplainstring.xml
│       └── uistring.xml
├── herramientas/
│   ├── desempacar_data_dat.py   # Lee y desempaca Data.dat a _trabajo/ (solo local)
│   ├── extraer_textos.py        # Extrae textos-en.json desde los XML originales
│   └── hoja.py                  # Exporta e importa la planilla Excel (.xlsx)
└── LEEME.md
```

> **Importante:** no se sube al repositorio el contenido desempacado de `Data.dat` ni imágenes del cliente original. Aquí solo viven los XML traducidos y las herramientas.

---

## Cómo traducir o corregir textos con la planilla

El flujo de trabajo usa una planilla Excel (`.xlsx`) donde solo se edita la columna **ESPAÑOL**:

1. **Preparar los originales en inglés (una sola vez, en tu PC):**
   Con una copia limpia del cliente (con `Data.dat` y `LTMsg.dll`), desempaca los textos originales en `_trabajo/` (ignorado por git):
   ```bat
   python traduccion/herramientas/desempacar_data_dat.py extraer --cliente RUTA_AL_CLIENTE
   python traduccion/herramientas/extraer_textos.py generar --cliente RUTA_AL_CLIENTE
   ```

2. **Exportar la planilla:**
   ```bat
   python traduccion/herramientas/hoja.py exportar EDA-traduccion.xlsx
   ```
   Si ya tienes una planilla previa y quieres conservar lo traducido, pásala como segundo argumento:
   ```bat
   python traduccion/herramientas/hoja.py exportar EDA-traduccion-nueva.xlsx EDA-traduccion-anterior.xlsx
   ```

3. **Editar la columna `ESPAÑOL` en Excel:**
   - Conserva `[TEXTO]` y `[NÚMERO]` en el mismo orden que en la columna `INGLÉS` (la herramienta los vuelve a convertir en `%s`, `%d`, etc.).
   - Para saltos de línea dentro de una celda usa `Alt+Enter`.
   - Revisa la columna `OJO`: marca avisos de espacio (`⛔ NO ENTRA`) cuando un rótulo podría pisarse con números en pantalla.

4. **Importar la planilla a `traduccion/es/`:**
   ```bat
   python traduccion/herramientas/hoja.py importar EDA-traduccion.xlsx
   ```
   Esto actualiza los 5 XML en `traduccion/es/` listos para probar y commitear.

5. **Comprobar la herramienta y los XML:**
   ```bat
   python traduccion/herramientas/hoja.py control
   ```

---

## Cómo probar la traducción

La DLL (`d3d9.dll`) busca cada archivo traducido en este orden cuando `[traduccion] idioma=es` está activo (viene prendido por defecto):

1. **Carpeta suelta junto al juego** (`traducciones\es\<ruta>`): tiene prioridad sobre lo embebido. Sirve para editar un XML y probarlo enseguida **sin recompilar** `d3d9.dll`.
2. **Traducción embebida dentro de `d3d9.dll`**: generada automáticamente desde `traduccion/<idioma>/**` al compilar con `herramientas/dll_d3d9/compilar.py`. Es lo que reciben todos los jugadores con el launcher (no necesitan ninguna carpeta extra).
3. **`Data.dat` original**: cualquier archivo que no esté traducido se lee del contenedor original sin cambios.

### Cómo apagarla o cambiar de idioma

★ **El jugador lo elige en el launcher** (23-nov, decisión del dueño del launcher): «Opciones del juego» de EDA →
**Idioma** (Español / English). El launcher escribe `[traduccion] idioma=` en `eda_d3d9.ini` antes de abrir el juego,
con la misma rutina que ya usa para las demás opciones de EDA (sólo esa clave; el resto del `.ini` no se toca).
Los idiomas que ofrece el selector salen del contenido dinámico del Coordinador: cuando se sume otro idioma
(por ejemplo `pt`), se agrega ahí, sin sacar un launcher nuevo.

A mano, en `eda_d3d9.ini` (junto al juego):
- `idioma=es` → español (por defecto).
- `idioma=en` (o `off`, `ninguno`) → desactiva la traducción y vuelve al inglés original sin enganchar SolFS.
- `[general] mejoras=0` → también la desactiva.
- Variable de entorno `EDA_IDIOMA=en` (o `es`) → pisa el `.ini` para esa sesión.

---

## Cómo agregar otro idioma

1. Crea una carpeta nueva bajo `traduccion/<codigo>/` (por ejemplo `traduccion/pt/` para portugués; usa letras minúsculas, mínimo 2 caracteres).
2. Copia dentro los XML traducidos conservando la misma estructura relativa (`string/international/uistring.xml`, etc.), o importa tu planilla indicando `--idioma pt`:
   ```bat
   python traduccion/herramientas/hoja.py importar EDA-traduccion-pt.xlsx --idioma pt
   ```
3. Recompila la DLL (`python herramientas/dll_d3d9/compilar.py`): `compilar.py` detecta automáticamente todas las subcarpetas de idioma dentro de `traduccion/` y las embebe en `d3d9.dll`.
4. Actívalo con `idioma=pt` en `eda_d3d9.ini` o `EDA_IDIOMA=pt`.
