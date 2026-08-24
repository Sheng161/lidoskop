from app.crawler import CrawledPage, CrawlResult
from app.scoring import calculate_score


def test_empty_crawl_scores_zero() -> None:
    factors = calculate_score(CrawlResult([], [], []), "ООО Ромашка", "1650000000")
    assert sum(item.points for item in factors) == 0
    assert all(item.evidence_url is None for item in factors)


def test_confirmed_site_facts_are_explainable() -> None:
    page = CrawledPage(
        url="https://romashka.ru/contacts",
        title="ООО Ромашка — контакты",
        text="ООО Ромашка ИНН 1650000000 контакты info@romashka.ru новости команда vk.com/romashka",
        status_code=200,
        content_hash="abc",
        emails=["info@romashka.ru"],
    )
    factors = calculate_score(CrawlResult([page], [], []), "ООО Ромашка", "1650000000")
    indexed = {item.category: item for item in factors}
    assert indexed["website_available"].points > 0
    assert indexed["https"].points > 0
    assert indexed["contacts"].evidence_url == page.url
    assert indexed["content_freshness"].points == 0
