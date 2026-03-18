# 🚗 Drowsiness Detection System
### Real-time Driver Alertness Monitoring using Computer Vision & Raspberry Pi

**G H Patel College of Engineering and Technology**  
Department of Computer Engineering | Mini Project (202040601) | A.Y. 2025–26

| Team Member | Enrollment No. |
|---|---|
| Dhyan Shah | 12302040501014 |
| Darsh Patel | 12302040501006 |
| Het Patel | 12302040501021 |

**Mentor:** Prof. Khyati Mehta

---

## 📌 Overview

This project is a real-time drowsiness detection system that monitors a driver's face continuously using a camera. It detects early signs of drowsiness through three signals — **eye closure**, **head nodding**, and **yawning** — and triggers multi-level alerts via buzzer, LED indicators, and an automatic Telegram message with location to an emergency contact.

---

## ✨ Features

- 👁️ **Eye Closure Detection** — using Eye Aspect Ratio (EAR) via MediaPipe Face Mesh
- 🗣️ **Head Pose Estimation** — pitch angle tracking to detect forward head nod
- 🥱 **Yawn Detection** — using Mouth Aspect Ratio (MAR)
- 📊 **Fatigue Score (0–100%)** — weighted real-time drowsiness meter with smoothing and slow decay
- 🚨 **3-Level Alert System** — Warning → Critical → Escalated
- 🔔 **Buzzer Alert** — hardware buzzer on Raspberry Pi GPIO
- 💡 **LED Indicators** — Green (awake) / Red (drowsy)
- 📱 **Telegram Emergency Alert** — sends snapshot photo + location to emergency contact
- 📍 **IP-based Location** — city, region and Google Maps link in alert message
- 📝 **CSV Session Logger** — logs EAR, pitch, yaw, roll, fatigue score every second

---

## 🛠️ Hardware Requirements

| Component | Quantity | Purpose |
|---|---|---|
| Raspberry Pi 4 | 1 | Main processing unit |
| Waveshare IMX219 Camera (8MP CSI) | 1 | Face capture |
| Active Buzzer (5V) | 1 | Audio alert |
| Red LED | 1 | Drowsy indicator |
| Green LED | 1 | Awake indicator |
| 220Ω Resistors | 2 | LED current limiting |
| 2N2222 Transistor | 1 | Buzzer GPIO protection |
| Half Breadboard | 1 | Circuit assembly |
| Jumper Wires (M-F) | 15 | GPIO connections |

---

## 💻 Software Requirements

| Software | Version |
|---|---|
| Python | 3.8+ |
| OpenCV | 4.x |
| MediaPipe | 0.8.x |
| NumPy | Latest |
| SciPy | Latest |
| Requests | Latest |
| absl-py | Latest |
| Picamera2 | Latest (RPi only) |
| RPi.GPIO | Latest (RPi only) |

---

## ⚙️ Installation

### Windows (Testing)

```bash
pip install mediapipe opencv-python numpy scipy requests absl-py pygame
```

### Raspberry Pi (Deployment)

```bash
sudo apt update
sudo apt install -y python3-picamera2
pip install mediapipe opencv-python numpy scipy requests absl-py pygame
```

Enable camera interface:
```bash
sudo raspi-config
# Interface Options → Camera → Enable → Reboot
```

Set audio output to 3.5mm jack:
```bash
sudo raspi-config
# System Options → Audio → Headphones
```

---

## 🔌 GPIO Wiring (Raspberry Pi)

```
RPi GPIO 18  →  2N2222 Base (via 1kΩ resistor)  →  Buzzer +
RPi GPIO 23  →  220Ω Resistor  →  Green LED +
RPi GPIO 24  →  220Ω Resistor  →  Red LED +
RPi GND      →  Buzzer -, LED -, Transistor Emitter
```

**Circuit diagram:**
```
GPIO 18 ──[1kΩ]── 2N2222 Base
                   2N2222 Collector ── Buzzer + ── 5V
                   2N2222 Emitter  ── GND

GPIO 23 ──[220Ω]── Green LED + ── GND
GPIO 24 ──[220Ω]── Red LED   + ── GND
```

---

## 📁 Project Structure

```
Drowsiness_Detection/
│
├── EAR.py                          # Main detection script
├── warning.mp3                     # Voice alert — warning level
├── critical.mp3                    # Voice alert — critical level
├── escalated.mp3                   # Voice alert — escalated level
├── drowsiness_log_YYYYMMDD_HHMMSS.csv   # Auto-generated session log
└── README.md                       # This file
```

---

## 🚀 Running the Script

### Windows
```bash
python EAR.py
```

### Raspberry Pi (with display)
```bash
python3 EAR.py
```

### Raspberry Pi (headless — no monitor)
Comment out `cv2.imshow()` line in the script, then:
```bash
python3 EAR.py
```

Press **`q`** to quit.

---

## 🔧 Key Configuration Parameters

All tunable parameters are at the top of `EAR.py`:

