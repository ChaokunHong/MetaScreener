<template>
  <div class="home">
    <div class="bg-orbs" aria-hidden="true">
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
      <div class="orb orb-3"></div>
      <div class="orb orb-4"></div>
    </div>

    <section
      ref="heroRef"
      class="hero-liquid"
      @pointermove="onHeroPointerMove"
      @pointerleave="onHeroPointerLeave"
    >
      <div class="hero-ambient" aria-hidden="true"></div>
      <div class="hero-prism" aria-hidden="true"></div>
      <div class="hero-caustics" aria-hidden="true"></div>
      <div class="hero-noise" aria-hidden="true"></div>
      <div class="hero-shimmer" aria-hidden="true"></div>
      <div class="hero-refraction" aria-hidden="true"></div>
      <div class="hero-content">
        <div class="hero-badge">
          <span class="badge-glow"></span>
          <span class="badge-dot"></span>
          Open-Source Systematic Review Tool
        </div>
        <h1 class="hero-title">
          Screen thousands of papers<br />
          <span class="hero-gradient">with AI consensus.</span>
        </h1>
        <p class="hero-desc">
          4 open-source LLMs form a Hierarchical Consensus Network.
          Calibrated confidence. Full reproducibility. No proprietary models.
        </p>
        <div class="hero-actions">
          <router-link to="/settings" class="btn-liquid btn-primary">
            <span class="btn-shine"></span>
            <i class="fas fa-microchip"></i>
            Configure LLMs
          </router-link>
          <a
            href="https://github.com/ChaokunHong/MetaScreener"
            target="_blank"
            rel="noopener"
            class="btn-liquid btn-secondary"
          >
            <span class="btn-shine btn-shine-slow"></span>
            <i class="fab fa-github"></i>
            GitHub
          </a>
        </div>
      </div>
    </section>

    <section class="pipeline">
      <div class="pipeline-header">
        <h2 class="pipeline-title">End-to-end pipeline</h2>
        <p class="pipeline-sub">From criteria definition to risk-of-bias assessment</p>
      </div>
      <div class="pipeline-grid">
        <router-link
          v-for="(step, i) in steps"
          :key="step.path"
          :to="step.path"
          class="step-liquid"
          :style="{ '--step-accent': step.color, '--step-tint': step.tint }"
        >
          <div class="step-inner-glow" :style="{ background: step.glow }"></div>
          <div class="step-number">0{{ i + 1 }}</div>
          <div class="step-icon" :style="{ background: step.tint, color: step.color }">
            <i :class="step.icon"></i>
          </div>
          <div class="step-title">{{ step.title }}</div>
          <div class="step-desc">{{ step.desc }}</div>
          <div class="step-arrow"><i class="fas fa-arrow-right"></i></div>
        </router-link>
      </div>
    </section>

    <section class="stats-float">
      <div v-for="stat in stats" :key="stat.label" class="stat-capsule">
        <div class="stat-value">{{ stat.value }}</div>
        <div class="stat-label">{{ stat.label }}</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { apiGet } from '@/api'

const steps = [
  { path: '/criteria',   icon: 'fas fa-list-check',     title: 'Define Criteria',      desc: 'PICO wizard with multi-model consensus and semantic deduplication.',   tint: 'rgba(139,92,246,0.12)',  color: '#8b5cf6', glow: 'radial-gradient(circle at 30% 20%, rgba(139,92,246,0.08) 0%, transparent 60%)' },
  { path: '/screening',  icon: 'fas fa-filter',          title: 'Screen Literature',    desc: '4 LLMs screen in parallel with calibrated confidence aggregation.',   tint: 'rgba(6,182,212,0.12)',   color: '#06b6d4', glow: 'radial-gradient(circle at 30% 20%, rgba(6,182,212,0.08) 0%, transparent 60%)' },
  { path: '/extraction', icon: 'fas fa-table',           title: 'Extract Data',         desc: 'Structured data extraction from PDFs with YAML-defined forms.',       tint: 'rgba(16,185,129,0.12)',  color: '#10b981', glow: 'radial-gradient(circle at 30% 20%, rgba(16,185,129,0.08) 0%, transparent 60%)' },
  { path: '/quality',    icon: 'fas fa-clipboard-check', title: 'Assess Quality',       desc: 'Risk of bias via RoB 2, ROBINS-I, or QUADAS-2 frameworks.',          tint: 'rgba(245,158,11,0.12)',  color: '#f59e0b', glow: 'radial-gradient(circle at 30% 20%, rgba(245,158,11,0.08) 0%, transparent 60%)' },
  { path: '/evaluation', icon: 'fas fa-chart-bar',       title: 'Evaluate Performance', desc: 'Sensitivity, specificity, AUROC with bootstrap confidence intervals.', tint: 'rgba(239,68,68,0.1)',  color: '#ef4444', glow: 'radial-gradient(circle at 30% 20%, rgba(239,68,68,0.07) 0%, transparent 60%)' },
]

