// Default backend URL for the playground. Overridable from the in-page settings
// (stored in localStorage as `nimbus_backend_url`), and at deploy time by editing this file.
window.NIMBUS_CONFIG = {
  defaultBackendUrl: "http://localhost:8100",
  get backendUrl() {
    return (localStorage.getItem("nimbus_backend_url") || this.defaultBackendUrl).replace(/\/$/, "");
  },
};
