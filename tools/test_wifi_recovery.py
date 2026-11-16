"""Dočasně zkusí neexistující síť a ověří návrat k uložené Wi-Fi bez restartu."""
import argparse
import json
import time
import urllib.request
import uuid

import serial
from probe_improv import command, packets, strings


def connected_url(port, timeout=6):
    command(port, 2)
    for kind, data in packets(port, timeout):
        if kind == 4 and data[0] == 1:
            urls = strings(data)
            if urls:
                return urls[0]
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port")
    args = parser.parse_args()
    with serial.Serial(port=None, baudrate=115200, timeout=.1) as port:
        port.dtr = False
        port.rts = False
        port.port = args.port
        port.open()
        time.sleep(.3)
        port.reset_input_buffer()
        original = None
        deadline = time.monotonic() + 20
        while not original and time.monotonic() < deadline:
            original = connected_url(port)
        assert original, "Test vyžaduje připojenou Wi-Fi."
        with urllib.request.urlopen(original + "/api/info", timeout=5) as response:
            identity = json.load(response)["id"]
        ssid = ("buzzer-test-" + uuid.uuid4().hex[:16]).encode()
        payload = bytes([1, len(ssid)+2, len(ssid)]) + ssid + b"\x00"
        frame = bytearray(b"IMPROV") + bytes([1, 3, len(payload)]) + payload
        frame.append(sum(frame) & 255)
        port.write(frame)
        for kind, data in packets(port, 30):
            if kind == 2 and data[0] == 3:
                print("Neexistující síť byla po časovém limitu odmítnuta.", flush=True)
                break
        else:
            raise AssertionError("Připojování neskončilo očekávanou chybou.")
        deadline = time.monotonic() + 45
        recovered = None
        while time.monotonic() < deadline:
            recovered = connected_url(port)
            if recovered:
                break
        assert recovered, "Zařízení neobnovilo původní připojení."
        with urllib.request.urlopen(recovered + "/api/info", timeout=5) as response:
            assert json.load(response)["id"] == identity
        print("Původní Wi-Fi i HTTP API se obnovily bez restartu a bez opětovného zadání hesla.")


if __name__ == "__main__":
    main()
