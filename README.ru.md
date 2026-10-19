*Русский* · [English](README.md)

# Marketplace MCP

MCP-сервер для аккаунтов покупателей Ozon, Wildberries и Яндекс Маркета. У адаптеров отдельные профили браузера, вход и разрешения.

| Адаптер | Возможности |
|---|---|
| Ozon | Заказы и возвраты, история покупок, каталог, корзина, избранное и списки, оформление заказа, финансы |
| Wildberries | Вход, синхронизация заказов и исторических цен |
| Яндекс Маркет | Вход, поиск и карточки товаров, список и синхронизация заказов, корзина и избранное под флагом |
| Общее хранилище | Нормализованные списки заказов и их детали для всех адаптеров |

## Требования

Все адаптеры используют постоянные профили Chromium. В Docker браузер запускается через Xvfb; задайте --shm-size=1g и подключите /data как постоянный том. Профиль даёт доступ к аккаунту, поэтому храните том приватно. Вызовы всех адаптеров выполняются в одном рабочем потоке последовательно: долгий запрос Ozon или ожидание входа блокирует обращения к другим маркетплейсам.

Для адаптера Ozon указано требование российского IP. Требование российского IP для Wildberries и Яндекс Маркета не проверено; сетевые ограничения могут зависеть от аккаунта и местоположения.

## Быстрый запуск

Для локальной разработки установите зависимости и Chromium, затем запустите сервер:

    uv sync
    uv run playwright install --with-deps chromium
    uv run python -m marketplace_mcp

Для Docker:

    docker build -t marketplace-mcp .
    docker run -i --rm --shm-size=1g -v /opt/marketplace-mcp:/data marketplace-mcp

По умолчанию используется stdio. Для постоянно работающего HTTP-сервера задайте MARKETPLACE_TRANSPORT=http и откройте порт 8084. На нём доступны /mcp и /metrics.

Войдите отдельно: через инструменты сессии Ozon, wildberries_open_login() или yandex_market_open_login(). Статус сессии каждого адаптера подтверждает доступ. Учётные данные и cookies остаются в соответствующем профиле.

## Общее поведение

Перед чтением локальной копии синхронизируйте заказы, если данные могут быть пустыми или устаревшими: Ozon использует sync_orders(), Wildberries — wildberries_sync_orders(), Яндекс Маркет — yandex_market_sync_orders(). Затем вызывайте marketplace_orders(marketplace=...) и marketplace_order_details(marketplace=..., order_number=...). Идентификатор маркетплейса входит в ключи базы данных.

Неиспользуемый контекст браузера закрывается лениво через MARKETPLACE_IDLE_SECONDS (по умолчанию 600 секунд); таймаут проверяется при начале следующей операции с браузером. Сохранённый профиль остаётся на диске и открывается при следующем вызове. Ноль отключает закрытие по простою.

Ошибки содержат код, например [session_expired], [rate_limited] или [upstream_unavailable]. Ошибка не означает пустой аккаунт. Изменяющие аккаунт операции ограничиваются настройками каждого адаптера. Оформление заказа Ozon может потратить деньги и имеет отдельный защитный флаг.

## Инструменты

Ozon: list_orders, order_products, order_parcels, purchases, bought_items, list_returns, search, get_search_filters, product_details, get_reviews, get_description, delivery_estimate, find_cheaper, get_cart, set_cart_quantity, select_cart_items, list_favorites, set_favorite, get_lists, create_list, delete_list, set_list_membership, check_favorite_price_drops, list_selections, get_selection, selection_products, create_selection, add_to_selection, remove_from_selection, set_selection_items, edit_selection, set_selection_public, delete_selection, get_checkout, configure_checkout, place_order, pay_order, list_cancel_reasons, cancel_order, session_status, start_login, submit_login_code, get_finances, get_points, sync_orders, sync_prices, store_stats, link_duplicates.

Wildberries: wildberries_open_login, wildberries_session_status, wildberries_sync_orders, wildberries_sync_prices.

Яндекс Маркет: yandex_market_open_login, yandex_market_session_status, yandex_market_search, yandex_market_product_details, yandex_market_add_to_cart, yandex_market_set_favorite, yandex_market_list_orders, yandex_market_sync_orders.

Общее хранилище: marketplace_orders, marketplace_order_details.

Подробности: [Ozon](docs/ozon.md), [Wildberries](docs/wildberries.md), [Яндекс Маркет](docs/yandex-market.md), [настройки окружения](env.example). Синхронизация Яндекс Маркета хранит товары на уровне заказа под ключом yandex-order:{order_number}; разделение на посылки, способ оплаты, получатель и адрес доставки недоступны.

## Настройки

Общие параметры используют префикс MARKETPLACE_: MARKETPLACE_STORE_PATH, MARKETPLACE_TRANSPORT, MARKETPLACE_HOST, MARKETPLACE_PORT, MARKETPLACE_ALLOWED_HOSTS и MARKETPLACE_IDLE_SECONDS. Настройки Ozon остаются с префиксом OZON_, Wildberries и Яндекс Маркета имеют отдельные префиксы. Значения по умолчанию и пояснения указаны в env.example. Старые OZON_ имена общих настроек пока работают и выдают предупреждение об устаревании.

## Разработка

make check-all форматирует и проверяет код, запускает проверку типов и тесты. Версия uv закреплена одинаково в Dockerfile и CI; обновляйте её в обоих местах одновременно.
