(() => {
  const openButton = document.getElementById("media-gallery-btn");
  const panel = document.getElementById("media-gallery-panel");
  const closeButton = document.getElementById("media-gallery-close");
  const tabs = document.getElementById("media-gallery-tabs");
  const content = document.getElementById("media-gallery-content");
  const moreButton = document.getElementById("media-gallery-more");
  if (!openButton || !panel || !closeButton || !tabs || !content || !moreButton) return;

  const chatId = document.body.dataset.chatId;
  const roomSlug = document.body.dataset.roomSlug;
  const scopeApi = chatId
    ? `/api/direct-chats/${encodeURIComponent(chatId)}`
    : `/api/rooms/${encodeURIComponent(roomSlug)}`;
  let activeType = "all";
  let nextBeforeId = null;
  let loading = false;

  function formatMediaDate(iso) {
    const value = /(?:Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : `${iso}Z`;
    return new Date(value).toLocaleString([], {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function createMediaElement(item) {
    if (item.type === "image") {
      const link = document.createElement("a");
      link.href = item.file_url;
      link.target = "_blank";
      link.rel = "noopener";
      link.className = "media-gallery-preview";
      const image = document.createElement("img");
      image.src = item.file_url;
      image.alt = item.file_name || "Imagen compartida";
      image.loading = "lazy";
      link.appendChild(image);
      return link;
    }
    if (item.type === "video") {
      const video = document.createElement("video");
      video.className = "media-gallery-preview";
      video.src = item.file_url;
      video.controls = true;
      video.preload = "metadata";
      return video;
    }
    if (item.type === "audio") {
      const audio = document.createElement("audio");
      audio.src = item.file_url;
      audio.controls = true;
      audio.preload = "metadata";
      return audio;
    }
    const link = document.createElement("a");
    link.href = item.file_url;
    link.download = item.file_name || "Archivo";
    link.className = "media-gallery-file-link";
    link.textContent = `📎 ${item.file_name || "Descargar archivo"}`;
    return link;
  }

  function renderItem(item) {
    const card = document.createElement("article");
    card.className = `media-gallery-item media-kind-${item.type}`;
    card.dataset.messageId = String(item.id);
    const media = createMediaElement(item);
    const meta = document.createElement("div");
    meta.className = "media-gallery-meta";
    const author = document.createElement("strong");
    author.textContent = item.author_name || "Participante";
    const date = document.createElement("time");
    date.dateTime = item.created_at;
    date.textContent = formatMediaDate(item.created_at);
    meta.append(author, date);
    card.append(media, meta);
    content.appendChild(card);
  }

  function updateCounts(counts) {
    tabs.querySelectorAll("[data-media-type]").forEach((button) => {
      const count = counts?.[button.dataset.mediaType] || 0;
      const badge = button.querySelector("span");
      if (badge) badge.textContent = String(count);
    });
  }

  function showEmpty() {
    const empty = document.createElement("div");
    empty.className = "media-gallery-empty";
    empty.innerHTML = "<span>🗂️</span><strong>Aún no hay contenido aquí</strong><small>Las fotos, videos, audios y archivos aparecerán en este panel.</small>";
    content.appendChild(empty);
  }

  function showError(message) {
    const error = document.createElement("div");
    error.className = "media-gallery-empty";
    const icon = document.createElement("span");
    icon.textContent = "⚠️";
    const text = document.createElement("strong");
    text.textContent = message;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = "Reintentar";
    retry.addEventListener("click", () => loadMedia(false));
    error.append(icon, text, retry);
    content.replaceChildren(error);
  }

  async function loadMedia(append) {
    if (loading) return;
    loading = true;
    if (!append) {
      content.replaceChildren();
      nextBeforeId = null;
      content.setAttribute("aria-busy", "true");
    }
    moreButton.disabled = true;
    try {
      const query = new URLSearchParams({ type: activeType, limit: "80" });
      if (append && nextBeforeId) query.set("before_id", String(nextBeforeId));
      const response = await fetch(`${scopeApi}/media?${query}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "No se pudo cargar el contenido");
      updateCounts(data.counts);
      (data.items || []).forEach(renderItem);
      if (!append && !(data.items || []).length) showEmpty();
      nextBeforeId = data.next_before_id;
      moreButton.hidden = !data.has_more;
    } catch (error) {
      showError(error.message);
      moreButton.hidden = true;
    } finally {
      loading = false;
      moreButton.disabled = false;
      content.removeAttribute("aria-busy");
    }
  }

  function closeOtherPanels() {
    ["pinned-panel", "join-requests-panel", "direct-requests-panel", "name-editor-panel"].forEach((id) => {
      const element = document.getElementById(id);
      if (element) element.hidden = true;
    });
    document.getElementById("settings-panel")?.classList.remove("show");
    document.getElementById("online-users")?.classList.remove("show");
  }

  function closePanel() {
    panel.hidden = true;
    openButton.classList.remove("active");
    openButton.setAttribute("aria-expanded", "false");
  }

  window.closeMediaGallery = closePanel;

  openButton.addEventListener("click", () => {
    const willOpen = panel.hidden;
    panel.hidden = !willOpen;
    openButton.classList.toggle("active", willOpen);
    openButton.setAttribute("aria-expanded", String(willOpen));
    if (willOpen) {
      closeOtherPanels();
      loadMedia(false);
    }
  });

  closeButton.addEventListener("click", closePanel);

  tabs.addEventListener("click", (event) => {
    const button = event.target.closest("[data-media-type]");
    if (!button || button.dataset.mediaType === activeType) return;
    activeType = button.dataset.mediaType;
    tabs.querySelectorAll("[data-media-type]").forEach((tab) => {
      tab.classList.toggle("active", tab === button);
    });
    loadMedia(false);
  });

  moreButton.addEventListener("click", () => loadMedia(true));
  document.addEventListener("chat:media-changed", () => {
    if (!panel.hidden) loadMedia(false);
  });
})();
