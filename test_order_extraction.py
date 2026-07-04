#!/usr/bin/env python3
"""Test script for order details extraction"""
import re

# Copy the relevant functions from customer_agent.py
GOVERNORATES = [
    "القاهرة",
    "الجيزة",
    "الإسكندرية",
    "الدقهلية",
    "الشرقية",
    "المنوفية",
    "القليوبية",
    "الغربية",
    "البحيرة",
    "السويس",
    "بورسعيد",
    "دمياط",
    "الإسماعيلية",
    "كفر الشيخ",
    "الفيوم",
    "بني سويف",
    "المنيا",
    "أسيوط",
    "سوهاج",
    "قنا",
    "الأقصر",
    "أسوان",
    "البحر الأحمر",
    "الوادي الجديد",
    "مطروح",
    "شمال سيناء",
    "جنوب سيناء",
]

PHONE_PATTERN = re.compile(r"01[0125][0-9]{8}")

ADDRESS_NOISE_WORDS = [
    "تمام",
    "موافق",
    "عايز",
    "قطعتين",
    "قطعة",
    "قطع",
    "اوردر",
    "أستاذ",
    "استاذ",
]


def _normalize_arabic(text: str) -> str:
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return text


def _text_blob(text: str) -> str:
    return _normalize_arabic(text.lower())


def _is_governorate_word(word: str) -> bool:
    normalized = _normalize_arabic(word)
    for gov in GOVERNORATES:
        if _normalize_arabic(gov) == normalized or _normalize_arabic(gov) in normalized:
            return True
    return False


def _extract_governorate(text: str) -> str:
    normalized_text = _normalize_arabic(text)
    for gov in GOVERNORATES:
        gov_normalized = _normalize_arabic(gov)
        # Match both with and without "ال"
        gov_without_al = gov_normalized.replace("ال", "")
        if gov_normalized in normalized_text or gov_without_al in normalized_text:
            return gov.replace("الاسكندرية", "الإسكندرية").replace("القاهره", "القاهرة")
    return ""


def _parse_name_from_text(text: str) -> str:
    patterns = [
        r"اسم[ىي]\s+(.+?)(?:\.|$|،|,|\s+و|\s+عايز)",
        r"(?:أ?ست[اذ]?\s+)([\u0600-\u06FF]+?)(?:،|,|\s+عايز|$|\.)",
        r"(?:انا|أنا)\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)",
        # Pattern for name at start or after "من" before governorate: "محمود احمد من قاهرة..."
        r"^([\u0600-\u06FF]+\s+[\u0600-\u06FF]+)(?:\s+من\s+[\u0600-\u06FF]+)",
        r"من\s+([\u0600-\u06FF]+\s+[\u0600-\u06FF]+)(?:\s+[\u0600-\u06FF]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip(" .،,")
            if name and not _is_governorate_word(name):
                return name
    return ""


def _clean_address_text(text: str, phone: str, governorate: str, name: str = "") -> str:
    address = text
    if phone:
        address = address.replace(phone, " ")
    if governorate:
        address = address.replace(governorate, " ")
        address = address.replace(governorate.replace("الإ", "الا"), " ")
    if name and name != "عميل":
        address = address.replace(name, " ")
    for noise in ADDRESS_NOISE_WORDS:
        address = re.sub(rf"\b{re.escape(noise)}\b", " ", address, flags=re.IGNORECASE)
    address = re.sub(
        r"اسم[ىي]\s+[\u0600-\u06FF\s]+|(?:أ?ست[اذ]?\s+[\u0600-\u06FF\s]+)|(?:عايز\s+قط.+?)|(?:تمام\s+يا\s+.+?)",
        " ",
        address,
        flags=re.IGNORECASE,
    )
    address = re.sub(r"\s+", " ", address).strip(" ,.")
    return address


def _parse_customer_details(text: str) -> tuple[str, str, str, str]:
    phone_match = PHONE_PATTERN.search(text)
    phone = phone_match.group(0) if phone_match else ""
    governorate = _extract_governorate(text)
    name = _parse_name_from_text(text)
    address = _clean_address_text(text, phone, governorate, name)
    if not name:
        name = "عميل"
    return name, phone, governorate, address


# Test with the provided message
test_message = "محمود احمد من قاهرة شارع المعز امام المدرسة 01013544163"
print(f"Test message: {test_message}")
print("-" * 50)

name, phone, governorate, address = _parse_customer_details(test_message)

print(f"Name: {name}")
print(f"Phone: {phone}")
print(f"Governorate: {governorate}")
print(f"Address: {address}")
print("-" * 50)

# Check if all required fields are present
if name and name != "عميل" and phone and governorate and address:
    print("✓ SUCCESS: All fields extracted correctly from single message")
else:
    print("✗ FAILED: Some fields missing")
    if not name or name == "عميل":
        print(f"  - Name missing or default: '{name}'")
    if not phone:
        print(f"  - Phone missing")
    if not governorate:
        print(f"  - Governorate missing")
    if not address:
        print(f"  - Address missing")
