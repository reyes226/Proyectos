import re, socket, subprocess, threading, time, json
import sys, os, argparse, platform
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CHECK_INTERVAL  = 30     # segundos entre ciclos
TIMEOUT         = 3      # timeout TCP/UDP
ICMP_TIMEOUT    = 2      # timeout ping
ALERT_THRESHOLD = 3      # ciclos sin resp -> ALERTA NODO FUERA
SUBNET_PREFIX   = 24     # /24 = 254 hosts

# Agrega aqui la IP de tu celular u otros nodos manuales:
EXTRA_NODES: list = [
    # "192.168.1.105",   # Mi celular
    # "192.168.1.106",   # Tablet
]

OUTPUT_FILE = Path(__file__).parent.resolve() / "monitor_state.json"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"
IS_MAC     = platform.system() == "Darwin"

# =============================================================
#  REGEX PATTERNS (requisito del proyecto)
# =============================================================
RE_IP_LINUX   = re.compile(r'inet\s+((?:\d{1,3}\.){3}\d{1,3})\/(\d+)')
RE_IP_WIN     = re.compile(r'IPv4[^:]+:\s*((?:\d{1,3}\.){3}\d{1,3})', re.I)
RE_IP         = re.compile(r'^((?:\d{1,3}\.){3}\d{1,3})$')
RE_MAC        = re.compile(r'([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}')
RE_HOSTNAME   = re.compile(r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z]{2,}$')
RE_PHONE      = re.compile(r'\+?\d[\d\s\-\.]{7,14}\d')
RE_WHOIS_TEL  = re.compile(r'(?:phone|tel|fax)[:\s]+([+\d][\d\s\-\.\(\)]{6,20})', re.I)
RE_HTTP_ST    = re.compile(r'HTTP/[\d\.]+\s+(\d{3})')
RE_SMTP       = re.compile(r'^220\s+(.+)$', re.MULTILINE)
RE_POP3       = re.compile(r'^\+OK\s*(.*)', re.MULTILINE)
RE_IMAP       = re.compile(r'^\*\s+OK\s+(.*)', re.MULTILINE)
RE_SSH        = re.compile(r'^SSH-([\d\.]+)-(\S+)', re.MULTILINE)
RE_RTT_LIN    = re.compile(r'time[=<]([\d\.]+)\s*ms')
RE_RTT_WIN    = re.compile(r'(?:tiempo|time)[=<]([\d\.]+)\s*ms', re.I)

# =============================================================
#  1. DETECTAR IP LOCAL — CMD/BASH + REGEX
# =============================================================

def get_local_ip_cmd() -> dict:
    """
    Windows : ipconfig  -> Regex RE_IP_WIN
    Linux   : ip addr   -> Regex RE_IP_LINUX
    Bash ERE equivalente:
      Win  : IPv4[^:]+:\\s*((\\d{1,3}\\.){3}\\d{1,3})
      Linux: inet\\s+((\\d{1,3}\\.){3}\\d{1,3})/(\\d+)
    """
    result = {"method": "cmd+regex", "os": platform.system(), "interfaces": []}
    try:
        if IS_WINDOWS:
            raw = subprocess.check_output(
                ["ipconfig"], stderr=subprocess.DEVNULL,
                text=True, encoding="cp1252", errors="ignore"
            )
            for ip in RE_IP_WIN.findall(raw):
                if RE_IP.match(ip) and not ip.startswith("127.") and not ip.startswith("169."):
                    result["interfaces"].append({"ip": ip, "prefix": 24})
        else:
            raw = subprocess.check_output(
                ["bash", "-c", "ip addr show 2>/dev/null || ifconfig 2>/dev/null"],
                stderr=subprocess.DEVNULL, text=True
            )
            for ip, prefix in RE_IP_LINUX.findall(raw):
                if not ip.startswith("127."):
                    result["interfaces"].append({"ip": ip, "prefix": int(prefix)})
    except Exception as e:
        result["error"] = str(e)
    return result


