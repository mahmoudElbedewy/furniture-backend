import os
from decouple import config
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

# ── Vision (لقراءة صور المنتجات - أدمن فقط) ──
vision_llm_direct = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=config("GOOGLE_API_KEY", default=""),
    temperature=0,
    max_retries=1,
)
nara_mimo_vision = ChatOpenAI(
    base_url="https://router.naraya.ai/v1",
    api_key=config("NARA_API_KEY", default=""),
    model="mimo-v2.5-free",
    temperature=0,
)
heavy_4_openai_oss = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=config("OPENROUTER_API_KEY", default=""),
    model="google/gemini-2.0-flash-exp:free",
    temperature=0,
)
vision_llm = vision_llm_direct.with_fallbacks([nara_mimo_vision, heavy_4_openai_oss])

# ── Light (استخراج بيانات نصية - أدمن فقط) ──
light_3_groq = ChatGroq(
    api_key=config("GROQ_API_KEY_1", default=""),
    model="llama-3.1-8b-instant",
    temperature=0.2,
    max_retries=1,
)
light_5_llama_or = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=config("OPENROUTER_API_KEY", default=""),
    model="meta-llama/llama-3.3-70b-instruct:free",
    temperature=0,
)
nara_mistral_large = ChatOpenAI(
    base_url="https://router.naraya.ai/v1",
    api_key=config("NARA_API_KEY", default=""),
    model="mistral-large",
    temperature=0,
)
light_llm = light_3_groq.with_fallbacks([light_5_llama_or, nara_mistral_large])

# ── Chat (شخصية البياع - عميل عادي) ──
vision_llm_chat = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=config("GOOGLE_API_KEY", default=""),
    temperature=0.3,
    max_retries=1,
)
nara_mistral_large_chat = ChatOpenAI(
    base_url="https://router.naraya.ai/v1",
    api_key=config("NARA_API_KEY", default=""),
    model="mistral-large",
    temperature=0.3,
)
_groq_chat = ChatGroq(
    api_key=config("GROQ_API_KEY_1", default=""),
    model="llama-3.1-8b-instant",
    temperature=0.3,
    max_retries=1,
)
_groq_chat_alt = ChatGroq(
    api_key=config("GROQ_API_KEY_2", default=config("GROQ_API_KEY_1", default="")),
    model="llama-3.3-70b-versatile",
    temperature=0.3,
    max_retries=1,
)
_openrouter_chat = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=config("OPENROUTER_API_KEY", default=""),
    model="meta-llama/llama-3.3-70b-instruct:free",
    temperature=0.3,
)

# كل نماذج الشات المتاحة — يُجرّبها الـ agent واحدًا تلو الآخر عند الفشل
CHAT_LLMS = [
    vision_llm_chat,
    nara_mistral_large_chat,
    _groq_chat_alt,
    _groq_chat,
    _openrouter_chat,
    nara_mistral_large,
    light_3_groq,
]

simple_chat_llm = vision_llm_chat.with_fallbacks(
    [nara_mistral_large_chat, _groq_chat_alt, _groq_chat, _openrouter_chat]
)
