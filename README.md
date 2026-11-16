# Pajenicko BuzzerDisplay Enhanced

Vlastní firmware pro Pájeníčko BuzerDisplej a lokální integrace Home Assistantu
s kartou zobrazující skutečný obraz LED matice.

**Vývojová verze 0.1.0-dev.1.** Firmware již běžel na fyzickém zařízení.
Stabilní vydání zatím není k dispozici; úplné zapojení do HA 2026.11 zbývá ověřit.
Podrobnosti obsahuje [záznam ověření](docs/VALIDATION.md).

## Co systém umí

- Přímé ovládání z Home Assistantu bez MQTT a bez cloudu.
- Až osm obrazovek s textem nebo hodnotou vybrané entity, jednotkou a přesností.
- Posun dlouhého textu doleva i doprava, 1–80 pixelů za sekundu; 0 posun vypne.
- Nájezd a odjezd zleva, zprava, shora, zdola a změnou jasu.
- Ostré blikání, plynulé pulzování a inverze.
- Vlastní české bitmapové písmo, `°C`, `%`, `µ`, `Ω`, měnové znaky a šipky.
- Dočasná oznámení s automatickým návratem k běžným obrazovkám.
- Obnovování Wi-Fi s omezenou délkou pokusu a postupně delšími prodlevami.
- Vykreslování v samostatné úloze; síťový požadavek animaci nezastaví.
- Detekce zastaralých dat. HA obnovuje údaje nejméně každých 30 sekund;
  po 90 sekundách bez aktualizace se zobrazuje upozornění.
- Konfigurace Wi-Fi přes Improv Serial, malý český web a mDNS vyhledání.
- Karta HA přebírá obrazový buffer a aktuální jas, nejvýše 25 snímků/s.
  Přenos běží pouze při otevřené kartě a sdílí se mezi diváky.

MAX7219 řídí jas po modulech v 16 úrovních. Fade používá společný jas obrazu;
jednotlivé pixely nemají vlastní odstíny. Přenos do karty má síťové zpoždění
a může vynechat mezisnímky. Nejde o odhad posunu textu v prohlížeči.

## Home Assistant Marketplace

Použijte **Nastavení → Marketplace → Přidat z odkazu**
a vložte `https://github.com/CooLajz/Pajenicko-BuzzerDisplay-Enhanced`.
Typ obsahu je **Integrace**. Poté přidejte
Pajenicko BuzzerDisplay Enhanced v **Nastavení → Zařízení a služby**. Minimální cílová verze
pro Marketplace je Home Assistant 2026.11.

Repozitář obsahuje právě jednu integraci v `custom_components/buzzer_display/`
a `hacs.json` v kořeni. Karta je součástí integrace a její modul se zaregistruje
automaticky. Samostatný repozitář ani druhá instalace karty nejsou potřeba.

Při prvním spuštění se na panelu zobrazí šestimístný párovací kód. Znovu jej
zobrazíte podržením tlačítka BOOT po dobu jedné sekundy. Platí tři minuty.
V průvodci HA zadejte adresu zařízení a tento kód. Dlouhodobý klíč se uloží
do konfigurace HA a do NVS zařízení, nikoli do firmwaru nebo do karty.

V možnostech integrace přidejte obrazovky. Pro pevnou zprávu vyplňte pouze text.
Pro hodnotu vyberte entitu; text se použije jako popisek před hodnotou.
Nedostupný senzor se zobrazuje jako „Nedostupné“. Doba obrazovky je minimální:
dlouhý text se nejprve celý posune. Oznámení má naopak pevnou dobu platnosti.

Příklad karty (entitu nahraďte skutečnou entitou zařízení):

```yaml
type: custom:buzzer-display-card
entity: sensor.buzzer_display_abcdef_sila_signalu
title: Displej v pracovně
```

Automatizace mohou použít akci `buzzer_display.show_message`. Vyberte zařízení,
text, dobu zobrazení, rychlost a efekty ve vizuálním editoru akce. Pro jednoduché
ovládání jsou k dispozici také entity jasu, zapnutí, otočení, zprávy, síly signálu,
doby běhu, zastaralých údajů a tlačítko ukončení oznámení.

## Firmware a Wi-Fi

Cíl: ESP32-S3, 16 MiB quad flash, 4 × MAX7219, 32 × 8 bodů.
Piny jsou DIN 40, CLK 39, CS 41. PSRAM se nepoužívá. USB převodník komunikuje
přes UART na 115200 baud. Výchozí otočení bylo ověřeno na testovacím panelu;
v integraci lze přepnout otočení o 180°.

