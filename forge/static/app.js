"use strict";
const $ = (selector) => document.querySelector(selector);
let currentRun = null;
let activeEvents = null;
let documentsSignature = "";
let modelsReady = false;
let busy = false;
let selectedDocuments = new Set();

function textElement(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}
function notice(message = "") {
  $("#notice").textContent = message;
  $("#notice").hidden = !message;
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "Please check the form and try again.";
    throw new Error(detail);
  }
  return body;
}
function post(body = {}) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}
function controls() {
  $("#ask-button").disabled = busy || !modelsReady;
  $("#cancel-button").hidden = !busy;
}
async function readiness() {
  try {
    await api("/api/ready");
    modelsReady = true;
    $("#model-status").textContent = "● Local models ready · qwen3:4b + nomic-embed-text · Files stay on this machine";
    $("#model-status").classList.remove("unavailable");
  } catch (error) {
    modelsReady = false;
    $("#model-status").textContent = "Models unavailable. " + error.message + " See README for the local setup commands.";
    $("#model-status").classList.add("unavailable");
  }
  controls();
}
async function loadDocuments() {
  const docs = await api("/api/documents");
  const signature = JSON.stringify(docs);
  if (signature === documentsSignature) return;
  documentsSignature = signature;
  $("#doc-count").textContent = docs.length;
  const list = $("#documents");
  list.replaceChildren();
  if (!docs.length) list.append(textElement("li", "Your library is empty. Add a document to get started.", "empty"));
  selectedDocuments = new Set([...selectedDocuments].filter((id) => docs.some((doc) => doc.id === id)));
  for (const doc of docs) {
    const li = document.createElement("li");
    const row = textElement("div", "", "document-row");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = "doc-" + doc.id;
    input.checked = selectedDocuments.has(doc.id);
    input.disabled = doc.status !== "ready";
    input.addEventListener("change", () => input.checked ? selectedDocuments.add(doc.id) : selectedDocuments.delete(doc.id));
    const label = textElement("label", doc.name);
    label.htmlFor = input.id;
    row.append(input, label);
    const details = textElement("div", "", "doc-details");
    details.append(textElement("div", `${doc.status} · version ${doc.version} · ${doc.pages} page${doc.pages === 1 ? "" : "s"}`));
    if (doc.extraction_ms != null) details.append(textElement("div", `Extraction: ${Math.round(doc.extraction_ms)} ms`));
    if (doc.error) details.append(textElement("p", doc.error));
    for (const warning of doc.warnings) details.append(textElement("p", warning));
    const actions = textElement("div", "", "doc-actions");
    if (doc.status === "failed") {
      const retry = textElement("button", "Retry indexing", "text-button");
      retry.addEventListener("click", async () => {
        try { await api(`/api/documents/${doc.id}/retry`, post()); await loadDocuments(); }
        catch (error) { notice(error.message); }
      });
      actions.append(retry);
    }
    const remove = textElement("button", "Delete", "text-button delete");
    remove.setAttribute("aria-label", "Delete " + doc.name);
    remove.addEventListener("click", async () => {
      if (!window.confirm("Delete this document and saved answers that use it? Active questions will stop.")) return;
      try {
        await api(`/api/documents/${doc.id}`, { method: "DELETE" });
        if (currentRun) await renderRun(currentRun);
        await refresh();
      } catch (error) { notice(error.message); }
    });
    actions.append(remove);
    details.append(actions);
    li.append(row, details);
    list.append(li);
  }
}
async function showSource(id) {
  try {
    const source = await api("/api/sources/" + encodeURIComponent(id));
    $("#source-title").textContent = source.name;
    $("#source-meta").textContent = `Page ${source.page} · version ${source.version}`;
    $("#source-text").textContent = source.text;
    $("#source-dialog").showModal();
  } catch (error) { notice(error.message); }
}
async function renderRun(id) {
  const run = await api("/api/runs/" + id);
  currentRun = id;
  $("#run-status").textContent = run.status.toUpperCase();
  $("#answer-heading").textContent = run.status === "redacted" ? "Source document deleted" : (run.question || "Your answer");
  $("#answer").textContent = run.status === "redacted"
    ? "This answer was removed with its source document."
    : run.answer || run.error || "Reading your documents…";
  $("#citations").replaceChildren();
  for (const [index, citation] of run.citations.entries()) {
    const button = textElement("button", `${index + 1}. ${citation.name} · p. ${citation.page}`, "citation");
    button.title = citation.quote;
    button.addEventListener("click", () => showSource(citation.id));
    $("#citations").append(button);
  }
  $("#timings").replaceChildren();
  const labels = { retrieval_ms: "Retrieval", first_token_ms: "First model token", total_ms: "Total" };
  for (const [key, value] of Object.entries(run.timings)) {
    const item = document.createElement("div");
    item.append(textElement("dt", labels[key] || key), textElement("dd", `${Math.round(value)} ms`));
    $("#timings").append(item);
  }
  busy = ["running", "queued"].includes(run.status);
  controls();
  return run;
}
function subscribe(id) {
  if (activeEvents) activeEvents.close();
  const events = new EventSource(`/api/runs/${id}/events`);
  activeEvents = events;
  let answerStarted = false;
  events.addEventListener("progress", (event) => {
    if (currentRun === id) $("#run-status").textContent = JSON.parse(event.data).message;
  });
  events.addEventListener("answer", (event) => {
    if (currentRun !== id) return;
    if (!answerStarted) { $("#answer").textContent = ""; answerStarted = true; }
    $("#answer").append(document.createTextNode(JSON.parse(event.data).text));
  });
  events.addEventListener("done", async () => {
    events.close();
    try { if (currentRun === id) await renderRun(id); await loadHistory(); }
    catch (error) { notice(error.message); }
  });
  events.onerror = async () => {
    events.close();
    try {
      const run = await api("/api/runs/" + id);
      if (["queued", "running"].includes(run.status)) {
        notice("The live connection stopped. The question is still running; select it in Recent questions to reconnect.");
      }
      if (currentRun === id) await renderRun(id);
      await loadHistory();
    } catch { notice("The app connection stopped. Reload when the local server is available."); }
  };
}
async function loadHistory() {
  const runs = await api("/api/runs");
  const list = $("#history");
  list.replaceChildren();
  if (!runs.length) list.append(textElement("li", "Your questions will appear here.", "empty"));
  for (const run of runs) {
    const li = document.createElement("li");
    const button = textElement("button", run.question || "Answer removed with its source", "text-button");
    button.addEventListener("click", async () => {
      try {
        if (activeEvents) activeEvents.close();
        await renderRun(run.id);
        if (busy) subscribe(run.id);
        $("#answer-heading").scrollIntoView({ block: "nearest" });
      } catch (error) { notice(error.message); }
    });
    li.append(button, textElement("span", run.status, "run-label"));
    list.append(li);
  }
}
async function refresh() { await loadDocuments(); await loadHistory(); }
$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault(); notice();
  const input = $("#document-file");
  if (!input.files.length) return;
  if (input.files[0].size > 20 * 1024 * 1024) { notice("Files must be 20 MB or smaller."); return; }
  $("#upload-button").disabled = true;
  $("#upload-button").textContent = "Uploading…";
  try {
    const data = new FormData(); data.append("file", input.files[0]);
    const result = await api("/api/documents", { method: "POST", body: data });
    if (result.duplicate) notice("This document is already in your library.");
    input.value = ""; await loadDocuments();
  } catch (error) { notice(error.message); }
  finally { $("#upload-button").disabled = false; $("#upload-button").textContent = "Upload document ↑"; }
});
$("#question-form").addEventListener("submit", async (event) => {
  event.preventDefault(); notice();
  busy = true; controls();
  try {
    const result = await api("/api/questions", post({ question: $("#question").value, document_ids: [...selectedDocuments] }));
    await renderRun(result.id); subscribe(result.id); await loadHistory();
  } catch (error) { busy = false; controls(); notice(error.message); }
});
$("#cancel-button").addEventListener("click", async () => {
  if (!currentRun) return;
  try { await api(`/api/runs/${currentRun}/cancel`, post()); await renderRun(currentRun); await loadHistory(); }
  catch (error) { notice(error.message); }
});
$("#close-source").addEventListener("click", () => $("#source-dialog").close());
Promise.all([readiness(), refresh()]).catch((error) => notice(error.message));
setInterval(() => loadDocuments().catch(() => {}), 2000);
setInterval(readiness, 15000);
