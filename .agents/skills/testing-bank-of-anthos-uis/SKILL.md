---
name: testing-bank-of-anthos-uis
description: How to run and browser-test the Bank of Anthos frontends (Flask src/frontend and the Angular src/ui-angular SPA) on a local minikube cluster, including parity testing between them.
---

# Testing the Bank of Anthos frontends locally

## Bringing the stack up
- The app runs on minikube with the manifests in `kubernetes-manifests/` (8 original pods) plus `ui-angular` if that frontend exists.
- Off-GCP, tracing/metrics exporters crash the Java/Python services. Disable them before expecting pods to become Ready:
  `kubectl set env deployment --all ENABLE_TRACING=false ENABLE_METRICS=false`
- Expose the UIs with port-forwards (each in its own background shell):
  - Flask UI: `kubectl port-forward svc/frontend 8080:80` → http://127.0.0.1:8080
  - Angular UI: `kubectl port-forward svc/ui-angular 8081:80` → http://127.0.0.1:8081
- Rebuild the Angular image after a fix:
  `cd src/ui-angular && eval "$(minikube docker-env)" && docker build -t ui-angular:latest . && kubectl rollout restart deployment/ui-angular`

## Credentials and runtime config
- Demo login: `testuser` / `bankofanthos` (seeded demo account `1011226111`).
- `LOCAL_ROUTING_NUM` is `883745000` in the default `environment-config` ConfigMap; the deposit form must reject an external routing number equal to it.
- The Angular SPA reads demo creds and local routing from `GET /config.json`, rendered by nginx from env vars. Sanity check it first:
  `curl -s http://127.0.0.1:8081/config.json`
  Expect `{"demoUsername":"...","demoPassword":"...","localRouting":"..."}`. If it returns the literal `${VAR}` placeholders, the ConfigMap wiring in the deployment is broken.
- Angular stores its JWT in `sessionStorage.token`; Flask uses a `token` cookie. They are independent sessions, so you can drive both UIs side by side in two tabs of the same browser.

## Parity testing tips
- Treat `src/frontend/frontend.py` and `src/frontend/templates/*` as the spec. Useful anchors: `/home` route + `_populate_contact_labels`, payment handler, deposit handler (local-routing rejection), signup/logout, and the currency filter.
- The strongest cross-check: make a transaction in one UI, then reload the other UI and confirm the same balance and history row. Backend state is shared, so both must agree.
- Amounts are stored in cents; both UIs must render dollars. Watch for a row whose account has no contact — Flask prints `None` in the Label column while a port may print the raw account number (cosmetic difference, worth noting).
- **Known failure mode to check for in any non-Flask client:** `ledgerwriter POST /transactions` returns HTTP 201 with the plain-text body `ok`, and `userservice POST /users` similarly returns non-JSON. Angular's `HttpClient` defaults to `responseType: 'json'`, so a *successful* call is delivered to the error callback (parse error) and the UI shows a false "failed" banner while the transaction actually commits. Always verify a "failed" transaction by reloading the page / checking the balance before believing the banner. Fix is `this.http.post(url, body, { responseType: 'text' })`.
- Validation edges worth exercising: amount `0`, negative, above balance, non-numeric and over-long account numbers, and submitting the "New external account" deposit with empty account/routing. Verify a user-visible message or field-level invalid styling appears and that no transaction is created (reload to confirm).
- Signup: the `birthday` field is `<input type="date">`; type the digits `01011990` (no slashes) after clicking it, otherwise the value stays empty and the form silently stays invalid.

## Devin Secrets Needed
- None. All credentials are demo values baked into the manifests.
