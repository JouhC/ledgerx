export function joinUrl(base: string, path: string): string {
  if (!base) return path;
  if (!path) return base;
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

export function peso(x: number | null | undefined): string {
  if (x == null || Number.isNaN(x)) return "—";
  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    minimumFractionDigits: 2,
  }).format(x);
}

export function parseDate(value?: string | null): string | null {
  if (!value) return null;
  const d = new Date(value.replace(" ", "T").replace(/Z$/, ""));
  return Number.isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10);
}

export function toAmount(value?: string | number): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const n = Number(value.replace(/,/g, ""));
    return Number.isFinite(n) ? n : 0;
  }
  return 0;
}

export function monthOf(value?: string | null): string | null {
  if (!value) return null;
  return value.slice(0, 7);
}

export function daysDiff(from: string, to: string): number {
  const a = new Date(from);
  const b = new Date(to);
  return Math.floor((b.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
}