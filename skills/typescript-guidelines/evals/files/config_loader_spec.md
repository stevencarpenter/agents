# Spec: `loadConfig` — typed runtime-config loader

A module that fetches JSON config from `/config.json` at startup and hands the app a
fully-typed, validated config object. Target: browser, `strict` tsconfig with
`noUncheckedIndexedAccess` enabled.

## Shape

```jsonc
{
  "apiBaseUrl": "https://...",   // required, must be https
  "featureFlags": { "<name>": true },  // optional, defaults to {}
  "retryLimit": 3                // optional integer 0-10, defaults to 3
}
```

## Behavior

- `loadConfig(fetchImpl?)` returns a `Result`-shaped value — the caller must be able to
  distinguish, without try/catch: network failure, non-2xx response, malformed JSON,
  and schema-invalid config (which field, why). Never throw across the module boundary;
  never return `undefined` on failure.
- The raw `JSON.parse` output must be treated as `unknown` and narrowed by an explicit
  validation function — no `as Config` casts, no external validation library.
- All exported functions carry explicit return types.

## Deliverables

- `outputs/configLoader.ts`
- `outputs/configLoader.test.ts` (vitest style) covering: valid config, each failure
  kind, defaulting of optional fields, and rejection of http (non-https) apiBaseUrl.
