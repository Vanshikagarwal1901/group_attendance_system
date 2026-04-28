const state = {
  token: localStorage.getItem("token") || "",
  role: localStorage.getItem("role") || "",
  username: localStorage.getItem("username") || "",
  sessionId: null,
  authHeartbeatTimer: null,
  isScanning: false,
  studentRegistrationReady: false,
  facultySessions: [],
  facultyFaceFilter: "all",
  facultyStatusSummary: null,
  toastTimer: null,
  toastHideTimer: null,
};

const appConfig = window.__APP_CONFIG__ || {};
const API_BASE_URL = (appConfig.apiBaseUrl || "").replace(/\/$/, "");

const $ = (id) => document.getElementById(id);

function buildApiUrl(path) {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

function showMessage(text, isError = false, durationMs = null) {
  const box = $("messageBox");
  box.textContent = text;
  box.classList.toggle("error", isError);
  box.classList.remove("hide");
  box.hidden = false;
  requestAnimationFrame(() => box.classList.add("show"));

  if (state.toastTimer) {
    clearTimeout(state.toastTimer);
  }
  if (state.toastHideTimer) {
    clearTimeout(state.toastHideTimer);
  }

  const computedDuration = Math.min(14000, Math.max(4200, String(text).length * 42));
  const timeout = durationMs ?? computedDuration;

  state.toastTimer = setTimeout(() => {
    box.classList.remove("show");
    box.classList.add("hide");
    state.toastHideTimer = setTimeout(() => {
      box.hidden = true;
      box.classList.remove("hide");
    }, 220);
  }, timeout);
}

function revealElement(element, scrollIntoView = false) {
  if (!element) {
    return;
  }

  element.classList.remove("reveal-in");
  void element.offsetWidth;
  element.classList.add("reveal-in");

  if (scrollIntoView) {
    element.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  let response;

  try {
    response = await fetch(buildApiUrl(path), {
      mode: API_BASE_URL ? "cors" : "same-origin",
      ...options,
      headers,
    });
  } catch (error) {
    if (state.token) {
      clearSession();
      showRoleView();
    }
    throw new Error("Backend is unavailable. Please login again.");
  }

  if (!response.ok) {
    let msg = `Request failed: ${response.status}`;
    try {
      const data = await response.json();
      msg = data.detail || msg;
    } catch (error) {
      // Keep default message when body is not JSON.
    }
    if (response.status === 401 && state.token) {
      clearSession();
      showRoleView();
    }
    throw new Error(msg);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return null;
}

function setSession(token, role, username) {
  state.token = token;
  state.role = role;
  state.username = username;
  localStorage.setItem("token", token);
  localStorage.setItem("role", role);
  localStorage.setItem("username", username);
  startAuthHeartbeat();
}

function stopAuthHeartbeat() {
  if (state.authHeartbeatTimer) {
    clearInterval(state.authHeartbeatTimer);
    state.authHeartbeatTimer = null;
  }
}

function clearSession() {
  stopAuthHeartbeat();
  state.token = "";
  state.role = "";
  state.username = "";
  state.sessionId = null;
  state.studentRegistrationReady = false;
  state.facultySessions = [];
  state.facultyFaceFilter = "all";
  state.facultyStatusSummary = null;
  localStorage.removeItem("token");
  localStorage.removeItem("role");
  localStorage.removeItem("username");
}

function startAuthHeartbeat() {
  stopAuthHeartbeat();

  if (!state.token) {
    return;
  }

  state.authHeartbeatTimer = window.setInterval(async () => {
    if (!state.token) {
      stopAuthHeartbeat();
      return;
    }

    try {
      await api("/auth/me");
    } catch (error) {
      showMessage(error.message, true);
    }
  }, 30000);
}

function showRoleView() {
  $("loginCard").hidden = !!state.token;
  $("adminView").hidden = state.role !== "admin";
  $("facultyView").hidden = state.role !== "faculty";
  $("studentView").hidden = state.role !== "student";
  $("logoutBtn").hidden = !state.token;
  $("whoami").textContent = state.token ? `${state.username} (${state.role})` : "Not logged in";

  if (!state.token) {
    revealElement($("loginCard"));
    return;
  }

  if (state.role === "admin") revealElement($("adminView"));
  if (state.role === "faculty") revealElement($("facultyView"));
  if (state.role === "student") revealElement($("studentView"));
}

function clampPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return 0;
  }
  return Math.max(0, Math.min(100, n));
}

function statCard(key, value, options = {}) {
  const parsedNumber = typeof value === "number" ? value : Number.parseFloat(String(value).replace(/%/g, ""));
  const inferredPercent =
    typeof value === "string" && value.includes("%") && Number.isFinite(parsedNumber)
      ? parsedNumber
      : options.percent;
  const chartPercent = clampPercent(inferredPercent ?? 0);

  return `
    <div class="stat">
      <div class="k">${key}</div>
      <div class="v">${value}</div>
      <div class="stat-viz" aria-hidden="true">
        <div class="stat-ring" style="--value:${chartPercent};"></div>
        <div class="stat-bar"><span style="width:${chartPercent}%;"></span></div>
      </div>
    </div>`;
}

function renderStatsSkeleton(containerId, count = 4) {
  const container = $(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = Array.from({ length: count })
    .map(
      () => `
      <div class="stat stat-skeleton">
        <div class="skeleton skeleton-line short"></div>
        <div class="skeleton skeleton-line"></div>
        <div class="skeleton skeleton-line"></div>
      </div>`
    )
    .join("");
}

function renderPanelSkeleton(containerId, lines = 4) {
  const container = $(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = `
    <div class="panel skeleton-panel">
      ${Array.from({ length: lines })
        .map((_, idx) => `<div class="skeleton skeleton-line ${idx % 2 === 0 ? "" : "short"}"></div>`)
        .join("")}
    </div>`;
}

function renderTableSkeleton(containerId, rows = 5, cols = 4) {
  const container = $(containerId);
  if (!container) {
    return;
  }

  const rowHtml = Array.from({ length: rows })
    .map(
      () =>
        `<div class="skeleton-row">${Array.from({ length: cols })
          .map(() => '<div class="skeleton skeleton-line"></div>')
          .join("")}</div>`
    )
    .join("");

  container.innerHTML = `<div class="table-skeleton">${rowHtml}</div>`;
}

function actionButton(label, action, id, kind = "") {
  const classes = ["btn-mini", kind].filter(Boolean).join(" ");
  return `<button type="button" class="${classes}" data-action="${action}" data-id="${id}">${label}</button>`;
}

function formatCellValue(value) {
  if (typeof value === "boolean") {
    return value
      ? '<span class="badge badge-success">Yes</span>'
      : '<span class="badge badge-muted">No</span>';
  }

  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) {
      return `<span class="date-pill">${date.toLocaleString()}</span>`;
    }
  }

  return value ?? "-";
}

function renderSimpleTable(containerId, columns, items) {
  const container = $(containerId);
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No data found.</div>';
    return;
  }

  const head = columns.map((col) => `<th>${col.label}</th>`).join("");
  const rows = items
    .map((item) => {
      const cells = columns.map((col) => `<td>${formatCellValue(item[col.key])}</td>`).join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");

  container.innerHTML = `
    <div class="table-wrap">
      <table class="table">
        <thead><tr>${head}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function activateAdminSection(sectionId) {
  const panels = document.querySelectorAll("#adminView .admin-panel");
  let activePanel = null;
  panels.forEach((panel) => {
    panel.hidden = panel.id !== sectionId;
    if (!panel.hidden) {
      activePanel = panel;
    }
  });

  const navButtons = document.querySelectorAll("#adminView .admin-nav-btn");
  navButtons.forEach((button) => {
    const isActive = button.dataset.adminSection === sectionId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-current", isActive ? "page" : "false");
  });

  revealElement(activePanel);
}

function activateFacultySection(sectionId) {
  const panels = document.querySelectorAll("#facultyView .role-panel");
  let activePanel = null;
  panels.forEach((panel) => {
    panel.hidden = panel.id !== sectionId;
    if (!panel.hidden) {
      activePanel = panel;
    }
  });

  const navButtons = document.querySelectorAll("#facultyView .role-nav-btn");
  navButtons.forEach((button) => {
    const isActive = button.dataset.facultySection === sectionId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-current", isActive ? "page" : "false");
  });

  revealElement(activePanel);
}

function activateStudentSection(sectionId) {
  const panels = document.querySelectorAll("#studentView .role-panel");
  let activePanel = null;
  panels.forEach((panel) => {
    panel.hidden = panel.id !== sectionId;
    if (!panel.hidden) {
      activePanel = panel;
    }
  });

  const navButtons = document.querySelectorAll("#studentView .role-nav-btn");
  navButtons.forEach((button) => {
    const isActive = button.dataset.studentSection === sectionId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-current", isActive ? "page" : "false");
  });

  revealElement(activePanel);
}

function renderStudentLookup(data) {
  const target = $("adminStudentLookup");

  const facultyText = data.faculties.length
    ? data.faculties.map((f) => `${f.name} (${f.username})`).join(", ")
    : "No faculty assigned";

  target.innerHTML = `
    <div class="panel">
      <strong>${data.student.name}</strong><br />
      Username: ${data.student.username}<br />
      Student ID: ${data.student.id}<br />
      Faculty: ${facultyText}
    </div>
    <div class="stats" style="margin-top:12px;">
      ${statCard("Total Classes", data.summary.total_classes, { percent: 100 })}
      ${statCard("Present", data.summary.present_classes, {
        percent: data.summary.total_classes
          ? (data.summary.present_classes / data.summary.total_classes) * 100
          : 0,
      })}
      ${statCard("Absent", data.summary.absent_classes, {
        percent: data.summary.total_classes
          ? (data.summary.absent_classes / data.summary.total_classes) * 100
          : 0,
      })}
      ${statCard("Attendance", `${data.summary.attendance_percentage}%`, {
        percent: data.summary.attendance_percentage,
      })}
    </div>
    <h4>Student Attendance Records</h4>
    <div id="adminStudentRecordTable"></div>
  `;

  renderSimpleTable(
    "adminStudentRecordTable",
    [
      { key: "record_id", label: "Record ID" },
      { key: "session_id", label: "Session ID" },
      { key: "subject_name", label: "Subject" },
      { key: "faculty_name", label: "Faculty" },
      { key: "session_date", label: "Date" },
      { key: "is_finalized", label: "Finalized" },
      { key: "is_present", label: "Present" },
      { key: "is_manual_override", label: "Manual" },
    ],
    data.records
  );
}

function renderStudentPhotoStatus(photoStatus) {
  const summary = photoStatus.registration_ready
    ? "Registration complete. You can reupload photos any time."
    : "Registration pending. Upload at least 3 photos.";

  $("studentPhotoStatus").innerHTML = `
    <strong>Photo Registration Status</strong><br />
    Total uploaded photos: ${photoStatus.total_photos}<br />
    Ready for attendance: ${photoStatus.registration_ready ? "Yes" : "No"}<br />
    ${summary}`;

  $("reuploadPhotosBtn").hidden = !photoStatus.can_reupload;
}

function renderStudentAttendanceHistory(items) {
  renderSimpleTable(
    "studentAttendanceHistory",
    [
      { key: "session_id", label: "Session ID" },
      { key: "subject_name", label: "Subject" },
      { key: "session_date", label: "Date & Time" },
      { key: "faculty_name", label: "Faculty" },
      { key: "faculty_username", label: "Faculty Username" },
      { key: "is_present", label: "Present" },
      { key: "is_manual_override", label: "Manual" },
      { key: "is_finalized", label: "Finalized" },
    ],
    items
  );
}

async function refreshStudentPhotoPreview() {
  try {
    const preview = await api("/student/photo-preview");
    if (!preview || !preview.image_data) {
      $("studentPhotoPreviewWrap").hidden = true;
      $("studentPhotoPreviewHint").textContent = "No registration photo available yet.";
      return;
    }

    $("studentPhotoPreviewImg").src = preview.image_data;
    $("studentPhotoPreviewWrap").hidden = false;
    $("studentPhotoPreviewHint").textContent = `Showing latest uploaded photo: ${preview.file_name}`;
  } catch (_error) {
    $("studentPhotoPreviewWrap").hidden = true;
    $("studentPhotoPreviewHint").textContent = "No registration photo available yet.";
  }
}

function renderFaceCards(containerId, faces, recognized) {
  const container = $(containerId);
  if (!faces.length) {
    container.innerHTML = '<div class="empty-state">No faces in this section.</div>';
    return;
  }

  container.innerHTML = `
    <div class="face-review-grid">
      ${faces
        .map((face) => {
          const title = recognized
            ? `${face.matched_student_name || "Unknown"} (${face.matched_student_id || "-"})`
            : "Not recognized";
          const sub = recognized
            ? `Username: ${face.matched_student_username || "-"}`
            : "No match found in registered student photos";
          const safeFaceId = String(face.face_id || "").replace(/[^a-zA-Z0-9_-]/g, "_");
          const unmarked = state.facultyStatusSummary?.unmarked_students || [];
          const unmarkedOptions = unmarked.length
            ? unmarked
                .map(
                  (student) =>
                    `<option value="${student.student_id}">${student.student_id} - ${student.student_name} (${student.student_username})</option>`
                )
                .join("")
            : '<option value="">No unmarked students</option>';
          const manualMarkBlock = !recognized
            ? `
              <label>
                Mark This Face As
                <select id="faceMarkStudent_${safeFaceId}" ${unmarked.length ? "" : "disabled"}>${unmarkedOptions}</select>
              </label>
              <button type="button" class="btn-mini" data-action="faculty-mark-face" data-face-id="${face.face_id}" data-select-id="faceMarkStudent_${safeFaceId}" ${unmarked.length ? "" : "disabled"}>Mark Present</button>`
            : "";
          return `
            <div class="face-card">
              <img src="${face.image_data || ""}" alt="Detected face" />
              <p><strong>${title}</strong></p>
              <p>${sub}</p>
              <p>Source: ${face.group_image_name || "-"}</p>
              <p>Similarity: ${face.best_similarity ?? "-"}</p>
              ${manualMarkBlock}
            </div>`;
        })
        .join("")}
    </div>`;
}

function renderFacultyStatusSummary(summary) {
  if (!summary) {
    $("facultyStatusSummary").innerHTML = "No session selected.";
    $("facultyMarkedStudents").innerHTML = '<div class="empty-state">No data found.</div>';
    $("facultyUnmarkedStudents").innerHTML = '<div class="empty-state">No data found.</div>';
    return;
  }

  state.facultyStatusSummary = summary;
  $("facultyStatusSummary").innerHTML = `
    <strong>Attendance Coverage</strong><br />
    Session ID: ${summary.session_id}<br />
    Subject: ${summary.subject_name}<br />
    Marked students: ${summary.marked_count}<br />
    Unmarked students: ${summary.unmarked_count}`;

  renderSimpleTable(
    "facultyMarkedStudents",
    [
      { key: "student_id", label: "Student ID" },
      { key: "student_name", label: "Name" },
      { key: "student_username", label: "Username" },
      { key: "is_manual_override", label: "Manual" },
    ],
    summary.marked_students || []
  );

  renderSimpleTable(
    "facultyUnmarkedStudents",
    [
      { key: "student_id", label: "Student ID" },
      { key: "student_name", label: "Name" },
      { key: "student_username", label: "Username" },
      { key: "is_manual_override", label: "Manual" },
    ],
    summary.unmarked_students || []
  );
}

async function refreshFacultyStatusSummary() {
  if (!state.sessionId) {
    state.facultyStatusSummary = null;
    renderFacultyStatusSummary(null);
    return;
  }

  try {
    renderPanelSkeleton("facultyStatusSummary", 4);
    renderTableSkeleton("facultyMarkedStudents", 4, 4);
    renderTableSkeleton("facultyUnmarkedStudents", 4, 4);

    const summary = await api(`/faculty/attendance/${state.sessionId}/status-summary`);
    renderFacultyStatusSummary(summary);
  } catch (_error) {
    state.facultyStatusSummary = null;
    renderFacultyStatusSummary(null);
  }
}

function applyFacultyFaceFilter() {
  const recognizedBlock = $("facultyRecognizedBlock");
  const unrecognizedBlock = $("facultyUnrecognizedBlock");

  const showRecognized = state.facultyFaceFilter === "all" || state.facultyFaceFilter === "recognized";
  const showUnrecognized = state.facultyFaceFilter === "all" || state.facultyFaceFilter === "unrecognized";

  recognizedBlock.hidden = !showRecognized;
  unrecognizedBlock.hidden = !showUnrecognized;

  $("facesFilterAllBtn").classList.toggle("active", state.facultyFaceFilter === "all");
  $("facesFilterRecognizedBtn").classList.toggle("active", state.facultyFaceFilter === "recognized");
  $("facesFilterUnrecognizedBtn").classList.toggle("active", state.facultyFaceFilter === "unrecognized");
}

function setFacultyFaceFilter(filterKey) {
  state.facultyFaceFilter = filterKey;
  applyFacultyFaceFilter();
}

async function refreshFacultyFacesReview() {
  if (!state.sessionId) {
    $("facultyFacesSummary").innerHTML = "No session selected.";
    $("facultyRecognizedFaces").innerHTML = '<div class="empty-state">No data found.</div>';
    $("facultyUnrecognizedFaces").innerHTML = '<div class="empty-state">No data found.</div>';
    return;
  }

  try {
    renderPanelSkeleton("facultyFacesSummary", 4);
    renderTableSkeleton("facultyRecognizedFaces", 3, 2);
    renderTableSkeleton("facultyUnrecognizedFaces", 3, 2);

    const data = await api(`/faculty/attendance/${state.sessionId}/faces-review`);
    $("facultyFacesSummary").innerHTML = `
      <strong>Extraction Summary</strong><br />
      Session ID: ${data.session_id}<br />
      Subject: ${data.subject_name}<br />
      Total detected faces: ${data.total_detected}<br />
      Recognized faces: ${data.recognized_count}<br />
      Unrecognized faces: ${data.unrecognized_count}`;

    renderFaceCards("facultyRecognizedFaces", data.recognized_faces || [], true);
    renderFaceCards("facultyUnrecognizedFaces", data.unrecognized_faces || [], false);
  } catch (_error) {
    $("facultyFacesSummary").innerHTML = "No extracted face data available for this session yet.";
    $("facultyRecognizedFaces").innerHTML = '<div class="empty-state">No recognized faces yet.</div>';
    $("facultyUnrecognizedFaces").innerHTML = '<div class="empty-state">No unrecognized faces yet.</div>';
  }

  applyFacultyFaceFilter();
}

async function login(username, password) {
  const tokenData = await api("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  const payload = JSON.parse(atob(tokenData.access_token.split(".")[1]));
  setSession(tokenData.access_token, payload.role, payload.sub);
  showRoleView();
  await refreshRoleData();
}

async function refreshAdminData() {
  renderStatsSkeleton("adminStats", 4);
  renderTableSkeleton("adminFaculty", 6, 4);
  renderTableSkeleton("adminStudents", 6, 4);
  renderTableSkeleton("adminAssignments", 6, 5);
  renderTableSkeleton("adminSessions", 6, 5);
  renderTableSkeleton("adminRecords", 8, 6);

  const [dash, faculty, students, assignments, sessions, records] = await Promise.all([
    api("/admin/dashboard"),
    api("/admin/faculty"),
    api("/admin/students"),
    api("/admin/assignments"),
    api("/admin/sessions"),
    api("/admin/records"),
  ]);

  const totalUsers = dash.faculty_count + dash.student_count + 1;
  const assignmentCoverage = dash.student_count ? (dash.assignment_count / dash.student_count) * 100 : 0;

  $("adminStats").innerHTML =
    statCard("Faculty", dash.faculty_count, { percent: totalUsers ? (dash.faculty_count / totalUsers) * 100 : 0 }) +
    statCard("Students", dash.student_count, { percent: totalUsers ? (dash.student_count / totalUsers) * 100 : 0 }) +
    statCard("Assignments", dash.assignment_count, { percent: assignmentCoverage }) +
    statCard("Total Users", totalUsers, { percent: 100 });

  const facultySelect = $("facultySelect");
  const studentSelect = $("studentSelect");

  facultySelect.innerHTML = faculty
    .map((f) => `<option value="${f.id}">${f.full_name} (${f.username})</option>`)
    .join("");

  studentSelect.innerHTML = students
    .map((s) => `<option value="${s.id}">${s.full_name} (${s.username})</option>`)
    .join("");

  $("adminFaculty").innerHTML = `
    <table class="table">
      <thead><tr><th>ID</th><th>Name</th><th>Username</th><th>Actions</th></tr></thead>
      <tbody>
        ${faculty
          .map(
            (f) => `<tr>
              <td>${f.id}</td>
              <td>${f.full_name}</td>
              <td>${f.username}</td>
              <td>${actionButton("Update", "admin-update-user", f.id)} ${actionButton("Delete", "admin-delete-user", f.id)}</td>
            </tr>`
          )
          .join("")}
      </tbody>
    </table>`;

  $("adminStudents").innerHTML = `
    <table class="table">
      <thead><tr><th>ID</th><th>Name</th><th>Username</th><th>Actions</th></tr></thead>
      <tbody>
        ${students
          .map(
            (s) => `<tr>
              <td>${s.id}</td>
              <td>${s.full_name}</td>
              <td>${s.username}</td>
              <td>${actionButton("Update", "admin-update-user", s.id)} ${actionButton("Delete", "admin-delete-user", s.id)}</td>
            </tr>`
          )
          .join("")}
      </tbody>
    </table>`;

  renderSimpleTable(
    "adminAssignments",
    [
      { key: "assignment_id", label: "ID" },
      { key: "faculty_name", label: "Faculty" },
      { key: "student_name", label: "Student" },
      { key: "faculty_id", label: "Faculty ID" },
      { key: "student_id", label: "Student ID" },
      { key: "actions", label: "Actions" },
    ],
    assignments.map((a) => ({
      ...a,
      actions: actionButton("Delete", "admin-delete-assignment", a.assignment_id),
    }))
  );

  renderSimpleTable(
    "adminSessions",
    [
      { key: "session_id", label: "Session ID" },
      { key: "faculty_name", label: "Faculty" },
      { key: "subject_name", label: "Subject" },
      { key: "session_date", label: "Date" },
      { key: "is_finalized", label: "Finalized" },
      { key: "actions", label: "Actions" },
    ],
    sessions.map((s) => ({
      ...s,
      actions: actionButton("Delete", "admin-delete-session", s.session_id),
    }))
  );

  renderSimpleTable(
    "adminRecords",
    [
      { key: "record_id", label: "Record ID" },
      { key: "session_id", label: "Session ID" },
      { key: "subject_name", label: "Subject" },
      { key: "student_name", label: "Student" },
      { key: "is_present", label: "Present" },
      { key: "is_manual_override", label: "Manual" },
      { key: "actions", label: "Actions" },
    ],
    records.map((r) => ({
      ...r,
      actions:
        `<button type="button" class="btn-mini" data-action="admin-toggle-record" data-id="${r.record_id}" data-current-present="${r.is_present}">Toggle Presence</button>` +
        " " +
        actionButton("Delete", "admin-delete-record", r.record_id),
    }))
  );
}

async function refreshStudentData() {
  renderStatsSkeleton("studentStats", 4);
  renderPanelSkeleton("myFaculty", 3);
  renderPanelSkeleton("studentPhotoStatus", 3);
  renderTableSkeleton("studentAttendanceHistory", 6, 5);

  const [dash, facultyInfo, photoStatus, attendanceHistory] = await Promise.all([
    api("/student/dashboard"),
    api("/student/my-faculty"),
    api("/student/photo-status"),
    api("/student/attendance-history"),
  ]);

  state.studentRegistrationReady = photoStatus.registration_ready;
  renderStudentPhotoStatus(photoStatus);
  renderStudentAttendanceHistory(attendanceHistory);
  await refreshStudentPhotoPreview();

  $("studentStats").innerHTML =
    statCard("Total Classes", dash.total_classes, { percent: 100 }) +
    statCard("Attended", dash.attended_classes, {
      percent: dash.total_classes ? (dash.attended_classes / dash.total_classes) * 100 : 0,
    }) +
    statCard("Absent", dash.absent_classes, {
      percent: dash.total_classes ? (dash.absent_classes / dash.total_classes) * 100 : 0,
    }) +
    statCard("Percentage", `${dash.attendance_percentage}%`, { percent: dash.attendance_percentage });

  if (!facultyInfo.faculty) {
    $("myFaculty").innerHTML = "Not assigned yet.";
  } else {
    const faculties = facultyInfo.faculties && facultyInfo.faculties.length ? facultyInfo.faculties : [facultyInfo.faculty];
    $("myFaculty").innerHTML = faculties
      .map(
        (f) => `
      <strong>${f.name}</strong><br />
      Username: ${f.username}<br />
      Faculty ID: ${f.id}`
      )
      .join("<hr />");
  }
}

function setScanInProgress(inProgress, keepStatusText = false) {
  state.isScanning = inProgress;
  const scanForm = $("scanForm");
  const scanInput = $("groupPhotos");
  const scanBtn = scanForm ? scanForm.querySelector("button[type='submit']") : null;

  if (scanInput) {
    scanInput.disabled = inProgress;
  }
  if (scanBtn) {
    scanBtn.disabled = inProgress;
    scanBtn.textContent = inProgress ? "Scanning..." : "Scan & Auto Mark";
  }
  if ($("scanStatus") && !keepStatusText) {
    $("scanStatus").textContent = inProgress ? "Scan status: in progress..." : "Scan status: idle";
  }
}

async function refreshFacultyLiveSession() {
  const data = await api("/faculty/attendance/live");
  if (data.live) {
    state.sessionId = data.live.session_id;
    $("currentSession").textContent = String(state.sessionId);
    return;
  }

  state.sessionId = null;
  $("currentSession").textContent = "none";
}

function renderFacultySessionMeta(session) {
  if (!session) {
    $("facultySessionMeta").innerHTML = "No session selected.";
    return;
  }

  const deadlineText = session.update_deadline ? new Date(session.update_deadline).toLocaleString() : "N/A";
  const statusText = session.can_update ? "Editable" : "Locked";

  $("facultySessionMeta").innerHTML = `
    <strong>Session Details</strong><br />
    Session ID: ${session.session_id}<br />
    Subject: ${session.subject_name}<br />
    Date: ${new Date(session.session_date).toLocaleString()}<br />
    Finalized: ${session.is_finalized ? "Yes" : "No"}<br />
    Update status: ${statusText}<br />
    Update deadline: ${deadlineText}`;
}

function getSelectedFacultySession() {
  if (!state.sessionId) {
    return null;
  }
  return state.facultySessions.find((s) => s.session_id === state.sessionId) || null;
}

async function refreshFacultyAssignedStudents() {
  const students = await api("/faculty/students");
  const studentSelect = $("manualStudentId");

  if (!students.length) {
    studentSelect.innerHTML = '<option value="">No assigned students</option>';
    studentSelect.disabled = true;
    return;
  }

  studentSelect.innerHTML = students
    .map((student) => `<option value="${student.id}">${student.id} - ${student.full_name} (${student.username})</option>`)
    .join("");
  studentSelect.disabled = false;
}

async function refreshFacultySessions() {
  renderTableSkeleton("facultySessionsTable", 6, 6);

  const sessions = await api("/faculty/attendance/sessions");
  state.facultySessions = sessions;

  renderSimpleTable(
    "facultySessionsTable",
    [
      { key: "session_id", label: "Session ID" },
      { key: "subject_name", label: "Subject" },
      { key: "session_date", label: "Date" },
      { key: "is_finalized", label: "Finalized" },
      { key: "can_update", label: "Editable" },
      { key: "update_deadline", label: "Update Deadline" },
      { key: "actions", label: "Actions" },
    ],
    sessions.map((session) => ({
      ...session,
      actions: actionButton("Open", "faculty-open-session", session.session_id),
    }))
  );

  renderFacultySessionMeta(getSelectedFacultySession());
}

async function refreshRoleData() {
  if (!state.token) {
    return;
  }
  if (state.role === "admin") {
    await refreshAdminData();
    activateAdminSection("adminSectionCreateStudent");
  }
  if (state.role === "student") {
    await refreshStudentData();
    if (state.studentRegistrationReady) {
      activateStudentSection("studentSectionSummary");
    } else {
      activateStudentSection("studentSectionRegister");
    }
  }
  if (state.role === "faculty") {
    await Promise.all([refreshFacultyLiveSession(), refreshFacultySessions(), refreshFacultyAssignedStudents()]);
    if (state.sessionId) {
      activateFacultySection("facultySectionScan");
    } else {
      activateFacultySection("facultySectionStart");
      renderFacultySessionMeta(null);
    }
  }
}

function renderAttendanceTable(items) {
  if (!items.length) {
    $("facultyAttendanceTable").innerHTML = '<div class="empty-state">No records found.</div>';
    return;
  }

  const rows = items
    .map(
      (item) => `
      <tr>
        <td>${item.student_id}</td>
        <td>${item.student_name}</td>
        <td>${item.is_present ? '<span class="badge badge-success">Present</span>' : '<span class="badge badge-danger">Absent</span>'}</td>
        <td>${item.is_manual_override ? '<span class="badge badge-brand">Manual</span>' : '<span class="badge badge-muted">Auto</span>'}</td>
      </tr>`
    )
    .join("");

  $("facultyAttendanceTable").innerHTML = `
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Student ID</th>
            <th>Name</th>
            <th>Status</th>
            <th>Mode</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function validateUserCreateForm(fullName, username, password) {
  if (!fullName) {
    return "Full name is required";
  }
  if (username.length < 3) {
    return "Username must be at least 3 characters";
  }
  if (password.length < 5) {
    return "Password must be at least 5 characters";
  }
  return "";
}

$("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await login($("loginUsername").value.trim(), $("loginPassword").value.trim());
    showMessage("Login successful");
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("logoutBtn").addEventListener("click", () => {
  clearSession();
  showRoleView();
  showMessage("Logged out");
});

$("addFacultyForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fullName = $("facultyName").value.trim();
  const username = $("facultyUsername").value.trim();
  const password = $("facultyPassword").value;
  const validationMessage = validateUserCreateForm(fullName, username, password);
  if (validationMessage) {
    showMessage(validationMessage, true);
    return;
  }

  try {
    await api("/admin/faculty", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: fullName,
        username: username,
        password: password,
      }),
    });
    e.target.reset();
    await refreshAdminData();
    showMessage("Faculty created");
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("addStudentForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fullName = $("studentName").value.trim();
  const username = $("studentUsername").value.trim();
  const password = $("studentPassword").value;
  const validationMessage = validateUserCreateForm(fullName, username, password);
  if (validationMessage) {
    showMessage(validationMessage, true);
    return;
  }

  try {
    await api("/admin/student", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: fullName,
        username: username,
        password: password,
      }),
    });
    e.target.reset();
    await refreshAdminData();
    showMessage("Student created");
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("assignForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/admin/assign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        faculty_id: Number($("facultySelect").value),
        student_id: Number($("studentSelect").value),
      }),
    });
    await refreshAdminData();
    showMessage("Student assigned to faculty");
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("refreshAdminDataBtn").addEventListener("click", async () => {
  try {
    await refreshAdminData();
    showMessage("Admin tables refreshed");
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("adminStudentSearchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const studentId = Number($("adminStudentSearchId").value);

  if (!Number.isInteger(studentId) || studentId <= 0) {
    showMessage("Enter a valid student ID", true);
    return;
  }

  try {
    const data = await api(`/admin/students/${studentId}/records`);
    renderStudentLookup(data);
    showMessage("Student data loaded");
  } catch (error) {
    $("adminStudentLookup").innerHTML = '<div class="empty-state">No student data found.</div>';
    showMessage(error.message, true);
  }
});

$("startSessionForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = await api("/faculty/attendance/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject_name: $("subjectName").value.trim() }),
    });
    state.sessionId = data.session_id;
    $("currentSession").textContent = String(state.sessionId);
    await refreshFacultySessions();
    await refreshFacultyAssignedStudents();
    renderFacultySessionMeta(getSelectedFacultySession());
    activateFacultySection("facultySectionScan");
    if (data.already_live) {
      showMessage(`Session ${state.sessionId} is already live. Continue with photo upload.`, true);
      return;
    }
    showMessage(`Session ${state.sessionId} started. Upload group photos next.`);
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("scanForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.sessionId) {
    showMessage("Start session first", true);
    return;
  }

  const files = $("groupPhotos").files;
  if (!files.length) {
    showMessage("Select at least one group photo", true);
    return;
  }

  try {
    setScanInProgress(true);
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));

    const data = await api(`/faculty/attendance/${state.sessionId}/scan`, {
      method: "POST",
      body: form,
    });

    if ($("scanStatus")) {
      $("scanStatus").textContent = `Scan status: completed (auto-marked ${data.present_marked})`;
    }
    const attendanceRows = await api(`/faculty/attendance/${state.sessionId}`);
    renderAttendanceTable(attendanceRows);
    activateFacultySection("facultySectionAttendance");
    renderFacultySessionMeta(getSelectedFacultySession());
    await refreshFacultyStatusSummary();
    await refreshFacultyFacesReview();
    showMessage(`Auto-marked: ${data.present_marked}. Review attendance next.`);
  } catch (error) {
    showMessage(error.message, true);
    if ($("scanStatus")) {
      $("scanStatus").textContent = "Scan status: failed";
    }
  } finally {
    setScanInProgress(false, true);
  }
});

