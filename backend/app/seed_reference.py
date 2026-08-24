import asyncio

from sqlalchemy.dialects.postgresql import insert

from app.db import SessionFactory
from app.models import AppSetting

FEDERAL_DISTRICTS: dict[str, list[dict[str, str]]] = {
    "Центральный": [
        {"region": "Москва", "capital": "Москва"},
        {"region": "Московская область", "capital": "Москва"},
        {"region": "Белгородская область", "capital": "Белгород"},
        {"region": "Брянская область", "capital": "Брянск"},
        {"region": "Владимирская область", "capital": "Владимир"},
        {"region": "Воронежская область", "capital": "Воронеж"},
        {"region": "Ивановская область", "capital": "Иваново"},
        {"region": "Калужская область", "capital": "Калуга"},
        {"region": "Костромская область", "capital": "Кострома"},
        {"region": "Курская область", "capital": "Курск"},
        {"region": "Липецкая область", "capital": "Липецк"},
        {"region": "Орловская область", "capital": "Орёл"},
        {"region": "Рязанская область", "capital": "Рязань"},
        {"region": "Смоленская область", "capital": "Смоленск"},
        {"region": "Тамбовская область", "capital": "Тамбов"},
        {"region": "Тверская область", "capital": "Тверь"},
        {"region": "Тульская область", "capital": "Тула"},
        {"region": "Ярославская область", "capital": "Ярославль"},
    ],
    "Северо-Западный": [
        {"region": "Санкт-Петербург", "capital": "Санкт-Петербург"},
        {"region": "Ленинградская область", "capital": "Гатчина"},
        {"region": "Республика Карелия", "capital": "Петрозаводск"},
        {"region": "Республика Коми", "capital": "Сыктывкар"},
        {"region": "Архангельская область", "capital": "Архангельск"},
        {"region": "Вологодская область", "capital": "Вологда"},
        {"region": "Калининградская область", "capital": "Калининград"},
        {"region": "Мурманская область", "capital": "Мурманск"},
        {"region": "Новгородская область", "capital": "Великий Новгород"},
        {"region": "Псковская область", "capital": "Псков"},
        {"region": "Ненецкий автономный округ", "capital": "Нарьян-Мар"},
    ],
    "Южный": [
        {"region": "Республика Адыгея", "capital": "Майкоп"},
        {"region": "Республика Калмыкия", "capital": "Элиста"},
        {"region": "Республика Крым", "capital": "Симферополь"},
        {"region": "Краснодарский край", "capital": "Краснодар"},
        {"region": "Астраханская область", "capital": "Астрахань"},
        {"region": "Волгоградская область", "capital": "Волгоград"},
        {"region": "Ростовская область", "capital": "Ростов-на-Дону"},
        {"region": "Севастополь", "capital": "Севастополь"},
    ],
    "Северо-Кавказский": [
        {"region": "Республика Дагестан", "capital": "Махачкала"},
        {"region": "Республика Ингушетия", "capital": "Магас"},
        {"region": "Кабардино-Балкарская Республика", "capital": "Нальчик"},
        {"region": "Карачаево-Черкесская Республика", "capital": "Черкесск"},
        {"region": "Республика Северная Осетия — Алания", "capital": "Владикавказ"},
        {"region": "Чеченская Республика", "capital": "Грозный"},
        {"region": "Ставропольский край", "capital": "Ставрополь"},
    ],
    "Приволжский": [
        {"region": "Республика Башкортостан", "capital": "Уфа"},
        {"region": "Республика Марий Эл", "capital": "Йошкар-Ола"},
        {"region": "Республика Мордовия", "capital": "Саранск"},
        {"region": "Республика Татарстан", "capital": "Казань"},
        {"region": "Удмуртская Республика", "capital": "Ижевск"},
        {"region": "Чувашская Республика", "capital": "Чебоксары"},
        {"region": "Пермский край", "capital": "Пермь"},
        {"region": "Кировская область", "capital": "Киров"},
        {"region": "Нижегородская область", "capital": "Нижний Новгород"},
        {"region": "Оренбургская область", "capital": "Оренбург"},
        {"region": "Пензенская область", "capital": "Пенза"},
        {"region": "Самарская область", "capital": "Самара"},
        {"region": "Саратовская область", "capital": "Саратов"},
        {"region": "Ульяновская область", "capital": "Ульяновск"},
    ],
    "Уральский": [
        {"region": "Курганская область", "capital": "Курган"},
        {"region": "Свердловская область", "capital": "Екатеринбург"},
        {"region": "Тюменская область", "capital": "Тюмень"},
        {"region": "Челябинская область", "capital": "Челябинск"},
        {"region": "Ханты-Мансийский автономный округ — Югра", "capital": "Ханты-Мансийск"},
        {"region": "Ямало-Ненецкий автономный округ", "capital": "Салехард"},
    ],
    "Сибирский": [
        {"region": "Республика Алтай", "capital": "Горно-Алтайск"},
        {"region": "Республика Тыва", "capital": "Кызыл"},
        {"region": "Республика Хакасия", "capital": "Абакан"},
        {"region": "Алтайский край", "capital": "Барнаул"},
        {"region": "Красноярский край", "capital": "Красноярск"},
        {"region": "Иркутская область", "capital": "Иркутск"},
        {"region": "Кемеровская область — Кузбасс", "capital": "Кемерово"},
        {"region": "Новосибирская область", "capital": "Новосибирск"},
        {"region": "Омская область", "capital": "Омск"},
        {"region": "Томская область", "capital": "Томск"},
    ],
    "Дальневосточный": [
        {"region": "Республика Бурятия", "capital": "Улан-Удэ"},
        {"region": "Республика Саха (Якутия)", "capital": "Якутск"},
        {"region": "Забайкальский край", "capital": "Чита"},
        {"region": "Камчатский край", "capital": "Петропавловск-Камчатский"},
        {"region": "Приморский край", "capital": "Владивосток"},
        {"region": "Хабаровский край", "capital": "Хабаровск"},
        {"region": "Амурская область", "capital": "Благовещенск"},
        {"region": "Магаданская область", "capital": "Магадан"},
        {"region": "Сахалинская область", "capital": "Южно-Сахалинск"},
        {"region": "Еврейская автономная область", "capital": "Биробиджан"},
        {"region": "Чукотский автономный округ", "capital": "Анадырь"},
    ],
}


async def seed() -> None:
    async with SessionFactory() as session:
        statement = insert(AppSetting).values(
            key="geography_reference", public_value={"federal_districts": FEDERAL_DISTRICTS}
        )
        statement = statement.on_conflict_do_update(
            index_elements=[AppSetting.key],
            set_={"public_value": statement.excluded.public_value},
        )
        await session.execute(statement)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
