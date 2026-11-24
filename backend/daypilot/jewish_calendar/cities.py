"""
רשימת ערים ראשונית.

קואורדינטות בקירוב (מספיק לדיוק של דקה בזמני שקיעה).
דקות הדלקת נרות לפני השקיעה לפי המנהג הנפוץ בעיר. אפשר לשנות לכל משתמשת בהגדרות.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CityInfo:
    key: str
    name_he: str
    name_en: str
    latitude: float
    longitude: float
    altitude: int
    candle_offset_minutes: int


CITIES: list[CityInfo] = [
    CityInfo("jerusalem", "ירושלים", "Jerusalem", 31.7780, 35.2354, 754, 40),
    CityInfo("bnei_brak", "בני ברק", "Bnei Brak", 32.0807, 34.8338, 30, 20),
    CityInfo("tel_aviv", "תל אביב", "Tel Aviv", 32.0853, 34.7818, 5, 20),
    CityInfo("petah_tikva", "פתח תקווה", "Petah Tikva", 32.0871, 34.8875, 54, 20),
    CityInfo("haifa", "חיפה", "Haifa", 32.7940, 34.9896, 50, 30),
    CityInfo("beer_sheva", "באר שבע", "Beersheba", 31.2518, 34.7913, 260, 20),
    CityInfo("ashdod", "אשדוד", "Ashdod", 31.8014, 34.6435, 20, 20),
    CityInfo("beit_shemesh", "בית שמש", "Beit Shemesh", 31.7470, 34.9881, 300, 20),
    CityInfo("modiin_illit", "מודיעין עילית", "Modiin Illit", 31.9334, 35.0410, 320, 20),
    CityInfo("beitar_illit", "ביתר עילית", "Beitar Illit", 31.6979, 35.1153, 740, 20),
    CityInfo("elad", "אלעד", "Elad", 32.0522, 34.9510, 150, 20),
    CityInfo("netanya", "נתניה", "Netanya", 32.3215, 34.8532, 30, 20),
    CityInfo("rehovot", "רחובות", "Rehovot", 31.8928, 34.8113, 50, 20),
    CityInfo("safed", "צפת", "Safed", 32.9646, 35.4960, 900, 20),
    CityInfo("tiberias", "טבריה", "Tiberias", 32.7922, 35.5312, -200, 20),
]

DEFAULT_CITY_KEY = "jerusalem"


def city_by_key(key: str) -> CityInfo:
    for city in CITIES:
        if city.key == key:
            return city
    raise KeyError(key)
