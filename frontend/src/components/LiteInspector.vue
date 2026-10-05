<script setup>
import { computed, ref, watch } from 'vue'
import { COLOR_NAMES, COLOR_NAMES_EN, NODE_COLORS, STATUS_ORDER, STATUS_FULL } from '../i18n.js'
import DateField from './DateField.vue'

const props = defineProps({ node: Object, lang: String, x: Number, y: Number })
const emit = defineEmits(['delete', 'save', 'change', 'view', 'image', 'pick', 'open'])

// Рисунок: файл выбирается здесь, а уменьшает/кладёт в узел App.vue (attachImage).
const fileEl = ref(null)
function pickFile() {
  if (!fileEl.value) return
  fileEl.value.value = ''
  fileEl.value.click()
}
function onFile(e) {
  const f = e.target.files && e.target.files[0]
  if (f) emit('image', f)
  e.target.value = ''
}
function clearImage() { props.node.image = ''; emit('change') }
// Ссылки на файл: путь целиком живёт в узле (до MAX_LINKS штук), диалог выбора открывает
// сервер — App.vue: браузер путь файла не отдаёт. Прошлая версия хранила одну ссылку в node.file.
const MAX_LINKS = 5
const links = computed(() => {
  const a = Array.isArray(props.node.files) ? props.node.files.filter(Boolean) : []
  if (!a.length && props.node.file) a.push(props.node.file)   // граф прошлой версии
  return a.slice(0, MAX_LINKS)
})
function fileLabel(p) { return String(p || '').split(/[\\/]/).pop() || String(p || '') }
function removeLink(i) {
  const a = links.value.slice()
  a.splice(i, 1)
  props.node.files = a
  emit('change')
}
// Затенение рисунка — ползунок из ТРЁХ позиций, по центру «Авто» (Ярослав 01.10.26).
// Слева направо: выключено (off) — авто (auto, по приближению) — включено (on). См. onDrawBackground в App.vue.
const DIM_ORDER = ['off', 'auto', 'on']
const DIM_LABELS_RU = ['выключено', 'авто', 'включено']
const DIM_LABELS_EN = ['off', 'auto', 'on']
const dimIndex = computed(() => Math.max(0, DIM_ORDER.indexOf(props.node.dimMode || 'auto')))
function setDimIndex(i) { props.node.dimMode = DIM_ORDER[Number(i)] || 'auto'; emit('change') }

function setLabel(e) { props.node.title = e.target.value; emit('change') }
function setDesc(e) { props.node.description = e.target.value; emit('change') }
function setTags(e) { props.node.tags = e.target.value.split(',').map(t => t.trim()).filter(Boolean); emit('change') }
// Меняем только акцент (рамка, полоса связи): заливку карточки рисует активная тема,
// поэтому bgcolor не трогаем — иначе он перекрыл бы «стекло» и градиент холста.
function setColor(c) {
  if (props.node.color === c) return
  props.node.color = c
  emit('change')
}
// В карточке «пустой» статус = '' (иначе рисовалась бы пустая подпись в углу).
function setStatus(v) { props.node.status = (v === 'none' ? '' : v); emit('change') }
// Дата приходит из DateField строкой 'YYYY-MM-DD' (свой календарь, см. DateField.vue);
// пустая строка — очистка. Формат хранения в graph.json не менялся.
function setDue(v) { props.node.due = v || ''; emit('change') }

// Подзадачи (просьба Ярослава 01.10.26): по названию в строке. Это НЕ поле карточки и оно
// не сохраняется: по кнопке «Сохранить» App.vue создаёт по карточке на каждую строку и
// связывает их с основной, после чего панель закрывается. Поле стартует пустым для каждой карточки.
const subtasks = ref('')
watch(() => (props.node && props.node.id), () => { subtasks.value = '' })
function emitSave() {
  const names = subtasks.value.split('\n').map(s => s.trim()).filter(Boolean)
  emit('save', { subtasks: names })
}

