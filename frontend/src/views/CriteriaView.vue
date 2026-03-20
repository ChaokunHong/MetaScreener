<template>
  <div class="criteria-page">
    <!-- API Key Setup Modal -->
    <Teleport to="body">
      <div v-if="showApiModal" class="modal-overlay" @click.self="showApiModal = false">
        <div class="modal-glass">
          <div class="modal-header">
            <div class="modal-header-title">
              <div class="modal-header-icon"><i class="fas fa-key"></i></div>
              <h3>API Key Required</h3>
            </div>
            <button class="modal-close-btn" @click="showApiModal = false"><i class="fas fa-times"></i></button>
          </div>
          <div class="modal-body">
            <p class="modal-subtitle">MetaScreener uses open-source LLMs via OpenRouter. A free API key takes under 2 minutes to set up.</p>
            <div class="modal-steps">
              <div class="modal-step-item">
                <div class="modal-step-num">1</div>
                <div class="modal-step-text">Visit <strong>openrouter.ai</strong> and create a free account</div>
              </div>
              <div class="modal-step-item">
                <div class="modal-step-num">2</div>
                <div class="modal-step-text">Go to <strong>Keys</strong> and click <strong>Create Key</strong></div>
              </div>
              <div class="modal-step-item">
                <div class="modal-step-num">3</div>
                <div class="modal-step-text">Copy your key and save it in <strong>Settings</strong></div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showApiModal = false">I'll do it later</button>
            <router-link to="/settings" class="btn btn-primary" @click="showApiModal = false">
              <i class="fas fa-cog"></i> Open Settings
            </router-link>
          </div>
        </div>
      </div>
    </Teleport>

    <h1 class="page-title" style="margin-bottom: 0.25rem;">Define Criteria</h1>
    <p class="text-muted" style="margin-bottom: 1.5rem;">Set up inclusion and exclusion criteria for your systematic review screening.</p>

    <!-- ═══════ MODE SELECTOR (before editor is shown) ═══════ -->
    <div v-if="!generatedCriteria" class="glass-card">
      <div class="section-title"><i class="fas fa-filter"></i> How would you like to define criteria?</div>

      <div class="criteria-mode-grid">
        <button
          class="criteria-mode-card"
          :class="{ active: mode === 'ai' }"
          @click="mode = 'ai'"
        >
          <div class="criteria-mode-icon"><i class="fas fa-wand-magic-sparkles"></i></div>
          <div class="criteria-mode-name">AI-Assisted</div>
          <div class="criteria-mode-desc">Describe your topic and let AI detect the framework and generate criteria automatically</div>
          <span class="criteria-mode-badge recommended">Recommended</span>
        </button>

        <button
          class="criteria-mode-card"
          :class="{ active: mode === 'manual' }"
          @click="mode = 'manual'"
        >
          <div class="criteria-mode-icon"><i class="fas fa-pen-to-square"></i></div>
          <div class="criteria-mode-name">Manual Entry</div>
          <div class="criteria-mode-desc">Choose a framework (PICO, PEO, SPIDER, etc.) and add terms yourself</div>
        </button>

        <button
          class="criteria-mode-card"
          :class="{ active: mode === 'import' }"
          @click="mode = 'import'"
        >
          <div class="criteria-mode-icon"><i class="fas fa-file-import"></i></div>
          <div class="criteria-mode-name">Import File</div>
          <div class="criteria-mode-desc">Upload a previously exported criteria file (JSON) from a past session</div>
        </button>
      </div>
    </div>

    <!-- ═══════ AI-ASSISTED MODE ═══════ -->
    <div v-if="!generatedCriteria && mode === 'ai'" class="glass-card">
      <div class="section-title"><i class="fas fa-wand-magic-sparkles"></i> Generate from Research Topic</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Describe what your systematic review is about. The AI will generate structured inclusion and exclusion criteria that you can review and edit.
      </p>

      <!-- Model Count Selector -->
      <div style="display:flex;gap:0.75rem;margin-bottom:1rem;align-items:center;">
        <button
          class="btn btn-sm"
          :class="selectedModelCount === 2 ? 'btn-primary' : 'btn-secondary'"
          @click="selectedModelCount = 2"
        >
          <i class="fas fa-bolt"></i> Fast (2 models)
        </button>
        <button
          class="btn btn-sm"
          :class="selectedModelCount === 4 ? 'btn-primary' : 'btn-secondary'"
          @click="selectedModelCount = 4"
        >
          <i class="fas fa-microscope"></i> Thorough (4 models)
        </button>
        <span style="font-size:0.8rem;opacity:0.7;">
          {{ selectedModelCount === 2 ? '~15-30s' : '~30-60s' }}
        </span>
      </div>

      <div class="form-group" style="margin-bottom: 0.75rem;">
        <label class="form-label">Your research topic</label>
        <textarea
          v-model="topicText"
          class="form-control"
          rows="3"
          placeholder="e.g. Effectiveness of cognitive behavioural therapy for treating depression in adolescents compared to pharmacotherapy"
        ></textarea>
      </div>

      <!-- PICO guide -->
      <div class="pico-guide">
        <div class="pico-guide-title"><i class="fas fa-lightbulb"></i> Try to include these elements:</div>
        <div class="pico-guide-items">
          <div class="pico-guide-item">
            <span class="pico-letter">P</span>
            <div>
              <div class="pico-item-label">Population</div>
              <div class="pico-item-example">Who are you studying? e.g. "adult ICU patients"</div>
            </div>
          </div>
          <div class="pico-guide-item">
            <span class="pico-letter">I</span>
            <div>
              <div class="pico-item-label">Intervention</div>
              <div class="pico-item-example">What treatment or exposure? e.g. "carbapenems"</div>
            </div>
          </div>
          <div class="pico-guide-item">
            <span class="pico-letter pico-letter-optional">C</span>
            <div>
              <div class="pico-item-label">Comparator <span class="pico-optional-tag">optional</span></div>
              <div class="pico-item-example">Compared to what? e.g. "placebo", "standard care"</div>
            </div>
          </div>
          <div class="pico-guide-item">
            <span class="pico-letter">O</span>
            <div>
              <div class="pico-item-label">Outcome</div>
              <div class="pico-item-example">What are you measuring? e.g. "mortality", "resistance rates"</div>
            </div>
          </div>
        </div>
      </div>

      <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-top: 1.25rem;">
        <button
          class="btn btn-primary"
          :disabled="generatingCriteria || !topicText.trim()"
          @click="doGenerateCriteria"
        >
          <i v-if="generatingCriteria" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-wand-magic-sparkles"></i>
          <span v-if="generatingCriteria">Generating criteria...</span>
          <span v-else>Generate Criteria</span>
        </button>
        <span v-if="generatingCriteria" class="text-muted" style="font-size: 0.8rem;">
          This takes 15-30 seconds
        </span>
      </div>

      <div v-if="criteriaError" class="alert alert-danger" style="margin-top: 0.75rem;">
        {{ criteriaError }}
      </div>
    </div>

    <!-- ═══════ GENERATION PROGRESS & LOG ═══════ -->
    <div v-if="generatingCriteria || (criteriaGenLog && !generatedCriteria)" class="glass-card">
      <div class="section-title"><i class="fas fa-spinner fa-spin"></i> Generating Criteria</div>
      <div style="margin-bottom: 1rem;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 0.4rem;">
          <span class="text-muted">{{ criteriaGenStatus }}</span>
          <span class="text-muted">{{ criteriaGenProgress }}%</span>
        </div>
        <div class="progress">
          <div class="progress-bar" :style="{ width: criteriaGenProgress + '%' }"></div>
        </div>
        <div class="progress-log" ref="criteriaLogEl" style="margin-top: 0.75rem; max-height: 240px;">{{ criteriaGenLog }}</div>
      </div>
    </div>

    <!-- ═══════ MANUAL ENTRY MODE ═══════ -->
    <div v-if="!generatedCriteria && mode === 'manual'" class="glass-card">
      <div class="section-title"><i class="fas fa-pen-to-square"></i> Manual Criteria Entry</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Choose your framework, then add inclusion and exclusion terms for each element. Click <strong>+ Add</strong> to add terms, press Enter to confirm.
      </p>

      <!-- Framework selector + research question row -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.25rem;">
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label">Framework</label>
          <select v-model="selectedFramework" class="form-control" @change="onFrameworkChange">
            <option v-for="fw in frameworkOptions" :key="fw.value" :value="fw.value">{{ fw.label }}</option>
          </select>
        </div>
        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-label">Research question <span style="color: var(--text-secondary); font-weight: 400;">(optional)</span></label>
          <input
            v-model="manualResearchQuestion"
            class="form-control"
            placeholder="e.g. Does CBT reduce depression symptoms in adolescents?"
          />
        </div>
      </div>

      <!-- Framework description hint -->
      <div v-if="frameworkHint" class="pico-guide" style="padding: 0.75rem 1rem; margin-bottom: 1.25rem;">
        <div class="pico-guide-title" style="margin-bottom: 0;"><i class="fas fa-circle-info"></i> {{ frameworkHint }}</div>
      </div>

      <!-- Dynamic element cards -->
      <div class="criteria-elements-editor">
        <div
          v-for="elem in activeElements"
          :key="elem.key"
          class="criteria-element-editor-card"
        >
          <div class="criteria-element-name">
            <span class="pico-letter" style="font-size: 0.7rem; width: 20px; height: 20px; line-height: 20px; margin-right: 0.4rem;">{{ elem.letter }}</span>
            {{ elem.label }}
            <span v-if="elem.optional" class="pico-optional-tag" style="margin-left: 0.4rem;">optional</span>
          </div>

          <!-- Include row -->
          <div class="criteria-editor-row">
            <span class="criteria-term-label include">Include</span>
            <div class="criteria-chips-wrap">
              <span v-for="(term, idx) in manualElements[elem.key]?.include" :key="idx" class="criteria-chip include editable">
                {{ term }}
                <button class="chip-remove" @click="manualElements[elem.key]?.include.splice(idx, 1)" title="Remove">&times;</button>
              </span>
              <button v-if="!(addingTerm?.key === elem.key && addingTerm?.type === 'include')" class="add-chip-btn" @click="startAdd(elem.key, 'include')">
                <i class="fas fa-plus"></i> Add
              </button>
              <input
                v-if="addingTerm?.key === elem.key && addingTerm?.type === 'include'"
                ref="addTermInput"
                v-model="newTermText"
                class="add-chip-input"
                placeholder="Type term, Enter to add"
                @keyup.enter="confirmAdd(elem.key, 'include')"
                @keyup.esc="cancelAdd"
                @blur="cancelAdd"
              />
            </div>
          </div>

          <!-- Exclude row -->
          <div class="criteria-editor-row">
            <span class="criteria-term-label exclude">Exclude</span>
            <div class="criteria-chips-wrap">
              <span v-for="(term, idx) in manualElements[elem.key]?.exclude" :key="idx" class="criteria-chip exclude editable">
                {{ term }}
                <button class="chip-remove" @click="manualElements[elem.key]?.exclude.splice(idx, 1)" title="Remove">&times;</button>
              </span>
              <button v-if="!(addingTerm?.key === elem.key && addingTerm?.type === 'exclude')" class="add-chip-btn" @click="startAdd(elem.key, 'exclude')">
                <i class="fas fa-plus"></i> Add
              </button>
              <input
                v-if="addingTerm?.key === elem.key && addingTerm?.type === 'exclude'"
                ref="addTermInput"
                v-model="newTermText"
                class="add-chip-input"
                placeholder="Type term, Enter to add"
                @keyup.enter="confirmAdd(elem.key, 'exclude')"
                @keyup.esc="cancelAdd"
                @blur="cancelAdd"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Custom: add new element -->
      <div v-if="selectedFramework === 'custom'" style="margin-bottom: 1rem;">
        <div v-if="!addingCustomElement" style="display: flex; align-items: center; gap: 0.5rem;">
          <button class="btn btn-secondary btn-sm" @click="addingCustomElement = true">
            <i class="fas fa-plus"></i> Add Element
          </button>
          <span class="text-muted" style="font-size: 0.78rem;">Define your own criteria elements</span>
        </div>
        <div v-else style="display: flex; align-items: center; gap: 0.5rem;">
          <input
            ref="customElementInput"
            v-model="customElementName"
            class="form-control"
            style="max-width: 240px; padding: 0.4rem 0.75rem; font-size: 0.85rem;"
            placeholder="Element name (e.g. Setting)"
            @keyup.enter="confirmCustomElement"
            @keyup.esc="addingCustomElement = false"
          />
          <button class="btn btn-primary btn-sm" @click="confirmCustomElement" :disabled="!customElementName.trim()">
            <i class="fas fa-check"></i>
          </button>
          <button class="btn btn-secondary btn-sm" @click="addingCustomElement = false">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>

      <!-- ── Manual Mode: Screening Filters ── -->
      <div class="screening-filters-section" style="margin-top: 1.25rem;">
        <div class="section-subtitle"><i class="fas fa-sliders"></i> Screening Filters <span class="pico-optional-tag" style="margin-left: 0.4rem;">optional</span></div>
        <p class="text-muted" style="font-size: 0.8rem; margin-bottom: 0.75rem;">
          Papers matching these filters are automatically excluded during screening.
        </p>

        <!-- Publication type exclude -->
        <div class="filter-row">
          <label class="filter-label"><i class="fas fa-file-lines"></i> Excluded Publication Types</label>
          <div class="criteria-chips-wrap">
            <span v-for="(pt, idx) in editPubTypeExclude" :key="idx" class="criteria-chip exclude editable">
              {{ pt }}
              <button class="chip-remove" @click="removePubType(idx)" title="Remove">&times;</button>
            </span>
            <button v-if="!addingPubType" class="add-chip-btn" @click="startAddPubType">
              <i class="fas fa-plus"></i> Add
            </button>
            <input
              v-if="addingPubType"
              ref="pubTypeInput"
              v-model="newPubTypeText"
              class="add-chip-input"
              placeholder="e.g. case_report"
              @keyup.enter="confirmPubType"
              @keyup.esc="addingPubType = false"
              @blur="confirmPubType"
            />
          </div>
        </div>

        <!-- Language restriction -->
        <div class="filter-row">
          <label class="filter-label"><i class="fas fa-language"></i> Language Restriction</label>
          <div class="criteria-chips-wrap">
            <span v-for="(lang, idx) in editLanguageRestriction" :key="idx" class="criteria-chip include editable">
              {{ lang }}
              <button class="chip-remove" @click="removeLang(idx)" title="Remove">&times;</button>
            </span>
            <button v-if="!addingLang" class="add-chip-btn" @click="startAddLang">
              <i class="fas fa-plus"></i> Add
            </button>
            <input
              v-if="addingLang"
              ref="langInput"
              v-model="newLangText"
              class="add-chip-input"
              placeholder="e.g. en, zh, es"
              @keyup.enter="confirmLang"
              @keyup.esc="addingLang = false"
              @blur="confirmLang"
            />
          </div>
          <span v-if="editLanguageRestriction.length === 0" class="text-muted" style="font-size: 0.75rem; margin-left: 0.5rem;">
            All languages accepted
          </span>
        </div>

        <!-- Date range -->
        <div class="filter-row">
          <label class="filter-label"><i class="fas fa-calendar-range"></i> Date Range</label>
          <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
            <input
              v-model="editDateFrom"
              class="form-control form-control-sm"
              style="max-width: 140px;"
              type="text"
              placeholder="From (e.g. 2015)"
            />
            <span class="text-muted">to</span>
            <input
              v-model="editDateTo"
              class="form-control form-control-sm"
              style="max-width: 140px;"
              type="text"
              placeholder="To (e.g. 2024)"
            />
            <span v-if="!editDateFrom && !editDateTo" class="text-muted" style="font-size: 0.75rem;">
              No date restriction
            </span>
          </div>
        </div>
      </div>

      <div style="display: flex; align-items: center; gap: 0.75rem; margin-top: 0.75rem;">
        <button
          class="btn btn-primary"
          :disabled="!hasAnyManualTerms"
          @click="applyManualCriteria"
        >
          <i class="fas fa-check"></i> Review Criteria
        </button>
        <span v-if="!hasAnyManualTerms" class="text-muted" style="font-size: 0.8rem;">
          Add at least one include or exclude term to continue
        </span>
      </div>

      <div v-if="criteriaError" class="alert alert-danger" style="margin-top: 0.75rem;">
        {{ criteriaError }}
      </div>
    </div>

    <!-- ═══════ IMPORT FILE MODE ═══════ -->
    <div v-if="!generatedCriteria && mode === 'import'" class="glass-card">
      <div class="section-title"><i class="fas fa-file-import"></i> Import Criteria File</div>
      <p class="text-muted" style="margin-bottom: 1rem;">
        Upload a criteria file exported from a previous MetaScreener session. Supports JSON format.
      </p>

      <div class="form-group" style="margin-bottom: 1rem;">
        <label class="form-label">Select criteria file</label>
        <input ref="importFileInput" type="file" accept=".json,.yaml,.yml" class="form-control" style="padding: 0.5rem;" @change="onImportFile" />
      </div>

      <div v-if="importedContent">
        <div class="alert alert-success" style="margin-bottom: 0.75rem;">
          <i class="fas fa-check-circle"></i> File loaded successfully. Click below to review.
        </div>
        <button class="btn btn-primary" @click="doApplyImported">
          <i class="fas fa-eye"></i> Review Imported Criteria
        </button>
      </div>

      <div v-if="criteriaError" class="alert alert-danger" style="margin-top: 0.75rem;">
        {{ criteriaError }}
      </div>
    </div>

    <!-- ═══════ CRITERIA EDITOR (shared by all modes) ═══════ -->
    <div v-if="generatedCriteria" class="glass-card">
      <div class="section-title"><i class="fas fa-filter"></i> Review & Edit Criteria</div>

      <div class="criteria-editor">
        <div class="criteria-editor-header">
          <span class="criteria-framework-badge">{{ generatedCriteria.framework?.toUpperCase() }}</span>
          <span v-if="generatedCriteria.detected_language" class="criteria-lang-badge">
            <i class="fas fa-language"></i> {{ generatedCriteria.detected_language.toUpperCase() }}
          </span>
          <span v-if="generatedCriteria.research_question" class="criteria-rq">
            {{ generatedCriteria.research_question }}
          </span>
        </div>

        <div class="criteria-editor-note">
          <i class="fas fa-circle-check" style="color: #059669;"></i>
          Review and refine below, then confirm to proceed to screening.
        </div>

        <!-- Missing elements warning -->
        <div v-if="missingRequiredElements.length > 0" class="criteria-missing-warning">
          <i class="fas fa-triangle-exclamation"></i>
          Missing required elements: <strong>{{ missingRequiredElements.map(k => capitalise(k.replace(/_/g, ' '))).join(', ') }}</strong>.
          Click "AI Suggest" on each to generate terms.
        </div>

        <!-- Editable element cards -->
        <div class="criteria-elements-editor">
          <div
            v-for="(elem, key) in editableCriteria.elements"
            :key="key"
            class="criteria-element-editor-card"
          >
            <div class="criteria-element-name">
              {{ capitalise(String(elem.name || key)) }}
              <span v-if="elem.element_quality != null"
                    :class="['quality-badge',
                             elem.element_quality >= 70 ? 'quality-high' :
                             elem.element_quality >= 40 ? 'quality-mid' : 'quality-low']">
                {{ elem.element_quality >= 70 ? 'High quality' :
                   elem.element_quality >= 40 ? 'Review recommended' : 'Needs attention' }}
              </span>
            </div>

            <!-- Include row -->
            <div class="criteria-editor-row">
              <span class="criteria-term-label include">Include</span>
              <div class="criteria-chips-wrap">
                <span v-for="(term, idx) in elem.include" :key="idx" class="criteria-chip include editable">
                  {{ term }}
                  <span v-if="meshResults[term]" style="margin-left:0.25rem;">
                    <i v-if="meshResults[term].is_valid" class="fas fa-check-circle" style="color:#22c55e;font-size:0.65rem;" title="Valid MeSH heading"></i>
                    <span v-else>
                      <i class="fas fa-exclamation-triangle" style="color:#f59e0b;font-size:0.65rem;"
                        :title="meshResults[term].suggested_mesh
                          ? `Not MeSH. Suggested: ${meshResults[term].suggested_mesh}`
                          : 'Not a recognized MeSH heading'"
                      ></i>
                      <button
                        v-if="meshResults[term].suggested_mesh"
                        style="background:none;border:none;cursor:pointer;color:#f59e0b;font-size:0.6rem;text-decoration:underline;padding:0 0.15rem;"
                        @click="replaceMeshTerm(String(key), term, meshResults[term].suggested_mesh!)"
                      >Replace</button>
                    </span>
                  </span>
                  <button class="chip-remove" @click="removeTerm(String(key), 'include', idx)" title="Remove">&times;</button>
                </span>
                <button v-if="!(addingTerm?.key === key && addingTerm?.type === 'include')" class="add-chip-btn" @click="startAdd(String(key), 'include')">
                  <i class="fas fa-plus"></i> Add
                </button>
                <input
                  v-if="addingTerm?.key === key && addingTerm?.type === 'include'"
                  ref="addTermInput"
                  v-model="newTermText"
                  class="add-chip-input"
                  placeholder="Type term, Enter to add"
                  @keyup.enter="confirmAdd(String(key), 'include')"
                  @keyup.esc="cancelAdd"
                  @blur="cancelAdd"
                />
              </div>
            </div>

            <!-- Exclude row -->
            <div class="criteria-editor-row">
              <span class="criteria-term-label exclude">Exclude</span>
              <div class="criteria-chips-wrap">
                <span v-for="(term, idx) in elem.exclude" :key="idx" class="criteria-chip exclude editable">
                  {{ term }}
                  <button class="chip-remove" @click="removeTerm(String(key), 'exclude', idx)" title="Remove">&times;</button>
                </span>
                <button v-if="!(addingTerm?.key === key && addingTerm?.type === 'exclude')" class="add-chip-btn" @click="startAdd(String(key), 'exclude')">
                  <i class="fas fa-plus"></i> Add
                </button>
                <input
                  v-if="addingTerm?.key === key && addingTerm?.type === 'exclude'"
                  ref="addTermInput"
                  v-model="newTermText"
                  class="add-chip-input"
                  placeholder="Type term, Enter to add"
                  @keyup.enter="confirmAdd(String(key), 'exclude')"
                  @keyup.esc="cancelAdd"
                  @blur="cancelAdd"
                />
              </div>
            </div>

            <!-- AI Suggest Button -->
            <button
              class="btn btn-secondary btn-sm"
              style="margin-top:0.5rem;"
              :disabled="suggestLoading[String(key)]"
              @click="suggestTerms(String(key), String(elem.name || key))"
            >
              <i :class="suggestLoading[String(key)] ? 'fas fa-spinner fa-spin' : 'fas fa-magic'"></i>
              {{ suggestLoading[String(key)] ? 'Suggesting...' : 'AI Suggest' }}
            </button>

            <!-- Suggestion Chips -->
            <div v-if="suggestions[String(key)]?.length" style="margin-top:0.5rem;display:flex;flex-wrap:wrap;gap:0.4rem;align-items:center;">
              <span
                v-for="s in suggestions[String(key)]"
                :key="s.term"
                :title="s.rationale"
                style="display:inline-flex;align-items:center;gap:0.3rem;padding:0.25rem 0.6rem;border-radius:999px;font-size:0.82rem;background:rgba(129,216,208,0.15);border:1px solid rgba(129,216,208,0.3);backdrop-filter:blur(6px);"
              >
                {{ s.term }}
                <button
                  style="background:none;border:none;cursor:pointer;color:var(--tiffany-green,#81d8d0);font-weight:bold;padding:0.1rem 0.25rem;font-size:0.8rem;"
                  title="Adopt this term"
                  @click="adoptSuggestion(String(key), s.term)"
                >+</button>
                <button
                  style="background:none;border:none;cursor:pointer;opacity:0.5;padding:0.1rem 0.25rem;font-size:0.8rem;"
                  title="Dismiss"
                  @click="dismissSuggestion(String(key), s.term)"
                >&times;</button>
              </span>
              <button
                style="background:none;border:none;cursor:pointer;font-size:0.75rem;opacity:0.6;color:inherit;text-decoration:underline;"
                @click="dismissAllSuggestions(String(key))"
              >Dismiss all</button>
            </div>

            <!-- Ambiguity flags -->
            <div v-if="elem.ambiguity_flags?.length" class="ambiguity-section">
              <details>
                <summary class="ambiguity-toggle">
                  Review flagged items ({{ elem.ambiguity_flags.length }})
                </summary>
                <div class="ambiguity-items">
                  <div v-for="(flag, i) in elem.ambiguity_flags" :key="i" class="ambiguity-item">
                    <span class="ambiguity-text">{{ flag }}</span>
                    <button @click="dismissFlag(String(key), Number(i))" class="btn-sm btn-muted">Dismiss</button>
                  </div>
                </div>
              </details>
            </div>
          </div>
        </div>

        <!-- Pilot Search -->
        <div style="margin-top:2rem;padding-top:1.5rem;border-top:1px solid rgba(255,255,255,0.1);">
          <button class="btn btn-secondary" :disabled="pilotLoading" @click="runPilotSearch">
            <i :class="pilotLoading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
            {{ pilotLoading ? 'Searching PubMed...' : 'Pilot Search' }}
          </button>

          <div v-if="pilotResult" style="margin-top:1rem;">
            <div style="font-size:0.95rem;margin-bottom:0.75rem;">
              Found <strong>{{ pilotResult.search_result.total_hits }}</strong> articles on PubMed
              <a :href="pilotResult.search_result.pubmed_url" target="_blank" style="margin-left:0.5rem;font-size:0.8rem;">
                View on PubMed <i class="fas fa-external-link-alt"></i>
              </a>
            </div>

            <div style="display:flex;flex-direction:column;gap:0.5rem;margin-bottom:1rem;">
              <div
                v-for="(art, idx) in pilotResult.search_result.articles.slice(0, 5)"
                :key="art.pmid"
                style="padding:0.75rem 1rem;border-radius:12px;background:rgba(255,255,255,0.06);backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,0.1);"
              >
                <div style="display:flex;align-items:start;gap:0.5rem;">
                  <i
                    v-if="pilotResult.assessments[idx]"
                    class="fas fa-circle"
                    :style="{ color: pilotResult.assessments[idx].is_relevant ? '#22c55e' : '#ef4444', fontSize: '0.5rem', marginTop: '0.4rem' }"
                    :title="pilotResult.assessments[idx]?.reason || ''"
                  ></i>
                  <div>
                    <div style="font-weight:600;font-size:0.85rem;">{{ art.title }}</div>
                    <div style="font-size:0.75rem;opacity:0.7;">
                      {{ art.authors }} {{ art.year ? `(${art.year})` : '' }} &middot; PMID: {{ art.pmid }}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="pilotResult.estimated_precision !== null && pilotResult.estimated_precision !== undefined"
              style="padding:0.75rem 1rem;border-radius:12px;font-size:0.9rem;"
              :style="{
                background: pilotResult.estimated_precision > 0.8 ? 'rgba(34,197,94,0.1)' :
                            pilotResult.estimated_precision >= 0.5 ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)',
                border: '1px solid ' + (pilotResult.estimated_precision > 0.8 ? 'rgba(34,197,94,0.3)' :
                        pilotResult.estimated_precision >= 0.5 ? 'rgba(245,158,11,0.3)' : 'rgba(239,68,68,0.3)')
              }"
            >
              <strong>Estimated Precision:</strong>
              {{ Math.round(pilotResult.estimated_precision * 100) }}%
              ({{ pilotResult.assessments.filter(a => a.is_relevant).length }}/{{ pilotResult.assessments.length }} relevant)
              <span v-if="pilotResult.estimated_precision < 0.5" style="margin-left:0.5rem;"> — Consider narrowing your criteria</span>
              <span v-else-if="pilotResult.estimated_precision > 0.8" style="margin-left:0.5rem;"> — Good precision</span>
            </div>
            <div v-else-if="pilotResult.assessments.length === 0 && pilotResult.search_result.articles.length > 0"
              style="padding:0.5rem;font-size:0.85rem;opacity:0.6;">
              Could not assess relevance (LLM unavailable)
            </div>
          </div>
        </div>

        <!-- ── Screening Filters ── -->
        <div class="screening-filters-section">
          <div class="section-subtitle"><i class="fas fa-sliders"></i> Screening Filters</div>
          <p class="text-muted" style="font-size: 0.8rem; margin-bottom: 0.75rem;">
            These filters are applied as hard rules during screening. Papers matching these criteria are automatically excluded at Tier 0.
          </p>

          <!-- Publication type exclude -->
          <div class="filter-row">
            <label class="filter-label"><i class="fas fa-file-lines"></i> Excluded Publication Types</label>
            <div class="criteria-chips-wrap">
              <span v-for="(pt, idx) in editPubTypeExclude" :key="idx" class="criteria-chip exclude editable">
                {{ pt }}
                <button class="chip-remove" @click="removePubType(idx)" title="Remove">&times;</button>
              </span>
              <button v-if="!addingPubType" class="add-chip-btn" @click="startAddPubType">
                <i class="fas fa-plus"></i> Add
              </button>
              <input
                v-if="addingPubType"
                ref="pubTypeInput"
                v-model="newPubTypeText"
                class="add-chip-input"
                placeholder="e.g. case_report"
                @keyup.enter="confirmPubType"
                @keyup.esc="addingPubType = false"
                @blur="confirmPubType"
              />
            </div>
          </div>

          <!-- Language restriction -->
          <div class="filter-row">
            <label class="filter-label"><i class="fas fa-language"></i> Language Restriction</label>
            <div class="criteria-chips-wrap">
              <span v-for="(lang, idx) in editLanguageRestriction" :key="idx" class="criteria-chip include editable">
                {{ lang }}
                <button class="chip-remove" @click="removeLang(idx)" title="Remove">&times;</button>
              </span>
              <button v-if="!addingLang" class="add-chip-btn" @click="startAddLang">
                <i class="fas fa-plus"></i> Add
              </button>
              <input
                v-if="addingLang"
                ref="langInput"
                v-model="newLangText"
                class="add-chip-input"
                placeholder="e.g. en, zh, es"
                @keyup.enter="confirmLang"
                @keyup.esc="addingLang = false"
                @blur="confirmLang"
              />
            </div>
            <span v-if="editLanguageRestriction.length === 0" class="text-muted" style="font-size: 0.75rem; margin-left: 0.5rem;">
              All languages accepted
            </span>
          </div>

          <!-- Date range -->
          <div class="filter-row">
            <label class="filter-label"><i class="fas fa-calendar-range"></i> Publication Date Range</label>
            <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
              <input
                v-model="editDateFrom"
                class="form-control form-control-sm"
                style="max-width: 140px;"
                type="text"
                placeholder="From (e.g. 2015)"
              />
              <span class="text-muted">to</span>
              <input
                v-model="editDateTo"
                class="form-control form-control-sm"
                style="max-width: 140px;"
                type="text"
                placeholder="To (e.g. 2024)"
              />
              <span v-if="!editDateFrom && !editDateTo" class="text-muted" style="font-size: 0.75rem;">
                No date restriction
              </span>
            </div>
          </div>
        </div>

        <!-- Editor actions -->
        <div class="criteria-editor-actions">
          <button class="btn btn-primary" @click="confirmCriteria">
            <i class="fas fa-check"></i> Confirm & Save Criteria
          </button>
          <button v-if="sourceMode === 'ai'" class="btn btn-secondary" @click="doRegenerateCriteria" :disabled="generatingCriteria">
            <i v-if="generatingCriteria" class="fas fa-spinner fa-spin"></i>
            <i v-else class="fas fa-rotate"></i>
            Regenerate
          </button>
          <button class="btn btn-secondary" @click="resetCriteriaEditor">
            <i class="fas fa-arrow-left"></i> Start Over
          </button>
        </div>

        <!-- Success banner (after criteria confirmed) -->
        <div v-if="criteriaSaved" class="alert alert-success" style="margin-top: 1rem;">
          <i class="fas fa-check-circle"></i>
          Criteria saved! You can now go to
          <router-link to="/screening" style="color: inherit; font-weight: 600; text-decoration: underline;">Screening</router-link>
          to upload your search results.
        </div>
      </div>

      <div v-if="criteriaError" class="alert alert-danger" style="margin-top: 0.75rem;">
        {{ criteriaError }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted } from 'vue'
