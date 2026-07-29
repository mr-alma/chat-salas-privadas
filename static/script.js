const chatBox = document.getElementById("chat-box");
const form = document.getElementById("chat-form");
const input = document.getElementById("msg-input");
const sendBtn = form.querySelector(".send-btn");
const myNameLabel = document.getElementById("my-name-label");
const myRoleTag = document.getElementById("my-role-tag");
const myProfileAvatar = document.getElementById("my-profile-avatar");
const typingIndicator = document.getElementById("typing-indicator");
const roomSlug = document.body.dataset.roomSlug;
const roomName = document.body.dataset.roomName;
const ROOM_API = `/api/rooms/${encodeURIComponent(roomSlug)}`;
const roomRailList = document.getElementById("room-rail-list");
const directRailList = document.getElementById("direct-rail-list");
const accessGate = document.getElementById("access-gate");
const accessForm = document.getElementById("access-form");
const accessSecret = document.getElementById("access-secret");
const accessLabel = document.getElementById("access-label");
const accessHelp = document.getElementById("access-help");
const accessError = document.getElementById("access-error");
const accessSubmit = document.getElementById("access-submit");
const rememberDevice = document.getElementById("remember-device");
const nameGate = document.getElementById("name-gate");
const nameForm = document.getElementById("name-form");
const displayName = document.getElementById("display-name");
const nameError = document.getElementById("name-error");
const approvalGate = document.getElementById("approval-gate");
const appToast = document.getElementById("app-toast");
const appToastText = document.getElementById("app-toast-text");
const appToastClose = document.getElementById("app-toast-close");
const pinnedBtn = document.getElementById("pinned-btn");
const pinnedPanel = document.getElementById("pinned-panel");
const pinnedPreview = document.getElementById("pinned-preview");
const jumpPinnedBtn = document.getElementById("jump-pinned-btn");
const unpinBtn = document.getElementById("unpin-btn");
const joinRequestsBtn = document.getElementById("join-requests-btn");
const joinRequestCount = document.getElementById("join-request-count");
const joinRequestsPanel = document.getElementById("join-requests-panel");
const joinRequestsList = document.getElementById("join-requests-list");
const expulsionRequestsList = document.getElementById("expulsion-requests-list");
const directRequestsBtn = document.getElementById("direct-requests-btn");
const directRequestCount = document.getElementById("direct-request-count");
const directRequestsPanel = document.getElementById("direct-requests-panel");
const directRequestsList = document.getElementById("direct-requests-list");
const mentionMenu = document.getElementById("mention-menu");
const changeNameBtn = document.getElementById("change-name-btn");
const nameEditorPanel = document.getElementById("name-editor-panel");
const changeNameForm = document.getElementById("change-name-form");
const newDisplayName = document.getElementById("new-display-name");
const changeNameError = document.getElementById("change-name-error");
const cancelNameChange = document.getElementById("cancel-name-change");
const deleteConfirmDialog = document.getElementById("delete-confirm-dialog");
const cancelDeleteForAll = document.getElementById("cancel-delete-for-all");
const confirmDeleteForAll = document.getElementById("confirm-delete-for-all");
const readOnlyBanner = document.getElementById("read-only-banner");

const attachBtn = document.getElementById("attach-btn");
const fileInput = document.getElementById("file-input");
const micBtn = document.getElementById("mic-btn");
const recordStatus = document.getElementById("record-status");
const cancelRecordBtn = document.getElementById("cancel-record-btn");

const replyBar = document.getElementById("reply-bar");
const replyBarName = document.getElementById("reply-bar-name");
const replyBarText = document.getElementById("reply-bar-text");
const replyBarCancel = document.getElementById("reply-bar-cancel");

const uploadStatus = document.getElementById("upload-status");
const voicePreview = document.getElementById("voice-preview");
const voicePreviewAudio = document.getElementById("voice-preview-audio");
const voiceDiscardBtn = document.getElementById("voice-discard-btn");
const voiceSendBtn = document.getElementById("voice-send-btn");

let myName = localStorage.getItem("chat_name");
let lastId = 0;
let chatVersion = null;
let replyingTo = null; // { id, name, text, type }
let roomConfig = null;
let accessLocked = true;
let amOwner = false;
let myMemberId = null;
let myRole = "participant";
let roomParticipants = [];
let pinnedMessageId = null;
let membershipPollTimer = null;
let unreadPollTimer = null;
let chatStarted = false;
let deleteConfirmationResolver = null;
let joinRequestSignature = "";
let expulsionRequestSignature = "";
let onlineUserSignature = "";
let joinRequestTotal = 0;
let expulsionRequestTotal = 0;
let directRequestSignature = "";
let directChats = [];
let activePersonMenu = null;
const unreadByRoom = {};

const settingsBtn = document.getElementById("settings-btn");
const settingsPanel = document.getElementById("settings-panel");
const darkModeToggle = document.getElementById("dark-mode-toggle");
const soundToggle = document.getElementById("sound-toggle");
const onlineUsers = document.getElementById("online-users");
const onlineBtn = document.getElementById("online-btn");
const offlineBanner = document.getElementById("offline-banner");
const filePreview = document.getElementById("file-preview");
const filePreviewContent = document.getElementById("file-preview-content");
const fileDiscardBtn = document.getElementById("file-discard-btn");
const fileSendBtn = document.getElementById("file-send-btn");
let pendingFile = null;
let unreadCount = 0;
const normalTitle = document.title;
const shareBtn = document.getElementById("share-btn");
const shareStatus = document.getElementById("share-status");
const KNOWN_ROOMS_KEY = "chat_known_rooms";
const ROLE_ORDER = { guest: 0, participant: 1, moderator: 2, admin: 3 };
const ROLE_LABELS = {
  guest: "Invitado",
  participant: "Participante",
  moderator: "Moderador",
  admin: "Admin",
};

function readKnownRooms() {
  try {
    const rooms = JSON.parse(localStorage.getItem(KNOWN_ROOMS_KEY) || "[]");
    return Array.isArray(rooms)
      ? rooms.filter((room) => room && /^[a-z0-9_-]{4,32}$/.test(room.slug) && room.name)
      : [];
  } catch (_error) {
    return [];
  }
}

function roomInitials(name) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word.charAt(0))
    .join("")
    .toUpperCase() || "?";
}

function roomColor(slug) {
  let hash = 0;
  for (const character of slug) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return `hsl(${Math.abs(hash) % 360} 65% 55%)`;
}

function normalizedKnownRooms() {
  const bySlug = new Map();
  bySlug.set("general", { slug: "general", name: "Sala general" });
  readKnownRooms().forEach((room) => bySlug.set(room.slug, room));
  return [...bySlug.values()].slice(0, 20);
}

function renderRoomRail() {
  const fragment = document.createDocumentFragment();
  normalizedKnownRooms().forEach((room) => {
    const link = document.createElement("a");
    link.className = "room-bubble room-entry";
    link.href = `/room/${encodeURIComponent(room.slug)}`;
    link.title = room.name;
    link.setAttribute("aria-label", `Cambiar a ${room.name}`);
    link.style.setProperty("--room-color", roomColor(room.slug));
    link.textContent = roomInitials(room.name);
    const unread = unreadByRoom[room.slug] || 0;
    if (unread > 0 && room.slug !== roomSlug) {
      const badge = document.createElement("span");
      badge.className = "room-unread-badge";
      badge.textContent = unread > 99 ? "99+" : String(unread);
      link.appendChild(badge);
    }
    if (room.slug === roomSlug) {
      link.classList.add("active");
      link.setAttribute("aria-current", "page");
    }
    fragment.appendChild(link);
  });
  roomRailList.replaceChildren(fragment);
}

function directInitials(name) {
  return roomInitials(name);
}

function closePersonMenu() {
  if (activePersonMenu) activePersonMenu.remove();
  activePersonMenu = null;
}

