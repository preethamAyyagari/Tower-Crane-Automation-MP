from flask import Flask, render_template_string, jsonify, request
import config

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Crane Telemetry & Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: 'Segoe UI', monospace; background: #1a1e24; color: #d2dae2; margin: 0; padding: 20px; }
        h1 { color: #ecf0f1; text-align: center; margin-bottom: 20px; }
        .top-status { display: flex; justify-content: center; gap: 15px; align-items: center; margin-bottom: 20px; flex-wrap: wrap;}
        .badge { padding: 8px 16px; border-radius: 6px; font-weight: bold; background: #2c3e50; }
        .badge.active { background: #20bf6b; color: white; }
        .badge.logging { background: #e84118; color: white; animation: blink 1.5s infinite; }
        @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        .section-header { border-bottom: 2px solid #34495e; color: #0fb9b1; padding-bottom: 6px; margin: 25px 0 15px 0; font-size: 1.1rem; }
        .grid { display: flex; flex-wrap: wrap; gap: 15px; justify-content: center; }
        .card { background: #242c35; border: 1px solid #3a4754; border-radius: 8px; width: 310px; padding: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .card h3 { margin: 0 0 10px 0; color: #3498db; border-bottom: 1px solid #3a4754; padding-bottom: 5px; }
        .readout { font-size: 16px; display: flex; justify-content: space-between; margin-bottom: 8px; }
        .val-adc { color: #2ecc71; font-weight: bold; }
        .val-dac { color: #eb3b5a; font-weight: bold; }
        .val-enc { color: #f1c40f; font-weight: bold; }
        .chart-box { height: 110px; background: #1a1e24; border-radius: 4px; padding: 4px; margin-bottom: 10px; }
        .controls { display: flex; flex-direction: column; gap: 6px; }
        .input-row { display: flex; gap: 8px; }
        input { width: 50%; padding: 6px; border-radius: 4px; border: 1px solid #485460; background: #c8d6e5; text-align: center; font-weight: bold; }
        button { border: none; border-radius: 4px; padding: 8px; font-weight: bold; cursor: pointer; }
        .btn-go { background: #20bf6b; color: white; }
        .btn-stop { background: #eb3b5a; color: white; }
        .btn-rst { background: #576574; color: white; }
        .btn-toggle { background: #3498db; color: white; }
        .btn-log-start { background: #e84118; color: white; }
        .btn-log-stop { background: #718093; color: white; }
    </style>
</head>
<body>
    <h1>Crane Telemetry & USB Monitor</h1>

    <div class="top-status">
        <div id="joyBadge" class="badge">🕹️ Joystick: Ready</div>
        <button class="btn-toggle" onclick="toggleJoystick()">Toggle Joystick Auto-Control</button>
        <div id="logBadge" class="badge">📁 Logger: Idle</div>
        <button id="logBtn" class="btn-log-start" onclick="toggleLogging()">⏺ Start SQL Logging</button>
    </div>

    <div class="section-header">📡 Analog Sensor Readings (CN0554 AD7124)</div>
    <div class="grid">
        {% for ch, name in adc_channels %}
        <div class="card">
            <h3>ADC {{ ch }} - {{ name }}</h3>
            <div class="readout"><span>Signal:</span><span id="adc-{{ ch }}" class="val-adc">0.000V</span></div>
            <div class="chart-box"><canvas id="adcChart-{{ ch }}"></canvas></div>
        </div>
        {% endfor %}
    </div>

    <div class="section-header">⚙️ Motor Drive & Axes Output (LTC2688 DAC)</div>
    <div class="grid">
        {% for ch, name, has_enc, axis_key in dac_channels %}
        <div class="card">
            <h3>CH {{ ch }} - {{ name }}</h3>
            <div class="readout">
                <span id="dac-{{ ch }}" class="val-dac">0.00V Out</span>
                {% if has_enc %}
                <span id="enc-{{ axis_key }}" class="val-enc">Enc: 0</span>
                {% else %}
                <span style="color:#8395a7;">Analog Open-Loop</span>
                {% endif %}
            </div>

            <div class="chart-box"><canvas id="dacChart-{{ ch }}"></canvas></div>
            
            <div class="controls">
                <div class="input-row">
                    <input id="v-{{ ch }}" type="number" step="0.1" value="2.0" placeholder="Volts">
                    {% if has_enc %}
                    <input id="t-{{ ch }}" type="number" step="50" value="500" placeholder="Target">
                    {% endif %}
                </div>
                {% if has_enc %}
                <button class="btn-go" onclick="sendCmd('{{ axis_key }}', {{ ch }})">MOVE TO POSITION</button>
                <button class="btn-rst" onclick="post('/zero', {axis: '{{ axis_key }}'})">Zero Axis</button>
                {% else %}
                <button class="btn-go" onclick="setVoltageOnly({{ ch }})">APPLY VOLTAGE</button>
                {% endif %}
                <button class="btn-stop" onclick="post('/stop', {ch: {{ ch }}})">STOP</button>
            </div>
        </div>
        {% endfor %}
    </div>

    <script>
        const adcCharts = {};
        const dacCharts = {};
        const MAX_POINTS = 30;
        let joyEnabled = true;
        let isLoggingActive = false;

        function createAutoChart(ctx, borderColor) {
            return new Chart(ctx, {
                type: 'line',
                data: { 
                    labels: Array(MAX_POINTS).fill(''), 
                    datasets: [{ data: Array(MAX_POINTS).fill(null), borderColor: borderColor, borderWidth: 2 }] 
                },
                options: {
                    responsive: true, 
                    maintainAspectRatio: false, 
                    animation: false,
                    plugins: { legend: { display: false } },
                    scales: { 
                        y: { 
                            grid: { color: 'rgba(255, 255, 255, 0.08)' },
                            ticks: { color: '#aaa', font: { size: 10 } }
                        }, 
                        x: { display: false } 
                    },
                    elements: { point: { radius: 0 } }
                }
            });
        }

        document.querySelectorAll("[id^='adcChart-']").forEach(canvas => {
            const id = canvas.id.split('-')[1];
            adcCharts[id] = createAutoChart(canvas.getContext('2d'), '#2ecc71');
        });

        document.querySelectorAll("[id^='dacChart-']").forEach(canvas => {
            const id = canvas.id.split('-')[1];
            dacCharts[id] = createAutoChart(canvas.getContext('2d'), '#eb3b5a');
        });

        function post(url, data) { fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)}); }

        function sendCmd(axis, ch) {
            post('/cmd', {axis: axis, ch: ch, v: document.getElementById('v-' + ch).value, t: document.getElementById('t-' + ch).value});
        }

        function setVoltageOnly(ch) {
            post('/set_v', {ch: ch, v: document.getElementById('v-' + ch).value});
        }

        function toggleJoystick() {
            joyEnabled = !joyEnabled;
            post('/toggle_joy', {enabled: joyEnabled});
        }

        function toggleLogging() {
            isLoggingActive = !isLoggingActive;
            fetch('/toggle_log', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({logging: isLoggingActive})
            }).then(r => r.json()).then(res => {
                const btn = document.getElementById('logBtn');
                const badge = document.getElementById('logBadge');
                if (res.logging) {
                    btn.innerText = "⏹ Stop SQL Logging";
                    btn.className = "btn-log-stop";
                    badge.innerText = "📁 Recording to DB...";
                    badge.className = "badge logging";
                } else {
                    btn.innerText = "⏺ Start SQL Logging";
                    btn.className = "btn-log-start";
                    badge.innerText = "📁 Logger: Saved";
                    badge.className = "badge";
                }
            });
        }

        setInterval(() => {
            fetch('/data').then(r => r.json()).then(data => {
                data.adc.forEach((val, i) => {
                    const el = document.getElementById('adc-' + i);
                    if (el) el.innerText = val.toFixed(3) + 'V';
                    if (adcCharts[i]) {
                        adcCharts[i].data.datasets[0].data.shift();
                        adcCharts[i].data.datasets[0].data.push(val);
                        adcCharts[i].update();
                    }
                });

                data.dac.forEach((val, i) => {
                    const el = document.getElementById('dac-' + i);
                    if (el) el.innerText = val.toFixed(2) + 'V Out';
                    if (dacCharts[i]) {
                        dacCharts[i].data.datasets[0].data.shift();
                        dacCharts[i].data.datasets[0].data.push(val);
                        dacCharts[i].update();
                    }
                });

                if (document.getElementById('enc-spin'))
                    document.getElementById('enc-spin').innerText = "Enc: " + data.enc.spin;
                if (document.getElementById('enc-trolley'))
                    document.getElementById('enc-trolley').innerText = "Enc: " + data.enc.trolley;

                const badge = document.getElementById('joyBadge');
                if (!data.joy.enabled) {
                    badge.innerText = "🕹️ Joystick: Disabled";
                    badge.classList.remove('active');
                } else if (data.joy.in_use) {
                    badge.innerText = "🕹️ Joystick: Active (Manual Driving)";
                    badge.classList.add('active');
                } else {
                    badge.innerText = "🕹️ Joystick: Standby (Centered)";
                    badge.classList.remove('active');
                }
            });
        }, 250);
    </script>
</body>
</html>
"""

def create_app(controller, logger):
    app = Flask(__name__)

    @app.route('/')
    def index():
        adc_map = [
            (config.ADC_CH_JOYSTICK_X, 'Joystick X (Spin)'),
            (config.ADC_CH_JOYSTICK_Y, 'Joystick Y (Trolley)'),
            (config.ADC_CH_HOOK_SENSOR, 'Hook Sensor'),
            (config.ADC_CH_TILT_SENSOR, 'Tilt Sensor'),
            (config.ADC_CH_SWING_ALPHA, 'Alpha Swing Sensor'),
            (config.ADC_CH_SWING_BETA,  'Beta Swing Sensor')
        ]
        dac_map = [
            (config.DAC_CH_SPIN, 'Spin Motor', True, 'spin'),
            (config.DAC_CH_TROLLEY, 'Trolley Motor', True, 'trolley'),
            (config.DAC_CH_HOOK, 'Hook Motor (Open-Loop)', False, 'hook'),
            (config.DAC_CH_TILT, 'Tilt Motor (Open-Loop)', False, 'tilt')
        ]
        return render_template_string(HTML_TEMPLATE, adc_channels=adc_map, dac_channels=dac_map)

    @app.route('/data')
    def telemetry():
        return jsonify(controller.get_status())

    @app.route('/cmd', methods=['POST'])
    def cmd():
        d = request.json
        controller.set_target(d['axis'], int(d['t']), float(d['v']))
        return jsonify(ok=True)

    @app.route('/set_v', methods=['POST'])
    def set_v():
        d = request.json
        controller.set_output_voltage(int(d['ch']), float(d['v']))
        return jsonify(ok=True)

    @app.route('/stop', methods=['POST'])
    def stop():
        controller.stop_axis(int(request.json['ch']))
        return jsonify(ok=True)

    @app.route('/zero', methods=['POST'])
    def zero():
        controller.reset_encoder(request.json['axis'])
        return jsonify(ok=True)

    @app.route('/toggle_joy', methods=['POST'])
    def toggle_joy():
        controller.toggle_joystick(bool(request.json['enabled']))
        return jsonify(ok=True)

    @app.route('/toggle_log', methods=['POST'])
    def toggle_log():
        should_log = bool(request.json['logging'])
        if should_log:
            db_path = logger.start()
            return jsonify(logging=True, file=db_path)
        else:
            db_path = logger.stop()
            return jsonify(logging=False, file=db_path)

    return app