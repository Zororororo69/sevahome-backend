from fastapi import FastAPI, HTTPException, Depends
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
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY")

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
        "name": user.name
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
        query = db.query(models.WorkerProfile)
        if location:
            query = query.filter(models.WorkerProfile.location.ilike(f"%{location}%"))
        if skill:
            query = query.filter(models.WorkerProfile.skills.ilike(f"%{skill}%"))
        workers = query.all()
        return workers
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/workers/{worker_id}")
def get_worker(worker_id: int, db: Session = Depends(get_db)):
    try:
        worker = db.query(models.WorkerProfile).filter(
            models.WorkerProfile.id == worker_id
        ).first()
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found!")
        return worker
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