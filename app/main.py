from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.models import User, UserRole
from app.routers import admin, auth, faculty, student

app = FastAPI(title="Group Face Attendance System")


def _migrate_faculty_students_schema() -> None:
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='faculty_students'")
        ).first()
        if not row or not row[0]:
            return

        table_sql = str(row[0]).upper()
        needs_migration = (
            "UQ_STUDENT_SINGLE_FACULTY" in table_sql
            or "UNIQUE (STUDENT_ID)" in table_sql
        )
        if not needs_migration:
            return

        db.execute(text("PRAGMA foreign_keys=OFF"))
        db.execute(
            text(
                """
                CREATE TABLE faculty_students_new (
                    id INTEGER PRIMARY KEY,
                    faculty_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    CONSTRAINT uq_faculty_student_pair UNIQUE (faculty_id, student_id),
                    FOREIGN KEY(faculty_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
        )
        db.execute(
            text(
                """
                INSERT OR IGNORE INTO faculty_students_new (id, faculty_id, student_id)
                SELECT id, faculty_id, student_id FROM faculty_students
                """
            )
        )
        db.execute(text("DROP TABLE faculty_students"))
        db.execute(text("ALTER TABLE faculty_students_new RENAME TO faculty_students"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_faculty_students_faculty_id ON faculty_students (faculty_id)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_faculty_students_student_id ON faculty_students (student_id)"))
        db.execute(text("PRAGMA foreign_keys=ON"))
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_faculty_students_schema()

    db = SessionLocal()
    try:
        # Ensure one bootstrap admin exists.
        admin_user = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if not admin_user:
            db.add(
                User(
                    username="admin",
                    password_hash=hash_password("admin123"),
                    full_name="System Admin",
                    role=UserRole.ADMIN,
                )
            )
            db.commit()
    finally:
        db.close()


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(faculty.router)
app.include_router(student.router)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    return {
        "app": "Group Face Attendance System",
        "status": "running",
        "default_admin": {"username": "admin", "password": "admin123"},
    }
