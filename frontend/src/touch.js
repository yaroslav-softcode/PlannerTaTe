// Касания на холсте (телефон, планшет).
//
// Зачем этот файл. LiteGraph 0.7.18 по умолчанию слушает ТОЛЬКО мышь
// (LiteGraph.pointerevents_method = "mouse"), а Chrome не превращает касания в
// mousedown. Замер 01.10.26 настоящими touch-событиями через CDP: при движении
// пальцем приходили touchstart 1, pointermove 8, touchmove 7, pointerdown 1 —
// и НИ ОДНОГО mousedown. Поэтому на телефоне холст не двигался и не
// масштабировался, хотя кнопки (обычные DOM-элементы) на касания реагировали.
//
// Что делает:
//   1) один палец — работает штатный механизм LiteGraph через Pointer Events;
//      переключатель ставится в App.vue перед созданием LGraphCanvas;
//   2) два пальца — щипок (масштаб) и сдвиг холста. Такого кода в библиотеке
//      нет вообще (в build/litegraph.core.js ноль совпадений по "pinch"),
//      поэтому он живёт здесь.
// Мышь не затрагивается: слушаем только touch-события.

export function installTouchSupport(canvasEl, lc) {
  const active = new Map()   // identifier касания -> [x, y] в координатах холста
  let pinch = null           // { startDist, startScale, lastMid }

  const local = (t) => {
    const r = canvasEl.getBoundingClientRect()
    return [t.clientX - r.left, t.clientY - r.top]
  }
  const points = () => [...active.values()]
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1])
  const redraw = () => { lc.setDirty(true, true); if (lc.ds.onredraw) lc.ds.onredraw(lc.ds) }

  // Гасим штатное перетаскивание LiteGraph: во время щипка холст двигаем сами,
  // иначе сдвиг применился бы дважды, а карточка под пальцем «прилипла» бы.
  const stopLitegraphDrag = () => {
    lc.dragging_canvas = false
    lc.node_dragged = null
    lc.dragging_rectangle = null
  }

  const start = (e) => {
    for (const t of e.changedTouches) active.set(t.identifier, local(t))
    const pts = points()
    if (pts.length >= 2) {
      pinch = { startDist: Math.max(1, dist(pts[0], pts[1])), startScale: lc.ds.scale, lastMid: mid(pts[0], pts[1]) }
      stopLitegraphDrag()
      e.preventDefault()
    }
  }

  const move = (e) => {
    for (const t of e.changedTouches) if (active.has(t.identifier)) active.set(t.identifier, local(t))
    const pts = points()
    if (pts.length < 2 || !pinch) return
    const m = mid(pts[0], pts[1])
    // 1) сдвиг холста за серединой двух пальцев
    const scale = lc.ds.scale || 1
    lc.ds.offset[0] += (m[0] - pinch.lastMid[0]) / scale
    lc.ds.offset[1] += (m[1] - pinch.lastMid[1]) / scale
    pinch.lastMid = m
    // 2) масштаб вокруг середины — changeScale сам удерживает точку под пальцами
    const want = Math.max(lc.ds.min_scale, Math.min(lc.ds.max_scale, pinch.startScale * (dist(pts[0], pts[1]) / pinch.startDist)))
    if (Math.abs(want - lc.ds.scale) > 0.0005) lc.ds.changeScale(want, m)
    stopLitegraphDrag()
    redraw()
    e.preventDefault()
  }

  const end = (e) => {
    for (const t of e.changedTouches) active.delete(t.identifier)
    if (points().length < 2) pinch = null   // остался один палец — дальше обычное поведение
  }

  canvasEl.addEventListener('touchstart', start, { passive: false })
  canvasEl.addEventListener('touchmove', move, { passive: false })
  canvasEl.addEventListener('touchend', end, { passive: false })
  canvasEl.addEventListener('touchcancel', end, { passive: false })

  return () => {
    canvasEl.removeEventListener('touchstart', start)
    canvasEl.removeEventListener('touchmove', move)
    canvasEl.removeEventListener('touchend', end)
    canvasEl.removeEventListener('touchcancel', end)
  }
}
