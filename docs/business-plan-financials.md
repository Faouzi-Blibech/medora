# Ward: business plan with Tunisian prices and a 3-year financial model

> **Status:** draft, 2026-10-11. Companion to [business-plan.md](business-plan.md), which covers the problem, the solution, the competition and the go-to-market story. This file holds the numbers.
> **Prices** are real Tunisian prices found online in October 2026. The store or source is named on each line, and links are in section 14. Lines marked *est.* are our own estimates and must be replaced with a quote.
> **Currency:** amounts are in TND and exclude VAT unless marked TTC. Exchange rates on 5 October 2026 (BCT): 1 EUR = 3.369 TND, 1 USD = 3.006 TND.

---

## 1. Summary

| | |
|---|---|
| **What we sell** | A per-bed monthly subscription for the bedside and nursing layer of a hospital: shared record, bedside dose reminders, NEWS2 alerts, handover, pharmacy and AI assistants. The bedside unit is leased and the system is installed on the hospital's own server. |
| **First customers** | Private clinics in Tunisia: about 110 clinics and 7,821 beds |
| **Average price** | **74.5 TND per bed per month** excluding VAT, bedside unit lease included |
| **Bedside unit cost** | **≈ 88 TND** per unit, built from parts bought in Tunisian shops |
| **Cost to a 40-bed clinic** | 2,980 TND/month excl. VAT. That is 1.4–2.0 % of the ward's bed revenue. |
| **Base case targets** | 40 paying beds at the end of year 1, 300 at the end of year 2, 900 at the end of year 3 |
| **Revenue** | Year 1: 17 k TND. Year 2: 193 k TND. Year 3: 575 k TND. |
| **EBITDA break-even** | Month 30 in the base case, month 26 in the fast case |
| **Funding** | Year 1: 45 k TND from prizes, an incubator and a grant, while the founders live on the Startup Act allowance. Then a **350 k TND seed round** at the start of year 2. |
| **Lowest cash after the seed** | 113 k TND, a safety buffer of about 3 months of year-3 costs |

---

## 2. Bedside unit: bill of materials with Tunisian prices

Prices are for single units bought from Tunisian online shops (TTC). Buying 100 units would bring them down; we kept retail prices to stay conservative.

| Part | Price (TND TTC) | Cheapest source found | Other Tunisian prices seen |
|---|---:|---|---|
| ESP32-C3 SuperMini | 12.000 | Seli.tn | 2BTrading 19.900; Didactico 32.000 |
| 0.96" OLED SSD1306, I2C | 17.000 | Little-son.tn | Souilah 17.500; Didactico 18.000; Best Buy Tunisie 16.500 (old listing) |
| DS1307 RTC module with a CR2032 cell | 4.800 | CoThings | 2BTrading 4.750; Didactico 7.800; Souilah 8.000; Jumia 10.990 |
| SG90 micro servo, 180° | 6.900 | CoThings | Hobbystart, Seli and Souilah 7.000; Didactico 7.300; ES Online 8.500 |
| 5 V 2 A power adapter | 10.000 | Spacenet.tn | |
| USB-C cable, 1 m | 5.900 | Spacenet.tn | |
| 3D-printed case and 4-slot pill disc, about 120 g of PLA | 15.000 | *est.*: a Bambu PLA refill costs 85 TND at 3dprint.tn, and we add machine time | |
| Wires, perfboard, screws | 8.000 | *est.* | |
| Assembly and test, 30 minutes | 8.000 | *est.* | |
| **Total per unit** | **≈ 87.6** | | **≈ 112** at Didactico prices |

Two extra costs come on top:
- **Spare units:** we keep 10 % extra on each site, so a 40-bed clinic needs 44 units, or **3,854 TND** of hardware.
- **Replacement reserve:** we assume 5 % of the units are replaced each year, about 0.37 TND per bed per month.
- **Not included:** shipping, which is about 8 TND per order (Aramex at CoThings) and free above 150 TND at Souilah.

**On-site server for a clinic:**

| Item | TND TTC | Source |
|---|---:|---|
| Mini PC BMAX B6 Pro, i5 / 16 GB / 512 GB SSD | 1,029 | Mytek; 999 at Zoom.com.tn |
| Small UPS | 350 | *est.* |
| Backup SSD | 250 | *est.* |
| **Server bundle** | **1,629** | |

