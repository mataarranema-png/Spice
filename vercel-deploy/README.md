# วิธี deploy VBA Academy ขึ้น Vercel

## วิธีที่แนะนำ (เชื่อม repo ตรง ๆ)

1. ไปที่ https://vercel.com/new แล้วเลือก repository `mataarranema-png/Spice`
2. ตั้งค่า **Root Directory** = `vba-academy`
3. Framework จะถูกตรวจเป็น **Vite** อัตโนมัติ (Build `npm run build`, Output `dist`)
4. กด Deploy — จากนั้นทุกครั้งที่ push จะ deploy ให้เอง

> ถ้า Vercel มองไม่เห็น repo ให้กด "Adjust GitHub App Permissions" แล้วให้สิทธิ์ repo นี้

## วิธีสำรอง (build จาก GitHub โดยไม่ต้องเชื่อม repo)

โฟลเดอร์นี้คือโปรเจกต์เปล่าที่ดึงซอร์สจาก GitHub มา build ตอน deploy
ใช้ตอนที่ Vercel ยังไม่มีสิทธิ์เข้าถึง repo

ตั้งค่าโปรเจกต์บน Vercel เป็น:

- Framework Preset: **Other**
- Install Command: `echo skip-root-install`
- Build Command: `bash build.sh`
- Output Directory: `dist`
- (ไม่บังคับ) Environment Variable `APP_BRANCH` เพื่อเลือก branch ที่จะ build
