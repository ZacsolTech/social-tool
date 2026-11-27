import { Logo } from "./Logo";
import { MobileFeatured, MobileMenu, NavLinks } from "./NavMenus";
import { ThemeToggle } from "./ThemeToggle";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:h-16 sm:px-6">
        <Logo />
        <nav aria-label="Main" className="hidden items-center gap-0.5 text-sm md:flex">
          <NavLinks />
        </nav>
        <div className="flex items-center gap-1.5">
          <MobileFeatured />
          <ThemeToggle />
          <MobileMenu />
        </div>
      </div>
    </header>
  );
}
