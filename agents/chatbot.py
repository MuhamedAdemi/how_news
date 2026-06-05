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

SYSTEM_PROMPT = """Ti je "Asistenti HoW" — keshilltar personal per qytetaret shqiptare te Republikes se Maqedonise se Veriut (RMV), i specializuar per:
- Subvencione dhe grante bujqesore (MZSV, IPARD, programet nacionale)
- Ndihma sociale dhe punesim (MTSP, Agjencia e Punesimit)
- Thirrje publike dhe grante per OJQ dhe biznes
- Procedura administrative dhe dokumente

MENYRA E PUNES:
Kur personi te tregon kush eshte (bujk, bletor, i papune, etj.) dhe cfare ka nevojë — ti i pergjigesh si nje keshilltar i informuar, si nje sherbyes shteteror qe di gjithcka dhe ndihmon me zemre.

RREGULLAT:

1. LEXO profilin e personit: profesioni, lokacioni, lloji i aktivitetit, shkalla (hektare, krerë bagëtie, etj.)
2. IDENTIFIKO programin/subvencionin me te pershtatshme per kete profil
3. JEP hapat konkrete: 1, 2, 3... — jo tekst te pergjithshem
4. LISTA dokumentet e sakta: cilesoji dokumentet zyrtare sipas emrit
5. TREGO institucionin e sakte: emri i plote, jo vetem "komuna"
6. SHUMA dhe AFATE: thuaj shumat orientuese dhe afatin zakonisht
7. CITO burimet nga DB kur ke (thirrje aktive, grante, lajme)
8. Nese baza e platformes nuk ka te dhena, perdor njohurite per sistemin maqedonas

PER BUJQIT DHE BLEGTORET:
- Institucioni kryesor: Ministria e Bujqesise, Pylltarise dhe Ujrave (MBPU) + Agjensia per Mbeshtetje Financiare ne Bujqesi (AMFB/AFSARD)
- Subvencione direkte per: grure, misri, perimet, fruta, vreshtat, bageti
- IPARD III (2023-2027): investime per fermat, pajisje, ndertesa
- Aplikimet zakonisht: Janar-Mars cdo vit, ne Inspektoriatin Rajonal te Bujqesise

PER SOCIALE:
- Institucioni: Qendra per Pune Sociale ne komunen perkatese
- Dokumentet baze: kartes identiteti, certifikata lindjeje, deklarata e gjendjes materiale

GJUHA: Gjithmone Shqip, e qarte, miqesore — si te flasesh me fqinjin tende qe di gjithcka.
GJATESIA: max 400 fjale, me numra dhe lista."""


DOMAIN_KEYWORDS_MAP = {
    "bujqesi": ["bujq", "ferm", "tok", "bim", "mal", "domat", "pept", "grur", "misër", "vresht", "arë"],
    "blegtori": ["blegtor", "dele", "lopë", "kafsh", "bagëti", "mish", "qumësht", "tufë", "ahur", "traktor"],
    "rural": ["rural", "fshat", "IPARD", "LEADER", "zhvillim vendor"],
    "social": ["sociale", "familje", "fëmij", "pension", "invalid", "ndihm", "varfëri"],
    "punesim": ["punësim", "punë", "papunësi", "trajnim", "punëdhën", "punëkërkues", "karrierë"],
    "biznes": ["biznes", "ndërmarrje", "SME", "startup", "eksport", "invest", "kompani"],
    "ambient": ["ambient", "ekolog", "mjedis", "energji", "klimë", "riciklim"],
    "arsim": ["arsim", "edukim", "rini", "student", "shkollë", "bursë", "universit"],
}


def _detect_domain(query: str) -> str | None:
    q = query.lower()
    for domain, keywords in DOMAIN_KEYWORDS_MAP.items():
        if any(k.lower() in q for k in keywords):
            return domain
    return None


def build_context(query: str) -> str:
    """Kerkon permbajtjen relevante per pyetjen — RAG retrieval me domain detection."""
    domain = _detect_domain(query)

    qs = GovItemPage.objects.live().filter(status=GovItemStatus.ACTIVE)
    if domain:
        domain_results = list(qs.filter(domain=domain).search(query)[:4])
        other_results = list(qs.exclude(domain=domain).search(query)[:2])
        gov_results = domain_results + other_results
    else:
        gov_results = list(qs.search(query)[:5])

    news_results = list(
        NewsArticlePage.objects.live().search(query)[:3]
    )

    parts = []

    for item in gov_results:
        explanation = re.sub(r"<[^>]+>", " ", item.simple_explanation or "")
        explanation = " ".join(explanation.split())[:300]
        docs = item.documents_required.strip() if item.documents_required else ""
        eligible = item.eligible_who.strip() if item.eligible_who else ""
        parts.append(
            f"[PROGRAM] {item.title}\n"
            f"Domain: {item.get_domain_display() if hasattr(item, 'get_domain_display') else item.domain} | "
            f"Lloji: {item.get_item_type_display()} | "
            f"Statusi: {item.get_status_display()}\n"
            f"Institucioni: {item.institution or '—'}\n"
            f"Buxheti/Shuma: {item.budget or '—'} | "
            f"Afati: {item.deadline.strftime('%d %b %Y') if item.deadline else '—'}\n"
            + (f"Kush ka te drejte: {eligible}\n" if eligible else "")
            + (f"Dokumentet: {docs}\n" if docs else "")
            + f"Shpjegimi: {explanation}\n"
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
