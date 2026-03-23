// =============================================================================
// script.js — Color Vision Detector
//
// Sections:
//   1. Ishihara test  (test.html)       — driven by PLATE_DATA from Flask
//   2. Farnsworth D-15 test (mosaic.html) — drag-and-drop arrangement test
// =============================================================================


// =============================================================================
// SECTION 1 — ISHIHARA TEST
// =============================================================================

let currentQuestion = 0;
let normalScore  = 0;
let protanScore  = 0;
let deutanScore  = 0;
let userAnswers  = [];

// ---------------------------------------------------------------------------
// DOMContentLoaded — boots whichever test is present on the page.
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", function () {

  // ── Ishihara (test.html) ─────────────────────────────────────────────────
  if (typeof PLATE_DATA !== "undefined" && Array.isArray(PLATE_DATA) && PLATE_DATA.length > 0) {
    console.log("PLATE_DATA loaded:", PLATE_DATA.length, "plates");
    loadPlate(0);

    const input = document.getElementById("answerInput");
    if (input) {
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") nextQuestion();
      });
    }
  }

  // ── Farnsworth D-15 (mosaic.html) ────────────────────────────────────────
  if (document.getElementById("discTray")) {
    initD15();
  }

});


// ---------------------------------------------------------------------------
// loadPlate — update the UI for plate at index i.
// ---------------------------------------------------------------------------
function loadPlate(index) {
  const plate = PLATE_DATA[index];

  const plateImage = document.getElementById("plateImage");
  if (plateImage) {
    plateImage.src = "/static/images/" + plate.image;
  }

  const questionCount = document.getElementById("questionCount");
  if (questionCount) {
    questionCount.innerText =
      "Question " + (index + 1) + " of " + PLATE_DATA.length;
  }

  const progressBar = document.getElementById("progressBar");
  if (progressBar) {
    progressBar.style.width = (index / PLATE_DATA.length * 100) + "%";
  }

  const answerInput = document.getElementById("answerInput");
  if (answerInput) {
    answerInput.value = "";
    answerInput.focus();
  }
}

// ---------------------------------------------------------------------------
// nextQuestion — called by the Next button and Enter key.
// ---------------------------------------------------------------------------
function nextQuestion() {
  const answerInput = document.getElementById("answerInput");
  if (!answerInput) return;

  const userAnswer = answerInput.value.trim();
  if (userAnswer === "") {
    alert("Please enter an answer before proceeding.\nType 0 if you cannot see any number.");
    return;
  }

  const plate = PLATE_DATA[currentQuestion];

  // Client-side tally (backend re-scores from answersJson; this is a fallback).
  const ua = userAnswer.toLowerCase();
  if (ua === (plate.normal_answer || "").toLowerCase())  normalScore++;
  if (plate.protan_answer && ua === plate.protan_answer.toLowerCase()) protanScore++;
  if (plate.deutan_answer && ua === plate.deutan_answer.toLowerCase()) deutanScore++;

  userAnswers.push({
    plateId:       plate.id,
    userAnswer:    userAnswer,
    question:      plate.description || ("Plate " + plate.id),
    correctAnswer: plate.normal_answer || "(nothing)"
  });

  currentQuestion++;

  if (currentQuestion < PLATE_DATA.length) {
    loadPlate(currentQuestion);
  } else {
    finishTest();
  }
}

// ---------------------------------------------------------------------------
// finishTest — populate the hidden form and submit to Flask.
// ---------------------------------------------------------------------------
function finishTest() {
  const total = PLATE_DATA.length;

  const form         = document.getElementById("ishiharaForm");
  const normalField  = document.getElementById("normalScoreField");
  const protanField  = document.getElementById("protanScoreField");
  const deutanField  = document.getElementById("deutanScoreField");
  const totalField   = document.getElementById("totalQuestionsField");
  const answersField = document.getElementById("answersJsonField");

  if (form && normalField && protanField && deutanField && totalField) {
    normalField.value  = normalScore.toString();
    protanField.value  = protanScore.toString();
    deutanField.value  = deutanScore.toString();
    totalField.value   = total.toString();

    if (answersField) {
      answersField.value = JSON.stringify(userAnswers);
    }

    form.submit();
    return;
  }

  // Fallback: redirect if form elements are missing.
  window.location.href = "/result";
}


// =============================================================================
// SECTION 2 — FARNSWORTH D-15 TEST
// =============================================================================

