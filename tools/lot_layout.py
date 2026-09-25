"""Disposizione reale del piazzale, in coordinate modello (x lungo il piazzale, y verso nord-ovest; metri).

Ricalcata sull'ortofoto Esri z19 (raddrizzata nel sistema del modello) e controllata sui panorami Street View del
settembre 2022. Il modello v0.3 fatto a mano aveva l'edificio al posto giusto ma il resto spostato: isole ~6 m verso
nord-ovest e ruotate di 2 gradi, fascia centrale larga 10 m invece di 4.6, bordo nord-ovest 10-15 m troppo in la',
marciapiede sud-est 1.5 m troppo dentro.

Usato da blender_export.py (fondo del piazzale, ringhiere) e build_level.py (oggetti).
"""
import math

# ---------------------------------------------------------------- isole diagonali (due file)
# trasformazione rigida modello -> realta' stimata sugli alberi delle isole (errore medio 1 m)
ISL_ROT_DEG = 1.970
ISL_T = (-0.643, -5.944)


def island_xform(x, y):
    a = math.radians(ISL_ROT_DEG); c, s = math.cos(a), math.sin(a)
    return c * x - s * y + ISL_T[0], s * x + c * y + ISL_T[1]


def in_old_islands(x, y):
    return -17.0 <= x <= 70.0 and -18.5 <= y <= 7.5


# ---------------------------------------------------------------- fascia centrale (tra strada e piazzale)
# striscia di terra ed erba secca con cordolo, alberi, lampioni e la pensilina verde
MED_X0, MED_X1 = -21.0, 75.0
MED_HALF = 2.3


def median_y(x):
    return 0.0348 * x - 32.314


def in_old_median(x, y):
    return -23.0 <= x <= 77.0 and -35.0 <= y <= -22.0


# ---------------------------------------------------------------- bordi del piazzale
# cordolo sud-est: linea scura del cordolo rilevata metro per metro sull'ortofoto (scarto medio 0.2 m) e controllata su
# Street View 2022 (cordolo a ~4 m dall'auto, marciapiede di ~2.6 m). Come isole e fascia centrale non e' parallelo
# all'asse del modello: prima era una retta a y -47, 3 m troppo dentro a sud-ovest e 2 m troppo fuori a nord-est.
SE_CURB = [(-36.0, -51.2), (-20.0, -50.6), (0.0, -50.3), (20.0, -49.7), (40.0, -48.7), (60.0, -47.8), (80.0, -46.9),
           (100.0, -45.8), (120.0, -44.6), (135.0, -43.2), (150.0, -41.9)]
# Street View 2022: la Rava non finisce nel piazzale, prosegue a nord-est (OSM: strada da x 115, y -40); marciapiede e
# ringhiera sud-est la seguono. La testata nord-est ha una ringhiera marrone davanti al canneto e si apre sulla strada.
SE_EXT_X = 150.0           # il marciapiede sud-est continua lungo la strada fino a qui
NE_OPEN_Y = -34.0          # varco nella testata nord-est per la strada: da qui al cordolo sud-est
# a sud-ovest (Street View giugno 2024): il marciapiede sud-est prosegue lungo la Rava; da x -25 la sua ringhiera e' a
# telai dipinti di colori diversi, con il varco d'ingresso al "Parco calisthenics e fitness" (bacheche e cartello blu);
# la stessa ringhiera colorata corre sul lato nord-ovest della Rava oltre l'angolo del piazzale (build_extras.py)
SE_WEST_X = -48.0
SE_COLOR_FROM_X = -25.0
PARK_GAP = (-32.6, -30.4)
PARK_BOARDS_X = [-34.3, -35.7]
NW_COLOR_FROM_X, NW_COLOR_TO_X = -38.5, -80.0
# cubo di cemento col murale sotto la pensilina sud-est, all'angolo sud-ovest dell'edificio (Street View 2022)
GRAFFITI_CUBE = (90.0, -16.3)
SE_WALK = 2.5              # autobloccanti grigi tra cordolo e ringhiera


