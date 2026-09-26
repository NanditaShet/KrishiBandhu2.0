
import os, base64, mimetypes, hmac, hashlib
from datetime import datetime
from pathlib import Path
from functools import wraps

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()
BASE = Path(__file__).resolve().parent
UPLOAD_DIR = BASE / "uploads"
INSTANCE_DIR = BASE / "instance"
UPLOAD_DIR.mkdir(exist_ok=True)
INSTANCE_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + str(INSTANCE_DIR / "krishibandhu.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
db = SQLAlchemy(app)
ALLOWED = {"png","jpg","jpeg","webp"}

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    role=db.Column(db.String(20),nullable=False)
    name=db.Column(db.String(120),nullable=False)
    email=db.Column(db.String(160),unique=True,nullable=False)
    password_hash=db.Column(db.String(255),nullable=False)
    phone=db.Column(db.String(30))
    language=db.Column(db.String(5),default="en")
    location=db.Column(db.String(160))
    created_at=db.Column(db.DateTime,default=datetime.utcnow)

class FarmerProfile(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey("user.id"),unique=True,nullable=False)
    crop=db.Column(db.String(100)); farm_size=db.Column(db.String(50)); district=db.Column(db.String(100)); state=db.Column(db.String(100),default="Karnataka")
    user=db.relationship("User")

class ExpertProfile(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey("user.id"),unique=True,nullable=False)
    qualification=db.Column(db.String(160)); specialization=db.Column(db.String(160)); experience_years=db.Column(db.Integer,default=0)
    bio=db.Column(db.Text); online_fee=db.Column(db.Float,default=0); field_fee=db.Column(db.Float,default=0); availability=db.Column(db.String(255))
    user=db.relationship("User")

class CustomerProfile(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey("user.id"),unique=True,nullable=False)
    address=db.Column(db.Text); user=db.relationship("User")

class CropReport(db.Model):
    id=db.Column(db.Integer,primary_key=True); farmer_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    crop=db.Column(db.String(100),nullable=False); image_path=db.Column(db.String(255)); voice_text=db.Column(db.Text); description=db.Column(db.Text)
    ai_result=db.Column(db.Text); confidence=db.Column(db.Float); status=db.Column(db.String(50),default="AI reviewed"); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    farmer=db.relationship("User")

class ExpertRequest(db.Model):
    id=db.Column(db.Integer,primary_key=True); farmer_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    expert_id=db.Column(db.Integer,db.ForeignKey("user.id")); crop_report_id=db.Column(db.Integer,db.ForeignKey("crop_report.id"))
    consultation_type=db.Column(db.String(30),default="online"); status=db.Column(db.String(40),default="Pending")
    farmer_message=db.Column(db.Text); expert_response=db.Column(db.Text); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    farmer=db.relationship("User",foreign_keys=[farmer_id]); expert=db.relationship("User",foreign_keys=[expert_id]); report=db.relationship("CropReport")

class Product(db.Model):
    id=db.Column(db.Integer,primary_key=True); farmer_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    name=db.Column(db.String(160),nullable=False); crop=db.Column(db.String(100),nullable=False); quantity_kg=db.Column(db.Float,nullable=False)
    price_per_kg=db.Column(db.Float,nullable=False); location=db.Column(db.String(160),nullable=False); harvest_date=db.Column(db.String(40))
    quality=db.Column(db.String(80)); description=db.Column(db.Text); active=db.Column(db.Boolean,default=True); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    farmer=db.relationship("User")

class Order(db.Model):
    id=db.Column(db.Integer,primary_key=True); customer_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False); farmer_id=db.Column(db.Integer,db.ForeignKey("user.id"),nullable=False)
    product_id=db.Column(db.Integer,db.ForeignKey("product.id"),nullable=False); quantity_kg=db.Column(db.Float,nullable=False); unit_price=db.Column(db.Float,nullable=False)
    total_amount=db.Column(db.Float,nullable=False); status=db.Column(db.String(40),default="Payment Pending"); payment_order_id=db.Column(db.String(120)); payment_id=db.Column(db.String(120))
    delivery_address=db.Column(db.Text); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    customer=db.relationship("User",foreign_keys=[customer_id]); farmer=db.relationship("User",foreign_keys=[farmer_id]); product=db.relationship("Product")