import { apiGet, apiPost } from '@/api'
import { useCriteriaStore, type SavedCriteria, type CriteriaElements, type GenerationMeta } from '@/stores/criteria'

const { criteria: savedCriteria, topic: savedTopic, setCriteria, setTopic } = useCriteriaStore()

// ── API Key ────────────────────────────────────────────────
const showApiModal = ref(false)

onMounted(async () => {
  try {
    const s = await apiGet<{ api_keys: { openrouter: string } }>('/settings')
    if (!s.api_keys?.openrouter?.trim()) {
      showApiModal.value = true
    }
  } catch {
    // server might not be running yet
  }

  // Restore from store if criteria were previously saved
  if (savedCriteria.value) {
    generatedCriteria.value = savedCriteria.value
    editableCriteria.value = {
      elements: Object.fromEntries(
        Object.entries(savedCriteria.value.elements).map(([k, v]) => [
          k, {
            name: v.name,
            include: [...v.include],
            exclude: [...v.exclude],
            element_quality: v.element_quality ?? null,
            ambiguity_flags: v.ambiguity_flags ? [...v.ambiguity_flags] : [],
            model_votes: v.model_votes ? { ...v.model_votes } : undefined,
          }
        ])
      )
    }
    loadFiltersFromCriteria(savedCriteria.value)
    sourceMode.value = 'restored'
  }
  if (savedTopic.value) {
    topicText.value = savedTopic.value
  }
})

