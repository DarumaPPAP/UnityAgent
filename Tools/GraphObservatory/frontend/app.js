(function () {
  "use strict";

  const graph = window.__CONTEXT_GRAPH__ || { nodes: [], edges: [] };
  const architecture = window.__HUMAN_ARCHITECTURE__ || {
    concepts: [],
    tour: [],
    task_demo: { title: "", subtitle: "", steps: [] },
    system_stack: [],
    principles: []
  };
  const prefersReducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const TOUR_STEP_MS = 6000;
  const DEMO_STEP_MS = 4200;

  function byId(id) { return document.getElementById(id); }
  function text(element, value) {
    if (element) element.textContent = value == null ? "" : String(value);
  }
  function clear(element) {
    if (element) element.replaceChildren();
  }
  function copyText(value) {
    if (!value || !navigator.clipboard) return;
    navigator.clipboard.writeText(value);
  }
  function makeListItem(value) {
    const item = document.createElement("li");
    text(item, typeof value === "string" ? value : (value.label || value.id || ""));
    return item;
  }
  function renderList(id, values) {
    const target = byId(id);
    clear(target);
    (values || []).forEach((value) => target.appendChild(makeListItem(value)));
  }

  const sections = Array.from(document.querySelectorAll(".page-section"));
  const navButtons = Array.from(document.querySelectorAll(".nav-button"));

  function showSection(sectionId) {
    sections.forEach((section) => { section.hidden = section.id !== sectionId; });
    navButtons.forEach((button) => button.classList.toggle("is-active", button.dataset.target === sectionId));
    window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
  }

  navButtons.forEach((button) => {
    button.addEventListener("click", () => showSection(button.dataset.target));
  });
  byId("jump-explore").addEventListener("click", () => showSection("explore"));

  text(byId("architecture-tagline"), architecture.tagline || "");

  const conceptById = new Map((architecture.concepts || []).map((concept) => [concept.id, concept]));
  const conceptButtons = new Map();

  function renderConceptFlow() {
    const flow = byId("concept-flow");
    clear(flow);
    (architecture.concepts || []).forEach((concept, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "concept-card";
      button.dataset.conceptId = concept.id;
      button.setAttribute("aria-pressed", "false");

      const number = document.createElement("span");
      number.className = "concept-number";
      text(number, String(index + 1).padStart(2, "0"));
      const title = document.createElement("strong");
      text(title, concept.label);
      const question = document.createElement("small");
      text(question, concept.question);

      button.append(number, title, question);
      button.addEventListener("click", () => selectConcept(concept.id));
      flow.appendChild(button);
      conceptButtons.set(concept.id, button);
    });
  }

  function renderConceptSources(concept) {
    const target = byId("concept-sources");
    clear(target);
    (concept.source_paths || []).forEach((path) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "source-button";
      button.title = "Click to copy repository path";
      text(button, path);
      button.addEventListener("click", () => copyText(path));
      target.appendChild(button);
    });
  }

  function selectConcept(conceptId, options) {
    const concept = conceptById.get(conceptId);
    if (!concept) return;
    conceptButtons.forEach((button, id) => {
      const active = id === conceptId;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    const index = (architecture.concepts || []).findIndex((item) => item.id === conceptId);
    text(byId("concept-title"), concept.label);
    text(byId("concept-question"), concept.question);
    text(byId("concept-summary"), concept.summary);
    text(byId("concept-description"), concept.description);
    text(byId("concept-index"), index >= 0 ? String(index + 1).padStart(2, "0") : "");
    renderList("concept-machine-areas", concept.machine_areas);
    renderConceptSources(concept);
    if (options && options.focusDetail) {
      byId("concept-title").scrollIntoView({ block: "center", behavior: prefersReducedMotion ? "auto" : "smooth" });
    }
  }

  function clearConceptSelection() {
    conceptButtons.forEach((button) => {
      button.classList.remove("is-active");
      button.setAttribute("aria-pressed", "false");
    });
  }

  function renderSystemStack() {
    const target = byId("system-stack");
    clear(target);
    (architecture.system_stack || []).forEach((item) => {
      const card = document.createElement("div");
      card.className = "system-card";
      const title = document.createElement("strong");
      const question = document.createElement("span");
      const summary = document.createElement("p");
      text(title, item.label);
      text(question, item.question);
      text(summary, item.summary);
      card.append(title, question, summary);
      target.appendChild(card);
    });
  }

  renderList("architecture-principles", architecture.principles);
  renderConceptFlow();
  renderSystemStack();
  if ((architecture.concepts || []).length) selectConcept(architecture.concepts[0].id);

  let tourIndex = 0;
  let tourTimer = 0;
  let tourPlaying = false;

  function stopTourTimer() {
    if (tourTimer) window.clearTimeout(tourTimer);
    tourTimer = 0;
  }

  function scheduleTour() {
    stopTourTimer();
    if (!tourPlaying || prefersReducedMotion || !(architecture.tour || []).length) return;
    tourTimer = window.setTimeout(() => {
      if (tourIndex >= architecture.tour.length - 1) {
        tourPlaying = false;
        updateTourToggle();
        return;
      }
      setTourStep(tourIndex + 1);
      scheduleTour();
    }, TOUR_STEP_MS);
  }

  function updateTourToggle() {
    if (prefersReducedMotion) {
      text(byId("tour-toggle"), "次");
      byId("tour-toggle").setAttribute("aria-label", "Next tour step");
      return;
    }
    text(byId("tour-toggle"), tourPlaying ? "Ⅱ" : "▶");
    byId("tour-toggle").setAttribute("aria-label", tourPlaying ? "Pause tour" : "Play tour");
  }

  function setTourStep(index) {
    const tour = architecture.tour || [];
    if (!tour.length) return;
    tourIndex = Math.max(0, Math.min(index, tour.length - 1));
    const step = tour[tourIndex];
    text(byId("tour-title"), step.label);
    text(byId("tour-caption"), step.caption);
    const percent = ((tourIndex + 1) / tour.length) * 100;
    byId("tour-progress-bar").style.width = `${percent}%`;
    if (step.concept_id) selectConcept(step.concept_id);
    else clearConceptSelection();
  }

  function startTour() {
    showSection("overview");
    setTourStep(0);
    tourPlaying = !prefersReducedMotion;
    updateTourToggle();
    scheduleTour();
    byId("tour-panel").scrollIntoView({ block: "center", behavior: prefersReducedMotion ? "auto" : "smooth" });
  }

  byId("start-tour").addEventListener("click", startTour);
  byId("tour-toggle").addEventListener("click", () => {
    if (prefersReducedMotion) {
      const last = (architecture.tour || []).length - 1;
      setTourStep(tourIndex >= last ? 0 : tourIndex + 1);
      return;
    }
    tourPlaying = !tourPlaying;
    updateTourToggle();
    scheduleTour();
  });
  byId("tour-prev").addEventListener("click", () => {
    setTourStep(tourIndex - 1);
    scheduleTour();
  });
  byId("tour-next").addEventListener("click", () => {
    setTourStep(tourIndex + 1);
    scheduleTour();
  });
  setTourStep(0);
  updateTourToggle();

  const demo = architecture.task_demo || { title: "", subtitle: "", steps: [] };
  text(byId("demo-title"), demo.title || "Task Demo");
  text(byId("demo-subtitle"), demo.subtitle || "");
  text(byId("demo-request"), demo.title || "");
  const demoStepElements = [];
  let demoIndex = -1;
  let demoTimer = 0;
  let demoPlaying = false;

  function renderDemoSteps() {
    const target = byId("demo-steps");
    clear(target);
    (demo.steps || []).forEach((step, index) => {
      const card = document.createElement("div");
      card.className = "demo-step";
      card.dataset.demoIndex = String(index);
      const title = document.createElement("strong");
      const detail = document.createElement("span");
      text(title, step.label);
      text(detail, step.detail);
      card.append(title, detail);
      target.appendChild(card);
      demoStepElements.push(card);
    });
  }

  function setDemoStep(index) {
    const steps = demo.steps || [];
    if (!steps.length) return;
    demoIndex = Math.max(0, Math.min(index, steps.length - 1));
    const step = steps[demoIndex];
    demoStepElements.forEach((element, itemIndex) => element.classList.toggle("is-active", itemIndex === demoIndex));
    text(byId("demo-step-title"), step.label);
    text(byId("demo-step-detail"), step.detail);
  }

  function stopDemo() {
    if (demoTimer) window.clearTimeout(demoTimer);
    demoTimer = 0;
    demoPlaying = false;
    text(byId("demo-play"), "▶ Demoを再生");
  }

  function scheduleDemo() {
    if (demoTimer) window.clearTimeout(demoTimer);
    if (!demoPlaying || prefersReducedMotion) return;
    demoTimer = window.setTimeout(() => {
      if (demoIndex >= demo.steps.length - 1) {
        stopDemo();
        return;
      }
      setDemoStep(demoIndex + 1);
      scheduleDemo();
    }, DEMO_STEP_MS);
  }

  byId("demo-play").addEventListener("click", () => {
    if (prefersReducedMotion) {
      const last = (demo.steps || []).length - 1;
      setDemoStep(demoIndex < 0 || demoIndex >= last ? 0 : demoIndex + 1);
      text(byId("demo-play"), "次のStep →");
      return;
    }
    if (demoPlaying) {
      stopDemo();
      return;
    }
    demoPlaying = true;
    text(byId("demo-play"), "Ⅱ 一時停止");
    setDemoStep(0);
    scheduleDemo();
  });
  renderDemoSteps();
  if (prefersReducedMotion) text(byId("demo-play"), "Stepを見る →");

  const contextNodes = graph.nodes.filter((node) => node.type === "context");
  const contextById = new Map(contextNodes.map((node) => [node.id, node]));
  const contextList = byId("context-list");
  const search = byId("search");
  const priority = byId("priority");
  let selectedContextId = "";

  function searchableContextText(node) {
    const meta = node.metadata || {};
    const values = [node.label]
      .concat(meta.summary || [])
      .concat(meta.purpose || [])
      .concat(meta.tags || []);
    return values.join(" ").toLowerCase();
  }

  function selectContext(contextId) {
    const node = contextById.get(contextId);
    if (!node) return;
    selectedContextId = contextId;
    renderContextList();
    renderContextDetails(node);
  }

  function renderContextDetails(node) {
    const meta = node.metadata || {};
    text(byId("selected-title"), node.label);
    text(byId("selected-summary"), (meta.summary || []).join(" "));
    renderList("purpose", meta.purpose);
    renderList("decisions", meta.decisions);
    renderList("forbidden", meta.forbidden);
    renderList("related", meta.related);
    const source = meta.provenance || {};
    text(byId("source-path"), source.source_path || "");

    const relationBox = byId("relations");
    clear(relationBox);
    graph.edges
      .filter((edge) => edge.source === node.id || edge.target === node.id)
      .forEach((edge) => {
        const otherId = edge.source === node.id ? edge.target : edge.source;
        const other = contextById.get(otherId);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "relation";
        text(button, `${edge.relation}: ${(other && other.label) || otherId}`);
        if (other) button.addEventListener("click", () => selectContext(otherId));
        relationBox.appendChild(button);
      });
  }

  function renderContextList() {
    clear(contextList);
    const query = search.value.trim().toLowerCase();
    const matches = contextNodes.filter((node) => {
      const meta = node.metadata || {};
      return (!priority.value || meta.priority === priority.value) && (!query || searchableContextText(node).includes(query));
    });
    text(byId("context-count"), `${matches.length} / ${contextNodes.length} contexts`);
    matches.slice(0, 60).forEach((node) => {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(selectedContextId === node.id));
      text(button, node.label);
      button.addEventListener("click", () => selectContext(node.id));
      const item = document.createElement("li");
      item.appendChild(button);
      contextList.appendChild(item);
    });
  }

  byId("copy-source").addEventListener("click", () => copyText(byId("source-path").textContent));
  search.addEventListener("input", renderContextList);
  priority.addEventListener("change", renderContextList);
  renderContextList();
})();