def get_local_ip_python() -> dict:
    """Python socket puro + Regex de validacion (multiplataforma)."""
    result = {"method": "python+regex", "interfaces": []}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        if RE_IP.match(ip) and not ip.startswith("127.") and not ip.startswith("169."):
            result["interfaces"].append({"ip": ip, "source": "udp-trick"})
        try:
            ip2 = socket.gethostbyname(socket.gethostname())
            if RE_IP.match(ip2) and not ip2.startswith("127.") and ip2 != ip:
                result["interfaces"].append({"ip": ip2, "source": "hostname"})
        except Exception:
            pass
    except Exception as e:
        result["error"] = str(e)
    return result


def get_primary_ip() -> str:
    for info in [get_local_ip_python(), get_local_ip_cmd()]:
        if info.get("interfaces"):
            return info["interfaces"][0]["ip"]
    return "127.0.0.1"


# =============================================================
#  2. SUBRED Y DESCUBRIMIENTO
# =============================================================

def ip_to_int(ip):
    p = list(map(int, ip.split(".")))
    return (p[0]<<24)|(p[1]<<16)|(p[2]<<8)|p[3]

def int_to_ip(n):
    return ".".join([str((n>>i)&0xFF) for i in (24,16,8,0)])

def get_subnet_hosts(local_ip, prefix=24):
    mask = (0xFFFFFFFF << (32-prefix)) & 0xFFFFFFFF
    net  = ip_to_int(local_ip) & mask
    return [int_to_ip(net|i) for i in range(1, min((1<<(32-prefix))-1, 255))
            if int_to_ip(net|i) != local_ip]


def ping_host(ip, timeout=ICMP_TIMEOUT):
    """Ping multiplataforma. Extrae RTT con Regex."""
    try:
        t0  = time.time()
        cmd = (["ping","-n","1","-w",str(timeout*1000),ip] if IS_WINDOWS
               else ["ping","-c","1","-W",str(timeout),ip])
        enc = "cp1252" if IS_WINDOWS else "utf-8"
        r   = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout+2, encoding=enc, errors="ignore")
        rtt = round((time.time()-t0)*1000, 2)
        re_rtt = RE_RTT_WIN if IS_WINDOWS else RE_RTT_LIN
        m = re_rtt.search(r.stdout)
        if m:
            rtt = float(m.group(1))
        return r.returncode == 0, rtt
    except Exception:
        return False, 0.0


def discover_subnet(local_ip, prefix=24, max_workers=60):
    hosts = get_subnet_hosts(local_ip, prefix)
    alive = []
    lock  = threading.Lock()
    def _chk(ip):
        ok, rtt = ping_host(ip)
        if ok:
            with lock:
                alive.append({"ip": ip, "rtt_ms": rtt})
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        ex.map(_chk, hosts)
    return sorted(alive, key=lambda x: ip_to_int(x["ip"]))


# =============================================================
#  3. HOSTNAME Y TELEFONO
# =============================================================

def resolve_hostname(ip):
    try:
        h = socket.gethostbyaddr(ip)[0]
        return h if h != ip else ip
    except Exception:
        return ip

def get_phone_from_whois(ip):
    """Extrae telefono de 'whois' con Regex RE_WHOIS_TEL."""
    try:
        raw = subprocess.check_output(
            ["whois", ip], stderr=subprocess.DEVNULL,
            text=True, timeout=8, errors="ignore"
        )
        for m in RE_WHOIS_TEL.findall(raw):
            m = m.strip()
            if RE_PHONE.match(m):
                return m
        return "N/A"
    except Exception:
        return "N/A"


# =============================================================
#  4. CHEQUEO DE SERVICIOS
# =============================================================

def check_tcp(ip, port, timeout=TIMEOUT):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        ok     = s.connect_ex((ip, port)) == 0
        banner = ""
        if ok:
            try:
                s.settimeout(1)
                banner = s.recv(256).decode("utf-8","ignore").strip()[:80]
            except Exception:
                pass
        s.close()
        return ok, banner
    except Exception:
        return False, ""

def check_udp(ip, port, timeout=TIMEOUT):
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(b"\x00", (ip, port))
        try:
            s.recvfrom(256)
            return True, "responded"
        except socket.timeout:
            return True, "open|filtered"
        except Exception:
            return False, "unreachable"
    except Exception:
        return False, ""
    finally:
        if s:
            try: s.close()
            except: pass