$("manualForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.sessionId) {
    showMessage("Select a session from Previous Sessions or start a new one first.", true);
    return;
  }

  try {
    const selectedStudent = $("manualStudentId").value;
    if (!selectedStudent) {
      showMessage("No assigned student available for manual update", true);
      return;
    }

    const studentId = Number(selectedStudent);
    if (!Number.isInteger(studentId) || studentId <= 0) {
      showMessage("Enter a valid student ID", true);
      return;
    }

    const manualBtn = $("manualForm").querySelector("button[type='submit']");
    manualBtn.disabled = true;
    manualBtn.textContent = "Updating...";

    await api(`/faculty/attendance/${state.sessionId}/manual`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        student_id: studentId,
        is_present: $("manualPresence").value === "true",
      }),
    });
    showMessage("Manual update saved");
    try {
      const data = await api(`/faculty/attendance/${state.sessionId}`);
      renderAttendanceTable(data);
      activateFacultySection("facultySectionAttendance");
      await refreshFacultySessions();
      await refreshFacultyAssignedStudents();
      renderFacultySessionMeta(getSelectedFacultySession());
      await refreshFacultyStatusSummary();
      await refreshFacultyFacesReview();
    } catch {
      // Keep manual success even if table refresh fails.
    }
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    const manualBtn = $("manualForm").querySelector("button[type='submit']");
    manualBtn.disabled = false;
    manualBtn.textContent = "Update Manually";
  }
});