const stats = ref([
  { value: '4', label: 'Open-Source LLMs' },
  { value: 'v2.0', label: 'Version' },
  { value: 'HCN', label: 'Architecture' },
  { value: 'TRIPOD-LLM', label: 'Compliance' },
])

const heroRef = ref<HTMLElement | null>(null)
let reduceMotion = false
let heroRafId: number | null = null
let currentX = 0
let currentY = 0
let targetX = 0
let targetY = 0

function applyHeroVars(x: number, y: number) {
  if (!heroRef.value) return

  heroRef.value.style.setProperty('--hero-tilt-x', `${(-y * 5).toFixed(2)}deg`)
  heroRef.value.style.setProperty('--hero-tilt-y', `${(x * 6).toFixed(2)}deg`)
  heroRef.value.style.setProperty('--hero-glow-x', `${(50 + x * 18).toFixed(2)}%`)
  heroRef.value.style.setProperty('--hero-glow-y', `${(46 + y * 18).toFixed(2)}%`)
}

function animateHeroFrame() {
  currentX += (targetX - currentX) * 0.11
  currentY += (targetY - currentY) * 0.11
  applyHeroVars(currentX, currentY)

  const settled =
    Math.abs(targetX - currentX) < 0.003 &&
    Math.abs(targetY - currentY) < 0.003

  if (settled) {
    heroRafId = null
    return
  }

  heroRafId = requestAnimationFrame(animateHeroFrame)
}

function queueHeroAnimation() {
  if (reduceMotion || heroRafId !== null) return
  heroRafId = requestAnimationFrame(animateHeroFrame)
}

function onHeroPointerMove(event: PointerEvent) {
  if (!heroRef.value || reduceMotion) return

  const rect = heroRef.value.getBoundingClientRect()
  const normalizedX = ((event.clientX - rect.left) / rect.width - 0.5) * 2
  const normalizedY = ((event.clientY - rect.top) / rect.height - 0.5) * 2

  targetX = Math.max(-1, Math.min(1, normalizedX))
  targetY = Math.max(-1, Math.min(1, normalizedY))
  queueHeroAnimation()
}

function onHeroPointerLeave() {
  targetX = 0
  targetY = 0
  queueHeroAnimation()
}

onMounted(async () => {
  if (typeof window !== 'undefined') {
    reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }
  applyHeroVars(0, 0)

  try {
    const health = await apiGet<{ version: string }>('/health')
    stats.value[1] = { value: `v${health.version}`, label: 'Version' }
  } catch {
  }
})

onUnmounted(() => {
  if (heroRafId !== null) {
    cancelAnimationFrame(heroRafId)
  }
})
</script>

<style scoped>
/* ── Animated Background Orbs ───────────────────────── */
.bg-orbs {
  position: fixed;
  inset: 0;
  z-index: -1;
  overflow: hidden;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  will-change: transform;
}

.orb-1 {
  width: 500px; height: 500px;
  top: -10%; right: -5%;
  background: radial-gradient(circle, rgba(139,92,246,0.25) 0%, rgba(192,132,252,0.08) 60%, transparent 80%);
  animation: float-orb 20s ease-in-out infinite;
}
.orb-2 {
  width: 450px; height: 450px;
  bottom: -8%; left: -3%;
  background: radial-gradient(circle, rgba(6,182,212,0.22) 0%, rgba(103,232,249,0.06) 60%, transparent 80%);
  animation: float-orb 25s ease-in-out infinite reverse;
}
.orb-3 {
  width: 300px; height: 300px;
  top: 40%; left: 15%;
  background: radial-gradient(circle, rgba(16,185,129,0.18) 0%, transparent 70%);
  animation: float-orb 18s ease-in-out infinite 3s;
}
.orb-4 {
  width: 250px; height: 250px;
  top: 20%; right: 20%;
  background: radial-gradient(circle, rgba(245,158,11,0.15) 0%, transparent 70%);
  animation: float-orb 22s ease-in-out infinite 7s;
}

