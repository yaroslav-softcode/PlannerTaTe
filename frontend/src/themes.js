/* Темы оформления PlannerTaTe — 10 тем (a, b, e, i, k, o, q, s, y, ab).
   Одна тема = палитра для canvas (карточки, связи, сетка) + preview для переключателя.
   Цвета интерфейса (сайдбар, панели, кнопки) живут в CSS-переменных с тем же именем —
   см. styles.css, блок :root[data-theme="..."]. Добавить тему = один объект здесь
   + один блок переменных в CSS + id в THEME_IDS.
   Палитры тем генерирует скрипт workspace/gen_themes.py, который сам подбирает
   контрасты (текст >= 7, muted >= 4.5, акцент как текст >= 4.5, подпись на
   акцентной кнопке >= 3). Правки в палитрах делать в нём, иначе таблица
   контрастов в README перестанет соответствовать коду.
   Архитектура карточек: light+flat (как C), dark glass (как A), dark neon (как B),
   dark flat — четыре проверенных рецепта, цвета задаёт тема.
   Нынешние темы — все тёмные, у каждой градиентный фон холста: на ровном фоне
   на канве видны артефакты GPU-отрисовки («стрейфы»). 01.10.26 по просьбе Ярослава
   из кода удалены 20 тем, которые до этого были скрыты (c,d,f,g,h,j,l,m,n,p,r,t,u,
   v,w,x,z,aa,ac,ad) — их куски сохранены в workspace/removed_themes_20261001/. */

