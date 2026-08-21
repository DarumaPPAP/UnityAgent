(function () {
  "use strict";
  const graph = window.__CONTEXT_GRAPH__ || { nodes: [], edges: [] };
  const nodes = graph.nodes.filter((node) => node.type === "context").slice(0, 25);
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const list = document.getElementById("context-list");
  const search = document.getElementById("search");
  const priority = document.getElementById("priority");
  let selected = null;

  function text(element, value) { element.textContent = value == null ? "" : String(value); }
  function listText(id, values) {
    const target = document.getElementById(id);
    target.replaceChildren();
    (values || []).forEach((value) => {
      const item = document.createElement("li");
      text(item, typeof value === "string" ? value : (value.label || value.id || ""));
      target.appendChild(item);
    });
  }
  function renderDetails(node) {
    const meta = node.metadata || {};
    text(document.getElementById("selected-title"), node.label);
    text(document.getElementById("selected-summary"), (meta.summary || []).join(" "));
    listText("purpose", meta.purpose);
    listText("decisions", meta.decisions);
    listText("forbidden", meta.forbidden);
    listText("related", meta.related);
    const source = meta.provenance || {};
    text(document.getElementById("source-path"), source.source_path || "");
    const relationBox = document.getElementById("relations");
    relationBox.replaceChildren();
    graph.edges.filter((edge) => edge.source === node.id || edge.target === node.id).forEach((edge) => {
      const item = document.createElement("span");
      item.className = "relation";
      const other = byId.get(edge.source === node.id ? edge.target : edge.source);
      text(item, `${edge.relation}: ${(other && other.label) || edge.target}`);
      relationBox.appendChild(item);
    });
  }
  function renderList() {
    list.replaceChildren();
    const query = search.value.toLowerCase();
    nodes.filter((node) => {
      const meta = node.metadata || {};
      return (!priority.value || meta.priority === priority.value) && (!query || node.label.toLowerCase().includes(query));
    }).slice(0, 20).forEach((node) => {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(selected === node.id));
      text(button, node.label);
      button.addEventListener("click", () => { selected = node.id; renderList(); renderDetails(node); });
      const item = document.createElement("li"); item.appendChild(button); list.appendChild(item);
    });
  }
  document.getElementById("copy-source").addEventListener("click", () => {
    const value = document.getElementById("source-path").textContent;
    if (navigator.clipboard && value) navigator.clipboard.writeText(value);
  });
  search.addEventListener("input", renderList); priority.addEventListener("change", renderList);
  renderList();
})();
