import requests
import json
import time
import os
import datetime
from urllib.parse import quote
from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ---------------- CONFIGURATION ----------------
# ตั้งค่า API Token และ Webhook URL ได้ที่นี่
OPENPROJECT_URL = "https://openproject.softdebut.com"
API_TOKEN = os.getenv("OP_API_TOKEN", "281b6e0ffc17cd92b812ef95f3d79f559274aadba480a8fadfda78317405bf1b")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1552228564601020416/DvjJb6ba2-EPJmXTi_pr6qgtQWWEh-uvMeLPh04mHACUjAtmKNn0ZwfnV8IQjUoDmoDI")

# ความถี่ในการเช็คข้อมูล (วินาที)
POLL_INTERVAL_SECONDS = 10 

# ชื่อไฟล์เก็บความจำ
STATE_FILE = "notified_tasks.json"
# -----------------------------------------------

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)

def check_discord_notifications():
    if not API_TOKEN or API_TOKEN == "YOUR_API_TOKEN_HERE":
        print("[ERROR] Please set OP_API_TOKEN environment variable or put it in the script.")
        return

    # Status 9 = Ready for internal test
    filters = '[{"status":{"operator":"=","values":["9"]}}]'
    sort_by = '[["updatedAt","desc"]]'
    
    api_url = f"{OPENPROJECT_URL}/api/v3/work_packages?filters={quote(filters)}&sortBy={quote(sort_by)}&pageSize=10"
    
    auth = requests.auth.HTTPBasicAuth('apikey', API_TOKEN)
    headers = {"Accept": "application/json"}
    
    try:
        res = requests.get(api_url, auth=auth, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
    except Exception as e:
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Failed to fetch from OpenProject API: {e}")
        return

    elements = data.get("_embedded", {}).get("elements", [])
    if not elements:
        return
        
    notified_tasks = load_state()
    updated = False
    
    for task in elements:
        task_id = str(task["id"])
        updated_at = task.get("updatedAt")
        
        if notified_tasks.get(task_id) != updated_at:
            notified_tasks[task_id] = updated_at
            updated = True
            
            task_time = datetime.datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            now_time = datetime.datetime.now(datetime.timezone.utc)
            
            diff_minutes = (now_time - task_time).total_seconds() / 60.0
            
            # ส่งแจ้งเตือนเฉพาะงานที่อัปเดตภายใน 5 นาทีที่ผ่านมา
            if diff_minutes <= 5:
                task_subject = task.get("subject", "")
                
                # --- หาผู้สร้าง (IS06 หรือ Author) ---
                author_title = ""
                custom_field_11 = task.get("customField11")
                links = task.get("_links", {})
                
                if custom_field_11 and isinstance(custom_field_11, str):
                    author_title = custom_field_11.lower()
                elif links.get("customField11", {}).get("title"):
                    author_title = links["customField11"]["title"].lower()
                    
                if not author_title or author_title == "-" or author_title == "no value":
                    if links.get("author", {}).get("title"):
                        author_title = links["author"]["title"].lower()
                        
                # --- จัดการ Discord Tag ---
                discord_tag = 'ทุกคน (All)'
                if 'moss' in author_title: discord_tag = '<@838278874692321334>'
                elif 'fern' in author_title: discord_tag = '<@1488462977421279292>'
                elif 'ging' in author_title: discord_tag = '<@814869031445725205>'
                elif 'nat' in author_title: discord_tag = '<@1488461803091656705>'
                elif 'chit' in author_title: discord_tag = '<@690134773481472017>'
                
                project_title = links.get("project", {}).get("title", "OpenProject")
                type_title = links.get("type", {}).get("title", "Task")
                
                task_url = f"{OPENPROJECT_URL}/work_packages/{task_id}/activity"
                
                embed = {
                    "title": f"[#{task_id}] {task_subject}",
                    "url": task_url,
                    "description": f"**{type_title}** เปลี่ยนสถานะเป็น **Ready for internal test** แล้ว\\n📌 **Project:** {project_title}\\n👤 **ผู้สร้างบัค:** {discord_tag}",
                    "color": 3066993,
                    "author": {
                        "name": "QA Companion Notifier",
                        "icon_url": "https://cdn-icons-png.flaticon.com/512/9424/9424846.png"
                    },
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                
                payload = {
                    "content": discord_tag,
                    "embeds": [embed]
                }
                
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Sending webhook for Task #{task_id}")
                try:
                    requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
                except Exception as e:
                    print(f"[ERROR] Webhook failed: {e}")
                    
                time.sleep(1) # ป้องกัน Rate limit ของ Discord

    # ลบ task เก่าออกจากเมมโมรี่ถ้ามันตกจาก 10 อันดับล่าสุดไปแล้ว
    current_ids = set(str(t["id"]) for t in elements)
    keys_to_delete = [k for k in notified_tasks.keys() if k not in current_ids]
    for k in keys_to_delete:
        del notified_tasks[k]
        updated = True
        
    if updated:
        save_state(notified_tasks)

if __name__ == "__main__":
    print("[BOT] Standalone Discord Notifier Bot is starting...")
    print(f"Polling interval: {POLL_INTERVAL_SECONDS} seconds")
    
    # Start the Flask web server in a background thread
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    while True:
        try:
            check_discord_notifications()
        except Exception as e:
            print(f"[FATAL ERROR] {e}")
        time.sleep(POLL_INTERVAL_SECONDS)
