import HomeHeader from "./HomeHeader";
import HomeHero from "./HomeHero";
import HomeFeatures from "./HomeFeatures";
import HomeHowItWorks from "./HomeHowItWorks";
import HomeDetectionPreview from "./HomeDetectionPreview";
import HomeCTA from "./HomeCTA";
import HomeFooter from "./HomeFooter";

export default function HomePage() {
  return (
    <div className="h-full bg-[var(--color-bg)] text-[var(--color-text-primary)] overflow-y-auto overflow-x-hidden">
      <HomeHeader />
      <HomeHero />
      <HomeFeatures />
      <HomeHowItWorks />
      <HomeDetectionPreview />
      <HomeCTA />
      <HomeFooter />
    </div>
  );
}