@keyframes float-orb {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(30px, -40px) scale(1.05); }
  50% { transform: translate(-20px, 20px) scale(0.95); }
  75% { transform: translate(15px, 30px) scale(1.03); }
}

/* ── Hero — Premium Liquid Glass ───────────────────── */
.hero-liquid {
  --hero-tilt-x: 0deg;
  --hero-tilt-y: 0deg;
  --hero-glow-x: 50%;
  --hero-glow-y: 46%;

  position: relative;
  text-align: center;
  padding: 82px 52px 66px;
  margin: 24px 0 52px;
  border-radius: 30px;
  isolation: isolate;
  background: linear-gradient(
    130deg,
    rgba(255,255,255,0.8) 0%,
    rgba(255,255,255,0.56) 33%,
    rgba(255,255,255,0.68) 70%,
    rgba(255,255,255,0.78) 100%
  );
  -webkit-backdrop-filter: blur(34px) saturate(175%) brightness(1.12);
  backdrop-filter: blur(34px) saturate(175%) brightness(1.12);
  border: 1px solid rgba(255,255,255,0.88);
  box-shadow:
    0 32px 72px rgba(15,23,42,0.12),
    0 12px 28px rgba(14,165,233,0.1),
    inset 0 2px 0 rgba(255,255,255,0.95),
    inset 0 -1px 0 rgba(255,255,255,0.38),
    inset 0 48px 70px -38px rgba(255,255,255,0.44);
  transform: perspective(1400px) rotateX(var(--hero-tilt-x)) rotateY(var(--hero-tilt-y));
  transform-style: preserve-3d;
  will-change: transform;
  transition: border-color 260ms ease, box-shadow 260ms ease;
  overflow: hidden;
}

.hero-liquid:hover {
  border-color: rgba(255,255,255,0.98);
  box-shadow:
    0 38px 82px rgba(15,23,42,0.14),
    0 14px 34px rgba(6,182,212,0.14),
    inset 0 2px 0 rgba(255,255,255,1),
    inset 0 -1px 0 rgba(255,255,255,0.46);
}

.hero-liquid::before {
  content: '';
  position: absolute;
  inset: 1px;
  border-radius: 29px;
  background: radial-gradient(
    circle at var(--hero-glow-x) var(--hero-glow-y),
    rgba(255,255,255,0.44) 0%,
    rgba(255,255,255,0.19) 26%,
    transparent 62%
  );
  pointer-events: none;
  z-index: 0;
}

.hero-liquid::after {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 30px;
  background:
    linear-gradient(
      112deg,
      rgba(103,232,249,0.26) 0%,
      transparent 25%,
      transparent 74%,
      rgba(16,185,129,0.22) 100%
    ),
    linear-gradient(
      286deg,
      rgba(255,255,255,0.48) 0%,
      transparent 30%,
      transparent 72%,
      rgba(148,163,184,0.16) 100%
    );
  mix-blend-mode: screen;
  opacity: 0.74;
  pointer-events: none;
  z-index: 6;
}

.hero-ambient,
.hero-prism,
.hero-caustics,
.hero-noise,
.hero-shimmer,
.hero-refraction {
  position: absolute;
  pointer-events: none;
}

.hero-ambient {
  inset: -46%;
  background: conic-gradient(
    from 0deg at 50% 50%,
    rgba(34,211,238,0.22) 0deg,
    rgba(16,185,129,0.18) 100deg,
    rgba(14,165,233,0.2) 190deg,
    rgba(244,114,182,0.12) 280deg,
    rgba(34,211,238,0.22) 360deg
  );
  filter: blur(72px);
  opacity: 0.56;
  mix-blend-mode: screen;
  animation: hero-ambient-spin 24s linear infinite;
  z-index: 1;
}

