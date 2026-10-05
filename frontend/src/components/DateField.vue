<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { L18N, MONTHS, WD_SHORT } from '../i18n.js'

/* Своё поле даты вместо <input type="date">. Причина (Ярослав 01.10.26: «когда на русском
   открываю календарь, там месяцы и другое на английском»): нативный календарь рисует БРАУЗЕР
   и подписывает его на языке браузера, а не приложения — повлиять на это нельзя.
   Поэтому календарь рисуем сами из словарей приложения.
   Наружу и внутрь — строка 'YYYY-MM-DD' (формат graph.json НЕ меняется), на экране 'ДД.ММ.ГГГГ'. */
const props = defineProps({
  model: { type: String, default: '' },
  lang: { type: String, default: 'ru' },
})
const emit = defineEmits(['change'])

const ru = computed(() => props.lang !== 'en')
const d = computed(() => L18N[ru.value ? 'ru' : 'en'])
const monthNames = computed(() => MONTHS[ru.value ? 'ru' : 'en'])
const weekDays = computed(() => WD_SHORT[ru.value ? 'ru' : 'en'])

const p2 = (n) => String(n).padStart(2, '0')
const iso = (dt) => `${dt.getFullYear()}-${p2(dt.getMonth() + 1)}-${p2(dt.getDate())}`
function toDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || ''))
  if (!m) return null
  const dt = new Date(+m[1], +m[2] - 1, +m[3])
  const ok = dt.getFullYear() === +m[1] && dt.getMonth() === +m[2] - 1 && dt.getDate() === +m[3]
  return ok ? dt : null
}
// На экране — короткий формат ДД.ММ.ГГ (просьба Ярослава 01.10.26: «сделай год двумя цифрами, а то
// не влезает»). В graph.json по-прежнему 'YYYY-MM-DD' — меняется только вид.
const show = (dt) => (dt ? `${p2(dt.getDate())}.${p2(dt.getMonth() + 1)}.${String(dt.getFullYear()).slice(-2)}` : '')
const text = computed(() => show(toDate(props.model)))
const today = new Date()
const todayIso = iso(today)

const open = ref(false)
const view = ref({ y: today.getFullYear(), m: today.getMonth() })
const box = ref({ left: 0, top: 0 })
const fieldEl = ref(null)
const popEl = ref(null)

// Разбор ручного ввода: «5.10.26», «05.10.2026», «5.10», «05102026», «5 10 26».
// Возвращает 'YYYY-MM-DD', '' для пустого поля и null, если разобрать не удалось
// (тогда оставляем прежнее значение — как с полем времени).
function parseTyped(s) {
  const raw = String(s || '').trim()
  if (!raw) return ''
  const parts = raw.split(/[^\d]+/).filter(Boolean)
  let dd, mm, yy
  if (parts.length >= 3) { dd = +parts[0]; mm = +parts[1]; yy = +parts[2] }
  else if (parts.length === 2) { dd = +parts[0]; mm = +parts[1] }
  else if (parts[0] && parts[0].length >= 6) { const v = parts[0]; dd = +v.slice(0, 2); mm = +v.slice(2, 4); yy = +v.slice(4) }
  else if (parts[0] && parts[0].length === 4) { dd = +parts[0].slice(0, 2); mm = +parts[0].slice(2, 4) }
  else return null
  if (yy === undefined || Number.isNaN(yy)) yy = today.getFullYear()
  if (yy < 100) yy += 2000
  if (!(dd >= 1 && dd <= 31 && mm >= 1 && mm <= 12)) return null
  const dt = new Date(yy, mm - 1, dd)
  if (dt.getDate() !== dd || dt.getMonth() !== mm - 1 || dt.getFullYear() !== yy) return null
  return iso(dt)
}
function onType(e) {
  const v = parseTyped(e.target.value)
  if (v === null) { e.target.value = text.value; return }   // мусор не портит прежнюю дату
  emit('change', v)
  e.target.value = show(toDate(v))
}

// 42 клетки: понедельник первым, дни соседних месяцев серые (сетка не «прыгает» по высоте).
const cells = computed(() => {
  const { y, m } = view.value
  const start = (new Date(y, m, 1).getDay() + 6) % 7
  const out = []
  for (let i = 0; i < 42; i++) {
    const dt = new Date(y, m, 1 - start + i)
    out.push({ iso: iso(dt), day: dt.getDate(), out: dt.getMonth() !== m || dt.getFullYear() !== y })
  }
  return out
})

