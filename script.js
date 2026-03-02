const questions = [
  { image: "images/test1.png", answer: "29" },
  { image: "images/test2.png", answer: "12" },
  { image: "images/test3.png", answer: "8" }
];

let currentQuestion = 0;
let score = 0;

function nextQuestion() {
  const userAnswer = document.getElementById("answerInput").value;

  if (userAnswer === questions[currentQuestion].answer) {
    score++;
  }

  currentQuestion++;

  if (currentQuestion < questions.length) {
    document.getElementById("plateImage").src =
      questions[currentQuestion].image;

    document.getElementById("questionCount").innerText =
      "Question " + (currentQuestion + 1) + " of " + questions.length;

    document.getElementById("answerInput").value = "";
  } else {
    alert("Test Finished! Your score: " + score + "/" + questions.length);
  }
}