def check_http(ip, port=80, https=False):
    import urllib.request, ssl
    scheme = "https" if https else "http"
    url    = f"{scheme}://{ip}:{port}/"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent","PRTG-Lite/2.0")
        kw = {"context": ctx} if https else {}
        with urllib.request.urlopen(req, timeout=TIMEOUT, **kw) as resp:
            return {"up": True, "code": resp.status}
    except Exception as e:
        m = RE_HTTP_ST.search(str(e))
        if m:
            return {"up": True, "code": int(m.group(1))}
        return {"up": False, "code": 0}

def check_ssh(ip):
    ok, b = check_tcp(ip, 22)
    m = RE_SSH.search(b) if b else None
    return {"up": ok, "version": m.group(1) if m else "?",
            "sw": (m.group(2) if m else b[:20]) if b else ""}

def check_smtp(ip):
    ok, b = check_tcp(ip, 25)
    m = RE_SMTP.search(b) if b else None
    return {"up": ok, "banner": (m.group(1) if m else b)[:40]}

def check_pop3(ip):
    ok, b = check_tcp(ip, 110)
    m = RE_POP3.search(b) if b else None
    return {"up": ok, "banner": (m.group(1) if m else b)[:40]}

def check_imap(ip):
    ok, b = check_tcp(ip, 143)
    m = RE_IMAP.search(b) if b else None
    return {"up": ok, "banner": (m.group(1) if m else b)[:40]}

def check_snmp(ip):
    PKT = bytes([0x30,0x29,0x02,0x01,0x00,0x04,0x06,0x70,0x75,0x62,0x6c,0x69,
                 0x63,0xa0,0x1c,0x02,0x04,0x00,0x00,0x00,0x01,0x02,0x01,0x00,
                 0x02,0x01,0x00,0x30,0x0e,0x30,0x0c,0x06,0x08,0x2b,0x06,0x01,
                 0x02,0x01,0x01,0x01,0x00,0x05,0x00])
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(TIMEOUT)
        s.sendto(PKT, (ip, 161))
        data, _ = s.recvfrom(1024)
        desc = re.search(rb'[\x20-\x7e]{4,}', data[40:])
        return {"up": True,
                "sysDescr": desc.group().decode("ascii","ignore")[:50] if desc else "OK"}
    except Exception:
        return {"up": False, "sysDescr": ""}
    finally:
        if s:
            try: s.close()
            except: pass

def check_icmp(ip):
    ok, rtt = ping_host(ip)
    return {"up": ok, "rtt_ms": rtt}

def check_all_services(ip):
    t0 = time.time()
    r  = {
        "ICMP":   check_icmp(ip),
        "HTTP":   check_http(ip, 80),
        "HTTPS":  check_http(ip, 443, https=True),
        "SSH":    check_ssh(ip),
        "SNMP":   check_snmp(ip),
        "SMTP":   check_smtp(ip),
        "POP3":   check_pop3(ip),
        "IMAP":   check_imap(ip),
        "UDP/53": {"up": check_udp(ip,53)[0], "proto":"UDP"},
    }
    r["_ms"] = round((time.time()-t0)*1000, 1)
    return r


# =============================================================
#  PYSHARK — Captura de trafico (opcional)
# =============================================================

PYSHARK_OK = False
try:
    import pyshark
    PYSHARK_OK = True
except ImportError:
    pass


