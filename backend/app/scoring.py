from dataclasses import dataclass

from app.crawler import CrawlResult


@dataclass(frozen=True)
class FactorResult:
    category: str
    weight: float
    points: float
    explanation: str
    evidence_url: str | None


DEFAULT_WEIGHTS = {
    "website_available": 18.0,
    "https": 10.0,
    "contacts": 12.0,
    "company_pages": 10.0,
    "team": 8.0,
    "news": 8.0,
    "vacancies": 5.0,
    "social": 8.0,
    "requisites": 8.0,
    "content_freshness": 5.0,
    "technical_resources": 4.0,
    "identity_consistency": 4.0,
}


def calculate_score(crawl: CrawlResult, company_name: str, inn: str | None) -> list[FactorResult]:
    pages = crawl.pages
    combined = " ".join(page.text.lower() for page in pages)
    urls = " ".join(page.url.lower() for page in pages)
    first_url = pages[0].url if pages else None

    def factor(
        category: str, condition: bool, explanation: str, url: str | None = first_url
    ) -> FactorResult:
        weight = DEFAULT_WEIGHTS[category]
        return FactorResult(
            category, weight, weight if condition else 0.0, explanation, url if condition else None
        )

    has_contacts = any(page.emails or page.phones for page in pages)
    has_team = any(word in combined or word in urls for word in ("команда", "руководство", "team"))
    has_news = any(word in combined or word in urls for word in ("новости", "news", "пресс-центр"))
    has_vacancies = any(
        word in combined or word in urls for word in ("ваканс", "career", "работа у нас")
    )
    has_social = any(
        domain in combined for domain in ("vk.com", "t.me/", "rutube.ru", "youtube.com", "dzen.ru")
    )
    has_requisites = bool(inn and inn in combined) or any(
        word in combined or word in urls for word in ("реквизит", "инн", "ogrn")
    )
    normalized_words = [word for word in company_name.lower().split() if len(word) > 3]
    identity = bool(normalized_words and any(word in combined for word in normalized_words[:3]))
    return [
        factor(
            "website_available", bool(pages and pages[0].status_code < 400), "Сайт отвечает по HTTP"
        ),
        factor(
            "https", bool(first_url and first_url.startswith("https://")), "Сайт использует HTTPS"
        ),
        factor("contacts", has_contacts, "На официальном сайте опубликованы контакты"),
        factor("company_pages", len(pages) > 1, "Доступны дополнительные страницы компании"),
        factor("team", has_team, "Обнаружена информация о команде или руководстве"),
        factor("news", has_news, "Обнаружен новостной раздел"),
        factor("vacancies", has_vacancies, "Обнаружена информация о вакансиях"),
        factor("social", has_social, "Обнаружены официальные социальные площадки"),
        factor("requisites", has_requisites, "Реквизиты подтверждаются содержимым сайта"),
        factor("content_freshness", False, "Свежесть контента не подтверждена надёжной датой"),
        factor("technical_resources", "github.com" in combined, "Обнаружены технические ресурсы"),
        factor("identity_consistency", identity, "Название организации согласуется с сайтом"),
    ]