const ru = computed(() => props.lang === 'ru')
const statusOptions = computed(() => {
  const dict = STATUS_FULL[ru.value ? 'ru' : 'en']
  return STATUS_ORDER.map(k => [k, dict[k]])
})
// Названия цветов тоже локализуем (было: всегда русские подписи, хотя COLOR_NAMES_EN уже был).
// Значение option — всегда hex из NODE_COLORS (ключи там русские), а подпись берём по языку;
// COLOR_NAMES_EN совпадает по порядку с COLOR_NAMES (см. комментарий в i18n.js).
const colorOptions = computed(() => COLOR_NAMES.map((key, i) => ({
  key,
  value: NODE_COLORS[key],
  label: (ru.value ? COLOR_NAMES : COLOR_NAMES_EN)[i] || key,
})))
</script>

<template>
  <div class="inspector" :style="{ '--ox': (x ?? 0) + 'px', '--oy': (y ?? 0) + 'px' }">
    <label class="lbl">{{ ru ? 'Задача' : 'Task' }}</label>
    <input class="inp" :id="'insp-' + node.id" :value="node.title" @input="setLabel($event)" :placeholder="ru ? 'Задача' : 'Task'" />

    <label class="lbl">{{ ru ? 'Описание' : 'Description' }}</label>
    <textarea class="inp ta" rows="3" :value="node.description || ''" @input="setDesc($event)" :placeholder="ru ? 'Что нужно сделать…' : 'What to do…'"></textarea>

    <label class="lbl">{{ ru ? 'Подзадачи' : 'Subtasks' }}</label>
    <textarea class="inp ta" rows="2" v-model="subtasks"
              :placeholder="ru ? 'По одному названию в строке — создадутся и привяжутся к этой задаче' : 'One name per line — created and linked to this task'"></textarea>

    <!-- Статус и срок — одной строкой, каждый подписью сверху: слева статус, справа срок
         (просьба Ярослава 01.10.26). Половины панели им хватает с запасом. -->
    <div class="row2">
      <div class="cell">
        <label class="lbl">{{ ru ? 'Статус' : 'Status' }}</label>
        <select class="sel" :value="node.status || 'none'" @change="setStatus($event.target.value)">
          <option v-for="([val, lbl]) in statusOptions" :key="val" :value="val">{{ lbl }}</option>
        </select>
      </div>
      <div class="cell">
        <label class="lbl">{{ ru ? 'Срок' : 'Due' }}</label>
        <DateField :model="node.due || ''" :lang="lang" @change="setDue" />
      </div>
    </div>

    <!-- Бывший «Рисунок» — теперь «Фон» (просьба Ярослава 03.10.26): это фон карточки. -->
    <label class="lbl">{{ ru ? 'Фон' : 'Background' }}</label>
    <div class="pic-row">
      <div class="pic" :class="{ empty: !node.image }"
           :style="node.image ? { backgroundImage: 'url(' + node.image + ')' } : null"
           :title="node.image ? (ru ? 'Показать целиком' : 'View full size') : ''"
           @click="node.image && $emit('view', node.image)">
        <span v-if="!node.image">{{ ru ? 'нет' : 'none' }}</span>
      </div>
      <div class="pic-btns">
        <button class="mini" @click="pickFile">{{ ru ? 'Выбрать фон…' : 'Choose background…' }}</button>
        <button v-if="node.image" class="mini danger" @click="clearImage">{{ ru ? 'Убрать' : 'Remove' }}</button>
      </div>
    </div>
    <input ref="fileEl" class="hidden-file" type="file" accept="image/*" @change="onFile" />

    <!-- Подпись — в две строки слева, а ползунок с подписями делений — справа от неё
         (просьба Ярослава 01.10.26). Строки подписи выровнены по ползунку и по подписям
         делений: line-height подобран так, чтобы высоты блоков совпали. -->
    <div class="dim-row">
      <label class="lbl dim-lbl"><span>{{ ru ? 'Затенение' : 'Background' }}</span><span>{{ ru ? 'фона' : 'dimming' }}</span></label>
      <div class="dim-wrap">
        <input class="dim-range" type="range" min="0" max="2" step="1" :value="dimIndex" @input="setDimIndex($event.target.value)" />
        <div class="dim-scale">
          <span v-for="(lab, i) in (ru ? DIM_LABELS_RU : DIM_LABELS_EN)" :key="i" :class="{ on: dimIndex === i }">{{ lab }}</span>
        </div>
      </div>
    </div>

    <!-- Ссылки на файл: НЕ как рисунок — надпись слева, кнопка справа от неё, а ниже просто
         строками перечислены имена добавленных файлов (просьба Ярослава 03.10.26).
         Больше MAX_LINKS ссылок не добавить — кнопка гаснет. -->
    <div class="link-head">
      <label class="lbl">{{ ru ? 'Ссылка на файл' : 'File link' }}</label>
      <button class="mini" :disabled="links.length >= MAX_LINKS" @click="$emit('pick')"
              :title="links.length >= MAX_LINKS ? (ru ? 'Больше 5 ссылок в карточке нельзя' : 'Up to 5 links per card') : (ru ? 'Добавить ссылку на файл' : 'Add a file link')">
        {{ ru ? 'Добавить ссылку' : 'Add link' }}
      </button>
    </div>
    <div v-if="links.length" class="link-list">
      <div v-for="(p, i) in links" :key="i" class="link-line" :title="p">
        <span class="link-name" @click="$emit('open', p)">{{ fileLabel(p) }}</span>
        <button class="link-x" :title="ru ? 'Убрать' : 'Remove'" @click="removeLink(i)">×</button>
      </div>
    </div>

    <label class="lbl">{{ ru ? 'Цвет' : 'Color' }}</label>
    <select class="sel" :value="node.color" @change="setColor($event.target.value)">
      <option v-for="opt in colorOptions" :key="opt.key" :value="opt.value">{{ opt.label }}</option>
    </select>

    <div class="btn-row">
      <button class="save-btn" @click="emitSave">{{ ru ? 'Сохранить' : 'Save' }}</button>
      <!-- Создаёт карточку-напоминание, СВЯЗАННУЮ с этой задачей (просьба Ярослава 01.10.26). -->
      <button class="notify-btn" @click="$emit('notify')"
              :title="ru ? 'Создать связанное напоминание' : 'Create a linked reminder'">+<span class="emo">⏰</span></button>
      <button class="del-btn" @click="$emit('delete')">{{ ru ? 'Удалить' : 'Delete' }}</button>
    </div>
  </div>