// ── State ──────────────────────────────────────────────────
type CriteriaMode = 'ai' | 'manual' | 'import'
const mode = ref<CriteriaMode>('ai')
const selectedModelCount = ref<2 | 4>(4)
const sourceMode = ref<'ai' | 'manual' | 'import' | 'restored'>('ai')

const topicText = ref('')
const generatingCriteria = ref(false)
const criteriaError = ref('')
const criteriaSaved = ref(false)

// ── Criteria generation progress simulation ──────────────
const criteriaGenProgress = ref(0)
const criteriaGenStatus = ref('')
const criteriaGenLog = ref('')
const criteriaLogEl = ref<HTMLElement | null>(null)
let criteriaProgressTimer: ReturnType<typeof setInterval> | null = null

const CRITERIA_PROGRESS_STEPS = [
  { time: 0, pct: 5, msg: 'Preprocessing input...' },
  { time: 2000, pct: 15, msg: 'Detecting research framework...' },
  { time: 4000, pct: 30, msg: 'Connecting to LLM backend...' },
  { time: 7000, pct: 45, msg: 'Generating criteria with AI...' },
  { time: 12000, pct: 60, msg: 'Analysing research topic...' },
  { time: 17000, pct: 72, msg: 'Building inclusion / exclusion terms...' },
  { time: 22000, pct: 82, msg: 'Validating criteria quality...' },
  { time: 27000, pct: 90, msg: 'Finalising...' },
]

