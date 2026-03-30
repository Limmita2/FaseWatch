"""
Утилита для извлечения и нормализации украинских телефонных номеров из текста.
"""
import re

# Regex для поиска телефонных номеров в разных форматах
# Матчит: +38(067)627-62-25, 380-627-62-25, 0676276225 и игнорирует длинные числа
PHONE_PATTERN = re.compile(
    r'(?<!\d)(?:\+?38)?(?:[\s\-\(]*?)0(?:[\s\-\)]*?)(?:39|50|63|66|67|68|73|91|92|93|94|95|96|97|98|99)(?:[\s\-\)]*?\d){7}(?!\d)',
    re.MULTILINE
)


def normalize_phone(raw: str) -> str | None:
    """
    Приводит строку к формату 380XXXXXXXXX.
    Возвращает None если номер невалиден.
    """
    # Оставляем только цифры
    digits = re.sub(r'\D', '', raw)

    # Убираем лишние лидирующие нули
    if digits.startswith('00380'):
        digits = digits[2:]  # 00380... → 380...
    elif digits.startswith('80') and len(digits) == 11:
        digits = '3' + digits  # 80671234567 → 380671234567
    elif digits.startswith('0') and len(digits) == 10:
        digits = '38' + digits  # 0671234567 → 380671234567

    # Валидация: украинский номер = 12 цифр, начинается с 380
    if len(digits) == 12 and digits.startswith('380'):
        return digits

    return None


def extract_phones(text: str | None) -> list[str]:
    """
    Извлекает и нормализует все украинские номера телефонов из текста.
    Возвращает список уникальных нормализованных номеров.
    """
    if not text:
        return []

    matches = PHONE_PATTERN.findall(text)
    phones = set()
    for raw in matches:
        normalized = normalize_phone(raw)
        if normalized:
            phones.add(normalized)

    return list(phones)
