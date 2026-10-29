"""Игра «Взломай умный город» — учебная симуляция."""
import json, os, random, re, secrets, threading, time
from flask import Flask, jsonify, request, render_template, abort, redirect
import redis

app = Flask(__name__)
LOCK = threading.Lock()
ADMIN_KEY = os.environ.get("ADMIN_KEY") or secrets.token_hex(3)
PHASES = {"hack": "Взлом", "review": "Разбор", "defend": "Защита", "final": "Финал"}

# Redis
_rurl = os.environ.get("REDIS_URL") or os.environ.get("REDIS_PRIVATE_URL") or "redis://localhost:6379"
R = redis.from_url(_rurl, decode_responses=True)
STATE_KEY = "smartcity:state"

VULNS = {"noauth": "Нет аутентификации команд", "weakpin": "Слабый PIN + OSINT",
         "openport": "Открытый небезопасный порт", "physical": "Физический доступ",
         "replay": "Replay-атака", "dictpass": "Предсказуемый пароль (личные данные, словарь)",
         "defaultcreds": "Заводские учётные данные", "noupdate": "Непроверенная прошивка",
         "noenc": "Нет шифрования трафика", "noseg": "Нет сегментации сети",
         "reuse": "Повторное использование одного секрета в разных системах"}
MEASURES = {"auth": "Аутентификация команд", "pin": "Сложный код + второй фактор",
            "firewall": "Закрыть порты, файрвол", "lock": "Физическая защита и контроль доступа",
            "nonce": "Одноразовые коды (nonce, время жизни)", "passpol": "Парольная политика",
            "changecreds": "Смена заводских паролей", "signed": "Подписанные обновления",
            "tls": "Шифрование трафика (TLS)", "vlan": "Сегментация сети",
            "uniquesecrets": "Разные секреты для разных систем, без переиспользования"}

def St(q, a, src, ph="Ответ", t="text"):
    return dict(q=q, a=a, src=src, ph=ph, t=t)

def C(i, e, t, x, y, story, vuln, fix, steps, bonus=False, requires=None, trap=False):
    return dict(id=i, emoji=e, title=t, x=x, y=y, story=story, vuln=vuln, fix=fix, steps=steps,
                bonus=bonus, requires=requires, trap=trap, deco=False)

def D(i, e, t, x, y, story):
    return dict(id=i, emoji=e, title=t, x=x, y=y, story=story, vuln=None, fix=None, steps=[],
                bonus=False, requires=None, trap=False, deco=True)

