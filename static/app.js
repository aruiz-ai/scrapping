const PREVIEW_LIMIT = 60;
const POLL_INTERVAL = 1500;

const $ = (id) => document.getElementById(id);

let pollingNull;
let loginPollingNull;

const form = $("searchForm");
const searchBtn = $("searchBtn");
const authBanner = $("authBanner");
const progressCard = $("progressCard");
const statusMessage = $("statusMessage");
const currentPageEl = $("currentPage");
const foundEl = $("found");
const progressFill = $("progressFill");
const errorBox = $("errorBox");
const resultCard = $("resultCard");
const downloadBtn = $("downloadBtn");
const previewNote = $("previewNote");
const resultsBody = $("resultsBody");
const maxPagesInput = $("maxPages");
const allPagesCheckbox = $("allPages");
const empresaInput = $("empresa");
const labelEmpresa = $("labelEmpresa");

allPagesCheckbox.addEventListener("change", () => {
  maxPagesInput.disabled = allPagesCheckbox.checked;
});

// --- Pestañas ---
const tabLinks = document.querySelectorAll(".tab-link");
tabLinks.forEach((link) => {
  link.addEventListener("click", () => {
    // Remover clase active de todos los links
    tabLinks.forEach((l) => l.classList.remove("active"));
    // Añadir clase active al hecho clic
    link.classList.add("active");

    const tab = link.dataset.tab;
    if (tab === "candidatos") {
      // Cambiar el campo de empresa por tecnologías
      labelEmpresa.textContent = "Tecnologías o habilidades";
      empresaInput.placeholder = "Ej. JavaScript, Python, AWS, Docker";
      empresaInput.name = "tecnologias"; // Ajustar nombre para el payload
    } else {
      // Restaurar campo de empresa
      labelEmpresa.textContent = "Nombre de la empresa";
      empresaInput.placeholder = "Ej. Google, Microsoft, Mercado Libre...";
      empresaInput.name = "company";
    }
    // Forzar foco en el input
    empresaInput.focus();
  });
});

