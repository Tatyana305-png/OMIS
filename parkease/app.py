import os
import sqlite3
from datetime import datetime
from functools import wraps
from abc import ABC, abstractmethod
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "parkease.db")


# ============================
# 1. DATA TYPES & ENUMERATIONS
# ============================
class BookingStatus:
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class SlotType:
    STANDARD = "Обычное"
    DISABLED = "Для инвалидов"
    ELECTRIC = "Электро"


class PaymentStatus:
    INITIATED = "INITIATED"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class TimeRange:
    def __init__(self, start_time, end_time):
        self.start_time = start_time
        self.end_time = end_time

    def duration(self):
        return (self.end_time - self.start_time).total_seconds() / 3600


class GeoPoint:
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude


class SearchFilters:
    def __init__(self, name=None, max_price=None, radius=None, only_available=True):
        self.name = name
        self.max_price = max_price
        self.radius = radius
        self.only_available = only_available


# ===========
# 2. ENTITIES
# ===========
class User:
    def __init__(self, row):
        self.id = row["id"]
        self.full_name = row["full_name"]
        self.email = row["email"]
        self.password_hash = row["password_hash"]
        self.role = row["role"] if "role" in row.keys() else "driver"

    def login(self, email, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password) if self.email == email else False

    def updateProfile(self, full_name, avatar_url=None):
        pass


class Driver(User):
    def searchParking(self, filters):
        pass

    def bookSlot(self, slot_id, time_range):
        pass

    def cancelBooking(self, booking_id):
        pass

    def getBookingHistory(self):
        pass


class ParkingAdmin(User):
    def editParkingInfo(self, parking_id, data):
        pass

    def manageBooking(self, booking_id, action):
        pass

    def moderateReview(self, review_id, hide):
        pass


class Manager(User):
    def createParking(self, name, address):
        pass

    def deleteParking(self, parking_id):
        pass

    def assignAdmin(self, parking_id, user_id):
        pass

    def removeAdmin(self, parking_id, user_id):
        pass


class ParkingLot:
    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.address = row["address"]
        self.price_per_hour = row["price_per_hour"]
        self.work_hours = row["work_hours"]
        self.description = row["description"]
        self.total_slots = row["total_slots"]
        self.rating = 0.0

    def getAvailableSlots(self, time_range):
        return []

    def updateInfo(self, name, price):
        pass

    def calculateRating(self):
        pass


class ParkingSlot:
    def __init__(self, row):
        self.id = row["id"]
        self.number = row["number"]
        self.type = row["type"]
        self.price_per_hour = row["price_per_hour"] if "price_per_hour" in row.keys() else 0.0

    def isAvailable(self, time_range):
        return True


class Booking:
    def __init__(self, row):
        self.id = row["id"]
        self.user_id = row["user_id"]
        self.slot_id = row["slot_id"]
        self.start_time = row["start_time"]
        self.end_time = row["end_time"]
        self.status = row["status"]
        self.amount = row["amount"]

    def confirm(self):
        self.status = BookingStatus.CONFIRMED

    def cancel(self):
        self.status = BookingStatus.CANCELLED

    def complete(self):
        self.status = BookingStatus.COMPLETED

    def updateStatus(self, status):
        self.status = status


class Review:
    def __init__(self, row):
        self.id = row["id"]
        self.user_id = row["user_id"]
        self.parking_id = row["parking_id"]
        self.title = row["title"]
        self.text = row["text"]
        self.rating = row["rating"]
        self.isHidden = (row["status"] == "HIDDEN")

    def editTitle(self, title):
        self.title = title

    def editText(self, text):
        self.text = text

    def editRating(self, rating):
        self.rating = rating

    def restore(self):
        self.isHidden = False


class Payment:
    def __init__(self, amount, status):
        self.id = None
        self.amount = amount
        self.status = status
        self.paidAt = None

    def markPaid(self):
        self.status = PaymentStatus.PAID

    def markFailed(self):
        self.status = PaymentStatus.FAILED