OBJECTS = [
    C("light", "🚦", "Светофор", 16, 24, "Перекрёсток у мэрии. Сделай так, чтобы светофор горел красным.", "noauth", "auth", [
        St("Через какой порт можно достучаться до контроллера?", "5020", {
            "🖥 Скан портов": ["22/tcp filtered", "80/tcp open http", "161/udp open snmp", "5020/tcp open — неизвестно"],
            "🌐 Веб-страница (порт 80)": ["Статус перекрёстка обновляется раз в час", "Формы управления на странице нет"],
            "📊 SNMP (порт 161)": ["Доступны только счётчики проехавших машин", "Запись величин недоступна"],
            "📡 Перехват трафика, вчера 09:15": ["10.0.0.5:5020 → контроллер: 'SET GREEN'", "контроллер → 10.0.0.5:5020: 'OK'"]}, "Порт"),
        St("Отправь команду, чтобы загорелся красный.", "SET RED", {
            "📡 Перехват трафика, сегодня": ["08:02 'GET STATUS' → 'GREEN'", "08:10 'SET YELLOW' → 'OK'", "08:11 'SET GREEN' → 'OK'", "08:40 'REBOOT' → 'OK'"]}, "Команда")]),
    C("door", "🚪", "Домофон", 44, 16, "Подъезд дома №7. Консьерж отошёл, его телефон лежит на столе.", "weakpin", "pin", [
        St("Телефон заблокирован четырёхзначным кодом.", "1987", {
            "📷 Табличка на фасаде": ["Дом построен в 1958 году"],
            "🪧 Доска объявлений": ["Капремонт дома завершён в 1987 году", "Собрание жильцов — четверг, 19:00"],
            "📝 Стикер на обратной стороне чехла": ["код — год, когда у нас был ремонт"]}, "Код телефона"),
        St("Введи код домофона.", "1403|0314", {
            "📅 Календарь": ["3 июл: 🎂 ДР внучки Светы", "8 мар: цветы жене", "14 мар: 🎂 ДР — я", "22 мая: стоматолог"],
            "📞 Контакты": ["Я: Пётр Петрович Волков", "Сантехник Игорь", "Семёныч (подвал)"],
            "💬 Сообщения": ["Сосед: Петрович, домофон опять не принимает код, который ты давал!", "Петрович: странно, я его не трогал с того самого дня 😄"]}, "Код домофона")]),
    C("cam", "📷", "Камера", 76, 22, "Камера у входа в парк. Добудь запись за вчерашний день.", "openport", "firewall", [
        St("Какой порт открыт и не спрашивает пароль?", "23", {
            "🖥 Скан портов": ["22/tcp filtered", "23/tcp open", "443/tcp open", "554/tcp open"],
            "🔌 Подключение к 23": ["Connected.", "IP-CAM v2.1 ready", "cam-23>"],
            "🔌 Подключение к 443": ["TLS handshake failed: нужен сертификат"],
            "🔌 Подключение к 554": ["401 Unauthorized: нужен токен"]}, "Порт"),
        St("Ты в консоли. В какой папке лежат записи?", "/var/rec", {
            "💻 Консоль": ["$ ls /", "bin etc home tmp var", "$ ls /var", "log rec www", "$ ls /var/rec", "2026-10-28.mp4  2026-10-29.mp4"]}, "Путь к папке")]),
    C("lamp", "💡", "Фонарь", 12, 62, "Фонарь у школы. Выключи его.", "physical", "lock", [
        St("Что на опоре можно открыть без пароля?", "щиток|щит|шкаф", {
            "🔍 Осмотр опоры": ["Дверца на высоте 1,5 м с замком", "Кабель уходит под землю"],
            "📋 Инвентарный список": ["Опора №14: модель Lum-S, с сетевым модулем", "Опора №22 (эта): модель Lum-B, без сетевого модуля"],
            "📶 Радиоэфир рядом": ["Сигналов не обнаружено"]}, "Что открыть"),
        St("Каким ключом открывается замок дверцы?", "треугольный|треугольник|трёхгранный|трехгранный", {
            "🔍 Фото замка": ["Отверстие треугольной формы"],
            "🛒 Каталог хозмага": ["Ключ треугольный универсальный, 90 ₽", "Ключ шестигранный 5 мм, 120 ₽", "Ключ-барашек, 60 ₽"]}, "Какой ключ")]),
    C("barrier", "🚧", "Шлагбаум", 40, 70, "Парковка жилого дома. Заезжай без пульта.", "replay", "nonce", [
        St("На какой частоте (МГц) работает пульт шлагбаума?", "433", {
            "📻 Спектр рядом": ["315 МГц: всплеск, когда проезжает машина", "433 МГц: всплеск, когда жилец жмёт пульт", "868 МГц: ровный фоновый шум"],
            "📘 Обрывок паспорта": ["Модель BR-100, выпускается с 2012 года", "Для сравнения: BR-200 выпускается с 2020 года, с защитой от повтора сигнала"]}, "МГц"),
        St("Перехвати сигнал жильца и отправь его снова.", None, {}, "", "replay")]),
    C("home", "🏠", "Умный дом", 70, 66, "Приложение умного дома. Хозяйка рассеянная.", "dictpass", "passpol", [
        St("Логин в приложении — имя хозяйки.", "марина|marina", {
            "📸 Соцсеть": ["Марина К., 34 года", "Кот Барсик 🐱 — с нами с 2019 года", "Любит йогу"],
            "📮 Почтовый ящик": ["Уважаемая Марина Кузнецова, ваш заказ доставлен"],
            "📦 Коробка от хаба умного дома": ["Логин по умолчанию: admin", "Пароль по умолчанию: smart2023"]}, "Логин"),
        St("Теперь пароль.", "barsik2019|барсик2019", {
            "💬 Чат с мужем": ["Муж: напомни пароль от дома?", "Марина: та же комбинация, что всегда — кот и год, как мы его забрали"]}, "Пароль")]),
    C("wifi", "📶", "Городской Wi-Fi", 56, 44, "Роутер в парке. Зайди в его панель управления.", "defaultcreds", "changecreds", [
        St("Введи последние 4 цифры серийного номера.", "4417", {
            "🏷 Наклейка на корпусе": ["Модель TL-X500", "S/N: 2208A4417"],
            "📦 Коробка рядом": ["Гарантия до 2027", "Сеть: CityFree"]}, "4 цифры"),
        St("Войди в панель: логин и пароль.", "admin 4417", {
            "🗂 Обсуждение на форуме про эту модель": ["TL-X500, S/N ...A2201 → вход admin / 2201", "TL-X500, S/N ...B5820 → вход admin / 5820", "TL-X300 (другая модель!), S/N ...A1190 → вход admin / root"]}, "логин / пароль")], True),
    C("screen", "📺", "Рекламный экран", 88, 48, "Экран на площади. Покажи на нём свой контент.", "noupdate", "signed", [
        St("С какого домена экран скачивает прошивку?", "update.city.local", {
            "⚙️ Конфиг обновления (этот экран)": ["update_url=http://update.city.local/fw.bin", "check_hash=true", "verify_signature=false", "auto_install=true"],
            "📜 Лог": ["10:02 скачан fw.bin с http-сервера", "10:03 прошивка установлена"]}, "Домен"),
        St("Какой параметр конфига нужно изменить, чтобы экран принял чужую прошивку без проверки?", "verify_signature", {
            "⚙️ Конфиг обновления (этот экран)": ["update_url=http://update.city.local/fw.bin", "check_hash=true", "verify_signature=false", "auto_install=true"],
            "⚙️ Конфиг экрана в депо (настроен верно)": ["update_url=https://fw.city.local/fw.bin", "check_hash=true", "verify_signature=true", "auto_install=false"]}, "Параметр")], True),
    C("sensor", "🌡️", "Датчик воздуха", 28, 46, "Датчик на набережной. Заставь сервер принять твои данные.", "noenc", "tls", [
        St("Какой IP у датчика, чей трафик не шифруется?", "192.168.1.31", {
            "📡 Перехват Wi-Fi": ["192.168.1.20 → TLS 1.3 [зашифровано]", "192.168.1.31 → HTTP [открытый текст]", "192.168.1.40 → SSH [зашифровано]"],
            "🗺 Список устройств сети": ["192.168.1.20 камера парка", "192.168.1.31 датчик воздуха №42", "192.168.1.40 шлюз"]}, "IP"),
        St("Какой ключ датчик отправляет серверу?", "SENS-7731", {
            "🔬 Пакет №212": ["POST /data HTTP/1.1", "Host: api.city.local", "temp=21&id=42&key=SENS-7731"]}, "Ключ")], True),
    C("hub", "🏢", "Диспетчерская", 84, 84, "Ты внутри городской сети. Дойди до сервера диспетчерской.", "noseg", "vlan", [
        St("Какая сеть общая для всех устройств?", "10.0.0.0/24", {
            "🗺 Схема сети": ["Единая сеть 10.0.0.0/24", "Камеры: .10-.19", "Светофоры: .20-.29", "Сервер: где-то в этой же сети"],
            "🔧 Правила файрвола": ["Между устройствами правил нет", "Наружу: порт 443"]}, "Сеть"),
        St("Какой IP у камеры, где пароль так и не сменили?", "10.0.0.12|.12", {
            "📋 Список установки камер": [".10 установлена март 2024", ".12 установлена июнь 2024", ".15 установлена июнь 2024"],
            "📋 Журнал смены паролей за 2024": [".10 пароль сменён 10.03", ".15 пароль сменён 02.07"]}, "IP"),
        St("Какой IP у сервера диспетчерской?", "10.0.0.5", {
            "🗺 Схема сети (та же)": ["Сервер диспетчерской отмечен значком 🖥 на адресе 10.0.0.5"]}, "IP")], True),
    C("kiosk", "🅿️", "Парковочный автомат", 26, 10, "Старый автомат оплаты парковки у въезда. На вид — лёгкая цель.", None, None, [
        St("На экране меню сервиса. Введи пароль техника.", "admin123", {
            "🖥 Экран автомата": ["MAINTENANCE MODE", "login: admin", "password: ______"],
            "🏷 Стикер на корпусе (явно не от производителя)": ["Пароль техника: admin123", "Если не работает — звони в сервис"],
            "📋 Паспорт устройства": ["Модель PayKiosk-9, установлен в 2015"]}, "Пароль техника")], trap=True),
    C("drone", "🛸", "Дрон доставки", 50, 92,
      "Диспетчерская управляет дроном через тот же городской Wi-Fi. Открывается, когда взломаны Wi-Fi и диспетчерская.",
      "reuse", "uniquesecrets", [
        St("Введи IP сервера, которому дрон подчиняется — тот самый, что ты уже находил в диспетчерской.",
           "10.0.0.5", {"📡 Трафик дрона": ["Дрон каждые 10 сек слушает один и тот же сервер диспетчерской"]}, "IP сервера"),
        St("Код авторизации дрона — это то же, что ты уже находил на роутере Wi-Fi (4 цифры).",
           "4417", {"📄 Обгоревший фрагмент инструкции дрона": ["Код авторизации = последние 4 цифры серийного номера точки доступа, к которой подключён дрон"]}, "Код авторизации")],
      requires=["wifi", "hub"]),
    D("park",    "🌳", "Городской парк",       6,  42, "Обычный парк: скамейки, голуби, пара велодорожек. Ничего из электроники."),
    D("mayor",   "🏛",  "Мэрия",               60,  6, "Фасад здания мэрии. Торжественно, тихо, камер снаружи не видно."),
    D("stop",    "🚉", "Автобусная остановка", 34, 92, "Расписание автобусов и немного рекламы. Электроники нет."),
    D("fountain","⛲", "Городской фонтан",     92, 68, "Фонтан в сквере. Летом работает, сейчас отключён на зиму."),
]

