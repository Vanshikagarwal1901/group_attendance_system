from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import AttendanceRecord, AttendanceSession, FacultyStudent, StudentPhoto, User, UserRole
from app.schemas import AttendanceRecordRead, AttendanceSessionCreate, ManualAttendanceUpdate
from app.services.face_service import find_present_students

router = APIRouter(prefix="/faculty", tags=["faculty"])


def _get_assigned_students(db: Session, faculty_id: int) -> list[User]:
    rows = db.query(FacultyStudent).filter(FacultyStudent.faculty_id == faculty_id).all()
    student_ids = [row.student_id for row in rows]
    if not student_ids:
        return []
    return db.query(User).filter(User.id.in_(student_ids), User.role == UserRole.STUDENT).all()


def _sync_session_records(db: Session, session_id: int, faculty_id: int) -> int:
    assigned_students = _get_assigned_students(db, faculty_id)
    if not assigned_students:
        return 0

    existing_records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session_id).all()
    existing_student_ids = {record.student_id for record in existing_records}

    created = 0
    for student in assigned_students:
        if student.id in existing_student_ids:
            continue
        db.add(
            AttendanceRecord(
                session_id=session_id,
                student_id=student.id,
                is_present=False,
                is_manual_override=False,
            )
        )
        created += 1

    if created:
        db.commit()
    return created


@router.post("/attendance/start")
def start_attendance_session(
    payload: AttendanceSessionCreate,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    live_session = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.faculty_id == faculty.id,
            AttendanceSession.is_finalized.is_(False),
        )
        .order_by(AttendanceSession.id.desc())
        .first()
    )
    if live_session:
        assigned_students = _get_assigned_students(db, faculty.id)
        _sync_session_records(db, live_session.id, faculty.id)
        return {
            "session_id": live_session.id,
            "students_count": len(assigned_students),
            "already_live": True,
            "message": "Live session already exists. Finalize it before creating a new one.",
        }

    session = AttendanceSession(
        faculty_id=faculty.id,
        subject_name=payload.subject_name,
        session_date=datetime.utcnow(),
        is_finalized=False,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    assigned_students = _get_assigned_students(db, faculty.id)
    for student in assigned_students:
        db.add(AttendanceRecord(session_id=session.id, student_id=student.id, is_present=False, is_manual_override=False))

    db.commit()
    return {"session_id": session.id, "students_count": len(assigned_students), "already_live": False}


@router.get("/attendance/live")
def get_live_attendance_session(
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    live_session = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.faculty_id == faculty.id,
            AttendanceSession.is_finalized.is_(False),
        )
        .order_by(AttendanceSession.id.desc())
        .first()
    )

    if not live_session:
        return {"live": None}

    return {
        "live": {
            "session_id": live_session.id,
            "subject_name": live_session.subject_name,
            "session_date": live_session.session_date.isoformat(),
        }
    }


@router.post("/attendance/{session_id}/scan")
def scan_group_images(
    session_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id,
        AttendanceSession.faculty_id == faculty.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_finalized:
        raise HTTPException(status_code=400, detail="Session already finalized")

    _sync_session_records(db, session.id, faculty.id)

    assigned_students = _get_assigned_students(db, faculty.id)
    if not assigned_students:
        raise HTTPException(status_code=400, detail="No students assigned to faculty")

    student_photo_paths: dict[int, list[str]] = {}
    for student in assigned_students:
        photos = db.query(StudentPhoto).filter(StudentPhoto.student_id == student.id).all()
        if not photos:
            continue

        student_photo_paths[student.id] = [photo.image_path for photo in photos]

    if not student_photo_paths:
        raise HTTPException(status_code=400, detail="No student has registered photos yet")

    present_ids = find_present_students(files, student_photo_paths)

    records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session.id).all()
    for record in records:
        if record.student_id in present_ids:
            record.is_present = True
            record.is_manual_override = False

    db.commit()
    return {"present_marked": len(present_ids)}


@router.patch("/attendance/{session_id}/manual")
def manual_update_attendance(
    session_id: int,
    payload: ManualAttendanceUpdate,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id,
        AttendanceSession.faculty_id == faculty.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.is_finalized:
        raise HTTPException(status_code=400, detail="Session already finalized")

    _sync_session_records(db, session.id, faculty.id)

    assigned_students = _get_assigned_students(db, faculty.id)
    assigned_ids = {student.id for student in assigned_students}
    if payload.student_id not in assigned_ids:
        raise HTTPException(status_code=400, detail="Student is not assigned to this faculty")

    record = db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == session_id,
        AttendanceRecord.student_id == payload.student_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    record.is_present = payload.is_present
    record.is_manual_override = True
    db.commit()

    return {"message": "Attendance updated manually"}


@router.post("/attendance/{session_id}/finalize")
def finalize_attendance(
    session_id: int,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id,
        AttendanceSession.faculty_id == faculty.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_finalized = True
    db.commit()
    return {"message": "Attendance session finalized and saved"}


@router.get("/attendance/{session_id}", response_model=list[AttendanceRecordRead])
def view_attendance_session(
    session_id: int,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id,
        AttendanceSession.faculty_id == faculty.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    _sync_session_records(db, session.id, faculty.id)

    records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session_id).all()
    out: list[AttendanceRecordRead] = []
    for record in records:
        student = db.query(User).filter(User.id == record.student_id).first()
        out.append(
            AttendanceRecordRead(
                student_id=record.student_id,
                student_name=student.full_name,
                is_present=record.is_present,
                is_manual_override=record.is_manual_override,
            )
        )
    return out
