from datetime import datetime, timedelta
from pathlib import Path
import base64
import json
import mimetypes
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import AttendanceRecord, AttendanceSession, FacultyStudent, StudentPhoto, User, UserRole
from app.schemas import (
    AttendanceRecordRead,
    AttendanceSessionCreate,
    FaceReviewMarkRequest,
    FacultySessionSummary,
    ManualAttendanceUpdate,
)
from app.services.face_service import analyze_group_files

router = APIRouter(prefix="/faculty", tags=["faculty"])

FINALIZED_UPDATE_WINDOW_DAYS = int(os.getenv("FACULTY_UPDATE_WINDOW_DAYS", "7"))
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FACE_REVIEW_DIR = BASE_DIR / "data" / "session_face_reviews"
FACE_REVIEW_DIR.mkdir(parents=True, exist_ok=True)


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


def _update_deadline(session: AttendanceSession) -> datetime | None:
    if not session.is_finalized:
        return None
    return session.session_date + timedelta(days=FINALIZED_UPDATE_WINDOW_DAYS)


def _can_update_session(session: AttendanceSession) -> bool:
    if not session.is_finalized:
        return True
    deadline = _update_deadline(session)
    if deadline is None:
        return False
    return datetime.utcnow() <= deadline


def _ensure_session_editable(session: AttendanceSession) -> None:
    if _can_update_session(session):
        return

    deadline = _update_deadline(session)
    if deadline is None:
        raise HTTPException(status_code=400, detail="Session cannot be updated")

    raise HTTPException(
        status_code=400,
        detail=(
            "Update window has expired for this finalized session. "
            f"Edits are allowed only until {deadline.isoformat()}."
        ),
    )


def _face_review_file(session_id: int) -> Path:
    return FACE_REVIEW_DIR / f"session_{session_id}.json"


def _load_face_reviews(session_id: int) -> list[dict]:
    file_path = _face_review_file(session_id)
    if not file_path.exists():
        return []
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return payload


def _save_face_reviews(session_id: int, faces: list[dict]) -> None:
    file_path = _face_review_file(session_id)
    file_path.write_text(json.dumps(faces, ensure_ascii=True), encoding="utf-8")


def _face_image_data(path_str: str | None) -> str | None:
    if not path_str:
        return None
    path = Path(path_str)
    if not path.exists():
        return None
    mime_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _session_records_with_students(db: Session, session_id: int) -> list[tuple[AttendanceRecord, User | None]]:
    rows = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session_id).all()
    out: list[tuple[AttendanceRecord, User | None]] = []
    for row in rows:
        student = db.query(User).filter(User.id == row.student_id, User.role == UserRole.STUDENT).first()
        out.append((row, student))
    return out


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


@router.get("/attendance/sessions", response_model=list[FacultySessionSummary])
def list_faculty_attendance_sessions(
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    rows = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.faculty_id == faculty.id)
        .order_by(AttendanceSession.session_date.desc(), AttendanceSession.id.desc())
        .all()
    )

    out: list[FacultySessionSummary] = []
    for row in rows:
        out.append(
            FacultySessionSummary(
                session_id=row.id,
                subject_name=row.subject_name,
                session_date=row.session_date,
                is_finalized=row.is_finalized,
                can_update=_can_update_session(row),
                update_deadline=_update_deadline(row),
            )
        )
    return out


