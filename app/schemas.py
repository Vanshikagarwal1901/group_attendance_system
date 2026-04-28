from datetime import datetime

from pydantic import BaseModel, Field

from app.models import UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=5)
    full_name: str = Field(min_length=1, max_length=100)


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str | None = Field(default=None, min_length=5)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str
    role: UserRole

    class Config:
        from_attributes = True


class AssignmentCreate(BaseModel):
    faculty_id: int
    student_id: int


class AttendanceSessionCreate(BaseModel):
    subject_name: str = Field(min_length=1, max_length=120)


class AttendanceSessionUpdate(BaseModel):
    subject_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_finalized: bool | None = None


class ManualAttendanceUpdate(BaseModel):
    student_id: int
    is_present: bool


class AttendanceRecordUpdate(BaseModel):
    is_present: bool
    is_manual_override: bool | None = None


class AttendanceRecordRead(BaseModel):
    student_id: int
    student_name: str
    is_present: bool
    is_manual_override: bool


class SessionRead(BaseModel):
    id: int
    subject_name: str
    session_date: datetime
    is_finalized: bool


class StudentDashboard(BaseModel):
    total_classes: int
    attended_classes: int
    absent_classes: int
    attendance_percentage: float


class StudentPhotoStatus(BaseModel):
    total_photos: int
    registration_ready: bool
    can_reupload: bool


class StudentAttendanceHistoryItem(BaseModel):
    session_id: int
    subject_name: str
    session_date: datetime
    faculty_id: int | None
    faculty_name: str
    faculty_username: str | None
    is_present: bool
    is_manual_override: bool
    is_finalized: bool


class FacultySessionSummary(BaseModel):
    session_id: int
    subject_name: str
    session_date: datetime
    is_finalized: bool
    can_update: bool
    update_deadline: datetime | None


class FaceReviewMarkRequest(BaseModel):
    student_id: int
