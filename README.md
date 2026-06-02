# HoW News — Platforma Qytetare e House of Wisdom

> **Informacion qytetar, qeveria e thjeshtë dhe edukim për qytetarët e Maqedonisë së Veriut**

[![Django](https://img.shields.io/badge/Django-5.2-green)](https://djangoproject.com)
[![Wagtail](https://img.shields.io/badge/Wagtail-7.4-blue)](https://wagtail.org)
[![Groq AI](https://img.shields.io/badge/Groq_AI-LLaMA_3.3-orange)](https://groq.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## Misioni

HoW News është një platformë open-source e ndërtuar nga **House of Wisdom (HoW)** — OJQ e dedikuar ndaj emancipimit, edukimit dhe mbrojtjes së të drejtave të qytetarëve në Republikën e Maqedonisë së Veriut.

Platforma i shërben qytetarët e Maqedonisë së Veriut  duke:
- **Thjeshtësuar informacionin zyrtar qeveritar** — tenderë, grante, njoftime — në gjuhë të kuptueshme
- **Mbledhur lajme** nga burime shqipe dhe maqedonase në një vend
- **Ofherjë asistent AI** që i ndihmon qytetarët të kuptojnë procedurat administrative
- **Bërë transparente** mundësitë e financimit dhe shërbimet publike

---

## Karakteristikat Kryesore

### Lajme Ditore
- Agregim automatik nga 12+ burime RSS (Telegrafi, Koha.net, Portalb.mk, Meta.mk...)
- Filtrim sipas gjuhës (Shqip / Maqedonisht / Anglisht) dhe kategorisë
- Kërkim me filtra të avancuar

### Qeveria e Thjeshtë
- **Skanim automatik** i portaleve qeveritare të RMV
- **AI (Claude)** thjeshtëson gjuhën ligjore/burokratike në Shqip të qartë
- Informacion për: tenderë, grante, konkurse, ligje, njoftime sociale
- Komanda `process_url` — redaktori jep URL, AI krijon shpjegimin

### Asistenti AI (Chatbot RAG)
- Qytetari pyet lirshëm: *"Cilat grante janë të hapura për OJQ-të?"*
- AI kërkon në bazën e të dhënave lokale (RAG) dhe përgjigjet në Shqip
- Bazuar në **Groq + LLaMA 3.3 70B** — kosto **ZERO** (tier falas, 14,400 kërkesa/ditë)

### REST API
- Endpoint-e të plota për lajme, qeveri dhe video
- Dokumentacion Browsable API

---

## Stack Teknik

| Komponenti | Teknologjia |
|-----------|-------------|
| Backend | Django 5.2 + Wagtail 7.4 CMS |
| AI/NLP | Groq API — LLaMA 3.3 70B (FALAS) |
| RAG | Wagtail Search + LLaMA context |
| Frontend | Bootstrap 5.3 + Bootstrap Icons |
| API | Django REST Framework |
| RSS | feedparser |
| Scraping | requests + BeautifulSoup4 |
| Production | Docker + Gunicorn + WhiteNoise |
| DB | SQLite (dev) / PostgreSQL (prod) |

---

## Instalimi i Shpejtë

```bash
git clone https://github.com/MuhamedAdemi/how_news.git
cd how_news
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/Mac
pip install -r requirements.txt
cp .env.example .env           # edito .env
python manage.py migrate
python manage.py createsuperuser
python manage.py setup_site    # krijon strukturën + burimet
python manage.py fetch_feeds --limit 5   # lajmet e para
python manage.py runserver
```

Shko te `http://127.0.0.1:8000/admin/` dhe logohu.

---

## Komandat Kryesore

```bash
# Lajme nga RSS
python manage.py fetch_feeds --limit 20

# Informacion qeveritar (pa AI)
python manage.py fetch_gov --limit 5

# Informacion qeveritar me AI (kërkon ANTHROPIC_API_KEY)
python manage.py fetch_gov --ai --limit 5

# Proceso URL specifike zyrtare me AI
python manage.py process_url https://vlada.mk/mk-MK/...

# Shëno si të skaduara GovItemPage-t me afat të kaluar
python manage.py expire_gov_items  # (në zhvillim)
```

---

## Konfigurimi (.env)

```env
SECRET_KEY=django-key-e-gjate
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=                        # bosh = SQLite
GROQ_API_KEY=gsk_...                 # falas: console.groq.com
CSRF_TRUSTED_ORIGINS=http://localhost:8000
WAGTAILADMIN_BASE_URL=http://localhost:8000
```

---

## Docker (Produksion)

```bash
cp .env.example .env    # edito .env me vlera produksioni
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py setup_site
```

---

## Struktura e Projektit

```
how_news/
├── agents/          ← Chatbot AI + Discovery Agent
├── news/            ← Lajmet + RSS fetch
├── government/      ← Qeveria e Thjeshtë + fetch_gov
├── videos/          ← Video HoW (YouTube/Vimeo)
├── home/            ← Homepage + Wagtail admin branding
├── search/          ← Kërkim me filtra
└── how_news/
    ├── settings/    ← dev.py / production.py
    ├── urls.py
    └── api_urls.py  ← REST API endpoints
```

---

## Impakti Social

**Popullatë e synuar:**qytetarët në Republikën e Maqedonisë së Veriut

**Problemi:** Informacioni zyrtar qeveritar publikohet ekskluzivisht në Maqedonisht dhe me gjuhë tekniko-juridike, duke e bërë të paarritshem për komunitetin shqiptar ne këtë e thjeshtojm dhe e përshtatim edhe në shqip edhe në anglisht.

**Zgjidhja jonë:** Agregim automatik + AI thjeshtëson + chatbot i aksesueshëm.

---

## Kontributi

Pull request-et janë të mirëpritura. Shih [CONTRIBUTING.md](CONTRIBUTING.md) për detaje.

---

## Licenca

MIT License — shih [LICENSE](LICENSE).

---

## Kontakti

- **Organizata:** House of Wisdom (HoW)
- **GitHub:** [@MuhamedAdemi](https://github.com/MuhamedAdemi)
- **Email:** muahmedademi1214@gmail.com

---

*Ndërtuar me ❤️ për të ndihmuar qytetarët e Maqedonisë së Veriut*
