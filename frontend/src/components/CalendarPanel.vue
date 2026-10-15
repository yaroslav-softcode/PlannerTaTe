<script setup>
import { computed, ref } from 'vue'
import { L18N, MONTHS, WD_SHORT } from '../i18n.js'

/* Календарь — открывается кнопкой «📅 Календарь» в сайдбаре (просьба Ярослава 15.10.26).
   Показывает ДВА месяца сразу (текущий + следующий), стрелки листают, «Сегодня» возвращает.
   В дне — до восьми цветных плашек в цвет карточек: сетка на 4 колонки, полоска задачи
   = 2 колонки, кружок напоминания = 1 (Ярослав 15.10.26: «два кружка могут занимать одно
   место»; если плашек больше — счётчик «+N»);
   наведение на плашку — увеличенная настоящая
   карточка (картинку готовит App.vue: renderCardImage, offscreen LiteGraph); клик по дню —
   вертикальный список карточек этого дня в полный размер. Клик по карточке списка — показать
   её на поле (reveal). В календарь идут задачи и напоминания с заполненным сроком (due) —
   напоминания узкой карточкой «под время»; строки приходят готовыми из App.vue (buildCalendarRows). */
const props = defineProps({
  lang: { type: String, default: 'ru' },
  rows: { type: Array, default: () => [] },   // {id, due, color, w, h, img}
})
const emit = defineEmits(['close', 'reveal'])

const loc = computed(() => (props.lang === 'en' ? 'en' : 'ru'))
function t(k) {
  const d = L18N[loc.value]
  return d[k] || k
}

// Прозрачная рамка вокруг карточки в картинке (должна совпадать с CARD_PAD в App.vue):
// картинку показываем с этим запасом, чтобы свечение темы не обрезалось.
const IMG_PAD = 16

const now = new Date()
function isoOf(y, m, d) { return `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}` }
const todayIso = isoOf(now.getFullYear(), now.getMonth(), now.getDate())

// Первый из двух показываемых месяцев.
const base = ref({ y: now.getFullYear(), m: now.getMonth() })
function shift(delta) {
  const d = new Date(base.value.y, base.value.m + delta, 1)
  base.value = { y: d.getFullYear(), m: d.getMonth() }
}
function goToday() {
  base.value = { y: now.getFullYear(), m: now.getMonth() }
  day.value = ''
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1)

const months = computed(() => {
  const out = []
  for (let i = 0; i < 2; i++) {
    const d = new Date(base.value.y, base.value.m + i, 1)
    const y = d.getFullYear(), m = d.getMonth()
    const lead = (d.getDay() + 6) % 7                 // неделя с ПОНЕДЕЛЬНИКА (WD_SHORT так же)
    const days = new Date(y, m + 1, 0).getDate()
    const cells = []
    for (let k = 0; k < lead; k++) cells.push(null)
    for (let dd = 1; dd <= days; dd++) cells.push({ iso: isoOf(y, m, dd), d: dd })
    // Сетка ВСЕГДА шесть рядов (Ярослав 15.10.26: «всегда шесть рядов, чтобы высота не гуляла»):
    // пустые хвосты до 42 ячеек.
    while (cells.length % 7) cells.push(null)
    while (cells.length < 42) cells.push(null)
    out.push({ label: `${cap(MONTHS[loc.value][m])} ${y}`, cells })
  }
  return out
})

// Группировка карточек по дате срока.
const byDay = computed(() => {
  const m = new Map()
  for (const r of props.rows) {
    let a = m.get(r.due)
    if (!a) { a = []; m.set(r.due, a) }
    a.push(r)
  }
  return m
})
const day = ref('')                                  // '' — режим месяцев, иначе iso-дата дня
function openDay(iso) {
  if (!byDay.value.has(iso)) return
  // Гасим увеличную плашку: клик по дню часто приходится по плашке, её mouseleave при
  // перерисовке не выстрелит — и призрак карточки наехал бы на список дня (замер 15.10.26).
  hover.value = null
  day.value = iso
}
const chips = (iso) => byDay.value.get(iso) || []   // пустые дни: [] а не undefined (иначе .slice падает)
// В ячейке дня восемь мест: 2×4 ряда. До восьми — все плашки; больше — семь и счётчик «+N»
// в восьмом месте, чтобы рядов всегда было четыре и высота ячейки не менялась.
const shownChips = (iso) => { const a = chips(iso); return a.length > 8 ? a.slice(0, 7) : a }