> **Radiograph reading (AI pack):** the local vision model needs a GPU workstation, which this bundle does not include. We quote it per site and leave it out of the model below.

---

## 3. Pricing

Prices are per bed per month, excluding VAT. Tunisian VAT of 19 % is added on the invoice.

| Line | Price | What's included | Share of beds that take it (assumption) |
|---|---:|---|---:|
| Core licence | **45** | Shared record, bedside reminders, NEWS2 alerts, nurse-recorded vitals, SBAR handover, impact dashboard, patient app | 100 % |
| AI and messaging pack | **+20** | Assistants, daily summary, appointment triage, WhatsApp follow-up, health watch | 60 % |
| Pharmacy pack (new) | **+15** | Prescription checks, drug catalogue, dispensing with the soonest-expiring lot first (FEFO), stock, reorder | 50 % |
| Bedside unit lease | **+10** | The unit, spares, replacement and firmware updates | 100 % |
| **Average revenue per bed** | **74.5** | 45 + 20 × 0.6 + 15 × 0.5 + 10 | |
| Setup, one time | **3,000 + 50 per bed**, capped at 8,000 | Server bundle, installation, 2 days of training | A 40-bed clinic pays 5,000 |
| Public hospitals | **70 %** of the private price | Annual licence through TUNEPS procurement or a donor programme | |

Two differences from [business-plan.md](business-plan.md):
- That plan assumed 65 TND per bed on the full package. Here the **pharmacy pack** is a new line, and the AI and pharmacy packs are optional, which gives an average of 74.5 TND.
- **The lease pays for the unit:** a unit costs about 88 TND and earns 10 TND a month, so it pays for itself in about 9 months.

---

## 4. Value for the clinic (the buyer's maths)

Example: a **40-bed clinic** taking the average package at **2,980 TND/month excl. VAT**, or 3,546 TND TTC.

| Comparison | Figure | Source |
|---|---|---|
| Price of a hospital bed-day in a private clinic | 180–250 TND/day | cliniquetunisie.com, cliniques.tn (directories, not official prices) |
| Ward's monthly bed revenue at 70 % occupancy | 151,200–210,000 TND | 40 beds × 30 days × 70 % × day price |
| **Ward's cost as a share of that revenue** | **1.4–2.0 %** | |
| Bed-days that pay for Ward | **12–17 extra bed-days a month** across the ward, out of 840 | 2,980 ÷ 180 or 250 |
| Employer cost of an experienced private nurse | 1,515–2,565 TND/month | 1,300–2,200 gross (Tanitjobs 2026 salary guide) plus 16.57 % CNSS |
| **Ward in nurse terms** | The employer cost of **1.2–2.0** experienced nurses | |

**How to say it to a clinic director:** Ward pays for itself if it helps you do one of these:
- Fill about 2 % more bed-days.
- Save a little over one nurse's worth of time on the ward, across all shifts.
- Throw away less expired stock.

The pilot measures all three before and after go-live. We promise to measure the gains, not to deliver them.

---

## 5. Unit economics for a 40-bed clinic

| | TND |
|---|---:|
| Monthly recurring revenue | 2,980 |
| Monthly direct cost (WhatsApp messages at about 0.0216 TND each × 60 per bed, plus the unit reserve) | 67 |
| **Monthly gross margin** | **2,913 (98 %)** |
| Support allocation (one technician for every 10 clinics) | about 128 |
| **Monthly margin after support** | **≈ 2,785** |
| Upfront hardware: 44 units | 3,854 |
| Setup fee received minus setup cost (5,000 − 2,629) | −2,371 |
| Sales commission (one month of recurring revenue) plus demo travel (*est.*) | 2,980 + 1,500 |
| **Net upfront cost of winning a clinic** | **≈ 5,963** |
| **Payback period** | **≈ 2 months** of gross margin |

WhatsApp pricing source: Messaggio quotes 0.0064 EUR per utility message in Tunisia, and another aggregator gives 0.004 USD. Meta charges utility messages without a free tier from 1 October 2026. We use the higher figure.

---

## 6. Team and salaries

Salaries are gross per month, taken from the Tanitjobs 2026 salary guide. We add the employer's CNSS contribution of **16.57 %** (Africarrières breakdown); one source gives about 17.6 %, so check this with an accountant.

