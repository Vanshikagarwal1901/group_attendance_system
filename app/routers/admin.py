from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import hash_password, require_role
from app.database import get_db
from app.models import AttendanceRecord, AttendanceSession, FacultyStudent, User, UserRole
from app.schemas import (
    AssignmentCreate,
    AttendanceRecordUpdate,
    AttendanceSessionUpdate,
    UserCreate,
    UserRead,
    UserUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/faculty", response_model=UserRead)
def create_faculty(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    faculty = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.FACULTY,
    )
    db.add(faculty)
    db.commit()
    db.refresh(faculty)
    return faculty


@router.post("/student", response_model=UserRead)
def create_student(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    student = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.STUDENT,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_role(UserRole.ADMIN)),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.username and payload.username != target.username:
        exists = db.query(User).filter(User.username == payload.username, User.id != user_id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Username already exists")
        target.username = payload.username

    if payload.full_name is not None:
        target.full_name = payload.full_name

    if payload.password:
        target.password_hash = hash_password(payload.password)

    db.commit()
    return {"message": "User updated successfully"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_role(UserRole.ADMIN)),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == UserRole.ADMIN and target.id == admin_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own admin account")

    db.delete(target)
    db.commit()
    return {"message": "User deleted successfully"}


@router.get("/faculty", response_model=list[UserRead])
def list_faculty(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    return db.query(User).filter(User.role == UserRole.FACULTY).order_by(User.id.asc()).all()


@router.get("/students", response_model=list[UserRead])
def list_students(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    return db.query(User).filter(User.role == UserRole.STUDENT).order_by(User.id.asc()).all()


@router.post("/assign")
def assign_student_to_faculty(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    faculty = db.query(User).filter(User.id == payload.faculty_id, User.role == UserRole.FACULTY).first()
    student = db.query(User).filter(User.id == payload.student_id, User.role == UserRole.STUDENT).first()

    if not faculty or not student:
        raise HTTPException(status_code=404, detail="Faculty or student not found")

    existing = (
        db.query(FacultyStudent)
        .filter(
            FacultyStudent.faculty_id == faculty.id,
            FacultyStudent.student_id == student.id,
        )
        .first()
    )
    if existing:
        return {"message": "Student is already assigned to this faculty"}

    assignment = FacultyStudent(faculty_id=faculty.id, student_id=student.id)
    db.add(assignment)
    db.commit()

    return {"message": "Student assigned to faculty successfully"}


@router.get("/dashboard")
def admin_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    faculty_count = db.query(User).filter(User.role == UserRole.FACULTY).count()
    student_count = db.query(User).filter(User.role == UserRole.STUDENT).count()
    assignment_count = db.query(FacultyStudent).count()

    return {
        "faculty_count": faculty_count,
        "student_count": student_count,
        "assignment_count": assignment_count,
    }


@router.get("/assignments")
def list_assignments(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    rows = db.query(FacultyStudent).order_by(FacultyStudent.id.desc()).all()
    data = []
    for row in rows:
        faculty = db.query(User).filter(User.id == row.faculty_id).first()
        student = db.query(User).filter(User.id == row.student_id).first()
        data.append(
            {
                "assignment_id": row.id,
                "faculty_id": row.faculty_id,
                "faculty_name": faculty.full_name if faculty else "Unknown",
                "student_id": row.student_id,
                "student_name": student.full_name if student else "Unknown",
            }
        )
    return data


@router.delete("/assignments/{assignment_id}")
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    assignment = db.query(FacultyStudent).filter(FacultyStudent.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(assignment)
    db.commit()
    return {"message": "Assignment deleted successfully"}


@router.get("/sessions")
def list_attendance_sessions(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    rows = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.is_finalized.is_(True))
        .order_by(AttendanceSession.id.desc())
        .all()
    )
    data = []
    for row in rows:
        faculty = db.query(User).filter(User.id == row.faculty_id).first()
        data.append(
            {
                "session_id": row.id,
                "faculty_id": row.faculty_id,
                "faculty_name": faculty.full_name if faculty else "Unknown",
                "subject_name": row.subject_name,
                "session_date": row.session_date.isoformat(),
                "is_finalized": row.is_finalized,
            }
        )
    return data


@router.patch("/sessions/{session_id}")
def update_attendance_session(
    session_id: int,
    payload: AttendanceSessionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if payload.subject_name is not None:
        session.subject_name = payload.subject_name
    if payload.is_finalized is not None:
        session.is_finalized = payload.is_finalized

    db.commit()
    return {"message": "Session updated successfully"}


@router.delete("/sessions/{session_id}")
def delete_attendance_session(
    session_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    session = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(session)
    db.commit()
    return {"message": "Session deleted successfully"}


@router.get("/records")
def list_attendance_records(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    rows = (
        db.query(AttendanceRecord)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .filter(AttendanceSession.is_finalized.is_(True))
        .order_by(AttendanceRecord.id.desc())
        .limit(500)
        .all()
    )
    data = []
    for row in rows:
        student = db.query(User).filter(User.id == row.student_id).first()
        session = db.query(AttendanceSession).filter(AttendanceSession.id == row.session_id).first()
        data.append(
            {
                "record_id": row.id,
                "session_id": row.session_id,
                "subject_name": session.subject_name if session else "Unknown",
                "student_id": row.student_id,
                "student_name": student.full_name if student else "Unknown",
                "is_present": row.is_present,
                "is_manual_override": row.is_manual_override,
            }
        )
    return data


@router.patch("/records/{record_id}")
def update_attendance_record(
    record_id: int,
    payload: AttendanceRecordUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    record.is_present = payload.is_present
    record.is_manual_override = payload.is_manual_override if payload.is_manual_override is not None else True
    db.commit()
    return {"message": "Attendance record updated successfully"}


@router.delete("/records/{record_id}")
def delete_attendance_record(
    record_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    db.delete(record)
    db.commit()
    return {"message": "Attendance record deleted successfully"}


@router.get("/students/{student_id}/records")
def get_student_records(
    student_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    student = db.query(User).filter(User.id == student_id, User.role == UserRole.STUDENT).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    assignments = db.query(FacultyStudent).filter(FacultyStudent.student_id == student_id).all()
    faculty_data = []
    for assignment in assignments:
        faculty = db.query(User).filter(User.id == assignment.faculty_id, User.role == UserRole.FACULTY).first()
        if faculty:
            faculty_data.append(
                {
                    "id": faculty.id,
                    "name": faculty.full_name,
                    "username": faculty.username,
                }
            )

    rows = (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.student_id == student_id)
        .order_by(AttendanceRecord.id.desc())
        .all()
    )

    record_data = []
    present_count = 0
    absent_count = 0
    manual_count = 0

    for row in rows:
        session = db.query(AttendanceSession).filter(AttendanceSession.id == row.session_id).first()
        faculty_name = "Unknown"
        if session:
            faculty = db.query(User).filter(User.id == session.faculty_id).first()
            faculty_name = faculty.full_name if faculty else "Unknown"

        if row.is_present:
            present_count += 1
        else:
            absent_count += 1
        if row.is_manual_override:
            manual_count += 1

        record_data.append(
            {
                "record_id": row.id,
                "session_id": row.session_id,
                "subject_name": session.subject_name if session else "Unknown",
                "faculty_name": faculty_name,
                "session_date": session.session_date.isoformat() if session else None,
                "is_finalized": session.is_finalized if session else False,
                "is_present": row.is_present,
                "is_manual_override": row.is_manual_override,
            }
        )

    total = len(record_data)
    percentage = round((present_count / total) * 100, 2) if total else 0.0

    return {
        "student": {
            "id": student.id,
            "name": student.full_name,
            "username": student.username,
        },
        "faculties": faculty_data,
        "summary": {
            "total_classes": total,
            "present_classes": present_count,
            "absent_classes": absent_count,
            "manual_updates": manual_count,
            "attendance_percentage": percentage,
        },
        "records": record_data,
    }