/** #rrggbb + #rrggbb -> #rrggbb (t: 0..1 — доля второго цвета) */
export function mixHex(a, b, t) {
  const pa = parseHex(a), pb = parseHex(b)
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * t))
  return '#' + c.map(v => Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')).join('')
}
function parseHex(h) {
  let s = String(h || '#888888').replace('#', '')
  if (s.length === 3) s = s.split('').map(c => c + c).join('')
  const n = parseInt(s, 16) || 0
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
/** #rrggbb + alpha -> rgba(...) */
export function rgba(hex, a) {
  const [r, g, b] = parseHex(hex)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}
export function luma(hex) {
  const [r, g, b] = parseHex(hex)
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
}
/** Светлые темы: слишком светлый акцент притемняем, иначе белая карточка
    («Белый» в палитре) теряет рамку и полосу статуса. Раньше условие было жёстко
    `themeId !== 'c'`; 30.09.26 светлых тем стало четыре (c, d, j, l), поэтому
    смотрим на флаг light у темы, а оттенок притемнения берём из accentDarken
    (у темы C он не задан — работает прежний #4a5568, вид не изменился). */
function visibleAccent(hex, themeId) {
  const t = THEMES[themeId]
  if (!t) return hex
  // Монохромная тема («Чёрно-Белая» / «Мрамор», флаг mono): гасим ВСЁ цветное — карточку, полосу, порты, значки.
  // Светлота сохраняется, оттенок теряется. У ТЁМНОЙ монотемы серый светлый; у СВЕТЛОЙ — зеркалим
  // в тёмный, иначе белый серый сливается со светлым фоном/карточкой.
  if (t.mono) {
    const v = t.light
      ? Math.round(((1 - luma(hex)) * 0.55 + 0.12) * 255)
      : Math.round((luma(hex) * 0.9 + 0.15) * 255)
    const g = Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')
    return '#' + g + g + g
  }
  if (!t.light) return hex
  return luma(hex) > 0.78 ? mixHex(hex, t.accentDarken || '#4a5568', 0.55) : hex
}

/* Цвета статусов (полоса слева + текст статуса) — одинаковы во всех темах. */
export const STATUS_COLOR = {
  '': '#8b93a8', none: '#8b93a8', done: '#3fbf7f', wip: '#4f8ff7', waiting: '#e0a92b', problem: '#e05a5a',
}

/** Цвет надписи статуса. В монохромной теме — серый: сохраняем светлоту, убираем оттенок.
    Различать статусы в чёрно-белой теме помогает сама надпись (бегущая строка «ожидание»). */
export function statusColorOf(status) {
  const t = THEMES[activeId]
  const base = STATUS_COLOR[status || ''] || STATUS_COLOR['']
  if (!t || !t.mono) return base
  const v = t.light
    ? Math.round(((1 - luma(base)) * 0.55 + 0.12) * 255)
    : Math.round((luma(base) * 0.78 + 0.2) * 255)
  const g = Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')
  return '#' + g + g + g
}

const UI_FONT = "'Segoe UI', system-ui, sans-serif"
const MONO_FONT = "Consolas, 'Courier New', monospace"
// Леверы типографики: шрифт с засечками (family='serif') и тяжёлый плакатный
// (family='display'). Ни одна из нынешних 10 тем их не использует — оставлены
// для будущих тем с характерным шрифтом.
const SERIF_FONT = "Georgia, 'Times New Roman', serif"
const DISPLAY_FONT = "'Arial Black', 'Segoe UI', sans-serif"

export const THEMES = {
  /* ---------------- A. Стекло и градиент ---------------- */
  a: {
    id: 'a',
    label: { ru: 'Стекло', en: 'Glass' },
    hint: 'Полупрозрачные карточки на градиенте со свечением',
    // Превью для переключателя тем (цвета — как в старом .prev-a): фон, карточка, рамка, полоса.
    preview: { bg: 'linear-gradient(140deg, #141a2e, #1b1630 45%, #101726)',
               card: 'linear-gradient(180deg, rgba(120,150,255,.5), rgba(18,24,46,.82))',
               border: 'rgba(160,180,255,.55)', stripe: '#4f8ff7' },
    canvas: { roundRadius: 12, linkWidth: 2.6, linkBorder: 'rgba(4,6,14,.45)', linkGlow: 9, linkGlowAlpha: .5, ghost: '#9fb4e8' , linkColor: '#9fb4e8', linkAlpha: 0.8, linkCardMix: 0.3 },
    node: {
      radius: 12,
      fillTop: (acc) => rgba(mixHex(acc, '#ffffff', .34), .34),
      fillBot: (acc) => rgba(mixHex(acc, '#0a1020', .80), .80),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .42), .62),
      borderW: 1.5,
      glowColor: (acc) => rgba(acc, .5),
      glowBlur: 14,
      inner: 'rgba(255,255,255,.12)',
      shadow: { color: 'rgba(0,0,0,.45)', blur: 18, oy: 8 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#f2f4ff', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: 'rgba(216,223,255,.66)', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(200,208,235,.85)',
      imgDim: 'rgba(10,10,18,.58)',
      // Порты карточки (вариант 1): вход — кольцо, выход — точка.
      // portIdle — цвет свободного порта, portGlow — свечение (0 = без тени, просьба Ярослава 30.09.26),
      // portOutline — контур точки, portHole — заливка выемки (вариант «гнездо», сейчас не используется).
      portIdle: 'rgba(226,232,255,.5)', portGlow: 0, portOutline: 'rgba(6,9,18,.5)', portHole: 'rgba(4,7,16,.72)',
    },
    grid: { type: 'dots', spacing: 24, color: 'rgba(255,255,255,.065)', r: 1.1, minScale: .55 },
  },

  /* ---------------- B. Неон-терминал ---------------- */
  b: {
    id: 'b',
    label: { ru: 'Неон', en: 'Neon' },
    hint: 'Тёмный терминал: неоновые контуры, моноширинный шрифт',
    preview: { bg: '#070b10', card: '#041417', border: '#00ffd6', stripe: '#00ffd6' },
    canvas: { roundRadius: 6, linkWidth: 2, linkBorder: 'rgba(0,0,0,.55)', linkGlow: 12, linkGlowAlpha: .75, ghost: '#00ffd6' },
    node: {
      radius: 6,
      fillTop: (acc) => rgba(mixHex(acc, '#04070b', .88), .84),
      fillBot: (acc) => rgba(mixHex(acc, '#02040a', .93), .92),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .12), .85),
      borderW: 1,
      glowColor: (acc) => rgba(acc, .85),
      glowBlur: 16,
      inner: null,
      shadow: { color: 'rgba(0,0,0,.6)', blur: 14, oy: 6 },
      stripe: { w: 2, inset: 0, radius: 0, glow: 10 },
      titleColor: '#e6fff9', titleFamily: MONO_FONT, titleWeight: 700, titleSize: 11, titleLine: 14, titleUp: true,
      descColor: 'rgba(150,240,220,.6)', descFamily: MONO_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(150,240,220,.85)',
      imgDim: 'rgba(2,6,10,.72)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(0,255,214,.5)', portGlow: 0, portOutline: 'rgba(2,6,10,.75)', portHole: 'rgba(1,4,9,.85)',
    },
    grid: { type: 'lines', spacing: 26, color: 'rgba(0,255,214,.07)', r: 0, minScale: .4 },
  },



  /* ---------------- E. Океан ---------------- */
  e: {
    id: 'e',
    label: { ru: 'Океан', en: 'Ocean' },
    hint: 'Глубокий синий: полупрозрачные карточки, точки',
    preview: { bg: 'linear-gradient(150deg, #0b2138 0%, #08192b 55%, #061320 100%)', card: '#10374e', border: '#1b607e', stripe: '#35c2f0' },
    canvas: { roundRadius: 12, linkWidth: 2.6, linkBorder: 'rgba(4,6,14,.45)', linkGlow: 9, linkGlowAlpha: .5, ghost: '#8fc6e8' },
    node: {
      radius: 12,
      fillTop: (acc) => rgba(mixHex(acc, '#ffffff', .34), .34),
      fillBot: (acc) => rgba(mixHex(acc, '#04101c', .80), .80),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .42), .62),
      borderW: 1.5,
      glowColor: (acc) => rgba(acc, .5),
      glowBlur: 14,
      inner: 'rgba(255,255,255,.12)',
      shadow: { color: 'rgba(0,0,0,.45)', blur: 18, oy: 8 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#dbf4fc', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: 'rgba(145,221,247,.68)', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(145,221,247,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(53,194,240,0.5)', portGlow: 0, portOutline: 'rgba(6,9,18,.5)', portHole: 'rgba(4,7,16,.72)',
    },
    grid: { type: 'dots', spacing: 24, color: 'rgba(160,220,255,.07)', r: 1.1, minScale: .55 },
  },




  /* ---------------- I. Янтарь ---------------- */
  i: {
    id: 'i',
    label: { ru: 'Янтарь', en: 'Amber' },
    hint: 'Ретро-терминал: янтарный монохром, сканлайны',
    preview: { bg: 'radial-gradient(circle at 70% 20%, #1a1206 0%, #0b0803 60%)', card: '#372602', border: '#714f02', stripe: '#ffb000' },
    canvas: { roundRadius: 6, linkWidth: 2, linkBorder: 'rgba(0,0,0,.55)', linkGlow: 12, linkGlowAlpha: .75, ghost: '#ffc247' },
    node: {
      radius: 6,
      fillTop: (acc) => rgba(mixHex(acc, '#0a0703', .88), .84),
      fillBot: (acc) => rgba(mixHex(acc, '#100a02', .93), .92),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .12), .85),
      borderW: 1,
      glowColor: (acc) => rgba(acc, .85),
      glowBlur: 16,
      inner: null,
      shadow: { color: 'rgba(0,0,0,.6)', blur: 14, oy: 6 },
      stripe: { w: 2, inset: 0, radius: 0, glow: 10 },
      titleColor: '#fff1d1', titleFamily: MONO_FONT, titleWeight: 700, titleSize: 11, titleLine: 14, titleUp: true,
      descColor: 'rgba(255,212,116,.68)', descFamily: MONO_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(255,212,116,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(255,176,0,0.5)', portGlow: 0, portOutline: 'rgba(2,6,10,0.75)', portHole: 'rgba(1,4,10,0.85)',
    },
    grid: { type: 'lines', spacing: 26, color: 'rgba(255,176,0,.06)', r: 0, minScale: .4 },
  },


  /* ---------------- K. Сияние ---------------- */
  k: {
    id: 'k',
    label: { ru: 'Сияние', en: 'Aurora' },
    hint: 'Северное сияние: бирюза и фиолет, полупрозрачные карточки',
    preview: { bg: 'linear-gradient(150deg, #08202b 0%, #0b1626 45%, #06131a 100%)', card: '#163a3b', border: '#2b6d68', stripe: '#5eead4' },
    canvas: { roundRadius: 12, linkWidth: 2.6, linkBorder: 'rgba(4,6,14,.45)', linkGlow: 9, linkGlowAlpha: .5, ghost: '#7fe6d2' },
    node: {
      radius: 12,
      fillTop: (acc) => rgba(mixHex(acc, '#ffffff', .34), .34),
      fillBot: (acc) => rgba(mixHex(acc, '#041119', .80), .80),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .42), .62),
      borderW: 1.5,
      glowColor: (acc) => rgba(acc, .5),
      glowBlur: 14,
      inner: 'rgba(255,255,255,.12)',
      shadow: { color: 'rgba(0,0,0,.45)', blur: 18, oy: 8 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#e2fbf7', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: 'rgba(167,243,231,.68)', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(167,243,231,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(94,234,212,0.5)', portGlow: 0, portOutline: 'rgba(6,9,18,.5)', portHole: 'rgba(4,7,16,.72)',
    },
    grid: { type: 'dots', spacing: 26, color: 'rgba(140,240,220,.06)', r: 1.1, minScale: .55 },
  },




