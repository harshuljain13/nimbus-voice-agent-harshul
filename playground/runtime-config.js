// Default backend URL for the playground. Auto-selects: localhost during local dev, the deployed
// Render backend when served from anywhere else. Overridable from the in-page API-keys dialog
// (stored in localStorage as `nimbus_backend_url`).
window.NIMBUS_CONFIG = {
  defaultBackendUrl:
    (location.hostname === "localhost" || location.hostname === "127.0.0.1")
      ? "http://localhost:8100"
      : "https://nimbus-voice-agent-harshul.onrender.com",
  get backendUrl() {
    return (localStorage.getItem("nimbus_backend_url") || this.defaultBackendUrl).replace(/\/$/, "");
  },
};