Pro Firmware Hub se připravuje ZIP s `project.json`, `manifest.json` a kompaktním
factory obrazem. Podporuje Improv Serial včetně seznamu dostupných Wi-Fi sítí.
Publikování na firmware.nebovidy.cz je samostatný krok po fyzickém ověření.
Pravidla portálu: [integrační pokyny Firmware Hub](https://firmware.nebovidy.cz/integration/INSTRUCTIONS.md).

Pro lokální test lze vyplnit `WIFI_SSID` a `WIFI_PASSWORD` v ignorovaném `.env`
podle `.env.example` a spustit `python3 tools/provision_wifi.py /dev/cu.usbserial-…`.
Název sítě může obsahovat mezery, s uvozovkami i bez nich. Nástroj potřebuje
`pyserial`; soubor `.env` se nespouští jako shellový skript.

Pokud není dostupná Wi-Fi, po uplynutí časového limitu se spustí servisní AP
`buzzer-XXXXXX`. Jeho heslo je `BD` následované šestimístným kódem z displeje.
Prohlížeč se ke správě páruje samostatně stejným postupem přes BOOT.
Přístupový bod se po obnovení Wi-Fi a ukončení párování vypne.

Přihlašovací údaje nové sítě se do NVS uloží jako jeden záznam až po úspěšném
připojení. Neúspěšný pokus nenahradí původní fungující nastavení.

## Sestavení

Použijte Arduino CLI, balíček `esp32:esp32@3.0.7` a `MD_MAX72XX@3.5.1`.
Projekt používá Wi-Fi, NVS, HTTP server s WebSockety a cJSON ze stejného ESP32
core; nepotřebuje další webový framework ani MQTT knihovnu.

```sh
arduino-cli core install esp32:esp32@3.0.7 --config-file arduino-cli.yaml
arduino-cli lib install MD_MAX72XX@3.5.1 --config-file arduino-cli.yaml
python3 tools/build.py
python3 tools/package_firmware.py
```

Lokální cesty nástrojů lze nastavit v ignorovaném `tools/local.json` a
`arduino-cli.local.yaml`. Build ověřuje skutečné rozložení factory obrazu,
velikost aplikace vůči partition a prázdnou oblast NVS. ZIP neobsahuje nastavení,
zdrojové soubory ani tajné klíče. OTA aktualizace přes síť zatím nejsou implementované.

## Testy

```sh
mkdir -p build
clang++ -std=c++17 -fsanitize=address,undefined -I firmware/BuzzerDisplay \
  tests/display_core_test.cpp firmware/BuzzerDisplay/display_core.cpp -o build/core-tests
./build/core-tests
PYTHONPATH=. python -m pytest -q
python tools/preview_server.py
```

Pythonové testy vyžadují Home Assistant, pytest-homeassistant-custom-component
a aiohttp. Webový náhled běží pouze na `127.0.0.1:8765`, testovací kód je `123456`.
Jeho pixely vytváří stejné C++ jádro. Není náhradou za fyzický test.

## Data a kompatibilita

Před prvním veřejným vydáním je výchozí aktuální schéma NVS 1 v namespace
`buzzer`. Interní vývojové formáty nemají migrační závazek. Tovární konfigurace
Pájeníčka se neimportuje; Wi-Fi se nastaví přes Improv. Cizí namespace aplikace
sama nemaže. Factory instalace s vymazáním uživatelských dat je destruktivní.
Neznámé schéma našeho namespace zablokuje změny konfigurace bez tichého přepsání.

Nebyla založena historie podporovaných veřejných vydání. Čistá instalace,
uložená Wi-Fi a párování po aktualizaci, skutečný obraz matice i návrat po
neúspěšné změně sítě již byly ověřeny. Před stabilním vydáním zbývá dlouhodobý
test vypnutí/zapnutí routeru a celá instalace v HA 2026.11.

## Původ komponent

Aplikační firmware, font, API, integrace a karta jsou nové. Z původního projektu
Pájeníčka byly zjištěny hardwarové parametry, nikoli převzata aplikační logika.
Ovladač MD_MAX72XX je externí knihovna. Parser Improv vychází z oficiálního SDK;
viz [licenční informace](THIRD_PARTY.md). Nový kód projektu je pod [licencí MIT](LICENSE).