/* ---------------- O. Космос ---------------- */
  o: {
    id: 'o',
    label: { ru: 'Космос', en: 'Cosmos' },
    hint: 'Туманности на фоне, крупные скруглённые светящиеся связи',
    preview: { bg: '#0c1030', card: '#282654', border: '#4d4485', stripe: '#a78bfa' },
    canvas: { roundRadius: 24, linkWidth: 3.2, linkBorder: 'rgba(4,6,14,.45)', linkGlow: 14, linkGlowAlpha: 0.6, ghost: '#a78bfa' },
    node: {
      radius: 15,
      fillTop: (acc) => rgba(mixHex(acc, '#ffffff', .34), .34),
      fillBot: (acc) => rgba(mixHex(acc, '#0a0720', .80), .80),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .42), .62),
      borderW: 1.5,
      glowColor: (acc) => rgba(acc, .5),
      glowBlur: 18,
      inner: 'rgba(255,255,255,.12)',
      shadow: { color: 'rgba(0,0,0,.45)', blur: 18, oy: 8 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#efeafe', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: 'rgba(207,192,252,.68)', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(207,192,252,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(167,139,250,0.5)', portGlow: 0, portOutline: 'rgba(6,9,18,.5)', portHole: 'rgba(4,7,16,.72)',
    },
    grid: { type: 'none' },
  },


/* ---------------- Q. Магма ---------------- */
  q: {
    id: 'q',
    label: { ru: 'Магма', en: 'Magma' },
    hint: 'Тлеющие угли: почти чёрный фон, раскалённый оранжево-красный акцент, светящиеся связи',
    preview: { bg: 'radial-gradient(circle at 68% 78%, #2b1108 0%, #150a09 64%)', card: '#3f1b12', border: '#77321f', stripe: '#ff6a3d' },
    canvas: { roundRadius: 13, linkWidth: 2.8, linkBorder: 'rgba(4,6,14,.45)', linkGlow: 13, linkGlowAlpha: 0.55, ghost: '#ffa07a' },
    node: {
      radius: 13,
      fillTop: (acc) => rgba(mixHex(acc, '#ffffff', .34), .34),
      fillBot: (acc) => rgba(mixHex(acc, '#0d0605', .80), .80),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .42), .62),
      borderW: 1.4,
      glowColor: (acc) => rgba(acc, .5),
      glowBlur: 16,
      inner: 'rgba(255,255,255,.12)',
      shadow: { color: 'rgba(0,0,0,.45)', blur: 18, oy: 8 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#ffe4dc', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: 'rgba(255,174,149,.68)', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(255,174,149,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(255,106,61,0.5)', portGlow: 0, portOutline: 'rgba(6,9,18,.5)', portHole: 'rgba(4,7,16,.72)',
    },
    grid: { type: 'dots', spacing: 24, color: 'rgba(255,150,110,.06)', r: 1.1, minScale: .55 },
  },

/* ---------------- S. Пресса ---------------- */
  s: {
    id: 's',
    label: { ru: 'Пресса', en: 'Press' },
    hint: 'Газетная полоса: тёмные чернила, моноширинный шрифт, красный акцент',
    preview: { bg: 'linear-gradient(165deg, #1b2440 0%, #0f1424 55%, #090d18 100%)', card: '#351d29', border: '#67292f', stripe: '#e0453f' },
    canvas: { roundRadius: 10, linkWidth: 2.2, linkBorder: 'rgba(4,6,14,.45)', linkGlow: 8, linkGlowAlpha: 0.45, ghost: '#e8b9b3' , linkColor: '#cdc7bb', linkAlpha: 0.75, linkCardMix: 0.15 },
    node: {
      radius: 10,
      fillTop: (acc) => rgba(mixHex(acc, '#ffffff', .34), .34),
      fillBot: (acc) => rgba(mixHex(acc, '#090d18', .80), .80),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .42), .62),
      borderW: 1.2,
      glowColor: (acc) => rgba(acc, .5),
      glowBlur: 14,
      inner: 'rgba(255,255,255,.12)',
      shadow: { color: 'rgba(0,0,0,.45)', blur: 18, oy: 8 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#f9dedc', titleFamily: MONO_FONT, titleWeight: 700, titleSize: 12.5, titleLine: 15, titleUp: true,
      descColor: 'rgba(238,154,150,.68)', descFamily: MONO_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(238,154,150,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(224,69,63,0.5)', portGlow: 0, portOutline: 'rgba(6,9,18,.5)', portHole: 'rgba(4,7,16,.72)',
    },
    grid: { type: 'dots', spacing: 24, color: 'rgba(230,180,170,.06)', r: 1.1, minScale: .55 },
  },






/* ---------------- Y. Вольт ---------------- */
  y: {
    id: 'y',
    label: { ru: 'Вольт', en: 'Volt' },
    hint: 'Электро: фиолетово-бирюзовое свечение, моноширинный капс',
    preview: { bg: 'linear-gradient(150deg, #171043 0%, #0d0a24 55%, #07061a 100%)', card: '#24194a', border: '#422c7c', stripe: '#8b5cf6' },
    canvas: { roundRadius: 5, linkWidth: 2, linkBorder: 'rgba(0,0,0,.55)', linkGlow: 12, linkGlowAlpha: .75, ghost: '#a78bfa' },
    node: {
      radius: 5,
      fillTop: (acc) => rgba(mixHex(acc, '#060518', .88), .84),
      fillBot: (acc) => rgba(mixHex(acc, '#0b0824', .93), .92),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .12), .85),
      borderW: 1,
      glowColor: (acc) => rgba(acc, .85),
      glowBlur: 16,
      inner: null,
      shadow: { color: 'rgba(0,0,0,.6)', blur: 14, oy: 6 },
      stripe: { w: 2, inset: 0, radius: 0, glow: 10 },
      titleColor: '#eae2fd', titleFamily: MONO_FONT, titleWeight: 700, titleSize: 11.5, titleLine: 14.5, titleUp: true,
      descColor: 'rgba(192,166,250,.68)', descFamily: MONO_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(192,166,250,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(139,92,246,0.5)', portGlow: 0, portOutline: 'rgba(2,6,10,0.75)', portHole: 'rgba(1,4,10,0.85)',
    },
    grid: { type: 'lines', spacing: 24, color: 'rgba(139,92,246,.08)', r: 0, minScale: .4 },
  },



