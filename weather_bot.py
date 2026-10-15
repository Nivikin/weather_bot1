import os
import sys
from playwright.sync_api import sync_playwright

# Точная ссылка с координатами парка им. Ленина (Батайск)
TARGET_URL = "https://yandex.ru/pogoda/ru/bataysk?lat=47.138333&lon=39.744469"
COOKIE_STRING = os.environ.get("YANDEX_COOKIE", "")

def parse_cookies(cookie_str: str):
    """Записывает куки сразу для .yandex.ru и .yandex.by на случай редиректов."""
    cookies = []
    domains = [".yandex.ru", ".yandex.by"]
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, val = item.split("=", 1)
        for d in domains:
            cookies.append({
                "name": name.strip(),
                "value": val.strip(),
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
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:157.0) Gecko/20100101 Firefox/157.0",
            viewport={"width": 1280, "height": 800},
            locale="ru-RU",
            timezone_id="Europe/Moscow"
        )

        context.add_cookies(parse_cookies(COOKIE_STRING))
        page = context.new_page()

        # Блокируем тяжелую рекламу и метрику, чтобы страница грузилась за 3–5 секунд
        page.route("**/*{mc.yandex,adfox,an.yandex,avatars.mds}*", lambda route: route.abort())

        print(f"[*] Открываем {TARGET_URL}...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)

        # Проверка на капчу
        if "showcaptcha" in page.url or page.locator("div.SmartCaptcha").count() > 0:
            print("[x] Яндекс выдал капчу для текущего IP GitHub.")
            browser.close()
            sys.exit(0)

        # Ждем, пока кнопка «Да» появится И станет активной (сниется атрибут disabled после гидратации)
        active_yes_btn = page.locator('button[data-val="correct"]:not([disabled])').first

        try:
            active_yes_btn.wait_for(state="visible", timeout=15000)
            print("[+] Активная кнопка «Да» найдена! Нажимаем и ждем ответа сервера...")

            # Перехватываем POST-запрос подтверждения, чтобы убедиться в доставке
            with page.expect_response(
                lambda res: res.request.method == "POST" and "pogoda" in res.url,
                timeout=10000
            ) as response_info:
                active_yes_btn.click()

            resp = response_info.value
            body = resp.text()
            print(f"[+] Ответ сервера (HTTP {resp.status}): {body[:150]}")

        except Exception:
            print("[-] Кнопка опроса сейчас не активна (либо ответ в этом окне уже учтен).")

        browser.close()

if __name__ == "__main__":
    main()
