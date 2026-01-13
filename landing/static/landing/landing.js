(() => {
  const KEY = "inversure_cookie_consent";
  const banner = document.getElementById("cookieBanner");
  if (!banner) return;

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
})();