class TransportRequest(db.Model):
    id=db.Column(db.Integer,primary_key=True); order_id=db.Column(db.Integer,db.ForeignKey("order.id"),nullable=False)
    pickup=db.Column(db.String(255),nullable=False); destination=db.Column(db.String(255),nullable=False); status=db.Column(db.String(40),default="Requested")
    provider=db.Column(db.String(80),default="Local transport"); tracking_number=db.Column(db.String(120)); created_at=db.Column(db.DateTime,default=datetime.utcnow)
    order=db.relationship("Order")

def user():
    return db.session.get(User,session.get("user_id")) if session.get("user_id") else None

def required(role=None):
    def deco(fn):
        @wraps(fn)
        def w(*a,**k):
            u=user()
            if not u:return redirect(url_for("home"))
            if role and u.role!=role:return redirect(url_for("dashboard"))
            return fn(*a,**k)
        return w
    return deco

@app.context_processor
def ctx(): return {"current_user":user()}

@app.route("/")
def home(): return render_template("home.html")

@app.route("/register/<role>",methods=["GET","POST"])
def register(role):
    if role not in {"farmer","expert","customer"}: return redirect(url_for("home"))
    if request.method=="POST":
        email=request.form["email"].strip().lower()
        if User.query.filter_by(email=email).first(): flash("Email already registered."); return redirect(request.url)
        u=User(role=role,name=request.form["name"],email=email,password_hash=generate_password_hash(request.form["password"]),
               phone=request.form.get("phone"),language=request.form.get("language","en"),location=request.form.get("location"))
        db.session.add(u); db.session.flush()
        if role=="farmer":
            db.session.add(FarmerProfile(user_id=u.id,crop=request.form.get("crop"),farm_size=request.form.get("farm_size"),district=request.form.get("district"),state=request.form.get("state") or "Karnataka"))
        elif role=="expert":
            db.session.add(ExpertProfile(user_id=u.id,qualification=request.form.get("qualification"),specialization=request.form.get("specialization"),
                experience_years=int(request.form.get("experience_years") or 0),bio=request.form.get("bio"),
                online_fee=float(request.form.get("online_fee") or 0),field_fee=float(request.form.get("field_fee") or 0),availability=request.form.get("availability")))
        else: db.session.add(CustomerProfile(user_id=u.id,address=request.form.get("address")))
        db.session.commit(); return redirect(url_for("login",role=role))
    return render_template("register.html",role=role)

@app.route("/login/<role>",methods=["GET","POST"])
def login(role):
    if request.method=="POST":
        u=User.query.filter_by(email=request.form["email"].strip().lower(),role=role).first()
        if not u or not check_password_hash(u.password_hash,request.form["password"]): flash("Invalid login details."); return redirect(request.url)
        session.clear(); session["user_id"]=u.id; session["role"]=u.role; return redirect(url_for("dashboard"))
    return render_template("login.html",role=role)

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("home"))

@app.route("/dashboard")
@required()
def dashboard():
    u=user()
    if u.role=="farmer":
        p=FarmerProfile.query.filter_by(user_id=u.id).first()
        return render_template("farmer_dashboard.html",profile=p)
    if u.role=="expert":
        p=ExpertProfile.query.filter_by(user_id=u.id).first()
        reqs=ExpertRequest.query.order_by(ExpertRequest.created_at.desc()).all()
        return render_template("expert_dashboard.html",profile=p,requests=reqs)
    return render_template("customer_dashboard.html",products=Product.query.filter_by(active=True).all(),orders=Order.query.filter_by(customer_id=u.id).all())