OB = {o["id"]: o for o in OBJECTS}
def norm(s): return re.sub(r"[\s/:,;|\\\-]+", "", str(s).lower())
BASE = [o["id"] for o in OBJECTS if not o["bonus"] and not o["trap"] and not o["requires"] and not o["deco"]]
DECO_IDS = [o["id"] for o in OBJECTS if o["deco"]]
INCIDENT_TABS = sorted({tab for o in OBJECTS for st in o["steps"] if len(st["src"]) > 1 for tab in st["src"]})

# ── Redis helpers ────────────────────────────────────────────────────────────
EMPTY_STATE = {"phase": "hack", "players": {}, "events": [], "incident": None, "siren": None}

def load_state():
    raw = R.get(STATE_KEY)
    if raw:
        s = json.loads(raw)
        for k, v in EMPTY_STATE.items():
            s.setdefault(k, v)
        return s
    return dict(EMPTY_STATE)

def save_state(s):
    R.set(STATE_KEY, json.dumps(s, ensure_ascii=False))

# In-memory captures (per-request token, не нужен persistence)
CAPT = {}

# ── Game helpers ─────────────────────────────────────────────────────────────
def siren_active(s):
    sir = s.get("siren")
    return bool(sir and not sir["stopped"] and time.time() < sir["until"])

