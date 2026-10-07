/* Палитра цветов узлов */
export const NODE_COLORS = {
  'Белый': '#f5f5f5',
  'Зелёный': '#7bc67b',   // готово / выполнено
  'Жёлтый': '#e6c34a',   // в работе
  'Оранжевый': '#e08a3c', // ожидает
  'Красный': '#d95f5f',   // проблема
  'Синий': '#5b8fd9',    // план / корневой
  'Фиолетовый': '#9b7bd9',   // важно
  'Серый': '#bdbdbd',   // отложено
}
export const COLOR_NAMES = Object.keys(NODE_COLORS)
/* EN цвета (порядок совпадает с COLOR_NAMES / NODE_COLORS) */
export const COLOR_NAMES_EN = ['White', 'Green', 'Yellow', 'Orange', 'Red', 'Blue', 'Purple', 'Grey']

/* Статусы: FULL — подписи для инспектора, SHORT — для карточки (она всего 100×56).
   Ключ '' = статус не задан. */
export const STATUS_ORDER = ['none', 'done', 'wip', 'waiting', 'problem']
export const STATUS_FULL = {
  ru: { none: '—', done: 'Готово', wip: 'В работе', waiting: 'Ожидает', problem: 'Проблема' },
  en: { none: '—', done: 'Done', wip: 'In progress', waiting: 'Waiting', problem: 'Problem' },
}
export const STATUS_SHORT = {
  ru: { none: '', done: 'Готово', wip: 'В работе', waiting: 'Ожид.', problem: 'Проблема' },
  en: { none: '', done: 'Done', wip: 'WIP', waiting: 'Wait', problem: 'Problem' },
}

/* Напоминание (вид карточки 'notify'): как часто повторять и куда присылать.
   Ключи короткие — они пишутся в graph.json, поэтому не переименовывать. */
// Месяцы и дни недели — для своего календаря (DateField.vue): нативный календарь браузера
// подписывается на языке БРАУЗЕРА, а не приложения, поэтому названия держим у себя.
export const MONTHS = {
  ru: ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'],
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
}
export const WD_SHORT = {
  ru: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'],
  en: ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'],
}

export const REPEAT_ORDER = ['once', 'daily', 'weekly', 'weekdays', 'monthly']
export const REPEATS = {
  ru: { once: 'однократно', daily: 'ежедневно', weekly: 'еженедельно', weekdays: 'по будням', monthly: 'ежемесячно' },
  en: { once: 'once', daily: 'daily', weekly: 'weekly', weekdays: 'weekdays', monthly: 'monthly' },
}
/* Короткие формы повторения — ТОЛЬКО для карточки (в панели остаются полные слова: «ежемесячно»).
   Ярослав 01.10.26: «ежемесячно ежедневно можно сократить — ежемес. ежеднев. еженед.».
   «по будням» и «однократно» влезают целиком, их не трогаем; английские формы и так короткие. */
export const REPEATS_SHORT = {
  ru: { once: 'однократ.', daily: 'ежеднев.', weekly: 'еженед.', weekdays: 'по будням', monthly: 'ежемес.' },
  en: { once: 'once', daily: 'daily', weekly: 'weekly', weekdays: 'weekdays', monthly: 'monthly' },
}
/* Каналы доставки: 'pc' — уведомление Windows на компьютере, 'phone' — будильник в приложении
   PlannerTaTe на телефоне, 'telegram'/'vkmax' — бот и Макс. 02.10.26 Ярослав: «телеграмм и Макс
   пока временно убери» — галочек для них в панели больше нет, но данные и подписи оставлены:
   вернуть галочку = одна строка в CHANNEL_ORDER.
   CHANNEL_ORDER — что показано в панели напоминания; CHANNEL_ALL — полный список для нормализации
   порядка каналов в graph.json: у существующей карточки скрытый канал не теряется. */
export const CHANNEL_ORDER = ['pc', 'phone', 'tablet']
export const CHANNEL_ALL = ['pc', 'phone', 'tablet', 'telegram', 'vkmax']
export const CHANNEL_SHORT = {
  ru: { pc: 'ПК', phone: 'Тел', tablet: 'Плн', telegram: 'TG', vkmax: 'Макс' },
  en: { pc: 'PC', phone: 'Phone', tablet: 'Tab', telegram: 'TG', vkmax: 'Max' },
}