.hero-prism {
  inset: -22% -10%;
  background:
    radial-gradient(circle at 16% 24%, rgba(255,255,255,0.56) 0%, transparent 48%),
    radial-gradient(circle at 78% 18%, rgba(14,165,233,0.34) 0%, transparent 56%),
    radial-gradient(circle at 72% 82%, rgba(16,185,129,0.28) 0%, transparent 60%);
  filter: blur(30px);
  opacity: 0.7;
  mix-blend-mode: screen;
  animation: hero-prism-drift 14s ease-in-out infinite alternate;
  z-index: 2;
}

.hero-caustics {
  inset: -14%;
  background:
    radial-gradient(
      circle at var(--hero-glow-x) var(--hero-glow-y),
      rgba(255,255,255,0.58) 0%,
      rgba(255,255,255,0.3) 19%,
      rgba(255,255,255,0.08) 44%,
      transparent 67%
    ),
    repeating-linear-gradient(
      120deg,
      rgba(255,255,255,0.21) 0 2px,
      rgba(255,255,255,0) 2px 13px
    );
  mix-blend-mode: soft-light;
  opacity: 0.52;
  animation: hero-caustic-flow 15s linear infinite;
  z-index: 3;
}

.hero-noise {
  inset: 0;
  opacity: 0.14;
  mix-blend-mode: overlay;
  background-image:
    radial-gradient(circle at 18% 22%, rgba(255,255,255,0.32) 0 0.75px, transparent 0.82px),
    radial-gradient(circle at 70% 44%, rgba(255,255,255,0.3) 0 0.75px, transparent 0.82px),
    radial-gradient(circle at 44% 76%, rgba(255,255,255,0.28) 0 0.7px, transparent 0.78px);
  background-size: 4px 4px, 5px 5px, 6px 6px;
  z-index: 4;
}

.hero-shimmer {
  inset: -12%;
  background: linear-gradient(
    112deg,
    transparent 36%,
    rgba(255,255,255,0.2) 44%,
    rgba(255,255,255,0.58) 50%,
    rgba(255,255,255,0.2) 56%,
    transparent 64%
  );
  background-size: 210% 100%;
  opacity: 0.64;
  animation: hero-shimmer-sweep 6.8s ease-in-out infinite;
  z-index: 5;
}

.hero-refraction {
  inset: 0;
  background:
    linear-gradient(
      90deg,
      transparent 5%,
      rgba(255,255,255,0.94) 36%,
      rgba(255,255,255,0.98) 50%,
      rgba(255,255,255,0.9) 64%,
      transparent 95%
    ) top/100% 1px no-repeat,
    linear-gradient(
      90deg,
      transparent 10%,
      rgba(103,232,249,0.36) 45%,
      rgba(16,185,129,0.3) 55%,
      transparent 90%
    ) bottom/100% 1px no-repeat;
  z-index: 6;
}

@keyframes hero-ambient-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes hero-prism-drift {
  0% { transform: translate3d(-5%, -4%, 0) scale(1); }
  100% { transform: translate3d(6%, 5%, 0) scale(1.08); }
}

@keyframes hero-caustic-flow {
  0% { transform: translateX(0); }
  50% { transform: translateX(2%); }
  100% { transform: translateX(-2%); }
}

@keyframes hero-shimmer-sweep {
  0% { background-position: 220% 0; }
  100% { background-position: -220% 0; }
}

.hero-content {
  position: relative;
  z-index: 7;
  transform: translateZ(34px);
}

.hero-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  border-radius: 999px;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #0f766e;
  background: linear-gradient(
    135deg,
    rgba(255,255,255,0.74) 0%,
    rgba(220,252,255,0.52) 100%
  );
  border: 1px solid rgba(255,255,255,0.78);
  margin-bottom: 28px;
  letter-spacing: 0.01em;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  box-shadow:
    0 4px 14px rgba(14,116,144,0.12),
    inset 0 1px 0 rgba(255,255,255,0.88);
  overflow: hidden;
}

.badge-glow {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 15%,
    rgba(34,211,238,0.2) 50%,
    transparent 85%
  );
  animation: badge-glow-move 3.2s ease-in-out infinite;
}

@keyframes badge-glow-move {
  0%, 100% { transform: translateX(-100%); }
  50% { transform: translateX(100%); }
}

.badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #0ea5e9;
  box-shadow: 0 0 12px rgba(6,182,212,0.52);
  animation: pulse-dot 2.1s ease-in-out infinite;
  flex-shrink: 0;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; box-shadow: 0 0 9px rgba(6,182,212,0.48); }
  50% { opacity: 0.62; box-shadow: 0 0 18px rgba(16,185,129,0.56); }
}

