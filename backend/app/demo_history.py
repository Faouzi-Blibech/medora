"""OPT-IN synthetic ward history for the pilot impact dashboard (api.md 1.18).

    python -m app.demo_history --days 60      # add the history (does nothing if it is already there)
    python -m app.demo_history --reset        # remove only the rows this script created

Writes past ward operations ending two days ago, so nothing shows in today's views, open-alert lists or
"last 24 h" panels: discharged admissions, inactive prescriptions and their doses, vitals, acknowledged
alerts (bed only, no patient link, so they stay out of the clinical alert feeds), nurse notes, reviewed AI
summaries and past appointment requests. Everything is invented and
deterministic (fixed random seed). The live demo patients p-0001 and p-0005 are never used.

Every row it writes carries a marker so it can find (and remove) its own rows and nothing else:
ids start with `<prefix>-h` (`adm-h0001`, `rx-h0001`, `d-h000001`, `al-h00001`, `n-h00001`, `ais-h0001`,
`a-h0001`) and vitals use the device ids `hist-<bed>`.
"""

import argparse
import math
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.early_warning import score_news2
from app.models import AiSummary, Alert, Admission, Appointment, MedDose, Note, Patient, Prescription, Vital
from app.services.appointments import new_appointment_fields
from app.services.schedule import local_to_utc, today_local

SEED = 20261005
EXCLUDED = {"p-0001", "p-0005"}  # the live demo patients
DOCTOR, NURSES = "u-0001", ("u-0002", "u-0003")
BEDS = ("H-01", "H-02", "H-03", "H-04", "H-05", "H-06")
MARK = "hist-"  # vitals device id prefix

MEDS = [("Amlodipine 5mg", ["08:00"]), ("Paracetamol 500mg", ["08:00", "20:00"]), ("Furosemide 40mg", ["08:00"]),
        ("Metformin 850mg", ["08:00", "20:00"]), ("Bisoprolol 2.5mg", ["08:00"]),
        ("Enoxaparin 4000 IU", ["20:00"]), ("Omeprazole 20mg", ["08:00"]), ("Amoxicillin 1g", ["08:00", "14:00", "20:00"])]
NOTES = ["Patient comfortable, slept well.", "Ate full breakfast, walking in the corridor.",
         "Mild headache, paracetamol given as prescribed.", "Dressing changed, wound clean.",
         "Family visited, patient in good spirits.", "Complained of nausea after lunch, settled.",
         "Pain 3/10, no further complaints.", "Reminded patient to drink water.",
         "IV line checked, site clean.", "Patient asked about discharge date, doctor informed."]
REQUESTS = [("Contrôle de tension, traitement bien toléré", ["follow-up"]),
            ("Palpitations le soir depuis une semaine", ["palpitations"]),
            ("Shortness of breath when climbing stairs", ["dyspnea"]),
            ("Renouvellement d'ordonnance", ["prescription renewal"]),
            ("Swollen ankles for ten days", ["edema"]),
            ("ألم خفيف في الصدر عند المجهود", ["chest pain"]),
            ("Diabetes follow-up, HbA1c review", ["follow-up"]),
            ("Toux persistante depuis trois semaines", ["cough"])]


def _ids(prefix: str, width: int):
    n = 0
    while True:
        n += 1
        yield f"{prefix}-h{n:0{width}d}"


def present(db: Session) -> bool:
    return db.scalar(select(Admission.id).where(Admission.id.like("adm-h%")).limit(1)) is not None


def reset(db: Session) -> dict:
    """Delete only this script's rows (children first)."""
    out = {}
    for name, stmt in [
        ("alerts", delete(Alert).where(Alert.id.like("al-h%"))),
        ("notes", delete(Note).where(Note.id.like("n-h%"))),
        ("ai_summaries", delete(AiSummary).where(AiSummary.id.like("ais-h%"))),
        ("med_doses", delete(MedDose).where(MedDose.id.like("d-h%"))),
        ("prescriptions", delete(Prescription).where(Prescription.id.like("rx-h%"))),
        ("vitals", delete(Vital).where(Vital.device_id.like(f"{MARK}%"))),
        ("appointments", delete(Appointment).where(Appointment.id.like("a-h%"))),
        ("admissions", delete(Admission).where(Admission.id.like("adm-h%"))),
    ]:
        out[name] = db.execute(stmt).rowcount
    db.flush()
    return out


def _vital(rng: random.Random, base: tuple[int, int, float]) -> tuple[int, int, float]:
    hr, spo2, temp = base
    hr, spo2, temp = hr + rng.randint(-6, 6), min(100, spo2 + rng.randint(-1, 1)), temp + rng.uniform(-0.3, 0.3)
    r = rng.random()
    if r < 0.006:  # rare serious episode
        hr, spo2, temp = hr + 45, spo2 - 8, temp + 2.2
    elif r < 0.05:  # transient deterioration
        hr, spo2, temp = hr + rng.randint(18, 30), spo2 - rng.randint(2, 5), temp + rng.uniform(0.6, 1.4)
    return hr, spo2, round(temp, 1)


