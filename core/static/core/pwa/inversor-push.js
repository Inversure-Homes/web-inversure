(() => {
  const btn = document.getElementById("inv_push_btn");
  if (!btn) return;
  if (!("Notification" in window) || !("serviceWorker" in navigator)) {
    btn.classList.add("d-none");
    return;
  }

  const publicKeyUrl = btn.getAttribute("data-public-key-url") || "";
  const subscribeUrl = btn.getAttribute("data-subscribe-url") || "";
  const unsubscribeUrl = btn.getAttribute("data-unsubscribe-url") || "";

  const getCsrfToken = () => {
    const m = document.cookie.match(/(^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[2]) : "";
  };

  const urlBase64ToUint8Array = (base64String) => {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = window.atob(base64);
    return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
  };

  const setBtn = (state, label) => {
    btn.dataset.state = state;
    if (label) btn.textContent = label;
  };

  const updateState = async () => {
    if (Notification.permission === "denied") {
      setBtn("denied", "Notificaciones bloqueadas");
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      setBtn("enabled", "Notificaciones activas");
    } else {
      setBtn("idle", "Activar notificaciones");
    }
  };

  const subscribe = async () => {
    const keyResp = await fetch(publicKeyUrl, { credentials: "same-origin" });
    const keyData = await keyResp.json();
    if (!keyData || !keyData.publicKey) throw new Error("No public key");

    const reg = await navigator.serviceWorker.ready;
    const permission = await Notification.requestPermission();
    if (permission !== "granted") throw new Error("Permission denied");

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(keyData.publicKey),
    });

    const resp = await fetch(subscribeUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(getCsrfToken() ? { "X-CSRFToken": getCsrfToken() } : {}),
      },
      body: JSON.stringify({ subscription: sub }),
      credentials: "same-origin",
    });
    if (!resp.ok) throw new Error("Subscribe failed");
  };

  const unsubscribe = async () => {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (!sub) return;
    await sub.unsubscribe();
    await fetch(unsubscribeUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(getCsrfToken() ? { "X-CSRFToken": getCsrfToken() } : {}),
      },
      body: JSON.stringify({ endpoint: sub.endpoint }),
      credentials: "same-origin",
    });
  };

  btn.addEventListener("click", async () => {
    try {
      btn.disabled = true;
      if (btn.dataset.state === "enabled") {
        await unsubscribe();
      } else {
        await subscribe();
      }
    } catch (e) {
      console.warn(e);
    } finally {
      btn.disabled = false;
      await updateState();
    }
  });

  updateState().catch(() => {});
})();