.hero-title {
  font-size: 3.25rem;
  font-weight: 700;
  line-height: 1.08;
  letter-spacing: -0.038em;
  color: var(--text-primary, #1d1d1f);
  margin-bottom: 20px;
  text-shadow: 0 1px 0 rgba(255,255,255,0.72);
}

.hero-gradient {
  background: linear-gradient(120deg, #0284c7 0%, #06b6d4 44%, #10b981 80%, #84cc16 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-desc {
  font-size: 1.1rem;
  line-height: 1.68;
  color: rgba(51,65,85,0.86);
  max-width: 560px;
  margin: 0 auto 40px;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  justify-content: center;
}

/* ── Hero Buttons ───────────────────────────────────── */
.btn-liquid {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 13px 30px;
  border-radius: 16px;
  font-size: 0.9375rem;
  font-weight: 600;
  text-decoration: none;
  letter-spacing: -0.01em;
  overflow: hidden;
  transform: translateZ(0);
  transition: transform 240ms ease, box-shadow 240ms ease, border-color 240ms ease;
  -webkit-backdrop-filter: blur(14px) saturate(150%);
  backdrop-filter: blur(14px) saturate(150%);
}

.btn-liquid:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 3px rgba(129,216,208,0.28),
    0 0 0 6px rgba(139,92,246,0.16);
}

.btn-liquid > * {
  position: relative;
  z-index: 2;
}

.btn-liquid::after {
  content: '';
  position: absolute;
  inset: 1px;
  border-radius: 15px;
  border: 1px solid rgba(255,255,255,0.34);
  pointer-events: none;
}

.btn-primary {
  color: #4c1d95;
  background: linear-gradient(
    145deg,
    var(--btn-frost-bg-strong) 0%,
    var(--btn-frost-bg-soft) 100%
  );
  border: 1px solid rgba(139,92,246,0.56);
  box-shadow:
    0 8px 20px var(--btn-frost-shadow),
    inset 0 1px 0 rgba(255,255,255,0.8),
    inset 0 -1px 0 rgba(255,255,255,0.16),
    inset 0 0 0 1px rgba(139,92,246,0.14);
}

.btn-primary:hover {
  transform: translateY(-2px);
  border-color: rgba(139,92,246,0.72);
  box-shadow:
    0 14px 30px rgba(139,92,246,0.12),
    inset 0 1px 0 rgba(255,255,255,0.9);
}
.btn-primary:active {
  transform: translateY(0);
  border-color: rgba(129,216,208,0.62);
  box-shadow:
    0 10px 24px var(--btn-frost-shadow),
    inset 0 1px 0 rgba(255,255,255,0.36);
}

.btn-secondary {
  color: #155e75;
  background: linear-gradient(
    145deg,
    var(--btn-frost-bg-strong) 0%,
    var(--btn-frost-bg-soft) 100%
  );
  border: 1px solid rgba(129,216,208,0.56);
  box-shadow:
    0 8px 18px var(--btn-frost-shadow),
    inset 0 1px 0 rgba(255,255,255,0.78),
    inset 0 -1px 0 rgba(255,255,255,0.15),
    inset 0 0 0 1px rgba(129,216,208,0.14);
}

.btn-secondary:hover {
  transform: translateY(-2px);
  border-color: rgba(129,216,208,0.72);
  box-shadow:
    0 14px 30px rgba(129,216,208,0.12),
    inset 0 1px 0 rgba(255,255,255,0.88);
}
.btn-secondary:active {
  transform: translateY(0);
  border-color: rgba(139,92,246,0.62);
  box-shadow:
    0 10px 24px var(--btn-frost-shadow),
    inset 0 1px 0 rgba(255,255,255,0.36);
}

.btn-shine {
  position: absolute;
  inset: -2px;
  pointer-events: none;
  z-index: 1;
  background: linear-gradient(
    105deg,
    transparent 35%,
    rgba(255,255,255,0.16) 44%,
    rgba(255,255,255,0.42) 50%,
    rgba(255,255,255,0.16) 56%,
    transparent 65%
  );
  background-size: 290% 100%;
  animation: btn-shine-move 4.2s ease-in-out infinite 1s;
}

@keyframes btn-shine-move {
  0% { background-position: 300% 0; }
  100% { background-position: -300% 0; }
}

.btn-shine-slow {
  animation-duration: 5.4s !important;
  animation-delay: 2.2s !important;
}

/* ── Pipeline — Premium Glass Cards ─────────────────── */
.pipeline {
  padding: 10px 0 48px;
}

.pipeline-header {
  text-align: center;
  margin-bottom: 34px;
}

.pipeline-title {
  font-size: 1.8rem;
  font-weight: 700;
  letter-spacing: -0.032em;
  color: var(--text-primary, #1d1d1f);
  margin-bottom: 10px;
}

.pipeline-sub {
  font-size: 0.98rem;
  color: rgba(71, 85, 105, 0.82);
}

.pipeline-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 18px;
  position: relative;
  align-items: stretch;
}

.pipeline-grid::before {
  content: '';
  position: absolute;
  left: 2%;
  right: 2%;
  top: 74px;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(148, 163, 184, 0.25) 12%,
    rgba(148, 163, 184, 0.2) 88%,
    transparent 100%
  );
  z-index: 0;
}