@app.route("/profile",methods=["GET","POST"])
@required()
def profile():
    u=user()
    if request.method=="POST":
        u.name=request.form["name"]; u.phone=request.form.get("phone"); u.location=request.form.get("location"); u.language=request.form.get("language","en")
        if u.role=="farmer":
            p=FarmerProfile.query.filter_by(user_id=u.id).first() or FarmerProfile(user_id=u.id)
            p.crop=request.form.get("crop"); p.farm_size=request.form.get("farm_size"); p.district=request.form.get("district"); p.state=request.form.get("state")
            db.session.add(p)
        elif u.role=="expert":
            p=ExpertProfile.query.filter_by(user_id=u.id).first() or ExpertProfile(user_id=u.id)
            p.qualification=request.form.get("qualification"); p.specialization=request.form.get("specialization"); p.bio=request.form.get("bio"); p.availability=request.form.get("availability")
            p.experience_years=int(request.form.get("experience_years") or 0); p.online_fee=float(request.form.get("online_fee") or 0); p.field_fee=float(request.form.get("field_fee") or 0); db.session.add(p)
        else:
            p=CustomerProfile.query.filter_by(user_id=u.id).first() or CustomerProfile(user_id=u.id); p.address=request.form.get("address"); db.session.add(p)
        db.session.commit(); flash("Profile saved."); return redirect(url_for("profile"))
    return render_template("profile.html",farmer=FarmerProfile.query.filter_by(user_id=u.id).first(),expert=ExpertProfile.query.filter_by(user_id=u.id).first(),customer=CustomerProfile.query.filter_by(user_id=u.id).first())

@app.route("/crop-health", methods=["GET", "POST"])
@required("farmer")
def crop_health():

    if request.method == "GET":
        return render_template("crop_health.html")

    crop = request.form.get("crop", "")
    desc = request.form.get("description", "")
    voice = request.form.get("voice", "")

    file = request.files.get("image")
    filename = None

    if file and file.filename:
        filename = secure_filename(file.filename)
        filename = f"{user().id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        file.save(UPLOAD_DIR / filename)

    report = CropReport(
        farmer_id=user().id,
        crop=crop,
        image_path=filename,
        voice_text=voice,
        description=desc
    )

    db.session.add(report)
    db.session.commit()

    result, confidence = analyze_crop(
        filename,
        crop,
        desc,
        voice
    )

    report.ai_result = result
    report.confidence = confidence 
    db.session.commit()

    return redirect(url_for("crop_result", rid=report.id))


def analyze_crop(path, crop, desc, voice):

    key = os.getenv("GEMINI_API_KEY")

    if not key:
        return "Add GEMINI_API_KEY to .env to enable live AI analysis.", None

    try:
        from google import genai
        from google.genai import types
        import json
        import time

        client = genai.Client(api_key=key)

        prompt = f"""
You are an agricultural decision-support assistant.

Crop: {crop}

Farmer description: {desc}

Voice transcription: {voice}

Analyze the uploaded crop image.

Return ONLY valid JSON in this format:

{{
  "possible_issue": "possible crop issue",
  "confidence_percent": 75,
  "observed_symptoms": "symptoms observed in the image",
  "advisory": "safe general advisory",
  "escalation_needed": false
}}

Never claim a confirmed diagnosis.
Do not provide dangerous pesticide dosage instructions.
Recommend an agricultural expert when uncertain.
"""

        contents = [prompt]

        if path:
            image_bytes = (UPLOAD_DIR / path).read_bytes()

            contents.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mimetypes.guess_type(path)[0] or "image/jpeg"
                )
            )

        response = None

        for attempt in range(3):

            try:
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=contents
                )

                break

            except Exception as e:

                error_message = str(e)

                if "503" in error_message and attempt < 2:
                    time.sleep(3)

                else:
                    return f"AI service error: {error_message}", None

        if response is None:
            return "AI service did not return a response.", None

        out = response.text or ""

        conf = None

        try:

            # Remove Markdown code fences returned by Gemini
            cleaned = out.strip()

            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]

            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]

            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            cleaned = cleaned.strip()

            # Convert Gemini response into JSON
            obj = json.loads(cleaned)

            # Extract confidence
            if obj.get("confidence_percent") is not None:
                conf = float(obj.get("confidence_percent"))

            # Store clean formatted JSON
            out = json.dumps(
                obj,
                ensure_ascii=False,
                indent=2
            )

        except Exception:
            # Keep original response if parsing fails
            pass

        return out, conf

    except Exception as e:
        return f"AI service error: {e}", None
