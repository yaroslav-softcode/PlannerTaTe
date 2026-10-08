<script setup>
import { computed } from 'vue'
import { CHANNEL_ALL, CHANNEL_ORDER, COLOR_NAMES, COLOR_NAMES_EN, L18N, NODE_COLORS, REPEAT_ORDER, REPEATS } from '../i18n.js'
import DateField from './DateField.vue'

/* Панель НАПОМИНАНИЯ (вид карточки 'notify'). Основа — панель задачи (LiteInspector.vue):
   те же классы оформления (.inspector/.lbl/.inp/.sel/.row2/.btn-row/...), поэтому вид один.
   Отличия (просьба Ярослава 01.10.26):
     • нет полей «Подзадачи», «Рисунок», «Затенение рисунка» и «Статус» — у напоминания их нет;
     • «Задача» и «Описание» — РЕДАКТИРУЕМЫЕ поля (Ярослав 08.10.26): у привязанного напоминания
       их копирует основная карточка, у отдельного — пустые, и править можно и там, и там;
     • вместо статуса — дата и время, когда напоминание прозвучит, плюс количество и повторения;
     • «Куда придёт» — НЕСКОЛЬКО вариантов сразу (галочки): компьютер / телефон
       (02.10.26 Telegram и Макс временно убраны из списка — данные карточек не тронуты);
     • цвет — как в панели задачи. */
const props = defineProps({ node: Object, lang: String, x: Number, y: Number })
const emit = defineEmits(['delete', 'save', 'change'])

const ru = computed(() => props.lang === 'ru')
const t = (k) => L18N[ru.value ? 'ru' : 'en'][k]

const repeatOptions = computed(() => REPEAT_ORDER.map(k => [k, REPEATS[ru.value ? 'ru' : 'en'][k]]))
const colorOptions = computed(() => COLOR_NAMES.map((key, i) => ({
  key,
  value: NODE_COLORS[key],
  label: (ru.value ? COLOR_NAMES : COLOR_NAMES_EN)[i] || key,
})))
// Подпись канала — по имени канала (раньше был хвост из тернарников: новый канал молча
// получил бы подпись «Макс»). Неизвестное имя показываем как есть.
const CH_LABEL_KEY = { pc: 'remPc', phone: 'remPhone', tablet: 'remTablet', telegram: 'remTg', vkmax: 'remVk' }
const chLabel = (ch) => { const k = CH_LABEL_KEY[ch]; return k ? t(k) : ch }

function setLabel(e) { props.node.title = e.target.value; emit('change') }
function setDesc(e) { props.node.description = e.target.value; emit('change') }
// Дата приходит из DateField строкой 'YYYY-MM-DD' (свой календарь: нативный подписывался на
// языке браузера) ; пустая строка — очистка. Формат хранения в graph.json не менялся.
function setDate(v) { props.node.due = v || ''; emit('change') }
// Время — ВСЕГДА 24 часа (Ярослав 01.10.26). Нативный <input type="time"> показывает формат по
// локали браузера (у него выходило с «AM/PM»), поэтому поле текстовое с разбором ввода:
// принимаем «9», «930», «9:30», «09.30», «0930» — на выходе всегда «HH:MM».
function setTime(e) {
  const prev = props.node.remindTime || '09:00'
  const digits = String(e.target.value || '').replace(/\D/g, '')
  let hh = NaN, mm = NaN
  if (digits.length <= 2) { hh = parseInt(digits, 10); mm = 0 }
  else if (digits.length === 3) { hh = parseInt(digits.slice(0, 1), 10); mm = parseInt(digits.slice(1), 10) }
  else if (digits.length >= 4) { hh = parseInt(digits.slice(0, 2), 10); mm = parseInt(digits.slice(2, 4), 10) }
  const ok = Number.isFinite(hh) && Number.isFinite(mm) && hh >= 0 && hh <= 23 && mm >= 0 && mm <= 59
  props.node.remindTime = ok ? `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}` : prev
  e.target.value = props.node.remindTime          // показываем нормализованное значение
  emit('change')
}
function setRepeat(e) { props.node.repeatMode = e.target.value; emit('change') }
function hasCh(ch) { return Array.isArray(props.node.channels) && props.node.channels.indexOf(ch) >= 0 }
// Галочки каналов: можно отметить несколько сразу. Порядок всегда как в CHANNEL_ORDER,
// чтобы в graph.json не было случайного порядка (иначе файлы «дрожат»).
function toggleCh(ch) {
  const cur = Array.isArray(props.node.channels) ? props.node.channels.slice() : []
  const i = cur.indexOf(ch)
  if (i >= 0) cur.splice(i, 1); else cur.push(ch)
  // нормализуем по ПОЛНОМУ списку (CHANNEL_ALL): канал, убранный из панели, у карточки
  // сохраняется — иначе первое же нажатие галочки молча стёрло бы его из graph.json
  props.node.channels = CHANNEL_ALL.filter(c => cur.indexOf(c) >= 0)
  emit('change')
}
function setColor(c) {
  if (props.node.color === c) return
  props.node.color = c
  emit('change')
}
</script>

