/* Shared across Todaydeal pages. The date marker is local; totals live in GoatCounter. */
(() => {
  "use strict";
  const box = document.querySelector("[data-counter-code]");
  if (!box || location.hostname !== "hyac1107.github.io" ||
      !location.pathname.startsWith("/todaydeal/")) return;
  const code = box.dataset.counterCode;
  if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(code)) return;
  const origin = `https://${code}.goatcounter.com`;
  const path = "/todaydeal-visits";
  const key = `todaydeal:visit:${code}`;
  const day = () => new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);

  // Fail closed when storage is unavailable: never count every refresh by accident.
  async function record() {
    try {
      const today = day();
      if (localStorage.getItem(key) === today || window.goatcounter.filter()) return;
      const probe = `${key}:probe`;
      localStorage.setItem(probe, "1");
      localStorage.removeItem(probe);
      await new Promise(resolve => {
        const pixel = new Image();
        const timer = setTimeout(resolve, 8000);
        pixel.onload = () => {
          clearTimeout(timer);
          try { localStorage.setItem(key, today); } catch (_) { /* storage may be revoked */ }
          resolve();
        };
        pixel.onerror = () => { clearTimeout(timer); resolve(); };
        pixel.src = window.goatcounter.url({path, title: "오늘딜 방문", referrer: ""});
      });
    } catch (_) { /* A blocked tracker must never break the shop. */ }
  }

  async function display() {
    try {
      const response = await fetch(`${origin}/counter/${encodeURIComponent(path)}.json`, {
        signal: AbortSignal.timeout(8000), credentials: "omit",
      });
      if (!response.ok) return;
      const {count} = await response.json();
      // GoatCounter returns a formatted string; don't turn errors into a fake zero.
      if (typeof count !== "string" || !/^\d[\d, .\u00a0\u202f]*$/.test(count)) return;
      box.querySelector("[data-visitor-total]").textContent = `${count}회`;
      box.hidden = false;
    } catch (_) { /* Leave the counter hidden if unavailable. */ }
  }

  display();
  window.goatcounter = {no_onload: true, no_events: true};
  const tracker = document.createElement("script");
  tracker.dataset.goatcounter = `${origin}/count`;
  tracker.src = "https://gc.zgo.at/count.js";
  tracker.async = true;
  tracker.onload = () => {
    const visit = () => {
      if (document.visibilityState !== "visible") return;
      document.removeEventListener("visibilitychange", visit);
      if (navigator.locks) {
        navigator.locks.request(key, record).catch(() => {});
      } else {
        record();
      }
    };
    document.addEventListener("visibilitychange", visit);
    visit();
  };
  document.head.appendChild(tracker);
})();
