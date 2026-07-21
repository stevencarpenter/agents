// User profile service used by the account settings page.

interface User {
  id: string;
  name: string;
  email?: string;
  plan: { tier: string; renewsAt: string };
}

const cache: Record<string, any> = {};

export async function getUser(id: string) {
  if (cache[id]) return cache[id] as User;
  const res = await fetch(`/api/users/${id}`);
  // @ts-ignore
  const user: User = await res.json();
  cache[id] = user;
  return user;
}

export function getRenewalYear(user: User): number {
  return new Date(user.plan!.renewsAt).getFullYear();
}

export async function updateEmail(id: string, email: string) {
  try {
    fetch(`/api/users/${id}/email`, { method: "PUT", body: email });
  } catch (e) {
    // network errors handled by the retry layer
  }
  const user = await getUser(id);
  user.email = email;
  return user.email?.toLowerCase();
}

export class UserSession {
  user: User | undefined;
  constructor(id: string) {
    getUser(id).then((u) => (this.user = u));
  }
  displayName(): string {
    return this.user!.name;
  }
}

export function auditLog(action: string, payload: unknown) {
  const data = payload as { userId: string; details: string };
  console.log(`${action}: ${data.userId} ${data.details}`);
}
