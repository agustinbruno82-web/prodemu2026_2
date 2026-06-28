#!/usr/bin/env python3
"""
PRODEMU 2026 - Agente de carga automatica de resultados.

FASE 1 (grupos): lee partidos FINALIZADOS del Mundial desde football-data.org
y escribe los marcadores en Firebase RTDB en /results/{mID}.

FASE 2 (eliminatorias): para cada partido de llave finalizado escribe SOLO el
GANADOR (el que pasa de fase) en /f2/results/{mID}, igual que cuando el admin
carga el ganador a mano. El cuadro (que enfrenta a cada equipo) se calcula con
los resultados de grupos + la tabla oficial FIFA 2026 (Anexo C), igual que la web.

Nunca pisa un resultado ya cargado (respeta lo que cargaste a mano).

Uso:
  FOOTBALL_DATA_TOKEN=xxx python3 actualizar_resultados.py
  FOOTBALL_DATA_TOKEN=xxx DRY_RUN=1 python3 actualizar_resultados.py   # solo muestra

Solo usa la libreria estandar de Python.
"""

import json
import os
import sys
import unicodedata
import urllib.request

FIREBASE_URL = "https://prodemu-default-rtdb.firebaseio.com"
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "AIzaSyAk9rmCeKgYIMv7Fngul6RPv7r09-OE0YA")
API_URL = "https://api.football-data.org/v4/competitions/WC/matches?status=FINISHED"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN", "") not in ("", "0", "false")

GROUP_STAGE = "GROUP_STAGE"
KO_STAGES = {"LAST_32", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "FINAL"}


