"""Lokální protokol. Klíč neopouští síť Home Assistantu."""
from __future__ import annotations
import asyncio
import ipaddress
from aiohttp import ClientSession, ClientError, WSMsgType

class DeviceError(Exception):
    """Nedostupné zařízení nebo neplatná odpověď."""

class AuthenticationError(DeviceError):
    """Párování je nutné opakovat."""

def normalize_host(value: str) -> str:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if not value or any(char in value for char in "/?#@\\ \t\n\r"):
        raise ValueError("Zadejte pouze IP adresu nebo název zařízení.")
    try:
        ip = ipaddress.ip_address(value)
        return f"[{ip}]" if ip.version == 6 else str(ip)
    except ValueError:
        if ":" in value or len(value) > 253 or any(not (c.isascii() and (c.isalnum() or c in '.-')) for c in value):
            raise ValueError("Neplatná adresa zařízení.") from None
        return value.lower()

class BuzzerClient:
    def __init__(self, session: ClientSession, host: str, token: str = ""):
        self.session = session
        self.host = normalize_host(host)
        self.base = f"http://{self.host}"
        self.token = token

    async def request(self, method: str, path: str, data=None) -> dict:
        try:
            async with asyncio.timeout(5):
                async with self.session.request(method, self.base + path, json=data,
                    headers={"X-Buzzer-Key": self.token}, allow_redirects=False) as response:
                    if response.status in (401, 403):
                        raise AuthenticationError("Neplatný párovací kód nebo klíč.")
                    if response.status not in (200, 202):
                        raise DeviceError(f"Zařízení odmítlo požadavek ({response.status}).")
                    if response.content_length and response.content_length > 32768:
                        raise DeviceError("Příliš velká odpověď.")
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(4096):
                        raw.extend(chunk)
                        if len(raw) > 32768:
                            raise DeviceError("Příliš velká odpověď.")
                    import json
                    result = json.loads(raw)
                    if not isinstance(result, dict):
                        raise DeviceError("Neplatná odpověď zařízení.")
                    return result
        except (ClientError, TimeoutError, ValueError) as err:
            raise DeviceError("Zařízení neodpovídá nebo odeslalo neplatná data.") from err

    async def info(self):
        info = await self.request("GET", "/api/info")
        if info.get("api") != 1 or info.get("hardware") != "pajenicko-esp32s3-max7219-32x8" or not isinstance(info.get("id"), str):
            raise DeviceError("Zařízení nemá podporovaný firmware Pajenicko BuzzerDisplay Enhanced.")
        return info

    async def frames(self):
        try:
            async with self.session.ws_connect(self.base + "/api/live", heartbeat=20,
                max_msg_size=4096, receive_timeout=10) as socket:
                await socket.send_json({"token": self.token})
                async for message in socket:
                    if message.type == WSMsgType.TEXT:
                        frame = message.json()
                        if valid_frame(frame):
                            yield frame
                        else:
                            raise DeviceError("Neplatný obraz displeje.")
                    elif message.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED):
                        break
        except (ClientError, TimeoutError, ValueError) as err:
            raise DeviceError("Přenos obrazu byl přerušen.") from err

def valid_frame(frame) -> bool:
    if not isinstance(frame, dict):
        return False
    pixels = frame.get("pixels")
    return (isinstance(pixels, str) and len(pixels) == 64
        and all(c in "0123456789abcdef" for c in pixels)
        and type(frame.get("brightness")) is int and 0 <= frame["brightness"] <= 15
        and type(frame.get("on")) is bool)
