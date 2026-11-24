<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({ lang: String, prepareUpdate: Function })
const emit = defineEmits(['close', 'openlink'])
const TEXT = {
  ru: {
    title: 'О приложении', close: 'Закрыть', version: 'Версия',
    description: 'Задачи, связи и напоминания на одном холсте.',
    updates: 'Обновления', check: 'Проверить обновления', checking: 'Проверяем GitHub…', update: 'Обновить',
    install: 'Установить и перезапустить', idle: 'Проверьте, есть ли новая версия на GitHub.',
    current: 'Установлена актуальная версия.', available: 'Доступна версия {v}.',
    downloading: 'Скачиваем обновление…', ready: 'Обновление скачано и проверено.',
    installing: 'Установка обновления и перезапуск…',
    error: 'Не удалось связаться с GitHub. Проверьте подключение и попробуйте ещё раз.',
    verifyError: 'Файл обновления не прошёл проверку. Повторите загрузку.',
    installError: 'Не удалось начать установку. Повторите попытку.',
    saveError: 'Не удалось сохранить задачи. Обновление не запущено — попробуйте ещё раз.',
    unsupported: 'Автообновление доступно в установленном приложении для Windows.',
    restartNote: 'При обновлении приложение перезапустится. Задачи и настройки сохранятся.',
    author: 'Автор приложения', authorName: 'Ярослав Хмелев',
    authorInfo: 'Независимый разработчик PlannerTaTe, FAIR и Paste Pen.', thanks: 'Благодарить',
    otherApps: 'Другие приложения автора', download: 'Скачать последнюю версию', github: 'GitHub',
    fair: 'Free AI Reader — сокращает статьи, документы и тексты с помощью ИИ и читает их вслух. Поддерживает озвучку своим голосом, озвучку аудиокниг по голосам и сохранение аудио.',
    pastepen: 'Рисование поверх любых окон: заметки от руки, фигуры, текст и изображения. Удобно для объяснений, презентаций и работы со скриншотами.',
    screenshot: 'Скриншот приложения',
  },
  en: {
    title: 'About', close: 'Close', version: 'Version',
    description: 'Tasks, connections and reminders on one canvas.',
    updates: 'Updates', check: 'Check for updates', checking: 'Checking GitHub…', update: 'Update',
    install: 'Install and restart', idle: 'Check GitHub for a new version.',
    current: 'Your version is up to date.', available: 'Version {v} is available.',
    downloading: 'Downloading update…', ready: 'Update downloaded and verified.',
    installing: 'Installing update and restarting…',
    error: 'Could not connect to GitHub. Check your connection and try again.',
    verifyError: 'The update file failed verification. Please download it again.',
    installError: 'Could not start installation. Please try again.',
    saveError: 'Could not save your tasks. The update was not started. Please try again.',
    unsupported: 'Automatic updates are available in the installed Windows app.',
    restartNote: 'The app will restart during the update. Your tasks and settings will be kept.',
    author: 'App author', authorName: 'Yaroslav Khmelev',
    authorInfo: 'Independent developer of PlannerTaTe, FAIR and Paste Pen.', thanks: 'Donate',
    otherApps: 'More apps by the author', download: 'Download latest version', github: 'GitHub',
    fair: 'Free AI Reader uses AI to condense articles, documents and text, then reads them aloud. Supports custom voices, audiobook narration with per-character voices, and saving audio.',
    pastepen: 'Draw over any window: freehand notes, shapes, text and images. Useful for explanations, presentations and annotating screenshots.',
    screenshot: 'App screenshot',
  },
}
const lang = computed(() => props.lang === 'en' ? 'en' : 'ru')
const t = k => TEXT[lang.value][k]
const APPS = [
  { id: 'fair', name: 'FAIR', subtitle: 'Free AI Reader', repo: 'https://github.com/yaroslav-softcode/FAIR' },
  { id: 'pastepen', name: 'Paste Pen', subtitle: '', repo: 'https://github.com/yaroslav-softcode/paste-pen' },
]
const panel = ref(null)
const info = ref(null)
const update = ref({ state: 'idle', available: false, downloaded: 0, download_size: 0 })
const busy = ref(false)
const loading = ref(true)
const imageStamp = ref(0)
const fallback = ref({})
let live = true
let autoInstall = false
let operationGeneration = 0
let pollTimer = null
let previousFocus = null
const requests = new Set()
const version = computed(() => info.value?.current_version || update.value.current_version || '—')
const canInstall = computed(() => !!(info.value?.can_install ?? update.value.can_install))
const active = computed(() => ['checking', 'downloading', 'installing'].includes(update.value.state))
const updateAllowed = computed(() => canInstall.value && update.value.available && !active.value && !busy.value)
const progress = computed(() => {
  const total = Number(update.value.download_size) || 0
  return total > 0 ? Math.min(100, Math.round((Number(update.value.downloaded) || 0) * 100 / total)) : null
})
const statusText = computed(() => {
  const s = update.value
  if (s.state === 'error') {
    if (s.error === 'save_failed') return t('saveError')
    if (/digest|checksum|hash|size|invalid_asset|invalid_binary|verification|download_invalid/.test(s.error || '')) return t('verifyError')
    if (/install|helper|launch/.test(s.error || '')) return t('installError')
    return t('error')
  }
  if (s.state === 'available') return t('available').replace('{v}', s.latest_version || '')
  return t(s.state) || t('idle')
})
function imageUrl(app) {
  if (fallback.value[app.id]) return `/author-apps/${app.id}-${lang.value}.webp`
  return `/api/apps/${app.id}/screenshot?lang=${lang.value}&v=${imageStamp.value}`
}
async function api(path, post = false) {
  const controller = new AbortController()
  requests.add(controller)
  const timer = setTimeout(() => controller.abort(), 30000)
  try {
    const r = await fetch(path, { method: post ? 'POST' : 'GET', cache: 'no-store', signal: controller.signal,
      ...(post ? { headers: { 'X-Plannertate-Client': '1' } } : {}) })
    const data = await r.json()
    if (!r.ok) throw Object.assign(new Error(data.error || 'network_error'), { code: data.error })
    return data
  } finally { clearTimeout(timer); requests.delete(controller) }
}
function setError(e) {
  if (live) update.value = { ...update.value, state: 'error', error: e?.code || e?.message || 'network_error' }
}
function close() { emit('close') }
function keydown(e) {
  e.stopPropagation() // The graph must not receive Delete/Undo while About has focus.
  if (e.key === 'Escape') { e.preventDefault(); close(); return }
  if (e.key !== 'Tab') return
  const controls = [...panel.value.querySelectorAll('button:not([disabled]),a[href]')].filter(el => el.getClientRects().length)
  const first = controls[0], last = controls.at(-1)
  if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.value)) {
    e.preventDefault(); last?.focus()
  } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
}
async function checkUpdates() {
  if (!live || busy.value || active.value) return
  const generation = ++operationGeneration
  autoInstall = false
  busy.value = true
  update.value = { ...update.value, state: 'checking', error: '' }
  try {
    const data = await api('/api/updates/check', true)
    if (live && generation === operationGeneration) {
      update.value = data
      imageStamp.value = Date.now()
      fallback.value = {}
      if (['checking', 'downloading'].includes(data.state)) schedulePoll(generation)
    }
  } catch (e) { if (generation === operationGeneration) setError(e) }
  finally { if (live && generation === operationGeneration) busy.value = false }
}
async function installReady(generation = operationGeneration) {
  if (!live || !autoInstall || generation !== operationGeneration) return
  busy.value = true // polling enters here without startUpdate's busy lock
  autoInstall = false // exactly one installation request per explicit click
  try {
    const saved = props.prepareUpdate ? await props.prepareUpdate() : true
    if (!live || generation !== operationGeneration) return
    if (!saved) { setError({ code: 'save_failed' }); return }
    const data = await api('/api/updates/install', true)
    if (live && generation === operationGeneration) update.value = data
  } catch (e) { if (generation === operationGeneration) setError(e) }
  finally { if (live && generation === operationGeneration) busy.value = false }
}
function schedulePoll(generation = operationGeneration) {
  clearTimeout(pollTimer)
  pollTimer = setTimeout(async () => {
    if (!live || generation !== operationGeneration) return
    try {
      const data = await api('/api/updates/status')
      if (!live || generation !== operationGeneration) return
      update.value = data
      if (data.state === 'ready' && autoInstall) await installReady(generation)
      else if (['downloading', 'checking'].includes(data.state)) schedulePoll(generation)
    } catch (e) { if (generation === operationGeneration) setError(e) }
  }, 700)
}
async function startUpdate() {
  if (!live || !updateAllowed.value) return
  const generation = ++operationGeneration
  busy.value = true
  autoInstall = true
  try {
    if (update.value.state === 'ready') await installReady(generation)
    else {
      const data = await api('/api/updates/download', true)
      if (!live || generation !== operationGeneration) return
      update.value = data
      if (data.state === 'ready') await installReady(generation)
      else if (['downloading', 'checking'].includes(data.state)) schedulePoll(generation)
    }
  } catch (e) { if (generation === operationGeneration) { autoInstall = false; setError(e) } }
  finally { if (live && generation === operationGeneration) busy.value = false }
}
onMounted(async () => {
  previousFocus = document.activeElement
  await nextTick()
  panel.value?.querySelector('button')?.focus()
  try {
    const [about, state] = await Promise.all([api('/api/about'), api('/api/updates/status')])
    if (!live) return
    info.value = about; update.value = state
    if (['checking', 'downloading'].includes(state.state)) schedulePoll()
  } catch (e) { setError(e) }
  finally { if (live) loading.value = false }
})
onBeforeUnmount(() => {
  live = false; autoInstall = false
  operationGeneration++
  clearTimeout(pollTimer)
  for (const controller of requests) controller.abort()
  previousFocus?.focus?.()
})
</script>

