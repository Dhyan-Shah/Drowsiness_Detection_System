
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'       # suppress TF info/warnings/errors
os.environ['GLOG_minloglevel']      = '3'       # suppress MediaPipe glog messages
os.environ['GLOG_logtostderr']      = '0'       # stop glog writing to stderr
os.environ['MEDIAPIPE_DISABLE_GPU'] = '1'       # suppress GPU fallback messages
os.environ['KMP_WARNINGS']          = '0'       # suppress OpenMP warnings

import warnings
warnings.filterwarnings("ignore")

import absl.logging
absl.logging.set_verbosity(absl.logging.ERROR)
absl.logging.use_absl_handler()

import cv2
import mediapipe as mp
import numpy as np
from scipy.spatial import distance
from collections import deque
import time
import csv
import threading
import requests
from datetime import datetime

# ============================================================
# RPi GPIO SETUP (uncomment when deploying on Raspberry Pi)
# ============================================================
# import RPi.GPIO as GPIO
# BUZZER_PIN = 18
# LED_GREEN  = 23    # GREEN = awake
# LED_RED    = 24    # RED   = drowsy
# GPIO.setmode(GPIO.BCM)
# GPIO.setup(BUZZER_PIN, GPIO.OUT)
# GPIO.setup(LED_GREEN,  GPIO.OUT)
# GPIO.setup(LED_RED,    GPIO.OUT)
# buzzer_pwm = GPIO.PWM(BUZZER_PIN, 1000)
#
# def set_leds(awake):
#     GPIO.output(LED_GREEN, GPIO.HIGH if awake else GPIO.LOW)
#     GPIO.output(LED_RED,   GPIO.LOW  if awake else GPIO.HIGH)

# ============================================================
# Windows stub — no-op LED (replace with GPIO version on RPi)
# ============================================================
def set_leds(awake):
    pass


# ============================================================
# Telegram Alert Config
# ============================================================
TELEGRAM_TOKEN   = "8618054934:AAEXUCQdhbW3lgVZTXE-4Ig_JCWFenN2JzU"
TELEGRAM_CHAT_ID = "6291964543"
TELEGRAM_URL     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Telegram cooldown — don't spam messages (seconds)
TELEGRAM_COOLDOWN   = 60.0
last_telegram_time  = 0.0

def send_telegram_message(text):
    """Send a text message to the emergency contact."""
    try:
        requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=5
        )
    except Exception as e:
        print(f"[TELEGRAM] Message failed: {e}")

def send_telegram_photo(frame, caption):
    """Send a snapshot photo with caption to emergency contact."""
    try:
        _, buf = cv2.imencode('.jpg', frame)
        requests.post(
            f"{TELEGRAM_URL}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
            files={"photo": ("alert.jpg", buf.tobytes(), "image/jpeg")},
            timeout=10
        )
    except Exception as e:
        print(f"[TELEGRAM] Photo failed: {e}")

# ============================================================
# Location — IP based (Windows)
# On RPi with Neo-6M: replace get_location() with GPS version
# ============================================================
_cached_location = None   # cache so we don't hit API every alert

def get_location():
    """Get approximate location via IP geolocation. Cached after first call."""
    global _cached_location
    if _cached_location:
        return _cached_location
    try:
        r = requests.get("http://ip-api.com/json/", timeout=5)
        d = r.json()
        if d.get("status") == "success":
            _cached_location = {
                "city"    : d.get("city",        "Unknown"),
                "region"  : d.get("regionName",  "Unknown"),
                "country" : d.get("country",     "Unknown"),
                "lat"     : d.get("lat",          0.0),
                "lon"     : d.get("lon",          0.0),
            }
        else:
            _cached_location = {"city": "Unknown", "region": "", "country": "", "lat": 0.0, "lon": 0.0}
    except Exception as e:
        print(f"[LOCATION] Failed: {e}")
        _cached_location = {"city": "Unknown", "region": "", "country": "", "lat": 0.0, "lon": 0.0}
    return _cached_location

# Pre-fetch location at startup so first alert is instant
threading.Thread(target=get_location, daemon=True).start()