```python
EAR_THRESHOLD      = 0.20    # Eye closed threshold (lower = less sensitive)
PITCH_THRESHOLD    = -15.0   # Head nod angle in degrees
MAR_THRESHOLD      = 0.6     # Yawn detection threshold
EAR_CONSEC_FRAMES  = 15      # Frames before eye alert triggers (~0.5s)
HEAD_CONSEC_FRAMES = 25      # Frames before head alert triggers (~0.8s)
YAWN_CONSEC_FRAMES = 20      # Frames before yawn alert triggers (~0.67s)
ESCALATION_TIME    = 5.0     # Seconds before escalating to critical buzz
ALERT_COOLDOWN     = 3.0     # Seconds between buzzer triggers
TELEGRAM_COOLDOWN  = 60.0    # Seconds between Telegram messages
```

---

## 📊 How It Works

### 1. Eye Aspect Ratio (EAR)
MediaPipe provides 6 landmark points around each eye. EAR is calculated as:

```
EAR = (A + B) / (2 × C)
```
Where A, B are vertical eye distances and C is horizontal width.
- Open eye → EAR ≈ 0.28–0.30
- Closed eye → EAR < 0.20

### 2. Head Pose Estimation
Uses `cv2.solvePnP` to match 6 known 3D face points to their 2D camera positions, giving pitch, yaw and roll angles. Pitch below **-15°** indicates forward head nod.

### 3. Mouth Aspect Ratio (MAR)
Same concept as EAR applied to 8 mouth landmarks. MAR above **0.6** sustained for 20 frames indicates a yawn.

### 4. Fatigue Score
```
Score = (EAR score × 60%) + (Pitch score × 25%) + (Yawn score × 15%)
```
- Smoothed over 30-frame sliding window
- Jumps up instantly when drowsy
- Decays slowly (0.15/frame) when alert

### 5. Alert Levels

| Level | Trigger | Action |
|---|---|---|
| ⚠️ Warning | EAR or Head or Yawn alone | Short beep |
| 🔴 Critical | EAR + Head together | 3 rapid beeps |
| 🆘 Escalated | Drowsy for 5+ seconds | 6 aggressive beeps + Telegram |

---

## 📱 Telegram Setup

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow steps → copy token
3. Send a message to your bot
4. Open: `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Copy your `chat.id`
6. Update in script:
```python
TELEGRAM_TOKEN   = "your_token_here"
TELEGRAM_CHAT_ID = "your_chat_id_here"
```

### Sample Alert Message
```
🚨 DROWSINESS ALERT
━━━━━━━━━━━━━━━━━━━━
🕐 Time     : 02:35 PM, 13 March 2025
⚡ Level    : Severe 🔴
⏱ Duration : Drowsy for 6 seconds

📋 The driver appears to be seriously drowsy
   or may have fallen asleep. Immediate
   action is needed.

📍 Last known location:
   Vadodara, Gujarat, India
🗺  https://maps.google.com/?q=23.02,72.57
━━━━━━━━━━━━━━━━━━━━
Please check on the driver immediately.
```

---

## 📝 CSV Log Format

Auto-saved as `drowsiness_log_YYYYMMDD_HHMMSS.csv`:

```
timestamp, ear, pitch, yaw, roll, drowsiness_score, alert_level
2025-03-13 14:32:11, 0.172, -16.3, 2.1, -1.2, 83.0, escalated
```

---

## 🔄 Windows → RPi Migration Checklist

| Change | Windows | Raspberry Pi |
|---|---|---|
| Camera init | `cv2.VideoCapture(0)` | `Picamera2()` |
| Audio alert | `import winsound` | Comment out, use GPIO buzzer |
| GPIO buzzer | Commented out | Uncomment GPIO block |
| GPIO LEDs | Commented out | Uncomment GPIO block |
| Cleanup | `cap.release()` | `picam2.stop()` + `GPIO.cleanup()` |

---

## ⚠️ Known Limitations

- IP-based location is approximate (city level) — not GPS accurate
- Detection accuracy may reduce in low-light conditions
- Head pose estimation uses a generic 3D face model — may vary per person
- MediaPipe requires decent CPU — RPi 4 runs at lower FPS than desktop

---

## 🔮 Future Scope

- Calibration phase for personalized EAR threshold per driver
- Night mode with automatic brightness compensation
- Mobile app for real-time monitoring dashboard
- Cloud-based session log storage and analytics
- Integration with vehicle CAN bus for speed-aware sensitivity

---

## 📚 References

1. Soukupova & Cech — *Real-Time Eye Blink Detection using Facial Landmarks* (2016)
2. MediaPipe Face Mesh — [developers.google.com/mediapipe](https://developers.google.com/mediapipe)
3. OpenCV Documentation — [docs.opencv.org](https://docs.opencv.org)
4. Raspberry Pi GPIO Documentation — [raspberrypi.com/documentation](https://www.raspberrypi.com/documentation)

---

## 📄 License

This project is developed for academic purposes under Mini Project (202040601), G H Patel College of Engineering and Technology, CVM University.