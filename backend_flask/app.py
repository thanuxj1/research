from flask import Flask, jsonify

from assitance.app import bp as assistance_bp
from budget_planner.app import bp as budget_planner_bp
from Questions.app import bp as questions_bp


def create_app() -> Flask:

    app = Flask(__name__)

    # Mount the three components under prefixes
    app.register_blueprint(assistance_bp, url_prefix="/assistance")
    app.register_blueprint(budget_planner_bp, url_prefix="/budget_planner")
    app.register_blueprint(questions_bp, url_prefix="/questions")

    @app.get("/")
    def index():
        return jsonify({
            "success": True,
            "message": "Sri Lanka AI Tourism API (combined)",
            "routes": {
                "assistance": {
                    "recommend": "/assistance/recommend",
                    "predict_alias": "/assistance/predict"
                },
                "budget_planner": {
                    "predict": "/budget_planner/predict"
                },
                "questions": {
                    "predict": "/questions/predict",
                    "health": "/questions/health"
                }
            }
        })

    return app


app = create_app()


if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000, debug=True)
