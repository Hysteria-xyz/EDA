# Entornos de EDA: diferencias que hay que conocer para que los agentes se sincronicen

Varios agentes trabajan sobre el mismo repo: el de Urek-Mazinoo, el del dueño y los de otros colaboradores.
Cada uno corre en un lugar distinto. La mayoría de los problemas que tuvimos no fueron de código:
fueron de **entorno**: finales de línea, un `.bundle` viejo, una DLL bloqueada por Windows o un `git`
que no estaba en el PATH.

Este documento lista esas diferencias y propone una **forma común de trabajar**.
Hay que leerlo antes de tocar el repo y releerlo cuando algo «anda en mi máquina y no en la tuya».

> Lo escribió el agente de Urek-Mazinoo (14-nov-2026). Las filas E y D, las huellas de §4.1 y las
> correcciones medidas son del agente del dueño. Lo marcado **(a confirmar)** no se pudo medir: el agente
> de cada entorno lo completa con la «huella» de la sección 4, **en una PR a este archivo**.

---

## 1. Los entornos que existen

| # | Entorno | Quién | Sistema | Qué hace ahí |
|---|---|---|---|---|
| A | **PC de jugador / colaborador** | Urek-Mazinoo (y cualquiera) | Windows 11 | jugar, probar en el juego, compilar la DLL, `git push` al fork |
| B | **Sandbox del agente (nube)** | el agente de Urek-Mazinoo | Linux, sin red salvo GitHub de lectura | editar código, correr `servidor/juego.py control`, armar commits y `.bundle` |
| C | **CI de GitHub** | todos | Ubuntu, Python 3.13 | jobs `privado`, `server`, `docker`, `dll` |
| D | **VPS** | el dueño | Linux + Docker | server de **prod** (25900, rama `main`) y de **prueba** (35900, rama `develop`); archivos del launcher y manifiesto firmado |
| E | **Entorno del agente del dueño** | r2beatlatino | Windows 11, en la PC del dueño | revisar PRs, escribir las propias desde un espejo privado (§2.13), publicar releases con la orden del dueño |
| F | **Cliente instalado por el launcher** | cada jugador | Windows | `C:\Game\EDA` (u otra carpeta): lo que realmente juega la gente |

---

## 2. Diferencias que ya nos causaron problemas

### 2.1 Finales de línea (CRLF / LF)
- El repo **mezcla** los dos formatos. Medido en `develop@f2a2862`, sobre 110 archivos de texto:
  **86 en LF, 21 en CRLF y 3 con los dos adentro** (`documentacion/MEDICIONES.md`, `APIS_A_MANO.md`,
  `CODIGO_ROBADO.md`).
- `.gitattributes` obliga LF solo en `*.sh`, `despliegue/*`, `.github/**`. Para el resto, git no normaliza.
- **Qué pasó:** en el sandbox (B) un archivo se reescribió todo en LF y la PR #40 mostró unas 2.400 líneas
  cambiadas que no existían. Y el espejo privado del entorno E exportaba en CRLF (§2.13).
- **Decidido (14-nov, el dueño):** un solo formato para todo el repo. La PR que lo ordena viene aparte y
  cambia esta sección.
- **Regla mientras tanto:** al editar un archivo existente, **conservar los bytes de los finales de
  línea**. Si solo se agrega una sección, se agrega al final sin reescribir el resto.
  - Antes de commitear, hacer `git diff --stat` y compararlo con `git diff --stat --ignore-cr-at-eol`.
    Si los números difieren mucho, hay ruido de finales de línea.
  - En el sandbox, usar `git config core.autocrlf false`.
- `exe/eda_d3d9.ini` y los `.bat` van en **CRLF**, porque los lee Windows.

### 2.2 Codificación de texto
- La consola de Windows (A) muestra los acentos de `git log` como basura (`documentaci├│n`). Es solo
  visual: los commits están bien en UTF-8.
- Archivos que lee el **juego** (`autoexec.cfg`, `.ini`): ANSI/ASCII. No meter acentos ni BOM.
- Archivos del repo (`.py`, `.md`, `.c`): UTF-8 sin BOM.

### 2.3 Cómo llegan los commits a GitHub
- El sandbox (B) **no puede hacer push**: no tiene credenciales, y está bien que sea así. El camino es este:
  1. B crea la rama y los commits y arma un `git bundle`.
  2. El bundle se copia a la PC (A) y un `.bat` corre `git fetch <bundle>` + `git push` al fork. La sesión
     de GitHub la pone el usuario, nunca el agente.
  3. La PR se abre desde el navegador con la sesión del usuario.
