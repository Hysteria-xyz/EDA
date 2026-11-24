-- ARENA PvP EXPERIMENTAL (EDA_pvp) -- NO es un archivo del juego original.
-- Reemplaza EN MEMORIA data\scenario\easy\chapter1_1_e.lua (stage 1011, Easy, mapa Maps\Chapter1\Chapter1_1.dat)
-- SOLO en las instalaciones de prueba (EDA_pvp\A y \B), por la carpeta suelta de la d3d9.dll
-- (herramientas/dll_d3d9/eda_traduccion.c, tr_mi_open l.470-490). Data.dat no se toca.
--
-- Solo usa funciones registradas en EDA_limpio.exe (cadenas en 0x49E9xx-0x49EFxx) y SOLO como las usan los
-- guiones originales; cada uso cita de donde sale. Las que no tienen ningun uso original van con pcall y estan
-- marcadas [SIN VERIFICAR]. Texto solo ASCII (el juego lee los .lua en la codificacion coreana).
--
-- Lo observable desde afuera:
--   * cada scenario:InsertFunction("Nombre", ms) del master llega al server como 0x105C tipo 0 con el nombre y
--     los ms (PROTOCOLO.md 5.11: "OnTrigger_01" con 1000, "MessageTrigger_01" con 1500 = las llamadas de
--     chapter1_1_e.lua:167 y :191). Con EDA_LOG_HEX=1 el server.log muestra el cuerpo. Por eso cada fase tiene
--     una funcion con nombre propio (PvP_*), y la cantidad de vivos va en el NOMBRE (PvP_Vivos0/1/2).
--   * scenario:ShowTestMsg("texto", ms, color) en la pantalla [SIN VERIFICAR: registrada en el exe 0x49EE14,
--     solo aparece comentada en chapter1_11_e.lua (OnSwitch_05)].
--   * scenario:SendEvent() = el 0x1064 del master (fin de la stage; chapter1_1_e.lua:465).

PVP_MARCAS     = {"Player Start 04", "Player Start 08"}   -- Chapter1_1.dat: (1515.7, -790.4, -7482.5) y
                                                          -- (445.8, -790.4, -7215.0): 1102.8 u entre si
-- (25-nov) con equipos (PVP_GRUPOS): cada equipo de SU lado de la sala. Los 8 Player Start del mapa (LEEME.md):
-- x 1515.7 / 1248.2 (04, 05, 03, 06) = lado ROJO (numero par); x 445.8 / 713.3 (08, 02, 07, 01) = lado AZUL
-- (impar). El primero de cada lista es el de PVP_MARCAS: el 1 vs 1 queda igual que antes.
PVP_MARCAS_EQUIPO = {
	[1] = {"Player Start 04", "Player Start 05", "Player Start 03", "Player Start 06"},
	[2] = {"Player Start 08", "Player Start 02", "Player Start 07", "Player Start 01"},
}
PVP_CUENTA     = 5          -- segundos de cuenta regresiva
PVP_LIMITE_MS  = 300000     -- 5 min: fin por tiempo
PVP_DIAG       = true       -- cada 2 s, la vida de cada jugador (manager:GetHP) al server cuando cambia (PvP_HP_*)
PVP_DEPURAR    = false      -- true: ademas, los textos de depuracion en pantalla (ShowTestMsg; tapan los del jugador)
PVP_GRUPOS     = false      -- T04: SetEntityGroup (dos_clientes.py recursos instalar --grupos lo prende)
PVP_TELEPORT   = true       -- false (--sin-teleport): quedan donde aparecen, juntos (para las pruebas automaticas)

Data = {}                   -- (el original define aca sus NPC; esta arena no crea ninguno)

PvP = {fase = "carga", vivos = -1, max_vivos = 0, cuenta = 0, fin = false}

----------------------------------------------------------------------------------------------------------------------
-- utilidades

