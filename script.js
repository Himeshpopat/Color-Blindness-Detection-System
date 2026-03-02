const questions = [
  { image: "images/test1.png", normal: "29", protan: "70", deutan: "70" },
  { image: "images/test2.png", normal: "12", protan: "12", deutan: "12" },
  { image: "images/test3.png", normal: "8", protan: "3", deutan: "3" },

  { image: "images/test4.png", normal: "45", protan: "15", deutan: "15" },
  { image: "images/test5.png", normal: "74", protan: "21", deutan: "21" },
  { image: "images/test6.png", normal: "27", protan: "17", deutan: "17" },
  { image: "images/test7.png", normal: "2", protan: "?", deutan: "?" },
  { image: "images/test8.png", normal: "6", protan: "5", deutan: "5" },
  { image: "images/test9.png", normal: "42", protan: "?", deutan: "?" },
  { image: "images/test10.png", normal: "16", protan: "6", deutan: "6" }
];

let currentQuestion = 0;
let normalScore = 0;
let protanScore = 0;
let deutanScore = 0;

function nextQuestion() {
  const userAnswer = document.getElementById("answerInput").value.trim();

  if (userAnswer === "") {
    alert("Please enter an answer before proceeding.");
    return;
  }

  if (userAnswer === questions[currentQuestion].normal) normalScore++;
  if (userAnswer === questions[currentQuestion].protan) protanScore++;
  if (userAnswer === questions[currentQuestion].deutan) deutanScore++;

  currentQuestion++;

  if (currentQuestion < questions.length) {

    document.getElementById("plateImage").src =
      questions[currentQuestion].image;

    document.getElementById("questionCount").innerText =
      "Question " + (currentQuestion + 1) + " of " + questions.length;

    document.getElementById("answerInput").value = "";

    const progress = (currentQuestion / questions.length) * 100;
    document.getElementById("progressBar").style.width = progress + "%";

  } else {
    finishTest();
  }
}

function finishTest() {
  const total = questions.length;
  const percentage = Math.round((normalScore / total) * 100);

  let result = "";

  if (percentage >= 80) {
    result = "Normal Vision";
  } else if (protanScore > deutanScore) {
    result = "Possible Protanopia";
  } else {
    result = "Possible Deuteranopia";
  }

  // Create report object
  const report = {
    score: normalScore + "/" + total,
    percentage: percentage + "%",
    result: result,
    date: new Date().toLocaleString()
  };

  // Get existing reports
  let reports = JSON.parse(localStorage.getItem("reports")) || [];

  // Add new report
  reports.push(report);

  // Save back
  localStorage.setItem("reports", JSON.stringify(reports));

  window.location.href = "result.html";
}