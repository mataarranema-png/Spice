// จองคิวกำลังคนเข้าไลน์ พร้อมตัวช่วยจัดคนอัตโนมัติ
import { api, store } from '../api.js';
import { icon, esc, nf, toast, modal, field, selectOptions, readForm, confirmDialog, thaiDate } from '../ui.js';

const STATUS = {
  pending: ['warn', 'รอจัดคน'],
  partial: ['info', 'จัดคนบางส่วน'],
  assigned: ['ok', 'จัดคนครบแล้ว'],
  rejected: ['mute', 'ยกเลิก'],
};

function levelBar(level) {
  return `<span class="lvl">${[1, 2, 3, 4].map((i) =>
    `<i class="${i <= level ? 'on' : ''}"></i>`).join('')}</span>`;
}

export default {
  title: 'จองคิวกำลังคน',
  subtitle: 'ขอคนเข้าไลน์ล่วงหน้า ระบบเลือกคนที่เหมาะที่สุดให้พร้อมเหตุผล',

  async render(root) {
    const { items } = await api.get('/api/bookings');
    const pending = items.filter((b) => b.status === 'pending' || b.status === 'partial');
    const needPeople = items.reduce((a, b) => a + Math.max(b.required_qty - b.filled, 0), 0);

    const byDate = new Map();
    items.forEach((b) => {
      if (!byDate.has(b.book_date)) byDate.set(b.book_date, []);
      byDate.get(b.book_date).push(b);
    });

    root.innerHTML = `
      <div class="grid g4">
        <div class="card kpi"><div class="label">${icon('booking', 15)} คิวทั้งหมด</div>
          <div class="value num">${items.length}</div><div class="sub">ตั้งแต่วันนี้เป็นต้นไป</div></div>
        <div class="card kpi"><div class="label">${icon('clock', 15)} รอจัดคน</div>
          <div class="value num" style="color:var(--warn)">${pending.length}</div>
          <div class="sub">ยังขาดอีก ${needPeople} คน</div></div>
        <div class="card kpi"><div class="label">${icon('check', 15)} จัดครบแล้ว</div>
          <div class="value num" style="color:var(--ok)">${items.filter((b) => b.status === 'assigned').length}</div>
          <div class="sub">พร้อมเข้าไลน์</div></div>
        <div class="card kpi accent"><div class="label">${icon('brain', 15)} ตัวช่วยอัจฉริยะ</div>
          <div class="value num" style="font-size:26px">พร้อม</div>
          <div class="sub">จัดคนตามทักษะ กะ และความเป็นธรรม</div>
          ${store.can('leader') ? `<button class="btn primary sm mt" id="autoAll" style="width:100%">
            ${icon('bolt', 15)} จัดคนให้ทุกคิวที่ค้าง</button>` : ''}</div>
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>คิวจองทั้งหมด</h3><p>เรียงตามวันที่และกะ</p></div>
          <div class="right">${store.can('leader')
            ? `<button class="btn primary sm" id="addBtn">${icon('plus', 15)} เปิดคิวจองใหม่</button>` : ''}</div>
        </div>
        ${items.length ? [...byDate.entries()].map(([date, rows]) => `
          <div class="mb">
            <div class="row mb" style="gap:10px">
              <b style="font-size:13.5px">${thaiDate(date)}</b>
              <span class="badge mute">${rows.length} คิว</span>
              ${date === store.today ? '<span class="badge info">วันนี้</span>' : ''}
            </div>
            <div class="grid g2">
              ${rows.map((b) => `
                <div class="card flat" style="padding:16px">
                  <div class="row" style="justify-content:space-between;align-items:flex-start">
                    <div>
                      <b style="font-size:14.5px">${esc(b.line_code)} · กะ ${esc(b.shift)}</b>
                      <div class="t-sm t-mute" style="margin-top:3px">${esc(b.reason || 'ไม่ระบุเหตุผล')}</div>
                      <div class="t-sm t-mute">ขอโดย ${esc(b.requester || '-')}</div>
                    </div>
                    <span class="badge ${STATUS[b.status]?.[0] || 'mute'}">
                      <span class="dot"></span>${STATUS[b.status]?.[1] || b.status}</span>
                  </div>

                  <div class="row mt" style="gap:14px">
                    <div><span class="t-sm t-mute">ต้องการ</span>
                      <b class="mono" style="font-size:17px;margin-left:6px">${b.filled}/${b.required_qty}</b>
                      <span class="t-sm t-mute">คน</span></div>
                    <div><span class="t-sm t-mute">ทักษะขั้นต่ำ</span> ${levelBar(b.skill_min)}</div>
                  </div>
                  <div class="bar ${b.filled >= b.required_qty ? 'ok' : 'warn'}" style="margin-top:8px">
                    <i style="width:${Math.min(b.filled / b.required_qty * 100, 100)}%"></i></div>

                  <div class="chips mt">
                    ${b.assigned.map((a) => `<span class="chip on">${esc(a.name)}
                      <button class="btn ghost" data-unassign="${a.id}"
                        style="padding:0 0 0 5px;min-width:0;height:auto;color:inherit">✕</button></span>`).join('')
                      || '<span class="t-sm t-mute">ยังไม่มีคนในคิวนี้</span>'}
                  </div>

                  ${store.can('leader') ? `<div class="row mt">
                    <button class="btn primary sm" data-auto="${b.id}">${icon('brain', 14)} จัดคนอัตโนมัติ</button>
                    <button class="btn sm" data-pick="${b.id}">${icon('people', 14)} เลือกเอง</button>
                    <div style="flex:1"></div>
                    <button class="btn icon ghost sm" data-del="${b.id}" title="ลบคิว">${icon('trash', 15)}</button>
                  </div>` : ''}
                </div>`).join('')}
            </div>
          </div>`).join('')
        : `<div class="empty">${icon('booking', 42)}<b>ยังไม่มีคิวจอง</b>
           <div class="t-sm">เปิดคิวจองเมื่อไลน์ต้องการคนเพิ่ม</div></div>`}
      </div>`;

    const self = this;
    root.querySelector('#addBtn')?.addEventListener('click', () => self.bookingModal(root));
    root.querySelectorAll('[data-auto]').forEach((b) => {
      b.onclick = async () => {
        b.disabled = true;
        try {
          const res = await api.post(`/api/bookings/${b.dataset.auto}/auto`, {});
          toast(res.message, res.assigned.length ? 'ok' : 'bad');
          self.render(root);
        } catch (err) { toast(err.message, 'bad'); b.disabled = false; }
      };
    });
    root.querySelectorAll('[data-pick]').forEach((b) => {
      b.onclick = () => self.pickModal(Number(b.dataset.pick), root);
    });
    root.querySelectorAll('[data-unassign]').forEach((b) => {
      b.onclick = async () => {
        await api.del(`/api/assignments/${b.dataset.unassign}`);
        toast('เอาออกจากคิวแล้ว');
        self.render(root);
      };
    });
    root.querySelectorAll('[data-del]').forEach((b) => {
      b.onclick = () => confirmDialog('ลบคิวจองนี้หรือไม่', async () => {
        await api.del(`/api/bookings/${b.dataset.del}`);
        toast('ลบคิวแล้ว');
        self.render(root);
      });
    });
    root.querySelector('#autoAll')?.addEventListener('click', async (e) => {
      e.target.disabled = true;
      let total = 0;
      for (const b of pending) {
        try {
          const res = await api.post(`/api/bookings/${b.id}/auto`, {});
          total += res.assigned?.length || 0;
        } catch { /* ข้ามคิวที่จัดไม่ได้ */ }
      }
      toast(total ? `จัดคนอัตโนมัติได้ ${total} คน` : 'ไม่มีคนว่างที่ตรงเงื่อนไข', total ? 'ok' : 'bad');
      self.render(root);
    });
  },

  bookingModal(root) {
    const self = this;
    modal({
      title: 'เปิดคิวจองกำลังคน',
      subtitle: 'ระบุไลน์ วัน กะ และจำนวนคนที่ต้องการ',
      body: `<form id="bkForm" class="grid g2">
        ${field('วันที่', `<input name="book_date" type="date" value="${store.date}">`)}
        ${field('กะ', `<select name="shift"><option value="A">กะ A (เช้า)</option>
          <option value="B">กะ B (ดึก)</option></select>`)}
        ${field('ไลน์', `<select name="line_id">${selectOptions(store.lines, 'id',
          (l) => `${l.code} · ${l.name}`)}</select>`)}
        ${field('จำนวนคน', '<input name="required_qty" type="number" min="1" value="2">')}
        ${field('ทักษะขั้นต่ำ', `<select name="skill_min">
          <option value="1">ระดับ 1 · ฝึกงาน</option>
          <option value="2" selected>ระดับ 2 · ทำงานได้เอง</option>
          <option value="3">ระดับ 3 · ชำนาญ</option>
          <option value="4">ระดับ 4 · สอนคนอื่นได้</option></select>`)}
        ${field('เหตุผล', '<input name="reason" placeholder="เช่น เร่งยอดส่งลูกค้า">')}
      </form>`,
      onMount(overlay, close) {
        overlay.querySelector('[data-ok]').onclick = async () => {
          try {
            await api.post('/api/bookings', readForm(overlay.querySelector('#bkForm')));
            close();
            toast('เปิดคิวจองแล้ว');
            self.render(root);
          } catch (err) { toast(err.message, 'bad'); }
        };
      },
    });
  },

  async pickModal(bookingId, root) {
    const self = this;
    const { items } = await api.get(`/api/bookings/${bookingId}/suggest`);
    modal({
      title: 'เลือกคนเข้าคิว',
      subtitle: 'เรียงตามคะแนนความเหมาะสมที่ระบบคำนวณให้',
      wide: true,
      footer: `<button class="btn" data-close>ปิด</button>`,
      body: items.length ? `<div class="stack">${items.map((p) => `
        <div class="person">
          <div class="avatar">${esc(p.name.slice(0, 2))}</div>
          <div style="min-width:0">
            <b>${esc(p.name)}</b>
            <span>${esc(p.emp_code)} · ${esc(p.position)} · กะ ${esc(p.shift)}</span>
            <div class="t-sm t-mute" style="margin-top:3px">${p.reasons.map(esc).join(' · ')}</div>
          </div>
          <div class="score">
            <b>${p.score}</b>
            <div class="t-sm t-mute">คะแนน</div>
          </div>
          <button class="btn primary sm" data-add="${p.employee_id}" style="margin-left:12px">
            ${icon('plus', 14)} เพิ่ม</button>
        </div>`).join('')}</div>`
        : `<div class="empty">${icon('people', 40)}<b>ไม่มีคนที่ว่างและมีทักษะตรงเงื่อนไข</b>
           <div class="t-sm">ลองลดระดับทักษะขั้นต่ำ หรือเลือกวันอื่น</div></div>`,
      onMount(overlay, close) {
        overlay.querySelectorAll('[data-add]').forEach((b) => {
          b.onclick = async () => {
            try {
              await api.post(`/api/bookings/${bookingId}/assign`, { employee_id: b.dataset.add });
              b.closest('.person').style.opacity = '.4';
              b.disabled = true;
              toast('เพิ่มเข้าคิวแล้ว');
              self.render(root);
            } catch (err) { toast(err.message, 'bad'); }
          };
        });
      },
    });
  },
};