function startCriteriaProgressSim() {
  criteriaGenProgress.value = 0
  criteriaGenStatus.value = 'Starting wizard...'
  criteriaGenLog.value = ''
  const t0 = Date.now()
  let idx = 0
  criteriaProgressTimer = setInterval(() => {
    const elapsed = Date.now() - t0
    while (idx < CRITERIA_PROGRESS_STEPS.length && elapsed >= CRITERIA_PROGRESS_STEPS[idx].time) {
      const step = CRITERIA_PROGRESS_STEPS[idx]
      criteriaGenProgress.value = step.pct
      criteriaGenStatus.value = step.msg
      criteriaGenLog.value += step.msg + '\n'
      idx++
    }
    nextTick(() => {
      if (criteriaLogEl.value) criteriaLogEl.value.scrollTop = criteriaLogEl.value.scrollHeight
    })
  }, 500)
}

function stopCriteriaProgressSim(success: boolean) {
  if (criteriaProgressTimer) { clearInterval(criteriaProgressTimer); criteriaProgressTimer = null }
  if (success) {
    criteriaGenProgress.value = 100
    criteriaGenStatus.value = 'Complete!'
    criteriaGenLog.value += 'Criteria generated successfully!\n'
  }
}
const importedContent = ref('')
const importFileInput = ref<HTMLInputElement | null>(null)

interface GeneratedCriteria {
  framework: string
  research_question?: string
  detected_language?: string
  elements: CriteriaElements
  study_design_include?: string[]
  study_design_exclude?: string[]
  publication_type_exclude?: string[]
  language_restriction?: string[] | null
  date_from?: string | null
  date_to?: string | null
  generation_meta?: GenerationMeta
}

const generatedCriteria = ref<GeneratedCriteria | null>(null)
const editableCriteria = ref<{ elements: CriteriaElements }>({ elements: {} })
const missingRequiredElements = ref<string[]>([])
const missingOptionalElements = ref<string[]>([])

// ── Screening filters (shared by all modes) ─────────────
const DEFAULT_PUB_TYPE_EXCLUDE = ['review', 'editorial', 'letter', 'comment', 'erratum']

