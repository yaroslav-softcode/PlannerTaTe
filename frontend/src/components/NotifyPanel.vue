<script setup>
import { ref } from 'vue'

const props = defineProps({ lang: String })
const emit = defineEmits(['notify'])

const channel = ref('telegram')
const text = ref('')

const channels = () => props.lang === 'ru' ? ['Telegram (бот)', 'VK Max'] : ['Telegram (bot)', 'VK Max']
function send() {
  if (!text.value.trim()) return
  emit('notify', channel.value, text.value.trim())
  text.value = ''
}
</script>

<template>
  <div class="notify">
    <div class="n-title"><span class="emo">⏰</span> {{ lang === 'ru' ? 'Напоминания' : 'Reminders' }}</div>

    <label class="lbl">{{ lang === 'ru' ? 'Куда отправить' : 'Send to' }}</label>
    <select class="sel" v-model="channel">
      <option v-for="(c, i) in channels()" :key="i" value="telegram" v-if="i === 0">Telegram (бот)</option>
      <option value="vkmax" v-else>VK Max</option>
    </select>

    <label class="lbl">{{ lang === 'ru' ? 'Сообщение' : 'Message' }}</label>
    <textarea rows="3" :placeholder="lang === 'ru' ? 'Текст напоминания…' : 'Reminder text…'" :value="text" @input="text = $event.target.value" class="inp"></textarea>

    <button class="send-btn" @click="send">{{ lang === 'ru' ? 'Отправить' : 'Send' }}</button>

    <div class="note">
      {{ channel === 'telegram' ? 'Telegram-бот настраивается в backend.py' : 'VK Max Bot API (dev.max.ru)' }}
    </div>
  </div>
</template>

<style>
/* Панель напоминаний — цвета из переменных темы. Позицию задаёт .notify-wrap (styles.css). */
.notify {
  position: relative; width: 300px; padding: 14px;
  background: var(--panel-bg); color: var(--text); border: 1px solid var(--panel-border);
  border-radius: var(--radius); box-shadow: var(--panel-shadow); backdrop-filter: var(--panel-blur);
}
.n-title { font-size: 13.5px; font-weight: 700; margin-bottom: 8px; }
.lbl { display: block; font-size: 11px; color: var(--muted); margin: 8px 0 4px; }
.inp, .sel {
  width: 100%; padding: 6px 8px; background: var(--input-bg); color: var(--input-text);
  border: 1px solid var(--input-border); border-radius: 6px; box-sizing: border-box; font-family: inherit; font-size: 12px;
}
.inp:focus, .sel:focus { outline: none; border-color: var(--accent); }
.send-btn {
  width: 100%; margin-top: 10px; padding: 8px; cursor: pointer; font-family: inherit;
  background: linear-gradient(135deg, var(--accent), var(--accent2)); color: var(--primary-text);
  border: none; border-radius: var(--radius-sm); font-size: 12.5px; font-weight: 700;
  box-shadow: var(--shadow-primary);
}
.send-btn:hover { filter: brightness(1.08); }
.note { margin-top: 8px; font-size: 11px; color: var(--muted); }
</style>
