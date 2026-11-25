/* AI Research Assistant - frontend logic (vanilla JS, no build step) */
const C = window.APP_CONFIG, $ = id => document.getElementById(id), $$ = s => [...document.querySelectorAll(s)];
const store = { get: k => sessionStorage.getItem(k), set: (k, v) => sessionStorage.setItem(k, v), clear: () => sessionStorage.clear() };
const S = { mode: "signin", sessionId: null, docs: [], transcript: [], poll: null };

const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------- theme ---------- */
document.documentElement.dataset.theme = localStorage.getItem("theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
$("theme").onclick = () => { const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = t; localStorage.setItem("theme", t); };
$("menuBtn").onclick = () => $("sidebar").classList.toggle("open");

/* ---------- Cognito over REST (no SDK) ---------- */
async function cognito(target, payload) {
  const r = await fetch(`https://cognito-idp.${C.region}.amazonaws.com/`, { method: "POST",
    headers: { "Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "AWSCognitoIdentityProviderService." + target }, body: JSON.stringify(payload) });
  const d = await r.json();
  if (!r.ok) throw new Error(d.message || d.__type || "Authentication error");
  return d;
}
const TITLES = { signin: ["Sign in", "Sign in"], signup: ["Create account", "Sign up"], confirm: ["Verify your email", "Confirm"], forgot: ["Reset password", "Send code"], reset: ["Choose a new password", "Reset password"] };
function renderAuth() {
  $("authTitle").textContent = TITLES[S.mode][0]; $("authBtn").textContent = TITLES[S.mode][1];
  $("code").classList.toggle("hidden", !["confirm", "reset"].includes(S.mode));
  $("password").classList.toggle("hidden", S.mode === "confirm" || S.mode === "forgot");
  $("password").placeholder = S.mode === "reset" ? "New password" : "Password (8+, upper, lower, number)";
  $("toggleAuth").textContent = S.mode === "signin" ? "No account? Sign up" : "Back to sign in";
  $("authError").textContent = "";
}
$("toggleAuth").onclick = () => { S.mode = S.mode === "signin" ? "signup" : "signin"; renderAuth(); };
$("forgot").onclick = () => { S.mode = "forgot"; renderAuth(); };
$("authBtn").onclick = async () => {
  const email = $("email").value.trim(), password = $("password").value, code = $("code").value.trim();
  $("authError").textContent = ""; $("authBtn").disabled = true;
  try {
    if (S.mode === "signup") { await cognito("SignUp", { ClientId: C.clientId, Username: email, Password: password, UserAttributes: [{ Name: "email", Value: email }] }); S.mode = "confirm"; renderAuth(); }
    else if (S.mode === "confirm") { await cognito("ConfirmSignUp", { ClientId: C.clientId, Username: email, ConfirmationCode: code }); S.mode = "signin"; renderAuth(); $("authError").textContent = "Verified! Please sign in."; }
    else if (S.mode === "forgot") { await cognito("ForgotPassword", { ClientId: C.clientId, Username: email }); S.mode = "reset"; renderAuth(); $("authError").textContent = "Code sent to your email."; }
    else if (S.mode === "reset") { await cognito("ConfirmForgotPassword", { ClientId: C.clientId, Username: email, ConfirmationCode: code, Password: password }); S.mode = "signin"; renderAuth(); $("authError").textContent = "Password changed. Sign in."; }
    else {
      const r = (await cognito("InitiateAuth", { AuthFlow: "USER_PASSWORD_AUTH", ClientId: C.clientId, AuthParameters: { USERNAME: email, PASSWORD: password } })).AuthenticationResult;
      store.set("idToken", r.IdToken); store.set("refresh", r.RefreshToken); store.set("email", email); showApp();
    }
  } catch (e) { $("authError").textContent = e.message; }
  $("authBtn").disabled = false;
};
const logout = () => { store.clear(); clearInterval(S.poll); location.reload(); };
$("logout").onclick = logout;
async function refreshToken() {
  try { const r = await cognito("InitiateAuth", { AuthFlow: "REFRESH_TOKEN_AUTH", ClientId: C.clientId, AuthParameters: { REFRESH_TOKEN: store.get("refresh") } }); store.set("idToken", r.AuthenticationResult.IdToken); return true; }
  catch { return false; }
}

/* ---------- API helper (auto token refresh) ---------- */
async function api(path, opts = {}, retry = true) {
  const r = await fetch(C.apiUrl + path, { ...opts, headers: { "Content-Type": "application/json", Authorization: store.get("idToken") } });
  if (r.status === 401) { if (retry && await refreshToken()) return api(path, opts, false); logout(); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || d.message || "Request failed (" + r.status + ")");
  return d;
}

/* ---------- tabs ---------- */
$$(".tab").forEach(b => b.onclick = () => {
  $$(".tab").forEach(t => t.classList.toggle("active", t === b));
  $$(".tabpane").forEach(p => p.classList.add("hidden")); $("tab-" + b.dataset.tab).classList.remove("hidden");
  if (b.dataset.tab === "dash") loadStats();
});

/* ---------- app bootstrap ---------- */
function showApp() {
  $("auth").classList.add("hidden"); $("app").classList.remove("hidden");
  $("who").textContent = store.get("email"); loadDocs(); loadChats(); S.poll = setInterval(loadDocs, 5000);
}

/* ---------- documents ---------- */
async function loadDocs() {
  try {
    const { documents } = await api("/documents"); S.docs = documents;
    const checked = new Set($$(".sel:checked").map(c => c.value)), box = $("docs"); box.innerHTML = "";
    if (!documents.length) box.innerHTML = '<p class="hint">No documents yet.</p>';
    documents.forEach(d => {
      const row = document.createElement("div"); row.className = "doc";
      const cb = Object.assign(document.createElement("input"), { type: "checkbox", className: "sel", value: d.docId, disabled: d.status !== "READY", checked: checked.has(d.docId) });
      const name = document.createElement("div"); name.className = "name"; name.title = "Open original";
      name.textContent = (d.ext === "pdf" ? "📕 " : "📄 ") + d.filename;
      const meta = document.createElement("div"); meta.className = "hint";
      meta.textContent = d.status === "READY" ? `${d.pages} ${d.ext === "pdf" ? "pages" : "sections"} · ${d.chunks} chunks${d.ocr ? " · OCR" : ""}` : (d.error || "");
      name.appendChild(meta); name.onclick = () => openDoc(d.docId);
      const badge = Object.assign(document.createElement("span"), { className: "badge " + d.status, textContent: d.status });
      const del = Object.assign(document.createElement("button"), { className: "x", textContent: "×", title: "Delete" });
      del.onclick = async () => { if (confirm("Delete " + d.filename + "?")) { await api("/documents/" + d.docId, { method: "DELETE" }); loadDocs(); } };
      row.append(cb, name, badge, del); box.appendChild(row);
    });
    const ready = documents.filter(d => d.status === "READY");
    const keep = $("studyDoc").value;
    $("studyDoc").innerHTML = ready.map(d => `<option value="${esc(d.docId)}">${esc(d.filename)}</option>`).join("") || "<option value=''>No ready documents</option>";
    if (keep) $("studyDoc").value = keep;
    renderChips(ready.length > 0);
  } catch (e) { /* transient */ }
}
async function openDoc(docId, page) {
  try { const r = await api(`/documents/${docId}/url`); window.open(r.url + (r.ext === "pdf" && page ? "#page=" + page : ""), "_blank", "noopener"); }
  catch (e) { alert(e.message); }
}
const drop = $("drop");
drop.onclick = () => $("file").click();
["dragover", "dragenter"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => uploadFiles([...e.dataTransfer.files]));
$("file").onchange = () => { uploadFiles([...$("file").files]); $("file").value = ""; };

function putToS3(upload, file) {
  return new Promise((res, rej) => {
    const fd = new FormData(); Object.entries(upload.fields).forEach(([k, v]) => fd.append(k, v)); fd.append("file", file);
    const x = new XMLHttpRequest(); x.open("POST", upload.url);
    x.upload.onprogress = e => { $("bar").style.width = (e.loaded / e.total * 100) + "%"; };
    x.onload = () => x.status < 300 ? res() : rej(new Error("S3 upload failed (" + x.status + ")"));
    x.onerror = () => rej(new Error("Network error during upload")); x.send(fd);
  });
}
async function uploadFiles(files) {
  $("uploadMsg").textContent = "";
  for (const f of files) {
    if (!/\.(pdf|txt|md)$/i.test(f.name)) { $("uploadMsg").textContent = "Only PDF, TXT and MD files are supported."; continue; }
    if (f.size > 20 * 1024 * 1024) { $("uploadMsg").textContent = f.name + " exceeds 20 MB."; continue; }
    $("progress").classList.remove("hidden"); $("bar").style.width = "0";
    try { const { upload } = await api("/documents/upload-url", { method: "POST", body: JSON.stringify({ filename: f.name }) }); await putToS3(upload, f); }
    catch (e) { $("uploadMsg").textContent = e.message; }
    $("progress").classList.add("hidden"); loadDocs();
  }
}

/* ---------- markdown (escape first => XSS-safe) ---------- */
function inline(t) { return t.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>").replace(/\[(\d+)\]/g, '<span class="cite" data-ref="$1">$1</span>'); }
function md(src) {
  let html = "", ul = false, ol = false; const close = () => { if (ul) html += "</ul>"; if (ol) html += "</ol>"; ul = ol = false; };
  for (const line of esc(src).split("\n")) {
    let m;
    if ((m = line.match(/^#{1,4}\s+(.*)/))) { close(); html += `<h4>${inline(m[1])}</h4>`; }
    else if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (!ul) { close(); html += "<ul>"; ul = true; } html += `<li>${inline(m[1])}</li>`; }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (!ol) { close(); html += "<ol>"; ol = true; } html += `<li>${inline(m[1])}</li>`; }
    else if (!line.trim()) close(); else { close(); html += `<p>${inline(line)}</p>`; }
  }
  close(); return html;
}

/* ---------- chat ---------- */
function addUser(text) { const m = document.createElement("div"); m.className = "msg user"; m.textContent = text; $("chat").appendChild(m); scrollChat(); }
function scrollChat() { $("chat").scrollTop = $("chat").scrollHeight; }
function renderBot(data, el) {
  el = el || Object.assign(document.createElement("div"), { className: "msg bot" }); el.innerHTML = "";
  const body = document.createElement("div"); body.className = "body"; body.innerHTML = md(data.text ?? data.answer); el.appendChild(body);
  const meta = document.createElement("div"); meta.className = "meta";
  if (data.confidence && data.confidence !== "none") meta.innerHTML += `<span class="pill ${data.confidence}">confidence: ${data.confidence}</span>`;
  if (data.latencyMs) meta.innerHTML += `<span class="pill">${(data.latencyMs / 1000).toFixed(1)}s</span>`;
  if (data.usage && data.usage.inputTokens) meta.innerHTML += `<span class="pill">${data.usage.inputTokens + data.usage.outputTokens} tokens</span>`;
  const mk = (label, fn) => { const b = document.createElement("button"); b.textContent = label; b.onclick = fn; meta.appendChild(b); };
  mk("👍", () => sendFeedback(data, "up")); mk("👎", () => sendFeedback(data, "down"));
  mk("🔊", () => { speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(body.textContent)); });
  mk("📋", () => navigator.clipboard.writeText(body.textContent)); el.appendChild(meta);
  if (data.rewrittenQuestion && data.rewrittenQuestion !== data.question && data.question) { const r = document.createElement("div"); r.className = "hint"; r.textContent = "Searched for: " + data.rewrittenQuestion; el.appendChild(r); }
  const sources = data.sources || [];
  if (sources.length) {
    const box = document.createElement("div"); box.className = "sources"; box.append("Sources:");
    sources.forEach(s => {
      const det = document.createElement("details"); det.dataset.src = s.ref;
      const sum = document.createElement("summary"); sum.textContent = `[${s.ref}] ${s.filename} — page ${s.page} · similarity ${s.score}`;
      const sn = document.createElement("div"); sn.className = "snippet"; sn.textContent = "“" + s.snippet + "…”";
      const open = document.createElement("button"); open.className = "small ghost"; open.textContent = "Open at page " + s.page; open.onclick = () => openDoc(s.docId, s.page);
      det.append(sum, sn, open); box.appendChild(det);
    });
    el.appendChild(box);
    el.querySelectorAll(".cite").forEach(c => c.onclick = () => { const d = el.querySelector(`details[data-src="${c.dataset.ref}"]`); if (d) { d.open = true; d.classList.add("flash"); d.scrollIntoView({ block: "nearest" }); setTimeout(() => d.classList.remove("flash"), 1500); } });
  }
  return el;
}
async function sendFeedback(data, rating) { try { await api("/feedback", { method: "POST", body: JSON.stringify({ sessionId: S.sessionId, messageId: data.messageId, rating }) }); } catch (e) { /* ignore */ } }

async function ask(text) {
  const q = (text || $("q").value).trim(); if (!q) return;
  $("q").value = ""; addUser(q); $("send").disabled = true;
  const bot = Object.assign(document.createElement("div"), { className: "msg bot", textContent: "Searching your documents…" }); $("chat").appendChild(bot); scrollChat();
  try {
    const docIds = $$(".sel:checked").map(c => c.value);
    const res = await api("/ask", { method: "POST", body: JSON.stringify({ question: q, docIds, sessionId: S.sessionId, style: $("style").value }) });
    S.sessionId = res.sessionId; res.question = q; renderBot(res, bot);
    S.transcript.push({ q, a: res.answer, sources: res.sources }); loadChats();
  } catch (e) { bot.textContent = "⚠️ " + e.message; }
  $("send").disabled = false; scrollChat();
}
$("send").onclick = () => ask(); $("q").addEventListener("keydown", e => { if (e.key === "Enter") ask(); });
function renderChips(has) {
  $("chips").innerHTML = has ? ["Summarize the main ideas", "List the key definitions", "What are the conclusions?", "Explain this like I'm a beginner"].map(t => `<span class="chip">${t}</span>`).join("") : "";
  $$(".chip").forEach(c => c.onclick = () => ask(c.textContent));
}
$("newChat").onclick = () => { S.sessionId = null; S.transcript = []; $("chat").innerHTML = ""; addBotNote("New chat started. Ask me about your documents."); loadChats(); };
function addBotNote(t) { const m = Object.assign(document.createElement("div"), { className: "msg bot" }); m.innerHTML = `<div class="body">${esc(t)}</div>`; $("chat").appendChild(m); }
async function loadChats() {
  try {
    const { chats } = await api("/chats"), box = $("chats"); box.innerHTML = chats.length ? "" : '<p class="hint">No chats yet.</p>';
    chats.forEach(c => {
      const it = document.createElement("div"); it.className = "chat-item" + (c.sessionId === S.sessionId ? " active" : "");
      const t = document.createElement("span"); t.textContent = "💬 " + c.title; t.onclick = () => openChat(c.sessionId);
      const x = Object.assign(document.createElement("button"), { className: "x", textContent: "×" });
      x.onclick = async () => { await api("/chats/" + c.sessionId, { method: "DELETE" }); if (S.sessionId === c.sessionId) $("newChat").click(); else loadChats(); };
      it.append(t, x); box.appendChild(it);
    });
  } catch (e) { /* ignore */ }
}
async function openChat(sid) {
  const { messages } = await api("/chats/" + sid); S.sessionId = sid; S.transcript = []; $("chat").innerHTML = "";
  messages.forEach(m => { if (m.role === "user") addUser(m.text); else { $("chat").appendChild(renderBot({ text: m.text, sources: m.sources, confidence: m.confidence, messageId: m.messageId })); } });
  scrollChat(); loadChats();
}
$("exportChat").onclick = () => {
  const els = [...$("chat").children]; let out = "# AI Research Assistant — chat export\n\n";
  els.forEach(e => { out += (e.classList.contains("user") ? "**You:** " : "**Assistant:** ") + (e.querySelector(".body")?.textContent || e.textContent) + "\n\n"; });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([out], { type: "text/markdown" })), download: "chat-export.md" }); a.click();
};
/* voice input */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SR) $("mic").classList.add("hidden"); else $("mic").onclick = () => { const r = new SR(); r.lang = "en-US"; r.onresult = e => { $("q").value = e.results[0][0].transcript; ask(); }; r.start(); };

/* ---------- study studio ---------- */
$("studyGo").onclick = async () => {
  const docId = $("studyDoc").value; if (!docId) return;
  $("studyGo").disabled = true; $("studyOut").innerHTML = ""; $("studyStatus").textContent = "⏳ Generating… this can take up to a minute for large documents.";
  try {
    const { jobId } = await api("/study", { method: "POST", body: JSON.stringify({ docId, mode: $("studyMode").value, count: +$("studyCount").value }) });
    for (let i = 0; i < 100; i++) {
      await new Promise(r => setTimeout(r, 3000)); const j = await api("/study/" + jobId);
      if (j.status === "DONE") { $("studyStatus").textContent = ""; renderStudy(j.mode, j.result); break; }
      if (j.status === "FAILED") throw new Error(j.error);
    }
  } catch (e) { $("studyStatus").textContent = "⚠️ " + e.message; }
  $("studyGo").disabled = false;
};
function renderStudy(mode, r) {
  const out = $("studyOut");
  if (mode === "summary") out.innerHTML = `<div class="msg bot" style="max-width:100%"><div class="body">${md(r.markdown)}</div></div>`;
  else if (mode === "flashcards") {
    out.innerHTML = `<p class="hint">Click a card to flip it.</p><div class="cards">${r.cards.map(c => `<div class="flash-card"><div class="flash-inner"><div class="face">${esc(c.q)}</div><div class="face back">${esc(c.a)}${c.page ? `<br><span class="hint">p.${esc(c.page)}</span>` : ""}</div></div></div>`).join("")}</div>`;
    $$(".flash-card").forEach(c => c.onclick = () => c.classList.toggle("flipped"));
  } else if (mode === "keyterms") {
    out.innerHTML = `<table><tr><th>Term</th><th>Definition</th><th>Page</th></tr>${r.terms.map(t => `<tr><td><b>${esc(t.term)}</b></td><td>${esc(t.definition)}</td><td>${esc(t.page ?? "")}</td></tr>`).join("")}</table>`;
  } else renderQuiz(r.questions);
}
function renderQuiz(qs) {
  const out = $("studyOut"); out.innerHTML = qs.map((q, i) => `<div class="q" data-i="${i}"><b>${i + 1}. ${esc(q.question)}</b>${q.options.map((o, j) => `<label><input type="radio" name="q${i}" value="${j}"> ${esc(o)}</label>`).join("")}<div class="expl hidden">${esc(q.explanation)}${q.page ? " (p." + esc(q.page) + ")" : ""}</div></div>`).join("") + `<p><button id="grade">Submit answers</button> <b id="score"></b></p>`;
  $("grade").onclick = () => {
    let score = 0;
    qs.forEach((q, i) => {
      const box = out.querySelector(`.q[data-i="${i}"]`), labels = box.querySelectorAll("label"), pick = box.querySelector("input:checked");
      labels[q.answerIndex].classList.add("right"); if (pick && +pick.value === q.answerIndex) score++; else if (pick) labels[+pick.value].classList.add("wrong");
      box.querySelector(".expl").classList.remove("hidden");
    });
    $("score").textContent = `Score: ${score} / ${qs.length}`;
  };
}

/* ---------- dashboard ---------- */
async function loadStats() {
  const s = await api("/stats");
  const items = [["Documents", s.documents], ["Ready", s.ready], ["Pages", s.pages], ["Chunks indexed", s.chunks], ["OCR docs", s.ocrDocuments], ["Questions asked", s.questions], ["👍", s.thumbsUp], ["👎", s.thumbsDown]];
  $("stats").innerHTML = items.map(([l, v]) => `<div class="stat"><b>${v}</b>${l}</div>`).join("");
  $("libTable").innerHTML = `<table><tr><th>File</th><th>Status</th><th>Pages</th><th>Chunks</th><th>Added</th></tr>${S.docs.map(d => `<tr><td>${esc(d.filename)}</td><td>${esc(d.status)}</td><td>${esc(d.pages ?? "")}</td><td>${esc(d.chunks ?? "")}</td><td>${esc((d.createdAt || "").slice(0, 10))}</td></tr>`).join("")}</table>`;
}

renderAuth();
if (store.get("idToken")) showApp();
