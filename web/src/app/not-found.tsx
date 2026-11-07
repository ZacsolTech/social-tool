import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-4 py-32 text-center">
      <p className="font-display text-7xl italic text-accent">404</p>
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">This page doesn&apos;t exist</h1>
      <p className="mt-2 text-muted">Maybe the link was mistyped. The downloader is one click away.</p>
      <Link href="/" className="mt-8 inline-flex rounded-full bg-accent px-5 py-2.5 font-semibold text-accent-fg">
        Go to the downloader
      </Link>
    </div>
  );
}