function renderDirectRail(chats) {
  directChats = Array.isArray(chats) ? chats : [];
  if (!directRailList) return;
  const fragment = document.createDocumentFragment();
  directChats.forEach((chat) => {
    const link = document.createElement("a");
    link.className = "room-bubble room-entry direct-entry";
    link.href = chat.url;
    link.title = `${chat.other_name} · Chat privado`;
    link.setAttribute("aria-label", `Chat privado con ${chat.other_name}`);
    link.style.setProperty("--room-color", roomColor(`direct-${chat.id}`));
    link.textContent = directInitials(chat.other_name);
    if (chat.unread_count > 0) {
      const badge = document.createElement("span");
      badge.className = "room-unread-badge";
      badge.textContent = chat.unread_count > 99 ? "99+" : String(chat.unread_count);
      link.appendChild(badge);
    }
    fragment.appendChild(link);
  });
  directRailList.replaceChildren(fragment);
  directRailList.closest(".rail-direct-section")?.classList.toggle("empty", !directChats.length);
}

function renderDirectRequests(requests) {
  const pending = Array.isArray(requests) ? requests : [];
  const signature = JSON.stringify(
    pending.map((item) => [item.id, item.requester_name, item.requester_role, item.room_name])
  );
  directRequestsBtn.hidden = pending.length === 0;
  directRequestCount.textContent = pending.length > 9 ? "9+" : String(pending.length || "");
  if (!pending.length) directRequestsPanel.hidden = true;
  if (signature === directRequestSignature) return;
  directRequestSignature = signature;
  directRequestsList.replaceChildren();
  if (!pending.length) {
    const empty = document.createElement("p");
    empty.className = "panel-empty";
    empty.textContent = "No tienes solicitudes de chat privado.";
    directRequestsList.appendChild(empty);
    return;
  }
  pending.forEach((item) => {
    const row = document.createElement("article");
    row.className = "join-request-row direct-request-row";
    const summary = document.createElement("div");
    summary.className = "request-summary";
    summary.innerHTML = `
      <strong>${escapeHtml(item.requester_name)}</strong>
      <span class="role-tag role-${item.requester_role}">${escapeHtml(item.requester_role_label || roleLabel(item.requester_role))}</span>
      <small>Quiere iniciar un chat privado desde ${escapeHtml(item.room_name)}.</small>
    `;
    const actions = document.createElement("div");
    const accept = document.createElement("button");
    const reject = document.createElement("button");
    accept.type = reject.type = "button";
    accept.className = "approve-request-btn";
    reject.className = "reject-request-btn";
    accept.textContent = "Aceptar";
    reject.textContent = "Rechazar";
    async function decide(action) {
      accept.disabled = true;
      reject.disabled = true;
      const response = await fetch(`/api/direct-chat-requests/${item.id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        showAppToast(data.error || "No se pudo guardar tu decisión");
        accept.disabled = false;
        reject.disabled = false;
        return;
      }
      if (action === "accept") {
        window.location.assign(data.url);
        return;
      }
      row.remove();
      showAppToast("Solicitud de chat privado rechazada.");
      await pollDirectState();
    }
    accept.addEventListener("click", () => decide("accept"));
    reject.addEventListener("click", () => decide("reject"));
    actions.append(accept, reject);
    row.append(summary, actions);
    directRequestsList.appendChild(row);
  });
}

async function pollDirectState() {
  try {
    const response = await fetch("/api/direct-chats");
    if (!response.ok) return;
    const data = await response.json();
    renderDirectRail(data.chats);
    renderDirectRequests(data.requests);
  } catch (_error) {
    // La barra se sincroniza automáticamente en el siguiente ciclo.
  }
}

function rememberRoom(slug, name) {
  const previous = normalizedKnownRooms().filter((room) => room.slug !== slug);
  const current = { slug, name: (name || slug).trim().slice(0, 60) };
  const next = slug === "general"
    ? [current, ...previous.filter((room) => room.slug !== "general")]
    : [
        previous.find((room) => room.slug === "general") || { slug: "general", name: "Sala general" },
        current,
        ...previous.filter((room) => room.slug !== "general"),
      ];
  localStorage.setItem(KNOWN_ROOMS_KEY, JSON.stringify(next.slice(0, 20)));
  renderRoomRail();
}

renderRoomRail();

function showAppToast(message) {
  appToastText.textContent = message;
  appToast.hidden = false;
}

appToastClose.addEventListener("click", () => { appToast.hidden = true; });

function insertMention(name) {
  if (myRole === "guest") return;
  const start = Number.isInteger(input.selectionStart) ? input.selectionStart : input.value.length;
  const end = Number.isInteger(input.selectionEnd) ? input.selectionEnd : start;
  const before = input.value.slice(0, start);
  const after = input.value.slice(end);
  const leadingSpace = before && !/\s$/.test(before) ? " " : "";
  const mention = `${leadingSpace}@${name} `;
  input.value = `${before}${mention}${after}`;
  const cursor = before.length + mention.length;
  input.focus();
  input.setSelectionRange(cursor, cursor);
  updateMentionMenu();
}

async function requestPrivateChat(person) {
  const response = await fetch(`${ROOM_API}/members/${person.id}/direct-request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    showAppToast(data.error || "No se pudo enviar la solicitud de chat privado");
    return;
  }
  if (data.status === "accepted" && data.url) {
    window.location.assign(data.url);
    return;
  }
  await pollDirectState();
  if (data.status === "incoming_pending") {
    directRequestsPanel.hidden = false;
  }
  showAppToast(data.message || `Solicitud enviada a ${person.name}.`);
}

function openPersonMenu(event, person) {
  event.preventDefault();
  event.stopPropagation();
  closePersonMenu();
  const menu = document.createElement("div");
  menu.className = "person-action-menu";
  menu.setAttribute("role", "menu");
  const profileButton = document.createElement("button");
  profileButton.type = "button";
  profileButton.innerHTML = `<span aria-hidden="true">👤</span><span>Ver perfil</span>`;
  profileButton.addEventListener("click", (clickEvent) => {
    clickEvent.stopPropagation();
    closePersonMenu();
    window.openChatProfile?.(person.id, person.id === myMemberId);
  });
  menu.appendChild(profileButton);
  if (person.id === myMemberId) {
    document.body.appendChild(menu);
    const anchor = event.currentTarget.getBoundingClientRect();
    menu.style.left = `${Math.max(10, anchor.left)}px`;
    menu.style.top = `${anchor.bottom + 6}px`;
    activePersonMenu = menu;
    return;
  }
  const mentionButton = document.createElement("button");
  mentionButton.type = "button";
  mentionButton.innerHTML = `<span aria-hidden="true">@</span><span>Mencionar</span>`;
  mentionButton.addEventListener("click", (clickEvent) => {
    clickEvent.stopPropagation();
    insertMention(person.name);
    closePersonMenu();
  });
  if (myRole === "guest") {
    mentionButton.disabled = true;
    mentionButton.title = "El modo Invitado es de solo lectura";
  }
  const directButton = document.createElement("button");
  directButton.type = "button";
  directButton.innerHTML = `<span aria-hidden="true">💌</span><span>Iniciar chat privado</span>`;
  if (person.role === "guest" || myRole === "guest") {
    directButton.disabled = true;
    directButton.title = "Los invitados tienen acceso de solo lectura";
  } else {
    directButton.addEventListener("click", async (clickEvent) => {
      clickEvent.stopPropagation();
      directButton.disabled = true;
      await requestPrivateChat(person);
      closePersonMenu();
    });
  }
  menu.append(mentionButton, directButton);
  document.body.appendChild(menu);
  const anchor = event.currentTarget.getBoundingClientRect();
  const menuRect = menu.getBoundingClientRect();
  const left = Math.min(
    window.innerWidth - menuRect.width - 10,
    Math.max(10, anchor.left)
  );
  const roomBelow = window.innerHeight - anchor.bottom;
  const top = roomBelow >= menuRect.height + 8
    ? anchor.bottom + 6
    : Math.max(10, anchor.top - menuRect.height - 6);
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  activePersonMenu = menu;
}

document.addEventListener("click", closePersonMenu);
window.addEventListener("resize", closePersonMenu);
window.addEventListener("scroll", closePersonMenu, true);

function leaveRoomWithNotice(notice) {
  clearTimeout(pollTimer);
  clearTimeout(membershipPollTimer);
  clearTimeout(unreadPollTimer);
  window.location.assign(`/?notice=${encodeURIComponent(notice)}`);
}

shareBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(window.location.href);
    shareStatus.textContent = "Enlace copiado";
  } catch (_error) {
    shareStatus.textContent = `Enlace: ${window.location.href}`;
  }
  shareStatus.classList.add("show");
  setTimeout(() => shareStatus.classList.remove("show"), 1800);
});