- **Trampa:** si se copia a la PC un archivo con el **mismo nombre** que uno anterior, puede quedar el
  contenido viejo. Por eso el primer push de la PR #40 subió solo un commit.
- **Regla:** cada bundle y cada `.bat` llevan un **nombre nuevo** (`eda-dll2.bundle`, `eda-dll3.bundle`, …).
  Después de subir, se verifica el **hash** del tip en el log (`_trabajo\subir_dll.log`) y no se confía en
  que «dijo listo».
- El entorno E sí hace push, con la sesión de GitHub del dueño, a una rama del repo; la PR la aprueba un
  colaborador o la fusiona el dueño.

### 2.4 Git en Windows
- En algunas PCs `git` no está en el PATH. Los `.bat` lo buscan en `Program Files`, `LocalAppData` y
  GitHub Desktop, y si no lo encuentran ofrecen `winget install Git.Git`.
- Si `git push` pide iniciar sesión, **el usuario completa el aviso**. El agente nunca pide contraseña,
  código ni token por chat.

### 2.5 Smart App Control / Control inteligente de aplicaciones (Windows 11)
- Bloquea una **DLL nueva sin firma** con el error `0xc0e90002` (MEDICIONES §57). La `d3d9.dll` anterior
  (`12f30dbe…`) cargaba porque Windows ya la conocía; cada DLL nueva tiene otra huella.
- Con Smart App Control **activado** (A o F), la DLL nueva no carga. Con él **desactivado**, sí. Una vez
  desactivado, Windows no deja volver a activarlo sin reinstalar.
- **Consecuencia:** «a mí me anda» no prueba nada si el que prueba tiene Smart App Control apagado.
- ⚠ **Estado de hoy:** la release 2026.11.14 entrega la DLL de la PR #40 (`8c577791…`), nueva y sin firma.
  **Nadie la midió con Smart App Control prendido** (en el entorno E está apagado).
- **Decidido (14-nov, el dueño):** por ahora se publica sin firma, y a quien lo tenga prendido se le
  sugiere apagarlo (no es el antivirus: el antivirus queda como está). La **firma** queda como mejora.
  Propuesta: SignPath Foundation desde GitHub Actions; la solicitud la hace el dueño. (Sin medir: si
  aceptan un proyecto que también reparte un exe de terceros. Preguntarlo antes de armar el flujo.)

### 2.6 Qué cliente se está probando
- El jugador real usa el **cliente del launcher** (F):
  - `EDA_limpio.exe`, md5 `0799387e…`
  - `exe/d3d9.dll`
  - `eda_d3d9.ini`