const editPubTypeExclude = ref<string[]>([...DEFAULT_PUB_TYPE_EXCLUDE])
const editLanguageRestriction = ref<string[]>([])
const editDateFrom = ref('')
const editDateTo = ref('')

function loadFiltersFromCriteria(c: GeneratedCriteria) {
  editPubTypeExclude.value = c.publication_type_exclude?.length
    ? [...c.publication_type_exclude]
    : [...DEFAULT_PUB_TYPE_EXCLUDE]
  editLanguageRestriction.value = c.language_restriction?.length
    ? [...c.language_restriction]
    : []
  editDateFrom.value = c.date_from || ''
  editDateTo.value = c.date_to || ''
}

function resetFilters() {
  editPubTypeExclude.value = [...DEFAULT_PUB_TYPE_EXCLUDE]
  editLanguageRestriction.value = []
  editDateFrom.value = ''
  editDateTo.value = ''
}

// Pub type chip helpers
const addingPubType = ref(false)
const newPubTypeText = ref('')
const pubTypeInput = ref<HTMLInputElement | null>(null)

function startAddPubType() {
  addingPubType.value = true
  newPubTypeText.value = ''
  nextTick(() => pubTypeInput.value?.focus())
}
function confirmPubType() {
  const t = newPubTypeText.value.trim().toLowerCase()
  if (t && !editPubTypeExclude.value.includes(t)) {
    editPubTypeExclude.value.push(t)
  }
  addingPubType.value = false
  newPubTypeText.value = ''
}
function removePubType(idx: number) {
  editPubTypeExclude.value.splice(idx, 1)
}

// Language chip helpers
const addingLang = ref(false)
const newLangText = ref('')
const langInput = ref<HTMLInputElement | null>(null)

function startAddLang() {
  addingLang.value = true
  newLangText.value = ''
  nextTick(() => langInput.value?.focus())
}
function confirmLang() {
  const t = newLangText.value.trim().toLowerCase()
  if (t && !editLanguageRestriction.value.includes(t)) {
    editLanguageRestriction.value.push(t)
  }
  addingLang.value = false
  newLangText.value = ''
}
function removeLang(idx: number) {
  editLanguageRestriction.value.splice(idx, 1)
}

// Add-term inline state
const addTermInput = ref<HTMLInputElement | null>(null)
const addingTerm = ref<{ key: string; type: 'include' | 'exclude' } | null>(null)
const newTermText = ref('')

// ── Framework definitions (mirrors backend criteria/frameworks.py) ────
interface FrameworkElement {
  key: string
  letter: string
  label: string
  optional: boolean
}

interface FrameworkDef {
  value: string
  label: string
  hint: string
  elements: FrameworkElement[]
}

const FRAMEWORKS: FrameworkDef[] = [
  {
    value: 'pico', label: 'PICO',
    hint: 'Population, Intervention, Comparison, Outcome — for interventional studies (RCTs, clinical trials)',
    elements: [
      { key: 'population',   letter: 'P', label: 'Population',   optional: false },
      { key: 'intervention', letter: 'I', label: 'Intervention', optional: false },
      { key: 'comparison',   letter: 'C', label: 'Comparison',   optional: true },
      { key: 'outcome',      letter: 'O', label: 'Outcome',      optional: true },
    ],
  },
  {
    value: 'peo', label: 'PEO',
    hint: 'Population, Exposure, Outcome — for observational and epidemiological studies',
    elements: [
      { key: 'population', letter: 'P', label: 'Population', optional: false },
      { key: 'exposure',   letter: 'E', label: 'Exposure',   optional: false },
      { key: 'outcome',    letter: 'O', label: 'Outcome',    optional: true },
    ],
  },
  {
    value: 'peco', label: 'PECO',
    hint: 'Population, Exposure, Comparator, Outcome — for environmental and occupational health studies',
    elements: [
      { key: 'population',  letter: 'P', label: 'Population',  optional: false },
      { key: 'exposure',    letter: 'E', label: 'Exposure',    optional: false },
      { key: 'comparator',  letter: 'C', label: 'Comparator',  optional: true },
      { key: 'outcome',     letter: 'O', label: 'Outcome',     optional: true },
    ],
  },
  {
    value: 'spider', label: 'SPIDER',
    hint: 'Sample, Phenomenon of Interest, Design, Evaluation, Research type — for qualitative/mixed-methods research',
    elements: [
      { key: 'sample',                  letter: 'S', label: 'Sample',                  optional: false },
      { key: 'phenomenon_of_interest',  letter: 'PI', label: 'Phenomenon of Interest', optional: false },
      { key: 'design',                  letter: 'D', label: 'Design',                  optional: true },
      { key: 'evaluation',              letter: 'E', label: 'Evaluation',              optional: true },
      { key: 'research_type',           letter: 'R', label: 'Research Type',           optional: true },
    ],
  },
  {
    value: 'pcc', label: 'PCC',
    hint: 'Population, Concept, Context — for scoping reviews',
    elements: [
      { key: 'population', letter: 'P', label: 'Population', optional: false },
      { key: 'concept',    letter: 'C', label: 'Concept',    optional: false },
      { key: 'context',    letter: 'C', label: 'Context',    optional: true },
    ],
  },
  {
    value: 'pird', label: 'PIRD',
    hint: 'Population, Index test, Reference standard, Diagnosis — for diagnostic accuracy studies',
    elements: [
      { key: 'population',         letter: 'P', label: 'Population',         optional: false },
      { key: 'index_test',         letter: 'I', label: 'Index Test',         optional: false },
      { key: 'reference_standard', letter: 'R', label: 'Reference Standard', optional: true },
      { key: 'diagnosis',          letter: 'D', label: 'Diagnosis',          optional: true },
    ],
  },
  {
    value: 'pif', label: 'PIF',
    hint: 'Population, Index/prognostic Factor, Follow-up — for prognostic studies',
    elements: [
      { key: 'population',   letter: 'P', label: 'Population',             optional: false },
      { key: 'index_factor', letter: 'I', label: 'Index/Prognostic Factor', optional: false },
      { key: 'follow_up',    letter: 'F', label: 'Follow-up/Outcome',      optional: true },
    ],
  },
  {
    value: 'custom', label: 'Custom',
    hint: 'Define your own criteria elements — use this if no standard framework fits your review',
    elements: [],
  },
]

const frameworkOptions = FRAMEWORKS.map(fw => ({ value: fw.value, label: fw.label }))

// ── Manual mode state ──────────────────────────────────────
const manualResearchQuestion = ref('')
const selectedFramework = ref('pico')
const addingCustomElement = ref(false)
const customElementName = ref('')
const customElementInput = ref<HTMLInputElement | null>(null)

// Custom elements added by user (for custom framework)
const customElements = ref<FrameworkElement[]>([])

const activeElements = computed<FrameworkElement[]>(() => {
  if (selectedFramework.value === 'custom') return customElements.value
  const fw = FRAMEWORKS.find(f => f.value === selectedFramework.value)
  return fw?.elements ?? []
})

const frameworkHint = computed(() => {
  const fw = FRAMEWORKS.find(f => f.value === selectedFramework.value)
  return fw?.hint ?? ''
})

const manualElements = reactive<Record<string, { include: string[]; exclude: string[] }>>({})

// Ensure manualElements has entries for all active elements
function ensureManualElements() {
  for (const elem of activeElements.value) {
    if (!manualElements[elem.key]) {
      manualElements[elem.key] = { include: [], exclude: [] }
    }
  }
}

// Initialize for default framework and watch for changes
ensureManualElements()
watch(activeElements, ensureManualElements)

function onFrameworkChange() {
  ensureManualElements()
  // Focus the custom element input when switching to Custom with no elements
  if (selectedFramework.value === 'custom' && customElements.value.length === 0) {
    addingCustomElement.value = true
    nextTick(() => customElementInput.value?.focus())
  }
}

function confirmCustomElement() {
  const name = customElementName.value.trim()
  if (!name) return
  const key = name.toLowerCase().replace(/\s+/g, '_')
  if (customElements.value.some(e => e.key === key)) return // already exists
  customElements.value.push({
    key,
    letter: name.charAt(0).toUpperCase(),
    label: name,
    optional: false,
  })
  manualElements[key] = { include: [], exclude: [] }
  customElementName.value = ''
  addingCustomElement.value = false
}

const hasAnyManualTerms = computed(() => {
  return activeElements.value.some(elem => {
    const e = manualElements[elem.key]
    return e && (e.include.length > 0 || e.exclude.length > 0)
  })
})