# ===============
# 3. REPOSITORIES 
# ===============
class Repository(ABC):
    @abstractmethod
    def findById(self, id):
        pass

    @abstractmethod
    def findAll(self):
        pass

    @abstractmethod
    def save(self, entity):
        pass

    @abstractmethod
    def delete(self, id):
        pass


class ParkingLotRepository(Repository):
    def __init__(self, db):
        self.db = db

    def findById(self, id):
        row = self.db.execute("SELECT * FROM parkings WHERE id = ?", (id,)).fetchone()
        return ParkingLot(row) if row else None

    def findAll(self):
        return [ParkingLot(r) for r in self.db.execute("SELECT * FROM parkings").fetchall()]

    def findByFilters(self, filters):
        sql = "SELECT * FROM parkings WHERE 1=1"
        params = []
        if filters.name:
            sql += " AND (name LIKE ? OR address LIKE ?)"
            params += [f"%{filters.name}%", f"%{filters.name}%"]
        if filters.max_price:
            sql += " AND price_per_hour <= ?"
            params.append(filters.max_price)
        return [ParkingLot(r) for r in self.db.execute(sql, params).fetchall()]

    def save(self, entity):
        pass

    def delete(self, id):
        self.db.execute("DELETE FROM parkings WHERE id = ?", (id,))
        self.db.commit()


class BookingRepository(Repository):
    def __init__(self, db):
        self.db = db

    def findById(self, id):
        row = self.db.execute("SELECT * FROM bookings WHERE id = ?", (id,)).fetchone()
        return Booking(row) if row else None

    def findByDriverId(self, user_id):
        rows = self.db.execute("SELECT * FROM bookings WHERE user_id = ? ORDER BY created_at DESC",
                               (user_id,)).fetchall()
        return [Booking(r) for r in rows]

    def findAll(self):
        return [Booking(r) for r in self.db.execute("SELECT * FROM bookings").fetchall()]

    def save(self, booking):
        self.db.execute("UPDATE bookings SET status = ? WHERE id = ?", (booking.status, booking.id))
        self.db.commit()

    def delete(self, id):
        pass


# ==========
# 4. CONTROL 
# ==========
class PaymentGateway:
    def requestPayment(self, amount, card_number):
        return card_number.replace(" ", "").endswith("0000") or card_number == ""

    def chargeAmount(self, amount):
        return True


class ParkingLocator:
    def __init__(self, db):
        self.repo = ParkingLotRepository(db)

    def findParkingSlot(self, filters):
        lots = self.repo.findByFilters(filters)
        result = []
        for p in lots:
            free = self.repo.db.execute("SELECT COUNT(*) FROM slots WHERE parking_id = ?", (p.id,)).fetchone()[0]
            result.append({"parking": p, "free": free})
        return result

    def checkAvailability(self, slot_id, time_range):
        return True


class BookingService:
    def __init__(self, db):
        self.db = db

    def checkAvailability(self, slot_id, date, start, end):
        conflict = self.db.execute(
            "SELECT 1 FROM bookings WHERE slot_id = ? AND status IN ('PENDING','CONFIRMED') "
            "AND start_time < ? AND end_time > ?",
            (slot_id, f"{date} {end}", f"{date} {start}")
        ).fetchone()
        return conflict is None

    def createBooking(self, user_id, slot_id, date, start, end, price):
        h1 = datetime.strptime(start, "%H:%M")
        h2 = datetime.strptime(end, "%H:%M")
        hours = (h2 - h1).total_seconds() / 3600
        amount = round(hours * price, 2)
        cur = self.db.execute(
            "INSERT INTO bookings (user_id, slot_id, start_time, end_time, status, amount, created_at) "
            "VALUES (?, ?, ?, ?, 'PENDING', ?, ?)",
            (user_id, slot_id, f"{date} {start}", f"{date} {end}", amount, datetime.now().isoformat())
        )
        self.db.commit()
        return cur.lastrowid

    def processPayment(self, booking_id, amount, card):
        gateway = PaymentGateway()
        if gateway.requestPayment(amount, card):
            self.updateBookingStatus(booking_id, "CONFIRMED")
            return True
        else:
            self.updateBookingStatus(booking_id, "CANCELLED")
            return False

    def updateBookingStatus(self, booking_id, status):
        self.db.execute("UPDATE bookings SET status = ? WHERE id = ?", (status, booking_id))
        self.db.commit()


