from flask import Flask, request, render_template_string

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    output = ""
    if request.method == "POST":
        input1 = request.form.get("input1", "")
        input2 = request.form.get("input2", "")
        output = f"Input 1: {input1}, Input 2: {input2}"
    
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>Gaucho Guardian</title></head>
    <body>
        <form method="POST">
            <input type="text" name="input1" placeholder="Input 1"><br><br>
            <input type="text" name="input2" placeholder="Input 2"><br><br>
            <button type="submit">Submit</button>
        </form>
        {% if output %}
        <p><strong>Output:</strong> {{ output }}</p>
        {% endif %}
    </body>
    </html>
    """, output=output)