function applyTheme(dark) {
  document.body.classList.toggle("dark-mode", dark);
  darkModeToggle.checked = dark;
  localStorage.setItem("chat_dark_mode", dark ? "1" : "0");
}
applyTheme(localStorage.getItem("chat_dark_mode") === "1");
soundToggle.checked = localStorage.getItem("chat_sound") !== "0";
settingsBtn.addEventListener("click", () => {
  window.closeMediaGallery?.();
  settingsPanel.classList.toggle("show");
});
onlineBtn.addEventListener("click", () => {
  window.closeMediaGallery?.();
  onlineUsers.classList.toggle("show");
});
darkModeToggle.addEventListener("change", () => applyTheme(darkModeToggle.checked));
soundToggle.addEventListener("change", () => localStorage.setItem("chat_sound", soundToggle.checked ? "1" : "0"));

function playNotification() {
  if (!soundToggle.checked) return;
  const audio = new Audio("data:audio/wav;base64,UklGRjIAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQ4AAAAAgICAgICAgICAgICAgIA=");
  audio.play().catch(() => {});
}

// ---------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------

function askName() {
  while (!myName || !myName.trim()) {
    myName = prompt("¿Cómo te llamas?");
  }
  myName = myName.trim().slice(0, 40);
  localStorage.setItem("chat_name", myName);
  myNameLabel.textContent = myName;
}

function setCurrentName(name) {
  myName = name.trim().slice(0, 40);
  localStorage.setItem("chat_name", myName);
  myNameLabel.textContent = myName;
  const profile = roomParticipants.find((participant) => participant.id === myMemberId)
    || roomConfig?.member;
  if (profile) window.setChatAvatar?.(myProfileAvatar, profile);
}

function roleLabel(role) {
  return ROLE_LABELS[role] || ROLE_LABELS.participant;
}

function applyRoleUI(role) {
  myRole = ROLE_ORDER[role] === undefined ? "participant" : role;
  amOwner = myRole === "admin";
  myRoleTag.textContent = roleLabel(myRole);
  myRoleTag.className = `role-tag role-${myRole}`;
  const readOnly = myRole === "guest";
  form.hidden = readOnly;
  readOnlyBanner.hidden = !readOnly;
  changeNameBtn.disabled = false;
  if (!amOwner) {
    joinRequestsPanel.hidden = true;
  }
  if (readOnly) {
    closeNameEditor();
    clearReply();
    mentionMenu.hidden = true;
    voicePreview.classList.remove("show");
    filePreview.classList.remove("show");
  }
}

async function showMemberWelcome(member) {
  if (!member || !member.welcome) return false;
  const welcome = member.welcome;
  showAppToast(
    `¡Bienvenido! Has sido aceptado por ${welcome.approved_by_name} ` +
    `(${welcome.approved_by_role_label}) con el rol de ${welcome.assigned_role_label}.`
  );
  await fetch(`${ROOM_API}/membership/welcome-seen`, { method: "POST" }).catch(() => {});
  delete member.welcome;
  return true;
}

function closeNameEditor() {
  nameEditorPanel.hidden = true;
  changeNameError.textContent = "";
}

changeNameBtn.addEventListener("click", () => {
  closeNameEditor();
  window.openChatProfile?.(myMemberId, true);
});

cancelNameChange.addEventListener("click", closeNameEditor);

changeNameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = newDisplayName.value.trim();
  if (!name) {
    changeNameError.textContent = "Escribe el nombre que quieres mostrar.";
    return;
  }
  const saveButton = changeNameForm.querySelector('button[type="submit"]');
  saveButton.disabled = true;
  changeNameError.textContent = "";
  try {
    const response = await fetch(`${ROOM_API}/membership/name`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "No se pudo cambiar el nombre");
    const oldName = myName;
    setCurrentName(data.member.name);
    roomConfig.member = data.member;
    roomParticipants = roomParticipants.map((participant) => (
      participant.id === myMemberId
        ? { ...participant, name: data.member.name }
        : participant
    ));
    closeNameEditor();
    if (oldName !== data.member.name) {
      showAppToast(`Ahora apareces como ${data.member.name}.`);
    }
  } catch (error) {
    changeNameError.textContent = error.message;
  } finally {
    saveButton.disabled = false;
  }
});

function resolveDeleteConfirmation(confirmed) {
  deleteConfirmDialog.hidden = true;
  if (deleteConfirmationResolver) {
    deleteConfirmationResolver(confirmed);
    deleteConfirmationResolver = null;
  }
}

function askDeleteForAllConfirmation() {
  if (deleteConfirmationResolver) resolveDeleteConfirmation(false);
  deleteConfirmDialog.hidden = false;
  confirmDeleteForAll.focus();
  return new Promise((resolve) => {
    deleteConfirmationResolver = resolve;
  });
}

cancelDeleteForAll.addEventListener("click", () => resolveDeleteConfirmation(false));
confirmDeleteForAll.addEventListener("click", () => resolveDeleteConfirmation(true));
deleteConfirmDialog.addEventListener("click", (event) => {
  if (event.target === deleteConfirmDialog) resolveDeleteConfirmation(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !deleteConfirmDialog.hidden) {
    resolveDeleteConfirmation(false);
  }
});

function startChat() {
  setCurrentName(myName);
  nameGate.hidden = true;
  approvalGate.hidden = true;
  accessGate.hidden = true;
  accessLocked = false;
  document.body.classList.add("room-ready");
  rememberRoom(roomSlug, (roomConfig && roomConfig.name) || roomName);
  if (!chatStarted) {
    chatStarted = true;
    pollUpdates();
    pollUnreadCounts();
  }
  chatBox.scrollTop = chatBox.scrollHeight;
}

function showApprovalWaiting() {
  nameGate.hidden = true;
  accessGate.hidden = true;
  approvalGate.hidden = false;
  document.body.classList.remove("room-ready");
  clearTimeout(membershipPollTimer);
  membershipPollTimer = setTimeout(pollMembership, 1200);
}

async function pollMembership() {
  try {
    const response = await fetch(`${ROOM_API}/membership`, { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    const member = data.member;
    if (response.status === 401) {
      approvalGate.hidden = true;
      lockRoom();
      return;
    }
    if (member && member.status === "approved") {
      roomConfig.member = member;
      myMemberId = member.id;
      applyRoleUI(member.role);
      setCurrentName(member.name);
      if (!await showMemberWelcome(member)) {
        showAppToast(`¡Bienvenido a ${roomConfig.name}! Tu rol es ${roleLabel(member.role)}.`);
      }
      startChat();
      return;
    }
    if (member && member.status === "rejected") return leaveRoomWithNotice("rejected");
    if (member && member.status === "kicked") return leaveRoomWithNotice("kicked");
  } catch (_error) {
    // Una caída breve de red no cancela la solicitud.
  }
  membershipPollTimer = setTimeout(pollMembership, 1200);
}

async function prepareMembership() {
  const member = roomConfig && roomConfig.member;
  if (member && member.status === "kicked") return leaveRoomWithNotice("kicked");
  if (member && member.status === "rejected") return leaveRoomWithNotice("rejected");
  if (member && member.status === "pending") return showApprovalWaiting();
  if (member && member.status === "approved" && member.name) {
    myMemberId = member.id;
    applyRoleUI(member.role);
    setCurrentName(member.name);
    await showMemberWelcome(member);
    startChat();
    return;
  }
  document.body.classList.remove("room-ready");
  accessGate.hidden = true;
  nameGate.hidden = false;
  displayName.value = (member && member.name) || myName || "";
  displayName.focus();
}

nameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = displayName.value.trim();
  if (!name) {
    nameError.textContent = "Escribe el nombre que quieres mostrar.";
    return;
  }
  nameError.textContent = "";
  const submit = nameForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  submit.textContent = "Entrando…";
  try {
    const response = await fetch(`${ROOM_API}/membership`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok && response.status !== 202) {
      if (data.code === "member_kicked") return leaveRoomWithNotice("kicked");
      if (data.code === "approval_rejected") return leaveRoomWithNotice("rejected");
      throw new Error(data.error || "No se pudo entrar a la sala");
    }
    roomConfig.member = data.member;
    myMemberId = data.member.id;
    applyRoleUI(data.member.role);
    setCurrentName(data.member.name);
    if (data.member.status === "pending") {
      showApprovalWaiting();
    } else {
      if (!amOwner) {
        showAppToast(
          `¡Bienvenido a ${roomConfig.name}! Tu rol es ${roleLabel(data.member.role)}.`
        );
      }
      startChat();
    }
  } catch (error) {
    nameError.textContent = error.message;
  } finally {
    submit.disabled = false;
    submit.textContent = "Continuar";
  }
});

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str == null ? "" : String(str);
  return d.innerHTML;
}

