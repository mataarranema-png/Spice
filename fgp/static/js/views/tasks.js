// กระจายงานให้หัวหน้าไลน์ และติดตามสถานะ
import { api, store } from '../api.js';
import { icon, esc, toast, modal, field, selectOptions, readForm, confirmDialog, thaiDate, relTime } from '../ui.js';

const PRIORITY = { 1: ['mute', 'ปกติ'], 2: ['info', 'สำคัญ'], 3: ['warn', 'เร่งด่วน'], 4: ['bad', 'วิกฤต'] };
const COLUMNS = [
  { key: 'open', label: 'รอเริ่ม', color: 'var(--text-3)' },
  { key: 'doing', label: 'กำลังทำ', color: 'var(--accent)' },
  { key: 'done', label: 'เสร็จแล้ว', color: 'var(--ok)' },
];

export default {
  title: 'กระจายงาน Leader',
  subtitle: 'มอบหมายงานให้หัวหน้าไลน์ ติดตามความคืบหน้าเป็นบอร์ดเดียว',
  autoRefresh: 60000,

  async render(root) {
    const { items } = await api.get('/api/tasks');
    const overdue = items.filter((t) => t.status !== 'done' && t.due_date && t.due_date < store.today);

    root.innerHTML = `
      <div class="card">
        <div class="card-head">
          <div><h3>บอร์ดงาน</h3><p>${items.length} งานทั้งหมด · เกินกำหนด ${overdue.length} งาน</p></div>
          <div class="right">
            ${overdue.length ? `<span class="badge bad">${icon('alert', 12)} เกินกำหนด ${overdue.length}</span>` : ''}
            ${store.can('leader') ? `<button class="btn primary sm" id="addBtn">${icon('plus', 15)} มอบหมายงาน</button>` : ''}
          </div>
        </div>
        <div class="grid g3">
          ${COLUMNS.map((col) => {
            const rows = items.filter((t) => t.status === col.key);
            return `<div>
              <div class="row mb" style="gap:8px">
                <span style="width:8px;height:8px;border-radius:50%;background:${col.color}"></span>
                <b style="font-size:13.5px">${col.label}</b>
                <span class="badge mute">${rows.length}</span>
              </div>
              <div class="stack">
                ${rows.map((t) => {
                  const late = t.status !== 'done' && t.due_date && t.due_date < store.today;
                  return `<div class="card flat" style="padding:14px;${late ? 'border-color:rgba(255,84,112,.4)' : ''}">
                    <div class="row" style="justify-content:space-between;align-items:flex-start">
                      <b style="font-size:13.5px;line-height:1.5">${esc(t.title)}</b>
                      <span class="badge ${PRIORITY[t.priority]?.[0] || 'mute'}">${PRIORITY[t.priority]?.[1] || ''}</span>
                    </div>
                    ${t.detail ? `<p class="t-sm t-mute" style="margin-top:6px;line-height:1.6">${esc(t.detail)}</p>` : ''}
                    <div class="chips mt">
                      ${t.line_code ? `<span class="chip">${esc(t.line_code)}</span>` : ''}
                      ${t.assignee_name ? `<span class="chip">${icon('people', 11)} ${esc(t.assignee_name)}</span>` : ''}
                      <span class="chip ${late ? 'on' : ''}" ${late ? 'style="color:var(--bad);border-color:var(--bad)"' : ''}>
                        ${icon('clock', 11)} ${thaiDate(t.due_date)}</span>
                    </div>
                    <div class="row mt" style="gap:6px">
                      ${t.status !== 'done' ? `
                        ${t.status === 'open' ? `<button class="btn sm" data-move="${t.id}:doing">เริ่มทำ</button>` : ''}
                        <button class="btn sm primary" data-move="${t.id}:done">${icon('check', 14)} เสร็จ</button>` :
                        `<span class="t-sm t-mute">${relTime(t.done_at)}</span>`}
                      <div style="flex:1"></div>
                      ${store.can('leader') ? `
                        <button class="btn icon ghost sm" data-edit="${t.id}">${icon('edit', 14)}</button>
                        <button class="btn icon ghost sm" data-del="${t.id}">${icon('trash', 14)}</button>` : ''}
                    </div>
                  </div>`;
                }).join('') || `<div class="t-sm t-mute" style="padding:14px;text-align:center;
                  border:1px dashed var(--line);border-radius:12px">ว่าง</div>`}
              </div>
            </div>`;
          }).join('')}
        </div>
      </div>`;

    const self = this;
    root.querySelector('#addBtn')?.addEventListener('click', () => self.taskModal(null, root));
    root.querySelectorAll('[data-move]').forEach((b) => {
      b.onclick = async () => {
        const [id, status] = b.dataset.move.split(':');
        await api.put(`/api/tasks/${id}`, { status });
        toast(status === 'done' ? 'ปิดงานแล้ว' : 'เริ่มงานแล้ว');
        self.render(root);
      };
    });
    root.querySelectorAll('[data-edit]').forEach((b) => {
      b.onclick = () => self.taskModal(items.find((t) => t.id === Number(b.dataset.edit)), root);
    });
    root.querySelectorAll('[data-del]').forEach((b) => {
      b.onclick = () => confirmDialog('ลบงานนี้หรือไม่', async () => {
        await api.del(`/api/tasks/${b.dataset.del}`);
        toast('ลบงานแล้ว');
        self.render(root);
      });
    });
  },

  taskModal(task, root) {
    const self = this;
    modal({
      title: task ? 'แก้ไขงาน' : 'มอบหมายงานใหม่',
      body: `<form id="taskForm" class="grid g2">
        <div style="grid-column:1/-1">${field('หัวข้องาน',
          `<input name="title" required value="${esc(task?.title || '')}" placeholder="เช่น ตรวจ jig ก่อนเริ่มกะ">`)}</div>
        <div style="grid-column:1/-1">${field('รายละเอียด',
          `<textarea name="detail" placeholder="สิ่งที่ต้องทำและเงื่อนไขความสำเร็จ">${esc(task?.detail || '')}</textarea>`)}</div>
        ${field('มอบหมายให้', `<select name="assignee_id"><option value="">ไม่ระบุ</option>
          ${selectOptions(store.leaders, 'id', (u) => u.name, task?.assignee_id)}</select>`)}
        ${field('ไลน์ที่เกี่ยวข้อง', `<select name="line_id"><option value="">ไม่ระบุ</option>
          ${selectOptions(store.lines, 'id', (l) => l.code, task?.line_id)}</select>`)}
        ${field('ความสำคัญ', `<select name="priority">${Object.entries(PRIORITY).map(([k, v]) =>
          `<option value="${k}" ${String(task?.priority || 2) === k ? 'selected' : ''}>${v[1]}</option>`).join('')}</select>`)}
        ${field('กำหนดเสร็จ', `<input name="due_date" type="date" value="${task?.due_date || store.today}">`)}
      </form>`,
      onMount(overlay, close) {
        overlay.querySelector('[data-ok]').onclick = async () => {
          const data = readForm(overlay.querySelector('#taskForm'));
          try {
            if (task) await api.put(`/api/tasks/${task.id}`, data);
            else await api.post('/api/tasks', data);
            close();
            toast(task ? 'แก้ไขงานแล้ว' : 'มอบหมายงานแล้ว');
            self.render(root);
          } catch (err) { toast(err.message, 'bad'); }
        };
      },
    });
  },
};