| Role | Gross TND/month | Market range (Tanitjobs 2026) | Starts | Cost per year incl. CNSS |
|---|---:|---|---|---:|
| 3 founders, year 1 | 0 paid by Ward | Startup Act allowance from ANETI: 1,000–5,000 net/month per founder, for 1 year and up to 3 founders | Month 1 | 0 |
| 3 founders, year 2 | 2,500 each | | Month 13 | 104,913 |
| 3 founders, year 3 | 3,000 each | | Month 25 | 125,895 |
| Full-stack developer, junior | 1,800 | 1,400–2,200 | Month 13 | 25,179 |
| B2B sales and clinical success | 1,400 + commission | 900–1,400 + variable pay | Month 14 | 19,584 |
| Installer and support technician | 1,100 | 900–1,400 | Month 15 | 15,387 |
| Developer, experienced | 3,000 | 2,000–4,000 | Month 25 | 41,965 |
| B2B sales #2 | 1,500 | | Month 26 | 20,983 |
| Support technician #2 | 1,100 | | Month 27 | 15,387 |
| Clinical specialist (a nurse) | 1,800 | 1,300–2,200 | Month 28 | 25,179 |

Headcount: 3 people in year 1, 6 in year 2 and 10 in year 3.

The yearly cost column assumes 12 monthly salaries. If a collective agreement adds extra monthly payments, add them.

**Upside not counted:** under the Startup Act, the State pays the employer and employee CNSS contributions for labelled startups. The model still pays 16.57 % to stay conservative.

---

## 7. Operating costs

Amounts are per month unless marked one-off.

| Item | Year 1 | Year 2 | Year 3 | Source |
|---|---:|---:|---:|---|
| Office: coworking at about 300 TND per seat | 900 (3 seats) | 1,800 (6) | 3,000 (10) | Tunis fixed desks cost 185–400 TND/month (Workin.space, Proxity, freelances.tn); Regus starts at 340 |
| Accountant | 300 | 300 | 300 | *est.*: the Order of Chartered Accountants (OECT) reference rate is 1,500 TND excl. VAT per day, so this buys about 2.4 days a year |
| Tools, internet, phones | 200 | 500 | 800 | *est.* |
| Travel to clinics and demos | 250 | 1,000 | 2,000 | *est.* |
| Marketing: brochures, congress stands, video | 170 | 1,250 | 2,500 | *est.* |
| Legal and compliance: INPDP files, contracts, data processing agreements | 250 | 670 | 1,250 | *est.* |
| ISO 13485 groundwork | – | – | 3,300 | *est.*: about 40 k TND a year with a consultant |
| One-off: company registration (SUARL/SARL) | 2,000 | | | 700–2,500 TND depending on who does it (Copeps); legal notice 50 TND (RNE); 1,000 TND minimum capital, which stays in the company's bank account |
| One-off: trademark | 500 | | | *est.*: the INNORPI prior-art search costs 36 TND, and a trademark lasts 10 years |

---

## 8. Three-year financial plan, base case

Month 1 is the first month after registration, January 2027 if we register in November or December 2026.

**Sales plan (base case):**
- **Months 4–6:** a free pilot on 20 beds.
- **Year 1:** the pilot converts to a paid contract in month 7, and a second 20-bed contract follows in month 10.
- **Year 2:** six new clinics of 40 beds and one of 20.
- **Year 3:** ten new clinics of 40 beds, plus a 200-bed public hospital in month 30.

**Payment terms:** clinics pay 2 months after the invoice and the public hospital 6 months after.

| TND | Year 1 | Year 2 | Year 3 |
|---|---:|---:|---:|
| Paying beds, end of year | 40 | 300 | 900 |
| Average paying beds | 15 | 178 | 613 |
| Recurring revenue (licences and lease) | 13,410 | 159,430 | 517,030 |
| Setup fees | 4,000 | 34,000 | 58,000 |
| **Revenue** | **17,410** | **193,430** | **575,030** |
| Cost of sales: messaging, unit reserve, setup servers | 3,029 | 21,966 | 41,173 |
| **Gross margin** | 14,381 (83 %) | 171,464 (89 %) | 533,857 (93 %) |
| Payroll incl. CNSS (part of operating costs) | 0 | 160,867 | 278,952 |
| Operating costs incl. payroll and commissions | 27,340 | 236,792 | 459,102 |
| **EBITDA** | **−12,959** | **−65,328** | **+74,755** |
| Capital spending: bedside units and the pilot server | 5,483 | 25,054 | 57,816 |
| Funding received | 45,000 | 350,000 | 0 |
| **Cash at end of year** | **20,598** | **239,457** | **129,215** |
| Lowest cash during the year | 6,290 (month 3) | 239,457 | 112,822 |
| Monthly recurring revenue in month 12 of the year | 2,980 | 22,350 | 62,580 |

