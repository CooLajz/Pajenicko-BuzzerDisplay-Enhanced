#include "runtime.h"
#include "version.h"
#include "display_core.h"
#include "web_assets.h"
#include "improv.h"
#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <DNSServer.h>
#include <MD_MAX72xx.h>
#include <esp_http_server.h>
#include <esp_system.h>
#include <esp_mac.h>
#include <cJSON.h>
#include <atomic>
#include <algorithm>
#include <memory>

using namespace buzzer;
namespace {
MD_MAX72XX matrix(MD_MAX72XX::DR1CR0RR0_HW, 40, 39, 41, 4);
Preferences prefs;
DNSServer dns;
httpd_handle_t server = nullptr;
QueueHandle_t commands, wifiCommands;
DisplayEngine engine;
portMUX_TYPE frameLock = portMUX_INITIALIZER_UNLOCKED;
Frame currentFrame;
std::atomic<bool> frameWorkPending{false}, paired{false}, schemaOK{true};
std::atomic<uint8_t> settingBrightness{4};
std::atomic<bool> settingOn{true}, settingRotation{true};
std::atomic<uint32_t> pairingUntil{0};
String deviceID, hostname, apiToken, pairingCode;
String wifiSSID, wifiPassword, pendingSSID, pendingPassword;
bool pendingWiFi = false, pendingImprov = false, haveIP = false, apActive = false, scanPending = false;
bool connectingAttempt = false;
uint32_t connectAt = 0;
uint32_t wifiAt = 0, disconnectedAt = 0, buttonAt = 0, lastScanAt = 0;
uint32_t serialAt = 0, frameSequence = 0;
RetrySchedule retry;
struct Command {
  enum Kind { Playlist, Notification, Clear, Settings } kind;
  std::vector<Page> pages;
  uint32_t duration = 0;
  uint8_t brightness = 4;
  bool on = true, rotation = true;
};
struct WiFiCommand { char ssid[33]; char password[65]; bool improv = false; };
struct StoredWiFi { char ssid[33]; char password[65]; };
using Json = std::unique_ptr<cJSON, decltype(&cJSON_Delete)>;
Json json(cJSON* value) { return Json(value, cJSON_Delete); }
const cJSON* field(const cJSON* obj, const char* key) { return cJSON_GetObjectItemCaseSensitive(obj, key); }
const char* str(const cJSON* obj, const char* key) { const auto p = field(obj,key); return cJSON_IsString(p) ? p->valuestring : nullptr; }
bool windowOpen() { const uint32_t end=pairingUntil.load();return end && int32_t(end - millis()) > 0; }
bool push(Command* command) {
  if (xQueueSend(commands, &command, 0) == pdTRUE) return true;
  delete command; return false;
}
void showNotice(const std::string& text, uint32_t duration) {
  auto c = new Command; c->kind = Command::Notification; c->duration = duration;
  Page p; p.text = text; c->pages.push_back(p); push(c);
}
void openPairing() {
  pairingUntil = millis() + 180000;
}
void renderTask(void*) {
  matrix.begin(); matrix.control(MD_MAX72XX::UPDATE, MD_MAX72XX::OFF);
  const auto codePixels = rasterize(pairingCode.c_str());
  TickType_t tick = xTaskGetTickCount();
  for (;;) {
    Command* raw = nullptr;
    while (xQueueReceive(commands, &raw, 0) == pdTRUE) {
      std::unique_ptr<Command> c(raw);
      switch (c->kind) {
        case Command::Playlist: engine.playlist(c->pages, millis(), c->duration); break;
        case Command::Notification: engine.notify(c->pages.front(), millis(), c->duration); break;
        case Command::Clear: engine.clearNotification(); break;
        case Command::Settings:
          settingBrightness = c->brightness; settingOn = c->on; settingRotation = c->rotation;
          engine.settings(c->brightness,c->on); break;
      }
    }
    Frame next = engine.render(millis());
    if (windowOpen() && schemaOK) {
      // Fyzické párování musí být čitelné i při vypnutí displeje z HA.
      next.columns.fill(0); next.on = true; next.brightness = std::max<uint8_t>(4, settingBrightness);
      const size_t left = codePixels.size() < 32 ? (32-codePixels.size())/2 : 0;
      for (size_t x=0; x<codePixels.size() && x+left<32; ++x) next.columns[x+left]=codePixels[x];
    }
    matrix.control(MD_MAX72XX::SHUTDOWN, next.on ? MD_MAX72XX::OFF : MD_MAX72XX::ON);
    matrix.control(MD_MAX72XX::INTENSITY, next.brightness);
    for (int x=0; x<32; ++x) for (int y=0; y<8; ++y) {
      // Logické souřadnice jsou vlevo nahoře. Výchozí montáž je otočená o 180°.
      const int col = settingRotation ? x : 31-x;
      const int row = settingRotation ? 7-y : y;
      matrix.setPoint(row,col,next.on && (next.columns[x] & (1 << y)));
    }
    matrix.update();
    portENTER_CRITICAL(&frameLock); currentFrame = next; ++frameSequence; portEXIT_CRITICAL(&frameLock);
    vTaskDelayUntil(&tick, pdMS_TO_TICKS(20));
  }
}
Json frameJson() {
  Frame frame; uint32_t sequence;
  portENTER_CRITICAL(&frameLock); frame=currentFrame; sequence=frameSequence; portEXIT_CRITICAL(&frameLock);
  auto result=json(cJSON_CreateObject()); char hex[65];
  for (size_t i=0;i<32;++i) snprintf(hex+i*2,3,"%02x",frame.columns[i]);
  cJSON_AddStringToObject(result.get(),"pixels",hex);
  cJSON_AddNumberToObject(result.get(),"seq",sequence);
  cJSON_AddNumberToObject(result.get(),"brightness",frame.brightness);
  cJSON_AddBoolToObject(result.get(),"on",frame.on);
  cJSON_AddBoolToObject(result.get(),"stale",frame.stale);
  cJSON_AddNumberToObject(result.get(),"page",frame.page);
  return result;
}
esp_err_t reply(httpd_req_t* req, const cJSON* value, const char* status="200 OK") {
  char* payload=cJSON_PrintUnformatted(value);
  if (!payload) return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"Nedostatek paměti.");
  httpd_resp_set_status(req,status); httpd_resp_set_type(req,"application/json");
  httpd_resp_set_hdr(req,"Cache-Control","no-store");
  httpd_resp_set_hdr(req,"X-Content-Type-Options","nosniff");
  esp_err_t err=httpd_resp_send(req,payload,HTTPD_RESP_USE_STRLEN); cJSON_free(payload); return err;
}
esp_err_t error(httpd_req_t* req,const char* status,const char* text) {
  auto result=json(cJSON_CreateObject()); cJSON_AddStringToObject(result.get(),"error",text); return reply(req,result.get(),status);
}
bool authorized(httpd_req_t* req) {
  char token[64] = {};
  if (!schemaOK || !paired || httpd_req_get_hdr_value_str(req,"X-Buzzer-Key",token,sizeof(token)) != ESP_OK || apiToken != token) {
    error(req,"401 Unauthorized","Zařízení není spárováno nebo je klíč neplatný."); return false;
  }
  return true;
}
Json body(httpd_req_t* req) {
  char type[64]={};
  if (req->content_len < 2 || req->content_len > 16384 || httpd_req_get_hdr_value_str(req,"Content-Type",type,sizeof(type)) != ESP_OK || strncmp(type,"application/json",16)) return json(nullptr);
  std::string buffer(req->content_len,'\0'); size_t received=0;
  while (received<buffer.size()) { int n=httpd_req_recv(req,&buffer[received],buffer.size()-received); if(n<=0) return json(nullptr); received+=n; }
  return json(cJSON_ParseWithLength(buffer.data(),buffer.size()));
}
bool number(const cJSON* obj,const char* name,int lo,int hi,uint32_t& output) {
  const auto v=field(obj,name); if(!v) return true;
  if(!cJSON_IsNumber(v) || v->valuedouble<lo || v->valuedouble>hi || v->valuedouble!=int(v->valuedouble)) return false;
  output=v->valueint; return true;
}
bool boolean(const cJSON* obj,const char* name,bool& output) {
  const auto v=field(obj,name); if(!v) return true; if(!cJSON_IsBool(v)) return false; output=cJSON_IsTrue(v); return true;
}
bool effect(const cJSON* obj,const char* name,Effect& output) {
  if(!field(obj,name)) return true; const char* value=str(obj,name); if(!value) return false;
  const char* names[]={"none","left","right","up","down","fade"};
  for(int i=0;i<6;++i) if(!strcmp(value,names[i])) {output=Effect(i);return true;} return false;
}
bool page(const cJSON* obj,Page& p) {
  const char* text=str(obj,"text"); if(!text || strlen(text)>384 || !validUtf8(text)) return false; p.text=text;
  if (const char* id=str(obj,"id")) { if(!*id || strlen(id)>32) return false; p.id=id; }
  uint32_t speed=p.speed;
  if(!number(obj,"hold_ms",1000,300000,p.holdMs) || !number(obj,"transition_ms",100,5000,p.transitionMs) || !number(obj,"blink_ms",200,10000,p.blinkMs) || !number(obj,"speed",0,80,speed) || !boolean(obj,"invert",p.invert) || !boolean(obj,"scroll_right",p.scrollRight) || !effect(obj,"enter",p.enter) || !effect(obj,"exit",p.exit)) return false;
  p.speed=speed;
  if(field(obj,"blink")) { const char* value=str(obj,"blink"); if(!value) return false;
    if(!strcmp(value,"none"))p.blink=Blink::None; else if(!strcmp(value,"hard"))p.blink=Blink::Hard; else if(!strcmp(value,"fade"))p.blink=Blink::Fade; else return false; }
  return true;
}
esp_err_t api(httpd_req_t* req) {
  const String path(req->uri);
  if(req->method==HTTP_GET && path=="/api/info") {
    auto result=json(cJSON_CreateObject());
    cJSON_AddStringToObject(result.get(),"name",BUZZER_NAME); cJSON_AddStringToObject(result.get(),"id",deviceID.c_str());
    cJSON_AddStringToObject(result.get(),"version",BUZZER_VERSION); cJSON_AddStringToObject(result.get(),"hardware",BUZZER_PROFILE);
    cJSON_AddNumberToObject(result.get(),"api",1); cJSON_AddBoolToObject(result.get(),"paired",paired); cJSON_AddBoolToObject(result.get(),"storage_ok",schemaOK);
    return reply(req,result.get());
  }
  if(req->method==HTTP_POST && path=="/api/pair") {
    static uint32_t lastAttempt=0; static bool attempted=false;
    if(attempted && uint32_t(millis()-lastAttempt)<1000) return error(req,"429 Too Many Requests","Vyčkejte jednu sekundu.");
    lastAttempt=millis(); attempted=true;
    auto doc=body(req); const char* code=doc ? str(doc.get(),"code") : nullptr;
    if(!schemaOK || !windowOpen() || !code || pairingCode!=code) return error(req,"403 Forbidden","Otevřete párování tlačítkem BOOT a zadejte kód z displeje.");
    if(!paired) { if(!prefs.putBool("paired",true)) return error(req,"500 Internal Server Error","Párování nelze uložit."); paired=true; }
    pairingUntil=0;
    auto result=json(cJSON_CreateObject());cJSON_AddStringToObject(result.get(),"token",apiToken.c_str());cJSON_AddStringToObject(result.get(),"id",deviceID.c_str());
    return reply(req,result.get());
  }
  if(!authorized(req)) return ESP_OK;
  if(req->method==HTTP_GET && path=="/api/state") {
    auto result=frameJson();
    cJSON_AddNumberToObject(result.get(),"rssi",WiFi.status()==WL_CONNECTED ? WiFi.RSSI() : -127);
    cJSON_AddNumberToObject(result.get(),"uptime",millis()/1000);
    cJSON_AddNumberToObject(result.get(),"heap",ESP.getFreeHeap());
    cJSON_AddNumberToObject(result.get(),"target_brightness",settingBrightness);
    cJSON_AddBoolToObject(result.get(),"enabled",settingOn);
    cJSON_AddBoolToObject(result.get(),"rotation",settingRotation);
    cJSON_AddBoolToObject(result.get(),"wifi_connected",WiFi.status()==WL_CONNECTED);
    cJSON_AddStringToObject(result.get(),"version",BUZZER_VERSION);
    cJSON_AddStringToObject(result.get(),"ip",WiFi.localIP().toString().c_str());
    return reply(req,result.get());
  }
  if(req->method==HTTP_GET && path=="/api/frame") {auto result=frameJson();return reply(req,result.get());}
  if(req->method==HTTP_DELETE && path=="/api/notification") {auto c=new Command;c->kind=Command::Clear;if(!push(c))return error(req,"503 Service Unavailable","Fronta je plná.");}
  else if(req->method==HTTP_POST || req->method==HTTP_PUT) {
    auto doc=body(req);if(!doc || !cJSON_IsObject(doc.get()))return error(req,"400 Bad Request","Požadavek musí obsahovat platný objekt JSON.");
    if(path=="/api/wifi") {
      const char* ssid=str(doc.get(),"ssid");const char* password=str(doc.get(),"password");
      if(!ssid || !*ssid || strlen(ssid)>32 || !password || strlen(password)>63) return error(req,"400 Bad Request","Zkontrolujte údaje Wi-Fi.");
      WiFiCommand c={};strlcpy(c.ssid,ssid,sizeof(c.ssid));strlcpy(c.password,password,sizeof(c.password));
      if(xQueueSend(wifiCommands,&c,0)!=pdTRUE)return error(req,"409 Conflict","Připojování již probíhá.");
    } else {
      auto c=std::make_unique<Command>();
      if(path=="/api/playlist") {
        c->kind=Command::Playlist;c->duration=90000;
        const auto list=field(doc.get(),"pages");
        if(!cJSON_IsArray(list) || cJSON_GetArraySize(list)<1 || cJSON_GetArraySize(list)>8 || !number(doc.get(),"ttl_ms",10000,3600000,c->duration))return error(req,"400 Bad Request","Seznam musí mít 1 až 8 obrazovek a platnou dobu platnosti.");
        for(int i=0;i<cJSON_GetArraySize(list);++i) {Page p;if(!page(cJSON_GetArrayItem(list,i),p))return error(req,"400 Bad Request","Neplatná obrazovka.");for(const auto& old:c->pages)if(old.id==p.id)return error(req,"400 Bad Request","Identifikátory obrazovek musí být jedinečné.");c->pages.push_back(p);}
      } else if(path=="/api/notification") {
        c->kind=Command::Notification;c->duration=10000;Page p;
        if(!page(doc.get(),p) || !number(doc.get(),"duration_ms",1000,300000,c->duration))return error(req,"400 Bad Request","Neplatné oznámení.");c->pages.push_back(p);
      } else if(path=="/api/settings") {
        c->kind=Command::Settings;c->on=settingOn;c->rotation=settingRotation;uint32_t brightness=settingBrightness;
        if(!number(doc.get(),"brightness",0,15,brightness)||!boolean(doc.get(),"enabled",c->on)||!boolean(doc.get(),"rotation",c->rotation))return error(req,"400 Bad Request","Neplatné nastavení.");c->brightness=brightness;
      } else return error(req,"404 Not Found","Neznámá cesta.");
      if(!push(c.release()))return error(req,"503 Service Unavailable","Fronta je plná.");
    }
  } else return error(req,"404 Not Found","Neznámá cesta.");
  auto result=json(cJSON_CreateObject());cJSON_AddBoolToObject(result.get(),"accepted",true);return reply(req,result.get(),"202 Accepted");
}
esp_err_t live(httpd_req_t* req) {
  if(req->method==HTTP_GET) { req->sess_ctx=calloc(1,sizeof(bool));req->free_ctx=free;return req->sess_ctx ? ESP_OK : ESP_FAIL; }
  httpd_ws_frame_t packet={};packet.type=HTTPD_WS_TYPE_TEXT;
  if(httpd_ws_recv_frame(req,&packet,0)!=ESP_OK || packet.len>128)return ESP_FAIL;
  uint8_t payload[129]={};packet.payload=payload;
  if(httpd_ws_recv_frame(req,&packet,packet.len)!=ESP_OK)return ESP_FAIL;
  if(packet.type!=HTTPD_WS_TYPE_TEXT)return ESP_OK;
  auto doc=json(cJSON_ParseWithLength(reinterpret_cast<char*>(payload),packet.len));
  const char* token=doc ? str(doc.get(),"token") : nullptr;
  if(!schemaOK || !paired || !token || apiToken!=token)return ESP_FAIL;
  *static_cast<bool*>(req->sess_ctx)=true;return ESP_OK;
}
void broadcast(void*) {
  size_t count=8;int sockets[8];
  if(httpd_get_client_list(server,&count,sockets)==ESP_OK) {
    auto doc=frameJson();char* payload=cJSON_PrintUnformatted(doc.get());
    if(payload) {
      httpd_ws_frame_t frame={};frame.type=HTTPD_WS_TYPE_TEXT;frame.payload=reinterpret_cast<uint8_t*>(payload);frame.len=strlen(payload);
      for(size_t i=0;i<count;++i) {
        if(httpd_ws_get_fd_info(server,sockets[i])!=HTTPD_WS_CLIENT_WEBSOCKET)continue;
        auto auth=static_cast<bool*>(httpd_sess_get_ctx(server,sockets[i]));
        if(auth && *auth && httpd_ws_send_frame_async(server,sockets[i],&frame)!=ESP_OK)httpd_sess_trigger_close(server,sockets[i]);
      }
      cJSON_free(payload);
    }
  }
  frameWorkPending=false;
}
esp_err_t web(httpd_req_t* req) {
  httpd_resp_set_type(req,"text/html; charset=utf-8");
  httpd_resp_set_hdr(req,"Content-Encoding","gzip");
  httpd_resp_set_hdr(req,"Cache-Control","no-cache");
  httpd_resp_set_hdr(req,"X-Content-Type-Options","nosniff");
  httpd_resp_set_hdr(req,"Content-Security-Policy","default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws:; frame-ancestors 'none'");
  return httpd_resp_send(req,reinterpret_cast<const char*>(web_gz),sizeof(web_gz));
}
void startServer() {
  httpd_config_t config=HTTPD_DEFAULT_CONFIG();config.max_uri_handlers=12;config.max_open_sockets=7;
  config.stack_size=8192;config.lru_purge_enable=true;config.recv_wait_timeout=2;config.send_wait_timeout=1;config.uri_match_fn=httpd_uri_match_wildcard;
  if(httpd_start(&server,&config)!=ESP_OK)return;
  httpd_uri_t ws={};ws.uri="/api/live";ws.method=HTTP_GET;ws.handler=live;ws.is_websocket=true;httpd_register_uri_handler(server,&ws);
  for(auto method:{HTTP_GET,HTTP_POST,HTTP_PUT,HTTP_DELETE}) {httpd_uri_t uri={};uri.uri="/api/*";uri.method=method;uri.handler=api;httpd_register_uri_handler(server,&uri);}
  httpd_uri_t root={};root.uri="/*";root.method=HTTP_GET;root.handler=web;httpd_register_uri_handler(server,&root);
}
void serialFrame(uint8_t type,const std::vector<uint8_t>& data) {
  if(data.size()>255)return;
  std::vector<uint8_t> frame={'I','M','P','R','O','V',1,type,uint8_t(data.size())};
  frame.insert(frame.end(),data.begin(),data.end());uint8_t sum=0;for(uint8_t b:frame)sum+=b;frame.push_back(sum);
  Serial.write(frame.data(),frame.size());
}
void serialState(uint8_t state) {serialFrame(1,{state});}
void serialError(uint8_t error) {serialFrame(2,{error});}
void serialResult(improv::Command cmd,const std::vector<std::string>& data) {
  auto payload=improv::build_rpc_response(cmd,data,false);
  if(payload.size()>1)payload.resize(2+payload[1]); // SDK rezervuje místo pro nepoužitý checksum.
  serialFrame(4,payload);
}
bool improvCommand(improv::ImprovCommand command) {
  serialError(0);
  if(command.command==improv::GET_DEVICE_INFO)serialResult(command.command,{BUZZER_NAME,BUZZER_VERSION,"ESP32-S3",hostname.c_str()});
  else if(command.command==improv::GET_CURRENT_STATE) {
    serialState(pendingWiFi ? 3 : WiFi.status()==WL_CONNECTED ? 4 : 2);
    if(WiFi.status()==WL_CONNECTED)serialResult(improv::WIFI_SETTINGS,{("http://"+WiFi.localIP().toString()).c_str()});
  } else if(command.command==improv::WIFI_SETTINGS) {
    if(!schemaOK || command.ssid.empty() || command.ssid.size()>32 || command.password.size()>63) {serialError(1);return false;}
    WiFiCommand request={};strlcpy(request.ssid,command.ssid.c_str(),sizeof(request.ssid));strlcpy(request.password,command.password.c_str(),sizeof(request.password));request.improv=true;
    if(xQueueSend(wifiCommands,&request,0)!=pdTRUE)serialError(3);else serialState(3);
  } else if(command.command==improv::GET_WIFI_NETWORKS) {
    if(scanPending || (lastScanAt && millis()-lastScanAt<5000)) {serialResult(command.command,{});return false;}
    WiFi.scanNetworks(true);scanPending=true;lastScanAt=millis();
  } else serialError(2);
  return false;
}
void serviceSerial() {
  static uint8_t buffer[265];static size_t used=0;
  if(used && millis()-serialAt>1000)used=0;
  for(int budget=0;Serial.available() && budget<128;++budget) {
    uint8_t byte=Serial.read();serialAt=millis();buffer[used]=byte;
    bool more=improv::parse_improv_serial_byte(used,byte,buffer,improvCommand,[](improv::Error e){serialError(e);});
    used=more && used+1<sizeof(buffer) ? used+1 : 0;
  }
  if(scanPending) {
    int count=WiFi.scanComplete();
    if(count>=0) {
      std::vector<String> seen;
      for(int i=0;i<count && seen.size()<24;++i) {String ssid=WiFi.SSID(i);if(ssid.isEmpty() || std::find(seen.begin(),seen.end(),ssid)!=seen.end())continue;seen.push_back(ssid);
        serialResult(improv::GET_WIFI_NETWORKS,{ssid.c_str(),String(WiFi.RSSI(i)).c_str(),WiFi.encryptionType(i)==WIFI_AUTH_OPEN ? "NO" : "YES"});}
      serialResult(improv::GET_WIFI_NETWORKS,{});WiFi.scanDelete();scanPending=false;
    } else if(count==WIFI_SCAN_FAILED || millis()-lastScanAt>20000) {serialResult(improv::GET_WIFI_NETWORKS,{});scanPending=false;WiFi.scanDelete();}
  }
}
void startAP() {
  if(apActive)return;
  WiFi.mode(WIFI_AP_STA);
  // Heslo AP je náhodné pro zařízení; zobrazuje se jen při prvním nastavení.
  String apPassword="BD"+pairingCode;
  if(WiFi.softAP(hostname.c_str(),apPassword.c_str())) {apActive=true;dns.start(53,"*",WiFi.softAPIP());}
}
void serviceWiFi() {
  WiFiCommand request={};
  if(!pendingWiFi && xQueueReceive(wifiCommands,&request,0)==pdTRUE) {
    pendingSSID=request.ssid;pendingPassword=request.password;pendingImprov=request.improv;pendingWiFi=true;wifiAt=millis();
    connectingAttempt=false;WiFi.disconnect(false,false);WiFi.begin(pendingSSID.c_str(),pendingPassword.c_str());
  }
  const bool connected=WiFi.status()==WL_CONNECTED;
  if(pendingWiFi && connected) {
    // Ukládá se až ověřené spojení. Neplatné přihlašovací údaje nenahradí funkční.
    StoredWiFi stored={};strlcpy(stored.ssid,pendingSSID.c_str(),sizeof(stored.ssid));strlcpy(stored.password,pendingPassword.c_str(),sizeof(stored.password));
    if(prefs.putBytes("wifi",&stored,sizeof(stored))==sizeof(stored)) {
      wifiSSID=pendingSSID;wifiPassword=pendingPassword;
      if(pendingImprov){serialState(4);serialResult(improv::WIFI_SETTINGS,{("http://"+WiFi.localIP().toString()).c_str()});}
    } else if(pendingImprov)serialError(255);
    pendingWiFi=false;pendingPassword="";
  }
  if(pendingWiFi && millis()-wifiAt>=20000) {
    pendingWiFi=false;pendingPassword="";WiFi.disconnect(false,false);
    if(pendingImprov){serialError(3);serialState(2);}retry.connected();
  }
  if(connected && !haveIP) {
    haveIP=true;connectingAttempt=false;retry.connected();MDNS.end();
    if(MDNS.begin(hostname.c_str())) {MDNS.addService("buzzerdisplay","tcp",80);MDNS.addServiceTxt("buzzerdisplay","tcp","id",deviceID);MDNS.addServiceTxt("buzzerdisplay","tcp","version",BUZZER_VERSION);MDNS.addServiceTxt("buzzerdisplay","tcp","api","1");}
  } else if(!connected && haveIP) {haveIP=false;disconnectedAt=millis();MDNS.end();}
  if(!connected && !pendingWiFi && connectingAttempt && millis()-connectAt>=20000) {
    connectingAttempt=false;WiFi.disconnect(false,false);retry.attempted(millis());
  }
  if(!connected && !pendingWiFi && !connectingAttempt && !wifiSSID.isEmpty() && retry.due(millis())) {
    connectingAttempt=true;connectAt=millis();WiFi.disconnect(false,false);WiFi.begin(wifiSSID.c_str(),wifiPassword.c_str());
  }
  if(!connected && (wifiSSID.isEmpty() || millis()-disconnectedAt>60000))startAP();
  if(connected && apActive && !windowOpen()) {dns.stop();WiFi.softAPdisconnect(true);WiFi.mode(WIFI_STA);apActive=false;}
  if(apActive)dns.processNextRequest();
}
}
void buzzerSetup() {
  Serial.begin(115200);pinMode(0,INPUT_PULLUP);
  WiFi.persistent(false);WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(false);WiFi.setSleep(false);
  uint8_t mac[6]={};esp_read_mac(mac,ESP_MAC_WIFI_STA);
  char identity[13];snprintf(identity,sizeof(identity),"%02x%02x%02x%02x%02x%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
  deviceID=identity;hostname="buzzer-"+deviceID.substring(6);WiFi.setHostname(hostname.c_str());
  commands=xQueueCreate(8,sizeof(Command*));wifiCommands=xQueueCreate(1,sizeof(WiFiCommand));
  prefs.begin("buzzer",false);
  uint32_t schema=prefs.getUInt("schema",0);
  if(schema>1 || (schema==0 && prefs.isKey("token"))) schemaOK=false;
  if(schemaOK) {
    apiToken=prefs.getString("token","");
    if(schema==1 && apiToken.length()!=32) schemaOK=false;
    if(schema==0) {char token[33];for(int i=0;i<4;++i)snprintf(token+i*8,9,"%08lx",(unsigned long)esp_random());apiToken=token;if(prefs.putString("token",apiToken)!=32)schemaOK=false;}
    char code[7];snprintf(code,sizeof(code),"%06lu",(unsigned long)(esp_random()%1000000));pairingCode=code;
    if(prefs.isKey("wifi")) {
      StoredWiFi stored={};
      if(prefs.getBytesLength("wifi")!=sizeof(stored) || prefs.getBytes("wifi",&stored,sizeof(stored))!=sizeof(stored) || !memchr(stored.ssid,0,sizeof(stored.ssid)) || !memchr(stored.password,0,sizeof(stored.password))) schemaOK=false;
      else {wifiSSID=stored.ssid;wifiPassword=stored.password;}
    }
    paired=prefs.getBool("paired",false);
    if(schemaOK && schema==0 && !prefs.putUInt("schema",1))schemaOK=false;
    if(schemaOK) {
      auto c=new Command;c->kind=Command::Settings;c->brightness=prefs.getUChar("brightness",4);c->on=prefs.getBool("on",true);c->rotation=prefs.getBool("rotation",true);
      if(c->brightness>15){schemaOK=false;delete c;}else push(c);
    }
  }
  xTaskCreatePinnedToCore(renderTask,"matrix",6144,nullptr,2,nullptr,1);
  if(!schemaOK)showNotice("Nepodporovaný formát dat",300000);
  else if(!paired)openPairing();
  startServer();
}
void buzzerLoop() {
  serviceSerial();if(schemaOK)serviceWiFi();
  static uint32_t lastSave=0;
  if(schemaOK && millis()-lastSave>=2000) {
    lastSave=millis();
    if(prefs.getUChar("brightness",4)!=settingBrightness)prefs.putUChar("brightness",settingBrightness);
    if(prefs.getBool("on",true)!=settingOn)prefs.putBool("on",settingOn);
    if(prefs.getBool("rotation",true)!=settingRotation)prefs.putBool("rotation",settingRotation);
  }
  static bool buttonHandled=false;
  if(digitalRead(0)==LOW) {if(!buttonAt)buttonAt=millis();if(!buttonHandled && millis()-buttonAt>=1000){openPairing();buttonHandled=true;}}
  else {buttonAt=0;buttonHandled=false;}
  static uint32_t lastFrame=0;
  if(server && millis()-lastFrame>=40 && !frameWorkPending.exchange(true)) {
    lastFrame=millis();if(httpd_queue_work(server,broadcast,nullptr)!=ESP_OK)frameWorkPending=false;
  }
  delay(2);
}
