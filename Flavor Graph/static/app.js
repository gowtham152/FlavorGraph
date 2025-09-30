const ingredientInput = document.getElementById('ingredient-input');
const addBtn = document.getElementById('add-btn');
const chips = document.getElementById('ingredient-chips');
const suggestBtn = document.getElementById('suggest-btn');
const resetBtn = document.getElementById('reset-btn');
const suggestionsEl = document.getElementById('suggestions');
const yearEl = document.getElementById('year');

yearEl.textContent = new Date().getFullYear();

let ingredients = [];

function renderChips() {
  chips.innerHTML = '';
  ingredients.forEach((ing, idx) => {
    const chip = document.createElement('div');
    chip.className = 'chip';
    // use a visible close glyph and data index for removal
    chip.innerHTML = `<span>${ing}</span><span class="remove" data-idx="${idx}">\u2715</span>`;
    chips.appendChild(chip);
    // show animation
    requestAnimationFrame(() => chip.classList.add('show'));
  });
}

function addIngredient() {
  const raw = ingredientInput.value.trim();
  if (!raw) return;
  // Support comma-separated input (e.g. "a, b, c")
  const parts = raw.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  for (const val of parts) {
    if (!ingredients.includes(val)) ingredients.push(val);
  }
  ingredientInput.value = '';
  renderChips();
}

chips.addEventListener('click', (e) => {
  const idx = e.target.getAttribute('data-idx');
  if (idx !== null) {
    // animate removal
    const chipEl = e.target.closest('.chip');
    if (chipEl) {
      chipEl.style.transition = 'opacity .18s ease, transform .18s ease';
      chipEl.style.opacity = '0';
      chipEl.style.transform = 'scale(.92) translateX(6px)';
      setTimeout(() => {
        ingredients.splice(Number(idx), 1);
        renderChips();
      }, 180);
    } else {
      ingredients.splice(Number(idx), 1);
      renderChips();
    }
  }
});

addBtn.addEventListener('click', addIngredient);
ingredientInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') addIngredient();
});

resetBtn.addEventListener('click', () => {
  ingredients = [];
  renderChips();
  suggestionsEl.innerHTML = '';
});

function getNumber(id, min, max, fallback) {
  const v = Number(document.getElementById(id).value);
  if (Number.isFinite(v)) return Math.max(min, Math.min(max, v));
  return fallback;
}

async function suggest() {
  // If user has typed ingredients but not clicked Add, include them
  if (ingredientInput.value.trim()) addIngredient();

  suggestionsEl.innerHTML = '<div class="pill loading">Loading suggestions</div>';
  const payload = {
    available_ingredients: ingredients,
    max_missing: getNumber('max-missing', 0, 10, 3),
    allow_substitutions: document.getElementById('allow-subs').checked,
    plan_size: getNumber('plan-size', 1, 4, 1),
    max_suggestions: getNumber('max-suggestions', 1, 12, 6),
    prioritize_min_missing: true,
  };

  try {
    const res = await fetch('/api/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`Server returned ${res.status}: ${txt}`);
    }
    const data = await res.json();
    renderSuggestions(data.suggestions || []);
  } catch (e) {
    suggestionsEl.innerHTML = `<div class="pill">Error: ${e.message}</div>`;
  }
}

function renderSuggestions(list) {
  if (!list.length) {
    suggestionsEl.innerHTML = '<div class="pill">No suggestions. Try adding more ingredients or loosening constraints.</div>';
    return;
  }
  suggestionsEl.innerHTML = '';
  for (const s of list) {
    const card = document.createElement('div');
    card.className = 'card card-enter';
    const missing = s.missing || [];
    const covered = s.covered || [];
    const subs = s.substitutions || {};
    const subsLines = Object.entries(subs).map(([need, use]) => `${need} → ${use}`);
    card.innerHTML = `
      <h3>${s.title}</h3>
      <div class="meta">
        ${(s.tags || []).slice(0,4).map(t => `<span class="pill">${t}</span>`).join('')}
      </div>
      <div class="meta">
        <span class="pill covered">Covered: ${covered.length}</span>
        <span class="pill missing">Missing: ${missing.length}</span>
        <span class="pill subs">Subs: ${subsLines.length}</span>
      </div>
      <details>
        <summary>Ingredients</summary>
        <ul>${(s.ingredients||[]).map(i=>`<li>${i}</li>`).join('')}</ul>
      </details>
      <details>
        <summary>Instructions</summary>
        <ol>${(s.instructions||[]).map(i=>`<li>${i}</li>`).join('')}</ol>
      </details>
      ${missing.length ? `<details open><summary>Missing</summary><ul>${missing.map(m=>`<li class="missing">${m}</li>`).join('')}</ul></details>` : ''}
      ${subsLines.length ? `<details open><summary>Substitutions</summary><ul>${subsLines.map(m=>`<li class="subs">${m}</li>`).join('')}</ul></details>` : ''}
    `;
    suggestionsEl.appendChild(card);
    // staggered reveal
    requestAnimationFrame(() => {
      setTimeout(() => card.classList.remove('card-enter'), 60);
    });
  }
}

suggestBtn.addEventListener('click', suggest);