</template>

<style>
/* Панель свойств карточки. Цвета/радиусы — из переменных активной темы (styles.css),
   поэтому при переключении интерфейса панель перекрашивается вместе со всем окном.
   ВАЖНО: в min()/max() все аргументы обязаны быть одного типа. Было `max(var(--ox),4)`
   (длина + безразмерное число) => объявление «invalid at computed-value time», left/top
   отбрасывались и панель вставала под холстом => «inspector не появляется». Фикс: 4px.
   Нижний отступ считаем от реальной высоты панели (~430px с полем «Подзадачи»), плюс страховка max-height. */
.inspector {
  position: fixed; z-index: 20; width: 236px; padding: 10px 12px;
  background: var(--panel-bg); color: var(--text);
  border: 1px solid var(--panel-border); border-radius: var(--radius);
  box-shadow: var(--panel-shadow); backdrop-filter: var(--panel-blur);
  max-height: calc(100vh - 12px); overflow-y: auto;
  left: min(max(var(--ox), 4px), calc(100vw - 248px));
  /* 545 px — измеренная высота панели задачи в сборе (+запас). Было 430: при правом клике
     в нижней части экрана панель уезжала за нижний край и кнопки становились недоступны.
     Внешний max(4px, …) — страховка для коротких окон. */
  top: max(4px, min(max(var(--oy), 4px), calc(100vh - 545px)));
}
.btn-row { display: flex; gap: 6px; margin-top: 10px; align-items: stretch; }
/* Статус и срок делят ширину панели пополам: подпись сверху, поле во всю половину. */
.row2 { display: flex; gap: 8px; }
.row2 .cell { flex: 1 1 0; min-width: 0; }
.row2 .cell .lbl { margin-top: 8px; }
.notify-btn {
  flex: 0 0 auto; padding: 7px 8px; cursor: pointer; font-size: 12px; line-height: 1;
  font-family: inherit; border-radius: var(--radius-sm);
  background: var(--btn-bg); color: var(--btn-text); border: 1px solid var(--btn-border);
}
.notify-btn:hover { background: var(--btn-hover); }
.save-btn {
  flex: 1 1 auto; min-width: 0; padding: 7px; border: none; border-radius: var(--radius-sm); cursor: pointer;
  background: linear-gradient(135deg, var(--accent), var(--accent2)); color: var(--primary-text);
  font-size: 12px; font-family: inherit; font-weight: 600;
}
.save-btn:hover { filter: brightness(1.08); }
.lbl { display: block; font-size: 11px; color: var(--muted); margin: 8px 0 4px; }
/* Одна высота у полей и списков: у <select> своя «родная» высота (33 px), у <input> — своя (28 px),
   из-за чего «Статус» и «Срок» выглядели разного размера (жалоба Ярослава 01.10.26). Многострочные
   (.ta) не трогаем — у них своя высота. */
