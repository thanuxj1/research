import { useState, useRef, useEffect } from "react";
import FloatingMenu from "./components/ui/liquid-morph-floating-menu";

type Tab = "reviews" | "assistant" | "food";

// ── Cover page ─────────────────────────────────────────────────────────────

function CoverPage({ onEnter }: { onEnter: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    let W = 0, H = 0, t = 0, raf = 0;

    const resize = () => { W = c.width = window.innerWidth; H = c.height = window.innerHeight; };

    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      const d1 = Math.sin(t * 0.00028), d2 = Math.cos(t * 0.00021);
      const bg = ctx.createLinearGradient(0, 0, W * 0.7, H);
      bg.addColorStop(0, "#0D2236"); bg.addColorStop(0.55, "#081420"); bg.addColorStop(1, "#050E16");
      ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

      // teal orb
      ctx.save(); ctx.translate(W * (0.65 + d1 * 0.012), H * (0.30 + d2 * 0.010));
      const g1 = ctx.createRadialGradient(-W * 0.08, -H * 0.09, 0, 0, 0, W * 0.46);
      g1.addColorStop(0, "rgba(52,211,153,.55)"); g1.addColorStop(0.38, "rgba(16,133,96,.40)");
      g1.addColorStop(0.72, "rgba(8,80,56,.28)"); g1.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g1; ctx.beginPath();
      ctx.ellipse(0, 0, W * 0.40, H * 0.50, -0.22 + d1 * 0.018, 0, Math.PI * 2);
      ctx.fill(); ctx.restore();

      // gold orb
      ctx.save(); ctx.translate(W * (0.18 + d2 * 0.010), H * (0.72 + d1 * 0.009));
      const g2 = ctx.createRadialGradient(0, 0, 0, 0, 0, W * 0.28);
      g2.addColorStop(0, "rgba(232,184,75,.26)"); g2.addColorStop(0.5, "rgba(180,130,40,.10)");
      g2.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g2; ctx.beginPath();
      ctx.ellipse(0, 0, W * 0.24, H * 0.28, 0.3 + d2 * 0.014, 0, Math.PI * 2);
      ctx.fill(); ctx.restore();

      // vignette
      const vig = ctx.createRadialGradient(W * 0.5, H * 0.5, H * 0.18, W * 0.5, H * 0.5, H * 0.85);
      vig.addColorStop(0, "rgba(0,0,0,0)"); vig.addColorStop(1, "rgba(0,0,0,.58)");
      ctx.fillStyle = vig; ctx.fillRect(0, 0, W, H);

      t++; raf = requestAnimationFrame(draw);
    };

    resize();
    window.addEventListener("resize", resize);
    if (window.matchMedia("(prefers-reduced-motion:reduce)").matches) {
      t = 60; draw(); cancelAnimationFrame(raf);
    } else { draw(); }
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);

  return (
    <div className="fixed inset-0 flex items-center justify-center">
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
      <div className="relative z-10 flex flex-col items-center gap-5 text-center px-6">
        <h1
          className="font-black tracking-tighter text-white leading-none"
          style={{ fontSize: "clamp(3rem, 10vw, 7rem)" }}
        >
          Lost<span style={{ color: "#E8B84B" }}>in</span>SriLanka
        </h1>
        <p className="text-xs tracking-[0.25em] uppercase text-white/45 font-medium">
          AI Powered Smart Tourism Ecosystem
        </p>
        <div className="flex gap-8 text-sm text-white/55 font-medium">
          <span><strong className="text-[#E8B84B] font-bold">46,854</strong> reviews</span>
          <span><strong className="text-[#E8B84B] font-bold">293</strong> destinations</span>
          <span><strong className="text-[#E8B84B] font-bold">19</strong> districts</span>
        </div>
        <button
          onClick={onEnter}
          className="mt-3 px-8 py-3 bg-[#E8B84B] text-[#08111A] font-bold rounded-lg text-sm tracking-wide
                     hover:-translate-y-0.5 hover:shadow-[0_12px_30px_rgba(232,184,75,.42)]
                     transition-all duration-200"
        >
          Enter Platform →
        </button>
      </div>
    </div>
  );
}

// ── Portal ─────────────────────────────────────────────────────────────────

function Portal() {
  const [activeTab, setActiveTab] = useState<Tab>("reviews");
  const [menuOpen, setMenuOpen] = useState(false);
  const [loaded, setLoaded] = useState<Record<Tab, boolean>>({
    reviews: true,
    assistant: false,
    food: false,
  });

  const activate = (tab: Tab) => {
    setLoaded((prev) => ({ ...prev, [tab]: true }));
    setActiveTab(tab);
  };

  const menuItems = [
    { label: "Reviews",  onClick: () => activate("reviews") },
    { label: "AI Guide", onClick: () => activate("assistant") },
    { label: "Food",     onClick: () => activate("food") },
  ];

  return (
    <div className="fixed inset-0 bg-[#0D1B2A]">
      {/* Reviews */}
      <iframe
        src="/travellens/portal/index.html"
        title="Reviews"
        style={{
          position: "absolute", inset: 0, width: "100%", height: "100%",
          border: "none", zIndex: activeTab === "reviews" ? 10 : 0,
          visibility: activeTab === "reviews" ? "visible" : "hidden",
          pointerEvents: activeTab === "reviews" ? "auto" : "none",
        }}
      />

      {/* AI Assistant — inline component */}
      {loaded.assistant && (
        <div
          className="absolute inset-0 overflow-auto bg-[#060c17]"
          style={{
            zIndex: activeTab === "assistant" ? 10 : 0,
            visibility: activeTab === "assistant" ? "visible" : "hidden",
            pointerEvents: activeTab === "assistant" ? "auto" : "none",
          }}
        >
          {/* @ts-ignore — existing .jsx component */}
          <AIComponent />
        </div>
      )}

      {/* Food Guide */}
      {loaded.food && (
        <iframe
          src="/food/"
          title="Food Guide"
          style={{
            position: "absolute", inset: 0, width: "100%", height: "100%",
            border: "none", zIndex: activeTab === "food" ? 10 : 0,
            visibility: activeTab === "food" ? "visible" : "hidden",
            pointerEvents: activeTab === "food" ? "auto" : "none",
          }}
        />
      )}

      {/* Transparent overlay prevents iframes from stealing clicks when menu is open */}
      {menuOpen && (
        <div
          className="fixed inset-0"
          style={{ zIndex: 50 }}
          onMouseDown={() => setMenuOpen(false)}
        />
      )}

      <FloatingMenu items={menuItems} onOpenChange={setMenuOpen} />
    </div>
  );
}

// Lazy-load the existing AI assistant component
function AIComponent() {
  const [Comp, setComp] = useState<React.ComponentType<any> | null>(null);
  useEffect(() => {
    import("./Component2.jsx").then((m) => setComp(() => m.default));
  }, []);
  if (!Comp) return <div className="flex items-center justify-center h-screen text-white/40 text-sm">Loading…</div>;
  return <Comp onNavigateMap={() => {}} />;
}

// ── Root ───────────────────────────────────────────────────────────────────

export default function App() {
  const [entered, setEntered] = useState(false);
  return entered ? <Portal /> : <CoverPage onEnter={() => setEntered(true)} />;
}
