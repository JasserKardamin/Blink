/* Blink — interactions côté client (sans framework). */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  async function api(url, { method = "GET", body = null } = {}) {
    const headers = { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" };
    if (method !== "GET") headers["X-CSRFToken"] = getCookie("csrftoken");
    const resp = await fetch(url, { method, body, headers, credentials: "same-origin" });
    let data = null;
    try { data = await resp.json(); } catch (e) { /* réponse vide */ }
    if (!resp.ok) {
      const detail = (data && (data.detail || JSON.stringify(data))) || resp.statusText;
      throw new Error(detail);
    }
    return data;
  }

  const fmt = (s) => {
    s = Math.max(0, Math.round(s || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };

  /* ---------- Toasts ---------- */
  function toast(text, kind = "success") {
    const tpl = $("#toast-template");
    const box = $("#toasts");
    if (!tpl || !box) return;
    const node = tpl.content.firstElementChild.cloneNode(true);
    $("[data-toast-text]", node).textContent = text;
    if (kind === "error") {
      const icon = $("[data-toast-icon]", node);
      if (icon) { icon.className = "grid place-items-center w-9 h-9 rounded-full bg-salmon/20 text-salmon shrink-0"; icon.textContent = "!"; }
    }
    box.appendChild(node);
    bindToast(node);
  }
  function bindToast(node) {
    const close = () => { node.style.opacity = "0"; node.style.transition = "opacity .2s"; setTimeout(() => node.remove(), 200); };
    $("[data-toast-close]", node)?.addEventListener("click", close);
    setTimeout(close, 5000);
  }
  $$("[data-toast]").forEach(bindToast);
  window.blinkToast = toast;

  /* ---------- Menus déroulants ---------- */
  $$("[data-dropdown]").forEach((dd) => {
    const menu = $("[data-dropdown-menu]", dd);
    $("[data-dropdown-toggle]", dd).addEventListener("click", (e) => { e.stopPropagation(); menu.classList.toggle("hidden"); });
    document.addEventListener("click", (e) => { if (!dd.contains(e.target)) menu.classList.add("hidden"); });
  });

  /* ---------- Réactions (fetch, sans rechargement) ---------- */
  document.addEventListener("submit", async (e) => {
    const form = e.target.closest("[data-react-form]");
    if (!form) return;
    e.preventDefault();
    const btn = $("[data-react-button]", form) || form.querySelector("button");
    try {
      const data = await api(form.action, { method: "POST", body: new FormData(form) });
      // Formulaire simple (cœur) ou barre de réactions (plusieurs boutons).
      const bar = form.closest("[data-reaction-bar]");
      if (bar) {
        $$("[data-reaction-type]", bar).forEach((b) => b.classList.toggle("chip-active", data.active && b.dataset.reactionType === data.type));
        $$("[data-react-count]", bar).forEach((c) => (c.textContent = data.count));
        $$("[data-type-count]", bar).forEach((c) => (c.textContent = (data.counts || {})[c.dataset.typeCount] || 0));
      } else {
        btn.classList.toggle("is-liked", data.active);
        btn.setAttribute("aria-pressed", data.active ? "true" : "false");
        const count = $("[data-react-count]", form);
        if (count) count.textContent = data.count;
      }
      btn.classList.remove("pop"); void btn.offsetWidth; btn.classList.add("pop");
    } catch (err) {
      toast("Impossible d'enregistrer ta réaction.", "error");
    }
  });

  /* ---------- Lecteur audio avec onde ---------- */
  let currentAudio = null;
  $$("[data-audio-player]").forEach((player) => {
    const audio = $("[data-audio-el]", player);
    const bars = $$(".wave-bar", player);
    const time = $("[data-audio-time]", player);
    const total = time.textContent;
    const playIcon = $("[data-icon-play]", player);
    const pauseIcon = $("[data-icon-pause]", player);
    const setPlaying = (on) => { playIcon.classList.toggle("hidden", on); pauseIcon.classList.toggle("hidden", !on); };

    $("[data-audio-toggle]", player).addEventListener("click", () => {
      if (audio.paused) {
        if (currentAudio && currentAudio !== audio) currentAudio.pause();
        currentAudio = audio;
        audio.play().catch(() => toast("Lecture audio impossible.", "error"));
      } else audio.pause();
    });
    audio.addEventListener("play", () => setPlaying(true));
    audio.addEventListener("pause", () => setPlaying(false));
    audio.addEventListener("ended", () => { setPlaying(false); bars.forEach((b) => b.classList.remove("played")); time.textContent = total; });
    audio.addEventListener("timeupdate", () => {
      const d = isFinite(audio.duration) ? audio.duration : 0;
      const ratio = d ? audio.currentTime / d : 0;
      const n = Math.round(ratio * bars.length);
      bars.forEach((b, i) => b.classList.toggle("played", i < n));
      time.textContent = fmt(audio.currentTime);
    });
    $("[data-audio-wave]", player).addEventListener("click", (e) => {
      const rect = e.currentTarget.getBoundingClientRect();
      if (isFinite(audio.duration)) audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    });
  });

  /* ---------- Enregistreur vocal ---------- */
  function pickMime() {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
  }

  $$("[data-recorder]").forEach((rec) => {
    const form = rec.closest("form");
    const input = form && $("[data-recorder-input]", form);
    const durationInput = form && $("[data-recorder-duration]", form);
    const toggle = $("[data-rec-toggle]", rec);
    const status = $("[data-rec-status]", rec);
    const time = $("[data-rec-time]", rec);
    const preview = $("[data-rec-preview]", rec);
    const discard = $("[data-rec-discard]", rec);
    const upload = $("[data-rec-upload]", rec);
    const idleText = status.textContent;
    let recorder = null, chunks = [], started = 0, timer = null, stream = null;

    const setFile = (file, seconds) => {
      if (!input) return;
      const dt = new DataTransfer();
      if (file) dt.items.add(file);
      input.files = dt.files;
      if (durationInput) durationInput.value = file ? Math.round(seconds || 0) : "";
      preview.classList.toggle("hidden", !file);
      discard.classList.toggle("hidden", !file);
      if (file) {
        preview.src = URL.createObjectURL(file);
        status.textContent = "Message vocal prêt ✓";
        time.textContent = fmt(seconds);
      } else {
        preview.removeAttribute("src");
        status.textContent = idleText;
        time.textContent = "0:00";
      }
      rec.dispatchEvent(new CustomEvent("recorder:change", { bubbles: true, detail: { file } }));
    };

    const stopUI = () => {
      rec.classList.remove("rec-live");
      $("[data-rec-icon-start]", rec).classList.remove("hidden");
      $("[data-rec-icon-stop]", rec).classList.add("hidden");
      clearInterval(timer);
      stream?.getTracks().forEach((t) => t.stop());
    };

    toggle.addEventListener("click", async () => {
      if (recorder && recorder.state === "recording") { recorder.stop(); return; }
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        toast("Ton navigateur ne permet pas l'enregistrement : importe un fichier audio.", "error");
        upload?.click();
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        toast("Accès au micro refusé.", "error");
        return;
      }
      const mime = pickMime();
      recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks = [];
      recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      recorder.onstop = () => {
        stopUI();
        const seconds = (Date.now() - started) / 1000;
        const type = recorder.mimeType || "audio/webm";
        const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
        const file = new File([new Blob(chunks, { type })], `vocal-${Date.now()}.${ext}`, { type });
        setFile(file, seconds);
      };
      recorder.start();
      started = Date.now();
      rec.classList.add("rec-live");
      $("[data-rec-icon-start]", rec).classList.add("hidden");
      $("[data-rec-icon-stop]", rec).classList.remove("hidden");
      status.textContent = "Enregistrement… appuie pour arrêter";
      timer = setInterval(() => {
        const s = (Date.now() - started) / 1000;
        time.textContent = fmt(s);
        if (s > 300) recorder.stop(); // 5 minutes max
      }, 250);
    });

    discard.addEventListener("click", () => setFile(null, 0));
    upload?.addEventListener("change", () => {
      const file = upload.files[0];
      if (!file) return;
      const probe = new Audio(URL.createObjectURL(file));
      probe.addEventListener("loadedmetadata", () => setFile(file, isFinite(probe.duration) ? probe.duration : 0));
      probe.addEventListener("error", () => setFile(file, 0));
    });
  });

  /* Commentaire vocal : bouton d'envoi actif quand un enregistrement est prêt. */
  $$("[data-voice-comment-form]").forEach((form) => {
    const send = $("[data-voice-send]", form);
    form.addEventListener("recorder:change", (e) => send.classList.toggle("hidden", !e.detail.file));
  });

  /* ---------- Aperçu d'image ---------- */
  $$("[data-image-input]").forEach((input) => {
    const form = input.closest("form");
    const preview = form && $("[data-image-preview]", form);
    const empty = form && $("[data-image-empty]", form);
    input.addEventListener("change", () => {
      const file = input.files[0];
      if (!file || !preview) return;
      preview.src = URL.createObjectURL(file);
      preview.classList.remove("hidden");
      empty?.classList.add("hidden");
      form.dispatchEvent(new CustomEvent("image:change", { detail: { file } }));
    });
  });

  /* ---------- Génération IA : légende + hashtags ---------- */
  $$("[data-ai-panel]").forEach((panel) => {
    const form = panel.closest("form") || document;
    const button = $("[data-ai-generate]", panel);
    const result = $("[data-ai-result]", panel);
    const captionOut = $("[data-ai-caption]", panel);
    const tagsOut = $("[data-ai-tags]", panel);
    const engineOut = $("[data-ai-engine]", panel);
    const loading = $("[data-ai-loading]", panel);
    const caption = $("textarea[name=caption]", form);
    const hiddenCaption = $("input[name=caption_ia]", form);
    const hiddenTags = $("input[name=hashtags_ia]", form);
    const hiddenStyle = $("input[name=caption_style]", form);
    const imageInput = $("[data-image-input]", form);
    let style = $("[data-style].chip-active", panel)?.dataset.style || "poetique";
    let selectedTags = new Set();

    $$("[data-style]", panel).forEach((chip) => chip.addEventListener("click", () => {
      style = chip.dataset.style;
      $$("[data-style]", panel).forEach((c) => c.classList.toggle("chip-active", c === chip));
      if (!result.classList.contains("hidden")) generate();
    }));

    const syncTags = () => {
      if (hiddenTags) hiddenTags.value = Array.from(selectedTags).map((t) => "#" + t).join(" ");
    };

    async function generate() {
      const body = new FormData();
      body.append("style", style);
      if (panel.dataset.postId) body.append("post_id", panel.dataset.postId);
      else if (imageInput?.files[0]) body.append("image", imageInput.files[0]);
      else { toast("Choisis d'abord une photo 📷", "error"); return; }
      if (caption?.value) body.append("context", caption.value.slice(0, 500));
      const tpl = $("[data-ai-template]", panel);
      if (tpl?.value) body.append("template_id", tpl.value);

      button.disabled = true;
      loading.classList.remove("hidden");
      result.classList.add("hidden");
      try {
        const data = await api(panel.dataset.url, { method: "POST", body });
        captionOut.textContent = data.caption;
        engineOut.textContent = data.engine === "gemini" ? "Gemini" : "IA locale (hors-ligne)";
        tagsOut.innerHTML = "";
        selectedTags = new Set(data.hashtags);
        data.hashtags.forEach((tag) => {
          const chip = document.createElement("button");
          chip.type = "button";
          chip.className = "chip chip-active";
          chip.textContent = "#" + tag;
          chip.addEventListener("click", () => {
            if (selectedTags.has(tag)) selectedTags.delete(tag); else selectedTags.add(tag);
            chip.classList.toggle("chip-active", selectedTags.has(tag));
            syncTags();
          });
          tagsOut.appendChild(chip);
        });
        if (hiddenCaption) hiddenCaption.value = data.caption;
        if (hiddenStyle) hiddenStyle.value = data.style;
        syncTags();
        result.classList.remove("hidden");
      } catch (err) {
        toast("La génération IA a échoué : " + err.message, "error");
      } finally {
        button.disabled = false;
        loading.classList.add("hidden");
      }
    }

    button.addEventListener("click", generate);
    $("[data-ai-regenerate]", panel)?.addEventListener("click", generate);
    $("[data-ai-use]", panel)?.addEventListener("click", () => {
      if (caption) caption.value = captionOut.textContent;
      toast("Légende ajoutée ✨");
    });
  });

  /* ---------- Suivi des traitements IA asynchrones ---------- */
  $$("[data-poll-url]").forEach((el) => {
    let tries = 0;
    const tick = async () => {
      tries += 1;
      try {
        const data = await api(el.dataset.pollUrl);
        if (data.statut && data.statut !== "en_attente") { location.reload(); return; }
      } catch (e) { return; }
      if (tries < 90) setTimeout(tick, tries < 10 ? 1500 : 4000);
    };
    setTimeout(tick, 1500);
  });

  /* Rechargement différé (ex. détection de visages juste après publication). */
  $$("[data-reload-after]").forEach((el) => {
    setTimeout(() => location.reload(), parseInt(el.dataset.reloadAfter, 10) || 4000);
  });

  /* ---------- Tags des visages : surbrillance des cadres ---------- */
  $$("[data-face-row]").forEach((row) => {
    const box = document.getElementById("face-box-" + row.dataset.faceRow);
    if (!box) return;
    const on = () => box.classList.add("!border-salmon", "scale-105");
    const off = () => box.classList.remove("!border-salmon", "scale-105");
    row.addEventListener("mouseenter", on);
    row.addEventListener("mouseleave", off);
    row.addEventListener("focusin", on);
    row.addEventListener("focusout", off);
  });

  /* Valeur affichée des curseurs (filtres). */
  $$("input[type=range]").forEach((range) => {
    const out = document.createElement("span");
    out.className = "text-xs text-muted ml-2 tabular-nums";
    range.insertAdjacentElement("afterend", out);
    const sync = () => (out.textContent = range.value);
    range.addEventListener("input", sync);
    sync();
  });
})();
