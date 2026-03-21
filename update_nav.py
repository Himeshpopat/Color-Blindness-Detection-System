import os
import re

html_files = ["test.html", "simulation.html", "reports.html", "result.html", "mosaic.html", "index.html", "about.html"]
directory = r"c:\Users\newan_afogmpc\Desktop\AnshProject\Color-Blindness-Detection-System\templates"

replacement = """class="mode-btn">B/W Mode</button>
            {% if session.get('user_id') %}
            <a href="{{ url_for('logout') }}">Logout</a>
            {% else %}
            <a href="{{ url_for('login') }}">Login / Sign Up</a>
            {% endif %}
        </div>
    </nav>"""

for f in html_files:
    path = os.path.join(directory, f)
    if not os.path.exists(path):
        continue
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
    
    # Regex to find mode-btn ... up to </nav>
    pattern = re.compile(r'class="mode-btn">B/W Mode</button>.*?</nav>', re.DOTALL)
    new_content = pattern.sub(replacement, content)
    
    with open(path, "w", encoding="utf-8") as file:
        file.write(new_content)

print("Updated navigation bars in templates.")
