# 📱 Telegram Extractor Desktop App

A desktop application and background listener service for extracting, monitoring, and exporting Telegram messages.

---

## ✨ Features

- Extract Telegram messages from channels and groups
- Run a background listener service
- Export extracted data
- Simple desktop interface
- Local data processing
- Configurable settings

---

## 📂 Project Structure

```text
TelegramExtractorDesktopApp/
├── desktop/
│   ├── main.py
│   ├── dashboard_page.py
│   ├── extractor_module.py
│   ├── exporter_module.py
│   ├── telegram_worker.py
│   └── ...
│
├── listener_service/
│   ├── server.py
│   ├── listener_worker.py
│   ├── Procfile
│   └── requirements.txt
│
└── README.md
