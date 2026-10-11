# Medora: business model and business plan

> **Status:** working draft for HackCure @ ESEN, 2026-10-11. Owner: Faouzi.
> Every figure marked *estimate* or *assumption* is ours and must be checked with a real customer before it goes on a slide as fact. Market figures carry their source in section 17.
> **The numbers live in [business-plan-financials.md](business-plan-financials.md)** (Wali): Tunisian prices, the 3-year model, scenarios and funding. This file tells the story and uses the same figures; if the two disagree, the financials file wins.

## 1. Medora in one sentence

Medora connects the patient, the nurse, the doctor and the administration around **one shared patient record**, and automates the repetitive parts of the patient journey: appointment triage, dose reminders at the bedside, early-warning alerts, shift handover and follow-up messages on WhatsApp. People stay in charge; the AI only suggests.

**What we sell:** time back to nurses and doctors, fewer missed doses and missed warnings, and a hospital that can prove it with numbers.

## 2. The problem

| Who | What hurts today |
|---|---|
| Nurses | Paper charts, vitals copied by hand, verbal shift handovers where details get lost, alarms with no follow-up trail |
| Doctors | No single view of a patient: vitals, doses, notes and exams live in different places; reports arrive as paper or PDF |
| Administration | Waiting lists managed by phone and paper; empty slots after cancellations; no figures to show the ministry or the board |
| Patients | Long waits, no idea when the next dose or appointment is, no simple way to ask a question in Arabic or French |

The context in Tunisia makes this the right moment:
- The Ministry of Health is rolling out hospital information systems and the electronic medical record in public hospitals, with a €27.3 M programme financed by AFD in 15 public hospitals (PACS, electronic health records, digital archives, individual drug distribution).
- A national health identifier and the citizen portal Sahetna.tn were announced for 2026.
- Telemedicine has a legal framework since the 2022 decrees.
- Hospitals are being asked to digitise; most wards still lack the tools at the bedside.

## 3. The solution (what exists today in the prototype)

| Module | What it does | Who confirms |
|---|---|---|
| Shared record | One patient record for 4 roles, every read written to an audit log | |
| Bedside unit | ESP32 + screen + servo pill holder + real-time clock: dose reminders work even offline; turns to the right pill slot | Nurse gives the dose |
| Vitals and early warning | NEWS2 score on every reading, alerts to the nurse, WhatsApp to the on-call team | Nurse acknowledges |
| Nurse-recorded vitals | A nurse types a reading on her round; it is scored and alerted like a sensor reading | |
| Appointment triage | Urgency suggestion with red-flag rules the AI cannot lower | Admin confirms the slot |
| Waitlist backfill | A cancelled slot is offered to the next patient automatically (n8n + WhatsApp) | Patient accepts |
| AI assistants | Doctor, nurse and patient assistants over the record and uploaded reports, multilingual, with citations | Doctor / nurse |
| Daily summary | Rules-based summary of the last 24 h, optional LLM rewrite | Doctor marks as reviewed |
| Shift handover (SBAR) | Draft handover per patient for the next shift | Outgoing nurse confirms |
| Health calendar and weather watch | Public-health days, heatwave and dust alerts with the patients most at risk | |
| Pilot impact dashboard | Measured indicators: alert response time, doses on time, wait to appointment | |
| Patient app | Phone and desktop: medicines of the day, vitals in plain words, appointments, assistant | |

Also built by the team (merged 2026-10-11):
- **Hospital pharmacy (Hedi):** pharmacist review of every prescription (allergy, dose and interaction checks), dispensing by lot with first-expiry-first-out, nurse receipt, stock with reorder alerts.
- **Radiograph reading (Wali):** a local vision model drafts a report for an X-ray image, including outside X-rays a patient brings; the doctor edits and confirms it.

**Honesty, which is also a selling point:**
- Vitals are simulated in the prototype; the bedside unit has no sensors yet.
- The AI is not clinically validated. On X-rays it only drafts a report that a doctor must edit and confirm; it never diagnoses.
- Everything runs on the hospital's own server.
- The demo works with the internet off.

## 4. Customers and segments

