# 🎬 AI Video & Content Team Agent

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Aiogram 3](https://img.shields.io/badge/Aiogram-3.14+-2CA5E0?style=flat&logo=telegram&logoColor=white)](https://github.com/aiogram/aiogram)
[![Remotion](https://img.shields.io/badge/Remotion-4.0+-0B84F3?style=flat&logo=react&logoColor=white)](https://remotion.dev)
[![ElevenLabs Scribe](https://img.shields.io/badge/ElevenLabs-Scribe_API-black?style=flat)](https://elevenlabs.io)
[![MediaPipe](https://img.shields.io/badge/Google-MediaPipe_BlazeFace-FF6F00?style=flat&logo=google&logoColor=white)](https://developers.google.com/mediapipe)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-6.0+-007808?style=flat&logo=ffmpeg&logoColor=white)](https://ffmpeg.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Автономный Telegram-агент полного цикла для **профессионального видеомонтажа вертикальных роликов (Reels / Shorts / TikTok)** и управления контент-командой.

Бот принимает исходное видео говорящей головы (напрямую в Telegram или ссылкой на Яндекс.Диск), проводит пословную транскрибацию через **ElevenLabs Scribe**, вырезает брак и паузы без щелчков, накладывает кинетический зум с сохранением пропорций, автоматически определяет безопасную зону лица через **MediaPipe** и рендерит стильные luxury-субтитры через **Remotion Pro**.

---

## 🌟 Ключевые возможности

### 1. ✂️ Audio-First монтаж по методологии video-use
- **Пословная транскрибация (ElevenLabs Scribe)**: точность до миллисекунды для каждого слова, знака препинания и паузы.
- **Удаление мусора**: интеллектуальная вырезка слов-паразитов (*«эээ»*, *«ммм»*, заиканий, оговорок) и пауз тишины длительнее `0.4 сек`.
- **Бесшовные склейки (30ms afade)**: каждая точка разреза сглаживается микрофейдом громкости в 30 мс, полностью устраняя щелчки звуковой дорожки.
- **Эмоциональные якоря**: сохранение смеха, вздохов и эмоциональных интонаций спикера.

### 2. 🎯 MediaPipe BlazeFace: Безопасные зоны лица
- Кадровый анализ лица и линии волос спикера через облегченную нейросеть `blaze_face_short_range`.
- **Динамический расчет хэдрума**: субтитры автоматически размещаются в верхней зоне (`top: 185–240px`), если запас над головой достаточен, либо переносятся в нижнюю треть (`bottom: 440px`) на крупных планах.
- **Защита от наложения при зуме**: субтитры гарантированно не перекрывают лицо, глаза или лоб спикера.

### 3. 🎥 Кинетическое движение камеры (Zoompan)
- Плавный динамический зум `1.0x -> 1.08x` на ключевых смысловых отрезках.
- Смещение точки кадрирования с приоритетом сохранения верхней части головы (`y_zoom = ih/6 - (ih/zoom/6)`).

### 4. ✨ Luxury-субтитры Remotion Pro
- **Двухшрифтовая типографика**:
  - Основной текст: гротеск `Montserrat` (500, чистый и читаемый).
  - Акцентные слова: антиква `Cormorant Garamond` (курсив 700) фирменного сливочно-желтого оттенка (`#FFF066`).
- **Строгий перенос акцентов**: ударная смысловая фраза всегда начинается с новой строки.
- **Караоке-подсветка**: текущее произносимое слово подсвечивается синхронно со звуковой дорожкой.
- **Очистка от знаков препинания**: удаление лишних точек и запятых по канонам премиального вирального видеомонтажа.

### 5. 🎨 Профессиональный мастеринг звука и цвета
- **Apple HDR to SDR Tone Mapping**: правильное преобразование видео iPhone (HLG / BT.2020 10-bit) в стандартизированный Rec.709 без пересвета и потери контраста.
- **Нормализация громкости EBU R128**: фильтр `loudnorm` приводит звук к стандарту соцсетей (`-16 LUFS`, True Peak `-1.0 dBFS`).
- **Поддержка B-Roll**: менеджер врезок перебивок поверх речи спикера.

### 6. 🤖 Мультиагентная контент-команда
Бот оснащен переключаемыми ролями:
- **Видеомонтажер** — монтаж исходников, субтитры, B-roll.
- **Копирайтер** — посты, сценарии сериалов, хуки по формуле ВИСП (Выгода, Интрига, Срочность, Причастность).
- **Главред** — фактчекинг, вычитка стоп-слов, контроль инфостиля.
- **Смысловик / Аналитик** — транскрипция созвонов и выжимка тезисов.
- **Техспециалист** — диагностика и техническая автоматизация.

---

## 📋 Системные требования

| Компонент | Минимальная версия | Назначение |
|---|---|---|
| **Python** | 3.11+ | Ядро бота (Aiogram 3, async pipeline) |
| **Node.js** | 18+ / 20+ LTS | Рендерер Remotion |
| **FFmpeg** | 6.0+ | Обработка видео, HDR тонемаппинг, фильтры |
| **MediaPipe** | 0.10.14+ | Нейросетевой трекинг лиц |

---

## ⚡️ Быстрый старт

### 1. Клонирование репозитория
```bash
git clone https://github.com/alexrexby/ai-video-editor-agent.git
cd ai-video-editor-agent
```

### 2. Настройка виртуального окружения Python
```bash
python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Установка движка Remotion и шрифтов
```bash
cd remotion
npm install
bash public/fonts/download_fonts.sh
cd ..
```

### 4. Настройка переменных окружения
Скопируйте шаблон `.env.example` в `.env`:
```bash
cp .env.example .env
```
Заполните обязательные переменные:
- `BOT_TOKEN` — токен от `@BotFather`
- `ELEVENLABS_API_KEY` — ключ с ElevenLabs (для Scribe транскрибации)
- `POLZA_API_KEY` — ключ Polza.ai или OpenAI для текстовых агентов

### 5. Запуск бота
```bash
python main.py
```

---

## 🛠 Конфигурация (`.env`)

```ini
# Токен Telegram-бота (@BotFather)
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ

# ElevenLabs API Key (для пословных таймингов Scribe)
ELEVENLABS_API_KEY=sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# AI / LLM провайдер (Polza.ai или OpenAI API)
POLZA_API_KEY=pza_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
AI_BASE_URL=https://api.polza.ai/api/v1
CLAUDE_MODEL=anthropic/claude-sonnet-4.5

# Опционально: локальный Telegram Bot API сервер (поддерживает файлы до 2 ГБ)
USE_LOCAL_BOT_API=false
LOCAL_BOT_API_URL=http://127.0.0.1:8081

# Путь к Remotion (по умолчанию: ./remotion)
REMOTION_DIR=./remotion
```

---

## 🚀 Развертывание на Linux-сервере (Systemd)

Для развертывания на Ubuntu / Debian сервере используйте готовый скрипт:

```bash
# Выполните на сервере от root:
curl -sSL https://raw.githubusercontent.com/alexrexby/ai-video-editor-agent/main/deploy/setup_server.sh | bash -s /opt/ai_video_editor
```

Скрипт автоматически:
1. Установит FFmpeg, Python 3 venv, Node.js 20.x, Git.
2. Установит зависимости Python и Remotion.
3. Скачает шрифты Cormorant Garamond и Montserrat.
4. Настроит и активирует службу `ai-video-agent.service` в Systemd.

### Управление службой:
```bash
# Статус
systemctl status ai-video-agent.service

# Перезапуск
systemctl restart ai-video-agent.service

# Просмотр логов в реальном времени
journalctl -u ai-video-agent.service -f
```

---

## 💡 Использование в Telegram

1. **Монтаж видео**:
   - Отправьте боту видеосообщение, файл `.mp4`/`.mov` или ссылку на видео на Яндекс.Диске.
   - Бот автоматически запустит пайплайн: транскрибация -> очистка -> safe-zone трекинг -> генерация Remotion-субтитров -> сборка FFmpeg -> отправка готового Reels в чат.
2. **Переключение ролей команды**:
   - `/role` — меню выбора активного специалиста (Видеомонтажер, Копирайтер, Главред, Смысловик, Техспециалист).
3. **Работа в топиках (Forum Topics)**:
   - Включите ветки (Topics) в Telegram-супергруппе и настройте топики специалистов через `topic_roles.json`.

---

## 📂 Структура проекта

```text
├── main.py                    # Точка входа Telegram-бота (Aiogram 3)
├── config.py                  # Конфигурация и переменные окружения
├── requirements.txt           # Python-зависимости
├── .env.example               # Шаблон конфигурации
├── engine/
│   ├── video_pipeline.py      # Ядро видеомонтажа (EDL, MediaPipe, FFmpeg, Remotion)
│   ├── elevenlabs_scribe.py   # Пословный транскрибатор ElevenLabs Scribe
│   ├── broll_manager.py       # Менеджер врезок B-Roll футажей
│   ├── yandex_disk.py         # Загрузчик больших видео с Яндекс.Диска
│   ├── insta_monitor.py       # Анализ постов и каруселей Instagram
│   ├── agent_runner.py        # Запуск LLM-промптов ролей команды
│   ├── prompts.py             # Системные инструкции специалистов
│   └── video_montage/         # Вспомогательные рендереры и утилиты
├── handlers/
│   └── router.py              # Роутинг сообщений, медиа и команд Telegram
├── remotion/
│   ├── package.json           # Зависимости Node.js / Remotion
│   ├── render.mjs             # Node.js скрипт рендера последовательности кадров
│   └── src/
│       ├── Root.jsx           # Конфигурация Remotion-композиций
│       └── CaptionsOverlay.jsx# Компонент анимированных luxury-субтитров
└── deploy/
    ├── setup_server.sh        # Скрипт 1-click установки на Ubuntu/Debian
    ├── deploy.sh              # Скрипт синхронизации и обновления
    └── ai-video-agent.service # Юнит службы Systemd
```

---

## 📄 Лицензия

Проект распространяется под свободной лицензией **MIT**. Подробности в файле `LICENSE`.
