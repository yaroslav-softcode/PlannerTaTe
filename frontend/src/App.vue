<script setup>
import { ref, computed, reactive, nextTick, onMounted, onBeforeUnmount, toRaw, watch } from 'vue'
import { LGraph, LGraphCanvas, LGraphNode, LiteGraph } from 'litegraph.js'
import { NODE_COLORS, COLOR_NAMES, L18N, STATUS_SHORT, REPEATS, REPEATS_SHORT } from './i18n.js'
import { THEMES, THEME_IDS, CUSTOM_ID, setActiveTheme, theme, accentOf, linkColorOf, statusColorOf, STATUS_COLOR, rgba, customCfg, setCustom } from './themes.js'
import DescReader from './components/DescReader.vue'
import LiteInspector from './components/LiteInspector.vue'
import ReminderList from './components/ReminderList.vue'
import ReminderPanel from './components/ReminderPanel.vue'
import LicensePanel from './components/LicensePanel.vue'
import PhoneInstallPanel from './components/PhoneInstallPanel.vue'
import RestorePanel from './components/RestorePanel.vue'
import { installTouchSupport } from './touch.js'

// --- Регистрация кастомного прямоугольного узла (PlannerTaTe) ---
// Скруглённый rect как standalone-хелпер: roundRect(ctx, x, y, w, h, r).
// Работает в любом canvas-контексте — рисует по moveTo/lineTo/arcTo, не зависит от ctx.roundRect.
function roundRect(ctx, x, y, w, h, r) {
  const rad = typeof r === 'number' ? [r, r, r, r] : (r || [])
  const [tl, tr, br, bl] = rad.length >= 4 ? rad : [0, 0, 0, 0]
  ctx.beginPath()
  ctx.moveTo(x + tl, y)
  ctx.lineTo(x + w - tr, y)
  ctx.arcTo(x + w, y, x + w, y + tr, tr)
  ctx.lineTo(x + w, y + h - br)
  ctx.arcTo(x + w, y + h, x + w - br, y + h, br)
  ctx.lineTo(x + bl, y + h)
  ctx.arcTo(x, y + h, x, y + h - bl, bl)
  ctx.lineTo(x, y + tl)
  ctx.arcTo(x, y, x + tl, y, tl)
  ctx.closePath()
}

// 'YYYY-MM-DD' (значение <input type="date">) -> 'DD.MM.YY' для карточки.
function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '')
  return m ? `${m[3]}.${m[2]}.${m[1].slice(2)}` : (iso || '')
}

