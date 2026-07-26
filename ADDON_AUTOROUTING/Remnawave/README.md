# FreemanVPN routing для Remnawave

Workflow `.github/workflows/update-configs.yml` обновляет заголовок `routing`
в правилах ответов `HAPP` и `INCY`, когда меняется хотя бы один из файлов:

- `HAPP/DEFAULT.DEEPLINK`
- `INCY/DEFAULT.DEEPLINK`

## Настройка GitHub

Добавьте repository variable:

- `REMNAWAVE_API_BASE_URL` — URL API панели с суффиксом `/api`,
  например `https://panel.example.com/api`

Добавьте repository secret:

- `REMNAWAVE_TOKEN` — отдельный токен Remnawave со scopes
  `subscription-settings:get` и `subscription-settings:update`

## Требования к Response Rules

В Remnawave должны существовать:

- ровно одно правило с именем `HAPP`
- ровно одно правило с именем `INCY`
- ровно один заголовок `routing` в каждом из этих правил

Остальные поля и правила остаются под управлением Remnawave. Workflow получает
текущий набор правил, заменяет только два значения `routing` и отправляет оба
изменения одним PATCH-запросом.