def norm(name):
    s = unicodedata.normalize("NFD", name.lower().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    for suf in (" national football team",):
        s = s.replace(suf, "")
    return s


# Mapa: nombre en la API (ingles, normalizado) -> nombre PRODEMU
TEAM_MAP_RAW = {
    "mexico": "México", "south africa": "Sudáfrica",
    "korea republic": "Corea del Sur", "south korea": "Corea del Sur",
    "czechia": "Rep. Checa", "czech republic": "Rep. Checa",
    "canada": "Canadá",
    "bosnia and herzegovina": "Bosnia y Herzegovina",
    "bosnia-herzegovina": "Bosnia y Herzegovina", "bosnia": "Bosnia y Herzegovina",
    "qatar": "Qatar", "switzerland": "Suiza",
    "brazil": "Brasil", "morocco": "Marruecos",
    "haiti": "Haití", "scotland": "Escocia",
    "united states": "Estados Unidos", "usa": "Estados Unidos",
    "paraguay": "Paraguay", "australia": "Australia",
    "turkey": "Turquía", "turkiye": "Turquía",
    "germany": "Alemania", "curacao": "Curazao",
    "ivory coast": "Costa de Marfil", "cote d'ivoire": "Costa de Marfil",
    "ecuador": "Ecuador",
    "netherlands": "Países Bajos", "japan": "Japón",
    "sweden": "Suecia", "tunisia": "Túnez",
    "belgium": "Bélgica", "egypt": "Egipto",
    "iran": "Irán", "ir iran": "Irán", "new zealand": "Nueva Zelanda",
    "spain": "España", "cape verde": "Cabo Verde", "cabo verde": "Cabo Verde",
    "cape verde islands": "Cabo Verde",
    "saudi arabia": "Arabia Saudita", "uruguay": "Uruguay",
    "france": "Francia", "senegal": "Senegal",
    "iraq": "Irak", "norway": "Noruega",
    "argentina": "Argentina", "algeria": "Argelia",
    "austria": "Austria", "jordan": "Jordania",
    "portugal": "Portugal", "dr congo": "RD Congo", "congo dr": "RD Congo",
    "democratic republic of the congo": "RD Congo",
    "uzbekistan": "Uzbekistán", "colombia": "Colombia",
    "england": "Inglaterra", "croatia": "Croacia",
    "ghana": "Ghana", "panama": "Panamá",
}
TEAM_MAP = {norm(k): v for k, v in TEAM_MAP_RAW.items()}


# Grupos (id -> 4 equipos), igual que index.html
GRUPOS = {
    "A": ["México", "Sudáfrica", "Corea del Sur", "Rep. Checa"],
    "B": ["Canadá", "Bosnia y Herzegovina", "Qatar", "Suiza"],
    "C": ["Brasil", "Marruecos", "Haití", "Escocia"],
    "D": ["Estados Unidos", "Paraguay", "Australia", "Turquía"],
    "E": ["Alemania", "Curazao", "Costa de Marfil", "Ecuador"],
    "F": ["Países Bajos", "Japón", "Suecia", "Túnez"],
    "G": ["Bélgica", "Egipto", "Irán", "Nueva Zelanda"],
    "H": ["España", "Cabo Verde", "Arabia Saudita", "Uruguay"],
    "I": ["Francia", "Senegal", "Irak", "Noruega"],
    "J": ["Argentina", "Argelia", "Austria", "Jordania"],
    "K": ["Portugal", "RD Congo", "Uzbekistán", "Colombia"],
    "L": ["Inglaterra", "Croacia", "Ghana", "Panamá"],
}
TEAM2GROUP = {t: gid for gid, teams in GRUPOS.items() for t in teams}

# Fixture PRODEMU: 72 partidos de grupos (mismos IDs que index.html)
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

# ============================================================================
#  FASE 2 - CUADRO (mismos datos que index.html)
# ============================================================================
# R32: (id, slot_local, slot_visitante). '3-x' = un 3er puesto (lo asigna la tabla).
R32 = [
    ("r1", "1E", "3-1"), ("r2", "1I", "3-2"), ("r3", "2A", "2B"), ("r4", "1F", "2C"),
    ("r5", "2K", "2L"), ("r6", "1H", "2J"), ("r7", "1D", "3-3"), ("r8", "1G", "3-4"),
    ("r9", "1C", "2F"), ("r10", "2E", "2I"), ("r11", "1A", "3-5"), ("r12", "1L", "3-6"),
    ("r13", "1J", "2H"), ("r14", "2D", "2G"), ("r15", "1B", "3-7"), ("r16", "1K", "3-8"),
]
BRACKET_FEED = {
    "r2m1": ["r1m1", "r1m2"], "r2m2": ["r1m3", "r1m4"], "r2m3": ["r1m5", "r1m6"], "r2m4": ["r1m7", "r1m8"],
    "r2m5": ["r1m9", "r1m10"], "r2m6": ["r1m11", "r1m12"], "r2m7": ["r1m13", "r1m14"], "r2m8": ["r1m15", "r1m16"],
    "r3m1": ["r2m1", "r2m2"], "r3m2": ["r2m3", "r2m4"], "r3m3": ["r2m5", "r2m6"], "r3m4": ["r2m7", "r2m8"],
    "r4m1": ["r3m1", "r3m2"], "r4m2": ["r3m3", "r3m4"],
    "r5m1": ["r4m1", "r4m2"],
}
BRACKET_COUNTS = {"r1": 16, "r2": 8, "r3": 4, "r4": 2, "r5": 1}
ROUNDS = ["r1", "r2", "r3", "r4", "r5"]

# Tabla oficial FIFA 2026 (Anexo C). Clave = grupos de los 8 mejores 3os ordenados
# alfabeticamente. Valor = grupo del 3o que enfrenta a cada ganador, orden A,B,D,E,G,I,K,L.
ANNEXC_RAW = "ABCDEFGH:HGBCAFDE ABCDEFGI:CGBDAFEI ABCDEFGJ:CGBDAFEJ ABCDEFGK:CGBDAFEK ABCDEFGL:CGBDAFLE ABCDEFHI:HEBCAFDI ABCDEFHJ:HJBCAFDE ABCDEFHK:HEBCAFDK ABCDEFHL:HFBCADLE ABCDEFIJ:CJBDAFEI ABCDEFIK:CEBDAFIK ABCDEFIL:CEBDAFLI ABCDEFJK:CJBDAFEK ABCDEFJL:CJBDAFLE ABCDEFKL:CEBDAFLK ABCDEGHI:HGBCADEI ABCDEGHJ:HGBCADEJ ABCDEGHK:HGBCADEK ABCDEGHL:HGBCADLE ABCDEGIJ:EGBCADIJ ABCDEGIK:EGBCADIK ABCDEGIL:EGBCADLI ABCDEGJK:EGBCADJK ABCDEGJL:EGBCADLJ ABCDEGKL:EGBCADLK ABCDEHIJ:HJBCADEI ABCDEHIK:HEBCADIK ABCDEHIL:HEBCADLI ABCDEHJK:HJBCADEK ABCDEHJL:HJBCADLE ABCDEHKL:HEBCADLK ABCDEIJK:EJBCADIK ABCDEIJL:EJBCADLI ABCDEIKL:EIBCADLK ABCDEJKL:EJBCADLK ABCDFGHI:HGBCAFDI ABCDFGHJ:HGBCAFDJ ABCDFGHK:HGBCAFDK ABCDFGHL:CGBDAFLH ABCDFGIJ:CGBDAFIJ ABCDFGIK:CGBDAFIK ABCDFGIL:CGBDAFLI ABCDFGJK:CGBDAFJK ABCDFGJL:CGBDAFLJ ABCDFGKL:CGBDAFLK ABCDFHIJ:HJBCAFDI ABCDFHIK:HFBCADIK ABCDFHIL:HFBCADLI ABCDFHJK:HJBCAFDK ABCDFHJL:CJBDAFLH ABCDFHKL:HFBCADLK ABCDFIJK:CJBDAFIK ABCDFIJL:CJBDAFLI ABCDFIKL:CIBDAFLK ABCDFJKL:CJBDAFLK ABCDGHIJ:HGBCADIJ ABCDGHIK:HGBCADIK ABCDGHIL:HGBCADLI ABCDGHJK:HGBCADJK ABCDGHJL:HGBCADLJ ABCDGHKL:HGBCADLK ABCDGIJK:CJBDAGIK ABCDGIJL:CJBDAGLI ABCDGIKL:IGBCADLK ABCDGJKL:CJBDAGLK ABCDHIJK:HJBCADIK ABCDHIJL:HJBCADLI ABCDHIKL:HIBCADLK ABCDHJKL:HJBCADLK ABCDIJKL:IJBCADLK ABCEFGHI:HGBCAFEI ABCEFGHJ:HGBCAFEJ ABCEFGHK:HGBCAFEK ABCEFGHL:HGBCAFLE ABCEFGIJ:EGBCAFIJ ABCEFGIK:EGBCAFIK ABCEFGIL:EGBCAFLI ABCEFGJK:EGBCAFJK ABCEFGJL:EGBCAFLJ ABCEFGKL:EGBCAFLK ABCEFHIJ:HJBCAFEI ABCEFHIK:HEBCAFIK ABCEFHIL:HEBCAFLI ABCEFHJK:HJBCAFEK ABCEFHJL:HJBCAFLE ABCEFHKL:HEBCAFLK ABCEFIJK:EJBCAFIK ABCEFIJL:EJBCAFLI ABCEFIKL:EIBCAFLK ABCEFJKL:EJBCAFLK ABCEGHIJ:HJBCAGEI ABCEGHIK:EGBCAHIK ABCEGHIL:EGBCAHLI ABCEGHJK:HJBCAGEK ABCEGHJL:HJBCAGLE ABCEGHKL:EGBCAHLK ABCEGIJK:EJBCAGIK ABCEGIJL:EJBCAGLI ABCEGIKL:EGBAICLK ABCEGJKL:EJBCAGLK ABCEHIJK:EJBCAHIK ABCEHIJL:EJBCAHLI ABCEHIKL:EIBCAHLK ABCEHJKL:EJBCAHLK ABCEIJKL:EJBAICLK ABCFGHIJ:HGBCAFIJ ABCFGHIK:HGBCAFIK ABCFGHIL:HGBCAFLI ABCFGHJK:HGBCAFJK ABCFGHJL:HGBCAFLJ ABCFGHKL:HGBCAFLK ABCFGIJK:CJBFAGIK ABCFGIJL:CJBFAGLI ABCFGIKL:IGBCAFLK ABCFGJKL:CJBFAGLK ABCFHIJK:HJBCAFIK ABCFHIJL:HJBCAFLI ABCFHIKL:HIBCAFLK ABCFHJKL:HJBCAFLK ABCFIJKL:IJBCAFLK ABCGHIJK:HJBCAGIK ABCGHIJL:HJBCAGLI ABCGHIKL:IGBCAHLK ABCGHJKL:HJBCAGLK ABCGIJKL:IJBCAGLK ABCHIJKL:IJBCAHLK ABDEFGHI:HGBDAFEI ABDEFGHJ:HGBDAFEJ ABDEFGHK:HGBDAFEK ABDEFGHL:HGBDAFLE ABDEFGIJ:EGBDAFIJ ABDEFGIK:EGBDAFIK ABDEFGIL:EGBDAFLI ABDEFGJK:EGBDAFJK ABDEFGJL:EGBDAFLJ ABDEFGKL:EGBDAFLK ABDEFHIJ:HJBDAFEI ABDEFHIK:HEBDAFIK ABDEFHIL:HEBDAFLI ABDEFHJK:HJBDAFEK ABDEFHJL:HJBDAFLE ABDEFHKL:HEBDAFLK ABDEFIJK:EJBDAFIK ABDEFIJL:EJBDAFLI ABDEFIKL:EIBDAFLK ABDEFJKL:EJBDAFLK ABDEGHIJ:HJBDAGEI ABDEGHIK:EGBDAHIK ABDEGHIL:EGBDAHLI ABDEGHJK:HJBDAGEK ABDEGHJL:HJBDAGLE ABDEGHKL:EGBDAHLK ABDEGIJK:EJBDAGIK ABDEGIJL:EJBDAGLI ABDEGIKL:EGBAIDLK ABDEGJKL:EJBDAGLK ABDEHIJK:EJBDAHIK ABDEHIJL:EJBDAHLI ABDEHIKL:EIBDAHLK ABDEHJKL:EJBDAHLK ABDEIJKL:EJBAIDLK ABDFGHIJ:HGBDAFIJ ABDFGHIK:HGBDAFIK ABDFGHIL:HGBDAFLI ABDFGHJK:HGBDAFJK ABDFGHJL:HGBDAFLJ ABDFGHKL:HGBDAFLK ABDFGIJK:FJBDAGIK ABDFGIJL:FJBDAGLI ABDFGIKL:IGBDAFLK ABDFGJKL:FJBDAGLK ABDFHIJK:HJBDAFIK ABDFHIJL:HJBDAFLI ABDFHIKL:HIBDAFLK ABDFHJKL:HJBDAFLK ABDFIJKL:IJBDAFLK ABDGHIJK:HJBDAGIK ABDGHIJL:HJBDAGLI ABDGHIKL:IGBDAHLK ABDGHJKL:HJBDAGLK ABDGIJKL:IJBDAGLK ABDHIJKL:IJBDAHLK ABEFGHIJ:HJBFAGEI ABEFGHIK:EGBFAHIK ABEFGHIL:EGBFAHLI ABEFGHJK:HJBFAGEK ABEFGHJL:HJBFAGLE ABEFGHKL:EGBFAHLK ABEFGIJK:EJBFAGIK ABEFGIJL:EJBFAGLI ABEFGIKL:EGBAIFLK ABEFGJKL:EJBFAGLK ABEFHIJK:EJBFAHIK ABEFHIJL:EJBFAHLI ABEFHIKL:EIBFAHLK ABEFHJKL:EJBFAHLK ABEFIJKL:EJBAIFLK ABEGHIJK:EJBAHGIK ABEGHIJL:EJBAHGLI ABEGHIKL:EGBAIHLK ABEGHJKL:EJBAHGLK ABEGIJKL:EJBAIGLK ABEHIJKL:EJBAIHLK ABFGHIJK:HJBFAGIK ABFGHIJL:HJBFAGLI ABFGHIKL:HGBAIFLK ABFGHJKL:HJBFAGLK ABFGIJKL:IJBFAGLK ABFHIJKL:HJBAIFLK ABGHIJKL:HJBAIGLK ACDEFGHI:HGECAFDI ACDEFGHJ:HGJCAFDE ACDEFGHK:HGECAFDK ACDEFGHL:HGFCADLE ACDEFGIJ:CGJDAFEI ACDEFGIK:CGEDAFIK ACDEFGIL:CGEDAFLI ACDEFGJK:CGJDAFEK ACDEFGJL:CGJDAFLE ACDEFGKL:CGEDAFLK ACDEFHIJ:HJECAFDI ACDEFHIK:HEFCADIK ACDEFHIL:HEFCADLI ACDEFHJK:HJECAFDK ACDEFHJL:HJFCADLE ACDEFHKL:HEFCADLK ACDEFIJK:CJEDAFIK ACDEFIJL:CJEDAFLI ACDEFIKL:CEIDAFLK ACDEFJKL:CJEDAFLK ACDEGHIJ:HGJCADEI ACDEGHIK:HGECADIK ACDEGHIL:HGECADLI ACDEGHJK:HGJCADEK ACDEGHJL:HGJCADLE ACDEGHKL:HGECADLK ACDEGIJK:EGJCADIK ACDEGIJL:EGJCADLI ACDEGIKL:EGICADLK ACDEGJKL:EGJCADLK ACDEHIJK:HJECADIK ACDEHIJL:HJECADLI ACDEHIKL:HEICADLK ACDEHJKL:HJECADLK ACDEIJKL:EJICADLK ACDFGHIJ:HGJCAFDI ACDFGHIK:HGFCADIK ACDFGHIL:HGFCADLI ACDFGHJK:HGJCAFDK ACDFGHJL:CGJDAFLH ACDFGHKL:HGFCADLK ACDFGIJK:CGJDAFIK ACDFGIJL:CGJDAFLI ACDFGIKL:CGIDAFLK ACDFGJKL:CGJDAFLK ACDFHIJK:HJFCADIK ACDFHIJL:HJFCADLI ACDFHIKL:HFICADLK ACDFHJKL:HJFCADLK ACDFIJKL:CJIDAFLK ACDGHIJK:HGJCADIK ACDGHIJL:HGJCADLI ACDGHIKL:HGICADLK ACDGHJKL:HGJCADLK ACDGIJKL:IGJCADLK ACDHIJKL:HJICADLK ACEFGHIJ:HGJCAFEI ACEFGHIK:HGECAFIK ACEFGHIL:HGECAFLI ACEFGHJK:HGJCAFEK ACEFGHJL:HGJCAFLE ACEFGHKL:HGECAFLK ACEFGIJK:EGJCAFIK ACEFGIJL:EGJCAFLI ACEFGIKL:EGICAFLK ACEFGJKL:EGJCAFLK ACEFHIJK:HJECAFIK ACEFHIJL:HJECAFLI ACEFHIKL:HEICAFLK ACEFHJKL:HJECAFLK ACEFIJKL:EJICAFLK ACEGHIJK:EGJCAHIK ACEGHIJL:EGJCAHLI ACEGHIKL:EGICAHLK ACEGHJKL:EGJCAHLK ACEGIJKL:EJICAGLK ACEHIJKL:EJICAHLK ACFGHIJK:HGJCAFIK ACFGHIJL:HGJCAFLI ACFGHIKL:HGICAFLK ACFGHJKL:HGJCAFLK ACFGIJKL:IGJCAFLK ACFHIJKL:HJICAFLK ACGHIJKL:HJICAGLK ADEFGHIJ:HGJDAFEI ADEFGHIK:HGEDAFIK ADEFGHIL:HGEDAFLI ADEFGHJK:HGJDAFEK ADEFGHJL:HGJDAFLE ADEFGHKL:HGEDAFLK ADEFGIJK:EGJDAFIK ADEFGIJL:EGJDAFLI ADEFGIKL:EGIDAFLK ADEFGJKL:EGJDAFLK ADEFHIJK:HJEDAFIK ADEFHIJL:HJEDAFLI ADEFHIKL:HEIDAFLK ADEFHJKL:HJEDAFLK ADEFIJKL:EJIDAFLK ADEGHIJK:EGJDAHIK ADEGHIJL:EGJDAHLI ADEGHIKL:EGIDAHLK ADEGHJKL:EGJDAHLK ADEGIJKL:EJIDAGLK ADEHIJKL:EJIDAHLK ADFGHIJK:HGJDAFIK ADFGHIJL:HGJDAFLI ADFGHIKL:HGIDAFLK ADFGHJKL:HGJDAFLK ADFGIJKL:IGJDAFLK ADFHIJKL:HJIDAFLK ADGHIJKL:HJIDAGLK AEFGHIJK:EGJFAHIK AEFGHIJL:EGJFAHLI AEFGHIKL:EGIFAHLK AEFGHJKL:EGJFAHLK AEFGIJKL:EJIFAGLK AEFHIJKL:EJIFAHLK AEGHIJKL:EJIAHGLK AFGHIJKL:HJIFAGLK BCDEFGHI:CGBDHFEI BCDEFGHJ:HGBCJFDE BCDEFGHK:CGBDHFEK BCDEFGHL:CGBDHFLE BCDEFGIJ:CGBDJFEI BCDEFGIK:CGBDEFIK BCDEFGIL:CGBDEFLI BCDEFGJK:CGBDJFEK BCDEFGJL:CGBDJFLE BCDEFGKL:CGBDEFLK BCDEFHIJ:CJBDHFEI BCDEFHIK:CEBDHFIK BCDEFHIL:CEBDHFLI BCDEFHJK:CJBDHFEK BCDEFHJL:CJBDHFLE BCDEFHKL:CEBDHFLK BCDEFIJK:CJBDEFIK BCDEFIJL:CJBDEFLI BCDEFIKL:CEBDIFLK BCDEFJKL:CJBDEFLK BCDEGHIJ:HGBCJDEI BCDEGHIK:EGBCHDIK BCDEGHIL:EGBCHDLI BCDEGHJK:HGBCJDEK BCDEGHJL:HGBCJDLE BCDEGHKL:EGBCHDLK BCDEGIJK:EGBCJDIK BCDEGIJL:EGBCJDLI BCDEGIKL:EGBCIDLK BCDEGJKL:EGBCJDLK BCDEHIJK:EJBCHDIK BCDEHIJL:EJBCHDLI BCDEHIKL:EIBCHDLK BCDEHJKL:EJBCHDLK BCDEIJKL:EJBCIDLK BCDFGHIJ:HGBCJFDI BCDFGHIK:CGBDHFIK BCDFGHIL:CGBDHFLI BCDFGHJK:HGBCJFDK BCDFGHJL:CGBDHFLJ BCDFGHKL:CGBDHFLK BCDFGIJK:CGBDJFIK BCDFGIJL:CGBDJFLI BCDFGIKL:CGBDIFLK BCDFGJKL:CGBDJFLK BCDFHIJK:CJBDHFIK BCDFHIJL:CJBDHFLI BCDFHIKL:CIBDHFLK BCDFHJKL:CJBDHFLK BCDFIJKL:CJBDIFLK BCDGHIJK:HGBCJDIK BCDGHIJL:HGBCJDLI BCDGHIKL:HGBCIDLK BCDGHJKL:HGBCJDLK BCDGIJKL:IGBCJDLK BCDHIJKL:HJBCIDLK BCEFGHIJ:HGBCJFEI BCEFGHIK:EGBCHFIK BCEFGHIL:EGBCHFLI BCEFGHJK:HGBCJFEK BCEFGHJL:HGBCJFLE BCEFGHKL:EGBCHFLK BCEFGIJK:EGBCJFIK BCEFGIJL:EGBCJFLI BCEFGIKL:EGBCIFLK BCEFGJKL:EGBCJFLK BCEFHIJK:EJBCHFIK BCEFHIJL:EJBCHFLI BCEFHIKL:EIBCHFLK BCEFHJKL:EJBCHFLK BCEFIJKL:EJBCIFLK BCEGHIJK:EJBCHGIK BCEGHIJL:EJBCHGLI BCEGHIKL:EGBCIHLK BCEGHJKL:EJBCHGLK BCEGIJKL:EJBCIGLK BCEHIJKL:EJBCIHLK BCFGHIJK:HGBCJFIK BCFGHIJL:HGBCJFLI BCFGHIKL:HGBCIFLK BCFGHJKL:HGBCJFLK BCFGIJKL:IGBCJFLK BCFHIJKL:HJBCIFLK BCGHIJKL:HJBCIGLK BDEFGHIJ:HGBDJFEI BDEFGHIK:EGBDHFIK BDEFGHIL:EGBDHFLI BDEFGHJK:HGBDJFEK BDEFGHJL:HGBDJFLE BDEFGHKL:EGBDHFLK BDEFGIJK:EGBDJFIK BDEFGIJL:EGBDJFLI BDEFGIKL:EGBDIFLK BDEFGJKL:EGBDJFLK BDEFHIJK:EJBDHFIK BDEFHIJL:EJBDHFLI BDEFHIKL:EIBDHFLK BDEFHJKL:EJBDHFLK BDEFIJKL:EJBDIFLK BDEGHIJK:EJBDHGIK BDEGHIJL:EJBDHGLI BDEGHIKL:EGBDIHLK BDEGHJKL:EJBDHGLK BDEGIJKL:EJBDIGLK BDEHIJKL:EJBDIHLK BDFGHIJK:HGBDJFIK BDFGHIJL:HGBDJFLI BDFGHIKL:HGBDIFLK BDFGHJKL:HGBDJFLK BDFGIJKL:IGBDJFLK BDFHIJKL:HJBDIFLK BDGHIJKL:HJBDIGLK BEFGHIJK:EJBFHGIK BEFGHIJL:EJBFHGLI BEFGHIKL:EGBFIHLK BEFGHJKL:EJBFHGLK BEFGIJKL:EJBFIGLK BEFHIJKL:EJBFIHLK BEGHIJKL:EJIBHGLK BFGHIJKL:HJBFIGLK CDEFGHIJ:CGJDHFEI CDEFGHIK:CGEDHFIK CDEFGHIL:CGEDHFLI CDEFGHJK:CGJDHFEK CDEFGHJL:CGJDHFLE CDEFGHKL:CGEDHFLK CDEFGIJK:CGEDJFIK CDEFGIJL:CGEDJFLI CDEFGIKL:CGEDIFLK CDEFGJKL:CGEDJFLK CDEFHIJK:CJEDHFIK CDEFHIJL:CJEDHFLI CDEFHIKL:CEIDHFLK CDEFHJKL:CJEDHFLK CDEFIJKL:CJEDIFLK CDEGHIJK:EGJCHDIK CDEGHIJL:EGJCHDLI CDEGHIKL:EGICHDLK CDEGHJKL:EGJCHDLK CDEGIJKL:EGICJDLK CDEHIJKL:EJICHDLK CDFGHIJK:CGJDHFIK CDFGHIJL:CGJDHFLI CDFGHIKL:CGIDHFLK CDFGHJKL:CGJDHFLK CDFGIJKL:CGIDJFLK CDFHIJKL:CJIDHFLK CDGHIJKL:HGICJDLK CEFGHIJK:EGJCHFIK CEFGHIJL:EGJCHFLI CEFGHIKL:EGICHFLK CEFGHJKL:EGJCHFLK CEFGIJKL:EGICJFLK CEFHIJKL:EJICHFLK CEGHIJKL:EJICHGLK CFGHIJKL:HGICJFLK DEFGHIJK:EGJDHFIK DEFGHIJL:EGJDHFLI DEFGHIKL:EGIDHFLK DEFGHJKL:EGJDHFLK DEFGIJKL:EGIDJFLK DEFHIJKL:EJIDHFLK DEGHIJKL:EJIDHGLK DFGHIJKL:HGIDJFLK EFGHIJKL:EJIFHGLK"
F2_THIRD_TABLE = {s.split(":")[0]: s.split(":")[1] for s in ANNEXC_RAW.split()}
WIN_ORDER = ["A", "B", "D", "E", "G", "I", "K", "L"]
WIN2SLOT = {"A": "r11", "B": "r15", "D": "r7", "E": "r1", "G": "r8", "I": "r2", "K": "r16", "L": "r12"}


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
        raise RuntimeError(f"HTTP {e.code} {e.reason} -> {body[:300]}") from None


def firebase_anon_token():
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    try:
        resp = http_json(url, method="POST", data={"returnSecureToken": True})
        return resp.get("idToken")
    except RuntimeError as e:
        print(f"No se pudo autenticar con Firebase: {e}")
        return None


def traducir(nombre_api):
    return TEAM_MAP.get(norm(nombre_api))


# ── FASE 1: procesar resultados de grupos ──────────────────────────────────
def procesar(api_matches, actuales):
    """Devuelve {mid: {home, away}} con los marcadores nuevos de la fase de grupos."""
    finalizados = {}
    sin_mapear = set()
    for m in api_matches:
        if m.get("stage") != GROUP_STAGE:
            continue
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
        print(f"Equipo de la API sin mapear (agregar a TEAM_MAP): {nombre!r}")

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


# ── Tablas de posiciones (port de index.html) ──────────────────────────────
def _overall_key(t):
    return (-t["Pts"], -t["GD"], -t["GF"], t["name"])


def _resolve_tie(block, ms, results):
    if len(block) < 2:
        return block
    names = {t["name"] for t in block}
    mini = {t["name"]: {"Pts": 0, "GF": 0, "GA": 0, "GD": 0} for t in block}
    complete = True
    for mid, h, a in ms:
        if h in names and a in names:
            r = results.get(mid)
            if not r or r.get("home") is None or r.get("away") is None:
                complete = False
                continue
            gh, ga = int(r["home"]), int(r["away"])
            mini[h]["GF"] += gh; mini[h]["GA"] += ga
            mini[a]["GF"] += ga; mini[a]["GA"] += gh
            if gh > ga:
                mini[h]["Pts"] += 3
            elif gh < ga:
                mini[a]["Pts"] += 3
            else:
                mini[h]["Pts"] += 1; mini[a]["Pts"] += 1
    for x in mini.values():
        x["GD"] = x["GF"] - x["GA"]
    if not complete:
        return sorted(block, key=lambda t: (-t["GD"], -t["GF"], t["name"]))
    srt = sorted(block, key=lambda t: (-mini[t["name"]]["Pts"], -mini[t["name"]]["GD"], -mini[t["name"]]["GF"]))
    out = []
    i = 0
    while i < len(srt):
        j = i
        while (j < len(srt)
               and mini[srt[j]["name"]]["Pts"] == mini[srt[i]["name"]]["Pts"]
               and mini[srt[j]["name"]]["GD"] == mini[srt[i]["name"]]["GD"]
               and mini[srt[j]["name"]]["GF"] == mini[srt[i]["name"]]["GF"]):
            j += 1
        sub = srt[i:j]
        if 1 < len(sub) < len(block):
            out.extend(_resolve_tie(sub, ms, results))
        elif len(sub) > 1:
            out.extend(sorted(sub, key=lambda t: (-t["GD"], -t["GF"], t["name"])))
        else:
            out.append(sub[0])
        i = j
    return out


def group_matches(gid):
    return [(mid, h, a) for mid, h, a in PARTIDOS if TEAM2GROUP.get(h) == gid and TEAM2GROUP.get(a) == gid]


def calc_group_table(gid, results):
    st = {t: {"name": t, "GF": 0, "GA": 0, "GD": 0, "Pts": 0} for t in GRUPOS[gid]}
    ms = group_matches(gid)
    for mid, h, a in ms:
        r = results.get(mid)
        if not r or r.get("home") is None or r.get("away") is None:
            continue
        gh, ga = int(r["home"]), int(r["away"])
        st[h]["GF"] += gh; st[h]["GA"] += ga
        st[a]["GF"] += ga; st[a]["GA"] += gh
        if gh > ga:
            st[h]["Pts"] += 3
        elif gh < ga:
            st[a]["Pts"] += 3
        else:
            st[h]["Pts"] += 1; st[a]["Pts"] += 1
    for t in st.values():
        t["GD"] = t["GF"] - t["GA"]
    teams = sorted(st.values(), key=_overall_key)
    # ordenar respetando mano a mano dentro de bloques de igual puntaje
    out = []
    i = 0
    while i < len(teams):
        j = i
        while j < len(teams) and teams[j]["Pts"] == teams[i]["Pts"]:
            j += 1
        block = teams[i:j]
        out.extend(_resolve_tie(block, ms, results) if len(block) > 1 else block)
        i = j
    return out


def grupos_completos(results):
    return all(
        results.get(mid) and results[mid].get("home") is not None and results[mid].get("away") is not None
        for mid, _, _ in PARTIDOS
    )


def mejores_terceros(tables):
    thirds = []
    for gid, tabla in tables.items():
        if len(tabla) >= 3:
            t = dict(tabla[2]); t["groupId"] = gid
            thirds.append(t)
    thirds.sort(key=lambda t: (-t["Pts"], -t["GD"], -t["GF"], t["name"]))
    return thirds


def asignar_terceros(qual_groups):
    key = "".join(sorted(qual_groups))
    row = F2_THIRD_TABLE.get(key)
    if not row or len(row) != 8:
        return None
    return {WIN2SLOT[WIN_ORDER[i]]: row[i] for i in range(8)}


def construir_r32(tables, thirds):
    qual = [t["groupId"] for t in thirds[:8]]
    ta = asignar_terceros(qual)

    def name_of(gid, pos):
        tabla = tables.get(gid)
        return tabla[pos]["name"] if tabla and len(tabla) > pos else None

    def resolve(slot, rid):
        if slot.startswith("3"):
            gid = ta.get(rid) if ta else None
            return name_of(gid, 2) if gid else None
        return name_of(slot[1], int(slot[0]) - 1)

    bracket = {}
    for idx, (rid, hs, as_) in enumerate(R32):
        bracket["r1m" + str(idx + 1)] = (resolve(hs, rid), resolve(as_, rid))
    return bracket


# ── FASE 2: ganadores de eliminatorias ─────────────────────────────────────
def ko_winner_team(m):
    """Devuelve (homeES, awayES, ganadorES|None) de un partido de llave finalizado."""
    sc = m.get("score", {})
    h, a = traducir(m["homeTeam"]["name"]), traducir(m["awayTeam"]["name"])
    if h is None or a is None:
        return (h, a, None)
    w = sc.get("winner")
    if w == "HOME_TEAM":
        return (h, a, h)
    if w == "AWAY_TEAM":
        return (h, a, a)
    pen = sc.get("penalties") or {}
    if pen.get("home") is not None and pen.get("away") is not None and pen["home"] != pen["away"]:
        return (h, a, h if pen["home"] > pen["away"] else a)
    ft = sc.get("fullTime") or {}
    if ft.get("home") is not None and ft.get("away") is not None and ft["home"] != ft["away"]:
        return (h, a, h if ft["home"] > ft["away"] else a)
    return (h, a, None)


def procesar_fase2(api_matches, all_results, f2_actuales, f2_bracket_override):
    """Devuelve {mID: ganador} nuevo para /f2/results, o {} si el cuadro no esta listo."""
    if f2_bracket_override:
        bracket16 = {mid: (v.get("home"), v.get("away")) for mid, v in f2_bracket_override.items()}
    else:
        if not grupos_completos(all_results):
            print("Fase 2: faltan resultados de grupos -> el cuadro todavia no se puede calcular.")
            return {}
        tables = {gid: calc_group_table(gid, all_results) for gid in GRUPOS}
        thirds = mejores_terceros(tables)
        bracket16 = construir_r32(tables, thirds)

    # ganadores de la API por par de equipos
    ko_winner = {}
    sin_mapear = set()
    for m in api_matches:
        if m.get("stage") not in KO_STAGES:
            continue
        h, a, w = ko_winner_team(m)
        if h is None:
            sin_mapear.add(m["homeTeam"]["name"])
        if a is None:
            sin_mapear.add(m["awayTeam"]["name"])
        if h and a and w:
            ko_winner[frozenset((h, a))] = w
    for nombre in sorted(sin_mapear):
        print(f"Equipo KO sin mapear (agregar a TEAM_MAP): {nombre!r}")

    slot_teams = dict(bracket16)
    winner_of = {}
    nuevos = {}
    for ri, rnd in enumerate(ROUNDS):
        for i in range(1, BRACKET_COUNTS[rnd] + 1):
            mid = f"{rnd}m{i}"
            teams = slot_teams.get(mid)
            if not teams or teams[0] is None or teams[1] is None:
                continue
            if mid in f2_actuales and f2_actuales[mid]:
                winner_of[mid] = f2_actuales[mid]
                continue
            w = ko_winner.get(frozenset(teams))
            if w and w in teams:
                nuevos[mid] = w
                winner_of[mid] = w
        # armar los equipos de la ronda siguiente con los ganadores ya conocidos
        if ri + 1 < len(ROUNDS):
            nrnd = ROUNDS[ri + 1]
            for i in range(1, BRACKET_COUNTS[nrnd] + 1):
                nmid = f"{nrnd}m{i}"
                f0, f1 = BRACKET_FEED[nmid]
                slot_teams[nmid] = (winner_of.get(f0), winner_of.get(f1))
    return nuevos


def main():
    if not TOKEN:
        sys.exit("Falta la variable de entorno FOOTBALL_DATA_TOKEN")

    api = http_json(API_URL, headers={"X-Auth-Token": TOKEN})
    api_matches = api.get("matches", [])
    n_grp = sum(1 for m in api_matches if m.get("stage") == GROUP_STAGE)
    n_ko = sum(1 for m in api_matches if m.get("stage") in KO_STAGES)
    print(f"API: {len(api_matches)} finalizados ({n_grp} de grupos, {n_ko} de llave)")

    token = firebase_anon_token()
    auth_q = f"?auth={token}" if token else ""
    if not token:
        print("Sin token de Firebase: si las reglas exigen auth, las operaciones fallaran.")

    actuales = http_json(f"{FIREBASE_URL}/results.json{auth_q}") or {}
    print(f"Firebase: {len(actuales)} resultados de grupos ya cargados")

    # ---- FASE 1 ----
    nuevos = procesar(api_matches, actuales)
    for mid, r in sorted(nuevos.items(), key=lambda x: int(x[0][1:])):
        eq = next(p for p in PARTIDOS if p[0] == mid)
        print(f"{'[DRY] ' if DRY_RUN else 'F1 '}{mid}: {eq[1]} {r['home']} - {r['away']} {eq[2]}")
    if nuevos and not DRY_RUN:
        try:
            http_json(f"{FIREBASE_URL}/results.json{auth_q}", method="PATCH", data=nuevos)
            print(f"OK: {len(nuevos)} resultados de grupos escritos.")
        except RuntimeError as e:
            print(f"ERROR al escribir /results: {e}")

    all_results = {**actuales, **nuevos}

    # ---- FASE 2 ----
    f2_actuales = http_json(f"{FIREBASE_URL}/f2/results.json{auth_q}") or {}
    override = http_json(f"{FIREBASE_URL}/f2/bracket.json{auth_q}") or {}
    print(f"Firebase: {len(f2_actuales)} ganadores de Fase 2 ya cargados"
          + (" (cuadro manual/override activo)" if override else ""))
    f2_nuevos = procesar_fase2(api_matches, all_results, f2_actuales, override)
    for mid in sorted(f2_nuevos, key=lambda x: (ROUNDS.index(x.split("m")[0]), int(x.split("m")[1]))):
        print(f"{'[DRY] ' if DRY_RUN else 'F2 '}{mid}: pasa {f2_nuevos[mid]}")
    if f2_nuevos and not DRY_RUN:
        try:
            http_json(f"{FIREBASE_URL}/f2/results.json{auth_q}", method="PATCH", data=f2_nuevos)
            print(f"OK: {len(f2_nuevos)} ganadores de Fase 2 escritos.")
        except RuntimeError as e:
            print(f"ERROR al escribir /f2/results: {e}")

    if not nuevos and not f2_nuevos:
        print("Sin novedades.")
    if DRY_RUN:
        print("DRY_RUN activo: no se escribio nada en Firebase.")


if __name__ == "__main__":
    main()