| Segment | Size in Tunisia | Why they buy | Sales cycle | Priority |
|---|---|---|---|---|
| **Private clinics** (polyclinics, cardiology, surgery) | ~110 clinics, 7,821 beds (INS 2023) | Quality image, medical tourism (Libya, Algeria, sub-Saharan Africa), nurse shortage, competition between clinics | 2–6 months, one decision maker | **1: beachhead** |
| **Public hospitals** (24 university hospitals, 33 regional, 109 district) | 22,888 public beds (INS 2022) | Ministry digitisation programme, need for figures, staff shortage | 12–24 months, public procurement (TUNEPS) | 2: through pilots and programmes |
| Home care and after discharge | Growing with chronic disease | Follow-up of discharged patients at home | short | 3 |
| Export (Maghreb, West Africa) | Libya, Algeria, Mauritania, Senegal | Same French/Arabic context, same gaps | after 2 references | 4 |

**Buyer and users in a clinic:**
- **Buyer:** the managing director or owner.
- **Champion:** the head nurse (surveillante générale).
- **Gatekeepers:** IT and the medical director.
- **Users:** nurses, doctors and patients.

## 5. Value proposition per person

| Person | Promise | How we prove it in a pilot |
|---|---|---|
| Clinic director | Fewer adverse events and missed doses, a modern image, figures for the board | Impact dashboard: doses on time, alert response time |
| Head nurse | Handover in minutes, no lost information, workload visible | Handover confirmed per shift, notes per shift |
| Doctor | Whole patient on one screen, summary ready in the morning | Summaries reviewed per day |
| Patient | Knows the next dose and appointment, asks in Arabic or French | Assistant questions answered, appointment confirmations |
| IT | Self-hosted, open standards (MQTT, REST), no patient data leaves | Architecture document, audit log |

## 6. Business model

**SaaS licence per monitored bed per month, plus the bedside unit, plus setup.** On-premise installation, so the hospital keeps its data.

| Line | What | Price (*assumption, to test with customers*) |
|---|---|---|
| Pilot | 1 ward, 10–20 beds, 3 months, setup, training, impact report | Free or at cost (hardware only), against a signed letter of intent and the right to publish the results |
| Core licence | Shared record, bedside reminders, NEWS2 alerts, handover, impact dashboard, patient app | **45 TND / bed / month** |
| AI and messaging pack | Assistants, daily summaries, triage, WhatsApp follow-up, health watch | **+20 TND / bed / month** (assumed taken on 60 % of beds) |
| Pharmacy pack | Prescription checks, drug catalogue, dispensing by lot (FEFO), stock and reorder | **+15 TND / bed / month** (assumed 50 % of beds) |
| Bedside unit | Lease (default), or sale | **+10 TND / bed / month** lease, or **250 TND** per unit sale |
| Setup | Server bundle, installation, training (2 days) | **3,000 + 50 TND per bed**, capped at 8,000 (5,000 for 40 beds) |
| Public hospitals | Same modules | **70 %** of the private price, annual licence |
| **Average** | | **74.5 TND / bed / month** excl. VAT, unit lease included |
| Support | Updates, remote support, quarterly impact report | Included; on-site support at day rate |

Why per bed:
- Hospitals already think in beds.
- The price scales with the value.
- Budgets are easy to compute: a 40-bed clinic on the average package pays **2,980 TND per month** excl. VAT, which is 1.4–2.0 % of the ward's bed revenue (financials, section 4).

**Public sector variant:**
- Annual licence per hospital through public procurement.
- Or a component inside a ministry or donor programme (for example the AFD hospital information system programme), where Medora is the bedside and nursing layer that the electronic record does not cover.

## 7. Unit economics

Full detail with shop-by-shop prices: [financials, sections 2 and 5](business-plan-financials.md).

| | Figure |
|---|---|
| Bedside unit, parts from Tunisian shops | **≈ 88 TND** (≈ 112 at the dearest shop) |
| Lease income per unit | 10 TND/month: the unit pays for itself in about 9 months |
| On-site server bundle (mini PC, UPS, backup disk) | 1,629 TND TTC, paid from the setup fee |
| 40-bed clinic: monthly revenue | 2,980 TND |
| Direct cost (WhatsApp messages, unit reserve) | 67 TND/month: gross margin **98 %** |
| Margin after support (1 technician per 10 clinics) | ≈ 2,785 TND/month |
| Net upfront cost of winning the clinic (units, setup, commission, travel) | ≈ 5,963 TND |
| **Payback** | **≈ 2 months** |

