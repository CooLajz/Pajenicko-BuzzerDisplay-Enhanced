#include "display_core.h"
#include "font.h"
#include <algorithm>
#include <cmath>

namespace buzzer {
static bool decode(const std::string& text, size_t& i, uint32_t& c) {
  const auto lead = uint8_t(text[i++]);
  if (lead < 128) { c = lead; return true; }
  int n = lead >= 0xc2 && lead <= 0xdf ? 1 : lead >= 0xe0 && lead <= 0xef ? 2 : lead >= 0xf0 && lead <= 0xf4 ? 3 : -1;
  if (n < 0 || i + n > text.size()) return false;
  c = lead & (0x7f >> (n + 1));
  for (int j = 0; j < n; ++j) {
    uint8_t next = text[i++];
    if ((next & 0xc0) != 0x80) return false;
    c = (c << 6) | (next & 63);
  }
  return c >= (n == 1 ? 0x80u : n == 2 ? 0x800u : 0x10000u) && c <= 0x10ffff && !(c >= 0xd800 && c <= 0xdfff);
}
bool validUtf8(const std::string& text) {
  size_t i = 0; uint32_t c;
  while (i < text.size()) if (!decode(text, i, c) || c < 32 || c == 127) return false;
  return true;
}
std::vector<uint8_t> rasterize(const std::string& text) {
  std::vector<uint8_t> result;
  size_t i = 0; uint32_t c;
  while (i < text.size()) {
    if (!decode(text, i, c)) c = '?';
    if (c == 0x2103 || c == 0x2109) {
      const auto degree = glyphFor(0xb0);
      result.insert(result.end(), degree.begin(), degree.end()); result.push_back(0);
      c = c == 0x2103 ? 'C' : 'F';
    }
    const auto glyph = glyphFor(c);
    result.insert(result.end(), glyph.begin(), glyph.end());
    result.push_back(0);
  }
  if (!result.empty()) result.pop_back();
  return result;
}
void DisplayEngine::playlist(const std::vector<Page>& pages, uint32_t now, uint32_t ttlMs) {
  bool same = pages.size() == pages_.size();
  for (size_t i = 0; same && i < pages.size(); ++i) same = pages[i].id == pages_[i].id;
  pages_ = pages; receivedAt_ = now; ttlMs_ = ttlMs;
  if (!same || index_ >= pages_.size()) { index_ = 0; pageAt_ = now; }
}
void DisplayEngine::notify(const Page& page, uint32_t now, uint32_t durationMs) {
  notice_ = page; noticeAt_ = now; noticeDuration_ = durationMs; notifying_ = true;
}
void DisplayEngine::clearNotification() { notifying_ = false; }
void DisplayEngine::settings(uint8_t brightness, bool on) { brightness_ = std::min<uint8_t>(brightness, 15); on_ = on; }
static uint32_t holdTime(const Page& page, size_t width) {
  return std::max(page.holdMs, width > 32 && page.speed ? uint32_t((width - 32) * 1000 / page.speed + 1500) : 0u);
}
Frame DisplayEngine::render(uint32_t now) {
  Frame frame; frame.brightness = brightness_; frame.on = on_;
  if (!on_) return frame;
  const bool stale = ttlMs_ && uint32_t(now - receivedAt_) >= ttlMs_;
  frame.stale = stale;
  if (notifying_ && uint32_t(now - noticeAt_) >= noticeDuration_) { notifying_ = false; pageAt_ = now; }
  Page fallback;
  fallback.text = stale ? "Data nejsou dostupná" : "Pajenicko BuzzerDisplay Enhanced";
  fallback.id = "fallback";
  const Page* page = notifying_ ? &notice_ : (stale || pages_.empty() ? &fallback : &pages_[index_]);
  uint32_t age = now - (notifying_ ? noticeAt_ : pageAt_);
  auto pixels = rasterize(page->text);
  auto duration = [&](const Page& p, size_t width) { return holdTime(p, width) + (p.enter == Effect::None ? 0 : p.transitionMs) + (p.exit == Effect::None ? 0 : p.transitionMs); };
  if (!notifying_ && age >= duration(*page, pixels.size())) {
    pageAt_ = now; age = 0;
    if (!stale && !pages_.empty()) {
      index_ = (index_ + 1) % pages_.size();
      page = &pages_[index_]; pixels = rasterize(page->text);
    }
  }
  frame.page = index_;
  const uint32_t entering = page->enter == Effect::None ? 0 : page->transitionMs;
  const uint32_t holding = holdTime(*page, pixels.size());
  int x = pixels.size() <= 32 ? (32 - int(pixels.size())) / 2 : 0;
  int y = 0;
  double gain = 1.0;
  if (pixels.size() > 32 && page->speed) {
    // První i poslední znak se v rámci celé periody opravdu dostanou na panel.
    const uint32_t scrollAge = age > entering ? age - entering : 0;
    const int travel = std::min<int>(pixels.size()-32, uint64_t(scrollAge) * page->speed / 1000);
    x = page->scrollRight ? 32 - int(pixels.size()) + travel : -travel;
  }
  auto transition = [&](Effect effect, double distance) {
    switch (effect) {
      case Effect::Left: x -= int(std::ceil(32 * distance)); break;
      case Effect::Right: x += int(std::ceil(32 * distance)); break;
      case Effect::Up: y -= int(std::ceil(8 * distance)); break;
      case Effect::Down: y += int(std::ceil(8 * distance)); break;
      case Effect::Fade: gain *= 1.0 - distance; break;
      default: break;
    }
  };
  if (entering && age < entering) transition(page->enter, 1.0 - double(age) / entering);
  else {
    const uint32_t exitAt = notifying_ ? (noticeDuration_ > page->transitionMs ? noticeDuration_ - page->transitionMs : 0) : entering + holding;
    if (age >= exitAt) transition(page->exit, std::min(1.0, double(age - exitAt) / page->transitionMs));
  }
  if (page->blink != Blink::None) {
    const double phase = double(age % page->blinkMs) / page->blinkMs;
    if (page->blink == Blink::Hard) gain *= phase < .5 ? 1 : 0;
    else gain *= .5 + .5 * std::cos(phase * 6.283185307179586);
  }
  for (int screenX = 0; screenX < 32; ++screenX) {
    int sourceX = screenX - x;
    uint8_t column = sourceX >= 0 && sourceX < int(pixels.size()) ? pixels[sourceX] : 0;
    if (y >= 8 || y <= -8) column = 0;
    else column = y >= 0 ? uint8_t(column << y) : uint8_t(column >> -y);
    frame.columns[screenX] = page->invert ? uint8_t(~column) : column;
  }
  // Registr jasu 0 stále svítí; úplné zhasnutí musí vypnout panel.
  const int level = int(std::lround((brightness_ + 1) * gain));
  frame.on = level > 0;
  frame.brightness = level > 0 ? level - 1 : 0;
  if (!frame.on) frame.columns.fill(0);
  return frame;
}
}
