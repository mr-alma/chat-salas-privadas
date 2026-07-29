(() => {
  const button = document.getElementById("message-search-btn");
  const panel = document.getElementById("message-search-panel");
  const input = document.getElementById("message-search-input");
  const count = document.getElementById("message-search-count");
  const previous = document.getElementById("message-search-prev");
  const next = document.getElementById("message-search-next");
  const close = document.getElementById("message-search-close");
  if (!button || !panel || !input) return;

  const directId = document.body.dataset.chatId;
  const roomSlug = document.body.dataset.roomSlug;
  const api = directId
    ? `/api/direct-chats/${encodeURIComponent(directId)}/search`
    : `/api/rooms/${encodeURIComponent(roomSlug)}/search`;
  let matches = [];
  let activeIndex = -1;
  let searchTimer = null;
  let searchSequence = 0;

  function clearHighlight() {
    document.querySelectorAll(".search-hit").forEach((item) => {
      item.classList.remove("search-hit");
    });
  }

  function updateCount() {
    count.textContent = matches.length && activeIndex >= 0
      ? `${activeIndex + 1}/${matches.length}`
      : `0/${matches.length}`;
    previous.disabled = matches.length === 0;
    next.disabled = matches.length === 0;
  }

  async function focusMatch(index) {
    if (!matches.length) return;
    activeIndex = (index + matches.length) % matches.length;
    clearHighlight();
    let target = document.querySelector(`[data-id="${matches[activeIndex].id}"]`);
    if (!target && typeof window.refreshDirectSnapshot === "function") {
      await window.refreshDirectSnapshot();
      target = document.querySelector(`[data-id="${matches[activeIndex].id}"]`);
    }
    if (target) {
      target.classList.add("search-hit");
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    updateCount();
  }

  async function runSearch() {
    const query = input.value.trim();
    const sequence = ++searchSequence;
    if (!query) {
      matches = [];
      activeIndex = -1;
      clearHighlight();
      updateCount();
      return;
    }
    try {
      const response = await fetch(`${api}?q=${encodeURIComponent(query)}`);
      const data = await response.json().catch(() => ({}));
      if (sequence !== searchSequence) return;
      if (!response.ok) throw new Error(data.error || "No se pudo buscar");
      matches = Array.isArray(data.matches) ? data.matches : [];
      activeIndex = matches.length ? 0 : -1;
      if (matches.length) await focusMatch(0);
      else {
        clearHighlight();
        updateCount();
      }
    } catch (_error) {
      matches = [];
      activeIndex = -1;
      updateCount();
    }
  }

  button.addEventListener("click", () => {
    const opening = panel.hidden;
    panel.hidden = !opening;
    if (opening) {
      input.focus();
      input.select();
    } else {
      clearHighlight();
    }
  });
  close.addEventListener("click", () => {
    panel.hidden = true;
    clearHighlight();
  });
  input.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 220);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      focusMatch(activeIndex + (event.shiftKey ? -1 : 1));
    }
  });
  previous.addEventListener("click", () => focusMatch(activeIndex - 1));
  next.addEventListener("click", () => focusMatch(activeIndex + 1));
  updateCount();
})();
