const chatId = Number(document.body.dataset.chatId);
const originRoomSlug = document.body.dataset.roomSlug;
const originRoomName = document.body.dataset.roomName;
const DIRECT_API = `/api/direct-chats/${chatId}`;
const KNOWN_ROOMS_KEY = "chat_known_rooms";

const chatBox = document.getElementById("direct-chat-box");
const form = document.getElementById("direct-form");
const input = document.getElementById("direct-input");
const sendButton = form.querySelector(".send-btn");
const roomRailList = document.getElementById("room-rail-list");
const directRailList = document.getElementById("direct-rail-list");
const directPersonName = document.getElementById("direct-person-name");
const directPersonRole = document.getElementById("direct-person-role");
const directPersonAvatar = document.getElementById("direct-person-avatar");
const directPersonProfileBtn = document.getElementById("direct-person-profile-btn");
const myNameLabel = document.getElementById("my-name-label");
const myRoleTag = document.getElementById("my-role-tag");
const myProfileBtn = document.getElementById("my-profile-btn");
const myProfileAvatar = document.getElementById("my-profile-avatar");
const directPinnedBtn = document.getElementById("direct-pinned-btn");
const directPinnedPanel = document.getElementById("direct-pinned-panel");
const directPinnedPreview = document.getElementById("direct-pinned-preview");
const directStarredList = document.getElementById("direct-starred-list");
const deleteConfirmDialog = document.getElementById("direct-delete-confirm-dialog");
const deleteConfirmButton = document.getElementById("direct-delete-confirm");
const deleteCancelButton = document.getElementById("direct-delete-cancel");
const directRequestsBtn = document.getElementById("direct-requests-btn");
const directRequestCount = document.getElementById("direct-request-count");
const directRequestsPanel = document.getElementById("direct-requests-panel");
const directRequestsList = document.getElementById("direct-requests-list");
const settingsBtn = document.getElementById("settings-btn");
const settingsPanel = document.getElementById("settings-panel");
const darkModeToggle = document.getElementById("dark-mode-toggle");
const soundToggle = document.getElementById("sound-toggle");
const offlineBanner = document.getElementById("offline-banner");
const appToast = document.getElementById("app-toast");
const appToastText = document.getElementById("app-toast-text");
const appToastClose = document.getElementById("app-toast-close");
const attachButton = document.getElementById("direct-attach-btn");
const fileInput = document.getElementById("direct-file-input");
const filePreview = document.getElementById("file-preview");
const filePreviewContent = document.getElementById("file-preview-content");
const fileDiscardButton = document.getElementById("file-discard-btn");
const fileSendButton = document.getElementById("file-send-btn");
const uploadStatus = document.getElementById("upload-status");
const micButton = document.getElementById("direct-mic-btn");
const recordStatus = document.getElementById("direct-record-status");
const cancelRecordButton = document.getElementById("direct-cancel-record-btn");
const voicePreview = document.getElementById("voice-preview");
const voicePreviewAudio = document.getElementById("voice-preview-audio");
const voiceDiscardButton = document.getElementById("voice-discard-btn");
const voiceSendButton = document.getElementById("voice-send-btn");
const directReplyBar = document.getElementById("direct-reply-bar");
const directReplyName = document.getElementById("direct-reply-name");
const directReplyText = document.getElementById("direct-reply-text");
const directReplyCancel = document.getElementById("direct-reply-cancel");

const ROLE_LABELS = {
  guest: "Invitado",
  participant: "Participante",
  moderator: "Moderador",
  admin: "Admin",
};

let me = null;
let other = null;
let lastId = 0;
let pollTimer = null;
let stateTimer = null;
let pendingFile = null;
let requestSignature = "";
let firstSnapshot = true;
let serverVersion = -1;
let pinnedMessageId = null;
let currentMessages = new Map();
let deleteConfirmationResolver = null;
let pollRunning = false;
let replyingTo = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function roleLabel(role) {
  return ROLE_LABELS[role] || ROLE_LABELS.participant;
}

function initials(name) {
  return String(name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0))
    .join("")
    .toUpperCase() || "?";
}

function bubbleColor(seed) {
  let hash = 0;
  for (const character of String(seed)) {
    hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  }
  return `hsl(${Math.abs(hash) % 360} 65% 55%)`;
}

