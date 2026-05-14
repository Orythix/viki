/**
 * k6 smoke — validates k6 wiring in CI (public demo API, no secrets).
 * Real lab load: use labs/security-lab-smoke.js with QA_BASE_URL.
 */
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 2,
  duration: "10s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<800"],
  },
};

export default function () {
  const res = http.get("https://test-api.k6.io/public/crocodiles");
  check(res, { "status 200": (r) => r.status === 200 });
  sleep(0.3);
}