- **Break-even:** EBITDA turns positive for good in **month 30**.
- **Run rate:** at the end of year 3 recurring revenue reaches 751 k TND a year.
- **Funding need:** with no funding at all, the cumulative cash need peaks at **282 k TND**. The 350 k seed round covers that and leaves a buffer.
- **Corporate tax:** none in the plan. The Startup Act label exempts corporate tax for up to 8 years. Without the label, the rate is 15 % according to tax aggregators, though the Tunisian press describes 20 % as the standard rate; check with an accountant.
- **Depreciation:** left out because the plan reports EBITDA; capital spending is shown as cash.

---

## 9. Scenarios

| | Slow | **Base** | Fast |
|---|---|---|---|
| What changes | Half the clinics, each 3 months late, and only the experienced developer is hired in year 3 | Section 8 | One extra 40-bed clinic for every three in the base case |
| Paying beds, end of year 3 | 340 | **900** | 1,140 |
| Revenue in year 3 | 227,640 | **575,030** | 747,010 |
| EBITDA in year 3 | −183,295 | **+74,755** | +226,862 |
| Break-even month | not within 36 months | **30** | 26 |
| Cash at the end of month 36 | **−63,261** | **129,215** | 262,899 |

**Plan B if the slow case happens:**
- **Trigger:** fewer than 140 paying beds by month 24.
- **First:** freeze the year-3 hires.
- **Then:** keep the founders' pay at the year-2 level.
- **Fund the public hospital pilot with a grant:** AFD, the EU or the World Bank (see business-plan.md section 13).
- **Sell the units instead of leasing them:** a sale at 250 TND brings cash in upfront.

These steps keep cash positive. The model's slow case already includes the hiring freeze, so the other measures are what close the 63 k gap.

---

## 10. Funding and use of funds

| When | Source | Amount (TND) | Use |
|---|---|---:|---|
| Month 1 | Hackathon prize, university incubator | 15,000 | Company registration, trademark, pilot preparation |
| Month 4 | Innovation grant or competition | 30,000 | Pilot hardware (20 units and the server), INPDP file, travel |
| Months 1–12 | Startup Act founder allowance, paid by the State through ANETI | outside the company accounts | The founders' living costs in year 1 |
| Month 13 | **Seed round**: Smart Capital / Startup Tunisia funds, local VCs, business angels | **350,000** | See below |

**Planned use of the 350 k TND seed:**

| Share | Amount | Use |
|---:|---:|---|
| 60 % | 210,000 | Payroll for year 2 and the start of year 3: developer, sales, support, founders |
| 15 % | 52,500 | Bedside unit stock and servers for new sites |
| 15 % | 52,500 | Sales and marketing: commissions, demos, congresses |
| 10 % | 35,000 | Legal, INPDP, security, ISO 13485 groundwork |

---

## 11. Market size

The figures use average revenue per bed. Bed counts are from the INS: 7,821 private beds (2023) and 22,888 public beds (2022). Another source gives 7,178 private beds for 2023.

| Level | Beds | Revenue per year (TND) |
|---|---:|---:|
| **TAM:** all beds in Tunisia, public at 70 % of the price | 30,709 | **21.3 M** |
| **SAM:** all private beds plus 30 % of public beds | 14,687 | **11.3 M** |
| **SOM:** base-case target at the end of year 3 (700 private + 200 public beds) | 900 | **0.75 M** run rate, which is 6.7 % of the SAM |

Export to Libya, Algeria and the rest of the Maghreb is outside these figures.

---

## 12. Taxes, legal and administration

