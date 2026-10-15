import os
import sys
from playwright.sync_api import sync_playwright

# Используем именно yandex.by, откуда скопированы куки и HTML
TARGET_URL = "https://yandex.by/pogoda/ru/bataysk?lat=47.138333&lon=39.744469"
COOKIE_STRING = os.environ.get("YANDEX_COOKIE", "")

def parse_cookies(cookie_str: str):
    """Записывает куки для .yandex.by и .yandex.ru."""
    cookies = []
    domains = [".yandex.by", ".yandex.ru"]
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, val = item.split("=", 1)
        name = name.strip()
        val = val.strip()
        if not name:
            continue
        for d in domains:
            cookies.append({
                "name": name,
                "value": val,
                "domain": d,
                "path": "/"
            })
    return cookies

def main():
    if not COOKIE_STRING:
        print("[!] Ошибка: секрет YANDEX_COOKIE пуст.")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )

        # Используем родной User-Agent от Chrome (под движок Chromium) и передаем геолокацию Батайска
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            geolocation={"latitude": 47.138333, "longitude": 39.744469},
            permissions=["geolocation"]
        )

        # Скрываем флаг автоматизации webdriver
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        context.add_cookies(parse_cookies(COOKIE_STRING))
        page = context.new_page()

        print(f"[*] Открываем {TARGET_URL}...")
        try:
            page.goto(TARGET_URL, wait_until="load", timeout=40000)
        except Exception as e:
            print(f"[!] Предупреждение при загрузке: {e}")

        # Даем 5 секунд на выполнение зашифрованных скриптов _cry и гидратацию React
        page.wait_for_timeout(5000)

        # Диагностика того, что реально открылось на сервере GitHub
        current_url = page.url
        title = page.title()
        html = page.content()

        print(f"[*] Фактический URL: {current_url}")
        print(f"[*] Заголовок страницы: {title}")
        print(f"[*] Аккаунт распознан (Nivikin123): {'Да' if 'Nivikin123' in html else 'Нет'}")

        # Проверка на капчу
        if "showcaptcha" in current_url or "Ой!" in title or "робот" in html.lower():
            print("[x] Яндекс выдал капчу (SmartCaptcha) для IP-адреса сервера GitHub.")
            browser.close()
            sys.exit(0)

        # Проверяем наличие кнопки в HTML вообще (даже если она disabled)
        all_yes_btns = page.locator('button[data-val="correct"]')
        btn_count = all_yes_btns.count()
        print(f"[*] Найдено кнопок «Да» в коде страницы: {btn_count}")

        if btn_count == 0:
            print("[-] Кнопки опроса нет в разметке страницы.")
            browser.close()
            sys.exit(0)

        # Ждем, пока скрипт Яндекса снимет атрибут disabled (гидратация)
        active_yes_btn = page.locator('button[data-val="correct"]:not([disabled])').first

        try:
            active_yes_btn.wait_for(state="visible", timeout=20000)
            print("[+] Кнопка «Да» активна! Нажимаем...")

            with page.expect_response(
                lambda res: res.request.method == "POST" and "pogoda" in res.url,
                timeout=15000
            ) as response_info:
                active_yes_btn.click()

            resp = response_info.value
            print(f"[+] УСПЕХ! Ответ сервера (HTTP {resp.status}): {resp.text()[:150]}")

        except Exception as e:
            print(f"[!] Кнопка осталась заблокированной или не сработал клик: {e}")
            # Принудительно снимаем disabled и кликаем через JS на случай задержки гидратации
            print("[*] Пробуем принудительный клик...")
            try:
                all_yes_btns.first.evaluate("btn => { btn.removeAttribute('disabled'); btn.click(); }")
                page.wait_for_timeout(4000)
                print("[*] Принудительный клик выполнен.")
            except Exception as e2:
                print(f"[x] Ошибка принудительного клика: {e2}")

        browser.close()

if __name__ == "__main__":
    main()
