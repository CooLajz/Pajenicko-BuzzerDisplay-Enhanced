# Komponenty třetích stran

Licence MIT v kořeni se vztahuje na nový kód tohoto projektu. Následující
komponenty si zachovávají své vlastní licence.

- **Arduino ESP32 3.0.7**: https://github.com/espressif/arduino-esp32
  Používá se beze změn přes Arduino CLI. Licence komponent jsou součástí SDK.
- **MD_MAX72XX 3.5.1**: https://github.com/MajicDesigns/MD_MAX72XX
  Ovladač MAX7219, licence LGPL-2.1; instalován jako externí knihovna.
- **Improv Wi-Fi C++ SDK**: https://github.com/improv-wifi/sdk-cpp
  Základ `improv.h` a `improv.cpp`, commit
  `17898613a1c17062ca5af295ceb639b16b4930bf`, Apache-2.0.
  Použita lokální varianta již používaná v projektech autora, s kontrolami délek
  a přizpůsobením Arduino. Odesílání celých rámců a provozní stavový automat
  jsou implementované v tomto projektu. Text licence je v `licenses/Improv-Apache-2.0.txt`.
- **Pájeníčko BuzerDisplej**: https://github.com/Pajenicko/BuzerDisplej
  Zdroj hardwarového zapojení a typu mapování LED, nikoli zdroj aplikačního kódu.
