const createTab = document.getElementById("create-tab");
const joinTab = document.getElementById("join-tab");
const createForm = document.getElementById("create-room-form");
const joinForm = document.getElementById("join-room-form");
const accessType = document.getElementById("access-type");
const secretField = document.getElementById("secret-field");
const secretInput = document.getElementById("room-secret");
const secretLabel = document.getElementById("secret-label");
const secretHint = document.getElementById("secret-hint");
const toggleSecret = document.getElementById("toggle-secret");
const createError = document.getElementById("create-error");
const joinError = document.getElementById("join-error");
const approvalRequired = document.getElementById("approval-required");
const lobbyToast = document.getElementById("lobby-toast");
const lobbyToastText = document.getElementById("lobby-toast-text");
const lobbyToastClose = document.getElementById("lobby-toast-close");

const notice = new URLSearchParams(window.location.search).get("notice");
const noticeMessages = {
  kicked: "El administrador tomó la decisión de expulsarte de la sala.",
  rejected: "El administrador no te ha concedido el privilegio de entrar.",
};
if (noticeMessages[notice]) {
  lobbyToastText.textContent = noticeMessages[notice];
  lobbyToast.hidden = false;
  history.replaceState({}, "", "/");
}
lobbyToastClose.addEventListener("click", () => { lobbyToast.hidden = true; });

function selectTab(tab) {
  const creating = tab === "create";
  createTab.classList.toggle("active", creating);
  joinTab.classList.toggle("active", !creating);
  createForm.hidden = !creating;
  joinForm.hidden = creating;
  (creating ? document.getElementById("room-name") : document.getElementById("room-code")).focus();
}

createTab.addEventListener("click", () => selectTab("create"));
joinTab.addEventListener("click", () => selectTab("join"));

function updateSecretField() {
  const type = accessType.value;
  secretField.hidden = type === "public";
  secretInput.required = type !== "public";
  secretInput.value = "";
  secretInput.type = type === "code" ? "text" : "password";
  secretInput.inputMode = type === "code" ? "numeric" : "text";
  secretInput.maxLength = type === "code" ? 6 : 128;
  secretInput.pattern = type === "code" ? "\\d{6}" : ".{6,}";
  secretLabel.textContent = type === "code" ? "Código de acceso" : "Contraseña";
  secretHint.textContent = type === "code" ? "Escribe exactamente 6 dígitos." : "Usa al menos 6 caracteres.";
  toggleSecret.hidden = type === "code";
}

accessType.addEventListener("change", updateSecretField);
toggleSecret.addEventListener("click", () => {
  const show = secretInput.type === "password";
  secretInput.type = show ? "text" : "password";
  toggleSecret.textContent = show ? "Ocultar" : "Mostrar";
});

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  createError.textContent = "";
  const submit = document.getElementById("create-submit");
  submit.disabled = true;
  submit.textContent = "Creando…";
  try {
    const response = await fetch("/api/rooms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: document.getElementById("room-name").value,
        access_type: accessType.value,
        secret: secretInput.value,
        approval_required: approvalRequired.checked,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "No se pudo crear la sala");
    window.location.assign(`/room/${encodeURIComponent(data.slug)}`);
  } catch (error) {
    createError.textContent = error.message;
    submit.disabled = false;
    submit.textContent = "Crear sala";
  }
});

joinForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  joinError.textContent = "";
  const slug = document.getElementById("room-code").value.trim().toLowerCase();
  if (!/^[a-z0-9_-]{4,32}$/.test(slug)) {
    joinError.textContent = "Ese código de sala no parece válido.";
    return;
  }
  try {
    const response = await fetch(`/api/rooms/${encodeURIComponent(slug)}/config`);
    if (response.status === 404) throw new Error("No encontramos una sala con ese código.");
    if (!response.ok) throw new Error("No se pudo comprobar la sala.");
    window.location.assign(`/room/${encodeURIComponent(slug)}`);
  } catch (error) {
    joinError.textContent = error.message;
  }
});

updateSecretField();