function readKnownRooms() {
  try {
    const rooms = JSON.parse(localStorage.getItem(KNOWN_ROOMS_KEY) || "[]");
    return Array.isArray(rooms) ? rooms.filter((room) => room?.slug && room?.name) : [];
  } catch (_error) {
    return [];
  }
}

function knownRooms() {
  const bySlug = new Map();
  bySlug.set("general", { slug: "general", name: "Sala general" });
  readKnownRooms().forEach((room) => bySlug.set(room.slug, room));
  bySlug.set(originRoomSlug, { slug: originRoomSlug, name: originRoomName });
  return [...bySlug.values()].slice(0, 20);
}

function renderRoomRail() {
  const fragment = document.createDocumentFragment();
  knownRooms().forEach((room) => {
    const link = document.createElement("a");
    link.className = "room-bubble room-entry";
    link.href = `/room/${encodeURIComponent(room.slug)}`;
    link.title = room.name;
    link.setAttribute("aria-label", `Cambiar a ${room.name}`);
    link.style.setProperty("--room-color", bubbleColor(room.slug));
    link.textContent = initials(room.name);
    fragment.appendChild(link);
  });
  roomRailList.replaceChildren(fragment);
}

function renderDirectRail(chats) {
  const items = Array.isArray(chats) ? chats : [];
  const fragment = document.createDocumentFragment();
  items.forEach((chat) => {
    const link = document.createElement("a");
    link.className = "room-bubble room-entry direct-entry";
    link.href = chat.url;
    link.title = `${chat.other_name} · Chat privado`;
    link.setAttribute("aria-label", `Chat privado con ${chat.other_name}`);
    link.style.setProperty("--room-color", bubbleColor(`direct-${chat.id}`));
    if (chat.other_photo_url) {
      link.classList.add("has-photo");
      link.style.backgroundImage = `url("${String(chat.other_photo_url).replaceAll('"', "%22")}")`;
    } else {
      link.textContent = initials(chat.other_name);
    }
    if (chat.id === chatId) {
      link.classList.add("active");
      link.setAttribute("aria-current", "page");
    }
    if (chat.unread_count > 0 && chat.id !== chatId) {
      const badge = document.createElement("span");
      badge.className = "room-unread-badge";
      badge.textContent = chat.unread_count > 99 ? "99+" : String(chat.unread_count);
      link.appendChild(badge);
    }
    fragment.appendChild(link);
  });
  directRailList.replaceChildren(fragment);
  directRailList.closest(".rail-direct-section")?.classList.toggle("empty", !items.length);
}

function showToast(message) {
  appToastText.textContent = message;
  appToast.hidden = false;
}