# =================================
# 5. BOUNDARY (UI / Маршруты Flask)
# =================================
app = Flask(__name__)
app.secret_key = "parkease-secret-key-change-me"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        row = get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if row:
            if row["role"] == "driver":
                user = Driver(row)
            elif row["role"] == "admin":
                user = ParkingAdmin(row)
            else:
                user = Manager(row)
    return {"current_user": user}


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Войдите в систему", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session or session.get("role") not in roles:
                abort(403)
            return f(*args, **kwargs)

        return wrapper

    return decorator


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if row:
            if row["role"] == "driver":
                temp_user = Driver(row)
            elif row["role"] == "admin":
                temp_user = ParkingAdmin(row)
            else:
                temp_user = Manager(row)

            if temp_user.login(email, password):
                session["user_id"] = row["id"]
                session["role"] = row["role"]
                return redirect(url_for("index"))
        flash("Неверный email или пароль", "danger")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        from werkzeug.security import generate_password_hash
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        try:
            db.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'driver')",
                       (full_name, email, generate_password_hash(password)))
            db.commit()
            flash("Регистрация успешна. Войдите.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Пользователь с таким email уже существует", "danger")
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["role"] == 'driver':
        return redirect(url_for("search"))

    if session["role"] == 'admin':
        db = get_db()
        # Ищем первую парковку, где текущий пользователь является админом
        first_parking = db.execute("""
            SELECT p.id FROM parkings p 
            JOIN parking_admins pa ON p.id = pa.parking_id 
            WHERE pa.user_id = ? LIMIT 1
        """, (session["user_id"],)).fetchone()

        if first_parking:
            return redirect(url_for("admin_parking", parking_id=first_parking["id"]))
        else:
            return redirect(url_for("admin_parkings_list"))

    if session["role"] == 'manager':
        return redirect(url_for("manager_parkings"))


@app.route("/search")
@login_required
def search():
    locator = ParkingLocator(get_db())
    filters = SearchFilters(
        name=request.args.get("q", "").strip(),
        max_price=float(request.args.get("max_price")) if request.args.get("max_price") else None
    )
    result = locator.findParkingSlot(filters)
    return render_template("search.html", result=result, q=filters.name, max_price=filters.max_price)


@app.route("/parking/<int:parking_id>")
@login_required
def parking_detail(parking_id):
    db = get_db()
    repo = ParkingLotRepository(db)
    parking = repo.findById(parking_id)
    if not parking: abort(404)

    reviews = db.execute(
        "SELECT r.*, u.full_name FROM reviews r JOIN users u ON r.user_id = u.id WHERE r.parking_id = ? AND r.status = 'PUBLISHED'",
        (parking_id,)).fetchall()
    avg = db.execute("SELECT AVG(rating) FROM reviews WHERE parking_id = ? AND status = 'PUBLISHED'",
                     (parking_id,)).fetchone()[0]
    return render_template("parking_detail.html", parking=parking, reviews=reviews, avg=avg)


@app.route("/parking/<int:parking_id>/slots", methods=["GET", "POST"])
@login_required
def select_slot(parking_id):
    db = get_db()
    repo = ParkingLotRepository(db)
    parking = repo.findById(parking_id)
    date, start, end = request.values.get("date", ""), request.values.get("start", ""), request.values.get("end", "")

    slots = db.execute("SELECT * FROM slots WHERE parking_id = ? ORDER BY number", (parking_id,)).fetchall()
    busy_ids = set()

    if date and start and end:
        service = BookingService(db)
        for s in slots:
            if not service.checkAvailability(s["id"], date, start, end):
                busy_ids.add(s["id"])

    return render_template("select_slot.html", parking=parking, slots=slots, busy_ids=busy_ids, date=date, start=start,
                           end=end)


