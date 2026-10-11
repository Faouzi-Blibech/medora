# Pitch deck

Deck (private to Faouzi until shared from its Share menu): https://claude.ai/artifact/Md1Vc75fSnt4JXnqsjgUcY
It downloads as PowerPoint or PDF. Speaker notes are on every slide.

Updated for the reduced hardware (PR #13: ESP32 + OLED + servo + DS1307, no sensors; the simulator sends the vitals).

Name: **Medora**. Renaming = edit the cover, the footers and the deck title.

## Outline (10 slides, about 6 minutes with the live demo)

| # | Slide | Point |
|---|---|---|
| 1 | Cover | Medora: the patient journey, connected |
| 2 | Problem | Long waits, paper records, no shared record |
| 3 | Solution | Medora automates the patient process; four roles, one record |
| 4 | Journey | The 8-step golden path; switch to the live demo here (TEAM_PLAN.md section 5) |
| 5 | Bedside unit | ESP32 + OLED + servo + clock (Wokwi): offline reminders, servo pill holder; vitals and badge taps simulated |
| 6 | AI | Six modules: what each suggests, who confirms, what happens if the AI is down |
| 7 | Architecture | Everything on the hospital's own server |
| 8 | Privacy and honesty | Self-hosted, audit log, anonymised AI, INPDP; vitals simulated, AI not validated |
| 9 | Impact | What a pilot ward would measure; shorter waits are a result, not a promise |
| 10 | Team | Roles and role owners; Q&A |

## Fill in before presenting

- [ ] Slide 2: a source for the "6–12 months" wait, or drop the number
- [ ] Slide 5: a Wokwi screenshot of the bedside unit, or a photo if the real board is built (upload it in the deck editor)
- [ ] Slide 9: baselines `[__%]`, `[__ days]`, `[__ min]` if a partner hospital gives figures; otherwise present them as "what we would track"
- [ ] Slide 10: Hedi's and Wali's full names, contact email
- [ ] The project name, if it changes

## Q&A prep

- **Cost:** [cost per unit] for the bedside unit (ESP32, OLED, servo, clock module); certified sensors would add to it in production.
- **Where are the sensors?** Vitals and badge taps are simulated in this prototype (`simulator/`). They travel over the same MQTT contract real certified sensors would use, so adding them changes the device, not the system.
- **Scale:** one server per hospital, more devices on the same broker.
- **Data residency:** everything on-premise, n8n included; cloud AI is optional and receives no names or IDs.
- **AI is wrong:** red-flag rules set a floor the AI cannot lower, and a person confirms every output.
- **Offline:** dose reminders keep firing from the device's clock; readings replay on reconnect.
