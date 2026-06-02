/* Prospect BarberHub — main.js */

(function () {
  "use strict";

  const sidebar  = document.getElementById("sidebar");
  const overlay  = document.getElementById("sidebarOverlay");
  const toggle   = document.getElementById("sidebarToggle");

  function openSidebar() {
    sidebar?.classList.add("open");
    if (overlay) {
      overlay.style.display = "block";
      requestAnimationFrame(() => overlay.classList.add("visible"));
    }
    document.body.style.overflow = "hidden";
  }

  function closeSidebar() {
    sidebar?.classList.remove("open");
    if (overlay) {
      overlay.classList.remove("visible");
      // wait for fade-out transition before hiding
      overlay.addEventListener("transitionend", () => {
        if (!overlay.classList.contains("visible")) overlay.style.display = "";
      }, { once: true });
    }
    document.body.style.overflow = "";
  }

  function isMobile() {
    return window.innerWidth <= 768;
  }

  // Toggle button
  toggle?.addEventListener("click", (e) => {
    e.stopPropagation();
    sidebar?.classList.contains("open") ? closeSidebar() : openSidebar();
  });

  // Click overlay to close
  overlay?.addEventListener("click", closeSidebar);

  // Escape key to close
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebar?.classList.contains("open")) closeSidebar();
  });

  // Close sidebar when nav link clicked on mobile
  if (sidebar) {
    sidebar.querySelectorAll(".sidebar-link").forEach((link) => {
      link.addEventListener("click", () => {
        if (isMobile()) closeSidebar();
      });
    });
  }

  // Auto-dismiss flash alerts after 4.5 s
  setTimeout(() => {
    document.querySelectorAll(".alert.alert-dismissible.fade.show").forEach((el) => {
      try { bootstrap.Alert.getOrCreateInstance(el).close(); } catch (_) {}
    });
  }, 4500);

})();
