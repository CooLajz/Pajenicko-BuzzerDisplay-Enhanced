#pragma once
#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace buzzer {
enum class Effect { None, Left, Right, Up, Down, Fade };
enum class Blink { None, Hard, Fade };
struct Page {
  std::string id = "page";
  std::string text;
  uint32_t holdMs = 5000;
  uint32_t transitionMs = 600;
  uint32_t blinkMs = 1000;
  uint8_t speed = 20;  // Pixely za sekundu; nula znamená statický text.
  bool scrollRight = false;
  bool invert = false;
  Effect enter = Effect::None;
  Effect exit = Effect::None;
  Blink blink = Blink::None;
};
struct Frame {
  std::array<uint8_t, 32> columns{}; // Bit 0 je horní řádek.
  uint8_t brightness = 4;
  bool on = true;
  bool stale = false;
  uint8_t page = 0;
};
std::vector<uint8_t> rasterize(const std::string& text);
bool validUtf8(const std::string& text);
class DisplayEngine {
 public:
  void playlist(const std::vector<Page>& pages, uint32_t now, uint32_t ttlMs);
  void notify(const Page& page, uint32_t now, uint32_t durationMs);
  void clearNotification();
  void settings(uint8_t brightness, bool on);
  Frame render(uint32_t now);
 private:
  std::vector<Page> pages_;
  Page notice_;
  bool notifying_ = false;
  uint32_t noticeAt_ = 0, noticeDuration_ = 0;
  uint32_t pageAt_ = 0, receivedAt_ = 0, ttlMs_ = 0;
  uint8_t index_ = 0, brightness_ = 4;
  bool on_ = true;
};
// Časování pokusů je nezávislé na výsledku minulého spojení.
class RetrySchedule {
 public:
  bool due(uint32_t now) const { return !armed_ || uint32_t(now - at_) >= delay_; }
  void attempted(uint32_t now) { at_ = now; armed_ = true; delay_ = delay_ ? (delay_ < 30000 ? delay_ * 2 : 60000) : 2000; }
  void connected() { armed_ = false; delay_ = 0; }
 private:
  uint32_t at_ = 0, delay_ = 0;
  bool armed_ = false;
};
}
