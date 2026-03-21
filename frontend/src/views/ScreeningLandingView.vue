<template>
  <div>
    <h1 class="page-title" style="margin-bottom: 0.25rem;">Literature Screening</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Select a screening stage to begin.</p>

    <div class="glass-card">
      <div class="screening-stage-grid">
        <router-link to="/screening/ta" class="glass-section screening-stage-link">
          <div class="stage-card-icon">
            <i class="fas fa-file-lines"></i>
          </div>
          <h2 class="stage-card-title">Title / Abstract</h2>
          <p class="stage-card-desc">
            Upload search results (RIS, BibTeX, CSV, XML) and screen papers
            based on their title and abstract using multi-LLM consensus.
          </p>
          <div class="stage-card-steps">
            <span><i class="fas fa-list-check"></i> Select Criteria</span>
            <span><i class="fas fa-upload"></i> Upload Records</span>
            <span><i class="fas fa-robot"></i> Run HCN Pipeline</span>
          </div>
          <div class="stage-card-arrow"><i class="fas fa-arrow-right"></i></div>
        </router-link>

        <router-link to="/screening/ft" class="glass-section screening-stage-link">
          <div class="stage-card-icon">
            <i class="fas fa-file-pdf"></i>
          </div>
          <h2 class="stage-card-title">Full-Text</h2>
          <p class="stage-card-desc">
            Upload PDF full-texts of papers that passed title/abstract screening.
            Deep screening with automatic chunking for long documents.
          </p>
          <div class="stage-card-steps">
            <span><i class="fas fa-list-check"></i> Select Criteria</span>
            <span><i class="fas fa-file-pdf"></i> Upload PDFs</span>
            <span><i class="fas fa-robot"></i> Run FT Pipeline</span>
          </div>
          <div class="stage-card-arrow"><i class="fas fa-arrow-right"></i></div>
        </router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.screening-stage-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}
@media (max-width: 700px) {
  .screening-stage-grid { grid-template-columns: 1fr; }
}
.screening-stage-link {
  position: relative;
  display: flex;
  flex-direction: column;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  transition: border-color 0.2s, transform 0.2s;
}
.screening-stage-link:hover {
  border-color: rgba(139, 92, 246, 0.5);
  transform: translateY(-2px);
}
.stage-card-icon {
  width: 48px; height: 48px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.3rem;
  background: rgba(139, 92, 246, 0.12);
  color: var(--primary-purple, #8b5cf6);
  margin-bottom: 1rem;
}
.stage-card-title { font-size: 1.2rem; font-weight: 700; margin: 0 0 0.5rem 0; }
.stage-card-desc {
  font-size: 0.85rem; color: var(--text-secondary, #999);
  margin: 0 0 1rem 0; line-height: 1.5; flex: 1;
}
.stage-card-steps {
  display: flex; flex-direction: column; gap: 0.3rem;
  font-size: 0.78rem; color: var(--text-secondary, #999);
}
.stage-card-steps span { display: flex; align-items: center; gap: 0.4rem; }
.stage-card-steps i {
  width: 16px; text-align: center;
  color: var(--primary-purple, #8b5cf6); font-size: 0.7rem;
}
.stage-card-arrow {
  position: absolute; top: 50%; right: 1.25rem;
  transform: translateY(-50%);
  font-size: 1.1rem; color: var(--text-secondary, #999);
  opacity: 0; transition: opacity 0.2s, transform 0.2s;
}
.screening-stage-link:hover .stage-card-arrow {
  opacity: 1; transform: translateY(-50%) translateX(4px);
}
</style>