// ---------------------------------------------------------------------------
// Cap definitions — must stay in sync with app.py D15_CAPS and result.html.
// id 0  = reference cap (fixed, shown separately)
// id 1–14 = movable caps (user arranges these)
// id 15 = end cap (fixed)
// ---------------------------------------------------------------------------
const D15_CAPS = [
  { id:  0, label: "Cap 0",  hex: "#7b68b5" },  // 5P   5/4 — reference
  { id:  1, label: "Cap 1",  hex: "#8d64c0" },  // 7.5PB 5/6
  { id:  2, label: "Cap 2",  hex: "#5f77c8" },  // 10PB 5/6
  { id:  3, label: "Cap 3",  hex: "#4a8fc0" },  // 2.5B  5/6
  { id:  4, label: "Cap 4",  hex: "#3da4b0" },  // 5B    5/6
  { id:  5, label: "Cap 5",  hex: "#35b09a" },  // 7.5BG 5/6
  { id:  6, label: "Cap 6",  hex: "#40b07a" },  // 10BG  5/6
  { id:  7, label: "Cap 7",  hex: "#60aa5a" },  // 2.5G  5/6
  { id:  8, label: "Cap 8",  hex: "#8fa840" },  // 5G    5/6
  { id:  9, label: "Cap 9",  hex: "#b8a030" },  // 7.5GY 5/6
  { id: 10, label: "Cap 10", hex: "#d09428" },  // 10GY  5/6
  { id: 11, label: "Cap 11", hex: "#d47830" },  // 2.5Y  5/6
  { id: 12, label: "Cap 12", hex: "#cc5840" },  // 5YR   5/6
  { id: 13, label: "Cap 13", hex: "#bc4460" },  // 10R   5/6
  { id: 14, label: "Cap 14", hex: "#a04888" },  // 2.5RP 5/6
  { id: 15, label: "Cap 15", hex: "#8855a8" },  // 5RP   5/6 — end cap
];

const MOVABLE_IDS = D15_CAPS.slice(1, 15).map(c => c.id);  // ids 1–14
const REF_CAP     = D15_CAPS[0];
const END_CAP     = D15_CAPS[15];

// State
let d15TrayOrder      = [];   // current order of cap ids in the tray
let d15DragSrcIdx     = null; // index being dragged
let d15TouchSelected  = null; // index selected by first tap (mobile)

// ---------------------------------------------------------------------------
// initD15 — called on DOMContentLoaded when discTray exists.
// ---------------------------------------------------------------------------
function initD15() {
  // Paint fixed reference and end caps
  const refEl = document.getElementById("refCap");
  const endEl = document.getElementById("endCap");
  if (refEl) refEl.style.background = REF_CAP.hex;
  if (endEl) endEl.style.background = END_CAP.hex;

  // Tray drag-over highlight
  const tray = document.getElementById("discTray");
  if (tray) {
    tray.addEventListener("dragover",  function (e) {
      e.preventDefault();
      tray.classList.add("drag-over");
    });
    tray.addEventListener("dragleave", function () { tray.classList.remove("drag-over"); });
    tray.addEventListener("drop",      function () { tray.classList.remove("drag-over"); });
  }

  resetD15Tray();
}

// ---------------------------------------------------------------------------
// resetD15Tray — shuffle movable caps and render.
// ---------------------------------------------------------------------------
function resetD15Tray() {
  d15TouchSelected = null;
  d15TrayOrder = d15Shuffle([...MOVABLE_IDS]);
  renderD15Tray();
}

// ---------------------------------------------------------------------------
// d15Shuffle — Fisher-Yates in place.
// ---------------------------------------------------------------------------
function d15Shuffle(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

// ---------------------------------------------------------------------------
// renderD15Tray — rebuild disc DOM from d15TrayOrder.
// ---------------------------------------------------------------------------
function renderD15Tray() {
  const tray = document.getElementById("discTray");
  if (!tray) return;
  tray.innerHTML = "";

  d15TrayOrder.forEach(function (capId, idx) {
    const cap = D15_CAPS[capId];

    const wrapper = document.createElement("div");
    wrapper.className = "disc-wrapper";

    const disc = document.createElement("div");
    disc.className   = "disc";
    disc.style.background = cap.hex;
    disc.title       = cap.label;
    disc.draggable   = true;
    disc.dataset.idx = idx;

    // Desktop drag events
    disc.addEventListener("dragstart", d15DragStart);
    disc.addEventListener("dragover",  d15DragOver);
    disc.addEventListener("drop",      d15Drop);
    disc.addEventListener("dragend",   d15DragEnd);
    disc.addEventListener("dragenter", d15DragEnter);
    disc.addEventListener("dragleave", d15DragLeave);

    // Mobile touch events (tap-to-select, tap-to-swap)
    disc.addEventListener("touchstart", d15TouchStart, { passive: false });
    disc.addEventListener("touchmove",  function (e) { e.preventDefault(); }, { passive: false });

    const numLabel = document.createElement("div");
    numLabel.className   = "disc-number";
    numLabel.textContent = idx + 1;

    wrapper.appendChild(disc);
    wrapper.appendChild(numLabel);
    tray.appendChild(wrapper);
  });

  updateD15Pill();
}

// ---------------------------------------------------------------------------
// updateD15Pill — update the progress/hint pill text.
// ---------------------------------------------------------------------------
function updateD15Pill() {
  const pill = document.getElementById("progressPill");
  if (!pill) return;
  const isCorrect = d15TrayOrder.every(function (id, i) { return id === i + 1; });
  pill.textContent = isCorrect
    ? "✓ Looks great! Submit when ready."
    : d15TrayOrder.length + " discs arranged — drag to reorder";
}

// ---------------------------------------------------------------------------
// Drag & Drop handlers (desktop)
// ---------------------------------------------------------------------------
function d15DragStart(e) {
  d15DragSrcIdx = parseInt(e.currentTarget.dataset.idx);
  e.currentTarget.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
}

function d15DragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
}

