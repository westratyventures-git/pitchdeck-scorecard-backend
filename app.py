import os
import re
import uuid
import gc
import fitz
import json
import datetime
from typing import Dict, Any

from openai import OpenAI

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# ============================================================
# CONFIG
# ============================================================
UPLOAD_TMP = "/tmp"
os.makedirs(UPLOAD_TMP, exist_ok=True)

OPENAI_API_KEY = os.environ.get("apiKey")
client = OpenAI(api_key=OPENAI_API_KEY)

MODEL_NAME = "gpt-4.1-mini"

# ============================================================
# UPDATED VC-GRADE CATEGORY FACTORS 
# + IP CATEGORY SKIPPABLE
# ============================================================
CATEGORY_FORMULAS = {
    "Market Opportunity": {
        "weight": 20,
        "subfactors": [
            "TAM Clarity",
            "SAM Definition",
            "SOM Attainability",
            "Market Growth Evidence",
            "Timing & Tailwinds",
            "Macro & Regulatory Fit"
        ],
        "formula": "({TAM Clarity}+{SAM Definition}+{SOM Attainability}+{Market Growth Evidence}+{Timing & Tailwinds}+{Macro & Regulatory Fit})/6*20"
    },

    "Problem–Solution Fit": {
        "weight": 20,
        "subfactors": [
            "Pain Point Severity",
            "Problem Clarity",
            "Solution–Problem Fit",
            "Use Case Strength",
            "Value Realization Evidence"
        ],
        "formula": "({Pain Point Severity}+{Problem Clarity}+{Solution–Problem Fit}+{Use Case Strength}+{Value Realization Evidence})/5*20"
    },

    "Product & Technology": {
        "weight": 20,
        "subfactors": [
            "Product Clarity",
            "Innovation Level",
            "Tech Architecture Depth",
            "Regulatory/Technical Moat",
            "Scalability",
            "UX Quality"
        ],
        "formula": "({Product Clarity}+{Innovation Level}+{Tech Architecture Depth}+{Regulatory/Technical Moat}+{Scalability}+{UX Quality})/6*20"
    },

    "Competition & Differentiation": {
        "weight": 10,
        "subfactors": [
            "Competitor Awareness",
            "Competitive Positioning",
            "Differentiation Clarity",
            "Switching Barrier Evidence",
            "MOAT"
        ],
        "formula": "({Competitor Awareness}+{Competitive Positioning}+{Differentiation Clarity}+{Switching Barrier Evidence}+{MOAT})/5*10"
    },

    "Business Model & Unit Economics": {
        "weight": 15,
        "subfactors": [
            "Revenue Logic Clarity",
            "Cost Structure Understanding",
            "Scalable Economics",
            "CAC Logic",
            "LTV Logic",
            "Profitability Outlook"
        ],
        "formula": "({Revenue Logic Clarity}+{Cost Structure Understanding}+{Scalable Economics}+{CAC Logic}+{LTV Logic}+{Profitability Outlook})/6*15"
    },

    "Financials Quality": {
        "weight": 10,
        "subfactors": [
            "Financial Transparency",
            "Assumption Logic",
            "Forecast Realism",
            "Revenue Model Validation"
        ],
        "formula": "({Financial Transparency}+{Assumption Logic}+{Forecast Realism}+{Revenue Model Validation})/4*10"
    },

    "Traction & GTM": {
        "weight": 10,
        "subfactors": [
            "Traction Evidence",
            "Growth Strategy Clarity",
            "Distribution Channels",
            "Retention/Engagement Signals",
            "GTM Maturity"
        ],
        "formula": "({Traction Evidence}+{Growth Strategy Clarity}+{Distribution Channels}+{Retention/Engagement Signals}+{GTM Maturity})/5*10"
    },

    "Team Strength": {
        "weight": 10,
        "subfactors": [
            "Founder Domain Expertise",
            "Execution Track Record",
            "Team Completeness",
            "Technical Capability",
            "Founder–Market Fit"
        ],
        "formula": "({Founder Domain Expertise}+{Execution Track Record}+{Team Completeness}+{Technical Capability}+{Founder–Market Fit})/5*10"
    },

    "Risk & Compliance": {
        "weight": 5,
        "subfactors": [
            "Regulatory Readiness",
            "Compliance Adequacy",
            "Risk Awareness",
            "Risk Mitigation Evidence"
        ],
        "formula": "({Regulatory Readiness}+{Compliance Adequacy}+{Risk Awareness}+{Risk Mitigation Evidence})/4*5"
    },

    "Ask & Utilization": {
        "weight": 10,
        "subfactors": [
            "Ask Clarity",
            "Utilization Breakdown",
            "Milestone Fit",
            "Fundraising Strategy Maturity"
        ],
        "formula": "({Ask Clarity}+{Utilization Breakdown}+{Milestone Fit}+{Fundraising Strategy Maturity})/4*10"
    },

    "Design & Narrative": {
        "weight": 20,
        "subfactors": [
            "Visual Clarity",
            "Narrative Consistency",
            "Slide Flow",
            "Signal-to-Noise Ratio"
        ],
        "formula": "({Visual Clarity}+{Narrative Consistency}+{Slide Flow}+{Signal-to-Noise Ratio})/4*5"
    },

    "UVP & USP": {
        "weight": 5,
        "subfactors": [
            "UVP Strength",
            "USP Clarity",
            "Customer Benefit Sharpness",
            "Our Big Idea"
        ],
        "formula": "({UVP Strength}+{USP Clarity}+{Customer Benefit Sharpness}+{Our Big Idea})/4*5"
    },

    "IP / Defensibility": {
        "weight": 5,
        "subfactors": [
            "IP Evidence"
        ],
        "formula": "{IP Evidence}*5"
    },

    "Roadmap": {
        "weight": 5,
        "subfactors": [
            "Roadmap Clarity",
            "Execution Milestones",
            "Timeline Realism"
        ],
        "formula": "({Roadmap Clarity}+{Execution Milestones}+{Timeline Realism})/3*5"
    }
}