@router.get("/students")
def list_assigned_students(
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    students = _get_assigned_students(db, faculty.id)
    return [
        {
            "id": student.id,
            "full_name": student.full_name,
            "username": student.username,
        }
        for student in sorted(students, key=lambda s: (s.full_name.lower(), s.id))
    ]


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
    _ensure_session_editable(session)

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

    analysis = analyze_group_files(files, student_photo_paths)
    present_ids: set[int] = analysis["present_ids"]  # type: ignore[assignment]
    detected_faces: list[dict] = analysis["detected_faces"]  # type: ignore[assignment]

    student_lookup = {student.id: student for student in assigned_students}
    for face in detected_faces:
        matched_student_id = face.get("matched_student_id")
        student = student_lookup.get(matched_student_id) if isinstance(matched_student_id, int) else None
        face["matched_student_name"] = student.full_name if student else None
        face["matched_student_username"] = student.username if student else None

    existing_faces = _load_face_reviews(session.id)
    existing_faces.extend(detected_faces)
    _save_face_reviews(session.id, existing_faces)

    records = db.query(AttendanceRecord).filter(AttendanceRecord.session_id == session.id).all()
    for record in records:
        if record.student_id in present_ids:
            record.is_present = True
            record.is_manual_override = False

    db.commit()
    recognized_count = sum(1 for face in detected_faces if face.get("recognized"))
    return {
        "present_marked": len(present_ids),
        "detected_faces": len(detected_faces),
        "recognized_faces": recognized_count,
        "unrecognized_faces": max(len(detected_faces) - recognized_count, 0),
    }


@router.get("/attendance/{session_id}/faces-review")
def get_session_faces_review(
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

    faces = _load_face_reviews(session_id)

    recognized_faces = []
    unrecognized_faces = []
    for face in faces:
        face_payload = {
            "face_id": face.get("face_id"),
            "group_image_name": face.get("group_image_name"),
            "recognized": bool(face.get("recognized")),
            "matched_student_id": face.get("matched_student_id"),
            "matched_student_name": face.get("matched_student_name"),
            "matched_student_username": face.get("matched_student_username"),
            "best_similarity": face.get("best_similarity"),
            "image_data": _face_image_data(face.get("crop_path")),
        }
        if face_payload["recognized"]:
            recognized_faces.append(face_payload)
        else:
            unrecognized_faces.append(face_payload)

    return {
        "session_id": session.id,
        "subject_name": session.subject_name,
        "total_detected": len(faces),
        "recognized_count": len(recognized_faces),
        "unrecognized_count": len(unrecognized_faces),
        "recognized_faces": recognized_faces,
        "unrecognized_faces": unrecognized_faces,
    }


@router.get("/attendance/{session_id}/status-summary")
def get_session_status_summary(
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

    marked_students: list[dict[str, object]] = []
    unmarked_students: list[dict[str, object]] = []
    for record, student in _session_records_with_students(db, session.id):
        if not student:
            continue
        payload = {
            "student_id": student.id,
            "student_name": student.full_name,
            "student_username": student.username,
            "is_manual_override": record.is_manual_override,
        }
        if record.is_present:
            marked_students.append(payload)
        else:
            unmarked_students.append(payload)

    marked_students.sort(key=lambda s: str(s["student_name"]).lower())
    unmarked_students.sort(key=lambda s: str(s["student_name"]).lower())

    return {
        "session_id": session.id,
        "subject_name": session.subject_name,
        "marked_students": marked_students,
        "unmarked_students": unmarked_students,
        "marked_count": len(marked_students),
        "unmarked_count": len(unmarked_students),
    }


@router.patch("/attendance/{session_id}/faces-review/{face_id}/mark")
def mark_unrecognized_face(
    session_id: int,
    face_id: str,
    payload: FaceReviewMarkRequest,
    db: Session = Depends(get_db),
    faculty: User = Depends(require_role(UserRole.FACULTY)),
):
    session = db.query(AttendanceSession).filter(
        AttendanceSession.id == session_id,
        AttendanceSession.faculty_id == faculty.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    _ensure_session_editable(session)
    _sync_session_records(db, session.id, faculty.id)

    assigned_students = _get_assigned_students(db, faculty.id)
    student_lookup = {student.id: student for student in assigned_students}
    student = student_lookup.get(payload.student_id)
    if not student:
        raise HTTPException(status_code=400, detail="Student is not assigned to this faculty")

    record = db.query(AttendanceRecord).filter(
        AttendanceRecord.session_id == session.id,
        AttendanceRecord.student_id == student.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    record.is_present = True
    record.is_manual_override = True
    db.commit()

    faces = _load_face_reviews(session.id)
    updated = False
    for face in faces:
        if str(face.get("face_id")) != face_id:
            continue
        face["recognized"] = True
        face["matched_student_id"] = student.id
        face["matched_student_name"] = student.full_name
        face["matched_student_username"] = student.username
        updated = True
        break

    if updated:
        _save_face_reviews(session.id, faces)

    return {
        "message": "Unrecognized face mapped to student and marked present.",
        "face_updated": updated,
    }


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
    _ensure_session_editable(session)

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
