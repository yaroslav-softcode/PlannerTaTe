<script setup>
import { ref, computed } from 'vue'
import { L18N } from '../i18n.js'

/* Читалка описания карточки — открывается кнопкой-лупой на карточке (телефон, ближний план).
   Просьба Ярослава 05.10.26: полноэкранное окно «как в Telegram» — вверху название карточки и
   кнопка «назад» (видна всегда, даже при прокрутке), текст описания скроллится пальцем.
   Компонент ТОЛЬКО читает: описание не правится (правка — в панели карточки по ПКМ).
   Цвета — только переменные активной темы (см. styles.css), как у остальных панелей проекта. */
const props = defineProps({
  title: { type: String, default: '' },
  text: { type: String, default: '' },
  lang: { type: String, default: 'ru' },
})
const emit = defineEmits(['close', 'openlink'])

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
</script>

<template>
  <div class="reader">
    <div class="rd-head" :class="{ sep: scrolled }">
      <button class="rd-back" @click="emit('close')">
        <span class="arrow">‹</span>{{ t('readerBack') }}
      </button>
      <div class="rd-title">{{ title || t('label') }}<span class="rd-esc">{{ t('readerEsc') }}</span></div>
    </div>
    <div class="rd-body" @scroll="onScroll">
      <div class="rd-text"><template v-for="(p, i) in parts" :key="i"><a v-if="p.a" :href="p.href" @click="onLink(p.href, $event)">{{ p.a }}</a><template v-else>{{ p.t }}</template></template></div>
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
.rd-back {
  align-self: flex-end; display: inline-flex; align-items: center; gap: 7px;
  min-height: 36px; padding: 4px 13px 4px 9px; cursor: pointer;
  font-family: inherit; font-size: 14px; font-weight: 600;
  background: var(--input-bg); color: var(--text);
  border: 1px solid var(--input-border); border-radius: var(--radius-sm);
}
.rd-back:active { border-color: var(--accent); }
/* Кнопка «назад» справа (просьба Ярослава 05.10.26): стрелка и подпись в одном порядке,
   меняется только сторона — заголовок карточки остаётся слева во всю ширину. */
.rd-back .arrow { font-size: 19px; line-height: 1; margin-top: -2px; }
.rd-title { font-size: 15px; font-weight: 700; line-height: 1.3; overflow-wrap: anywhere; }
.rd-body { flex: 1 1 auto; overflow-y: auto; -webkit-overflow-scrolling: touch; overscroll-behavior: contain; }
.rd-text {
  padding: 12px 16px 32px; font-size: 15px; line-height: 1.55;
  white-space: pre-wrap; overflow-wrap: anywhere;   /* переносы строк автора описания сохраняем */
}
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
}
</style>
