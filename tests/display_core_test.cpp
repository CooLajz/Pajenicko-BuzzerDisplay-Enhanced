#include "display_core.h"
#include <cassert>
#include <iostream>
#include <iomanip>
using namespace buzzer;
static bool any(const Frame& f) { for(auto b:f.columns)if(b)return true;return false; }
int main(int argc,char**argv) {
  if(argc>1 && std::string(argv[1])=="--frames") {
    DisplayEngine e;Page p;p.id="test";p.text=argc>2?argv[2]:"23,5°C";
    if(argc>3)p.speed=atoi(argv[3]);if(argc>4)p.blink=Blink(atoi(argv[4]));if(argc>5)p.invert=atoi(argv[5]);
    if(argc>6)p.enter=Effect(atoi(argv[6]));if(argc>7)p.exit=Effect(atoi(argv[7]));
    e.notify(p,0,10000);
    for(uint32_t t=0;t<10000;t+=40){auto f=e.render(t);std::cout<<"{\"pixels\":\"";for(auto c:f.columns)std::cout<<std::hex<<std::setw(2)<<std::setfill('0')<<int(c);std::cout<<std::dec<<"\",\"brightness\":"<<int(f.brightness)<<",\"on\":"<<(f.on?"true":"false")<<",\"stale\":false,\"page\":0,\"seq\":"<<t/40<<"}\n";}return 0;
  }
  assert(validUtf8("Příliš žluťoučký kůň 23,5 °C 45 %"));
  assert(!validUtf8(std::string("\xc0\xaf",2)));assert(!validUtf8(std::string("\xed\xa0\x80",3)));assert(!validUtf8("text\n"));
  assert(rasterize("23,5°C").size()<=32);assert(rasterize("℃")==rasterize("°C"));
  for(auto pair: {std::pair<const char*,const char*>{"č","c"},{"ě","e"},{"ř","r"},{"š","s"},{"ž","z"},{"ť","t"},{"ď","d"},{"ň","n"},{"ů","u"},{"ý","y"}})assert(rasterize(pair.first)!=rasterize(pair.second));
  Page p;p.text="23,5°C";DisplayEngine e;e.playlist({p},0,90000);
  auto base=e.render(0);assert(any(base)&&!base.stale);
  p.invert=true;e.playlist({p},0,90000);auto inverse=e.render(0);
  for(int i=0;i<32;++i)assert(uint8_t(~base.columns[i])==inverse.columns[i]);
  p.invert=false;p.blink=Blink::Hard;e.playlist({p},0,90000);assert(e.render(0).on);assert(!e.render(500).on);assert(!any(e.render(500)));assert(e.render(1000).on);
  p.blink=Blink::Fade;e.playlist({p},0,90000);assert(e.render(0).brightness>e.render(200).brightness);assert(!e.render(500).on);
  p.blink=Blink::None;
  for(auto effect:{Effect::Left,Effect::Right,Effect::Up,Effect::Down}) {p.enter=effect;e.playlist({p},0,90000);assert(!any(e.render(0)));assert(any(e.render(600)));}
  p.enter=Effect::Fade;e.playlist({p},0,90000);assert(!e.render(0).on);assert(e.render(600).on);
  p.enter=Effect::None;p.exit=Effect::Fade;e.notify(p,0,1000);assert(e.render(100).brightness>e.render(800).brightness);assert(!e.render(990).on);
  e.clearNotification();p.exit=Effect::None;p.text="ABCDEFGHIJKLMNOPQRSTUVWXYZ";p.speed=20;e.playlist({p},0,90000);
  assert(e.render(0).columns!=e.render(100).columns);
  p.scrollRight=true;e.playlist({p},0,90000);assert(e.render(0).columns!=e.render(100).columns);
  p.speed=0;e.playlist({p},0,90000);assert(e.render(0).columns==e.render(100).columns);
  Page q;q.id="next";q.text="NEXT";p.speed=20;p.holdMs=1000;e.playlist({p,q},0,90000);
  assert(e.render(2000).page==0);assert(e.render(20000).page==1);
  e.playlist({p},0xfffff000u,10000);assert(!e.render(0).stale);assert(e.render(0x2000).stale);
  e.settings(15,false);assert(!e.render(0).on);e.settings(15,true);assert(e.render(0).on);
  DisplayEngine startup;
  const auto firstStartup=startup.render(0);
  assert(firstStartup.columns!=startup.render(100).columns);
  assert(firstStartup.columns==startup.render(20000).columns);
  assert(firstStartup.columns!=startup.render(20100).columns);
  startup.playlist({q},0,1000);
  const auto firstStale=startup.render(10000);
  assert(firstStale.stale);
  assert(firstStale.columns!=startup.render(10100).columns);
  assert(firstStale.columns==startup.render(20000).columns);
  RetrySchedule retry;assert(retry.due(0));retry.attempted(0);assert(!retry.due(1999));assert(retry.due(2000));
  uint32_t now=2000;for(int i=0;i<30;++i){retry.attempted(now);assert(retry.due(now+60000));now+=60000;}
  retry.connected();assert(retry.due(now));retry.attempted(0xfffffff0);assert(retry.due(2000));
  std::cout<<"Testy rendereru, UTF-8, efektů, expirace a opakovaných pokusů prošly.\n";
}
