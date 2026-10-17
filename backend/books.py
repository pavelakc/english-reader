"""Catalog of free graded readers by Paul Nation & colleagues (Victoria University of Wellington).

Source page: https://www.wgtn.ac.nz/lals/resources/paul-nations-resources/readers
Licence: free to use and distribute, must not be offered for sale.

level = vocabulary size in word families (0 = single version).
Rough CEFR guide: 1200 ≈ A2, 4000 ≈ B1+, 6000 ≈ B2, 8000 ≈ C1.
"""

BASE = "https://www.wgtn.ac.nz/lals/resources/paul-nations-resources/readers/mid-frequency-graded-readers/"
FREE = "https://www.wgtn.ac.nz/lals/resources/paul-nations-resources/readers/free-graded-readers/"


def _lv(pattern):
    return {lv: BASE + pattern.format(lv) for lv in (4000, 6000, 8000)}


BOOKS = [
    {
        "id": "burning-bed",
        "title": "The Burning Bed",
        "author": "Paul Nation",
        "kind": "story",
        "about": "Короткая смешная история из жизни автора. Есть аудио.",
        "levels": {0: "https://www.wgtn.ac.nz/__data/assets/pdf_file/0003/1918416/The-Burning-Bed-text.pdf"},
        "audio": "https://www.wgtn.ac.nz/__data/assets/audio_file/0011/1918415/The-burning-bed.mp3",
    },
    {
        "id": "fire-on-the-mountain",
        "title": "Fire on the Mountain",
        "author": "Gerry Meister & Paul Nation",
        "kind": "fiction",
        "about": "Приключенческая повесть на 1 200 слов — самый лёгкий уровень (≈A2).",
        "levels": {1200: FREE + "Fire-on-the-Mountain.pdf"},
    },
    {
        "id": "indonesian-love-story",
        "title": "Indonesian Love Story",
        "author": "Gerry Meister & Paul Nation",
        "kind": "fiction",
        "about": "История любви на 1 200 слов (≈A2).",
        "levels": {1200: FREE + "Indonesian-Love-Story.pdf"},
    },
    {
        "id": "sherlock-holmes",
        "title": "The Adventures of Sherlock Holmes",
        "author": "Arthur Conan Doyle",
        "kind": "fiction",
        "about": "12 детективных рассказов о Шерлоке Холмсе.",
        "levels": _lv("Sherlock-Holmes-{}-version.pdf"),
    },
    {
        "id": "time-machine",
        "title": "The Time Machine",
        "author": "H. G. Wells",
        "kind": "fiction",
        "about": "Классическая фантастика о путешествии в далёкое будущее.",
        "levels": _lv("The-Time-Machine-Simplified-{}-Version.pdf"),
    },
    {
        "id": "great-gatsby",
        "title": "The Great Gatsby",
        "author": "F. Scott Fitzgerald",
        "kind": "fiction",
        "about": "Америка 1920-х: богатство, вечеринки и загадочный Гэтсби.",
        "levels": _lv("The-Great-Gatsby-Simplified-{}-Version.pdf"),
    },
    {
        "id": "jekyll-hyde",
        "title": "Dr Jekyll and Mr Hyde",
        "author": "Robert Louis Stevenson",
        "kind": "fiction",
        "about": "Учёный, который живёт двумя жизнями.",
        "levels": _lv("The-Strange-Case-of-Dr-Jekyll-and-Mr-Hyde-simplified-{}-level-version.pdf"),
    },
    {
        "id": "metamorphosis",
        "title": "Metamorphosis",
        "author": "Franz Kafka",
        "kind": "fiction",
        "about": "Грегор просыпается огромным насекомым.",
        "levels": _lv("Metamorphosis-{}-version.pdf"),
    },
    {
        "id": "christmas-carol",
        "title": "A Christmas Carol",
        "author": "Charles Dickens",
        "kind": "fiction",
        "about": "Скупой Скрудж и три рождественских призрака.",
        "levels": _lv("A-Christmas-Carol-simplified-{}-level-version.pdf"),
    },
    {
        "id": "alice",
        "title": "Alice's Adventures in Wonderland",
        "author": "Lewis Carroll",
        "kind": "fiction",
        "about": "Алиса в Стране чудес — игра со словами и логикой.",
        "levels": _lv("Alice-{}-word-version.pdf"),
    },
    {
        "id": "more-william",
        "title": "More William",
        "author": "Richmal Crompton",
        "kind": "fiction",
        "about": "Смешные истории о мальчике, который вечно попадает в неприятности.",
        "levels": _lv("More-William-simplified-{}-level-version.txt"),
    },
    {
        "id": "jane-eyre",
        "title": "Jane Eyre",
        "author": "Charlotte Brontë",
        "kind": "fiction",
        "about": "Классический роман о трудном пути к счастью.",
        "levels": _lv("Jane-Eyre-simplified-{}-word-level.pdf"),
    },
    {
        "id": "wuthering-heights",
        "title": "Wuthering Heights",
        "author": "Emily Brontë",
        "kind": "fiction",
        "about": "Грозовой перевал — сложный, но сильный роман.",
        "levels": {lv: BASE + f"Wuthering-Heights-{lv}.pdf" for lv in (4000, 6000, 8000)},
    },
    {
        "id": "art-of-war",
        "title": "The Art of War",
        "author": "Sun Tzu",
        "kind": "non-fiction",
        "about": "Искусство войны — практичные советы, которые применяют и в бизнесе.",
        "levels": _lv("Art-of-War-simplified-{}-version.txt"),
    },
    {
        "id": "japan",
        "title": "Glimpses of an Unfamiliar Japan",
        "author": "Lafcadio Hearn",
        "kind": "non-fiction",
        "about": "Путешествие по Японии 1890-х.",
        "levels": _lv("Glimpses-of-Unfamiliar-Japan-{}-version.pdf"),
    },
    {
        "id": "free-culture",
        "title": "Free Culture",
        "author": "Lawrence Lessig",
        "kind": "non-fiction",
        "about": "Как медиа и закон контролируют творчество.",
        "levels": {
            4000: BASE + "Free-Culture-simplified-4000-level.pdf",
            6000: BASE + "Free-Culture-simplified-6000-level.pdf",
            8000: BASE + "Free-Culture-simplified-8000-version.pdf",
        },
    },
    {
        "id": "frederick-douglass",
        "title": "Narrative of the Life of Frederick Douglass",
        "author": "Frederick Douglass",
        "kind": "non-fiction",
        "about": "Автобиография человека, бежавшего из рабства. Есть жестокие сцены.",
        "levels": _lv("frederick-douglass-simplified-{}-level.pdf"),
    },
    {
        "id": "the-prince",
        "title": "The Prince",
        "author": "Niccolò Machiavelli",
        "kind": "non-fiction",
        "about": "«Государь» — как должен вести себя правитель.",
        "levels": {4000: BASE + "Prince-Adapted2.pdf"},
    },
]

