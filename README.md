# AI Lecture Summarizer

AI Lecture Summarizer turns a pasted lecture transcript or class notes into a
structured study pack. It uses Streamlit for the web interface and Google's
official `google-genai` Python SDK to ask Gemini for JSON-structured material.

## Features

- Short, medium, or detailed lecture summaries.
- Organized notes, key concepts, and source-labeled definitions.
- Five interactive multiple-choice questions with scoring and explanations.
- Short-answer revision questions and five revealable flashcards.
- A revision sheet with facts, formulas, definitions, takeaways, and an exam
  reminder list.
- TXT summary and complete Markdown downloads.
- Example lecture, approximate word count, reset control, and transcript-size
  validation.
- Upload text-based PDFs for local text extraction before study-pack generation.
- No database. Your transcript is sent to the Gemini API; this app does not
  work offline.

## Technology

- Python 3.10 or newer
- Streamlit 1.66.1
- Google Gen AI SDK (`google-genai` 2.33.0), using Gemini 3.5 Flash-Lite for
  lower-latency study material generation
- Pydantic 2.14.1
- python-dotenv 1.2.4
- pypdf 6.21.4 for local text-based PDF extraction

The app uses Google's recommended Interactions API and structured JSON output
with Pydantic validation. It requests minimal reasoning and caps generated
output to keep response times and study packs manageable. Very long transcripts
still take longer to process because Gemini must read the supplied text.

## Project structure

```text
ai-lecture-summarizer/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── modules/
│   ├── __init__.py
│   ├── ai_service.py
│   ├── pdf_service.py
│   └── prompts.py
└── tests/
    ├── __init__.py
    └── test_ai_service.py
```

## Setup on Windows

1. Install Python 3.10+ and make sure `python` is available in PowerShell.
2. Obtain an API key from [Google AI Studio](https://aistudio.google.com/apikey).
   Keep the key private. API availability and usage limits depend on your
   Google account and region.
3. Open PowerShell in the project folder and create/activate a virtual
   environment:

   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```

4. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

5. Create a local `.env` file from the example and add your key:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   Set `GEMINI_API_KEY` to your own key, without committing `.env` or sharing
   its contents. `.gitignore` excludes it from Git.

6. Start the app:

   ```powershell
   streamlit run app.py
   ```

   Streamlit prints a local URL (normally `http://localhost:8501`) to open in
   your browser.

## Test the project

With the dependencies installed, run:

```powershell
python -m unittest discover -s tests -v
```

The tests cover transcript validation, PDF text extraction and upload,
missing configuration, structured response parsing, quiz scoring, Markdown
export, and the example/reset UI flow. They do not make a paid or live Gemini
API request.

## Try the example

Select **Load example transcript** in the app to fill this sample:

> Today we are introducing binary search, an algorithm for finding a target
> value in a sorted list. We compare the target with the middle element. If
> they match, the search is complete. If the target is smaller, we continue in
> the left half; if it is larger, we continue in the right half. Each
> comparison removes about half of the remaining elements, so the time
> complexity is O(log n). Binary search requires the data to be sorted. For
> example, in the sorted list [2, 5, 8, 12, 16, 23, 38], to find 16 we first
> check 12, then search the right half and check 23, then check 16. The
> algorithm uses constant extra space in its iterative form.

Choose **Computer Science** and **Medium**, then click **Generate study
material**. An example of a transcript-grounded summary could be:

> Binary search locates a target in sorted data by comparing it with the middle
> element and repeatedly continuing in the relevant half. This reduces the
> search area by about half per comparison, giving O(log n) time complexity.
> Its iterative form uses constant extra space.

Generated wording may vary. Review the definitions' source labels and check
the output against your lecture notes.

## Troubleshooting

- **Missing API key:** confirm `.env` is in the same folder as `app.py` and
  contains `GEMINI_API_KEY=your_actual_key`. Restart Streamlit after changing
  it. Never paste the key into the app's transcript field.
- **Invalid or permission-denied key:** create/check the key in Google AI
  Studio and confirm Gemini API access is enabled for it.
- **Quota or rate limit:** wait before retrying and check current quota and
  usage limits in Google AI Studio.
- **Connection error:** check internet access and try again.
- **Transcript too long:** reduce the input to 30,000 characters or fewer.
- **PDF has no selectable text:** scanned/image-only PDFs need OCR before
  upload. Password-protected PDFs must be unlocked first. PDF uploads are
  limited to 20 MB, 100 pages, and 30,000 extracted characters.
- **Malformed model response:** retry; the app validates the required sections
  and reports responses it cannot safely display.
- **PowerShell activation blocked:** use the Windows Python launcher from the
  active environment by calling `.venv\Scripts\python.exe -m pip install -r
  requirements.txt` and `.venv\Scripts\python.exe -m streamlit run app.py`.

## How it works

```text
Student
   ↓ transcript + subject + summary length
Streamlit UI (app.py)
   ↓ validated request
Python AI Service (modules/ai_service.py + prompts.py)
   ↓ structured JSON request
Gemini API
   ↓ JSON response
Pydantic validation → study tabs, quiz, flashcards, downloads
```

The prompt asks Gemini to use the transcript as the source for lecture facts.
Potentially useful context not found in the transcript must be labeled
supplementary, and unexplained terms are identified instead of guessed. This
reduces unsupported claims but does not guarantee that generated content is
perfect; students should verify it.

## Two-minute classroom presentation

“Hello everyone. My project is AI Lecture Summarizer, a small study dashboard
that turns lecture transcripts into organized revision material.

The student can paste notes or load the built-in binary-search example, pick a
subject and summary length, and generate a study pack. The Streamlit interface
passes the transcript and choices to a separate Python service. That service
uses Google's official Gemini SDK and requests structured JSON. Pydantic
checks the response before the app displays it.

The study pack includes a summary, organized notes, key concepts, definitions,
five multiple-choice questions, short-answer revision questions, five
flashcards, and an exam revision sheet. The quiz gives a score and
explanations, and each flashcard answer can be revealed on demand. Students
can download the summary as plain text and all the material as Markdown.

An important design choice is grounding. The prompt tells Gemini not to add
lecture-specific facts that are not supported by the transcript. If a
definition needs context beyond the lecture, the app labels it supplementary.
This is an AI aid, so students should still review the generated material.

The app requires an internet connection and a Gemini API key stored locally
in a `.env` file. The key is not shown in the interface or placed in source
code, and the project does not use a database. Thank you.”

## Likely professor questions

1. **How does the app communicate with Gemini?**  
   The Python service uses Google's official `google-genai` package and its
   Interactions API.
2. **How do you make the response predictable?**  
   Gemini is asked for JSON matching a Pydantic schema, and Pydantic validates
   the response before display.
3. **How do you reduce hallucinations?**  
   The prompt restricts lecture facts to the supplied transcript and labels
   supplementary explanations. AI output still needs human review.
4. **Where is the API key stored?**  
   In a local `.env` file, excluded from Git by `.gitignore`; it is not
   hardcoded or shown in the interface.
5. **Does it work without the internet?**  
   No. The interface runs locally, but study-material generation calls the
   cloud Gemini API.

## Future enhancements

- Add transcript file uploads and speech-to-text for recorded lectures.
- Let students save and organize study packs by course with a privacy-aware
  local database.
- Add spaced-repetition scheduling and progress tracking for quizzes and
  flashcards.
