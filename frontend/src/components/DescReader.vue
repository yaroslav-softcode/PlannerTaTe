<script setup>
import { ref } from 'vue'
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
const emit = defineEmits(['close'])

function t(k) {
  const d = L18N[props.lang === 'en' ? 'en' : 'ru']
  return d[k] || k
}

// Тень-разделитель под шапкой появляется только когда текст реально прокручен —
// иначе вверху висит лишняя полоса (шапка и так на месте).
const scrolled = ref(false)
function onScroll(e) { scrolled.value = e.target.scrollTop > 4 }
</script>

<template>
  <div class="reader">
    <div class="rd-head" :class="{ sep: scrolled }">
      <button class="rd-back" @click="emit('close')">
        <span class="arrow">‹</span>{{ t('readerBack') }}
      </button>
      <div class="rd-title">{{ title || t('label') }}</div>
    </div>
    <div class="rd-body" @scroll="onScroll">
      <div class="rd-text">{{ text }}</div>
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
</style>