function setError(message) {
  if (!message) {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
    return;
  }
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function makeLoginBanner() {
  authBanner.innerHTML =
    "Para buscar en LinkedIn necesitas una sesión activa. " +
    "Haz clic en el botón, inicia sesión en la ventana del navegador que se abre y la sesión quedará guardada. " +
    "<button type='button' id='loginBtn' class='btn-secondary'>Iniciar sesión en LinkedIn</button>";
  authBanner.classList.remove("hidden");
  $("loginBtn").addEventListener("click", startLogin);
}

function renderAuthStatus(data) {
  if (data.login_running) {
    authBanner.textContent = "Esperando a que completes el inicio de sesión en la ventana del navegador...";
    authBanner.classList.remove("hidden");
    return;
  }
  if (data.last_result && data.last_result.ok === false) {
    authBanner.textContent = "Error al iniciar sesión: " + data.last_result.error;
    authBanner.classList.remove("hidden");
    makeLoginBanner();
  } else if (data.logged_in) {
    authBanner.textContent = "Sesión de LinkedIn activa.";
    authBanner.className = "banner banner-ok";
    authBanner.classList.remove("hidden");
  } else {
    makeLoginBanner();
  }
}

async function getAuthStatus() {
  try {
    const res = await fetch("/api/auth/status");
    return await res.json();
  } catch {
    return null;
  }
}

async function refreshAuth() {
  const data = await getAuthStatus();
  if (data) renderAuthStatus(data);
}

function startLogin() {
  fetch("/api/login", { method: "POST" })
    .then(() => pollLogin())
    .catch(() => setError("No se pudo iniciar el proceso de login."));
}

function pollLogin() {
  clearInterval(loginPollingNull);
  loginPollingNull = setInterval(async () => {
    const data = await getAuthStatus();
    if (!data) return;
    if (!data.login_running) {
      clearInterval(loginPollingNull);
      renderAuthStatus(data);
      if (data.logged_in) setError(null);
    } else {
      renderAuthStatus(data);
    }
  }, 1500);
}

function renderTable(job) {
  const results = job.results || [];
  resultsBody.innerHTML = "";
  const fragment = document.createDocumentFragment();
  const shown = Math.min(results.length, PREVIEW_LIMIT);
  results.slice(0, shown).forEach((row) => {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = row.name || "-";
    const role = document.createElement("td");
    role.textContent = row.role || "-";
    const url = document.createElement("td");
    if (row.url) {
      const a = document.createElement("a");
      a.href = row.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = row.url;
      url.appendChild(a);
    } else {
      url.textContent = "-";
    }
    tr.append(name, role, url);
    fragment.appendChild(tr);
  });
  resultsBody.appendChild(fragment);

  if (results.length > PREVIEW_LIMIT) {
    previewNote.textContent =
      "Mostrando los primeros " + PREVIEW_LIMIT + " de " + results.length + " resultados.";
  } else {
    previewNote.textContent = "";
  }
}

function renderJob(job) {
  statusMessage.textContent = job.message || job.status;
  currentPageEl.textContent = job.current_page || 0;
  foundEl.textContent = job.found || 0;

  if (job.all_pages) {
    progressFill.classList.add("indeterminate");
    progressFill.style.width = "";
  } else {
    progressFill.classList.remove("indeterminate");
    progressFill.style.width = Math.min(100, ((job.current_page || 0) / (job.max_pages || 1)) * 100) + "%";
  }

  if (job.status === "running" || job.status === "pending") {
    renderTable(job);
  } else if (job.status === "done") {
    clearInterval(pollingNull);
    progressFill.classList.remove("indeterminate");
    progressFill.style.width = "100%";
    renderTable(job);
    resultCard.classList.remove("hidden");
    downloadBtn.href = "/api/jobs/" + job.id + "/download";
    downloadBtn.classList.remove("hidden");
    searchBtn.disabled = false;
    searchBtn.classList.remove("btn-disabled");
    searchBtn.textContent = "Buscar empleados";
  } else if (job.status === "needs_login") {
    clearInterval(pollingNull);
    resultCard.classList.add("hidden");
    setError(job.error);
    refreshAuth();
    searchBtn.disabled = false;
    searchBtn.classList.remove("btn-disabled");
    searchBtn.textContent = "Buscar empleados";
  } else if (job.status === "error") {
    clearInterval(pollingNull);
    setError(job.error || "Ocurrió un error inesperado.");
    searchBtn.disabled = false;
    searchBtn.classList.remove("btn-disabled");
    searchBtn.textContent = "Buscar empleados";
  }
}

function startJob(jobId) {
  resultCard.classList.add("hidden");
  progressCard.classList.remove("hidden");
  clearInterval(pollingNull);
  pollingNull = setInterval(async () => {
    try {
      const res = await fetch("/api/jobs/" + jobId);
      if (!res.ok) {
        clearInterval(pollingNull);
        setError("No se pudo obtener el estado del proceso.");
        return;
      }
      renderJob(await res.json());
    } catch {
      clearInterval(pollingNull);
      setError("Error de conexión con el servidor.");
    }
  }, POLL_INTERVAL);
}

function splitList(text) {
  return String(text || "")
    .split(/[;|\n]+/)
    .map((s) => s.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setError(null);

  const auth = await getAuthStatus();
  if (!auth || !auth.logged_in) {
    setError("Necesitas iniciar sesión en LinkedIn antes de buscar.");
    refreshAuth();
    return;
  }

  // Determinar el valor y nombre del campo según la pestaña activa
  const tabActivo = document.querySelector(".tab-link.active").dataset.tab;
  let companyValue = $("empresa").value.trim();
  let payloadCompany = companyValue;

  if (tabActivo === "candidatos") {
    // En la pestaña Candidatos, el campo contiene tecnologías; lo enviamos
    // como "company" para compatibilidad con el backend, pero el usuario
    // sabe que debe poner palabras clave de tecnología.
    empresaInput.name = "company"; // asegurar nombre consistente
    payloadCompany = empresaInput.placeholder; // usar el placeholder como valor de búsqueda
  }

  const maxPages = parseInt(maxPagesInput.value, 10) || 10;
  const payload = allPagesCheckbox.checked
    ? { company: payloadCompany, all_pages: true }
    : { company: payloadCompany, max_pages: maxPages };

  const filters = {};
  const locations = splitList($("filterLocations").value);
  const industries = splitList($("filterIndustries").value);
  if (locations.length) filters.locations = locations;
  if (industries.length) filters.industries = industries;
  if (Object.keys(filters).length) payload.filters = filters;

  searchBtn.disabled = true;
  searchBtn.classList.add("btn-disabled");
  searchBtn.textContent = "Buscando...";

  try {
    const res = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "La búsqueda falló.");
    }
    progressCard.classList.remove("hidden");
    startJob(data.job_id);
  } catch (error) {
    searchBtn.disabled = false;
    searchBtn.classList.remove("btn-disabled");
    searchBtn.textContent = "Buscar empleados";
    setError(error.message);
  }
});

refreshAuth();