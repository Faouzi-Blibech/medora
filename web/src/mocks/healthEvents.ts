// GENERATED from backend/app/health_seed.py (plan Task 8). Re-run the generator after editing the seed.
import type { HealthEvent } from "@/lib/types";

/** Seed events without the per-user flags (api.ts adds matches_me/following). */
export const HEALTH_EVENTS: Omit<HealthEvent, "matches_me" | "following">[] = [
  {
    "id": "he-0001",
    "category": "screening",
    "starts_on": "2026-09-30",
    "ends_on": "2026-10-30",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": "F",
      "min_age": 40,
      "max_age": null
    },
    "organizer": "ONFP",
    "source_url": "https://www.onfp.tn",
    "title": {
      "en": "Octobre Rose: free breast cancer screening",
      "fr": "Octobre Rose : dépistage gratuit du cancer du sein",
      "ar": "أكتوبر الوردي: الكشف المجاني عن سرطان الثدي"
    },
    "description": {
      "en": "Free clinical breast exams at ONFP centres and the Mamo Life mobile clinic in all 24 governorates.",
      "fr": "Examens cliniques des seins gratuits dans les centres de l'ONFP et la clinique mobile Mamo Life, dans les 24 gouvernorats.",
      "ar": "فحوصات سريرية مجانية للثدي في مراكز الديوان الوطني للأسرة والعمران البشري والعيادة المتنقلة Mamo Life في الولايات الـ24."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0002",
    "category": "mental_health",
    "starts_on": "2026-10-10",
    "ends_on": "2026-10-10",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": null,
      "max_age": null
    },
    "organizer": "WHO",
    "source_url": "https://www.who.int/campaigns/world-mental-health-day",
    "title": {
      "en": "World Mental Health Day",
      "fr": "Journée mondiale de la santé mentale",
      "ar": "اليوم العالمي للصحة النفسية"
    },
    "description": {
      "en": "Talk about how you feel. Support is available at your basic health centre.",
      "fr": "Parlez de ce que vous ressentez. Un soutien est disponible dans votre centre de santé de base.",
      "ar": "تحدّث عمّا تشعر به. الدعم متوفر في مركز الصحة الأساسية القريب منك."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0003",
    "category": "vaccination",
    "starts_on": "2026-10-15",
    "ends_on": "2027-02-28",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": 65,
      "max_age": null
    },
    "organizer": "Ministère de la Santé",
    "source_url": "http://www.santetunisie.rns.tn",
    "title": {
      "en": "Seasonal flu vaccination",
      "fr": "Vaccination contre la grippe saisonnière",
      "ar": "التلقيح ضد النزلة الموسمية"
    },
    "description": {
      "en": "Flu vaccine at pharmacies and basic health centres. Priority: people over 65, pregnant women, chronic illness, health workers.",
      "fr": "Vaccin antigrippal en pharmacie et dans les centres de santé de base. Prioritaires : plus de 65 ans, femmes enceintes, maladies chroniques, soignants.",
      "ar": "لقاح النزلة متوفر في الصيدليات ومراكز الصحة الأساسية. الأولوية: من تجاوزوا 65 سنة، الحوامل، أصحاب الأمراض المزمنة، والعاملون في الصحة."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0004",
    "category": "screening",
    "starts_on": "2026-11-01",
    "ends_on": "2026-11-30",
    "audience": {
      "roles": [
        "patient",
        "doctor"
      ],
      "sex": "M",
      "min_age": 50,
      "max_age": null
    },
    "organizer": "Movember",
    "source_url": "https://movember.com",
    "title": {
      "en": "Movember: prostate cancer awareness",
      "fr": "Movember : sensibilisation au cancer de la prostate",
      "ar": "نوفمبر الأزرق: التوعية بسرطان البروستات"
    },
    "description": {
      "en": "Men over 50: ask your doctor whether a prostate check is right for you.",
      "fr": "Hommes de plus de 50 ans : demandez à votre médecin si un contrôle de la prostate vous concerne.",
      "ar": "للرجال فوق 50 سنة: اسأل طبيبك إن كان فحص البروستات مناسبًا لك."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0005",
    "category": "chronic_disease",
    "starts_on": "2026-11-14",
    "ends_on": "2026-11-14",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": null,
      "max_age": null
    },
    "organizer": "IDF / WHO",
    "source_url": "https://worlddiabetesday.org",
    "title": {
      "en": "World Diabetes Day",
      "fr": "Journée mondiale du diabète",
      "ar": "اليوم العالمي للسكري"
    },
    "description": {
      "en": "Free blood sugar checks are often offered on this day. Know your numbers.",
      "fr": "Des contrôles gratuits de la glycémie sont souvent proposés ce jour-là. Connaissez vos chiffres.",
      "ar": "غالبًا ما تُقدَّم فحوصات مجانية لنسبة السكر في الدم في هذا اليوم. اعرف أرقامك."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0006",
    "category": "infectious_disease",
    "starts_on": "2026-12-01",
    "ends_on": "2026-12-01",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": 15,
      "max_age": null
    },
    "organizer": "UNAIDS / WHO",
    "source_url": "https://www.who.int/campaigns/world-aids-day",
    "title": {
      "en": "World AIDS Day",
      "fr": "Journée mondiale de lutte contre le sida",
      "ar": "اليوم العالمي لمكافحة السيدا"
    },
    "description": {
      "en": "Free and anonymous HIV testing is available. Ask at your health centre.",
      "fr": "Le dépistage du VIH est gratuit et anonyme. Renseignez-vous dans votre centre de santé.",
      "ar": "الكشف عن فيروس نقص المناعة مجاني وسري. استفسر في مركزك الصحي."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0007",
    "category": "screening",
    "starts_on": "2027-02-04",
    "ends_on": "2027-02-04",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": null,
      "max_age": null
    },
    "organizer": "UICC",
    "source_url": "https://www.worldcancerday.org",
    "title": {
      "en": "World Cancer Day",
      "fr": "Journée mondiale contre le cancer",
      "ar": "اليوم العالمي لمكافحة السرطان"
    },
    "description": {
      "en": "Ask your doctor which screening fits your age.",
      "fr": "Demandez à votre médecin quel dépistage correspond à votre âge.",
      "ar": "اسأل طبيبك عن الفحص المناسب لعمرك."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0008",
    "category": "chronic_disease",
    "starts_on": "2027-02-08",
    "ends_on": "2027-03-09",
    "audience": {
      "roles": [
        "patient",
        "doctor",
        "nurse"
      ],
      "sex": null,
      "min_age": 18,
      "max_age": null
    },
    "organizer": "Ministère de la Santé",
    "source_url": "http://www.santetunisie.rns.tn",
    "title": {
      "en": "Ramadan: fasting safely with diabetes or hypertension (approximate dates)",
      "fr": "Ramadan : jeûner en sécurité avec un diabète ou une hypertension (dates approximatives)",
      "ar": "رمضان: الصيام بأمان مع السكري أو ارتفاع ضغط الدم (تواريخ تقريبية)"
    },
    "description": {
      "en": "See your doctor before Ramadan to adapt your treatment.",
      "fr": "Consultez votre médecin avant le Ramadan pour adapter votre traitement.",
      "ar": "راجع طبيبك قبل رمضان لتكييف علاجك."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0009",
    "category": "infectious_disease",
    "starts_on": "2027-03-24",
    "ends_on": "2027-03-24",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": null,
      "max_age": null
    },
    "organizer": "WHO",
    "source_url": "https://www.who.int/campaigns/world-tb-day",
    "title": {
      "en": "World Tuberculosis Day",
      "fr": "Journée mondiale de la tuberculose",
      "ar": "اليوم العالمي لمكافحة السل"
    },
    "description": {
      "en": "A cough for more than two weeks needs a check. Diagnosis and treatment are free.",
      "fr": "Une toux de plus de deux semaines doit être contrôlée. Le diagnostic et le traitement sont gratuits.",
      "ar": "السعال لأكثر من أسبوعين يستوجب الفحص. التشخيص والعلاج مجانيان."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0010",
    "category": "lifestyle",
    "starts_on": "2027-04-07",
    "ends_on": "2027-04-07",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": null,
      "max_age": null
    },
    "organizer": "WHO",
    "source_url": "https://www.who.int/campaigns/world-health-day",
    "title": {
      "en": "World Health Day",
      "fr": "Journée mondiale de la santé",
      "ar": "اليوم العالمي للصحة"
    },
    "description": {
      "en": "The WHO theme of the year, with events in health centres.",
      "fr": "Le thème de l'année de l'OMS, avec des activités dans les centres de santé.",
      "ar": "موضوع السنة لمنظمة الصحة العالمية، مع أنشطة في المراكز الصحية."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0011",
    "category": "vaccination",
    "starts_on": "2027-04-24",
    "ends_on": "2027-04-30",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": null,
      "max_age": null
    },
    "organizer": "WHO / Ministère de la Santé",
    "source_url": "https://www.who.int/campaigns/world-immunization-week",
    "title": {
      "en": "World Immunization Week",
      "fr": "Semaine mondiale de la vaccination",
      "ar": "الأسبوع العالمي للتلقيح"
    },
    "description": {
      "en": "Check that your family's vaccination record is up to date.",
      "fr": "Vérifiez que le carnet de vaccination de votre famille est à jour.",
      "ar": "تأكد من أن دفتر تلقيح عائلتك محيَّن."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0012",
    "category": "vaccination",
    "starts_on": "2027-04-05",
    "ends_on": "2027-04-30",
    "audience": {
      "roles": [
        "patient",
        "doctor",
        "nurse"
      ],
      "sex": "F",
      "min_age": 11,
      "max_age": 13
    },
    "organizer": "Ministère de la Santé",
    "source_url": "http://www.santetunisie.rns.tn",
    "title": {
      "en": "HPV vaccination for 12-year-old girls",
      "fr": "Vaccination HPV des filles de 12 ans",
      "ar": "التلقيح ضد فيروس الورم الحليمي للفتيات في سن 12"
    },
    "description": {
      "en": "Free, in schools (6th year) and at basic health centres, with parental consent.",
      "fr": "Gratuite, à l'école (6e année) et dans les centres de santé de base, avec l'accord des parents.",
      "ar": "مجاني، في المدارس (السنة السادسة) وفي مراكز الصحة الأساسية، بموافقة الوليّ."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0013",
    "category": "chronic_disease",
    "starts_on": "2027-05-17",
    "ends_on": "2027-05-17",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": 18,
      "max_age": null
    },
    "organizer": "World Hypertension League",
    "source_url": "https://www.whleague.org",
    "title": {
      "en": "World Hypertension Day",
      "fr": "Journée mondiale de l'hypertension",
      "ar": "اليوم العالمي لارتفاع ضغط الدم"
    },
    "description": {
      "en": "Have your blood pressure measured. It is quick and free at health centres.",
      "fr": "Faites mesurer votre tension. C'est rapide et gratuit dans les centres de santé.",
      "ar": "قِس ضغط دمك. الأمر سريع ومجاني في المراكز الصحية."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0014",
    "category": "lifestyle",
    "starts_on": "2027-05-31",
    "ends_on": "2027-05-31",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": 15,
      "max_age": null
    },
    "organizer": "WHO",
    "source_url": "https://www.who.int/campaigns/world-no-tobacco-day",
    "title": {
      "en": "World No Tobacco Day",
      "fr": "Journée mondiale sans tabac",
      "ar": "اليوم العالمي للامتناع عن التدخين"
    },
    "description": {
      "en": "Stop-smoking consultations are available. Ask your doctor.",
      "fr": "Des consultations d'aide à l'arrêt du tabac existent. Parlez-en à votre médecin.",
      "ar": "تتوفر استشارات للمساعدة على الإقلاع عن التدخين. تحدّث مع طبيبك."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0015",
    "category": "blood_donation",
    "starts_on": "2027-06-14",
    "ends_on": "2027-06-14",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": 18,
      "max_age": 65
    },
    "organizer": "CNTS / WHO",
    "source_url": "https://www.who.int/campaigns/world-blood-donor-day",
    "title": {
      "en": "World Blood Donor Day",
      "fr": "Journée mondiale du donneur de sang",
      "ar": "اليوم العالمي للمتبرعين بالدم"
    },
    "description": {
      "en": "Give blood at the national blood transfusion centre (CNTS) or a mobile unit.",
      "fr": "Donnez votre sang au Centre national de transfusion sanguine (CNTS) ou dans une unité mobile.",
      "ar": "تبرّع بالدم في المركز الوطني لنقل الدم أو في وحدة متنقلة."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0016",
    "category": "infectious_disease",
    "starts_on": "2027-07-28",
    "ends_on": "2027-07-28",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": null,
      "max_age": null
    },
    "organizer": "WHO",
    "source_url": "https://www.who.int/campaigns/world-hepatitis-day",
    "title": {
      "en": "World Hepatitis Day",
      "fr": "Journée mondiale contre l'hépatite",
      "ar": "اليوم العالمي لالتهاب الكبد"
    },
    "description": {
      "en": "Hepatitis B and C can be tested and treated. Ask about a test.",
      "fr": "Les hépatites B et C se dépistent et se traitent. Demandez un test.",
      "ar": "يمكن الكشف عن التهاب الكبد ب و ج وعلاجهما. اسأل عن التحليل."
    },
    "notify_days_before": 3,
    "announced_at": null
  },
  {
    "id": "he-0017",
    "category": "chronic_disease",
    "starts_on": "2027-09-29",
    "ends_on": "2027-09-29",
    "audience": {
      "roles": [
        "patient",
        "nurse",
        "doctor",
        "admin"
      ],
      "sex": null,
      "min_age": 18,
      "max_age": null
    },
    "organizer": "World Heart Federation",
    "source_url": "https://world-heart-federation.org/world-heart-day",
    "title": {
      "en": "World Heart Day",
      "fr": "Journée mondiale du cœur",
      "ar": "اليوم العالمي للقلب"
    },
    "description": {
      "en": "Move more, eat less salt, check your blood pressure.",
      "fr": "Bougez plus, mangez moins salé, contrôlez votre tension.",
      "ar": "تحرّك أكثر، قلّل الملح، وراقب ضغط دمك."
    },
    "notify_days_before": 3,
    "announced_at": null
  }
];
