# 🚀 FreemanVPN routing для Marzneshin

Один `subscription.py` для **любых** подписок (JSON и Non-JSON). Тип роутинга выбирается через переменную окружения.

## Установка

**1.** Скопируйте `subscription.py` на сервер:

```bash
curl -fLo /var/lib/marzneshin/subscription.py \
  https://raw.githubusercontent.com/losogudok/freemanvpn-routing/main/ADDON_AUTOROUTING/Marzneshin/subscription.py
```

**2.** Прилинкуйте файл в `docker-compose.yml` панели (`/etc/opt/marzneshin/docker-compose.yml`):

```yaml
services:
  marzneshin:
    volumes:
      - /var/lib/marzneshin:/var/lib/marzneshin
      - /var/lib/marzneshin/subscription.py:/app/app/routes/subscription.py   # ← добавить
```

**3.** *(опционально)* Выберите профиль роутинга через env var:

```yaml
    environment:
      FREEMANVPN_ROUTING_SOURCE: "default"   # default | jsonsub | whitelist | custom
      # FREEMANVPN_ROUTING_CUSTOM: "happ://..."  # только при source=custom
```

| Значение | Что отдаётся клиенту |
|---|---|
| `default` | Полный профиль: RU/BY direct, YouTube/Telegram/GitHub через прокси, реклама блокируется **(по умолчанию)** |
| `jsonsub` | Минимальный профиль для JSON-подписок: только DNS + кастомные geoip/geosite |
| `whitelist` | Direct только для сервисов и IP из белых списков РФ; всё остальное через прокси |
| `custom` | Ваша произвольная ссылка из `FREEMANVPN_ROUTING_CUSTOM` |

**4.** Перезагрузите Marzneshin:

```bash
marzneshin restart
```

Готово! Happ-клиенты при следующей синхронизации подписки получат FreemanVPN-роутинг в заголовке `Routing:`.

## Как это работает

- `subscription.py` монтируется поверх оригинального файла Marzneshin.
- При отдаче подписки он подтягивает содержимое `.DEEPLINK`-файла из [freemanvpn-routing](https://github.com/losogudok/freemanvpn-routing) с **кешем 10 минут** — никаких блокирующих запросов на каждый ответ.
- Если GitHub недоступен — отдаётся последний успешный ответ. Если кеш пуст — заголовок просто не ставится (ничего не ломается).

## Обновление

Чтобы обновить `subscription.py` на свежую версию:

```bash
curl -fLo /var/lib/marzneshin/subscription.py \
  https://raw.githubusercontent.com/losogudok/freemanvpn-routing/main/ADDON_AUTOROUTING/Marzneshin/subscription.py
marzneshin restart
```
