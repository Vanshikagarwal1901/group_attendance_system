from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, Enum):
    ADMIN = "admin"
    FACULTY = "faculty"
    STUDENT = "student"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), index=True)
    full_name: Mapped[str] = mapped_column(String(100), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    faculty_assignments: Mapped[list["FacultyStudent"]] = relationship(
        "FacultyStudent",
        foreign_keys="FacultyStudent.faculty_id",
        back_populates="faculty",
    )
    student_assignments: Mapped[list["FacultyStudent"]] = relationship(
        "FacultyStudent",
        foreign_keys="FacultyStudent.student_id",
        back_populates="student",
    )
    student_photos: Mapped[list["StudentPhoto"]] = relationship("StudentPhoto", back_populates="student")


class FacultyStudent(Base):
    __tablename__ = "faculty_students"
    __table_args__ = (UniqueConstraint("faculty_id", "student_id", name="uq_faculty_student_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    faculty: Mapped[User] = relationship("User", foreign_keys=[faculty_id], back_populates="faculty_assignments")
    student: Mapped[User] = relationship("User", foreign_keys=[student_id], back_populates="student_assignments")


class StudentPhoto(Base):
    __tablename__ = "student_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    image_path: Mapped[str] = mapped_column(String(255))
    face_encoding: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    student: Mapped[User] = relationship("User", back_populates="student_photos")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_name: Mapped[str] = mapped_column(String(120))
    session_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_finalized: Mapped[bool] = mapped_column(Boolean, default=False)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_session_student"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("attendance_sessions.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_present: Mapped[bool] = mapped_column(Boolean, default=False)
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
