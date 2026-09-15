from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import base64
import tempfile
import os
import sqlite3
import hashlib
import uuid
import urllib.request
import json
from groq import Groq

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect('chinese_app.db', timeout=10)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            status TEXT DEFAULT 'Pending',
            verify_token TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)
CHINESE_TOPIC_RULE = """Сен "Қытай тілі" платформасының ИИ-тьюторысың. Тек қытай тілі тақырыбында сөйле."""

# Сіздің Google Apps Script сілтемеңіз
GAS_URL = "https://script.google.com/macros/s/AKfycbyMSEjTeQwQnG2yZUbJjiL4sBJpQ1P5Op3yv2Q4yKF_qkVP9ZiqJ5nj3xaK6FBRVhJIGg/exec"

def send_verification_email(user_email: str, user_name: str, token: str, base_url: str):
    verify_link = f"{base_url}/verify?token={token}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin: 0; padding: 40px 20px; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #F4EEE0;">
        <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.05);">
            <tr>
                <td style="padding: 40px 40px 20px 40px; text-align: center; border-bottom: 2px solid #F4EEE0;">
                    <div style="display: inline-block; background-color: #A61B29; color: #ffffff; width: 48px; height: 48px; line-height: 48px; text-align: center; font-size: 24px; font-weight: bold; border-radius: 6px; margin-bottom: 15px;">汉</div>
                    <h1 style="margin: 0; color: #1B1B1F; font-size: 24px;">Қытай тілі</h1>
                </td>
            </tr>
            <tr>
                <td style="padding: 40px;">
                    <h2 style="margin-top: 0; color: #1B1B1F;">Сәлем, {user_name}!</h2>
                    <p style="color: #4B5563; font-size: 16px; line-height: 1.6;">Платформаға қош келдіңіз! Кабинетке кіру үшін поштаңызды растаңыз:</p>
                    <div style="text-align: center; margin-top: 25px; margin-bottom: 25px;">
                        <a href="{verify_link}" style="background-color: #A61B29; color: #ffffff; text-decoration: none; padding: 16px 32px; border-radius: 8px; font-weight: bold; display: inline-block;">Поштаны растау</a>
                    </div>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    payload = {
        "to": user_email,
        "subject": "Электронды поштаңызды растаңыз — Қытай тілі",
        "htmlBody": html_content
    }

    try:
        req = urllib.request.Request(
            GAS_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode())
            if res_data.get("status") == "success":
                return True, "Success"
            else:
                return False, res_data.get("message", "Белгісіз қате")
    except Exception as e:
        return False, f"GAS қатесі: {str(e)}"

@app.get("/verify")
def verify_email(token: str):
    conn = sqlite3.connect('chinese_app.db', timeout=10)
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM users WHERE verify_token = ?', (token,))
        user = cursor.fetchone()
        
        frontend_url = "https://aminakabdyrakym.github.io/chinese/index.html"
        
        if user:
            cursor.execute('UPDATE users SET status = "Verified" WHERE verify_token = ?', (token,))
            conn.commit()
            return RedirectResponse(url=f"{frontend_url}?verified=true")
        else:
            return RedirectResponse(url=f"{frontend_url}?verified=false")
    finally:
        conn.close()

@app.post("/api")
async def handle_post(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        action = data.get("action")

        # 1. ТІРКЕЛУ
        if action == 'register':
            name = data.get("name")
            email = data.get("email")
            password = data.get("password")
            
            hashed_pw = hashlib.sha256(password.encode()).hexdigest()
            token = str(uuid.uuid4())

            role = 'teacher' if name == 'Bulanay Yerkin' else 'student'
            status = 'Verified' if name == 'Bulanay Yerkin' else 'Pending'

            conn = sqlite3.connect('chinese_app.db', timeout=10)
            try:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO users (name, email, password, role, status, verify_token) VALUES (?, ?, ?, ?, ?, ?)', 
                               (name, email, hashed_pw, role, status, token))
                conn.commit()
                
                if role != 'teacher':
                    base_url = "https://chinese-backend-yurc.onrender.com"
                    
                    # Хаттың сәтті жіберілгенін тексереміз
                    is_sent, error_message = send_verification_email(email, name, token, base_url)
                    
                    if not is_sent:
                        # Егер хат кетпесе, базадан өшіріп тастаймыз (қайта тіркелуге мүмкіндік беру үшін)
                        cursor.execute('DELETE FROM users WHERE email = ?', (email,))
                        conn.commit()
                        return {"status": "error", "message": f"Пошта жіберу қатесі: {error_message}"}
                
                return {"status": "success", "message": "Тіркелу сәтті аяқталды! Поштаңызды тексеріңіз."}
            except sqlite3.IntegrityError:
                return {"status": "error", "message": "Бұл email бұрын тіркелген!"}
            finally:
                conn.close()

        # 2. КІРУ
        elif action == 'login':
            identifier = data.get("identifier")
            password = data.get("password")
            hashed_pw = hashlib.sha256(password.encode()).hexdigest()

            conn = sqlite3.connect('chinese_app.db', timeout=10)
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT name, role, status FROM users WHERE (email = ? OR name = ?) AND password = ?', 
                               (identifier, identifier, hashed_pw))
                user = cursor.fetchone()
            finally:
                conn.close()

            if user:
                if user[2] != 'Verified' and user[1] != 'teacher':
                    return {"status": "error", "message": "Почта расталмаған! Поштаңызды тексеріңіз."}
                return {"status": "success", "name": user[0], "role": user[1]}
            else:
                return {"status": "error", "message": "Email немесе құпия сөз қате!"}

        # 3. АДМИНГЕ ОҚУШЫЛАРДЫ ТІЗІП БЕРУ
        elif action == 'get_users':
            conn = sqlite3.connect('chinese_app.db', timeout=10)
            try:
                cursor = conn.cursor()
                cursor.execute('SELECT name, email, status, role FROM users')
                rows = cursor.fetchall()
                users_list = [{"name": r[0], "email": r[1], "status": r[2], "role": r[3]} for r in rows]
                return {"status": "success", "users": users_list}
            finally:
                conn.close()

        # 4. ИИ ТУТОР
        elif action == 'ai_tutor':
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": CHINESE_TOPIC_RULE}, {"role": "user", "content": data.get("message", "")}],
                model="openai/gpt-oss-20b", 
            )
            return {"status": "success", "reply": chat_completion.choices[0].message.content}

        elif action in ['evaluate_tone', 'ai_tutor_voice']:
            audio_bytes = base64.b64decode(data.get("audioBase64", "").split(",")[-1])
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_path = temp_audio.name

            with open(temp_path, "rb") as file:
                transcription = client.audio.transcriptions.create(file=(os.path.basename(temp_path), file.read()), model="whisper-large-v3-turbo")
            os.remove(temp_path)
            
            prompt = f'Оқушы мынаны айтты: "{transcription.text}". Тоны дұрыс па?' if action == 'evaluate_tone' else f"Оқушы былай деді: {transcription.text}. Қысқа жауап бер."
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": CHINESE_TOPIC_RULE}, {"role": "user", "content": prompt}],
                model="openai/gpt-oss-20b",
            )
            return {"status": "success", "reply": chat_completion.choices[0].message.content}

        return {"status": "error", "message": "Белгісіз әрекет"}

    except Exception as e:
        return {"status": "error", "message": str(e)}