function PvP_Msg(texto, ms)
	-- ShowTestMsg: firma de chapter1_11_e.lua (comentada): ("texto", 4000, 0xffffffff).
	-- MEDIDO 25-nov (sesion 20261124-171402, fotos): dibuja en el MISMO cuadro de mensajes que ShowMsg, asi que el
	-- texto de depuracion tapaba la cuenta regresiva. Solo con PVP_DEPURAR; lo que ve el jugador va por PvP_Texto.
	if (PVP_DEPURAR) then
		pcall(scenario.ShowTestMsg, scenario, texto, ms or 3000, 0xffffffff)
	end
end

-- lo que ve el jugador: ShowMsg(INDEX, ms, color) como todos los originales (chapter1_11_e.lua:163, "4000,
-- 0xffffffff"). Los INDEX 1180-1190 son de la arena (herramientas/pvp/arena/textos_arena.xml), que
-- dos_clientes.py agrega a chapter1_string.xml: libres en el bloque Chapter 1-1 (1101-1109).
PVP_TXT = {preparar = 1180, cuenta = 1180, pelea = 1186, fin = 1187, tiempo = 1188, desconexion = 1189, equipo = 1190}
function PvP_Texto(indice, ms)
	pcall(scenario.ShowMsg, scenario, indice, ms or 4000, 0xffffffff)
end

-- los jugadores presentes. TeleportAllPlayers (chapter1_14_e.lua:997-1015) recorre GetPlayerID(i) DESDE 1; el exe
-- lee un u8 de la lista CScenario+0x90 (PVP_SETENTITYGROUP.md, 0x62A9A0). ⚠ MEDIDO 24-nov: el ID de ENTIDAD 0 es un
-- jugador (rui) — no se descarta. MEDIDO (sesion 20261124-064447): GetPlayerID(0..4) = -1, 1, -1, 0, -1 con kai y
-- rui en la sala: un lugar vacio da -1 (no 0xffffffff). Se recorre 0..8 y se descartan nil, -1, 0xffffffff.
function PvP_Jugadores()
	local ids, visto = {}, {}
	for i = 0, 8 do
		local id = scenario:GetPlayerID(i)
		-- (medido 24-nov: el vacio llega como -1 en un cliente y como 4294967295 en el otro; un ID de jugador es chico)
		if (id ~= nil and id >= 0 and id < 65536 and not visto[id]) then
			visto[id] = true
			ids[#ids + 1] = id
		end
	end
	return ids
end

-- avisa al server (0x105C tipo 0, con el NOMBRE) que devuelve GetPlayerID(i) para i = 0..4: «PvP_P<i>_<id>»
function PvP_InformarIDs()
	for i = 0, 4 do
		local id = scenario:GetPlayerID(i)
		local nombre = "PvP_P" .. i .. "_" .. ((id == nil) and "nil" or string.format("%d", id))
		_G[nombre] = function() return 1 end
		scenario:InsertFunction(nombre, 0)
	end
end

-- cuantos vivos, con la guarda del original (chapter1_11_e.lua:340-343: con 0 todavia no hay nadie)
function PvP_Vivos()
	return scenario:GetAlivePlayerNum()
end

----------------------------------------------------------------------------------------------------------------------
-- arranque: como el original (chapter1_1_e.lua:145-149), sin briefing ni monstruos

function	Initialize(server_random)
	scenario:InitPlayGame("Player Start")          -- chapter1_1_e.lua:146
	scenario:InsertFunction("PvP_Teleport", 3000)   -- InsertFunction(nombre, ms): chapter1_1_e.lua:147, :156
	return 1
end

-- las dos apariciones: TeleportToMarker(PlayerID, "marcador") como TeleportAllPlayers (chapter1_14_e.lua:1010).
-- (Solo el master mueve el mundo: 0x637C25, PVP_ARQUITECTURA.md.) Los de mas de dos quedan donde aparecieron.
-- el equipo de un jugador: 1 = rojo (ID par), 2 = azul (ID impar). Es la regla de la sala (battle_ui.py) y la de
-- PvP_Grupos; los dos clientes llegan a lo mismo porque depende del ID y no del orden de la lista.
function PvP_Equipo(id)
	return ((id % 2) == 0) and 1 or 2
end

-- el marcador de cada ID. Sin equipos: el orden de la lista (como el 24-nov). Con equipos: el lado del equipo, en
-- orden de ID dentro del equipo (la lista se ordena: los dos clientes eligen igual).
function PvP_Marcas(ids)
	local m = {}
	if (not PVP_GRUPOS) then
		for i = 1, #ids do
			m[ids[i]] = PVP_MARCAS[i]
		end
		return m
	end
	-- orden a mano (insercion): string.format ya se uso en vivo, la biblioteca table todavia no
	local orden = {}
	for i = 1, #ids do
		local j = #orden
		while (j >= 1 and orden[j] > ids[i]) do
			orden[j + 1] = orden[j]
			j = j - 1
		end
		orden[j + 1] = ids[i]
	end
	local cuantos = {0, 0}
	for i = 1, #orden do
		local e = PvP_Equipo(orden[i])
		cuantos[e] = cuantos[e] + 1
		m[orden[i]] = PVP_MARCAS_EQUIPO[e][cuantos[e]]
	end
	return m
end

function	PvP_Teleport()
	PvP_InformarIDs()
	local ids = PvP_Jugadores()
	local marcas = PvP_Marcas(ids)
	local t = ""
	for i = 1, #ids do
		if (PVP_TELEPORT and marcas[ids[i]] ~= nil) then
			scenario:TeleportToMarker(ids[i], marcas[ids[i]])
			t = t .. " id " .. tostring(ids[i]) .. "->" .. string.sub(marcas[ids[i]], -2)
		end
	end
	PvP.fase = "teleport"
	PvP_Msg("ARENA PvP: " .. #ids .. " jugadores. Teletransporte:" .. t, 3000)
	PvP_Texto(PVP_TXT.preparar, 2900)
	-- (25-nov) los grupos se cambian AL TERMINAR la cuenta (PvP_Cuenta), no aca: mientras todos comparten el grupo
	-- 1 los golpes entre jugadores no hacen dano (T01, medido), asi que la cuenta regresiva es tiempo protegido.
	PvP.cuenta = PVP_CUENTA
	scenario:InsertFunction("PvP_Cuenta", 3000)
	if (PVP_DIAG) then
		scenario:InsertFunction("PvP_Diag", 2000)
	end
	return 1
end

----------------------------------------------------------------------------------------------------------------------
-- T04: grupos. NO se llama nada mientras PVP_GRUPOS = false (dos_clientes.py recursos instalar --grupos lo prende).
-- Firma verificada (PVP_SETENTITYGROUP.md): scenario:SetEntityGroup(idEntidad, grupo), dos numeros pasados a entero
-- (despachador 0x62F820, impl. 0x6385F0, SOLO el master: +0x168). CEntity::SetGroup 0x560CD0: +0x40 = 1 << (grupo-1),
-- grupo 1..32. Jugadores nacen con 1 (mascara 0x1), los NPC con 2 (CreateNpc(...,2) en los .lua). El filtro de golpes
-- 0x554B8E descarta si atacante.+0x40 & victima.+0x40 != 0. Se deja al J1 en 1 y el J2 pasa al 3 (mascara 0x4: ni
-- del lado del J1 ni del de los NPC). Sale como 0x105C tipo 0x1B y el otro juego lo aplica en 0x6445FE.
PVP_GRUPO_J2 = 3

-- ⚠ MEDIDO 24-nov (sesion 20261124-074413): LOS DOS CLIENTES corren este guion y cada uno ve la lista de IDs en
-- otro orden: A pidio SetEntityGroup(0, 3) y B SetEntityGroup(1, 3); como el cambio se sincroniza, los DOS
-- quedaron en 0x4 = el mismo grupo otra vez, y no hubo dano. Por eso la eleccion tiene que ser la MISMA en los dos:
-- se ordenan los IDs y el menor va al 1 y el mayor al PVP_GRUPO_J2, explicitamente (repetirlo no cambia nada).
function	PvP_Grupos()
	local ids = PvP_Jugadores()
	if (#ids < 2) then
		PvP_Msg("PVP_GRUPOS: hacen falta 2 jugadores (hay " .. #ids .. ")", 3000)
		return 1
	end
	-- (24-nov) EQUIPOS: el ID de entidad de un jugador es su numero de sala (medido) y la sala pinta la fila del
	-- numero par de ROJO y la del impar de AZUL (herramientas/pvp/battle_ui.py): par -> grupo 1, impar -> grupo
	-- PVP_GRUPO_J2. Los del mismo color comparten grupo (no se danan); con dos jugadores es el 1 vs 1 de siempre.
	local t = ""
	for i = 1, #ids do
		local g = (PvP_Equipo(ids[i]) == 1) and 1 or PVP_GRUPO_J2
		scenario:SetEntityGroup(ids[i], g)
		t = t .. " id " .. tostring(ids[i]) .. "->" .. g
	end
	PvP_Msg("PVP_GRUPOS:" .. t, 4000)
	scenario:InsertFunction("PvP_GruposHecho", 0)    -- aviso al server: el cambio se pidio
	return 1
end

function	PvP_GruposHecho()	return 1	end

----------------------------------------------------------------------------------------------------------------------
-- cuenta regresiva: una funcion que se vuelve a agendar cada 1000 ms (patron InsertFunction de los originales)

function	PvP_Cuenta()
	if (PvP.cuenta > 0) then
		PvP_Msg("Duelo en " .. PvP.cuenta, 900)
		if (PvP.cuenta <= 5) then
			PvP_Texto(PVP_TXT.cuenta + 6 - PvP.cuenta, 950)   -- 1181 = "en 5" ... 1185 = "en 1"
		end
		PvP.cuenta = PvP.cuenta - 1
		scenario:InsertFunction("PvP_Cuenta", 1000)
		return 1
	end
	PvP.fase = "pelea"
	if (PVP_GRUPOS) then
		PvP_Grupos()                                   -- recien ahora los jugadores se pueden danar
	end
	PvP_Msg("YA! (limite " .. (PVP_LIMITE_MS / 1000) .. " s)", 2000)
	PvP_Texto(PVP_TXT.pelea, 2000)
	scenario:InsertFunction("PvP_Pelea", 0)          -- un aviso al server: empieza la pelea
	scenario:InsertFunction("PvP_Vigilar", 0)        -- sondeo: devuelve 0 hasta que pasa algo (DoorSwitch_01, :187-196)
	scenario:InsertFunction("PvP_Limite", PVP_LIMITE_MS)
	return 1
end

function	PvP_Pelea()
	return 1
end

----------------------------------------------------------------------------------------------------------------------
-- vigilar vivos y desconexiones; cada cambio de vivos se avisa con un nombre propio (PvP_Vivos0/1/2)

function	PvP_Vivos0()	return 1	end
function	PvP_Vivos1()	return 1	end
function	PvP_Vivos2()	return 1	end
function	PvP_Desconexion()	return 1	end

function	PvP_Vigilar()
	if (PvP.fin) then
		return 1
	end
	local vivos = PvP_Vivos()
	if (vivos ~= PvP.vivos) then
		PvP.vivos = vivos
		if (vivos >= 0 and vivos <= 2) then
			scenario:InsertFunction("PvP_Vivos" .. vivos, 0)
		end
	end
	-- [SIN VERIFICAR] GetPlayerNum(): registrada (exe 0x49EDAC), sin uso en los .lua originales
	local ok, n = pcall(scenario.GetPlayerNum, scenario)
	if (ok and n ~= nil and n < 2) then
		scenario:InsertFunction("PvP_Desconexion", 0)
		PvP_Terminar("Desconexion: queda " .. tostring(n) .. " jugador", PVP_TXT.desconexion)
		return 1
	end
	if (vivos > PvP.max_vivos) then
		PvP.max_vivos = vivos
	end
	-- con 0 "todavia no hay nadie" (chapter1_11_e.lua:340-343): solo se cierra despues de haber visto 2 vivos
	if (PvP.max_vivos >= 2 and vivos >= 0 and vivos <= 1) then
		PvP_Terminar("Fin del duelo: vivos " .. vivos, PVP_TXT.fin)
		return 1
	end
	-- (25-nov) por equipos (2 vs 2 o mas): termina cuando queda en pie un solo equipo, aunque queden 2+ vivos
	if (PVP_GRUPOS and PvP.max_vivos >= 3) then
		local ev = PvP_EquiposVivos(PvP_Jugadores())
		if (ev ~= nil and ev <= 1) then
			PvP_Terminar("Fin del duelo: queda un equipo", PVP_TXT.equipo)
			return 1
		end
	end
	return 0
end

-- cuantos equipos tienen a alguien vivo, con manager:GetHP(id) [SIN VERIFICAR con jugadores: lo mide PvP_Diag].
-- nil si alguna lectura falla o no es un numero: entonces vale solo la regla de GetAlivePlayerNum de arriba.
function PvP_EquiposVivos(ids)
	local vivo = {false, false}
	for i = 1, #ids do
		local ok, hp = pcall(manager.GetHP, manager, ids[i])
		if (not ok or type(hp) ~= "number") then
			return nil
		end
		if (hp > 0) then
			vivo[PvP_Equipo(ids[i])] = true
		end
	end
	return (vivo[1] and 1 or 0) + (vivo[2] and 1 or 0)
end

function	PvP_Limite()
	if (not PvP.fin) then
		PvP_Terminar("Fin por tiempo", PVP_TXT.tiempo)
	end
	return 1
end

----------------------------------------------------------------------------------------------------------------------
-- diagnostico: la vida de cada jugador segun ESTE cliente.
-- [SIN VERIFICAR] manager:GetHP(id) con un jugador: el original lo usa con un NPC (chapter1_1_e.lua:421)
-- (25-nov) como ShowTestMsg no se ve, cada lectura va al server en el NOMBRE de una funcion (como PvP_InformarIDs):
-- «PvP_HP_<id>_<vida>» (o «_err» si la llamada falla), y solo cuando cambia, para no llenar el registro.

PvP.hp_visto = {}
function	PvP_Diag()
	if (PvP.fin) then
		return 1
	end
	local ids = PvP_Jugadores()
	local t = "[" .. PvP.fase .. "] vivos " .. tostring(PvP.vivos)
	for i = 1, #ids do
		local ok, hp = pcall(manager.GetHP, manager, ids[i])
		t = t .. " | J" .. i .. " id " .. tostring(ids[i]) .. " HP " .. (ok and tostring(hp) or "?")
		local valor = (ok and type(hp) == "number") and string.format("%d", hp) or "err"
		if (PvP.hp_visto[ids[i]] ~= valor) then
			PvP.hp_visto[ids[i]] = valor
			local nombre = "PvP_HP_" .. string.format("%d", ids[i]) .. "_" .. valor
			_G[nombre] = function() return 1 end
			scenario:InsertFunction(nombre, 0)
		end
	end
	PvP_Msg(t, 1900)
	scenario:InsertFunction("PvP_Diag", 2000)
	return 1
end

----------------------------------------------------------------------------------------------------------------------
-- fin controlado: como el original (chapter1_1_e.lua:457 y :464-467): mensaje, 5 s, OnEnd -> SendEvent (0x1064)

function	PvP_Terminar(texto, indice)
	PvP.fin = true
	PvP.fase = "fin"
	PvP_Msg(texto .. ". Fin de la stage en 5 s", 4500)
	PvP_Texto(indice or PVP_TXT.fin, 4500)
	scenario:InsertFunction("OnEnd", 5000)
end

function	OnEnd()
	scenario:SendEvent()
	return 1
end