<template>
  <Teleport to="body">
    <div class="about-overlay" @click.self="close" @keydown="keydown">
      <section ref="panel" class="about-panel" role="dialog" aria-modal="true" aria-labelledby="about-title"
               tabindex="-1" data-testid="about-panel">
        <header class="about-header">
          <h1 id="about-title">{{ t('title') }}</h1>
          <button class="about-close" :title="t('close')" :aria-label="t('close')" @click="close">×</button>
        </header>
        <div class="about-scroll">
          <div class="about-brand"><span>Planner</span><span class="about-ta">Ta</span><span class="about-te">Te</span></div>
          <div class="about-version">{{ t('version') }} <strong>{{ version }}</strong><span>Windows</span></div>
          <p class="about-description">{{ t('description') }}</p>
          <section class="about-updates" :aria-label="t('updates')">
            <h2>{{ t('updates') }}</h2>
            <p class="about-update-status" :class="{ 'about-error': update.state === 'error' }" role="status" aria-live="polite"
               data-testid="update-status">{{ statusText }}</p>
            <div v-if="update.state === 'downloading'" class="about-progress">
              <progress :value="progress ?? undefined" max="100" :aria-label="t('downloading')"></progress>
              <span v-if="progress != null">{{ progress }}%</span>
            </div>
            <div class="about-actions">
              <button class="about-btn" :disabled="loading || busy || active" data-testid="check-updates" @click="checkUpdates">
                {{ update.state === 'checking' ? t('checking') : t('check') }}
              </button>
              <button class="about-btn about-primary" :disabled="!updateAllowed" data-testid="install-update" @click="startUpdate">
                {{ update.state === 'ready' ? t('install') : t('update') }}
              </button>
            </div>
            <p class="about-note">{{ canInstall ? t('restartNote') : t('unsupported') }}</p>
          </section>
          <section class="about-author">
            <div>
              <h2>{{ t('author') }}</h2>
              <strong class="about-author-name">{{ t('authorName') }}</strong>
              <p>{{ t('authorInfo') }}</p>
            </div>
            <button class="about-btn about-donate" data-testid="about-donate"
                    @click="emit('openlink', 'https://www.donationalerts.com/r/yaroslav_khmelev')">{{ t('thanks') }}</button>
          </section>
          <section class="about-other">
            <h2>{{ t('otherApps') }}</h2>
            <article v-for="app in APPS" :key="app.id" class="about-app">
              <a class="about-image-link" :href="app.repo" target="_blank" rel="noopener noreferrer" :aria-label="app.name + ' — GitHub'">
                <img :src="imageUrl(app)" :alt="app.name + ' — ' + t('screenshot')" width="1200" height="750"
                     @error="fallback[app.id] = true" />
              </a>
              <div class="about-app-text">
                <h3>{{ app.name }}</h3>
                <p>{{ t(app.id) }}</p>
                <a class="about-btn about-app-download" :href="`/api/apps/${app.id}/download`" target="_blank" rel="noopener noreferrer">{{ t('download') }} ↗</a>
              </div>
            </article>
          </section>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.about-overlay { position: fixed; inset: 0; z-index: 120; display: flex; align-items: center; justify-content: center;
  padding: 18px; box-sizing: border-box; background: rgba(0,0,0,.5); }
