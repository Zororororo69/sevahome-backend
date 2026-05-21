from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from sqlalchemy.orm import Session
from database import engine, get_db, Base
import models, schemas
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
import os
from dotenv import load_dotenv

load_dotenv()

# --- Setup ---
Base.metadata.create_all(bind=engine)
app = FastAPI(title="SevaHome API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY")
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# --- Helper Functions ---
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def create_token(user_id: int, role: str):
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

# --- Routes ---
@app.get("/")
def home():
    return {"message": "SevaHome API is running!"}

@app.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserRegister, db: Session = Depends(get_db)):
    try:
        existing = db.query(models.User).filter(models.User.email == user.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered!")
        
        existing_phone = db.query(models.User).filter(models.User.phone == user.phone).first()
        if existing_phone:
            raise HTTPException(status_code=400, detail="Phone already registered!")
        
        if user.role not in ["customer", "worker"]:
            raise HTTPException(status_code=400, detail="Role must be customer or worker!")
        
        new_user = models.User(
            name=user.name,
            email=user.email,
            password=hash_password(user.password),
            phone=user.phone,
            role=user.role
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except HTTPException:
        raise
    except Exception as e:
        print(f"REGISTER ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login")
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    # Find user
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid email or password!")
    
    # Check password
    if not verify_password(credentials.password, user.password):
        raise HTTPException(status_code=400, detail="Invalid email or password!")
    
    # Create token
    token = create_token(user.id, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "name": user.name,
        "user_id": user.id
    }

@app.post("/worker/profile")
def create_worker_profile(
    profile: schemas.WorkerProfileCreate,
    db: Session = Depends(get_db)
):
    try:
        # For now we'll pass user_id directly
        # Later we'll get it from JWT token
        new_profile = models.WorkerProfile(
            user_id=profile.user_id,
            bio=profile.bio,
            hourly_rate=profile.hourly_rate,
            experience=profile.experience,
            location=profile.location,
            skills=profile.skills
        )
        db.add(new_profile)
        db.commit()
        db.refresh(new_profile)
        return new_profile
    except Exception as e:
        print(f"PROFILE ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/workers")
def get_workers(
    location: str = None,
    skill: str = None,
    db: Session = Depends(get_db)
):
    try:
        query = db.query(models.WorkerProfile, models.User).join(
            models.User, models.WorkerProfile.user_id == models.User.id
        )
        if location:
            query = query.filter(models.WorkerProfile.location.ilike(f"%{location}%"))
        if skill:
            query = query.filter(models.WorkerProfile.skills.ilike(f"%{skill}%"))
        results = query.all()
        workers = []
        for profile, user in results:
            w = profile.__dict__.copy()
            w["name"] = user.name
            w["email"] = user.email
            workers.append(w)
        return workers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/workers/{worker_id}")
def get_worker(worker_id: int, db: Session = Depends(get_db)):
    try:
        result = db.query(models.WorkerProfile, models.User).join(
            models.User, models.WorkerProfile.user_id == models.User.id
        ).filter(models.WorkerProfile.id == worker_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="Worker not found!")
        profile, user = result
        w = profile.__dict__.copy()
        w["name"] = user.name
        w["email"] = user.email
        return w
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/bookings")
def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db)):
    try:
        # Check worker exists
        worker = db.query(models.WorkerProfile).filter(
            models.WorkerProfile.id == booking.worker_id
        ).first()
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found!")

        # Check worker is available
        if not worker.is_available:
            raise HTTPException(status_code=400, detail="Worker is not available!")

        new_booking = models.Booking(
            customer_id=booking.customer_id,
            worker_id=booking.worker_id,
            service_id=booking.service_id,
            date=booking.date,
            notes=booking.notes,
            status="pending"
        )
        db.add(new_booking)
        db.commit()
        db.refresh(new_booking)
        return new_booking
    except HTTPException:
        raise
    except Exception as e:
        print(f"BOOKING ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/bookings/{booking_id}")
def get_booking(booking_id: int, db: Session = Depends(get_db)):
    try:
        booking = db.query(models.Booking).filter(
            models.Booking.id == booking_id
        ).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found!")
        return booking
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/customers/{customer_id}/bookings")
def get_customer_bookings(customer_id: int, db: Session = Depends(get_db)):
    try:
        bookings = db.query(models.Booking).filter(
            models.Booking.customer_id == customer_id
        ).all()
        return bookings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))    
    
@app.post("/services")
def create_service(name: str, description: str, db: Session = Depends(get_db)):
    try:
        service = models.Service(name=name, description=description)
        db.add(service)
        db.commit()
        db.refresh(service)
        return service
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))    
    