function escapeRegExp(str) {
  return String(str).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function formatTime(iso) {
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(iso);
  const d = new Date(hasTimezone ? iso : `${iso}Z`);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function previewFor(msg) {
  if (msg.type === "text") return msg.text;
  return { image: "📷 Imagen", audio: "🎤 Nota de voz", video: "🎬 Video", file: "📎 Archivo" }[msg.type] || "";
}

// ---------------------------------------------------------------------
// Render de mensajes
// ---------------------------------------------------------------------

function renderMessage(m) {
  if (m.type === "system") {
    const system = document.createElement("div");
    system.className = "system-message";
    system.dataset.id = m.id;
    system.innerHTML = `<span>${escapeHtml(m.text || "")}</span><time>${formatTime(m.created_at)}</time>`;
    chatBox.appendChild(system);
    return;
  }
  if (m.type === "deleted") {
    const deleted = document.createElement("div");
    deleted.className = "deleted-message";
    deleted.dataset.id = m.id;
    deleted.innerHTML = `<span>${escapeHtml(m.text || "")}</span><time>${formatTime(m.created_at)}</time>`;
    chatBox.appendChild(deleted);
    return;
  }
  const hiddenMessages = JSON.parse(localStorage.getItem("chat_hidden_messages") || "[]");
  if (hiddenMessages.includes(m.id)) return;
  const div = document.createElement("div");
  const isMine = m.author_member_id === myMemberId;
  div.className = "msg " + (isMine ? "mine" : "theirs");
  if (m.id === pinnedMessageId) div.classList.add("pinned");
  div.style.setProperty("--user-color", m.color || "#4E7CFF");
  div.dataset.id = m.id;

  let replyHtml = "";
  if (m.reply_to_id) {
    replyHtml = `
      <span class="reply-preview" data-jump="${m.reply_to_id}">
        <span class="reply-name">${escapeHtml(m.reply_to_name || "")}</span>
        <span class="reply-snippet">${escapeHtml(m.reply_to_text || "")}</span>
      </span>`;
  }

  let mediaHtml = "";
  if (m.type === "image") {
    mediaHtml = `<img class="msg-media" src="${m.file_url}" alt="imagen" onclick="window.open('${m.file_url}', '_blank')" />`;
  } else if (m.type === "video") {
    mediaHtml = `<video class="msg-media" src="${m.file_url}" controls></video>`;
  } else if (m.type === "audio") {
    mediaHtml = `<audio class="msg-audio" src="${m.file_url}" controls></audio>`;
  } else if (m.type === "file") {
    mediaHtml = `<a class="msg-file" href="${m.file_url}" download="${escapeHtml(m.file_name || "Archivo")}">📎 Descargar: ${escapeHtml(m.file_name || "Archivo")}</a>`;
  }

  const safeText = escapeHtml(m.text || "");
  const mention = myName && safeText.toLowerCase().includes(`@${myName.toLowerCase()}`);
  const textHtml = m.text ? `<p>${mention ? safeText.replace(new RegExp(`@${escapeRegExp(myName)}`, "ig"), `<span class="mention">$&</span>`) : safeText}</p>` : "";
  const reactions = (m.reactions || []).map(r => r.emoji).join(" ");
  const canInteract = myRole !== "guest";
  const ownActions = canInteract
    ? `<span class="own-actions">${isMine ? `<button class="edit-btn">✏️</button>` : ""}</span>`
    : "";
  const authorRole = m.author_role || "participant";
  const avatarHtml = m.author_photo_url
    ? `<span class="profile-avatar message-avatar has-photo" style="background-image:url('${escapeHtml(m.author_photo_url)}')"></span>`
    : `<span class="profile-avatar message-avatar">${escapeHtml(directInitials(m.name))}</span>`;
  const nameHtml = !isMine && canInteract
    ? `<button type="button" class="msg-name person-name-btn">${avatarHtml}${escapeHtml(m.name)} <span class="role-tag role-${authorRole}">${escapeHtml(m.author_role_label || roleLabel(authorRole))}</span></button>`
    : `<span class="msg-name">${avatarHtml}${escapeHtml(m.name)} <span class="role-tag role-${authorRole}">${escapeHtml(m.author_role_label || roleLabel(authorRole))}</span></span>`;
  const reactionControls = canInteract
    ? `<div class="reaction-row"><span>${reactions}</span><button class="reaction-trigger" title="Reaccionar">+</button><button class="pin-message-btn" title="${m.id === pinnedMessageId ? "Desfijar" : "Fijar mensaje"}">📌</button><button class="delete-btn message-delete-btn" title="${myRole === "admin" || myRole === "moderator" ? "Opciones de borrado" : "Borrar para mí"}">🗑️</button><span class="reaction-picker"><button>👍</button><button>❤️</button><button>😂</button><button>😮</button></span></div>`
    : `<div class="reaction-row"><span>${reactions}</span></div>`;

  div.innerHTML = `
    <div class="bubble">
      ${nameHtml}
      ${replyHtml}
      ${mediaHtml}
      ${textHtml}
      ${reactionControls}
      ${isMine && m.read_count ? `<span class="read-status">Visto</span>` : ""}
      <span class="msg-time">${formatTime(m.created_at)}</span>
      ${canInteract ? `<button type="button" class="reply-btn" title="Responder">↩</button>` : ""}
      ${ownActions}
    </div>
  `;

  const personNameButton = div.querySelector(".person-name-btn");
  if (personNameButton) {
    personNameButton.addEventListener("click", (event) => openPersonMenu(event, {
      id: m.author_member_id,
      name: m.name,
      role: authorRole,
    }));
  }

  const pinMessageButton = div.querySelector(".pin-message-btn");
  if (pinMessageButton) pinMessageButton.addEventListener("click", async (event) => {
    event.stopPropagation();
    const messageId = m.id === pinnedMessageId ? null : m.id;
    const response = await fetch(`${ROOM_API}/pin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) showAppToast(data.error || "No se pudo actualizar el mensaje fijado");
  });

  const replyButton = div.querySelector(".reply-btn");
  if (replyButton) replyButton.addEventListener("click", () => setReply(m));
  const picker = div.querySelector(".reaction-picker");
  const reactionTrigger = div.querySelector(".reaction-trigger");
  if (reactionTrigger && picker) {
    reactionTrigger.addEventListener("click", () => picker.classList.toggle("show"));
    picker.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
      picker.classList.remove("show");
      fetch(`${ROOM_API}/reactions`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message_id:m.id,name:myName,emoji:button.textContent})});
    }));
  }
  const editBtn = div.querySelector(".edit-btn");
  if (editBtn) editBtn.addEventListener("click", async () => {
    const text = prompt("Editar mensaje", m.text || "");
    if (text && text.trim()) await fetch(`${ROOM_API}/messages/${m.id}`, {method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:myName,text})});
    location.reload();
  });
  let actionsTimer = null;
  function showActions() {
    div.classList.add("actions-open");
    clearTimeout(actionsTimer);
    actionsTimer = setTimeout(() => {
      div.classList.remove("actions-open");
      div.querySelectorAll(".delete-menu, .reaction-picker").forEach((el) => el.classList.remove("show"));
    }, 15000);
  }
  if (canInteract) div.addEventListener("click", showActions);

  const deleteBtn = div.querySelector(".delete-btn");
  if (deleteBtn) deleteBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    const existing = div.querySelector(".delete-menu");
    if (existing) { existing.classList.toggle("show"); return; }
    const menu = document.createElement("span");
    menu.className = "delete-menu show";
    const canDeleteForAll = isMine || myRole === "admin" || myRole === "moderator";
    menu.innerHTML = `<button data-scope="me">Borrar para mí</button>${canDeleteForAll ? `<button data-scope="all">Borrar para todos</button>` : ""}`;
    div.querySelector(".own-actions").appendChild(menu);
    menu.querySelectorAll("button").forEach((button) => button.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (button.dataset.scope === "all") {
        menu.classList.remove("show");
        if (!await askDeleteForAllConfirmation()) return;
        const response = await fetch(`${ROOM_API}/messages/${m.id}`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          showAppToast(data.error || "No se pudo borrar el mensaje");
          return;
        }
        div.className = "deleted-message";
        div.innerHTML = `<span>${escapeHtml(data.text || "Este mensaje fue borrado")}</span><time>${formatTime(m.created_at)}</time>`;
      } else {
        const hidden = JSON.parse(localStorage.getItem("chat_hidden_messages") || "[]");
        if (!hidden.includes(m.id)) localStorage.setItem("chat_hidden_messages", JSON.stringify([...hidden, m.id]));
        div.remove();
      }
    }));
  });

  const jumpEl = div.querySelector(".reply-preview");
  if (jumpEl) {
    jumpEl.addEventListener("click", () => jumpToMessage(m.reply_to_id));
  }

  chatBox.appendChild(div);
}

function jumpToMessage(id) {
  const el = chatBox.querySelector(`[data-id="${id}"]`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("highlight");
    setTimeout(() => el.classList.remove("highlight"), 1200);
  }
}

function isNearBottom() {
  return chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < 120;
}

function renderPinnedMessage(message) {
  pinnedMessageId = message ? message.id : null;
  pinnedBtn.hidden = !message;
  if (!message) {
    pinnedPanel.hidden = true;
    pinnedPreview.textContent = "";
    return;
  }
  const preview = message.type === "text"
    ? message.text
    : previewFor(message);
  pinnedPreview.textContent = `${message.name}: ${preview || "Mensaje"}`;
}

function updateAdminRequestIndicator() {
  const total = amOwner ? joinRequestTotal + expulsionRequestTotal : 0;
  joinRequestsBtn.hidden = !amOwner;
  joinRequestCount.textContent = total ? String(total) : "";
  joinRequestCount.hidden = !total;
}

function renderJoinRequests(requests) {
  const pending = amOwner ? (requests || []) : [];
  joinRequestTotal = pending.length;
  updateAdminRequestIndicator();
  const signature = JSON.stringify(pending.map((item) => [item.id, item.name]));
  if (signature === joinRequestSignature) return;
  joinRequestSignature = signature;
  joinRequestsList.replaceChildren();
  if (!pending.length) {
    const empty = document.createElement("p");
    empty.className = "panel-empty";
    empty.textContent = "No hay solicitudes pendientes.";
    joinRequestsList.appendChild(empty);
    return;
  }
  pending.forEach((requestItem) => {
    const row = document.createElement("div");
    row.className = "join-request-row";
    const name = document.createElement("span");
    name.textContent = requestItem.name;
    const actions = document.createElement("div");
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = "approve-btn";
    approve.textContent = "Aceptar";
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "reject-btn";
    reject.textContent = "Rechazar";
    const roleMenu = document.createElement("div");
    roleMenu.className = "approval-role-menu";
    roleMenu.hidden = true;
    Object.entries(ROLE_LABELS).reverse().forEach(([role, label]) => {
      const roleButton = document.createElement("button");
      roleButton.type = "button";
      roleButton.className = `role-choice role-${role}`;
      roleButton.textContent = label;
      roleButton.addEventListener("click", async () => {
        approve.disabled = true;
        reject.disabled = true;
        const response = await fetch(`${ROOM_API}/members/${requestItem.id}/decision`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "approve", role }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          showAppToast(data.error || "No se pudo aceptar la solicitud");
          approve.disabled = false;
          reject.disabled = false;
          return;
        }
        row.remove();
      });
      roleMenu.appendChild(roleButton);
    });
    approve.addEventListener("click", () => {
      roleMenu.hidden = !roleMenu.hidden;
    });
    reject.addEventListener("click", async () => {
      approve.disabled = true;
      reject.disabled = true;
      const response = await fetch(`${ROOM_API}/members/${requestItem.id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "reject" }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        showAppToast(data.error || "No se pudo guardar la decisión");
        approve.disabled = false;
        reject.disabled = false;
        return;
      }
      row.remove();
    });
    actions.append(approve, reject);
    row.append(name, actions, roleMenu);
    joinRequestsList.appendChild(row);
  });
}