function renderRequests(requests) {
  const pending = Array.isArray(requests) ? requests : [];
  const signature = JSON.stringify(pending.map((item) => [
    item.id,
    item.requester_name,
    item.requester_role,
    item.room_name,
  ]));
  directRequestsBtn.hidden = pending.length === 0;
  directRequestCount.textContent = pending.length > 9 ? "9+" : String(pending.length || "");
  if (!pending.length) directRequestsPanel.hidden = true;
  if (signature === requestSignature) return;
  requestSignature = signature;
  directRequestsList.replaceChildren();
  pending.forEach((item) => {
    const row = document.createElement("article");
    row.className = "join-request-row direct-request-row";
    const summary = document.createElement("div");
    summary.className = "request-summary";
    summary.innerHTML = `
      <strong>${escapeHtml(item.requester_name)}</strong>
      <span class="role-tag role-${item.requester_role}">${escapeHtml(item.requester_role_label)}</span>
      <small>Quiere iniciar un chat privado desde ${escapeHtml(item.room_name)}.</small>
    `;
    const actions = document.createElement("div");
    const accept = document.createElement("button");
    const reject = document.createElement("button");
    accept.type = reject.type = "button";
    accept.textContent = "Aceptar";
    reject.textContent = "Rechazar";
    async function decide(action) {
      accept.disabled = reject.disabled = true;
      const response = await fetch(`/api/direct-chat-requests/${item.id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        showToast(data.error || "No se pudo guardar tu decisión");
        accept.disabled = reject.disabled = false;
        return;
      }
      if (action === "accept") {
        window.location.assign(data.url);
        return;
      }
      showToast("Solicitud de chat privado rechazada.");
      await pollState();
    }
    accept.addEventListener("click", () => decide("accept"));
    reject.addEventListener("click", () => decide("reject"));
    actions.append(accept, reject);
    row.append(summary, actions);
    directRequestsList.appendChild(row);
  });
}

async function pollState() {
  try {
    const response = await fetch("/api/direct-chats");
    if (!response.ok) return;
    const data = await response.json();
    renderDirectRail(data.chats);
    renderRequests(data.requests);
  } catch (_error) {
    // Se recupera en la siguiente sincronización.
  } finally {
    clearTimeout(stateTimer);
    stateTimer = setTimeout(pollState, 2500);
  }
}

function applyMemberUI() {
  window.currentChatMemberId = me.id;
  directPersonName.textContent = other.name;
  directPersonRole.textContent = roleLabel(other.role);
  directPersonRole.className = `role-tag role-${other.role}`;
  myNameLabel.textContent = me.name;
  myRoleTag.textContent = roleLabel(me.role);
  myRoleTag.className = `role-tag role-${me.role}`;
  window.setChatAvatar?.(directPersonAvatar, other);
  window.setChatAvatar?.(myProfileAvatar, me);
  window.syncChatProfile?.(me);
  window.syncChatProfile?.(other);
  document.title = `${other.name} · Chat privado`;
  input.placeholder = `Mensaje privado para ${other.name}…`;
}

function formatTime(iso) {
  const value = /(?:Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : `${iso}Z`;
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function isNearBottom() {
  return chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < 100;
}

function mediaHtml(message) {
  const safeUrl = escapeHtml(message.file_url || "");
  const safeName = escapeHtml(message.file_name || "Archivo");
  if (message.type === "image") {
    return `<a href="${safeUrl}" target="_blank" rel="noopener"><img class="msg-media" src="${safeUrl}" alt="${safeName}"></a>`;
  }
  if (message.type === "video") {
    return `<video class="msg-media" src="${safeUrl}" controls></video>`;
  }
  if (message.type === "audio") {
    return `<audio class="msg-audio" src="${safeUrl}" controls></audio>`;
  }
  if (message.type === "file") {
    return `<a class="msg-file" href="${safeUrl}" download="${safeName}">📎 Descargar: ${safeName}</a>`;
  }
  return "";
}

function directMessagePreview(message) {
  if (!message) return "Mensaje";
  if (message.type === "text") return message.text || "Mensaje";
  return {
    image: "📷 Imagen",
    video: "🎬 Video",
    audio: "🎤 Nota de voz",
    file: `📎 ${message.file_name || "Archivo"}`,
  }[message.type] || "Mensaje";
}

function setDirectReply(message) {
  replyingTo = {
    id: message.id,
    name: message.author_name,
    text: directMessagePreview(message),
  };
  directReplyName.textContent = replyingTo.name;
  directReplyText.textContent = replyingTo.text;
  directReplyBar.classList.add("show");
  input.focus();
}

function clearDirectReply() {
  replyingTo = null;
  directReplyBar.classList.remove("show");
  directReplyName.textContent = "";
  directReplyText.textContent = "";
}

function askDeleteForEveryone() {
  if (deleteConfirmationResolver) deleteConfirmationResolver(false);
  deleteConfirmDialog.hidden = false;
  deleteConfirmButton.focus();
  return new Promise((resolve) => {
    deleteConfirmationResolver = resolve;
  });
}

function resolveDeleteConfirmation(result) {
  deleteConfirmDialog.hidden = true;
  if (deleteConfirmationResolver) {
    deleteConfirmationResolver(result);
    deleteConfirmationResolver = null;
  }
}

async function mutateMessage(path, options = {}) {
  const response = await fetch(`${DIRECT_API}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "No se pudo actualizar el mensaje");
  await window.refreshDirectSnapshot();
  return data;
}

function openDirectProfileMenu(event, memberId) {
  event.preventDefault();
  event.stopPropagation();
  document.querySelector(".person-action-menu.direct-profile-menu")?.remove();
  const menu = document.createElement("div");
  menu.className = "person-action-menu direct-profile-menu";
  const profileButton = document.createElement("button");
  profileButton.type = "button";
  profileButton.innerHTML = "<span>👤</span><span>Ver perfil</span>";
  profileButton.addEventListener("click", () => {
    menu.remove();
    window.openChatProfile?.(memberId, memberId === me.id);
  });
  menu.appendChild(profileButton);
  document.body.appendChild(menu);
  const anchor = event.currentTarget.getBoundingClientRect();
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(10, Math.min(anchor.left, window.innerWidth - rect.width - 10))}px`;
  menu.style.top = `${anchor.bottom + 6}px`;
  setTimeout(() => {
    document.addEventListener("click", () => menu.remove(), { once: true });
  }, 0);
}

function groupedReactions(reactions) {
  const grouped = new Map();
  (reactions || []).forEach((reaction) => {
    if (!grouped.has(reaction.emoji)) grouped.set(reaction.emoji, []);
    grouped.get(reaction.emoji).push(reaction.name);
  });
  return [...grouped.entries()].map(([emoji, names]) => (
    `<span class="reaction-badge" title="${escapeHtml(names.join(", "))}">${emoji}${names.length > 1 ? ` ${names.length}` : ""}</span>`
  )).join("");
}

function renderMessage(message) {
  currentMessages.set(message.id, message);
  const mine = message.author_member_id === me.id;
  const wrapper = document.createElement("article");
  wrapper.className = `msg ${mine ? "mine" : "theirs"} direct-message`;
  if (message.id === pinnedMessageId) wrapper.classList.add("pinned");
  if (message.starred) wrapper.classList.add("starred");
  wrapper.dataset.id = message.id;
  wrapper.style.setProperty(
    "--user-color",
    mine ? "#4E7CFF" : bubbleColor(`member-${message.author_member_id}`)
  );

  if (message.type === "deleted") {
    wrapper.classList.add("direct-deleted-message");
    wrapper.innerHTML = `
      <div class="bubble deleted-bubble">
        <span class="deleted-copy">🚫 Este mensaje fue eliminado</span>
        <span class="msg-time">${formatTime(message.created_at)}</span>
        ${mine ? `<span class="delivery-status status-${message.delivery_status || "sent"}" title="${message.delivery_status === "seen" ? "Visto" : message.delivery_status === "delivered" ? "Entregado" : "Enviado"}">${message.delivery_status === "seen" ? "✓✓" : message.delivery_status === "delivered" ? "✓✓" : "✓"}</span>` : ""}
      </div>`;
    chatBox.appendChild(wrapper);
    return;
  }

  const text = message.text ? `<p>${escapeHtml(message.text)}</p>` : "";
  const replyMarkup = message.reply_to_id
    ? `<button type="button" class="reply-preview direct-reply-preview" data-reply-id="${message.reply_to_id}">
         <span class="reply-name">${escapeHtml(message.reply_to_name || "")}</span>
         <span class="reply-snippet">${escapeHtml(message.reply_to_text || "Mensaje")}</span>
       </button>`
    : "";
  const reactionMarkup = groupedReactions(message.reactions);
  const delivery = message.delivery_status || "sent";
  const deliveryTitle = delivery === "seen" ? "Visto" : delivery === "delivered" ? "Entregado" : "Enviado";
  const avatarMarkup = message.author_photo_url
    ? `<span class="profile-avatar message-avatar has-photo" style="background-image:url('${escapeHtml(message.author_photo_url)}')"></span>`
    : `<span class="profile-avatar message-avatar">${escapeHtml(initials(message.author_name))}</span>`;
  wrapper.innerHTML = `
    <div class="bubble">
      <button type="button" class="direct-message-author">
        ${avatarMarkup}
        <span class="msg-name">${escapeHtml(message.author_name)}
          <span class="role-tag role-participant">Participante</span>
        </span>
      </button>
      ${message.starred ? `<span class="message-star" title="Mensaje destacado">★</span>` : ""}
      ${replyMarkup}
      ${mediaHtml(message)}
      ${text}
      <div class="reaction-row">
        <span class="reaction-summary">${reactionMarkup}</span>
        <button type="button" class="reaction-trigger" title="Reaccionar">☺</button>
        <button type="button" class="pin-message-btn" title="${message.id === pinnedMessageId ? "Desfijar" : "Fijar mensaje"}">📌</button>
        <button type="button" class="star-message-btn" title="${message.starred ? "Quitar de destacados" : "Destacar mensaje"}">${message.starred ? "★" : "☆"}</button>
        ${mine && message.type === "text" ? `<button type="button" class="edit-btn" title="Editar">✏️</button>` : ""}
        <button type="button" class="message-delete-btn delete-btn" title="Opciones de borrado">🗑️</button>
        <span class="reaction-picker"><button>👍</button><button>❤️</button><button>😂</button><button>😮</button><button>😢</button><button>🎉</button></span>
      </div>
      <span class="msg-time">${formatTime(message.created_at)}${message.edited_at ? " · editado" : ""}</span>
      ${mine ? `<span class="delivery-status status-${delivery}" title="${deliveryTitle}">${delivery === "sent" ? "✓" : "✓✓"}</span>` : ""}
      <button type="button" class="reply-btn direct-reply-btn" title="Responder">↩</button>
    </div>
  `;

  wrapper.querySelector(".direct-reply-preview")?.addEventListener("click", (event) => {
    event.stopPropagation();
    jumpToDirectMessage(message.reply_to_id);
  });
  wrapper.querySelector(".direct-reply-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    setDirectReply(message);
  });
  wrapper.querySelector(".direct-message-author").addEventListener(
    "click",
    (event) => openDirectProfileMenu(event, message.author_member_id)
  );
  wrapper.querySelector(".reaction-trigger").addEventListener("click", (event) => {
    event.stopPropagation();
    wrapper.querySelector(".reaction-picker").classList.toggle("show");
  });
  wrapper.querySelectorAll(".reaction-picker button").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      try {
        await mutateMessage(`/messages/${message.id}/reactions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ emoji: button.textContent }),
        });
      } catch (error) {
        showToast(error.message);
      }
    });
  });
  wrapper.querySelector(".pin-message-btn").addEventListener("click", async (event) => {
    event.stopPropagation();
    try {
      await mutateMessage("/pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_id: message.id === pinnedMessageId ? null : message.id }),
      });
    } catch (error) {
      showToast(error.message);
    }
  });
  wrapper.querySelector(".star-message-btn").addEventListener("click", async (event) => {
    event.stopPropagation();
    try {
      await mutateMessage(`/messages/${message.id}/star`, { method: "POST" });
    } catch (error) {
      showToast(error.message);
    }
  });
  wrapper.querySelector(".edit-btn")?.addEventListener("click", async (event) => {
    event.stopPropagation();
    const edited = prompt("Editar mensaje", message.text || "");
    if (!edited?.trim() || edited.trim() === message.text) return;
    try {
      await mutateMessage(`/messages/${message.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: edited.trim() }),
      });
    } catch (error) {
      showToast(error.message);
    }
  });
  wrapper.querySelector(".message-delete-btn").addEventListener("click", (event) => {
    event.stopPropagation();
    let menu = wrapper.querySelector(".delete-menu");
    if (menu) {
      menu.classList.toggle("show");
      return;
    }
    menu = document.createElement("span");
    menu.className = "delete-menu show";
    menu.innerHTML = `
      <button type="button" data-scope="me">Borrar para mí</button>
      ${mine ? '<button type="button" data-scope="everyone">Borrar para todos</button>' : ""}
    `;
    wrapper.querySelector(".reaction-row").appendChild(menu);
    menu.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", async (clickEvent) => {
        clickEvent.stopPropagation();
        const scope = button.dataset.scope;
        if (scope === "everyone" && !await askDeleteForEveryone()) return;
        try {
          await mutateMessage(`/messages/${message.id}`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scope }),
          });
        } catch (error) {
          showToast(error.message);
        }
      });
    });
  });
  wrapper.addEventListener("click", () => {
    wrapper.classList.add("actions-open");
    clearTimeout(wrapper.actionsTimer);
    wrapper.actionsTimer = setTimeout(() => wrapper.classList.remove("actions-open"), 12000);
  });
  chatBox.appendChild(wrapper);
}

function playNotification() {
  if (!soundToggle.checked) return;
  const sound = new Audio("data:audio/wav;base64,UklGRjIAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQ4AAAAAgICAgICAgICAgICAgIA=");
  sound.play().catch(() => {});
}

function jumpToDirectMessage(messageId) {
  const target = chatBox.querySelector(`[data-id="${messageId}"]`);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.add("search-hit");
  setTimeout(() => target.classList.remove("search-hit"), 1600);
}

function renderSavedMessages(pinned, starred) {
  pinnedMessageId = pinned?.id || null;
  directPinnedPreview.textContent = pinned
    ? `${pinned.author_name}: ${directMessagePreview(pinned).slice(0, 90)}`
    : "No hay ningún mensaje fijado.";
  directPinnedPreview.disabled = !pinned;
  directPinnedPreview.onclick = pinned ? () => {
    jumpToDirectMessage(pinned.id);
    directPinnedPanel.hidden = true;
  } : null;
  directStarredList.replaceChildren();
  const starredItems = Array.isArray(starred) ? starred : [];
  if (!starredItems.length) {
    const empty = document.createElement("span");
    empty.className = "saved-empty";
    empty.textContent = "Tus mensajes destacados aparecerán aquí.";
    directStarredList.appendChild(empty);
  } else {
    starredItems.forEach((message) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "saved-message-preview starred-preview";
      item.innerHTML = `<span>★</span><b>${escapeHtml(message.author_name)}</b><small>${escapeHtml(directMessagePreview(message).slice(0, 80))}</small>`;
      item.addEventListener("click", () => {
        jumpToDirectMessage(message.id);
        directPinnedPanel.hidden = true;
      });
      directStarredList.appendChild(item);
    });
  }
}

function updateReceiptMarks(receipts) {
  Object.entries(receipts || {}).forEach(([messageId, status]) => {
    const receipt = chatBox.querySelector(`[data-id="${messageId}"] .delivery-status`);
    if (!receipt) return;
    receipt.className = `delivery-status status-${status}`;
    receipt.textContent = status === "sent" ? "✓" : "✓✓";
    receipt.title = status === "seen" ? "Visto" : status === "delivered" ? "Entregado" : "Enviado";
  });
}

async function fetchDirectUpdates(since) {
  const response = await fetch(`${DIRECT_API}/updates?since=${since}`);
  if (response.status === 403) {
    window.location.assign(`/?notice=${encodeURIComponent("direct_unavailable")}`);
    throw new Error("Chat privado no disponible");
  }
  if (!response.ok) throw new Error("No se pudo sincronizar");
  return response.json();
}

async function syncMessages(forceSnapshot = false) {
  const requestedSince = forceSnapshot ? 0 : lastId;
  let data = await fetchDirectUpdates(requestedSince);
  if (!forceSnapshot && serverVersion >= 0 && data.version !== serverVersion) {
    data = await fetchDirectUpdates(0);
    forceSnapshot = true;
  }
  me = data.member;
  other = data.other;
  applyMemberUI();
  const keepBottom = isNearBottom();
  if (forceSnapshot) {
    chatBox.replaceChildren();
    currentMessages.clear();
    lastId = 0;
  }
  renderSavedMessages(data.pinned_message, data.starred_messages);
  for (const message of data.messages || []) {
    renderMessage(message);
    lastId = Math.max(lastId, message.id);
    if (!firstSnapshot && !forceSnapshot && message.author_member_id !== me.id) playNotification();
  }
  updateReceiptMarks(data.receipts);
  serverVersion = data.version;
  if (keepBottom || firstSnapshot) chatBox.scrollTop = chatBox.scrollHeight;
  firstSnapshot = false;
  offlineBanner.classList.remove("show");
  return data;
}

window.refreshDirectSnapshot = async () => {
  try {
    return await syncMessages(true);
  } catch (error) {
    showToast(error.message);
    throw error;
  }
};

async function pollMessages() {
  if (pollRunning) return;
  pollRunning = true;
  try {
    await syncMessages(false);
  } catch (_error) {
    offlineBanner.classList.add("show");
  } finally {
    pollRunning = false;
    clearTimeout(pollTimer);
    pollTimer = setTimeout(pollMessages, 1000);
  }
}

function newClientMessageId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function sendPayload(payload) {
  const stablePayload = {
    ...payload,
    reply_to_id: payload.reply_to_id ?? replyingTo?.id ?? null,
    client_message_id: payload.client_message_id || newClientMessageId(),
  };
  const retryDelays = [0, 250, 700];
  let lastError = new Error("No se pudo enviar el mensaje");
  for (const delay of retryDelays) {
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    let response;
    try {
      response = await fetch(`${DIRECT_API}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(stablePayload),
      });
    } catch (_networkError) {
      lastError = new Error("La conexión se interrumpió mientras se enviaba el mensaje.");
      continue;
    }
    const data = await response.json().catch(() => ({}));
    if (response.ok) {
      clearDirectReply();
      await window.refreshDirectSnapshot();
      if (stablePayload.type !== "text") {
        document.dispatchEvent(new CustomEvent("chat:media-changed"));
      }
      return data;
    }
    lastError = new Error(data.error || "No se pudo enviar el mensaje");
    if (response.status !== 503 && !data.retryable) throw lastError;
  }
  throw lastError;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || sendButton.disabled) return;
  const clientMessageId = newClientMessageId();
  sendButton.disabled = true;
  input.disabled = true;
  try {
    await sendPayload({ type: "text", text, client_message_id: clientMessageId });
    input.value = "";
  } catch (error) {
    showToast(error.message);
  } finally {
    sendButton.disabled = false;
    input.disabled = false;
    input.focus();
  }
});