.inspector .inp, .inspector .sel, .inspector .df-inp, .inspector .df-btn { height: 32px; box-sizing: border-box; }
/* 03.10.26 (просьба Ярослава): списки «Статус» и «Цвет», поле «Срок» и кнопка-календарик — на 25% ниже
   (32 → 24 px). Только в панели задачи: панель напоминания носит те же классы плюс .rem, её не трогаем.
   Однострочные поля .inp (Задача, Описание) тоже остаются 32 px — просили лишь перечисленные элементы. */
.inspector:not(.rem) .sel, .inspector:not(.rem) .df-inp, .inspector:not(.rem) .df-btn { height: 24px; }
.inspector .inp.ta { height: auto; }
.inp, .sel {
  width: 100%; padding: 6px 8px; background: var(--input-bg); color: var(--input-text);
  border: 1px solid var(--input-border); border-radius: 6px; box-sizing: border-box; font-family: inherit;
}
/* В списках 24px — вертикальные отступы уменьшены, иначе при border-box текст зажимается (только панель задачи).
   03.10.26 (Ярослав: «в статусе снизу обрезаются буквы с хвостиками типа Д»): у <select> шрифт НЕ наследуется —
   браузер даёт свои 13.33px, строка выходит ~17.8px и в поле 24px (16px внутри) низ глифов режется. Делаем как в
   соседнем «Сроке»: font-size 12px (там это .date) + отступы 2px, тогда строка ~16px влезает с запасом. */
.inspector:not(.rem) .sel { font-size: 12px; padding: 2px 8px; }
.inp:focus, .sel:focus { outline: none; border-color: var(--accent); }
.ta { resize: vertical; min-height: 52px; font-size: 12px; }
.date { font-size: 12px; }
.del-btn {
  flex: 0 0 auto; padding: 7px 10px; cursor: pointer; font-size: 12px; font-family: inherit;
  background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border);
  border-radius: var(--radius-sm);
}
.del-btn:hover { filter: brightness(1.15); }
.pic-row { display: flex; gap: 8px; align-items: stretch; }
.pic {
  flex: 0 0 96px; height: 56px; border-radius: var(--radius-sm); border: 1px solid var(--input-border);
  background: var(--input-bg) center/cover no-repeat; display: flex; align-items: center;
  justify-content: center; font-size: 11px; color: var(--muted); overflow: hidden; cursor: zoom-in;
}
.pic.empty { cursor: default; border-style: dashed; }
/* Ссылки на файл: надпись слева, кнопка справа от неё, ниже — строки с именами файлов
   (просьба Ярослава 03.10.26). Файлы на диске НЕ копируются, поэтому тут только имена. */
