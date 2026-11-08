<script setup>
import { ref, computed, nextTick } from 'vue'
import { L18N } from '../i18n.js'

/* Читалка описания карточки — открывается кнопкой-лупой на карточке.
   Просьба Ярослава 05.10.26: полноэкранное окно «как в Telegram» — вверху название карточки и
   кнопка «назад» (видна всегда, даже при прокрутке), текст описания скроллится пальцем.
   08.11.26 (просьба Ярослава, ТОЛЬКО КОМПЬЮТЕР): в читалке можно поправить описание и сохранить —
   кнопка «Правка» превращает текст в поле, «Сохранить» пишет в карточку (App.vue: saveReaderDesc),
   «Отмена»/Esc возвращают чтение. На телефоне (editable=false) читалка остаётся только для чтения.
   Цвета — только переменные активной темы (см. styles.css), как у остальных панелей проекта. */
const props = defineProps({
  title: { type: String, default: '' },
  text: { type: String, default: '' },
  lang: { type: String, default: 'ru' },
  editable: { type: Boolean, default: false },   // правка — только на компьютере
})
const emit = defineEmits(['close', 'openlink', 'save'])

function t(k) {
  const d = L18N[props.lang === 'en' ? 'en' : 'ru']
  return d[k] || k
}

// Тень-разделитель под шапкой появляется только когда текст реально прокручен —
// иначе вверху висит лишняя полоса (шапка и так на месте).
const scrolled = ref(false)
function onScroll(e) { scrolled.value = e.target.scrollTop > 4 }

// Телефон определяем так же, как в App.vue (IS_PHONE): ссылка ведёт себя по-разному,
// и читалка должна понимать, где она открыта.
const IS_PHONE = (() => {
  try { return window.matchMedia('(pointer: coarse)').matches } catch (e) { return false }
})()

// Ссылки в описании — кликабельные (просьба Ярослава 06.11.26, 1.10). Текст раскладывается
// на части МАССИВОМ и рисуется через {{ }}, а не v-html: в DOM уходит обычный текст,
// разметкой становится только то, что действительно похоже на адрес.
const LINK_RE = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']{4,})/gi

