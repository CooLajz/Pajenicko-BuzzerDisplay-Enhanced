"""Fyzický test HTTP/WS. Vyžaduje lokální spárované build/device-session.json."""
import asyncio
import importlib.util
import json
from pathlib import Path

from aiohttp import ClientSession

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("buzzer_api", ROOT / "custom_components/buzzer_display/api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


async def frames(client, count=35):
    received = []
    stream = client.frames()
    try:
        async with asyncio.timeout(8):
            async for frame in stream:
                received.append(frame)
                if len(received) >= count:
                    break
    finally:
        await stream.aclose()
    assert len(received) == count, "Přenos obrazu byl předčasně ukončen."
    assert all(b["seq"] > a["seq"] for a, b in zip(received, received[1:])), "Snímky se neposouvají."
    return received


async def main():
    local = json.loads((ROOT / "build/device-session.json").read_text())
    async with ClientSession() as session:
        client = api.BuzzerClient(session, local["host"], local["token"])
        info = await client.info()
        assert info["paired"] and info["storage_ok"]
        original = await client.request("GET", "/api/state")
        rejected = api.BuzzerClient(session, local["host"], "invalid-test-key")
        try:
            await rejected.request("GET", "/api/state")
        except api.AuthenticationError:
            pass
        else:
            raise AssertionError("API přijalo neplatný klíč.")
        try:
            await client.request("POST", "/api/settings", {"brightness": 15, "enabled": True})
            await client.request("POST", "/api/notification", {"text": "23,5°C", "speed": 0, "duration_ms": 5000})
            await asyncio.sleep(.1)
            font = json.loads((ROOT / "docs/font.json").read_text())
            columns = []
            for character in "23,5°C":
                columns += font[character] + [0]
            columns.pop()
            assert len(columns) <= 32
            left = (32-len(columns))//2
            expected = bytes([0]*left + columns + [0]*(32-left-len(columns))).hex()
            static = await frames(client)
            assert all(f["pixels"] == expected and f["on"] and f["brightness"] == 15 for f in static)
            print("Skutečné pixely teploty přes WebSocket odpovídají fontu; přenos běží.", flush=True)
            for blink in ("hard", "fade"):
                await client.request("POST", "/api/notification", {
                    "text": "68 %", "blink": blink, "blink_ms": 1000, "duration_ms": 5000})
                sample = await frames(client)
                assert any(f["on"] for f in sample) and any(not f["on"] for f in sample)
                if blink == "fade":
                    assert len({f["brightness"] for f in sample}) >= 5
            print("Ostré blikání i víceúrovňové pulzování prošly na zařízení.", flush=True)
            await client.request("POST", "/api/notification", {
                "text": "Příliš žluťoučký kůň", "speed": 25, "duration_ms": 5000})
            sample = await frames(client)
            assert len({f["pixels"] for f in sample}) >= 15
            print("Český text se posouvá a klient po opakovaném připojení přijímá nové snímky.", flush=True)
        finally:
            await client.request("DELETE", "/api/notification")
            await client.request("POST", "/api/settings", {
                "brightness": original["target_brightness"], "enabled": original["enabled"]})
        await client.request("PUT", "/api/playlist", {"ttl_ms": 300000, "pages": [
            {"id": "demo-temperature", "text": "23,5°C", "hold_ms": 4000, "speed": 0, "enter": "fade", "exit": "fade"},
            {"id": "demo-czech", "text": "Příliš žluťoučký kůň", "hold_ms": 4000, "speed": 25, "enter": "right", "exit": "left"},
            {"id": "demo-percent", "text": "68 %", "hold_ms": 4000, "invert": True, "enter": "up", "exit": "down"}
        ]})
        print("Na displeji běží pětiminutová ukázka s výslovně testovacími hodnotami 23,5 °C a 68 %.")


if __name__ == "__main__":
    asyncio.run(main())
