# Terminal Isernia 3D

Mappa per **BeamNG.drive 0.39**: l'ex terminal bus di Isernia (località Le Piane), ricostruito in scala
reale e georeferenziato. Pagina della mod: https://www.beamng.com/resources/terminal-isernia.29704/

![Piazzale](docs/screenshot_piazzale.jpg)

| | |
|---|---|
| ![Facciata con pensilina](docs/screenshot.jpg) | ![Vista aerea](docs/screenshot_aereo.jpg) |
| ![Notte](docs/screenshot_notte.jpg) | ![Il salice piangente (v1.0.1)](docs/screenshot_salice.jpg) |
| ![Archi con le grate (v1.0.1)](docs/screenshot_archi.jpg) | |

## Novità della v1.0.3

Il fondo del piazzale è ricostruito da zero sulla disposizione vera (`tools/lot_layout.py`), ricalcata sull'ortofoto
e controllata sulle foto satellitari e su Street View 2022. Il modello v0.3 aveva l'edificio al posto giusto ma il resto spostato:

- **Isole diagonali** al loro posto: circa 6 m più a sud-est e ruotate di 2°, allineate agli alberi veri (scarto medio di 1 m).
- **Fascia centrale** tra piazzale e Strada Rava larga 4,6 m (prima 10): cordolo, lato strada in autobloccanti rossastri,
  terra ed erba secca, gli alberi sulle chiome vere e la pensilina verde dove sta davvero (a x 8, sul lato della fermata).
- **Marciapiedi rifatti**: nord-ovest lungo il bordo vero (prima 10-15 m troppo in là), sud-est in autobloccanti grigi
  tra cordolo e ringhiera, sud-ovest lungo il vialetto; ringhiere nuove più leggere sui due lati lunghi.
- Tolte le **strisce gialle** degli stalli (su Street View 2022 non ci sono più) e gli oggetti in carreggiata
  (barriere di plastica, cassonetti, fusti, cassone macerie); gli idranti stanno sui marciapiedi.
- **Due container prefabbricati** nell'angolo nord-ovest, all'imbocco della stradina dell'autolavaggio, e la
  **bacheca** arrugginita sul marciapiede sud-est; il salice ha il tronco a ridosso della ringhiera.
- La linea elettrica è oltre la nuova ringhiera; lampioni, alberi e paline alla quota del fondo nuovo; le auto
  parcheggiate non finiscono più sopra le isole.
- **Glitch**: il terreno (celle da 2 m) non affiora più dall'asfalto lungo i cordoli; i cordoli hanno la faccia posteriore.

## Novità della v1.0.1

Correzioni dopo una nuova analisi della mappa (script `tools/analyze_level.py` + giro in gioco, riferimento Street View 2022):

- **Il grande salice piangente** sul marciapiede nord-ovest, prima della ringhiera, fatto su misura (nel gioco non c'è): chioma a cupola di
  ~13 m con centinaia di "tende" di rametti pendenti, come elemento forest con il vento.
- **Asfalto**: roughness da asfalto asciutto (prima sembrava bagnato), variazione macro su tutto il piazzale,
  corsie consumate dai bus e bordi più sporchi.
- **Sgommate vere**: tracce dei singoli pneumatici (ciambelle col centro che scivola, archi di drift, un otto,
  partenze e frenate), tagliate automaticamente dove passerebbero su marciapiedi, isole e cordoli.
- Macchie d'olio negli stalli e alle fermate dei bus invece che sparse a caso.
- **Grate metalliche** nei tre archi della facciata; facciata ripulita dalle macchie dipinte della v0.3.
- Ringhiera marrone scuro arrugginita, pannelli delle pensiline in policarbonato sporco, marciapiedi grigio-rossastri.
- Canneto più verde, con varchi di cespugli (prima da lontano sembrava mais).
- **Dintorni**: edifici su piazzole in piano (prima in pendenza erano mezzi sepolti), niente doppioni né case sulla
  carreggiata; alberi e lampioni non spuntano più dentro le case; arredo appoggiato al suolo vero.
- **Strade**: agli incroci tutte le vie arrivano alla stessa quota (prima gradini fino al 400%), ponti corti
  percorribili, viadotti della SS650 con impalcato, cordoli e pile.
- **Cielo**: meno foschia sulle colline, più nuvole, stelle e luna di notte.
- **Confronto con Street View (set 2022)**: graffiti sulla fascia bassa della facciata ad archi, lucernario a piramide sul
  tetto, pennacchi sul canneto, linea elettrica con pali di cemento lungo il lato sud-est, marciapiede lungo la ringhiera
  in autobloccanti grigi, lampioni del piazzale a pastorale (braccio curvo), alberi dei campi a gruppi e filari.
- **Piazzale com'è davvero**: tolto il rettangolo a sud-ovest del modello v0.3 (nella realtà è bosco e cantiere, il
  piazzale finisce al vialetto pedonale); la Strada Comunale Rava si raccorda al bordo nuovo; isole diagonali in terra
  ed erba secca con giovani latifoglie; crepe, rappezzi e sgommate non sbordano più su isole e marciapiedi.