// Значения по умолчанию для новой карточки-напоминания: сегодняшняя дата и ближайший круглый
// час (напоминание «через час», а не «в полночь») — так панель открывается с осмысленным сроком.
function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function defaultRemindTime() {
  const d = new Date(Date.now() + 3600 * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:00`
}

// Разбивает текст на строки по ширине maxW (с учётом \n). Шрифт должен быть уже выставлен.
function wrapText(ctx, text, maxW) {
  const lines = []
  for (const paragraph of String(text || '').split('\n')) {
    let cur = ''
    for (const word of paragraph.split(' ')) {
      const test = cur ? cur + ' ' + word : word
      if (ctx.measureText(test).width > maxW && cur) { lines.push(cur); cur = word } else cur = test
    }
    if (cur || lines.length === 0) lines.push(cur)
  }
  return lines
}

// Быстрый перенос для ДЛИННЫХ текстов (описание карточки) — просьба Ярослава 05.10.26:
// на телефоне при приближении карточки с описанием в 5 000 знаков падали кадры.
// Отличия от wrapText: слова мерятся по отдельности и КЭШируются по шрифту (было — растущая
// строка на каждое слово), и есть ранняя остановка — больше maxLines строк не нужно, лишнее
// всё равно уходит под «…». Короткие тексты (название) по-прежнему идут через wrapText.
const WORD_W = new Map()
function wordWidth(ctx, word) {
  const k = ctx.font + '\u0001' + word
  let w = WORD_W.get(k)
  if (w === undefined) {
    w = ctx.measureText(word).width
    if (WORD_W.size > 40000) WORD_W.clear()   // страховка от бесконечного роста
    WORD_W.set(k, w)
  }
  return w
}
function wrapTextLimited(ctx, text, maxW, maxLines) {
  const lines = []
  const sp = wordWidth(ctx, ' ')
  for (const paragraph of String(text || '').split('\n')) {
    let cur = '', curW = 0
    for (const word of paragraph.split(' ')) {
      if (!word) continue
      const ww = wordWidth(ctx, word)
      const test = cur ? curW + sp + ww : ww
      if (test > maxW && cur) {
        lines.push(cur)
        if (lines.length >= maxLines) return lines
        cur = word; curW = ww
      } else { cur = cur ? cur + ' ' + word : word; curW = test }
    }
    if (cur) lines.push(cur)
    if (lines.length >= maxLines) return lines
  }
  return lines.length ? lines : ['']
}

// Обрезает текст по ширине maxW, добавляя «…» (для нижних углов карточки).
const MAX_DESC_LINES = 3   // сколько строк описания помещаем в карточку 100×56
// Отрисовка карточки зависит от зума холста (просьба Ярослава 30.09.26):
//  • средний/дальний план (зум < zoomDetail()) — видно только НАЗВАНИЕ крупным кеглем
//    во всю карточку (мелкое описание на таком расстоянии всё равно не читается),
//    снизу остаются статус и срок, если они заданы;
//  • ближний план (зум ≥ zoomDetail(), то есть почти максимум — максимум холста 10) —
//    название уходит в шапку сверху, под ним описание ЦЕЛИКОМ: кегль подбирается так,
//    чтобы весь текст влез в карточку (вблизи мелкий шрифт уже читается).
// Порог перехода «средний → ближний план» — ОДИН на всё: по нему и показывается описание,
// и затеняется рисунок в авто-режиме (просьба Ярослава 05.10.26: «всё вместе»). Было 5.
// Теперь компьютер 4, телефон 3 — показывать раньше (экран телефона маленький: уже на ~3
// карточка занимает почти всю ширину, мелкий кегль читается). Телефон — по «грубому» указателю.
const ZOOM_DETAIL_DESKTOP = 4
const ZOOM_DETAIL_PHONE = 3
const IS_PHONE = (() => {
  try { return window.matchMedia('(pointer: coarse)').matches } catch (e) { return false }
})()
const zoomDetail = () => (IS_PHONE ? ZOOM_DETAIL_PHONE : ZOOM_DETAIL_DESKTOP)
const ZOOM_TITLE_MAX = 26   // крупное название на среднем плане: диапазон подбора кегля
const ZOOM_TITLE_MIN = 10
const MIN_DESC_SIZE = 2.6   // мельче описание не читается даже вблизи

// --- Активное окно: рабочая область холста, ограниченная рамкой -----------------
// Ярослав 01.10.26: сначала собрали область вчетверо больше окна (стороны вдвое), потом откатили,
// затем «Сделай активное окно восемь раз больше» → площадь в 8 раз больше окна, то есть стороны
// в √8 ≈ 2.83 раза (карточки при этом того же размера). Внутри области рисуется сетка, по периметру
// идёт тонкая линия-рамка, панорама зажимается её краями, а отпущенные за границей карточки
// возвращаются внутрь — иначе их было бы не достать: за границу не уехать.
const FIELD_AREA_X = 8
const FIELD_SIDE_X = Math.sqrt(FIELD_AREA_X)    // ≈2.83 — во сколько раз сторона больше окна
const FIELD = { x: 0, y: 0, w: 1200, h: 800 }   // пересчитывается под окно в updateField()
function updateField() {
  const w = (canvasEl.value && canvasEl.value.clientWidth) || 1200
  const h = (canvasEl.value && canvasEl.value.clientHeight) || 800
  FIELD.w = Math.round(w * FIELD_SIDE_X)
  FIELD.h = Math.round(h * FIELD_SIDE_X)
}
let viewScale = 1           // текущий зум холста (обновляет хук onDrawBackground)
const ARROW_LEN = 9        // длина треугольника-указателя направления связи (координаты графа)

// Порты карточки — вариант 1 набора (вернул Ярослав 30.09.26): вход — КОЛЬЦО, выход — ТОЧКА,
// врезаны в верхние углы (центр на дуге скругления, как полоса статуса). Одна формула на всё:
// отрисовку, концы связей (getConnectionPos) и попадание мышью.
const PORT = {
  r: 4.2,                 // радиус порта (координаты графа)
  ring: 2.2,              // толщина кольца на входе
  out: 0,                 // сдвиг центра наружу от дуги скругления
  minCorner: 3,
}
function portOffset() {
  // точка на дуге скругления под 45°: R − R/√2 ≈ 0.293·R (для скругления < 10px не ниже 3px)
  const R = theme().node.radius || 10
  const onArc = Math.max(PORT.minCorner, R * 0.293)
  return Math.max(0.4, Math.round((onArc - PORT.out) * 10) / 10)
}
// Кнопка «открыть описание целиком» — лупа с плюсом внутри (просьба Ярослава 05.10.26).
// Рисуем линиями, цветом текста карточки: у эмодзи на Windows свои цвета, а карточка должна
// жить в палитре темы (как будильник и значки вложений).
function drawZoomBtn(ctx, cx, cy, size, color) {
  const r = size * 0.33
  ctx.save()
  ctx.strokeStyle = color
  ctx.lineWidth = Math.max(1, size * 0.09)
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)               // линза
  ctx.stroke()
  const a = Math.PI * 0.25                          // рукоятка — вниз-вправо
  ctx.beginPath()
  ctx.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r)
  ctx.lineTo(cx + Math.cos(a) * (r + size * 0.28), cy + Math.sin(a) * (r + size * 0.28))
  ctx.stroke()
  const p = r * 0.52                                // плюс внутри линзы
  ctx.beginPath()
  ctx.moveTo(cx - p, cy); ctx.lineTo(cx + p, cy)
  ctx.moveTo(cx, cy - p); ctx.lineTo(cx, cy + p)
  ctx.stroke()
  ctx.restore()
}

function portLocalPos(node, isInput) {
  const d = portOffset()
  return isInput ? [d, d] : [node.size[0] - d, d]
}
// Будильник для монохромной темы: чашечка-циферблат, две «ножки», кнопка и стрелки — всё линиями
// цветом текста карточки (эмодзи ⏰ в Windows всегда цветной, поэтому знак рисуем сами).
function drawBellMono(ctx, cx, top, size, color) {
  const r = size * 0.33
  const cy = top + size * 0.64
  ctx.save()
  ctx.strokeStyle = color
  ctx.lineWidth = Math.max(1, size * 0.085)
  ctx.lineCap = 'round'
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke()          // корпус
  ctx.beginPath(); ctx.arc(cx - r, cy - r, r * 0.45, Math.PI * 1.08, Math.PI * 1.92); ctx.stroke()  // левая ножка
  ctx.beginPath(); ctx.arc(cx + r, cy - r, r * 0.45, Math.PI * 1.08, Math.PI * 1.92); ctx.stroke()  // правая ножка
  ctx.beginPath();                                                          // стрелки
  ctx.moveTo(cx, cy); ctx.lineTo(cx, cy - r * 0.6)
  ctx.moveTo(cx, cy); ctx.lineTo(cx + r * 0.48, cy + r * 0.2)
  ctx.stroke()
  ctx.beginPath(); ctx.moveTo(cx, cy - r * 1.5); ctx.lineTo(cx, cy - r * 1.06); ctx.stroke()  // кнопка
  ctx.restore()
}

// Цвет порта: вход — цвет входящей связи, выход — акцент самой карточки.
// Свободный порт (нет связей) отдаём теме — см. portIdle в themes.js.
function portColor(node, isInput) {
  const g = node.graph
  if (!g) return null
  if (!isInput) return linkColorOf(node.color)
  const links = g.links || {}
  for (const id in links) {
    const l = links[id]
    if (l && l.target_id == node.id) {
      const src = g.getNodeById(l.origin_id)
      if (src) return linkColorOf(src.color)
    }
  }
  return null
}
function fitText(ctx, text, maxW) {
  if (ctx.measureText(text).width <= maxW) return text
  let s = text
  while (s.length > 1 && ctx.measureText(s + '…').width > maxW) s = s.slice(0, -1)
  return s + '…'
}

// --- Рисунки на карточках ---------------------------------------------------
// Картинка хранится как data-URL прямо в узле (и, значит, в graph.json).
// Кеш: один HTMLImageElement на каждый data-URL, иначе Image() создавался бы каждый кадр.
const IMG_CACHE = new Map()
function getImage(src) {
  let img = IMG_CACHE.get(src)
  if (!img) {
    img = new Image()
    img.onload = () => { if (liteCanvas) liteCanvas.setDirty(true, true) }
    img.onerror = () => { if (liteCanvas) liteCanvas.setDirty(true, true) }
    img.src = src
    IMG_CACHE.set(src, img)
  }
  return img
}

// Уменьшает картинку до maxSide по большей стороне и отдаёт JPEG data-URL
// (иначе graph.json распухнет от оригиналов). Прозрачность заливаем фоном.
function shrinkImage(src, maxSide = 360, quality = 0.85) {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      try {
        const k = Math.min(1, maxSide / Math.max(img.width || 1, img.height || 1))
        const w = Math.max(1, Math.round((img.width || 1) * k))
        const h = Math.max(1, Math.round((img.height || 1) * k))
        const c = document.createElement('canvas')
        c.width = w; c.height = h
        const cx = c.getContext('2d')
        cx.fillStyle = '#1e1e2e'; cx.fillRect(0, 0, w, h)
        cx.drawImage(img, 0, 0, w, h)
        resolve(c.toDataURL('image/jpeg', quality))
      } catch (e) { console.error(e); resolve(null) }
    }
    img.onerror = () => resolve(null)
    img.src = src
  })
}

class RectNode extends LGraphNode {
  constructor() {
    super()
    this.title = 'Задача'
    // Вид карточки: 'task' — задача, 'notify' — напоминание (значок ⏰ и свой цвет).
    // Ярослав 01.10.26: «В левом меню там, где у нас плюс задача ниже сделай кнопку + уведомление» (так он называл её до переименования в напоминание).
    this.kind = 'task'
    this.color = '#5b8fd9'
    // Заливку и рамку карточки рисует тема (onDrawBackground), поэтому штатный фон
    // LiteGraph держим прозрачным: иначе он перекрывает полупрозрачное «стекло»
    // и градиент холста, который должен просвечивать сквозь карточку.
    this.bgcolor = 'rgba(0,0,0,0)'
    this.tags = []
    this.status = ''
    this.description = ''
    this.due = ''
    this.image = ''   // ФОН карточки: data-URL (копия внутри узла; «рисунок» → «фон», 03.10.26)
    // ССЫЛКИ НА ФАЙЛЫ в системе — массив ПОЛНЫХ путей, не больше MAX_FILES (файлы НЕ копируем).
    this.files = []
    this._badges = []   // места значков вложения в локальных координатах — для попадания мышью
    // Затенение рисунка: 'auto' — как раньше (затемняем только на среднем/дальнем плане),
    // 'on' — всегда включено, 'off' — всегда выключено. Выбирается в панели карточки.
    this.dimMode = 'auto'
    // --- Поля НАПОМИНАНИЯ (используются только при kind = 'notify') ---
    // Когда и как прозвучит: дата лежит в общем поле due, время — своё поле.
    // Частота («повторения») и каналы доставки заполняются в панели напоминания
    // (ReminderPanel.vue). Само срабатывание в срок — следующий шаг, здесь только данные и вид.
    // Отдельного «количества» нет: сколько раз — задаёт частота (Ярослав 01.10.26: «количество
    // повторений вообще убери»).
    this.remindTime = '09:00'    // 'HH:MM' — во сколько прозвучит
    this.repeatMode = 'once'     // once | daily | weekly | weekdays | monthly
    // Куда придёт напоминание: pc (Windows) | phone (телефон) | tablet (планшет). По умолчанию
    // включены ВСЕ ТРИ (просьба Ярослава 06.10.26) — лишний канал снимается галочкой в панели.
    this.channels = ['pc', 'phone', 'tablet']
    this.inputs = [{ name: 'вход', type: '*', link: null, label: '' }]
    this.outputs = [{ name: 'выход', type: '*', links: null, label: '' }]
    this.hideSlotDots()
    // Убираем встроенную шапку LiteGraph (заголовок над карточкой), чтобы задача не дублировалась.
    this.constructor.title_mode = LiteGraph.NO_TITLE
    // БАГ (нашёл Ярослав 01.10.26): шапки у карточки нет, но LiteGraph всё равно держал
    // невидимую кнопку сворачивания в полосе NODE_TITLE_HEIGHT (30 px) НАД карточкой у левого
    // края. Клик по верхней кромке рядом с левым углом попадал в неё -> карточка сворачивалась
    // («рамка смещается и выделяет только верхнюю часть панельки»). Гасим сворачивание класса.
    this.constructor.collapsable = false
    this.size = [100, 56] // ~16:9 (ширина = высота * 16/9), та же высота, короче длина
  }

  // Зона нажатия — ровно карточка. Библиотека (LGraphNode.isPointInside) добавляет сверху
  // полосу под несуществующий заголовок (NODE_TITLE_HEIGHT = 30 px, холст не в live-режиме) и
  // почти срезает нижнюю кромку: клик ВЫШЕ карточки выбирал её, а по нижней границе — не
  // выбирал (жалоба Ярослава 01.10.26: «смести область нажатия вниз»). По бокам оставляем
  // библиотечные ±4 px, сверху и снизу — по 2 px, чтобы кромки уверенно брались мышью.
  isPointInside(x, y, margin) {
    const m = margin || 0
    const px = this.pos[0], py = this.pos[1], w = this.size[0], h = this.size[1]
    return x > px - 4 - m && x < px + w + 4 + m && y > py - 2 - m && y < py + h + 2 + m
  }
  // Текст «во сколько прозвучит» для карточки-напоминания. «×N» больше нет: количество убрано,
  // частоту задаёт поле «Повторения» (Ярослав 01.10.26).
  reminderTimeText() {
    return String(this.remindTime || '').trim() || '--:--'
  }
  // Подпись повторения для нижней строки карточки. На карточке — КОРОТКАЯ форма
  // («ежеднев.», «еженед.», «ежемес.»): полные слова упирались в дату и обрезались многоточием
  // (Ярослав 01.10.26). В панели напоминания остаются полные слова (REPEATS).
  // Каналы доставки на карточку НЕ выводим: на 100 px она влезает только с повторением и датой,
  // каналы видны и выбираются в панели напоминания (решение после замера 01.10.26).
  repeatLabel() {
    const loc = (lang && lang.value) === 'en' ? 'en' : 'ru'
    const dict = REPEATS_SHORT[loc] || REPEATS_SHORT.ru
    return dict[this.repeatMode] || dict.once
  }
  // Кастомные поля (статус / описание / срок / теги) LiteGraph сам не сохраняет —
  // дописываем их в объект сериализации. Обратно они восстанавливаются автоматически
  // (LGraphNode.configure копирует все ключи из info), отдельный onConfigure не нужен.
  onSerialize(o) {
    o.status = this.status || ''
    o.description = this.description || ''
    o.due = this.due || ''
    o.tags = this.tags || []
    o.image = this.image || ''
    // Ссылки на файлы. Граф, сохранённый прошлой версией, держал одну ссылку в поле file —
    // не теряем её: переводим в список.
    const fLinks = Array.isArray(this.files) ? this.files.filter(Boolean).slice(0, MAX_FILES) : []
    if (!fLinks.length && this.file) fLinks.push(this.file)
    o.files = fLinks
    o.dimMode = this.dimMode || 'auto'
    o.kind = this.kind || 'task'
    // Панель устройства: 'phone' | 'tablet' — по нему рисуется глиф устройства и привязываются
    // задачи, пришедшие с устройства синхронизацией (06.10.26).
    if (this.kind === 'device') o.device = this.device || 'phone'
    // Поля напоминания — чтобы не потерялись при сохранении в graph.json.
    o.remindTime = this.remindTime || ''
    o.repeatMode = this.repeatMode || 'once'
    o.channels = Array.isArray(this.channels) ? this.channels.slice() : []
  }
  // Старые графы хранят непрозрачный bgcolor: на загрузке сбрасываем его в прозрачный,
  // чтобы карточку всегда рисовала активная тема, а не «зашитый» в файл цвет.
  // Там же гасим заводские точки портов (их мог восстановить configure из файла).
  onConfigure() {
    this.bgcolor = 'rgba(0,0,0,0)'
    this.hideSlotDots()
    // Панель устройства — системная плитка: вход ей не нужен (кольца нет), ресайз запрещён
    // (LiteGraph эти поля из файла не восстанавливает — задаём при каждой загрузке графа).
    if ((this.kind || 'task') === 'device') { this.resizable = false; this.inputs = [] }
  }
  // Заводские точки портов LiteGraph рисует своим зелёным (#7F7). Гасим их прозрачным
  // цветом слота — свои порты (кольцо на входе, точка на выходе) рисует тема.
  hideSlotDots() {
    for (const list of [this.inputs, this.outputs]) {
      if (!list) continue
      for (const s of list) { s.color_on = 'rgba(0,0,0,0)'; s.color_off = 'rgba(0,0,0,0)' }
    }
  }
  // LiteGraph.addInput() внутри делает setSize(this.computeSize()) — это пересчитывает размер
  // и превращает его в Float32Array, ломая утверждённый размер карточки 100×56 (видно при fan-in,
  // когда к занятому входу добавляется второй). После вызова возвращаем фиксированный размер.
  addInput(name, type, extra_info) {
    const input = super.addInput(name, type, extra_info)
    this.size = [100, 56]
    this.hideSlotDots()   // новый слот тоже не должен рисовать заводскую зелёную точку
    return input
  }
  // Несколько карточек на один вход: при подключении к уже занятому слоту создаём новый пустой.
  onBeforeConnectInput(target_slot) {
    // Проверка дупликата ДО создания точки-призрака.
    // Источник перетаскиваемой связи — на канвасе (драг). Отменяем попытку,
    // если между этим источником и текущей задачей связь уже есть —
    // тогда LiteGraph не создаст вторую точку и вторую линию.
    const src = liteCanvas && liteCanvas.connecting_node ? toRaw(liteCanvas.connecting_node) : null
    if (src) {
      for (const id in this.graph.links) {
        const link = this.graph.links[id]
        if (link && link.origin_id == src.id && link.target_id == this.id) {
          return false
        }
      }
    }
    if (this.inputs[target_slot] && this.inputs[target_slot].link != null) {
      const idx = this.inputs.length + 1
      const slot = this.addInput(`вход ${idx}`, '*')
      slot.label = ''
      return this.inputs.length - 1
    }
    return target_slot
  }
  // Одна связь между двумя задачами: отменяем попытку повторно привязать тот же узел к тому же целевому.
  // Работает как для драг-дроп, так и для программного connect(). Разные узлы на один приёмник (fan-in) не блокируются — у них другой origin_id.
  onConnectOutput(slot, inputType, input, target_node) {
    if (!this.graph || !target_node) return true
    for (const id in this.graph.links) {
      const link = this.graph.links[id]
      if (link && link.origin_id == this.id && link.target_id == target_node.id) {
        return false
      }
    }
    return true
  }
  // Вся внешность карточки берётся из активной темы (палитра — src/themes.js),
  // цвет-акцент — это выбор пользователя (node.color), он же рамка и полоса.
  onDrawBackground(ctx) {
    const w = this.size[0], h = this.size[1]
    const t = theme().node
    const acc = accentOf(this.color)
    const r = Math.max(2, Math.min(t.radius, h / 2, w / 2))
    if ((this.kind || 'task') === 'device') { this.drawDeviceTile(ctx, t, acc, r); return }
    const statusColor = statusColorOf(this.status || 'none')

    // 1. Тело карточки: градиент темы (у «стекла» полупрозрачный — сквозь него виден холст).
    ctx.save()
    if (t.shadow) { ctx.shadowColor = t.shadow.color; ctx.shadowBlur = t.shadow.blur; ctx.shadowOffsetY = t.shadow.oy || 0 }
    roundRect(ctx, 0, 0, w, h, r)
    const g = ctx.createLinearGradient(0, 0, 0, h)
    g.addColorStop(0, t.fillTop(acc))
    g.addColorStop(1, t.fillBot(acc))
    ctx.fillStyle = g
    ctx.fill()
    ctx.restore()

    // 2. Рисунок = фон карточки (object-fit: cover) + затемнение, чтобы текст читался.
    if (this.image) {
      const img = getImage(this.image)
      if (img.complete && img.naturalWidth) {
        const k = Math.max(w / img.naturalWidth, h / img.naturalHeight)
        const dw = img.naturalWidth * k, dh = img.naturalHeight * k
        ctx.save()
        roundRect(ctx, 0, 0, w, h, r); ctx.clip()
        ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh)
        // Затенение рисунка. По умолчанию ('auto') затемняем только на среднем/дальнем плане:
        // там на карточке лишь название, и оно должно читаться по рисунку, а вблизи появляется
        // описание и рисунок показывается как есть. В панели карточки это можно переключить
        // на «всегда включено» / «всегда выключено» (просьба Ярослава 01.10.26).
        const dimMode = this.dimMode || 'auto'
        if (dimMode === 'on' || (dimMode === 'auto' && viewScale < zoomDetail())) {
          ctx.fillStyle = t.imgDim
          ctx.fillRect(0, 0, w, h)
        }
        ctx.restore()
      }
    }

    // 3. Рамка: цвет — акцент узла, свечение — из темы (у неона сильное, у светлой темы нет).
    ctx.save()
    if (t.glowBlur) { ctx.shadowColor = t.glowColor(acc); ctx.shadowBlur = t.glowBlur; ctx.shadowOffsetY = t.glowOffsetY || 0 }
    roundRect(ctx, t.borderW / 2, t.borderW / 2, w - t.borderW, h - t.borderW, r)
    ctx.lineWidth = t.borderW
    ctx.strokeStyle = t.border(acc)
    ctx.stroke()
    ctx.restore()

    // 4. Блик по верху внутри — «стекло» (тема A).
    if (t.inner) {
      ctx.save()
      roundRect(ctx, 0, 0, w, h, r); ctx.clip()
      ctx.strokeStyle = t.inner; ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(r * 0.7, 1.2); ctx.lineTo(w - r * 0.7, 1.2); ctx.stroke()
      ctx.restore()
    }

    // 5. Полоса статуса слева (её цвет — статус, а не акцент карточки).
    const st = t.stripe
    if (st && st.w) {
      ctx.save()
      roundRect(ctx, 0, 0, w, h, r); ctx.clip()
      if (st.glow) { ctx.shadowColor = statusColor; ctx.shadowBlur = st.glow }
      ctx.fillStyle = statusColor
      const inset = st.inset || 0
      if (st.radius) roundRect(ctx, 0, inset, st.w, h - inset * 2, st.radius)
      else { ctx.beginPath(); ctx.rect(0, 0, st.w, h) }
      ctx.fill()
      ctx.restore()
    }
  }
  // --- Панель устройства («Смартфон»/«Планшет»), 06.10.26 ----------------------------------
  // Квадратная плитка 56×56: тело как у карточки (палитра активной темы), внутри — глиф
  // устройства и подпись. Глиф рисуем ЛИНИЯМИ, как значки вложений и будильник: эмодзи
  // в Windows всегда цветные и не слушаются тем. Порт-точка — сверху по центру, её рисует
  // onDrawForeground. Плитку нельзя удалить (deleteSelected/duplicateNode не трогают),
  // задачи с устройства встают к ней детьми, файл с плитки уезжает на устройство.
  // Параметр темы зовём tm: имя t внутри занято функцией перевода (иначе на каждом кадре
  // падало «I is not a function» — подпись панели не рисовалась. Баг найден и исправлен 06.10.26).
  drawDeviceTile(ctx, tm, acc, r) {
    const w = this.size[0], h = this.size[1]
    const isTab = this.device === 'tablet'
    // 1. Тело: градиент темы + тень (как у карточки).
    ctx.save()
    if (tm.shadow) { ctx.shadowColor = tm.shadow.color; ctx.shadowBlur = tm.shadow.blur; ctx.shadowOffsetY = tm.shadow.oy || 0 }
    roundRect(ctx, 0, 0, w, h, r)
    const g = ctx.createLinearGradient(0, 0, 0, h)
    g.addColorStop(0, tm.fillTop(acc))
    g.addColorStop(1, tm.fillBot(acc))
    ctx.fillStyle = g
    ctx.fill()
    ctx.restore()
    // 2. Рамка: цвет — акцент темы, свечение — из темы (у светлых тем его нет).
    ctx.save()
    if (tm.glowBlur) { ctx.shadowColor = tm.glowColor(acc); ctx.shadowBlur = tm.glowBlur; ctx.shadowOffsetY = tm.glowOffsetY || 0 }
    roundRect(ctx, tm.borderW / 2, tm.borderW / 2, w - tm.borderW, h - tm.borderW, r)
    ctx.lineWidth = tm.borderW
    ctx.strokeStyle = tm.border(acc)
    ctx.stroke()
    ctx.restore()
    // 3. Блик по верху внутри — «стекло».
    if (tm.inner) {
      ctx.save()
      roundRect(ctx, 0, 0, w, h, r); ctx.clip()
      ctx.strokeStyle = tm.inner; ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(r * 0.7, 1.2); ctx.lineTo(w - r * 0.7, 1.2); ctx.stroke()
      ctx.restore()
    }
    // 4. Глиф устройства: корпус, экран (подкрашен акцентом), детали.
    const cx = w / 2
    ctx.save()
    ctx.lineJoin = 'round'
    ctx.strokeStyle = tm.titleColor
    ctx.fillStyle = tm.titleColor
    ctx.lineWidth = 1.3
    if (isTab) {
      const bw = 28, bh = 21, bx = cx - bw / 2, by = 10
      roundRect(ctx, bx, by, bw, bh, 3); ctx.stroke()
      ctx.save(); ctx.globalAlpha = 0.30; ctx.fillStyle = acc
      roundRect(ctx, bx + 2.2, by + 2.2, bw - 4.4, bh - 6.2, 1.5); ctx.fill(); ctx.restore()
      ctx.beginPath(); ctx.arc(cx, by + bh - 2, 0.9, 0, Math.PI * 2); ctx.fill()
    } else {
      const bw = 20, bh = 30, bx = cx - bw / 2, by = 4
      roundRect(ctx, bx, by, bw, bh, 3.8); ctx.stroke()
      ctx.save(); ctx.globalAlpha = 0.30; ctx.fillStyle = acc
      roundRect(ctx, bx + 2, by + 2.8, bw - 4, bh - 8.6, 2); ctx.fill(); ctx.restore()
      ctx.beginPath(); ctx.moveTo(cx - 3.4, by + 1.6); ctx.lineTo(cx + 3.4, by + 1.6); ctx.stroke()
      ctx.beginPath(); ctx.arc(cx, by + bh - 2.8, 1.1, 0, Math.PI * 2); ctx.stroke()
    }
    ctx.restore()
    // 5. Подпись: кегль не больше 10 (плитка маленькая), КАПС — как у названий темы.
    ctx.save()
    ctx.font = `${tm.titleWeight} ${Math.min(10, tm.titleSize)}px ${tm.titleFamily}`
    ctx.fillStyle = tm.titleColor
    ctx.textAlign = 'center'
    ctx.textBaseline = 'alphabetic'
    let label = t(isTab ? 'deviceTablet' : 'devicePhone')
    if (tm.titleUp) label = label.toUpperCase()
    ctx.fillText(label, cx, h - 6)
    ctx.restore()
  }
  // Порт панели устройства: ОДНА точка сверху по центру (кольца нет — решение Ярослава 06.10.26).
  drawDeviceDot(ctx, w, t) {
    const color = linkColorOf(this.color)
    ctx.save()
    ctx.shadowBlur = 0
    ctx.shadowColor = 'transparent'
    if (t.portGlow) { ctx.shadowColor = color; ctx.shadowBlur = t.portGlow }
    ctx.beginPath()
    ctx.arc(w / 2, 0, PORT.r, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()
    if (t.portOutline) {   // тонкий контур, чтобы точка читалась на светлой плитке
      ctx.shadowBlur = 0
      ctx.lineWidth = 1
      ctx.strokeStyle = t.portOutline
      ctx.stroke()
    }
    ctx.restore()
  }
  // Порты карточки лежат в верхних углах, и все входы сходятся в ОДНУ точку (левый
  // верхний угол): LiteGraph держит по слоту на связь и рисовал бы «лестницу» точек.
  // Здесь же задаём и концы связей — LiteGraph берёт их из этого же метода.
  // У панели устройства выход — одна точка СВЕРХУ ПО ЦЕНТРУ (06.10.26).
  getConnectionPos(is_input, _slot_number, out) {
    const dst = out || [0, 0]
    if (!is_input && (this.kind || 'task') === 'device') {
      dst[0] = this.pos[0] + this.size[0] / 2
      dst[1] = this.pos[1]
      return dst
    }
    const [lx, ly] = portLocalPos(this, !!is_input)
    dst[0] = this.pos[0] + lx
    dst[1] = this.pos[1] + ly
    return dst
  }
  onDrawForeground(ctx) {
    const w = this.size[0], h = this.size[1]
    const t = theme().node

    // Панель устройства: кроме точки-порта сверху по центру ничего не рисуем (кольца нет).
    if ((this.kind || 'task') === 'device') { this.drawDeviceDot(ctx, w, t); return }

    // Разметка карточки сверху вниз: название (по центру), описание, нижняя строка —
    // статус слева и срок справа. Каждая зона отъедает высоту у той, что выше, поэтому
    // ничего не наезжает друг на друга. Шрифты/цвета — из темы.
    // План отображения выбирается по зуму холста: на среднем плане — только крупное
    // название (см. zoomDetail()), вблизи — шапка сверху и описание целиком мелким шрифтом.
    // Карточка-напоминание: значок ⏰ стоит СВЕРХУ ПО ЦЕНТРУ, поэтому текст вправо не сдвигаем
    // (Ярослав 01.10.26: «значок будильника должен быть сверху по центру» + «центрирование
    // основного названия проверь»).
    const bellPad = 0
    const titleCx = w / 2
    const loc = (lang && lang.value) === 'en' ? 'en' : 'ru'
    // Карточка-напоминания (kind 'notify') вместо названия показывает ЧТО и КОГДА прозвучит:
    // в слоте названия — время, в нижней строке СЛЕВА — повторение («ежедневно», «еженедельно»),
    // СПРАВА — дата, как у задачи (Ярослав 01.10.26).
    const isRem = this.kind === 'notify'
    const statusText = isRem ? this.repeatLabel() : (STATUS_SHORT[loc][this.status] || '')
    const dueText = this.due ? shortDate(this.due) : ''   // у напоминания здесь дата срока
    // Описание: переносы строк, которые поставил пользователь, сохраняем (схлопываем
    // только пробелы внутри строки) — тогда карточка повторяет то, что видно в поле.
    const descText = isRem ? '' : (this.description || '')
      .split('\n').map(s => s.replace(/[ \t]+/g, ' ').trim()).filter(Boolean).join('\n')

    // Значки вложений стоят МЕЖДУ статусом и датой, поэтому их полосу отнимаем у подписей:
    // иначе статус и дата занимают всю ширину, коридора в середине нет — и значков не видно
    // (замер 03.10.26: на карточке со статусом и сроком значок не рисовался вовсе).
    // Высота значка — как у даты (просьба Ярослава 03.10.26), отсюда и небольшой размер.
    // ВАЖНО: объявлять badges/badgeS/badgeW ДО hasBadgeFile — иначе обращение до инициализации
    // и отрисовка падает с «Cannot access before initialization» (наступил 03.10.26).
    const badges = filesOf(this)
    const badgeS = badges.length ? t.statusSize : 0
    const badgeW = badgeS ? Math.round(badgeS * 0.82) : 0
    const badgeGap = badges.length > 3 ? 1 : 2     // чем больше ссылок, тем плотнее ряд
    const badgeZone = badgeS ? badges.length * badgeW + (badges.length - 1) * badgeGap + 8 : 0

    // Значки вложения (если к карточке приложены ссылки на файлы) занимают место в нижней
    // строке — значит, она существует, даже когда нет ни статуса, ни срока.
    const hasBadgeFile = badges.length > 0
    const hasFooter = !!(statusText || dueText || hasBadgeFile)
    // Нижняя строка (статус слева, срок справа) прижата к НИЖНЕЙ ГРАНИ карточки: зазор считаем
    // по чернилам глифов (actualBoundingBox*), а не по строчному боксу, — так надписи стоят
    // максимально близко к грани при любом шрифте (просьба Ярослава 01.10.26). Отсюда же берём
    // полосу footerH, которую нельзя занимать названию и описанию.
    const footerPad = 6                       // поля слева/справа у надписей
    const maxSide = Math.max(14, (w - badgeZone) / 2 - footerPad - 2)   // столько места каждому углу
    const footerBottomPad = 2                 // зазор от чернил до нижней грани карточки
    let footerAsc = Math.round(t.statusSize * 0.72)
    let footerDesc = Math.round(t.statusSize * 0.2)
    let statusShown = ''
    let dueShown = ''
    if (hasFooter) {
      // Раскладка нижней строки. Приоритет (просьба Ярослава 03.10.26): ДАТА -> ЗНАЧКИ -> СТАТУС.
      // Значки важнее статуса: если на всё места не хватает, они занимают полосу статуса, а сам
      // статус убирается целиком — от обрезанного «В…» толку нет, а дата остаётся целой.
      // Без значков всё как было: подписи делят ширину пополам (maxSide).
      const availW = w - footerPad * 2
      const GAP = 5, MIN_STATUS = 14
      let stNat = 0, duNat = 0
      if (statusText) { ctx.font = `${t.statusWeight} ${t.statusSize}px ${t.statusFamily}`; stNat = ctx.measureText(statusText).width }
      if (dueText) { ctx.font = `${t.statusSize}px ${t.statusFamily}`; duNat = ctx.measureText(dueText).width }
      let duLim = maxSide, stLim = maxSide
      if (badges.length) {
        // Значки занимают полосу ТОЙ подписи, которой нет: нет даты — берут и её место
        // (просьба Ярослава 03.10.26), поэтому под отсутствующую подпись ничего не резервируем.
        duLim = dueText ? Math.max(16, Math.min(duNat, availW - badgeZone - GAP)) : 0
        // Статусу — остаток; мало места, значит значки его вытеснили.
        const rest = availW - (duLim ? duLim + GAP : 0) - badgeZone
        stLim = stNat ? (rest >= MIN_STATUS ? Math.min(stNat, rest) : 0) : 0
      }
      if (statusText && stLim > 0) {
        // У напоминания слева стоит повторение — оно длиннее даты («по будням», «ежемесячно»),
        // поэтому левой подписи отдаём всё место до даты, а не половину карточки: граница
        // сдвинута вправо, иначе слова обрезались многоточием (просьба Ярослава 01.10.26).
        let leftLim = stLim
        if (isRem && dueText) leftLim = Math.max(24, availW - duNat - 6)
        statusShown = fitText(ctx, t.titleUp ? statusText.toUpperCase() : statusText, leftLim)
        const mSt = ctx.measureText(statusShown)
        if (mSt.actualBoundingBoxAscent > 0) footerAsc = mSt.actualBoundingBoxAscent
        if (mSt.actualBoundingBoxDescent > 0) footerDesc = mSt.actualBoundingBoxDescent
      }
      if (dueText) {
        dueShown = fitText(ctx, dueText, duLim)
        const mDue = ctx.measureText(dueShown)
        if (mDue.actualBoundingBoxAscent > 0) footerAsc = Math.max(footerAsc, mDue.actualBoundingBoxAscent)
        if (mDue.actualBoundingBoxDescent > 0) footerDesc = Math.max(footerDesc, mDue.actualBoundingBoxDescent)
      }
    }
    // Высота нижней полосы: по чернилам подписей, но не ниже значка (он выше строки текста).
    const footerH = hasFooter
      ? Math.round(Math.max(footerAsc + footerDesc + footerBottomPad + 4, badgeS ? badgeS + 5 : 0))
      : 0
    const footerBaseline = h - footerBottomPad - footerDesc
    // Высота, доступная названию и описанию (низ карточки отдаём под статус/срок).
    const availH = Math.max(0, h - footerH)
    // Низ содержимого (шапка либо описание). Нижняя строка теперь у самой грани, но содержимое
    // всё равно не должно её задевать — эту полосу стерегут clamp'ы по footerH ниже.
    let contentBottom = 0

    // Название: в неоне — капсом. Сначала ставим шрифт, потом меряем (иначе перенос
    // считался по шрифту прошлого кадра).
    const raw = isRem ? this.reminderTimeText() : (t.titleUp ? String(this.title || '').toUpperCase() : String(this.title || ''))
    const setTitleFont = (size) => { ctx.font = `${t.titleWeight} ${size}px ${t.titleFamily}` }

    ctx.fillStyle = t.titleColor
    ctx.textBaseline = 'middle'
    ctx.textAlign = 'center'

    this._zoomBtn = null   // кнопка-лупа (телефон, ближний план) — пересчитывается ветками ниже
    if (viewScale < zoomDetail() || isRem) {   // напоминание всегда рисуем «крупно по центру»
      // СРЕДНИЙ/ДАЛЬНИЙ ПЛАН: название крупно, во всю карточку; описание не показываем.
      // Берём максимальный кегль из диапазона, при котором строки ещё влезают.
      let size = ZOOM_TITLE_MAX, lines = [], lineHeight = 0
      for (; size >= ZOOM_TITLE_MIN; size -= 1) {
        setTitleFont(size)
        lines = wrapText(ctx, raw, w - 14 - bellPad)
        lineHeight = Math.round(size * 1.12)
        if (lines.length * lineHeight <= availH - 2) break
      }
      if (lines.length * lineHeight > availH - 2) {   // совсем длинное имя — режем строки
        if (size < ZOOM_TITLE_MIN) {                  // цикл дошёл до минимума, не уложившись
          size = ZOOM_TITLE_MIN
          setTitleFont(size)
          lines = wrapText(ctx, raw, w - 14 - bellPad)
          lineHeight = Math.round(size * 1.12)
        }
        const keep = Math.max(1, Math.floor((availH - 2) / lineHeight))
        const rest = lines.slice(keep - 1).join(' ')
        lines = lines.slice(0, keep - 1)
        lines.push(fitText(ctx, rest, w - 14 - bellPad))
      }
      setTitleFont(size)
      // Название — по центру КАРТОЧКИ, а не области без нижней строки (просьба Ярослава
      // 01.10.26): статус и срок на центровку не влияют. Ограничение одно — блок не должен
      // зайти в полосу нижней строки, иначе последняя строка ляжет на статус/срок.
      const blockH = lines.length * lineHeight
      // У напоминания над временем стоит значок, поэтому центрируем в полосе ПОД ним
      // (иначе значок сверху и время «слипались»), у задачи — как было, по центру карточки.
      const cy = isRem
        ? Math.min(REM_ICON_BOTTOM + (h - footerH - REM_ICON_BOTTOM) / 2, h - footerH - blockH / 2)
        : Math.min(h / 2, h - footerH - blockH / 2)
      let y = Math.max(2, cy - blockH / 2) + lineHeight / 2
      for (const line of lines) {
        ctx.fillText(line, titleCx, y)
        y += lineHeight
      }
      contentBottom = y - lineHeight / 2
    } else {
      // БЛИЖНИЙ ПЛАН: название — в шапке сверху (как у обычной карточки).
      const top = 3
      let fontSize = t.titleSize, lineHeight = t.titleLine
      setTitleFont(fontSize)
      let lines = wrapText(ctx, raw, w - 24 - bellPad)
      if (lines.length * lineHeight > availH - 2) {   // очень длинное имя — чуть мельче
        fontSize = Math.max(9, t.titleSize - 2)
        lineHeight = Math.max(11, t.titleLine - 2)
        setTitleFont(fontSize)
        lines = wrapText(ctx, raw, w - 24 - bellPad)
      }
      // Шапка не должна съесть всю карточку: если есть описание — отдаём под неё не больше
      // половины высоты, а слишком длинное имя режем многоточием (иначе описание вылезало).
      const titleMax = descText ? Math.max(lineHeight, Math.floor((availH - top) * 0.5)) : availH - top - 1
      if (lines.length * lineHeight > titleMax) {
        const keep = Math.max(1, Math.floor(titleMax / lineHeight))
        const rest = lines.slice(keep - 1).join(' ')
        lines = lines.slice(0, keep - 1)
        lines.push(fitText(ctx, rest, w - 24 - bellPad))
        setTitleFont(fontSize)
      }
      let y = top + lineHeight / 2
      for (const line of lines) {
        ctx.fillText(line, titleCx, y)
        y += lineHeight
      }
      contentBottom = y - lineHeight / 2   // низ шапки — от него считаем положение надписей

      // Описание целиком: уменьшаем кегль от тематического, пока все строки не влезут.
      // Раскладка КЭШируется на карточке (05.10.26): при перетаскивании холста кадр берёт готовые
      // строки, а не раскладывает описание заново. На 5 000 знаков это было ~8 300 замеров текста
      // на каждый кадр — на телефоне при приближении карточки кадры проваливались.
      if (descText) {
        const descAvail = Math.max(0, availH - top - lines.length * lineHeight - 1)
        const layKey = [descText.length, descText.slice(0, 24), descText.slice(-24),
                        Math.round(w), Math.round(descAvail), t.descFamily, t.descSize].join('\u0001')
        let lay = this._descLayout
        if (!lay || lay.key !== layKey) {
          let size = t.descSize, dl = [], lh = 0
          for (; size >= MIN_DESC_SIZE; size = Math.round((size - 0.4) * 10) / 10) {
            ctx.font = `${size}px ${t.descFamily}`
            lh = Math.max(3, size * 1.16)
            const fits = Math.max(1, Math.floor(descAvail / lh))
            dl = wrapTextLimited(ctx, descText, w - 12, fits + 1)   // лишние строки не считаем
            if (dl.length <= fits) break
          }
          if (dl.length * lh > descAvail) {   // не влезло даже минимальным кеглем — обрезаем «…»
            const keep = Math.max(1, Math.floor(descAvail / lh))
            const ell = '…'
            ctx.font = `${size}px ${t.descFamily}`
            const tail = dl.slice(keep - 1).join(' ')
            dl = dl.slice(0, keep - 1)
            const fitted = fitText(ctx, tail, w - 12 - ctx.measureText(ell).width)
            dl.push(fitted.endsWith(ell) ? fitted : fitted + ell)   // «…» — признак обрезки
          }
          lay = { key: layKey, lines: dl, size, lh }
          this._descLayout = lay
        }
        const dl = lay.lines, size = lay.size, lh = lay.lh
        if (descAvail >= lh) {   // если места под описание не осталось — просто не рисуем
          ctx.font = `${size}px ${t.descFamily}`
          ctx.fillStyle = t.descColor
          // Описание — с левым выравниванием (просьба Ярослава 05.10.26: «обычное равнение
          // налево, а не по центру»). Отступ совпадает с боковым полем переноса (w - 12).
          ctx.textAlign = 'left'
          const descPadL = 6
          let dy = top + lines.length * lineHeight + lh / 2
          for (const line of dl) {
            ctx.fillText(line, descPadL, dy)
            dy += lh
          }
          contentBottom = dy - lh / 2   // низ описания — надписи идут следом за ним
        }
      }
    }

    // Кнопка-лупа «открыть описание целиком» (просьба Ярослава 05.10.26): только на телефоне и
    // только когда описание уже показано (ближний план). Левый верхний угол, ПРАВЕЕ порта входа —
    // сам порт врезан в угол и занимает область ~7×7 единиц, наехать на него нельзя.
    if (IS_PHONE && viewScale >= zoomDetail() && !isRem && descText) {
      const bs = 11                       // размер значка в единицах карточки (на телефоне ×3 ≈ 33 px)
      const bx = 9, by = 1.5              // правее порта входа, в полосе шапки
      drawZoomBtn(ctx, bx + bs / 2, by + bs / 2, bs, t.titleColor)
      const pad = 3                       // запас под палец (мишень мелкая)
      this._zoomBtn = { x: bx - pad, y: by - pad, w: bs + pad * 2, h: bs + pad * 2 }
    }

    if (hasFooter) {
      // Надписи посчитаны выше и прижаты к нижней грани (footerBaseline) — здесь только рисуем:
      // кегль не пересчитывается дважды и положение не «прыгает» между кадрами.
      ctx.textBaseline = 'alphabetic'
      if (statusShown) {
        ctx.font = `${t.statusWeight} ${t.statusSize}px ${t.statusFamily}`
        ctx.fillStyle = statusColorOf(isRem ? '' : (this.status || 'none'))
        ctx.textAlign = 'left'
        ctx.fillText(statusShown, footerPad, footerBaseline)
      }
      if (dueShown) {
        ctx.font = `${t.statusSize}px ${t.statusFamily}`
        ctx.fillStyle = t.dueColor
        ctx.textAlign = 'right'
        ctx.fillText(dueShown, w - footerPad, footerBaseline)
      }
      // Значок вложения — МЕЖДУ статусом и датой: ставим его в центр свободного промежутка
      // между ними, поэтому он никогда не наезжает на подписи. Не влез — не рисуем совсем
      // (место важнее значка), но тогда и клика по нему нет.
      if (badges.length) {
        // Размеры (badgeS/badgeW) посчитаны выше — вместе с полосой, которую мы уже отняли
        // у подписей. Здесь выбираем место: ряд значков по центру свободного коридора.
        ctx.font = `${t.statusWeight} ${t.statusSize}px ${t.statusFamily}`
        const stW = statusShown ? ctx.measureText(statusShown).width : 0
        ctx.font = `${t.statusSize}px ${t.statusFamily}`
        const duW = dueShown ? ctx.measureText(dueShown).width : 0
        const gapL = footerPad + stW + (stW ? 4 : 0)
        const gapR = w - footerPad - duW - (duW ? 4 : 0)
        const rowW = badges.length * badgeW + (badges.length - 1) * badgeGap
        // Не влез в коридор (статус и дата широкие) — центруем по карточке: подписи обрежутся
        // многоточием (fitText), а значки важнее и рисуются поверх всей нижней строки.
        let bx0 = (gapR - gapL >= rowW) ? (gapL + gapR) / 2 - rowW / 2 : w / 2 - rowW / 2
        bx0 = Math.max(2, Math.min(bx0, w - rowW - 2))
        // Опорная линия — по чернилам нижней строки, но с зажимом, иначе значки нижним краем
        // вылезали за грань карточки (замер 03.10.26: низ 57.3 при высоте 56).
        const cyb = Math.min(footerBaseline - (footerAsc - footerDesc) / 2, h - badgeS / 2 - 3)
        this._badges = []
        badges.forEach((p, i) => {
          const cx = bx0 + i * (badgeW + badgeGap) + badgeW / 2
      const kind = fileKind(p)
          drawFileBadge(ctx, kind, cx, cyb, badgeS, badgeTint(t, kind))
          // Область попадания: по 2px запаса (мишень мелкая), но СТРОГО внутри карточки.
          const rx = Math.max(0, cx - badgeW / 2 - 2), ry = Math.max(0, cyb - badgeS / 2 - 2)
          this._badges.push({ x: rx, y: ry, path: p,
                              w: Math.min(w, cx + badgeW / 2 + 2) - rx,
                              h: Math.min(h, cyb + badgeS / 2 + 2) - ry })
        })
      } else {
        this._badges = []
      }
    }

    // Значок напоминания: будильник СВЕРХУ ПО ЦЕНТРУ карточки (Ярослав 01.10.26).
    // Рисуем последним по тексту, но до портов: ширина глифа ⏰ ~16.5 px в 12px.
    if (this.kind === 'notify') {
      ctx.save()
      if (theme().mono) {
        // В монохромной теме эмодзи ⏰ остаётся цветным при любом шрифте — рисуем будильник линиями.
        drawBellMono(ctx, w / 2, 3, 12, t.titleColor)
      } else {
        ctx.font = '12px "Segoe UI Emoji", "Noto Color Emoji", sans-serif'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText('⏰', w / 2, 3)
      }
      ctx.restore()
    }

    // Порты (вариант 1): вход — кольцо, выход — точка; оба в цвете связи, врезаны в угол.
    // Рисуем последними, чтобы были поверх текста и по ним удобно было тянуть связь.
    const drawPort = (isInput) => {
      const color = portColor(this, isInput) || t.portIdle
      const [px, py] = portLocalPos(this, isInput)
      ctx.save()
      // Тени/свечения у портов нет (portGlow = 0 в темах, просьба Ярослава): гасим явно,
      // чтобы порт не подхватил тень от карточки, нарисованной до него.
      ctx.shadowBlur = 0
      ctx.shadowColor = 'transparent'
      if (t.portGlow) { ctx.shadowColor = color; ctx.shadowBlur = t.portGlow }
      ctx.beginPath()
      if (isInput) {
        // Кольцо вписываем так, чтобы его ВНЕШНИЙ край совпал с внешним краем точки на выходе
        // (у точки в темах A/B есть ещё тонкий контур 1px, поэтому внешний радиус = r + 0.5).
        // Раньше обводка шла по радиусу r и кольцо выглядело крупнее точки.
        const dotOuter = PORT.r + (t.portOutline ? 0.5 : 0)
        ctx.arc(px, py, dotOuter - PORT.ring / 2, 0, Math.PI * 2)
        ctx.lineWidth = PORT.ring
        ctx.strokeStyle = color
        ctx.stroke()
      } else {
        ctx.arc(px, py, PORT.r, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
        if (t.portOutline) {   // тонкий контур, чтобы точка читалась на светлой карточке
          ctx.shadowBlur = 0
          ctx.lineWidth = 1
          ctx.strokeStyle = t.portOutline
          ctx.stroke()
        }
      }
      ctx.restore()
    }
    drawPort(true)
    drawPort(false)

    ctx.textAlign = 'left'
    ctx.textBaseline = 'alphabetic'
  }
}
// Минимальный размер карточки = размер при создании.
// LiteGraph при перетаскивании уголка обрезает размер по computeSize():
//   desired_size[0] = Math.max(min_size[0], desired_size[0])
// а computeSize() без статического `size` считает минимум сам:
//   size[0] = max(вход+выход+10, ширина названия, LiteGraph.NODE_WIDTH = 140)
//   size[1] = кол-во слотов * NODE_SLOT_HEIGHT   (4 входа → 80)
// Отсюда симптом «растянул карточку — обратно к 100 она уже не возвращается».
// Со статическим `size` computeSize() сразу возвращает его (LiteGraph, строка 3677),
// поэтому минимум ресайза задаётся этой парой, а увеличивать по-прежнему можно сколько угодно.
// 01.10.26 (просьба Ярослава): минимальная ВЫСОТА уменьшена вдвое — 56 -> 28. Минимальная
// ширина осталась 100. Размер СОЗДАНИЯ новой карточки не меняется (см. this.size в конструкторе).
RectNode.size = [100, 28]
// Низ значка ⏰ на карточке-напоминании: время центрируется в свободной полосе ПОД ним
// (значок сверху по центру, просьба Ярослава 01.10.26), а не в середине всей карточки.
const REM_ICON_BOTTOM = 18
// Цвет карточки-напоминания по умолчанию (у задачи — '#5b8fd9').
const NOTIFY_COLOR = '#9b7bd9'
// В монохромной теме новая карточка-напоминания тоже серая (иначе в «Чёрно-Белой» фиолетовое пятно).
function notifyColor() { return theme().mono ? '#8e949c' : NOTIFY_COLOR }
LiteGraph.registerNodeType('rectnode', RectNode)

// --- State ---
// Язык интерфейса помним между запусками, как тему и сайдбар (localStorage['plannertate_lang']).
// Раньше он сбрасывался на русский при каждой перезагрузке — из-за этого, например, календарь
// после обновления страницы снова становился русским (замечание Ярослава 01.10.26).
// Язык: сохранённый выбор помним; если выбора ещё НЕ было (первый запуск/чистый профиль) —
// берём язык системы, чтобы на английской Windows приложение само открывалось английским
// (просьба Ярослава 04.10.26). Раньше всегда стартовал русский.
const savedLang = localStorage.getItem('plannertate_lang')
const lang = ref(
  (savedLang === 'en' || savedLang === 'ru') ? savedLang
    : (String(navigator.language || navigator.userLanguage || '').toLowerCase().indexOf('en') === 0 ? 'en' : 'ru')
)
watch(lang, (v) => {
  const code = v === 'en' ? 'en' : 'ru'
  try { localStorage.setItem('plannertate_lang', code) } catch (e) {}
  document.documentElement.lang = code        // и сама страница объявляет свой язык
}, { immediate: true })
// Только просмотр (04.10.26, просьба Ярослава): на телефоне/планшете открывается СОХРАНЁННАЯ копия
// страницы (origin appassets.androidplatform.net) — сохранить правки она всё равно не может, поэтому
// поля карточки и кнопки «Сохранить/Удалить» там неактивны. На компьютере всё как было.
const readOnly = ref(
  location.origin.indexOf('appassets.androidplatform.net') >= 0 ||
  localStorage.getItem('plannertate_readonly') === '1'
)
// Только просмотр (сохранённая копия на телефоне/планшете): правка всё равно не сохраняется.
// Ярослав 04.10.26: по «Сохранить/Удалить» (и остальным действиям) карточка просто ЗАКРЫВАЕТСЯ,
// без уведомлений — и так видно, что менять нельзя, раз все поля неактивны.
function roBlocked() {
  selectedNode.value = null
  if (liteCanvas && liteCanvas.selectNode) liteCanvas.selectNode(null, false)
}
const selectedNode = ref(null)
const inspectorPos = ref({ x: 12, y: 12 })
const showNotify = ref(false)
// Левый сайдбар сворачивается кнопкой «Свернуть» (просьба Ярослава 01.10.26).
// Состояние помним между запусками, как тему: localStorage['plannertate_side'] = '1' | '0'.
const sideOpen = ref(localStorage.getItem('plannertate_side') !== '0')
function setSideOpen(v) {
  sideOpen.value = !!v
  localStorage.setItem('plannertate_side', sideOpen.value ? '1' : '0')
  // Место освободившегося холста подхватит ResizeObserver на #canvasWrap (см. initCanvas).
}
const viewImage = ref('')   // data-URL рисунка, открытого на весь экран
// Узел, чьё описание открыто в полноэкранной читалке (кнопка-лупа на карточке, телефон).
const descReaderNode = ref(null)
const canvasEl = ref(null)
// Подсказка у значка ссылки: { x, y, name, path } или null (Ярослав 03.10.26).
const fileTip = ref(null)
// Тема: 'a' — стекло, 'b' — неон, 'c' — светлая. Выбор запоминается в localStorage.
// Если сохранена тема, которой больше нет в списке выбора (спрятана) — стартуем со стандартной.
const savedTheme = localStorage.getItem('plannertate_theme')
// Был ли у ЭТОГО браузера свой выбор темы. Нужно, чтобы сообщать телефону тему только со своего
// компьютера и только когда выбор действительно сделан: иначе чужой браузер в сети (или свежий
// профиль) при открытии страницы затёр бы тему хозяина своей, по умолчанию (03.10.26).
const hadSavedTheme = THEME_IDS.includes(savedTheme)
const themeName = ref(hadSavedTheme ? savedTheme : 'a')
// 30.09.26: тем стало 12, поэтому в сайдбаре видна только активная, а полный список
// (все 12 с мини-превью) открывается по клику. Просьба Ярослава: «сделать так, чтобы
// они все не представлялись, а там можно было выбирать какую тему».
const themeOpen = ref(false)
// Настройки «Своей» темы показываются при её выборе и прячутся кнопкой «Сохранить»
// (Ярослав 03.10.26). Повторный выбор «Своей» в списке — снова раскрывает.
const customOpen = ref(false)
function pickTheme(id) { themeName.value = id; themeOpen.value = false; customOpen.value = id === CUSTOM_ID }

// Открывая список тем, подкручиваем его так, чтобы ВЫБРАННАЯ тема встала первой видимой строкой,
// а темы выше просто ушли за верхний край (просьба Ярослава 03.10.26: «чтобы колесо прокрутки
// было настроено на текущую тему»). Список уже отсортирован по THEME_IDS — порядок не меняем.
const themePopEl = ref(null)
function toggleThemeList() {
  themeOpen.value = !themeOpen.value
  if (!themeOpen.value) return
  // Ждём отрисовки списка (v-if) — до неё элементов ещё нет в DOM.
  nextTick(() => {
    const box = themePopEl.value
    if (!box) return
    const el = box.querySelector('.theme-item.on')
    if (!el) return
    // offsetTop пункта отсчитывается от padding-края .theme-pop (она position:absolute —
    // offsetParent). Вычитаем только внутренний отступ: тогда выбираемая тема встаёт ровно на
    // ту же линию, где стоит первый пункт неоткрытого списка (без сдвига на рамку).
    const pad = parseFloat(getComputedStyle(box).paddingTop) || 0
    box.scrollTop = Math.max(0, el.offsetTop - pad)
  })
}

// --- «Своя» тема (конструктор) ----------------------------------------------
// Ярослав 03.10.26: «последней темой добавь свою — выбираешь интерфейс из существующих тем
// и шрифт любой из системы, размер, жирность и капслок для названий карточек».
// Палитра — у выбранной базовой темы; шрифт/размер/жирность/капс названий — свои.
const custom = ref(customCfg())
const fontBusy = ref(false)
// Базовый набор (Windows). Кнопкой «Загрузить шрифты системы» список пополняется всеми
// установленными шрифтами через Local Font Access API (secure context; localhost подходит,
// браузер спросит разрешение). Если API нет/отказано — остаётся этот набор.
const FONTS_BASE = ['Segoe UI', 'Arial', 'Calibri', 'Cambria', 'Candara', 'Consolas', 'Constantia',
  'Corbel', 'Courier New', 'Franklin Gothic Medium', 'Gabriola', 'Georgia', 'Impact', 'Lucida Console',
  'Lucida Sans Unicode', 'Microsoft Sans Serif', 'Palatino Linotype', 'Segoe Print', 'Segoe Script',
  'Sylfaen', 'Tahoma', 'Times New Roman', 'Trebuchet MS', 'Verdana', 'Bahnschrift', 'Cascadia Code',
  'Cascadia Mono', 'Century Gothic', 'Comic Sans MS', 'Garamond', 'Rockwell', 'Arial Black', 'Arial Narrow']
const fontList = ref(FONTS_BASE.slice())
function customSet(p) {
  custom.value = setCustom(p)
  pushThemeToServer(themeName.value)   // настройки «Своей» темы тоже уезжают телефону
  applyTheme(themeName.value)      // пересобрать холст (data-theme/--ui-font + титулы)
}
async function loadSystemFonts() {
  if (fontBusy.value) return
  fontBusy.value = true
  try {
    if (typeof window.queryLocalFonts !== 'function') throw new Error('no-api')
    const list = await window.queryLocalFonts()
    const fams = [...new Set(list.map(f => f && f.family).filter(Boolean))].sort((a, b) => a.localeCompare(b))
    fontList.value = [...new Set([...fams, ...FONTS_BASE])]
  } catch (e) {
    fontList.value = FONTS_BASE.slice()
  } finally { fontBusy.value = false }
}
// Пикер шрифта — СВОЙ выпадающий список, а не <datalist>: нативный datalist в Chrome после
// выбора значения повторно не раскрывается (баг, замечен Ярославом 03.10.26). Здесь список
// открывается по клику всегда; сверху — поиск, снизу — подтяжка системных шрифтов.
const fontOpen = ref(false)
const fontQuery = ref('')
const fontShown = computed(() => {
  const q = fontQuery.value.trim().toLowerCase()
  const l = q ? fontList.value.filter(f => f.toLowerCase().includes(q)) : fontList.value
  return l.slice(0, 300)
})
function pickFont(f) {
  customSet({ font: String(f || '').trim() })
  fontOpen.value = false
  fontQuery.value = ''
}
let liteCanvas = null, graph = null
let removeTouchSupport = null   // снятие обработчиков касаний (см. src/touch.js)

function t(k) { return L18N[lang.value][k] }

async function initCanvas() {
  if (!canvasEl.value) return
  // Холст ещё не расcтанован (width < 10): ждём layout, а не прерываемся — иначе приложение "мёртво".
  if (canvasEl.value.clientWidth < 10) {
    requestAnimationFrame(() => setTimeout(initCanvas, 30))
    return
  }

  graph = new LGraph()
  // Касания на телефоне: LiteGraph по умолчанию слушает только мышь ("mouse"),
  // а от пальца приходят Pointer Events — переключаемся на них ПЕРЕД созданием
  // холста (имя события берётся в момент подписки). Мышь pointer-события тоже
  // шлёт, поэтому на компьютере поведение прежнее. Щипок двумя пальцами в
  // библиотеке не реализован — его доводит src/touch.js.
  LiteGraph.pointerevents_method = 'pointer'
  liteCanvas = new LGraphCanvas(canvasEl.value, graph)
  removeTouchSupport = installTouchSupport(canvasEl.value, liteCanvas)
  // Зум колесом: снимаем мёртвый библиотечный 'mousewheel' (иначе, если браузер пришлёт оба
  // события, холст прыгнет на двойной шаг) и ведём колесо сами по современному 'wheel'.
  // passive: false обязателен — processMouseWheel зовёт preventDefault, чтобы страница не ехала.
  canvasEl.value.removeEventListener('mousewheel', liteCanvas._mousewheel_callback)
  canvasEl.value.removeEventListener('DOMMouseScroll', liteCanvas._mousewheel_callback)
  canvasEl.value.addEventListener('wheel', onCanvasWheel, { passive: false })
  // Подсказка у значков ссылок (Ярослав 03.10.26). Прячем при уходе курсора и нажатии.
  canvasEl.value.addEventListener('mousemove', onCanvasHover)
  canvasEl.value.addEventListener('mouseleave', hideFileTip)
  canvasEl.value.addEventListener('mousedown', hideFileTip)
  liteCanvas.clear()
  resizeCanvas()
  const ro = new ResizeObserver(() => resizeCanvas())
  ro.observe(document.getElementById('canvasWrap'))

  // setTheme — для верификаторов из workspace/ (кликать по выпадающему списку
  // из Playwright неудобно: список нужно сначала раскрыть).
  window.__plannertate = { graph, liteCanvas, field: FIELD, setTheme: (id) => { themeName.value = id } }

  // Применяем тему к холсту (фоновая сетка, стиль связей, радиус скругления).
  applyCanvasTheme(liteCanvas)

  // Сначала пробуем поднять последний сохранённый граф (graph.json через /api/load).
  // Демо-узлы создаём только если сохранения нет — иначе они перекрыли бы данные.
  const loaded = await loadGraph()
  if (!loaded) createDemoNodes()
  // Графы прошлых версий держали одну ссылку в поле file — переводим её в список files
  // и убираем старое поле, чтобы оно не тянулось дальше.
  for (const n of (graph._nodes || [])) {
    if (!Array.isArray(n.files)) n.files = n.file ? [n.file] : []
    if (n.file) delete n.file
  }

  // Панели устройств («Смартфон»/«Планшет») — системные плитки: создаём при загрузке,
  // если их ещё нет (см. ensureDevicePanels).
  ensureDevicePanels()

  // Активное окно в 8 раз больше + содержимое в его середине (см. FIELD_AREA_X).
  applyFieldView()
  armAutoSave()   // с этого момента любое изменение карточек сохраняется автоматически

  // Двойной щелчок по пустому месту — НИЧЕГО не создаётся (по карточке — подзадача, см. onDblClick).
  // Отключаем ВНУТРЕННИЙ обработчик LiteGraph: по умолчанию двойной щелчок по
  // пустому месту вызывает showSearchBox (палитра/окно с типами нодов + нижняя
  // тёмно-синяя панель). onDblClick = () => {} глушит и двойной щелчок по узлу.
  liteCanvas.allow_searchbox = false
  liteCanvas.onDblClick = () => {}

  // Правый клик по карточке обслуживает НАШ inspector, поэтому встроенное меню
  // LiteGraph (Inputs / Properties / Title / Mode / Resize / Collapse / Pin /
  // Colors / Shapes / Remove / Clone) гасим — иначе оно перекрывает панель.
  // Выделение узла при этом остаётся: его делает processMouseDown до этого вызова.
  liteCanvas.processContextMenu = () => {}

  // Панель открывается ТОЛЬКО правым кликом (см. onContextMenu). Левый клик по карточке
  // её не открывает (раньше вылезала на любое выделение); клик по пустому месту — закрывает.
  liteCanvas.onSelectionChange = (sel) => {
    const arr = Object.keys(sel || {})
    if (!arr.length) selectedNode.value = null
  }

  // Двойной клик по карточке создаёт подзадачу со связью (см. onDblClick), по пустому месту —
  // ничего; узел добавляется кнопкой «+ Задача» в сайдбаре.
  canvasEl.value.addEventListener('dblclick', onDblClick)
  // правый клик по карточке — открыть редактирование в инспекторе
  canvasEl.value.addEventListener('contextmenu', onContextMenu)
  // рисунки: перетаскивание файла прямо на карточку (Ctrl+V обрабатывается на уровне документа)
  canvasEl.value.addEventListener('dragover', onDragOver)
  canvasEl.value.addEventListener('drop', onCanvasDrop)
  // клик по треугольнику на середине связи — удаление связи (+ подсветка при наведении)
  liteCanvas.onMouse = onMouse
  canvasEl.value.addEventListener('pointermove', onCanvasMouseMove)
  canvasEl.value.addEventListener('pointerleave', () => setHoveredLink(null))
  // подзадачи едут за перетаскиваемым родителем (см. onDocMouseMove)
  // capture: наш обработчик обязан отработать ДО обработчиков LiteGraph, иначе точка отсчёта
  // не будет выставлена к моменту, как библиотека начнёт двигать карточку.
  // ВАЖНО (02.10.26): здесь именно pointer-события, а НЕ мышиные. Холст работает на pointer
  // (иначе не работают касания), и LiteGraph гасит pointerdown через preventDefault — после этого
  // браузер не присылает совместимые mousedown/mousemove, и «верёвочка» молча переставала
  // работать на компьютере. Замер: pointerdown 1, mousedown 0, mousemove 0.
  canvasEl.value.addEventListener('pointerdown', onCanvasMouseDown, true)
  document.addEventListener('pointerdown', onDocMouseDownCapture, true)   // Ctrl+клик — копия карточки
  document.addEventListener('pointermove', onDocMouseMove)
  document.addEventListener('pointerup', onDocMouseUp)

  animate()
}

// Демо-граф: показывается только при первом запуске, когда graph.json ещё пуст.
// bgcolor не задаём — заливку карточки рисует активная тема (см. onDrawBackground).
function createDemoNodes() {
  // Названия — на языке интерфейса: на английском приложение показывает Project / Stage 1 / Stage 2
  // (просьба Ярослава 04.10.26). Раньше были жёстко русскими.
  const n1 = graph.add(new RectNode()); n1.pos = [120, 200]; n1.title = t('demoRoot')
  n1.color = '#5b8fd9'; n1.status = 'wip'; n1.due = '2026-10-10'
  const n2 = graph.add(new RectNode()); n2.pos = [460, 130]; n2.title = t('demoStage') + ' 1'
  n2.color = '#7bc67b'; n2.status = 'done'
  const n3 = graph.add(new RectNode()); n3.pos = [460, 320]; n3.title = t('demoStage') + ' 2'
  n3.color = '#e6c34a'; n3.status = 'waiting'; n3.due = '2026-10-25'

  const mkLink = (from, to) => { try { from.connect(0, to, 0) } catch (e) {} }
  setTimeout(() => { mkLink(n1, n2); mkLink(n1, n3) }, 60)
}

function resizeCanvas() {
  if (!liteCanvas || !canvasEl.value) return
  const w = canvasEl.value.clientWidth, h = canvasEl.value.clientHeight
  liteCanvas.resize(w, h)
  updateField()   // область меряется от окна: при изменении размера пересчитывается
}

// Ставит вид на середину содержимого графа (масштаб 1 — карточки прежнего размера).
// screenX = (graphX + ds.offset[0]) * ds.scale  =>  offset = размер/(2*scale) - центр содержимого.
function applyFieldView() {
  if (!liteCanvas || !canvasEl.value || !graph) return
  updateField()
  const ds = liteCanvas.ds
  ds.scale = 1
  const w = canvasEl.value.clientWidth, h = canvasEl.value.clientHeight
  const nodes = graph._nodes || []
  let bx = 0, by = 0
  if (nodes.length) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
    for (const n of nodes) {
      const [x, y] = n.pos, [nw, nh] = n.size
      x0 = Math.min(x0, x); y0 = Math.min(y0, y)
      x1 = Math.max(x1, x + nw); y1 = Math.max(y1, y + nh)
    }
    bx = (x0 + x1) / 2; by = (y0 + y1) / 2
  }
  ds.offset = [w / (2 * ds.scale) - bx, h / (2 * ds.scale) - by]
}

// Экран -> координаты графа (та же формула, что у LiteGraph.adjustMouseEvent).
// canvasX = (clientX - rect.left) / ds.scale - ds.offset[0]
function screenToGraph(px, py) {
  if (!liteCanvas || !canvasEl.value) return [px, py]
  const ds = liteCanvas.ds
  const rect = canvasEl.value.getBoundingClientRect()
  const x = px - rect.left, y = py - rect.top
  return [x / (ds.scale || 1) - (ds.offset[0] || 0),
          y / (ds.scale || 1) - (ds.offset[1] || 0)]
}

// --- Тема оформления ---------------------------------------------------------
// Интерфейс (сайдбар, панели, кнопки) переключается атрибутом data-theme на <html>:
// значения переменных лежат в styles.css. Canvas (карточки, связи, фоновая сетка)
// читает палитру из themes.js, поэтому тему надо «применить» и к холсту.
const THEME_KEY = 'plannertate_theme'

function applyTheme(id) {
  const t = setActiveTheme(id)
  // У «Своей» темы (CUSTOM_ID) своего CSS-блока нет: палитру берём у БАЗОВОЙ темы (t.base),
  // а шрифт интерфейса подставляем переменной --ui-font. Прочие темы работают как раньше.
  document.documentElement.dataset.theme = t.base || t.id
  applyUiFont(t)
  try { localStorage.setItem(THEME_KEY, t.id) } catch (e) {}
  if (liteCanvas) { applyCanvasTheme(liteCanvas); liteCanvas.setDirty(true, true) }
}

// Тема уезжает на телефон (03.10.26, просьба Ярослава): телефону тему из браузера не видно,
// поэтому компьютер отдаёт выбранную тему серверу, а телефон забирает её при синхронизации.
// Ошибку глотаем: упавшая отправка темы не повод мешать работе.
function pushThemeToServer(id) {
  // На ТЕЛЕФОНЕ тему на сервер НЕ отправляем (просьба Ярослава 05.10.26): выбор темы на телефоне —
  // это выбор самого телефона, он не должен менять тему компьютера.
  if (IS_PHONE) return
  // Кто «свой», решает СЕРВЕР по адресу запроса (см. _owner_machine в backend.py): страницу
  // можно открыть и по сетевому адресу, а браузер этого не различает — из-за этой проверки
  // тема могла не уезжать вовсе (разбор бага 03.10.26).
  try {
    fetch('/api/ui_state', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: id, custom: customCfg() }),
    }).catch(() => {})
  } catch (e) {}
}

// Шрифт интерфейса для «Своей» темы — выбранный в настройках (иначе переменную снимаем).
function applyUiFont(t) {
  const fam = (t.id === CUSTOM_ID && t.custom && t.custom.font) ? String(t.custom.font).replace(/"/g, '') : ''
  if (fam) document.documentElement.style.setProperty('--ui-font', '"' + fam + '", "Segoe UI", system-ui, sans-serif')
  else document.documentElement.style.removeProperty('--ui-font')
}

function applyCanvasTheme(lc) {
  const t = theme()
  // Фон холста рисуем сами: градиент/пятна — CSS (.canvas-wrap), а сетку — onDrawBackground
  // (он вызывается внутри трансформации графа, поэтому сетка панорамируется вместе с ним).
  lc.clear_background = true        // штатная очистка фонового слоя — нужна, иначе сетка «размазывается»
  lc.clear_background_color = null  // …но серый прямоугольник LiteGraph не рисуем
  lc.background_image = null        // и его картинку-сетку тоже выключаем
  // LiteGraph по умолчанию обводит холст рамкой по периметру:
  //   if (this.render_canvas_border) { ctx.strokeStyle = "#235"; ctx.strokeRect(0,0,canvas.width,canvas.height) }
  // (litegraph.core.js, ~8502). Линия в 1 px лежит ровно на границе канваса, поэтому видна
  // половинкой пикселя (замер: rgba(34,50,84,0.5) по всем четырём сторонам) — на светлой теме
  // это заметный серый прямоугольник вокруг всего фона. Флаг выключаем целиком.
  lc.render_canvas_border = false
  // Ещё один служебный рисунок LiteGraph — серая строка статистики внизу холста
  // («Nodes: …», «FPS: …»): renderInfo() рисует её шрифтом 10px Arial цветом #888
  // в точке (0, height-80) и включается флагом show_info (по умолчанию true, ~5373).
  // На светлой теме это единственные серые пятна на ровном фоне — гасим.
  lc.show_info = false
  lc.round_radius = t.canvas.roundRadius
  lc.connections_width = t.canvas.linkWidth
  lc.render_connections_border = !!t.canvas.linkBorder
  lc.default_link_color = '#8892b0'
  // Заводские цвета портов и «призрака» перетаскиваемой связи у LiteGraph зелёные (#7F7):
  // сами точки гасим (их рисует тема), а призрак красим в цвет темы.
  const ghost = t.canvas.ghost || '#8fa4c8'
  lc.default_connection_color = {
    input_off: 'rgba(0,0,0,0)', input_on: 'rgba(0,0,0,0)',
    output_off: 'rgba(0,0,0,0)', output_on: 'rgba(0,0,0,0)',
  }
  lc.default_connection_color_byType = { '*': ghost }
  lc.default_connection_color_byTypeOff = { '*': ghost }
  lc.onDrawBackground = (ctx) => {
    viewScale = (lc.ds && lc.ds.scale) || 1   // нужен карточкам: выбор плана отображения
    // Рамку вокруг всей рабочей области убрали 01.10.26 (просьба Ярослава: «удали ещё границы,
    // которые вокруг всей области») — холст теперь ровный, сетка идёт по всей видимой части.
    drawThemeGrid(ctx, lc)
  }
  // Связи: цвет — от узла-источника, свечение — из темы. Оборачиваем renderLink один раз.
  // Заодно меняем заводской кружок на середине связи: LiteGraph рисует его через ctx.arc,
  // поэтому на время штатной отрисовки глушим arc (у связи arc больше нигде не нужен —
  // линия рисуется кривыми и отрезками) и вместо кружка рисуем закрашенный ТРЕУГОЛЬНИК,
  // повёрнутый по касательной в середине связи, то есть остриём туда, куда связь идёт.
  if (!lc.__plannertateLinkWrap) {
    lc.__plannertateLinkWrap = true
    const orig = lc.renderLink.bind(lc)
    lc.renderLink = function (ctx, a, b, link, skip_border, flow, color, start_dir, end_dir, num_sublines) {
      const th = theme()
      const origin = link && link.origin_id != null ? this.graph.getNodeById(link.origin_id) : null
      const c0 = color || (origin ? linkColorOf(origin.color) : '#8892b0')
      // Цвет связи. Тема задаёт СВОЙ цвет связи, а цвет карточки-источника остаётся в нём лишь
      // оттенком (linkCardMix) — так видно, от кого идёт связь, но линия читается как часть темы.
      // Просьба Ярослава 02.10.26: связи во всех темах были одного цвета (цвет карточки).
      // У темы без linkColor (Неон) всё как было — цвет карточки целиком.
      const thLink = th.canvas.linkColor
      const keep = th.canvas.linkCardMix == null ? 1 : th.canvas.linkCardMix
      const c = (thLink && !color && typeof c0 === 'string' && c0[0] === '#') ? tintHex(c0, thLink, keep) : c0
      const glow = th.canvas.linkGlow
      const la = th.canvas.linkAlpha == null ? 1 : th.canvas.linkAlpha
      ctx.save()
      ctx.globalAlpha = la
      if (glow) {
        ctx.shadowBlur = glow
        ctx.shadowColor = (typeof c === 'string' && c[0] === '#') ? rgba(c, th.canvas.linkGlowAlpha) : c
      }
      const realArc = ctx.arc
      ctx.arc = () => {}   // заводской кружок в середине связи не рисуем
      try {
        orig(ctx, a, b, link, skip_border, flow, c, start_dir, end_dir, num_sublines)
      } finally {
        ctx.arc = realArc
      }
      ctx.restore()

      if (link && link._pos) {
        // направление: касательная в середине связи (по ней же LiteGraph считает link._pos)
        const p0 = this.computeConnectionPoint(a, b, 0.45, start_dir, end_dir)
        const p1 = this.computeConnectionPoint(a, b, 0.55, start_dir, end_dir)
        const ang = Math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        const L = ARROW_LEN   // длина треугольника в координатах графа
        ctx.save()
        ctx.globalAlpha = la
        ctx.translate(link._pos[0], link._pos[1])
        ctx.rotate(ang)
        ctx.beginPath()
        ctx.moveTo(L * 0.6, 0)              // острие — вперёд по направлению связи
        ctx.lineTo(-L * 0.4, -L * 0.45)
        ctx.lineTo(-L * 0.4, L * 0.45)
        ctx.closePath()
        ctx.fillStyle = c
        ctx.fill()
        if (th.canvas.linkBorder) {          // тонкий контур — чтобы треугольник читался на линии
          ctx.lineWidth = 1
          ctx.strokeStyle = th.canvas.linkBorder
          ctx.stroke()
        }
        ctx.restore()
      }
    }
  }
}

// Смешивание двух цветов '#rrggbb': keep — доля первого (базового) цвета, остальное — от target.
// Нужно для связей: цвет карточки-источника остаётся оттенком в цвете темы.
function tintHex(base, target, keep) {
  const parse = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
  const a = parse(base), b = parse(target)
  return '#' + a.map((v, i) => {
    const m = Math.round(v * keep + b[i] * (1 - keep))
    return Math.max(0, Math.min(255, m)).toString(16).padStart(2, '0')
  }).join('')
}

// Фоновая сетка: точки (темы A и C) или тонкие линии (тема B), в координатах графа.
function drawThemeGrid(ctx, lc) {
  const spec = theme().grid
  // Тема может выключить сетку совсем: type 'none' (светлая тема — ровный фон,
  // просьба Ярослава 30.09.26: «убери точки, сделай одним цветом»).
  if (!spec || spec.type === 'none') return
  const scale = (lc.ds && lc.ds.scale) || 1
  if (!spec.screen && scale < spec.minScale) return
  const va = lc.visible_area
  if (!va) return
  // Сетка, закреплённая В ОКНЕ (тема «Чертёж», 01.10.26, просьба Ярослава: «в видимой части и стоит
  // на месте при панораме — за ней пусто»). Рисуется в экранных координатах: шаг задан в пикселях
  // окна, положение отсчитывается от левого верхнего угла холста, поэтому сетка не едет вместе с
  // графом при панораме и не меняет шаг при зуме — она работает как линейка окна. Толщина линии
  // пересчитывается в 1/scale, чтобы на экране оставался ровно 1 px.
  if (spec.screen) {
    const ds = lc.ds || { scale: 1, offset: [0, 0] }
    const sc = ds.scale || 1
    const cw = ctx.canvas.clientWidth || ctx.canvas.width
    const chh = ctx.canvas.clientHeight || ctx.canvas.height
    const gx0 = -ds.offset[0], gy0 = -ds.offset[1]
    const gx1 = gx0 + cw / sc, gy1 = gy0 + chh / sc
    ctx.save()
    ctx.strokeStyle = spec.color
    ctx.lineWidth = 1 / sc
    ctx.beginPath()
    for (let sx = 0; sx <= cw; sx += spec.spacing) { const x = gx0 + sx / sc; ctx.moveTo(x, gy0); ctx.lineTo(x, gy1) }
    for (let sy = 0; sy <= chh; sy += spec.spacing) { const y = gy0 + sy / sc; ctx.moveTo(gx0, y); ctx.lineTo(gx1, y) }
    ctx.stroke()
    ctx.restore()
    return
  }
  // Сетка рисуется по ВСЕЙ видимой части холста: внутри рамки активного окна и за ней — одинаково
  // (просьба Ярослава 01.10.26: «Сделай фон в рамке и за рамкой одинаковой»). Раньше сетку я обрезал
  // по рамке, и за линией фон выглядел иначе. Рамка остаётся только как линия-ориентир.
  const bx0 = va[0], by0 = va[1]
  const bx1 = va[0] + va[2], by1 = va[1] + va[3]
  const step = spec.spacing
  const x1 = bx1, y1 = by1
  const x0 = Math.floor(bx0 / step) * step, y0 = Math.floor(by0 / step) * step
  ctx.save()
  if (spec.type === 'lines') {
    ctx.strokeStyle = spec.color
    ctx.lineWidth = 1 / scale
    ctx.beginPath()
    for (let x = x0; x <= x1; x += step) { ctx.moveTo(x, by0); ctx.lineTo(x, y1) }
    for (let y = y0; y <= y1; y += step) { ctx.moveTo(bx0, y); ctx.lineTo(x1, y) }
    ctx.stroke()
  } else {
    // при мелком зуме прореживаем, чтобы не рисовать десятки тысяч точек
    let s = step
    let r = spec.r / scale
    const cols = Math.ceil((x1 - x0) / step) + 1
    const rows = Math.ceil((y1 - y0) / step) + 1
    if (cols * rows > 9000) { s = step * 2; r = r * 1.6 }
    const sx = Math.floor(bx0 / s) * s, sy = Math.floor(by0 / s) * s
    ctx.fillStyle = spec.color
    for (let x = sx; x <= x1; x += s) {
      for (let y = sy; y <= y1; y += s) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill() }
    }
  }
  ctx.restore()
}

// --- Клик по треугольнику на середине связи удаляет связь -------------------
// LiteGraph кладёт середину связи в link._pos (renderLink → computeConnectionPoint(a,b,0.5,…)),
// а сам кружок в этом месте мы заменили закрашенным треугольником по направлению связи
// (см. обёртку renderLink выше) — цель клика та же: середина связи.
// Ловим клик по нему в хуке onMouse: он вызывается в начале processMouseDown уже
// ПОСЛЕ adjustMouseEvent (значит canvasX/canvasY — координаты графа), а return true
// отменяет штатную обработку LiteGraph (выделение, старт перетаскивания связи).
const LINK_DOT_RADIUS = 10   // пиксели экрана

// Значок вложения на карточке: попадание считаем по прямоугольнику, который записала
// отрисовка (в ЛОКАЛЬНЫХ координатах узла) — так же, как LiteGraph ищет свои области.
function fileBadgeAt(gx, gy) {
  if (!graph) return ''
  for (const n of (graph._nodes || [])) {
    const bs = n._badges
    if (!bs || !bs.length) continue
    const lx = gx - n.pos[0], ly = gy - n.pos[1]
    for (const b of bs) {
      if (lx >= b.x && lx <= b.x + b.w && ly >= b.y && ly <= b.y + b.h) return b.path
    }
  }
  return ''
}

// Подсказка при наведении на значок ссылки: имя файла и путь целиком (просьба Ярослава 03.10.26).
// Своя подсказка, а не библиотечная: у LiteGraph подсказка одна на узел, а значков на карточке
// до пяти — попадание по каждому у нас уже есть (fileBadgeAt), остаётся показать текст.
function hideFileTip() { if (fileTip.value) fileTip.value = null }
// ЗУМ КОЛЕСОМ. LiteGraph 0.7.18 вешает приближение ТОЛЬКО на устаревшее событие 'mousewheel',
// которое Chrome больше не присылает: событие 'wheel' до холста доходило, а масштаб не менялся
// (проверено пробой 03.10.26; прямой вызов liteCanvas.processMouseWheel при этом работал).
// Поэтому библиотечный обработчик снимаем и отдаём событие ему же сами — по 'wheel'.
function onCanvasWheel(ev) {
  hideFileTip()
  if (!liteCanvas) return
  // processMouseWheel читает wheelDeltaY (устаревшее поле), знак — как у wheelDelta: вверх = плюс.
  const k = ev.deltaMode === 1 ? 16 : (ev.deltaMode === 2 ? 100 : 1)
  const wd = (typeof ev.wheelDelta === 'number' && ev.wheelDelta) ? ev.wheelDelta : -ev.deltaY * k
  // Свойство у WheelEvent только для чтения — подставляем через defineProperty, иначе в строгом
  // режиме (ES-модуль) обычное присваивание бросает исключение.
  try { Object.defineProperty(ev, 'wheelDeltaY', { value: wd, writable: true, configurable: true }) } catch (e) {}
  liteCanvas.processMouseWheel(ev)
}
function onCanvasHover(ev) {
  if (!graph || !liteCanvas) { hideFileTip(); return }
  // Во время перетаскивания карточки или тяги связи подсказка только мешает.
  if (liteCanvas.node_dragged || liteCanvas.connecting_node) { hideFileTip(); return }
  const [gx, gy] = screenToGraph(ev.clientX, ev.clientY)
  const path = fileBadgeAt(gx, gy)
  if (!path) { hideFileTip(); return }
  // Держим подсказку внутри окна: у правого/нижнего края разворачиваем её в другую сторону.
  const x = Math.min(ev.clientX + 14, Math.max(4, window.innerWidth - 340))
  const y = Math.min(ev.clientY + 18, Math.max(4, window.innerHeight - 64))
  const cur = fileTip.value
  if (cur && cur.path === path && cur.x === x && cur.y === y) return   // зря не дёргаем реактивность
  fileTip.value = { x, y, name: shortFileName(path), path }
}

// Кнопка-лупа на карточке (телефон, ближний план): попадание — по прямоугольнику, который записала
// отрисовка (локальные координаты узла). Возвращаем сам узел: его описание открываем в читалке.
function zoomBtnNodeAt(gx, gy) {
  if (!graph) return null
  for (const n of (graph._nodes || [])) {
    const b = n._zoomBtn
    if (!b) continue
    const lx = gx - n.pos[0], ly = gy - n.pos[1]
    if (lx >= b.x && lx <= b.x + b.w && ly >= b.y && ly <= b.y + b.h) return n
  }
  return null
}

function linkDotAt(gx, gy) {
  if (!graph || !liteCanvas) return null
  const scale = (liteCanvas.ds && liteCanvas.ds.scale) || 1
  const r = LINK_DOT_RADIUS / scale
  let best = null, bestD = r
  for (const id in graph.links) {
    const link = graph.links[id]
    if (!link) continue
    let p = link._pos
    if (!p || (p[0] === 0 && p[1] === 0)) {
      // _pos заполняется при отрисовке; если связи ещё не рисовались — считаем сами
      const a = graph.getNodeById(link.origin_id), b = graph.getNodeById(link.target_id)
      if (!a || !b) continue
      const p0 = a.getConnectionPos(false, link.origin_slot)
      const p1 = b.getConnectionPos(true, link.target_slot)
      p = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2]
    }
    const d = Math.hypot(gx - p[0], gy - p[1])
    if (d < bestD) { bestD = d; best = link }
  }
  return best
}

let hoveredLink = null
function setHoveredLink(link) {
  if (!liteCanvas) return
  liteCanvas.highlighted_links = liteCanvas.highlighted_links || {}
  if (hoveredLink === link) return
  if (hoveredLink) delete liteCanvas.highlighted_links[hoveredLink.id]
  hoveredLink = link || null
  if (hoveredLink) liteCanvas.highlighted_links[hoveredLink.id] = true   // LiteGraph красит такую связь белым
  liteCanvas.setDirty(true, true)
}

// Наведение: подсвечиваем связь и треугольник (связь становится белой — «клик удалит»).
function onCanvasMouseMove(ev) {
  if (!graph || !liteCanvas) return
  const [gx, gy] = screenToGraph(ev.clientX, ev.clientY)
  setHoveredLink(linkDotAt(gx, gy))
}

// Клик по треугольнику — удаляем связь.
function onMouse(ev) {
  if (ev.which !== 1) return false
  // Клик по значку вложения — открыть ИМЕННО ЭТОТ файл системной программой (Ярослав 03.10.26).
  const badgePath = fileBadgeAt(ev.canvasX, ev.canvasY)
  if (badgePath) { openFileLink(badgePath, nodeWithFile(badgePath)); return true }
  // Кнопка-лупа (телефон): открыть описание целиком в полноэкранной читалке.
  const zoomNode = zoomBtnNodeAt(ev.canvasX, ev.canvasY)
  if (zoomNode) { descReaderNode.value = zoomNode; return true }
  const link = linkDotAt(ev.canvasX, ev.canvasY)
  if (!link) return false
  setHoveredLink(null)
  graph.removeLink(link.id)   // сам снимает и с выхода, и со входа
  onNodeChange()
  return true                 // штатную обработку LiteGraph пропускаем
}

// Создаёт карточку с центром в точке графа (cx, cy). Возвращает узел.
function createNode(cx, cy) {
  if (!graph || !liteCanvas) return null
  const n = graph.add(new RectNode())
  const [w, h] = n.size
  n.pos = [cx - w / 2, cy - h / 2]
  selectedNode.value = n
  return n
}

// --- Панели устройств («Смартфон» и «Планшет»), 06.10.26 ------------------------------------
// Просьба Ярослава: две системные плитки на холсте 56×56. Их нельзя удалить; задача, пришедшая
// с устройства синхронизацией, встаёт к своей панели РЕБЁНКОМ (связь «панель → задача» ставит
// backend при приёме задачи, см. _add_phone_task); файл, брошенный на плитку, уезжает на
// устройство (sendFilesToDevice). Плитки создаются ОДИН раз при загрузке графа, если их ещё нет;
// место — слева от самой левой карточки, чтобы глаз сразу их находил.
const DEVICE_SIDE = 56
function ensureDevicePanels() {
  if (!graph || readOnly.value) return
  const have = new Set()
  let minX = Infinity, minY = Infinity
  for (const n of (graph._nodes || [])) {
    if ((n.kind || 'task') === 'device') { have.add(n.device || 'phone'); continue }
    minX = Math.min(minX, n.pos[0])
    minY = Math.min(minY, n.pos[1])
  }
  const baseX = Math.max(20, (isFinite(minX) ? minX : 210) - 150)
  const baseY = isFinite(minY) ? minY : 60
  let made = false
  for (const [i, dev] of ['phone', 'tablet'].entries()) {
    if (have.has(dev)) continue
    const n = new RectNode()
    n.kind = 'device'
    n.device = dev
    n.size = [DEVICE_SIDE, DEVICE_SIDE]
    n.resizable = false                 // плитка не тянется за уголок
    n.inputs = []                       // кольца нет — панель только источник связей
    n.hideSlotDots()
    n.title = t(dev === 'tablet' ? 'deviceTablet' : 'devicePhone')
    n.color = '#5b8fd9'
    graph.add(n)
    n.pos = [baseX, baseY + i * (DEVICE_SIDE + 20)]
    made = true
  }
  if (made) {
    liteCanvas.setDirty(true, true)
    onNodeChange()
    // Панели фиксируем в graph.json СРАЗУ (находка 06.10.26): armAutoSave «подписывает» граф уже
    // с панелями, и автосохранение больше не видит изменений — панели могли лежать в памяти
    // незаписанными. Тогда первая же задача с телефона могла получить id, как у панели, и при
    // следующем сохранении браузером потерялась бы (слияние считало бы её «усвоенной»).
    saveGraph(true)
  }
}

// Двойной клик по КАРТОЧКЕ — создать пустую подзадачу и связать её с основной
// (просьба Ярослава 01.10.26: «при двойном клике по задаче создавалась пустая
// подчинённая задача со связью»). По пустому месту, как и раньше, ничего не создаётся.
function onDblClick(ev) {
  if (!graph || !liteCanvas || !canvasEl.value) return
  const [gx, gy] = screenToGraph(ev.clientX, ev.clientY)   // screenToGraph сам вычитает rect.left
  let parent = null
  try { parent = graph.getNodeOnPos(gx, gy) } catch (e) {}
  if (!parent) return                 // клик по пустому месту — ничего не создаём
  parent = toRaw(parent)
  if ((parent.kind || 'task') === 'device') return   // по панели устройства подзадача не создаётся
  selectedNode.value = null           // панель по двойному клику НЕ открываем: она только по ПКМ
  const child = createSubtask(parent)
  if (!child) return
  liteCanvas.selectNode(child)        // новая карточка подсвечена — видно, что она появилась
  liteCanvas.setDirty(true, true)
  onNodeChange()                      // автосохранение подхватит карточку и связь
}

// Подзадача: пустая карточка справа от основной + связь «основная → подзадача».
// Место ищем свободное (сначала на уровне основной, затем стопкой вверх/вниз, затем
// следующий столбец правее) — иначе вторая и третья подзадачи легли бы на первую.
function createSubtask(parent, index = 0, total = 1) {
  if (!graph || !parent) return null
  const [w, h] = RectNode.size
  const GAP_X = 46, GAP_Y = 26
  const sx = w + GAP_X, sy = h + GAP_Y
  const cx0 = parent.pos[0] + parent.size[0] + GAP_X + w / 2
  const cy0 = parent.pos[1] + parent.size[1] / 2 + (index - (total - 1) / 2) * sy
  const busy = (cx, cy) => (graph._nodes || []).some(o => o !== parent &&
    Math.abs(o.pos[0] + o.size[0] / 2 - cx) < w * 0.9 && Math.abs(o.pos[1] + o.size[1] / 2 - cy) < h * 0.9)
  let cx = cx0, cy = cy0
  outer:
  for (let col = 0; col < 6; col++) {
    for (const dy of [0, 1, -1, 2, -2]) {
      const tx = cx0 + col * sx, ty = cy0 + dy * sy
      if (!busy(tx, ty)) { cx = tx; cy = ty; break outer }
    }
  }
  const n = graph.add(new RectNode())
  n.pos = [cx - w / 2, cy - h / 2]
  try { parent.connect(0, n, 0) } catch (e) {}   // выход основной → вход подзадачи
  n._fitOnce = true                              // размер под название подберётся при первой правке
  return n
}

// Копия карточки (Ctrl+клик): переносим её данные, но НЕ связи — Ярослав выбрал вариант
// «только саму карточку» (01.10.26). Копия встаёт в первое свободное место справа от исходной.
function freeSpotNear(src, skip) {
  const w = src.size[0], h = src.size[1]
  const GAP_X = 46, GAP_Y = 26
  const cx0 = src.pos[0] + w + GAP_X + w / 2          // сразу правее исходной карточки
  const cy0 = src.pos[1] + h / 2
  const busy = (cx, cy) => (graph._nodes || []).some(o => o !== skip &&
    Math.abs(o.pos[0] + o.size[0] / 2 - cx) < w * 0.9 && Math.abs(o.pos[1] + o.size[1] / 2 - cy) < h * 0.9)
  for (const dy of [0, 1, -1, 2, -2]) {
    const cy = cy0 + dy * (h + GAP_Y)
    if (!busy(cx0, cy)) return [cx0, cy]
  }
  return [cx0, cy0 + 3 * (h + GAP_Y)]
}
function duplicateNode(n) {
  if (!graph || !liteCanvas || !n) return null
  const s = toRaw(n)
  if ((s.kind || 'task') === 'device') { flash(t('deviceNoDelete')); return null }   // системную панель не копируем
  const copy = graph.add(new RectNode())
  copy.title = s.title
  copy.kind = s.kind || 'task'
  copy.color = s.color
  copy.status = s.status || ''
  copy.description = s.description || ''
  copy.due = s.due || ''
  copy.tags = Array.isArray(s.tags) ? s.tags.slice() : []
  copy.image = s.image || ''
  copy.files = (Array.isArray(s.files) ? s.files.slice(0, MAX_FILES) : (s.file ? [s.file] : []))
  copy.dimMode = s.dimMode || 'auto'
  copy.remindTime = s.remindTime || '09:00'
  copy.repeatMode = s.repeatMode || 'once'
  copy.channels = Array.isArray(s.channels) ? s.channels.slice() : ['pc', 'phone', 'tablet']
  copy.size = [s.size[0], s.size[1]]                  // размер уже подогнан под название
  const [cx, cy] = freeSpotNear(s, copy)
  copy.pos = [cx - copy.size[0] / 2, cy - copy.size[1] / 2]
  if (liteCanvas.selectNode) liteCanvas.selectNode(copy)   // выделяем копию, как при создании
  liteCanvas.setDirty(true, true)
  onNodeChange()                                      // автосохранение подхватит копию
  return copy
}

// --- Подзадачи едут за родителем («как на верёвочке») ------------------------------
// Просьба Ярослава 01.10.26: «при движении карточки, если у неё есть подчинённые, связь
// не удлинялась бы, а они двигались за ней»; а если тянуть саму подзадачу — она уходит
// свободно, и связь удлиняется.
// LiteGraph двигает только ВЫДЕЛЕННЫЕ карточки, поэтому потомков смещаем сами — на то же
// смещение мыши в координатах графа (LiteGraph двигает выделенные на delta/scale, то есть
// ровно на эту же величину). Карточку, которая выделена и едет сама, пропускаем — иначе
// смещение применилось бы к ней дважды.
function buildChildrenMap() {
  const map = new Map()
  if (!graph) return map
  for (const id in graph.links) {
    const l = graph.links[id]
    if (!l) continue
    if (!map.has(l.origin_id)) map.set(l.origin_id, [])
    map.get(l.origin_id).push(l.target_id)
  }
  return map
}
function isNodeSelected(n) {
  return !!(liteCanvas && liteCanvas.selected_nodes && liteCanvas.selected_nodes[n.id])
}
// «Верёвочка» с лёгким натяжением. Потомков ведём не жёстко, а через ЦЕЛЬ: цель — жёсткое
// смещение (позиция родителя + смещение, снятое на старте), а карточка догоняет цель в каждом
// кадре (stepFollowLag). Из-за этого при движении подзадача чуть отстаёт и связь слегка
// растягивается, а после остановки ветка сходится в ту же геометрию, что была до
// перетаскивания, — в покое длина связи прежняя, пиксель в пиксель.
const FOLLOW_EASE = 0.275  // доля пути до цели за кадр: меньше — сильнее отставание (0.275 = вдвое мягче прежних 0.55)
const FOLLOW_EPS = 0.35    // ближе этого — доводим позицию точно и успокаиваемся

// Цели для всей ветки под перетаскиваемым узлом (пересчитываются на каждом движении мыши).
function updateFollowTargets(st) {
  const parent = graph.getNodeById(st.id)
  if (!parent) return
  const targets = new Map()
  const seen = new Set()
  const walk = (node, tx, ty) => {
    for (const id of st.kids.get(node.id) || []) {
      if (seen.has(id)) continue          // защита от цикла в связях
      seen.add(id)
      const child = graph.getNodeById(id)
      const base = st.base.get(id)
      if (!child || !base) continue
      if (isNodeSelected(child)) continue // едет сама — её ветку тянет её собственное перемещение
      targets.set(id, [tx + base[0], ty + base[1]])
      walk(child, tx + base[0], ty + base[1])
    }
  }
  walk(parent, parent.pos[0], parent.pos[1])
  st.targets = targets
}

// Кадр «догоняния» (зовётся из animate() до отрисовки): карточки идут к своим целям,
// поэтому связь во время движения слегка натягивается, а не рвётся жёстко.
function stepFollowLag() {
  const lc = liteCanvas
  if (!lc || !graph || !dragFollow) return
  let busy = false
  for (const [id, t] of dragFollow.targets) {
    const n = graph.getNodeById(id)
    if (!n) continue
    const dx = t[0] - n.pos[0], dy = t[1] - n.pos[1]
    if (Math.abs(dx) < FOLLOW_EPS && Math.abs(dy) < FOLLOW_EPS) { n.pos[0] = t[0]; n.pos[1] = t[1]; continue }
    n.pos[0] += dx * FOLLOW_EASE
    n.pos[1] += dy * FOLLOW_EASE
    busy = true
  }
  if (busy) lc.setDirty(true, true)
  if (!busy && !lc.node_dragged) finishFollow()   // отпустили и всё сошлось — фиксируем точно
}
// Смещения потомков относительно их родителей на начало перетаскивания: по ним в конце
// восстанавливаем геометрию точно (LiteGraph в конце округляет позицию карточки — без этого
// накопился бы субпиксельный сдвиг, а связи поехали бы на доли пикселя).
function collectBase(node, kids, seen, out) {
  for (const id of kids.get(node.id) || []) {
    if (seen.has(id)) continue
    seen.add(id)
    const c = graph.getNodeById(id)
    if (!c) continue
    out.set(id, [c.pos[0] - node.pos[0], c.pos[1] - node.pos[1]])
    collectBase(c, kids, seen, out)
  }
}
// Финал «верёвочки»: когда ветка сошлась, ставим позиции РОВНО по целям. Цели считаем от
// ТЕКУЩЕЙ позиции родителя (LiteGraph на отпускании округляет её) — поэтому в покое смещения
// потомков совпадают с исходными до пикселя и длина связи та же, что была до перетаскивания.
function finishFollow() {
  if (!dragFollow || !graph) return
  const st = dragFollow
  updateFollowTargets(st)
  for (const [id, t] of st.targets) {
    const n = graph.getNodeById(id)
    if (!n) continue
    n.pos[0] = t[0]
    n.pos[1] = t[1]
  }
  dragFollow = null
  if (liteCanvas) liteCanvas.setDirty(true, true)
}
// Начало перетаскивания: LiteGraph выставил node_dragged прямо в этом же mousedown, а наш
// слушатель висит на том же элементе ниже по регистрации — значит карточка уже известна.
// Точку отсчёта берём по ПОЗИЦИИ КАРТОЧКИ, а не по координатам мыши: так смещение потомков
// совпадает с движением родителя пиксель в пиксель, чем бы ни двигался сам LiteGraph.
let dragFollow = null   // { id, lastPos: [x, y], kids, base, targets }
function onCanvasMouseDown(ev) {
  if (ev.button !== 0) return
  dragFollow = null
  if (!liteCanvas || !graph) return
  // Кнопка-лупа на карточке (телефон, ближний план): открываем описание в читалке и гасим событие,
  // чтобы карточка не выделилась и холст не поехал. Ловим ЗДЕСЬ, потому что касания (в отличие от
  // мыши) до liteCanvas.onMouse не доходят — замер 05.10.26: у тапа по холсту onMouse пуст.
  const [bx, by] = screenToGraph(ev.clientX, ev.clientY)
  const zoomNode = zoomBtnNodeAt(bx, by)
  if (zoomNode) {
    ev.preventDefault()
    ev.stopImmediatePropagation()
    descReaderNode.value = zoomNode
    return
  }
  // LiteGraph начинает перетаскивание НЕ в mousedown, а на первом движении мыши, поэтому
  // node_dragged тут ещё пуст — карточку под курсором определяем сами тем же hit-тестом.
  let n = liteCanvas.node_dragged
  if (!n) {
    const [mx, my] = screenToGraph(ev.clientX, ev.clientY)
    try { n = graph.getNodeOnPos(mx, my) } catch (e) {}
  }
  if (!n) return
  const kids = buildChildrenMap()
  const base = new Map()
  collectBase(n, kids, new Set(), base)
  dragFollow = { id: n.id, lastPos: [n.pos[0], n.pos[1]], kids, base, targets: new Map() }
}
// Ctrl+клик по карточке — её копия рядом (просьба Ярослава 01.10.26: «чтобы она копировалась»).
// Слушаем на документе в фазе ПЕРЕХВАТА: событие не дойдёт до обработчиков холста, поэтому
// LiteGraph не выделит и не потащит исходную карточку вместе с копированием.
function onDocMouseDownCapture(ev) {
  if (ev.button !== 0 || !(ev.ctrlKey || ev.metaKey)) return
  if (!graph || !liteCanvas) return
  const [gx, gy] = screenToGraph(ev.clientX, ev.clientY)
  let n = null
  try { n = graph.getNodeOnPos(gx, gy) } catch (e) {}
  if (!n) return                      // по пустому месту Ctrl+клик ничего не делает
  ev.preventDefault()
  ev.stopPropagation()
  duplicateNode(n)
}
// Слушаем на документе, а не на холсте: при быстром перетаскивании курсор выходит за холст,
// события на самом холсте пропадают — подзадачи тогда отстали бы от родителя.
function onDocMouseMove() {
  if (!liteCanvas || !graph) return
  const dragged = liteCanvas.node_dragged
  if (!dragged) return                        // отпустили: ветку догонит stepFollowLag (см. animate)
  if (!dragFollow || dragFollow.id !== dragged.id) {
    // Подстраховка, если mousedown прошёл мимо (например, перетаскивание начал сам LiteGraph):
    // принимаем текущее положение за точку отсчёта, цели посчитаем на следующем движении.
    const kids = buildChildrenMap()
    const base = new Map()
    collectBase(dragged, kids, new Set(), base)
    dragFollow = { id: dragged.id, lastPos: [dragged.pos[0], dragged.pos[1]], kids, base, targets: new Map() }
    return
  }
  dragFollow.lastPos = [dragged.pos[0], dragged.pos[1]]
  updateFollowTargets(dragFollow)   // цели на этот кадр; позиции догоняют их в animate()
}
// Конец перетаскивания: LiteGraph округлил позицию карточки — возвращаем потомкам ровно те
// смещения, что были в начале, чтобы связь не удлинилась ни на пиксель.
function onDocMouseUp() {
  // Сразу не снапим: ветка должна догнать родителя плавно (это и есть «слегка тянется»).
  // Точные позиции выставит finishFollow(), когда кадры догоняния успокоятся. Если мышь
  // отпустили без движения (целей нет) — доводим сразу.
  if (dragFollow && !dragFollow.targets.size) finishFollow()
}

// --- Файлы-ссылки на карточке -----------------------------------------------
// Ярослав 03.10.26: в карточке хранится ТОЛЬКО ПУТЬ к файлу (сами файлы не копируются),
// а по клику на значок файл открывается стандартной программой системы.
const MAX_FILES = 5   // максимум ссылок на файлы в одной карточке (Ярослав 03.10.26)
// Виды значков ссылок — по типу файла (Ярослав 03.10.26: «добавь больше значков по видам файлов»).
// Всё, что не попало ни в один список, — обычный документ (лист с загнутым углом).
const AUDIO_EXT = ['mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma', 'opus', 'aiff', 'mid', 'midi']
const VIDEO_EXT = ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'webm', 'm4v', 'mpg', 'mpeg', 'flv', '3gp', 'ts']
const IMAGE_EXT = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'tif', 'tiff', 'heic', 'heif', 'avif', 'ico', 'raw', 'psd', 'ai', 'eps']
const SHEET_EXT = ['xlsx', 'xls', 'xlsm', 'csv', 'tsv', 'ods', 'numbers']
const SLIDES_EXT = ['pptx', 'ppt', 'pps', 'pptm', 'odp', 'key']
const ARCHIVE_EXT = ['zip', 'rar', '7z', 'tar', 'gz', 'tgz', 'bz2', 'xz', 'zst', 'iso', 'cab', 'lzma']
const CODE_EXT = ['js', 'mjs', 'cjs', 'ts', 'tsx', 'jsx', 'py', 'pyw', 'java', 'c', 'h', 'cpp', 'hpp', 'cc', 'cs', 'go', 'rs', 'rb', 'php', 'pl', 'lua', 'swift', 'kt', 'scala', 'dart', 'html', 'htm', 'css', 'scss', 'less', 'json', 'xml', 'yml', 'yaml', 'toml', 'ini', 'sh', 'bash', 'sql', 'vue', 'svelte', 'ipynb', 'asm']
const APP_EXT = ['exe', 'msi', 'msix', 'appx', 'bat', 'cmd', 'com', 'ps1', 'vbs', 'apk', 'jar', 'dmg', 'deb', 'rpm', 'appimage']
function fileExt(p) {
  const s = String(p || '')
  const i = s.lastIndexOf('.')
  return i > 0 ? s.slice(i + 1).toLowerCase() : ''
}
// Вид значка по расширению: отсюда берётся и рисунок на карточке, и подпись в разговоре.
// Порядок проверок = приоритет; списки не пересекаются, поэтому порядок не важен.
function fileKind(p) {
  const e = fileExt(p)
  if (AUDIO_EXT.indexOf(e) >= 0) return 'audio'
  if (VIDEO_EXT.indexOf(e) >= 0) return 'video'
  if (IMAGE_EXT.indexOf(e) >= 0) return 'image'
  if (SHEET_EXT.indexOf(e) >= 0) return 'sheet'
  if (SLIDES_EXT.indexOf(e) >= 0) return 'slides'
  if (ARCHIVE_EXT.indexOf(e) >= 0) return 'archive'
  if (CODE_EXT.indexOf(e) >= 0) return 'code'
  if (APP_EXT.indexOf(e) >= 0) return 'app'
  return 'file'
}
function shortFileName(p) { return String(p || '').split(/[\\/]/).pop() || String(p || '') }

// Ссылки карточки: массив путей (не больше MAX_FILES). Прошлая версия держала одну ссылку
// в поле file — такое значение читаем как список из одного элемента.
function filesOf(n) {
  const a = n && Array.isArray(n.files) ? n.files.filter(Boolean) : []
  if (!a.length && n && n.file) a.push(n.file)
  return a.slice(0, MAX_FILES)
}

// Карточка, которой принадлежит эта ссылка (нужна, когда по ссылке-имени надо выбрать файл).
function nodeWithFile(path) {
  const p = String(path || '')
  for (const n of (graph && graph._nodes) || []) if (filesOf(n).indexOf(p) >= 0) return n
  return null
}

// Путь из данных перетаскивания. Chrome путь файла НЕ отдаёт (приватность); если система всё же
// положила file:///C:/... — берём его, и тогда перетаскивание прикладывает ссылку напрямую.
function localPathFromUri(s) {
  // Путь из данных перетаскивания. Chrome путь файла обычно НЕ отдаёт (приватность), но если
  // система его всё же положила — берём сразу, без поиска и диалога. Принимаем ОБЕ формы:
  // file:///G:/папка/файл.txt и обычный путь G:\папка\файл.txt (в такой форме его отдаёт
  // проводник Windows) — 05.10.26.
  const first = String(s || '').split('\n')[0].trim().replace(/^"(.*)"$/, '$1')
  if (!first) return ''
  const m = /^file:\/\/(.+)$/i.exec(first)
  let p = m ? decodeURIComponent(m[1]) : first
  p = p.replace(/^\/([A-Za-z]:)/, '$1')            // file:///C:/... → C:/...
  if (!/^[A-Za-z]:[\\/]/.test(p)) return ''        // только полный путь с буквой диска
  return p.replace(/\//g, '\\')
}

// Значок вложения: лист / нота / плёнка. Рисуем ЛИНИЯМИ, а не эмодзи: на мелком кегле (≈11px
// в нижней строке) эмодзи мутнеют, а в монохромных темах ещё и остаются цветными. Цвет —
// t.dueColor (как у даты): значок читается как служебная метка, а не как элемент статуса.
// Значок ссылки на карточке. Девять видов (просьба Ярослава 03.10.26): лист (обычный документ),
// картинка, таблица, архив, презентация, код, программа, нота, плёнка. Рисуем ЛИНИЯМИ, а не
// эмодзи: на кегле ≈8px эмодзи мутнеют, а в монохромных темах остаются цветными.
// Цвет значка ссылки — по ТИПУ файла (03.10.26, просьба Ярослава: «линии, но цвет по типу файла,
// в монотемах — серые»). Два набора: на светлой карточке нужен насыщенный тон, на тёмной — светлый,
// иначе значок сливается с фоном. В монотемах (Чёрно-Белая, Мрамор) остаётся прежний цвет темы.
const BADGE_TINT_LIGHT = {
  file: '#3f6ea8', image: '#c06f8f', sheet: '#2f8f6f', archive: '#a8811f', slides: '#b0604a',
  code: '#2f6f88', app: '#5f5f6b', audio: '#8351a8', video: '#c0564a',
}
const BADGE_TINT_DARK = {
  file: '#7ea8e0', image: '#e0a0bb', sheet: '#6dc9a6', archive: '#dfc06a', slides: '#e0937a',
  code: '#7fc4d8', app: '#b9bcc7', audio: '#bda0e0', video: '#e88f7d',
}
function badgeTint(t, kind) {
  // ВАЖНО: t здесь — стиль УЗЛА (theme().node), у него нет флагов light/mono.
  // Флаги живут на самой теме, поэтому читаем их через theme().
  const th = theme()
  if (th.mono) return t.dueColor
  return (th.light ? BADGE_TINT_LIGHT : BADGE_TINT_DARK)[kind] || t.dueColor
}

function drawFileBadge(ctx, kind, cx, cy, s, color) {
  const w = s * 0.82, h = s
  const x = cx - w / 2, y = cy - h / 2
  ctx.save()
  ctx.strokeStyle = color
  ctx.fillStyle = color
  ctx.lineWidth = Math.max(1, Math.round(s * 0.14 * 10) / 10)
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  // Короткие помощники: у всех значков одна система координат (доли w/h), иначе пропорции
  // разъезжаются при смене размера значка.
  const M = (px, py) => ctx.moveTo(x + w * px, y + h * py)
  const L = (px, py) => ctx.lineTo(x + w * px, y + h * py)
  const box = (px, py, pw, ph) => ctx.rect(x + w * px, y + h * py, w * pw, h * ph)
  const dot = (px, py, r) => { ctx.beginPath(); ctx.arc(x + w * px, y + h * py, Math.max(0.8, w * r), 0, Math.PI * 2); ctx.fill() }
  if (kind === 'audio') {
    ctx.beginPath(); ctx.moveTo(x + w * 0.72, y + h * 0.04); ctx.lineTo(x + w * 0.72, y + h * 0.72); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(x + w * 0.72, y + h * 0.04)
    ctx.quadraticCurveTo(x + w, y + h * 0.14, x + w, y + h * 0.34); ctx.stroke()
    ctx.beginPath(); ctx.ellipse(x + w * 0.46, y + h * 0.76, w * 0.26, h * 0.2, -0.35, 0, Math.PI * 2); ctx.fill()
  } else if (kind === 'video') {
    // Видео: кадр с треугольником «играть» (03.10.26, выбор Ярослава — плёнка не нравилась).
    ctx.beginPath(); box(0.04, 0.14, 0.92, 0.72); ctx.stroke()
    ctx.beginPath(); M(0.41, 0.31); L(0.41, 0.69); L(0.72, 0.5); ctx.closePath(); ctx.fill()
  } else if (kind === 'image') {
    // Картинка: рамка, солнце и горы.
    ctx.beginPath(); box(0, 0.08, 1, 0.84); ctx.stroke()
    dot(0.27, 0.31, 0.1)
    ctx.beginPath(); M(0.12, 0.86); L(0.4, 0.5); L(0.6, 0.7); L(0.74, 0.58); L(0.9, 0.86); ctx.stroke()
  } else if (kind === 'sheet') {
    // Таблица: лист с таблицей внутри (03.10.26, выбор Ярослава — прежняя сетка не нравилась).
    // Уголок загнут, внутри — сетка 2x2: силуэт «лист» отличает значок от документа.
    ctx.beginPath()
    M(0.1, 0); L(0.68, 0); L(1, 0.3); L(1, 1); L(0.1, 1); ctx.closePath(); ctx.stroke()
    ctx.beginPath(); M(0.68, 0); L(0.68, 0.3); L(1, 0.3); ctx.stroke()
    ctx.beginPath(); box(0.24, 0.46, 0.6, 0.4)
    M(0.24, 0.62); L(0.84, 0.62); M(0.54, 0.46); L(0.54, 0.86)
    ctx.stroke()
  } else if (kind === 'archive') {
    // Архив: коробка с молнией по центру.
    ctx.beginPath(); box(0.08, 0.06, 0.84, 0.88); ctx.stroke()
    ctx.beginPath()
    for (let i = 0; i < 4; i++) { M(0.5, 0.16 + i * 0.2); L(0.5, 0.2 + i * 0.2) }
    ctx.stroke()
  } else if (kind === 'slides') {
    // Презентация: доска на стойке со столбиками.
    ctx.beginPath(); box(0.06, 0.06, 0.88, 0.6); ctx.stroke()
    ctx.beginPath(); M(0.5, 0.66); L(0.5, 0.84); M(0.3, 0.92); L(0.7, 0.92); ctx.stroke()
    ctx.beginPath()
    M(0.2, 0.56); L(0.2, 0.4); M(0.38, 0.56); L(0.38, 0.26); M(0.56, 0.56); L(0.56, 0.46)
    ctx.stroke()
  } else if (kind === 'code') {
    // Код: угловые скобки и косая черта.
    ctx.beginPath(); M(0.34, 0.26); L(0.12, 0.5); L(0.34, 0.74); ctx.stroke()
    ctx.beginPath(); M(0.66, 0.26); L(0.88, 0.5); L(0.66, 0.74); ctx.stroke()
    ctx.beginPath(); M(0.58, 0.18); L(0.42, 0.82); ctx.stroke()
  } else if (kind === 'app') {
    // Программа: окно с полосой заголовка и двумя кнопками.
    ctx.beginPath(); box(0.02, 0.12, 0.96, 0.76); ctx.stroke()
    ctx.beginPath(); M(0.02, 0.36); L(0.98, 0.36); ctx.stroke()
    dot(0.13, 0.24, 0.06); dot(0.28, 0.24, 0.06)
  } else {
    // Обычный документ: лист с загнутым углом и строками текста.
    const fold = h * 0.32
    ctx.beginPath()
    ctx.moveTo(x + w * 0.18, y); ctx.lineTo(x + w * 0.66, y); ctx.lineTo(x + w, y + fold)
    ctx.lineTo(x + w, y + h); ctx.lineTo(x + w * 0.18, y + h); ctx.closePath(); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(x + w * 0.66, y); ctx.lineTo(x + w * 0.66, y + fold)
    ctx.lineTo(x + w, y + fold); ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(x + w * 0.34, y + h * 0.58); ctx.lineTo(x + w * 0.84, y + h * 0.58)
    ctx.moveTo(x + w * 0.34, y + h * 0.78); ctx.lineTo(x + w * 0.72, y + h * 0.78); ctx.stroke()
  }
  ctx.restore()
}

// --- Рисунки: приём картинки (кнопка в инспекторе / Ctrl+V / перетаскивание на карточку) ---
async function attachImage(node, blob) {
  if (!node || !blob) return
  const url = URL.createObjectURL(blob)
  try {
    const dataUrl = await shrinkImage(url)
    if (!dataUrl) { flash('Не удалось прочитать картинку'); return }
    // Пишем ЧЕРЕЗ reactive(): узел может быть «сырым» объектом LiteGraph, и присваивание
    // в него напрямую Vue не замечает — карточка перерисуется, а инспектор нет
    // (не появятся превью и кнопка «Убрать»). reactive() вернёт тот же прокси, что уже
    // отслеживает панель, если она открыта на этом узле.
    reactive(node).image = dataUrl
    onNodeChange()
  } finally { URL.revokeObjectURL(url) }
}

// --- Ссылка на файл: приложить (нативный диалог) и открыть -------------------
// Путь выбранного файла знает только СЕРВЕР — он работает на этом же компьютере, а браузер
// путь не отдаёт (приватность). Поэтому выбор идёт через /api/pick_file (диалог Windows).
// Добавить ссылку в карточку (список, не больше MAX_FILES). true — добавили (или уже была).
function addFileLink(node, path) {
  const n = node && toRaw(node)
  const p = String(path || '').trim()
  if (!n || !p) return false
  const cur = filesOf(n).slice()
  if (cur.indexOf(p) >= 0) { reactive(n).files = cur; return true }    // такая ссылка уже есть
  if (cur.length >= MAX_FILES) { flash(t('fileLimit')); return false }
  cur.push(p)
  reactive(n).files = cur
  onNodeChange()
  return true
}

async function pickFileLink(node, initialName = '') {
  const n = node && toRaw(node)
  if (!n) return
  if (filesOf(n).length >= MAX_FILES) { flash(t('fileLimit')); return }
  try {
    const r = await fetch('/api/pick_file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Plannertate-Client': '1' },
      body: JSON.stringify({ name: initialName || '' }),
    })
    const j = await r.json().catch(() => ({}))
    if (j.status === 'cancel') return                       // закрыл диалог — ничего не делаем
    if (j.status !== 'ok' || !j.path) { flash(j.error || t('filePickFail')); return }
    addFileLink(n, j.path)
  } catch (e) { console.error(e); flash(t('filePickFail')) }
}

// Бросок файла на карточку. Путь браузер не отдаёт (защита Chrome), но отдаёт приметы файла:
// имя, размер и время изменения. Сервер по трём приметам сам находит файл (/api/locate_file)
// — в ссылку пишется ПОЛНЫЙ путь, без диалогов и ручных действий (просьба Ярослава 06.10.26:
// «Я не должен совершать каких-либо дополнительных действий — автоматически»). Не нашлось —
// прежний диалог выбора с подставленным именем (последний шанс); отмена — ссылка не добавляется.
async function attachDroppedFile(node, f) {
  const n = node && toRaw(node)
  if (!n || !f) return
  if (filesOf(n).length >= MAX_FILES) { flash(t('fileLimit')); return }
  const name = String(f.name || '').trim()
  if (!name) return
  try {
    const r = await fetch('/api/locate_file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Plannertate-Client': '1' },
      body: JSON.stringify({ name, size: f.size || 0, mtime: (f.lastModified || 0) / 1000 }),
    })
    const j = await r.json().catch(() => ({}))
    if (j.status === 'ok' && j.path) { addFileLink(n, String(j.path)); return }
  } catch (e) { /* не вышло — ниже диалог */ }
  pickFileLink(n, name)
}

// --- Лицензия / поддержка автора (03.10.26, просьба Ярослава) --------------------------------
// Клик по логотипу открывает страницу поддержки. Кнопка «Лицензия» ведёт туда же, но сначала
// человек выбирает оценку, а внизу панели видно сумму. Сумму DonationAlerts из ссылки НЕ принимает
// (проверено 03.10.26: ни ?amount, ни ?sum, ни /nick/250 — страница всегда показывает свои 10 ₽),
// поэтому сумма показывается в панели, а страница открывается как есть.
// После «Оплатить» флаг уходит на сервер (license.json) — кнопка больше не показывается никогда,
// в том числе после перезапуска сервера.
const DONATE_URL = 'https://www.donationalerts.com/r/yaroslav_khmelev'
const showLicense = ref(false)

// --- Установка приложения на телефон (03.10.26, просьба Ярослава) ---------------------------
// При первом запуске (файла ключа ещё не было) предлагаем поставить приложение на телефон;
// «Позже» запоминается на компьютере, а кнопка внизу боковой панели остаётся навсегда.
const phoneState = ref(null)
const showPhone = ref(false)
const showPhoneAsk = ref(false)
const installDevice = ref('phone')     // 'phone' | 'tablet' — какая панель установки открыта
function openInstall(dev) { installDevice.value = dev === 'tablet' ? 'tablet' : 'phone'; showPhone.value = true }

// --- «Установить MCP на Гермес» (06.10.26, просьба Ярослава) ---------------------------------
// Приложение не ставит MCP само: кнопка показывает готовое сообщение с путями к файлам —
// его копируют и отправляют Гермесу, и тот всё устанавливает своим ходом.
const showMcp = ref(false)
const mcpInfo = ref(null)
async function openMcpPanel() {
  showMcp.value = true
  mcpInfo.value = null
  try {
    const r = await fetch('/api/mcp/info')
    mcpInfo.value = await r.json()
  } catch (e) {
    mcpInfo.value = { installed: false, text: '', error: true }
  }
}
async function copyMcpText() {
  const s = mcpInfo.value && mcpInfo.value.text
  if (!s) return
  let ok = false
  try { await navigator.clipboard.writeText(s); ok = true } catch (e) { ok = false }
  if (!ok) {
    try {
      const ta = document.createElement('textarea')
      ta.value = s
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      ok = document.execCommand('copy')
      ta.remove()
    } catch (e) { ok = false }
  }
  flash(ok ? t('mcpCopied') : t('mcpCopyFail'))
}
// Восстановление из копии (04.10.26, просьба Ярослава): кнопка-значок рядом с «создать копию».
// Сервер сначала сохраняет текущий граф отдельной копией, потом подменяет файл; после успеха
// перезагружаем страницу, иначе браузер (он держит граф в памяти) затрёт восстановленное.
const showRestore = ref(false)
async function doRestore(file) {
  try {
    const r = await fetch('/api/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Plannertate-Client': '1' },
      body: JSON.stringify({ file }),
    })
    const j = await r.json().catch(() => ({}))
    if (r.ok && j && j.status === 'ok') {
      showRestore.value = false
      flash(t('restoreDone'))
      setTimeout(() => location.reload(), 1200)
    } else flash(t('restoreFail'))
  } catch (e) { flash(t('restoreFail')) }
}

// Резервная копия графа: кнопка-значок рядом со «Свернуть» (просьба Ярослава 04.10.26).
async function makeBackup() {
  try {
    const r = await fetch('/api/backup', { method: 'POST', headers: { 'X-Plannertate-Client': '1' } })
    const j = await r.json().catch(() => ({}))
    if (r.ok && j && j.status === 'ok') flash(t('backupDone') + (j.file ? ' · ' + j.file : ''))
    else flash(t('backupFail'))
  } catch (e) { flash(t('backupFail')) }
}

async function loadPhoneState() {
  try {
    const r = await fetch('/api/phone/state')
    if (!r.ok) return
    phoneState.value = await r.json()
    if (phoneState.value.firstRun && !phoneState.value.promptSeen) showPhoneAsk.value = true
  } catch (e) { console.error(e) }
}

async function phoneAskLater() {
  showPhoneAsk.value = false
  if (phoneState.value) phoneState.value.promptSeen = true
  try { await fetch('/api/phone/prompt_seen', { method: 'POST' }) } catch (e) { /* окно уже закрыто */ }
}

function phoneAskYes() {
  showPhone.value = true
  phoneAskLater()      // окно показано — при следующем запуске не всплывает
}
// null — состояние ЕЩЁ НЕ спросили у сервера: до ответа кнопку не показываем.
// Иначе у тех, кто уже оплатил, она мелькает при каждой перезагрузке страницы (Ярослав, 03.10.26).
const licenseDone = ref(null)

async function loadLicense() {
  try {
    const r = await fetch('/api/license')
    const j = await r.json().catch(() => ({}))
    licenseDone.value = !!j.done
  } catch (e) { console.error(e) }
}

// Ссылку открывает сервер: окно приложения может быть без вкладок, а система откроет браузер.
async function openUrl(url) {
  try {
    const r = await fetch('/api/open_url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Plannertate-Client': '1' },
      body: JSON.stringify({ url }),
    })
    const j = await r.json().catch(() => ({}))
    if (j.status !== 'ok') { flash(j.error || t('licOpenFail')); return false }
    return true
  } catch (e) { console.error(e); flash(t('licOpenFail')); return false }
}

function openDonate() { openUrl(DONATE_URL) }   // клик по логотипу программы

async function onLicensePay(row) {
  showLicense.value = false
  try {
    await fetch('/api/license_done', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Plannertate-Client': '1' },
      body: JSON.stringify({ amount: row && row.rub, usd: row && row.usd, text: row && row.text, currency: 'RUB' }),
    })
  } catch (e) { console.error(e) }
  licenseDone.value = true
  await openUrl(DONATE_URL)
  flash(t('licThanks'))
}

// имя → путь в списке ссылок карточки: в следующий раз файл откроется сразу (06.10.26).
function replaceFileInNode(n, name, p) {
  const cur = filesOf(n).slice()
  const i = cur.indexOf(name)
  if (i < 0) return
  if (cur.indexOf(p) >= 0) cur.splice(i, 1)
  else cur[i] = p
  reactive(n).files = cur
  onNodeChange()
}

// Ссылка-ИМЯ осталась только у СТАРЫХ карточек (новые ссылки сразу получают полный путь — см.
// attachDroppedFile). Клик по такому имени просит указать файл (диалог откроется с этим
// именем), заменяет имя на выбранный полный путь и открывает файл сразу.
async function resolveFileLink(n, name) {
  const target = shortFileName(name)
  try {
    const r = await fetch('/api/pick_file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Plannertate-Client': '1' },
      body: JSON.stringify({ name: target }),
    })
    const j = await r.json().catch(() => ({}))
    if (j.status === 'cancel') return                       // закрыл диалог — ничего не делаем
    if (j.status !== 'ok' || !j.path) { flash(j.error || t('filePickFail')); return }
    const p = String(j.path)
    replaceFileInNode(n, name, p)
    await openFileLink(p, n)
  } catch (e) { console.error(e); flash(t('filePickFail')) }
}

// Клик по значку на карточке (и по ссылке в панели) — открыть файл стандартной программой.
async function openFileLink(path, node = null) {
  const p = String(path || '')
  if (!p) return
  // Ссылка-ИМЯ (так приходит перетаскивание: браузер путь не отдаёт — решение Ярослава 05.10.26).
  // Клик по ней уточняет путь (диалог откроется с этим именем) и открывает файл — resolveFileLink.
  if (!/^[A-Za-z]:[\\/]/.test(p) && !p.startsWith('\\\\') && !p.startsWith('/')) {
    const n = node || nodeWithFile(p)
    if (!n) { flash(t('fileOpenFail')); return }
    await resolveFileLink(n, p)
    return
  }
  try {
    const r = await fetch('/api/open_file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Plannertate-Client': '1' },
      body: JSON.stringify({ path: p }),
    })
    const j = await r.json().catch(() => ({}))
    if (j.status !== 'ok') flash(j.error || t('fileOpenFail'))
  } catch (e) { console.error(e); flash(t('fileOpenFail')) }
}

// Ctrl+V: картинка из буфера уходит в открытую карточку.
// В текстовом поле пропускаем вставку только если в буфере есть ещё и обычный текст.
function onPaste(ev) {
  // Карточка — как в deleteSelected: сначала Vue-реф (после ПКМ/панели), затем выделение самого
  // холста (после обычного ЛКМ: LiteGraph хранит выделенное в liteCanvas.selected_nodes, а реф
  // при ЛКМ не обновляется — только сбрасывается на пустом выделении).
  const node = (selectedNode.value && toRaw(selectedNode.value))
    || Object.values((liteCanvas && liteCanvas.selected_nodes) || {})[0]
  if (!node) return
  const t = ev.target
  const inField = !!(t && t.matches && t.matches('input,textarea'))
  const items = Array.prototype.slice.call((ev.clipboardData && ev.clipboardData.items) || [])
  const img = items.find((it) => it.kind === 'file' && it.type && it.type.indexOf('image/') === 0)
  if (!img) {
    // Картинки нет — может, в буфере АДРЕС файла (скопирован из адресной строки браузера:
    // file:///C:/…, или путь вида C:\…)? Тогда Ctrl+V при выделенной карточке записывает его
    // в ссылку (просьба Ярослава 06.10.26: «скопировать адрес файла и записать его в этот
    // значок»). В текстовом поле не мешаем обычной вставке текста.
    if (inField) return
    const txt = (ev.clipboardData && ev.clipboardData.getData('text/plain')) || ''
    const p = localPathFromUri(txt)
    if (!p) return
    if ((node.kind || 'task') === 'notify') { flash(t('fileNoReminder')); return }
    ev.preventDefault()
    addFileLink(node, p)
    return
  }
  const hasText = items.some((it) => it.kind === 'string' && it.type === 'text/plain')
  if (inField && hasText) return
  const f = img.getAsFile()
  if (!f) return
  ev.preventDefault()
  attachImage(node, f)
}

// Перетаскивание картинки на карточку: смотрим, над какой нодой бросили.
function onDragOver(ev) {
  const types = ev.dataTransfer && ev.dataTransfer.types
  if (types && Array.prototype.indexOf.call(types, 'Files') !== -1) ev.preventDefault()
}
function onCanvasDrop(ev) {
  const dt = ev.dataTransfer
  const f = dt && dt.files && dt.files[0]
  if (!f) {
    // Файла в данных нет — возможно, перетащили АДРЕС (ссылку) из адресной строки браузера
    // (file:///C:/…). Тогда путь записывается в ссылку карточки (06.10.26). Панели устройств
    // адрес не принимают — им бросают файлы.
    const txt = dt ? ((dt.getData && (dt.getData('text/uri-list') || dt.getData('text/plain'))) || '') : ''
    const p = localPathFromUri(txt)
    if (!p) return
    ev.preventDefault()
    const [gx0, gy0] = screenToGraph(ev.clientX, ev.clientY)
    const node0 = graph.getNodeOnPos(gx0, gy0)
    if (!node0 || (node0.kind || 'task') === 'device') return
    if (node0.kind === 'notify') { flash(t('fileNoReminder')); return }
    addFileLink(node0, p)
    return
  }
  // Гасим drop ВСЕГДА, для любого файла: иначе браузер уходит со страницы и открывает файл сам
  // (это был реальный баг — 03.10.26).
  ev.preventDefault()
  const [gx, gy] = screenToGraph(ev.clientX, ev.clientY)
  const node = graph.getNodeOnPos(gx, gy)
  if (!node) return
  // Панель устройства: ЛЮБОЙ файл, брошенный на плитку, уезжает на устройство (06.10.26).
  if ((node.kind || 'task') === 'device') { sendFilesToDevice(node, dt.files); return }
  if (f.type && f.type.indexOf('image/') === 0) { attachImage(node, f); return }
  // У напоминания нижнюю строку целиком занимает подпись повторения — значку там нет места,
  // и ссылка была бы невидимой и некликабельной. Говорим прямо, а не делаем вид.
  if (node.kind === 'notify') { flash(t('fileNoReminder')); return }
  // Не картинка — прикладываем как ССЫЛКУ на файл (файл на диске остаётся на месте).
  // Адрес берём из данных перетаскивания; если адреса нет — сразу откроется диалог выбора
  // файла, и в ссылку попадёт ПОЛНЫЙ путь (просьба Ярослава 06.10.26).
  const uri = (dt.getData && (dt.getData('text/uri-list') || dt.getData('text/plain'))) || ''
  const local = localPathFromUri(uri)
  if (local) { addFileLink(node, local); return }
  attachDroppedFile(node, f)
}

// Файл, брошенный на панель устройства: копируем его на сервер в очередь устройства
// (папка device_files/<phone|tablet> рядом с graph.json). Устройство заберёт файл при
// ближайшей синхронизации — приём добавим в приложение телефона отдельным шагом
// (просьба Ярослава 06.10.26: «перетаскиваешь любой файл — он начинает копироваться»).
async function sendFilesToDevice(node, files) {
  if (readOnly.value) { roBlocked(); return }
  const dev = toRaw(node).device === 'tablet' ? 'tablet' : 'phone'
  const list = Array.prototype.slice.call(files || [])
  if (!list.length) return
  let ok = 0
  for (const f of list) {
    try {
      const fd = new FormData()
      fd.append('file', f, f.name || 'file')
      const r = await fetch('/api/device/file?device=' + dev, {
        method: 'POST', body: fd, headers: { 'X-Plannertate-Client': '1' },
      })
      const j = await r.json().catch(() => null)
      if (j && j.status === 'ok') ok++
    } catch (e) { /* неудача — посчитаем ниже */ }
  }
  const devName = t(dev === 'tablet' ? 'deviceTablet' : 'devicePhone')
  if (ok) flash(t('deviceFileOk').replace('{dev}', devName) + (ok > 1 ? ' ×' + ok : ''))
  else flash(t('deviceFileFail'))
}

// Правый клик по карточке: выделить её и открыть inspector с автофокусом на задачу.
function onContextMenu(ev) {
  // Правый клик — единственный способ открыть панель (левый клик по карточке её не трогает).
  if (!graph || !liteCanvas) return
  const target = ev.target && ev.target.closest ? ev.target.closest('canvas') : null
  if (target !== canvasEl.value) return
  const [gx, gy] = screenToGraph(ev.clientX, ev.clientY)   // screenToGraph уже вычитает rect.left
  let found = null
  try {
    found = graph.getNodeOnPos(gx, gy)   // LiteGraph hit-test over _nodes (top-most wins)
  } catch (e) {}
  if (!found) return
  // Панель устройства: панель карточки для неё не открываем — системной плитке править нечего.
  if ((found.kind || 'task') === 'device') { ev.preventDefault(); ev.stopPropagation(); return }
  ev.preventDefault()
  ev.stopPropagation()   // не даём LiteGraph-обработчику очистить выделение после правого клика
  liteCanvas.selectNode(found)
  selectedNode.value = toRaw(found)
  inspectorPos.value = { x: ev.clientX, y: ev.clientY }
  nextTick(() => {
    clampInspector(ev.clientX, ev.clientY)   // панель подросла (поле рисунка) — прижимаем к экрану по реальному размеру
    // Автофокус на «Задачу» нужен только для правки. В режиме просмотра (сохранённая копия
    // на телефоне/планшете) НЕ фокусируем: иначе сфокусированное поле можно набирать, и
    // блокировка кликов не помогает — «остальные неактивны, а название правится» (Ярослав 04.10.26).
    if (readOnly.value) return
    const inp = document.getElementById('insp-' + found.id)
    if (inp) inp.focus()
  })
}

// Панель должна быть целиком на экране: меряем её фактический размер и поджимаем позицию.
function clampInspector(cx, cy) {
  const el = document.querySelector('.inspector')
  if (!el) return
  const r = el.getBoundingClientRect()
  const x = Math.min(Math.max(4, cx), Math.max(4, window.innerWidth - r.width - 4))
  const y = Math.min(Math.max(4, cy), Math.max(4, window.innerHeight - r.height - 4))
  if (x !== inspectorPos.value.x || y !== inspectorPos.value.y) inspectorPos.value = { x, y }
}

// Удаление: работаем с тем, что выбрано в Vue-рефе, а если его нет — с выделением LiteGraph.
// ВНИМАНИЕ: выделенные узлы LiteGraph хранит на канвасе (liteCanvas.selected_nodes), не на graph.
function deleteSelected() {
  if (readOnly.value) { roBlocked(); return }
  const n = toRaw(selectedNode.value) || Object.values((liteCanvas && liteCanvas.selected_nodes) || {})[0]
  if (!n) return
  // Панели устройств («Смартфон»/«Планшет») — системные: удалить нельзя (просьба Ярослава 06.10.26).
  if ((n.kind || 'task') === 'device') { flash(t('deviceNoDelete')); return }
  graph.remove(n)
  selectedNode.value = null
}

// --- Список напоминаний (кнопка «⏰ Список напоминаний» в сайдбаре) ------------------------
// Просьба Ярослава 01.10.26: таблица ВСЕХ активных напоминаний (задача, время, дата, повторение,
// доставка); по строке можно нажать (показать карточку) и удалить ненужное напоминание.
// Строки собираем из ЖИВОГО графа при каждом открытии и после каждого удаления: graph._nodes не
// реактивен, вычисляемого свойства тут мало.
const reminderRows = ref([])
const CH_REM_KEY = { pc: 'remPc', phone: 'remPhone', tablet: 'remTablet', telegram: 'remTg', vkmax: 'remVk' }

function buildReminderRows() {
  const d = L18N[(lang && lang.value) === 'en' ? 'en' : 'ru']
  const rows = []
  for (const n of (graph._nodes || [])) {
    if ((n.kind || 'task') !== 'notify') continue
    const repWord = (REPEATS[(lang && lang.value) === 'en' ? 'en' : 'ru'] || REPEATS.ru)[n.repeatMode] ||
                    REPEATS[(lang && lang.value) === 'en' ? 'en' : 'ru'].once
    const chans = (n.channels || []).filter(c => CH_REM_KEY[c]).map(c => d[CH_REM_KEY[c]])
    rows.push({
      id: n.id,
      title: String(n.title || '').trim(),
      time: String(n.remindTime || '').trim() || '--:--',
      date: n.due ? shortDate(n.due) : '—',
      repeat: repWord,
      channels: chans.length ? chans.join(', ') : '—',
      color: n.color ? accentOf(n.color) : '',   // цвет точки: в монохромной теме станет серым
      // сортировка: сначала ближайшие по дате, внутри даты — по времени
      _k: `${n.due || '9999-99-99'} ${String(n.remindTime || '99:99')}`,
    })
  }
  rows.sort((a, b) => (a._k < b._k ? -1 : a._k > b._k ? 1 : 0))
  for (const r of rows) delete r._k
  reminderRows.value = rows
}

function toggleReminderList() {
  showNotify.value = !showNotify.value
  if (showNotify.value) buildReminderRows()
}

// Нажатие по строке: показываем карточку на холсте (центрируем) и выделяем её — панель открывается
// сама. Список при этом НЕ закрывается, чтобы можно было удалить несколько подряд.
function revealReminder(id) {
  const n = graph.getNodeById(id)
  if (!n || !liteCanvas) return
  const ds = liteCanvas.ds, sc = ds.scale
  ds.offset[0] = liteCanvas.canvas.width / (2 * sc) - (n.pos[0] + n.size[0] / 2)
  ds.offset[1] = liteCanvas.canvas.height / (2 * sc) - (n.pos[1] + n.size[1] / 2)
  // Выделение ставим И в LiteGraph (иначе карточка не подсветится на холсте), И в Vue-реф
  // (по нему открывается панель карточки).
  if (liteCanvas.selectNodes) liteCanvas.selectNodes([n], false)
  else if (liteCanvas.selected_nodes) liteCanvas.selected_nodes[n.id] = true
  selectedNode.value = n
  liteCanvas.setDirty(true, true)
}

function deleteReminder(id) {
  const n = graph.getNodeById(id)
  if (!n) return
  graph.remove(n)                                   // связи LiteGraph чистит сам
  if (selectedNode.value && toRaw(selectedNode.value).id === id) selectedNode.value = null
  if (liteCanvas) liteCanvas.setDirty(true, true)
  buildReminderRows()
  saveGraph(true)                                   // удаление сразу на сервер: подпись автосохранения
                                                    // не следит за полями напоминания
}

// Новая карточка — в середине видимой части активного окна. Ярослав 01.10.26: «чтобы новые
// карточки создавались по центру». Если там уже стоит карточка, шагаем каскадом (вправо-вниз
// на четверть карточки), иначе несколько новых легли бы идеально друг на друга.
// kind: 'task' — задача («+ Задача»), 'notify' — напоминание («+ Напоминание», значок ⏰).
function addCardAtCenter(kind = 'task') {
  if (!liteCanvas || !canvasEl.value) return
  const rect = canvasEl.value.getBoundingClientRect()
  const [gx, gy] = screenToGraph(rect.left + rect.width / 2, rect.top + rect.height / 2)
  const [w, h] = RectNode.size
  const clampX = (v) => Math.min(Math.max(v, FIELD.x + w / 2), FIELD.x + FIELD.w - w / 2)
  const clampY = (v) => Math.min(Math.max(v, FIELD.y + h / 2), FIELD.y + FIELD.h - h / 2)
  const busy = (cx, cy) => (graph._nodes || []).some(o =>
    Math.abs(o.pos[0] + o.size[0] / 2 - cx) < 24 && Math.abs(o.pos[1] + o.size[1] / 2 - cy) < 18)
  let step = 0
  while (step < 24 && busy(clampX(gx + step * w * 0.26), clampY(gy + step * h * 0.36))) step++
  const node = createNode(clampX(gx + step * w * 0.26), clampY(gy + step * h * 0.36))
  if (node) {
    if (kind === 'notify') {           // напоминание: свой цвет и название по умолчанию
      node.kind = 'notify'
      node.color = notifyColor()
      node.title = t('notifyTitle')
    }
    // Новая карточка: при первой правке подберём размер под название (см. fitCardToTitle).
    node._fitOnce = true
  }
}
function onAddTask() { if (readOnly.value) return roBlocked(); addCardAtCenter('task') }
// «+ Напоминание» из сайдбара — не пустая карточка в центре холста, а напоминание к ВЫДЕЛЕННОЙ
// задаче (см. onAddNotify ниже): так выполняется «задача и описание копируются с основной карточки».

// --- save / load ---
// pos/size в LiteGraph могут быть Float32Array, и JSON.stringify превращает их
// в {"0":645,"1":522,"2":0,...}. Приводим к обычным массивам [x, y]:
// и при сохранении, и при загрузке старого файла.
function normalizeVec(obj, key) {
  const v = obj && obj[key]
  if (!v || Array.isArray(v)) return
  obj[key] = [Number(v[0]) || 0, Number(v[1]) || 0]
}
function normalizeNode(n) { normalizeVec(n, 'pos'); normalizeVec(n, 'size') }

// silent = true — автосохранение: пишем на сервер без всплывающего окна (иначе оно вылезало
// бы после каждого изменения карточки). Ярослав 01.10.26: «чтобы при любом изменении карточки
// автоматически сохранялось».
let savingNow = false      // защита от гонки: автосохранение может стартовать, пока идёт предыдущее
let pendingSave = false
async function saveGraph(silent = false) {
  if (savingNow) { pendingSave = true; return }   // второй запрос не шлём — перезапишем после первого
  savingNow = true
  try {
    const data = graph.serialize()
    if (Array.isArray(data.nodes)) data.nodes.forEach(normalizeNode)
    await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
    // Успех не сообщаем: автосохранение работает само, а всплывающее «Сохранено» мешало.
    // Об ошибке всё равно говорим — молча терять правки нельзя.
  } catch (e) { console.error(e); flash(t('saveFailed')) }
  finally {
    savingNow = false
    if (pendingSave) { pendingSave = false; saveGraph(true) }
  }
}

// --- Автосохранение -----------------------------------------------------------
// Любое изменение карточки (перетаскивание, ресайз, правка полей, цвет, рисунок,
// создание/удаление, связи) уходит на сервер само. Следим за «подписью» графа —
// дёшево (для 1000 карточек ~несколько мс) и не требует ловить все события LiteGraph.
// Проверка не чаще раза в 700 мс, запись — через 600 мс после последнего изменения
// (чтобы не слать запрос на каждый кадр перетаскивания).
let autoSaveArmed = false
let lastGraphSig = null
let autoSaveTimer = null
function graphSignature() {
  if (!graph || !graph._nodes) return ''
  const parts = []
  for (const n of graph._nodes) {
    const img = n.image || ''
    parts.push(n.id, n.pos[0], n.pos[1], n.size[0], n.size[1], n.title || '', n.description || '',
               n.status || '', n.due || '', n.color || '', img.length, img.slice(0, 24), img.slice(-24),
               n.tags ? n.tags.join(',') : '',
               // Ссылки на файлы ОБЯЗАТЕЛЬНО в подписи (найдено 05.10.26): без них приложение файл
               // прикладывало, но автосохранение не срабатывало — ссылка пропадала после перезапуска.
               filesOf(n).join('|'))
  }
  const links = []
  for (const id in graph.links) {
    const l = graph.links[id]
    if (l) links.push(l.origin_id + '>' + l.target_id + '@' + l.origin_slot + ':' + l.target_slot)
  }
  return parts.join('\u001f') + '\u001e' + links.sort().join(',')
}
function armAutoSave() { lastGraphSig = graphSignature(); autoSaveArmed = true }
let lastSigCheck = 0
function watchAutoSave() {
  if (!autoSaveArmed || !graph) return
  const now = (typeof performance !== 'undefined' ? performance.now() : Date.now())
  if (now - lastSigCheck < 700) return
  lastSigCheck = now
  const sig = graphSignature()
  if (sig === lastGraphSig) return
  lastGraphSig = sig
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => { autoSaveTimer = null; saveGraph(true) }, 600)
}

// Возвращает true, если сохранённый граф найден и загружен.
async function loadGraph() {
  try {
    const res = await fetch('/api/load')
    if (!res.ok) return false
    const data = await res.json()
    if (!data || !Array.isArray(data.nodes) || !data.nodes.length) return false
    data.nodes.forEach(normalizeNode)
    graph.configure(data)                 // configure сам чистит старый граф (keep_old не задан)
    graph.setDirtyCanvas(true, true)
    if (liteCanvas) liteCanvas.setDirty(true, true)
    // Файловые карточки от устройств сразу сжимаем до «максимально низкой» высоты (06.10.26):
    // название при этом остаётся целым — расчёт см. в fitFileCard.
    for (const n of graph._nodes || []) if (isDeviceFileCard(n)) fitFileCard(n)
    return true
  } catch (e) { console.error(e); return false }
}

// --- Подбор ширины новой задачи под название --------------------------------------
// Ярослав 01.10.26: «при первом сохранении новой задачи подбирая её ширину, чтобы текст шапки
// полностью влезал; если название длинное — допускается перенос на две строки».
// Делается один раз для только что созданной карточки (флаг _fitOnce с момента создания):
//   • влезает в одну строку  -> ширина = сколько нужно тексту (не меньше 100, не больше 200);
//   • не влезает и в 200     -> ширина 200, название переносится на две строки, карточка выше на строку.
const FIT_W_MIN = 100    // минимум ширины (совпадает с минимальным ресайзом)
const FIT_W_MAX = 200    // максимум ширины: длинное название уходит на несколько строк
const FIT_PAD = 24       // тот же боковой отступ, что при отрисовке названия (w - 24)
const FIT_FOOTER = 13    // нижняя полоса карточки (статус/срок)
const FIT_H_MAX = 420    // предохранитель: выше карточку автоматом не растягиваем
// Подбор размера карточки под название: ширина — под самую длинную строку (100…200),
// высота — под ВСЕ строки названия (при описании шапке отдают половину высоты, см. отрисовку).
// Размер только УВЕЛИЧИВАЕТСЯ: если текущий уже вмещает название, карточку не трогаем —
// поэтому ручной ресайз пользователя автоподбор никогда не ломает.
// Ставится: 1) при первой правке только что созданной задачи (флаг _fitOnce);
//           2) по кнопке «Сохранить» в панели карточки (просьба Ярослава 01.10.26).
function fitCardToTitle(node) {
  if (!node || !liteCanvas) return
  if ((node.kind || 'task') === 'device') return   // системная плитка свой размер не меняет
  const t = theme().node
  const ctx = liteCanvas.ctx
  // Напоминание: на карточке НЕТ названия — в слоте названия стоит время, снизу дата и каналы.
  // Поэтому считаем ширину по ним (иначе карточка растянулась бы под скопированное название задачи).
  if ((node.kind || 'task') === 'notify') {
    const keep = ctx.font
    ctx.font = `${t.titleWeight} ${t.titleSize}px ${t.titleFamily}`
    const timeW = ctx.measureText(node.reminderTimeText ? node.reminderTimeText() : '').width
    // Повторение рисуется ТЕМ ЖЕ шрифтом, что и статус у задачи (с жирностью темы!),
    // дата — обычным: иначе замер выходит меньше реального и подпись обрезается.
    ctx.font = `${t.statusWeight} ${t.statusSize}px ${t.statusFamily}`
    const repW = node.repeatLabel ? ctx.measureText(node.repeatLabel()).width : 0
    ctx.font = `${t.statusSize}px ${t.statusFamily}`
    const dateW = node.due ? ctx.measureText(shortDate(node.due)).width : 0
    ctx.font = keep
    // Нижняя строка рисуется по УГЛАМ: слева повторение, справа дата, и каждому углу достаётся
    // половина ширины карточки минус поля (footerPad 6 + 2, как в отрисовке). Поэтому ширину
    // считаем так, чтобы в половину влезла ЦЕЛИКОМ самая длинная из них, — иначе «ежедневно»
    // превращалось в «ежедне…» (замер 01.10.26: нужно ≥ 2*(48+8) = 112 px).
    // Нижняя строка идёт ОТ КРАЯ ДО КРАЯ: слева повторение, справа дата — значит карточке нужно
    // вместить обе подписи разом (а не половину каждой): поля 6+6 и зазор 6 между ними.
    const need = repW + dateW + 18
    const wWanted = Math.min(FIT_W_MAX, Math.max(FIT_W_MIN, Math.ceil(Math.max(timeW + 20, need))))
    const cur = node.size || [FIT_W_MIN, 56]
    const W = Math.max(cur[0], wWanted)
    const H = Math.max(cur[1], 56)      // ниже 56 значок, время и нижняя строка не поместятся
    if (Math.abs(W - cur[0]) > 0.5 || Math.abs(H - cur[1]) > 0.5) {
      node.size = [Math.round(W), Math.round(H)]
      liteCanvas.setDirty(true, true)
    }
    return
  }
  const title = String(node.title || '').trim()
  if (!title) return                    // название ещё не ввели — подберём позже
  const keepFont = ctx.font
  ctx.font = `${t.titleWeight} ${t.titleSize}px ${t.titleFamily}`
  const text = t.titleUp ? title.toUpperCase() : title
  const natural = ctx.measureText(text).width + FIT_PAD
  const wWanted = Math.min(FIT_W_MAX, Math.max(FIT_W_MIN, Math.ceil(natural)))
  const cur = node.size || [FIT_W_MIN, 56]
  const W = Math.max(cur[0], wWanted)                              // ширина не уменьшается
  const lines = wrapText(ctx, text, Math.max(20, W - FIT_PAD)).length
  ctx.font = keepFont
  const hasDesc = String(node.description || '').trim().length > 0
  const titleBlock = lines * Math.max(t.titleLine || 15, 12)
  const hNeeded = FIT_FOOTER + titleBlock * (hasDesc ? 2 : 1) + 4
  const H = Math.max(cur[1], Math.min(FIT_H_MAX, hNeeded))
  if (Math.abs(W - cur[0]) > 0.5 || Math.abs(H - cur[1]) > 0.5) {
    node.size = [Math.round(W), Math.round(H)]
    liteCanvas.setDirty(true, true)
  }
}

// --- Файловые карточки от устройств: «максимально низко, но название целиком» (06.10.26) ---
// Карточка-ссылка на файл, приехавший с телефона/планшета (files = путь в device_files/inbox).
// Высота ставится МИНИМАЛЬНОЙ, при которой по формулам отрисовки название НЕ обрезается:
// при описании заголовку отдаётся половина высоты (см. отрисовку ближнего плана), поэтому
// запаса нужно вдвое больше строк названия. Отличие от fitCardToTitle: высота может УМЕНЬШАТЬСЯ.
function isDeviceFileCard(n) {
  if (!n || (n.kind || 'task') === 'device') return false
  const f = filesOf(n)
  if (f.length !== 1) return false
  return /device_files[\\/]inbox[\\/]/i.test(String(f[0]))
}

function fitFileCard(node) {
  if (!node || !liteCanvas) return
  const t = theme().node
  const ctx = liteCanvas.ctx
  const keepFont = ctx.font
  const w = Math.max(FIT_W_MIN, Math.round(node.size ? node.size[0] : FIT_W_MIN))
  const raw = t.titleUp ? String(node.title || '').toUpperCase() : String(node.title || '')
  if (!raw.trim()) return

  // Нижняя полоса (статус + значок вложения) — теми же формулами, что в отрисовке.
  const loc = (lang && lang.value) === 'en' ? 'en' : 'ru'
  const statusText = (STATUS_SHORT[loc] || {})[node.status] || ''
  const badgeS = t.statusSize            // у карточек-файлов всегда есть значок вложения
  let footerAsc = Math.round(t.statusSize * 0.72)
  let footerDesc = Math.round(t.statusSize * 0.2)
  if (statusText) {
    ctx.font = `${t.statusWeight} ${t.statusSize}px ${t.statusFamily}`
    const m = ctx.measureText(statusText)
    if (m.actualBoundingBoxAscent > 0) footerAsc = m.actualBoundingBoxAscent
    if (m.actualBoundingBoxDescent > 0) footerDesc = m.actualBoundingBoxDescent
  }
  const footerH = Math.round(Math.max(footerAsc + footerDesc + 2 + 4, badgeS ? badgeS + 5 : 0))

  // Название: строки считаем тем же шрифтом и полем, что ближний план (w - 24).
  ctx.font = `${t.titleWeight} ${t.titleSize}px ${t.titleFamily}`
  const lines = wrapText(ctx, raw, w - 24).length
  const titleBlock = lines * Math.max(t.titleLine || 15, 12)
  ctx.font = keepFont
  // Надпись «Файл с телефона/планшета» не нужна (просьба Ярослава 06.10.26: связь с панелью
  // и так показывает источник) — у старых карточек из графа убираем её здесь же.
  const d = String(node.description || '').trim()
  if (d === 'Файл с телефона' || d === 'Файл с планшета' ||
      d === 'File from phone' || d === 'File from tablet') node.description = ''
  const hasDesc = String(node.description || '').trim().length > 0
  // Заголовку при описании отрисовка отдаёт половину доступной высоты — отсюда ×2 (+4 — запас).
  const need = hasDesc ? 2 * titleBlock + 4 : titleBlock + 4
  const H = Math.max(28, Math.round(footerH + need))
  const cur = node.size || [w, H]
  if (Math.abs(H - cur[1]) > 0.5 || Math.abs(w - cur[0]) > 0.5) {
    node.size = [w, H]
    liteCanvas.setDirty(true, true)
  }
}

function onNodeChange() {
  // any node mutation (color / title / status / tags) -> force LiteGraph repaint.
  // ВНИМАНИЕ: у LGraphCanvas метод называется setDirty (setDirtyCanvas есть только у LGraph/LGraphNode),
  // иначе здесь летел TypeError «liteCanvas.setDirtyCanvas is not a function» на каждое изменение в инспекторе.
  if (liteCanvas) liteCanvas.setDirty(true, true)
  // Новая карточка подбирает размер под название при первой же правке (в т.ч. при первом сохранении).
  const fresh = selectedNode.value && toRaw(selectedNode.value)
  if (fresh && fresh._fitOnce) {
    if (String(fresh.title || '').trim()) { fitCardToTitle(fresh); fresh._fitOnce = false }
  }
}

// Кнопка «Сохранить» в панели карточки: сохранить и ЗАКРЫТЬ панель.
// Ярослав 01.10.26: «после кнопки сохранить это окно должно пропадать».
// Само сохранение и так идёт автоматом, кнопка остаётся как привычный жест «готово».
function saveAndCloseInspector(payload) {
  if (readOnly.value) { roBlocked(); return }
  // Перед сохранением подгоняем карточку под название, чтобы заголовок влез целиком
  // (Ярослав 01.10.26: «после нажатия кнопки сохранить подбирай высоту/ширину, чтобы весь текст заголовка влез»).
  const n = selectedNode.value && toRaw(selectedNode.value)
  if (n) fitCardToTitle(n)
  // Поле «Подзадачи» в панели (Ярослав 01.10.26): по названию в строке — карточки создаются
  // сразу и привязываются к основной. Само поле не сохраняется: после панель закрывается,
  // а подзадачи живут на холсте своими карточками.
  const names = (payload && Array.isArray(payload.subtasks)) ? payload.subtasks : []
  if (n && names.length) {
    names.forEach((name, i) => {
      const child = createSubtask(n, i, names.length)
      if (!child) return
      child.title = name
      fitCardToTitle(child)     // подзадача сразу подбирает размер под своё название
      child._fitOnce = false
    })
    if (liteCanvas) liteCanvas.setDirty(true, true)
  }
  saveGraph()
  selectedNode.value = null                                  // закрывает панель (v-if="selectedNode")
  if (liteCanvas && liteCanvas.selectNode) liteCanvas.selectNode(null, false)   // снять и выделение на холсте
}

// Кнопка «+⏰» в панели карточки (между «Сохранить» и «Удалить»): создаёт карточку-напоминание,
// СВЯЗАННУЮ с редактируемой задачей — ставим её в свободное место справа и привязываем
// родитель → напоминание (просьба Ярослава 01.10.26). Панель остаётся открытой на исходной
// карточке, чтобы можно было продолжать её править.
// Наполнение новой карточки-напоминания. Задача и описание КОПИРУЮТСЯ с основной карточки
// (Ярослав 01.10.26: «описания и задача должны копироваться с основной карточки») — это снимок
// на момент создания: дальше напоминание живёт своей жизнью. Срок — сегодня + ближайший круглый час.
function fillReminderDefaults(node, src) {
  node.kind = 'notify'
  node.color = notifyColor()
  node.title = (src && String(src.title || '').trim()) || t('notifyTitle')
  node.description = (src && src.description) || ''
  node.due = todayISO()
  node.remindTime = defaultRemindTime()
  node.repeatMode = 'once'
  // Все три канала по умолчанию (просьба Ярослава 06.10.26): компьютер + телефон + планшет;
  // ненужные снимаются галочками в панели напоминания.
  node.channels = ['pc', 'phone', 'tablet']
}
// Создать напоминание рядом с исходной карточкой и связать их (родитель → напоминание).
function addNotifyFrom(src) {
  if (!graph || !src) return null
  const child = createSubtask(toRaw(src), 0, 1)    // свободное место справа + связь с родителем
  if (!child) return null
  fillReminderDefaults(child, toRaw(src))
  fitCardToTitle(child)
  child._fitOnce = false
  if (liteCanvas) liteCanvas.setDirty(true, true)
  saveGraph()                                      // сразу фиксируем в graph.json
  return child
}
// Закрыть панель карточки — ровно так же, как после «Сохранить»: снять selectedNode (по нему
// v-if у панели) и снять выделение на холсте.
function closeInspectorPanel() {
  selectedNode.value = null
  if (liteCanvas && liteCanvas.selectNode) liteCanvas.selectNode(null, false)
}
// Кнопка «+⏰» в панели задачи: напоминание к РЕДАКТИРУЕМОЙ карточке. Панель ЗАКРЫВАЕТСЯ
// (просьба Ярослава 01.10.26: «когда в карточке задачи нажимаешь кнопку добавить напоминание,
// меню должно закрываться») — раньше оставалась открытой.
function inspAddNotify() {
  if (readOnly.value) { roBlocked(); return }
  const parent = selectedNode.value && toRaw(selectedNode.value)
  if (!parent) return
  const child = addNotifyFrom(parent)
  if (!child) return
  closeInspectorPanel()
}
// Кнопка сайдбара «+ Напоминание»: задачу берём у ВЫДЕЛЕННОЙ карточки; если ничего не выделено —
// неблокирующая подсказка (вариант выбран Ярославом 01.10.26).
function onAddNotify() {
  if (readOnly.value) { roBlocked(); return }
  const sel = (liteCanvas && liteCanvas.selected_nodes && Object.values(liteCanvas.selected_nodes)[0])
    || (selectedNode.value && toRaw(selectedNode.value))
  if (!sel) { flash(t('remNoCard')); return }
  const child = addNotifyFrom(sel)
  if (child) closeInspectorPanel()          // и открытая панель карточки закрывается — как у «+⏰»
}

async function notify(channel, text) {
  try {
    const res = await fetch('/api/notify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ channel, text }) })
    const data = await res.json()
    if (data.status === 'ok') flash('Отправлено в ' + channel)
    else flash(data.error || 'Ошибка отправки')
  } catch (e) { flash('Нет подключения к backend.py') }
}

// Сообщения больше НЕ всплывающим окном: оно перекрывало работу и требовало нажатия «ОК».
// Теперь это плашка внизу экрана, которая сама исчезает через 2.6 с.
// Ярослав 01.10.26: «кнопка закрыть это уведомление ... только мешается».
const toastMsg = ref('')
let toastTimer = null
function flash(msg) {
  toastMsg.value = msg
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMsg.value = '' }, 2600)
}

window.addEventListener('keydown', (ev) => {
  if (ev.key === 'Escape' && descReaderNode.value) { descReaderNode.value = null; return }
  if (ev.key === 'Escape' && viewImage.value) { viewImage.value = ''; return }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === 's') { ev.preventDefault(); saveGraph() }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === 'o') { ev.preventDefault(); loadGraph() }
  if ((ev.key === 'Delete' || ev.key === 'Backspace') && selectedNode.value && !ev.target.matches('input,textarea')) { ev.preventDefault(); deleteSelected() }
})

// Ctrl+V с картинкой в буфере — в открытую карточку (см. onPaste).
document.addEventListener('paste', onPaste)



// Рамка активного окна: тонкая линия по периметру, толщина постоянна на экране (1 px).
function animate() {
  watchAutoSave()
  stepFollowLag()                     // «верёвочка»: подзадачи догоняют перетаскиваемую карточку
  if (liteCanvas) liteCanvas.draw()
  requestAnimationFrame(animate)
}

// Ждём, пока холст станет в layout, затем инициализируем LiteGraph (и поднимаем сохранённый граф).
onMounted(() => {
  applyTheme(themeName.value)          // тема ставится до initCanvas: холст сразу создаётся в ней
  if (hadSavedTheme) pushThemeToServer(themeName.value)   // тему своего браузера отдаём телефону
  // Первый запуск после появления этой возможности: сервер темы ещё не знает — отдаём свою.
  fetch('/api/ui_state', { cache: 'no-store' }).then(r => r.json())
    .then(s => { if (s && !s.theme) pushThemeToServer(themeName.value) }).catch(() => {})
  initCanvas().catch(e => console.error('[plannertate] init failed', e))
  loadLicense()                        // кнопку «Лицензия» показываем, только если её ещё не оплатили
  loadPhoneState()                     // первый запуск: предложить поставить приложение на телефон
})

// Переключение темы из сайдбара: и CSS-интерфейс, и отрисовка холста.
watch(themeName, (id) => { applyTheme(id); pushThemeToServer(id) })

// Тема отправляется не только при изменении: пока окно открыто, обновляем запись при возврате
// на вкладку и раз в пять минут. Так телефон рано или поздно получит верную тему сам, даже если
// страницу не перезагружали (разбор бага 03.10.26: без F5 тема не уезжала).
const themePushTimer = setInterval(() => pushThemeToServer(themeName.value), 5 * 60 * 1000)
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) pushThemeToServer(themeName.value)
})

onBeforeUnmount(() => {
  clearInterval(themePushTimer)
  hideFileTip()
  if (canvasEl.value) {
    canvasEl.value.removeEventListener('mousemove', onCanvasHover)
    canvasEl.value.removeEventListener('mouseleave', hideFileTip)
    canvasEl.value.removeEventListener('wheel', onCanvasWheel)
    canvasEl.value.removeEventListener('mousedown', hideFileTip)
  }
  document.removeEventListener('pointermove', onDocMouseMove)
  document.removeEventListener('pointerup', onDocMouseUp)
  document.removeEventListener('pointerdown', onDocMouseDownCapture, true)
  if (removeTouchSupport) { removeTouchSupport(); removeTouchSupport = null }
  graph = null; liteCanvas = null
})
</script>

<template>
  <div class="app" :class="{ ro: readOnly }">
    <!-- Сайдбар -->
    <aside class="side" :class="{ 'side-hidden': !sideOpen }">
      <div class="side-head">
        <!-- Название: левый клик — страница поддержки автора (03.10.26). Справа — кнопка лицензии. -->
          <div class="logo" :title="t('licLogo')" @click="openDonate"><span class="lg-app">Planner</span><span class="lg-ma">Ta</span><span class="lg-te">Te</span></div>
          <button v-if="licenseDone === false" class="lic-btn" @click="showLicense = true">{{ t('licBtn') }}</button>
      </div>

      <button class="btn primary center" @click="onAddTask">{{ t('addTask') }}</button>
      <button class="btn center" @click="onAddNotify">{{ t('addNotify') }}</button>

      <div class="divider"></div>

      <!-- Интерфейс: 10 тем (палитры — src/themes.js, переменные — styles.css).
           Показываем только активную; остальные — в списке ниже (клик по фону закрывает). -->
      <div class="field">
        <label class="label">Интерфейс</label>
        <div class="theme-picker">
          <button class="theme-trigger" :title="THEMES[themeName].hint" @click="toggleThemeList">
            <span class="theme-prev" :style="{ background: THEMES[themeName].preview.bg }">
              <span class="tp-card" :style="{ background: THEMES[themeName].preview.card, borderColor: THEMES[themeName].preview.border }"></span>
              <span class="tp-stripe" :style="{ background: THEMES[themeName].preview.stripe }"></span>
            </span>
            <span class="theme-name">{{ THEMES[themeName].label[lang] || THEMES[themeName].label.ru }}</span>
            <span class="theme-caret">▾</span>
          </button>
          <template v-if="themeOpen">
            <div class="theme-backdrop" @click="themeOpen = false"></div>
            <div ref="themePopEl" class="theme-pop">
              <button v-for="id in THEME_IDS" :key="id" class="theme-item"
                      :class="{ on: themeName === id }" :data-theme-key="id"
                      :title="THEMES[id].hint" @click="pickTheme(id)">
                <span class="theme-prev" :style="{ background: THEMES[id].preview.bg }">
                  <span class="tp-card" :style="{ background: THEMES[id].preview.card, borderColor: THEMES[id].preview.border }"></span>
                  <span class="tp-stripe" :style="{ background: THEMES[id].preview.stripe }"></span>
                </span>
                <span class="theme-name">{{ THEMES[id].label[lang] || THEMES[id].label.ru }}</span>
              </button>
            </div>
          </template>
        </div>

        <!-- «Своя» тема: настройки показываем только когда она выбрана -->
        <div v-if="themeName === CUSTOM_ID && customOpen" class="custom-theme">
          <label class="label">{{ t('thPalette') }}</label>
          <select class="select" :value="custom.base" @change="customSet({ base: $event.target.value })">
            <option v-for="id in THEME_IDS.filter(x => x !== CUSTOM_ID)" :key="id" :value="id">
              {{ THEMES[id].label[lang] || THEMES[id].label.ru }}
            </option>
          </select>

          <label class="label">{{ t('thFont') }}</label>
          <div class="font-picker">
            <button class="theme-trigger" @click="fontOpen = !fontOpen">
              <span class="fname" :style="custom.font ? { fontFamily: custom.font } : null">
                {{ custom.font || t('thFontPh') }}
              </span>
              <span class="theme-caret">▾</span>
            </button>
            <template v-if="fontOpen">
              <div class="theme-backdrop" @click="fontOpen = false"></div>
              <div class="font-pop">
                <input class="inp" v-model="fontQuery" :placeholder="t('thFontSearch')"
                       @keydown.enter="pickFont(fontQuery)">
                <div class="font-list">
                  <button class="theme-item" @click="pickFont('')">
                    <span class="theme-name">{{ t('thFontDef') }}</span>
                  </button>
                  <button v-for="f in fontShown" :key="f" class="theme-item"
                          :class="{ on: f === custom.font }" @click="pickFont(f)">
                    <span class="theme-name" :style="{ fontFamily: f }">{{ f }}</span>
                  </button>
                  <div v-if="!fontShown.length" class="font-empty">{{ t('thFontNone') }}</div>
                </div>
                <button class="btn center" :disabled="fontBusy" @click="loadSystemFonts">
                  {{ fontBusy ? '…' : t('thFontLoad') }}
                </button>
              </div>
            </template>
          </div>

          <label class="ct-check">
            <input type="checkbox" :checked="custom.weight >= 600"
                   @change="customSet({ weight: $event.target.checked ? 700 : 400 })">
            <span>{{ t('thWeight') }}</span>
          </label>
          <label class="ct-check">
            <input type="checkbox" :checked="custom.caps" @change="customSet({ caps: $event.target.checked })">
            <span>{{ t('thCaps') }}</span>
          </label>

          <button class="btn primary center" @click="customOpen = false">{{ t('thSave') }}</button>
        </div>
      </div>

      <div class="divider"></div>

      <!-- Выбор языка перенесён в один ряд с кнопкой «Свернуть» (просьба Ярослава 03.10.26):
           кнопка слева, язык справа; подпись «Язык» убрана — и так понятно, что это язык. -->

      <!-- Кнопка «Сохранить» убрана 01.10.26 (просьба Ярослава): автосохранение включено,
           а Ctrl+S на всякий случай остался. -->

      <button class="btn" @click="toggleReminderList"><span class="emo">⏰</span> {{ t('notify') }}</button>

      <!-- Подпись «PlannerTaTe v0.5 — LiteGraph / Прямоугольные узлы + коннекторы» удалена 01.10.26
           по просьбе Ярослава. -->

      <!-- Низ панели: кнопка «Свернуть» и подсказка по управлению карточками.
           Кнопка именно здесь: панель карточки (правый клик) перекрывает ВЕРХ сайдбара. -->
      <div class="side-foot">
        <!-- Установка на телефон — доступна в любой момент (03.10.26). Оформление — общий класс
             .btn, как у «Списка напоминаний»: раньше своя раскраска в светлых темах сливалась
             с фоном панели (просьба Ярослава 03.10.26). -->
        <button class="btn" @click="openInstall('phone')"><span class="emo">📱</span> {{ t('phoneBtn') }}</button>
        <button class="btn" @click="openInstall('tablet')"><span class="emo">📟</span> {{ t('phoneBtnTab') }}</button>

        <!-- «Установить MCP на Гермес» (06.10.26, просьба Ярослава): готовое сообщение с файлами —
             его копируют и отправляют Гермесу, тот подключает сервер сам. -->
        <button class="btn" @click="openMcpPanel"><span class="emo mcp-girl" aria-hidden="true"></span> {{ t('mcpBtn') }}</button>

        <div class="foot-row">
          <button v-if="!readOnly" class="icon-btn" :title="t('backupTitle')" @click="makeBackup"><span class="emo">💾</span></button>
          <button v-if="!readOnly" class="icon-btn" :title="t('restoreTitle')" @click="showRestore = true"><span class="emo">♻️</span></button>
          <span class="lang-lbl">{{ t('lang_label') }}</span>
          <select v-model="lang" class="select lang-sel">
            <option value="ru">Русский</option>
            <option value="en">English</option>
          </select>
        </div>
        <div class="side-hint">
          <div v-for="(h, i) in t('selectHint')" :key="i" class="hint-line">{{ h }}</div>
        </div>
        <!-- «Свернуть» — в САМОМ НИЗУ панели (просьба Ярослава 04.10.26): в одном ряду
             с копией и выбором языка ей не хватало места. -->
        <button class="collapse-btn" @click="setSideOpen(false)">‹ {{ t('collapse') }}</button>
      </div>
    </aside>

    <!-- Кнопка на левой кромке: возвращает свёрнутую панель -->
    <button v-if="!sideOpen" class="side-restore" :title="t('expand')" @click="setSideOpen(true)">›</button>

    <!-- Подсказка у значка ссылки: имя файла и путь целиком. Позиция — по курсору (fixed),
       кликам не мешает (pointer-events: none). -->
    <div v-if="fileTip" class="file-tip" :style="{ left: fileTip.x + 'px', top: fileTip.y + 'px' }">
    <b>{{ fileTip.name }}</b>
    <span>{{ fileTip.path }}</span>
    </div>

    <!-- Холст -->
    <div id="canvasWrap" class="canvas-wrap">
      <canvas id="canvasEl" ref="canvasEl"></canvas>
      <LiteInspector v-if="selectedNode && selectedNode.kind !== 'notify' && selectedNode.kind !== 'device'" :node="selectedNode" :lang="lang" :x="inspectorPos.x" :y="inspectorPos.y" @delete="deleteSelected" @save="saveAndCloseInspector" @notify="inspAddNotify" @change="onNodeChange" @view="viewImage = $event" @image="attachImage(selectedNode, $event)"
                 @pick="pickFileLink(selectedNode)" @open="(p) => openFileLink(p, selectedNode)" />
      <!-- Напоминание редактируется СВОЕЙ панелью: нет подзадач, рисунка и статуса; задача и
           описание показаны серым (скопированы с основной карточки), есть дата/время, количество
           и повторения, каналы доставки. -->
      <ReminderPanel v-else-if="selectedNode && selectedNode.kind !== 'device'" :node="selectedNode" :lang="lang" :x="inspectorPos.x" :y="inspectorPos.y" @delete="deleteSelected" @save="saveAndCloseInspector" @change="onNodeChange" />
      <!-- Панель лицензии: «Оцените приложение», четыре строки с выбором, внизу сумма и «Оплатить». -->
    <LicensePanel v-if="showLicense" :lang="lang" :x="24" :y="70"
                  @close="showLicense = false" @pay="onLicensePay" />
    <!-- Установка на телефон: свой адрес в сети, QR-код, ключ (03.10.26) -->
    <PhoneInstallPanel v-if="showPhone" :lang="lang" :device="installDevice" :state="phoneState" :x="24" :y="70"
                       @close="showPhone = false" @refresh="loadPhoneState" />
    <!-- Восстановление графа из резервной копии (04.10.26) -->
    <RestorePanel v-if="showRestore" :lang="lang" :x="24" :y="70"
                  @close="showRestore = false" @restore="doRestore" />

    <!-- Окно первого запуска: предлагаем поставить приложение на телефон -->
    <div v-if="showPhoneAsk" class="phone-ask-wrap">
      <div class="phone-ask">
        <div class="phone-ask-q">{{ t('phoneAsk') }}</div>
        <div class="phone-ask-btns">
          <button class="phone-ask-yes" @click="phoneAskYes">{{ t('phoneAskYes') }}</button>
          <button class="phone-ask-later" @click="phoneAskLater">{{ t('phoneAskLater') }}</button>
        </div>
      </div>
    </div>

    <!-- «Установить MCP на Гермес»: статус и готовое сообщение для Гермеса (06.10.26) -->
    <div v-if="showMcp" class="phone-ask-wrap" @click.self="showMcp = false">
      <div class="phone-ask mcp-ask">
        <div class="phone-ask-q">{{ t('mcpTitle') }}</div>
        <div class="mcp-status" :class="{ ok: mcpInfo && mcpInfo.installed }">
          {{ mcpInfo == null ? t('mcpChecking') : (mcpInfo.installed ? t('mcpInstalled') : t('mcpNotInstalled')) }}
        </div>
        <div class="mcp-about">{{ t('mcpAbout') }}</div>
        <pre v-if="mcpInfo && mcpInfo.text" class="mcp-text">{{ mcpInfo.text }}</pre>
        <div class="phone-ask-btns">
          <button v-if="mcpInfo && mcpInfo.text" class="phone-ask-yes" @click="copyMcpText">{{ t('mcpCopy') }}</button>
          <button class="phone-ask-later" @click="showMcp = false">{{ t('close') }}</button>
        </div>
      </div>
    </div>

    <!-- Список напоминаний: таблица всех напоминаний. Заменил прежнюю панель отправки
           в Telegram/Макс (NotifyPanel.vue больше не открывается — файл оставлен). -->
      <div class="rlist-wrap">
        <ReminderList v-if="showNotify" :lang="lang" :rows="reminderRows"
                      @close="showNotify = false" @delete="deleteReminder" @reveal="revealReminder" />
      </div>

      <!-- Пометка «только просмотр» (сохранённая копия на телефоне/планшете) -->
      <!-- Пометка «только просмотр»: на телефоне/планшете прячем её, когда открыта боковая
           панель — там она перекрывается панелью (просьба Ярослава 04.10.26). -->
      <div v-if="readOnly && !sideOpen" class="ro-badge">{{ t('roNotice') }}</div>

    <!-- Просмотр рисунка на весь экран: клик по фону или Esc закрывает -->
      <!-- Полноэкранная читалка описания: открывается кнопкой-лупой на карточке (телефон) -->
      <DescReader v-if="descReaderNode" :title="String(descReaderNode.title || '')"
                  :text="String(descReaderNode.description || '')" :lang="lang"
                  @close="descReaderNode = null" />

      <div v-if="viewImage" class="img-modal" @click="viewImage = ''">
        <img :src="viewImage" alt="" />
      </div>
    </div>
  </div>
  <!-- Плашка сообщений (например, «Не удалось сохранить»): не блокирует работу. -->
  <div v-if="toastMsg" class="toast">{{ toastMsg }}</div>
</template>

<style>
/* Своей раскраски у кнопки установки на телефон больше нет (03.10.26). Была .phone-btn с
   background: var(--card) — в светлых темах этот цвет совпадает с фоном панели, и кнопка
   становилась невидимой. Теперь это обычный .btn, как у «Списка напоминаний»: цвета берутся
   из темы (--btn-bg / --btn-text / --btn-border), поэтому кнопка видна в любой теме. */

/* Окно первого запуска «Установить приложение на телефон Android?» */
.phone-ask-wrap {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.phone-ask {
  max-width: 420px;
  padding: 22px 22px 16px;
  border-radius: 14px;
  /* Цвета — из темы приложения (06.10.26, просьба Ярослава): как у панелей (.inspector/.ph).
     Раньше здесь стояли имена --card/--border/--foreground, которых нет ни в одной теме, —
     окно всегда рисовалось запасными тёмными цветами и выбивалось из светлых тем. */
  background: var(--panel-bg, #2a2a2e);
  border: 1px solid var(--panel-border, rgba(127, 127, 127, 0.35));
  color: var(--text, #e8e8e8);
  box-shadow: var(--panel-shadow, 0 18px 48px rgba(0, 0, 0, 0.45));
  backdrop-filter: var(--panel-blur, none);
}
.phone-ask-q { font-size: 16px; line-height: 1.4; margin-bottom: 16px; }
.phone-ask-btns { display: flex; gap: 10px; justify-content: flex-end; }
.phone-ask-yes, .phone-ask-later {
  padding: 9px 16px;
  border-radius: 10px;
  font-size: 14px;
  cursor: pointer;
}
/* Кнопки меню — в цветах темы, как .btn.primary / .btn (06.10.26, просьба Ярослава). */
.phone-ask-yes {
  border: none; font-weight: 600;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  color: var(--primary-text, #fff);
  box-shadow: var(--shadow-primary);
}
.phone-ask-yes:hover { filter: brightness(1.1); }
.phone-ask-later {
  border: 1px solid var(--btn-border, rgba(127, 127, 127, 0.4));
  background: var(--btn-bg, transparent);
  color: var(--btn-text, #e8e8e8);
}
.phone-ask-later:hover { background: var(--btn-hover, rgba(127, 127, 127, 0.15)); }
/* Окно «Установить MCP на Гермес» (06.10.26): шире обычного, текст сообщения — моноширинный */
.mcp-ask { max-width: 640px; }
.mcp-status { font-size: 13px; color: #e08a3c; margin-bottom: 8px; }
.mcp-status.ok { color: #7bc67b; }
.mcp-about { font-size: 13px; line-height: 1.45; color: var(--muted, #99a0c0); margin-bottom: 10px; }
/* Значок «Гермес» у кнопки MCP (06.10.26, просьба Ярослава): чёрно-белая «девочка» из логотипа
   Hermes. Цвет берём от текста кнопки (маска + currentColor) — читается в любой из тем. */
.mcp-girl {
  display: inline-block; width: 1.15em; height: 1.15em; background: currentColor;
  vertical-align: -0.18em;
  -webkit-mask: url(/hermes-girl.png) center / contain no-repeat;
  mask: url(/hermes-girl.png) center / contain no-repeat;
}
.mcp-text {
  white-space: pre-wrap; word-break: break-word; text-align: left;
  font: 12px/1.5 ui-monospace, Consolas, monospace;
  background: var(--input-bg, rgba(127, 127, 127, 0.10));
  border: 1px solid var(--input-border, rgba(127, 127, 127, 0.35));
  border-radius: 8px; padding: 10px; margin: 0 0 14px 0;
  max-height: 300px; overflow: auto;
}
/* Все стили интерфейса — в src/styles.css (переменные трёх тем + классы).
   Здесь оставлено только то, что относится к самому компоненту. */
canvas#canvasEl { width: 100%; height: 100%; display: block; touch-action: none; }

/* Подсказка у значка ссылки: имя файла и путь целиком (Ярослав 03.10.26).
   Позиция — fixed, по курсору; pointer-events: none, чтобы не мешать клику по значку. */
.file-tip {
  position: fixed; z-index: 60; pointer-events: none; max-width: 360px;
  padding: 5px 8px; border-radius: 6px;
  background: var(--input-bg); border: 1px solid var(--input-border);
  box-shadow: 0 4px 14px rgba(0, 0, 0, .3);
  font-size: 11px; line-height: 1.35; color: var(--text);
}
.file-tip b { display: block; font-weight: 600; word-break: break-all; }
.file-tip span { display: block; margin-top: 2px; font-size: 10px; color: var(--muted); word-break: break-all; }
</style>