// ── AI Generate ────────────────────────────────────────────
async function doGenerateCriteria() {
  if (!topicText.value.trim()) { criteriaError.value = 'Please enter a research topic.'; return }
  criteriaError.value = ''
  criteriaSaved.value = false
  generatingCriteria.value = true
  setTopic(topicText.value.trim())
  startCriteriaProgressSim()
  try {
    const result = await apiPost<GeneratedCriteria>('/screening/criteria-preview', {
      topic: topicText.value.trim(),
      n_models: selectedModelCount.value,
    })
    stopCriteriaProgressSim(true)
    if (result.generation_meta) {
      const meta = result.generation_meta
      criteriaGenLog.value += `Consensus: ${meta.consensus_method} (${meta.n_models} models)\n`
      if (meta.n_dedup_merges > 0) {
        criteriaGenLog.value += `Semantic dedup: merged ${meta.n_dedup_merges} term groups\n`
      }
      if (meta.n_ambiguity_flags > 0) {
        criteriaGenLog.value += `${meta.n_ambiguity_flags} items flagged for review\n`
      }
      // Track missing elements
      missingRequiredElements.value = meta.missing_required ?? []
      missingOptionalElements.value = meta.missing_optional ?? []
      if (missingRequiredElements.value.length > 0) {
        criteriaGenLog.value += `Missing required elements: ${missingRequiredElements.value.join(', ')}\n`
      }
    } else {
      missingRequiredElements.value = []
      missingOptionalElements.value = []
    }
    generatedCriteria.value = result
    sourceMode.value = 'ai'
    // Build editable elements from returned result
    const editableElements: CriteriaElements = Object.fromEntries(
      Object.entries(result.elements).map(([k, v]) => [
        k, {
          name: v.name,
          include: [...v.include],
          exclude: [...v.exclude],
          element_quality: v.element_quality ?? null,
          ambiguity_flags: v.ambiguity_flags ? [...v.ambiguity_flags] : [],
          model_votes: v.model_votes ? { ...v.model_votes } : undefined,
        }
      ])
    )
    // Ensure missing elements appear in editor (empty) so user can AI-Suggest them
    const fw = FRAMEWORKS.find(f => f.value === result.framework?.toLowerCase())
    if (fw) {
      for (const fwElem of fw.elements) {
        if (!editableElements[fwElem.key]) {
          editableElements[fwElem.key] = { name: fwElem.label, include: [], exclude: [] }
        }
      }
    }
    editableCriteria.value = { elements: editableElements }
    loadFiltersFromCriteria(result)
    validateMeshTerms()
  } catch (e: unknown) {
    stopCriteriaProgressSim(false)
    const msg = (e as Error).message || 'Generation failed'
    criteriaGenLog.value += `ERROR: ${msg}\n`
    criteriaError.value = msg.includes('API key') ? msg : `Criteria generation failed: ${msg}`
    if (msg.includes('API key') || msg.includes('not configured')) {
      showApiModal.value = true
    }
  } finally {
    generatingCriteria.value = false
  }
}

// ── Manual Apply ───────────────────────────────────────────
function applyManualCriteria() {
  criteriaError.value = ''
  criteriaSaved.value = false

  const elements: CriteriaElements = {}
  for (const elem of activeElements.value) {
    const src = manualElements[elem.key]
    if (src && (src.include.length > 0 || src.exclude.length > 0)) {
      elements[elem.key] = {
        name: elem.label,
        include: [...src.include],
        exclude: [...src.exclude],
      }
    }
  }

  const criteria: GeneratedCriteria = {
    framework: selectedFramework.value.toUpperCase(),
    research_question: manualResearchQuestion.value.trim() || undefined,
    detected_language: 'en',
    elements,
    publication_type_exclude: [...editPubTypeExclude.value],
    language_restriction: editLanguageRestriction.value.length ? [...editLanguageRestriction.value] : null,
    date_from: editDateFrom.value || null,
    date_to: editDateTo.value || null,
  }
  generatedCriteria.value = criteria
  sourceMode.value = 'manual'
  editableCriteria.value = {
    elements: Object.fromEntries(
      Object.entries(criteria.elements).map(([k, v]) => [
        k, { name: v.name, include: [...v.include], exclude: [...v.exclude] }
      ])
    )
  }
}

// ── Import ─────────────────────────────────────────────────
async function onImportFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (f) importedContent.value = await f.text()
}

function doApplyImported() {
  if (!importedContent.value.trim()) return
  criteriaError.value = ''
  try {
    const text = importedContent.value.trim()
    let parsed: Record<string, unknown>
    try {
      parsed = JSON.parse(text)
    } catch {
      criteriaError.value = 'Only JSON criteria files are supported for import.'
      return
    }
    const criteria: GeneratedCriteria = {
      framework: String(parsed.framework || 'PICO'),
      research_question: String(parsed.research_question || ''),
      detected_language: String(parsed.detected_language || 'en'),
      elements: (parsed.elements || {}) as CriteriaElements,
      publication_type_exclude: Array.isArray(parsed.publication_type_exclude) ? parsed.publication_type_exclude as string[] : undefined,
      language_restriction: Array.isArray(parsed.language_restriction) ? parsed.language_restriction as string[] : null,
      date_from: parsed.date_from ? String(parsed.date_from) : null,
      date_to: parsed.date_to ? String(parsed.date_to) : null,
    }
    generatedCriteria.value = criteria
    sourceMode.value = 'import'
    editableCriteria.value = {
      elements: Object.fromEntries(
        Object.entries(criteria.elements).map(([k, v]) => [
          k, { name: v.name, include: [...v.include], exclude: [...v.exclude] }
        ])
      )
    }
    loadFiltersFromCriteria(criteria)
  } catch (e: unknown) {
    criteriaError.value = `Failed to apply imported criteria: ${(e as Error).message}`
  }
}

// ── Chip editing ───────────────────────────────────────────
function removeTerm(key: string, type: 'include' | 'exclude', idx: number) {
  const elem = editableCriteria.value.elements[key]
  if (elem) elem[type].splice(idx, 1)
}

function startAdd(key: string, type: 'include' | 'exclude') {
  addingTerm.value = { key, type }
  newTermText.value = ''
  nextTick(() => {
    // addTermInput can be an array of refs when inside v-for
    const el = Array.isArray(addTermInput.value) ? addTermInput.value[0] : addTermInput.value
    el?.focus()
  })
}

function confirmAdd(key: string, type: 'include' | 'exclude') {
  const t = newTermText.value.trim()
  if (!t) { cancelAdd(); return }

  // Decide which data source to modify
  if (generatedCriteria.value) {
    editableCriteria.value.elements[key]?.[type].push(t)
  } else {
    // Manual mode — modify manualElements
    manualElements[key]?.[type].push(t)
  }
  cancelAdd()
}

function cancelAdd() {
  addingTerm.value = null
  newTermText.value = ''
}

function dismissFlag(elementKey: string, flagIndex: number) {
  const elem = editableCriteria.value.elements[elementKey]
  if (elem?.ambiguity_flags) {
    elem.ambiguity_flags.splice(flagIndex, 1)
  }
}

// ── AI Suggest ────────────────────────────────────────────
interface TermSuggestion {
  term: string
  rationale: string
}

const suggestLoading = reactive<Record<string, boolean>>({})
const suggestions = reactive<Record<string, TermSuggestion[]>>({})

async function suggestTerms(elemKey: string, elemName: string) {
  if (suggestLoading[elemKey]) return
  suggestLoading[elemKey] = true
  try {
    const elem = editableCriteria.value.elements[elemKey]
    const resp = await apiPost<{ suggestions: TermSuggestion[] }>('/screening/suggest-terms', {
      element_key: elemKey,
      element_name: elemName,
      current_include: elem?.include || [],
      current_exclude: elem?.exclude || [],
      topic: topicText.value.trim(),
      framework: selectedFramework.value,
    })
    suggestions[elemKey] = resp.suggestions
  } catch (e: any) {
    criteriaError.value = `Suggest failed for ${elemName}: ${e?.response?.data?.detail || e.message}`
  } finally {
    suggestLoading[elemKey] = false
  }
}

function adoptSuggestion(elemKey: string, term: string) {
  if (!editableCriteria.value.elements[elemKey]) {
    editableCriteria.value.elements[elemKey] = { include: [], exclude: [] }
  }
  editableCriteria.value.elements[elemKey].include.push(term)
  suggestions[elemKey] = (suggestions[elemKey] || []).filter(s => s.term !== term)
}

function dismissSuggestion(elemKey: string, term: string) {
  suggestions[elemKey] = (suggestions[elemKey] || []).filter(s => s.term !== term)
}

function dismissAllSuggestions(elemKey: string) {
  suggestions[elemKey] = []
}

async function doRegenerateCriteria() {
  generatedCriteria.value = null
  editableCriteria.value = { elements: {} }
  criteriaSaved.value = false
  criteriaGenLog.value = ''
  await doGenerateCriteria()
}

function resetCriteriaEditor() {
  generatedCriteria.value = null
  editableCriteria.value = { elements: {} }
  criteriaSaved.value = false
  sourceMode.value = mode.value
  resetFilters()
}

// ── Confirm & save to store ────────────────────────────────
function confirmCriteria() {
  const criteria = generatedCriteria.value
  if (!criteria) return
  const saved: SavedCriteria = {
    framework: criteria.framework,
    research_question: criteria.research_question,
    detected_language: criteria.detected_language,
    elements: editableCriteria.value.elements,
    publication_type_exclude: editPubTypeExclude.value.length ? [...editPubTypeExclude.value] : [],
    language_restriction: editLanguageRestriction.value.length ? [...editLanguageRestriction.value] : null,
    date_from: editDateFrom.value || null,
    date_to: editDateTo.value || null,
  }
  setCriteria(saved)
  criteriaSaved.value = true

  // Fire-and-forget: save to history
  const elemCount = Object.values(saved.elements).reduce((n, e) => n + e.include.length + e.exclude.length, 0)
  apiPost('/history/criteria', {
    data: saved,
    name: `Criteria — ${saved.framework}`,
    summary: `${saved.framework} framework, ${elemCount} terms${saved.research_question ? ': ' + saved.research_question.slice(0, 60) : ''}`,
  }).catch(() => { /* non-critical */ })
}

function capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ')
}

// ── MeSH Validation ────────────────────────────────────────
interface MeSHResult {
  term: string
  is_valid: boolean
  mesh_uid: string | null
  suggested_mesh: string | null
  suggestion_uid: string | null
}