// Список дня: напоминание встаёт СПРАВА от карточки, к которой привязано связью
// (Ярослав 15.10.26: «просто размещать карточку и напоминания справа от неё», линий не рисуем).
const dayGroups = computed(() => {
  const list = chips(day.value)
  const rems = list.filter(r => r.notify)
  const used = new Set()
  const out = []
  for (const r of list) {
    if (r.notify) continue
    const kids = rems.filter(k => k.parent === r.id && !used.has(k.id))
    kids.forEach(k => used.add(k.id))
    out.push({ main: r, kids })
  }
  for (const k of rems) if (!used.has(k.id)) out.push({ main: k, kids: [] })   // висящие — отдельно
  return out
})

function dayLabel(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  return `${d} ${cap(MONTHS[loc.value][m - 1])} ${y}, ${WD_SHORT[loc.value][(dt.getDay() + 6) % 7]}`
}

// Увеличенная карточка при наведении на плашку: картинка уже отрендерена App.vue.
// Ставим справа от плашки, а если не влезает в окно — слева / выше.
const hover = ref(null)
function onChipEnter(ev, r) {
  const rc = ev.currentTarget.getBoundingClientRect()
  const pw = r.w + IMG_PAD * 2, ph = r.h + IMG_PAD * 2
  let x = rc.right + 8, y = rc.top - IMG_PAD
  if (x + pw > window.innerWidth - 6) x = rc.left - pw - 8
  if (x < 6) x = 6
  if (y + ph > window.innerHeight - 6) y = window.innerHeight - ph - 6
  if (y < 6) y = 6
  hover.value = { row: r, x, y }
}
</script>

<template>
  <div class="cal" :class="{ daymode: !!day }">
    <div class="cal-head">
      <div class="cal-title"><span class="emo">📅</span> {{ t('calTitle') }}</div>
      <template v-if="!day">
        <button class="cal-nav" title="‹" @click="shift(-1)">‹</button>
        <button class="cal-nav" title="›" @click="shift(1)">›</button>
        <button class="cal-today" @click="goToday">{{ t('calToday') }}</button>
      </template>
      <button class="cal-x" :title="t('close')" @click="emit('close')">✕</button>
    </div>

    <!-- Режим месяцев: два месяца рядом -->
    <div v-if="!day" class="cal-body">
      <div class="cal-hint">{{ t('calHint') }}</div>
      <div class="cal-months">
        <div v-for="(mo, mi) in months" :key="mi" class="cal-month">
          <div class="cal-mtitle">{{ mo.label }}</div>
          <div class="cal-wd"><span v-for="(w, wi) in WD_SHORT[loc]" :key="wi">{{ w }}</span></div>
          <div class="cal-grid">
            <div v-for="(cell, ci) in mo.cells" :key="ci" class="cal-cell"
                 :class="{ empty: !cell, today: cell && cell.iso === todayIso,
                          has: cell && byDay.has(cell.iso) }"
                 @click="cell && openDay(cell.iso)">
              <template v-if="cell">
                <div class="cal-date">{{ cell.d }}</div>
                <div class="cal-chips">
                  <i v-for="r in shownChips(cell.iso)" :key="r.id" class="cal-chip"
                     :class="{ rem: r.notify }"
                     :style="{ background: r.color || 'var(--muted)' }"
                     @mouseenter="onChipEnter($event, r)" @mouseleave="hover = null"
                     @click.stop="openDay(cell.iso)"></i>
                  <span v-if="chips(cell.iso).length > 8" class="cal-more">+{{ chips(cell.iso).length - 7 }}</span>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div v-if="!rows.length" class="cal-nodata">{{ t('calNoDue') }}</div>
    </div>

    <!-- Режим дня: все карточки дня вертикальным списком в полный размер (Ярослав 15.10.26) -->
    <div v-else class="cal-day">
      <div class="cal-daybar">
        <button class="cal-back" @click="day = ''">‹ {{ t('calBack') }}</button>
        <div class="cal-daytitle">{{ dayLabel(day) }}</div>
        <div class="cal-count">{{ chips(day).length }}</div>
      </div>
      <div v-if="!chips(day).length" class="cal-nodata">{{ t('calDayEmpty') }}</div>
      <div v-else class="cal-daylist">
        <div v-for="g in dayGroups" :key="g.main.id" class="cal-row">
          <img class="cal-card" :data-id="g.main.id" :src="g.main.img" :title="t('calReveal')"
               :style="{ width: (g.main.w + IMG_PAD * 2) + 'px', height: (g.main.h + IMG_PAD * 2) + 'px' }"
               @click="emit('reveal', g.main.id)" />
          <img v-for="r in g.kids" :key="r.id" class="cal-card" :data-id="r.id" :src="r.img" :title="t('calReveal')"
               :style="{ width: (r.w + IMG_PAD * 2) + 'px', height: (r.h + IMG_PAD * 2) + 'px' }"
               @click="emit('reveal', r.id)" />
        </div>
      </div>
    </div>

    <!-- Увеличная карточка при наведении на плашку -->
    <img v-if="hover" class="cal-preview" :src="hover.row.img"
         :style="{ left: hover.x + 'px', top: hover.y + 'px',
                   width: (hover.row.w + IMG_PAD * 2) + 'px', height: (hover.row.h + IMG_PAD * 2) + 'px' }" />
  </div>
