"""Předá Wi-Fi z ignorovaného .env přes Improv, bez výpisu credentials."""
import argparse
import ast
from pathlib import Path
import time
import serial
from probe_improv import command, packets, strings

def credentials():
    values={}
    for raw in (Path(__file__).resolve().parents[1]/'.env').read_text().splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line:continue
        key,value=line.split('=',1);key=key.removeprefix('export ').strip();value=value.strip()
        if key not in ('WIFI_SSID','WIFI_PASSWORD'):continue
        if value.startswith(('"',"'")):
            try:value=ast.literal_eval(value)
            except (ValueError,SyntaxError):raise RuntimeError('Neplatné uvozovky v lokálním .env.') from None
        values[key]=value
    if not values.get('WIFI_SSID') or 'WIFI_PASSWORD' not in values:raise RuntimeError('Doplňte WIFI_SSID a WIFI_PASSWORD v lokálním .env.')
    ssid=values['WIFI_SSID'].encode();password=values['WIFI_PASSWORD'].encode()
    if not 1<=len(ssid)<=32 or len(password)>63:raise RuntimeError('Délka Wi-Fi údajů neodpovídá protokolu.')
    return ssid,password

def main():
    parser=argparse.ArgumentParser();parser.add_argument('port');args=parser.parse_args()
    ssid,password=credentials()
    payload=bytes([1,2+len(ssid)+len(password),len(ssid)])+ssid+bytes([len(password)])+password
    frame=bytearray(b'IMPROV')+bytes([1,3,len(payload)])+payload;frame.append(sum(frame)&255)
    with serial.Serial(port=None,baudrate=115200,timeout=.1) as port:
        port.dtr=False;port.rts=False;port.port=args.port;port.open();time.sleep(.3);port.reset_input_buffer();port.write(frame)
        connected=False
        for kind,data in packets(port,30):
            if kind==2 and data[0]:raise RuntimeError(f'Improv odmítl nastavení, kód {data[0]}. Přihlašovací údaje nejsou vypsány.')
            if kind==1 and data[0]==4:connected=True
            if kind==4 and data[0]==1:
                urls=strings(data)
                if connected and urls:
                    print('Wi-Fi byla úspěšně nastavena přes Improv.')
                    print('Adresa zařízení: '+urls[0])
                    return
        raise RuntimeError('Zařízení nepotvrdilo připojení v časovém limitu.')
if __name__=='__main__':main()
