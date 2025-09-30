from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Iterable
import json
import math


@dataclass
class SuggestionRequest:
    available_ingredients: List[str]
    max_missing: int = 3
    allow_substitutions: bool = True
    max_suggestions: int = 8
    plan_size: int = 1
    prioritize_min_missing: bool = True


class FlavorGraphEngine:
    def __init__(
        self,
        recipes_path: Path,
        substitutions_path: Path,
        ingredient_tags_path: Path,
    ) -> None:
        self.recipes_path = Path(recipes_path)
        self.substitutions_path = Path(substitutions_path)
        self.ingredient_tags_path = Path(ingredient_tags_path)
        self.recipes: Dict[str, Dict] = {}
        self.substitutions: Dict[str, List[str]] = {}
        self.ingredient_tags: Dict[str, List[str]] = {}
        self.ingredient_to_recipes: Dict[str, Set[str]] = {}
        self._load()

    # --------------------------- Data Loading ---------------------------
    def _load(self) -> None:
        if self.recipes_path.exists():
            self.recipes = {r["id"]: r for r in json.loads(self.recipes_path.read_text(encoding="utf-8"))}
        if self.substitutions_path.exists():
            self.substitutions = json.loads(self.substitutions_path.read_text(encoding="utf-8"))
        if self.ingredient_tags_path.exists():
            self.ingredient_tags = json.loads(self.ingredient_tags_path.read_text(encoding="utf-8"))

        # Build inverted index: ingredient -> recipes
        self.ingredient_to_recipes = {}
        for recipe_id, recipe in self.recipes.items():
            for ingredient in recipe.get("ingredients", []):
                key = ingredient.strip().lower()
                self.ingredient_to_recipes.setdefault(key, set()).add(recipe_id)

    # --------------------------- Public API ---------------------------
    def get_all_recipes(self) -> List[Dict]:
        return list(self.recipes.values())

    def get_all_ingredients(self) -> List[str]:
        ingredients: Set[str] = set()
        for r in self.recipes.values():
            for ing in r.get("ingredients", []):
                ingredients.add(ing)
        return sorted(ingredients)

    # --------------------------- Core Algorithms ---------------------------
    def suggest_recipes(self, req: SuggestionRequest) -> Dict:
        available = {i.strip().lower() for i in req.available_ingredients}

        # Greedy pre-ranking by coverage vs. missing cost
        greedy_scores: List[Tuple[str, float, Dict]] = []
        for recipe_id, recipe in self.recipes.items():
            missing, covered, subs = self._compute_missing_and_subs(recipe, available, req.allow_substitutions)
            if len(missing) <= req.max_missing:
                score = self._score_recipe(covered, missing, subs)
                greedy_scores.append((recipe_id, score, {
                    "missing": sorted(missing),
                    "covered": sorted(covered),
                    "subs": subs,
                }))

        greedy_scores.sort(key=lambda x: (len(self.recipes[x[0]].get("ingredients", [])), -x[1]) if req.prioritize_min_missing else -x[1])
        top_candidates = greedy_scores[: max(25, req.max_suggestions * 3)]

        # Backtracking to select a plan of recipes maximizing coverage with minimal missing
        best_plan: List[str] = []
        best_plan_score = -math.inf
        best_plan_details: Dict[str, Dict] = {}

        def backtrack(start_idx: int, chosen: List[Tuple[str, float, Dict]], used_ingredients: Set[str]) -> None:
            nonlocal best_plan, best_plan_score, best_plan_details
            # Prune if chosen too large
            if len(chosen) > req.plan_size:
                return

            # Evaluate current plan
            plan_ids = [rid for rid, _, _ in chosen]
            plan_missing: Set[str] = set()
            plan_covered: Set[str] = set()
            plan_subs: Dict[str, str] = {}
            for rid, _, details in chosen:
                plan_missing.update(details["missing"])
                plan_covered.update(details["covered"])
                plan_subs.update(details["subs"])

            # Hard constraint: total missing across plan
            if len(plan_missing) <= req.max_missing:
                score = self._score_plan(plan_covered, plan_missing, plan_subs)
                if score > best_plan_score:
                    best_plan = plan_ids.copy()
                    best_plan_score = score
                    best_plan_details = {rid: det for rid, _, det in chosen}

            # Continue search if we can add more
            if len(chosen) == req.plan_size:
                return

            for i in range(start_idx, len(top_candidates)):
                rid, score, details = top_candidates[i]
                # Simple pruning: avoid redundant ingredients overlap only if it worsens missing significantly
                new_missing = set(details["missing"]) - used_ingredients
                if len(new_missing) > req.max_missing:
                    continue
                chosen.append((rid, score, details))
                backtrack(i + 1, chosen, used_ingredients | set(details["covered"]))
                chosen.pop()

        backtrack(0, [], set())

        # If no multi-recipe plan found, fall back to top singles
        if not best_plan:
            best_plan = [rid for rid, _, _ in top_candidates[: req.max_suggestions]]
            best_plan_details = {rid: det for rid, _, det in top_candidates[: req.max_suggestions]}

        suggestions: List[Dict] = []
        for rid in best_plan[: req.max_suggestions]:
            r = self.recipes[rid]
            det = best_plan_details.get(rid, {"missing": [], "covered": [], "subs": {}})
            suggestions.append({
                "id": rid,
                "title": r["title"],
                "ingredients": r.get("ingredients", []),
                "instructions": r.get("instructions", []),
                "tags": r.get("tags", []),
                "missing": det.get("missing", []),
                "covered": det.get("covered", []),
                "substitutions": det.get("subs", {}),
            })

        return {
            "suggestions": suggestions,
            "plan_size": req.plan_size,
            "max_missing": req.max_missing,
        }

    def analyze_gaps(self, recipe_ids: List[str], available: List[str]) -> Dict:
        available_set = {i.strip().lower() for i in available}
        gaps: Dict[str, Dict] = {}
        for rid in recipe_ids:
            r = self.recipes.get(rid)
            if not r:
                continue
            missing, covered, subs = self._compute_missing_and_subs(r, available_set, True)
            suggestions: Dict[str, List[str]] = {}
            for m in missing:
                suggestions[m] = self.substitutions.get(m, [])
            gaps[rid] = {
                "title": r["title"],
                "missing": sorted(missing),
                "covered": sorted(covered),
                "substitution_candidates": suggestions,
            }
        return {"gaps": gaps}

    # --------------------------- Helpers ---------------------------
    def _compute_missing_and_subs(self, recipe: Dict, available: Set[str], allow_subs: bool) -> Tuple[Set[str], Set[str], Dict[str, str]]:
        missing: Set[str] = set()
        covered: Set[str] = set()
        subs_used: Dict[str, str] = {}
        for ing in recipe.get("ingredients", []):
            ing_key = ing.strip().lower()
            if ing_key in available:
                covered.add(ing_key)
                continue
            if allow_subs:
                for alt in self.substitutions.get(ing_key, []):
                    if alt in available:
                        covered.add(ing_key)
                        subs_used[ing_key] = alt
                        break
                else:
                    missing.add(ing_key)
            else:
                missing.add(ing_key)
        return missing, covered, subs_used

    def _score_recipe(self, covered: Iterable[str], missing: Iterable[str], subs_used: Dict[str, str]) -> float:
        covered_count = len(set(covered))
        missing_count = len(set(missing))
        subs_penalty = 0.2 * len(subs_used)
        return covered_count - (missing_count + subs_penalty)

    def _score_plan(self, covered: Set[str], missing: Set[str], subs_used: Dict[str, str]) -> float:
        # Reward coverage, penalize missing and substitutions
        return len(covered) - (1.5 * len(missing)) - (0.2 * len(subs_used))


