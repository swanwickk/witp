# War in the Pacific: Admiral's Edition (WitP-AE) - Master Cheatsheet & Decision Tables

A high-density operational cheatsheet capturing core decision trees, combat thresholds, ratios, and heuristics from the manual.

---

## 1. Quick Decision Rules

| Situation | Action to Take | Why / Rule Mechanism |
|---|---|---|
| **TF approaching enemy carrier umbrella** | Set TF Speed to *Mission Speed*, order 100% Fighter CAP, alter path via Waypoints | Avoid daytime dive/torpedo bomber ambush; maximize CAP interception. |
| **Port Level 0–1 with urgent troop need** | Dispatch *Fast Transport TF* (DD/APD) during Night phase only | Conventional AK/AP cannot unload fast enough; will be destroyed at beachhead by dawn airstrikes. |
| **Enemy base has Fort Level ≥ 3** | NEVER launch Shock Attack; use *Bombardment Attack* then *Deliberate Attack* | Shock attack against Fort 3+ doubles defender lethality, shattering attacker AV and cohesion. |
| **Pilot Fatigue reaches 30+** | Rotate squadron to *Rest / Training* (0% combat mission) | Fatigue > 30 exponentially spikes operational crash rates and slashes dogfight survival. |
| **Airbase aircraft count > Base Capacity** | Ferry surplus squadrons to rear bases immediately | Overstacking penalty causes massive maintenance backlogs, abortive sorties, and vulnerability to ground strafing. |
| **Warship Flotation (FLT) damage > 50** | Form single-ship TF with 1–2 DD escorts; steer for nearest Port Level ≥ 3 at *Cruise Speed* | High speed increases water intake per turn; solitary transit minimizes formation drag and collision risks. |
| **Target base has high Coastal Guns (CD)** | Bombard with Battleships (BB) at night; suppress CD guns before bringing transports into beachhead | Coastal artillery tears unarmored amphibious transports to pieces during daylight landing phases. |
| **Japanese Heavy Industry (HI) running low on fuel** | Prioritize tanker convoys from Palembang/Miri directly to Tokyo/Kobe | 1 HI requires 1 Oil/Fuel + 2 Resources daily. If fuel fails, HI halts, stopping supply & R&D generation. |

---

## 2. Thresholds & Numerical Standards

### Air Operations Thresholds
- **Airbase Aircraft Capacity**: Base Level × 50 aircraft (e.g., Level 3 airfield supports 150 aircraft). Overstacking triggers severe ops losses.
- **Aviation Support Ratio**: Exactly **1 Aviation Support Point per Engine** (Single-engine fighter = 1 pt; twin-engine bomber = 2 pts; 4-engine bomber = 4 pts). Deficits degrade serviceability.
- **Pilot Fatigue Limits**:
  - `0–15`: Optimal combat readiness.
  - `16–30`: Acceptable for ongoing campaigns; minor accuracy decay.
  - `31–50`: Severe operational risk; sorties suffer heavy non-combat losses.
  - `> 50`: Grounded or combat-ineffective; mandatory rest required.
- **Fighter Sweep Altitude Advantage**: Always cruise **2,000–3,000 feet higher** than expected enemy CAP altitude to claim diving energy modifier.

### Naval Operations Thresholds
- **Port Docking Limits**:
  - `Port Level 1–2`: Very small (coastal craft, sub chasers, barges). Large ships cannot dock; must lighter cargo.
  - `Port Level 3–4`: Minor port. Destroyers, minor escorts, and small freighters can dock.
  - `Port Level 5–6`: Major naval facility. Cruisers, medium merchantmen dock; basic repair capabilities.
  - `Port Level 7+`: Fleet base. Battleships, fleet aircraft carriers dock; drydocking and heavy system repairs available.
- **Task Force Escort Ratio**: Minimum **1.5 DD/DE per capital warship** (CV, BB, CA) or major merchantman (AK, AP).
- **Damage Assessment Limits**:
  - `FLT ≥ 50`: Vessel in critical danger of foundering. Limit speed to 5–8 knots (Cruise).
  - `SYS ≥ 50`: Heavy weapon, radar, and engine breakdown. Warship combat value eliminated; retreat to drydock.
  - `FIRE ≥ 40`: Danger of catastrophic ammunition magazine explosion. Primary damage control priority.

### Ground Combat Thresholds
- **Assault Odds Requirements**:
  - `1:1 Odds`: Fortifications hold; both sides suffer proportional attrition.
  - `2:1 Odds`: Fortification level reduced by 1; defender forced to roll morale checks.
  - `3:1 Odds`: Substantial breakthrough; heavy defender casualties and fortification reduction.
  - `≥ 4:1 Odds`: Defender broken; forced retreat from hex if retreat route is open.
- **Preparation Points (Prep Level)**:
  - `0–49`: Severe combat disruption penalty on assault; heavy disembarkation casualties.
  - `50–80`: Adequate for defensive formations or secondary assaults.
  - `100`: Full combat power applied, 100% device survivability bonus on amphibious landings.
- **Ground Support Ratio**: **1 Support Squad per 10 combat/artillery squads**. Shortages cause exponential disruption spikes during movement.

---

## 3. Amphibious Assault Decision Tree

```
                      [Plan Amphibious Assault]
                                  │
                 Has target base prep reached 100?
                         ┌────────┴────────┐
                        NO                YES
                         │                 │
                Wait / Assign staging     Verify Naval & Air Superiority
                base until Prep = 100              │
                                          Are enemy CVs / LBA eliminated?
                                                   ┌────────┴────────┐
                                                  NO                YES
                                                   │                 │
                                          Conduct Carrier Strike   Form Assault TF:
                                          & Airbase Bombardment    - Attack Transports (APA/AKA)
                                                   │               - Escort Carriers (CVE) for CAP
                                                   │               - BB/CA Fire Support Group
                                                   │                         │
                                                   └─────────► Execute Night Shore Bombardment
                                                                     │
                                                              Land Troops at Dawn
```

---

## 4. Ship Repair Decision Matrix

| Damage Type | Damage Severity | Required Port / Facility | Recommended Mode |
|---|---|---|---|
| **System (SYS)** | 1–30 | Port Level 3+ or Repair Ship (AR) | *Pierside Repair* at forward base |
| **System (SYS)** | 31–80 | Port Level 6+ with Machine Shops | *Shipyard Repair* |
| **Flotation (FLT)** | 1–20 | Port Level 4+ with AR support | *Pierside Repair* to stabilize |
| **Flotation (FLT)** | 21–60 | Port Level 7+ or Floating Drydock (AFD) | *Drydock Repair* |
| **Engine / Machinery** | Any Major | Major Home Fleet Base (e.g., Pearl Harbor, Yokosuka) | *Full Shipyard Overhaul* |
| **Fire (FIRE)** | Any Value | Immediate onboard Damage Control | Set task priority to firefighting; do NOT steam at high speed |

---

## 5. Logistics & Supply Priorities

1. **Active Combat Frontlines**: Maintain stockpile ≥ 3× Required Supply.
2. **Forward Airbases**: Maintain stockpile ≥ 2× Required Supply + sufficient aviation fuel to support 5 full strike pulses.
3. **Depot Hubs**: Consolidate fuel and supply at central maritime junctions (e.g., Noumea, Truk, Darwin, Singapore) rather than dispersing across isolated atolls.
4. **Merchant Shipping Defenses**: Never run unescorted merchant convoys through waters with Detection Level (DL) ≥ 2.
