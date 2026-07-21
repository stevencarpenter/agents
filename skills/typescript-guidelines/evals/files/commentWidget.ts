// Embeddable comment widget: renders comments fetched from our API into a host page.
// Bundled for the BROWSER and also imported by the SSR server for prerendering.

import { readFileSync } from "node:fs";

type Comment = { author: string; body: string; createdAt: string };

const TEMPLATE = readFileSync("./comment.html", "utf-8");

export async function renderComments(container: HTMLElement, threadId: string) {
  const res = await fetch(`https://api.example.com/threads/${threadId}/comments`);
  const comments: Comment[] = JSON.parse(await res.text());

  for (const c of comments) {
    const el = document.createElement("div");
    el.innerHTML = TEMPLATE.replace("{{author}}", c.author).replace("{{body}}", c.body);
    container.appendChild(el);
  }
}

export function trackWidgetLoad(threadId: string) {
  // Fire-and-forget analytics; API key comes from the build env.
  fetch(`https://telemetry.example.com/load?key=${import.meta.env.TELEMETRY_SECRET}&t=${threadId}`);
}
