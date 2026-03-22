<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Literature Screening</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Select a screening stage to begin.</p>

    <div class="glass-card">
      <div class="screening-stage-grid">
        <!-- TI/AB Card -->
        <router-link to="/screening/ta" class="stage-card stage-card--ta">
          <div class="stage-card-glow stage-card-glow--ta"></div>
          <div class="stage-card-content">
            <div class="stage-card-top">
              <div class="stage-card-icon stage-card-icon--ta">
                <i class="fas fa-file-lines"></i>
              </div>
              <div class="stage-card-badge">Step 1</div>
            </div>
            <h2 class="stage-card-title">Title / Abstract</h2>
            <p class="stage-card-desc">
              Screen papers by title and abstract using multi-LLM consensus.
              Upload search exports from PubMed, Scopus, or other databases.
            </p>
            <div class="stage-card-divider"></div>
            <div class="stage-card-steps">
              <div class="stage-step">
                <div class="stage-step-dot"></div>
                <span>Select Criteria</span>
              </div>
              <div class="stage-step">
                <div class="stage-step-dot"></div>
                <span>Upload RIS / BibTeX / CSV</span>
              </div>
              <div class="stage-step">
                <div class="stage-step-dot"></div>
                <span>Run HCN Pipeline</span>
              </div>
            </div>
            <div class="stage-card-footer">
              <span class="stage-card-cta">Get started <i class="fas fa-arrow-right"></i></span>
            </div>
          </div>
        </router-link>

        <!-- Vertical divider -->
        <div class="stage-divider"></div>

        <!-- FT Card -->
        <router-link to="/screening/ft" class="stage-card stage-card--ft">
          <div class="stage-card-glow stage-card-glow--ft"></div>
          <div class="stage-card-content">
            <div class="stage-card-top">
              <div class="stage-card-icon stage-card-icon--ft">
                <i class="fas fa-file-pdf"></i>
              </div>
              <div class="stage-card-badge">Step 2</div>
            </div>
            <h2 class="stage-card-title">Full-Text</h2>
            <p class="stage-card-desc">
              Deep screening of PDF full-texts with automatic section detection
              and intelligent chunking for long documents.
            </p>
            <div class="stage-card-divider"></div>
            <div class="stage-card-steps">
              <div class="stage-step">
                <div class="stage-step-dot"></div>
                <span>Select Criteria</span>
              </div>
              <div class="stage-step">
                <div class="stage-step-dot"></div>
                <span>Upload PDFs</span>
              </div>
              <div class="stage-step">
                <div class="stage-step-dot"></div>
                <span>Run FT Pipeline</span>
              </div>
            </div>
            <div class="stage-card-footer">
              <span class="stage-card-cta">Get started <i class="fas fa-arrow-right"></i></span>
            </div>
          </div>
        </router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.screening-stage-grid {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 0;
  align-items: stretch;
}
@media (max-width: 700px) {
  .screening-stage-grid { grid-template-columns: 1fr; }
  .stage-divider { display: none; }
}

/* ── Vertical Divider ──────────────────── */
.stage-divider {
  width: 1px;
  margin: 1rem 0;
  background: linear-gradient(180deg, transparent 0%, rgba(255,255,255,0.12) 30%, rgba(255,255,255,0.12) 70%, transparent 100%);
}

/* ── Card ──────────────────────────────── */
.stage-card {
  position: relative;
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  overflow: hidden;
  text-decoration: none;
  color: inherit;
  border: 1px solid transparent;
  background: transparent;
  margin: 0 0.75rem;
  transition: border-color 0.25s, transform 0.25s, box-shadow 0.25s;
}
.stage-card:hover {
  border-color: rgba(139,92,246,0.2);
  background: rgba(255,255,255,0.015);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(139,92,246,0.06);
}

/* ── Ambient glow ──────────────────────── */
.stage-card-glow {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.35s;
  pointer-events: none;
}
.stage-card:hover .stage-card-glow { opacity: 1; }
.stage-card-glow--ta {
  background: radial-gradient(ellipse at 20% 0%, rgba(6,182,212,0.08) 0%, transparent 65%);
}
.stage-card-glow--ft {
  background: radial-gradient(ellipse at 20% 0%, rgba(139,92,246,0.08) 0%, transparent 65%);
}

/* ── Content ───────────────────────────── */
.stage-card-content {
  position: relative;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.stage-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.stage-card-icon {
  width: 44px; height: 44px;
  border-radius: 11px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.15rem;
}
.stage-card-icon--ta {
  background: rgba(6,182,212,0.12);
  color: #67d2df;
}
.stage-card-icon--ft {
  background: rgba(139,92,246,0.12);
  color: #a78bfa;
}
.stage-card-badge {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  color: var(--text-secondary, #999);
}

/* ── Typography ────────────────────────── */
.stage-card-title {
  font-size: 1.15rem;
  font-weight: 700;
  margin: 0 0 0.5rem 0;
}
.stage-card-desc {
  font-size: 0.82rem;
  color: var(--text-secondary, #999);
  line-height: 1.55;
  margin: 0;
  flex: 1;
}

/* ── Divider ───────────────────────────── */
.stage-card-divider {
  height: 1px;
  margin: 1rem 0;
  background: linear-gradient(90deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.03) 100%);
}

/* ── Steps ─────────────────────────────── */
.stage-card-steps {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-bottom: 1rem;
  flex: 1;
}
.stage-step {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.78rem;
  color: var(--text-secondary, #999);
}
.stage-step-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(139,92,246,0.4);
  flex-shrink: 0;
}

/* ── Footer CTA ────────────────────────── */
.stage-card-footer {
  display: flex;
  justify-content: flex-end;
}
.stage-card-cta {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--primary-purple, #8b5cf6);
  opacity: 0.6;
  transition: opacity 0.2s, gap 0.2s;
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.stage-card:hover .stage-card-cta {
  opacity: 1;
  gap: 0.55rem;
}
</style>