.step-liquid {
  --step-accent: #8b5cf6;
  --step-tint: rgba(139, 92, 246, 0.12);

  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-height: 236px;
  padding: 22px 18px 18px;
  border-radius: 22px;
  background:
    radial-gradient(
      150% 120% at -6% -15%,
      var(--step-tint) 0%,
      rgba(255, 255, 255, 0) 54%
    ),
    linear-gradient(
      158deg,
      rgba(255,255,255,0.88) 0%,
      rgba(255,255,255,0.6) 52%,
      rgba(255,255,255,0.72) 100%
    );
  -webkit-backdrop-filter: blur(18px) saturate(165%) brightness(1.08);
  backdrop-filter: blur(18px) saturate(165%) brightness(1.08);
  border: 1px solid rgba(255,255,255,0.82);
  text-decoration: none;
  transition:
    transform 320ms cubic-bezier(0.2, 0.8, 0.2, 1),
    border-color 280ms ease,
    box-shadow 320ms ease;
  box-shadow:
    0 8px 22px rgba(15, 23, 42, 0.08),
    0 2px 8px rgba(255,255,255,0.34),
    inset 0 1px 0 rgba(255,255,255,0.94),
    inset 0 -1px 0 rgba(255,255,255,0.28);
  overflow: hidden;
  isolation: isolate;
}

.step-inner-glow {
  position: absolute;
  inset: -28%;
  opacity: 0.4;
  transition: opacity 320ms ease, transform 320ms ease;
  mix-blend-mode: soft-light;
  pointer-events: none;
  z-index: 0;
}

.step-liquid::before {
  content: '';
  position: absolute;
  top: 0;
  left: 12%;
  right: 12%;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255,255,255,0.95) 45%,
    rgba(255,255,255,0.95) 55%,
    transparent 100%
  );
  z-index: 2;
}

.step-liquid::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 16%;
  right: 16%;
  height: 2px;
  border-radius: 2px;
  background: linear-gradient(90deg, transparent, var(--step-accent), transparent);
  opacity: 0.22;
  transition: opacity 280ms ease, left 280ms ease, right 280ms ease;
}

.step-liquid:hover {
  transform: translateY(-10px);
  border-color: rgba(255,255,255,0.96);
  box-shadow:
    0 18px 38px rgba(15, 23, 42, 0.14),
    0 10px 22px var(--step-tint),
    inset 0 2px 0 rgba(255,255,255,1),
    inset 0 -1px 0 rgba(255,255,255,0.4);
}

.step-liquid:hover .step-inner-glow {
  opacity: 0.76;
  transform: scale(1.05);
}

.step-liquid:hover::after {
  opacity: 0.95;
  left: 10%;
  right: 10%;
}

.step-liquid:hover .step-arrow {
  opacity: 1;
  transform: translateX(0);
}

.step-number {
  display: inline-flex;
  align-self: flex-start;
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 0.655rem;
  font-weight: 700;
  color: rgba(71, 85, 105, 0.66);
  letter-spacing: 0.08em;
  margin-bottom: 12px;
  font-variant-numeric: tabular-nums;
  background: rgba(255,255,255,0.54);
  border: 1px solid rgba(255,255,255,0.7);
  position: relative;
  z-index: 3;
}

