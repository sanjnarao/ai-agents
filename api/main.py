import os, tempfile, zipfile, json, subprocess, glob, re, shutil
from pathlib import Path
from typing import List, Optional

import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---- Config ----
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
# Adjust to your analyzer build output:
ANALYZER_DLL = os.environ.get(
    "ANALYZER_DLL",
    str(Path(__file__).resolve().parents[1] / "analyzer" / "SolutionAnalyzer" / "bin" / "Release" / "net8.0" / "SolutionAnalyzer.dll")
)

app = FastAPI(title="CodeDoc Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def find_sln(root: Path) -> Optional[Path]:
    for p in root.rglob("*.sln"):
        return p
    return None

def flatten_semantic_json(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for item in data:
        lines.append(f"Project: {item.get('Project','')}")
        lines.append(f"File: {item.get('File','')}")
        classes = item.get("Classes") or []
        methods = item.get("Methods") or []
        comments = item.get("Comments") or []
        if classes: lines.append(f"  Classes: {', '.join(classes)}")
        if methods: lines.append(f"  Methods: {', '.join(methods)}")
        if comments: lines.append(f"  Comments: {' | '.join(comments)}")
        lines.append("")
    return "\n".join(lines)

def basic_chunk(text: str, max_chars=1500):
    parts = re.split(r"\n{2,}|(?m)^#+\s", text)
    out, buf = [], ""
    for part in parts:
        if len(buf) + len(part) + 2 <= max_chars:
            buf += ("\n\n" + part) if buf else part
        else:
            if buf: out.append(buf)
            buf = part
    if buf: out.append(buf)
    return [c.strip() for c in out if c.strip()]

def pick_top_k(query_text: str, doc_texts: List[str], k: int = 6) -> List[str]:
    # Tiny lexical relevance: prefer chunks sharing terms
    # (Replace with TF-IDF/embeddings later if you like)
    q_terms = set(re.findall(r"\b\w{3,}\b", query_text.lower()))
    scored = []
    for t in doc_texts:
        terms = set(re.findall(r"\b\w{3,}\b", t.lower()))
        score = len(q_terms & terms)
        scored.append((score, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:k]]

def call_ollama(prompt: str) -> str:
    r = requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
                      timeout=600)
    r.raise_for_status()
    obj = r.json()
    return obj.get("response", "")

@app.post("/api/analyze")
async def analyze(
    solution_zip: UploadFile = File(..., description="Zip containing .sln + all projects"),
    extra_docs: Optional[List[UploadFile]] = File(default=None, description="Optional additional docs (md/txt/pdf/docx)")
):
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        # Save and extract zip
        zpath = tmpdir / solution_zip.filename
        zpath.write_bytes(await solution_zip.read())
        try:
            with zipfile.ZipFile(zpath, "r") as zf:
                zf.extractall(tmpdir)
        except zipfile.BadZipFile:
            raise HTTPException(400, detail="Invalid ZIP file")

        sln = find_sln(tmpdir)
        if not sln:
            raise HTTPException(400, detail="No .sln found inside zip")

        # Run analyzer (writes semantic_summary.json in cwd)
        try:
            proc = subprocess.run(
                ["dotnet", ANALYZER_DLL, str(sln)],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=600
            )
        except FileNotFoundError:
            raise HTTPException(500, detail="dotnet SDK not found on PATH")
        if proc.returncode != 0:
            raise HTTPException(500, detail=f"Analyzer failed: {proc.stderr}")

        summary_json = tmpdir / "semantic_summary.json"
        if not summary_json.exists():
            raise HTTPException(500, detail="semantic_summary.json not produced by analyzer")

        sem_text = flatten_semantic_json(summary_json)

        # Gather extra docs (optional)
        doc_chunks = []
        if extra_docs:
            for up in extra_docs:
                name = (up.filename or "").lower()
                b = await up.read()
                # Simple handling: md/txt only for brevity
                if name.endswith(".md") or name.endswith(".txt"):
                    doc_chunks.extend(basic_chunk(b.decode("utf-8", errors="ignore")))
                else:
                    # ignore binary types in this minimal prototype
                    pass

        selected = pick_top_k(sem_text, doc_chunks, k=8) if doc_chunks else []

        prompt = f"""You are a technical writer.
        Goal: Produce business-facing documentation (audience: PMs, QA, leadership).

        Existing documentation snippets (authoritative, prefer these when conflicts arise):
        {("\n\n---\n".join(selected)) if selected else "(no extra docs provided)"}

        Extracted semantic summary (from code analysis):
        ---BEGIN SEMANTIC SUMMARY---
        {sem_text}
        ---END SEMANTIC SUMMARY---

        Tasks:
        1) Write a cohesive overview: problem solved, core capabilities, key modules, and business value.
        2) Resolve conflicts in favor of the existing snippets (if any).
        3) List unclear areas under "Open Questions".
        4) Keep it concise and executive-friendly (~800–1200 words).
        """

        try:
            md = call_ollama(prompt)
        except Exception as e:
            raise HTTPException(500, detail=f"Ollama call failed: {e}")

        return JSONResponse({"markdown": md})