def generate(db: Session, days: int = 60, now: datetime | None = None) -> dict:
    """Add the history unless it is already there. Returns row counts (all zero when nothing was added)."""
    counts = dict.fromkeys(["admissions", "prescriptions", "med_doses", "vitals", "alerts", "notes",
                            "ai_summaries", "appointments"], 0)
    if present(db):
        return counts
    rng = random.Random(SEED)
    today = today_local() if now is None else now.astimezone(UTC).date()
    end = local_to_utc(today - timedelta(days=2), "00:00")  # nothing on the last two days
    start = end - timedelta(days=days)
    pos = lambda t: (t - start) / (end - start)  # noqa: E731  0 at the start of the window, 1 at its end

    patients = [p for p in db.scalars(select(Patient).order_by(Patient.id)) if p.id not in EXCLUDED][:10]
    if not patients:
        return counts
    adm_id, rx_id, d_id, al_id = _ids("adm", 4), _ids("rx", 4), _ids("d", 6), _ids("al", 5)
    n_id, s_id, a_id = _ids("n", 5), _ids("ais", 4), _ids("a", 4)
    free_at = {p.id: start for p in patients}

    def alert(bed, kind, sev, at, msg, news2=None, extra=None):
        # No patient_id: the nurse and doctor alert feeds list a patient's alerts newest first with times only,
        # so linked history alerts would read as today's. The bed is kept in device_id; the impact counts all.
        f = pos(at)
        median = 8.0 - 5.5 * f  # acknowledgement gets faster over the window
        delay = median * (0.7 if sev in ("high", "critical") else 1.0) * math.exp(rng.gauss(0, 0.55))
        db.add(Alert(id=next(al_id), patient_id=None, device_id=f"{MARK}{bed}", kind=kind, severity=sev, news2=news2,
                     message=msg, ai_suggested=extra, created_at=at, acked_by=rng.choice(NURSES),
                     acked_at=at + timedelta(minutes=max(0.3, delay))))
        counts["alerts"] += 1

    bed_free = {b: start + timedelta(hours=rng.randint(0, 36)) for b in BEDS}
    while bed_free:  # always fill the bed that frees up first, so patients are booked in time order
        bed = min(bed_free, key=lambda b: (bed_free[b], b))
        t = bed_free[bed]
        stay = timedelta(days=rng.randint(3, 8), hours=rng.randint(0, 20))
        if t + stay > end:
            stay = end - t - timedelta(hours=3)  # the last stay of the bed ends with the window
            if stay < timedelta(days=1):
                del bed_free[bed]
                continue
        ready = [p for p in patients if free_at[p.id] <= t]
        if not ready:
            bed_free[bed] = t + timedelta(hours=12)
            continue
        p = rng.choice(ready)
        admit, discharge = t, t + stay
        free_at[p.id] = discharge + timedelta(days=1)
        db.add(Admission(id=next(adm_id), patient_id=p.id, bed=bed, admitted_at=admit, discharged_at=discharge))
        counts["admissions"] += 1

        # prescription and its doses
        meds = rng.sample(MEDS, rng.randint(1, 3))
        rx = Prescription(id=next(rx_id), patient_id=p.id, doctor_id=DOCTOR, active=False, created_at=admit,
                          care_plan="Synthetic history", items=[{"med": m, "times": ts, "slot": i + 1,
                                                                "days": stay.days + 1}
                                                               for i, (m, ts) in enumerate(meds)])
        db.add(rx)
        db.flush()
        counts["prescriptions"] += 1
        day = admit.date()
        while day <= discharge.date():
            for slot, (med, times) in enumerate(meds, start=1):
                for hhmm in times:
                    at = local_to_utc(day, hhmm)
                    if not admit <= at < discharge:
                        continue
                    f, r = pos(at), rng.random()
                    if r < 0.84 + 0.08 * f:
                        status = "taken"
                        late = rng.random() > 0.82 + 0.12 * f
                        upd = at + timedelta(minutes=rng.randint(35, 120) if late else rng.randint(1, 25))
                    elif r < 0.985:
                        status, upd = "missed", at + timedelta(minutes=30)
                    else:
                        status, upd = "dispensed", at + timedelta(minutes=1)  # never confirmed
                    db.add(MedDose(id=next(d_id), prescription_id=rx.id, patient_id=p.id, scheduled_at=at,
                                   time_of_day=hhmm, meds=[med], slot=slot, status=status,
                                   taken_method="button" if status == "taken" else None, updated_at=upd))
                    counts["med_doses"] += 1
                    if status == "missed" and rng.random() < 0.6:
                        alert(bed, "dose_missed", "medium", upd, f"Dose missed: {med} ({hhmm})")
            day += timedelta(days=1)

        # vitals: nurse rounds every 4 h, plus simulator readings every 30 min on more stays over time
        base = (rng.randint(68, 86), rng.randint(95, 98), round(rng.uniform(36.6, 37.1), 1))
        simulated = rng.random() < 0.2 + 0.55 * pos(admit)
        last_alert: dict[str, datetime] = {}
        step = timedelta(minutes=30 if simulated else 240)
        vt = admit + timedelta(minutes=7)
        k = 0
        while vt < discharge:
            manual = not simulated or k % 8 == 0
            hr, spo2, temp = _vital(rng, base)
            news = score_news2(hr, spo2, temp)
            db.add(Vital(ts=vt, device_id=f"{MARK}{bed}", patient_id=p.id, hr=hr, spo2=spo2, temp=temp,
                         news2=news.score, source="manual" if manual else "simulator",
                         nurse_id=rng.choice(NURSES) if manual else None))
            counts["vitals"] += 1
            if news.severity in ("medium", "high", "critical") and (
                    vt - last_alert.get(news.severity, start) > timedelta(hours=6)):
                last_alert[news.severity] = vt
                alert(bed, "news2", news.severity, vt + timedelta(seconds=20),
                      f"NEWS2 {news.score} ({news.severity}): HR {hr}, SpO2 {spo2}%, temp {temp}",
                      news.score, {"source": "rules", "score": news.score, "severity": news.severity,
                                   "parts": news.parts})
            vt += step
            k += 1

        # call button, nurse notes, AI summaries every other day
        d = admit
        while d < discharge:
            if rng.random() < 0.35:
                at = d + timedelta(hours=rng.uniform(1, 22))
                if at < discharge:
                    alert(bed, "call_nurse", "low", at, "Patient pressed the call button")
            for _ in range(rng.randint(1, 3)):
                at = d + timedelta(hours=rng.uniform(0.5, 23.5))
                if at < discharge:
                    db.add(Note(id=next(n_id), patient_id=p.id, author_id=rng.choice(NURSES),
                                text=rng.choice(NOTES), created_at=at))
                    counts["notes"] += 1
            if (d - admit).days % 2 == 0:
                at = d + timedelta(hours=7)
                reviewed = rng.random() < 0.55 + 0.4 * pos(at)
                db.add(AiSummary(id=next(s_id), patient_id=p.id, created_at=at,
                                 human_confirmed_by=DOCTOR if reviewed else None,
                                 ai_suggested={"summary": f"Stable stay in bed {bed}; vitals mostly in range.",
                                               "interactions": [], "source": "rules",
                                               "reviewed_at": (at + timedelta(hours=2)).strftime(
                                                   "%Y-%m-%dT%H:%M:%SZ") if reviewed else None}))
                counts["ai_summaries"] += 1
            d += timedelta(days=1)
        bed_free[bed] = discharge + timedelta(hours=rng.randint(2, 30))

    # appointment requests: confirmed by a doctor, cancelled, or refilled by the backfill (confirmed_by empty)
    t = start
    freed: list[datetime] = []
    while True:
        t += timedelta(hours=rng.uniform(4, 12))
        if t >= end - timedelta(hours=6):
            break
        p = rng.choice(patients)
        text_, symptoms = rng.choice(REQUESTS)
        fields = new_appointment_fields(p, text_, symptoms, today=t.date())
        a = Appointment(id=next(a_id), created_at=t, **fields)
        f = pos(t)
        wait = timedelta(days=rng.uniform(3, 12) * (1 - 0.45 * f))
        wait = min(wait, end - t - timedelta(hours=2))  # every slot is in the past too
        slot = (t + wait).replace(minute=0, second=0, microsecond=0)
        r = rng.random()
        if freed and r < 0.25 + 0.2 * f and freed[0] > t:  # takes a slot someone else cancelled
            a.status, a.slot_at, a.doctor_id = "confirmed", freed.pop(0), DOCTOR
        elif r < 0.85:
            a.status, a.slot_at, a.doctor_id = "confirmed", slot, DOCTOR
            a.confirmed_by = a.human_confirmed_by = DOCTOR  # as apply_confirm does
        else:
            a.status, a.slot_at, a.doctor_id = "cancelled", slot, DOCTOR  # booked, then cancelled
            a.confirmed_by = a.human_confirmed_by = DOCTOR
            freed.append(slot)
            freed.sort()
        freed = [s for s in freed if s > t]
        db.add(a)
        counts["appointments"] += 1
    db.flush()
    return counts


def main() -> None:
    from app.config import check_secrets, get_settings
    from app.db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=60, help="length of the history window (default 60)")
    ap.add_argument("--reset", action="store_true", help="remove only the rows this script created")
    args = ap.parse_args()
    check_secrets(get_settings())
    with SessionLocal() as s:
        if args.reset:
            print("removed", reset(s))
        else:
            out = generate(s, args.days)
            print("added", out) if any(out.values()) else print("history already present, nothing to do")
        s.commit()


if __name__ == "__main__":
    main()
