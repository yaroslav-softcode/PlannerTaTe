<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import QRCode from 'qrcode'
import { L18N } from '../i18n.js'

// Панель «Установка на телефон» (03.10.26, просьба Ярослава).
// Показывает СВОЙ адрес компьютера в сети (у каждого пользователя он свой), ссылку на приложение,
// QR-код для камеры телефона и ключ доступа. Открывается из боковой панели и сама при первом запуске.
//
// 04.10.26 (просьба Ярослава): сверху добавлен выбор «По сети (Wi-Fi) / Нет Wi-Fi». Во втором
// режиме — инструкция установки ПО КАБЕЛЮ через «USB-модем»: у пользователя может не быть Wi-Fi,
// и тогда телефон подключается шнуром, а у компьютера появляется отдельный кабельный адрес
// (его отдаёт сервер: state.cableLink / installPhoneCable / installTabletCable).
const props = defineProps({ lang: String, device: String, state: Object, x: Number, y: Number })
const emit = defineEmits(['close', 'refresh'])

const lang = computed(() => (props.lang === 'en' ? 'en' : 'ru'))
const t = (k) => (L18N[lang.value] || L18N.ru)[k]

const qr = ref('')
const copied = ref('')
const mode = ref('wifi')                       // 'wifi' | 'cable'
const dev = computed(() => (props.device === 'tablet' ? 'tablet' : 'phone'))
const title = computed(() => t(dev.value === 'tablet' ? 'phoneTitleTab' : 'phoneTitle'))
// Что показываем и копируем текстом — простой адрес загрузки (без ключа), как и раньше.
const link = computed(() => (props.state && props.state.link) || '')
// Кабельный адрес (адаптер USB-модема). Пусто — значит кабель не поднят.
const cableLink = computed(() => (props.state && props.state.cableLink) || '')
// Что кладём в QR: страница установки со ключом и типом устройства — для сети или для кабеля.
const qrContent = computed(() => {
  const st = props.state || {}
  const wifi = (dev.value === 'tablet' ? st.installTablet : st.installPhone) || st.link || ''
  const cable = (dev.value === 'tablet' ? st.installTabletCable : st.installPhoneCable) || st.cableLink || ''
  return mode.value === 'cable' ? cable : wifi
})
const key = computed(() => (props.state && props.state.key) || '')

// QR рисуется прямо в браузере: компьютер нового пользователя может быть вообще без интернета,
// поэтому никаких внешних сервисов — только ссылка, которую и так видно текстом.
async function makeQr() {
  if (!qrContent.value) { qr.value = ''; return }
  try {
    qr.value = await QRCode.toDataURL(qrContent.value, { width: 280, margin: 1 })
  } catch (e) {
    qr.value = ''
  }
}
onMounted(makeQr)
watch(qrContent, makeQr)

async function copy(text, what) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = what
    setTimeout(() => { if (copied.value === what) copied.value = '' }, 1500)
  } catch (e) { /* буфер обмена недоступен — не беда, текст видно на экране */ }
}
</script>