.link-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 8px; }
.link-head .lbl { margin: 8px 0 4px; }
.link-list { display: flex; flex-direction: column; gap: 3px; }
.link-line {
  display: flex; align-items: center; gap: 6px; padding: 3px 4px 3px 7px;
  background: var(--input-bg); border: 1px solid var(--input-border); border-radius: 6px;
}
.link-name {
  flex: 1 1 auto; min-width: 0; font-size: 11px; color: var(--text); cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.link-name:hover { color: var(--accent); text-decoration: underline; }
.link-x {
  flex: 0 0 auto; width: 18px; height: 18px; padding: 0; line-height: 1; cursor: pointer;
  background: var(--danger-bg); color: var(--danger-text); border: 1px solid var(--danger-border);
  border-radius: 4px; font-size: 12px; font-family: inherit;
}
.link-x:hover { filter: brightness(1.15); }
.mini:disabled { opacity: .5; cursor: default; }
.pic-btns { flex: 1; display: flex; flex-direction: column; gap: 6px; justify-content: center; }
/* 03.10.26 (просьба Ярослава): кнопки «Выбрать фон», «Убрать», «Добавить ссылку» — на 25% ниже.
   Было padding 6px/6px при высоте 29 px (6+6 отступы + рамки 2 + строка 15); 2.375px даёт ровно 21.75 px = 29 × 0.75.
   По ширине всё как было — горизонтальные отступы те же 8px. */
.mini {
  padding: 2.375px 8px; background: var(--btn-bg); color: var(--btn-text); border: 1px solid var(--btn-border);
  border-radius: 6px; cursor: pointer; font-size: 11px; font-family: inherit;
}
.mini:hover { background: var(--btn-hover); }
/* Ползунок затенения рисунка: три деления (выключено — авто — включено), активное подписано акцентом.
   Подпись «Затенение / рисунка» стоит слева в две строки, ползунок с делениями — справа.
   line-height: 16px подобран по замеру: строка 1 совпадает с ползунком, строка 2 — с подписями делений. */
/* Колонки растянуты по высоте (align-items: stretch), а две строки подписи разведены
   по её краям (justify-content: space-between) — тогда строка «Затенение» встаёт ровно
   напротив ползунка, а «рисунка» — напротив подписей делений (замер: дельты 1.0 и 0.0 px). */
.dim-row { display: flex; align-items: stretch; gap: 10px; }
.dim-row .dim-lbl { flex: 0 0 auto; width: auto; white-space: nowrap; margin: 0; line-height: 12.5px; padding-top: 1px;
  display: flex; flex-direction: column; justify-content: space-between; }
.dim-wrap { flex: 1 1 auto; min-width: 0; }
.dim-range { display: block; width: 100%; height: 16px; margin: 0; accent-color: var(--accent); cursor: pointer; }
/* Подписи делений подняты к ползунку на полкорпуса (просьба Ярослава 01.10.26: «поднимите
   подписи выше на полкорпуса»): отступ стал отрицательным, поэтому строки делений идут
   вплотную к ползунку, а вторая строка подписи «рисунка» (она прижата к низу колонки)
   поднимается вместе с ними. Чернила текста и ползунка не пересекаются. */
.dim-scale { display: flex; justify-content: space-between; margin-top: 0; line-height: 12px; font-size: 10px; color: var(--muted); }
.dim-scale .on { color: var(--accent); font-weight: 600; }
.mini.danger { background: var(--danger-bg); color: var(--danger-text); border-color: var(--danger-border); }
.hidden-file { display: none; }
</style>