ABOUT_I18N = {'burning-bed': {'uk': 'Коротка смішна історія з життя автора. Є аудіо.', 'en': "A short funny story from the author's life. With audio."},
    'fire-on-the-mountain': {'uk': 'Пригодницька повість на 1 200 слів — найлегший рівень (≈A2).', 'en': 'An adventure story using just 1,200 words — the easiest level (≈A2).'},
    'indonesian-love-story': {'uk': 'Історія кохання на 1 200 слів (≈A2).', 'en': 'A love story using 1,200 words (≈A2).'},
    'sherlock-holmes': {'uk': '12 детективних оповідань про Шерлока Холмса.', 'en': '12 detective stories about Sherlock Holmes.'},
    'time-machine': {'uk': 'Класична фантастика про подорож у далеке майбутнє.', 'en': 'Classic science fiction about a journey into the far future.'},
    'great-gatsby': {'uk': 'Америка 1920-х: багатство, вечірки й загадковий Гетсбі.', 'en': '1920s America: wealth, parties and the mysterious Gatsby.'},
    'jekyll-hyde': {'uk': 'Учений, який живе двома життями.', 'en': 'A scientist who lives two lives.'},
    'metamorphosis': {'uk': 'Грегор прокидається величезною комахою.', 'en': 'Gregor wakes up as a giant insect.'},
    'christmas-carol': {'uk': 'Скупий Скрудж і три різдвяні привиди.', 'en': 'Mean old Scrooge and three Christmas ghosts.'},
    'alice': {'uk': 'Аліса в Країні чудес — гра зі словами й логікою.', 'en': 'Alice in Wonderland — a playful game with words and logic.'},
    'more-william': {'uk': 'Смішні історії про хлопчика, який постійно вскакує в халепу.', 'en': 'Funny stories about a boy who is always in trouble.'},
    'jane-eyre': {'uk': 'Класичний роман про важкий шлях до щастя.', 'en': 'A classic novel about a hard road to happiness.'},
    'wuthering-heights': {'uk': 'Буремний перевал — складний, але сильний роман.', 'en': 'Wuthering Heights — a difficult but powerful novel.'},
    'art-of-war': {'uk': 'Мистецтво війни — практичні поради, які застосовують і в бізнесі.', 'en': 'The Art of War — practical advice also used in business.'},
    'japan': {'uk': 'Подорож Японією 1890-х.', 'en': 'A journey through Japan in the 1890s.'},
    'free-culture': {'uk': 'Як медіа й закон контролюють творчість.', 'en': 'How media and law control creativity.'},
    'frederick-douglass': {'uk': 'Автобіографія людини, яка втекла з рабства. Є жорстокі сцени.', 'en': 'The autobiography of a man who escaped slavery. Contains violent scenes.'},
    'the-prince': {'uk': '«Державець» — як має поводитися правитель.', 'en': 'The Prince — how a ruler should behave.'}}

for _b in BOOKS:
    for _lang, _text in ABOUT_I18N.get(_b["id"], {}).items():
        _b["about_" + _lang] = _text

BOOKS_BY_ID = {b["id"]: b for b in BOOKS}


def public_catalog():
    out = []
    for b in BOOKS:
        item = {k: v for k, v in b.items() if k != "levels"}
        item["levels"] = sorted(b["levels"].keys())
        out.append(item)
    return out