def apply_incident(s, src):
    inc = s.get("incident")
    if inc and inc["tab"] in src and time.time() < inc["until"]:
        src = dict(src)
        src[inc["tab"]] = ["⛔ Технические работы, источник временно недоступен.", "Попробуй другой источник или вернись через минуту."]
    return src

def log_event(s, txt):
    s["events"].append({"t": time.strftime("%H:%M:%S"), "txt": txt})
    s["events"] = s["events"][-60:]

def unlocked(p):
    return all(i in p["hacked"] for i in BASE)

def access_error(p, o):
    if o["trap"] or o["deco"]:
        return None
    if o["requires"] and not all(r in p["hacked"] for r in o["requires"]):
        names = ", ".join(OB[r]["title"] for r in o["requires"])
        return f"Сначала нужно взломать: {names}"
    if o["bonus"] and not unlocked(p):
        return "Сначала взломай основные объекты"
    return None

# ── Background loops ─────────────────────────────────────────────────────────
def incident_loop():
    while True:
        time.sleep(random.randint(70, 130))
        dur = random.randint(20, 30)
        with LOCK:
            s = load_state()
            if s["phase"] != "hack" or not INCIDENT_TABS:
                continue
            tab = random.choice(INCIDENT_TABS)
            s["incident"] = {"tab": tab, "until": time.time() + dur}
            log_event(s, f"⚠️ Городское происшествие: «{tab}» временно недоступен")
            save_state(s)
        time.sleep(dur)

