from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import AttendanceRecord, AttendanceSession, FacultyStudent, StudentPhoto, User, UserRole
from app.schemas import StudentDashboard
from app.services.face_service import register_student_photo

router = APIRouter(prefix="/student", tags=["student"])


@router.post("/register-photos")
def register_student_photos(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    student: User = Depends(require_role(UserRole.STUDENT)),
):
    if len(files) < 1:
        raise HTTPException(status_code=400, detail="Upload at least one photo")

    saved = 0
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

    if saved == 0:
        raise HTTPException(status_code=400, detail="No valid face photo uploaded")

    db.commit()
    total_count = db.query(StudentPhoto).filter(StudentPhoto.student_id == student.id).count()

    return {
        "message": "Student registration photos saved",
        "uploaded_now": saved,
        "total_photos": total_count,
        "registration_ready": total_count >= 3,
        "failed": failed,
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
