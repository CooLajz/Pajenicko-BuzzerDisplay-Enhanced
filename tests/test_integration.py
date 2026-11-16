"""Lokální testy integrace v opravdovém runtime Home Assistantu."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch
import pytest
from aiohttp import web, ClientSession
from homeassistant.core import HomeAssistant
from custom_components.buzzer_display.api import BuzzerClient, DeviceError, AuthenticationError, normalize_host, valid_frame
from custom_components.buzzer_display.formatting import format_page
from custom_components.buzzer_display.coordinator import BuzzerCoordinator
from custom_components.buzzer_display.config_flow import BuzzerConfigFlow, BuzzerOptionsFlow

ROOT=Path(__file__).resolve().parents[1]

def test_formatting():
    p={"id":"temperature","entity_id":"sensor.temperature","text":"Pokoj"}
    assert format_page(p,"23.55",{"unit_of_measurement":"°C"})["text"]=="Pokoj 23,6 °C"
    assert format_page(p,"unavailable",{})["text"]=="Pokoj Nedostupné"
    assert format_page(p,"off",{})["text"]=="Pokoj Vypnuto"
    assert format_page({"id":"text","text":"e\u030c"},None,{})["text"]=="ě"
    assert len(format_page({"id":"text","text":"ř"*400},None,{})["text"].encode())<=384

def test_host_and_frame_validation():
    assert normalize_host("buzzer.local")=="buzzer.local"
    assert normalize_host("[::1]")=="[::1]"
    for value in ["user:pass@host","host/path","http://host","host:8080","host\r\nX: a"]:
        with pytest.raises(ValueError):normalize_host(value)
    f={"pixels":"00"*32,"on":True,"brightness":15}
    assert valid_frame(f)
    for patch in [{"pixels":"zz"*32},{"pixels":"00"},{"brightness":16},{"brightness":True},{"on":"true"}]:
        assert not valid_frame({**f,**patch})

def test_marketplace_packaging():
    hacs=json.loads((ROOT/'hacs.json').read_text())
    assert hacs['homeassistant']=='2026.11.0'
    components=list((ROOT/'custom_components').glob('*/manifest.json'))
    assert len(components)==1
    manifest=json.loads(components[0].read_text())
    assert manifest['domain']=='buzzer_display'
    assert manifest['version']=='0.1.0-dev.1'
    for lang in ('cs','en'):
        translations=json.loads((components[0].parent/'translations'/f'{lang}.json').read_text())
        assert translations['config']['step']['pair']['data']['code']
    assert (components[0].parent/'frontend/buzzer-display-card.js').is_file()

@pytest.mark.enable_socket
@pytest.mark.asyncio
async def test_client_and_coordinator(hass, socket_enabled):
    calls=[]
    async def handler(request):
        if request.path=='/api/info':return web.json_response({'id':'123456','api':1,'hardware':'pajenicko-esp32s3-max7219-32x8','version':'0.1.0-dev.1','name':'Pajenicko BuzzerDisplay Enhanced'})
        if request.headers.get('X-Buzzer-Key')!='test-token':return web.json_response({},status=401)
        if request.method in ('POST','PUT'):calls.append(await request.json());return web.json_response({'accepted':True},status=202)
        return web.json_response({'rssi':-55,'stale':False})
    app=web.Application();app.router.add_route('*','/api/{tail:.*}',handler)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    port=site._server.sockets[0].getsockname()[1]
    try:
        async with ClientSession() as session:
            client=BuzzerClient(session,'127.0.0.1','test-token');client.base=f'http://127.0.0.1:{port}'
            info=await client.info();assert info['api']==1
            hass.states.async_set('sensor.temperature','23.1',{'unit_of_measurement':'°C'})
            entry=MagicMock();entry.options={'pages':[{'id':'room','entity_id':'sensor.temperature'}]}
            coordinator=BuzzerCoordinator(hass,entry,client,info)
            data=await coordinator._async_update_data();assert data['rssi']==-55
            assert calls[-1]['pages'][0]['text']=='23,1 °C'
            hass.states.async_set('sensor.temperature','unavailable')
            await coordinator.publish();assert calls[-1]['pages'][0]['text']=='Nedostupné'
            client.token='wrong'
            with pytest.raises(AuthenticationError):await client.request('GET','/api/state')
            await coordinator.shutdown()
    finally:
        await runner.cleanup()


def test_platform_imports():
    import importlib
    for platform in ['sensor','binary_sensor','switch','number','text','button']:
        module=importlib.import_module('custom_components.buzzer_display.'+platform)
        assert callable(module.async_setup_entry)

@pytest.mark.usefixtures("enable_custom_integrations")
async def test_pairing_flow_and_options(hass):
    from homeassistant.data_entry_flow import FlowResultType
    info={'id':'123456abcdef','api':1,'name':'Pajenicko BuzzerDisplay Enhanced','version':'0.1.0-dev.1'}
    with patch.object(BuzzerClient,'info',return_value=info), patch.object(BuzzerClient,'request',return_value={'token':'a'*32,'id':info['id']}), patch('custom_components.buzzer_display.async_setup_entry',return_value=True), patch('custom_components.buzzer_display.async_setup',return_value=True), patch('homeassistant.components.frontend.async_setup',return_value=True):
        result=await hass.config_entries.flow.async_init('buzzer_display',context={'source':'user'},data={'host':'buzzer.local'})
        assert result['type']==FlowResultType.FORM and result['step_id']=='pair'
        result=await hass.config_entries.flow.async_configure(result['flow_id'],{'code':'123456'})
        assert result['type']==FlowResultType.CREATE_ENTRY
        entry=result['result']
        await hass.async_block_till_done()
        result=await hass.config_entries.options.async_init(entry.entry_id)
        assert result['type']==FlowResultType.MENU
        result=await hass.config_entries.options.async_configure(result['flow_id'],{'next_step_id':'add_page'})
        assert result['step_id']=='page'
        result=await hass.config_entries.options.async_configure(result['flow_id'],{'text':'Pokoj','entity_id':'sensor.temperature','speed':25,'enter':'up','exit':'fade','blink':'fade','invert':True})
        assert result['type']==FlowResultType.CREATE_ENTRY
        assert entry.options['pages'][0]['entity_id']=='sensor.temperature'
        assert entry.options['pages'][0]['enter']=='up'
        await hass.async_block_till_done()
