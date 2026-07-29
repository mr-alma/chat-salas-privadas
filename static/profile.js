(() => {
  const roomSlug = document.body.dataset.roomSlug;
  const roomApi = `/api/rooms/${encodeURIComponent(roomSlug)}`;
  const dialog = document.getElementById("profile-dialog");
  if (!dialog) return;

  const closeButton = document.getElementById("profile-dialog-close");
  const avatar = document.getElementById("profile-dialog-avatar");
  const title = document.getElementById("profile-dialog-title");
  const roleTag = document.getElementById("profile-dialog-role");
  const bioText = document.getElementById("profile-dialog-bio");
  const form = document.getElementById("profile-edit-form");
  const nameInput = document.getElementById("profile-name-input");
  const bioInput = document.getElementById("profile-bio-input");
  const formError = document.getElementById("profile-form-error");
  const photoButton = document.getElementById("profile-photo-change");
  const photoInput = document.getElementById("profile-photo-input");
  const banner = document.getElementById("profile-banner-view");
  const bannerButton = document.getElementById("profile-banner-change");
  const bannerInput = document.getElementById("profile-banner-input");
  const mediaViewer = document.getElementById("profile-media-viewer");
  const mediaViewerImage = document.getElementById("profile-media-viewer-image");
  const mediaViewerClose = document.getElementById("profile-media-viewer-close");
  let activeProfile = null;

  function initials(name) {
    return String(name || "?")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part.charAt(0))
      .join("")
      .toUpperCase() || "?";
  }

  function setAvatar(element, profile) {
    if (!element) return;
    element.textContent = profile.photo_url ? "" : initials(profile.name);
    element.classList.toggle("has-photo", Boolean(profile.photo_url));
    element.style.backgroundImage = profile.photo_url
      ? `url("${String(profile.photo_url).replaceAll('"', "%22")}")`
      : "";
  }

  window.setChatAvatar = setAvatar;

  function setBanner(profile) {
    if (!banner) return;
    banner.classList.toggle("has-photo", Boolean(profile.banner_url));
    banner.style.backgroundImage = profile.banner_url
      ? `linear-gradient(110deg, rgba(45,38,112,.15), rgba(35,151,188,.08)), url("${String(profile.banner_url).replaceAll('"', "%22")}")`
      : "";
  }

  function closeMediaViewer() {
    mediaViewer.hidden = true;
    mediaViewerImage.removeAttribute("src");
  }

  function openMediaViewer(url, alt) {
    if (!url) return;
    mediaViewerImage.src = url;
    mediaViewerImage.alt = alt;
    mediaViewer.hidden = false;
    mediaViewerClose.focus();
  }

  function notify(message) {
    if (typeof window.showAppToast === "function") window.showAppToast(message);
    else if (typeof window.showToast === "function") window.showToast(message);
  }

  function closeProfile() {
    closeMediaViewer();
    dialog.hidden = true;
    formError.textContent = "";
    activeProfile = null;
  }

  function paintProfile(profile, editable) {
    activeProfile = { ...profile, editable };
    const directMode = document.body.classList.contains("direct-page");
    const visibleRole = directMode ? "participant" : (profile.role || "participant");
    const visibleRoleLabel = directMode ? "Participante" : (profile.role_label || "Participante");
    title.textContent = profile.name;
    roleTag.textContent = visibleRoleLabel;
    roleTag.className = `role-tag role-${visibleRole}`;
    bioText.textContent = profile.bio || "Esta persona todavía no ha escrito una biografía.";
    setAvatar(avatar, profile);
    setBanner(profile);
    form.hidden = !editable;
    photoButton.hidden = !editable;
    bannerButton.hidden = !editable;
    avatar.disabled = !profile.photo_url && !editable;
    banner.disabled = !profile.banner_url && !editable;
    avatar.title = profile.photo_url ? "Ampliar foto de perfil" : editable ? "Agregar foto de perfil" : "";
    banner.title = profile.banner_url ? "Ampliar banner" : editable ? "Agregar banner" : "";
    bioText.hidden = editable;
    if (editable) {
      nameInput.value = profile.name || "";
      bioInput.value = profile.bio || "";
    }
  }

  window.syncChatProfile = (profile) => {
    if (!profile || !activeProfile || profile.id !== activeProfile.id) return;
    const editable = Boolean(activeProfile.editable);
    activeProfile = { ...activeProfile, ...profile, editable };
    const directMode = document.body.classList.contains("direct-page");
    const visibleRole = directMode ? "participant" : (activeProfile.role || "participant");
    const visibleRoleLabel = directMode
      ? "Participante"
      : (activeProfile.role_label || "Participante");
    title.textContent = activeProfile.name;
    roleTag.textContent = visibleRoleLabel;
    roleTag.className = `role-tag role-${visibleRole}`;
    setAvatar(avatar, activeProfile);
    setBanner(activeProfile);
    avatar.disabled = !activeProfile.photo_url && !editable;
    banner.disabled = !activeProfile.banner_url && !editable;
    avatar.title = activeProfile.photo_url
      ? "Ampliar foto de perfil"
      : editable ? "Agregar foto de perfil" : "";
    banner.title = activeProfile.banner_url
      ? "Ampliar banner"
      : editable ? "Agregar banner" : "";
    if (!editable) {
      bioText.textContent = activeProfile.bio || "Esta persona todavía no ha escrito una biografía.";
    }
  };

  window.openChatProfile = async (memberId, editableHint = false) => {
    try {
      const response = await fetch(`${roomApi}/members/${encodeURIComponent(memberId)}/profile`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "No se pudo abrir el perfil");
      paintProfile(
        data.profile,
        Boolean(data.editable && editableHint && window.currentChatMemberId === data.profile.id)
      );
      dialog.hidden = false;
      if (!form.hidden) nameInput.focus();
    } catch (error) {
      notify(error.message);
    }
  };

  closeButton.addEventListener("click", closeProfile);
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeProfile();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!mediaViewer.hidden) closeMediaViewer();
    else if (!dialog.hidden) closeProfile();
  });

  mediaViewerClose.addEventListener("click", closeMediaViewer);
  mediaViewer.addEventListener("click", (event) => {
    if (event.target === mediaViewer) closeMediaViewer();
  });
  avatar.addEventListener("click", () => {
    if (activeProfile?.photo_url) {
      openMediaViewer(activeProfile.photo_url, `Foto de perfil de ${activeProfile.name}`);
    } else if (activeProfile?.editable) {
      photoInput.click();
    }
  });
  banner.addEventListener("click", () => {
    if (activeProfile?.banner_url) {
      openMediaViewer(activeProfile.banner_url, `Banner de ${activeProfile.name}`);
    } else if (activeProfile?.editable) {
      bannerInput.click();
    }
  });
  photoButton.addEventListener("click", () => photoInput.click());
  photoInput.addEventListener("change", async () => {
    const photo = photoInput.files?.[0];
    if (!photo || !activeProfile) return;
    photoButton.disabled = true;
    formError.textContent = "";
    try {
      const body = new FormData();
      body.append("photo", photo);
      const response = await fetch(`${roomApi}/profile/photo`, {
        method: "POST",
        body,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "No se pudo cambiar la foto");
      activeProfile.photo_url = data.photo_url;
      setAvatar(avatar, activeProfile);
      avatar.disabled = false;
      setAvatar(document.getElementById("my-profile-avatar"), activeProfile);
      document.dispatchEvent(new CustomEvent("chat:profile-updated", {
        detail: { profile: { ...activeProfile } },
      }));
      notify("Tu foto de perfil se actualizó.");
    } catch (error) {
      formError.textContent = error.message;
    } finally {
      photoButton.disabled = false;
      photoInput.value = "";
    }
  });

  bannerButton.addEventListener("click", () => bannerInput.click());
  bannerInput.addEventListener("change", async () => {
    const selectedBanner = bannerInput.files?.[0];
    if (!selectedBanner || !activeProfile) return;
    bannerButton.disabled = true;
    formError.textContent = "";
    try {
      const body = new FormData();
      body.append("banner", selectedBanner);
      const response = await fetch(`${roomApi}/profile/banner`, {
        method: "POST",
        body,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "No se pudo cambiar el banner");
      activeProfile.banner_url = data.banner_url;
      setBanner(activeProfile);
      banner.disabled = false;
      document.dispatchEvent(new CustomEvent("chat:profile-updated", {
        detail: { profile: { ...activeProfile } },
      }));
      notify("Tu banner se actualizó.");
    } catch (error) {
      formError.textContent = error.message;
    } finally {
      bannerButton.disabled = false;
      bannerInput.value = "";
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!activeProfile) return;
    const name = nameInput.value.trim();
    const bio = bioInput.value.trim();
    if (!name) {
      formError.textContent = "Escribe el nombre que quieres mostrar.";
      return;
    }
    const save = form.querySelector('button[type="submit"]');
    save.disabled = true;
    formError.textContent = "";
    try {
      if (name !== activeProfile.name) {
        const nameResponse = await fetch(`${roomApi}/membership/name`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
        const nameData = await nameResponse.json().catch(() => ({}));
        if (!nameResponse.ok) throw new Error(nameData.error || "No se pudo cambiar el nombre");
        activeProfile.name = nameData.member.name;
      }
      const profileResponse = await fetch(`${roomApi}/profile`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bio }),
      });
      const profileData = await profileResponse.json().catch(() => ({}));
      if (!profileResponse.ok) throw new Error(profileData.error || "No se pudo guardar el perfil");
      activeProfile = { ...profileData.profile, editable: true };
      paintProfile(activeProfile, true);
      setAvatar(document.getElementById("my-profile-avatar"), activeProfile);
      document.dispatchEvent(new CustomEvent("chat:profile-updated", {
        detail: { profile: { ...activeProfile } },
      }));
      notify("Perfil guardado.");
    } catch (error) {
      formError.textContent = error.message;
    } finally {
      save.disabled = false;
    }
  });
})();