# ============================================================
# HELPERS
# ============================================================
def sanitize_label(label: str) -> str:
    s = re.sub(r'[^0-9a-zA-Z]', '_', label)
    return re.sub(r'_+', '_', s).strip('_') or 'var'


def extract_text_from_pdf_fileobj(fileobj) -> str:
    """ Extract PDF text """
    try:
        path = getattr(fileobj, "name", None)
        if path:
            doc = fitz.open(path)
            return "\n\n".join([p.get_text().strip() for p in doc])
    except:
        pass

    try:
        data = fileobj.read()
        doc = fitz.open(stream=data, filetype="pdf")
        return "\n\n".join([p.get_text().strip() for p in doc])
    except:
        return ""


# ============================================================
# SINGLE API CALL — GPT PROMPT
# ============================================================
def score_all_subfactors_single_call(full_text: str):

    categories = {cat: cfg["subfactors"] for cat, cfg in CATEGORY_FORMULAS.items()}
    category_json = json.dumps(categories, indent=2)

    prompt = f"""
You are a senior VC analyst. Score all categories strictly based on evidence in the pitch deck.

IMPORTANT RULES:
- Score each subfactor 0–100
- For **IP Evidence**, return 0–100 if IP exists, otherwise "none"
- If "none", the backend will skip that category.

Return ONLY valid JSON:
{{
  "scores": {{
    "Category": {{
      "Subfactor": number OR "none"
    }}
  }},
  "overall_improvement": 
    "4–5 line improvement analysis. Do not mention IP if skipped. 
     End with: For a more detailed investor-ready pitchdeck, contact Westraty Ventures."
}}

CATEGORIES:
{category_json}

PITCH:
\"\"\"{full_text[:8000]}\"\"\"
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        return json.loads(response.choices[0].message.content.strip())
    except:
        return {
            "scores": {cat: {sf: 50 for sf in cfg["subfactors"]} for cat, cfg in CATEGORY_FORMULAS.items()},
            "overall_improvement": "Improve clarity, traction and flow."
        }


# ============================================================
# COMPUTE WEIGHTED SCORE
# ============================================================
def compute_weighted_score(subfactor_scores, formula_str, category):
    if category == "IP / Defensibility":
        if str(subfactor_scores["IP Evidence"]).lower() == "none":
            return None

    label_to_var = {lbl: sanitize_label(lbl) for lbl in subfactor_scores}

    local_vars = {
        sanitize_label(lbl): (
            0 if str(val).lower() == "none" else val / 100.0
        )
        for lbl, val in subfactor_scores.items()
    }

    safe_expr = formula_str
    for lbl, varname in label_to_var.items():
        safe_expr = safe_expr.replace(f"{{{lbl}}}", varname)

    try:
        return round(float(eval(safe_expr, {}, local_vars)), 2)
    except:
        return 0


# ============================================================
# MAIN SCORING LOGIC
# ============================================================
def score_pitchdeck(text: str):
    api_result = score_all_subfactors_single_call(text)

    all_scores = api_result["scores"]
    improvement_summary = api_result["overall_improvement"]

    results = {}
    total_points = 0.0
    effective_weight = 0.0

    for category, cfg in CATEGORY_FORMULAS.items():
        sub_scores = all_scores[category]
        weighted = compute_weighted_score(sub_scores, cfg["formula"], category)

        results[category] = {
            "subfactor_scores (%)": sub_scores,
            "weighted_score (points)": weighted if weighted is not None else "SKIPPED"
        }

        if weighted is not None:
            total_points += weighted
            effective_weight += cfg["weight"]

    total_score_percent = round((total_points / effective_weight) * 100.0, 2)

    interpretation = (
        "Needs major revisions" if total_score_percent < 50 else
        "Good, but can be improved" if total_score_percent < 80 else
        "Strong pitch — investor ready"
    )

    return results, total_score_percent, interpretation, improvement_summary


# ============================================================
# FASTAPI — CLEAN BACKEND (NO GRADIO)
# ============================================================
api = FastAPI()
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
ADMIN_DIR = os.path.join(UPLOAD_DIR, "admin_pitchdecks")
USER_DIR = os.path.join(UPLOAD_DIR, "user_pitchdecks")
os.makedirs(ADMIN_DIR, exist_ok=True)
os.makedirs(USER_DIR, exist_ok=True)


@api.post("/score")
async def score_pdf(file: UploadFile = File(...), uploader: str = "admin"):

    text = extract_text_from_pdf_fileobj(file.file)
    if not text:
        return {"error": "Unable to read PDF"}

    results, total_score, interpretation, improvement_summary = score_pitchdeck(text)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^a-zA-Z0-9_\.-]', '_', file.filename)
    filename = f"{os.path.splitext(safe_name)[0]}_{timestamp}.pdf"
    save_dir = ADMIN_DIR if uploader == "admin" else USER_DIR

    file_path = os.path.join(save_dir, filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    result_data = {
        "filename": filename,
        "timestamp": timestamp,
        "total_score (%)": total_score,
        "interpretation": interpretation,
        "overall_improvement": improvement_summary,
        "detailed_scorecard": results
    }

    json_path = os.path.join(save_dir, f"{os.path.splitext(filename)[0]}.json")
    with open(json_path, "w") as jf:
        json.dump(result_data, jf, indent=2)

    return result_data


@api.get("/admin/pitchdecks")
def list_admin_pitchdecks():
    decks = []
    for f in os.listdir(ADMIN_DIR):
        if f.endswith(".json"):
            with open(os.path.join(ADMIN_DIR, f)) as jf:
                decks.append(json.load(jf))
    return decks


@api.get("/user/pitchdecks")
def list_user_pitchdecks():
    decks = []
    for f in os.listdir(USER_DIR):
        if f.endswith(".json"):
            with open(os.path.join(USER_DIR, f)) as jf:
                decks.append(json.load(jf))
    return decks


@api.get("/download/{uploader}/{filename}")
def download_pitchdeck(uploader: str, filename: str):
    folder = ADMIN_DIR if uploader == "admin" else USER_DIR
    file_path = os.path.join(folder, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File not found"}


# ============================================================
# RUN FASTAPI (FOR DEVELOPMENT ONLY)
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8000)