def _pl(P, x):
    if x <= P[0][0]:
        return P[0][1]
    for (x0, y0), (x1, y1) in zip(P, P[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return P[-1][1]


def se_curb_y(x):
    return _pl(SE_CURB, x)


def se_rail_y(x):
    return se_curb_y(x) - SE_WALK


def se_curb_line(xa, xb, step=10.0):
    """cordolo sud-est da xa a xb (anche al contrario), con i vertici della spezzata."""
    lo, hi = min(xa, xb), max(xa, xb)
    xs = sorted({lo, hi} | {x for x, _ in SE_CURB if lo < x < hi} | set(v for v in _frange(lo, hi, step)))
    if xa > xb:
        xs = xs[::-1]
    return [(x, se_curb_y(x)) for x in xs]


def _frange(a, b, s):
    v = a + s
    while v < b - 0.5:
        yield v
        v += s
SW_X = -35.5               # bordo sud-ovest (marciapiede fino a SW_X - SW_WALK)
SW_WALK = 2.5
NE_X = 119.0
NW_WALK = 2.4              # marciapiede nord-ovest oltre il cordolo, ringhiera sul bordo esterno
# cordolo nord-ovest (bordo dell'asfalto), da sud-ovest a nord-est
NW_CURB = [(-35.5, 31.5), (-28.0, 29.6), (-18.0, 25.6), (-8.0, 21.0), (2.0, 16.0), (10.0, 13.4), (20.0, 12.4),
           (40.0, 11.6), (60.0, 11.3), (80.0, 11.8), (95.0, 12.8), (108.0, 14.6), (114.0, 16.0)]
NW_WALK_FROM = -12.0       # il marciapiede nord-ovest parte dopo i casotti (prima c'e' l'uscita per l'autolavaggio)


def nw_curb_y(x):
    P = NW_CURB
    if x <= P[0][0]:
        return P[0][1]
    for (x0, y0), (x1, y1) in zip(P, P[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return P[-1][1]


def lot_outline():
    """contorno dell'asfalto (antiorario): lato sud-est, testata nord-est arrotondata, bordo nord-ovest, lato sud-ovest."""
    pts = se_curb_line(SW_X, NE_X) + [(NE_X, 10.0)]
    cx, cy, r = NE_X - 5.0, 10.0, 5.0                       # angolo nord-est raccordato
    for k in range(1, 9):
        a = math.radians(90 * k / 8)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts += [p for p in reversed(NW_CURB) if p[0] < cx]
    if pts[-1] != (SW_X, NW_CURB[0][1]):
        pts.append((SW_X, NW_CURB[0][1]))
    return pts


# ---------------------------------------------------------------- oggetti nuovi visti dal vero
# due container prefabbricati nell'angolo nord-ovest (satellite: tetti chiari, grigio-bianco e crema; il rettangolo scuro
# sull'ortofoto Esri e' la loro ombra verso nord-ovest)
# tolti su indicazione dell'utente (non fanno parte del terminal): la lista resta per le maschere dei decal
KIOSKS = []
WILLOW = (7.5, 16.0)       # tronco del salice sul marciapiede nord-ovest, a ridosso della ringhiera (chioma a ~(7, 16.5))
NOTICE_BOARD = (38.0, se_rail_y(38.0) + 0.45)
PARK_SIGN = (-38.4, se_rail_y(-38.4) - 3.5)
PARK_BIN = (-33.3, se_rail_y(-33.3) + 0.45)   # bacheca sul marciapiede sud-est (telaio arrugginito, pannello sbiadito)
# chiome della fascia centrale sull'ortofoto (quelle delle isole coincidono entro 1 m con island_xform)
MEDIAN_CROWNS = [(-16.3, -32.6), (-6.9, -32.7), (44.8, -31.2), (62.7, -30.4), (69.9, -29.3)]
# fascia centrale, da Street View 2022: a x ~63 un cespuglio tondo (non un albero); accanto alla pensilina un pruno a
# foglia rossa (nel gioco non c'e': leccio da citta', chioma scura e compatta) con un cespuglietto ai piedi
MEDIAN_SHRUB_AT = [62.7]
MEDIAN_DARK_TREE_AT = [42.6]
MEDIAN_EXTRA_SHRUBS = [(41.4, -31.9)]
# x vere degli alberi della fascia centrale (Street View 2022, direzioni dai panorami lungo la Rava): il pruno sta ~2 m a
# ovest della pensilina, gli alberelli non stanno addosso ai lampioni
MEDIAN_TREE_X = {-16.3: -14.6, 44.8: 42.6, 69.9: 67.9}
MEDIAN_SOIL_OFF = 0.8      # centro della striscia in terra (lato piazzale): gli autobloccanti sono sul lato strada
TREE_LAMP_CLEAR = 2.0      # alberelli ad almeno 2 m dai pali
# pensilina della fascia centrale: resta alla x del modello v0.3 (~45, Street View 2022 la conferma li')
MEDIAN_SHELTER = None
# isola a "E" della v0.3 a sud-est dell'edificio: stalli dei bus tra i bracci (Street View 2024: righe gialle sbiadite
# in diagonale e un paletto rosso sul braccio centrale)
E_BAYS = [(88.2, 94.9), (96.6, 104.4)]      # x degli stalli, tra y -29.9 e -34.0
E_BAY_Y = (-29.9, -34.0)
E_POST = (95.75, -32.2)


def in_median(x, y, pad=0.0):
    return MED_X0 - MED_HALF - pad <= x <= MED_X1 + MED_HALF + pad and abs(y - median_y(x)) <= MED_HALF + pad


def in_carwash_road(x, y):
    """imbocco della stradina dell'autolavaggio (varco nel cordolo nord-ovest)."""
    return -34.0 < x < -19.0 and y > nw_curb_y(x) - 1.0


def in_kiosk(x, y, pad=0.0):
    return any(abs(x - cx) <= L / 2 + pad and abs(y - cy) <= W / 2 + pad for (cx, cy), L, W, _ in KIOSKS)


def snap_tree(x, y):
    """albero della fascia centrale -> chioma vera piu' vicina (entro 5 m)."""
    if not in_median(x, y, 1.0):
        return x, y
    c = min(MEDIAN_CROWNS, key=lambda q: math.hypot(q[0] - x, q[1] - y))
    return c if math.hypot(c[0] - x, c[1] - y) < 5.0 else (x, y)


# ---------------------------------------------------------------- riposizionamento degli oggetti del modello v0.3
def relocate(x, y):
    """posizione vecchia (modello v0.3) -> posizione nella disposizione reale."""
    if y < -40.0 and SW_X - 1 < x < NE_X + 1:                 # marciapiede sud-est
        return x, se_rail_y(x) + 0.4                       # lampioni vicino alla ringhiera (Street View 2022)
    if SW_X - SW_WALK - 1.0 < x < SW_X + 1.0 and -34.0 < y < NW_CURB[0][1]:   # marciapiede sud-ovest
        return SW_X - SW_WALK / 2, y
    if in_old_median(x, y):
        return min(max(x, MED_X0 + 1.5), MED_X1 - 1.5), median_y(x)
    if in_old_islands(x, y):
        return island_xform(x, y)
    if y > 10.0 and x > NW_WALK_FROM:                          # marciapiede nord-ovest
        return x, nw_curb_y(x) + NW_WALK * 0.5
    return x, y
