# Happ compact Xray JSON

С 2026-11-22 общее правило `HAPP` выдаёт compact JSON всем подпискам,
запрошенным с User-Agent Happ. Обычные серверы используют `Xray Compact`,
Auto и российский IP — общие `Xray Auto Compact` и `Russian IP Compact`.
Назначения и UUID описаны в [каталоге общих конфигов](shared-client-routing.md).

## Сборка и геоданные

Политики берутся из `XRAY_JSON/DEFAULT.JSON`, DEFAULT с настройками Auto-пула
и `XRAY_JSON/RUSSIAN_IP.JSON`. Генераторы Happ и v2RayTun используют общий
`scripts/xray_templates.py`, сохраняя DNS, FakeDNS, sniffing и порядок правил.
В Auto назначения proxy заменяются балансировщиком.

`build-xray` один раз выбирает закреплённые geo release tags и скачивает DAT.
Их SHA256, URL и содержимое используются для проверки compact-шаблонов,
expanded-политик и routing-профиля Happ в одной сборке.

```sh
python3 scripts/render-happ.py dist/xray-json/happ \
  --build-info dist/xray-json/russian-ip/build-info.json
python3 scripts/check-happ.py dist/xray-json/happ \
  --assets /path/to/downloaded-dat --xray /path/to/xray
```

В bundle `happ/` входят `default.json`, `leastload.json`, `russian-ip.json`,
`routing.json`, `routing.deeplink` и `build-info.json`, покрытые общим
`SHA256SUMS`. Минимальный routing-профиль называется `FreemanVPN JSON`,
содержит Tunnel DNS и URL DAT, `UseChunkFiles: "false"` и пустые списки правил.
Правила маршрутизации остаются внутри полного JSON каждого сервера.
`LastUpdated` — время последнего из двух geo-релизов в Unix seconds.

DEFAULT и WHITELIST нативных профилей HAPP/INCY генерируются из общего
источника политик и используют те же закреплённые геоданные; минимальный
JSONSUB предназначен для доставки полных JSON.

## Настройка общего правила

Сначала прочитайте действующие правила и назначения, сохраните полный
снимок приватно. Используйте существующие shared compact шаблоны,
не создавая отдельные копии Happ. Все три UUID переменные обязательны:

| Переменная | Шаблон |
| --- | --- |
| `REMNAWAVE_HAPP_TEMPLATE_UUID` | `Xray Compact`, тот же UUID, что у v2RayTun DEFAULT |
| `REMNAWAVE_HAPP_AUTO_TEMPLATE_UUID` | `Xray Auto Compact`, тот же UUID, что у v2RayTun Auto |
| `REMNAWAVE_HAPP_RU_TEMPLATE_UUID` | `Russian IP Compact` |

Правило `HAPP` должно быть enabled, с оператором AND и единственным условием:
User-Agent CONTAINS `happ`, `caseSensitive: false`. Оно располагается до fallback.
Привязки к подписке в общем правиле нет. Предыдущее персональное правило
`HAPP_PRIVATE_RUSSIAN_IP` удаляется при согласованном общем включении.

Настройки общего правила:

- `responseType: XRAY_JSON`, `subscriptionTemplate: Xray Compact`.
- `ignoreHostXrayJsonTemplate: false` сохраняет назначения Auto/RU.
- `applyHeadersToEnd: true`, `ignoreServeJsonAtBaseSubscription: true`.
- Заголовок `routing` — минимальный `happ://routing/onadd/...` из bundle.
- `excludeHostsByTags: ["XRAY_EXPANDED_ONLY"]`; фильтр `XRAY_COMPACT_ONLY`
  в этом правиле скрывал бы нужные Auto/RU Host.

```sh
# Existing API/token, HAPP_DEFAULT, INCY_DEFAULT and RUNNER_TEMP are also required.
bash scripts/sync-remnawave-routing.sh dist/xray-json
```

Синхронизация требует проверенный bundle и перед PATCH проверяет условия
общего правила. Для старых установок с персональным правилом она сохраняет
его scope; сама не создаёт и не удаляет правила или Host, не меняет условия.
Содержимое шаблонов и управляемые поля правил обновляются транзакционно,
проверяются ответом PATCH и повторным GET. При неопределённом результате или
ошибке чтения восстанавливаются исходные настройки и затронутые шаблоны.
Каждый shared UUID записывается и откатывается один раз.

## Проверка выдачи и клиента

При смене scope проверяйте как прежнюю персональную подписку, так и другую
действующую подписку Happ с её существующим HWID. Ответ должен быть HTTP 200
с массивом JSON, минимальным routing header и единственными Auto/RU в пределах
доступных пользователю Host. Проверяйте ссылки outbound/balancer и parsing
каждого JSON с DAT этой сборки. Ответы остальных клиентов должны сохраниться.

[Отчёт Android-приёмки 2026-11-21](happ-compact-acceptance-2026-11-21.md)
описывает исходный персональный этап. Общее правило меняет аудиторию выдачи,
а не подтверждает работу всех версий и платформ Happ. Сохраняется известное
ограничение индикатора `Ping checking` при включённом VPN. Проверка RU на
российском подключении не заменяет проверку с зарубежной сети.