.step-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.08rem;
  margin-bottom: 14px;
  border: 1px solid rgba(255,255,255,0.5);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.56),
    0 4px 10px rgba(15,23,42,0.08);
  transition: transform 300ms ease, box-shadow 300ms ease;
  position: relative;
  z-index: 3;
}

.step-liquid:hover .step-icon {
  transform: translateY(-2px) scale(1.06);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.64),
    0 8px 16px rgba(15,23,42,0.1);
}

.step-title {
  font-size: 0.95rem;
  font-weight: 650;
  color: var(--text-primary, #1d1d1f);
  margin-bottom: 7px;
  letter-spacing: -0.012em;
  line-height: 1.35;
  position: relative;
  z-index: 3;
}

.step-desc {
  font-size: 0.79rem;
  line-height: 1.62;
  color: rgba(71, 85, 105, 0.8);
  position: relative;
  z-index: 3;
  margin-bottom: auto;
}

.step-arrow {
  margin-top: 14px;
  align-self: flex-end;
  width: 30px;
  height: 30px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.73rem;
  color: var(--step-accent);
  background: rgba(255,255,255,0.62);
  border: 1px solid rgba(255,255,255,0.72);
  opacity: 0.72;
  transform: translateX(-6px);
  transition: all 300ms ease;
  position: relative;
  z-index: 3;
}

/* ── Stats — Floating Glass Capsules ────────────────── */
.stats-float {
  display: flex;
  justify-content: center;
  gap: 14px;
  padding: 8px 0 28px;
}

.stat-capsule {
  text-align: center;
  padding: 22px 36px;
  border-radius: 18px;
  background: linear-gradient(145deg,
    rgba(255,255,255,0.7) 0%,
    rgba(255,255,255,0.45) 100%);
  -webkit-backdrop-filter: blur(18px) saturate(160%) brightness(1.1);
  backdrop-filter: blur(18px) saturate(160%) brightness(1.1);
  border: 1.5px solid rgba(255,255,255,0.85);
  box-shadow:
    0 4px 16px rgba(31,38,135,0.05),
    inset 0 1.5px 0 rgba(255,255,255,0.85),
    inset 0 -1px 0 rgba(255,255,255,0.3);
  min-width: 150px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.stat-capsule:hover {
  transform: translateY(-4px);
  background: linear-gradient(145deg,
    rgba(255,255,255,0.88) 0%,
    rgba(255,255,255,0.65) 100%);
  box-shadow:
    0 12px 32px rgba(31,38,135,0.09),
    inset 0 2px 0 rgba(255,255,255,1);
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary, #1d1d1f);
}

.stat-label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  margin-top: 4px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* ── Responsive ─────────────────────────────────────── */
@media (max-width: 900px) {
  .pipeline-grid::before { display: none; }
  .pipeline-grid { grid-template-columns: repeat(3, 1fr); }
  .step-liquid { min-height: 220px; }
  .stats-float { flex-wrap: wrap; }
}

@media (max-width: 640px) {
  .hero-liquid {
    padding: 48px 24px 40px;
    margin: 12px 0 32px;
    border-radius: 20px;
    transform: none !important;
  }
  .hero-content { transform: none; }
  .hero-ambient, .hero-prism, .hero-caustics { opacity: 0.4; }
  .hero-title { font-size: 2.25rem; }
  .hero-desc { font-size: 1rem; }
  .pipeline-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
  .step-liquid {
    min-height: 0;
    padding: 18px 14px 14px;
    border-radius: 16px;
  }
  .step-number { margin-bottom: 10px; }
  .step-icon { width: 42px; height: 42px; border-radius: 12px; margin-bottom: 12px; }
  .step-title { font-size: 0.88rem; }
  .step-desc { font-size: 0.76rem; line-height: 1.58; }
  .step-arrow { width: 26px; height: 26px; border-radius: 8px; margin-top: 12px; }
  .stats-float { gap: 8px; }
  .stat-capsule { min-width: 0; flex: 1; padding: 16px 12px; }
  .orb { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .hero-liquid {
    transform: none !important;
    transition: none !important;
  }
  .hero-content {
    transform: none;
  }
  .hero-ambient,
  .hero-prism,
  .hero-caustics,
  .hero-shimmer,
  .badge-glow,
  .badge-dot,
  .btn-shine {
    animation: none !important;
  }
}
</style>
