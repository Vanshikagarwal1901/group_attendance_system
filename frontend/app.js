const state = {
  token: localStorage.getItem("token") || "",
  role: localStorage.getItem("role") || "",
  username: localStorage.getItem("username") || "",
  sessionId: null,
  isScanning: false,
};

const $ = (id) => document.getElementById(id);

function showMessage(text, isError = false) {
  const box = $("messageBox");
  box.textContent = text;
  box.classList.toggle("error", isError);
  box.hidden = false;
  setTimeout(() => {
    box.hidden = true;
  }, 2800);
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(path, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let msg = `Request failed: ${response.status}`;
    try {
      const data = await response.json();
      msg = data.detail || msg;
    } catch (error) {
      // Keep default message when body is not JSON.
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
}

function clearSession() {
  state.token = "";
  state.role = "";
  state.username = "";
  state.sessionId = null;
  localStorage.removeItem("token");
  localStorage.removeItem("role");
  localStorage.removeItem("username");
}

function showRoleView() {
  $("loginCard").hidden = !!state.token;
  $("adminView").hidden = state.role !== "admin";
  $("facultyView").hidden = state.role !== "faculty";
  $("studentView").hidden = state.role !== "student";
  $("logoutBtn").hidden = !state.token;
  $("whoami").textContent = state.token ? `${state.username} (${state.role})` : "Not logged in";
}

function statCard(key, value) {
  return `<div class="stat"><div class="k">${key}</div><div class="v">${value}</div></div>`;
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
  panels.forEach((panel) => {
    panel.hidden = panel.id !== sectionId;
  });

  const navButtons = document.querySelectorAll("#adminView .admin-nav-btn");
  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.adminSection === sectionId);
  });
}

function activateFacultySection(sectionId) {
  const panels = document.querySelectorAll("#facultyView .role-panel");
  panels.forEach((panel) => {
    panel.hidden = panel.id !== sectionId;
  });

  const navButtons = document.querySelectorAll("#facultyView .role-nav-btn");
  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.facultySection === sectionId);
  });
}

function activateStudentSection(sectionId) {
  const panels = document.querySelectorAll("#studentView .role-panel");
  panels.forEach((panel) => {
    panel.hidden = panel.id !== sectionId;
  });

  const navButtons = document.querySelectorAll("#studentView .role-nav-btn");
  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.studentSection === sectionId);
  });
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
      ${statCard("Total Classes", data.summary.total_classes)}
      ${statCard("Present", data.summary.present_classes)}
      ${statCard("Absent", data.summary.absent_classes)}
      ${statCard("Attendance", `${data.summary.attendance_percentage}%`)}
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
  const [dash, faculty, students, assignments, sessions, records] = await Promise.all([
    api("/admin/dashboard"),
    api("/admin/faculty"),
    api("/admin/students"),
    api("/admin/assignments"),
    api("/admin/sessions"),
    api("/admin/records"),
  ]);

  $("adminStats").innerHTML =
    statCard("Faculty", dash.faculty_count) +
    statCard("Students", dash.student_count) +
    statCard("Assignments", dash.assignment_count) +
    statCard("Total Users", dash.faculty_count + dash.student_count + 1);

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
        actionButton("Toggle Presence", "admin-toggle-record", r.record_id) +
        " " +
        actionButton("Delete", "admin-delete-record", r.record_id),
    }))
  );
}

async function refreshStudentData() {
  const [dash, facultyInfo] = await Promise.all([api("/student/dashboard"), api("/student/my-faculty")]);

  $("studentStats").innerHTML =
    statCard("Total Classes", dash.total_classes) +
    statCard("Attended", dash.attended_classes) +
    statCard("Absent", dash.absent_classes) +
    statCard("Percentage", `${dash.attendance_percentage}%`);

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
    activateStudentSection("studentSectionRegister");
  }
  if (state.role === "faculty") {
    await refreshFacultyLiveSession();
    activateFacultySection("facultySectionStart");
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
  try {
    await api("/admin/faculty", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: $("facultyName").value.trim(),
        username: $("facultyUsername").value.trim(),
        password: $("facultyPassword").value,
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
  try {
    await api("/admin/student", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: $("studentName").value.trim(),
        username: $("studentUsername").value.trim(),
        password: $("studentPassword").value,
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
    if (data.already_live) {
      showMessage(`Session ${state.sessionId} is already live. Finalize it before creating a new one.`, true);
      return;
    }
    showMessage(`Session ${state.sessionId} started`);
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
    showMessage(`Auto-marked: ${data.present_marked}`);
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
    try {
      await refreshFacultyLiveSession();
    } catch (error) {
      showMessage(error.message, true);
      return;
    }
    if (!state.sessionId) {
      showMessage("No live session found. Start session first", true);
      return;
    }
  }

  try {
    const studentId = Number($("manualStudentId").value);
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
    showMessage("Start session first", true);
    return;
  }

  try {
    const data = await api(`/faculty/attendance/${state.sessionId}`);
    renderAttendanceTable(data);
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("finalizeBtn").addEventListener("click", async () => {
  if (!state.sessionId) {
    showMessage("Start session first", true);
    return;
  }

  try {
    await api(`/faculty/attendance/${state.sessionId}/finalize`, { method: "POST" });
    state.sessionId = null;
    $("currentSession").textContent = "none";
    showMessage("Attendance finalized");
  } catch (error) {
    showMessage(error.message, true);
  }
});

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
    showMessage(`Uploaded ${data.uploaded_now}. Total: ${data.total_photos} (${ready})`);
    await refreshStudentData();
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
      const currentValueCell = button.closest("tr")?.children?.[4];
      const current = (currentValueCell?.textContent || "").toLowerCase().includes("true");
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

$("facultyView").addEventListener("click", (e) => {
  const navButton = e.target.closest(".role-nav-btn");
  if (!navButton) {
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
  showRoleView();
  if (state.token) {
    try {
      await refreshRoleData();
    } catch (error) {
      clearSession();
      showRoleView();
      showMessage("Session expired. Please login again.", true);
    }
  }
})();
