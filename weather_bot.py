import os
import re
import sys
import json
import time
import random
import string
import base64
import urllib.parse
from playwright.sync_api import sync_playwright

TARGET_URL = "https://yandex.by/pogoda/ru/bataysk?lat=47.138333&lon=39.744469"
POST_URL = "https://yandex.by/pogoda/ru/bataysk"
COOKIE_STRING = os.environ.get("YANDEX_COOKIE", "")

def parse_cookies(cookie_str: str):
    """Очищает и преобразует строку Cookie для .yandex.by и .yandex.ru."""
    cookie_str = cookie_str.strip()
    if cookie_str.lower().startswith("cookie:"):
        cookie_str = cookie_str[7:].strip()

    cookies = []
    domains = [".yandex.by", ".yandex.ru"]
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, val = item.split("=", 1)
        name, val = name.strip(), val.strip()
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

def decrypt_yandex_scripts(html: str) -> str:
    """Расшифровывает XOR-скрипты Яндекса вида Hg0U(atob(`...`), `key`) из HTML."""
    decoded_chunks = []
    pattern = r'atob\(`([^`]+)`\)\s*,\s*`([^`]+)`'
    for b64_data, key in re.findall(pattern, html):
        try:
            raw_bytes = base64.b64decode(b64_data)
            key_bytes = key.encode("latin1")
            key_len = len(key_bytes)
            xored = bytes(b ^ key_bytes[i % key_len] for i, b in enumerate(raw_bytes))
            unquoted = urllib.parse.unquote(xored.decode("latin1"), encoding="utf-8", errors="replace")
            decoded_chunks.append(unquoted)
        except Exception:
            pass
    return "\n".join(decoded_chunks)

