
import time
import re
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# =====================================
# НАСТРОЙКИ
# =====================================

TOKEN = "6116556985:AAHme10EwOumFSKDkGFzq2WIk-86iNX4BIQ"
CHAT_ID = "507290424"

URL = "https://scanbet.io/pinnacle/drops/football?comparison=open&sort=asc"

THRESHOLD = 1.25
CHECK_INTERVAL = 600

sent = set()

# Все собранные строки
all_matches = {}

# =====================================
# TELEGRAM
# =====================================

session = requests.Session()


def send(msg):

    try:

        response = session.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": msg
            },
            timeout=15
        )

        result = response.json()

        if result.get("ok"):
            print("✅ Telegram отправлен!")
            return True

        print("❌ Telegram error:", result)
        return False

    except Exception as e:

        print("❌ Telegram error:", e)
        return False


# =====================================
# CHROME
# =====================================

options = webdriver.ChromeOptions()

options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)


# =====================================
# ПОЛУЧЕНИЕ ВИДИМЫХ СТРОК
# =====================================

def get_visible_rows():

    script = """
    const table = document.querySelector('table.drops-table');

    if (!table) return [];

    return Array.from(
        table.querySelectorAll('tbody tr[role="row"]')
    ).map(row => {

        const timeCell = row.querySelector(
            'td.mat-column-eventTime'
        );

        const eventCell = row.querySelector(
            'td.mat-column-eventInfo'
        );

        const totalCell = row.querySelector(
            'td.mat-column-T'
        );

        if (!timeCell || !eventCell || !totalCell) {
            return null;
        }

        return {
            time: timeCell.innerText.trim(),
            event: eventCell.innerText.trim(),
            total: totalCell.innerText.trim()
        };

    }).filter(row => row !== null);
    """

    return driver.execute_script(script)


# =====================================
# СОХРАНЕНИЕ СТРОК
# =====================================

def save_rows(rows):

    added = 0

    for row in rows:

        key = (
            row["time"] + "|" +
            row["event"]
        )

        if key not in all_matches:
            added += 1

        all_matches[key] = row

    return added


# =====================================
# SHOW MORE
# =====================================

def show_all_rows():

    print("\n🔄 ЗАГРУЗКА SHOW MORE")

    clicks = 0

    while True:

        try:

            buttons = driver.find_elements(
                By.CSS_SELECTOR,
                "button.show-more-btn"
            )

            if not buttons:
                print("✅ Show More закончился")
                break

            button = buttons[0]

            if not button.is_displayed() or not button.is_enabled():
                print("⚠️ Show More недоступен")
                break

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                button
            )

            before = get_visible_rows()
            save_rows(before)

            driver.execute_script(
                "arguments[0].click();",
                button
            )

            clicks += 1

            print(f"🖱 Show More №{clicks}")

            time.sleep(2)

            after = get_visible_rows()

            added = save_rows(after)

            print(
                f"📊 Видимых строк: {len(after)} | "
                f"Всего уникальных собрано: {len(all_matches)}"
            )

            if clicks > 100:
                print("⚠️ Защитный лимит нажатий")
                break

        except Exception as e:

            print("SHOW MORE ERROR:", e)
            break

    # Финальный сбор
    save_rows(get_visible_rows())

    print("\n✅ ЗАГРУЗКА ЗАВЕРШЕНА")
    print("🖱 Нажатий:", clicks)
    print("📊 Собрано записей:", len(all_matches))


# =====================================
# ПРОКРУТКА ТАБЛИЦЫ
# =====================================