function d15DragEnter(e) {
  e.currentTarget.classList.add("drag-target");
}

function d15DragLeave(e) {
  e.currentTarget.classList.remove("drag-target");
}

function d15Drop(e) {
  e.preventDefault();
  const dropIdx = parseInt(e.currentTarget.dataset.idx);
  if (d15DragSrcIdx === null || d15DragSrcIdx === dropIdx) return;

  const tmp = d15TrayOrder[d15DragSrcIdx];
  d15TrayOrder[d15DragSrcIdx] = d15TrayOrder[dropIdx];
  d15TrayOrder[dropIdx] = tmp;

  d15DragSrcIdx = null;
  renderD15Tray();
}

function d15DragEnd(e) {
  e.currentTarget.classList.remove("dragging");
  document.querySelectorAll(".drag-target").forEach(function (el) {
    el.classList.remove("drag-target");
  });
  d15DragSrcIdx = null;
}

// ---------------------------------------------------------------------------
// Touch handler (mobile) — tap first disc to select, tap second to swap.
// ---------------------------------------------------------------------------
function d15TouchStart(e) {
  e.preventDefault();
  const idx = parseInt(e.currentTarget.dataset.idx);

  if (d15TouchSelected === null) {
    // First tap — select and highlight
    d15TouchSelected = idx;
    e.currentTarget.style.border  = "3px solid #4facfe";
    e.currentTarget.style.transform = "scale(1.15)";
  } else if (d15TouchSelected === idx) {
    // Tap same disc — deselect
    d15TouchSelected = null;
    renderD15Tray();
  } else {
    // Second tap — swap
    const tmp = d15TrayOrder[d15TouchSelected];
    d15TrayOrder[d15TouchSelected] = d15TrayOrder[idx];
    d15TrayOrder[idx] = tmp;
    d15TouchSelected = null;
    renderD15Tray();
  }
}

// ---------------------------------------------------------------------------
// submitD15 — build full order and POST to Flask via hidden form.
// ---------------------------------------------------------------------------
function submitD15() {
  const fullOrder = [REF_CAP.id].concat(d15TrayOrder).concat([END_CAP.id]);
  const field = document.getElementById("orderField");
  const form  = document.getElementById("d15Form");
  if (field && form) {
    field.value = JSON.stringify(fullOrder);
    form.submit();
  }
}

// ---------------------------------------------------------------------------
// D-15 polar diagram — drawn on the result page.
// Called from result.html after the page loads, if canvas + data are present.
// ---------------------------------------------------------------------------
function drawD15Diagram(canvasId, userOrder) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !userOrder || !userOrder.length) return;

  const CAP_HEX = D15_CAPS.map(function (c) { return c.hex; });

  const ctx  = canvas.getContext("2d");
  const cx   = canvas.width  / 2;
  const cy   = canvas.height / 2;
  const R    = canvas.width  / 2 - 38;
  const discR = 16;

  function capAngle(capId) {
    return -Math.PI / 2 + (capId / 16) * 2 * Math.PI;
  }

  function capXY(capId) {
    const a = capAngle(capId);
    return { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
  }

  // Background ring
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, 2 * Math.PI);
  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  ctx.lineWidth   = 1;
  ctx.stroke();

  // Ideal grey order lines (0→1→2…→15)
  for (let i = 0; i < 15; i++) {
    const a = capXY(i);
    const b = capXY(i + 1);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = "rgba(180,180,180,0.22)";
    ctx.lineWidth   = 1.5;
    ctx.stroke();
  }

  // User arrangement lines (coloured)
  for (let i = 0; i < userOrder.length - 1; i++) {
    const a = capXY(userOrder[i]);
    const b = capXY(userOrder[i + 1]);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = CAP_HEX[userOrder[i]];
    ctx.lineWidth   = 2.5;
    ctx.stroke();
  }

  // Disc dots + labels
  for (let id = 0; id <= 15; id++) {
    const { x, y } = capXY(id);
    ctx.beginPath();
    ctx.arc(x, y, discR, 0, 2 * Math.PI);
    ctx.fillStyle   = CAP_HEX[id];
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.5)";
    ctx.lineWidth   = 2;
    ctx.stroke();

    ctx.fillStyle    = "white";
    ctx.font         = "bold 10px Segoe UI";
    ctx.textAlign    = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(id === 0 ? "R" : String(id), x, y);
  }
}


// =============================================================================
// SHARED UTILITY — B/W Mode toggle (used by all pages)
// =============================================================================
function toggleBW() {
  document.body.classList.toggle("bw-mode");
  localStorage.setItem("mode",
    document.body.classList.contains("bw-mode") ? "bw" : "color"
  );
}

// Apply saved mode on every page load
if (localStorage.getItem("mode") === "bw") {
  document.body.classList.add("bw-mode");
}