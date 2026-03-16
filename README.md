# Group Face Attendance System (Starter)

This is a FastAPI starter backend for your workflow:

1. Admin creates faculty and students.
2. Admin assigns students to a faculty.
3. Student logs in first time and uploads face photos from different angles.
4. Faculty starts class attendance session and uploads one or more group photos.
5. System auto-marks present students using face recognition.
6. Faculty manually corrects attendance if someone was missed.
7. Faculty finalizes attendance.
8. Student dashboard shows attended/absent counts.

## Tech Stack

- FastAPI
- SQLite (SQLAlchemy)
- JWT auth
- OpenCV (Haar Cascade + LBPH) for matching

## Project Structure

```text
app/
  auth.py
  database.py
  main.py
  models.py
  schemas.py
  routers/
    auth.py
    admin.py
    faculty.py
    student.py
  services/
    face_service.py
data/
requirements.txt
README.md
```

## Setup

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open Swagger UI at: `http://127.0.0.1:8000/docs`

## Default Admin

- Username: `admin`
- Password: `admin123`

Change this in `app/main.py` before production.

## Main APIs

### Auth

- `POST /auth/login`

### Admin

- `POST /admin/faculty`
- `POST /admin/student`
- `POST /admin/assign`
- `GET /admin/dashboard`

### Student

- `POST /student/register-photos` (upload 3+ files)
- `GET /student/dashboard`
- `GET /student/my-faculty`

### Faculty

- `POST /faculty/attendance/start`
- `POST /faculty/attendance/{session_id}/scan` (upload one or more group photos)
- `PATCH /faculty/attendance/{session_id}/manual`
- `GET /faculty/attendance/{session_id}`
- `POST /faculty/attendance/{session_id}/finalize`

## Notes

- For best accuracy, student registration photos should be clear and from multiple angles.
- Group photos should have visible faces with decent lighting.
- Matching confidence threshold is configured in `app/services/face_service.py`.

## Production Improvements

- Add subject/class timetable entities.
- Add per-class section and semester mapping.
- Add image quality checks and anti-spoofing.
- Add frontend dashboards (React or Flutter).
- Move secrets to environment variables.
- Add migrations with Alembic.
