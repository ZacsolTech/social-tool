export function LegalPage({ title, updated, children }: { title: string; updated?: string; children: React.ReactNode }) {
  return (
    <article className="mx-auto max-w-2xl px-4 pt-14 sm:px-6 sm:pt-20">
      <h1 className="text-4xl font-semibold tracking-[-0.03em]">{title}</h1>
      {updated && <p className="mt-2 text-sm text-subtle">Last updated {updated}</p>}
      <div className="mt-8 space-y-4 text-[15px] leading-relaxed text-muted [&_a]:text-accent [&_a]:underline-offset-2 hover:[&_a]:underline [&_h2]:mt-10 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-fg [&_li]:ml-5 [&_li]:list-disc [&_strong]:text-fg">
        {children}
      </div>
    </article>
  );
}
