from flask import Flask, jsonify, request, render_template
from pathlib import Path
from flavorgraph.engine import FlavorGraphEngine, SuggestionRequest


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    project_root = Path(__file__).parent
    data_dir = project_root / "data"

    engine = FlavorGraphEngine(
        recipes_path=data_dir / "recipes.json",
        substitutions_path=data_dir / "substitutions.json",
        ingredient_tags_path=data_dir / "ingredient_tags.json",
    )

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/recipes", methods=["GET"])
    def list_recipes():
        return jsonify({
            "recipes": engine.get_all_recipes()
        })

    @app.route("/api/ingredients", methods=["GET"])
    def list_ingredients():
        return jsonify({
            "ingredients": engine.get_all_ingredients()
        })

    @app.route("/api/suggest", methods=["POST"])
    def suggest():
        payload = request.get_json(force=True) or {}
        req = SuggestionRequest(
            available_ingredients=[i.strip().lower() for i in payload.get("available_ingredients", []) if i and isinstance(i, str)],
            max_missing=int(payload.get("max_missing", 3)),
            allow_substitutions=bool(payload.get("allow_substitutions", True)),
            max_suggestions=int(payload.get("max_suggestions", 8)),
            plan_size=int(payload.get("plan_size", 1)),
            prioritize_min_missing=bool(payload.get("prioritize_min_missing", True)),
        )

        results = engine.suggest_recipes(req)
        return jsonify(results)

    @app.route("/api/analyze_gaps", methods=["POST"])
    def analyze_gaps():
        payload = request.get_json(force=True) or {}
        recipe_ids = payload.get("recipe_ids", [])
        available = [i.strip().lower() for i in payload.get("available_ingredients", []) if i and isinstance(i, str)]
        analysis = engine.analyze_gaps(recipe_ids, available)
        return jsonify(analysis)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)


