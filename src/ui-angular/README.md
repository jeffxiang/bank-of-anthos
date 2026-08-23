# Angular frontend

This directory contains the Angular 14 single-page frontend for Bank of America.
It runs alongside the existing Flask frontend and uses nginx to serve the
bundle and proxy backend API requests through one browser origin.

## Local development

The repository pins the Angular 14 toolchain to Node 16.10.x:

```sh
npm ci
npm test
npm run build
```

The Kubernetes service is `ui-angular` and is a `ClusterIP`. Its nginx
configuration receives `USERSERVICE_API_ADDR`, `BALANCES_API_ADDR`,
`HISTORY_API_ADDR`, `CONTACTS_API_ADDR`, and `TRANSACTIONS_API_ADDR` from the
cluster's `service-api-config` ConfigMap.