function discardFile() {
  pendingFile = null;
  fileInput.value = "";
  filePreviewContent.replaceChildren();
  filePreview.classList.remove("show");
}

function previewFile(file) {
  filePreviewContent.replaceChildren();
  const url = URL.createObjectURL(file);
  let preview;
  if (file.type.startsWith("image/")) {
    preview = document.createElement("img");
    preview.src = url;
    preview.alt = file.name;
  } else if (file.type.startsWith("video/")) {
    preview = document.createElement("video");
    preview.src = url;
    preview.controls = true;
  } else if (file.type.startsWith("audio/")) {
    preview = document.createElement("audio");
    preview.src = url;
    preview.controls = true;
  } else {
    preview = document.createElement("span");
    preview.textContent = `📎 ${file.name}`;
  }
  filePreviewContent.appendChild(preview);
  filePreview.classList.add("show");
}

attachButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  pendingFile = fileInput.files?.[0] || null;
  if (pendingFile) previewFile(pendingFile);
});
fileDiscardButton.addEventListener("click", discardFile);
async function uploadAndSendDirect(file, kindHint) {
  uploadStatus.textContent = "Subiendo archivo…";
  uploadStatus.classList.add("show");
  try {
    const body = new FormData();
    body.append("file", file);
    if (kindHint) body.append("kind", kindHint);
    const uploadResponse = await fetch(`${DIRECT_API}/upload`, { method: "POST", body });
    const upload = await uploadResponse.json().catch(() => ({}));
    if (!uploadResponse.ok) throw new Error(upload.error || "No se pudo subir el archivo");
    await sendPayload({
      type: upload.type,
      file_url: upload.url,
      file_name: upload.filename,
    });
    uploadStatus.textContent = "Archivo enviado";
  } catch (error) {
    uploadStatus.textContent = "";
    uploadStatus.classList.remove("show");
    showToast(error.message);
    throw error;
  } finally {
    setTimeout(() => uploadStatus.classList.remove("show"), 1600);
  }
}