@app.route("/crop-result/<int:rid>")
@required("farmer")
def crop_result(rid):
    r=CropReport.query.get_or_404(rid)
    if r.farmer_id!=user().id:return redirect(url_for("dashboard"))
    return render_template("crop_result.html",report=r)

@app.route("/uploads/<filename>")
def uploaded_file(filename): return send_from_directory(UPLOAD_DIR,filename)

@app.route("/experts")
@required("farmer")
def experts(): return render_template("experts.html",experts=ExpertProfile.query.all())

@app.route("/expert/request/<int:eid>",methods=["POST"])
@required("farmer")
def expert_request(eid):
    r=ExpertRequest(farmer_id=user().id,expert_id=eid,consultation_type=request.form.get("consultation_type","online"),farmer_message=request.form.get("message"))
    db.session.add(r); db.session.commit(); flash("Consultation request sent."); return redirect(url_for("experts"))

@app.route("/expert/case/<int:rid>",methods=["GET","POST"])
@required("expert")
def expert_case(rid):
    r=ExpertRequest.query.get_or_404(rid)
    if request.method=="POST":
        a=request.form.get("action"); r.expert_id=user().id
        r.status={"accept":"Accepted","reject":"Rejected","respond":"Expert Responded"}.get(a,r.status)
        if a=="respond":r.expert_response=request.form.get("expert_response")
        db.session.commit(); return redirect(url_for("expert_case",rid=rid))
    return render_template("expert_case.html",req=r)

@app.route("/products")
@required()
def products(): return render_template("products.html",products=Product.query.filter_by(active=True).all())

@app.route("/products/new",methods=["GET","POST"])
@required("farmer")
def new_product():
    if request.method=="POST":
        p=Product(farmer_id=user().id,name=request.form["name"],crop=request.form["crop"],quantity_kg=float(request.form["quantity_kg"]),
                  price_per_kg=float(request.form["price_per_kg"]),location=request.form["location"],harvest_date=request.form.get("harvest_date"),
                  quality=request.form.get("quality"),description=request.form.get("description"))
        db.session.add(p); db.session.commit(); return redirect(url_for("products"))
    return render_template("new_product.html")

@app.route("/products/<int:pid>")
@required()
def product_detail(pid): return render_template("product_detail.html",product=Product.query.get_or_404(pid))

@app.route("/orders/create/<int:pid>",methods=["POST"])
@required("customer")
def create_order(pid):
    p=Product.query.get_or_404(pid); qty=float(request.form["quantity_kg"])
    if qty<=0 or qty>p.quantity_kg: flash("Invalid quantity."); return redirect(url_for("product_detail",pid=pid))
    o=Order(customer_id=user().id,farmer_id=p.farmer_id,product_id=p.id,quantity_kg=qty,unit_price=p.price_per_kg,total_amount=qty*p.price_per_kg,delivery_address=request.form["delivery_address"])
    db.session.add(o); db.session.commit()
    if os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"):
        import razorpay
        c=razorpay.Client(auth=(os.getenv("RAZORPAY_KEY_ID"),os.getenv("RAZORPAY_KEY_SECRET")))
        ro=c.order.create({"amount":int(o.total_amount*100),"currency":"INR","receipt":f"KB-{o.id}"})
        o.payment_order_id=ro["id"]; db.session.commit()
        return render_template("payment.html",order=o,key_id=os.getenv("RAZORPAY_KEY_ID"))
    flash("Order saved. Add Razorpay test keys to enable online payment."); return redirect(url_for("orders"))

