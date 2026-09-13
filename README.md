# 🌶️ Spice

**เว็บแอปสั่งรันโมเดล AI ที่ยืมการ์ดจอ Tesla T4 จาก Google Colab มาเป็นแรงประมวลผล**

ล็อกอินด้วยบัญชี Google ครั้งเดียว → เปิด Colab วางคำสั่งบรรทัดเดียว →
การ์ดจอของ Colab กลายเป็นเครื่องประมวลผลของคุณ พร้อมเชื่อม Google Drive
ด้วย `rclone` แบบไม่ต้องตั้งค่าเอง

```
เบราว์เซอร์ ──สั่งงาน──▶ เซิร์ฟเวอร์ Spice ──จ่ายงาน──▶ Colab T4 ──▶ Google Drive
     ▲                      (คิว + โทเคน)                  │            (rclone)
     └──────────── ผลลัพธ์สดผ่าน SSE ───────────────────────┘
```

---

## ✨ ความสามารถ

| | |
|---|---|
| 🔐 **ล็อกอิน Google** | OAuth 2.0 เต็มรูปแบบ เซสชันเก็บในคุกกี้ `httponly` โทเคนเข้ารหัสก่อนลงฐานข้อมูล จำกัดผู้ใช้ตามอีเมล/โดเมนได้ |
| ⚡ **ยืมการ์ดจอ** | จับคู่ Colab ด้วยรหัสใช้ครั้งเดียว เห็น VRAM และการใช้งาน GPU สด ๆ เชื่อมหลายเครื่องพร้อมกันได้ |
| 🗄️ **rclone อัตโนมัติ** | สร้าง `rclone.conf` จากสิทธิ์ที่อนุญาตไว้แล้ว เครื่อง Colab ดึงไปเมานต์ Drive ได้เอง |
| 🎛️ **หลายชนิดงาน** | โมเดลภาษา · สร้างภาพ · ถอดเสียง · ทำเวกเตอร์ พร้อมบอกว่าเครื่องที่มีรันไหวไหม |
| 🧠 **คลังความรู้ Vault** | เก็บเอกสารไว้ค้นแบบใกล้เคียง รองรับภาษาไทยที่ไม่เว้นวรรค ใช้ได้ทันทีแม้ยังไม่มี GPU |
| 📡 **อัปเดตสด** | ความคืบหน้า บันทึกการทำงาน และสถานะ GPU ส่งเข้าหน้าเว็บผ่าน SSE ไม่ต้องกดรีเฟรช |
| 🎨 **UI สองธีม** | ธีมมืด/สว่าง ใช้งานได้ตั้งแต่จอมือถือ 390px ถึงจอใหญ่ |

---

## 🚀 เริ่มใช้งานใน 5 นาที

### 1. ติดตั้งและรัน

```bash
git clone https://github.com/mataarranema-png/Spice.git
cd Spice
./run.sh                 # สร้าง venv ติดตั้งไลบรารี แล้วเปิดเซิร์ฟเวอร์ให้เอง
```

เปิด <http://localhost:8000> — ถ้ายังไม่ได้ตั้งค่า Google หน้าเว็บจะบอกให้ทราบ

### 2. ขอกุญแจ Google OAuth