/* ---------------- AB. Кобальт ---------------- */
  ab: {
    id: 'ab',
    label: { ru: 'Кобальт', en: 'Cobalt' },
    hint: 'Штормовой: стальной синий, плотные карточки, резкие углы',
    preview: { bg: 'linear-gradient(155deg, #1e2a3a 0%, #131b26 55%, #0b1119 100%)', card: '#23304b', border: '#395080', stripe: '#6f9bff' },
    canvas: { roundRadius: 6, linkWidth: 2.6, linkBorder: 'rgba(4,6,14,.45)', linkGlow: 9, linkGlowAlpha: 0.3, linkAlpha: 0.7, ghost: '#9db6e8' },
    node: {
      radius: 6,
      fillTop: (acc) => rgba(mixHex(acc, '#ffffff', .34), .34),
      fillBot: (acc) => rgba(mixHex(acc, '#080d14', .80), .80),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .42), .62),
      borderW: 1.5,
      glowColor: (acc) => rgba(acc, .5),
      glowBlur: 14,
      inner: 'rgba(255,255,255,.12)',
      shadow: { color: 'rgba(0,0,0,.45)', blur: 18, oy: 8 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#e5edff', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: 'rgba(177,201,255,.68)', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(177,201,255,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(111,155,255,0.5)', portGlow: 0, portOutline: 'rgba(6,9,18,.5)', portHole: 'rgba(4,7,16,.72)',
    },
    grid: { type: 'dots', spacing: 26, color: 'rgba(150,180,255,.07)', r: 1.1, minScale: .55 },
  },