| Topic | Rule | Effect on the plan |
|---|---|---|
| Company form | SUARL or SARL; minimum capital 1,000 TND | Registration in month 1 |
| Startup Act label (Law 2018-20) | Corporate tax exemption, the State pays CNSS contributions, a 1-year allowance for up to 3 founders, valid for up to 8 years from registration | Apply in months 1–3. A 2026 reform that would extend the label to 10 years is announced but not confirmed. |
| VAT | Standard rate 19 % (PwC). Reduced rates of 7 % and 13 % apply only to listed operations. | Invoices add 19 % on top of the prices above |
| Employer CNSS | 16.57 % of gross pay, capped at 5 times the minimum wage (SMIG) | Included in payroll |
| Minimum wage | SMIG for a 48-hour week: 554.736 TND gross from 1 January 2026, then 611.520 by 2028 | Floor for any hire |
| Health data | Law 2004-63 and Decree 2007-3004: prior INPDP authorisation before processing health data | File for the pilot site in month 1 |
| Trademark | INNORPI; 10 years, renewable | Month 1 |

---

## 13. What to verify before this goes on a slide

**Get real quotes:**
- [ ] Unit parts for 20 and 100 units from Seli, CoThings and 2BTrading, then update section 2.
- [ ] 3D printing cost for the case.
- [ ] A UPS for the server bundle.
- [ ] A GPU workstation for radiograph reading.

**Check with an accountant:**
- [ ] The CNSS rate.
- [ ] The corporate tax rate outside the Startup Act.
- [ ] Monthly accounting fees.
- [ ] How the Startup Act CNSS coverage works in practice.

**Check with Meta or a WhatsApp provider:**
- [ ] The Tunisia rate per utility message.

**Test with customers:**
- [ ] Ask 5 clinics in demos about the 45 + 20 + 15 + 10 price and the 70 % public discount.
- [ ] Ask one clinic for its real bed-day price, occupancy and nurse salaries, to replace the directory figures in section 4.

**Check the market figure:**
- [ ] Private bed count: 7,821 or 7,178.

## 14. Sources