@app.route("/parking/<int:parking_id>/book", methods=["POST"])
@login_required
def book(parking_id):
    db = get_db()
    repo = ParkingLotRepository(db)
    parking = repo.findById(parking_id)

    slot_id, date, start, end = request.form.get("slot_id", type=int), request.form.get("date"), request.form.get(
        "start"), request.form.get("end")
    service = BookingService(db)

    if not service.checkAvailability(slot_id, date, start, end):
        flash("Это место уже занято", "danger")
        return redirect(url_for("select_slot", parking_id=parking_id, date=date, start=start, end=end))

    booking_id = service.createBooking(session["user_id"], slot_id, date, start, end, parking.price_per_hour)
    return redirect(url_for("payment", booking_id=booking_id))


@app.route("/payment/<int:booking_id>", methods=["GET", "POST"])
@login_required
def payment(booking_id):
    db = get_db()
    row = db.execute(
        "SELECT b.*, s.number AS slot_number, p.name AS parking_name, p.address FROM bookings b JOIN slots s ON b.slot_id = s.id JOIN parkings p ON s.parking_id = p.id WHERE b.id = ?",
        (booking_id,)).fetchone()

    if request.method == "POST":
        service = BookingService(db)
        card = request.form.get("card_number", "")
        service.processPayment(booking_id, row["amount"], card)
        return redirect(url_for("booking_result", booking_id=booking_id))

    return render_template("payment.html", booking=row)


@app.route("/booking/<int:booking_id>/result")
@login_required
def booking_result(booking_id):
    db = get_db()
    row = db.execute(
        "SELECT b.*, s.number AS slot_number, p.name AS parking_name FROM bookings b JOIN slots s ON b.slot_id = s.id JOIN parkings p ON s.parking_id = p.id WHERE b.id = ?",
        (booking_id,)).fetchone()
    return render_template("booking_result.html", booking=row)


@app.route("/profile")
@login_required
def profile():
    db = get_db()
    tab = request.args.get("tab", "bookings")

    bookings = db.execute(
        "SELECT b.*, s.number AS slot_number, p.name AS parking_name FROM bookings b JOIN slots s ON b.slot_id = s.id JOIN parkings p ON s.parking_id = p.id WHERE b.user_id = ? ORDER BY b.created_at DESC",
        (session["user_id"],)).fetchall()
    reviews = db.execute(
        "SELECT r.*, p.name AS parking_name FROM reviews r JOIN parkings p ON r.parking_id = p.id WHERE r.user_id = ?",
        (session["user_id"],)).fetchall()
    return render_template("profile.html", bookings=bookings, reviews=reviews, tab=tab)


