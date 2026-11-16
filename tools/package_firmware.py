"""Ověření skutečného merged obrazu a příprava ZIPu pro Firmware Hub."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import struct
import shlex
import zipfile

ROOT=Path(__file__).resolve().parents[1]
build=ROOT/'build/firmware'
version=re.search(r'#define BUZZER_VERSION "([^"]+)"',(ROOT/'firmware/BuzzerDisplay/version.h').read_text())[1]
if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?',version):raise SystemExit('Neplatná verze.')
properties=dict(line.split('=',1) for line in (build/'build.properties').read_text().splitlines() if '=' in line)
if properties.get('build.mcu')!='esp32s3' or properties.get('build.flash_size')!='16MB':raise SystemExit('Neočekávaný hardwarový cíl.')
recipe=shlex.split(properties['recipe.hooks.objcopy.postobjcopy.3.pattern'])
parts={Path(recipe[i+1]).name:(int(value,0),Path(recipe[i+1])) for i,value in enumerate(recipe[:-1]) if re.fullmatch(r'0x[0-9a-fA-F]+',value)}
partition_offset=parts['BuzzerDisplay.ino.partitions.bin'][0]
part=(build/'BuzzerDisplay.ino.partitions.bin').read_bytes()
partitions={}
for start in range(0,len(part),32):
    if part[start:start+2]!=b'\xaa\x50':break
    magic,kind,subtype,offset,size,label,flags=struct.unpack('<HBBII16sI',part[start:start+32])
    partitions[label.rstrip(b'\0').decode()]=(offset,size)
app=(build/'BuzzerDisplay.ino.bin').read_bytes()
merged=(build/'BuzzerDisplay.ino.merged.bin').read_bytes()
offset,size=partitions['app0']
assert len(app)<=size and merged[offset:offset+len(app)]==app,'Aplikace neodpovídá partition.'
assert merged[partition_offset:partition_offset+len(part)]==part,'Nesoulad partition tabulky.'
nvs_offset,nvs_size=partitions['nvs']
assert merged[nvs_offset:nvs_offset+nvs_size]==b'\xff'*nvs_size,'Factory obraz obsahuje uložená data.'
assert len(merged)==16*1024*1024,'Nesprávná velikost flash.'
for address,file in parts.values():
    content=file.read_bytes()
    assert merged[address:address+len(content)]==content,f'Nesoulad části {file.name}.'
# Ořez pouze nevyužitého konce obrazu, zachování offsetů z Arduino buildu.
end=(len(merged.rstrip(b'\xff'))+4095)//4096*4096
factory=merged[:end]
release=ROOT/'build/release'
if release.exists():shutil.rmtree(release)
release.mkdir()
(release/'buzzer-display.factory.bin').write_bytes(factory)
manifest={'name':'Pajenicko BuzzerDisplay Enhanced','version':version,'hardwareProfile':'pajenicko-esp32s3-max7219-32x8','new_install_prompt_erase':True,'new_install_improv_wait_time':20,'builds':[{'chipFamily':'ESP32-S3','improv':True,'parts':[{'path':'buzzer-display.factory.bin','offset':0}]}]}
project={'name':'Pajenicko BuzzerDisplay Enhanced','description':'LED matice 32 × 8 s českými znaky, animacemi a lokálním ovládáním z Home Assistantu.','icon':'clock'}
for name,data in [('manifest.json',manifest),('project.json',project)]:
    (release/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
archive=ROOT/'build'/f'buzzer-display-{version}.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for file in sorted(release.iterdir()):z.write(file,file.name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert set(z.namelist())=={'manifest.json','project.json','buzzer-display.factory.bin'}
print(json.dumps({'version':version,'factory_bytes':len(factory),'sha256':hashlib.sha256(factory).hexdigest(),'archive':str(archive),'app_offset':offset,'partition_offset':partition_offset},ensure_ascii=False,indent=2))
