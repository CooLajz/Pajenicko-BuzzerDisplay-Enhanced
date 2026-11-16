# Stav ověření

Průběžný vývojový záznam k 16. listopadu 2026. Není dokladem veřejného vydání.

## Hardware

Přes ROM/esptool potvrzen ESP32-S3 rev. 0.2, krystal 40 MHz, quad flash 16 MiB.
Po přepojení z USB hubu se port změnil z `cu.usbserial-130` na `cu.usbserial-110`.
Záloha byla na výslovný pokyn vlastníka vynechána. Původní firmware lze nahrát
instalátorem výrobce; původní uživatelské nastavení tím není garantováno.

- Nahrán factory obraz vývojové verze `0.1.0-dev.1`; esptool ověřil hash zápisu.
- Improv na skutečném zařízení: metadata, stav, seznam Wi-Fi sítí a jeho ukončení.
- Wi-Fi nastavena přes Improv z lokálního `.env`, včetně SSID obsahujícího mezeru.
- Následný zápis pouze aplikace a restart zachovaly Wi-Fi i párování.
- Identifikátor načten z fyzické MAC, nikoli z dosud neinicializovaného rozhraní.
- Neexistující náhodná Wi-Fi byla odmítnuta po 20 sekundách. Zařízení se samo
  vrátilo k původní síti a HTTP API bez opětovného zadání hesla.
- Fyzické párování proběhlo kódem z panelu. HTTP API odmítlo nesprávný klíč.
- Skutečný WS buffer pro `23,5°C` byl porovnán se všemi 32 sloupci fontu.
  Ověřeno postupující číslování snímků, ostré blikání, více úrovní fade,
  pohyb českého textu a opakované připojení klienta včetně návratu Wi-Fi.
- Vlastník potvrdil zobrazenou teplotu, český text a efekty na LED panelu.

## Software

- Arduino ESP32 3.0.7: první a následný build prošly.
- Nativní C++ testy s AddressSanitizer a UndefinedBehaviorSanitizer: prošly.
- Pokryté chování: platné/neplatné UTF-8, odlišení českých znaků, inverze,
  blikání obou typů, nájezdy, fade-out oznámení, posun v obou směrech,
  statický režim, čas na průchod dlouhého textu, opakování úvodních a chybových
  textů, expirace a přetečení millis.
- Opakované pokusy o připojení mají jednotkové testy časování. Fyzický výpadek
  Wi-Fi zatím nebyl ověřen.
- Lokální HA testy používají existující prostředí 2026.2.3. Běh ani instalace
  přes Marketplace v 2026.11 tím nejsou prokázány. Šest testů pokrývá formátování,
  validaci protokolu, strukturu balíčku, klienta/koordinátor, import všech platforem
  a průvodce párováním s uložením nastavení obrazovky.

## Web a karta

Ověřeno v Codex IAB na lokálním testovacím serveru, nikoli na fyzickém zařízení:
párování, živé pixely, odeslání textu, volba plynulého blikání, nájezd shora,
fade-out, náhled karty. Prohlížeč u karty nehlásil chyby konzole.
Ověřena šířka 390 px; dokument měl 375 px bez vodorovného přetečení.
Desktopový návrh i realizace byly prohlédnuty pomocí view_image.
HTTP server fyzického zařízení poskytuje přesně sestavený HTML zdroj v gzip.
Náhledy z lokálního testovacího serveru neobsahují skutečné údaje uživatele.
Po přejmenování byly znovu zkontrolovány viewporty 1440 × 1024 a 390 × 844,
bez vodorovného přetečení. Karta nehlásila chyby konzole.
Snímky: [web](web-preview.jpg) a [karta](card-preview.jpg).

### Srovnání s návrhem

| Oblast | Výsledek |
| --- | --- |
| Struktura | Zachována horní navigace, náhled, formulář a vedlejší diagnostika. |
| Barvy | Bílé pozadí, tmavá matice, červený akcent, jemné dělicí linky. |
| Texty | České texty s vykáním; rozšířeno o uživatelem vyžádané směry efektů. |
| Název | Na přání vlastníka změněn na Pajenicko BuzzerDisplay Enhanced. |
| Typografie | Systémové písmo; menší ovladače kvůli dalším požadovaným nastavením. |
| Matice | Záměrně skutečných 32 × 8 bodů a náš font místo přibližné kresby návrhu. |
| Jas | Záměrně odpovídá přijatému snímku, není trvale na maximální červené. |
| Mobil | Jeden sloupec, ovladače ve dvou sloupcích, bez přetečení. |

Návrh `web-concept.png` vznikl vestavěným Image Gen. Zadání: čistý bílý
český ovládací panel Buzzer Display, červená 32 × 8 matice, zkušební zpráva,
stav zařízení a záložky Přehled, Wi-Fi, Spárování, Diagnostika.

## Dosud neověřeno / nepřipraveno ke stabilnímu vydání

Improv přímo ve webovém instalátoru, opakované vypnutí a zapnutí skutečného AP,
dlouhodobý provoz, celý tok v HA 2026.11 a publikování na Firmware Hub.
Zkouška neexistující sítě není náhradou za dlouhodobý test výpadků routeru.
Do domácího serveru nebylo zasahováno. OTA aktualizace nejsou implementované.