def telegram_alert(frame, alert_level, drowsy_dur, ear, score):
    """Send non-tech friendly alert in background thread."""
    def _send():
        ts  = datetime.now().strftime('%I:%M %p, %d %B %Y')   # e.g. 02:35 PM, 13 March 2025
        loc = get_location()
        maps_url = f"https://maps.google.com/?q={loc['lat']},{loc['lon']}"

        # Human-friendly drowsiness level
        if score >= 75 or alert_level == "escalated":
            level_text = "Severe 🔴"
            description = (
                "The driver appears to be seriously drowsy or may have fallen asleep. "
                "Immediate action is needed."
            )
            emoji = "🚨"
        elif score >= 45 or alert_level == "critical":
            level_text = "Moderate 🟠"
            description = (
                "The driver is showing clear signs of drowsiness — "
                "eyes closing and/or head drooping."
            )
            emoji = "⚠️"
        else:
            level_text = "Mild 🟡"
            description = (
                "The driver is showing early signs of tiredness. "
                "A short break is recommended."
            )
            emoji = "💤"

        # Duration in plain words
        mins = int(drowsy_dur // 60)
        secs = int(drowsy_dur % 60)
        if mins > 0:
            dur_text = f"{mins} minute{'s' if mins > 1 else ''} and {secs} seconds"
        else:
            dur_text = f"{secs} seconds"

        caption = (
            f"{emoji} DROWSINESS ALERT\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Time      : {ts}\n"
            f"⚡ Level     : {level_text}\n"
            f"⏱ Duration  : Drowsy for {dur_text}\n"
            f"\n"
            f"📋 {description}\n"
            f"\n"
            f"📍 Last known location:\n"
            f"   {loc['city']}, {loc['region']}, {loc['country']}\n"
            f"🗺  {maps_url}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Please check on the driver immediately."
        )
        send_telegram_photo(frame, caption)
    threading.Thread(target=_send, daemon=True).start()


# ============================================================
# Audio Alert — Windows winsound (threaded so it won't block)
# Comment out on RPi and use buzzer_pwm instead
# ============================================================
import winsound

def _beep_thread(level):
    if level == "warning":
        winsound.Beep(800, 400)
    elif level == "critical":
        for _ in range(3):
            winsound.Beep(1200, 200)
            time.sleep(0.1)
    elif level == "escalated":
        for _ in range(6):
            winsound.Beep(1500, 300)
            time.sleep(0.05)

def buzz_alert(level="warning"):
    threading.Thread(target=_beep_thread, args=(level,), daemon=True).start()

    # --- RPi buzzer (uncomment on Pi) ---
    # def _rpi_buzz():
    #     if level == "warning":
    #         buzzer_pwm.start(50); time.sleep(0.4); buzzer_pwm.stop()
    #     elif level == "critical":
    #         for _ in range(3):
    #             buzzer_pwm.start(50); time.sleep(0.2); buzzer_pwm.stop(); time.sleep(0.1)
    #     elif level == "escalated":
    #         for _ in range(6):
    #             buzzer_pwm.start(80); time.sleep(0.3); buzzer_pwm.stop(); time.sleep(0.05)
    # threading.Thread(target=_rpi_buzz, daemon=True).start()


# ============================================================
# MediaPipe Setup
# ============================================================
mp_face_mesh = mp.solutions.face_mesh

LEFT_EYE          = [33, 160, 158, 133, 153, 144]
RIGHT_EYE         = [362, 385, 387, 263, 373, 380]
FACE_LANDMARK_IDS = [1, 152, 33, 263, 61, 291]

# Mouth landmarks for yawn detection (MAR)
MOUTH_LANDMARKS   = [61, 291, 39, 181, 0, 17, 269, 405]

FACE_3D_MODEL = np.array([
    [0.0,    0.0,    0.0   ],
    [0.0,   -330.0, -65.0  ],
    [-225.0, 170.0, -135.0 ],
    [225.0,  170.0, -135.0 ],
    [-150.0,-150.0, -125.0 ],
    [150.0, -150.0, -125.0 ],
], dtype=np.float64)


# ============================================================
# Thresholds & Config
# ============================================================
EAR_THRESHOLD      = 0.20
PITCH_THRESHOLD    = -15.0   # raised from -10 to reduce false positives
ROLL_THRESHOLD     = 15.0

# Soft scoring range — score starts rising BEFORE hard threshold
EAR_SOFT_MAX  = 0.28   # fully awake above this EAR
EAR_SOFT_MIN  = 0.13   # fully asleep below this EAR
PITCH_NOD_MAX = -8.0   # starts scoring pitch before -15
PITCH_NOD_MIN = -30.0  # fully nodded
ROLL_SOFT_MAX = 10.0   # starts scoring roll before 15°
ROLL_SOFT_MIN = 30.0   # fully tilted

# Fatigue accumulator decay rate (per frame when awake)
FATIGUE_DECAY = 0.15   # score drops this much per frame when no drowsiness
EAR_CONSEC_FRAMES   = 15
HEAD_CONSEC_FRAMES  = 25    # ~0.8s at 30fps — requires more sustained nod
MAR_THRESHOLD       = 0.6   # mouth aspect ratio — above this = yawning
YAWN_CONSEC_FRAMES  = 20    # ~0.67s of sustained yawn to trigger alert
ESCALATION_TIME    = 5.0    # seconds until escalated buzz
ALERT_COOLDOWN     = 3.0    # seconds between buzzer triggers
LOG_INTERVAL       = 1.0    # seconds between CSV rows


# ============================================================
# CSV Session Logger
# ============================================================
log_filename = f"drowsiness_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

def init_csv():
    with open(log_filename, 'w', newline='') as f:
        csv.writer(f).writerow([
            "timestamp", "ear", "pitch", "yaw", "roll",
            "drowsiness_score", "alert_level"
        ])
    print(f"[LOG] Logging session to: {log_filename}")

def log_row(ear, pitch, yaw, roll, score, alert_level):
    with open(log_filename, 'a', newline='') as f:
        csv.writer(f).writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            f"{ear:.3f}", f"{pitch:.2f}", f"{yaw:.2f}", f"{roll:.2f}",
            f"{score:.1f}", alert_level
        ])


