# ============================================================
# 📄 AI RESEARCH PAPER ASSISTANT
# Gemini + Gradio + PDF Upload + Live Progress + Retry Handling
#
# Analyzes a research paper and produces:
#   • Summary
#   • Methodology
#   • Limitations
#
# Run locally in VS Code:
#   1. pip install -r requirements.txt
#   2. Create a .env file next to this script with:
#        GEMINI_API_KEY=your_real_key_here
#   3. python research_paper_assistant.py
# ============================================================

import gradio as gr
import time
import random
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


# ============================================================
# 1. GEMINI API SETUP
# ============================================================

load_dotenv()  # reads GEMINI_API_KEY from a local .env file

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        """
        GEMINI_API_KEY not set.

        Create a file named ".env" in this same folder containing:
            GEMINI_API_KEY=your_real_key_here

        Never hardcode the key directly in this script.
        """
    )

client = genai.Client(api_key=api_key)


# ============================================================
# 2. MODEL CONFIGURATION
# ============================================================

# Fast, cost-effective model for high-volume use
FAST_MODEL = "gemini-3.1-flash-lite"

# More capable fallback model
FALLBACK_MODEL = "gemini-3.5-flash"

# NOTE: Google renames/deprecates Gemini models fairly often.
# If either call starts failing with a "model not found" error,
# check https://ai.google.dev/gemini-api/docs/models for the
# current list and update the two lines above.


# Maximum PDF size accepted (inline upload limit is ~20 MB;
# we keep a safety margin)

MAX_PDF_MB = 18


# ============================================================
# 3. HELPER FUNCTION
#    Detect temporary Gemini errors
# ============================================================

def is_temporary_error(error):

    error_text = str(error).lower()

    temporary_messages = [
        "503",
        "service unavailable",
        "unavailable",
        "overloaded",
        "busy",
        "429",
        "rate limit",
        "rate_limit",
        "resource_exhausted",
        "timeout",
        "timed out",
        "deadline",
        "deadline_exceeded",
        "500",
        "internal server error"
    ]

    return any(message in error_text for message in temporary_messages)


# ============================================================
# 4. PROMPT BUILDER
# ============================================================

def build_analysis_prompt(detail_level, audience, include_future_work):

    future_work_section = ""

    if include_future_work:
        future_work_section = """

## 🔭 Future Work & Open Questions

List 3-5 directions the paper itself suggests, or that
follow directly from its limitations. Clearly separate
what the authors proposed from what you are inferring.
"""

    prompt = f"""
You are an AI Research Paper Assistant helping a student
or researcher understand an academic paper.

Analyze the attached research paper carefully and produce
a structured breakdown.


READER PROFILE
--------------

Detail Level: {detail_level}

Audience: {audience}


CRITICAL RULES
--------------

1. Base EVERYTHING strictly on the actual content of the
   paper provided. Do not add outside facts.

2. If something is not stated in the paper (for example,
   dataset size, funding, or ablation details), write
   "Not specified in the paper" instead of guessing.

3. Never invent citations, numbers, author names, or results.

4. Quote sparingly — at most a few words at a time. Explain
   things in your own words instead.

5. Distinguish clearly between:
   - what the authors CLAIM
   - what the results actually SHOW
   - what YOU assess as a limitation

6. Use clean Markdown formatting with the exact section
   headings given below.

7. Match the depth to the requested detail level, and the
   vocabulary to the audience.


OUTPUT FORMAT
-------------

# 📄 Research Paper Analysis


## 🏷️ Paper at a Glance

| Field | Detail |
|---|---|
| Title | ... |
| Authors | ... |
| Venue / Year | ... |
| Research Area | ... |
| Paper Type | (e.g. empirical study, survey, theoretical, system paper) |

Use "Not specified in the paper" for anything missing.


## 🎯 Research Problem

State, in 2-4 sentences, the problem the paper is trying
to solve and why it matters.


## 📝 Summary

Summarize the paper in your own words. Cover the motivation,
the approach, and the headline findings. Keep it readable
and self-contained.


## 🔑 Key Contributions

List the 3-5 main contributions as bullet points, exactly
as the paper frames them.


## 🔬 Methodology

Break the methodology down clearly:

**Approach:** What method, model, or framework is used.

**Data:** Datasets, sample size, sources, how data was
collected or preprocessed.

**Experimental Setup:** Baselines compared against,
evaluation metrics, hyperparameters or configurations,
hardware if mentioned.

**Procedure:** The step-by-step flow of what the authors
actually did.


## 📊 Key Results

Report the main quantitative and qualitative findings.
Include the actual numbers the paper reports where
available. Do not round or embellish them.


## ⚠️ Limitations

Give two clearly separated groups:

**Acknowledged by the authors:**
Limitations the paper itself states.

**Additional observations:**
Weaknesses you notice — for example small sample size,
narrow evaluation, missing baselines, no ablation study,
generalizability concerns, reproducibility gaps, or
potential bias. Mark these clearly as your own assessment.


## 🧠 Critical Assessment

Give a short, balanced take:

**Strengths:** 3 points.

**Concerns:** 3 points.
{future_work_section}

## ⚡ Quick Revision Points

5 concise bullet points capturing what someone should
remember about this paper.


## 🎤 Discussion Questions

Generate 5 questions that could be asked about this paper
in a seminar, viva, or journal club.
"""

    return prompt


