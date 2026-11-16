"""Lokální QA webu a karty. Pixely generuje skutečné C++ jádro firmwaru."""
import asyncio
import json
import time
from pathlib import Path
from aiohttp import web

ROOT=Path(__file__).resolve().parents[1]
frames=[]
started=0
effects=['none','left','right','up','down','fade']

async def render(data=None):
    global frames,started
    data=data or {}
    process=await asyncio.create_subprocess_exec(str(ROOT/'build/core-tests'),'--frames',data.get('text','23,5°C'),str(data.get('speed',20)),str(['none','hard','fade'].index(data.get('blink','none'))),str(int(data.get('invert',False))),str(effects.index(data.get('enter','none'))),str(effects.index(data.get('exit','none'))),stdout=asyncio.subprocess.PIPE)
    stdout,_=await process.communicate()
    if process.returncode:raise RuntimeError('Renderer selhal')
    frames=[json.loads(line) for line in stdout.splitlines()];started=time.monotonic()

def frame():
    return frames[int((time.monotonic()-started)*25)%len(frames)]

async def api(request):
    route=request.match_info['name']
    if route=='info':return web.json_response({'id':'preview000001','name':'Pajenicko BuzzerDisplay Enhanced','version':'0.1.0-dev.1','api':1,'hardware':'pajenicko-esp32s3-max7219-32x8','paired':True,'storage_ok':True})
    if route=='pair':
        data=await request.json()
        return web.json_response({'token':'local-preview-only'} if data.get('code')=='123456' else {'error':'Neplatný kód.'},status=200 if data.get('code')=='123456' else 403)
    if route=='live':
        ws=web.WebSocketResponse();await ws.prepare(request)
        data=await ws.receive_json()
        if data.get('token')!='local-preview-only':await ws.close();return ws
        try:
            while not ws.closed:
                await ws.send_json(frame());await asyncio.sleep(.04)
        except (ConnectionResetError,asyncio.CancelledError):pass
        return ws
    if request.headers.get('X-Buzzer-Key')!='local-preview-only':return web.json_response({'error':'Zadejte testovací kód 123456.'},status=401)
    if route=='notification':await render(await request.json());return web.json_response({'accepted':True},status=202)
    if route=='wifi':return web.json_response({'accepted':True},status=202)
    if route=='state':return web.json_response({**frame(),'rssi':-56,'uptime':int(time.monotonic()-started),'heap':210000,'target_brightness':4,'enabled':True,'rotation':True,'wifi_connected':True,'version':'0.1.0-dev.1','ip':'127.0.0.1'})
    return web.json_response(frame())

async def page(request):return web.FileResponse(ROOT/'firmware/web/index.html')
async def card_js(request):return web.FileResponse(ROOT/'custom_components/buzzer_display/frontend/buzzer-display-card.js')
async def card_page(request):
    return web.Response(text='''<!doctype html><html lang="cs"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Test karty Pajenicko BuzzerDisplay Enhanced</title><style>body{font-family:system-ui;background:#f6f6f8;padding:35px;color:#222;--secondary-text-color:#666;--primary-text-color:#222}main{max-width:600px;margin:auto}ha-card{display:block;background:white;border:1px solid #ddd;border-radius:15px}h1{font-size:22px}p{font-size:14px;color:#666}</style><main><h1>Lokální test karty Home Assistantu</h1><p>Obraz vzniká stejným rendererem jako ve firmwaru. Toto není připojení k fyzickému displeji.</p><buzzer-display-card></buzzer-display-card></main><script src="/card.js"></script><script>const card=document.querySelector('buzzer-display-card');card.setConfig({entity:'sensor.buzzer_signal',title:'Pajenicko BuzzerDisplay Enhanced'});card.hass={connection:{subscribeMessage:async callback=>{const ws=new WebSocket('ws://'+location.host+'/api/live');ws.onopen=()=>ws.send(JSON.stringify({token:'local-preview-only'}));ws.onmessage=e=>callback({available:true,...JSON.parse(e.data)});return ()=>ws.close();}}};</script></html>''',content_type='text/html')

async def main():
    await render();app=web.Application();app.router.add_route('*','/api/{name}',api);app.router.add_get('/',page);app.router.add_get('/card.js',card_js);app.router.add_get('/card',card_page)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',8765);await site.start();print('Lokální test: http://127.0.0.1:8765 (kód 123456)',flush=True)
    try:await asyncio.Event().wait()
    finally:await runner.cleanup()
if __name__=='__main__':asyncio.run(main())
