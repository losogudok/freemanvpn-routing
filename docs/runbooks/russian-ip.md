# Russian IP: отдельный клиентский шаблон для Host в Remnawave

Компактный исходник: [XRAY_JSON/RUSSIAN_IP.JSON](../../XRAY_JSON/RUSSIAN_IP.JSON).
Он сохраняет структуру DEFAULT: SOCKS `10808`, HTTP `10809`, sniffing,
FakeDNS, статические адреса ФНС и внедрение текущего Host как `proxy` через
`remnawave.addVirtualHostAsOutbound`. Транспорт, TLS, UUID и адрес сервера
добавляет панель из Host/inbound; в клиентский шаблон их вручную не записывают.

Это отдельный шаблон для пункта «🇷🇺 Российский IP» в существующей подписке.
DEFAULT, Auto, HAPP/INCY payloads и действующие Response Rules не изменяются.
Workflow автоматически обновляет отдельный шаблон панели по UUID из
`REMNAWAVE_RU_IP_TEMPLATE_UUID`.

Готовый файл для установки:
[RUSSIAN_IP.JSON](https://github.com/losogudok/freemanvpn-routing/releases/download/russian-ip/RUSSIAN_IP.JSON).
Он обновляется после успешной сборки в **Update Routing Configs** на `main`.
Это шаблон Remnawave: данные подключения и outbound `proxy` добавляет панель.

## CI/CD: общий pipeline

Russian IP включён в [Update Routing Configs](../../.github/workflows/update-configs.yml).
Отдельного workflow, renderer или скрипта синхронизации для него нет.
Сборка запускается при push в `main`, по событию
`repository_dispatch: update-routing-configs` от geo-репозиториев и вручную.
На pull request выполняется job `build-xray` без публикации и обращения
к рабочей панели.

Job `build-xray` выбирает версии FreemanVPN GeoIP/Geosite один раз и использует
общий [render-xray-json.sh](../../scripts/render-xray-json.sh) для DEFAULT
и Russian IP. Auto строится из уже развёрнутого DEFAULT. Xray закреплён
по версии и SHA256 архива. Проверяются общая синхронизация и 25 сценариев
Russian IP для каждого варианта: компактного с DAT из сборок и развёрнутого
с пустым каталогом geo-файлов.

Все JSON сохраняются в Actions artifact `xray-json` на 30 дней:
`default.json`, `leastload.json` и каталог `russian-ip/`.
В общем `SHA256SUMS` записаны суммы всех файлов комплекта.
Job `publish-xray` публикует содержимое `russian-ip/` в
[GitHub Release `russian-ip`](https://github.com/losogudok/freemanvpn-routing/releases/tag/russian-ip):

| Файл | Назначение |
| --- | --- |
| `RUSSIAN_IP.JSON` | Развёрнутый шаблон для панели, не требующий клиентских DAT |
| `RUSSIAN_IP.compact.JSON` | Компактный шаблон для клиента с настроенными FreemanVPN DAT |
| `build-info.json` | Git commit исходников, версия Xray, теги, URL и SHA256 обоих DAT |
| `SHA256SUMS` | Контрольные суммы двух JSON и метаданных |

Релиз обновляется после успешной сборки на `main`; URL остаётся постоянным.
Используйте `/releases/download/russian-ip/…`, а не
`/releases/latest/download/…`. Публикация использует штатный `GITHUB_TOKEN`.

Для обновления панели в GitHub **Settings → Secrets and variables → Actions**
нужны существующие настройки общей синхронизации и UUID Russian IP:

| Тип | Имя | Значение |
| --- | --- | --- |
| Repository variable | `REMNAWAVE_API_BASE_URL` | Адрес API панели с `/api` |
| Repository variable | `REMNAWAVE_RU_IP_TEMPLATE_UUID` | UUID отдельного шаблона типа Xray JSON для RU Host |
| Repository secret | `REMNAWAVE_TOKEN` | API-токен с доступом к subscription templates и subscription settings |

Job `sync-remnawave` использует общий
[sync-remnawave-routing.sh](../../scripts/sync-remnawave-routing.sh).
Он скачивает тот же artifact, проверяет контрольные суммы и обновляет
DEFAULT, Auto, настроенные compact/sing-box шаблоны, Russian IP и заголовки
подписки в одной транзакции. Повторной сборки JSON перед PATCH нет.
Проверяются ответ PATCH и сохранённое содержимое через GET; при сбое
восстанавливаются все затронутые шаблоны и настройки. Неудачный откат
отмечается в логе, job остаётся красным. Имена шаблонов и назначения Host
синхронизация не меняет.

Если `REMNAWAVE_RU_IP_TEMPLATE_UUID` не задана, общий pipeline пропускает
обновление RU-шаблона, продолжая обслуживать остальные цели. Если UUID
задан, но отсутствует, имеет неверный тип или совпадает с другой управляемой
целью, вся синхронизация останавливается до записей. Сам шаблон нужно один
раз создать в панели и назначить Host по инструкции ниже.

Первый запуск после настройки UUID: **Actions → Update Routing Configs →
Run workflow → main → force_sync: true**. Этот флаг нужен также для ручного
повторного обновления панели, когда исходники и геоданные не менялись.
Релиз публикуется до синхронизации; при сетевой ошибке панели он остаётся
доступным. После исправления доступа можно перезапустить job
`sync-remnawave` или запустить workflow с `force_sync: true`.

## Политика

- Домены `.ru`, `.su`, `.рф` (punycode), FreemanVPN `category-ru`,
  `whitelist` и `ip-checkers` направляются через `proxy`, то есть выбранный
  RU Host. Проверки IP поэтому показывают адрес этого Host.
- Подсети из FreemanVPN `geoip:direct` и `geoip:whitelist` также направляются
  через `proxy`. Имя категории `direct` не задаёт выход: его задаёт
  `outboundTag` правила. Применяются списки из тех же сборок FreemanVPN,
  что и в DEFAULT/Happ; отдельная сторонняя страновая база не используется.
- Это не строго страновая геобаза РФ: `direct` включает также Беларусь,
  дополнительные сети и Apple Push. Они тоже пойдут через RU Host.
  IPv4/IPv6 обрабатываются в пределах содержимого этих категорий.
- Локальные имена и приватные адреса идут напрямую. Доменные правила RU
  имеют приоритет над IP-классификацией; обращение к локальному сервису по
  имени `.ru` тоже будет считаться RU-направлением.
- Блокировок в этом шаблоне нет. Остальной TCP/UDP идёт напрямую;
  YouTube/GitHub/Telegram не перенаправляются через RU просто потому,
  что они PROXY в обычном DEFAULT.
- DNS для выбранных RU-доменов и проверок IP использует Yandex DoH через RU.
  Остальные запросы встроенного DNS используют Google DoH напрямую.

`routing.domainStrategy: IPOnDemand` нужен для неизвестного домена с IP
из выбранных категорий FreemanVPN:
Xray проверяет его адрес до финального `tcp,udp → direct`. С `IPIfNonMatch`
финальное правило уже совпало бы, и повторного прохода с DNS не случилось бы.
При ошибке разрешения неизвестного домена классификация по IP не гарантируется.
Это политика по доменным спискам и геобазе, а не определение юрисдикции
каждого сервиса.

## Geo-файлы и подготовка для панели

Компактный исходник использует `geosite:` и `geoip:` так же, как остальные
шаблоны `XRAY_JSON`. Для запуска ему нужны **оба DAT-файла из сборок
freemanvpn-geoip и freemanvpn-geosite**, а не стандартные geo-файлы клиента.
Для обычных клиентских профилей URL сборок берутся из `Geoipurl` и
`Geositeurl` в `HAPP/DEFAULT.JSON`. У опубликованного Russian IP compact
точные URL проверенных DAT записаны в `build-info.json` рядом с JSON.

В Happ эти URL входят в routing payload. В компактной подписке v2RayTun
они передаются заголовками `geoipurl` и `geositeurl` вместе с metadata
`routing`, как описано в [инструкции](v2raytun-compact-json.md).
Добавлять поля Happ `Geoipurl`/`Geositeurl` в Xray JSON не нужно:
само ядро Xray не скачивает DAT по таким полям.

Для обычной выдачи Remnawave можно развернуть категории в домены и CIDR
штатным renderer, как для DEFAULT. Источниками остаются сборки FreemanVPN.

Для ручной сборки из корня freemanvpn-routing нужны `bash`, `git`, `jq`,
`python3` и установленный Xray:

```sh
bash scripts/render-xray-json.sh XRAY_JSON/RUSSIAN_IP.JSON /tmp/russian-ip.json
python3 scripts/check-russian-ip.py /tmp/russian-ip.json
```

Общий renderer берёт последние числовые release tags
`losogudok/freemanvpn-geoip` и `losogudok/freemanvpn-geosite` и разворачивает
категории из опубликованных CIDR/доменных списков. Сторонняя страновая база
не загружается.

Чтобы повторить версии геоданных из скачанного `build-info.json`:

```sh
FREEMAN_GEOIP_TAG="$(jq -r '.geoip.tag' /tmp/russian-ip-install/build-info.json)" \
FREEMAN_GEOSITE_TAG="$(jq -r '.geosite.tag' /tmp/russian-ip-install/build-info.json)" \
  bash scripts/render-xray-json.sh XRAY_JSON/RUSSIAN_IP.JSON /tmp/russian-ip.json
```

В обычный шаблон панели вставляется **развёрнутый `RUSSIAN_IP.JSON`** из релиза
или локальной сборки.
В нём нет `geoip:`/`geosite:`, поэтому клиентские geo-файлы ему не требуются.
Компактный исходник можно использовать при настроенной доставке обоих
FreemanVPN DAT-файлов. Новая категория `geoip:ru` не нужна.

## Назначение одному Host

Скачайте весь комплект и проверьте контрольные суммы:

```sh
mkdir -p /tmp/russian-ip-install
release_url='https://github.com/losogudok/freemanvpn-routing/releases/download/russian-ip'
for filename in RUSSIAN_IP.JSON RUSSIAN_IP.compact.JSON build-info.json SHA256SUMS; do
  curl -fL --retry 3 "$release_url/$filename" -o "/tmp/russian-ip-install/$filename"
done
(cd /tmp/russian-ip-install && sha256sum --check SHA256SUMS)
```

1. В Remnawave откройте **Subscription Templates**, создайте отдельный
   шаблон типа **Xray JSON** с именем `Russian IP`. Вставьте содержимое
   `/tmp/russian-ip-install/RUSSIAN_IP.JSON` и сохраните. Укажите UUID этого
   шаблона в repository variable `REMNAWAVE_RU_IP_TEMPLATE_UUID`.
2. Создайте отдельный включённый и видимый Host с названием
   `🇷🇺 Российский IP`. Привяжите его к inbound российского сервера с
   российским выходом. Этот inbound должен быть доступен скваду пользователя.
   Требование к серверному routing описано ниже.
3. В расширенных настройках этого Host в поле **Xray JSON Template**
   выберите `Russian IP`. Остальные Host сохраняют свои шаблоны.
4. Для нужного клиента применяемый **Response Rule** должен выдавать
   `XRAY_JSON`; `ignoreHostXrayJsonTemplate` должен быть `false` либо
   отсутствовать. Не назначайте Russian IP глобальным шаблоном подписки:
   это режим одного Host.
5. Обновите подписку в приложении и выберите `🇷🇺 Российский IP`.
   В полученном JSON панель должна убрать секцию `remnawave` и добавить
   outbound `proxy` с данными выбранного RU Host. В приложении не должны
   заменять эти правила глобальные или импортированные маршруты.
6. Проверьте `2ip.ru`: должен отображаться российский выход сервера.
   Для российского сайта в логах Xray должен выбираться `proxy`, для
   зарубежного сайта вне выбранных FreemanVPN-списков — `direct`.

После успешного job **sync-remnawave** содержимое этого шаблона обновлено
автоматически. Host переназначать не нужно, но пользователи должны обновить
подписку. При ручной установке без CI заменяйте содержимое существующего
шаблона развёрнутым JSON из релиза. Исходник из `XRAY_JSON/` и
`RUSSIAN_IP.compact.JSON` не являются заменой развёрнутого файла, если
доставка FreemanVPN DAT в клиент не настроена.

Шаблон не является готовым конфигом для ручного запуска Xray: до обработки
панелью в нём намеренно нет `proxy`. Для проверки ядра checker подставляет
локальные заглушки, не содержащие пользовательских данных.

INCY сейчас получает `XRAY_BASE64` с общим routing payload. Назначение этого
шаблона Host само по себе не меняет эту выдачу. Совместимость полного JSON,
порядок объединения правил, DNS и отсутствие вмешательства клиентских
глобальных правил должны проверяться на нужных версиях приложений.

## Обязательное условие на RU Node

Клиент выбирает путь до RU, а Node выбирает место выхода в интернет.
Текущий `bridge-profile.json` содержит пересылку в DE. Категория
FreemanVPN `category-ru` в нём не тождественна стандартному Geosite
`category-ru`, а IP-правила без разрешения домена не обеспечивают RU-выход
для каждого нового домена. Поэтому один клиентский файл не гарантирует
российский IP для всех выбранных направлений при любом серверном routing.

Для гарантированного RU-выхода используйте отдельный inbound, например
`VLESS_XHTTP_RU_EXIT`, и после правил блокировок, но перед пересылкой в DE
добавьте серверное правило:

```json
{
  "inboundTag": ["VLESS_XHTTP_RU_EXIT"],
  "outboundTag": "DIRECT"
}
```

Входной HTTP path и локальный порт такого inbound должны быть отдельными,
например `/api-ru/` и `127.0.0.1:8005`, с соответствующим `grpc_pass` в
существующем Nginx на 443. Два Host с одним inbound не получают разные
серверные правила только из-за назначения разных клиентских шаблонов.
Не перенаправляйте общий stream-up inbound в DIRECT, если другие Host
должны по-прежнему использовать через него DE.

Этот шаг не применялся к Node или Nginx. Также нужны работающий российский
публичный выход сервера и корректный IPv6-выход либо отдельная IPv4-политика.

## Проверка

Checker проверяет 25 сценариев выбора маршрута: RU-домены, `category-ru`,
`whitelist`, проверки IP, IPv4/IPv6 из GeoIP, неизвестные домены с адресами
из этих списков, зарубежные/BY/Apple IP, локальную сеть, отсутствие
блокировки рекламы и отдельные правила DNS. Все outbounds в проверке
заменены на локальные blackhole, сетевые обращения наружу исключены.

Для компактного исходника передайте каталог с DAT-файлами, скачанными
по URL из `HAPP/DEFAULT.JSON`:

```sh
python3 scripts/check-russian-ip.py XRAY_JSON/RUSSIAN_IP.JSON \
  --assets /path/to/freemanvpn-assets
```

Для развёрнутого варианта `--assets` не нужен: checker использует пустой
каталог geo-файлов. Оба варианта проверены на Xray 26.11.9.

Это проверка маршрутизации ядра. Импорт в панель, внедрение реального
outbound, приложение, фактический RU IP и DNS внутри мобильного туннеля
нужно проверить после назначения Host.

Источники: [Remnawave per-host templates](https://docs.rw/learn-en/routing-rules/),
[Xray routing](https://xtls.github.io/en/config/routing.html),
[Xray DNS tags и DoH](https://xtls.github.io/en/config/dns.html),
[FreemanVPN GeoIP](https://github.com/losogudok/freemanvpn-geoip),
[FreemanVPN Geosite](https://github.com/losogudok/freemanvpn-geosite).