@app.route("/booking/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    service = BookingService(get_db())
    service.updateBookingStatus(booking_id, "CANCELLED")
    return redirect(url_for("profile"))


@app.route("/parking/<int:parking_id>/review", methods=["POST"])
@login_required
def add_review(parking_id):
    db = get_db()
    db.execute(
        "INSERT INTO reviews (user_id, parking_id, rating, title, text, status, created_at) VALUES (?, ?, ?, ?, ?, 'PUBLISHED', ?)",
        (session["user_id"], parking_id, request.form.get("rating"), request.form.get("title"),
         request.form.get("text"), datetime.now().isoformat()))
    db.commit()
    return redirect(url_for("parking_detail", parking_id=parking_id))


@app.route("/reviews/<int:parking_id>")
@login_required
def reviews_list(parking_id):
    db = get_db()
    parking = ParkingLotRepository(db).findById(parking_id)
    reviews = db.execute(
        "SELECT r.*, u.full_name FROM reviews r JOIN users u ON r.user_id = u.id WHERE r.parking_id = ? AND r.status = 'PUBLISHED'",
        (parking_id,)).fetchall()
    return render_template("reviews.html", parking=parking, reviews=reviews)


# ========================
# ADMIN & MANAGER BOUNDARY
# ========================
def check_admin_for_parking(parking_id):
    row = get_db().execute("SELECT 1 FROM parking_admins WHERE parking_id = ? AND user_id = ?",
                           (parking_id, session["user_id"])).fetchone()
    return row is not None


@app.route("/admin/parkings")
@role_required("admin")
def admin_parkings_list():
    db = get_db()
    parkings = db.execute(
        "SELECT p.* FROM parkings p JOIN parking_admins pa ON p.id = pa.parking_id WHERE pa.user_id = ?",
        (session["user_id"],)).fetchall()
    return render_template("admin_parkings_list.html", parkings=parkings)


@app.route("/admin/parking/<int:parking_id>", methods=["GET", "POST"])
@role_required("admin", "manager")
def admin_parking(parking_id):
    if session["role"] == "admin" and not check_admin_for_parking(parking_id): abort(403)
    db = get_db()
    if request.method == "POST":
        db.execute("UPDATE parkings SET name=?, address=?, price_per_hour=?, work_hours=?, description=? WHERE id=?",
                   (request.form["name"], request.form["address"], request.form["price"], request.form["hours"],
                    request.form["description"], parking_id))
        db.commit()
        return redirect(url_for("admin_parking", parking_id=parking_id))

    parking = ParkingLotRepository(db).findById(parking_id)
    stats = {
        "active": db.execute(
            "SELECT COUNT(*) FROM bookings b JOIN slots s ON b.slot_id=s.id WHERE s.parking_id=? AND b.status IN ('PENDING','CONFIRMED')",
            (parking_id,)).fetchone()[0],
        "new_reviews": db.execute("SELECT COUNT(*) FROM reviews WHERE parking_id=? AND status='PUBLISHED'",
                                  (parking_id,)).fetchone()[0],
        "free": db.execute("SELECT COUNT(*) FROM slots WHERE parking_id=?", (parking_id,)).fetchone()[0]
    }
    if session["role"] == "admin":
        my_parkings = db.execute(
            "SELECT * FROM parkings p JOIN parking_admins pa ON p.id=pa.parking_id WHERE pa.user_id=?",
            (session["user_id"],)).fetchall()
    else:
        my_parkings = db.execute("SELECT * FROM parkings").fetchall()
    return render_template("admin_parking.html", parking=parking, stats=stats, my_parkings=my_parkings)


@app.route("/admin/parking/<int:parking_id>/bookings")
@role_required("admin", "manager")
def admin_bookings(parking_id):
    if session["role"] == "admin" and not check_admin_for_parking(parking_id): abort(403)
    db = get_db()
    bookings = db.execute(
        "SELECT b.*, u.full_name, s.number AS slot_number FROM bookings b JOIN users u ON b.user_id=u.id JOIN slots s ON b.slot_id=s.id WHERE s.parking_id=? ORDER BY b.created_at DESC",
        (parking_id,)).fetchall()
    if session["role"] == "admin":
        my_parkings = db.execute(
            "SELECT * FROM parkings p JOIN parking_admins pa ON p.id=pa.parking_id WHERE pa.user_id=?",
            (session["user_id"],)).fetchall()
    else:
        my_parkings = db.execute("SELECT * FROM parkings").fetchall()
    return render_template("admin_bookings.html", parking={"id": parking_id}, bookings=bookings,
                           my_parkings=my_parkings)


@app.route("/admin/booking/<int:booking_id>/status/<status>", methods=["POST"])
@role_required("admin", "manager")
def admin_set_booking_status(booking_id, status):
    BookingService(get_db()).updateBookingStatus(booking_id, status)
    return redirect(request.referrer)


@app.route("/admin/parking/<int:parking_id>/reviews")
@role_required("admin", "manager")
def admin_reviews(parking_id):
    if session["role"] == "admin" and not check_admin_for_parking(parking_id): abort(403)
    db = get_db()
    status_filter = request.args.get("status", "ALL")
    sql = "SELECT r.*, u.full_name FROM reviews r JOIN users u ON r.user_id=u.id WHERE r.parking_id=?"
    params = [parking_id]
    if status_filter != "ALL":
        sql += " AND r.status = ?"
        params.append(status_filter)
    reviews = db.execute(sql, params).fetchall()
    if session["role"] == "admin":
        my_parkings = db.execute(
            "SELECT * FROM parkings p JOIN parking_admins pa ON p.id=pa.parking_id WHERE pa.user_id=?",
            (session["user_id"],)).fetchall()
    else:
        my_parkings = db.execute("SELECT * FROM parkings").fetchall()
    return render_template("admin_reviews.html", parking={"id": parking_id}, reviews=reviews,
                           current_status=status_filter, my_parkings=my_parkings)


@app.route("/admin/review/<int:review_id>/toggle", methods=["POST"])
@role_required("admin", "manager")
def admin_toggle_review(review_id):
    db = get_db()
    row = db.execute("SELECT status FROM reviews WHERE id=?", (review_id,)).fetchone()
    new_status = "HIDDEN" if row["status"] == "PUBLISHED" else "PUBLISHED"
    db.execute("UPDATE reviews SET status=? WHERE id=?", (new_status, review_id))
    db.commit()
    return redirect(request.referrer)


@app.route("/manager/parkings")
@role_required("manager")
def manager_parkings():
    parkings = ParkingLotRepository(get_db()).findAll()
    return render_template("manager_parkings.html", parkings=parkings)


@app.route("/manager/admins")
@role_required("manager")
def manager_admins_redirect():
    db = get_db()
    first_parking = db.execute("SELECT id FROM parkings LIMIT 1").fetchone()
    if first_parking:
        return redirect(url_for("manager_admins", parking_id=first_parking["id"]))
    flash("В системе пока нет парковок", "warning")
    return redirect(url_for("manager_parkings"))


@app.route("/manager/parking/create", methods=["POST"])
@role_required("manager")
def manager_create_parking():
    db = get_db()
    cur = db.execute(
        "INSERT INTO parkings (name, address, price_per_hour, work_hours, total_slots) VALUES (?, ?, ?, ?, ?)",
        (request.form["name"], request.form["address"], request.form["price"], request.form["hours"],
         request.form["total_slots"]))
    parking_id = cur.lastrowid
    for n in range(1, int(request.form["total_slots"]) + 1):
        db.execute("INSERT INTO slots (parking_id, number) VALUES (?, ?)", (parking_id, n))
    db.commit()
    return redirect(url_for("manager_parkings"))


@app.route("/manager/parking/<int:parking_id>/delete", methods=["POST"])
@role_required("manager")
def manager_delete_parking(parking_id):
    ParkingLotRepository(get_db()).delete(parking_id)
    return redirect(url_for("manager_parkings"))


@app.route("/manager/parking/<int:parking_id>/admins", methods=["GET", "POST"])
@role_required("manager")
def manager_admins(parking_id):
    db = get_db()
    if request.method == "POST":
        from werkzeug.security import generate_password_hash
        email = request.form["email"]
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            db.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                       (email, email, generate_password_hash("123456")))
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        try:
            db.execute("INSERT INTO parking_admins (parking_id, user_id) VALUES (?, ?)", (parking_id, user["id"]))
            db.commit()
        except sqlite3.IntegrityError:
            pass
        return redirect(url_for("manager_admins", parking_id=parking_id))

    admins = db.execute("SELECT u.* FROM users u JOIN parking_admins pa ON u.id=pa.user_id WHERE pa.parking_id=?",
                        (parking_id,)).fetchall()
    parking = ParkingLotRepository(db).findById(parking_id)
    my_parkings = db.execute("SELECT * FROM parkings").fetchall()
    return render_template("manager_admins.html", parking=parking, admins=admins, my_parkings=my_parkings)


@app.route("/manager/parking/<int:parking_id>/admins/<int:user_id>/remove", methods=["POST"])
@role_required("manager")
def manager_remove_admin(parking_id, user_id):
    db = get_db()
    db.execute("DELETE FROM parking_admins WHERE parking_id=? AND user_id=?", (parking_id, user_id))
    db.commit()
    return redirect(url_for("manager_admins", parking_id=parking_id))


if __name__ == "__main__":
    app.run(debug=True)
