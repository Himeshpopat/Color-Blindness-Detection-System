// Ishihara questions configuration (image paths are served from Flask static)
const questions = [
  { image: "/static/images/test1.png", normal: "29", protan: "70", deutan: "70" },
  { image: "/static/images/test2.png", normal: "12", protan: "12", deutan: "12" },
  { image: "/static/images/test3.png", normal: "8", protan: "3", deutan: "3" },
  { image: "/static/images/test4.png", normal: "45", protan: "15", deutan: "15" },
  { image: "/static/images/test5.png", normal: "74", protan: "21", deutan: "21" },
  { image: "/static/images/test6.png", normal: "27", protan: "17", deutan: "17" },
  { image: "/static/images/test7.png", normal: "2", protan: "?", deutan: "?" },
  { image: "/static/images/test8.png", normal: "6", protan: "5", deutan: "5" },
  { image: "/static/images/test9.png", normal: "42", protan: "?", deutan: "?" },
  { image: "/static/images/test10.png", normal: "16", protan: "6", deutan: "6" }
];

let currentQuestion = 0;
let normalScore = 0;
let protanScore = 0;
let deutanScore = 0;

function nextQuestion() {
  const answerInput = document.getElementById("answerInput");
  if (!answerInput) return;

  const userAnswer = answerInput.value.trim();

  if (userAnswer === "") {
    alert("Please enter an answer before proceeding.");
    return;
  }

  if (userAnswer === questions[currentQuestion].normal) normalScore++;
  if (userAnswer === questions[currentQuestion].protan) protanScore++;
  if (userAnswer === questions[currentQuestion].deutan) deutanScore++;

  currentQuestion++;

  if (currentQuestion < questions.length) {
    const plateImage = document.getElementById("plateImage");
    if (plateImage) {
      plateImage.src = questions[currentQuestion].image;
    }

    const questionCount = document.getElementById("questionCount");
    if (questionCount) {
      questionCount.innerText =
        "Question " + (currentQuestion + 1) + " of " + questions.length;
    }

    answerInput.value = "";

    const progress = (currentQuestion / questions.length) * 100;
    const progressBar = document.getElementById("progressBar");
    if (progressBar) {
      progressBar.style.width = progress + "%";
    }
  } else {
    finishTest();
  }
}

function finishTest() {
  const total = questions.length;

  // Prefer backend evaluation: submit scores to Flask
  const form = document.getElementById("ishiharaForm");
  const normalField = document.getElementById("normalScoreField");
  const protanField = document.getElementById("protanScoreField");
  const deutanField = document.getElementById("deutanScoreField");
  const totalField = document.getElementById("totalQuestionsField");

  if (form && normalField && protanField && deutanField && totalField) {
    normalField.value = normalScore.toString();
    protanField.value = protanScore.toString();
    deutanField.value = deutanScore.toString();
    totalField.value = total.toString();

    form.submit();
    return;
  }

  // Fallback to old client-side behaviour if form is missing
  const percentage = Math.round((normalScore / total) * 100);
  let result = "";

  if (percentage >= 80) {
    result = "Normal Vision";
  } else if (protanScore > deutanScore) {
    result = "Possible Protanopia";
  } else {
    result = "Possible Deuteranopia";
  }

  const report = {
    score: normalScore + "/" + total,
    percentage: percentage + "%",
    result: result,
    date: new Date().toLocaleString()
  };

  let reports = JSON.parse(localStorage.getItem("reports")) || [];
  reports.push(report);
  localStorage.setItem("reports", JSON.stringify(reports));

  window.location.href = "/result";
}

// ===================== Mosaic digit rendering =====================
// We use a 6x6 grid. Each pattern entry is 0 (background) or 1 (foreground)
// and visually forms a single digit using two color groups.

const MOSAIC_GRID_SIZE = 6;

// Patterns are row-major, length = 36. Digits: 3, 5, 8, 2, 9
const mosaicPatterns = {
  1: {
    digit: "3",
    type: "rg",
    pattern: [
      // .1111.
      0, 1, 1, 1, 1, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // ..11..
      0, 0, 1, 1, 0, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // .1111.
      0, 1, 1, 1, 1, 0
    ]
  },
  2: {
    digit: "5",
    type: "rg",
    pattern: [
      // .1111.
      0, 1, 1, 1, 1, 0,
      // .1....
      0, 1, 0, 0, 0, 0,
      // .111..
      0, 1, 1, 1, 0, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // .1111.
      0, 1, 1, 1, 1, 0
    ]
  },
  3: {
    digit: "8",
    type: "by",
    pattern: [
      // .1111.
      0, 1, 1, 1, 1, 0,
      // .1..1.
      0, 1, 0, 0, 1, 0,
      // .1111.
      0, 1, 1, 1, 1, 0,
      // .1..1.
      0, 1, 0, 0, 1, 0,
      // .1..1.
      0, 1, 0, 0, 1, 0,
      // .1111.
      0, 1, 1, 1, 1, 0
    ]
  },
  4: {
    digit: "2",
    type: "rg",
    pattern: [
      // .1111.
      0, 1, 1, 1, 1, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // .1111.
      0, 1, 1, 1, 1, 0,
      // .1....
      0, 1, 0, 0, 0, 0,
      // .1111.
      0, 1, 1, 1, 1, 0
    ]
  },
  5: {
    digit: "9",
    type: "by",
    pattern: [
      // .1111.
      0, 1, 1, 1, 1, 0,
      // .1..1.
      0, 1, 0, 0, 1, 0,
      // .1111.
      0, 1, 1, 1, 1, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // ....1.
      0, 0, 0, 0, 1, 0,
      // .1111.
      0, 1, 1, 1, 1, 0
    ]
  }
};

function initMosaicTiles() {
  const containers = document.querySelectorAll(".mosaic-tile");
  if (!containers.length) return;

  containers.forEach((container) => {
    const idAttr = container.getAttribute("data-question-id");
    const qId = parseInt(idAttr || "", 10);
    const def = mosaicPatterns[qId];
    if (!def) return;

    const isRG = def.type === "rg";
    const totalCells = MOSAIC_GRID_SIZE * MOSAIC_GRID_SIZE;

    for (let i = 0; i < totalCells; i++) {
      const span = document.createElement("span");
      const on = def.pattern[i] === 1;
      span.className = on
        ? (isRG ? "mosaic-fg-rg" : "mosaic-fg-by")
        : (isRG ? "mosaic-bg-rg" : "mosaic-bg-by");
      container.appendChild(span);
    }
  });
}

document.addEventListener("DOMContentLoaded", initMosaicTiles);