**Exchange rate:**
- [BCT rates, 5 October 2026 (Tunisie Numérique)](https://www.tunisienumerique.com/taux-de-change-tunisie-2026-10-05/)

**Bedside unit parts:**
- [ESP32-C3 SuperMini, Seli.tn](https://seli.tn/product/esp32-c3-supermini-carte-de-developpement-esp32-c3-supermini/)
- [ESP32 boards, Didactico](https://didactico.tn/categorie-produit/carte-programmable/modules-iot/cartes-esp32/)
- [ESP32-C3 board, 2BTrading](https://2btrading.tn/cartes-de-developpement/9407-carte-de-developpement-esp32-c3.html)
- [OLED displays, Little-son.tn](https://little-son.tn/79-afficheurs)
- [OLED 0.96" I2C, Didactico](https://didactico.tn/shop/composants-electroniques/optoelectronique/afficheurs-lcd-graphiques/ecran-oled-bleu-0-96i2c-ssd1306-4pin-vcc-gnd/)
- [OLED, Souilah Électronique](https://souilah-electronique.tn/modules-et-capteurs/377-afficheur-12864-lcd-oled-ssd1306-i2c-096-bleu-et-jaune.html)
- [DS1307 with CR2032, CoThings](https://cothings.net/products/module-dhorloge-en-temps-reel-rtc-ds1307-24c32-avec-pile-cr2032)
- [DS1307, 2BTrading](https://2btrading.tn/accueil/454-module-horloge-i2c-module-rtc-temps-reel-ds1307-24c32.html)
- [DS1307, Didactico](https://didactico.tn/produit/module-rtc-ds1307/)
- [SG90 servos, CoThings](https://cothings.net/collections/servomoteurs)
- [SG90, Hobbystart](https://hobbystart.tn/product/servo-moteur-sg90/)
- [SG90 180°, Didactico](https://www.didactico.tn/produit/servomoteur-sg90-9g-180-degres/)
- [5 V 2 A adapter, Spacenet](https://spacenet.tn/chargeur-pc-portable/87023-chargeur-secteur-adaptable-5v-2a-noir.html)
- [USB-C cable, Spacenet](https://spacenet.tn/cable-chargeur/100529-cable-chargeur-xo-nb265-type-c-blanc.html)
- [PLA filament, 3dprint.tn](https://3dprint.tn/boutique/)

**Server:**
- [BMAX mini PCs, Mytek](https://www.mytek.tn/bmax)
- [BMAX B6 Pro, Zoom.com.tn](https://zoom.com.tn/unite-centrale/17262-mini-pc-bmax-b6-pro-i5-1030ng7-16go-512gossd-win11.html)

**Salaries and payroll:**
- [Tanitjobs: salaries in Tunisia 2026 by sector and job](https://www.tanitjobs.com/blog/675/salaires-tunisie-2026-guide-complet-secteur-metier/)
- [Tunisie Numérique: public-sector nurse pay](https://www.tunisienumerique.com/1090377-2/)
- [Africarrières: employer charges in Tunisia (CNSS 16.57 %)](https://africarrieres.com/tunisie/fr/guide/employeur-entreprise/charges-employeur)
- [FMC Group: total cost of employment](https://fmcgroup.com/fr/total-cost-of-employment-tunisia/)
- [Business News: SMIG raised (30 April 2026)](https://businessnews.com.tn/2026/04/30/tunisie-le-smig-revu-a-la-hausse/1399410/)
- [FIPA: cost of factors, January 2025](https://investintunisia.tn/wp-content/uploads/2025/01/Couts-des-facteurs-FIPA-FR-Janvier-2025-1.pdf)

**Clinic prices and bed counts:**
- [Clinic prices, cliniquetunisie.com](https://www.cliniquetunisie.com/tarifs.html)
- [Clinic prices, cliniques.tn](https://www.cliniques.tn/)
- [Kapitalis / INS: bed counts](https://kapitalis.com/tunisie/?p=12906017)

**Messaging:**
- [WhatsApp pricing in Tunisia, Messaggio](https://messaggio.com/pricing-whatsapp/tunisia/)
- [WhatsApp API rates by country, Whautomate](https://whautomate.com/whatsapp-business-api-pricing)
- [Changes from 1 October 2026, EngageLab](https://www.engagelab.com/blog/whatsapp-business-api-pricing)

**Office and company setup:**
- [Coworking prices in Tunis, Workin.space](https://workin.space/en/tunisia/tunis)
- [Office rental guide, Proxity](https://proxity.tn/location-bureau-tunisie/)
- [Coworking spaces, freelances.tn](https://www.freelances.tn/blog/conseils-freelance/le-tour-de-tunisie-des-meilleurs-espaces-de-coworking-pour-freelances-2)
- [Regus Tunis](https://www.regus.com/fr-fr/tunisia/tunis)
- [SUARL registration procedure, Idaraty (RNE)](https://www.idaraty.tn/public/fr/procedures/creation-societe-unipersonnelle-a-responsabilite-limitee-suarl-rne)
- [Minimum capital for a SARL, Copeps](https://copeps.fr/actualites/capital-minimum-sarl-tunisie/)
- [Costs of starting a small company, Copeps](https://copeps.fr/actualites/petite-entreprise-tunisie/)
- [OECT reference fees (Managers.tn)](https://managers.tn/?p=49217)
- [INPI country sheet on Tunisia, 2025 (INNORPI)](https://www.inpi.fr/sites/default/files/2025-09/Fiche%20PI%20Tunisie%202025.pdf)

**Startup Act:**
- [Startup Act guide (bourse amounts)](https://uploads-ssl.webflow.com/60e6bc58a4328775758e87d0/61e57188783deb6c013d8e9b_Guide%20StartupAct%20.pdf)
- [Deloitte: Startup Act summary](https://blog.avocats.deloitte.fr/tunisie-breves-fiscales-juridiques/)
- [Ministry of Communication Technologies: label procedure](https://www.mtc.gov.tn/fileadmin/StartupAct/Startup_Act_-_procedures_conditions_obtention_du_label.pdf)
- [Proposed 2026 amendments (not confirmed)](https://maitre-haifaguedhami.me/actualites/startup-act-tunisie-amendements-2026)

**Taxes:**
- [PwC: other taxes in Tunisia (VAT)](https://taxsummaries.pwc.com/tunisia/corporate/other-taxes)
- [Business News: IACE proposals for the 2026 Finance Law (corporate tax)](https://businessnews.com.tn/2025/11/24/plf-2026-les-seize-recommandations-de-liace-pour-alleger-la-pression-fiscale/1374542/)
- [Corporate tax rate, taxratesbycountry](https://taxratesbycountry.com/fr/corporate-tax-in-tunisia/)