/* Локализация RU / EN */
export const L18N = {
  ru: {
    title: 'PlannerTaTe', status: 'Статус',
    newRoot: '+ Корневой узел', addTask: '+ Задача', addNotify: '+ Напоминание', save: 'Сохранить (Ctrl+S)', open: 'Открыть',
    notify: 'Список напоминаний', notifyTitle: 'Напоминание', collapse: 'Свернуть', expand: 'Развернуть', settings: 'Настройки', label: 'Название', color: 'Цвет', tags: 'Теги',
    delete: 'Удалить узел', connectFrom: 'Связать отсюда',
    readerBack: 'Назад',
    // Подсказка по карточкам — МАССИВОМ: в панели каждая комбинация выводится своей строкой
    // (03.10.26, просьба Ярослава: «разложи по строчкам»).
    selectHint: [
      'ЛКМ — выбрать карточку',
      'ПКМ — редактировать карточку',
      'Ctrl + ЛКМ — копировать карточку',
      'Кольцо — вход, кружок — выход: тяните связь от кружка к кольцу',
      'Клик по связи — удалить связь',
      'Двойной клик по карточке — подзадача',
      'Перетаскивание мышкой файлов в карточку — создание ссылки/фона',
      'Клик по значку файла на карточке — открытие ссылки',
    ],
    saveMsg: 'Сохранено в graph.json', saveFailed: 'Не удалось сохранить', saveRejected: 'Сохранение отклонено', filePickFail: 'Не удалось выбрать файл', fileOpenFail: 'Не удалось открыть файл', fileNoReminder: 'К напоминанию файл приложить нельзя — только к задаче', fileLimit: 'В карточке уже 5 ссылок — больше нельзя', channel: 'Куда отправить', message: 'Сообщение', send: 'Отправить',
    lang_label: 'Язык', channels: ['Telegram (бот)', 'VK Max'], placeholders: { msg: 'Текст напоминания…' },
    remDate: 'Дата начала', remTime: 'Время', remRepeat: 'Повторения', remTo: 'Куда придёт',
    close: 'Закрыть',
    /* «Своя» тема — конструктор (App.vue) */
    thPalette: 'Палитра (из темы)', thFont: 'Шрифт', thFontPh: 'любой шрифт системы',
    thFontLoad: 'Загрузить шрифты системы', thSize: 'Размер названий', thWeight: 'Жирность названий',
    thCaps: 'КАПС для названий карточек', thSave: 'Сохранить',
    thFontSearch: 'Поиск шрифта…', thFontDef: 'По умолчанию (шрифт темы)', thFontNone: 'Ничего не найдено',
    /* Таблица «Список напоминаний» (ReminderList.vue) */
    remListTitle: 'Список напоминаний', remListEmpty: 'Пока нет ни одного напоминания',
    rlTask: 'Задача', rlTime: 'Время', rlDate: 'Дата начала', rlRepeat: 'Повторение', rlHow: 'Доставка',
    rlDelete: 'Удалить', rlReally: 'Точно удалить?', rlReveal: 'Нажми, чтобы показать карточку на холсте',
    remNoCard: 'Сначала выберите карточку-задачу', today: 'Сегодня',
    remPc: 'На компьютере', remPhone: 'На телефоне', remTablet: 'На планшете', remTg: 'Telegram (бот)', remVk: 'Макс',
    /* Лицензия / поддержка автора (03.10.26). Строки оценки идут в том же порядке, что суммы
       в LicensePanel.vue (10 / 100 / 500 / 1000 ₽) — переставлять только вместе. */
    /* Установка приложения на телефон (03.10.26, просьба Ярослава) */
    phoneBtn: 'Установить на телефон',
    phoneBtnTab: 'Установить на планшет',
    phoneTitle: 'Установка на телефон',
    phoneTitleTab: 'Установка на планшет',
    phoneAsk: 'Установить приложение на телефон с ОС Андроид?',
    phoneAskYes: 'Да, установить',
    phoneAskLater: 'Позже',
    /* «Установить MCP на Гермес» (06.10.26, просьба Ярослава) */
    mcpBtn: 'Установить MCP на Гермес',
    mcpTitle: 'MCP для Гермеса',
    mcpChecking: 'Проверяю…',
    mcpInstalled: 'Похоже, MCP уже подключён к Гермесу.',
    mcpNotInstalled: 'Похоже, MCP ещё не подключён (или не удалось проверить).',
    mcpAbout: 'MCP — «мост» между Гермесом и планировщиком: задачи, файлы и чат «Гермес» на телефоне. Скопируйте сообщение ниже и отправьте его Гермесу в чате — он подключит сервер сам.',
    mcpCopy: 'Скопировать сообщение',
    mcpCopied: 'Скопировано — отправьте Гермесу',
    mcpCopyFail: 'Не получилось скопировать — выделите текст и скопируйте вручную',
    phoneStep1: '1. Наведите камеру телефона или планшета на этот код — откроется загрузка приложения:',
    phoneStep2: '2. Скачайте и установите: «Разрешить установку из этого источника» → «Установить».',
    phoneStep3: '3. Откройте PlannerTaTe на устройстве — адрес компьютера он найдёт сам. Останется ввести ключ (если приложение уже стоит, повторное наведение камеры подставит адрес и ключ само):',
    phoneKeyLabel: 'Ключ доступа',
    phoneCopy: 'Скопировать',
    phoneCopied: 'Скопировано',
    phoneSameNet: 'Телефон должен быть в той же сети Wi-Fi, что и компьютер.',
    phoneNoApk: 'Файл приложения ещё не положен рядом с программой — положите APK в папку app.',
    backupTitle: 'Создать резервную копию',
    backupDone: 'Резервная копия создана',
    backupFail: 'Не удалось создать копию',
    restoreTitle: 'Восстановить из резервной копии',
    restoreNote: 'Текущий граф сохранится отдельной копией — восстановление можно отменить. Выберите копию и нажмите «Восстановить» ещё раз для подтверждения.',
    restoreDo: 'Восстановить',
    restoreReally: 'Точно?',
    restoreEmpty: 'Резервных копий пока нет',
    restoreDone: 'Восстановлено — страница сейчас обновится',
    restoreFail: 'Не удалось восстановить',
    roNotice: 'Просмотр: правка карточек — на компьютере',
    demoRoot: 'Проект', demoStage: 'Этап',
    /* Пояснение под шагами установки (03.10.26, текст Ярослава). Списки RU и EN — ОДИН В ОДИН:
       столько же строк и тот же порядок, переставлять только вместе. */
    phoneAbout: [
      'Основное приложение для работы установлено на компьютере.',
      'Приложение на телефоне при синхронизации копирует все карточки и напоминания с компьютера на телефон при нахождении в одной сети Wi-Fi (автоматическая синхронизация проходит 07:00, 10:00, 14:00, 17:00, 21:00, 23:00).',
      'Запланированные напоминания воспроизводятся на телефоне в срок со звуком, установленным на будильник телефона.',
      'На телефоне можно создать новые карточки и напоминания, и они будут скопированы на компьютер при первой успешной синхронизации.',
      'Изменение существующих карточек на телефоне не поддерживается из-за возможных конфликтов с компьютером при синхронизации (возможны изменения в следующих версиях приложения).',
    ],
    phoneLinkLabel: 'Ссылка для телефона',
    /* Установка по кабелю (кнопка «Нет Wi-Fi», 04.10.26, просьба Ярослава) */
    wifiTab: 'По Wi-Fi (рекомендуется)',
    noWifiTab: 'Нет Wi-Fi',
    cableStep1: '1. Подключите устройство к компьютеру кабелем.',
    cableStep2: '2. На устройстве опустите шторку → способ подключения USB → «USB-модем» (включить).',
    cableStep3: '3. Откройте на устройстве этот адрес — откроется загрузка приложения:',
    cableStep4: '4. Скачайте и установите приложение, затем нажмите «Открыть и заполнить» — адрес и ключ подставятся сами.',
    cableWaiting: 'Кабельное подключение не найдено. Подключите кабель и включите «USB-модем» — адрес появится здесь. Проверить можно кнопкой ниже.',
    cableRefresh: 'Проверить снова',
    cableHint: 'Ключ можно ввести вручную или использовать кнопку автозаполнения (QR-код).',
    phoneManual: 'Если камерой не получится — откройте эту ссылку в браузере телефона:',
    licBtn: 'Благодарить',
    licTitle: 'Оцените приложение',
    licRows: [
      'Плохо, но вижу потенциал',
      'Нормально, задачу закрывает',
      'Хорошо, заметно ускоряет работу',
      'Отлично, пользуюсь каждый день',
    ],
    licPay: 'Оплатить',
    licThanks: 'Спасибо! Кнопка «Благодарить» больше не появится',
    licOpenFail: 'Не удалось открыть страницу оплаты',
    licLogo: 'Открыть страницу поддержки',
    /* Панели устройств на холсте («Смартфон»/«Планшет», 06.10.26, просьба Ярослава) */
    devicePhone: 'Смартфон',
    deviceTablet: 'Планшет',
    deviceNoDelete: 'Панель устройства удалить нельзя — она системная',
    deviceFileOk: 'Файл уехал на «{dev}» — дойдёт при синхронизации',
    deviceFileFail: 'Не удалось отправить файл на устройство',
    },
  en: {
    title: 'PlannerTaTe', status: 'Status',
    newRoot: '+ Root node', addTask: '+ Task', addNotify: '+ Reminder', save: 'Save (Ctrl+S)', open: 'Open',
    notify: 'Reminder list', notifyTitle: 'Reminder', collapse: 'Collapse', expand: 'Expand', settings: 'Settings', label: 'Label', color: 'Color', tags: 'Tags',
    delete: 'Delete node', connectFrom: 'Connect from here',
    readerBack: 'Back',
    selectHint: [
      'LMB — select a card',
      'RMB — edit a card',
      'Ctrl + LMB — duplicate a card',
      'Ring — input, dot — output: drag a link from dot to ring',
      'Click a link — delete the link',
      'Double-click a card — add subtask',
      'Drag a file onto a card — create a link/background',
      'Click the file badge on a card — open the link',
    ],
    saveMsg: 'Saved to graph.json', saveFailed: 'Could not save', saveRejected: 'Save rejected', filePickFail: 'Could not pick the file', fileOpenFail: 'Could not open the file', fileNoReminder: 'A file can be attached to a task only, not to a reminder', fileLimit: 'A card can hold up to 5 links', channel: 'Send to', message: 'Message', send: 'Send',
    lang_label: 'Language', channels: ['Telegram (bot)', 'VK Max'], placeholders: { msg: 'Reminder text…' },
    remDate: 'Start date', remTime: 'Time', remRepeat: 'Repeat', remTo: 'Where to send',
    close: 'Close',
    /* Custom theme — builder (App.vue) */
    thPalette: 'Palette (from theme)', thFont: 'Font', thFontPh: 'any system font',
    thFontLoad: 'Load system fonts', thSize: 'Title size', thWeight: 'Title weight',
    thCaps: 'CAPS for card titles', thSave: 'Save',
    thFontSearch: 'Search font…', thFontDef: 'Default (theme font)', thFontNone: 'Nothing found',
    /* Reminder-list table (ReminderList.vue) */
    remListTitle: 'Reminder list', remListEmpty: 'No reminders yet',
    rlTask: 'Task', rlTime: 'Time', rlDate: 'Start date', rlRepeat: 'Repeat', rlHow: 'Delivery',
    rlDelete: 'Delete', rlReally: 'Delete for sure?', rlReveal: 'Click to show the card on the canvas',
    remNoCard: 'Select a task card first', today: 'Today',
    remPc: 'On this computer', remPhone: 'On the phone', remTablet: 'On the tablet', remTg: 'Telegram (bot)', remVk: 'Max',
    /* Licence / supporting the author (03.10.26) — same order as the amounts in LicensePanel.vue */
    /* Phone app install (03.10.26) */
    phoneBtn: 'Install on the phone',
    phoneBtnTab: 'Install on the tablet',
    phoneTitle: 'Install on the phone',
    phoneTitleTab: 'Install on the tablet',
    phoneAsk: 'Install the app on an Android phone?',
    phoneAskYes: 'Yes, install',
    phoneAskLater: 'Later',
    /* Set up MCP for Hermes (06.10.26) */
    mcpBtn: 'Set up MCP for Hermes',
    mcpTitle: 'MCP for Hermes',
    mcpChecking: 'Checking…',
    mcpInstalled: 'Looks like MCP is already connected to Hermes.',
    mcpNotInstalled: 'Looks like MCP is not connected yet (or the check failed).',
    mcpAbout: 'MCP is the bridge between Hermes and the planner: tasks, files and the Hermes chat on your phone. Copy the message below and send it to Hermes in your chat — he will set the server up himself.',
    mcpCopy: 'Copy the message',
    mcpCopied: 'Copied — now send it to Hermes',
    mcpCopyFail: 'Could not copy — select the text and copy it manually',
    phoneStep1: '1. Point the phone or tablet camera at this code — the app download opens:',
    phoneStep2: '2. Download and install it: “Allow install from this source” → “Install”.',
    phoneStep3: '3. Open PlannerTaTe on the device — it finds the computer by itself. Then enter the key (if the app is already installed, scanning the code again fills in the address and key for you):',
    phoneKeyLabel: 'Access key',
    phoneCopy: 'Copy',
    phoneCopied: 'Copied',
    phoneSameNet: 'The phone must be on the same Wi-Fi network as the computer.',
    phoneNoApk: 'The app file is not next to the program yet — put the APK into the app folder.',
    backupTitle: 'Create a backup',
    backupDone: 'Backup created',
    backupFail: 'Could not create a backup',
    restoreTitle: 'Restore from a backup',
    restoreNote: 'The current graph is saved as a separate copy, so a restore can be undone. Pick a copy and press Restore again to confirm.',
    restoreDo: 'Restore',
    restoreReally: 'Sure?',
    restoreEmpty: 'No backups yet',
    restoreDone: 'Restored — the page will reload now',
    restoreFail: 'Could not restore',
    roNotice: 'View only: edit the cards on the computer',
    demoRoot: 'Project', demoStage: 'Stage',
    /* Explanation under the install steps (03.10.26, Yaroslav's text). RU and EN lists are
       ONE TO ONE: same number of lines, same order — change only together. */
    phoneAbout: [
      'The main working app is installed on the computer.',
      'When syncing, the phone app copies all cards and reminders from the computer to the phone while both are on the same Wi-Fi network (automatic sync runs at 07:00, 10:00, 14:00, 17:00, 21:00 and 23:00).',
      'Scheduled reminders fire on the phone on time, with the sound set for the phone alarm.',
      'You can create new cards and reminders on the phone; they are copied to the computer on the first successful sync.',
      'Editing existing cards on the phone is not supported because of possible conflicts with the computer during sync (this may change in future versions of the app).',
    ],
    phoneLinkLabel: 'Link for the phone',
    /* Cable install (the “No Wi-Fi” button, 04.10.26) */
    wifiTab: 'Over Wi-Fi (recommended)',
    noWifiTab: 'No Wi-Fi',
    cableStep1: '1. Connect the device to the computer with the cable.',
    cableStep2: '2. On the device pull down the shade → USB connection mode → “USB tethering” (turn it on).',
    cableStep3: '3. Open this address on the device — the app download opens:',
    cableStep4: '4. Download and install the app, then tap “Open and fill in” — the address and key are filled in for you.',
    cableWaiting: 'No cable connection found. Plug in the cable and turn on “USB tethering” — the address will appear here. Use the button below to check.',
    cableRefresh: 'Check again',
    cableHint: 'The key can be typed manually, or use the autofill button (QR code).',
    phoneManual: 'If the camera does not work, open this link in the phone browser:',
    licBtn: 'Donate',
    licTitle: 'Rate the app',
    licRows: [
      'Bad, but I see the potential',
      'Okay, it gets the job done',
      'Good, it speeds me up',
      'Great, I use it every day',
    ],
    licPay: 'Pay',
    licThanks: "Thank you! The Donate button won't appear again",
    licOpenFail: 'Could not open the payment page',
    licLogo: 'Open the support page',
    /* Device panels on the canvas (“Smartphone”/“Tablet”, 06.10.26) */
    devicePhone: 'Phone',
    deviceTablet: 'Tablet',
    deviceNoDelete: "The device panel can't be deleted — it is a system element",
    deviceFileOk: 'The file is on its way to “{dev}” — it will arrive at the next sync',
    deviceFileFail: 'Could not send the file to the device',
    }
}
