import json
import re
import logging
import signal
from datetime import datetime
from playwright.sync_api import sync_playwright, Page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()],
)

class TwitterScraper:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

        # Чтобы не дублировать твиты при прокрутке
        self.processed_tweets = set()

        # Корректное завершение при Ctrl+C
        self.should_exit = False
        signal.signal(signal.SIGINT, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        logging.info("\nПолучен сигнал прерывания. Завершаем работу...")
        self.should_exit = True

    def connect_to_browser(self) -> bool:
        """
        Подключаемся к существующему Chromium по CDP (localhost:9222).
        Убедитесь, что запустили браузер с --remote-debugging-port=9222.
        """
        try:
            playwright = sync_playwright().start()
            self.browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
            if not self.browser.contexts:
                raise RuntimeError("Не найдено открытых контекстов браузера")

            self.context = self.browser.contexts[0]
            if not self.context.pages:
                raise RuntimeError("Нет открытых страниц в контексте")

            self.page = self.context.pages[-1]
            logging.info(f"Успешное подключение к странице: {self.page.url}")
            return True
        except Exception as e:
            logging.error(f"Ошибка подключения к браузеру: {e}")
            return False

    @staticmethod
    def safe_get_text(selector: str, container, default: str = "0") -> str:
        """
        Безопасное получение текста по селектору. Если элемент не найден, возвращаем default.
        """
        try:
            el = container.query_selector(selector)
            return el.inner_text().strip() if el else default
        except Exception as e:
            logging.warning(f"safe_get_text({selector}): {e}")
            return default

    @staticmethod
    def handle_suffix(text: str) -> int:
        """
        Преобразование "12.3K" -> 12300, "1.2M" -> 1200000, и т.п.
        Если ничего не совпало, пробуем int(text).
        """
        text_clean = text.replace(",", "").strip()
        suffix_map = {"K": 1e3, "M": 1e6, "B": 1e9}

        match = re.search(r"([\d.]+)\s*([KMB])?", text_clean, re.IGNORECASE)
        if match:
            num = float(match.group(1))
            suffix = (match.group(2) or "").upper()
            multiplier = suffix_map.get(suffix, 1)
            return int(num * multiplier)
        else:
            try:
                return int(text_clean)
            except ValueError:
                return 0

    def wait_for_element(self, selector: str, timeout: int = 5000) -> bool:
        """
        Ожидание появления элемента на странице
        """
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception as e:
            logging.warning(f"Не дождались элемента: {selector} - {e}")
            return False

    def parse_followers_and_tweets(self) -> dict:
        """
        Сбор общего количества подписчиков (followers) и твитов (posts).
        """
        data = {"Подписчики": 0, "Количество твитов": 0}
        try:
            # Подписчики - примерный селектор
            followers_sel = "a[href$='/verified_followers'] span.css-1jxf684"
            if self.wait_for_element(followers_sel):
                f_text = self.safe_get_text(followers_sel, self.page, default="0")
                data["Подписчики"] = self.handle_suffix(f_text)

            # Количество твитов - примерный селектор (может меняться)
            tweets_sel = "xpath=//div[@dir='ltr' and contains(., 'posts')]"
            if self.wait_for_element(tweets_sel, timeout=10000):
                t_text = self.safe_get_text(tweets_sel, self.page, default="0")
                match = re.search(r"([\d.,]+)\s*posts", t_text, re.IGNORECASE)
                if match:
                    data["Количество твитов"] = self.handle_suffix(match.group(1))
                else:
                    logging.warning(f"Не удалось извлечь кол-во твитов из: {t_text}")

        except Exception as e:
            logging.error(f"Ошибка парсинга подписчиков/твитов: {e}")

        return data

    def parse_engagement(self, tweet) -> dict:
        """
        Собираем метрики:
        {
            "Reply": 0,
            "Repost": 0,
            "Like": 0,
            "Views": 0
        }

        1) Смотрим aria-label (div[role='group'][aria-label]).
           Убираем точки, запятые, приводим к lower().
           Пытаемся найти пары (число, слово).
        2) reply|comment -> Reply
           retweet|repost -> Repost
           like -> Like
           view -> Views
        3) Если Views до сих пор 0, смотрим a[aria-label*='views'].
        4) Если Reply = 0, дополнительно читаем кнопку data-testid='reply'.
        5) Если после всего все 0, делаем рекурсивный вызов.
        """
        result = {"Reply": 0, "Repost": 0, "Like": 0, "Views": 0}
        try:
            self.wait_for_element("div[role='group'][aria-label]", timeout=5000)

            # 1) Читаем aria-label
            engagement_block = tweet.query_selector("div[role='group'][aria-label]")
            if engagement_block:
                aria_text = engagement_block.get_attribute("aria-label") or ""
                aria_clean = aria_text.replace(".", "").replace(",", "").lower()

                pattern = re.compile(r"(\d+)\s+(\w+)")
                matches = pattern.findall(aria_clean)

                for c_str, w in matches:
                    c_val = int(c_str)
                    if "reply" in w or "comment" in w:
                        result["Reply"] = c_val
                    elif "retweet" in w or "repost" in w:
                        result["Repost"] = c_val
                    elif "like" in w:
                        result["Like"] = c_val
                    elif "view" in w:
                        result["Views"] = c_val

            # 2) Если Views всё ещё 0, смотрим отдельно
            if result["Views"] == 0:
                views_text = self.safe_get_text("a[aria-label*='views']", tweet, default="0")
                result["Views"] = self.handle_suffix(views_text)

            # 3) Дополнительная проверка для Reply через кнопку data-testid='reply'
            #    Если в aria-label Reply не нашлось
            if result["Reply"] == 0:
                r_btn_text = self.safe_get_text("div[data-testid='reply'] span", tweet, default="0")
                r_val = self.handle_suffix(r_btn_text)
                if r_val > 0:
                    result["Reply"] = r_val

            # 4) Если всё осталось по нулям, пробуем рекурсию (как в "первом" скрипте)
            if sum(result.values()) == 0:
                logging.warning("Метрики по нулям, пробуем повторно parse_engagement.")
                return self.parse_engagement(tweet)

        except Exception as e:
            logging.error(f"Ошибка извлечения метрик: {e}")

        return result

    def get_tweet_type(self, tweet) -> str:
        """
        Определяем тип поста: Оригинальный, Ретвит, Цитирование, Рекламный пост.
        """
        retweet_check = tweet.query_selector("div[data-testid='socialContext']:has-text('Reposted')")
        if retweet_check:
            return "Ретвит"

        quote_check = tweet.query_selector("div[data-testid='quoteTweet']")
        if quote_check:
            return "Цитирование"

        promoted_check = tweet.query_selector("div[data-testid='placementTracking']")
        if promoted_check:
            return "Рекламный пост"

        return "Оригинальный пост"

    def parse_tweet(self, tweet) -> dict:
        """
        Парсинг одного твита:
        {
            "id": "...",
            "Тип поста": "...",
            "Текст": "...",
            "Дата": "...",
            "Взаимодействия": { "Reply", "Repost", "Like", "Views" }
        }
        """
        try:
            # ID твита или hash HTML
            tweet_id = tweet.get_attribute("data-tweet-id") or str(hash(tweet.inner_html()))
            
            text_el = tweet.query_selector("div[data-testid='tweetText']")
            tweet_text = text_el.inner_text() if text_el else "Не указано"

            time_el = tweet.query_selector("time")
            tweet_date = time_el.get_attribute("datetime") if time_el else "Не указано"

            tweet_type = self.get_tweet_type(tweet)
            engagement = self.parse_engagement(tweet)

            return {
                "id": tweet_id,
                "Тип поста": tweet_type,
                "Текст": tweet_text,
                "Дата": tweet_date,
                "Взаимодействия": engagement
            }

        except Exception as e:
            logging.error(f"Ошибка парсинга твита: {e}")
            return {}

    def get_tweet_elements(self) -> list:
        """
        Возвращает список article-элементов с твитами
        """
        return self.page.query_selector_all("article[data-testid='tweet']")

    def load_and_parse_tweets(self) -> list:
        """
        Прокручивает ленту, пока появляются новые твиты,
        или останавливается, если новых твитов нет / Ctrl+C.
        """
        all_tweets = []
        scroll_step = 800
        scroll_delay = 2000

        try:
            while not self.should_exit:
                before = self.get_tweet_elements()

                self.page.evaluate(f"window.scrollBy(0, {scroll_step})")
                self.page.wait_for_timeout(scroll_delay)

                after = self.get_tweet_elements()
                new_ones = [t for t in after if t not in before]

                for tw in new_ones:
                    t_data = self.parse_tweet(tw)
                    if t_data.get("id") and t_data["id"] not in self.processed_tweets:
                        all_tweets.append(t_data)
                        self.processed_tweets.add(t_data["id"])
                        logging.info(f"Добавлен твит ID: {t_data['id']}")

                if not new_ones:
                    logging.info("Новых твитов не появилось. Остановка прокрутки.")
                    break

        except Exception as e:
            logging.error(f"Ошибка при прокрутке/парсинге: {e}")

        return all_tweets

    def scrape_profile(self) -> dict:
        """
        Основная функция:
        1) Подключиться к браузеру
        2) Собрать метрики профиля (подписчики, твиты)
        3) Прокрутить ленту, собрать все твиты
        4) Сохранить результат в JSON
        """
        if not self.connect_to_browser():
            return {}

        profile_info = {
            "Имя аккаунта": "Не указано",
            "Хендл": "Не указано",
            "Подписчики": 0,
            "Количество твитов": 0,
            "Посты": []
        }
        try:
            # Имя (либо title вкладки)
            user_name = self.safe_get_text("div[data-testid='UserName'] span", self.page, default="Не указано")
            if user_name == "Не указано":
                user_name = self.page.title() or "Не указано"
            profile_info["Имя аккаунта"] = user_name

            # Хендл из URL
            if self.page.url:
                h = self.page.url.rstrip("/").split("/")[-1]
                profile_info["Хендл"] = "@" + h

            # Парсим подписчиков, твиты
            profile_info.update(self.parse_followers_and_tweets())

            # Проверяем, есть ли хоть один твит
            if not self.wait_for_element("article[data-testid='tweet']", timeout=10000):
                logging.error("Не найдено твитов на странице.")
            else:
                tweets_list = self.load_and_parse_tweets()
                profile_info["Посты"].extend(tweets_list)

            # Сохранение в JSON
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"twitter_data_{stamp}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(profile_info, f, ensure_ascii=False, indent=4)

            logging.info(f"Сохранено {len(profile_info['Посты'])} твитов в {filename}")
            return profile_info

        except Exception as e:
            logging.error(f"Критическая ошибка при сборе: {e}")
            return {}
        finally:
            if self.browser:
                self.browser.close()

if __name__ == "__main__":
    scraper = TwitterScraper()
    data = scraper.scrape_profile()
    logging.info("Сбор данных завершён.")