function place() {
  const el = fieldEl.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const W = 234, H = 274
  const left = Math.min(Math.max(4, r.left - 2), Math.max(4, window.innerWidth - W - 4))
  let top = r.bottom + 4
  if (top + H > window.innerHeight - 4) top = Math.max(4, r.top - H - 4)   // не влезло снизу — открываем вверх
  box.value = { left, top }
}
function onDocDown(e) {
  const f = fieldEl.value, pp = popEl.value
  if (f && f.contains(e.target)) return
  if (pp && pp.contains(e.target)) return
  close()
}
function onEsc(e) { if (e.key === 'Escape') close() }
function onReflow() { if (open.value) place() }
function openCal() {
  const dt = toDate(props.model)
  view.value = dt ? { y: dt.getFullYear(), m: dt.getMonth() } : { y: today.getFullYear(), m: today.getMonth() }
  open.value = true
  place()
  // pointerdown, а не mousedown: см. пояснение в App.vue (холст на pointer-событиях
  // гасит совместимые мышиные события, и mousedown до документа не доходит)
  document.addEventListener('pointerdown', onDocDown, true)
  document.addEventListener('keydown', onEsc, true)
  window.addEventListener('resize', onReflow, true)
  window.addEventListener('scroll', onReflow, true)
}
function close() {
  open.value = false
  document.removeEventListener('pointerdown', onDocDown, true)
  document.removeEventListener('keydown', onEsc, true)
  window.removeEventListener('resize', onReflow, true)
  window.removeEventListener('scroll', onReflow, true)
}
function toggle() { open.value ? close() : openCal() }
function pick(c) { emit('change', c.iso); close() }
function shift(n) {
  const dt = new Date(view.value.y, view.value.m + n, 1)
  view.value = { y: dt.getFullYear(), m: dt.getMonth() }
}
function goToday() { emit('change', todayIso); close() }
onBeforeUnmount(close)
</script>

<template>
  <div class="df" ref="fieldEl">
    <input
      class="inp date df-inp" type="text" inputmode="numeric" maxlength="8"
      :placeholder="ru ? 'ДД.ММ.ГГ' : 'DD.MM.YY'"
      :value="text" @change="onType" />
    <button class="df-btn" type="button" :title="ru ? 'Календарь' : 'Calendar'"
            @click="toggle"><span class="emo">📅</span></button>

    <!-- Телепорт в body: панель карточки — position: fixed с overflow-y: auto и backdrop-filter,
         внутри неё всплывающий календарь был бы обрезан. -->
    <Teleport to="body">
      <div v-if="open" class="df-pop" ref="popEl" :style="{ left: box.left + 'px', top: box.top + 'px' }">
        <div class="df-head">
          <button class="df-nav" type="button" @click="shift(-1)">‹</button>
          <div class="df-title">{{ monthNames[view.m] }} {{ view.y }}</div>
          <button class="df-nav" type="button" @click="shift(1)">›</button>
        </div>
        <div class="df-wd">
          <span v-for="w in weekDays" :key="w">{{ w }}</span>
        </div>
        <div class="df-grid">
          <button v-for="c in cells" :key="c.iso" type="button" class="df-day"
                  :class="{ out: c.out, sel: c.iso === model, now: c.iso === todayIso }"
                  @click="pick(c)">{{ c.day }}</button>
        </div>
        <div class="df-foot">
          <button class="df-today" type="button" @click="goToday">{{ d.today }}</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style>
/* Календарь рисуем сами — цвета из переменных темы, ничего своего. Классы с префиксом df-,
   чтобы не задеть чужие. Всплывашка — position: fixed и телепорт в body (см. шаблон). */
.df { display: flex; align-items: center; gap: 4px; width: 100%; }
.df-inp { flex: 1 1 auto; min-width: 0; height: 32px; box-sizing: border-box; }
/* Высота кнопки = высоте поля (32 px, см. правило .inspector .inp:not(.ta) в LiteInspector.vue),
   иначе поле даты было ниже соседнего «Статуса» (просьба Ярослава 01.10.26). */
.df-btn {
  flex: 0 0 auto; width: 22px; height: 32px; padding: 0; cursor: pointer; font-size: 11px;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border); border-radius: 6px;
}
.df-btn:hover { border-color: var(--accent); }
.df-pop {
  position: fixed; z-index: 45; width: 234px; padding: 8px;
  background: var(--panel-bg); color: var(--text);
  border: 1px solid var(--panel-border); border-radius: var(--radius);
  box-shadow: var(--panel-shadow); backdrop-filter: var(--panel-blur);
}
.df-head { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.df-title { flex: 1 1 auto; text-align: center; font-size: 12px; font-weight: 700; text-transform: capitalize; }
.df-nav {
  width: 22px; height: 22px; padding: 0; cursor: pointer; font-size: 13px; line-height: 1;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border); border-radius: 6px;
}
.df-nav:hover { border-color: var(--accent); }
.df-wd, .df-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; }
.df-wd span { text-align: center; font-size: 10px; color: var(--muted); padding-bottom: 2px; }
.df-day {
  height: 26px; padding: 0; cursor: pointer; font-family: inherit; font-size: 11.5px;
  background: transparent; color: var(--text); border: 1px solid transparent; border-radius: 5px;
}
.df-day:hover { background: var(--input-bg); border-color: var(--input-border); }
.df-day.out { color: var(--muted); opacity: .55; }
.df-day.now { border-color: var(--accent); }
.df-day.sel { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: var(--primary-text); font-weight: 700; }
.df-foot { margin-top: 6px; display: flex; justify-content: center; }
.df-today {
  cursor: pointer; font-family: inherit; font-size: 11px; padding: 3px 10px; border-radius: 6px;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border);
}
.df-today:hover { border-color: var(--accent); }
</style>