# ============================================================
# 5. GEMINI ANALYSIS FUNCTION
# ============================================================

def analyze_research_paper(pdf_path, detail_level, audience, include_future_work):

    with open(pdf_path, "rb") as pdf_file:
        pdf_bytes = pdf_file.read()

    prompt = build_analysis_prompt(
        detail_level=detail_level,
        audience=audience,
        include_future_work=include_future_work
    )

    contents = [
        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        prompt
    ]

    models = [FAST_MODEL, FALLBACK_MODEL]

    max_retries_per_model = 3

    last_error = None

    for model_name in models:

        print("\n======================================")
        print(f"Trying model: {model_name}")
        print("======================================")

        for attempt in range(max_retries_per_model):

            try:
                print(f"Attempt {attempt + 1}/{max_retries_per_model}")

                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config={"max_output_tokens": 6000}
                )

                if response is not None and response.text and response.text.strip():
                    print(f"✅ SUCCESS using {model_name}")
                    return response.text

                raise RuntimeError("Gemini returned an empty response.")

            except Exception as error:

                last_error = error

                print(f"⚠️ Error: {type(error).__name__}")
                print(str(error))

                if not is_temporary_error(error):
                    raise error

                if attempt < max_retries_per_model - 1:
                    wait_time = (2 ** attempt) + random.uniform(0.2, 0.8)
                    print("⏳ Temporary Gemini error.")
                    print(f"Retrying in {wait_time:.1f} seconds...")
                    time.sleep(wait_time)

        print(f"❌ {model_name} failed.")
        print("Trying fallback model...")

    raise RuntimeError(
        """
        Gemini is temporarily unavailable.

        Both configured models were unable to
        process the request.

        Please wait a few seconds and try again.
        """
    )


# ============================================================
# 6. MAIN UI FUNCTION
# ============================================================

def research_assistant_ui(pdf_file, detail_level, audience, include_future_work):

    if pdf_file is None:
        yield (
            """
            ### ❌ No Paper Uploaded

            Please upload a research paper in PDF format.
            """,
            ""
        )
        return

    pdf_path = pdf_file.name if hasattr(pdf_file, "name") else pdf_file

    if not str(pdf_path).lower().endswith(".pdf"):
        yield (
            """
            ### ❌ Unsupported File Type

            Only **PDF** files are supported.

            Please export your paper as a PDF
            and upload it again.
            """,
            ""
        )
        return

    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)

    if file_size_mb > MAX_PDF_MB:
        yield (
            f"""
            ### ❌ File Too Large

            Your file is **{file_size_mb:.1f} MB**.

            The limit is **{MAX_PDF_MB} MB**.

            Try compressing the PDF, or upload only
            the main paper without the appendices.
            """,
            ""
        )
        return

    file_name = os.path.basename(pdf_path)

    yield (
        f"""
        ### 🤖 Research Paper Assistant

        🟢 **Step 1/4 — Paper Received**

        **File:** `{file_name}`

        **Size:** {file_size_mb:.2f} MB
        """,
        ""
    )

    time.sleep(0.6)

    yield (
        f"""
        ### 🤖 Research Paper Assistant

        🟢 Step 1/4 — Paper received (`{file_name}`)

        🔄 **Step 2/4 — Building Analysis Prompt**

        Configuring for **{detail_level}** detail,
        audience: **{audience}**...
        """,
        ""
    )

    time.sleep(0.6)

    yield (
        f"""
        ### 🤖 Research Paper Assistant

        🟢 Step 1/4 — Paper received (`{file_name}`)

        🟢 Step 2/4 — Prompt prepared

        🔄 **Step 3/4 — Reading & Analyzing the Paper**

        Gemini is reading the full PDF and extracting the
        summary, methodology and limitations.

        *Longer papers take more time — please wait.*
        """,
        ""
    )

    try:
        result = analyze_research_paper(
            pdf_path=pdf_path,
            detail_level=detail_level,
            audience=audience,
            include_future_work=include_future_work
        )

    except Exception as error:

        if is_temporary_error(error):
            yield (
                """
                ### ⏳ Gemini is Temporarily Busy

                The Gemini service is currently
                handling many requests.

                🔄 Automatic retries were attempted.

                **Please wait a few seconds and try again.**
                """,
                ""
            )
        else:
            yield (
                f"""
                ### ❌ Gemini Error

                **Error Type:**
                `{type(error).__name__}`

                **Details:**
                `{str(error)}`
                """,
                ""
            )

        return

    yield (
        f"""
        ### 🤖 Research Paper Assistant

        🟢 Step 1/4 — Paper received (`{file_name}`)

        🟢 Step 2/4 — Prompt prepared

        🟢 Step 3/4 — Paper analyzed

        🔄 **Step 4/4 — Formatting the Report**
        """,
        result
    )

    time.sleep(0.6)

    yield (
        f"""
        ### ✅ Analysis Complete!

        **Paper:** `{file_name}`

        Your structured research paper breakdown
        is ready below.

        **Powered by Gemini**
        """,
        result
    )