fileSendButton.addEventListener("click", async () => {
  if (!pendingFile || fileSendButton.disabled) return;
  fileSendButton.disabled = true;
  const file = pendingFile;
  try {
    await uploadAndSendDirect(file);
    discardFile();
  } catch (_error) {
    // El archivo permanece en la vista previa para volver a intentarlo.
  } finally {
    fileSendButton.disabled = false;
  }
});

let mediaRecorder = null;
let voiceStream = null;
let recordedChunks = [];
let recordTimer = null;
let recordLimitTimer = null;
let recordSeconds = 0;
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

function resetRecordingUI() {
  clearInterval(recordTimer);
  clearTimeout(recordLimitTimer);
  micButton.classList.remove("recording");
  recordStatus.textContent = "";
  cancelRecordButton.hidden = true;
}

voiceDiscardButton.addEventListener("click", clearVoicePreview);
voiceSendButton.addEventListener("click", async () => {
  if (!pendingVoiceFile || voiceSendButton.disabled) return;
  voiceSendButton.disabled = true;
  const file = pendingVoiceFile;
  try {
    await uploadAndSendDirect(file, "audio");
    clearVoicePreview();
  } catch (_error) {
    // La grabación sigue disponible para reintentar.
  } finally {
    voiceSendButton.disabled = false;
  }
});