# ============================================================
# EAR
# ============================================================
def eye_aspect_ratio(eye):
    A = distance.euclidean(eye[1], eye[5])
    B = distance.euclidean(eye[2], eye[4])
    C = distance.euclidean(eye[0], eye[3])
    return (A + B) / (2.0 * C)


# ============================================================
# MAR — Mouth Aspect Ratio (yawn detection)
# ============================================================
def mouth_aspect_ratio(landmarks, w, h):
    # 8 mouth points: corners + top/bottom lip
    pts = [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in MOUTH_LANDMARKS]
    # Horizontal width — corner to corner
    C = distance.euclidean(pts[0], pts[1])
    # 3 vertical distances across the mouth opening
    A = distance.euclidean(pts[2], pts[7])
    B = distance.euclidean(pts[3], pts[6])
    D = distance.euclidean(pts[4], pts[5])
    if C == 0:
        return 0.0
    return (A + B + D) / (3.0 * C)


# ============================================================
# Head Pose
# ============================================================
def get_head_pose(landmarks, w, h):
    face_2d = np.array([
        [landmarks[i].x * w, landmarks[i].y * h]
        for i in FACE_LANDMARK_IDS
    ], dtype=np.float64)

    focal_length = w
    cam_matrix   = np.array([
        [focal_length, 0, w / 2],
        [0, focal_length, h / 2],
        [0, 0, 1]
    ], dtype=np.float64)

    success, rot_vec, _ = cv2.solvePnP(
        FACE_3D_MODEL, face_2d, cam_matrix, np.zeros((4, 1)),
        flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not success:
        return 0.0, 0.0, 0.0

    rmat, _  = cv2.Rodrigues(rot_vec)
    angles, _, _, _, _, _ = cv2.RQDecomp3x3(rmat)
    return angles[0] * 360, angles[1] * 360, angles[2] * 360


# ============================================================
# Sliding window histories (Fix 1 — smoothing)
# ============================================================
EAR_HISTORY   = deque(maxlen=30)   # ~1s at 30fps
PITCH_HISTORY = deque(maxlen=30)
ROLL_HISTORY  = deque(maxlen=30)


# ============================================================
# Drowsiness Score (0–100)
# Fix 1: uses smoothed values
# Fix 2: soft scoring curve — starts before hard threshold
# Fix 3: fatigue accumulator lives in main loop (see below)
# Weights: EAR 55% | Pitch 30% | Roll 15%
# ============================================================
YAWN_HISTORY  = deque(maxlen=30)

def compute_score(ear, pitch, roll, mar=0.0):
    # --- Smooth inputs ---
    EAR_HISTORY.append(ear)
    PITCH_HISTORY.append(pitch)
    ROLL_HISTORY.append(roll)
    YAWN_HISTORY.append(mar)
    s_ear   = float(np.mean(EAR_HISTORY))
    s_pitch = float(np.mean(PITCH_HISTORY))
    s_roll  = float(np.mean(ROLL_HISTORY))
    s_mar   = float(np.mean(YAWN_HISTORY))

    # --- Soft EAR score ---
    ear_s = (EAR_SOFT_MAX - s_ear) / (EAR_SOFT_MAX - EAR_SOFT_MIN)
    ear_s = max(0.0, min(1.0, ear_s)) * 100

    # --- Soft pitch score ---
    pitch_s = (PITCH_NOD_MAX - s_pitch) / (PITCH_NOD_MAX - PITCH_NOD_MIN)
    pitch_s = max(0.0, min(1.0, pitch_s)) * 100

    # --- MAR yawn score (0 below threshold, rises above MAR_THRESHOLD) ---
    yawn_s = (s_mar - MAR_THRESHOLD) / (1.0 - MAR_THRESHOLD)
    yawn_s = max(0.0, min(1.0, yawn_s)) * 100

    # Weights: EAR 60% | Pitch 25% | Yawn 15%
    raw = (ear_s * 0.60) + (pitch_s * 0.25) + (yawn_s * 0.15)
    return round(min(raw, 100.0), 1)


# ============================================================
# Fatigue Meter Bar
# ============================================================
def draw_fatigue_meter(frame, score):
    bx, by, bw, bh = 15, 62, 210, 15
    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (45, 45, 45), -1)

    fill  = int((score / 100.0) * bw)
    color = (0, 220, 80) if score < 40 else (0, 200, 255) if score < 70 else (0, 60, 255)
    if fill > 0:
        cv2.rectangle(frame, (bx, by), (bx + fill, by + bh), color, -1)

    cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (160, 160, 160), 1)
    cv2.putText(frame, f"Fatigue {score:.0f}%",
                (bx + bw + 8, by + 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.48, (210, 210, 210), 1)


# ============================================================
# Full HUD
# ============================================================
def draw_hud(frame, ear, mar, pitch, yaw, roll, score,
             ear_alert, head_alert, yawn_alert, alert_level, drowsy_dur):
    h, w, _ = frame.shape

    # Dark top banner
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 85), (18, 18, 18), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    # EAR + MAR
    cv2.putText(frame, f"EAR: {ear:.2f}", (15, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                (0, 60, 255) if ear_alert else (0, 230, 100), 2)

    # MAR (yawn)
    mar_color = (0, 165, 255) if yawn_alert else (0, 230, 100)
    cv2.putText(frame, f"MAR:{mar:.2f}", (150, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, mar_color, 1)

    # Head angles
    cv2.putText(frame, f"P:{pitch:+.1f}  Y:{yaw:+.1f}  R:{roll:+.1f}",
                (270, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                (0, 60, 255) if head_alert else (0, 230, 100), 1)

    # Fatigue meter
    draw_fatigue_meter(frame, score)

    # Drowsy timer
    if drowsy_dur > 0:
        cv2.putText(frame, f"Drowsy: {drowsy_dur:.1f}s",
                    (w - 185, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2)

    # LED dot removed — physical RPi LEDs handle this on hardware

    # Alert banners removed — buzzer + LED dot handles all alerting


# ============================================================
# Camera Init
# ============================================================
# Windows → cv2.VideoCapture(0, cv2.CAP_DSHOW)
# RPi     → cv2.VideoCapture(0)   ← remove CAP_DSHOW
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

print("Camera opened:", cap.isOpened())
if not cap.isOpened():
    print("ERROR: Camera not accessible"); exit()

init_csv()

# ============================================================
# State
# ============================================================
ear_counter     = 0
head_counter    = 0
yawn_counter    = 0
last_alert_time = 0.0
last_log_time   = 0.0
drowsy_start    = None
alert_cooldown  = ALERT_COOLDOWN
fatigue_score   = 0.0     # accumulated fatigue (Fix 3 — slow decay)
last_telegram_time = 0.0  # cooldown tracker for Telegram alerts


# ============================================================
# Main Loop
# ============================================================
with mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
) as face_mesh:

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Frame not read — exiting"); break

        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = face_mesh.process(rgb)
        rgb.flags.writeable = True

        ear   = 0.0;  pitch = 0.0;  yaw = 0.0;  roll = 0.0
        mar   = 0.0
        score = 0.0
        ear_alert   = False
        head_alert  = False
        yawn_alert  = False
        alert_level = "none"
        drowsy_dur  = 0.0

        if results.multi_face_landmarks:
            lm = results.multi_face_landmarks[0].landmark

            # EAR
            left_eye  = [(int(lm[i].x * w), int(lm[i].y * h)) for i in LEFT_EYE]
            right_eye = [(int(lm[i].x * w), int(lm[i].y * h)) for i in RIGHT_EYE]
            ear = (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2.0
            for p in left_eye + right_eye:
                cv2.circle(frame, p, 2, (0, 255, 120), -1)

            # Yawn (MAR)
            mar = mouth_aspect_ratio(lm, w, h)
            # Draw mouth dots when yawning
            if mar > MAR_THRESHOLD:
                for i in MOUTH_LANDMARKS:
                    p = (int(lm[i].x * w), int(lm[i].y * h))
                    cv2.circle(frame, p, 2, (0, 165, 255), -1)

            # Head pose
            pitch, yaw, roll = get_head_pose(lm, w, h)

            # Drowsiness score (raw, smoothed)
            raw_score = compute_score(ear, pitch, roll, mar)

            # Fix 3 — Fatigue accumulator: rises fast, decays slowly
            if raw_score > fatigue_score:
                fatigue_score = raw_score                      # jump up instantly
            else:
                fatigue_score = max(0.0, fatigue_score - FATIGUE_DECAY)  # decay slowly
            score = round(fatigue_score, 1)

            # Counters
            ear_counter  = ear_counter  + 1 if ear < EAR_THRESHOLD else 0
            # Roll removed from head counter — only forward pitch nod counts
            head_counter = head_counter + 1 if pitch < PITCH_THRESHOLD else 0
            yawn_counter = yawn_counter + 1 if mar > MAR_THRESHOLD else 0

            ear_alert  = ear_counter  >= EAR_CONSEC_FRAMES
            head_alert = head_counter >= HEAD_CONSEC_FRAMES
            yawn_alert = yawn_counter >= YAWN_CONSEC_FRAMES
            any_alert  = ear_alert or head_alert or yawn_alert

            # Drowsy duration
            now = time.time()
            if any_alert:
                drowsy_start = drowsy_start or now
                drowsy_dur   = now - drowsy_start
            else:
                drowsy_start = None

            # Alert level
            if any_alert:
                if drowsy_dur >= ESCALATION_TIME:
                    alert_level   = "escalated"
                    alert_cooldown = 1.5         # buzz more frequently when escalated
                elif ear_alert and head_alert:
                    alert_level   = "critical"
                    alert_cooldown = 3.0
                elif ear_alert:
                    alert_level   = "warning_ear"
                    alert_cooldown = 3.0
                elif yawn_alert:
                    alert_level   = "warning_yawn"
                    alert_cooldown = 5.0   # yawns need longer cooldown
                else:
                    alert_level   = "warning_head"
                    alert_cooldown = 3.0
            else:
                alert_cooldown = ALERT_COOLDOWN

            # LED
            set_leds(awake=not any_alert)

            # Buzzer
            if any_alert and (now - last_alert_time > alert_cooldown):
                last_alert_time = now
                buzz_alert(alert_level if alert_level == "escalated"
                           else "critical" if alert_level == "critical"
                           else "warning")   # warning covers yawn + ear + head

            # Telegram alert (only on escalated or critical, with cooldown)
            if any_alert and alert_level in ("escalated", "critical"):
                if now - last_telegram_time > TELEGRAM_COOLDOWN:
                    last_telegram_time = now
                    telegram_alert(frame.copy(), alert_level, drowsy_dur, ear, score)
                    print(f"[TELEGRAM] Alert sent — {alert_level}")

            # CSV log
            if now - last_log_time >= LOG_INTERVAL:
                last_log_time = now
                log_row(ear, pitch, yaw, roll, score, alert_level)

        # HUD
        draw_hud(frame, ear, mar, pitch, yaw, roll, score,
                 ear_alert, head_alert, yawn_alert, alert_level, drowsy_dur)

        cv2.imshow("Drowsiness Detection System", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break


# ============================================================
# Cleanup
# ============================================================
cap.release()
cv2.destroyAllWindows()

# RPi only:
# GPIO.cleanup()

print(f"\nSession ended. Log saved → {log_filename}")