# ============================================================
# 7. DOWNLOAD HELPER
#    Save the analysis as a Markdown file
# ============================================================

def save_analysis(analysis_text):

    if not analysis_text or not analysis_text.strip():
        return None

    output_path = os.path.join(os.getcwd(), "paper_analysis.md")

    with open(output_path, "w", encoding="utf-8") as out_file:
        out_file.write(analysis_text)

    return output_path


# ============================================================
# 8. CREATE GRADIO APPLICATION
# ============================================================

with gr.Blocks(title="AI Research Paper Assistant") as research_app:

    gr.Markdown(
        """
        # 📄 AI Research Paper Assistant

        ### Upload a paper — get the summary, methodology and limitations

        **Gemini + Prompt Engineering + Gradio**
        """
    )

    with gr.Row():

        with gr.Column(scale=1):

            gr.Markdown("## 📤 Upload Paper")

            pdf_input = gr.File(
                label="📄 Research Paper (PDF only)",
                file_types=[".pdf"],
                file_count="single",
                type="filepath"
            )

            detail_level = gr.Dropdown(
                choices=["Quick Overview", "Standard", "In-Depth"],
                value="Standard",
                label="📊 Detail Level"
            )

            audience = gr.Dropdown(
                choices=[
                    "Undergraduate Student",
                    "Postgraduate Student",
                    "Researcher / Domain Expert",
                    "Non-Technical Reader"
                ],
                value="Postgraduate Student",
                label="🎓 Audience"
            )

            include_future_work = gr.Checkbox(
                label="🔭 Include Future Work section",
                value=True
            )

            with gr.Row():
                analyze_btn = gr.Button("🔍 Analyze Paper", variant="primary")
                clear_btn = gr.ClearButton(value="🗑️ Clear")

            download_btn = gr.Button("💾 Download Analysis (.md)")

            download_file = gr.File(label="📥 Your Analysis File", visible=True)

        with gr.Column(scale=2):

            gr.Markdown("## 🤖 Analysis Engine")

            status = gr.Markdown(
                """
                ### ⏳ Waiting for a Paper

                Upload a PDF on the left.

                Then click:

                **🔍 Analyze Paper**
                """
            )

            result = gr.Markdown(
                """
                ### 📄 Paper Analysis

                Your summary, methodology breakdown and
                limitations will appear here.
                """
            )

    gr.Markdown(
        """
        ---

        ### 🔄 Application Workflow

        **PDF Upload → Prompt Engineering → Gemini (multimodal PDF reading) → Structured Analysis**

        *AI analysis can misread tables, figures and equations.
        Always verify key numbers, claims and methodology
        details against the original paper before citing them.*
        """
    )

    analyze_btn.click(
        fn=research_assistant_ui,
        inputs=[pdf_input, detail_level, audience, include_future_work],
        outputs=[status, result]
    )

    download_btn.click(
        fn=save_analysis,
        inputs=[result],
        outputs=[download_file]
    )

    clear_btn.add([pdf_input, status, result, download_file])


# ============================================================
# 9. LAUNCH
# ============================================================

if __name__ == "__main__":
    research_app.launch()