micButton.addEventListener("click", async () => {
  if (mediaRecorder?.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    showToast("Este navegador no permite grabar audio o el sitio no está usando HTTPS.");
    return;
  }
  try {
    clearVoicePreview();
    voiceStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedChunks = [];
    discardRecording = false;
    mediaRecorder = new MediaRecorder(voiceStream);
    mediaRecorder.ondataavailable = (event) => {
      if (event.data?.size) recordedChunks.push(event.data);
    };
    mediaRecorder.onstop = () => {
      voiceStream?.getTracks().forEach((track) => track.stop());
      voiceStream = null;
      resetRecordingUI();
      const mimeType = mediaRecorder.mimeType || "audio/webm";
      const blob = new Blob(recordedChunks, { type: mimeType });
      if (!discardRecording && blob.size > 0) {
        const extension = mimeType.includes("ogg") ? "ogg" : "webm";
        showVoicePreview(
          new File(
            [blob],
            `nota_de_voz_${Date.now()}.${extension}`,
            { type: mimeType }
          )
        );
      }
      discardRecording = false;
    };
    mediaRecorder.start();
    micButton.classList.add("recording");
    cancelRecordButton.hidden = false;
    recordSeconds = 0;
    recordStatus.textContent = "0:00";
    recordTimer = setInterval(() => {
      recordSeconds += 1;
      const minutes = Math.floor(recordSeconds / 60);
      const seconds = String(recordSeconds % 60).padStart(2, "0");
      recordStatus.textContent = `${minutes}:${seconds}`;
    }, 1000);
    recordLimitTimer = setTimeout(() => {
      if (mediaRecorder?.state === "recording") {
        showToast("La grabación llegó al límite de 5 minutos y se detuvo.");
        mediaRecorder.stop();
      }
    }, MAX_RECORD_SECONDS * 1000);
  } catch (error) {
    voiceStream?.getTracks().forEach((track) => track.stop());
    voiceStream = null;
    resetRecordingUI();
    showToast(`No se pudo acceder al micrófono: ${error.message}`);
  }
});

