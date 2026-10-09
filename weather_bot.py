import os
import sys
from playwright.sync_api import sync_playwright

TARGET_URL = "https://yandex.ru/pogoda/ru/bataysk"

# Cookie берутся из переменной окружения (для GitHub Secrets) или подставляются напрямую
COOKIE_STRING = os.environ.get("YANDEX_COOKIE", "")

def parse_cookies(cookie_str: str, domain: str = ".yandex.ru"):
    """Преобразует стандартную строку cookie браузера в формат для Playwright."""
    cookies = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, val = item.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": val.strip(),
            "domain": domain,
            "path": "/"
        })
    return cookies

def main():
    if not COOKIE_STRING:
        print("[!] Ошибка: строка куков не найдена в переменных окружения.")
        sys.exit(1)

    with sync_playwright() as p:
        # Запуск легковесного Chromium в headless-режиме
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="ru-RU"
        )

        # Подгружаем сессию пользователя
        cookies = parse_cookies(COOKIE_STRING)
        context.add_cookies(cookies)

        page = context.new_page()

        print(f"[*] Открываем {TARGET_URL}...")
        try:
            page.goto(TARGET_URL, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"[!] Предупреждение при загрузке страницы: {e}")

        # Проверка на капчу от Яндекса
        if "showcaptcha" in page.url or page.locator("div.SmartCaptcha").count() > 0:
            print("[x] Яндекс выдал капчу на этом IP. Действие заблокировано.")
            browser.close()
            sys.exit(1)

        # Ищем кнопку подтверждения «Да»
        # В разметке Яндекса это кнопка с data-val="correct" или текстом "Да"
        yes_btn = page.locator('button[data-val="correct"], button:has-text("Да")').first

        if yes_btn.is_visible(timeout=7000):
            print("[+] Опрос найден. Нажимаем «Да»...")
            yes_btn.click()
            page.wait_for_timeout(3000)  # Ждем фиксации отправки на бэкенде
            print("[+] Голос успешно отправлен!")
        else:
            print("[-] Кнопка опроса в данный момент не активна на странице (слот закрыт).")

        browser.close()

if __name__ == "__main__":
    main()