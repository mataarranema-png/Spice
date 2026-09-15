import { chromium } from 'playwright';

const SHOT = '/tmp/claude-0/-home-user-Spice/e69b79fc-9586-549c-9723-5a73692648cb/scratchpad';
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message));

await page.goto('http://localhost:4173/', { waitUntil: 'networkidle' });
await page.waitForTimeout(600);

console.log('หัวข้อ:', await page.title());
console.log('บทเรียนแรก:', (await page.locator('.lesson-hero h2').textContent())?.trim());

// 1) รันโค้ดบทแรก (MsgBox)
await page.getByRole('button', { name: /รันโค้ด/ }).click();
await page.waitForSelector('.msgbox', { timeout: 5000 });
console.log('MsgBox เด้ง:', (await page.locator('.msgbox-body').textContent())?.trim());
await page.locator('.msgbox-btn', { hasText: 'ตกลง' }).click();
await page.waitForTimeout(700);
const toast1 = await page.locator('.win-toast').textContent().catch(() => null);
console.log('ผลบท 1:', toast1?.trim() ?? 'ไม่มี toast');
console.log('XP:', (await page.locator('.xp-label').textContent())?.trim());
await page.screenshot({ path: `${SHOT}/shot-lesson1.png` });

// 2) ไปบทที่ 2 แล้วใส่เฉลย รัน ตรวจผลในกริด
await page.getByRole('button', { name: /บทถัดไป/ }).click();
await page.waitForTimeout(500);
console.log('บทที่ 2:', (await page.locator('.lesson-hero h2').textContent())?.trim());
await page.getByRole('button', { name: /ดูเฉลย/ }).click();
await page.getByRole('button', { name: /รันโค้ด/ }).click();
await page.waitForTimeout(900);
const a1 = await page.locator('table.sheet tbody tr').nth(0).locator('td').nth(1).textContent();
const a3 = await page.locator('table.sheet tbody tr').nth(2).locator('td').nth(1).textContent();
console.log('กริด A1:', a1?.trim(), '| A3:', a3?.trim());
const passed = await page.locator('.task.pass').count();
const total = await page.locator('.task').count();
console.log(`ภารกิจผ่าน ${passed}/${total}`);

// 3) ทดสอบบทที่มีการจัดรูปแบบ (ด่าน 5 บทแรก) — เช็กสีพื้นหลัง
await page.locator('.level-head', { hasText: 'บังคับ Excel ตัวจริง' }).click();
await page.waitForTimeout(300);
await page.locator('.lesson-item', { hasText: 'แต่งหน้าทาปากให้เซลล์' }).click();
await page.waitForTimeout(400);
await page.getByRole('button', { name: /ดูเฉลย/ }).click();
await page.getByRole('button', { name: /รันโค้ด/ }).click();
await page.waitForTimeout(900);
const headerBg = await page.locator('table.sheet tbody tr').nth(0).locator('td').nth(1).evaluate((el) => getComputedStyle(el).backgroundColor);
const headerWeight = await page.locator('table.sheet tbody tr').nth(0).locator('td').nth(1).locator('.cell').evaluate((el) => getComputedStyle(el).fontWeight);
console.log('สีพื้นหัวตาราง:', headerBg, '| น้ำหนักฟอนต์:', headerWeight);
console.log('ภารกิจด่าน 5:', await page.locator('.task.pass').count(), '/', await page.locator('.task').count());
await page.screenshot({ path: `${SHOT}/shot-format.png` });

// 4) ทดสอบโปรเจกต์จบ (ด่าน 6 บทสุดท้าย)
await page.locator('.level-head', { hasText: 'ระดับมือโปร' }).click();
await page.waitForTimeout(300);
await page.locator('.lesson-item', { hasText: 'Dashboard' }).click();
await page.waitForTimeout(400);
await page.getByRole('button', { name: /ดูเฉลย/ }).click();
await page.getByRole('button', { name: /รันโค้ด/ }).click();
await page.waitForTimeout(1200);
console.log('ภารกิจ Dashboard:', await page.locator('.task.pass').count(), '/', await page.locator('.task').count());
await page.screenshot({ path: `${SHOT}/shot-dashboard.png`, fullPage: false });

// 5) ทดสอบโค้ดที่ผิด → ต้องขึ้น error พร้อมเลขบรรทัด
await page.locator('.editor-area textarea').fill('Sub Test()\n  Range("A1").Valu = 5\nEnd Sub');
await page.getByRole('button', { name: /รันโค้ด/ }).click();
await page.waitForTimeout(700);
console.log('ข้อความ error:', (await page.locator('.console .line-err').first().textContent())?.trim());

// 6) มือถือ
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(500);
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
console.log('ล้นแนวนอนบนมือถือ (px):', overflow);
await page.screenshot({ path: `${SHOT}/shot-mobile.png`, fullPage: false });

console.log('\nError ใน console:', errors.length ? errors : 'ไม่มี');
await browser.close();