cancelRecordButton.addEventListener("click", () => {
  if (mediaRecorder?.state === "recording") {
    discardRecording = true;
    mediaRecorder.stop();
  }
});

function applyTheme(dark) {
  document.body.classList.toggle("dark-mode", dark);
  darkModeToggle.checked = dark;
  localStorage.setItem("chat_dark_mode", dark ? "1" : "0");
}

appToastClose.addEventListener("click", () => { appToast.hidden = true; });
directReplyCancel.addEventListener("click", clearDirectReply);
deleteCancelButton.addEventListener("click", () => resolveDeleteConfirmation(false));
deleteConfirmButton.addEventListener("click", () => resolveDeleteConfirmation(true));
deleteConfirmDialog.addEventListener("click", (event) => {
  if (event.target === deleteConfirmDialog) resolveDeleteConfirmation(false);
});
directPinnedBtn.addEventListener("click", () => {
  window.closeMediaGallery?.();
  directPinnedPanel.hidden = !directPinnedPanel.hidden;
});
directPersonProfileBtn.addEventListener("click", (event) => {
  openDirectProfileMenu(event, other.id);
});
myProfileBtn.addEventListener("click", () => {
  window.openChatProfile?.(me.id, true);
});
document.addEventListener("chat:profile-updated", (event) => {
  if (!event.detail?.profile || event.detail.profile.id !== me?.id) return;
  me = { ...me, ...event.detail.profile, role: "participant", role_label: "Participante" };
  applyMemberUI();
  window.refreshDirectSnapshot?.().catch(() => {});
});
settingsBtn.addEventListener("click", () => {
  window.closeMediaGallery?.();
  directPinnedPanel.hidden = true;
  settingsPanel.classList.toggle("show");
});
directRequestsBtn.addEventListener("click", () => {
  window.closeMediaGallery?.();
  directPinnedPanel.hidden = true;
  directRequestsPanel.hidden = !directRequestsPanel.hidden;
});
darkModeToggle.addEventListener("change", () => applyTheme(darkModeToggle.checked));
soundToggle.addEventListener("change", () => {
  localStorage.setItem("chat_sound", soundToggle.checked ? "1" : "0");
});

async function start() {
  applyTheme(localStorage.getItem("chat_dark_mode") === "1");
  soundToggle.checked = localStorage.getItem("chat_sound") !== "0";
  const saved = knownRooms().filter((room) => room.slug !== originRoomSlug);
  localStorage.setItem(
    KNOWN_ROOMS_KEY,
    JSON.stringify([
      { slug: originRoomSlug, name: originRoomName },
      ...saved,
    ].slice(0, 20))
  );
  renderRoomRail();
  try {
    const response = await fetch(`${DIRECT_API}/config`);
    if (!response.ok) {
      window.location.assign("/");
      return;
    }
    const config = await response.json();
    me = config.member;
    other = config.other;
    applyMemberUI();
    await Promise.all([pollMessages(), pollState()]);
  } catch (_error) {
    offlineBanner.classList.add("show");
  }
}

window.addEventListener("beforeunload", () => {
  clearTimeout(pollTimer);
  clearTimeout(stateTimer);
  if (mediaRecorder?.state === "recording") {
    discardRecording = true;
    mediaRecorder.stop();
  }
  voiceStream?.getTracks().forEach((track) => track.stop());
});

start();
