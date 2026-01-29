#!/bin/bash
apt update && apt install -y python3 python3-pip nginx certbot ufw sqlite3
pip3 install -r requirements.txt

# SSL Certificate (Let's Encrypt)
certbot certonly --standalone -d yourdomain.com

# Firewall
ufw allow 443 && ufw allow 80 && ufw --force enable

# Deploy
mkdir -p /opt/wooly && cd /opt/wooly
# Copy all files here

# Systemd service
cat > /etc/systemd/system/wooly-c2.service <<EOF
[Unit]
Description=Wooly C2 Pentest Platform
After=network.target

[Service]
User=root
WorkingDirectory=/opt/wooly
ExecStart=/usr/local/bin/gunicorn -w 4 -b 0.0.0.0:443 \\
    --certfile /etc/letsencrypt/live/yourdomain.com/fullchain.pem \\
    --keyfile /etc/letsencrypt/live/yourdomain.com/privkey.pem \\
    wooly_c2:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload && systemctl enable wooly-c2 && systemctl start wooly-c2