const meshResults = ref<Record<string, MeSHResult>>({})
const meshLoading = ref(false)

async function validateMeshTerms() {
  const allTerms = new Set<string>()
  for (const elem of Object.values(editableCriteria.value.elements)) {
    for (const t of (elem.include || [])) allTerms.add(t)
    for (const t of (elem.exclude || [])) allTerms.add(t)
  }
  if (allTerms.size === 0) return

  meshLoading.value = true
  try {
    const resp = await apiPost<{ results: MeSHResult[] }>('/screening/validate-mesh', {
      terms: [...allTerms],
    })
    const map: Record<string, MeSHResult> = {}
    for (const r of resp.results) map[r.term] = r
    meshResults.value = map
  } catch (e) {
    console.warn('MeSH validation failed', e)
  } finally {
    meshLoading.value = false
  }
}

function replaceMeshTerm(elemKey: string, oldTerm: string, newTerm: string) {
  const elem = editableCriteria.value.elements[elemKey]
  if (!elem) return
  const idx = elem.include.indexOf(oldTerm)
  if (idx >= 0) elem.include[idx] = newTerm
  validateMeshTerms()
}

// ── Pilot Search ───────────────────────────────────────────
interface PilotArticle {
  pmid: string; title: string; authors: string; year: number | null; abstract: string | null
}
interface PilotAssessment {
  pmid: string; title: string; is_relevant: boolean; reason: string
}
interface PilotDiagnostic {
  search_result: { query: string; total_hits: number; articles: PilotArticle[]; pubmed_url: string }
  assessments: PilotAssessment[]
  estimated_precision: number | null
  model_used: string
}

const pilotLoading = ref(false)
const pilotResult = ref<PilotDiagnostic | null>(null)

async function runPilotSearch() {
  pilotLoading.value = true
  pilotResult.value = null
  try {
    const meshList = Object.values(meshResults.value)
    const result = await apiPost<PilotDiagnostic>('/screening/pilot-search', {
      criteria: editableCriteria.value,
      mesh_results: meshList.length > 0 ? meshList : null,
    })
    pilotResult.value = result
  } catch (e: any) {
    criteriaError.value = `Pilot search failed: ${e?.response?.data?.detail || e.message}`
  } finally {
    pilotLoading.value = false
  }
}
</script>

<style scoped>
.criteria-page {
  --cp-aqua: #00cccc;
  --cp-tiffany: #81d8d0;
  --cp-violet: #8b5cf6;
  --cp-violet-deep: #7347e8;
  --cp-text-soft: rgba(71, 85, 105, 0.84);
  position: relative;
}

.criteria-page :deep(.page-title) {
  letter-spacing: -0.03em;
}

.criteria-page > .glass-card {
  position: relative;
  overflow: hidden;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.86);
  background:
    radial-gradient(
      120% 95% at 0% 0%,
      rgba(129, 216, 208, 0.12) 0%,
      rgba(129, 216, 208, 0) 46%
    ),
    radial-gradient(
      130% 110% at 100% 100%,
      rgba(139, 92, 246, 0.12) 0%,
      rgba(139, 92, 246, 0) 52%
    ),
    linear-gradient(
      152deg,
      rgba(255, 255, 255, 0.86) 0%,
      rgba(255, 255, 255, 0.62) 52%,
      rgba(255, 255, 255, 0.74) 100%
    );
  -webkit-backdrop-filter: blur(20px) saturate(150%) brightness(1.06);
  backdrop-filter: blur(20px) saturate(150%) brightness(1.06);
  box-shadow:
    0 12px 30px rgba(15, 23, 42, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.94),
    inset 0 -1px 0 rgba(255, 255, 255, 0.3);
}

.criteria-page > .glass-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 10%;
  right: 10%;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.96) 50%,
    transparent 100%
  );
  pointer-events: none;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.04rem;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.section-title i {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #155e75;
  background: linear-gradient(
    140deg,
    rgba(212, 249, 245, 0.9) 0%,
    rgba(218, 233, 255, 0.74) 52%,
    rgba(232, 220, 255, 0.7) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.8);
}

.criteria-mode-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.criteria-mode-card {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--btn-frost-border);
  border-radius: 16px;
  padding: 16px;
  text-align: left;
  cursor: pointer;
  background:
    linear-gradient(
      145deg,
      var(--btn-frost-bg-strong) 0%,
      var(--btn-frost-bg-soft) 100%
    );
  -webkit-backdrop-filter: blur(14px) saturate(145%);
  backdrop-filter: blur(14px) saturate(145%);
  transition:
    transform 260ms ease,
    border-color 240ms ease,
    box-shadow 260ms ease;
  box-shadow:
    0 6px 16px rgba(15, 23, 42, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.62);
}

.criteria-mode-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(
    120% 90% at 0% 0%,
    rgba(129, 216, 208, 0.12) 0%,
    transparent 48%
  );
  pointer-events: none;
  opacity: 0;
  transition: opacity 240ms ease;
}

.criteria-mode-card:hover {
  transform: translateY(-3px);
  border-color: rgba(210, 243, 239, 0.9);
  box-shadow:
    0 10px 22px rgba(15, 23, 42, 0.08),
    0 6px 16px rgba(129, 216, 208, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
}

.criteria-mode-card:hover::before {
  opacity: 1;
}

.criteria-mode-card.active {
  border-color: rgba(169, 231, 226, 0.94);
  background:
    linear-gradient(
      145deg,
      rgba(231, 225, 248, 0.42) 0%,
      rgba(214, 229, 245, 0.28) 55%,
      rgba(221, 234, 246, 0.26) 100%
    );
  box-shadow:
    0 12px 24px rgba(0, 204, 204, 0.12),
    0 10px 22px rgba(139, 92, 246, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
}

.criteria-mode-card.active::before {
  opacity: 1;
}

.criteria-mode-card:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 3px rgba(129, 216, 208, 0.3),
    0 0 0 6px rgba(139, 92, 246, 0.16);
}

.criteria-mode-icon {
  width: 38px;
  height: 38px;
  border-radius: 11px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.95rem;
  color: #0f766e;
  margin-bottom: 10px;
  background: linear-gradient(
    140deg,
    rgba(212, 249, 245, 0.9) 0%,
    rgba(214, 233, 255, 0.78) 56%,
    rgba(229, 219, 255, 0.74) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.82);
}

.criteria-mode-name {
  font-size: 0.95rem;
  font-weight: 650;
  margin-bottom: 6px;
  color: #0f172a;
}

.criteria-mode-desc {
  font-size: 0.79rem;
  line-height: 1.58;
  color: var(--cp-text-soft);
}

.criteria-mode-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.65rem;
  font-weight: 650;
  letter-spacing: 0.02em;
}

.criteria-mode-badge.recommended {
  color: #0f766e;
  background: rgba(204, 250, 241, 0.78);
  border: 1px solid rgba(167, 243, 208, 0.7);
}

.pico-guide {
  border-radius: 14px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: linear-gradient(
    150deg,
    rgba(255, 255, 255, 0.78) 0%,
    rgba(255, 255, 255, 0.58) 100%
  );
  box-shadow:
    0 6px 16px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.pico-guide-title {
  font-size: 0.84rem;
  font-weight: 650;
  color: #155e75;
  margin-bottom: 10px;
}

.pico-guide-items {
  display: grid;
  gap: 8px;
}

.pico-guide-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.56);
  border: 1px solid rgba(255, 255, 255, 0.72);
}

.pico-letter {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
  color: #155e75;
  background: linear-gradient(
    140deg,
    rgba(207, 250, 243, 0.86) 0%,
    rgba(219, 234, 254, 0.72) 100%
  );
  border: 1px solid rgba(255, 255, 255, 0.8);
  flex-shrink: 0;
}

.pico-letter-optional {
  color: #5b21b6;
  background: linear-gradient(
    140deg,
    rgba(233, 213, 255, 0.82) 0%,
    rgba(221, 214, 254, 0.72) 100%
  );
}

.pico-item-label {
  font-size: 0.78rem;
  font-weight: 640;
  color: #0f172a;
}

.pico-item-example {
  margin-top: 2px;
  font-size: 0.75rem;
  color: rgba(71, 85, 105, 0.8);
}

.pico-optional-tag {
  font-size: 0.64rem;
  font-weight: 600;
  color: #5b21b6;
  background: rgba(233, 213, 255, 0.62);
  border: 1px solid rgba(216, 180, 254, 0.64);
  border-radius: 999px;
  padding: 1px 6px;
}

.criteria-editor {
  border-radius: 16px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.84);
  background: linear-gradient(
    150deg,
    rgba(255, 255, 255, 0.72) 0%,
    rgba(255, 255, 255, 0.56) 100%
  );
}

.criteria-editor-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.criteria-framework-badge,
.criteria-lang-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 650;
  border: 1px solid rgba(255, 255, 255, 0.78);
  background: rgba(255, 255, 255, 0.68);
  color: #155e75;
}

.criteria-rq {
  font-size: 0.79rem;
  color: var(--cp-text-soft);
}

.criteria-editor-note {
  border-radius: 10px;
  padding: 8px 10px;
  margin-bottom: 12px;
  font-size: 0.78rem;
  color: #0f766e;
  background: rgba(236, 253, 245, 0.66);
  border: 1px solid rgba(167, 243, 208, 0.62);
}

.criteria-missing-warning {
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 0.82rem;
  color: #92400e;
  background: rgba(255, 237, 213, 0.72);
  border: 1px solid rgba(251, 191, 36, 0.55);
  display: flex;
  align-items: center;
  gap: 8px;
}
.criteria-missing-warning i {
  color: #d97706;
  font-size: 1rem;
}

