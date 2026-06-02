"""
HoW News Chatbot — RAG mbi GovItemPage + NewsArticlePage.

Perdor Wagtail search per retrieval dhe Groq (LLaMA) per pergjigje.
Kosto: ZERO — Groq ka tier falas me 14,400 kerkesa/dite.
Regjistrohu ne: https://console.groq.com (falas, pa karte krediti)
"""
import os
import re

from government.models import GovItemPage, GovItemStatus
from news.models import NewsArticlePage

CHATBOT_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Ti je asistenti inteligjent i platformes "HoW News" — iniciative e House of Wisdom per qytetaret shqiptare te Republikes se Maqedonise se Veriut.

Misioni yt: T'i ndihmosh qytetareve te kuptojne dhe te aksesojne sherbimet publike, tenderrat, grantet, ligjet dhe njoftimet qeveritare te RMV, ne gjuhe te thjeshte shqipe.

Rregullat:
- Pergjigju VETEM ne Shqip, te qarte dhe te thjeshte
- Kur ke informacion nga baza e te dhenave, cito titullin dhe linkun
- Nese nuk ke informacion te mjaftueshem, thuaj sinqerisht dhe keshillo per ku te gjeje
- Mos jep keshilla juridike zyrtare
- Per afate dhe shuma, ji i sakte
- Pergjigja maksimale: 300 fjale"""


def build_context(query: str) -> str:
    """Kerkon permbajtjen relevante per pyetjen — RAG retrieval."""
    gov_results = list(
        GovItemPage.objects.live()
        .filter(status=GovItemStatus.ACTIVE)
        .search(query)[:5]
    )
    news_results = list(
        NewsArticlePage.objects.live().search(query)[:3]
    )

    parts = []

    for item in gov_results:
        explanation = re.sub(r"<[^>]+>", " ", item.simple_explanation or "")
        explanation = " ".join(explanation.split())[:300]
        parts.append(
            f"[QEVERIA] {item.title}\n"
            f"Lloji: {item.get_item_type_display()} | "
            f"Statusi: {item.get_status_display()}\n"
            f"Institucioni: {item.institution or '—'}\n"
            f"Buxheti: {item.budget or '—'} | "
            f"Afati: {item.deadline.strftime('%d %b %Y') if item.deadline else '—'}\n"
            f"Shpjegimi: {explanation}\n"
            f"Link: {item.original_url or '(pa link)'}"
        )

    for item in news_results:
        parts.append(
            f"[LAJM] {item.title}\n"
            f"Burimi: {item.source_name or '—'} | "
            f"Data: {item.first_published_at.strftime('%d %b %Y') if item.first_published_at else '—'}\n"
            f"{item.intro[:200] if item.intro else '—'}"
        )

    if not parts:
        return "(Nuk u gjet informacion specifik ne bazen e te dhenave per kete pyetje.)"

    return "\n\n---\n\n".join(parts)


def chat(question: str, history: list | None = None) -> dict:
    """
    Kryen nje kthim chatbot.
    Kthen: {'answer': str, 'sources': int, 'error': str|None}
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return {
            "answer": "Chatbot-i nuk eshte konfiguruar. Shto GROQ_API_KEY ne .env (falas: console.groq.com).",
            "sources": 0,
            "error": "no_api_key",
        }

    try:
        from groq import Groq
    except ImportError:
        return {
            "answer": "Libraria 'groq' nuk eshte instaluar. Ekzekuto: pip install groq",
            "sources": 0,
            "error": "import_error",
        }

    context = build_context(question)
    source_count = context.count("[QEVERIA]") + context.count("[LAJM]")

    # Groq (OpenAI-compatible): system message si elementi i pare
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({
        "role": "user",
        "content": (
            f"Pyetja e qytetarit: {question}\n\n"
            f"Informacion i disponueshem nga baza e te dhenave te HoW News:\n\n"
            f"{context}"
        ),
    })

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=CHATBOT_MODEL,
            messages=messages,
            max_tokens=800,
            temperature=0.3,
        )
        answer = response.choices[0].message.content
        return {"answer": answer, "sources": source_count, "error": None}
    except Exception as exc:
        return {
            "answer": "Ndodhi nje gabim teknik. Provo perseri.",
            "sources": 0,
            "error": str(exc),
        }
