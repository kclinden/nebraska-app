from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory
import boto3

app = Flask(__name__)
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
players_table = dynamodb.Table("NebraskaPlayers")
schedule_table = dynamodb.Table("NebraskaSchedule2026")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Husker Football 2026</title>
    <style>
        :root {
            --scarlet: #e41c38;
            --scarlet-dark: #a81228;
            --cream: #fff8ef;
            --ink: #241b1c;
            --line: #ead8cb;
            --card: #fffdf9;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            font-family: 'Trebuchet MS', 'Segoe UI', sans-serif;
            color: var(--ink);
            background:
                radial-gradient(circle at 20% 0%, #ffe9e2 0%, transparent 35%),
                radial-gradient(circle at 90% 10%, #ffd8df 0%, transparent 28%),
                linear-gradient(180deg, #fffaf5 0%, #fff3ea 100%);
        }

        .container {
            max-width: 1120px;
            margin: 28px auto;
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: 0 14px 34px rgba(82, 33, 33, 0.12);
            overflow: hidden;
        }

        .hero {
            display: grid;
            grid-template-columns: 1.25fr 1fr;
            gap: 24px;
            padding: 28px 30px;
            background:
                linear-gradient(135deg, rgba(228, 28, 56, 0.95), rgba(176, 16, 42, 0.98)),
                repeating-linear-gradient(45deg, rgba(255, 255, 255, 0.08) 0, rgba(255, 255, 255, 0.08) 8px, transparent 8px, transparent 16px);
            color: #fff;
            border-bottom: 5px solid #840f22;
        }

        .hero h1 {
            margin: 0;
            font-size: clamp(32px, 4vw, 52px);
            line-height: 0.95;
            letter-spacing: 1.2px;
            text-transform: uppercase;
        }

        .tagline {
            margin: 12px 0 18px;
            max-width: 560px;
            font-size: 16px;
            line-height: 1.45;
            color: #ffe9eb;
        }

        .logo-row {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
        }

        .n-logo {
            display: inline-grid;
            place-items: center;
            width: 46px;
            height: 46px;
            border-radius: 10px;
            background: #fff;
            border: 2px solid rgba(255, 255, 255, 0.6);
            color: var(--scarlet);
            font-size: 29px;
            font-weight: 900;
            line-height: 1;
            box-shadow: inset 0 0 0 2px #b7142d;
        }

        .chip {
            display: inline-block;
            padding: 7px 11px;
            border-radius: 999px;
            font-weight: 700;
            font-size: 12px;
            letter-spacing: 0.4px;
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.25);
        }

        .hero-right {
            display: grid;
            grid-template-rows: auto auto;
            gap: 12px;
            align-content: start;
        }

        .history {
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.28);
            border-radius: 14px;
            padding: 14px;
        }

        .history h3 {
            margin: 0 0 8px;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: #ffe9eb;
        }

        .history-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }

        .stat {
            background: rgba(255, 255, 255, 0.16);
            border-radius: 10px;
            padding: 10px;
            text-align: center;
        }

        .stat strong {
            display: block;
            font-size: 26px;
            line-height: 1;
        }

        .stat span {
            font-size: 12px;
            color: #ffe8ea;
        }

        .titles {
            margin-top: 8px;
            font-size: 12px;
            color: #ffe8ea;
        }

        .hero-image {
            background: #fff;
            border-radius: 14px;
            border: 2px solid #f2d7cc;
            padding: 10px;
            box-shadow: 0 8px 22px rgba(45, 16, 16, 0.14);
        }

        .hero-image img {
            width: 100%;
            display: block;
            border-radius: 10px;
            border: 1px solid #ead8cb;
        }

        .hero-image-caption {
            margin-top: 8px;
            font-size: 12px;
            color: #5d4b45;
            text-align: center;
        }

        .main-content {
            padding: 22px 30px 30px;
        }

        .toolbar {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 14px;
            margin-bottom: 14px;
        }

        .tabs { display: flex; gap: 10px; }

        button {
            background-color: var(--scarlet);
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 15px;
            font-weight: 700;
            transition: background-color 120ms ease, transform 120ms ease;
        }

        button:hover { background-color: #b31227; }

        .tab-btn {
            background-color: #fff;
            color: var(--scarlet);
            border: 2px solid var(--scarlet);
        }

        .tab-btn.active {
            background-color: var(--scarlet);
            color: #fff;
        }

        .tab-panel { display: none; }
        .tab-panel.active { display: block; }

        #playBtn {
            background: linear-gradient(180deg, #ef3f4f 0%, #e41c38 60%, #b5122b 100%);
            color: #fff9f0;
            border: 2px solid #8f0d22;
            text-shadow: 0 1px 0 #7a0b1c;
            box-shadow: 0 5px 0 #8f0d22, 0 8px 20px rgba(164, 17, 39, 0.35);
            min-width: 215px;
        }

        #playBtn:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 0 #8f0d22, 0 10px 24px rgba(164, 17, 39, 0.4);
        }

        #playBtn:active {
            transform: translateY(2px);
            box-shadow: 0 2px 0 #8f0d22, 0 4px 10px rgba(164, 17, 39, 0.25);
        }

        .card {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 16px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
            background: #fff;
            border-radius: 10px;
            overflow: hidden;
        }

        th, td {
            padding: 12px;
            border: 1px solid #efdfd4;
            text-align: left;
        }

        th {
            background: var(--scarlet);
            color: white;
            font-size: 14px;
            letter-spacing: 0.3px;
        }

        tr:nth-child(even) { background-color: #fff8f4; }

        .delete-btn {
            background-color: #645550;
            padding: 6px 10px;
            font-size: 12px;
        }

        .delete-btn:hover { background-color: #3f3633; }

        .form-group { margin: 14px 0; text-align: left; }
        label { display: block; margin-bottom: 6px; font-weight: 700; }

        input[type="text"], input[type="number"] {
            width: 100%;
            padding: 9px;
            border: 1px solid #d8c1b3;
            border-radius: 8px;
            font-size: 14px;
        }

        .panel-title {
            margin: 0 0 8px;
            font-size: 22px;
            color: #7d1122;
            text-transform: uppercase;
            letter-spacing: 0.7px;
        }

        @media (max-width: 900px) {
            .hero {
                grid-template-columns: 1fr;
            }

            .container {
                margin: 12px;
            }

            .main-content,
            .hero {
                padding: 20px;
            }

            .toolbar {
                flex-direction: column;
                align-items: stretch;
            }

            .tabs {
                width: 100%;
            }

            .tab-btn,
            #playBtn {
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="hero">
            <div>
                <div class="logo-row">
                    <span class="n-logo">N</span>
                    <span class="chip">HUSKER PRIDE</span>
                    <span class="chip">LINCOLN, NE</span>
                </div>
                <h1>NEBRASKA CORNHUSKERS</h1>
                <p class="tagline">
                    Built for Big Red fans: track the 2026 roster and schedule, celebrate championship history,
                    and crank up Hail Varsity before kickoff.
                </p>
            </div>

            <div class="hero-right">
                <div class="history">
                    <h3>Program Legacy</h3>
                    <div class="history-grid">
                        <div class="stat">
                            <strong>5</strong>
                            <span>National Titles</span>
                        </div>
                        <div class="stat">
                            <strong>46</strong>
                            <span>Conference Titles</span>
                        </div>
                        <div class="stat">
                            <strong>3</strong>
                            <span>Heisman Winners</span>
                        </div>
                        <div class="stat">
                            <strong>900+</strong>
                            <span>All-Time Wins</span>
                        </div>
                    </div>
                    <p class="titles">National Championships: 1970, 1971, 1994, 1995, 1997</p>
                </div>

                <div class="hero-image">
                    <img src="/nebraska_football.png" alt="Nebraska football pride artwork">
                    <div class="hero-image-caption">Big Red energy for every game week.</div>
                </div>
            </div>
        </div>

        <div class="main-content">
            <div class="toolbar">
                <div class="tabs">
                    <button id="rosterTab" class="tab-btn active" type="button">Roster 2026</button>
                    <button id="scheduleTab" class="tab-btn" type="button">Schedule 2026</button>
                </div>
                <button id="playBtn">Play Hail Varsity</button>
            </div>

            <div id="rosterPanel" class="tab-panel active card">
                <h2 class="panel-title">Roster</h2>
                <table>
                    <tr>
                        <th>Jersey #</th>
                        <th>Name</th>
                        <th>Position</th>
                        <th>Actions</th>
                    </tr>
                    {% for player in players %}
                    <tr>
                        <td>{{ player.JerseyNumber }}</td>
                        <td>{{ player.Name }}</td>
                        <td>{{ player.Position }}</td>
                        <td>
                            <form action="/delete" method="POST" style="display:inline;">
                                <input type="hidden" name="jersey" value="{{ player.JerseyNumber }}">
                                <input type="hidden" name="name" value="{{ player.Name }}">
                                <button type="submit" class="delete-btn">Remove</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </table>

                <hr style="border: 0; border-top: 1px solid #eee3da; margin: 26px 0;">

                <h3 class="panel-title" style="font-size: 18px;">Add Player</h3>
                <form action="/add" method="POST">
                    <div class="form-group">
                        <label for="jersey">Jersey Number:</label>
                        <input type="number" id="jersey" name="jersey" required>
                    </div>
                    <div class="form-group">
                        <label for="name">Player Name:</label>
                        <input type="text" id="name" name="name" required>
                    </div>
                    <div class="form-group">
                        <label for="position">Position:</label>
                        <input type="text" id="position" name="position" required>
                    </div>
                    <button type="submit">Add Player</button>
                </form>
            </div>

            <div id="schedulePanel" class="tab-panel card">
                <h2 class="panel-title">2026 Schedule</h2>
                <table>
                    <tr>
                        <th>Week</th>
                        <th>Date</th>
                        <th>Opponent</th>
                        <th>Location</th>
                        <th>Type</th>
                    </tr>
                    {% for game in schedule %}
                    <tr>
                        <td>{{ game.GameId }}</td>
                        <td>{{ game.Date }}</td>
                        <td>{{ game.Opponent }}</td>
                        <td>{{ game.Location }}</td>
                        <td>{{ "Home" if game.Home else "Away" }}</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        </div>
    </div>

    <script>
        const rosterTab = document.getElementById('rosterTab');
        const scheduleTab = document.getElementById('scheduleTab');
        const rosterPanel = document.getElementById('rosterPanel');
        const schedulePanel = document.getElementById('schedulePanel');

        function activateTab(tabName) {
            const showRoster = tabName === 'roster';
            rosterTab.classList.toggle('active', showRoster);
            scheduleTab.classList.toggle('active', !showRoster);
            rosterPanel.classList.toggle('active', showRoster);
            schedulePanel.classList.toggle('active', !showRoster);
        }

        rosterTab.addEventListener('click', () => activateTab('roster'));
        scheduleTab.addEventListener('click', () => activateTab('schedule'));

        const playBtn = document.getElementById('playBtn');
        let activePlayback = null;

        playBtn.addEventListener('click', async () => {
            if (activePlayback) {
                activePlayback.stop();
                return;
            }

            const AudioContext = window.AudioContext || window.webkitAudioContext;
            const ctx = new AudioContext();
            await ctx.resume();

            const activeNodes = [];
            let stopped = false;

            const stopPlayback = () => {
                if (stopped) {
                    return;
                }
                stopped = true;
                const now = ctx.currentTime;
                activeNodes.forEach(({ osc, gain }) => {
                    try {
                        gain.gain.cancelScheduledValues(now);
                        gain.gain.setTargetAtTime(0.0001, now, 0.02);
                        osc.stop(now + 0.05);
                    } catch (e) {
                        // Node may already be stopped.
                    }
                });
                activePlayback = null;
                playBtn.textContent = 'Play Hail Varsity';
                setTimeout(() => {
                    ctx.close().catch(() => {});
                }, 120);
            };

            activePlayback = { stop: stopPlayback };
            playBtn.textContent = 'Stop Hail Varsity';

            const tempo = 118;
            const beat = 60 / tempo;
            const H = beat * 0.5;
            const Q = beat;
            const DQ = beat * 1.5;

            const N = {
                E3: 164.81,
                F3: 174.61,
                G3: 196.0,
                A3: 220.0,
                B3: 246.94,
                C4: 261.63,
                D4: 293.66,
                E4: 329.63,
                F4: 349.23,
                G4: 392.0,
                A4: 440.0,
                B4: 493.88,
                C5: 523.25,
                D5: 587.33,
                E5: 659.25
            };

            // Lead phrase approximates Hail Varsity contour with longer playback.
            const lead = [
                [N.G4, Q], [N.B4, Q], [N.C5, Q], [N.B4, Q],
                [N.A4, Q], [N.G4, Q], [N.E4, Q], [N.G4, Q],
                [N.B4, DQ], [N.A4, H], [N.G4, Q], [N.E4, Q],

                [N.G4, Q], [N.B4, Q], [N.C5, Q], [N.D5, Q],
                [N.E5, DQ], [N.D5, H], [N.C5, Q], [N.B4, Q],
                [N.A4, DQ], [N.G4, H], [N.E4, Q], [N.G4, Q],

                [N.A4, Q], [N.B4, Q], [N.C5, Q], [N.B4, Q],
                [N.A4, Q], [N.G4, Q], [N.E4, Q], [N.G4, Q],
                [N.B4, DQ], [N.C5, H], [N.D5, Q], [N.C5, Q],

                [N.B4, Q], [N.A4, Q], [N.G4, DQ], [N.E4, H],
                [N.G4, Q], [N.A4, Q], [N.B4, Q], [N.G4, Q],
                [N.E4, DQ], [N.G4, H], [N.C5, Q], [N.B4, Q],
                [N.A4, Q], [N.G4, DQ]
            ];

            // Bass keeps marching feel under melody.
            const bass = [
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.G3, Q], [N.G3, Q],
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.D4, Q], [N.D4, Q],

                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.G3, Q], [N.G3, Q],
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.D4, Q], [N.D4, Q],

                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.G3, Q], [N.G3, Q],
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.D4, Q], [N.D4, Q],

                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.G3, Q], [N.G3, Q],
                [N.E3, Q], [N.E3, Q], [N.B3, Q], [N.B3, Q],
                [N.C4, Q], [N.C4, Q], [N.D4, Q], [N.D4, Q]
            ];

            function scheduleVoice(sequence, type, volume, startAt, detune = 0) {
                let t = startAt;
                sequence.forEach(([freq, dur]) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();

                    osc.type = type;
                    osc.frequency.value = freq;
                    osc.detune.value = detune;

                    osc.connect(gain);
                    gain.connect(ctx.destination);

                    const attack = Math.min(0.03, dur * 0.2);
                    const release = Math.min(0.1, dur * 0.35);
                    const sustain = Math.max(dur - attack - release, 0.01);
                    const stopAt = t + attack + sustain + release;

                    gain.gain.setValueAtTime(0.0001, t);
                    gain.gain.linearRampToValueAtTime(volume, t + attack);
                    gain.gain.setValueAtTime(volume, t + attack + sustain);
                    gain.gain.exponentialRampToValueAtTime(0.0001, stopAt);

                    osc.start(t);
                    osc.stop(stopAt + 0.01);
                    activeNodes.push({ osc, gain });
                    t += dur;
                });

                return t;
            }

            const startAt = ctx.currentTime + 0.08;
            const endLeadA = scheduleVoice(lead, 'triangle', 0.085, startAt, -4);
            const endLeadB = scheduleVoice(lead, 'sine', 0.04, startAt, 4);
            const endBass = scheduleVoice(bass, 'square', 0.03, startAt, 0);
            const songEndAt = Math.max(endLeadA, endLeadB, endBass);

            const msUntilDone = Math.max((songEndAt - ctx.currentTime) * 1000 + 200, 0);
            setTimeout(() => {
                if (activePlayback && activePlayback.stop === stopPlayback) {
                    stopPlayback();
                }
            }, msUntilDone);
        });
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    try:
        players_response = players_table.scan()
        players = players_response.get("Items", [])
        players = sorted(players, key=lambda x: (int(x["JerseyNumber"]), x["Name"]))

        schedule_response = schedule_table.scan()
        schedule = schedule_response.get("Items", [])
        schedule = sorted(schedule, key=lambda x: int(x["GameId"]))

        return render_template_string(HTML_TEMPLATE, players=players, schedule=schedule)
    except Exception as exc:
        return f"Error connecting to DynamoDB: {exc}", 500


@app.route("/nebraska_football.png")
def nebraska_football_image():
    return send_from_directory(".", "nebraska_football.png")


@app.route("/add", methods=["POST"])
def add_player():
    jersey = request.form.get("jersey")
    name = request.form.get("name")
    position = request.form.get("position")

    if jersey and name and position:
        players_table.put_item(
            Item={
                "JerseyNumber": int(jersey),
                "PlayerName": name,
                "Name": name,
                "Position": position,
            }
        )
    return redirect(url_for("index"))


@app.route("/delete", methods=["POST"])
def delete_player():
    jersey = request.form.get("jersey")
    name = request.form.get("name")
    if jersey and name:
        players_table.delete_item(Key={"JerseyNumber": int(jersey), "PlayerName": name})
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