class SharkSniffer:
    """
    Captura trafico en vivo con pyshark.
    Detecta IPs nuevas y las registra automaticamente en el monitor.
    Requiere: pip install pyshark  +  Npcap (Windows) / libpcap (Linux)
    """
    def __init__(self, monitor, interface=None, bpf="ip"):
        self.monitor   = monitor
        self.interface = interface
        self.bpf       = bpf
        self.running   = False
        self.seen      = set()
        self.thread    = None
        self.stats     = {"packets": 0, "new_ips": 0}

    def _detect_iface(self):
        if self.interface:
            return self.interface
        try:
            ifaces = pyshark.LiveCapture().interfaces
            for i in ifaces:
                if "loopback" not in i.lower() and i.lower() not in ("lo",):
                    return i
            return ifaces[0] if ifaces else None
        except Exception:
            return None

    def start(self):
        if not PYSHARK_OK:
            print("[SHARK] pyshark no instalado. Ejecuta: pip install pyshark")
            return
        self.running = True
        self.thread  = threading.Thread(
            target=self._loop, daemon=True, name="shark"
        )
        self.thread.start()
        iface = self.interface or "auto"
        print(f"[SHARK] Captura activa — interfaz: {iface}")

    def stop(self):
        self.running = False

    def _loop(self):
        iface = self._detect_iface()
        if not iface:
            print("[SHARK] No se detecto interfaz de red")
            return
        try:
            cap = pyshark.LiveCapture(
                interface=iface,
                bpf_filter=self.bpf,
                display_filter="ip"
            )
            for pkt in cap.sniff_continuously():
                if not self.running:
                    break
                try:
                    self.stats["packets"] += 1
                    src = str(getattr(pkt.ip, 'src', ''))
                    dst = str(getattr(pkt.ip, 'dst', ''))
                    for ip in [src, dst]:
                        if (ip and RE_IP.match(ip)
                                and not ip.startswith("127.")
                                and not ip.startswith("224.")
                                and not ip.startswith("255.")
                                and ip not in self.seen):
                            self.seen.add(ip)
                            self.stats["new_ips"] += 1
                            self.monitor.register(ip, source="pyshark")
                            print(f"[SHARK] Nueva IP en trafico: {ip}")
                except AttributeError:
                    pass
        except Exception as e:
            print(f"[SHARK] Error: {e}")


# =============================================================
#  5-7. ESTADO POR NODO + ALERTAS
# =============================================================

class NodeState:
    def __init__(self, ip, label="", source="scan"):
        self.ip          = ip
        self.hostname    = ip
        self.phone       = "N/A"
        self.label       = label    # "Mi celular", "Router"...
        self.source      = source   # scan | manual | pyshark | local
        self.services    = {}
        self.fail_streak = 0
        self.alerted     = False
        self.last_seen   = None
        self.last_check  = None
        self.history     = []
        self.lock        = threading.Lock()

    def update(self, svc):
        with self.lock:
            self.services   = svc
            self.last_check = datetime.now().isoformat()
            any_up = any(v.get("up") for k,v in svc.items() if not k.startswith("_"))
            if any_up:
                self.last_seen   = self.last_check
                self.fail_streak = 0
                self.alerted     = False
            else:
                self.fail_streak += 1
            self.history.append({
                "ts": self.last_check, "up": any_up, "streak": self.fail_streak
            })
            self.history = self.history[-10:]

    def is_down(self):    return self.fail_streak >= ALERT_THRESHOLD
    def need_alert(self): return self.is_down() and not self.alerted

    def to_dict(self):
        with self.lock:
            return {
                "ip":         self.ip,
                "hostname":   self.hostname,
                "phone":      self.phone,
                "label":      self.label,
                "source":     self.source,
                "services":   self.services,
                "streak":     self.fail_streak,
                "status":     "DOWN" if self.is_down() else "UP",
                "last_seen":  self.last_seen,
                "last_check": self.last_check,
                "history":    self.history[-5:],
            }


# =============================================================
#  MONITOR PRINCIPAL
# =============================================================

