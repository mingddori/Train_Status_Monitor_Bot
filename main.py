from flask import Flask, request
import threading
import time
import requests
import datetime
import os
from dotenv import load_dotenv

# 🧪 환경변수 로드
load_dotenv()
# BOT_TOKEN = os.getenv("BOT_TOKEN")
# CHAT_ID = os.getenv("CHAT_ID")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
SEARCH_URL = os.environ.get("SEARCH_URL")

# Flask 서버
app = Flask(__name__)

# 🚆 모니터링 데이터
train_numbers = []
previous_status = {}
# url = os.getenv("SEARCH_URL") + "/getdata.php"
url = SEARCH_URL + "/getdata.php"

base_headers = {"Content-Type": "application/json"}

last_monitor_time = None  # 마지막 조회 시


@app.route("/")
def home():
    return "🚆 열차 모니터링 중입니다."


@app.route("/ping")
def ping():
    return "pong"


pending_updates = {}  # {user_id: {"action": "set"|"add", "index": idx}}


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        message = data["message"]
        chat_id = str(message["chat"]["id"])
        user_id = str(message["from"]["id"])
        text = message.get("text", "").strip()

        # ✅ [여기에 삽입 시작]
        if text.startswith("/"):
            if user_id in pending_updates:
                pending_updates.pop(user_id)
                send_telegram("⚠️ 진행 중이던 작업을 취소하고 새 명령어를 실행합니다.", chat_id)
        # ✅ [여기에 삽입 끝]

        # 1. 📋 열차 목록 조회
        if text == "/view":
            if train_numbers:
                msg = "📋 현재 추적 중인 열차 목록:\n" + "\n".join(
                    [f"{i}: {num}" for i, num in enumerate(train_numbers)])
            else:
                msg = "📭 현재 추적 중인 열차가 없습니다."
            send_telegram(msg, chat_id)

        # 2. ➕ 열차 추가 시작
        elif text == "/add":
            pending_updates[user_id] = {"action": "add"}
            send_telegram("➕ 추가할 열차 번호를 입력해주세요.", chat_id)

        # 3. ❌ 열차 삭제 시작 (인덱스 입력 대기)
        elif text == "/del":
            if train_numbers:
                pending_updates[user_id] = {"action": "delete"}
                msg = "🗑️ 삭제할 열차 인덱스를 입력해주세요.\n(☠️전체 삭제를 원하시면 '-1'을 입력해주세요.)\n\n📋 현재 목록:\n" + "\n".join(
                    [f"{i}: {num}" for i, num in enumerate(train_numbers)])
                send_telegram(msg, chat_id)
            else:
                send_telegram("📭 삭제할 열차가 없습니다.", chat_id)

        # 4. 🔎 대화형 상태 조회 시작
        elif text == "/status":
            pending_updates[user_id] = {"action": "status", "step": 1}
            send_telegram("🔍 조회할 열차 번호를 입력해주세요.", chat_id)

        # 5. ⌨️ 사용자 입력 처리
        elif user_id in pending_updates:
            info = pending_updates[user_id]
            new_text = text.strip()

            if info["action"] == "add":
                train_numbers.append(new_text)
                send_telegram(f"✅ 새 열차 {new_text}를 목록에 추가했습니다.", chat_id)

                zone = fetch_train_info(new_text, get_today())
                if zone:
                    send_telegram(f"🔍 열차 {new_text} 현재 상태: {zone}", chat_id)
                else:
                    send_telegram(f"⚠️ 열차 {new_text} 조회 실패 또는 운행 정보 없음",
                                  chat_id)

                pending_updates.pop(user_id)

            elif info["action"] == "delete":
                try:
                    idx = int(new_text)
                    if idx == -1:
                        train_numbers.clear()
                        previous_status.clear()
                        send_telegram("🗑️ 모든 열차가 삭제되었습니다.", chat_id)
                    elif 0 <= idx < len(train_numbers):
                        deleted = train_numbers.pop(idx)
                        previous_status.pop(deleted, None)
                        msg = f"🗑️ {idx}번 열차 {deleted} 삭제 완료\n"
                        if train_numbers:
                            msg += "📋 남은 목록:\n" + "\n".join([
                                f"{i}: {num}"
                                for i, num in enumerate(train_numbers)
                            ])
                        else:
                            msg += "📭 목록이 비어 있습니다."
                        send_telegram(msg, chat_id)
                    else:
                        send_telegram("❌ 유효한 인덱스를 입력해주세요.", chat_id)
                except:
                    send_telegram("❌ 숫자 형식의 인덱스를 입력해주세요.", chat_id)
                pending_updates.pop(user_id)

            elif info["action"] == "status":
                if info.get("step") == 1:
                    info["train"] = new_text
                    info["step"] = 2
                    send_telegram(
                        "📆 조회할 날짜를 입력해주세요 (YYYYMMDD). 오늘 날짜는 0을 입력하세요.",
                        chat_id)

                elif info.get("step") == 2:
                    train_no = info["train"]
                    if new_text == "0":
                        date_str = get_today()
                    else:
                        try:
                            datetime.datetime.strptime(new_text, "%Y%m%d")
                            date_str = new_text
                        except ValueError:
                            send_telegram(
                                "❌ 날짜 형식이 잘못되었습니다. YYYYMMDD 형식으로 다시 시도해주세요.",
                                chat_id)
                            return "ok", 200

                    zone = fetch_train_info(train_no, date_str)
                    if zone:
                        send_telegram(
                            f"🚆 열차 {train_no} 상태 조회 결과:\n날짜: {date_str}\n현재 위치: {zone}",
                            chat_id)
                    else:
                        send_telegram(
                            f"⚠️ 열차 {train_no} 조회 실패 또는 운행 정보 없음 (날짜: {date_str})",
                            chat_id)

                    pending_updates.pop(user_id)

        # 6. ⏳ 다음 조회까지 남은 시간 확인
        elif text == "/next":
            if last_monitor_time:
                elapsed = time.time() - last_monitor_time
                remaining = int(max(0, 600 - elapsed))
                send_telegram(f"⏱️ 다음 조회까지 약 {remaining}초 남았습니다.", chat_id)
            else:
                send_telegram("⏱️ 조회가 아직 시작되지 않았습니다.", chat_id)

        # 7. 🆘 도움말 출력
        elif text == "/help":
            msg = ("🤖 사용 가능한 명령어 목록:\n\n"
                   "📋 `/view` - 현재 추적 중인 열차 목록 보기\n"
                   "➕ `/add` - 열차 번호 추가 (입력 대기)\n"
                   "❌ `/del` - 열차 삭제 시작 (인덱스 입력 대기)\n"
                   "🔍 `/status` - 특정 열차 상태 즉시 조회 (열차 번호, 날짜 입력 대기)\n"
                   "⌛ `/next` - 다음 조회까지 남은 시간\n"
                   "🆘 `/help` - 이 도움말 보기")
            send_telegram(msg, chat_id)
    return "ok", 200


