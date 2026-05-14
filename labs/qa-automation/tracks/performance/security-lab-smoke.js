/**
 * k6 against local labs/security-lab (defensive). Run only on authorized networks.
 *
 *   set QA_BASE_URL=http://127.0.0.1:8000
 *   k6 run labs/security-lab-smoke.js
 */
import http from "k6/http";
import { check } from "k6";

const base = __ENV.QA_BASE_URL || "http://127.0.0.1:8000";
const key = __ENV.QA_API_KEY || "dev-lab-change-me";

export const options = { vus: 1, duration: "15s" };

export default function () {
  const h = { headers: { "X-Lab-API-Key": key, "X-Lab-Role": "lab_admin" } };
  const health = http.get(`${base.replace(/\/$/, "")}/health`);
  check(health, { "health 200": (r) => r.status === 200 });

  const metrics = http.get(`${base.replace(/\/$/, "")}/api/v1/metrics`, h);
  check(metrics, { "metrics 200": (r) => r.status === 200 });
}