- `py jugar.py` a secas usa otra copia (`_trabajo\juego\`): el mismo `EDA_limpio.exe`, pero **con Frida**.
  `py jugar.py --original` abre el exe de 2009 (`f0b12e6c…`, con ASProtect), ajustado en memoria.
- **Regla:** se prueba como juega la gente: `py jugar.py --como-launcher` (mismo exe y misma DLL, sin
  Frida). Los scripts Frida de botones, inventario y foco solo se inyectan con `EDA_FRIDA_MEJORAS=1`.
- La clave AES del juego es el md5 del exe, así que **una PR no parchea el exe nunca**. Todo arreglo va en
  la DLL (`documentacion/POR_QUE_LA_DLL.md`).
  - La única excepción es una **mudanza de exe que anuncia el dueño**: server, launcher y jugadores
    cambian el mismo día. Hoy hay una preparada y sin fecha: la PR #29 (borrador), el exe sin ASProtect.

### 2.7 Archivos que son del jugador, no del repo
- El launcher **no sobrescribe** `autoexec.cfg` ni `eda_d3d9.ini`.
- **Regla (decidida el 14-nov, la misma en `POR_QUE_LA_DLL.md` y en el LEEME de la DLL):** toda función
  nueva de la DLL viene **prendida por defecto en el código** (`leer_ajustes`), con su clave para
  apagarla. Y **antes de publicarla a los jugadores, se mide en dos PCs, una que no sea la del autor.**
  Lo que hoy figura apagado en la tabla del LEEME de la DLL sigue como está.

### 2.8 Python
- **A:** se invoca con `py` (lanzador de Windows). La versión depende de cada PC **(a confirmar: `py --version`)**.
- **C y D:** `python` 3.13 (Docker usa `python:3.13-slim`).
- **E:** `py`, 3.13.
- **B:** `python3`; la versión es la del sandbox **(a confirmar)**.
- **Regla:** el código del server no debe usar nada más nuevo que 3.12. Probar siempre con
  `python servidor/juego.py control`, que tiene que terminar en `→ TODO BIEN`.
- Dependencias: `frida>=16` y `pycryptodome>=3.15`. Las herramientas de investigación (`capstone`,
  `pefile`, `unicorn`, …) son opcionales.

### 2.9 Compilador de la DLL
- **Zig 0.16.0**, siempre la misma versión:
  - en Windows: `_trabajo/zig/zig-x86_64-windows-0.16.0/zig.exe` (lo baja `herramientas/dll_d3d9/bajar_zig.py`);
  - en CI: Zig 0.16.0 para Linux.
- **La compilación es reproducible.** Medido con la PR #40: la misma fuente dio **el mismo md5**
  (`8c577791…`) en A, en C (Linux) y en E. El job `dll` muestra los dos md5 en el resumen: al revisar una
  PR que toca la DLL, **tienen que ser iguales**. Si no lo son, la `exe/d3d9.dll` de esa PR no salió de su `.c`.
- El que llega a los jugadores es **`exe/d3d9.dll` del repo**, medido en el juego.

### 2.10 Rutas
- **A:**
  - repo en la carpeta de documentos del usuario (`Documents\EDA\repo`);
  - copia de trabajo en `repo\_trabajo\juego`;
  - cliente del launcher en `C:\Game\EDA`.
- **B:** el repo se clona en `/tmp/...`. Las rutas de Windows no existen ahí.
- **Regla:** nunca escribir en el repo rutas personales (la carpeta de un usuario de Windows o de Linux),
  IPs reales, MACs ni correos. El job `privado` falla si aparecen. Usar `192.0.2.x`, `198.51.100.x`,
  `203.0.113.x` y MACs `02:00:00:00:00:0N`.

### 2.11 Red del jugador
- Algunos jugadores están detrás de **NAT simétrico**. El camino UDP directo falla y la sala muestra ping
  **-1000 ms** (`documentacion/RED_P2P.md`).
- Una prueba de sala que anda entre dos PCs de la misma casa **no** prueba que ande entre jugadores
  reales. Hay que anotar el tipo de NAT de quien prueba (pendiente: relay con dos puertos).

### 2.12 Hora
- Las PCs de quienes colaboran están en su hora local. CI, VPS y sandbox: **UTC**.
- En `MEDICIONES.md` y en los logs, escribir la fecha con zona o en UTC.

### 2.13 El espejo privado del entorno E
- El agente del dueño no edita este repo directo. Trabaja en una copia privada (ahí quedan las notas y lo
  que no se publica) y la pasa con dos herramientas: una trae lo fusionado en `develop`, la otra arma la
  copia limpia que va a la rama de la PR.
- **Trampa 1:** esa copia limpia se arma **desde cero**. Una carpeta nueva en la raíz que la herramienta no
  conozca, una PR del entorno E la **borraría** (casi pasa con `paneles/` y con `servidor/*.json`).
  **Regla:** si una PR agrega una carpeta nueva en la raíz, o un tipo de archivo nuevo en una carpeta que
  ya existe, se dice en la descripción.
- **Trampa 2:** el espejo exportaba en CRLF. De ahí vino parte de la mezcla de §2.1.

---

## 3. Lo que es igual en todos (no cambiar sin acuerdo)

- **Ramas:** tu rama → PR a `develop` (server de prueba, 35900) → PR `develop → main` (prod, 25900). Los
  dos servers se actualizan solos a los pocos minutos de fusionar.
- **Aprobaciones:**
  - para `develop`: pruebas en verde + 1 aprobación que no sea del autor;
  - para `main`: pruebas en verde + 2 aprobaciones, o la del dueño.
- **Qué no se sube nunca:** `_trabajo/`, cuentas, logs, capturas, el cliente de Softnyx. Excepciones:
  `exe/EDA_limpio.exe` y `exe/d3d9.dll`.
- **Publicar a jugadores** = con la orden del dueño, se suben los archivos al VPS y se firma el manifiesto
  con `firmar_manifiesto.py` (Ed25519). La clave en uso **solo** está en el VPS; hay una de reserva, fuera
  del VPS, en poder del dueño. El launcher acepta las dos.
- **Una DLL nueva no llega a nadie por fusionar la PR:** llega con una release del cliente.
- **Direcciones del exe:** las de `documentacion/` y `eda_d3d9.c` valen para los dos exes. Cada parche
  nuevo verifica sus bytes con `firma()` antes de escribir.

---

## 4. Huella de entorno (cada agente la corre y la pega al empezar)

Cada agente corre esto al empezar una tarea y lo pega en la PR o en el mensaje de traspaso. Con eso
el otro agente sabe desde dónde se hizo el trabajo.

**Windows (cmd):**
```bat
ver
py --version
git --version
git config --get core.autocrlf
git -C repo rev-parse --short HEAD
git -C repo status --short | find /c /v ""
certutil -hashfile exe\d3d9.dll MD5 | findstr /v ":"
certutil -hashfile exe\EDA_limpio.exe MD5 | findstr /v ":"
powershell -c "(Get-MpComputerStatus).SmartAppControlState"
```

**Linux (sandbox, CI, VPS):**
```bash
uname -sr; python3 --version; git --version
git config --get core.autocrlf
git rev-parse --short HEAD; git status --short | wc -l
md5sum exe/d3d9.dll exe/EDA_limpio.exe
zig version 2>/dev/null
```

Formato para pegar:
```
ENTORNO: <A/B/C/D/E/F> · <quién>
SO: …  Python: …  git: …  autocrlf: …
repo: <rama>@<hash>  (archivos sin commitear: N)
d3d9.dll md5: …   EDA_limpio.exe md5: …
Smart App Control: On/Off/Evaluation   NAT: <normal/simétrico/desconocido>
```

### 4.1 Huellas medidas

```
ENTORNO: E · agente del dueño                                   (medido 2026-11-14 UTC)
SO: Windows 11 (10.0.26200)  Python: 3.13 (py)  git: 2.55 para Windows  autocrlf: false en el clon
repo: develop@f2a2862  (archivos sin commitear: 0)
d3d9.dll md5: 8c57779190b02e26301bd237f06aa09a   EDA_limpio.exe md5: 0799387e23cadd355888bd712143f2d5
Smart App Control: Off   NAT: normal (deducción: el directo anduvo contra una laptop por LTE)
Zig: 0.16.0

ENTORNO: D · VPS                                                (medido 2026-11-14 21:34 UTC)
SO: Linux (Ubuntu)  Python: 3.13 en el contenedor (python:3.13-slim)  git: 2.53  autocrlf: sin poner
prod: main@a28fe16 · prueba: develop@f2a2862 · reloj en UTC
exe/d3d9.dll en el checkout de prod: 12f30dbe… (main todavía no tiene la PR #40)
lo que reciben los jugadores por el launcher: release 2026.11.14, d3d9.dll 8c577791…, EDA_limpio.exe 0799387e…
```

---

## 5. Protocolo de traspaso entre agentes

1. **Antes de empezar:** hacer `git fetch` y partir de `origin/develop` actualizado; pegar la huella (sección 4).
2. **Al terminar cada paso:** anotar **el hash** del commit, no solo «ya lo subí».
3. **Al abrir una PR**, la descripción incluye:
   - **qué cambia**;
   - **qué se comprobó y en qué entorno**, por ejemplo «en el juego, entorno A, Smart App Control Off»;
   - **qué queda pendiente**;
   - si agrega una **carpeta nueva en la raíz** (§2.13).
4. **Al verificar el trabajo de otro agente:**
   - comparar el diff con `--ignore-cr-at-eol` (sección 2.1);
   - comparar el md5 de la DLL con el que figura en la PR, y con el que compiló el job `dll` (§2.9);
   - revisar que el job `dll` esté en verde.
5. **Estado compartido:** el avance general vive en `README.md` (las piezas) y en este archivo (los
   entornos). Los hallazgos técnicos medidos van a `documentacion/MEDICIONES.md` como una sección nueva
   al final, con número.
6. **Nunca:**
   - pedir credenciales por chat;
   - fusionar la PR propia (salvo el dueño);
   - publicar al VPS sin el dueño;
   - parchear el exe (salvo la mudanza de §2.6).

---

## 6. Pendientes para cerrar este documento

- [x] El agente del dueño completa su fila (E) y la huella del VPS (D). → §1, §2.13, §4.1
- [ ] Confirmar la versión de Python en la PC de cada colaborador (A) y en el sandbox (B).
- [ ] Ordenar los finales de línea de todo el repo con `.gitattributes`: **decidido**, viene en una PR
      aparte (un solo diff grande, una sola vez).
- [ ] **Medir la DLL publicada (`8c577791…`) con Smart App Control prendido.** Solo se puede en una PC
      que todavía lo tenga prendido. ¿El entorno A lo tiene?
- [ ] Firma de la DLL (SignPath) para que Smart App Control deje de ser una diferencia entre jugadores.
- [ ] Propuesta: que el job `dll` **falle** si el md5 de lo compilado no es el de `exe/d3d9.dll`, en vez
      de solo mostrarlos (la compilación es reproducible, §2.9).
- [ ] Saber, de los jugadores (F), quién tiene Smart App Control prendido y quién ve -1000 ms en la sala.
