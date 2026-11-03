import os
import sqlite3
import config
from flask import Flask, render_template_string, jsonify, request, send_file
import matplotlib
matplotlib.use('Agg')  # Headless backend for web server rendering
import matplotlib.pyplot as plt
import io

app = Flask(__name__)

# Base directory for logs: 2 levels above this script ('../../logs')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.abspath(os.path.join(BASE_DIR, config.LOGS_DIR_RELATIVE))

PLOTTER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Crane Log SQLite Visualizer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Segoe UI', monospace; background: #1a1e24; color: #d2dae2; margin: 0; padding: 20px; }
        h1 { color: #ecf0f1; text-align: center; margin-bottom: 25px; }
        .container { max-width: 1200px; margin: auto; }
        .panel { background: #242c35; border: 1px solid #3a4754; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .row { display: flex; flex-wrap: wrap; gap: 15px; align-items: center; margin-bottom: 15px; }
        label { font-weight: bold; color: #0fb9b1; }
        select, input { padding: 8px 12px; border-radius: 4px; border: 1px solid #485460; background: #c8d6e5; color: #1a1e24; font-weight: bold; }
        select { min-width: 280px; }
        .checkbox-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; margin: 15px 0; }
        .checkbox-item { background: #1a1e24; padding: 10px; border-radius: 6px; border: 1px solid #3a4754; display: flex; align-items: center; gap: 10px; }
        .checkbox-item input[type="checkbox"] { transform: scale(1.3); cursor: pointer; }
        .color-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
        button { padding: 10px 20px; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; transition: 0.2s; }
        .btn-plot { background: #20bf6b; color: white; font-size: 15px; }
        .btn-plot:hover { background: #26de81; }
        .btn-save { background: #8e44ad; color: white; font-size: 15px; }
        .btn-save:hover { background: #9b59b6; }
        .chart-box { height: 450px; background: #1a1e24; border-radius: 6px; padding: 15px; margin-top: 15px; }
        .status-msg { color: #f39c12; margin-top: 10px; font-weight: bold; }
    </style>
</head>
<body>
<div class="container">
    <h1> Crane SQLite Data Log Visualizer</h1>

    <div class="panel">
        <div class="row">
            <label for="dbSelect">Select Log File:</label>
            <select id="dbSelect" onchange="fetchTables()"></select>
            <button onclick="refreshDbList()"> Refresh Files</button>
        </div>

        <label>Select Tables / Signals to Plot (1 or more):</label>
        <div id="tableList" class="checkbox-grid">
            <em>Select a log file above to see available tables...</em>
        </div>

        <div class="row" style="margin-top: 20px;">
            <label for="layoutMode">Graph Layout:</label>
            <select id="layoutMode">
                <option value="overlay">Overlay (Single Common Y-Axis, Auto-Scaled)</option>
                <option value="stacked">Subplots (Stacked Individual Y-Axes per Signal)</option>
            </select>
            <button class="btn-plot" onclick="plotSelected()"> Render Graph</button>
        </div>

        <div class="row" style="margin-top: 15px; border-top: 1px solid #3a4754; padding-top: 15px;">
            <label for="exportName">Save File As:</label>
            <input id="exportName" type="text" value="crane_telemetry_plot" style="width: 260px;">
            <span>.png</span>
            <button class="btn-save" onclick="downloadImage()"> Save High-Res PNG</button>
        </div>
        <div id="status" class="status-msg"></div>
    </div>

    <div class="panel">
        <div class="chart-box">
            <canvas id="mainChart"></canvas>
        </div>
    </div>
</div>

<script>
    const TRACE_COLORS = [
        '#00d2d3', '#ff9f43', '#10ac84', '#ee5253', 
        '#5f27cd', '#54a0ff', '#f368e0', '#0abde3', 
        '#ff6b6b', '#48dbfb'
    ];
    let chartInstance = null;

    window.onload = function() {
        refreshDbList();
    };

    function setStatus(msg) {
        document.getElementById('status').innerText = msg;
    }

    function refreshDbList() {
        fetch('/api/list_logs').then(r => r.json()).then(files => {
            const sel = document.getElementById('dbSelect');
            sel.innerHTML = '';
            if (files.length === 0) {
                sel.innerHTML = '<option value="">No .db logs found in ../../logs</option>';
                return;
            }
            files.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f;
                opt.innerText = f;
                sel.appendChild(opt);
            });
            fetchTables();
        });
    }

    function fetchTables() {
        const db = document.getElementById('dbSelect').value;
        if (!db) return;
        fetch('/api/list_tables?db=' + encodeURIComponent(db))
            .then(r => r.json())
            .then(tables => {
                const container = document.getElementById('tableList');
                container.innerHTML = '';
                tables.forEach((t, i) => {
                    const color = TRACE_COLORS[i % TRACE_COLORS.length];
                    const div = document.createElement('div');
                    div.className = 'checkbox-item';
                    div.innerHTML = `
                        <input type="checkbox" id="chk_${t}" value="${t}" ${i < 3 ? 'checked' : ''}>
                        <span class="color-dot" style="background: ${color};"></span>
                        <label for="chk_${t}" style="color: #ecf0f1; cursor: pointer;">${t}</label>
                    `;
                    container.appendChild(div);
                });
            });
    }

    function getSelectedTables() {
        const checks = document.querySelectorAll('#tableList input[type="checkbox"]:checked');
        return Array.from(checks).map(c => c.value);
    }

    function plotSelected() {
        const db = document.getElementById('dbSelect').value;
        const selected = getSelectedTables();

        if (!db) { setStatus(" Please select a log database first."); return; }
        if (selected.length === 0) { setStatus(" Please check at least one table to plot."); return; }

        setStatus("Loading telemetry data...");

        fetch('/api/get_data', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ db: db, tables: selected })
        }).then(r => r.json()).then(data => {
            setStatus("Rendering graph with " + selected.length + " signal(s)...");
            renderChartJS(data);
            setStatus("");
        }).catch(err => {
            setStatus("❌ Error loading graph: " + err);
        });
    }

    function renderChartJS(payload) {
        const ctx = document.getElementById('mainChart').getContext('2d');
        if (chartInstance) chartInstance.destroy();

        // Build datasets
        const datasets = payload.series.map((s, idx) => ({
            label: s.table,
            data: s.points.map(pt => ({ x: pt.t, y: pt.v })),
            borderColor: TRACE_COLORS[idx % TRACE_COLORS.length],
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.1
        }));

        chartInstance = new Chart(ctx, {
            type: 'line',
            data: { datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { labels: { color: '#ecf0f1', font: { size: 12 } } },
                    tooltip: { mode: 'index', intersect: false }
                },
                scales: {
                    x: {
                        type: 'linear',
                        title: { display: true, text: 'Time (seconds)', color: '#0fb9b1', font: { size: 13, weight: 'bold' } },
                        grid: { color: 'rgba(255, 255, 255, 0.12)', lineWidth: 1 },
                        ticks: { color: '#aaa' }
                    },
                    y: {
                        title: { display: true, text: 'Signal Magnitude (Volts)', color: '#0fb9b1', font: { size: 13, weight: 'bold' } },
                        // Automatic scaling bounds strictly to min/max data points
                        grid: { color: 'rgba(255, 255, 255, 0.12)', lineWidth: 1 },
                        ticks: { color: '#aaa' }
                    }
                }
            }
        });
    }

    function downloadImage() {
        const db = document.getElementById('dbSelect').value;
        const selected = getSelectedTables();
        const exportName = document.getElementById('exportName').value || 'crane_telemetry_plot';
        const layout = document.getElementById('layoutMode').value;

        if (!db || selected.length === 0) {
            alert("Please select a file and at least one table before saving.");
            return;
        }

        setStatus("Generating high-resolution PNG via server-side Matplotlib...");

        const url = `/api/export_png?db=${encodeURIComponent(db)}&tables=${encodeURIComponent(selected.join(','))}&filename=${encodeURIComponent(exportName)}&layout=${layout}`;
        window.location.href = url;
        setTimeout(() => setStatus(""), 2000);
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(PLOTTER_HTML)

@app.route('/api/list_logs')
def list_logs():
    if not os.path.exists(LOGS_DIR):
        return jsonify([])
    files = [f for f in os.listdir(LOGS_DIR) if f.endswith('.db')]
    files.sort(reverse=True)  # Newest first
    return jsonify(files)

@app.route('/api/list_tables')
def list_tables():
    db_name = request.args.get('db')
    db_path = os.path.join(LOGS_DIR, db_name)
    if not os.path.exists(db_path):
        return jsonify([])
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    return jsonify(tables)

@app.route('/api/get_data', methods=['POST'])
def get_data():
    req = request.json
    db_name = req.get('db')
    selected_tables = req.get('tables', [])
    db_path = os.path.join(LOGS_DIR, db_name)

    if not os.path.exists(db_path):
        return jsonify(error="DB not found"), 404

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    response_data = []

    for tbl in selected_tables:
        cur.execute(f"SELECT timestamp, value FROM {tbl} ORDER BY timestamp ASC")
        rows = cur.fetchall()
        response_data.append({
            "table": tbl,
            "points": [{"t": round(r[0], 4), "v": round(r[1], 3)} for r in rows]
        })

    conn.close()
    return jsonify(series=response_data)

@app.route('/api/export_png')
def export_png():
    db_name = request.args.get('db')
    tables = request.args.get('tables', '').split(',')
    export_filename = request.args.get('filename', 'crane_plot').strip()
    layout = request.args.get('layout', 'overlay')

    if not export_filename.endswith('.png'):
        export_filename += '.png'

    db_path = os.path.join(LOGS_DIR, db_name)
    if not os.path.exists(db_path) or not tables:
        return "Invalid parameters", 400

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    plt.style.use('dark_background')
    colors = ['#00d2d3', '#ff9f43', '#10ac84', '#ee5253', '#5f27cd', '#54a0ff', '#f368e0', '#ff6b6b']

    if layout == 'stacked':
        # Subplot mode: each table gets its own dedicated row with independent auto-scaled Y axis
        fig, axes = plt.subplots(len(tables), 1, figsize=(12, 3.5 * len(tables)), sharex=True)
        if len(tables) == 1:
            axes = [axes]

        for i, tbl in enumerate(tables):
            cur.execute(f"SELECT timestamp, value FROM {tbl} ORDER BY timestamp ASC")
            data = cur.fetchall()
            t = [r[0] for r in data]
            v = [r[1] for r in data]
            c = colors[i % len(colors)]

            ax = axes[i]
            ax.plot(t, v, color=c, label=tbl, linewidth=1.8)
            ax.set_ylabel(f"{tbl}\n(Volts)", fontsize=10, fontweight='bold', color=c)
            # Both Major and Minor grid lines for readability
            ax.grid(True, which='major', color='#485460', linestyle='-', alpha=0.7)
            ax.grid(True, which='minor', color='#2d3436', linestyle=':', alpha=0.5)
            ax.minorticks_on()
            ax.legend(loc='upper right')

        axes[-1].set_xlabel("Time (seconds)", fontsize=11, fontweight='bold', color='#0fb9b1')
        plt.suptitle(f"Crane Telemetry Log: {db_name}", fontsize=13, fontweight='bold', color='#ecf0f1')
        plt.tight_layout()

    else:
        # Overlay mode: All traces share one auto-scaled Y-axis with distinct colors
        fig, ax = plt.subplots(figsize=(12, 6))
        for i, tbl in enumerate(tables):
            cur.execute(f"SELECT timestamp, value FROM {tbl} ORDER BY timestamp ASC")
            data = cur.fetchall()
            t = [r[0] for r in data]
            v = [r[1] for r in data]
            c = colors[i % len(colors)]
            ax.plot(t, v, color=c, label=tbl, linewidth=1.8)

        ax.set_xlabel("Time (seconds)", fontsize=11, fontweight='bold', color='#0fb9b1')
        ax.set_ylabel("Signal Amplitude (Volts)", fontsize=11, fontweight='bold', color='#0fb9b1')
        ax.set_title(f"Crane Telemetry Log: {db_name}", fontsize=13, fontweight='bold', color='#ecf0f1')
        
        # Grid lines on both axes
        ax.grid(True, which='major', color='#485460', linestyle='-', alpha=0.7)
        ax.grid(True, which='minor', color='#2d3436', linestyle=':', alpha=0.5)
        ax.minorticks_on()
        ax.legend(loc='upper right', framealpha=0.8)
        plt.tight_layout()

    conn.close()

    # Save to memory buffer and serve download
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)

    return send_file(buf, mimetype='image/png', as_attachment=True, download_name=export_filename)

if __name__ == '__main__':
    print(" SQLite Visualizer operational on http://0.0.0.0:5003")
    app.run(host='0.0.0.0', port=5003, debug=False)