function renderExpulsionRequests(requests) {
  const pending = amOwner ? (requests || []) : [];
  expulsionRequestTotal = pending.length;
  updateAdminRequestIndicator();
  const signature = JSON.stringify(
    pending.map((item) => [
      item.id,
      item.requester_id,
      item.requester_name,
      item.requester_role,
      item.target_id,
      item.target_name,
      item.target_role,
    ])
  );
  if (signature === expulsionRequestSignature) return;
  expulsionRequestSignature = signature;
  expulsionRequestsList.replaceChildren();
  if (!pending.length) {
    const empty = document.createElement("p");
    empty.className = "panel-empty";
    empty.textContent = "No hay expulsiones esperando aprobación.";
    expulsionRequestsList.appendChild(empty);
    return;
  }

  pending.forEach((requestItem) => {
    const row = document.createElement("div");
    row.className = "join-request-row expulsion-request-row";
    const summary = document.createElement("div");
    summary.className = "expulsion-request-summary";
    summary.innerHTML = `
      <span><strong>${escapeHtml(requestItem.requester_name)}</strong>
        <span class="role-tag role-${requestItem.requester_role}">${escapeHtml(requestItem.requester_role_label)}</span>
      </span>
      <small>solicita expulsar a</small>
      <span><strong>${escapeHtml(requestItem.target_name)}</strong>
        <span class="role-tag role-${requestItem.target_role}">${escapeHtml(requestItem.target_role_label)}</span>
      </span>`;
    const actions = document.createElement("div");
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = "approve-btn";
    approve.textContent = "Aprobar expulsión";
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "reject-btn";
    reject.textContent = "Rechazar";

    async function decide(action) {
      approve.disabled = true;
      reject.disabled = true;
      const response = await fetch(
        `${ROOM_API}/expulsion-requests/${requestItem.id}/decision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action }),
        }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        showAppToast(data.error || "No se pudo guardar la decisión");
        approve.disabled = false;
        reject.disabled = false;
        return;
      }
      row.remove();
      showAppToast(
        action === "approve"
          ? `${requestItem.target_name} fue expulsado tras tu aprobación.`
          : "La solicitud de expulsión fue rechazada."
      );
    }

    approve.addEventListener("click", () => decide("approve"));
    reject.addEventListener("click", () => decide("reject"));
    actions.append(approve, reject);
    row.append(summary, actions);
    expulsionRequestsList.appendChild(row);
  });
}

function renderOnlineUsers(users) {
  const online = Array.isArray(users) ? users : [];
  const signature = JSON.stringify(
    online.map((person) => [person.id, person.name, person.role, Boolean(person.kick_pending)])
  );
  if (signature === onlineUserSignature) return;
  onlineUserSignature = signature;
  onlineUsers.replaceChildren();
  const heading = document.createElement("div");
  heading.className = "online-panel-heading";
  heading.innerHTML = `<strong>Usuarios online</strong><span>${online.length}</span>`;
  onlineUsers.appendChild(heading);
  if (!online.length) {
    const empty = document.createElement("p");
    empty.className = "panel-empty";
    empty.textContent = "No hay otras personas conectadas ahora.";
    onlineUsers.appendChild(empty);
    return;
  }

  online.forEach((person) => {
    const row = document.createElement("div");
    row.className = "online-member-row";
    const identity = document.createElement("div");
    identity.className = "online-member-identity";
    if (myRole !== "guest" && person.id !== myMemberId) {
      const nameButton = document.createElement("button");
      nameButton.type = "button";
      nameButton.className = "online-person-name person-name-btn";
      nameButton.textContent = person.name;
      nameButton.addEventListener("click", (event) => openPersonMenu(event, person));
      identity.appendChild(nameButton);
    } else {
      const name = document.createElement("strong");
      name.textContent = person.name;
      identity.appendChild(name);
    }
    const roleTag = document.createElement("span");
    roleTag.className = `role-tag role-${person.role}`;
    roleTag.textContent = person.role_label || roleLabel(person.role);
    identity.appendChild(roleTag);
    row.appendChild(identity);

    const canKick = (
      myRole === "admin" ||
      (myRole === "moderator" && person.role !== "admin")
    ) && person.id !== myMemberId;
    const canChangeRole = myRole === "admin" && person.id !== myMemberId;
    if (canKick || canChangeRole) {
      const manage = document.createElement("button");
      manage.type = "button";
      manage.className = "manage-member-btn";
      manage.textContent = "Gestionar";
      const panel = document.createElement("div");
      panel.className = "member-manage-panel";
      panel.hidden = true;
      manage.addEventListener("click", () => {
        panel.hidden = !panel.hidden;
      });

      const kick = document.createElement("button");
      kick.type = "button";
      kick.className = "kick-member-btn";
      kick.textContent = person.kick_pending ? "Solicitud pendiente" : "Expulsar";
      kick.disabled = Boolean(person.kick_pending);
      kick.addEventListener("click", async () => {
        kick.disabled = true;
        const response = await fetch(`${ROOM_API}/members/${person.id}/kick`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          showAppToast(data.error || "No se pudo expulsar a la persona");
          kick.disabled = false;
          return;
        }
        if (data.status === "pending_approval") {
          person.kick_pending = true;
          kick.textContent = "Solicitud enviada";
          showAppToast(data.message || "La solicitud espera la aprobación de un Admin.");
          return;
        }
        row.remove();
      });
      panel.appendChild(kick);

      if (canChangeRole) {
        const currentLevel = ROLE_ORDER[person.role];
        const directions = [
          {
            action: "ascend",
            label: "Ascender en jerarquía",
            roles: Object.keys(ROLE_ORDER).filter((role) => ROLE_ORDER[role] > currentLevel),
          },
          {
            action: "descend",
            label: "Descender en jerarquía",
            roles: Object.keys(ROLE_ORDER).filter((role) => ROLE_ORDER[role] < currentLevel).reverse(),
          },
        ];
        directions.forEach(({ action, label, roles }) => {
          if (!roles.length) return;
          const directionButton = document.createElement("button");
          directionButton.type = "button";
          directionButton.className = "hierarchy-btn";
          directionButton.textContent = label;
          const choices = document.createElement("div");
          choices.className = "hierarchy-choices";
          choices.hidden = true;
          directionButton.addEventListener("click", () => {
            choices.hidden = !choices.hidden;
          });
          roles.forEach((role) => {
            const choice = document.createElement("button");
            choice.type = "button";
            choice.className = `role-choice role-${role}`;
            choice.textContent = roleLabel(role);
            choice.addEventListener("click", async () => {
              const response = await fetch(`${ROOM_API}/members/${person.id}/role`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action, role }),
              });
              const data = await response.json().catch(() => ({}));
              if (!response.ok) {
                showAppToast(data.error || "No se pudo cambiar el rol");
                return;
              }
              person.role = data.role;
              person.role_label = data.role_label;
              renderOnlineUsers(online);
            });
            choices.appendChild(choice);
          });
          panel.append(directionButton, choices);
        });
      }

      row.append(manage, panel);
    }
    onlineUsers.appendChild(row);
  });
}

function applyUpdateMetadata(data) {
  myMemberId = data.member_id || myMemberId;
  window.currentChatMemberId = myMemberId;
  applyRoleUI(data.member_role || myRole);
  roomParticipants = data.participants || [];
  const myProfile = roomParticipants.find((participant) => participant.id === myMemberId);
  if (myProfile) {
    if (myProfile.name !== myName) setCurrentName(myProfile.name);
    roomConfig.member = { ...roomConfig.member, ...myProfile };
    window.setChatAvatar?.(myProfileAvatar, myProfile);
  }
  roomParticipants.forEach((participant) => window.syncChatProfile?.(participant));
  renderJoinRequests(data.join_requests);
  renderExpulsionRequests(data.expulsion_requests);
  const pendingExpulsionTargets = new Set(data.pending_expulsion_target_ids || []);
  renderOnlineUsers(
    (data.online || []).map((person) => ({
      ...person,
      kick_pending: pendingExpulsionTargets.has(person.id),
    }))
  );
  renderPinnedMessage(data.pinned_message);
}

document.addEventListener("chat:profile-updated", (event) => {
  const profile = event.detail?.profile;
  if (!profile || profile.id !== myMemberId) return;
  setCurrentName(profile.name);
  roomConfig.member = { ...roomConfig.member, ...profile };
  roomParticipants = roomParticipants.map((participant) => (
    participant.id === profile.id ? { ...participant, ...profile } : participant
  ));
  window.setChatAvatar?.(myProfileAvatar, profile);
});

pinnedBtn.addEventListener("click", () => {
  window.closeMediaGallery?.();
  pinnedPanel.hidden = !pinnedPanel.hidden;
});

joinRequestsBtn.addEventListener("click", () => {
  window.closeMediaGallery?.();
  joinRequestsPanel.hidden = !joinRequestsPanel.hidden;
});

directRequestsBtn.addEventListener("click", () => {
  window.closeMediaGallery?.();
  directRequestsPanel.hidden = !directRequestsPanel.hidden;
});

jumpPinnedBtn.addEventListener("click", () => {
  if (pinnedMessageId) jumpToMessage(pinnedMessageId);
  pinnedPanel.hidden = true;
});

unpinBtn.addEventListener("click", async () => {
  await fetch(`${ROOM_API}/pin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message_id: null }),
  });
  pinnedPanel.hidden = true;
});

