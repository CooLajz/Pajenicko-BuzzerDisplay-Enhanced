"""Reprodukovatelný build; volitelné lokální cesty nejsou součástí Gitu."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
FQBN='esp32:esp32:esp32s3:FlashSize=16M,PartitionScheme=custom,PSRAM=disabled,CDCOnBoot=default,FlashMode=dio'
config=ROOT/'arduino-cli.local.yaml'
if not config.exists():config=ROOT/'arduino-cli.yaml'
settings=json.loads((ROOT/'tools/local.json').read_text()) if (ROOT/'tools/local.json').exists() else {}
env=os.environ.copy()
if settings.get('pythonpath'):env['PYTHONPATH']=settings['pythonpath']
for generator in ['generate_font.py','embed_web.py']:
    subprocess.run([sys.executable,str(ROOT/'tools'/generator)],check=True)
command=[settings.get('arduino_cli','arduino-cli'),'compile','--config-file',str(config),'--fqbn',FQBN,'--build-path',str(ROOT/'build/firmware')]
for key,value in settings.get('properties',{}).items():command+=['--build-property',f'{key}={value}']
subprocess.run(command+[str(ROOT/'firmware/BuzzerDisplay')],env=env,check=True)
properties=subprocess.check_output(command+['--show-properties=expanded',str(ROOT/'firmware/BuzzerDisplay')],env=env,text=True)
(ROOT/'build/firmware/build.properties').write_text(properties)
print('Firmware je sestaven. Pro balíček spusťte python3 tools/package_firmware.py.')
