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
PVP_CUENTA     = 5          -- segundos de cuenta regresiva
PVP_LIMITE_MS  = 300000     -- 5 min: fin por tiempo
PVP_DIAG       = true       -- mostrar en pantalla la vida de los dos cada 2 s (manager:GetHP)
PVP_GRUPOS     = false      -- T04: SetEntityGroup (dos_clientes.py recursos instalar --grupos lo prende)
PVP_TELEPORT   = true       -- false (--sin-teleport): quedan donde aparecen, juntos (para las pruebas automaticas)

Data = {}                   -- (el original define aca sus NPC; esta arena no crea ninguno)

PvP = {fase = "carga", vivos = -1, max_vivos = 0, cuenta = 0, fin = false}

----------------------------------------------------------------------------------------------------------------------
-- utilidades

function PvP_Msg(texto, ms)
	-- [SIN VERIFICAR] ShowTestMsg: firma de chapter1_11_e.lua (comentada): ("texto", 4000, 0xffffffff)
	pcall(scenario.ShowTestMsg, scenario, texto, ms or 3000, 0xffffffff)
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
function	PvP_Teleport()
	PvP_InformarIDs()
	local ids = PvP_Jugadores()
	for i = 1, #ids do
		if (PVP_TELEPORT and PVP_MARCAS[i] ~= nil) then
			scenario:TeleportToMarker(ids[i], PVP_MARCAS[i])
		end
	end
	PvP.fase = "teleport"
	PvP_Msg("ARENA PvP: " .. #ids .. " jugadores. Teletransporte a " .. PVP_MARCAS[1] .. " / " .. PVP_MARCAS[2], 3000)
	if (PVP_GRUPOS) then
		scenario:InsertFunction("PvP_Grupos", 500)
	end
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
	table.sort(ids)
	scenario:SetEntityGroup(ids[1], 1)
	scenario:SetEntityGroup(ids[2], PVP_GRUPO_J2)
	PvP_Msg("PVP_GRUPOS: id " .. tostring(ids[1]) .. " -> grupo 1, id " .. tostring(ids[2]) .. " -> grupo " .. PVP_GRUPO_J2, 4000)
	scenario:InsertFunction("PvP_GruposHecho", 0)    -- aviso al server: el cambio se pidio
	return 1
end

function	PvP_GruposHecho()	return 1	end

----------------------------------------------------------------------------------------------------------------------
-- cuenta regresiva: una funcion que se vuelve a agendar cada 1000 ms (patron InsertFunction de los originales)

function	PvP_Cuenta()
	if (PvP.cuenta > 0) then
		PvP_Msg("Duelo en " .. PvP.cuenta, 900)
		PvP.cuenta = PvP.cuenta - 1
		scenario:InsertFunction("PvP_Cuenta", 1000)
		return 1
	end
	PvP.fase = "pelea"
	PvP_Msg("YA! (limite " .. (PVP_LIMITE_MS / 1000) .. " s)", 2000)
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
		PvP_Terminar("Desconexion: queda " .. tostring(n) .. " jugador")
		return 1
	end
	if (vivos > PvP.max_vivos) then
		PvP.max_vivos = vivos
	end
	-- con 0 "todavia no hay nadie" (chapter1_11_e.lua:340-343): solo se cierra despues de haber visto 2 vivos
	if (PvP.max_vivos >= 2 and vivos >= 0 and vivos <= 1) then
		PvP_Terminar("Fin del duelo: vivos " .. vivos)
		return 1
	end
	return 0
end

function	PvP_Limite()
	if (not PvP.fin) then
		PvP_Terminar("Fin por tiempo")
	end
	return 1
end

----------------------------------------------------------------------------------------------------------------------
-- diagnostico en pantalla: la vida de cada jugador segun ESTE cliente.
-- [SIN VERIFICAR] manager:GetHP(id) con un jugador: el original lo usa con un NPC (chapter1_1_e.lua:421)

function	PvP_Diag()
	if (PvP.fin) then
		return 1
	end
	local ids = PvP_Jugadores()
	local t = "[" .. PvP.fase .. "] vivos " .. tostring(PvP.vivos)
	for i = 1, #ids do
		local ok, hp = pcall(manager.GetHP, manager, ids[i])
		t = t .. " | J" .. i .. " id " .. tostring(ids[i]) .. " HP " .. (ok and tostring(hp) or "?")
	end
	PvP_Msg(t, 1900)
	scenario:InsertFunction("PvP_Diag", 2000)
	return 1
end

----------------------------------------------------------------------------------------------------------------------
-- fin controlado: como el original (chapter1_1_e.lua:457 y :464-467): mensaje, 5 s, OnEnd -> SendEvent (0x1064)

function	PvP_Terminar(texto)
	PvP.fin = true
	PvP.fase = "fin"
	PvP_Msg(texto .. ". Fin de la stage en 5 s", 4500)
	scenario:InsertFunction("OnEnd", 5000)
end

function	OnEnd()
	scenario:SendEvent()
	return 1
end