def collect_all_rows():

    print("\n🔍 СОБИРАЕМ ВСЕ СТРОКИ")

    # Находим прокручиваемые контейнеры
    containers = driver.execute_script("""
        return Array.from(document.querySelectorAll('*'))
            .filter(el =>
                el.scrollHeight > el.clientHeight + 50 &&
                el.clientHeight > 100
            )
            .sort((a,b) =>
                b.scrollHeight - b.clientHeight -
                (a.scrollHeight - a.clientHeight)
            )
            .slice(0, 10);
    """)

    if not containers:

        save_rows(get_visible_rows())

        print("⚠️ Отдельный контейнер прокрутки не найден")

        return

    for index in range(len(containers)):

        try:

            # Сохраняем текущие строки
            save_rows(get_visible_rows())

            driver.execute_script("""
                arguments[0].scrollTop = 0;
            """, containers[index])

            time.sleep(0.5)

            previous_count = -1
            stable = 0

            while stable < 3:

                save_rows(get_visible_rows())

                current_count = len(all_matches)

                if current_count == previous_count:
                    stable += 1
                else:
                    stable = 0

                previous_count = current_count

                driver.execute_script("""
                    arguments[0].scrollTop +=
                    Math.max(200, arguments[0].clientHeight * 0.7);
                """, containers[index])

                time.sleep(0.4)

            save_rows(get_visible_rows())

        except Exception as e:

            print("SCROLL ERROR:", e)

    print(
        f"✅ Собрано уникальных записей: {len(all_matches)}"
    )


# =====================================
# ПАРСИНГ ТОТАЛА
# =====================================

def parse_total(value):

    numbers = re.findall(
        r'[-+]?\d+(?:[.,]\d+)?',
        value
    )

    if len(numbers) < 2:
        return None

    return (
        float(numbers[0].replace(",", ".")),
        float(numbers[1].replace(",", "."))
    )


# =====================================
# ОБРАБОТКА СИГНАЛОВ
# =====================================

def process_matches():

    signals = 0

    for row in list(all_matches.values()):

        try:

            parsed = parse_total(row["total"])

            if parsed is None:
                continue

            old_t, new_t = parsed

            diff = round(abs(old_t - new_t), 2)

            if diff < THRESHOLD:
                continue

            event_lines = [
                x.strip()
                for x in row["event"].splitlines()
                if x.strip()
            ]

            match = (
                event_lines[0]
                if event_lines else "Unknown"
            )

            league = (
                event_lines[1]
                if len(event_lines) > 1 else ""
            )

            key = (
                row["time"] + "|" +
                match + "|" +
                str(old_t) + "|" +
                str(new_t)
            )

            if key in sent:
                continue

            msg = (
                "🚨 PINNACLE TOTAL MOVE\n\n"
                f'🕒 {row["time"]}\n'
                f"🏆 {league}\n"
                f"⚽ {match}\n"
                f"📊 T: {old_t} → {new_t}\n"
                f"📈 Move: {diff}"
            )

            print(
                f"🎯 {match}: "
                f"{old_t} → {new_t} ({diff})"
            )

            if send(msg):
                sent.add(key)
                signals += 1

        except Exception as e:

            print("ROW ERROR:", e)

    print(f"🔔 Новых сигналов: {signals}")


# =====================================
# ЗАПУСК
# =====================================

try:

    print("🚀 ЗАПУСК СКАНЕРА...")
    print("🌐 Opening site...")

    driver.get(URL)

    WebDriverWait(driver, 40).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "table.drops-table")
        )
    )

    WebDriverWait(driver, 40).until(
        lambda d: len(get_visible_rows()) > 0
    )

    print("✅ Таблица найдена")

    # Загружаем дополнительные матчи
    show_all_rows()

    # Собираем строки прокруткой
    collect_all_rows()

    # Приветствие
    send(
        "🚀 PINNACLE SCANNER ЗАПУЩЕН!\n\n"
        "✅ ScanBet подключен\n"
        "✅ Show More обработан\n"
        f"📊 Собрано записей: {len(all_matches)}\n"
        f"📈 Порог: {THRESHOLD}\n"
        f"⏱ Проверка: {CHECK_INTERVAL} сек.\n"
        "🔔 Мониторинг активен!"
    )

    print("\n🚀 SCANNER STARTED!")

    # =================================
    # МОНИТОРИНГ
    # =================================

    while True:

        try:

            # Повторно собираем все доступные строки
            collect_all_rows()

            print(
                f"\n📊 Всего матчей в памяти: "
                f"{len(all_matches)}"
            )

            process_matches()

        except Exception as e:

            print("❌ LOOP ERROR:", e)

        time.sleep(CHECK_INTERVAL)

except KeyboardInterrupt:

    print("\n🛑 Сканер остановлен")

except Exception as e:

    print("❌ CRITICAL ERROR:", e)

finally:

    driver.quit()
    session.close()
