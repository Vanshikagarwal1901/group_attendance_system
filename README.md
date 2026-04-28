# Group Face Attendance System

Group Face Attendance System is a face-recognition-based attendance platform for an admin, faculty, and student workflow.

The project includes a FastAPI backend, a static frontend, SQLite persistence, JWT authentication, and face recognition using RetinaFace and DeepFace-based matching.

## What It Does

1. Admin creates faculty and student accounts.
2. Admin assigns students to faculty.
3. Students register face photos from their device.
4. Faculty starts an attendance session and uploads group photos.
5. The system detects and matches faces automatically.
6. Faculty manually corrects missed records when needed.
7. Faculty finalizes the session.
8. Students view attendance history and totals.

## Features

- Role-based login for admin, faculty, and student.
- Face photo registration for students.
- Auto attendance marking from group photos.
- Manual attendance correction.
- Session review and finalized session history.
- Student dashboard with attendance summary.
- Mobile-friendly frontend layout.
- Restart-safe authentication: tokens become invalid after the backend is restarted.

## Tech Stack

- FastAPI
- SQLAlchemy + SQLite
- JWT authentication
- RetinaFace
- DeepFace
- OpenCV
- Vanilla JavaScript frontend

## Project Structure

```text
app/
  auth.py
  database.py
  main.py
  models.py
  schemas.py
  routers/
    admin.py
    auth.py
    faculty.py
    student.py
  services/
    face_service.py
frontend/
  index.html
  app.js
  styles.css
data/
  group_faces/
  group_images/
  session_face_reviews/
  student_images/
requirements.txt
README.md
```

## Local Setup

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Run the backend

```powershell
uvicorn app.main:app --reload
```

Open the app at:

- Web UI: `http://127.0.0.1:8000/`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Default Admin Account

- Username: `admin`
- Password: `admin123`

The bootstrap admin is created automatically on first startup if no admin exists.

## Authentication Behavior

- Login uses JWT bearer tokens.
- Tokens are stored in browser local storage.
- Tokens are invalidated when the backend restarts, so users must log in again after a server restart.
- If the backend is unavailable or returns `401`, the frontend clears the cached session automatically.

## Mobile-Friendly UI

The frontend is designed to work on phones and desktops:

- The top bar collapses into a stacked layout on smaller screens.
- Admin and role navigation panels stack vertically on mobile.
- Tables stay usable by scrolling horizontally instead of breaking the layout.
- Buttons expand to full width where that improves touch use.

For best mobile demonstrations, open the site in a browser with a narrow viewport or use your phone directly.

## Key Environment Variables

### Backend

- `APP_CORS_ORIGINS`: Comma-separated list of allowed frontend origins. Example: `https://your-frontend.vercel.app,https://your-api.onrender.com`
- `FACE_MODEL_NAME`: Face model name used by DeepFace. Default: `Facenet512`
- `FACE_SIMILARITY_THRESHOLD`: Matching threshold used by recognition logic.
- `FACE_MIN_SIZE_PX`: Minimum detected face size.
- `FACE_MIN_SHARPNESS`: Blur filter threshold.
- `FACULTY_UPDATE_WINDOW_DAYS`: Number of days after finalization when edits remain allowed. Default: `7`

### Frontend

The frontend can target a separate backend by setting `window.__APP_CONFIG__.apiBaseUrl` before `frontend/app.js` loads.

Example:

```html
<script>
  window.__APP_CONFIG__ = {
    apiBaseUrl: "https://your-api.example.com"
  };
</script>
```

If no API base URL is set, the frontend uses same-origin requests.

## API Overview

### Auth

- `POST /auth/login`
- `GET /auth/me`

### Admin

- `GET /admin/dashboard`
- `GET /admin/faculty`
- `POST /admin/faculty`
- `PATCH /admin/users/{user_id}`
- `DELETE /admin/users/{user_id}`
- `GET /admin/students`
- `POST /admin/student`
- `POST /admin/assign`
- `GET /admin/assignments`
- `DELETE /admin/assignments/{assignment_id}`
- `GET /admin/sessions`
- `PATCH /admin/sessions/{session_id}`
- `DELETE /admin/sessions/{session_id}`
- `GET /admin/records`

### Student

- `POST /student/register-photos`
- `GET /student/photo-status`
- `GET /student/photo-preview`
- `DELETE /student/photos`
- `GET /student/dashboard`
- `GET /student/my-faculty`
- `GET /student/attendance-history`

### Faculty

- `POST /faculty/attendance/start`
- `GET /faculty/attendance/live`
- `GET /faculty/attendance/sessions`
- `GET /faculty/students`
- `POST /faculty/attendance/{session_id}/scan`
- `GET /faculty/attendance/{session_id}/faces-review`
- `GET /faculty/attendance/{session_id}/status-summary`
- `GET /faculty/attendance/{session_id}`
- `PATCH /faculty/attendance/{session_id}/manual`
- `POST /faculty/attendance/{session_id}/finalize`

## Notes for Face Recognition

- Student registration photos should be clear and cover multiple angles.
- Group photos should show faces clearly and use decent lighting.
- Missing or unreadable student images are skipped instead of breaking the request.
- Recognition settings can be tuned through the environment variables listed above.

## Troubleshooting

- If login works but the UI immediately sends you back to the login screen, check whether the backend restarted. Existing tokens are intentionally invalidated.
- If the frontend is hosted separately, make sure `APP_CORS_ORIGINS` includes the frontend origin.
- If the frontend cannot reach the API, confirm `window.__APP_CONFIG__.apiBaseUrl` is set correctly.
- If scanning is slow or inaccurate, review the face model and threshold settings.

## Development Notes

- SQLite is used by default, so the app is easy to run locally.
- The default admin account exists only as a bootstrap convenience; change it for production use.
- The current frontend is vanilla JavaScript, which keeps deployment simple across hosting platforms.