<template>
  <div class="inspector rem" :style="{ '--ox': (x ?? 0) + 'px', '--oy': (y ?? 0) + 'px' }">
    <div class="rem-head"><span class="emo">⏰</span> {{ t('notifyTitle') }}</div>

    <!-- Задача и описание. У привязанного напоминания их копирует основная карточка при
         создании, у отдельного (Ярослав 08.10.26) их нет вовсе — поэтому поля РЕДАКТИРУЕМЫЕ
         в обоих случаях: пользователь правит что хочет, связь с задачей этого не запрещает. -->
    <label class="lbl">{{ ru ? 'Задача' : 'Task' }}</label>
    <input class="inp" :value="node.title || ''" @input="setLabel($event)"
           :placeholder="ru ? 'Задача' : 'Task'" />

    <label class="lbl">{{ ru ? 'Описание' : 'Description' }}</label>
    <textarea class="inp ta" rows="3" :value="node.description || ''" @input="setDesc($event)"
              :placeholder="ru ? 'Что нужно сделать…' : 'What to do…'"></textarea>

    <div class="row2">
      <div class="cell">
        <label class="lbl">{{ t('remDate') }}</label>
        <DateField :model="node.due || ''" :lang="lang" @change="setDate" />
      </div>
      <div class="cell">
        <label class="lbl">{{ t('remTime') }}</label>
        <input class="inp date" type="text" inputmode="numeric" maxlength="5" :placeholder="ru ? 'ЧЧ:ММ' : 'HH:MM'"
               :value="node.remindTime || '09:00'" @change="setTime" />
      </div>
    </div>

    <!-- Поля «количество» нет: сколько раз — задаёт частота (Ярослав 01.10.26). -->
    <label class="lbl">{{ t('remRepeat') }}</label>
    <select class="sel" :value="node.repeatMode || 'once'" @change="setRepeat">
      <option v-for="([val, lbl]) in repeatOptions" :key="val" :value="val">{{ lbl }}</option>
    </select>

    <label class="lbl">{{ t('remTo') }}</label>
    <label class="rem-chk" v-for="ch in CHANNEL_ORDER" :key="ch">
      <input type="checkbox" :checked="hasCh(ch)" @change="toggleCh(ch)" />
      <span>{{ chLabel(ch) }}</span>
    </label>

    <label class="lbl">{{ ru ? 'Цвет' : 'Color' }}</label>
    <select class="sel" :value="node.color" @change="setColor($event.target.value)">
      <option v-for="opt in colorOptions" :key="opt.key" :value="opt.value">{{ opt.label }}</option>
    </select>

    <div class="btn-row">
      <button class="save-btn" @click="$emit('save')">{{ ru ? 'Сохранить' : 'Save' }}</button>
      <button class="del-btn" @click="$emit('delete')">{{ ru ? 'Удалить' : 'Delete' }}</button>
    </div>
  </div>
</template>

<style>
/* Оформление берём из общего набора классов (задан в LiteInspector.vue, стили не scoped),
   здесь — только то, чего у задачи нет. Классы с префиксом rem- , чтобы не задеть чужие. */
.rem-head { font-size: 13px; font-weight: 700; margin: 0 0 2px; }
/* Предел для верха: панель напоминания — ~502 px (замер), поэтому при клике внизу экрана
   кнопки «Сохранить/Удалить» уехали бы за край. Внешний max(4px, …) страхует короткие окна,
   где 100vh - 515px уходит в минус. */
.inspector.rem { top: max(4px, min(max(var(--oy), 4px), calc(100vh - 515px))); }
.rem-ro {
  font-size: 12px; color: var(--muted); background: var(--input-bg);
  border: 1px dashed var(--input-border); border-radius: 6px; padding: 5px 8px;
  max-height: 54px; overflow: hidden; white-space: pre-wrap; word-break: break-word;
}
.rem-chk {
  display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--text);
  margin: 5px 0; cursor: pointer;
}
.rem-chk input { width: 14px; height: 14px; margin: 0; accent-color: var(--accent); cursor: pointer; }
</style>