class PRTGLite:
    def __init__(self, extra_nodes=None, use_shark=False, shark_iface=None):
        self.local_ip   = get_primary_ip()
        self.nodes      = {}
        self.nodes_lock = threading.Lock()
        self.alerts     = []
        self.running    = False
        self.cycle      = 0
        self.extras     = extra_nodes or []
        self.shark      = SharkSniffer(self, interface=shark_iface) if use_shark else None

    # ── Registrar nodo ──
    def register(self, ip, label="", source="scan"):
        """
        Para agregar tu celular desde codigo:
            monitor.register("192.168.1.105", label="Mi celular", source="manual")
        """
        if not RE_IP.match(ip):
            print(f"[!] IP invalida ignorada: {ip}")
            return
        with self.nodes_lock:
            if ip not in self.nodes:
                n = NodeState(ip, label=label, source=source)
                def _enrich(n=n):
                    n.hostname = resolve_hostname(n.ip)
                    n.phone    = get_phone_from_whois(n.ip)
                threading.Thread(target=_enrich, daemon=True).start()
                self.nodes[ip] = n
                tag = f" [{label}]" if label else ""
                print(f"  [+] {ip}{tag}  ({source})")

    # ── Hilo por nodo (requisito #9) ──
    def _node_worker(self, ip):
        """Un hilo dedicado por nodo, corre continuamente."""
        while self.running:
            try:
                results = check_all_services(ip)
                node    = self.nodes[ip]
                node.update(results)

                # ── ALERTA NODO FUERA (#6, #7) ──
                if node.need_alert():
                    node.alerted = True
                    lbl = f" ({node.label})" if node.label else ""
                    msg = (f"ALERTA NODO FUERA: {ip}{lbl} [{node.hostname}]"
                           f" — sin respuesta x{node.fail_streak} ciclos")
                    self.alerts.append({
                        "ts": datetime.now().isoformat(),
                        "ip": ip, "hostname": node.hostname,
                        "label": node.label, "msg": msg
                    })
                    print(f"\n{'!'*65}\n  ALERTA: {msg}\n{'!'*65}\n")

            except Exception as ex:
                print(f"  [ERR node-{ip}] {ex}")

            for _ in range(CHECK_INTERVAL * 10):
                if not self.running:
                    return
                time.sleep(0.1)

    # ── Descubrimiento ──
    def discover(self, prefix=SUBNET_PREFIX):
        base = f"{self.local_ip.rsplit('.',1)[0]}.0"
        print(f"\n{'='*65}")
        print(f"  SO       : {platform.system()} {platform.release()}")
        print(f"  IP local : {self.local_ip}")
        print(f"  Subred   : {base}/{prefix}")
        print(f"  Salida   : {OUTPUT_FILE}")
        print(f"  pyshark  : {'SI' if PYSHARK_OK else 'NO (pip install pyshark)'}")
        print(f"{'='*65}")
        print(f"  Escaneando subred ICMP...")

        alive = discover_subnet(self.local_ip, prefix)
        self.register(self.local_ip, label="localhost", source="local")
        for h in alive:
            self.register(h["ip"])
        for ip in self.extras:
            ip = ip.strip()
            if ip:
                self.register(ip, label="manual", source="manual")

        print(f"\n  Subred: {len(alive)}  |  Manuales: {len(self.extras)}  |  Total: {len(self.nodes)}\n")

    # ── Arrancar ──
    def start(self):
        self.running = True
        for ip in list(self.nodes.keys()):
            threading.Thread(
                target=self._node_worker, args=(ip,),
                daemon=True, name=f"node-{ip}"
            ).start()
        if self.shark:
            self.shark.start()
        print(f"[*] {len(self.nodes)} hilos activos | intervalo={CHECK_INTERVAL}s | umbral={ALERT_THRESHOLD} ciclos\n")

    def stop(self):
        self.running = False
        if self.shark:
            self.shark.stop()

    # ── Guardar JSON ──
    def save(self):
        state = {
            "generated": datetime.now().isoformat(),
            "os":        platform.system(),
            "local_ip":  self.local_ip,
            "cycle":     self.cycle,
            "pyshark":   PYSHARK_OK and self.shark is not None,
            "nodes":     {ip: n.to_dict() for ip, n in self.nodes.items()},
            "alerts":    self.alerts[-30:],
        }
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Error guardando JSON: {e}")

    # ── Tabla consola ──
    def print_table(self):
        COLS = ["ICMP","HTTP","HTTPS","SSH","SNMP","SMTP","POP3","IMAP","UDP/53"]
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        SEP  = "-" * 120

        print(f"\n{'-'*65}")
        print(f"  PRTG-LITE  Ciclo #{self.cycle}  {ts}  Alertas:{len(self.alerts)}")
        print(f"  SO:{platform.system()}  IP:{self.local_ip}  Nodos:{len(self.nodes)}")
        print(f"{'-'*65}")
        hdr = f"  {'IP':<16} {'HOSTNAME/LABEL':<25} {'ST':^6} " + " ".join(f"{c:^9}" for c in COLS)
        print(hdr)
        print(f"  {SEP}")
        with self.nodes_lock:
            for ip, n in sorted(self.nodes.items(), key=lambda x: ip_to_int(x[0])):
                st   = "DOWN!" if n.is_down() else "UP   "
                name = n.hostname[:16] + (f"[{n.label}]" if n.label else "")
                row  = f"  {ip:<16} {name:<25} {st:^6} "
                for c in COLS:
                    svc = n.services.get(c, {})
                    row += f"{'?' if not n.services else ('OK' if svc.get('up') else '--'):^9}"
                print(row)
        print(f"  {SEP}")
        if self.alerts:
            print("  ALERTAS:")
            for a in self.alerts[-5:]:
                print(f"    [{a['ts'][11:19]}] {a['msg'][:70]}")
        print()

    # ── Run ──
    def run(self, prefix=SUBNET_PREFIX):
        print("=" * 65)
        print("  PRTG-LITE v2.0  —  Monitor de Red")
        print("=" * 65)
        print("\n[1] CMD/BASH + REGEX:")
        print(json.dumps(get_local_ip_cmd(), indent=2))
        print("\n[2] PYTHON + REGEX:")
        print(json.dumps(get_local_ip_python(), indent=2))

        self.discover(prefix)
        self.start()
        try:
            while True:
                time.sleep(CHECK_INTERVAL)
                self.cycle += 1
                self.print_table()
                self.save()
        except KeyboardInterrupt:
            print("\n[*] Deteniendo...")
            self.stop()
            self.save()
            print(f"[*] Guardado en: {OUTPUT_FILE}")


