from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# --- User Schemas ---
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: str
    role: str  # "customer" or "worker"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    role: str
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True

# --- Worker Profile Schemas ---
class WorkerProfileCreate(BaseModel):
    bio: Optional[str] = None
    hourly_rate: float
    experience: int = 0
    location: str
    skills: Optional[str] = None

class WorkerProfileResponse(BaseModel):
    id: int
    bio: Optional[str]
    hourly_rate: float
    experience: int
    location: str
    trust_score: float
    is_available: bool
    skills: Optional[str]

    class Config:
        from_attributes = True

# --- Booking Schemas ---
class BookingCreate(BaseModel):
    worker_id: int
    service_id: int
    date: datetime
    notes: Optional[str] = None

class BookingResponse(BaseModel):
    id: int
    customer_id: int
    worker_id: int
    service_id: int
    date: datetime
    status: str
    total_price: Optional[float]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# --- Review Schemas ---
class ReviewCreate(BaseModel):
    booking_id: int
    reviewee_id: int
    rating: float
    comment: Optional[str] = None

class ReviewResponse(BaseModel):
    id: int
    booking_id: int
    reviewer_id: int
    reviewee_id: int
    rating: float
    comment: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class WorkerProfileCreate(BaseModel):
    user_id: int
    bio: Optional[str] = None
    hourly_rate: float
    experience: int = 0
    location: str
    skills: Optional[str] = None

class BookingCreate(BaseModel):
    customer_id: int
    worker_id: int
    service_id: int
    date: datetime
    notes: Optional[str] = None

class ReviewCreate(BaseModel):
    booking_id: int
    reviewer_id: int
    reviewee_id: int
    rating: float
    comment: Optional[str] = None    

class WorkerProfileUpdate(BaseModel):
    bio: str = None
    hourly_rate: float = None
    experience: int = None
    location: str = None
    skills: str = None
    is_available: bool = None