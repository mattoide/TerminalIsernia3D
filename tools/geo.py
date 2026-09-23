"""Georeferenziazione comune a tutti gli script.

Sistema del livello BeamNG (dalla v1.0):
  X = est, Y = nord, Z = quota in metri relativa al piazzale (Z=0 = asfalto del terminal).
  Origine = LAT0/LON0 (centro dell'ex terminal bus, localita' Le Piane, Isernia).

La mod originale (v0.3) aveva il piazzale allineato all'asse X; per portarla nel sistema reale
si ruota di MODEL_ROT_DEG attorno a Z e si trasla di MODEL_OFFSET (valori ricavati
sovrapponendo la pianta del modello alle ortofoto).
"""
import math

LAT0, LON0 = 41.6043, 14.2463
R_EARTH = 6378137.0
K0 = math.cos(math.radians(LAT0))           # fattore di scala Mercatore locale

MODEL_ROT_DEG = 44.5                         # rotazione modello v0.3 -> est/nord
MODEL_OFFSET = (-38.304, -26.315)            # traslazione (m) dopo la rotazione


def ll2en(lat, lon):
    """lat/lon WGS84 -> metri est/nord locali (Mercatore scalato, esatto entro pochi km)."""
    x = R_EARTH * math.radians(lon - LON0) * K0
    y = R_EARTH * (math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
                   - math.log(math.tan(math.pi / 4 + math.radians(LAT0) / 2))) * K0
    return x, y


def en2ll(x, y):
    lon = LON0 + math.degrees(x / (R_EARTH * K0))
    m0 = math.log(math.tan(math.pi / 4 + math.radians(LAT0) / 2))
    lat = math.degrees(2 * math.atan(math.exp(y / (R_EARTH * K0) + m0)) - math.pi / 2)
    return lat, lon


def model2world(x, y):
    """coordinate del modello v0.3 (Blender / livello vecchio) -> est/nord."""
    t = math.radians(MODEL_ROT_DEG)
    return (math.cos(t) * x - math.sin(t) * y + MODEL_OFFSET[0],
            math.sin(t) * x + math.cos(t) * y + MODEL_OFFSET[1])


def world2model(x, y):
    """inverso di model2world."""
    t = math.radians(MODEL_ROT_DEG)
    x, y = x - MODEL_OFFSET[0], y - MODEL_OFFSET[1]
    return math.cos(t) * x + math.sin(t) * y, -math.sin(t) * x + math.cos(t) * y


def model_rot_matrix3():
    """matrice 3x3 (row-major, come i rotationMatrix di BeamNG) della rotazione modello->mondo."""
    t = math.radians(MODEL_ROT_DEG)
    c, s = math.cos(t), math.sin(t)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def tile_xy(lat, lon, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
