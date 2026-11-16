"""Ověření Improv Serial bez čtení či výpisu přihlašovacích údajů."""
import argparse
import time
import serial

def command(port, code):
    data=bytearray(b'IMPROV')+bytes([1,3,2,code,0])
    data.append(sum(data)&255);port.write(data)

def packets(port, timeout=6):
    buffer=bytearray();end=time.monotonic()+timeout
    while time.monotonic()<end:
        buffer.extend(port.read(256))
        while True:
            start=buffer.find(b'IMPROV')
            if start<0:
                buffer[:]=buffer[-5:];break
            if start:del buffer[:start]
            if len(buffer)<9:break
            size=buffer[8]+10
            if len(buffer)<size:break
            packet=bytes(buffer[:size]);del buffer[:size]
            if packet[6]!=1 or (sum(packet[:-1])&255)!=packet[-1]:continue
            yield packet[7],packet[9:-1]

def strings(data):
    result=[];index=2
    if len(data)<2 or data[1]!=len(data)-2:raise RuntimeError('Neplatná délka RPC odpovědi.')
    while index<len(data):
        length=data[index];index+=1
        if index+length>len(data):raise RuntimeError('Neplatná délka řetězce.')
        result.append(data[index:index+length].decode());index+=length
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('port');args=parser.parse_args()
    with serial.Serial(port=None,baudrate=115200,timeout=.1) as port:
        port.dtr=False;port.rts=False;port.port=args.port;port.open();time.sleep(1);port.reset_input_buffer()
        command(port,3)
        info=None
        for kind,data in packets(port):
            if kind==4 and data[0]==3:info=strings(data);break
        if not info or info[:3]!=['Pajenicko BuzzerDisplay Enhanced','0.1.0-dev.1','ESP32-S3']:raise RuntimeError(f'Neočekávaná metadata: {info}')
        print('Improv metadata: '+', '.join(info))
        command(port,2)
        for kind,data in packets(port):
            if kind==1:
                print('Improv stav: '+{2:'připraveno k nastavení Wi-Fi',3:'připojování',4:'připojeno'}.get(data[0],str(data[0])));break
        else:raise RuntimeError('Zařízení nevrátilo stav.')
        command(port,4);count=0;complete=False
        for kind,data in packets(port,20):
            if kind==4 and data[0]==4:
                values=strings(data)
                if not values:complete=True;break
                assert len(values)==3
                count+=1
        if not complete:raise RuntimeError('Seznam Wi-Fi sítí nebyl ukončen.')
        print(f'Improv výběr Wi-Fi: nalezeno {count} sítí; seznam je řádně ukončen.')
if __name__=='__main__':main()
