# Setup: Bitwarden для секретов

Никаких `.env` файлов с секретами — все API ключи в Bitwarden, скрипт сам их тянет.

## Шаг 1 — добавить ключ в Bitwarden (в приложении Bitwarden или на сайте)

1. Открой Bitwarden app
2. **+ New Item** → Type: **Login**
3. Заполни:
   - **Name:** `TABUU Upload-Post API`  (имя ровно такое, скрипт ищет по нему)
   - **Username:** твой email от Upload-Post (необязательно, для памяти)
   - **Password:** сюда вставляешь API key из Upload-Post
4. Save

Так же для будущих сервисов: `TABUU Loudly`, `TABUU Ditto` и т.д. — просто пароль в поле Password.

## Шаг 2 — Bitwarden CLI (один раз)

```bash
# Залогиниться (вводишь email + master password)
bw login
```

## Шаг 3 — разблокировать сессию (раз в день)

```bash
# Разблокировка возвращает токен сессии
export BW_SESSION="$(bw unlock --raw)"
```

Этот `export` действует только в текущем терминале. Чтобы не делать каждый раз вручную:

**Опция A (проще):** добавь алиас в `~/.zshrc`:
```bash
alias bw-unlock='export BW_SESSION="$(bw unlock --raw)"'
```
Запускаешь `bw-unlock` один раз в день.

**Опция B (через macOS keychain — для автоматизации):** можно сохранить session в keychain и тянуть автоматом. Если нужно — попроси, сделаю.

## Шаг 4 — проверить что секрет тянется

```bash
cd /Users/a1111/Downloads/tabuu-tier-evolution/scraper
python3 secrets.py "TABUU Upload-Post API"
```

Должен вывести твой API key. Если выводит — всё ок.

## Шаг 5 — запустить fetcher

```bash
python3 fetch_upload_post.py
```

Создаст `../upload_post_metrics.json` с тем что отдал API.

---

## Где взять Upload-Post API key

1. Зайди https://app.upload-post.com (или https://www.upload-post.com → Login)
2. Settings / Account / API Keys
3. Generate new key → копируешь
4. Вставляешь в Bitwarden как Password у item `TABUU Upload-Post API`
