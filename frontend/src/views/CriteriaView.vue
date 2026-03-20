<template>
  <div>
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

      <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
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

        <!-- Editable element cards -->
        <div class="criteria-elements-editor">
          <div
            v-for="(elem, key) in editableCriteria.elements"
            :key="key"
            class="criteria-element-editor-card"
          >
            <div class="criteria-element-name">{{ capitalise(String(elem.name || key)) }}</div>

            <!-- Include row -->
            <div class="criteria-editor-row">
              <span class="criteria-term-label include">Include</span>
              <div class="criteria-chips-wrap">
                <span v-for="(term, idx) in elem.include" :key="idx" class="criteria-chip include editable">
                  {{ term }}
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
import { useCriteriaStore, type SavedCriteria, type CriteriaElements } from '@/stores/criteria'

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
          k, { name: v.name, include: [...v.include], exclude: [...v.exclude] }
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
}

const generatedCriteria = ref<GeneratedCriteria | null>(null)
const editableCriteria = ref<{ elements: CriteriaElements }>({ elements: {} })

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
    })
    stopCriteriaProgressSim(true)
    generatedCriteria.value = result
    sourceMode.value = 'ai'
    editableCriteria.value = {
      elements: Object.fromEntries(
        Object.entries(result.elements).map(([k, v]) => [
          k, { name: v.name, include: [...v.include], exclude: [...v.exclude] }
        ])
      )
    }
    loadFiltersFromCriteria(result)
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
</script>