@app.post("/reviews")
def create_review(review: schemas.ReviewCreate, db: Session = Depends(get_db)):
    try:
        # Check booking exists
        booking = db.query(models.Booking).filter(
            models.Booking.id == review.booking_id
        ).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found!")

        # Check booking is completed
        if booking.status != "completed":
            raise HTTPException(status_code=400, detail="Can only review completed bookings!")

        # Check rating is between 1 and 5
        if review.rating < 1 or review.rating > 5:
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5!")

        new_review = models.Review(
            booking_id=review.booking_id,
            reviewer_id=review.reviewer_id,
            reviewee_id=review.reviewee_id,
            rating=review.rating,
            comment=review.comment
        )
        db.add(new_review)
        db.commit()
        db.refresh(new_review)

        # Update worker trust score
        worker_reviews = db.query(models.Review).filter(
            models.Review.reviewee_id == review.reviewee_id
        ).all()
        avg_rating = sum(r.rating for r in worker_reviews) / len(worker_reviews)
        worker_profile = db.query(models.WorkerProfile).filter(
            models.WorkerProfile.user_id == review.reviewee_id
        ).first()
        if worker_profile:
            worker_profile.trust_score = round(avg_rating * 20, 1)
            db.commit()

        return new_review
    except HTTPException:
        raise
    except Exception as e:
        print(f"REVIEW ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/workers/{worker_id}/reviews")
def get_worker_reviews(worker_id: int, db: Session = Depends(get_db)):
    try:
        reviews = db.query(models.Review).filter(
            models.Review.reviewee_id == worker_id
        ).all()
        return reviews
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/bookings/{booking_id}/status")
def update_booking_status(booking_id: int, status: str, db: Session = Depends(get_db)):
    try:
        valid_statuses = ["pending", "confirmed", "completed", "cancelled"]
        if status not in valid_statuses:
            raise HTTPException(status_code=400, detail="Invalid status!")

        booking = db.query(models.Booking).filter(
            models.Booking.id == booking_id
        ).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found!")

        booking.status = status
        db.commit()
        db.refresh(booking)
        return booking
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/worker/submit-verification")
async def submit_verification(
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        # Check worker profile exists
        worker = db.query(models.WorkerProfile).filter(
            models.WorkerProfile.user_id == user_id
        ).first()
        if not worker:
            raise HTTPException(status_code=404, detail="Worker profile not found!")

        # Save file
        import shutil
        import os
        os.makedirs("verification_docs", exist_ok=True)
        file_path = f"verification_docs/{user_id}_{file.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Update worker verification status
        worker.verification_doc = file_path
        worker.verification_status = "pending"
        db.commit()

        return {"message": "Verification document submitted successfully!"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/pending-verifications")
def get_pending_verifications(db: Session = Depends(get_db)):
    try:
        workers = db.query(models.WorkerProfile).filter(
            models.WorkerProfile.verification_status == "pending"
        ).all()
        return workers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/admin/verify-worker/{worker_id}")
def verify_worker(worker_id: int, approve: bool, db: Session = Depends(get_db)):
    try:
        worker = db.query(models.WorkerProfile).filter(
            models.WorkerProfile.id == worker_id
        ).first()
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found!")

        if approve:
            worker.verification_status = "verified"
            worker.is_verified_worker = True
            worker.trust_score = min(worker.trust_score + 20, 100)
        else:
            worker.verification_status = "rejected"
            worker.is_verified_worker = False

        db.commit()
        return {"message": f"Worker {'verified' if approve else 'rejected'} successfully!"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))   

@app.post("/worker/generate-bio")
def generate_bio(
    name: str,
    skills: str,
    experience: int,
    location: str,
    db: Session = Depends(get_db)
):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": """You are a professional profile writer for a home services app in Nepal. 
                Write a short, friendly, professional bio for a worker.
                Write in simple English. Maximum 3 sentences.
                Make it warm and trustworthy."""},
                {"role": "user", "content": f"Write a bio for: Name: {name}, Skills: {skills}, Experience: {experience} years, Location: {location}"}
            ]
        )
        return {"bio": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))  

@app.get("/workers/{user_id}/bookings")
def get_worker_bookings(user_id: int, db: Session = Depends(get_db)):
    try:
        profile = db.query(models.WorkerProfile).filter(
            models.WorkerProfile.user_id == user_id
        ).first()
        if not profile:
            return []
        bookings = db.query(models.Booking).filter(
            models.Booking.worker_id == profile.id
        ).all()
        return bookings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))