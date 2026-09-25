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
SE_CURB_Y = -47.0          # cordolo lato strada del marciapiede sud-est
SE_RAIL_Y = -49.6          # ringhiera sud-est (autobloccanti grigi tra cordolo e ringhiera)
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
    pts = [(SW_X, SE_CURB_Y), (NE_X, SE_CURB_Y), (NE_X, 10.0)]
    cx, cy, r = NE_X - 5.0, 10.0, 5.0                       # angolo nord-est raccordato
    for k in range(1, 9):
        a = math.radians(90 * k / 8)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts += [p for p in reversed(NW_CURB) if p[0] < cx]
    if pts[-1] != (SW_X, NW_CURB[0][1]):
        pts.append((SW_X, NW_CURB[0][1]))
    return pts


# lastra rettangolare a sud-est dell'edificio (x0, y0, x1, y1): al posto dell'isola a "E" della v0.3
EAST_SLAB = (85.5, -34.6, 107.2, -27.2)


# ---------------------------------------------------------------- oggetti nuovi visti dal vero
# due container prefabbricati nell'angolo nord-ovest (satellite: tetti chiari, grigio-bianco e crema; il rettangolo scuro
# sull'ortofoto Esri e' la loro ombra verso nord-ovest)
KIOSKS = [((-11.7, 17.1), 6.6, 2.35, "grey"), ((-4.9, 17.1), 5.7, 2.35, "cream")]
WILLOW = (7.5, 16.0)       # tronco del salice sul marciapiede nord-ovest, a ridosso della ringhiera (chioma a ~(7, 16.5))
NOTICE_BOARD = (38.0, SE_RAIL_Y + 0.45)   # bacheca sul marciapiede sud-est (telaio arrugginito, pannello sbiadito)
# chiome della fascia centrale sull'ortofoto (quelle delle isole coincidono entro 1 m con island_xform)
MEDIAN_CROWNS = [(-16.3, -32.6), (-6.9, -32.7), (44.8, -31.2), (62.7, -30.4), (69.9, -29.3)]
# pensilina della fascia centrale: sull'ortofoto e' la tettoia a griglia 3.8 x 2.3 m sul lato strada, non a x 45
MEDIAN_SHELTER = (8.1, -33.1)


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
        return x, (SE_CURB_Y + SE_RAIL_Y) / 2 - 0.2
    if SW_X - SW_WALK - 1.0 < x < SW_X + 1.0 and -34.0 < y < NW_CURB[0][1]:   # marciapiede sud-ovest
        return SW_X - SW_WALK / 2, y
    if in_old_median(x, y):
        return min(max(x, MED_X0 + 1.5), MED_X1 - 1.5), median_y(x)
    if in_old_islands(x, y):
        return island_xform(x, y)
    if y > 10.0 and x > NW_WALK_FROM:                          # marciapiede nord-ovest
        return x, nw_curb_y(x) + NW_WALK * 0.5
    return x, y