# 🔔 텔레그램 알림
def send_telegram(message, chat_id=CHAT_ID):
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        res = requests.post(telegram_url,
                            data={
                                "chat_id": chat_id,
                                "text": message
                            })
        if res.status_code != 200:
            print("⚠️ 텔레그램 전송 실패:", res.text)
    except Exception as e:
        print("❗ 텔레그램 예외:", e)


# 📆 오늘 날짜
def get_today():
    return datetime.datetime.now().strftime("%Y%m%d")


# 🚄 열차 정보 조회
def fetch_train_info(train_no, target_day):
    payload = {
        "act": "SearchTrainInfo",
        "date": target_day,
        "hour": "",
        "page": 0,
        "q": train_no,
        "q2": ""
    }
    # header_url = os.getenv("SEARCH_URL") + f"/?act=SearchTrainInfo&q={train_no}&d={target_day}&h=&q2="
    header_url = SEARCH_URL + f"/?act=SearchTrainInfo&q={train_no}&d={target_day}&h=&q2="

    headers = {
        **base_headers, "Referer": header_url
    }

    try:
        res = requests.post(url, json=payload, headers=headers)
        data = res.json()
        if data.get("result") == 200 and data.get("data"):
            return data["data"]["info"].get("zone")
    except Exception as e:
        print(f"❗ {train_no} 조회 실패: {e}")
    return None


# 🔁 모니터링 루프 (별도 쓰레드에서 실행)
def monitor_loop():
    global last_monitor_time
    print("🟢 모니터링 루프 시작")
    send_telegram("🟢 모니터링 루프 시작", )
    send_telegram("🟢 열차 모니터링이 시작되었습니다. `/help` 명령어로 사용 가능한 명령어를 확인해주세요.")
    while True:
        last_monitor_time = time.time()
        today = get_today()
        for train_no in train_numbers:
            zone = fetch_train_info(train_no, today)
            if zone is None:
                print(f"[{train_no}] 🚫 운행 정보 없음 또는 요청 실패")
            else:
                prev = previous_status.get(train_no)
                if prev is None:
                    print(f"[{train_no}] ✅ 초기 상태 등록: {zone}")
                    send_telegram(f"🚆 열차 {train_no} 상태 초기 등록\n현재: {zone}")
                elif prev != zone:
                    print(
                        f"[{train_no}] ⚠️ 상태 변경 감지!\n - 이전: {prev}\n - 현재: {zone}"
                    )
                    send_telegram(
                        f"🚨 열차 {train_no} 상태 변경\n이전: {prev}\n현재: {zone}")
                else:
                    print(f"[{train_no}] 🔄 상태 동일: {zone}")
                previous_status[train_no] = zone
        print("⏳ 10분 대기 중...")
        time.sleep(600)


# 💡 모니터링 쓰레드 시작
@app.before_first_request
def start_monitor_thread() :
    threading.Thread(target=monitor_loop, daemon=True).start()