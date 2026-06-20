#!/usr/bin/env python3
"""
PRODEMU 2026 — Agente de carga automática de resultados (fase de grupos).

Lee partidos FINALIZADOS del Mundial desde football-data.org y escribe
los marcadores en Firebase RTDB en /results/{mID}, el mismo path que usa
la web cuando el admin guarda resultados. Nunca pisa resultados ya cargados.

Uso:
  FOOTBALL_DATA_TOKEN=xxx python3 actualizar_resultados.py
  FOOTBALL_DATA_TOKEN=xxx DRY_RUN=1 python3 actualizar_resultados.py   # solo muestra, no escribe

Solo usa la librería estándar de Python (no requiere pip install).
"""

import json
import os
import sys
import unicodedata
import urllib.request

FIREBASE_URL = "https://prodemu-default-rtdb.firebaseio.com"
# Clave web pública del proyecto (la misma que está en index.html). No es secreta.
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "AIzaSyAk9rmCeKgYIMv7Fngul6RPv7r09-OE0YA")
API_URL = "https://api.football-data.org/v4/competitions/WC/matches?status=FINISHED"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN", "") not in ("", "0", "false")


def norm(name):
    """Normaliza un nombre: minúsculas, sin acentos, sin sufijos comunes."""
    s = unicodedata.normalize("NFD", name.lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    for suf in (" national football team",):
        s = s.replace(suf, "")
    return s


# ── Mapa: nombre en la API (inglés, normalizado) → nombre PRODEMU ──
# Incluye variantes habituales de football-data.org / FIFA.
TEAM_MAP_RAW = {
    # Grupo A
    "mexico": "México", "south africa": "Sudáfrica",
    "korea republic": "Corea del Sur", "south korea": "Corea del Sur",
    "czechia": "Rep. Checa", "czech republic": "Rep. Checa",
    # Grupo B
    "canada": "Canadá",
    "bosnia and herzegovina": "Bosnia y Herzegovina",
    "bosnia-herzegovina": "Bosnia y Herzegovina", "bosnia": "Bosnia y Herzegovina",
    "qatar": "Qatar", "switzerland": "Suiza",
    # Grupo C
    "brazil": "Brasil", "morocco": "Marruecos",
    "haiti": "Haití", "scotland": "Escocia",
    # Grupo D
    "united states": "Estados Unidos", "usa": "Estados Unidos",
    "paraguay": "Paraguay", "australia": "Australia",
    "turkey": "Turquía", "turkiye": "Turquía",
    # Grupo E
    "germany": "Alemania", "curacao": "Curazao",
    "ivory coast": "Costa de Marfil", "cote d'ivoire": "Costa de Marfil",
    "ecuador": "Ecuador",
    # Grupo F
    "netherlands": "Países Bajos", "japan": "Japón",
    "sweden": "Suecia", "tunisia": "Túnez",
    # Grupo G
    "belgium": "Bélgica", "egypt": "Egipto",
    "iran": "Irán", "ir iran": "Irán", "new zealand": "Nueva Zelanda",
    # Grupo H
    "spain": "España", "cape verde": "Cabo Verde", "cabo verde": "Cabo Verde",
    "cape verde islands": "Cabo Verde",
    "saudi arabia": "Arabia Saudita", "uruguay": "Uruguay",
    # Grupo I
    "france": "Francia", "senegal": "Senegal",
    "iraq": "Irak", "norway": "Noruega",
    # Grupo J
    "argentina": "Argentina", "algeria": "Argelia",
    "austria": "Austria", "jordan": "Jordania",
    # Grupo K
    "portugal": "Portugal", "dr congo": "RD Congo", "congo dr": "RD Congo",
    "democratic republic of the congo": "RD Congo",
    "uzbekistan": "Uzbekistán", "colombia": "Colombia",
    # Grupo L
    "england": "Inglaterra", "croatia": "Croacia",
    "ghana": "Ghana", "panama": "Panamá",
}
TEAM_MAP = {norm(k): v for k, v in TEAM_MAP_RAW.items()}


# ── Fixture PRODEMU: los 72 partidos de fase de grupos (mismos IDs que index.html) ──
PARTIDOS = [
    ("m1", "México", "Sudáfrica"), ("m2", "Corea del Sur", "Rep. Checa"),
    ("m3", "Rep. Checa", "Sudáfrica"), ("m4", "México", "Corea del Sur"),
    ("m5", "Sudáfrica", "Corea del Sur"), ("m6", "Rep. Checa", "México"),
    ("m7", "Canadá", "Bosnia y Herzegovina"), ("m8", "Qatar", "Suiza"),
    ("m9", "Suiza", "Bosnia y Herzegovina"), ("m10", "Canadá", "Qatar"),
    ("m11", "Suiza", "Canadá"), ("m12", "Bosnia y Herzegovina", "Qatar"),
    ("m13", "Brasil", "Marruecos"), ("m14", "Haití", "Escocia"),
    ("m15", "Escocia", "Marruecos"), ("m16", "Brasil", "Haití"),
    ("m17", "Marruecos", "Haití"), ("m18", "Brasil", "Escocia"),
    ("m19", "Estados Unidos", "Paraguay"), ("m20", "Australia", "Turquía"),
    ("m21", "Estados Unidos", "Australia"), ("m22", "Turquía", "Paraguay"),
    ("m23", "Paraguay", "Australia"), ("m24", "Turquía", "Estados Unidos"),
    ("m25", "Alemania", "Curazao"), ("m26", "Costa de Marfil", "Ecuador"),
    ("m27", "Alemania", "Costa de Marfil"), ("m28", "Ecuador", "Curazao"),
    ("m29", "Curazao", "Costa de Marfil"), ("m30", "Ecuador", "Alemania"),
    ("m31", "Países Bajos", "Japón"), ("m32", "Suecia", "Túnez"),
    ("m33", "Países Bajos", "Suecia"), ("m34", "Túnez", "Japón"),
    ("m35", "Japón", "Suecia"), ("m36", "Túnez", "Países Bajos"),
    ("m37", "Bélgica", "Egipto"), ("m38", "Irán", "Nueva Zelanda"),
    ("m39", "Bélgica", "Irán"), ("m40", "Nueva Zelanda", "Egipto"),
    ("m41", "Egipto", "Irán"), ("m42", "Nueva Zelanda", "Bélgica"),
    ("m43", "España", "Cabo Verde"), ("m44", "Arabia Saudita", "Uruguay"),
    ("m45", "España", "Arabia Saudita"), ("m46", "Uruguay", "Cabo Verde"),
    ("m47", "Cabo Verde", "Arabia Saudita"), ("m48", "Uruguay", "España"),
    ("m49", "Francia", "Senegal"), ("m50", "Irak", "Noruega"),
    ("m51", "Francia", "Irak"), ("m52", "Noruega", "Senegal"),
    ("m53", "Noruega", "Francia"), ("m54", "Senegal", "Irak"),
    ("m55", "Argentina", "Argelia"), ("m56", "Austria", "Jordania"),
    ("m57", "Argentina", "Austria"), ("m58", "Jordania", "Argelia"),
    ("m59", "Argelia", "Austria"), ("m60", "Jordania", "Argentina"),
    ("m61", "Portugal", "RD Congo"), ("m62", "Uzbekistán", "Colombia"),
    ("m63", "Portugal", "Uzbekistán"), ("m64", "Colombia", "RD Congo"),
    ("m65", "Colombia", "Portugal"), ("m66", "RD Congo", "Uzbekistán"),
    ("m67", "Inglaterra", "Croacia"), ("m68", "Ghana", "Panamá"),
    ("m69", "Inglaterra", "Ghana"), ("m70", "Panamá", "Croacia"),
    ("m71", "Croacia", "Ghana"), ("m72", "Panamá", "Inglaterra"),
]


def http_json(url, headers=None, method="GET", data=None):
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {e.reason} → {body[:300]}") from None


def firebase_anon_token():
    """Inicia sesión anónima en Firebase Auth y devuelve un idToken.
    Las reglas de la base ahora exigen autenticación (auth != null), así que
    necesitamos un token para poder leer y escribir en /results."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    try:
        resp = http_json(url, method="POST", data={"returnSecureToken": True})
        return resp.get("idToken")
    except RuntimeError as e:
        print(f"❌ No se pudo autenticar con Firebase: {e}")
        return None


def traducir(nombre_api):
    return TEAM_MAP.get(norm(nombre_api))


def procesar(api_matches, actuales):
    """Devuelve {mid: {home, away}} con los resultados nuevos. Función pura, testeable."""
    finalizados = {}
    sin_mapear = set()
    for m in api_matches:
        ft = m.get("score", {}).get("fullTime", {})
        if ft.get("home") is None:
            continue
        h, a = traducir(m["homeTeam"]["name"]), traducir(m["awayTeam"]["name"])
        if h is None:
            sin_mapear.add(m["homeTeam"]["name"])
        if a is None:
            sin_mapear.add(m["awayTeam"]["name"])
        if h and a:
            finalizados[frozenset((h, a))] = (ft["home"], ft["away"], h)

    for nombre in sorted(sin_mapear):
        print(f"⚠️  Equipo de la API sin mapear (agregar a TEAM_MAP): {nombre!r}")

    nuevos = {}
    for mid, home, away in PARTIDOS:
        if mid in actuales:
            continue
        dato = finalizados.get(frozenset((home, away)))
        if not dato:
            continue
        gh, ga, api_home = dato
        nuevos[mid] = {"home": gh, "away": ga} if api_home == home else {"home": ga, "away": gh}
    return nuevos


def main():
    if not TOKEN:
        sys.exit("❌ Falta la variable de entorno FOOTBALL_DATA_TOKEN")

    api = http_json(API_URL, headers={"X-Auth-Token": TOKEN})
    api_matches = api.get("matches", [])
    print(f"API: {len(api_matches)} partidos finalizados informados")
    for m in api_matches:
        print(f"  · {m['homeTeam']['name']} vs {m['awayTeam']['name']} — {m['score']['fullTime']}")

    token = firebase_anon_token()
    auth_q = f"?auth={token}" if token else ""
    if not token:
        print("⚠️  Sin token de Firebase: si las reglas exigen auth, las operaciones fallarán.")

    actuales = http_json(f"{FIREBASE_URL}/results.json{auth_q}") or {}
    print(f"Firebase: {len(actuales)} resultados ya cargados")

    nuevos = procesar(api_matches, actuales)

    if not nuevos:
        print("Sin novedades.")
        return

    for mid, r in sorted(nuevos.items(), key=lambda x: int(x[0][1:])):
        eq = next(p for p in PARTIDOS if p[0] == mid)
        print(f"{'[DRY-RUN] ' if DRY_RUN else '✅ '}{mid}: {eq[1]} {r['home']} - {r['away']} {eq[2]}")

    if DRY_RUN:
        print("DRY_RUN activo: no se escribió nada en Firebase.")
    else:
        try:
            http_json(f"{FIREBASE_URL}/results.json{auth_q}", method="PATCH", data=nuevos)
            print(f"✅ Escritos {len(nuevos)} resultados nuevos en Firebase.")
        except RuntimeError as e:
            print(f"❌ ERROR al escribir en Firebase: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