</template>

<style>
/* Календарь — цвета только из переменных активной темы, как у остальных панелей.
   Позицию центра задаёт .cal-wrap (styles.css). */
.cal {
  width: 880px; max-width: calc(100vw - 32px); max-height: calc(100vh - 32px); overflow: auto;
  background: var(--panel-bg); color: var(--text); border: 1px solid var(--panel-border);
  border-radius: var(--radius); box-shadow: var(--panel-shadow); backdrop-filter: var(--panel-blur);
}
/* Режим дня: карточки идут столбцом, широкая модалка не нужна — вдвое уже (Ярослав 15.10.26) */
.cal.daymode { width: 440px; }
.cal-head {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  border-bottom: 1px solid var(--panel-border); position: sticky; top: 0; z-index: 2;
  background: var(--panel-bg);
}
.cal-title { font-size: 13.5px; font-weight: 700; }
.cal-nav {
  width: 26px; height: 26px; cursor: pointer; font-family: inherit; font-size: 15px; line-height: 1;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border); border-radius: 6px;
}
.cal-nav:hover { border-color: var(--accent); }
.cal-today {
  cursor: pointer; font-family: inherit; font-size: 11.5px; padding: 5px 10px; border-radius: 6px;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border);
}
.cal-today:hover { border-color: var(--accent); }
.cal-x {
  margin-left: auto; width: 22px; height: 22px; cursor: pointer; font-family: inherit; font-size: 12px;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border); border-radius: 6px;
}
.cal-x:hover { border-color: var(--accent); }
.cal-hint { padding: 8px 12px 0; font-size: 10.5px; color: var(--muted); }

.cal-months { display: flex; flex-wrap: wrap; gap: 16px; padding: 8px 12px 12px; }
.cal-month { flex: 1 1 390px; min-width: 280px; }
.cal-mtitle { font-size: 12.5px; font-weight: 700; margin: 6px 0; }
.cal-wd { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; margin-bottom: 3px; }
.cal-wd span { text-align: center; font-size: 10px; color: var(--muted); }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); grid-auto-rows: 76px; gap: 4px; } /* 6 рядов по 76px — высота не гуляет */
.cal-cell {
  padding: 3px 4px 4px; border: 1px solid var(--panel-border); border-radius: 6px;
}
.cal-cell.empty { opacity: .35; }
.cal-cell.has { cursor: pointer; }
.cal-cell.has:hover { border-color: var(--accent); }
.cal-cell.today { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.cal-date { font-size: 10.5px; line-height: 1; color: var(--muted); }
/* Плашки дня: сетка на 4 колонки — полоска задачи = 2 колонки, кружок напоминания = 1
   (Ярослав 15.10.26: «кружки маленькие, два кружка могут занимать одно место»:
   ряд = 2 полоски, или 4 кружка, или полоска + два кружка). */
.cal-chips { display: grid; grid-template-columns: repeat(4, 1fr); gap: 3px; margin-top: 3px; align-items: center; }
.cal-chip { display: block; height: 8px; border-radius: 3px; cursor: pointer; grid-column: span 2; }
.cal-chip:hover { filter: brightness(1.25); }
/* напоминание — кружок, а не полоска (выбор Ярослава 15.10.26): форма сразу говорит «это время» */
.cal-chip.rem { width: 10px; height: 10px; border-radius: 50%; grid-column: span 1; justify-self: center; align-self: center; }
.cal-more { font-size: 9.5px; line-height: 10px; color: var(--muted); align-self: center; grid-column: span 1; }

.cal-daybar { display: flex; align-items: center; gap: 10px; padding: 10px 12px 0; }
.cal-back {
  cursor: pointer; font-family: inherit; font-size: 11.5px; padding: 5px 10px; border-radius: 6px;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border);
}
.cal-back:hover { border-color: var(--accent); }
.cal-daytitle { font-size: 13px; font-weight: 700; }
.cal-count { font-size: 11px; color: var(--muted); }
.cal-daylist { display: flex; flex-direction: column; gap: 2px; padding: 8px 14px 14px; }
.cal-row { display: flex; align-items: center; }
/* PNG карточки несёт прозрачное поле 16 px с каждой стороны — гасим его отрицательными
   полями, чтобы визуальный зазор между соседними карточками был ~6-8 px (Ярослав 15.10.26). */
.cal-card { cursor: pointer; margin: -13px; }

.cal-preview { position: fixed; z-index: 80; pointer-events: none; }
.cal-nodata { padding: 0 12px 12px; font-size: 11.5px; color: var(--muted); }
</style>
