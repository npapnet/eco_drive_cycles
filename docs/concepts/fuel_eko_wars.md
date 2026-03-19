# Project Specification: Fuel EKO Wars
**Concept:** A gamified ecosystem that leverages real-time vehicle telematics to incentivize Eco-Driving through social competition and tangible rewards.

## 1. Project Overview
"Fuel EKO Wars" is a hardware-software stack designed to bridge the gap between vehicle performance and driver behavior. By using an OBD-II interface and a mobile application, the system records high-frequency drive cycle data (speed, RPM, fuel consumption). This data is uploaded to a central server for statistical analysis, comparing the driver’s performance against both manufacturer benchmarks (NEDC/WLTP) and the community average. The result is a "Feedback Loop" where drivers are rewarded with points, fuel discounts, or products for improving their ecological footprint and road safety.

---

## 2. System Architecture
The project follows a three-tier architecture: the Edge (Vehicle/App), the Cloud (Server/Database), and the User Interface (Gamification).

### 2.1 Hardware & Edge Layer (The Driver's KIT)
* **OBD-II Device:** A low-cost ELM327-compatible device (WiFi/Bluetooth) connected to the vehicle's diagnostic port.
* **Mobile Gateway (App 1):** Initially utilizing the "Torque" Android application for data logging.
    * **Captured Parameters:** Vehicle speed, engine RPM, fuel consumption (FC), $CO_2$ emissions, GPS coordinates.
* **User/Vehicle Profiles:**
    * **Driver Data:** Age, email login.
    * **Refueling Data:** Quantity, fuel brand, timestamp, and manual entry/photo of receipts.
    * **Vehicle Specs:** Type, weight, horsepower, and NEDC/WLTP factory benchmarks (Urban, Extra-Urban, Mixed).

### 2.2 Server-Side Processing (App 2)
* **Data Ingestion:** A centralized database collects logs from the mobile gateway.
* **Statistical Engine:** Processes raw data to create:
    * **Individual Stats:** Performance vs. history (weekly/monthly).
    * **Comparative Stats:** Deviation from NEDC targets and the "Mean User" average.
    * **Research Analytics:** Data mining for the creation of real-world driving cycles for scientific use.

### 2.3 Interaction & Gamification (App 3)
The front-facing app communicates the analysis back to the user via:
* **Leaderboards:** Ranking based on fuel economy and "defensive driving" scores.
* **Rewards:** Vouchers for fuel, lubricants, or partner products (Supermarkets, Telecommunications).
* **Nudges:** "Penalty" messages that highlight missed rewards to discourage aggressive driving.

---

## 3. Implementation Workflow

### Drive Cycle Logic Diagram
Here is a simplified view of the data flow and feedback loop:

```tikz
\begin{tikzpicture}[node distance=2.5cm, auto, >=stealth]
    \node (obd) [draw, rectangle, rounded corners, align=center] {OBD-II \\ (Data Source)};
    \node (app1) [draw, rectangle, right of=obd, xshift=1.5cm, align=center] {Mobile App \\ (Logging)};
    \node (server) [draw, rectangle, below of=app1, align=center] {Server / DB \\ (Analysis)};
    \node (app3) [draw, rectangle, left of=server, xshift=-1.5cm, align=center] {User UI \\ (The Game)};
    
    \draw [->, thick] (obd) -- node {BT/WiFi} (app1);
    \draw [->, thick] (app1) -- node {Upload} (server);
    \draw [->, thick] (server) -- node {Feedback} (app3);
    \draw [->, dashed] (app3) -- node {Behavior Change} (obd);
\end{tikzpicture}
```

---

## 4. Evaluation Metrics (The "Eco-Index")
The system assesses drivers through four specific lenses:

1.  **Direct Comparison (NEDC):** Deviation from the vehicle's official factory fuel consumption.
2.  **Peer Comparison:** Performance relative to other drivers in the same vehicle category and road type (Urban vs. Extra-urban).
3.  **Behavioral Index:** Analyzing throttle position, acceleration/deceleration rates, RPM spikes, and idle time (stationary % with engine running).
4.  **Environmental Footprint:** Calculation of $CO_2$ savings and energy footprint.

---

## 5. Strategic Extensions
* **Corporate Value:** Enhances the "Environmental Profile" of the partner company (e.g., EKO) and increases customer loyalty.
* **Research & Public Policy:** Anonymized data can be provided to universities or the EU for creating updated "Real-world Driving Cycles."
* **Smart Features:** Integration of nearest gas station locations, fuel price tracking, and real-time user notifications.

---

## Proactive Logic & Methodology Check
* **Data Consistency:** You mention using "Torque" for logging. Torque saves logs locally as CSVs. Your workflow suggests an "App 3" to handle interaction. **Logic Error:** To make this seamless, App 3 must have a file-observer to automatically grab Torque's logs, or you need to build the logging directly into App 3. Manual uploading (mentioned in slide 20) is a major friction point for a "game."
* **NEDC vs. WLTP:** The slides mention NEDC (New European Driving Cycle) predominantly. Since this is 2026, NEDC is quite obsolete for newer cars. I have added WLTP to the metrics to ensure the software is relevant for vehicles post-2017.
* **Verification:** There is a gap in how "Fuel Brand" and "Receipts" are verified. If rewards are tied to using a specific brand (EKO), the system needs a way to validate the receipt photo via OCR to prevent "gaming" the game.

---

## Things to Clarify
| Section | Source Phrasing | Concern |
| :--- | :--- | :--- |
| **Data Flow** | "To torque (Εφ.1) κάνει συνεχή καταγραφή αλλά το αρχείο στέλνεται μόνο manually." | **Confidence < 70%:** It is unclear if you intend to keep Torque as a permanent middleman or if this is just for the prototype phase. Manual CSV uploads will likely kill user engagement. |
| **Penalty Logic** | "«Επιβάρυνση» χρηστών... Μηνύματα που τονίζουν το «χάσιμο» δώρων!!!" | **Confidence 50%:** In gamification, "Loss Aversion" is powerful, but "Charge/Penalty" usually refers to a financial cost. I've assumed these are just psychological "nudges," not actual fines. |
| **Comparison** | "Index για την σύγκριση... Πετάλ κάτω από ένα ποσοστό (πχ. αυγά)" | **Confidence 60%:** "Eggs" likely refers to the "driving like you have an egg under the pedal" analogy. I've translated this to "Throttle position analysis." |
| **Software Roles** | "Λογισμικό Εφ. 3" vs "Εφαρμογή (Εφ. 2)" | **Confidence 65%:** The numbering in the source is inconsistent (Slide 5 vs Slide 20). I have re-labeled them as App 1 (Logging), App 2 (Backend), and App 3 (UI) for clarity. |

#EcoDriving #OBDII #Gamification #MechanicalEngineering #SoftwareArchitecture #FuelEconomy

**Would you like me to draft a more detailed technical requirement for the "App 3" logic, specifically how it should automate the background data upload?**