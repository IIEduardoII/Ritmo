#!/usr/bin/env python3
import os, sys, time, json, sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

DATA = Path(os.path.expanduser('~/.local/share/ritmo'))
DB_PATH = DATA / 'ritmo.sqlite3'
VAPID_PRIV = DATA / 'vapid_private.pem'
TZ = ZoneInfo('America/Sao_Paulo')

def run_check():
    if not DB_PATH.exists() or not VAPID_PRIV.exists():
        return
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return

    now = datetime.now(TZ)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    today_str = now.strftime('%Y-%m-%d')
    c.execute("""
        SELECT id, routine_id, routine_name, scheduled_at, workout_id, notified_at
        FROM schedules
        WHERE workout_id IS NULL
          AND notified_at IS NULL
          AND scheduled_at LIKE ?
    """, (f"{today_str}%",))
    
    schedules = c.fetchall()
    due_schedules = []
    for s in schedules:
        try:
            sched_str = s['scheduled_at'].replace('T', ' ')[:19]
            sched_dt = datetime.strptime(sched_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
            diff_sec = (now - sched_dt).total_seconds()
            if -60 <= diff_sec <= 300:
                due_schedules.append(s)
        except Exception:
            pass

    if not due_schedules:
        conn.close()
        return

    c.execute("SELECT id, endpoint, p256dh, auth FROM push_subscriptions")
    subs = c.fetchall()
    if not subs:
        conn.close()
        return

    for sched in due_schedules:
        payload = json.dumps({
            "title": "Ritmo · Hora do Treino!",
            "body": f"Está na hora da sua rotina: {sched['routine_name']}",
            "tag": f"ritmo-treino-{sched['id']}",
            "url": "/#inicio"
        })
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub['endpoint'],
                        "keys": {"p256dh": sub['p256dh'], "auth": sub['auth']}
                    },
                    data=payload,
                    vapid_private_key=str(VAPID_PRIV),
                    vapid_claims={"sub": "mailto:ritmo@localhost"},
                    timeout=10
                )
            except WebPushException as ex:
                if ex.response and ex.response.status_code in (404, 410):
                    c.execute("DELETE FROM push_subscriptions WHERE id = ?", (sub['id'],))
            except Exception:
                pass
        
        c.execute("UPDATE schedules SET notified_at = ? WHERE id = ?", (now.strftime('%Y-%m-%d %H:%M:%S'), sched['id']))
        conn.commit()

    conn.close()

if __name__ == '__main__':
    while True:
        try:
            run_check()
        except Exception:
            pass
        time.sleep(30)