**What the clinic gets for it (the buyer's maths):** Medora costs the same as 1.2–2.0 experienced nurses, or 12–17 extra bed-days a month out of 840. It pays for itself if it fills about 2 % more bed-days, saves a little over one nurse's time across all shifts, or cuts expired stock. The pilot measures all three; we promise to measure, not to deliver.

Not in these figures: the GPU workstation that radiograph reading needs, quoted per site.

## 8. Market size

At the average price (74.5 TND/bed/month; public beds at 70 %). Detail: [financials, section 11](business-plan-financials.md).

| Level | Beds | Per year |
|---|---|---|
| Total market (Tunisia, all beds) | 30,709 (22,888 public + 7,821 private) | **≈ 21.3 M TND** |
| Reachable (all private beds + 30 % of public beds) | 14,687 | **≈ 11.3 M TND** |
| Target at the end of year 3 (700 private + 200 public beds) | 900 | **≈ 0.75 M TND** run rate, 6.7 % of the reachable market |

Beyond these figures:
- Export to the Maghreb multiplies the market several times.
- Algeria and Morocco have larger bed counts and the same languages.

## 9. Competition and positioning

| Player | What they do | Gap Medora fills |
|---|---|---|
| Hospital information systems (international and local editors, ministry programme) | Admissions, billing, electronic record | Weak at the bedside: no dose reminders, no early-warning loop, no nurse handover, little patient app |
| Med.tn, Tobba.tn and booking platforms | Appointment booking, teleconsultation | Outside the hospital; nothing for admitted patients |
| Patient monitor makers (Philips, GE, Mindray) | Certified monitors | Expensive per bed; data stays in the monitor; no shared workflow |
| Paper and Excel | The real competitor in most wards | Free, but no figures, lost information, no alerts |

**Positioning:**
- Medora is the **bedside and nursing workflow layer**: affordable, self-hosted, Arabic/French/English, works offline.
- It plugs into the record the hospital already has (REST, MQTT) instead of replacing it.

**What protects us:**
- The combined loop of device, alerts, handover and impact figures.
- Trilingual clinical content.
- Local presence and support.
- Pilot data that competitors do not have.

## 10. Regulation and compliance (to do before any real patient)

| Topic | What applies | Action |
|---|---|---|
| Personal and health data | Organic Law 2004-63; health data is sensitive and its processing needs **prior authorisation from the INPDP** (Decree 2007-3004) | File the declaration / authorisation request with the INPDP for the pilot site; data stays on the hospital's server; DPA contract with the hospital |
| Cross-border transfer | Only to adequate countries or with INPDP authorisation | Default: no transfer. The optional cloud LLM receives no names, phone numbers or IDs (already stripped); keep it off in the pilot unless authorised |
| Software as a medical device | The AI gives decision support, never a diagnosis; a person confirms every output, including the radiograph draft reports, which are the closest feature to a medical device | Keep this scope; check with the Ministry of Health's pharmacy and medicines directorate whether registration is needed; plan ISO 13485 / CE only when real sensors are added |
| Telemedicine | 2022 decrees | Only relevant if the doctor assistant is used for remote care |
| Information security | Hospital IT policy | Audit log (done), roles and access (done), backups, then ISO 27001 practices |
| Clinical honesty | No validated-AI claims | Keep "prototype, simulated vitals, AI not validated" in the UI and the pitch until a study exists |

## 11. Go-to-market plan

**Phase 0, now to 1 month: from hackathon to company**

| Step | Owner |
|---|---|
| Demo and pitch at HackCure; collect contacts of every doctor, clinic and judge interested | Faouzi |
| Register the company (SUARL or SARL) and apply for the **Startup Act label**: tax exemption, founder allowance, access to Startup Tunisia funding | Faouzi |
| Protect the name and brand (INNORPI); keep the code under a company licence | Faouzi |
| Turn the demo into a 5-minute video and a one-page brochure in French and Arabic | Faouzi |

**Phase 1, months 1–4: first pilot**

| Step | Owner |
|---|---|
| Sign 1 private clinic (cardiology or internal medicine ward, 10–20 beds) with a letter of intent | Faouzi |
| INPDP authorisation for the pilot | Faouzi |
| Build 20 bedside units; install the on-premise server | Wali (hardware, infra), Hedi (firmware) |
| Train nurses (2 sessions); the head nurse is the champion | All |
| Baseline measurement in week 0 (paper): handover time, missed doses, alert response | Faouzi |

**Phase 2, months 4–12: proof and first revenue**
- Publish the pilot impact report from the dashboard: before vs after, honest numbers.
- Convert the pilot into a paid contract.
- Sign 2–3 more clinics through referrals from the first one.
- Approach one public hospital through the ministry digitisation programme or a donor-funded project.
- Add real certified vital-sign sensors with a partner, as a separate regulated track.

**Phase 3, year 2–3: scale**
- 15 clinics and 2 public hospitals.
- First export customer (Libya or Algeria, through partner clinics).
- Distributor partnership with a medical equipment supplier.

**Channels:**
- Direct sales to clinics, with demos on site.
- Medical congresses and the nursing association.
- Medical equipment distributors.
- Public tenders (TUNEPS).
- Donor programmes (AFD, World Bank, EU).

## 12. Three-year projection (base case)

From [financials, section 8](business-plan-financials.md), where the monthly assumptions and the slow and fast cases are.

| TND | Year 1 | Year 2 | Year 3 |
|---|---:|---:|---:|
| Paying beds, end of year | 40 | 300 | 900 |
| Revenue | 17,410 | 193,430 | 575,030 |
| Gross margin | 83 % | 89 % | 93 % |
| EBITDA | −12,959 | −65,328 | **+74,755** |
| Team | 3 founders | 6 | 10 |
| Cash at end of year | 20,598 | 239,457 | 129,215 |

- EBITDA turns positive for good in **month 30** (month 26 in the fast case).
- The slow case (half the clinics, 3 months late) never breaks even in 36 months; its plan B is in the financials, section 9.

## 13. Funding and use of funds

| Source | What | When |
|---|---|---|
| Hackathon prizes, university incubator | Prototype to pilot | now |
| Startup Act label | Tax exemption, founder allowance for 1 year, patent cost support | months 1–3 |
| Startup Tunisia / Smart Capital funds, local VCs and accelerators | Seed investment | after the pilot results |
| Donor and innovation programmes (AFD Digital Africa, EU, World Bank health digitisation) | Grants, public-hospital pilots | months 3–12 |

**Amounts (financials, section 10):** 15 k TND from prizes and an incubator in month 1, a 30 k TND grant in month 4, the Startup Act allowance for the founders in year 1, then a **350 k TND seed round** in month 13.

**Use of the 350 k TND seed:**

| Share | Use |
|---|---|
| 60 % | Payroll for year 2 and early year 3: developer, sales, support, founders |
| 15 % | Bedside unit stock and servers for new sites |
| 15 % | Sales and marketing: commissions, demos, congresses |
| 10 % | Legal, INPDP, security, ISO 13485 groundwork |

## 14. Pilot success criteria (what we promise to measure, not the result)

Measured by the pilot impact dashboard, with a baseline taken before go-live:

| Indicator | Pilot target (*hypothesis*) |
|---|---|
| Median time from a high/critical alert to acknowledgement | under 5 minutes |
| Doses given on time | +15 points vs baseline |
| Missed doses per patient-day | −50 % |
| Shift handover time per nurse | −30 % |
| Time from appointment request to a confirmed slot | −40 % |
| Cancelled slots refilled | > 50 % |
| Nurse satisfaction (short survey) | ≥ 4 / 5 |

**Wording for the pitch:** "Medora automates the patient process; shorter waits are a result we will measure, not a promise."

## 15. Risks and how we handle them

| Risk | Impact | Mitigation |
|---|---|---|
| Long public procurement cycles | Slow revenue | Start with private clinics; enter the public sector through funded programmes |
| Data protection authorisation delays | Pilot blocked | Start the INPDP file in month 1; self-hosted design; no data transfer |
| Clinical liability of AI suggestions | Trust, legal | Human confirmation on every output, red-flag floor, audit trail, clear "decision support" scope |
| Nurse adoption | Low usage | Head nurse as champion, 2-minute workflows, Arabic interface, training, show their own figures |
| Hardware reliability | Missed reminders | Offline reminders from the device clock, watchdog, spare units on site |
| WhatsApp gateway (unofficial) | Number blocked | Low volume in the pilot; move to the official WhatsApp Business API or SMS for production |
| Competitors copy | Lost deals | Speed, local support, pilot data, integration with existing systems |
| Small team | Delivery risk | Clear lanes (product/AI, hardware, backend), first hires in support and sales |

## 16. The business to-do list (who does what next)

**This week (before and right after the pitch)**
- [ ] Faouzi: rehearse the pitch with sections 2, 6, 8 and 14 of this plan; add one slide "Business model" and one slide "Pilot plan".
- [ ] Faouzi: prepare a one-page brochure (French and Arabic) and the demo video.
- [ ] All: list 10 target clinics (name, city, ward, contact) and 3 public hospitals; each member brings personal contacts.
- [x] Wali: bedside unit costed with Tunisian shop prices (financials, section 2). Still to do: quotes for 20 and 100 units.
- [ ] Wali: write the one-page technical sheet for hospital IT (server specs, network, security, backup).

**Next month**
- [ ] Faouzi: company registration and Startup Act label application.
- [ ] Faouzi: INPDP declaration / authorisation request for the pilot site.
- [ ] All: 5 demos to clinics; target 1 letter of intent.
- [ ] Faouzi: test the price (45 + 20 + 15 + 10 TND/bed/month) in every demo and note the reaction; adjust section 6 and the financials.
- [ ] Hedi and Wali: build 20 units; define the sensor partner track.

**Questions the jury and buyers will ask (prepared answers)**

| Question | Answer |
|---|---|
| Who pays? | The clinic, per bed per month; the public hospital, through procurement or a funded programme |
| How much? | 74.5 TND per bed per month on average, unit lease included; 2,980 TND a month for a 40-bed clinic; pilot free against a letter of intent |
| Why not an existing hospital system? | They stop at the desk; Medora works at the bedside and plugs into them |
| Is the AI safe? | It only suggests; red-flag rules set a floor; a person confirms; everything is logged |
| Where is the data? | On the hospital's server; nothing leaves; INPDP authorisation is part of onboarding |
| Where are the sensors? | Simulated in the prototype through the same MQTT contract; certified sensors come through a partner as a regulated step |
| How do you make money in year 1? | First paid clinic after a 3-month pilot, a second in month 10, plus setup fees: 17 k TND. Break-even is month 30 |

## 17. Sources

- [INS / Kapitalis: hospital beds in Tunisia, public 22,888 (2022), private 7,821 (2023)](https://kapitalis.com/tunisie/?p=12906017)
- [Oxford Business Group: Tunisian health sector structure (university, regional, district hospitals; private clinics)](https://oxfordbusinessgroup.com/overview/annual-check-solid-foundation-sector-ready-overhaul)
- [Statista: public health facilities in Tunisia by type](https://www.statista.com/statistics/1194048/number-of-public-health-facilities-in-tunisia-by-type)
- [AFD: e-health strategy in Tunisian public hospitals (€27.3 M, 15 hospitals)](https://www.afd.fr/en/carte-des-projets/rebalancing-access-healthcare-implementing-e-health-strategy-public-hospitals)
- [UNESCWA: Tunisia digital health development programme](https://andp.unescwa.org/plans/1501)
- [Sahetna.tn and the national health identifier (2026)](https://www.capmad.com/post/mustapha-ferjani-finalises-sahetnatn-tunisias-national-electronic-medical-record-portal)
- [DLA Piper: data protection in Tunisia (Law 2004-63, INPDP)](https://www.dlapiperdataprotection.com/?t=law&c=TN)
- [Decree 2007-3004 (declaration and authorisation of processing)](https://www.knobbe.com/sites/default/files/2021-04/Tunisia_2007-3004.pdf)
- [Startup Act: label and benefits](https://startup.gov.tn/en/startup_act/discover)
- [Startup Genome: Tunisia ecosystem](https://startupgenome.com/ecosystems/Tunisia)
- [Med.tn (Dealroom)](https://app.dealroom.co/companies/med_tn) and [Tobba.tn (We Are Tech Africa)](https://www.wearetech.africa/fr/fils/solutions/tunisie-tobba-tn-une-solution-de-sante-numerique-accessible-a-tous)
- [Remote patient monitoring pricing benchmarks (US, for comparison only)](https://www.mindbowser.com/cost-of-remote-patient-monitoring/)

Exchange rates used for rough conversions: 1 USD ≈ 3.1 TND, 1 EUR ≈ 3.4 TND (approximate).