def main():
    if not COOKIE_STRING:
        print("[!] Ошибка: секрет YANDEX_COOKIE пуст.")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            geolocation={"latitude": 47.138333, "longitude": 39.744469},
            permissions=["geolocation"]
        )

        context.add_cookies(parse_cookies(COOKIE_STRING))
        page = context.new_page()

        print(f"[*] Открываем {TARGET_URL}...")
        try:
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(4000)
        except Exception as e:
            print(f"[!] Предупреждение при загрузке: {e}")

        html = page.content()

        # 1. Собираем расшифрованные данные из памяти браузера и из XOR-скриптов HTML
        try:
            next_f_data = page.evaluate("() => JSON.stringify(window.__next_f || [])")
        except Exception:
            next_f_data = ""

        decrypted_text = decrypt_yandex_scripts(html) + "\n" + next_f_data

        is_logged_in = "Nivikin123" in decrypted_text
        print(f"[*] Авторизация (Nivikin123) после расшифровки: {'Да' if is_logged_in else 'Нет'}")

        # 2. Извлекаем свежий CSRF-токен sk (формат: 40 hex-символов : 10 цифр времени)
        sk_match = (
            re.search(r'"sk"\s*:\s*"([a-f0-9]{40}:\d{10})"', decrypted_text)
            or re.search(r'([a-f0-9]{40}:\d{10})', decrypted_text)
        )

        if not sk_match:
            print("[x] Не удалось извлечь свежий токен sk со страницы. Проверьте свежесть куков.")
            browser.close()
            sys.exit(1)

        fresh_sk = sk_match.group(1)
        print(f"[+] Успешно получен свежий токен sk: {fresh_sk}")

        # 3. Считываем реальную текущую температуру и время генерации прогноза со страницы
        temp_val = 20
        temp_el = page.locator(".AppFactTemperature_value__2qhsG").first
        if temp_el.count() > 0:
            try:
                raw_t = temp_el.inner_text().strip().replace("−", "-")
                sign_el = page.locator(".AppFactTemperature_sign__1MeN4").first
                sign = sign_el.inner_text().strip() if sign_el.count() > 0 else ""
                temp_val = int(f"{sign}{raw_t}".replace("+", "").replace("−", "-"))
            except Exception:
                pass

        gen_match = re.search(r"nowcast_gen_time=(\d{10})", html) or re.search(r'"nowcast_gen_time"\s*:\s*(\d{10})', decrypted_text)
        nowcast_gen_time = int(gen_match.group(1)) if gen_match else int(time.time()) - 300

        print(f"[*] Текущая погода в Батайске: {temp_val}°C | nowcast_gen_time: {nowcast_gen_time}")

        # 4. Формируем и отправляем POST-запрос подтверждения прямо из контекста браузера
        rand_suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=11))
        report_id = f"mush{rand_suffix[:5]}.{rand_suffix}"

        vote_payload = [
            {
                "page": "error",
                "routeParams": {
                    "serviceNameRoute": "pogoda",
                    "localeRoute": "ru",
                    "slugRoute": "bataysk"
                },
                "searchParams": {},
                "sk": fresh_sk,
                "temp": temp_val,
                "cloudiness": 2,
                "prec_strength": 0,
                "prec_type": 0,
                "nowcast_gen_time": nowcast_gen_time,
                "lat": 47.138333,
                "lon": 39.744469,
                "precision": 15000,
                "user_prec_type": 0,
                "user_cloudiness": 2,
                "meta": {
                    "reportId": report_id,
                    "reportFrom": "main",
                    "platform": "desktop",
                    "yandexLogin": "Nivikin123"
                },
                "expFlags": "experiments=longterm_meteum,calendar"
            }
        ]

        state_tree = "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22serviceNameRoute%22%2C%22pogoda%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%5B%22localeRoute%22%2C%22ru%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22(geo)%22%2C%7B%22children%22%3A%5B%22(slot)%22%2C%7B%22children%22%3A%5B%22(common)%22%2C%7B%22children%22%3A%5B%5B%22slugRoute%22%2C%22bataysk%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22(main)%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%2C%22promo%22%3A%5B%22(slot)%22%2C%7B%22children%22%3A%5B%5B%22slugRoute%22%2C%22bataysk%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22(main)%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D"

        print("[*] Отправляем подтверждение погоды (Server Action POST)...")
        res1 = page.evaluate(
            """async ({ url, payload, stateTree }) => {
                const r = await fetch(url, {
                    method: "POST",
                    headers: {
                        "Accept": "text/x-component",
                        "Content-Type": "text/plain;charset=UTF-8",
                        "next-action": "409ffe09da184c3bdb7d1846ea6e8785b6adc4b5cf",
                        "next-router-state-tree": stateTree
                    },
                    body: payload
                });
                return { status: r.status, text: await r.text() };
            }""",
            {"url": POST_URL, "payload": json.dumps(vote_payload), "stateTree": state_tree}
        )

        print(f"[+] Шаг 1 (Голос) -> HTTP {res1['status']} | Ответ: {res1['text'][:200]}")

        # 5. Отправляем второй запрос фиксации состояния (afterReport)
        after_payload = [
            {
                "page": "main",
                "routeParams": {
                    "serviceNameRoute": "pogoda",
                    "localeRoute": "ru",
                    "slugRoute": "bataysk"
                },
                "searchParams": {},
                "sk": fresh_sk,
                "afterReport": True,
                "is404": "$undefined"
            }
        ]

        res2 = page.evaluate(
            """async ({ url, payload, stateTree }) => {
                const r = await fetch(url, {
                    method: "POST",
                    headers: {
                        "Accept": "text/x-component",
                        "Content-Type": "text/plain;charset=UTF-8",
                        "next-action": "408888a89051ec551025cd50727ac19fb7c6ed9361",
                        "next-router-state-tree": stateTree
                    },
                    body: payload
                });
                return { status: r.status };
            }""",
            {"url": POST_URL, "payload": json.dumps(after_payload), "stateTree": state_tree}
        )

        print(f"[+] Шаг 2 (AfterReport) -> HTTP {res2['status']}")
        browser.close()

if __name__ == "__main__":
    main()
