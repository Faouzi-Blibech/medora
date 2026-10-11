"""The demo health calendar: important public-health events in Tunisia, Oct 2026 → Sep 2027 (spec table).
National campaign dates are announced yearly by the Ministry of Health / ONFP; these are the published or usual
dates, and the admin can edit them. Inserted only when the id is missing, so an admin edit is never overwritten."""

from datetime import date

from sqlalchemy.orm import Session

from app.ids import reserve_upto
from app.models import HealthEvent

ALL = ["patient", "nurse", "doctor", "admin"]
STAFF = ["nurse", "doctor", "admin"]


def _aud(roles=ALL, sex=None, min_age=None, max_age=None) -> dict:
    return {"roles": list(roles), "sex": sex, "min_age": min_age, "max_age": max_age}


def _t(en: str, fr: str, ar: str) -> dict:
    return {"en": en, "fr": fr, "ar": ar}


EVENTS: list[dict] = [
    dict(
        id="he-0001",
        category="screening",
        starts_on=date(2026, 9, 30),
        ends_on=date(2026, 10, 30),
        audience=_aud(["patient", *STAFF], sex="F", min_age=40),
        organizer="ONFP",
        source_url="https://www.onfp.tn",
        title=_t(
            "Octobre Rose: free breast cancer screening",
            "Octobre Rose : dépistage gratuit du cancer du sein",
            "أكتوبر الوردي: الكشف المجاني عن سرطان الثدي",
        ),
        description=_t(
            "Free clinical breast exams at ONFP centres and the Mamo Life mobile clinic in all 24 governorates.",
            "Examens cliniques des seins gratuits dans les centres de l'ONFP et la clinique mobile Mamo Life, dans les 24 gouvernorats.",
            "فحوصات سريرية مجانية للثدي في مراكز الديوان الوطني للأسرة والعمران البشري والعيادة المتنقلة Mamo Life في الولايات الـ24.",
        ),
    ),
    dict(
        id="he-0002",
        category="mental_health",
        starts_on=date(2026, 10, 10),
        ends_on=date(2026, 10, 10),
        audience=_aud(),
        organizer="WHO",
        source_url="https://www.who.int/campaigns/world-mental-health-day",
        title=_t(
            "World Mental Health Day", "Journée mondiale de la santé mentale", "اليوم العالمي للصحة النفسية"
        ),
        description=_t(
            "Talk about how you feel. Support is available at your basic health centre.",
            "Parlez de ce que vous ressentez. Un soutien est disponible dans votre centre de santé de base.",
            "تحدّث عمّا تشعر به. الدعم متوفر في مركز الصحة الأساسية القريب منك.",
        ),
    ),
    dict(
        id="he-0003",
        category="vaccination",
        starts_on=date(2026, 10, 15),
        ends_on=date(2027, 2, 28),
        audience=_aud(["patient", *STAFF], min_age=65),
        organizer="Ministère de la Santé",
        source_url="http://www.santetunisie.rns.tn",
        title=_t(
            "Seasonal flu vaccination",
            "Vaccination contre la grippe saisonnière",
            "التلقيح ضد النزلة الموسمية",
        ),
        description=_t(
            "Flu vaccine at pharmacies and basic health centres. Priority: people over 65, pregnant women, chronic illness, health workers.",
            "Vaccin antigrippal en pharmacie et dans les centres de santé de base. Prioritaires : plus de 65 ans, femmes enceintes, maladies chroniques, soignants.",
            "لقاح النزلة متوفر في الصيدليات ومراكز الصحة الأساسية. الأولوية: من تجاوزوا 65 سنة، الحوامل، أصحاب الأمراض المزمنة، والعاملون في الصحة.",
        ),
    ),
    dict(
        id="he-0004",
        category="screening",
        starts_on=date(2026, 11, 1),
        ends_on=date(2026, 11, 30),
        audience=_aud(["patient", "doctor"], sex="M", min_age=50),
        organizer="Movember",
        source_url="https://movember.com",
        title=_t(
            "Movember: prostate cancer awareness",
            "Movember : sensibilisation au cancer de la prostate",
            "نوفمبر الأزرق: التوعية بسرطان البروستات",
        ),
        description=_t(
            "Men over 50: ask your doctor whether a prostate check is right for you.",
            "Hommes de plus de 50 ans : demandez à votre médecin si un contrôle de la prostate vous concerne.",
            "للرجال فوق 50 سنة: اسأل طبيبك إن كان فحص البروستات مناسبًا لك.",
        ),
    ),
    dict(
        id="he-0005",
        category="chronic_disease",
        starts_on=date(2026, 11, 14),
        ends_on=date(2026, 11, 14),
        audience=_aud(),
        organizer="IDF / WHO",
        source_url="https://worlddiabetesday.org",
        title=_t("World Diabetes Day", "Journée mondiale du diabète", "اليوم العالمي للسكري"),
        description=_t(
            "Free blood sugar checks are often offered on this day. Know your numbers.",
            "Des contrôles gratuits de la glycémie sont souvent proposés ce jour-là. Connaissez vos chiffres.",
            "غالبًا ما تُقدَّم فحوصات مجانية لنسبة السكر في الدم في هذا اليوم. اعرف أرقامك.",
        ),
    ),
    dict(
        id="he-0006",
        category="infectious_disease",
        starts_on=date(2026, 12, 1),
        ends_on=date(2026, 12, 1),
        audience=_aud(["patient", *STAFF], min_age=15),
        organizer="UNAIDS / WHO",
        source_url="https://www.who.int/campaigns/world-aids-day",
        title=_t(
            "World AIDS Day", "Journée mondiale de lutte contre le sida", "اليوم العالمي لمكافحة السيدا"
        ),
        description=_t(
            "Free and anonymous HIV testing is available. Ask at your health centre.",
            "Le dépistage du VIH est gratuit et anonyme. Renseignez-vous dans votre centre de santé.",
            "الكشف عن فيروس نقص المناعة مجاني وسري. استفسر في مركزك الصحي.",
        ),
    ),
    dict(
        id="he-0007",
        category="screening",
        starts_on=date(2027, 2, 4),
        ends_on=date(2027, 2, 4),
        audience=_aud(),
        organizer="UICC",
        source_url="https://www.worldcancerday.org",
        title=_t("World Cancer Day", "Journée mondiale contre le cancer", "اليوم العالمي لمكافحة السرطان"),
        description=_t(
            "Ask your doctor which screening fits your age.",
            "Demandez à votre médecin quel dépistage correspond à votre âge.",
            "اسأل طبيبك عن الفحص المناسب لعمرك.",
        ),
    ),
    dict(
        id="he-0008",
        category="chronic_disease",
        starts_on=date(2027, 2, 8),
        ends_on=date(2027, 3, 9),
        audience=_aud(["patient", "doctor", "nurse"], min_age=18),
        organizer="Ministère de la Santé",
        source_url="http://www.santetunisie.rns.tn",
        title=_t(
            "Ramadan: fasting safely with diabetes or hypertension (approximate dates)",
            "Ramadan : jeûner en sécurité avec un diabète ou une hypertension (dates approximatives)",
            "رمضان: الصيام بأمان مع السكري أو ارتفاع ضغط الدم (تواريخ تقريبية)",
        ),
        description=_t(
            "See your doctor before Ramadan to adapt your treatment.",
            "Consultez votre médecin avant le Ramadan pour adapter votre traitement.",
            "راجع طبيبك قبل رمضان لتكييف علاجك.",
        ),
    ),
    dict(
        id="he-0009",
        category="infectious_disease",
        starts_on=date(2027, 3, 24),
        ends_on=date(2027, 3, 24),
        audience=_aud(),
        organizer="WHO",
        source_url="https://www.who.int/campaigns/world-tb-day",
        title=_t(
            "World Tuberculosis Day", "Journée mondiale de la tuberculose", "اليوم العالمي لمكافحة السل"
        ),
        description=_t(
            "A cough for more than two weeks needs a check. Diagnosis and treatment are free.",
            "Une toux de plus de deux semaines doit être contrôlée. Le diagnostic et le traitement sont gratuits.",
            "السعال لأكثر من أسبوعين يستوجب الفحص. التشخيص والعلاج مجانيان.",
        ),
    ),
    dict(
        id="he-0010",
        category="lifestyle",
        starts_on=date(2027, 4, 7),
        ends_on=date(2027, 4, 7),
        audience=_aud(),
        organizer="WHO",
        source_url="https://www.who.int/campaigns/world-health-day",
        title=_t("World Health Day", "Journée mondiale de la santé", "اليوم العالمي للصحة"),
        description=_t(
            "The WHO theme of the year, with events in health centres.",
            "Le thème de l'année de l'OMS, avec des activités dans les centres de santé.",
            "موضوع السنة لمنظمة الصحة العالمية، مع أنشطة في المراكز الصحية.",
        ),
    ),
    dict(
        id="he-0011",
        category="vaccination",
        starts_on=date(2027, 4, 24),
        ends_on=date(2027, 4, 30),
        audience=_aud(),
        organizer="WHO / Ministère de la Santé",
        source_url="https://www.who.int/campaigns/world-immunization-week",
        title=_t("World Immunization Week", "Semaine mondiale de la vaccination", "الأسبوع العالمي للتلقيح"),
        description=_t(
            "Check that your family's vaccination record is up to date.",
            "Vérifiez que le carnet de vaccination de votre famille est à jour.",
            "تأكد من أن دفتر تلقيح عائلتك محيَّن.",
        ),
    ),
    dict(
        id="he-0012",
        category="vaccination",
        starts_on=date(2027, 4, 5),
        ends_on=date(2027, 4, 30),
        audience=_aud(["patient", "doctor", "nurse"], sex="F", min_age=11, max_age=13),
        organizer="Ministère de la Santé",
        source_url="http://www.santetunisie.rns.tn",
        title=_t(
            "HPV vaccination for 12-year-old girls",
            "Vaccination HPV des filles de 12 ans",
            "التلقيح ضد فيروس الورم الحليمي للفتيات في سن 12",
        ),
        description=_t(
            "Free, in schools (6th year) and at basic health centres, with parental consent.",
            "Gratuite, à l'école (6e année) et dans les centres de santé de base, avec l'accord des parents.",
            "مجاني، في المدارس (السنة السادسة) وفي مراكز الصحة الأساسية، بموافقة الوليّ.",
        ),
    ),
    dict(
        id="he-0013",
        category="chronic_disease",
        starts_on=date(2027, 5, 17),
        ends_on=date(2027, 5, 17),
        audience=_aud(["patient", *STAFF], min_age=18),
        organizer="World Hypertension League",
        source_url="https://www.whleague.org",
        title=_t(
            "World Hypertension Day", "Journée mondiale de l'hypertension", "اليوم العالمي لارتفاع ضغط الدم"
        ),
        description=_t(
            "Have your blood pressure measured. It is quick and free at health centres.",
            "Faites mesurer votre tension. C'est rapide et gratuit dans les centres de santé.",
            "قِس ضغط دمك. الأمر سريع ومجاني في المراكز الصحية.",
        ),
    ),
    dict(
        id="he-0014",
        category="lifestyle",
        starts_on=date(2027, 5, 31),
        ends_on=date(2027, 5, 31),
        audience=_aud(["patient", *STAFF], min_age=15),
        organizer="WHO",
        source_url="https://www.who.int/campaigns/world-no-tobacco-day",
        title=_t("World No Tobacco Day", "Journée mondiale sans tabac", "اليوم العالمي للامتناع عن التدخين"),
        description=_t(
            "Stop-smoking consultations are available. Ask your doctor.",
            "Des consultations d'aide à l'arrêt du tabac existent. Parlez-en à votre médecin.",
            "تتوفر استشارات للمساعدة على الإقلاع عن التدخين. تحدّث مع طبيبك.",
        ),
    ),
    dict(
        id="he-0015",
        category="blood_donation",
        starts_on=date(2027, 6, 14),
        ends_on=date(2027, 6, 14),
        audience=_aud(["patient", *STAFF], min_age=18, max_age=65),
        organizer="CNTS / WHO",
        source_url="https://www.who.int/campaigns/world-blood-donor-day",
        title=_t(
            "World Blood Donor Day", "Journée mondiale du donneur de sang", "اليوم العالمي للمتبرعين بالدم"
        ),
        description=_t(
            "Give blood at the national blood transfusion centre (CNTS) or a mobile unit.",
            "Donnez votre sang au Centre national de transfusion sanguine (CNTS) ou dans une unité mobile.",
            "تبرّع بالدم في المركز الوطني لنقل الدم أو في وحدة متنقلة.",
        ),
    ),
    dict(
        id="he-0016",
        category="infectious_disease",
        starts_on=date(2027, 7, 28),
        ends_on=date(2027, 7, 28),
        audience=_aud(),
        organizer="WHO",
        source_url="https://www.who.int/campaigns/world-hepatitis-day",
        title=_t("World Hepatitis Day", "Journée mondiale contre l'hépatite", "اليوم العالمي لالتهاب الكبد"),
        description=_t(
            "Hepatitis B and C can be tested and treated. Ask about a test.",
            "Les hépatites B et C se dépistent et se traitent. Demandez un test.",
            "يمكن الكشف عن التهاب الكبد ب و ج وعلاجهما. اسأل عن التحليل.",
        ),
    ),
    dict(
        id="he-0017",
        category="chronic_disease",
        starts_on=date(2027, 9, 29),
        ends_on=date(2027, 9, 29),
        audience=_aud(["patient", *STAFF], min_age=18),
        organizer="World Heart Federation",
        source_url="https://world-heart-federation.org/world-heart-day",
        title=_t("World Heart Day", "Journée mondiale du cœur", "اليوم العالمي للقلب"),
        description=_t(
            "Move more, eat less salt, check your blood pressure.",
            "Bougez plus, mangez moins salé, contrôlez votre tension.",
            "تحرّك أكثر، قلّل الملح، وراقب ضغط دمك.",
        ),
    ),
]


def seed_health_events(db: Session) -> int:
    """Insert the seed events whose id is missing. Returns how many were inserted."""
    added = 0
    for e in EVENTS:
        if db.get(HealthEvent, e["id"]) is None:
            db.add(HealthEvent(notify_days_before=3, **e))
            added += 1
    db.flush()
    reserve_upto(db, "he", len(EVENTS))
    return added