def siren_loop():
    while True:
        time.sleep(random.randint(150, 240))
        dur = random.randint(30, 45)
        with LOCK:
            s = load_state()
            if s["phase"] != "hack" or not DECO_IDS or siren_active(s):
                continue
            target = random.choice(DECO_IDS)
            s["siren"] = {"obj": target, "until": time.time() + dur, "stopped": False}
            log_event(s, "🚨 ТРЕВОГА! Кто-то пытается проникнуть в систему города. Ищите среди обычных на вид объектов!")
            save_state(s)
        time.sleep(dur)
        with LOCK:
            s = load_state()
            sir = s.get("siren")
            if sir and sir.get("obj") == target and not sir["stopped"]:
                log_event(s, "😈 Мошенник успел проникнуть в систему, пока его искали.")
                s["siren"] = None
                save_state(s)

# ── Auth helper ───────────────────────────────────────────────────────────────
def get_player(s, d):
    p = s["players"].get(d.get("pid"))
    if not p:
        abort(401)
    return p

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html")

@app.get("/board")
def board():
    return render_template("board.html")

@app.get("/api/objects")
def objects():
    pub = [dict(id=o["id"], emoji=o["emoji"], title=o["title"], x=o["x"], y=o["y"],
                story=o["story"], bonus=o["bonus"], trap=o["trap"], deco=o["deco"],
                requires=o["requires"], n=len(o["steps"])) for o in OBJECTS]
    return jsonify(objects=pub, vulns=VULNS, measures=MEASURES)

@app.post("/api/join")
def join():
    d = request.get_json(silent=True) or {}
    nick = (d.get("nick") or "").strip()[:16]
    if not nick:
        return jsonify(error="Введи ник"), 400
    with LOCK:
        s = load_state()
        for pid, p in s["players"].items():
            if p["nick"].lower() == nick.lower():
                if pid == d.get("pid"):
                    save_state(s)
                    return jsonify(pid=pid, nick=p["nick"])
                return jsonify(error="Этот ник занят, выбери другой"), 409
        pid = secrets.token_hex(4)
        s["players"][pid] = {"nick": nick, "score": 0, "hacked": {}, "defended": {}, "steps": {}}
        log_event(s, f"👋 {nick} вошёл в игру")
        save_state(s)
    return jsonify(pid=pid, nick=nick)

