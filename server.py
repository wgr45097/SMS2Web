#!/usr/bin/env python3

import sqlite3
import http.server
import socketserver
import datetime
import html
import os

DB_PATH = "/var/mobile/Library/SMS/sms.db"
PORT = 8000

MAC_EPOCH = datetime.datetime(2001, 1, 1)


def mac_time_to_datetime(mac_time):
    """
    Convert iOS nanosecond timestamp to datetime
    """
    try:
        ts = int(mac_time)
        if ts <= 0:
            return None
        ts_sec = ts / 1_000_000_000  # nanoseconds → seconds
        return MAC_EPOCH + datetime.timedelta(seconds=ts_sec)
    except:
        return None


def get_recent_messages(limit=10):
    """
    Return the most recent received messages (not from me)
    """
    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Ensure WAL mode
    cursor.execute("PRAGMA journal_mode=WAL;")

    query = """
    SELECT
        message.text,
        message.date,
        message.date_delivered,
        handle.id as sender
    FROM message
    LEFT JOIN handle ON message.handle_id = handle.ROWID
    WHERE message.is_from_me = 0
      AND message.text IS NOT NULL
    ORDER BY CASE WHEN message.date_delivered > 0 THEN message.date_delivered ELSE message.date END DESC
    LIMIT ?
    """
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        ts = row["date_delivered"] if row["date_delivered"] and row["date_delivered"] > 0 else row["date"]
        dt = mac_time_to_datetime(ts)
        messages.append({
            "sender": row["sender"] or "Unknown",
            "text": row["text"],
            "date": dt
        })
    return messages


class SMSHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        messages = get_recent_messages(10)

        html_content = """
        <html>
        <head>
            <title>Recent SMS Messages</title>
            <meta charset="utf-8">
            <style>
                body { font-family: sans-serif; margin: 40px; }
                .msg { margin-bottom: 20px; padding: 10px; border: 1px solid #ccc; }
                .sender { font-weight: bold; }
                .date { color: gray; font-size: 0.9em; }
                .text { margin-top: 5px; }
            </style>
        </head>
        <body>
        <h1>10 Most Recent Received SMS</h1>
        <p style="font-size:0.9em; color: gray;">
            Times are shown in your local timezone: <span id="local-tz">Loading...</span>
        </p>
        """

        for row in messages:
            date = row["date"]
            date_iso = date.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(date, datetime.datetime) else ""
            sender = html.escape(str(row["sender"]))
            text = html.escape(str(row["text"]))

            html_content += f"""
            <div class="msg">
                <div class="sender">From: {sender}</div>
                <div class="date" data-ts="{date_iso}">Received: {date_iso}</div>
                <div class="text">{text}</div>
            </div>
            """

        # JavaScript: set local timezone and convert timestamps
        html_content += """
        <script>
            // Display client local timezone in the header
            const tzName = Intl.DateTimeFormat().resolvedOptions().timeZone;
            document.getElementById('local-tz').textContent = tzName;

            // Convert each message timestamp to local time with abbreviation
            document.querySelectorAll('.date').forEach(function(el) {
                const ts = el.getAttribute('data-ts');
                if(ts) {
                    const dt = new Date(ts);
                    const options = { year: 'numeric', month: '2-digit', day: '2-digit',
                                      hour: '2-digit', minute: '2-digit', second: '2-digit',
                                      hour12: false, timeZoneName: 'short' };
                    el.textContent = 'Received: ' + dt.toLocaleString([], options);
                }
            });
        </script>
        """

        html_content += "</body></html>"

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))


if __name__ == "__main__":
    with socketserver.TCPServer(("0.0.0.0", PORT), SMSHandler) as httpd:
        print(f"Serving SMS page at http://0.0.0.0:{PORT}")
        httpd.serve_forever()