# =============================================================
#  ARGPARSE + MAIN
# =============================================================

def parse_args():
    p = argparse.ArgumentParser(description="PRTG-Lite: Monitor de red tipo PRTG")
    p.add_argument("--extra", nargs="+", default=[], metavar="IP",
        help="IPs extra (ej: celular). Uso: --extra 192.168.1.105 192.168.1.106")
    p.add_argument("--interval", type=int, default=CHECK_INTERVAL, metavar="SEG",
        help=f"Intervalo entre ciclos (default: {CHECK_INTERVAL}s)")
    p.add_argument("--prefix", type=int, default=SUBNET_PREFIX, metavar="BITS",
        help=f"Prefijo de subred (default: {SUBNET_PREFIX})")
    p.add_argument("--shark", action="store_true",
        help="Activar pyshark para captura de trafico")
    p.add_argument("--iface", type=str, default=None, metavar="INTERFAZ",
        help="Interfaz para pyshark (ej: eth0, Wi-Fi). Default: auto")
    p.add_argument("--no-discover", action="store_true",
        help="No escanear subred, solo monitorear --extra y localhost")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    CHECK_INTERVAL = args.interval

    if args.shark and not PYSHARK_OK:
        print("[!] pyshark no instalado.")
        print("    Windows : pip install pyshark  +  https://npcap.com/")
        print("    Linux   : pip install pyshark  +  sudo apt install libpcap-dev\n")

    monitor = PRTGLite(
        extra_nodes=list(set(EXTRA_NODES + args.extra)),
        use_shark=args.shark and PYSHARK_OK,
        shark_iface=args.iface
    )

    if args.no_discover:
        monitor.register(monitor.local_ip, label="localhost", source="local")
        for ip in set(EXTRA_NODES + args.extra):
            if ip.strip():
                monitor.register(ip.strip(), label="manual", source="manual")
        monitor.start()
        try:
            while True:
                time.sleep(args.interval)
                monitor.cycle += 1
                monitor.print_table()
                monitor.save()
        except KeyboardInterrupt:
            monitor.stop()
            monitor.save()
    else:
        monitor.run(prefix=args.prefix)