@app.post("/api/decoy")
def decoy():
    d = request.get_json(silent=True) or {}
    s = load_state()
    get_player(s, d)
    o = OB.get(d.get("obj"))
    if not o or not o["deco"]:
        return jsonify(error="Нельзя"), 400
    sir = s.get("siren")
    hot = bool(sir and sir["obj"] == o["id"] and not sir["stopped"] and time.time() < sir["until"])
    return jsonify(hot=hot)

@app.post("/api/stop_siren")
def stop_siren():
    with LOCK:
        d = request.get_json(silent=True) or {}
        s = load_state()
        p = get_player(s, d)
        sir = s.get("siren")
        if not sir or sir["obj"] != d.get("obj") or sir["stopped"] or time.time() >= sir["until"]:
            return jsonify(ok=False)
        sir["stopped"] = True
        p["score"] += 100
        log_event(s, f"🛡️ {p['nick']} остановил мошенника! +100")
        s["siren"] = None
        save_state(s)
    return jsonify(ok=True)

@app.post("/api/capture")
def capture():
    d = request.get_json(silent=True) or {}
    s = load_state()
    get_player(s, d)
    tok = secrets.token_hex(3).upper()
    CAPT[(d["pid"], d.get("obj", "barrier"))] = tok
    return jsonify(token=tok)

@app.post("/api/obj")
def obj_step():
    with LOCK:
        d = request.get_json(silent=True) or {}
        s = load_state()
        p = get_player(s, d)
        o = OB.get(d.get("obj"))
        if not o or o["deco"] or s["phase"] != "hack" or o["id"] in p["hacked"]:
            return jsonify(error="Сейчас взлом недоступен"), 400
        err = access_error(p, o)
        if err:
            return jsonify(error=err), 403
        i = p["steps"].get(o["id"], 0)
        src = {}
        for st in o["steps"][:i + 1]:
            src.update(st["src"])
        src = apply_incident(s, src)
        st = o["steps"][i]
        save_state(s)
    return jsonify(step=i, total=len(o["steps"]), q=st["q"], ph=st["ph"], t=st["t"], src=src)

@app.post("/api/hack")
def hack():
    with LOCK:
        d = request.get_json(silent=True) or {}
        s = load_state()
        p = get_player(s, d)
        o = OB.get(d.get("obj"))
        if not o or o["deco"] or s["phase"] != "hack" or o["id"] in p["hacked"]:
            return jsonify(error="Сейчас взлом недоступен"), 400
        err = access_error(p, o)
        if err:
            return jsonify(error=err), 403
        i = p["steps"].get(o["id"], 0)
        st = o["steps"][i]
        a = str(d.get("answer", "")).strip()
        if st["t"] == "replay":
            right = a != "" and a == CAPT.get((d["pid"], o["id"]))
        else:
            right = norm(a) in [norm(x) for x in st["a"].split("|")]
        if not right:
            p["score"] -= 5
            save_state(s)
            return jsonify(ok=False)
        p["steps"][o["id"]] = i + 1
        if i + 1 < len(o["steps"]):
            p["score"] += 20
            save_state(s)
            return jsonify(ok=True, done=False)
        if o["trap"]:
            p["hacked"][o["id"]] = {"vuln": "trap"}
            p["score"] -= 40
            log_event(s, f"🍯 {p['nick']} попался в ловушку: {o['title']}")
            save_state(s)
            return jsonify(ok=True, done=True, trap=True)
        p["hacked"][o["id"]] = {"vuln": None}
        p["score"] += 80
        log_event(s, f"💥 {p['nick']} взломал: {o['title']}")
        save_state(s)
    return jsonify(ok=True, done=True)