- **Autolavaggio**: la stradina asfaltata che sale dal piazzale, il piazzale in piano e la tettoia con 6 piste.

## Novità della v1.0 (rispetto alla 0.3)

- **Posizione reale**: il piazzale è ruotato e collocato esattamente come nella realtà (verificato su
  ortofoto e OpenStreetMap). Il sole segue ora, data e coordinate vere di Isernia.
- **Terreno reale** di 4 km (passo 2 m) dall'altimetria pubblica, più un **orizzonte fino a 16 km** (mesh di
  sfondo con boschi) con il Matese e le colline attorno. Al posto del vecchio terreno a griglia.
- **Materiali PBR fotografici** (base color, normal, roughness, AO) al posto dei bake procedurali:
  asfalto consumato con zone crepate, autobloccanti con muschio nelle fughe, cordoli in cemento,
  metallo zincato per i pali, intonaco giallo scrostato.
- **Facciata principale a risoluzione doppia**, ricostruita dalla foto originale (9248 px).
- **Dintorni da OpenStreetMap**: 935 strade (con bordi rovinati, strisce e crepe, percorribili dal
  traffico AI), circa 1600 edifici ricostruiti con i modelli ufficiali di Italy, boschi e campi.
- **Vegetazione vera**: circa 100.000 alberi e cespugli con LOD e vento, anche sulle colline lontane (pioppi lungo il torrente,
  querce e faggi nei boschi, lecci nelle aiuole del terminal, uliveti), più erba sul terreno.
- **Dettagli sul piazzale**: rappezzi, buche, macchie d'olio, tombini, crepe, foglie cadute e segni di sgommate.
- **Com'è oggi** (riferimento: Street View 2022/2024): pensiline a denti di sega con travi verdi e pannelli
  traslucidi, pilastri in cemento chiaro, ringhiera marrone arrugginita, canneto alto lungo i bordi, strisce gialle
  sbiadite, barriere di plastica rosse, idranti, lampioni decorativi a due globi, rifiuti davanti all'ingresso.
- **Notte**: i 29 lampioni si accendono da soli al tramonto (luce + corpo illuminante emissivo).
- Circa 3,5 volte meno triangoli nel modello del terminal (835k → ~245k), con le istanze per i lampioni.

## Installazione

Scarica `terminal_isernia.zip` e mettilo, senza estrarlo, in
`%LOCALAPPDATA%\BeamNG\BeamNG.drive\current\mods\`. La mappa si chiama **Terminal Isernia**.

Il livello usa alberi, edifici, decal e materiali già presenti nel gioco (Italy, East Coast, West Coast),
quindi serve BeamNG.drive 0.39 o successivo. Le 7 auto del gruppo "noi" della v0.3 sono state tolte: erano mod
non incluse e il gioco le disattivava con errori.

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
| `lot_layout.py` | disposizione reale del piazzale (contorno, cordoli, isole, fascia centrale, container, salice) usata da export e livello |
| `blender_props.py` | genera pensiline a denti di sega, ciuffi di canne, lampione a due globi, grate degli archi, il salice piangente, container e bacheca |
| `build_bridges.py` | viadotti (ponti OSM oltre 70 m): impalcato, cordoli e pile, con i DecalRoad sopra |
| `build_backdrop.py` | mesh di sfondo delle colline fino a 16 km |
| `build_textures.py` | converte le texture CC0 nel formato BeamNG, ricostruisce le foto dell'edificio, invecchia la facciata |
| `build_terrain.py` | terreni `.ter`, strati materiali da OSM/pendenza, mappe base 4096 |
| `build_level.py` | assembla il livello: cielo, luci, alberi, erba, strade, edifici, decal, spawn |
| `validate.py` | controlla json e che ogni file referenziato esista nella mod o nel gioco |
| `analyze_level.py` | controlli di qualità: edifici sovrapposti/sepolti/sulla strada, alberi e lampioni dentro le case, strade troppo ripide |
| `bng.py` | client del server MCP integrato in BeamNG, per i test automatici (caricamento, camere, screenshot) |

## Crediti e licenze delle fonti

- Modello originale, foto dell'edificio e idea: **Matto**.
- Texture PBR: [ambientCG](https://ambientcg.com) (CC0).
- Altimetria: [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (Mapzen/Tilezen, dati SRTM,
  EU-DEM e altri; vedi l'attribuzione del dataset).
- Strade, edifici, uso del suolo: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, ODbL.
- Immagini Street View: usate solo come riferimento visivo per forme e colori, nessuna immagine è inclusa.
- Alberi, edifici dei dintorni, decal e molti materiali: asset di BeamNG.drive, **non ridistribuiti**:
  il livello li richiama dai pacchetti del gioco installato.
