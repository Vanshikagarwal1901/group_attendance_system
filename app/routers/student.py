from pathlib import Path
from datetime import datetime
import base64
import mimetypes

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import AttendanceRecord, AttendanceSession, FacultyStudent, StudentPhoto, User, UserRole
from app.schemas import StudentAttendanceHistoryItem, StudentDashboard, StudentPhotoStatus
from app.services.face_service import register_student_photo

router = APIRouter(prefix="/student", tags=["student"])


def _photo_status_for_student(db: Session, student_id: int) -> StudentPhotoStatus:
    total_count = db.query(StudentPhoto).filter(StudentPhoto.student_id == student_id).count()
    return StudentPhotoStatus(
        total_photos=total_count,
        registration_ready=total_count >= 3,
        can_reupload=total_count >= 3,
    )


@router.post("/register-photos")
def register_student_photos(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    if len(files) < 1:
        raise HTTPException(status_code=400, detail="Upload at least one photo")

    saved = 0
    uploaded_files: list[str] = []
    failed: list[str] = []
    for file in files:
        try:
            path = register_student_photo(student.id, file)
        except ValueError as exc:
            failed.append(f"{file.filename}: {exc}")
            continue

        photo = StudentPhoto(student_id=student.id, image_path=path, face_encoding=b"")
        db.add(photo)
        saved += 1
        uploaded_files.append(file.filename or Path(path).name)

    if saved == 0:
        detail = "No valid face photo uploaded"
        if failed:
            detail = "No valid face photo uploaded. " + " | ".join(failed)
        raise HTTPException(status_code=400, detail=detail)

    db.commit()
    photo_status = _photo_status_for_student(db, student.id)

    return {
        "message": "Student registration photos saved",
        "uploaded_now": saved,
        "uploaded_files": uploaded_files,
        "total_photos": photo_status.total_photos,
        "registration_ready": photo_status.registration_ready,
        "failed": failed,
    }


@router.get("/photo-status", response_model=StudentPhotoStatus)
def student_photo_status(
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    return _photo_status_for_student(db, student.id)


@router.get("/photo-preview")
def student_photo_preview(
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    photo = (
        db.query(StudentPhoto)
        .filter(StudentPhoto.student_id == student.id)
        .order_by(StudentPhoto.created_at.desc(), StudentPhoto.id.desc())
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="No registration photo found")

    image_path = Path(photo.image_path)
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Stored photo file not found")

    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return {
        "image_data": f"data:{mime_type};base64,{encoded}",
        "file_name": image_path.name,
    }


@router.delete("/photos")
def reset_student_photos(
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    photos = db.query(StudentPhoto).filter(StudentPhoto.student_id == student.id).all()

    deleted_count = 0
    for photo in photos:
        image_path = Path(photo.image_path)
        image_path.unlink(missing_ok=True)
        db.delete(photo)
        deleted_count += 1

    db.commit()
    return {
        "message": "Student photos cleared. You can upload new photos now.",
        "deleted_count": deleted_count,
    }


@router.get("/dashboard", response_model=StudentDashboard)
def student_dashboard(
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    total_classes = (
        db.query(AttendanceRecord)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .filter(
            AttendanceRecord.student_id == student.id,
            AttendanceSession.is_finalized.is_(True),
        )
        .count()
    )
    attended_classes = (
        db.query(func.count(AttendanceRecord.id))
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .filter(
            AttendanceRecord.student_id == student.id,
            AttendanceRecord.is_present.is_(True),
            AttendanceSession.is_finalized.is_(True),
        )
        .scalar()
    ) or 0
    absent_classes = max(total_classes - attended_classes, 0)

    percentage = round((attended_classes / total_classes) * 100, 2) if total_classes else 0.0

    return StudentDashboard(
        total_classes=total_classes,
        attended_classes=attended_classes,
        absent_classes=absent_classes,
        attendance_percentage=percentage,
    )


@router.get("/my-faculty")
def student_faculty(
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    assignments = db.query(FacultyStudent).filter(FacultyStudent.student_id == student.id).all()
    if not assignments:
        return {"faculty": None}

    faculties = []
    for assignment in assignments:
        faculty = db.query(User).filter(User.id == assignment.faculty_id).first()
        if not faculty:
            continue
        faculties.append(
            {
                "id": faculty.id,
                "name": faculty.full_name,
                "username": faculty.username,
            }
        )

    if not faculties:
        return {"faculty": None}

    return {
        "faculty": faculties[0],
        "faculties": faculties,
    }


@router.get("/attendance-history", response_model=list[StudentAttendanceHistoryItem])
def student_attendance_history(
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    rows = (
        db.query(AttendanceRecord)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .filter(AttendanceRecord.student_id == student.id)
        .order_by(AttendanceSession.session_date.desc(), AttendanceRecord.id.desc())
        .all()
    )

    history: list[StudentAttendanceHistoryItem] = []
    for row in rows:
        session = db.query(AttendanceSession).filter(AttendanceSession.id == row.session_id).first()
        faculty = None
        if session:
            faculty = db.query(User).filter(User.id == session.faculty_id, User.role == UserRole.FACULTY).first()

        history.append(
            StudentAttendanceHistoryItem(
                session_id=row.session_id,
                subject_name=session.subject_name if session else "Unknown",
                session_date=session.session_date if session else datetime.utcnow(),
                faculty_id=faculty.id if faculty else None,
                faculty_name=faculty.full_name if faculty else "Unknown",
                faculty_username=faculty.username if faculty else None,
                is_present=row.is_present,
                is_manual_override=row.is_manual_override,
                is_finalized=session.is_finalized if session else False,
            )
        )

    return history