/* ---------------- AE. Бархат ---------------- */
  ae: {
    id: 'ae',
    label: { ru: 'Бархат', en: 'Velvet' },
    hint: 'Плюшевый фиолет: матовые карточки, засечки капсом, крупные скругления',
    preview: { bg: 'linear-gradient(155deg, #241534 0%, #1a1026 55%, #120b1a 100%)', card: '#281a33', border: '#4d3160', stripe: '#d1568f' },
    canvas: { roundRadius: 18, linkWidth: 2.2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#dca8c6' },
    node: {
      radius: 18,
      fillTop: () => '#281a33',
      fillBot: () => '#281a33',
      border: () => '#4d3160',
      borderW: 1,
      glowColor: () => 'rgba(0,0,0,.5)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(0,0,0,.42)', blur: 16, oy: 7 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#f7e1eb', titleFamily: SERIF_FONT, titleWeight: 700, titleSize: 13, titleLine: 16, titleUp: true,
      descColor: 'rgba(230,163,194,.68)', descFamily: SERIF_FONT, descSize: 8, descBand: 11,
      statusFamily: SERIF_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(230,163,194,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#dca8c6', portGlow: 0, portOutline: null, portHole: 'rgba(2,6,10,.7)',
    },
    grid: { type: 'lines', spacing: 26, color: 'rgba(209,86,143,.06)', r: 0, minScale: .4 },
  },

/* ---------------- AF. Лазурит ---------------- */
  af: {
    id: 'af',
    label: { ru: 'Лазурит', en: 'Lapis' },
    hint: 'Глубокий ультрамарин и золото: синее стекло, золотое свечение связей',
    preview: { bg: 'linear-gradient(155deg, #12245c 0%, #0d1b46 55%, #08122e 100%)', card: '#313339', border: '#64573a', stripe: '#e0b03c' },
    canvas: { roundRadius: 11, linkWidth: 2.8, linkBorder: 'rgba(4,6,14,.45)', linkGlow: 14, linkGlowAlpha: 0.6, ghost: '#e8c46a' },
    node: {
      radius: 11,
      fillTop: (acc) => rgba(mixHex(acc, '#ffffff', .34), .34),
      fillBot: (acc) => rgba(mixHex(acc, '#0a1740', .80), .80),
      border: (acc) => rgba(mixHex(acc, '#ffffff', .42), .62),
      borderW: 1.5,
      glowColor: (acc) => rgba(acc, .5),
      glowBlur: 16,
      inner: 'rgba(255,255,255,.12)',
      shadow: { color: 'rgba(0,0,0,.45)', blur: 18, oy: 8 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#f9f1dc', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: 'rgba(238,212,149,.68)', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(238,212,149,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: 'rgba(224,176,60,0.5)', portGlow: 0, portOutline: 'rgba(6,9,18,.5)', portHole: 'rgba(4,7,16,.72)',
    },
    grid: { type: 'dots', spacing: 24, color: 'rgba(224,176,60,.06)', r: 1.1, minScale: .55 },
  },

  /* ---------------- AG. Чёрно-Белая ---------------- */
  ag: {
    id: 'ag',
    label: { ru: 'Чёрно-Белая', en: 'Monochrome' },
    hint: 'Чёрно-белая: матовые карточки, белый акцент, без свечения',
    mono: true,
    preview: { bg: 'linear-gradient(155deg, #1d1d1d 0%, #141414 55%, #0c0c0c 100%)', card: '#1f1f1f', border: '#3c3c3c', stripe: '#f2f2f2' },
    canvas: { roundRadius: 10, linkWidth: 2.2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#cbcbcb', linkColor: '#cfcfcf', linkAlpha: 1, linkCardMix: 0.15 },
    node: {
      radius: 10,
      fillTop: () => '#1f1f1f',
      fillBot: () => '#1f1f1f',
      border: () => '#3c3c3c',
      borderW: 1,
      glowColor: () => 'rgba(0,0,0,.5)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(0,0,0,.42)', blur: 16, oy: 7 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#fdfdfd', titleFamily: MONO_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: true,
      descColor: 'rgba(248,248,248,.68)', descFamily: MONO_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(248,248,248,.9)',
      imgDim: 'rgba(6,10,18,.62)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#cbcbcb', portGlow: 0, portOutline: null, portHole: 'rgba(2,6,10,.7)',
    },
    grid: { type: 'lines', spacing: 26, color: 'rgba(255,255,255,.05)', r: 0, minScale: .4 },
  },

  /* ---------------- AH. Мрамор ---------------- */
  ah: {
    id: 'ah',
    label: { ru: 'Мрамор', en: 'Marble' },
    hint: 'Светлый монохром: белые матовые карточки, серый акцент, моноширинный капс',
    mono: true,
    light: true,
    linkTint: '#9ea5b6',
    accentDarken: '#3a3a40',
    preview: { bg: 'linear-gradient(155deg, #fafafb 0%, #f2f2f4 55%, #e8e8ec 100%)', card: '#ffffff', border: '#dcdce1', stripe: '#3f3f45' },
    canvas: { roundRadius: 10, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#a9a9b0', linkColor: '#7e7e86', linkAlpha: 1, linkCardMix: 0.2 },
    node: {
      radius: 10,
      fillTop: () => '#ffffff',
      fillBot: () => '#ffffff',
      border: () => '#dcdce1',
      borderW: 1,
      glowColor: () => 'rgba(28,28,34,.13)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(28,28,34,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#1b1b1d', titleFamily: MONO_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: true,
      descColor: '#6e6e6f', descFamily: MONO_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(110,110,111,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#a9a9b0', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'lines', spacing: 26, color: 'rgba(0,0,0,.05)', r: 0, minScale: .4 },
  },

/* ---------------- AI. Бумага ---------------- */
  ai: {
    id: 'ai',
    label: { ru: 'Бумага', en: 'Paper' },
    hint: 'Тёплая бумага: кремовые карточки, шрифт с засечками, кофейный акцент',
    light: true,
    linkTint: '#aba59e',
    accentDarken: '#5a4a38',
    preview: { bg: 'linear-gradient(160deg, #fdfaf3 0%, #f7f0e3 55%, #efe4d2 100%)', card: '#fffdf8', border: '#e6dcc8', stripe: '#8a5a2b' },
    canvas: { roundRadius: 8, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#c3a97f' },
    node: {
      radius: 8,
      fillTop: () => '#fffdf8',
      fillBot: () => '#fffdf8',
      border: () => '#e6dcc8',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 8, radius: 2, glow: 0 },
      titleColor: '#2a2320', titleFamily: SERIF_FONT, titleWeight: 600, titleSize: 12.5, titleLine: 15, titleUp: false,
      descColor: '#716e6a', descFamily: SERIF_FONT, descSize: 8, descBand: 11,
      statusFamily: SERIF_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(113,110,106,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#c3a97f', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- AJ. Иней ---------------- */
  aj: {
    id: 'aj',
    label: { ru: 'Иней', en: 'Frost' },
    hint: 'Холодный светлый: голубовато-серый, крупные скругления',
    light: true,
    linkTint: '#98b0ce',
    accentDarken: '#33546f',
    preview: { bg: 'linear-gradient(160deg, #f8fbff 0%, #e9f1fa 55%, #d9e6f4 100%)', card: '#ffffff', border: '#d5e3f2', stripe: '#3d7fbf' },
    canvas: { roundRadius: 14, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#9cc0e0' },
    node: {
      radius: 14,
      fillTop: () => '#ffffff',
      fillBot: () => '#ffffff',
      border: () => '#d5e3f2',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#1e2835', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#6d6f73', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(109,111,115,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#9cc0e0', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- AK. Гипс ---------------- */
  ak: {
    id: 'ak',
    label: { ru: 'Гипс', en: 'Gypsum' },
    hint: 'Почти белый минимализм: острые углы, тонкая чёткая рамка, графитовый акцент',
    light: true,
    linkTint: '#a2a8ba',
    accentDarken: '#3a3a3f',
    preview: { bg: 'linear-gradient(160deg, #fdfdff 0%, #f3f3f6 55%, #e9e9ed 100%)', card: '#ffffff', border: '#cfcfd4', stripe: '#43434a' },
    canvas: { roundRadius: 4, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#b0b0b6' },
    node: {
      radius: 4,
      fillTop: (acc) => mixHex('#ffffff', acc, 0.15),
      fillBot: (acc) => mixHex('#ffffff', acc, 0.07),
      border: () => '#cfcfd4',
      borderW: 1.2,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#1c1c1f', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#707070', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(112,112,112,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#b0b0b6', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'lines', spacing: 20, color: 'rgba(0,0,0,.04)', r: 0, minScale: .4 },
  },
/* ---------------- AL. Румянец ---------------- */
  al: {
    id: 'al',
    label: { ru: 'Румянец', en: 'Blush' },
    hint: 'Мягкий светлый: тёплый пудрово-розовый, сильные скругления',
    light: true,
    linkTint: '#b6a2b6',
    accentDarken: '#5c3a44',
    preview: { bg: 'linear-gradient(165deg, #fff9f7 0%, #f9e8e4 58%, #f2dcd7 100%)', card: '#ffffff', border: '#f0dcd7', stripe: '#c76a7e' },
    canvas: { roundRadius: 16, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#d9a3b0' },
    node: {
      radius: 16,
      fillTop: () => '#ffffff',
      fillBot: () => '#ffffff',
      border: () => '#f0dcd7',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#2a2022', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#736f6e', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(115,111,110,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#d9a3b0', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },

/* ---------------- AM. Миллиметр ---------------- */
  am: {
    id: 'am',
    label: { ru: 'Миллиметр', en: 'Millimeter' },
    hint: 'Инженерный светлый: миллиметровка, синие линии, острые углы, моно-цифры',
    light: true,
    linkTint: '#90a4c5',
    accentDarken: '#31456b',
    preview: { bg: 'linear-gradient(160deg, #f8fbff 0%, #eaf1fb 60%, #dde8f6 100%)', card: '#ffffff', border: '#c9d8ef', stripe: '#1d4ed8' },
    canvas: { roundRadius: 3, linkWidth: 1.6, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#8ea6cd' },
    node: {
      radius: 3,
      fillTop: () => '#ffffff',
      fillBot: () => '#ffffff',
      border: () => '#c9d8ef',
      borderW: 1.2,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 8, radius: 1, glow: 0 },
      titleColor: '#162239', titleFamily: MONO_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#6d6f73', descFamily: MONO_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(109,111,115,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#8ea6cd', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'lines', spacing: 16, color: 'rgba(37,74,150,.14)', r: 0, minScale: .35 },
  },

/* ---------------- D. Песок ---------------- */
  d: {
    id: 'd',
    label: { ru: 'Песок', en: 'Sand' },
    hint: 'Тёплый светлый: песочные тона, плоский фон',
    light: true,
    linkTint: '#aeaaa4',
    accentDarken: '#5a4a38',
    preview: { bg: '#f6f1e8', card: '#fffdf9', border: '#e7dcc9', stripe: '#b0771a' },
    canvas: { roundRadius: 10, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#c9b48c' },
    node: {
      radius: 10,
      fillTop: () => '#fffdf9',
      fillBot: () => '#fffdf9',
      border: () => '#e7dcc9',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#2a2230', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#706e6a', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(112,110,106,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#c9b48c', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },

/* ---------------- J. Роза ---------------- */
  j: {
    id: 'j',
    label: { ru: 'Роза', en: 'Rose' },
    hint: 'Мягкий светлый: розовые тона, плоский фон',
    light: true,
    linkTint: '#b59eba',
    accentDarken: '#5a3a4a',
    preview: { bg: '#fdf2f6', card: '#ffffff', border: '#f0d9e3', stripe: '#c4427c' },
    canvas: { roundRadius: 12, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#d79cb6' },
    node: {
      radius: 12,
      // 03.10.26 (просьба Ярослава): карточка подкрашена своим цветом — как у Гипса, Мяты, Лаванды, Бриза.
      fillTop: (acc) => mixHex('#ffffff', acc, 0.15),
      fillBot: (acc) => mixHex('#ffffff', acc, 0.07),
      border: () => '#f0d9e3',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#2a2230', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#736e70', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(115,110,112,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#d79cb6', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- L. Мята ---------------- */
  l: {
    id: 'l',
    label: { ru: 'Мята', en: 'Mint' },
    hint: 'Светлый холодный: мятный оттенок, плоский фон',
    light: true,
    linkTint: '#91b4b5',
    accentDarken: '#3d5a4d',
    preview: { bg: '#f0f7f3', card: '#ffffff', border: '#d9e9e0', stripe: '#2f9d78' },
    canvas: { roundRadius: 12, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#8fc7ad' },
    node: {
      radius: 12,
      fillTop: (acc) => mixHex('#ffffff', acc, 0.15),
      fillBot: (acc) => mixHex('#ffffff', acc, 0.07),
      border: () => '#d9e9e0',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#1d2332', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#6e716f', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(110,113,111,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#8fc7ad', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- M. Чертёж ---------------- */
  m: {
    id: 'm',
    label: { ru: 'Чертёж', en: 'Blueprint' },
    hint: 'Инженерный чертёж: острые углы, миллиметровка закреплена в окне',
    light: true,
    linkTint: '#90a4c5',
    accentDarken: '#31456b',
    preview: { bg: '#eef3fa', card: '#ffffff', border: '#c9d8ef', stripe: '#1d4ed8' },
    canvas: { roundRadius: 4, linkWidth: 1.6, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#8ea6cd' },
    node: {
      radius: 4,
      fillTop: () => '#ffffff',
      fillBot: () => '#ffffff',
      border: () => '#c9d8ef',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 10,
      glowOffsetY: 4,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.08)', blur: 10, oy: 6 },
      stripe: { w: 3, inset: 8, radius: 1, glow: 0 },
      titleColor: '#2a2230', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#6d6f73', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(109,111,115,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#8ea6cd', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'lines', spacing: 16, color: 'rgba(37,74,150,.14)', r: 0, minScale: .35, screen: true },
  },
/* ---------------- N. Пергамент ---------------- */
  n: {
    id: 'n',
    label: { ru: 'Пергамент', en: 'Parchment' },
    hint: 'Книжная страница: тёплая бумага, шрифт с засечками',
    light: true,
    linkTint: '#aaa6a2',
    accentDarken: '#6a4a2a',
    preview: { bg: '#f4ecdc', card: '#fffcf4', border: '#e3d5b6', stripe: '#9a4a1c' },
    canvas: { roundRadius: 6, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#c2ab86' },
    node: {
      radius: 6,
      fillTop: () => '#fffcf4',
      fillBot: () => '#fffcf4',
      border: () => '#e3d5b6',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 4, inset: 8, radius: 2, glow: 0 },
      titleColor: '#2a2230', titleFamily: SERIF_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#6e6b63', descFamily: SERIF_FONT, descSize: 8, descBand: 11,
      statusFamily: SERIF_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(110,107,99,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#c2ab86', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },

/* ---------------- P. Лаванда ---------------- */
  p: {
    id: 'p',
    label: { ru: 'Лаванда', en: 'Lavender' },
    hint: 'Светлая лаванда: мягкий фиолет, спокойные карточки без свечения',
    light: true,
    linkTint: '#9f9ecc',
    accentDarken: '#4a3a6e',
    preview: { bg: '#f6f3fc', card: '#ffffff', border: '#e4dcf6', stripe: '#6d4fd0' },
    canvas: { roundRadius: 14, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#ab9cda' },
    node: {
      radius: 14,
      fillTop: (acc) => mixHex('#ffffff', acc, 0.15),
      fillBot: (acc) => mixHex('#ffffff', acc, 0.07),
      border: () => '#e4dcf6',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#2a2230', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#706f73', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(112,111,115,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#ab9cda', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- R. Тушь ---------------- */
  r: {
    id: 'r',
    label: { ru: 'Тушь', en: 'Ink' },
    hint: 'Редакционный минимализм: белая бумага, чёрная обводка карточек, острые углы, без теней',
    light: true,
    linkTint: '#8e96a2',
    accentDarken: '#22223a',
    preview: { bg: '#fbfbf9', card: '#ffffff', border: '#1b1b1b', stripe: '#1f3a8a' },
    canvas: { roundRadius: 3, linkWidth: 1.8, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#8a8a86' },
    node: {
      radius: 3,
      fillTop: (acc) => mixHex('#ffffff', acc, 0.15),
      fillBot: (acc) => mixHex('#ffffff', acc, 0.07),
      border: () => '#1b1b1b',
      borderW: 1.5,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(0,0,0,0)', blur: 0, oy: 6 },
      stripe: { w: 3, inset: 8, radius: 0, glow: 0 },
      titleColor: '#2a2230', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#747473', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(116,116,115,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#8a8a86', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- T. Плакат ---------------- */
  t: {
    id: 't',
    label: { ru: 'Плакат', en: 'Poster' },
    hint: 'Агитплакат: тёплая бумага, тяжёлый плакатный шрифт капсом, красный акцент',
    light: true,
    linkTint: '#aea4a0',
    accentDarken: '#5a3a2a',
    preview: { bg: 'linear-gradient(165deg, #fdf6e8 0%, #f8e9d0 58%, #f2dcbd 100%)', card: '#fffaf1', border: '#e6d3b6', stripe: '#c9342a' },
    canvas: { roundRadius: 8, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#c9a882' },
    node: {
      radius: 8,
      fillTop: () => '#fffaf1',
      fillBot: () => '#fffaf1',
      border: () => '#e6d3b6',
      borderW: 1.2,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 4, inset: 8, radius: 2, glow: 0 },
      titleColor: '#2a2230', titleFamily: DISPLAY_FONT, titleWeight: 800, titleSize: 14, titleLine: 17, titleUp: true,
      descColor: '#716c64', descFamily: DISPLAY_FONT, descSize: 8, descBand: 11,
      statusFamily: DISPLAY_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(113,108,100,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#c9a882', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- U. Лёд ---------------- */
  u: {
    id: 'u',
    label: { ru: 'Лёд', en: 'Ice' },
    hint: 'Холодный светлый: ледяной голубой градиент, крупные скругления',
    light: true,
    linkTint: '#91acce',
    accentDarken: '#2b4a66',
    preview: { bg: 'linear-gradient(160deg, #f7fbff 0%, #e6f1fb 55%, #d7e7f7 100%)', card: '#ffffff', border: '#d6e6f5', stripe: '#2f7fd1' },
    canvas: { roundRadius: 12, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#8fb8e0' },
    node: {
      radius: 12,
      fillTop: () => '#ffffff',
      fillBot: () => '#ffffff',
      border: () => '#d6e6f5',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#2a2230', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#6d7073', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(109,112,115,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#8fb8e0', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- X. Пудра ---------------- */
  x: {
    id: 'x',
    label: { ru: 'Пудра', en: 'Powder' },
    hint: 'Нежная пудра: тёплый светлый градиент, засечки, сильный скруг',
    light: true,
    linkTint: '#b6a2b6',
    accentDarken: '#5c3a44',
    preview: { bg: 'linear-gradient(165deg, #fff8f6 0%, #f9e9e6 58%, #f2dcd8 100%)', card: '#ffffff', border: '#f0dcd8', stripe: '#cf7d92' },
    canvas: { roundRadius: 16, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#d9a3b0' },
    node: {
      radius: 16,
      fillTop: () => '#ffffff',
      fillBot: () => '#ffffff',
      border: () => '#f0dcd8',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#2a2230', titleFamily: SERIF_FONT, titleWeight: 700, titleSize: 12, titleLine: 15, titleUp: true,
      descColor: '#736f6e', descFamily: SERIF_FONT, descSize: 8, descBand: 11,
      statusFamily: SERIF_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(115,111,110,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#d9a3b0', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- AA. Бриз ---------------- */
  aa: {
    id: 'aa',
    label: { ru: 'Бриз', en: 'Breeze' },
    hint: 'Свежий светлый: аквамарин, скруглённые карточки',
    light: true,
    linkTint: '#89b5c2',
    accentDarken: '#35565a',
    preview: { bg: 'linear-gradient(165deg, #f6fdfc 0%, #e2f5f2 58%, #d0ece8 100%)', card: '#ffffff', border: '#d2eae6', stripe: '#17a2a2' },
    canvas: { roundRadius: 14, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#7fc9c6' },
    node: {
      radius: 14,
      fillTop: (acc) => mixHex('#ffffff', acc, 0.15),
      fillBot: (acc) => mixHex('#ffffff', acc, 0.07),
      border: () => '#d2eae6',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#2a2230', titleFamily: UI_FONT, titleWeight: 600, titleSize: 12, titleLine: 15, titleUp: false,
      descColor: '#6d7371', descFamily: UI_FONT, descSize: 8, descBand: 11,
      statusFamily: UI_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(109,115,113,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#7fc9c6', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },
/* ---------------- AC. Шафран ---------------- */
  ac: {
    id: 'ac',
    label: { ru: 'Шафран', en: 'Saffron' },
    hint: 'Пряный светлый: золотистая бумага, плакатный шрифт капсом',
    light: true,
    linkTint: '#b6ac9a',
    accentDarken: '#6b4a24',
    preview: { bg: 'linear-gradient(165deg, #fffaea 0%, #fbeecb 58%, #f6e0ae 100%)', card: '#fffdf6', border: '#ecd9ab', stripe: '#d98510' },
    canvas: { roundRadius: 10, linkWidth: 2, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#d8b878' },
    node: {
      radius: 10,
      fillTop: () => '#fffdf6',
      fillBot: () => '#fffdf6',
      border: () => '#ecd9ab',
      borderW: 1,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(24,39,75,.10)', blur: 14, oy: 6 },
      stripe: { w: 3, inset: 9, radius: 3, glow: 0 },
      titleColor: '#2a2230', titleFamily: DISPLAY_FONT, titleWeight: 800, titleSize: 13, titleLine: 16, titleUp: true,
      descColor: '#757169', descFamily: DISPLAY_FONT, descSize: 8, descBand: 11,
      statusFamily: DISPLAY_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(117,113,105,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#d8b878', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },

/* ---------------- AN. Перо ---------------- */
  an: {
    id: 'an',
    label: { ru: 'Перо', en: 'Pen' },
    hint: 'Тушь в лиловых чернилах, на сиреневой бумаге: чёрная обводка, моношрифт, капс',
    light: true,
    linkTint: '#9196a8',
    accentDarken: '#3a1c34',
    preview: { bg: '#f9f6f9', card: '#ffffff', border: '#1c1a20', stripe: '#6d2a5e' },
    canvas: { roundRadius: 3, linkWidth: 1.8, linkBorder: null, linkGlow: 0, linkGlowAlpha: 0, ghost: '#8f8a92' },
    node: {
      radius: 3,
      fillTop: () => '#ffffff',
      fillBot: () => '#ffffff',
      border: () => '#1c1a20',
      borderW: 1.5,
      glowColor: () => 'rgba(24,39,75,.16)',
      glowBlur: 12,
      glowOffsetY: 6,
      inner: null,
      shadow: { color: 'rgba(0,0,0,0)', blur: 0, oy: 6 },
      stripe: { w: 3, inset: 8, radius: 0, glow: 0 },
      titleColor: '#241b23', titleFamily: MONO_FONT, titleWeight: 400, titleSize: 11, titleLine: 14, titleUp: true,
      descColor: '#737173', descFamily: MONO_FONT, descSize: 8, descBand: 11,
      statusFamily: MONO_FONT, statusSize: 8.5, statusWeight: 700,
      dueColor: 'rgba(115,113,115,.9)',
      imgDim: 'rgba(12,16,28,.52)',
      // Порты (вариант 1): вход — кольцо, выход — точка; без свечения (portGlow = 0).
      portIdle: '#8f8a92', portGlow: 0, portOutline: null, portHole: 'rgba(38,46,64,.22)',
    },
    grid: { type: 'none' },
  },

}

// 01.10.26: 20 тем, которые до этого были скрыты, удалены из кода по просьбе Ярослава.
// Их объекты, CSS-блоки и спецификации лежат в workspace/removed_themes_20261001/:
// вернуть тему = вставить её кусок обратно и дописать id сюда.
// Порядок массива = порядок в меню тем. 02.10.26 (просьба Ярослава): Янтарь и Стекло поменяны
// местами — Янтарь первым. DEFAULT_THEME не менялся: приложение по-прежнему стартует со Стекло.
// ae Бархат — 02.10.26 Ярослав: «эта тема мне не понравилась». Убрана из списка, объект и CSS-блок
// оставлены на месте (вернуть = дописать 'ae' сюда; фон/капс/засечки матовые).
// af Лазурит — 02.10.26: «Эту тему ... удали». Убрана из списка, объект и CSS-блок оставлены
// (вернуть = дописать 'af' сюда).
// 03.10.26: убраны из меню по просьбе Ярослава — «ai Бумага, aj Иней, am Миллиметр, ac Шафран»
// (id можно вернуть в список в любой момент: код и блоки тем остаются на месте, как у e/ae/af).
export const THEME_IDS = ['i', 'b', 'a', 'k', 'o', 'q', 's', 'y', 'ab', 'ag', 'ah', 'ak', 'j', 'l', 'm', 'p', 'r', 'an', 'u', 'aa', 'my']
export const DEFAULT_THEME = 'a'
/* --- «Своя» тема (конструктор) ----------------------------------------------
   03.10.26, просьба Ярослава: «последней темой добавь свою — выбираешь интерфейс из
   существующих тем и шрифт любой, который установлен в системе, размер, жирность и
   кэпслок для названий карточек». Палитра берётся у выбранной БАЗОВОЙ темы (и её же
   data-theme ставит App.vue), поэтому своей CSS-блок не нужен; поверх подменяются
   титулы карточек: шрифт/жирность/капс (размер берётся у базовой темы). Помним в localStorage. */
export const CUSTOM_ID = 'my'
const CUSTOM_KEY = 'plannertate_custom'
const CUSTOM_DEF = { base: 'a', font: '', weight: 400, caps: false }
let customCfgCache = { ...CUSTOM_DEF }
try { Object.assign(customCfgCache, JSON.parse(localStorage.getItem(CUSTOM_KEY) || '{}')) } catch (e) {}
if (!THEMES[customCfgCache.base] || customCfgCache.base === CUSTOM_ID) customCfgCache.base = DEFAULT_THEME

let customBuilt = null
function buildCustom() {
  if (customBuilt) return customBuilt
  const c = customCfgCache
  const base = THEMES[c.base] || THEMES[DEFAULT_THEME]
  const node = { ...base.node }
  const fam = String(c.font || '').trim().replace(/"/g, '')
  if (fam) node.titleFamily = '"' + fam + '", ' + (base.node.titleFamily || 'sans-serif')
  // размер названий своей темой НЕ задаётся — берётся у базовой темы (Ярослав 03.10.26)
  node.titleWeight = Number(c.weight) || 400
  node.titleUp = !!c.caps
  customBuilt = {
    ...base, id: CUSTOM_ID, base: base.id, custom: { ...c },
    label: { ru: 'Своя', en: 'Custom' },
    hint: 'Своя тема: палитра от выбранной темы + свой шрифт, жирность и капс названий',
    node,
  }
  return customBuilt
}
/** Настройки своей темы (копия). */
export function customCfg() { return { ...customCfgCache } }
/** Изменить настройки своей темы; возвращает итоговые значения. */
export function setCustom(p) {
  const n = { ...customCfgCache, ...p }
  if (!THEMES[n.base] || n.base === CUSTOM_ID) n.base = customCfgCache.base
  n.font = String(n.font || '').slice(0, 60)
  const w = Number(n.weight); n.weight = isFinite(w) ? w : 400
  n.caps = !!n.caps
  customCfgCache = n
  customBuilt = null
  try { localStorage.setItem(CUSTOM_KEY, JSON.stringify(n)) } catch (e) {}
  return { ...n }
}
// THEMES['my'] — всегда свежая сборка: App.vue читает её и для label/preview, и для холста.
Object.defineProperty(THEMES, CUSTOM_ID, { get: buildCustom, enumerable: true, configurable: true })


/* --- Активная тема (модуль-синглтон: App.vue задаёт, отрисовка нод читает) --- */
let activeId = DEFAULT_THEME
export function setActiveTheme(id) {
  activeId = THEMES[id] ? id : DEFAULT_THEME
  return THEMES[activeId]
}
export function theme() { return THEMES[activeId] }
export function themeId() { return activeId }
/** Акцент узла, приведённый к видимости в текущей теме. */
export function accentOf(hex) { return visibleAccent(hex || '#5b8fd9', activeId) }
/** Цвет связи: акцент узла-источника (в светлых темах — приглушённый,
    оттенок приглушения — linkTint темы; у C он не задан => прежний #93a1bd). */
export function linkColorOf(hex) {
  const acc = visibleAccent(hex || '#5b8fd9', activeId)
  const t = THEMES[activeId]
  return (t && t.light) ? mixHex(acc, t.linkTint || '#93a1bd', .55) : acc
}
