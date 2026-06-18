// API base URL. Empty string => same-origin (uses the dev proxy in
// proxy.conf.json during `ng serve`, or the reverse proxy in Docker).
export const environment = {
  production: false,
  apiBaseUrl: '',
};
