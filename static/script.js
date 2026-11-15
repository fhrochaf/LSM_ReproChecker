(function () {
  "use strict";

  const dataEl = document.getElementById("papers-data");
  const papers = JSON.parse(dataEl.textContent);

  const grid = document.getElementById("card-grid");
  const searchInput = document.getElementById("search-input");
  const resultCount = document.getElementById("result-count");
  const statusFilterRow = document.getElementById("status-filter");
  const approachFilterRow = document.getElementById("approach-filter");
  const backdrop = document.getElementById("modal-backdrop");
  const modal = backdrop.querySelector(".modal");
  const modalBody = document.getElementById("modal-body");
  const modalClose = document.getElementById("modal-close");

  const activeStatuses = new Set();
  const activeApproaches = new Set();
  let hybridOnly = false;

  // Order here drives both the filter-chip order and card sort tie-breaking
  // elsewhere; keep it aligned with build.py's STATUS_SORT_RANK.
  const STATUSES = [
    { value: "REPRODUCIBLE", label: "Reproducible", badgeClass: "", color: "var(--status-repro)" },
    {
      value: "PARTIALLY_REPRODUCIBLE",
      label: "Partially reproducible",
      badgeClass: " card__badge--partial",
      modalBadgeClass: " modal__badge--partial",
      color: "var(--status-partial)",
    },
    {
      value: "NOT_REPRODUCIBLE",
      label: "Not reproducible",
      badgeClass: " card__badge--not",
      modalBadgeClass: " modal__badge--not",
      color: "var(--status-not)",
    },
  ];
  const statusByValue = Object.fromEntries(STATUSES.map((s) => [s.value, s]));

  // Method approach comes from the human-reviewed Scopus export's
  // Method_approach column (one value per paper); Method_hybrid flags papers
  // that combine approaches. Each approach has a fixed accent and note color
  // (see --approach-* / --note-* in style.css). Method_temporal is ignored.
  const APPROACHES = [
    { value: "DEEP_LEARNING", label: "Deep learning", key: "dl" },
    { value: "ML_STATISTICAL", label: "Machine learning / statistical", key: "ml" },
    { value: "RULE_BASED", label: "Rule-based", key: "rb" },
  ];
  const approachByValue = Object.fromEntries(APPROACHES.map((a) => [a.value, a]));
  const approachColorVar = (value) =>
    approachByValue[value] ? `var(--approach-${approachByValue[value].key})` : null;

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function approachTag(paper, extraClass) {
    const meta = approachByValue[paper.approach];
    if (!meta) return "";
    const hybrid = paper.hybrid ? '<span class="approach-tag__hybrid">hybrid</span>' : "";
    return `<div class="approach-tag ${extraClass || ""}" style="--approach-color:var(--approach-${meta.key})">
      <span class="approach-tag__dot"></span>${escapeHtml(meta.label)}${hybrid}
    </div>`;
  }

  function linkOrNone(link) {
    if (!link) {
      return '<span class="item__link item__link--none">no direct link available</span>';
    }
    const safe = escapeHtml(link);
    return `<a class="item__link" href="${safe}" target="_blank" rel="noopener noreferrer">${safe}</a>`;
  }

  function renderItemList(items, accent) {
    if (!items || items.length === 0) {
      return '<p class="modal__none">None reported.</p>';
    }
    const style = accent ? ` style="--item-accent:${accent}"` : "";
    return `<ul class="item-list">${items
      .map((item) => {
        const typeTag = item.method_type
          ? `<span class="tag">${escapeHtml(item.method_type.replace(/_/g, " "))}</span><br>`
          : "";
        const source = item.source ? `<div class="item__source">${escapeHtml(item.source)}</div>` : "";
        const summary = item.summary ? `<div class="item__summary">${escapeHtml(item.summary)}</div>` : "";
        return `<li class="item"${style}>
          ${typeTag}
          <div class="item__name">${escapeHtml(item.name || "Untitled")}</div>
          ${source}
          ${summary}
          ${linkOrNone(item.link)}
        </li>`;
      })
      .join("")}</ul>`;
  }

  function statusLabel(status) {
    if (!status) return "—";
    return status.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
  }

  function noteModifier(paper) {
    const meta = approachByValue[paper.approach];
    return meta ? meta.key : "none";
  }

  function renderCard(paper) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = `card card--${noteModifier(paper)}`;
    el.setAttribute("data-id", paper.id);

    const statusMeta = statusByValue[paper.status];
    const badgeClass = `card__badge${statusMeta?.badgeClass || ""}`;
    const badgeText = statusMeta?.label || "Unknown";

    const nDatasets = paper.datasets?.length || 0;
    const nMethods = paper.methods?.length || 0;
    el.innerHTML = `
      <div class="card__head">
        <span class="${badgeClass}">${badgeText}</span>
        <span class="card__year">${paper.year ?? ""}</span>
      </div>
      <h3 class="card__title">${escapeHtml(paper.title)}</h3>
      <div class="card__meta">${escapeHtml(paper.authors)}</div>
      ${approachTag(paper, "card__approach")}
      <p class="card__abstract">${escapeHtml(paper.abstract)}</p>
      <div class="card__footer">
        <span class="card__tagcount">
          <span class="card__stat"><b>${nDatasets}</b> dataset${nDatasets === 1 ? "" : "s"}</span>
          <span class="card__stat"><b>${nMethods}</b> method${nMethods === 1 ? "" : "s"}</span>
        </span>
        <span class="card__open">Details &rarr;</span>
      </div>
    `;
    el.addEventListener("click", () => openModal(paper));
    return el;
  }

  function openModal(paper) {
    const statusMeta = statusByValue[paper.status];
    const badgeClass = `modal__badge${statusMeta?.modalBadgeClass || ""}`;
    const badgeText = statusMeta?.label || "Unknown";
    const accent = approachColorVar(paper.approach);

    modal.className = `modal modal--${noteModifier(paper)}`;
    modalBody.innerHTML = `
      <span class="${badgeClass}">${badgeText}</span>
      <h2 class="modal__title">${escapeHtml(paper.title)}</h2>
      <div class="modal__meta">
        ${escapeHtml(paper.authors)} &middot; ${paper.year ?? ""}
        ${paper.doi_url ? `<br><a href="${escapeHtml(paper.doi_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(paper.doi)}</a>` : ""}
      </div>
      ${approachTag(paper, "modal__approach")}

      <div class="modal__section">
        <h3>Abstract</h3>
        <p class="modal__abstract">${escapeHtml(paper.abstract)}</p>
      </div>

      <div class="modal__section">
        <h3>Reproducibility assessment</h3>
        <p class="modal__assessment">${escapeHtml(paper.reproducibility_assessment)}</p>
      </div>

      <div class="modal__section">
        <h3>Methods (${paper.methods?.length || 0})</h3>
        ${renderItemList(paper.methods, accent)}
      </div>

      <div class="modal__section">
        <h3>Datasets (${paper.datasets?.length || 0})</h3>
        ${renderItemList(paper.datasets)}
      </div>

      <div class="modal__section">
        <h3>Data &amp; code availability on the publication's page</h3>
        <dl class="availability-grid">
          <div>
            <dt>Access</dt>
            <dd>${escapeHtml(statusLabel(paper.availability?.access_status))}</dd>
          </div>
          <div>
            <dt>Data</dt>
            <dd>${escapeHtml(statusLabel(paper.availability?.data_status))}</dd>
          </div>
          <div>
            <dt>Code</dt>
            <dd>${escapeHtml(statusLabel(paper.availability?.code_status))}</dd>
          </div>
        </dl>
        ${paper.availability?.author_statement
        ? `<p class="modal__assessment">${escapeHtml(paper.availability.author_statement)}</p>`
        : ""
      }
        ${renderItemList(paper.availability?.data_links)}
        ${renderItemList(paper.availability?.code_links, accent)}
      </div>
    `;
    backdrop.classList.add("is-open");
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    backdrop.classList.remove("is-open");
    document.body.style.overflow = "";
  }

  modalClose.addEventListener("click", closeModal);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });

  function searchHaystack(paper) {
    const datasetNames = (paper.datasets || []).map((d) => d.name).join(" ");
    const methodNames = (paper.methods || []).map((m) => m.name).join(" ");
    const approach = approachByValue[paper.approach]?.label || "";
    return [paper.title, paper.authors, paper.abstract, datasetNames, methodNames, approach]
      .join(" ")
      .toLowerCase();
  }

  function applyFilters() {
    const query = searchInput.value.trim().toLowerCase();
    const filtered = papers.filter((paper) => {
      if (query && !searchHaystack(paper).includes(query)) return false;
      if (activeStatuses.size > 0 && !activeStatuses.has(paper.status)) return false;
      if (activeApproaches.size > 0 && !activeApproaches.has(paper.approach)) return false;
      if (hybridOnly && !paper.hybrid) return false;
      return true;
    });
    renderGrid(filtered);
  }

  function renderGrid(filtered) {
    grid.innerHTML = "";
    if (filtered.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No papers match your search/filter.";
      grid.appendChild(empty);
    } else {
      filtered.forEach((paper) => grid.appendChild(renderCard(paper)));
    }
    resultCount.textContent = `${filtered.length} of ${papers.length} shown`;
  }

  // A "Clear …" link appended to a filter row while any of its chips is on.
  function syncClearButton(row, label, isAnyActive, onClear) {
    const existing = row.querySelector(".chip__clear");
    if (existing) existing.remove();
    if (!isAnyActive()) return;
    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "chip__clear";
    clearBtn.textContent = label;
    clearBtn.addEventListener("click", () => {
      onClear();
      row.querySelectorAll(".chip.is-active").forEach((c) => c.classList.remove("is-active"));
      clearBtn.remove();
      applyFilters();
    });
    row.appendChild(clearBtn);
  }

  function renderStatusFilter() {
    const counts = Object.fromEntries(STATUSES.map((s) => [s.value, 0]));
    papers.forEach((paper) => {
      if (paper.status in counts) counts[paper.status] += 1;
    });

    statusFilterRow.innerHTML =
      '<span class="filter-row__label">Status</span>' +
      STATUSES.map(
        (s) => `<button type="button" class="chip" data-status="${s.value}" style="--chip-color:${s.color}">
          <span class="chip__dot"></span>${escapeHtml(s.label)} (${counts[s.value] || 0})
        </button>`
      ).join("");

    const sync = () =>
      syncClearButton(statusFilterRow, "Clear status filters", () => activeStatuses.size > 0, () =>
        activeStatuses.clear()
      );

    statusFilterRow.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const status = chip.getAttribute("data-status");
        if (activeStatuses.has(status)) activeStatuses.delete(status);
        else activeStatuses.add(status);
        chip.classList.toggle("is-active", activeStatuses.has(status));
        sync();
        applyFilters();
      });
    });
  }

  function renderApproachFilter() {
    const counts = Object.fromEntries(APPROACHES.map((a) => [a.value, 0]));
    let hybridCount = 0;
    papers.forEach((paper) => {
      if (paper.approach in counts) counts[paper.approach] += 1;
      if (paper.hybrid) hybridCount += 1;
    });

    approachFilterRow.innerHTML =
      '<span class="filter-row__label">Method</span>' +
      APPROACHES.map(
        (a) => `<button type="button" class="chip" data-approach="${a.value}" style="--chip-color:var(--approach-${a.key})">
          <span class="chip__dot"></span>${escapeHtml(a.label)} (${counts[a.value]})
        </button>`
      ).join("") +
      `<span class="filter-row__sep" aria-hidden="true"></span>
       <button type="button" class="chip chip--hybrid" style="--chip-color:var(--color-hybrid)">
         <span class="chip__dot"></span>Hybrid only (${hybridCount})
       </button>`;

    const sync = () =>
      syncClearButton(
        approachFilterRow,
        "Clear method filters",
        () => activeApproaches.size > 0 || hybridOnly,
        () => {
          activeApproaches.clear();
          hybridOnly = false;
        }
      );

    approachFilterRow.querySelectorAll(".chip[data-approach]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const value = chip.getAttribute("data-approach");
        if (activeApproaches.has(value)) activeApproaches.delete(value);
        else activeApproaches.add(value);
        chip.classList.toggle("is-active", activeApproaches.has(value));
        sync();
        applyFilters();
      });
    });

    const hybridChip = approachFilterRow.querySelector(".chip--hybrid");
    hybridChip.addEventListener("click", () => {
      hybridOnly = !hybridOnly;
      hybridChip.classList.toggle("is-active", hybridOnly);
      sync();
      applyFilters();
    });
  }

  searchInput.addEventListener("input", applyFilters);

  renderStatusFilter();
  renderApproachFilter();
  renderGrid(papers);
})();