<template>
  <!-- Базовый вид тот же, что у панели лицензии (.inspector), своё — префиксом .ph-. -->
  <div class="inspector ph" :style="{ left: (x || 0) + 'px', top: (y || 0) + 'px' }">
    <div class="ph-head">
      <span class="ph-title">{{ title }}</span>
      <button class="ph-x" :title="t('close')" @click="emit('close')">×</button>
    </div>

    <!-- Вверху — выбор способа подключения: по сети или по кабелю (когда Wi-Fi нет) -->
    <div class="ph-tabs">
      <button class="ph-tab" :class="{ on: mode === 'wifi' }" @click="mode = 'wifi'">{{ t('wifiTab') }}</button>
      <button class="ph-tab" :class="{ on: mode === 'cable' }" @click="mode = 'cable'">{{ t('noWifiTab') }}</button>
    </div>

    <div class="ph-body">
      <div v-if="state && !state.apkReady" class="ph-warn">{{ t('phoneNoApk') }}</div>

      <!-- ===== Обычный путь: по Wi-Fi/сети ===== -->
      <template v-if="mode === 'wifi'">
        <div class="ph-step">{{ t('phoneStep1') }}</div>
        <div class="ph-qr-wrap">
          <img v-if="qr" class="ph-qr" :src="qr" :alt="link" />
          <div v-else class="ph-qr-empty">QR…</div>
        </div>

        <div class="ph-step">{{ t('phoneManual') }}</div>
        <div class="ph-row">
          <span class="ph-link">{{ link }}</span>
          <button class="ph-copy" @click="copy(link, 'link')">{{ copied === 'link' ? t('phoneCopied') : t('phoneCopy') }}</button>
        </div>

        <div class="ph-step">{{ t('phoneStep2') }}</div>

        <div class="ph-step">{{ t('phoneStep3') }}</div>
        <div class="ph-row">
          <span class="ph-key-label">{{ t('phoneKeyLabel') }}</span>
          <span class="ph-key">{{ key }}</span>
          <button class="ph-copy" @click="copy(key, 'key')">{{ copied === 'key' ? t('phoneCopied') : t('phoneCopy') }}</button>
        </div>

        <div class="ph-hint">{{ t('phoneSameNet') }}</div>
      </template>

      <!-- ===== Кабельный путь (Wi-Fi нет, только шнур) ===== -->
      <template v-else>
        <div class="ph-step">{{ t('cableStep1') }}</div>
        <div class="ph-step">{{ t('cableStep2') }}</div>

        <template v-if="cableLink">
          <div class="ph-step">{{ t('cableStep3') }}</div>
          <div class="ph-qr-wrap">
            <img v-if="qr" class="ph-qr" :src="qr" :alt="cableLink" />
            <div v-else class="ph-qr-empty">QR…</div>
          </div>
          <div class="ph-row">
            <span class="ph-link">{{ cableLink }}</span>
            <button class="ph-copy" @click="copy(cableLink, 'cable')">{{ copied === 'cable' ? t('phoneCopied') : t('phoneCopy') }}</button>
          </div>
          <div class="ph-step">{{ t('cableStep4') }}</div>
          <div class="ph-row">
            <span class="ph-key-label">{{ t('phoneKeyLabel') }}</span>
            <span class="ph-key">{{ key }}</span>
            <button class="ph-copy" @click="copy(key, 'key')">{{ copied === 'key' ? t('phoneCopied') : t('phoneCopy') }}</button>
          </div>
          <div class="ph-hint">{{ t('cableHint') }}</div>
        </template>

        <template v-else>
          <div class="ph-warn">{{ t('cableWaiting') }}</div>
          <button class="btn center" @click="emit('refresh')">{{ t('cableRefresh') }}</button>
        </template>
      </template>

      <!-- Пояснение (03.10.26, текст Ярослава): что стоит на компьютере, что делает синхронизация,
           что можно делать на телефоне, а что нельзя. Строки — списком в i18n (phoneAbout). -->
      <div class="ph-about">
        <div v-for="(line, i) in t('phoneAbout')" :key="i" class="ph-about-line">{{ line }}</div>
      </div>
    </div>
  </div>
</template>

<style>
/* Панель установки на телефон. Цвета — из темы приложения, ничего не переопределяем. */
.ph {
  width: 340px;
  max-height: calc(100vh - 120px);
  overflow: auto;
  z-index: 40;
}
.ph-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.ph-title { font-weight: 600; }
.ph-x {
  border: none;
  background: transparent;
  color: var(--muted-foreground, #888);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
/* Выбор способа подключения: «По сети (Wi-Fi)» / «Нет Wi-Fi» (04.10.26). */
.ph-tabs { display: flex; gap: 6px; margin-top: 10px; }
.ph-tab {
  flex: 1 1 0; padding: 6px 8px; border-radius: 9px; cursor: pointer; font-family: inherit;
  font-size: 11.5px; line-height: 1.25; background: var(--btn-bg, rgba(127, 127, 127, .12));
  color: var(--text); border: 1px solid var(--btn-border, rgba(127, 127, 127, .3));
}
.ph-tab:hover { background: var(--btn-hover, rgba(127, 127, 127, .2)); }
.ph-tab.on {
  background: linear-gradient(180deg, #ffa53c, #f08019); color: #1c1c1c; font-weight: 700;
  border-color: transparent;
}
.ph-body { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
.ph-step { font-size: 13px; opacity: 0.85; line-height: 1.35; }
.ph-qr-wrap { display: flex; justify-content: center; }
.ph-qr { width: 240px; height: 240px; background: #fff; padding: 6px; border-radius: 10px; }
.ph-qr-empty { width: 240px; height: 240px; display: flex; align-items: center; justify-content: center; opacity: 0.5; }
.ph-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  background: var(--card, rgba(127, 127, 127, 0.10));
  border: 1px solid var(--border, rgba(127, 127, 127, 0.25));
  border-radius: 10px;
  padding: 8px 10px;
}
.ph-link { font-size: 13px; word-break: break-all; }
.ph-key-label { font-size: 12px; opacity: 0.7; }
.ph-key {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.12em;
}
.ph-copy {
  margin-left: auto;
  border: 1px solid var(--border, rgba(127, 127, 127, 0.35));
  background: transparent;
  color: var(--foreground, #ddd);
  border-radius: 8px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}
.ph-hint { font-size: 12px; opacity: 0.65; }
.ph-warn { font-size: 13px; color: #d9822b; line-height: 1.35; }

/* Пояснение под шагами: отделено чертой. Переменные только те, что объявлены в styles.css
   (--divider, --muted) — у незнакомых имён браузер молча берёт запасной цвет. */
.ph-about {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 2px;
  padding-top: 10px;
  border-top: 1px solid var(--divider);
}
.ph-about-line { font-size: 12px; line-height: 1.35; color: var(--muted); }
</style>