.criteria-elements-editor {
  display: grid;
  gap: 12px;
}

.criteria-element-editor-card {
  border-radius: 14px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: linear-gradient(
    145deg,
    rgba(255, 255, 255, 0.78) 0%,
    rgba(255, 255, 255, 0.58) 100%
  );
  box-shadow:
    0 5px 14px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.criteria-element-name {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 0.85rem;
  font-weight: 650;
  color: #0f172a;
}

.criteria-editor-row {
  display: grid;
  grid-template-columns: 70px 1fr;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 9px;
}

.criteria-term-label {
  margin-top: 3px;
  font-size: 0.74rem;
  font-weight: 640;
}

.criteria-term-label.include { color: #0f766e; }
.criteria-term-label.exclude { color: #6b21a8; }

.criteria-chips-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.criteria-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 5px 9px;
  border-radius: 999px;
  font-size: 0.73rem;
  line-height: 1.2;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.68);
  color: #0f172a;
}

.criteria-chip.include {
  color: #0f766e;
  background: rgba(204, 250, 241, 0.7);
  border-color: rgba(167, 243, 208, 0.68);
}

.criteria-chip.exclude {
  color: #5b21b6;
  background: rgba(233, 213, 255, 0.68);
  border-color: rgba(216, 180, 254, 0.68);
}

.chip-remove {
  width: 16px;
  height: 16px;
  border: 1px solid var(--btn-frost-border);
  border-radius: 999px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  background: linear-gradient(
    145deg,
    var(--btn-frost-bg-strong) 0%,
    var(--btn-frost-bg-soft) 100%
  );
  -webkit-backdrop-filter: blur(8px) saturate(130%);
  backdrop-filter: blur(8px) saturate(130%);
  color: rgba(15, 23, 42, 0.65);
}

.chip-remove:hover {
  border-color: rgba(129, 216, 208, 0.66);
  color: #155e75;
}
.chip-remove:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px rgba(129, 216, 208, 0.22),
    0 0 0 4px rgba(139, 92, 246, 0.12);
}

.add-chip-btn {
  border: 1px dashed rgba(148, 163, 184, 0.62);
  border-radius: 999px;
  padding: 5px 9px;
  font-size: 0.73rem;
  background: linear-gradient(
    145deg,
    var(--btn-frost-bg-strong) 0%,
    var(--btn-frost-bg-soft) 100%
  );
  -webkit-backdrop-filter: blur(8px) saturate(130%);
  backdrop-filter: blur(8px) saturate(130%);
  color: #475569;
  cursor: pointer;
}

.add-chip-btn:hover {
  border-color: rgba(129, 216, 208, 0.82);
  color: #155e75;
}
.add-chip-btn:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px rgba(129, 216, 208, 0.22),
    0 0 0 4px rgba(139, 92, 246, 0.12);
}

.add-chip-input {
  border: 1px solid rgba(129, 216, 208, 0.72);
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 0.73rem;
  background: rgba(255, 255, 255, 0.84);
  color: #0f172a;
  min-width: 180px;
}

.add-chip-input:focus {
  outline: none;
  box-shadow: 0 0 0 3px rgba(129, 216, 208, 0.22);
}

.screening-filters-section {
  margin-top: 14px;
  border-radius: 14px;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background: linear-gradient(
    148deg,
    rgba(255, 255, 255, 0.72) 0%,
    rgba(255, 255, 255, 0.56) 100%
  );
}

.section-subtitle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.86rem;
  font-weight: 650;
  color: #0f172a;
  margin-bottom: 8px;
}

.section-subtitle i {
  color: #155e75;
}

.filter-row {
  display: grid;
  grid-template-columns: 190px 1fr;
  gap: 10px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed rgba(148, 163, 184, 0.22);
}

.filter-row:last-child {
  border-bottom: none;
}

.filter-label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 0.77rem;
  font-weight: 620;
  color: #334155;
}

.criteria-editor-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.form-control-sm {
  padding: 0.42rem 0.72rem;
  font-size: 0.82rem;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.32);
  -webkit-backdrop-filter: blur(5px);
  backdrop-filter: blur(5px);
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
}

.modal-glass {
  width: min(680px, 100%);
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  background:
    radial-gradient(
      120% 100% at 0% 0%,
      rgba(129, 216, 208, 0.14) 0%,
      transparent 48%
    ),
    radial-gradient(
      120% 110% at 100% 100%,
      rgba(139, 92, 246, 0.14) 0%,
      transparent 52%
    ),
    rgba(255, 255, 255, 0.9);
  -webkit-backdrop-filter: blur(24px) saturate(145%);
  backdrop-filter: blur(24px) saturate(145%);
  box-shadow:
    0 24px 56px rgba(15, 23, 42, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.modal-header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modal-header-icon {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #155e75;
  background: rgba(204, 250, 241, 0.72);
  border: 1px solid rgba(167, 243, 208, 0.7);
}

.modal-header h3 {
  font-size: 1rem;
  letter-spacing: -0.01em;
}

.modal-close-btn {
  width: 30px;
  height: 30px;
  border: 1px solid var(--btn-frost-border);
  border-radius: 9px;
  background: linear-gradient(
    145deg,
    var(--btn-frost-bg-strong) 0%,
    var(--btn-frost-bg-soft) 100%
  );
  -webkit-backdrop-filter: blur(12px) saturate(142%);
  backdrop-filter: blur(12px) saturate(142%);
  color: #64748b;
  cursor: pointer;
}

.modal-close-btn:hover {
  color: #155e75;
  border-color: rgba(129, 216, 208, 0.66);
}
.modal-close-btn:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px rgba(129, 216, 208, 0.22),
    0 0 0 4px rgba(139, 92, 246, 0.12);
}

.modal-body {
  padding: 14px 16px;
}

.modal-subtitle {
  font-size: 0.86rem;
  color: var(--cp-text-soft);
  margin-bottom: 10px;
}

.modal-steps {
  display: grid;
  gap: 8px;
}

.modal-step-item {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 8px;
  align-items: start;
  padding: 9px 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.74);
}

.modal-step-num {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 700;
  color: #155e75;
  background: rgba(204, 250, 241, 0.72);
  border: 1px solid rgba(167, 243, 208, 0.7);
}

.modal-step-text {
  font-size: 0.79rem;
  color: #334155;
  line-height: 1.54;
}

.modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding: 12px 16px 16px;
}

/* Quality badges */
.quality-badge {
  font-size: 0.68rem;
  padding: 3px 10px;
  border-radius: 999px;
  font-weight: 600;
  border: 1px solid var(--btn-frost-border);
  -webkit-backdrop-filter: blur(8px) saturate(130%);
  backdrop-filter: blur(8px) saturate(130%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.6);
}

.quality-high {
  background: linear-gradient(135deg, rgba(204,250,241,0.55) 0%, rgba(167,243,208,0.35) 100%);
  color: #0f766e;
  border-color: rgba(129,216,208,0.45);
}

.quality-mid {
  background: linear-gradient(135deg, rgba(254,243,199,0.55) 0%, rgba(253,230,138,0.35) 100%);
  color: #a16207;
  border-color: rgba(245,158,11,0.35);
}

.quality-low {
  background: linear-gradient(135deg, rgba(254,226,226,0.55) 0%, rgba(252,165,165,0.35) 100%);
  color: #b91c1c;
  border-color: rgba(248,113,113,0.35);
}

/* Ambiguity flags */
.ambiguity-section { margin-top: 10px; }
.ambiguity-toggle {
  cursor: pointer;
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 600;
}
.ambiguity-items { padding: 8px 0 2px; }
.ambiguity-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 10px;
  margin-bottom: 6px;
  font-size: 0.76rem;
  color: #475569;
  background: linear-gradient(145deg, var(--btn-frost-bg-strong) 0%, var(--btn-frost-bg-soft) 100%);
  border: 1px solid var(--btn-frost-border);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.6);
}

.btn-sm {
  font-size: 0.72rem;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--btn-frost-border);
  background: linear-gradient(
    145deg,
    var(--btn-frost-bg-strong) 0%,
    var(--btn-frost-bg-soft) 100%
  );
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  backdrop-filter: blur(10px) saturate(140%);
  cursor: pointer;
  box-shadow:
    0 2px 6px var(--btn-frost-shadow),
    inset 0 1px 0 rgba(255,255,255,0.7);
  transition: all 0.18s ease;
}
.btn-sm:hover {
  border-color: rgba(129, 216, 208, 0.58);
  box-shadow:
    0 4px 12px rgba(129, 216, 208, 0.1),
    inset 0 1px 0 rgba(255,255,255,0.82);
}

.btn-muted { opacity: 0.78; }
.btn-sm:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px rgba(129, 216, 208, 0.22),
    0 0 0 4px rgba(139, 92, 246, 0.12);
}

@media (max-width: 980px) {
  .criteria-mode-grid {
    grid-template-columns: 1fr 1fr;
  }
  .filter-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }
}

@media (max-width: 760px) {
  .criteria-page > .glass-card {
    border-radius: 15px;
    padding: 1rem;
  }
  .criteria-mode-grid {
    grid-template-columns: 1fr;
  }
  .criteria-editor-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .criteria-term-label {
    margin-top: 0;
  }
  .criteria-editor-actions {
    gap: 8px;
  }
  .modal-footer {
    flex-wrap: wrap;
  }
}
</style>