$("viewAttendanceBtn").addEventListener("click", async () => {
  if (!state.sessionId) {
    showMessage("Select a session from Previous Sessions or start a new one first.", true);
    return;
  }

  try {
    const data = await api(`/faculty/attendance/${state.sessionId}`);
    renderAttendanceTable(data);
    renderFacultySessionMeta(getSelectedFacultySession());
    await refreshFacultyStatusSummary();
    await refreshFacultyFacesReview();
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("finalizeBtn").addEventListener("click", async () => {
  if (!state.sessionId) {
    showMessage("Select a session from Previous Sessions or start a new one first.", true);
    return;
  }

  try {
    await api(`/faculty/attendance/${state.sessionId}/finalize`, { method: "POST" });
    await refreshFacultySessions();
    await refreshFacultyAssignedStudents();
    renderFacultySessionMeta(getSelectedFacultySession());
    showMessage("Attendance finalized. You can still edit within 7 days.");
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("goManualBtn").addEventListener("click", () => {
  activateFacultySection("facultySectionManual");
});

$("backToAttendanceBtn").addEventListener("click", () => {
  activateFacultySection("facultySectionAttendance");
});

$("refreshFacultySessionsBtn").addEventListener("click", async () => {
  try {
    await Promise.all([refreshFacultySessions(), refreshFacultyAssignedStudents()]);
    showMessage("Faculty sessions refreshed");
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("facesFilterAllBtn").addEventListener("click", () => setFacultyFaceFilter("all"));
$("facesFilterRecognizedBtn").addEventListener("click", () => setFacultyFaceFilter("recognized"));
$("facesFilterUnrecognizedBtn").addEventListener("click", () => setFacultyFaceFilter("unrecognized"));

$("registerPhotosForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const files = $("studentPhotos").files;
  if (files.length < 1) {
    showMessage("Select at least one photo", true);
    return;
  }

  try {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));

    const data = await api("/student/register-photos", {
      method: "POST",
      body: form,
    });

    const ready = data.registration_ready ? "ready" : "not ready";
    const uploadedText = data.uploaded_files && data.uploaded_files.length ? data.uploaded_files.join(" | ") : "None";
    const failedText = data.failed && data.failed.length ? data.failed.join(" | ") : "None";
    $("studentUploadResult").innerHTML = `
      <strong>Upload Result</strong><br />
      Uploaded now: ${data.uploaded_now}<br />
      Total photos: ${data.total_photos}<br />
      Registration: ${ready}<br />
      Successful files: ${uploadedText}<br />
      Failed files: ${failedText}`;

    showMessage(`Uploaded ${data.uploaded_now}. Total: ${data.total_photos} (${ready})`);
    e.target.reset();
    await refreshStudentData();
  } catch (error) {
    $("studentUploadResult").innerHTML = `
      <strong>Upload Result</strong><br />
      Upload failed: ${error.message}`;
    showMessage(error.message, true);
  }
});

$("reuploadPhotosBtn").addEventListener("click", async () => {
  const proceed = window.confirm(
    "This will remove all your existing registration photos. Do you want to continue?"
  );
  if (!proceed) {
    return;
  }

  try {
    const data = await api("/student/photos", { method: "DELETE" });
    $("studentUploadResult").innerHTML = `<strong>Upload Result</strong><br />${data.message}`;
    await refreshStudentData();
    activateStudentSection("studentSectionRegister");
    showMessage("Previous photos removed. Upload new photos now.");
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("adminView").addEventListener("click", async (e) => {
  const navButton = e.target.closest(".admin-nav-btn");
  if (navButton) {
    const sectionId = navButton.dataset.adminSection;
    if (sectionId) {
      activateAdminSection(sectionId);
    }
    return;
  }

  const button = e.target.closest("button[data-action]");
  if (!button) {
    return;
  }

  const action = button.dataset.action;
  const id = Number(button.dataset.id);
  if (!id) {
    showMessage("Invalid action target", true);
    return;
  }

  try {
    if (action === "admin-delete-user") {
      await api(`/admin/users/${id}`, { method: "DELETE" });
      showMessage("User deleted");
    }

    if (action === "admin-update-user") {
      const fullName = window.prompt("Enter new full name (leave blank to skip):", "");
      const username = window.prompt("Enter new username (leave blank to skip):", "");
      const payload = {};
      if (fullName && fullName.trim()) payload.full_name = fullName.trim();
      if (username && username.trim()) payload.username = username.trim();
      if (!Object.keys(payload).length) {
        showMessage("No update values provided", true);
        return;
      }
      await api(`/admin/users/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      showMessage("User updated");
    }

    if (action === "admin-delete-assignment") {
      await api(`/admin/assignments/${id}`, { method: "DELETE" });
      showMessage("Assignment deleted");
    }

    if (action === "admin-delete-session") {
      await api(`/admin/sessions/${id}`, { method: "DELETE" });
      showMessage("Session deleted");
    }

    if (action === "admin-toggle-record") {
      const current = String(button.dataset.currentPresent).toLowerCase() === "true";
      const next = !current;
      await api(`/admin/records/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_present: next, is_manual_override: next }),
      });
      showMessage("Record updated");
    }

    if (action === "admin-delete-record") {
      await api(`/admin/records/${id}`, { method: "DELETE" });
      showMessage("Record deleted");
    }

    await refreshAdminData();
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("facultyView").addEventListener("click", async (e) => {
  const navButton = e.target.closest(".role-nav-btn");
  if (!navButton) {
    const actionButtonElement = e.target.closest("button[data-action]");
    if (!actionButtonElement) {
      return;
    }

    if (actionButtonElement.dataset.action === "faculty-open-session") {
      const id = Number(actionButtonElement.dataset.id);
      if (!id) {
        showMessage("Invalid session selected", true);
        return;
      }

      state.sessionId = id;
      $("currentSession").textContent = String(id);

      try {
        const rows = await api(`/faculty/attendance/${id}`);
        renderAttendanceTable(rows);
        await refreshFacultyAssignedStudents();
        renderFacultySessionMeta(getSelectedFacultySession());
        await refreshFacultyStatusSummary();
        await refreshFacultyFacesReview();
        activateFacultySection("facultySectionAttendance");
        showMessage(`Opened session ${id}`);
      } catch (error) {
        showMessage(error.message, true);
      }
    }

    if (actionButtonElement.dataset.action === "faculty-mark-face") {
      if (!state.sessionId) {
        showMessage("Select a session first.", true);
        return;
      }

      const faceId = actionButtonElement.dataset.faceId;
      const selectId = actionButtonElement.dataset.selectId;
      if (!faceId || !selectId) {
        showMessage("Face mapping controls are invalid.", true);
        return;
      }

      const select = document.getElementById(selectId);
      if (!select) {
        showMessage("Student selector not found.", true);
        return;
      }

      const studentId = Number(select.value);
      if (!Number.isInteger(studentId) || studentId <= 0) {
        showMessage("Select a valid unmarked student.", true);
        return;
      }

      try {
        await api(`/faculty/attendance/${state.sessionId}/faces-review/${encodeURIComponent(faceId)}/mark`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ student_id: studentId }),
        });

        const rows = await api(`/faculty/attendance/${state.sessionId}`);
        renderAttendanceTable(rows);
        await refreshFacultyStatusSummary();
        await refreshFacultyFacesReview();
        showMessage("Face mapped and student marked present.");
      } catch (error) {
        showMessage(error.message, true);
      }
    }
    return;
  }
  const sectionId = navButton.dataset.facultySection;
  if (sectionId) {
    activateFacultySection(sectionId);
  }
});

$("studentView").addEventListener("click", (e) => {
  const navButton = e.target.closest(".role-nav-btn");
  if (!navButton) {
    return;
  }
  const sectionId = navButton.dataset.studentSection;
  if (sectionId) {
    activateStudentSection(sectionId);
  }
});

(async function init() {
  requestAnimationFrame(() => {
    document.body.classList.add("is-ready");
  });

  showRoleView();
  if (state.token) {
    try {
      await api("/auth/me");
      await refreshRoleData();
      startAuthHeartbeat();
    } catch (error) {
      clearSession();
      showRoleView();
      showMessage("Session expired. Please login again.", true);
    }
  }
})();
