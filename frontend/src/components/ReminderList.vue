<script setup>
import { ref } from 'vue'
import { L18N } from '../i18n.js'

/* Список напоминаний — открывается кнопкой «⏰ Список напоминаний» в сайдбаре.
   Просьба Ярослава 01.10.26: таблица ВСЕХ активных напоминаний со столбцами
   «Задача | Время | Дата | Повторение | Доставка»; по строке можно нажать (показать
   карточку на холсте) и удалить ненужное напоминание.
   Данные приходят ГОТОВЫМИ строками из App.vue (buildReminderRows) — компонент только рисует,
   поэтому в нём нет ни доступа к графу, ни форматирования дат. */
const props = defineProps({
  lang: { type: String, default: 'ru' },
  rows: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'delete', 'reveal'])

function t(k) {
  const d = L18N[props.lang === 'en' ? 'en' : 'ru']
  return d[k] || k
}

// Удаление в ДВА нажатия и без окна подтверждения (правило проекта: никаких блокирующих окон):
// первое нажатие переводит кнопку в «Точно?», второе — удаляет. Нажатие на другую строку сбрасывает.
const askId = ref(null)
function onDel(id) {
  if (askId.value === id) { askId.value = null; emit('delete', id) } else askId.value = id
}
</script>

<template>
  <div class="rlist">
    <div class="rl-head">
      <div class="rl-title"><span class="emo">⏰</span> {{ t('remListTitle') }}</div>
      <div class="rl-count">{{ rows.length }}</div>
      <button class="rl-x" :title="t('close')" @click="emit('close')">✕</button>
    </div>

    <div v-if="!rows.length" class="rl-empty">{{ t('remListEmpty') }}</div>

    <div v-else class="rl-body">
      <table class="rl-table">
        <thead>
          <tr>
            <th class="c-task">{{ t('rlTask') }}</th>
            <th class="c-num">{{ t('rlTime') }}</th>
            <th class="c-num">{{ t('rlDate') }}</th>
            <th>{{ t('rlRepeat') }}</th>
            <th>{{ t('rlHow') }}</th>
            <th class="c-act"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" :title="t('rlReveal')" @click="emit('reveal', r.id)">
            <td class="c-task"><i class="dot" :style="{ background: r.color }"></i>{{ r.title || '—' }}</td>
            <td class="c-num">{{ r.time }}</td>
            <td class="c-num">{{ r.date }}</td>
            <td>{{ r.repeat }}</td>
            <td>{{ r.channels }}</td>
            <td class="c-act">
              <button class="rl-del" :class="{ ask: askId === r.id }" @click.stop="onDel(r.id)">
                {{ askId === r.id ? t('rlReally') : t('rlDelete') }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style>
/* Таблица напоминаний — цвета только из переменных темы. Позицию задаёт .rlist-wrap (styles.css). */
.rlist {
  width: 744px; max-width: calc(100vw - 40px); overflow: hidden;   /* 620 px +20 % (просьба Ярослава 01.10.26) */
  background: var(--panel-bg); color: var(--text); border: 1px solid var(--panel-border);
  border-radius: var(--radius); box-shadow: var(--panel-shadow); backdrop-filter: var(--panel-blur);
}
.rl-head { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--panel-border); }
.rl-title { font-size: 13.5px; font-weight: 700; }
.rl-count { font-size: 11px; color: var(--muted); }
.rl-x {
  margin-left: auto; width: 22px; height: 22px; cursor: pointer; font-family: inherit; font-size: 12px;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border); border-radius: 6px;
}
.rl-x:hover { border-color: var(--accent); }
.rl-empty { padding: 18px 12px; font-size: 12px; color: var(--muted); text-align: center; }
.rl-body { max-height: 58vh; overflow: auto; }
.rl-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.rl-table th, .rl-table td { padding: 6px 8px; text-align: left; white-space: nowrap; }
.rl-table th {
  position: sticky; top: 0; z-index: 1; background: var(--panel-bg); color: var(--muted);
  font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: .03em;
  border-bottom: 1px solid var(--panel-border);
}
.rl-table tbody tr { cursor: pointer; border-bottom: 1px solid var(--panel-border); }
.rl-table tbody tr:hover { background: var(--input-bg); }
.rl-table tbody tr:last-child { border-bottom: none; }
.c-task { max-width: 190px; overflow: hidden; text-overflow: ellipsis; }
.c-num { font-variant-numeric: tabular-nums; }
.c-act { width: 1%; text-align: right; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.rl-del {
  cursor: pointer; font-family: inherit; font-size: 11px; padding: 3px 8px; border-radius: 6px;
  background: var(--input-bg); color: var(--text); border: 1px solid var(--input-border);
}
.rl-del:hover { border-color: var(--accent); }
.rl-del.ask {
  background: linear-gradient(135deg, var(--accent), var(--accent2)); color: var(--primary-text);
  border-color: transparent; font-weight: 700;
}
</style>
