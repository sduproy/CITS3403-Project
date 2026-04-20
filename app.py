from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('itinerary.html')

@app.route('/community')
def community():
    return render_template('community.html')

if __name__ == '__main__':
    app.run(debug=True)
