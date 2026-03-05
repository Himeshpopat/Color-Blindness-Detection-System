/* ===================== GLOBAL VARIABLES ===================== */
let testSet = [];
let currentIndex = 0;
let score = 0;
let currentSessionId = null; 
let isInitializing = false; // GUARD: Prevents double-triggering sessions

// Track category-specific performance for diagnosis
let diagnosticResults = {
    protan: { correct: 0, total: 0 },
    deutan: { correct: 0, total: 0 },
    tritan: { correct: 0, total: 0 },
    control: { correct: 0, total: 0 },
    general: { correct: 0, total: 0 }
};

/* ===================== ISHIHARA TEST LOGIC ===================== */

/**
 * Initializes the test: 
 * 1. Creates a session entry in MongoDB 'test_sessions'
 * 2. Fetches 10 random plates from the backend
 */
async function startTest() {
    // Check guard to prevent double session entries in DB
    if (isInitializing) return;
    isInitializing = true;

    // Get username from localStorage (set this during login)
    const username = localStorage.getItem("username") || "Guest_User";
    
    try {
        // 1. Log the Start Time in test_sessions
        const sessionRes = await fetch("http://127.0.0.1:5000/api/start_session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: username })
        });
        const sessionData = await sessionRes.json();
        currentSessionId = sessionData.session_id;

        // 2. Fetch the random test plates
        const response = await fetch("http://127.0.0.1:5000/api/get_test");
        if (!response.ok) throw new Error("Could not fetch test data");
        
        testSet = await response.json();
        updateQuestionUI();
    } catch (err) {
        console.error("Initialization failed:", err);
        const countDisplay = document.getElementById("questionCount");
        if(countDisplay) countDisplay.innerText = "Connection Error - Check Backend";
        isInitializing = false; // Allow retry if it failed
    }
}

/**
 * Updates the Image and Progress Bar
 */
function updateQuestionUI() {
    if (testSet.length === 0) return;

    const current = testSet[currentIndex];
    const imgElement = document.getElementById("plateImage");
    
    imgElement.src = current.image_url;
    
    document.getElementById("questionCount").innerText = 
        `Plate ${currentIndex + 1} of ${testSet.length}`;
    
    const answerInput = document.getElementById("answerInput");
    answerInput.value = "";
    answerInput.focus();

    const progress = (currentIndex / testSet.length) * 100;
    document.getElementById("progressBar").style.width = progress + "%";
}

/**
 * Validates the answer and tracks deficiency types
 */
async function nextQuestion() {
    const answerInput = document.getElementById("answerInput");
    const userAnswer = answerInput.value.trim();

    if (!userAnswer) {
        alert("Please enter a number.");
        return;
    }

    const currentPlate = testSet[currentIndex];
    const category = currentPlate.category;

    // Increment category totals
    diagnosticResults[category].total++;

    if (userAnswer === currentPlate.answer) {
        score++;
        diagnosticResults[category].correct++;
    }

    currentIndex++;

    if (currentIndex < testSet.length) {
        updateQuestionUI();
    } else {
        await finishTest();
    }
}

/**
 * 1. Logs End Time in 'test_sessions'
 * 2. Determines specific colorblindness type
 * 3. Saves detailed report to 'reports'
 */
async function finishTest() {
    const total = testSet.length;
    const percentage = Math.round((score / total) * 100);
    const username = localStorage.getItem("username") || "Guest_User";

    // --- Diagnostic Logic ---
    let resultStatus = "Normal Color Vision";
    let detailedDescription = "Your responses indicate standard color perception.";

    const pMissed = diagnosticResults.protan.total - diagnosticResults.protan.correct;
    const dMissed = diagnosticResults.deutan.total - diagnosticResults.deutan.correct;
    const tMissed = diagnosticResults.tritan.total - diagnosticResults.tritan.correct;

    if (percentage < 85) {
        if (diagnosticResults.control.total > 0 && diagnosticResults.control.correct === 0) {
            resultStatus = "Inconclusive";
            detailedDescription = "The control plate was not identified correctly. Please retake the test in better lighting.";
        } else if (tMissed > 0 && tMissed >= pMissed && tMissed >= dMissed) {
            resultStatus = "Possible Tritanopia";
            detailedDescription = "Results suggest difficulty with blue/yellow spectrums.";
        } else if (pMissed > dMissed) {
            resultStatus = "Possible Protanopia";
            detailedDescription = "Results suggest a Red-blind deficiency (Protanopia).";
        } else if (dMissed > pMissed) {
            resultStatus = "Possible Deuteranopia";
            detailedDescription = "Results suggest a Green-blind deficiency (Deuteranopia).";
        } else {
            resultStatus = "Color Vision Deficiency";
            detailedDescription = "General difficulty distinguishing color contrasts detected.";
        }
    }

    // Save for immediate display (Reduces latency on results page)
    localStorage.setItem("lastScore", score);
    localStorage.setItem("totalQuestions", total);
    localStorage.setItem("lastPercentage", percentage);
    localStorage.setItem("lastResult", resultStatus);
    localStorage.setItem("lastDescription", detailedDescription);

    try {
        // 1. Close the Test Session (Logs end_time)
        await fetch("http://127.0.0.1:5000/api/end_session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId })
        });

        // 2. Save the Diagnostic Report
        await fetch("http://127.0.0.1:5000/api/save_report", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username: username,
                result: resultStatus,
                score: `${score}/${total}`,
                percentage: `${percentage}%`
            })
        });

        window.location.href = "results.html";
    } catch (err) {
        console.error("Finalization error:", err);
        window.location.href = "results.html"; 
    }
}

/* ===================== INITIALIZATION ===================== */

// Use window.onload to ensure the DOM is ready and prevent multiple triggers
window.onload = function() {
    if (document.getElementById("plateImage")) {
        startTest();
    }
};

// Enter key support for input
const inputField = document.getElementById("answerInput");
if (inputField) {
    inputField.addEventListener("keypress", (e) => {
        if (e.key === "Enter") nextQuestion();
    });
}

// BW Mode Toggle
function toggleBW() {
    document.body.classList.toggle("bw-mode");
    localStorage.setItem("mode", document.body.classList.contains("bw-mode") ? "bw" : "color");
}