// ---------------------------------------------------------------------
// Responder a un mensaje
// ---------------------------------------------------------------------

function setReply(msg) {
  replyingTo = { id: msg.id, name: msg.name, text: msg.text, type: msg.type };
  replyBarName.textContent = msg.name;
  replyBarText.textContent = previewFor(msg);
  replyBar.classList.add("show");
  input.focus();
}

function clearReply() {
  replyingTo = null;
  replyBar.classList.remove("show");
}

replyBarCancel.addEventListener("click", clearReply);

// ---------------------------------------------------------------------
// Enviar mensajes (texto o archivo)
// ---------------------------------------------------------------------

function newClientMessageId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
}

function waitBeforeRetry(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function sendMessage({ type = "text", text = "", file_url = null, file_name = null }) {
  const payload = {
    name: myName,
    text,
    type,
    file_url,
    file_name,
    reply_to_id: replyingTo ? replyingTo.id : null,
    client_message_id: newClientMessageId(),
  };
  const retryDelays = [0, 250, 700];
  let lastError = new Error("No se pudo enviar el mensaje");

  for (const retryDelay of retryDelays) {
    if (retryDelay) await waitBeforeRetry(retryDelay);
    let res;
    try {
      res = await fetch(`${ROOM_API}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (_networkError) {
      lastError = new Error("La conexión se interrumpió mientras se enviaba el mensaje.");
      continue;
    }

    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      clearReply();
      if (payload.type !== "text") {
        document.dispatchEvent(new CustomEvent("chat:media-changed"));
      }
      return data;
    }
    lastError = new Error(data.error || "No se pudo enviar el mensaje");
    if (res.status !== 503 && !data.retryable) {
      throw lastError;
    }
  }
  throw lastError;
}

let sendingTextMessage = false;

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (sendingTextMessage) return;
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  stopTypingNow();
  sendingTextMessage = true;
  sendBtn.disabled = true;
  form.setAttribute("aria-busy", "true");
  try {
    await sendMessage({ type: "text", text });
  } catch (error) {
    input.value = input.value.trim()
      ? `${text} ${input.value}`
      : text;
    showAppToast(
      `${error.message} Tu texto sigue en la caja para que puedas intentarlo otra vez.`
    );
    input.focus();
  } finally {
    sendingTextMessage = false;
    sendBtn.disabled = false;
    form.removeAttribute("aria-busy");
  }
});

// ---------------------------------------------------------------------
// Adjuntar archivos (imagen / audio / video)
// ---------------------------------------------------------------------

attachBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  fileInput.value = "";
  if (!file) return;
  pendingFile = await compressImage(file);
  const url = URL.createObjectURL(pendingFile);
  if (pendingFile.type.startsWith("image/")) {
    filePreviewContent.innerHTML = `<img class="msg-media" src="${url}" alt="">`;
  } else if (pendingFile.type.startsWith("video/")) {
    filePreviewContent.innerHTML = `<video class="msg-media" src="${url}" controls></video>`;
  } else if (pendingFile.type.startsWith("audio/")) {
    filePreviewContent.innerHTML = `<audio class="msg-audio" src="${url}" controls></audio>`;
  } else {
    filePreviewContent.textContent = `📎 ${pendingFile.name}`;
  }
  filePreview.classList.add("show");
});
fileDiscardBtn.addEventListener("click", () => { pendingFile = null; filePreview.classList.remove("show"); filePreviewContent.innerHTML = ""; });
fileSendBtn.addEventListener("click", async () => { if (!pendingFile) return; const file = pendingFile; fileDiscardBtn.click(); await uploadAndSend(file); });

async function uploadAndSend(file, kindHint) {
  setUploadStatus(`Subiendo ${file.name}...`);
  try {
    const formData = new FormData();
    formData.append("file", file);
    if (kindHint) formData.append("kind", kindHint);

    const res = await fetch(`${ROOM_API}/upload`, { method: "POST", body: formData });
    if (res.status === 401) {
      lockRoom();
      throw new Error("Tu acceso venció. Vuelve a desbloquear la sala.");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Error al subir el archivo");
    }
    const data = await res.json();

    await sendMessage({ type: data.type, file_url: data.url, file_name: data.filename, text: "" });
  } catch (e) {
    alert("No se pudo enviar el archivo: " + e.message);
  } finally {
    setUploadStatus("");
  }
}

async function compressImage(file) {
  if (!file.type.startsWith("image/") || file.size < 900000) return file;
  const url = URL.createObjectURL(file);
  const image = new Image(); image.src = url;
  await image.decode();
  const scale = Math.min(1, 1600 / image.width);
  const canvas = document.createElement("canvas"); canvas.width = image.width * scale; canvas.height = image.height * scale;
  canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  URL.revokeObjectURL(url);
  return blob ? new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), {type:"image/jpeg"}) : file;
}

function setUploadStatus(text) {
  uploadStatus.textContent = text;
  uploadStatus.classList.toggle("show", !!text);
}

// ---------------------------------------------------------------------
// Grabar nota de voz
// ---------------------------------------------------------------------

let mediaRecorder = null;
let recordedChunks = [];
let recordTimer = null;
let recordSeconds = 0;
let recordLimitTimer = null;
let discardRecording = false;
let pendingVoiceFile = null;
let pendingVoiceUrl = null;
const MAX_RECORD_SECONDS = 5 * 60;

function clearVoicePreview() {
  pendingVoiceFile = null;
  voicePreviewAudio.removeAttribute("src");
  voicePreviewAudio.load();
  voicePreview.classList.remove("show");
  if (pendingVoiceUrl) URL.revokeObjectURL(pendingVoiceUrl);
  pendingVoiceUrl = null;
}

function showVoicePreview(file) {
  clearVoicePreview();
  pendingVoiceFile = file;
  pendingVoiceUrl = URL.createObjectURL(file);
  voicePreviewAudio.src = pendingVoiceUrl;
  voicePreview.classList.add("show");
}

voiceDiscardBtn.addEventListener("click", clearVoicePreview);
voiceSendBtn.addEventListener("click", async () => {
  if (!pendingVoiceFile) return;
  const file = pendingVoiceFile;
  voiceSendBtn.disabled = true;
  try {
    await uploadAndSend(file, "audio");
    clearVoicePreview();
  } finally {
    voiceSendBtn.disabled = false;
  }
});

micBtn.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("Este navegador no permite grabar audio (o el sitio no está en HTTPS).");
    return;
  }
  try {
    clearVoicePreview();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedChunks = [];
    discardRecording = false;
    mediaRecorder = new MediaRecorder(stream);

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) recordedChunks.push(e.data);
    };

    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      clearInterval(recordTimer);
      clearTimeout(recordLimitTimer);
      micBtn.classList.remove("recording");
      recordStatus.textContent = "";
      cancelRecordBtn.hidden = true;
      const blob = new Blob(recordedChunks, { type: "audio/webm" });
      if (!discardRecording && blob.size > 0) {
        const file = new File([blob], `nota_de_voz_${Date.now()}.webm`, { type: "audio/webm" });
        showVoicePreview(file);
      }
      discardRecording = false;
    };

    mediaRecorder.start();
    micBtn.classList.add("recording");
    cancelRecordBtn.hidden = false;
    recordSeconds = 0;
    recordStatus.textContent = "0:00";
    recordTimer = setInterval(() => {
      recordSeconds++;
      const m = Math.floor(recordSeconds / 60);
      const s = String(recordSeconds % 60).padStart(2, "0");
      recordStatus.textContent = `${m}:${s}`;
    }, 1000);
    recordLimitTimer = setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        alert("La grabación llegó al límite de 5 minutos y se detuvo.");
        mediaRecorder.stop();
      }
    }, MAX_RECORD_SECONDS * 1000);
  } catch (e) {
    alert("No se pudo acceder al micrófono: " + e.message);
  }
});

cancelRecordBtn.addEventListener("click", () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    discardRecording = true;
    mediaRecorder.stop();
  }
});

// ---------------------------------------------------------------------
// Indicador de "escribiendo..."
// ---------------------------------------------------------------------

let typingActive = false;
let typingStopTimer = null;

async function setTypingState(isTyping) {
  try {
    await fetch(`${ROOM_API}/typing`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: myName, is_typing: isTyping }),
    });
  } catch (e) {
    /* si falla no pasa nada grave, solo no se ve el indicador */
  }
}

function stopTypingNow() {
  clearTimeout(typingStopTimer);
  if (typingActive) {
    typingActive = false;
    setTypingState(false);
  }
}

function updateMentionMenu() {
  const caret = input.selectionStart == null ? input.value.length : input.selectionStart;
  const beforeCaret = input.value.slice(0, caret);
  const match = beforeCaret.match(/(^|\s)@([^@\s]*)$/);
  if (!match) {
    mentionMenu.hidden = true;
    return;
  }
  const query = (match[2] || "").toLowerCase();
  const matches = roomParticipants
    .filter((participant) => participant.name !== myName)
    .filter((participant) => participant.name.toLowerCase().includes(query))
    .slice(0, 8);
  mentionMenu.replaceChildren();
  if (!matches.length) {
    mentionMenu.hidden = true;
    return;
  }
  matches.forEach((participant) => {
    const button = document.createElement("button");
    button.type = "button";
    const mentionName = document.createElement("span");
    mentionName.textContent = `@${participant.name}`;
    const mentionRole = document.createElement("span");
    mentionRole.className = `role-tag role-${participant.role}`;
    mentionRole.textContent = participant.role_label || roleLabel(participant.role);
    button.append(mentionName, mentionRole);
    button.addEventListener("click", () => {
      const mentionStart = caret - match[2].length - 1;
      input.value = `${input.value.slice(0, mentionStart)}@${participant.name} ${input.value.slice(caret)}`;
      mentionMenu.hidden = true;
      input.focus();
      const nextCaret = mentionStart + participant.name.length + 2;
      input.setSelectionRange(nextCaret, nextCaret);
    });
    mentionMenu.appendChild(button);
  });
  mentionMenu.hidden = false;
}

input.addEventListener("input", () => {
  updateMentionMenu();
  if (!typingActive) {
    typingActive = true;
    setTypingState(true);
  }
  clearTimeout(typingStopTimer);
  typingStopTimer = setTimeout(() => {
    typingActive = false;
    setTypingState(false);
  }, 1800);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Escape") mentionMenu.hidden = true;
});

window.addEventListener("beforeunload", () => {
  if (navigator.sendBeacon) {
    navigator.sendBeacon(
      `${ROOM_API}/typing`,
      new Blob([JSON.stringify({ name: myName, is_typing: false })], { type: "application/json" })
    );
  }
});

function renderTyping(names) {
  if (!names || !names.length) {
    typingIndicator.classList.remove("show");
    typingIndicator.innerHTML = "";
    return;
  }
  let text;
  if (names.length === 1) text = `${names[0]} está escribiendo`;
  else if (names.length === 2) text = `${names[0]} y ${names[1]} están escribiendo`;
  else text = `${names[0]}, ${names[1]} y ${names.length - 2} más están escribiendo`;

  typingIndicator.innerHTML = `<span>${escapeHtml(text)}</span><span class="dots"><i></i><i></i><i></i></span>`;
  typingIndicator.classList.add("show");
}

// ---------------------------------------------------------------------
// Polling: trae mensajes nuevos + quién está escribiendo, cada segundo
// ---------------------------------------------------------------------

let pollTimer = null;

function lastSeenKey(slug) {
  return `chat_last_seen_${slug}`;
}

function markCurrentRoomSeen() {
  if (lastId > 0) localStorage.setItem(lastSeenKey(roomSlug), String(lastId));
  unreadByRoom[roomSlug] = 0;
  renderRoomRail();
}

async function pollUnreadCounts() {
  try {
    const rooms = normalizedKnownRooms().map((room) => ({
      slug: room.slug,
      seen: room.slug === roomSlug
        ? lastId
        : Number(localStorage.getItem(lastSeenKey(room.slug)) || 0),
    }));
    const response = await fetch("/api/rooms/unread", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rooms }),
    });
    if (response.ok) {
      const data = await response.json();
      Object.entries(data.rooms || {}).forEach(([slug, state]) => {
        unreadByRoom[slug] = slug === roomSlug ? 0 : state.count;
      });
      renderRoomRail();
    }
  } catch (_error) {
    // Los contadores se recuperan solos en el siguiente ciclo.
  } finally {
    await pollDirectState();
    if (chatStarted) unreadPollTimer = setTimeout(pollUnreadCounts, 2500);
  }
}

async function pollUpdates() {
  try {
    const res = await fetch(`${ROOM_API}/updates?since=${lastId}&me=${encodeURIComponent(myName)}`);
    if (res.status === 401) {
      lockRoom();
      return;
    }
    if (res.status === 403) {
      const denied = await res.json().catch(() => ({}));
      if (denied.code === "member_kicked") return leaveRoomWithNotice("kicked");
      if (denied.code === "approval_rejected") return leaveRoomWithNotice("rejected");
      return;
    }
    const data = await res.json();

    if (chatVersion !== null && data.version !== chatVersion) {
      const refresh = await fetch(`${ROOM_API}/updates?since=0&me=${encodeURIComponent(myName)}`);
      if (refresh.status === 401) {
        lockRoom();
        return;
      }
      if (refresh.status === 403) {
        const denied = await refresh.json().catch(() => ({}));
        if (denied.code === "member_kicked") return leaveRoomWithNotice("kicked");
        if (denied.code === "approval_rejected") return leaveRoomWithNotice("rejected");
        return;
      }
      const snapshot = await refresh.json();
      applyUpdateMetadata(snapshot);
      const keepBottom = isNearBottom();
      chatBox.innerHTML = "";
      lastId = 0;
      snapshot.messages.forEach((message) => {
        renderMessage(message);
        lastId = Math.max(lastId, message.id);
      });
      if (keepBottom) chatBox.scrollTop = chatBox.scrollHeight;
      chatVersion = snapshot.version;
      markCurrentRoomSeen();
      return;
    }
    chatVersion = data.version;
    applyUpdateMetadata(data);

    if (data.messages && data.messages.length) {
      const shouldStick = isNearBottom();
      data.messages.forEach((m) => {
        renderMessage(m);
        if (m.name !== myName && document.hidden) { unreadCount++; document.title = `(${unreadCount}) ${normalTitle}`; }
        if (m.name !== myName && lastId) playNotification();
        lastId = Math.max(lastId, m.id);
      });
      if (shouldStick) chatBox.scrollTop = chatBox.scrollHeight;
      markCurrentRoomSeen();
    }

    renderTyping(data.typing);
    offlineBanner.classList.remove("show");
  } catch (e) {
    offlineBanner.classList.add("show");
    console.error("Error de actualización:", e);
  } finally {
    if (!accessLocked) pollTimer = setTimeout(pollUpdates, 500);
  }
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) { unreadCount = 0; document.title = normalTitle; } });

// ---------------------------------------------------------------------
// Arranque
// ---------------------------------------------------------------------

function lockRoom(config = roomConfig) {
  accessLocked = true;
  chatStarted = false;
  clearTimeout(pollTimer);
  clearTimeout(unreadPollTimer);
  document.body.classList.remove("room-ready");
  accessGate.hidden = false;
  if (config && config.access_type === "code") {
    accessLabel.textContent = "Código de acceso";
    accessHelp.textContent = "Escribe el código de 6 dígitos para entrar.";
    accessSecret.type = "text";
    accessSecret.inputMode = "numeric";
    accessSecret.maxLength = 6;
    accessSecret.pattern = "\\d{6}";
  } else {
    accessLabel.textContent = "Contraseña";
    accessHelp.textContent = "Introduce la contraseña para entrar.";
    accessSecret.type = "password";
    accessSecret.removeAttribute("inputmode");
    accessSecret.maxLength = 128;
    accessSecret.removeAttribute("pattern");
  }
  setTimeout(() => accessSecret.focus(), 0);
}

async function enterRoom() {
  accessGate.hidden = true;
  const configResponse = await fetch(`${ROOM_API}/config`, { cache: "no-store" });
  roomConfig = await configResponse.json();
  if (!configResponse.ok) throw new Error(roomConfig.error || "No se pudo abrir la sala");
  await prepareMembership();
}

accessForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  accessError.textContent = "";
  accessSubmit.disabled = true;
  accessSubmit.textContent = "Comprobando…";
  try {
    const response = await fetch(`${ROOM_API}/access`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        secret: accessSecret.value,
        remember: rememberDevice.checked,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "No se pudo comprobar el acceso");
    accessSecret.value = "";
    await enterRoom();
  } catch (error) {
    accessError.textContent = error.message;
    accessSecret.select();
  } finally {
    accessSubmit.disabled = false;
    accessSubmit.textContent = "Entrar a la sala";
  }
});

async function boot() {
  try {
    const response = await fetch(`${ROOM_API}/config`, { cache: "no-store" });
    roomConfig = await response.json();
    if (!response.ok) throw new Error(roomConfig.error || "No se pudo abrir la sala");
    if (roomConfig.requires_access) {
      lockRoom(roomConfig);
      return;
    }
    await prepareMembership();
  } catch (error) {
    lockRoom(roomConfig);
    accessError.textContent = error.message;
    accessSecret.disabled = true;
    accessSubmit.disabled = true;
  }
}
boot();