@app.post("/api/vuln")
def vuln():
    with LOCK:
        d = request.get_json(silent=True) or {}
        s = load_state()
        p = get_player(s, d)
        o = OB.get(d.get("obj"))
        h = p["hacked"].get(o["id"]) if o else None
        if h is None or h["vuln"] or d.get("vuln") not in VULNS:
            return jsonify(error="Нельзя"), 400
        h["vuln"] = d["vuln"]
        ok = d["vuln"] == o["vuln"]
        if ok:
            p["score"] += 50
            log_event(s, f"🧠 {p['nick']} верно определил уязвимость: {o['title']}")
        save_state(s)
    return jsonify(ok=ok, correct=VULNS[o["vuln"]])

@app.post("/api/defend")
def defend():
    with LOCK:
        d = request.get_json(silent=True) or {}
        s = load_state()
        p = get_player(s, d)
        o = OB.get(d.get("obj"))
        if not o or s["phase"] != "defend" or o["id"] not in p["hacked"] or o["id"] in p["defended"] \
                or d.get("measure") not in MEASURES:
            return jsonify(error="Нельзя"), 400
        ok = d["measure"] == o["fix"]
        if ok:
            p["defended"][o["id"]] = True
            p["score"] += 80
            log_event(s, f"🛡️ {p['nick']} защитил: {o['title']}")
            save_state(s)
    return jsonify(ok=ok, correct=MEASURES[o["fix"]])

@app.get("/api/state")
def state():
    s = load_state()
    ph = s["phase"]
    ps = list(s["players"].values())
    ps.sort(key=lambda p: -p["score"])
    out = {"phase": ph, "feed": s["events"][-15:][::-1], "siren_active": siren_active(s),
           "board": [{"nick": p["nick"], "score": p["score"], "hacked": len(p["hacked"]),
                      "defended": len(p["defended"])} for p in ps]}
    me = s["players"].get(request.args.get("pid"))
    if me:
        out["me"] = me
        out["unlocked"] = unlocked(me)
    if ph != "hack":
        st = {o["id"]: {"correct": o["vuln"], "counts": {}} for o in OBJECTS if o["vuln"]}
        for p in ps:
            for oid, h in p["hacked"].items():
                if h["vuln"] and h["vuln"] != "trap" and oid in st:
                    c = st[oid]["counts"]
                    c[h["vuln"]] = c.get(h["vuln"], 0) + 1
        out["stats"] = st
    return jsonify(out)

def check_key():
    if request.args.get("key") != ADMIN_KEY:
        abort(403)

@app.get("/admin")
def admin():
    check_key()
    s = load_state()
    btn = "".join(f'<a href="/admin/phase/{k}?key={ADMIN_KEY}" style="margin:6px;padding:10px 16px;'
                  f'background:#f2a541;color:#1b1f3b;text-decoration:none;border-radius:6px">{v}</a>'
                  for k, v in PHASES.items())
    return (f'<body style="font-family:sans-serif;padding:24px"><h2>Управление игрой</h2>'
            f'<p>Сейчас: <b>{PHASES[s["phase"]]}</b>. Игроков: {len(s["players"])}</p>{btn}'
            f'<p><a href="/admin/reset?key={ADMIN_KEY}" onclick="return confirm(\'Сбросить всё?\')">Сбросить игру</a></p></body>')

@app.get("/admin/phase/<ph>")
def phase(ph):
    check_key()
    if ph not in PHASES:
        abort(404)
    with LOCK:
        s = load_state()
        s["phase"] = ph
        log_event(s, f"📢 Фаза: {PHASES[ph]}")
        save_state(s)
    return redirect(f"/admin?key={ADMIN_KEY}")

@app.get("/admin/reset")
def reset():
    check_key()
    with LOCK:
        s = dict(EMPTY_STATE)
        CAPT.clear()
        save_state(s)
    return redirect(f"/admin?key={ADMIN_KEY}")

if __name__ == "__main__":
    threading.Thread(target=incident_loop, daemon=True).start()
    threading.Thread(target=siren_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 8000))
    print(f"\nАдмин-ключ: {ADMIN_KEY}")
    app.run(host="0.0.0.0", port=port)