@app.route("/payment/verify",methods=["POST"])
@required("customer")
def payment_verify():
    d=request.get_json(); o=Order.query.get_or_404(int(d["order_id"]))
    msg=f'{d["razorpay_order_id"]}|{d["razorpay_payment_id"]}'.encode()
    expected=hmac.new(os.getenv("RAZORPAY_KEY_SECRET","").encode(),msg,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,d["razorpay_signature"]): return jsonify(ok=False,error="Signature verification failed"),400
    o.payment_id=d["razorpay_payment_id"]; o.status="Paid"; db.session.commit(); return jsonify(ok=True,redirect=url_for("orders"))

@app.route("/orders")
@required("customer")
def orders(): return render_template("orders.html",orders=Order.query.filter_by(customer_id=user().id).order_by(Order.created_at.desc()).all())

@app.route("/farmer-orders")
@required("farmer")
def farmer_orders(): return render_template("farmer_orders.html",orders=Order.query.filter_by(farmer_id=user().id).order_by(Order.created_at.desc()).all())

@app.route("/transport/<int:oid>",methods=["GET","POST"])
@required("farmer")
def transport(oid):
    o=Order.query.get_or_404(oid)
    if o.farmer_id!=user().id:return redirect(url_for("dashboard"))
    if request.method=="POST":
        db.session.add(TransportRequest(order_id=oid,pickup=request.form["pickup"],destination=request.form["destination"])); db.session.commit()
        flash("Transport request recorded."); return redirect(url_for("farmer_orders"))
    return render_template("transport.html",order=o)

@app.route("/weather")
@required()
def weather(): return render_template("weather.html")

@app.route("/api/weather")
@required()
def api_weather():
    loc = request.args.get("location") or user().location

    if not loc:
        return jsonify(
            error="Add a location to your profile first."
        ), 400

    # Find the latitude and longitude of the farmer's location
    g = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": loc,
            "count": 1,
            "language": "en",
            "format": "json"
        },
        timeout=10
    ).json()

    if not g.get("results"):
        return jsonify(
            error="Location not found."
        ), 404

    x = g["results"][0]

    # Get current + hourly forecast
    w = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": x["latitude"],
            "longitude": x["longitude"],

            # Current weather
            "current": (
                "temperature_2m,"
                "relative_humidity_2m,"
                "precipitation,"
                "weather_code,"
                "wind_speed_10m"
            ),

            # Upcoming hourly weather
            "hourly": (
                "temperature_2m,"
                "precipitation_probability,"
                "precipitation,"
                "weather_code,"
                "wind_speed_10m"
            ),

            "forecast_days": 2,
            "timezone": "auto"
        },
        timeout=10
    ).json()

    return jsonify(
        location=x,
        weather=w
    )

@app.route("/market")
@required()
def market(): return render_template("market.html")

@app.route("/api/market")
@required()
def api_market():
    url=os.getenv("MARKET_API_URL")
    if not url:return jsonify(verified=False,message="Configure an official market-data API in MARKET_API_URL.",prices=[])
    try:
        r=requests.get(url,headers={"Authorization":f"Bearer {os.getenv('MARKET_API_KEY','')}"},timeout=15); r.raise_for_status()
        return jsonify(verified=True,data=r.json())
    except Exception as e:return jsonify(verified=False,message=str(e),prices=[]),502

@app.route("/schemes")
@required()
def schemes(): return render_template("schemes.html")

with app.app_context(): db.create_all()
if __name__=="__main__": app.run(debug=True)