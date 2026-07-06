import { ArrowRight } from "lucide-react";
import { LandingButton } from "./LandingButton";
import "../../landing.css";

/**
 * Landing page hero, ported from prajwal5065/lead-intelligence-platform
 * (app/page.tsx, Navigation + Hero Section only, lines ~151-234 of the
 * original - per explicit scope: "just the landing page/hero section",
 * not the full marketing site with pricing/testimonials/FAQ/footer).
 *
 * Adaptations from the original Next.js source:
 * - next/image -> plain <img> (Vite has no next/image equivalent)
 * - @/components/ui/button (wraps @base-ui/react/button) -> LandingButton,
 *   a small local component matching the same two variants used here,
 *   avoiding a new dependency for a single-page hero port
 * - Copy, layout, and Tailwind classes preserved as-is from the original
 * - Uses its own oklch() color tokens (lp-*, see landing.css) rather than
 *   this project's Zapier-derived dashboard tokens - by explicit choice,
 *   since this is a different product surface (Pathfinder brand)
 */
export function LandingHero() {
  return (
    <main className="overflow-hidden bg-lp-background text-lp-foreground">
      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 bg-lp-background/80 backdrop-blur-md border-b border-lp-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-lp-primary to-lp-secondary flex items-center justify-center">
              <span className="text-white font-bold text-lg">P</span>
            </div>
            <span className="font-bold text-xl text-lp-foreground">Pathfinder</span>
          </div>
          <div className="flex items-center gap-8">
            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-lp-foreground/70 hover:text-lp-foreground transition">Features</a>
              <a href="#workflow" className="text-lp-foreground/70 hover:text-lp-foreground transition">Workflow</a>
              <a href="#usecases" className="text-lp-foreground/70 hover:text-lp-foreground transition">Use Cases</a>
              <a href="#pricing" className="text-lp-foreground/70 hover:text-lp-foreground transition">Pricing</a>
            </div>
            <LandingButton className="bg-lp-primary hover:bg-lp-primary/90 text-white px-4 py-2">
              Get Started
              <ArrowRight className="w-4 h-4 ml-2" />
            </LandingButton>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8 relative overflow-hidden">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div className="space-y-8">
              <div className="space-y-4">
                <div className="inline-block px-4 py-2 rounded-full bg-lp-accent/10 border border-lp-accent/30">
                  <p className="text-sm font-semibold text-lp-accent">🚀 Enterprise-Grade AI Intelligence</p>
                </div>
                <h1 className="text-5xl md:text-6xl font-bold text-lp-foreground leading-tight">
                  Discover{" "}
                  <span className="bg-gradient-to-r from-lp-primary to-lp-secondary bg-clip-text text-transparent">
                    High-Value Companies
                  </span>{" "}
                  at Scale
                </h1>
                <p className="text-xl text-lp-foreground/70 leading-relaxed max-w-lg">
                  AI-powered lead intelligence platform that discovers, enriches, and qualifies business
                  opportunities across any geographic region. Built for enterprises and sales teams.
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-4">
                <LandingButton className="bg-lp-primary hover:bg-lp-primary/90 text-white text-lg px-8 py-6 rounded-lg">
                  Start Free Discovery
                  <ArrowRight className="w-5 h-5 ml-2" />
                </LandingButton>
                <LandingButton
                  variant="outline"
                  className="text-lg px-8 py-6 rounded-lg border-lp-border hover:bg-lp-muted"
                >
                  Watch Demo
                </LandingButton>
              </div>

              <div className="flex gap-8 pt-8">
                <div>
                  <p className="text-3xl font-bold text-lp-foreground">50M+</p>
                  <p className="text-sm text-lp-foreground/60">Companies Discoverable</p>
                </div>
                <div>
                  <p className="text-3xl font-bold text-lp-foreground">150+</p>
                  <p className="text-sm text-lp-foreground/60">Countries Supported</p>
                </div>
                <div>
                  <p className="text-3xl font-bold text-lp-foreground">98%+</p>
                  <p className="text-sm text-lp-foreground/60">Data Accuracy</p>
                </div>
              </div>
            </div>

            <div className="relative h-96 md:h-full min-h-96">
              <div className="absolute inset-0 bg-gradient-to-br from-lp-primary/10 to-lp-secondary/10 rounded-2xl blur-3xl" />
              <img
                src="/hero-dashboard.png"
                alt="Pathfinder Dashboard"
                className="absolute inset-0 w-full h-full object-cover rounded-2xl shadow-2xl"
              />
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
