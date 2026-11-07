import Link from "next/link";
import { SITE } from "@/lib/site";

export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="9" fill="var(--accent)" />
      <path d="M12 9.5v13l11-6.5-11-6.5Z" fill="var(--accent-fg)" />
      <path d="M8 24.5h16" stroke="var(--accent-fg)" strokeWidth="2.2" strokeLinecap="round" opacity=".55" />
    </svg>
  );
}

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight" aria-label={`${SITE.name} home`}>
      <LogoMark />
      <span className="text-[17px]">{SITE.name}</span>
    </Link>
  );
}
