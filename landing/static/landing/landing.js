(() => {
  const KEY = "inversure_cookie_consent";
  const banner = document.getElementById("cookieBanner");

  if (banner) {
    const stored = localStorage.getItem(KEY);
    if (!stored) {
      banner.style.display = "block";
      banner.setAttribute("aria-hidden", "false");
    }

    const accept = document.getElementById("cookieAccept");
    const reject = document.getElementById("cookieReject");

    function save(value) {
      localStorage.setItem(KEY, value);
      banner.style.display = "none";
      banner.setAttribute("aria-hidden", "true");
    }

    if (accept) {
      accept.addEventListener("click", () => save("accepted"));
    }
    if (reject) {
      reject.addEventListener("click", () => save("rejected"));
    }
  }

  const openButtons = document.querySelectorAll("[data-lead-open]");
  const modals = document.querySelectorAll("[data-lead-modal]");

  function closeModal(modal) {
    modal.classList.remove("is-open");
    modal.setAttribute("aria-hidden", "true");
  }

  function openModal(modal) {
    modal.classList.add("is-open");
    modal.setAttribute("aria-hidden", "false");
  }

  openButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-lead-open");
      const modal = document.querySelector(`[data-lead-modal="${target}"]`);
      if (modal) {
        openModal(modal);
      }
    });
  });

  modals.forEach((modal) => {
    modal.querySelectorAll("[data-lead-close]").forEach((btn) => {
      btn.addEventListener("click", () => closeModal(modal));
    });
    if (modal.dataset.open === "true") {
      openModal(modal);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    modals.forEach((modal) => {
      if (modal.classList.contains("is-open")) {
        closeModal(modal);
      }
    });
  });
})();
