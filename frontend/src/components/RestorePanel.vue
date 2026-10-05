<script setup>
import { computed, onMounted, ref } from 'vue'
import { L18N } from '../i18n.js'

/* Панель «Восстановить из резервной копии» (04.10.26, просьба Ярослава: кнопка-значок рядом с
   «создать резервную копию»). Список копий берём у сервера (/api/backups), а само восстановление
   делает App.vue (/api/restore) — панель только показывает список и подтверждает выбор.
   Подтверждение двойное: первое нажатие «Восстановить» превращается в «Точно?». */
const props = defineProps({ lang: String, x: Number, y: Number })
const emit = defineEmits(['close', 'restore'])

const lang = computed(() => (props.lang === 'en' ? 'en' : 'ru'))
const t = (k) => (L18N[lang.value] || L18N.ru)[k]

const items = ref([])
const loading = ref(true)
const confirmFile = ref('')

function humanSize(n) {
  if (n === undefined || n === null) return ''
  if (n < 1024) return n + ' Б'
  if (n < 1048576) return (n / 1024).toFixed(1) + ' КБ'
  return (n / 1048576).toFixed(1) + ' МБ'
}
// graph.json.bak_2026-10-04_171500_manual -> «04.10.26 17:15:00 · manual»
function shortName(f) {
  const m = /^graph\.json\.bak_(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})(?:_(.+))?$/.exec(String(f || ''))
  if (!m) return f
  const [, y, mo, d, hh, mm, ss, tag] = m
  const base = `${d}.${mo}.${y.slice(2)} ${hh}:${mm}:${ss}`
  return tag ? base + ' · ' + tag : base
}
async function load() {
  loading.value = true
  try {
    const r = await fetch('/api/backups', { headers: { 'X-Plannertate-Client': '1' } })
    const j = await r.json()
    items.value = (j && Array.isArray(j.items)) ? j.items : []
  } catch (e) {
    items.value = []
  } finally {
    loading.value = false
  }
}
onMounted(load)

function click(file) {
  if (confirmFile.value === file) { emit('restore', file); return }
  confirmFile.value = file
  setTimeout(() => { if (confirmFile.value === file) confirmFile.value = '' }, 3000)
}
</script>

<template>
  <!-- Базовый вид — как у остальных панелей (.inspector), своё — префиксом .rst-. -->
  <div class="inspector rst" :style="{ left: (x || 0) + 'px', top: (y || 0) + 'px' }">
    <div class="rst-head">
      <span class="rst-title">{{ t('restoreTitle') }}</span>
      <button class="rst-x" :title="t('close')" @click="emit('close')">×</button>
    </div>

    <div class="rst-note">{{ t('restoreNote') }}</div>

    <div v-if="loading" class="rst-empty">…</div>
    <div v-else-if="!items.length" class="rst-empty">{{ t('restoreEmpty') }}</div>
    <div v-else class="rst-list">
      <div v-for="it in items" :key="it.file" class="rst-row" :title="it.file">
        <span class="rst-name">{{ shortName(it.file) }}<span class="rst-size">{{ humanSize(it.size) }}</span></span>
        <button class="rst-btn" :class="{ on: confirmFile === it.file }" @click="click(it.file)">
          {{ confirmFile === it.file ? t('restoreReally') : t('restoreDo') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style>
/* Панель восстановления. Цвета — из темы приложения, ничего своего. */
.inspector.rst { width: 340px; max-height: calc(100vh - 120px); overflow: auto; z-index: 40; }
.rst-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rst-title { font-weight: 600; }
.rst-x {
  border: none; background: transparent; color: var(--muted); font-size: 18px; line-height: 1; cursor: pointer;
}
.rst-x:hover { color: var(--text); }
.rst-note { font-size: 12px; color: var(--muted); margin: 8px 0; line-height: 1.35; }
.rst-empty { font-size: 12px; opacity: .7; padding: 6px 0; }
.rst-list { display: flex; flex-direction: column; gap: 5px; }
.rst-row {
  display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 8px;
  background: var(--btn-bg); border: 1px solid var(--btn-border);
}
.rst-name {
  flex: 1 1 auto; min-width: 0; font-size: 12px; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rst-size { color: var(--muted); font-size: 11px; margin-left: 6px; }
.rst-btn {
  flex: 0 0 auto; padding: 4px 10px; border-radius: 8px; cursor: pointer; font-family: inherit;
  font-size: 11px; background: transparent; color: var(--text); border: 1px solid var(--btn-border);
}
.rst-btn:hover { background: var(--btn-hover); }
.rst-btn.on {
  background: var(--danger-bg); color: var(--danger-text); border-color: var(--danger-border); font-weight: 600;
}
</style>