function linkParts(text) {
  const src = String(text || '')
  const out = []
  let last = 0
  let m
  LINK_RE.lastIndex = 0
  while ((m = LINK_RE.exec(src))) {
    if (m.index > last) out.push({ t: src.slice(last, m.index) })
    let url = m[0]
    let tail = ''
    // «смотри https://ru.wikipedia.org/wiki/Золото.» — точка в конце предложения не часть
    // адреса: хвостовую пунктуацию снимаем и возвращаем обычным текстом.
    while (/[.,;:!?»"')\]]$/.test(url)) { tail = url.slice(-1) + tail; url = url.slice(0, -1) }
    if (url) out.push({ a: url, href: /^https?:\/\//i.test(url) ? url : 'https://' + url })
    if (tail) out.push({ t: tail })
    last = m.index + m[0].length
  }
  if (last < src.length) out.push({ t: src.slice(last) })
  return out
}
const parts = computed(() => linkParts(props.text))

// Клик по ссылке. Компьютер: открывает СЕРВЕР (POST /api/open_url) — окно приложения может
// быть без вкладок, а система вызовет браузер. Телефон: не трогаем переход — ссылкой
// распорядится приложение (PlannerActivity уводит http-адрес в браузер системы), иначе
// WebView ушёл бы с планировщика на 404 локального загрузчика.
function onLink(url, ev) {
  if (IS_PHONE) return
  ev.preventDefault()
  emit('openlink', url)
}

// --- Правка описания прямо в читалке (Ярослав 08.11.26, только ПК) ------------------------------
const editing = ref(false)
const draft = ref('')
const taEl = ref(null)
async function startEdit() {
  draft.value = String(props.text || '')
  editing.value = true
  await nextTick()
  if (taEl.value) {
    taEl.value.focus()
    try { taEl.value.setSelectionRange(draft.value.length, draft.value.length) } catch (e) {}
    fitEdit()
  }
}
function cancelEdit() { editing.value = false }
function saveEdit() { emit('save', draft.value); editing.value = false }
// Поле растёт под текст: скроллит тело читалки, а не сам textarea (одна привычная полоса).
function fitEdit() {
  const el = taEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.max(Math.round(window.innerHeight * 0.6), el.scrollHeight) + 'px'
}
// Esc в поле — отменить правку, а не закрыть читалку (событие гасим, чтобы оконный слушатель
// App.vue его не увидел). Ctrl+S — сохранить правку, как привычный жест.
function onEditKey(ev) {
  if (ev.key === 'Escape') { ev.stopPropagation(); cancelEdit(); return }
  if ((ev.ctrlKey || ev.metaKey) && (ev.key === 's' || ev.key === 'ы')) { ev.preventDefault(); ev.stopPropagation(); saveEdit() }
}
// «Назад» во время правки сначала отменяет её — защита от случайной потери текста;
// второе нажатие (или вне правки) закрывает читалку.
function onBack() {
  if (editing.value) { cancelEdit(); return }
  emit('close')
}
</script>

<template>
  <div class="reader">
    <div class="rd-head" :class="{ sep: scrolled }">
      <div class="rd-top">
        <template v-if="editable">
          <button v-if="!editing" class="rd-btn" @click="startEdit">{{ t('readerEdit') }}</button>
          <template v-else>
            <button class="rd-btn rd-save" @click="saveEdit">{{ t('readerSave') }}</button>
            <button class="rd-btn" @click="cancelEdit">{{ t('readerCancel') }}</button>
          </template>
        </template>
        <button class="rd-back" @click="onBack">
          <span class="arrow">‹</span>{{ t('readerBack') }}
        </button>
      </div>
      <div class="rd-title">{{ title || t('label') }}<span class="rd-esc">{{ t('readerEsc') }}</span></div>
    </div>
    <div class="rd-body" @scroll="onScroll">
      <textarea v-if="editing" ref="taEl" class="rd-edit" v-model="draft" @input="fitEdit" @keydown="onEditKey"></textarea>
      <div v-else class="rd-text"><template v-for="(p, i) in parts" :key="i"><a v-if="p.a" :href="p.href" @click="onLink(p.href, $event)">{{ p.a }}</a><template v-else>{{ p.t }}</template></template></div>
    </div>
  </div>
</template>

<style>
/* Полный экран; z-index выше панели карточки (.inspector = 20) и списка напоминаний (.rlist-wrap = 35). */
.reader {
  position: fixed; inset: 0; z-index: 45; display: flex; flex-direction: column;
  background: var(--panel-bg); color: var(--text); backdrop-filter: var(--panel-blur);
  font-family: var(--ui-font);
}
.rd-head {
  flex: 0 0 auto; display: flex; flex-direction: column; gap: 6px;
  padding: 10px 14px 10px; border-bottom: 1px solid transparent; transition: border-color .15s;
}
.rd-head.sep { border-bottom-color: var(--panel-border); }
/* Кнопки шапки — в один ряд справа: [Правка | Сохранить Отмена] и «Назад» (Ярослав 08.11.26). */
.rd-top { display: flex; justify-content: flex-end; gap: 8px; }
.rd-back {
  display: inline-flex; align-items: center; gap: 7px;
  min-height: 36px; padding: 4px 13px 4px 9px; cursor: pointer;
  font-family: inherit; font-size: 14px; font-weight: 600;
  background: var(--input-bg); color: var(--text);
  border: 1px solid var(--input-border); border-radius: var(--radius-sm);
}
.rd-back:active { border-color: var(--accent); }
/* Кнопки правки (только ПК): тот же вид, что у «Назад»; «Сохранить» — акцентом темы. */
.rd-btn {
  display: inline-flex; align-items: center;
  min-height: 36px; padding: 4px 13px; cursor: pointer;
  font-family: inherit; font-size: 14px; font-weight: 600;
  background: var(--input-bg); color: var(--text);
  border: 1px solid var(--input-border); border-radius: var(--radius-sm);
}
.rd-btn:active { border-color: var(--accent); }
.rd-save {
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  color: var(--primary-text); border-color: transparent;
}
/* Кнопка «назад» справа (просьба Ярослава 05.10.26): стрелка и подпись в одном порядке,
   меняется только сторона — заголовок карточки остаётся слева во всю ширину. */
.rd-back .arrow { font-size: 19px; line-height: 1; margin-top: -2px; }
.rd-title { font-size: 15px; font-weight: 700; line-height: 1.3; overflow-wrap: anywhere; }
.rd-body { flex: 1 1 auto; overflow-y: auto; -webkit-overflow-scrolling: touch; overscroll-behavior: contain; }
.rd-text {
  padding: 12px 16px 32px; font-size: 15px; line-height: 1.55;
  white-space: pre-wrap; overflow-wrap: anywhere;   /* переносы строк автора описания сохраняем */
}
/* Поле правки (08.11.26): настоящий textarea в стиле полей панели карточки (фон и рамка —
   из темы; при фокусе рамка акцентом). Высоту ведёт fitEdit по содержимому, скроллит тело
   читалки — своя полоса не дублируется. */
.rd-edit {
  display: block; width: 100%; box-sizing: border-box; min-height: 60vh;
  padding: 12px 14px 16px; font-family: inherit; font-size: 15px; line-height: 1.55;
  background: var(--input-bg); color: var(--text);
  border: 1px solid var(--input-border); border-radius: var(--radius-sm);
  outline: none; resize: none; overflow: hidden;
  white-space: pre-wrap; overflow-wrap: anywhere; caret-color: var(--accent);
}
.rd-edit:focus { border-color: var(--accent); }
/* Ссылки (1.10) — кликабельные, цветом активной темы; подчёркивание есть и без ховера,
   чтобы на телефоне было видно, что по тексту можно нажать. */
.rd-text a {
  color: var(--accent); cursor: pointer; text-decoration: underline; text-underline-offset: 2px;
}
.rd-text a:active { opacity: .65; }
/* Подсказка про Esc — только на компьютере (на телефоне и так есть кнопка «Назад»). */
.rd-esc { display: none; }
/* Компьютер: широкая читалка неудобна «во всю стену» — текст колонкой по центру и крупнее.
   На телефоне (окно уже) всё остаётся ровно как было. */
@media (min-width: 720px) {
  .rd-head { padding: 14px 18px; }
  .rd-title { font-size: 17px; }
  .rd-esc { display: inline; margin-left: 10px; font-size: 12px; font-weight: 600;
            color: var(--muted-foreground); }
  .rd-text { max-width: 780px; margin: 0 auto; font-size: 17px; line-height: 1.62; }
  .rd-edit { max-width: 780px; margin: 0 auto; font-size: 17px; line-height: 1.62; }
}
</style>
