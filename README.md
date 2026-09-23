# Terminal Isernia 3D

Mappa per **BeamNG.drive 0.39**: l'ex terminal bus di Isernia (località Le Piane), ricostruito in scala
reale e georeferenziato. Pagina della mod: https://www.beamng.com/resources/terminal-isernia.29704/

## Novità della v1.0 (rispetto alla 0.3)

- **Posizione reale**: il piazzale è ruotato e collocato esattamente come nella realtà (verificato su
  ortofoto e OpenStreetMap). Il sole segue ora, data e coordinate vere di Isernia.
- **Terreno reale** di 4 km (passo 2 m) dall'altimetria pubblica, più un **orizzonte di 33 km** con il
  Matese e le colline attorno. Al posto del vecchio terreno a griglia.
- **Materiali PBR fotografici** (base color, normal, roughness, AO) al posto dei bake procedurali:
  asfalto consumato con zone crepate, autobloccanti con muschio nelle fughe, cordoli in cemento,
  metallo zincato per ringhiera e pali, intonaco giallo scrostato.
- **Facciata principale a risoluzione doppia**, ricostruita dalla foto originale (9248 px).
- **Dintorni da OpenStreetMap**: 935 strade (con bordi rovinati, strisce e crepe, percorribili dal
  traffico AI), circa 1600 edifici ricostruiti con i modelli ufficiali di Italy, boschi e campi.
- **Vegetazione vera**: circa 32.000 alberi e cespugli con LOD e vento (pioppi lungo il torrente,
  querce e faggi nei boschi, lecci nelle aiuole del terminal, uliveti), più erba sul terreno.
- **Dettagli sul piazzale**: rappezzi, buche, macchie d'olio, tombini, foglie cadute e segni di sgommate.
- **Notte**: i 29 lampioni si accendono da soli al tramonto (luce + corpo illuminante emissivo).
- Circa 3,5 volte meno triangoli nel modello del terminal (835k → ~245k), con le istanze per i lampioni.

## Installazione

Scarica `terminal_isernia.zip` e mettilo, senza estrarlo, in
`%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods\`. La mappa si chiama **Terminal Isernia**.

Il livello usa alberi, edifici, decal e materiali già presenti nel gioco (Italy, East Coast, West Coast),
quindi serve BeamNG.drive 0.39 o successivo. I veicoli del gruppo "noi" richiedono le relative mod.

## Struttura del repository

```
mod/levels/terminal_isernia/   la mod pronta (quello che finisce nello zip)
src/blender/terminal.blend     modello Blender del terminal (sorgente)
tools/                         pipeline di costruzione, tutta in Python
```

La pipeline ricostruisce tutto da zero:

```
python tools/fetch_sources.py      # scarica altimetria, OSM e texture CC0 (non versionati)
python tools/build_all.py --zip    # Blender -> texture -> terreno -> livello -> validazione -> dist/
```

| Script | Cosa fa |
|---|---|
| `geo.py` | georeferenziazione: sistema del livello = metri est/nord dal centro del terminal |
| `blender_export.py` | esporta il modello in `.dae` (writer Collada proprio: Blender 5 non lo ha più), UV in metri, asfalto tagliato al perimetro reale |
| `build_textures.py` | converte le texture CC0 nel formato BeamNG, ricostruisce le foto dell'edificio, invecchia la facciata |
| `build_terrain.py` | terreni `.ter`, strati materiali da OSM/pendenza, mappe base 4096 |
| `build_level.py` | assembla il livello: cielo, luci, alberi, erba, strade, edifici, decal, spawn |
| `validate.py` | controlla json e che ogni file referenziato esista nella mod o nel gioco |

## Crediti e licenze delle fonti

- Modello originale, foto dell'edificio e idea: **Matto**.
- Texture PBR: [ambientCG](https://ambientcg.com) (CC0).
- Altimetria: [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (Mapzen/Tilezen, dati SRTM,
  EU-DEM e altri; vedi l'attribuzione del dataset).
- Strade, edifici, uso del suolo: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, ODbL.
- Alberi, edifici dei dintorni, decal e molti materiali: asset di BeamNG.drive, **non ridistribuiti**:
  il livello li richiama dai pacchetti del gioco installato.
