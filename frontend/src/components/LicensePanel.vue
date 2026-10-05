<script setup>
import { computed, ref } from 'vue'
import { L18N } from '../i18n.js'

const props = defineProps({ lang: String, x: Number, y: Number })
const emit = defineEmits(['close', 'pay'])

// Суммы жёстко связаны со строками licRows в i18n.js — порядок один и тот же, менять только вместе.
// rub — цена для русского интерфейса, usd — для английского (показывается одна, по языку).
// Платёж на DonationAlerts идёт в рублях; долларовая цена — пересчёт по курсу 100 ₽ = $1.
const ROWS = [
  { rub: 10, usd: '0.10' },
  { rub: 100, usd: '1' },
  { rub: 500, usd: '5' },
  { rub: 1000, usd: '10' },
]
const pick = ref(1)                 // «Нормально, задачу закрывает» — средний вариант по умолчанию
const lang = computed(() => (props.lang === 'en' ? 'en' : 'ru'))
const t = (k) => (L18N[lang.value] || L18N.ru)[k]
const texts = computed(() => t('licRows') || [])
// Валюта ровно одна — по языку интерфейса (просьба Ярослава 03.10.26): русский → рубли,
// английский → доллары. Обе сразу не показываем никогда.
const money = (r) => (lang.value === 'en' ? `$${r.usd}` : `${r.rub} ₽`)
const chosen = computed(() => ROWS[pick.value])

function pay() {
  emit('pay', {
    index: pick.value,
    rub: chosen.value.rub,
    usd: chosen.value.usd,
    text: texts.value[pick.value] || '',
  })
}
</script>

<template>
  <!-- Панель поддержки. Базовый вид берём у .inspector (те же переменные темы, что у панели
       задачи), своё — только префиксом .lic-. -->
  <div class="inspector lic" :style="{ left: (x || 0) + 'px', top: (y || 0) + 'px' }">
    <div class="lic-head">
      <span class="lic-title">{{ t('licTitle') }}</span>
      <button class="lic-x" :title="t('close')" @click="emit('close')">×</button>
    </div>

    <button v-for="(row, i) in texts" :key="i" class="lic-row" :class="{ on: pick === i }" @click="pick = i">
      <span class="lic-check">{{ pick === i ? '✓' : '' }}</span>
      <span class="lic-text">{{ row }}</span>
      <span class="lic-money">{{ money(ROWS[i]) }}</span>
    </button>

    <div class="lic-foot">
      <span class="lic-sum">{{ money(chosen) }}</span>
      <button class="lic-pay" @click="pay">{{ t('licPay') }}</button>
    </div>
  </div>
</template>

<style>
/* 03.10.26, просьба Ярослава: панель с вопросом «Оцените приложение», четыре строки с выбором,
   внизу выбранная сумма и оранжевая кнопка «Оплатить». */
.inspector.lic { width: 296px; padding: 12px; }
.lic-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.lic-title { font-size: 13px; font-weight: 700; color: var(--text); }
.lic-x { background: transparent; border: 0; color: var(--muted); font-size: 18px; line-height: 1; cursor: pointer; padding: 0 2px; }
.lic-x:hover { color: var(--text); }
.lic-row { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left; cursor: pointer;
  padding: 7px 8px; margin-bottom: 4px; border-radius: 8px; font-family: inherit; font-size: 12px;
  background: var(--btn-bg); color: var(--btn-text); border: 1px solid var(--btn-border); }
.lic-row:hover { border-color: #e08a3c; }
.lic-row.on { border-color: #e08a3c; box-shadow: 0 0 0 1px #e08a3c inset; }
.lic-check { flex: 0 0 14px; width: 14px; height: 14px; border-radius: 50%; font-size: 10px; color: #fff;
  display: flex; align-items: center; justify-content: center; border: 1px solid var(--btn-border); }
.lic-row.on .lic-check { background: #e08a3c; border-color: #e08a3c; }
.lic-text { flex: 1 1 auto; min-width: 0; }
.lic-money { flex: 0 0 auto; color: var(--muted); font-size: 11px; white-space: nowrap; }
.lic-foot { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 10px; }
.lic-sum { font-size: 13px; font-weight: 700; color: var(--text); white-space: nowrap; }
.lic-pay { padding: 9px 18px; border: 0; border-radius: 10px; cursor: pointer; font-family: inherit;
  font-size: 13px; font-weight: 700; color: #fff;
  background: linear-gradient(180deg, #ffa53c, #f08019); box-shadow: 0 3px 10px rgba(240, 128, 25, .35); }
.lic-pay:hover { background: linear-gradient(180deg, #ffb455, #f58a24); }
.lic-pay:active { transform: translateY(1px); }
</style>