1. เข้า [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
2. สร้างโปรเจกต์ (หรือเลือกโปรเจกต์เดิม) แล้วกด **Create credentials → OAuth client ID**
3. ถ้าถูกขอให้ตั้ง **OAuth consent screen** ก่อน: เลือก *External* → กรอกชื่อแอปกับอีเมล →
   ในหน้า *Scopes* ไม่ต้องเพิ่มอะไร → ในหน้า *Test users* **ใส่อีเมล Google ของคุณเอง**
4. กลับมาสร้าง OAuth client ID: เลือก **Web application**
5. ใน **Authorized redirect URIs** ใส่ให้ตรงเป๊ะ:
   ```
   http://localhost:8000/auth/google/callback
   ```
   (ถ้าใช้โดเมนจริง ให้ใส่ `https://โดเมนของคุณ/auth/google/callback` ด้วย)
6. ก๊อป **Client ID** กับ **Client secret** มาใส่ในไฟล์ `.env`

```bash
cp .env.example .env      # ถ้ายังไม่มี (run.sh สร้างให้อัตโนมัติ)
```

```ini
SPICE_SECRET_KEY=<ผลลัพธ์จาก: python3 -c "import secrets;print(secrets.token_urlsafe(48))">
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxx
SPICE_BASE_URL=http://localhost:8000
SPICE_ALLOWED_EMAILS=อีเมลของคุณ@gmail.com     # แนะนำ: กันคนอื่นเข้าใช้เครื่องคุณ
```

รีสตาร์ตเซิร์ฟเวอร์ แล้วกด **เข้าสู่ระบบด้วย Google**

> 💡 **สำคัญ:** ตอนล็อกอิน Google จะขอสิทธิ์ Drive ด้วย — ต้องกด *อนุญาต*
> เพราะสิทธิ์นี้คือสิ่งที่ใช้สร้าง `rclone.conf` ให้อัตโนมัติ

### 3. ยืมการ์ดจอจาก Colab

1. ในเว็บ ไปที่ **เครื่อง GPU → + เชื่อมเครื่องใหม่** → จะได้รหัสจับคู่ 8 ตัว
2. เปิด [Google Colab](https://colab.research.google.com) → **Runtime → Change runtime type → T4 GPU**
3. ก๊อปคำสั่งบรรทัดเดียวจากหน้าเว็บไปวางในเซลล์ แล้วกดรัน
4. รอราว 10 วินาที เครื่องจะขึ้นสถานะ **ออนไลน์** ในหน้าเว็บเอง

หรือใช้โน้ตบุ๊กสำเร็จรูป: [`colab/Spice_GPU_Bridge.ipynb`](colab/Spice_GPU_Bridge.ipynb)
(อัปโหลดขึ้น Colab แล้วกรอกแค่ 2 ช่อง)

### 4. สั่งงานได้เลย

ไปที่ **สั่งงาน AI** → เลือกโมเดล → พิมพ์คำสั่ง → กดรัน

---

## 🌐 ให้ Colab เข้าถึงเซิร์ฟเวอร์ของคุณ

Colab อยู่บนอินเทอร์เน็ต จึงเรียก `localhost` ของคุณไม่ได้ เลือกทางใดทางหนึ่ง:

**ก. Cloudflare Tunnel (ฟรี ไม่ต้องเปิดพอร์ต)**
```bash
cloudflared tunnel --url http://localhost:8000
# จะได้ URL แบบ https://xxx.trycloudflare.com → เอาไปใส่ SPICE_BASE_URL
# แล้วเพิ่ม https://xxx.trycloudflare.com/auth/google/callback ใน Google Console
```

**ข. ngrok**
```bash
ngrok http 8000
```

**ค. เซิร์ฟเวอร์จริง** — วางหลัง nginx/Caddy พร้อม HTTPS แล้วตั้ง
`SPICE_BASE_URL=https://โดเมนของคุณ` (คุกกี้จะเปลี่ยนเป็นโหมด `secure` ให้เอง)

> ⚠️ ทุกครั้งที่ URL เปลี่ยน ต้องอัปเดตทั้ง `SPICE_BASE_URL` และ
> **Authorized redirect URIs** ใน Google Console ให้ตรงกัน

---

## 🗄️ rclone และ Google Drive ทำงานอย่างไร

Spice ไม่ได้ให้คุณรัน `rclone config` เอง แต่ใช้ refresh token ที่คุณอนุญาตไว้ตอนล็อกอิน
มาประกอบเป็นไฟล์ตั้งค่าให้ตรง ๆ:

```ini
[gdrive]
type = drive
client_id = <ของคุณ>
client_secret = <ของคุณ>
scope = drive
token = {"access_token":"…","refresh_token":"…","expiry":"…"}
```

- **หน้าเว็บ** — *Drive & rclone → ดาวน์โหลด rclone.conf* เอาไปใช้บนเครื่องไหนก็ได้
- **เครื่อง Colab** — ดึงไฟล์นี้เองผ่าน `GET /api/v1/worker/rclone` (ยืนยันตัวด้วย worker token)
  แล้วเมานต์ที่ `/content/gdrive` ให้อัตโนมัติ

เวลาสั่งงานจึงอ้างไฟล์ใน Drive ได้ตรง ๆ:

| ช่อง | ตัวอย่าง | ความหมาย |
|---|---|---|
| ไฟล์ต้นทาง | `gdrive:docs/รายงาน.txt` | อ่านไฟล์นี้เข้าไปเป็นบริบทให้โมเดล |
| โฟลเดอร์ปลายทาง | `gdrive:spice/outputs` | อัปโหลดผลลัพธ์กลับขึ้น Drive |

---

## 🧩 โมเดลที่รองรับ

| โมเดล | ชนิด | VRAM ที่ต้องใช้ | เหมาะกับ |
|---|---|---|---|
| Qwen2.5 7B Instruct | ข้อความ | ~14.6 GB (4bit) | งานทั่วไป เขียนโค้ด ไทย/อังกฤษ |
| Typhoon 2 3B | ข้อความ | ~6.8 GB | ภาษาไทยโดยเฉพาะ ตอบไว |
| Llama 3.2 3B Instruct | ข้อความ | ~6.8 GB | เบา ประหยัด VRAM |
| SDXL Turbo | รูปภาพ | ~8.8 GB | สร้างภาพจากข้อความใน 1–2 step |
| Whisper large-v3-turbo | เสียง | ~7.8 GB | ถอดเสียงไฟล์จาก Drive |
| BGE-M3 | เวกเตอร์ | ~3.9 GB | ทำ embedding เข้าคลัง Vault |

เพิ่มโมเดลเองได้ที่ [`server/catalog.py`](server/catalog.py) — เพิ่มรายการเดียว
แล้วหน้าเว็บกับตัวตรวจสอบงานจะรู้จักทันที

---

## 🔌 API หลัก

| Endpoint | ใช้ทำอะไร | ยืนยันตัวด้วย |
|---|---|---|
| `GET /auth/google/login` | เริ่มล็อกอิน Google | – |
| `GET /api/v1/me` | ข้อมูลบัญชีตัวเอง | คุกกี้เซสชัน |
| `POST /api/v1/workers/pair` | ขอรหัสจับคู่เครื่อง | คุกกี้เซสชัน |
| `GET /api/v1/workers` | รายชื่อเครื่องและ telemetry | คุกกี้เซสชัน |
| `POST /api/v1/jobs` | ส่งงานเข้าคิว | คุกกี้เซสชัน |
| `GET /api/v1/stream` | อัปเดตสด (SSE) | คุกกี้เซสชัน |
| `GET /api/v1/drive/rclone.conf` | โหลดไฟล์ตั้งค่า rclone | คุกกี้เซสชัน |
| `POST /api/v1/worker/register` | เครื่องขอเข้าร่วมด้วยรหัสจับคู่ | รหัสจับคู่ |
| `POST /api/v1/worker/lease` | เครื่องขอรับงานถัดไป | worker token |
| `POST /api/v1/worker/jobs/{id}/complete` | เครื่องส่งผลลัพธ์กลับ | worker token |

เอกสารเต็มพร้อมลองยิงจริงที่ **`/docs`** (สร้างอัตโนมัติโดย FastAPI)

---

## 🔒 ความปลอดภัย

- โทเคน Google **เข้ารหัสด้วย Fernet** ก่อนเก็บ (กุญแจมาจาก `SPICE_SECRET_KEY`)
- worker token เก็บเป็น **SHA-256 hash** เท่านั้น ของจริงแสดงครั้งเดียวตอนจับคู่
- รหัสจับคู่ **ใช้ได้ครั้งเดียว อายุ 15 นาที**
- `state` ของ OAuth เซ็นด้วย HMAC พร้อมเวลาหมดอายุ — กัน CSRF
- คุกกี้เซสชันเป็น `httponly` + `samesite=lax` และเป็น `secure` เองเมื่อใช้ HTTPS
- ทุกคิวรีกรองด้วย `user_id` — ผู้ใช้คนหนึ่งมองไม่เห็นงาน เครื่อง หรือเอกสารของอีกคน
- ตั้ง `SPICE_ALLOWED_EMAILS` หรือ `SPICE_ALLOWED_DOMAINS` เพื่อปิดไม่ให้คนนอกล็อกอิน

> ⚠️ เครื่อง worker ที่จับคู่แล้ว **เข้าถึง Google Drive ของคุณได้** ผ่าน rclone
> ให้เชื่อมเฉพาะเครื่องที่คุณควบคุมเอง และกด “ถอดเครื่อง” เมื่อเลิกใช้

---

## 🧪 ทดสอบ

```bash
.venv/bin/python -m pytest tests/ -q         # 48 เทสต์
```

อยากดูระบบทำงานครบวงจรโดยไม่ต้องมี GPU:

```bash
SPICE_DEV_LOGIN=1 ./run.sh                   # เปิดปุ่ม "เข้าใช้แบบเดโม"
# อีกเทอร์มินัลหนึ่ง — ใช้รหัสจับคู่จากหน้าเว็บ
.venv/bin/python scripts/simulate_worker.py --server http://localhost:8000 --pair XXXX-XXXX
```

เครื่องจำลองจะแกล้งเป็น Tesla T4 รับงานจากคิวแล้วตอบกลับ เห็นครบทั้งคิวงาน
ความคืบหน้า บันทึก และ telemetry

---

## 📁 โครงสร้างโปรเจกต์

```
server/               เซิร์ฟเวอร์ FastAPI
  ├── main.py         ประกอบแอป เสิร์ฟหน้าเว็บ และสคริปต์ bootstrap
  ├── config.py       อ่านค่าตั้งจาก .env
  ├── db.py           สคีมาและตัวช่วย SQLite
  ├── auth.py         OAuth ของ Google + ตรวจสิทธิ์
  ├── security.py     เซสชัน JWT, เข้ารหัสโทเคน, แฮช worker token
  ├── events.py       บัสเหตุการณ์สำหรับ SSE
  ├── vault.py        คลังความรู้และการค้นด้วย cosine
  ├── catalog.py      รายการโมเดลที่รองรับ
  └── routers/        auth · workers · jobs · drive · vault
web/                  หน้าเว็บ (ไม่มีขั้นตอน build ไม่พึ่ง framework)
colab/                ตัวแทนเครื่อง + โน้ตบุ๊กสำหรับ Colab
scripts/              เครื่องจำลองสำหรับทดสอบ
tests/                ชุดทดสอบ pytest
```

ข้อมูลทั้งหมดอยู่ในไฟล์เดียวที่ `data/spice.db` — สำรองข้อมูลก็แค่ก๊อปไฟล์นี้

---

## ⚙️ ค่าตั้งทั้งหมด

| ตัวแปร | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `SPICE_SECRET_KEY` | สุ่มใหม่ทุกครั้ง | กุญแจเซ็นเซสชันและเข้ารหัสโทเคน — **ต้องตั้งเอง** ไม่งั้นเซสชันหลุดทุกครั้งที่รีสตาร์ต |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | – | กุญแจจาก Google Cloud Console |
| `SPICE_BASE_URL` | `http://localhost:8000` | URL ที่เข้าถึงได้จากภายนอก ต้องตรงกับที่ตั้งใน Google |
| `SPICE_ALLOWED_EMAILS` | ว่าง (ทุกคน) | รายชื่ออีเมลที่อนุญาต คั่นด้วย comma |
| `SPICE_ALLOWED_DOMAINS` | ว่าง (ทุกคน) | โดเมนที่อนุญาต เช่น `mycompany.com` |
| `SPICE_DB_PATH` | `./data/spice.db` | ที่เก็บฐานข้อมูล |
| `SPICE_DEV_LOGIN` | `0` | `1` = เปิดปุ่มเข้าใช้แบบเดโม (ห้ามเปิดบน production) |

---

## ❓ คำถามที่พบบ่อย

**เครื่องขึ้นออฟไลน์ทั้งที่เซลล์ Colab ยังรันอยู่**
เซิร์ฟเวอร์เข้าถึงจากอินเทอร์เน็ตไม่ได้ หรือ Colab ตัดการเชื่อมต่อไปแล้ว —
ดูหัวข้อ *ให้ Colab เข้าถึงเซิร์ฟเวอร์ของคุณ*

**งานค้างที่ “รอคิว” ไม่ไปไหน**
ยังไม่มีเครื่องออนไลน์ หรือโมเดลที่เลือกต้องการ VRAM มากกว่าที่เครื่องมี
หน้าเลือกโมเดลจะบอกว่าอันไหน “รันได้เลย”

**Colab ตัดการเชื่อมต่อกลางคัน งานที่ค้างหายไหม**
ไม่หาย — งานที่ไม่มีความคืบหน้าเกิน 15 นาทีจะถูกโยนกลับเข้าคิวให้เครื่องอื่นทำต่อ

**ใช้การ์ดจอของเครื่องตัวเองแทน Colab ได้ไหม**
ได้ `spice_worker.py` เป็นสคริปต์ Python ธรรมดา รันบนเครื่องไหนที่มี NVIDIA GPU ก็ได้:
```bash
python colab/spice_worker.py --server https://... --pair XXXX-XXXX
```

**โหลดโมเดลครั้งแรกนานมาก**
ต้องดาวน์โหลดน้ำหนักโมเดลก่อน (หลาย GB) รอบถัดไปจะเร็วขึ้นมากเพราะค้างอยู่ใน
หน่วยความจำของเครื่องแล้ว

---

## 📄 สัญญาอนุญาต

MIT