.about-panel { width: min(840px, 100%); max-height: calc(100dvh - 36px); display: flex; flex-direction: column;
  box-sizing: border-box; background: var(--popup-bg, #1b2036); color: var(--text); border: 1px solid var(--panel-border, var(--btn-border));
  border-radius: 16px; box-shadow: var(--panel-shadow); font-family: var(--ui-font, inherit); overflow: hidden; outline: none; }
.about-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 24px;
  border-bottom: 1px solid var(--btn-border); flex-shrink: 0; }
.about-header h1 { margin: 0; font-size: 16px; font-weight: 700; }
.about-close { border: 0; background: transparent; color: var(--muted); font: inherit; font-size: 26px; cursor: pointer;
  line-height: 1; width: 32px; height: 32px; border-radius: 7px; }
.about-close:hover { background: var(--btn-bg); color: var(--text); }
.about-scroll { padding: 22px 24px 20px; overflow-y: auto; overscroll-behavior: contain; }
.about-brand { display: flex; font-size: 30px; font-weight: 800; line-height: 1.2; letter-spacing: -.9px; }
.about-ta { color: #8168ff; }
.about-te { background: linear-gradient(96deg,#2aabee,#229ed9); background-clip: text; -webkit-text-fill-color: transparent; }
.about-version { display: flex; align-items: center; gap: 7px; margin-top: 9px; font-size: 13px; color: var(--muted); }
.about-version strong { font-weight: 650; color: var(--text); }
.about-version span { font-size: 11px; border: 1px solid var(--btn-border); border-radius: 5px; padding: 2px 6px; margin-left: 4px; }
.about-description { margin: 9px 0 19px; color: var(--muted); font-size: 13px; line-height: 1.5; }
h2 { font-size: 13px; font-weight: 700; margin: 0 0 8px; }
.about-updates { padding: 16px; background: var(--btn-bg); border: 1px solid var(--btn-border); border-radius: 11px; }
.about-update-status { font-size: 13px; margin: 0 0 13px; min-height: 19px; line-height: 1.5; }
.about-update-status.about-error { color: var(--danger, #dd7a6e); }
.about-actions { display: flex; gap: 9px; flex-wrap: wrap; }
.about-btn { display: inline-flex; align-items: center; justify-content: center; padding: 9px 14px; min-height: 36px; box-sizing: border-box;
  border: 1px solid var(--btn-border); border-radius: 8px; background: var(--btn-bg); color: var(--btn-text, var(--text));
  font: inherit; font-size: 12px; line-height: 1.4; text-decoration: none; cursor: pointer; transition: background .15s, border-color .15s; }
.about-btn:hover:not(:disabled) { border-color: var(--accent, #8168ff); background: var(--input-bg, var(--btn-bg)); }
.about-btn:disabled { opacity: .45; cursor: default; }
.about-btn:focus-visible, .about-close:focus-visible, .about-image-link:focus-visible { outline: 2px solid var(--accent, #8168ff); outline-offset: 3px; }
.about-primary { background: #5360d6; border-color: #5360d6; color: #fff; }
.about-primary:hover:not(:disabled) { background: #4450c2; border-color: #4450c2; }
.about-note { margin: 10px 0 0; font-size: 11px; line-height: 1.5; color: var(--muted); }
.about-progress { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; font-size: 12px; }
.about-progress progress { width: 100%; height: 7px; accent-color: #8168ff; }
.about-author { margin-top: 22px; padding-bottom: 20px; border-bottom: 1px solid var(--btn-border); display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.about-author-name { font-size: 14px; font-weight: 650; }
.about-author p { margin: 6px 0 0; font-size: 12px; color: var(--muted); line-height: 1.5; }
.about-donate { flex-shrink: 0; color: #fff; background: #a8541f; border-color: #a8541f; font-weight: 650; }
.about-donate:hover:not(:disabled) { color: #fff; background: #934716; border-color: #934716; }
.about-other { margin-top: 19px; }
.about-other > h2 { margin-bottom: 14px; }
.about-app { display: grid; grid-template-columns: minmax(0, .95fr) minmax(0, 1fr); gap: 19px; align-items: center;
  padding: 0 0 17px; margin-bottom: 17px; border-bottom: 1px solid var(--btn-border); }
.about-app:last-of-type { border-bottom: 0; margin-bottom: 0; padding-bottom: 0; }
.about-image-link { display: flex; overflow: hidden; border-radius: 8px; border: 1px solid var(--btn-border); background: var(--input-bg); }
.about-app img { display: block; width: 100%; height: auto; aspect-ratio: 16 / 10; object-fit: contain; }
.about-app h3 { font-size: 17px; line-height: 1.3; margin: 0 0 7px; }
.about-app p { font-size: 12px; line-height: 1.6; color: var(--muted); margin: 0 0 12px; }
.about-app-download { font-size: 11px; padding: 8px 11px; }
@media (max-width: 620px) {
  .about-overlay { padding: 10px; }
  .about-panel { max-height: calc(100dvh - 20px); border-radius: 12px; }
  .about-header { padding: 12px 16px; }
  .about-scroll { padding: 18px 16px; }
  .about-app { grid-template-columns: 1fr; gap: 12px; }
  .about-author { align-items: flex-start; flex-direction: column; gap: 12px; }
}
</style>
